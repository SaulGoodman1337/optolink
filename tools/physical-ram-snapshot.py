#!/opt/optolink/venv/bin/python
"""Guarded read-only snapshot of the M16C-shaped 0x0400..0x53ff Physical_READ space.

Fixed range and function only. No write path and no arbitrary address option.
Two passes are captured so dynamic bytes can be separated from stable state.
"""
from __future__ import annotations
import argparse, ast, fcntl, json, os, signal, subprocess, time
from pathlib import Path

SPLITTER="optolink-splitter.service"
PARTY="optolink-party-emulator.service"
SCHEDULE="optolink-schedule-manager.service"
SETTINGS=Path("/opt/optolink/settings_ini.py")
LOCK="/run/lock/physical-ram-snapshot.lock"
RAM_START=0x0400
RAM_END=0x53FF
CHUNK=32
IDENT=(0x00F8,2)
HISTORY=(0x7507,0x7510,0x7519,0x7522,0x752B,0x7534,0x753D,0x7546,0x754F,0x7558)
MONITORS=((0x5738,1),(0xA132,29),*((a,9) for a in HISTORY))
ABORT=(signal.SIGINT,signal.SIGTERM,signal.SIGHUP)

class ProbeError(RuntimeError): pass

def checksum(body:bytes)->int:
    return sum(body[1:]) & 0xFF

def frame(function:int,address:int,length:int)->bytes:
    if function not in (0x01,0x03):
        raise ProbeError("blocked non-read function")
    if function==0x03 and not (RAM_START <= address <= RAM_END and length==CHUNK and address+length-1<=RAM_END):
        raise ProbeError("blocked Physical_READ outside fixed RAM range")
    allowed={(0x01,*IDENT), *((0x01,a,l) for a,l in MONITORS)}
    if function==0x01 and (function,address,length) not in allowed:
        raise ProbeError("blocked Virtual_READ outside monitor allowlist")
    b=bytes((0x41,0x05,0x00,function,address>>8,address&0xFF,length))
    return b+bytes((checksum(b),))

def read_port()->str:
    vals={}
    tree=ast.parse(SETTINGS.read_text(encoding="utf-8-sig"))
    for n in tree.body:
        if isinstance(n,ast.Assign):
            for t in n.targets:
                if isinstance(t,ast.Name) and t.id in {"port_optolink","port_vitoconnect","vs1protocol"}:
                    vals[t.id]=ast.literal_eval(n.value)
    if vals.get("vs1protocol") is not True or vals.get("port_vitoconnect") is not None:
        raise ProbeError("require permanent VS1 and no vitoconnect")
    p=vals.get("port_optolink")
    if not isinstance(p,str) or not p.startswith("/dev/"):
        raise ProbeError("invalid serial path")
    return p

def svc(cmd:str,unit:str):
    p=subprocess.run(["sudo","-n","/usr/bin/systemctl",cmd,unit],capture_output=True,text=True)
    if p.returncode: raise ProbeError(f"systemctl {cmd} {unit}: {p.stderr.strip()}")

def active(unit:str)->bool:
    return subprocess.run(["systemctl","is-active","--quiet",unit]).returncode==0

class Wire:
    def __init__(self,port,log):
        import serial
        self.s=serial.Serial(port=port,baudrate=4800,bytesize=8,parity="E",stopbits=2,
            timeout=.05,write_timeout=2,xonxoff=False,rtscts=False,dsrdtr=False,exclusive=True)
        self.log=log
    def close(self): self.s.close()
    def send(self,b:bytes):
        if self.s.write(b)!=len(b): raise ProbeError("partial serial write")
    def exact(self,n:int,timeout=3.0)->bytes:
        end=time.monotonic()+timeout; out=bytearray()
        while len(out)<n and time.monotonic()<end: out.extend(self.s.read(n-len(out)))
        if len(out)!=n: raise ProbeError(f"timeout expected {n}, got {len(out)}")
        return bytes(out)
    def wait_control(self,want:int,timeout=5.0):
        end=time.monotonic()+timeout; stray=bytearray()
        while time.monotonic()<end:
            b=self.s.read(1)
            if not b: continue
            if b==bytes((want,)):
                if stray: self.log("INIT_STRAY="+stray.hex())
                return
            if want==0x05 and b in (b"\x06",b"\x15"): continue
            if want==0x06 and b==b"\x05": continue
            stray.extend(b)
            if len(stray)>64: raise ProbeError("too much stray serial data during init")
        raise ProbeError(f"timeout control {want:02x}; stray={stray.hex()}")
    def enter(self):
        time.sleep(1.0)
        self.s.reset_input_buffer()
        self.send(b"\x04"); self.wait_control(0x05)
        self.send(b"\x16\x00\x00"); self.wait_control(0x06)
    def leave(self):
        try: self.send(b"\x04")
        except Exception: pass
    def request(self,function,address,length):
        req=frame(function,address,length); self.send(req)
        first=self.exact(1)
        if first==b"\x15": return {"status":"NACK","data":b"","command":None,"address":None,"request":req}
        if first!=b"\x06": raise ProbeError("expected ACK/NACK, got "+first.hex())
        h=self.exact(2)
        if h[0]!=0x41 or not 1<=h[1]<=64: raise ProbeError("bad P300 header")
        msg=h+self.exact(h[1]+1)
        if checksum(msg[:-1])!=msg[-1]: raise ProbeError("bad P300 checksum")
        typ=msg[2]&0x0F
        status="SUCCESS" if typ==1 else ("ERROR" if typ==3 else f"TYPE_{typ:02x}")
        result={"status":status,"command":msg[3],"address":int.from_bytes(msg[4:6],"big"),
                "data":msg[7:-1],"request":req,"response":msg}
        self.send(b"\x06")
        return result

def monitor_snapshot(w:Wire):
    out={}
    for a,l in MONITORS:
        r=w.request(0x01,a,l)
        if r["status"]!="SUCCESS" or r["address"]!=a: raise ProbeError(f"monitor failed 0x{a:04x}")
        out[a]=r["data"]
    return out

def guard_current(w:Wire):
    for a,l in ((0x5738,1),(0xA132,29)):
        r=w.request(0x01,a,l)
        if r["status"]!="SUCCESS": raise ProbeError(f"guard read failed 0x{a:04x}")
        if a==0x5738 and r["data"]!=b"\x00": raise ProbeError("GFA current fault became nonzero")
        if a==0xA132 and (len(r["data"])!=29 or r["data"][28]!=0): raise ProbeError("current alarm became nonzero")

def full_pass(w:Wire,pass_no:int,log):
    image=bytearray(); self_hits=[]; short_hits=[]
    blocks=(RAM_END-RAM_START+1)//CHUNK
    for i,a in enumerate(range(RAM_START,RAM_END+1,CHUNK)):
        r=w.request(0x03,a,CHUNK)
        if r["status"]!="SUCCESS" or r["command"]!=0x03 or r["address"]!=a or len(r["data"])!=CHUNK:
            raise ProbeError(f"Physical_READ failed at 0x{a:04x}: {r['status']}")
        data=r["data"]; image.extend(data)
        if r["request"] in data: self_hits.append(a)
        sig=bytes((0x00,0x03,a>>8,a&0xFF,CHUNK))
        if sig in data: short_hits.append(a)
        if (i+1)%32==0:
            log(f"PASS={pass_no} progress={i+1}/{blocks} address=0x{a:04x}")
            guard_current(w)
    return bytes(image),self_hits,short_hits

def page_diff(a:bytes,b:bytes):
    rows=[]
    for off in range(0,len(a),0x100):
        aa=a[off:off+0x100]; bb=b[off:off+0x100]
        rows.append({"address":RAM_START+off,"changed":sum(x!=y for x,y in zip(aa,bb)),"size":len(aa)})
    return rows

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--execute",action="store_true"); ap.add_argument("--self-test",action="store_true")
    args=ap.parse_args()
    if args.self_test:
        assert RAM_END-RAM_START+1==0x5000
        assert frame(0x03,0x0400,32).hex()=="410500030400202c"
        assert frame(0x03,0x53e0,32).hex()=="4105000353e0205b"
        try: frame(0x03,0x53f0,32); raise AssertionError("range gate failed")
        except ProbeError: pass
        print("SELFTEST=PASS"); return 0
    if not args.execute:
        print("plan only; use --execute for the fixed read-only 0x0400..0x53ff two-pass snapshot"); return 0
    lock_fd=os.open(LOCK,os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600); fcntl.flock(lock_fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
    log=lambda s: print(time.strftime("%H:%M:%S"),s,flush=True)
    states={u:active(u) for u in (SCHEDULE,PARTY,SPLITTER)}
    if not states[SPLITTER]: raise ProbeError("splitter not running before snapshot")
    changed=[]; w=None; prev={sig:signal.getsignal(sig) for sig in ABORT}
    for sig in ABORT: signal.signal(sig,lambda s,f: (_ for _ in ()).throw(ProbeError(f"signal {s}")))
    stamp=time.strftime("%Y%m%d-%H%M%S")
    try:
        for u in (SCHEDULE,PARTY,SPLITTER):
            if states[u]: svc("stop",u); changed.append(u); log("STOPPED "+u)
        w=Wire(read_port(),log); w.enter()
        ident=w.request(0x01,*IDENT)
        if ident["status"]!="SUCCESS" or ident["data"]!=bytes.fromhex("20 c2"): raise ProbeError("20C2 identity failed")
        base=monitor_snapshot(w)
        if base[0x5738]!=b"\x00" or base[0xA132][28]!=0: raise ProbeError("baseline active fault")
        p1,h1,s1=full_pass(w,1,log)
        guard_current(w)
        p2,h2,s2=full_pass(w,2,log)
        end=monitor_snapshot(w)
        if end[0x5738]!=b"\x00" or end[0xA132][28]!=0: raise ProbeError("final active fault")
        for a in HISTORY:
            if end[a]!=base[a]: raise ProbeError(f"fault history changed at 0x{a:04x}")
        out1=Path("/tmp")/f"physical-ram-{stamp}-pass1.bin"; out2=Path("/tmp")/f"physical-ram-{stamp}-pass2.bin"
        out1.write_bytes(p1); out2.write_bytes(p2)
        changed_bytes=sum(x!=y for x,y in zip(p1,p2))
        stable_payload=p1[0x53F0-RAM_START:0x5400-RAM_START]
        dup1=[]
        start=0
        while True:
            pos=p1.find(stable_payload,start)
            if pos<0: break
            dup1.append(RAM_START+pos); start=pos+1
        known=(0x00F8,0x5738,0xA132,*HISTORY)
        addr_hits={}
        for a in known:
            be=a.to_bytes(2,"big"); le=a.to_bytes(2,"little")
            addr_hits[f"0x{a:04x}"]={"be":p2.count(be),"le":p2.count(le)}
        report={"ram_start":RAM_START,"ram_end":RAM_END,"size":len(p1),"chunk":CHUNK,
                "changed_bytes":changed_bytes,"stable_bytes":len(p1)-changed_bytes,
                "self_frame_hits_pass1":[f"0x{x:04x}" for x in h1],"self_frame_hits_pass2":[f"0x{x:04x}" for x in h2],
                "short_request_hits_pass1":[f"0x{x:04x}" for x in s1],"short_request_hits_pass2":[f"0x{x:04x}" for x in s2],
                "53f0_payload_occurrences_pass1":[f"0x{x:04x}" for x in dup1],"known_address_bytepair_counts_pass2":addr_hits,
                "page_diff":page_diff(p1,p2),"pass1":str(out1),"pass2":str(out2)}
        outj=Path("/tmp")/f"physical-ram-{stamp}-report.json"; outj.write_text(json.dumps(report,indent=2)+"\n")
        log(f"SNAPSHOT_PASS changed_bytes={changed_bytes}/{len(p1)}")
        log("SELF_FRAME_HITS="+",".join(report["self_frame_hits_pass2"]) if report["self_frame_hits_pass2"] else "SELF_FRAME_HITS=none")
        log("53F0_DUPLICATES="+",".join(report["53f0_payload_occurrences_pass1"]))
        log("PASS1="+str(out1)); log("PASS2="+str(out2)); log("REPORT="+str(outj)); log("FAULT_GUARD=PASS")
        w.leave(); return 0
    finally:
        if w:
            try: w.close()
            except Exception: pass
        for u in reversed(changed):
            try: svc("start",u); log("RESTORED "+u)
            except Exception as e: log("RESTORE_ERROR "+str(e))
        for sig,h in prev.items(): signal.signal(sig,h)
        os.close(lock_fd)

if __name__=="__main__": raise SystemExit(main())