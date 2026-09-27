#!/opt/optolink/venv/bin/python
"""One-target read-only Physical_READ probe with fault-history guard.

Only fixed source-backed VitoTest and architecture-discriminator addresses are selectable.
No write function or arbitrary address option exists.
"""
from __future__ import annotations
import argparse, ast, fcntl, os, signal, subprocess, sys, time
from pathlib import Path

SPLITTER="optolink-splitter.service"
PARTY="optolink-party-emulator.service"
SCHEDULE="optolink-schedule-manager.service"
SETTINGS=Path("/opt/optolink/settings_ini.py")
TARGETS={"sysmode":(0x0004,4),"bd":(0x00BD,1),"2f":(0x002F,1),"3f":(0x003F,1),"9b":(0x009B,3),
         "dma0":(0x0020,16),"dma1":(0x0030,16),"uart01":(0x03A0,16),"dma_sel":(0x03B0,16),
         "ram0400":(0x0400,16),"ram53f0":(0x53F0,16),
         "df_f000":(0xF000,16),"df_fff0":(0xFFF0,16)}
COMPARE_TARGETS={"ram0400":(0x0400,16),"ram53f0":(0x53F0,16)}
HISTORY=(0x7507,0x7510,0x7519,0x7522,0x752B,0x7534,0x753D,0x7546,0x754F,0x7558)
MONITORS=((0x5738,1),(0xA132,29),*((a,9) for a in HISTORY))
IDENT=(0x00F8,2)
ABORT=(signal.SIGINT,signal.SIGTERM,signal.SIGHUP)

class ProbeError(RuntimeError): pass

def checksum(body:bytes)->int:
    return sum(body[1:]) & 0xFF
def frame(function:int,address:int,length:int)->bytes:
    if function not in (0x01,0x03):
        raise ProbeError("blocked non-read function")
    allowed={(0x01,*IDENT), *((0x01,a,l) for a,l in MONITORS)}
    allowed |= {(0x01,a,l) for a,l in COMPARE_TARGETS.values()}
    allowed |= {(0x03,a,l) for a,l in TARGETS.values()}
    if (function,address,length) not in allowed:
        raise ProbeError(f"blocked request 0x{function:02x}/0x{address:04x}/{length}")
    b=bytes((0x41,0x05,0x00,function,address>>8,address&0xFF,length))
    return b+bytes((checksum(b),))

def read_port_setting()->str:
    values={}
    tree=ast.parse(SETTINGS.read_text(encoding="utf-8-sig"))
    for n in tree.body:
        if isinstance(n,ast.Assign):
            for t in n.targets:
                if isinstance(t,ast.Name) and t.id in {"port_optolink","port_vitoconnect","vs1protocol"}:
                    values[t.id]=ast.literal_eval(n.value)
    if values.get("vs1protocol") is not True or values.get("port_vitoconnect") is not None:
        raise ProbeError("production settings are not permanent VS1/no-vitoconnect")
    p=values.get("port_optolink")
    if not isinstance(p,str) or not p.startswith("/dev/"):
        raise ProbeError("invalid serial path")
    return p

def svc(cmd:str,unit:str):
    p=subprocess.run(["sudo","-n","/usr/bin/systemctl",cmd,unit],capture_output=True,text=True)
    if p.returncode: raise ProbeError(f"systemctl {cmd} {unit}: {p.stderr.strip()}")
def active(unit:str)->bool:
    p=subprocess.run(["systemctl","is-active","--quiet",unit])
    return p.returncode==0

class Wire:
    def __init__(self,port,log):
        import serial
        self.s=serial.Serial(port=port,baudrate=4800,bytesize=8,parity="E",stopbits=2,
            timeout=.05,write_timeout=2,xonxoff=False,rtscts=False,dsrdtr=False,exclusive=True)
        self.log=log
    def close(self): self.s.close()
    def send(self,b:bytes):
        self.log("TX "+b.hex(" "))
        if self.s.write(b)!=len(b): raise ProbeError("partial serial write")
    def exact(self,n:int,timeout=2.5)->bytes:
        end=time.monotonic()+timeout; out=bytearray()
        while len(out)<n and time.monotonic()<end: out.extend(self.s.read(n-len(out)))
        if out: self.log("RX "+out.hex(" "))
        if len(out)!=n: raise ProbeError(f"timeout expected {n}, got {len(out)}")
        return bytes(out)
    def control(self,v:int,timeout=5):
        end=time.monotonic()+timeout
        while time.monotonic()<end:
            b=self.s.read(1)
            if not b: continue
            self.log("RX control "+b.hex(" "))
            if b==bytes((v,)): return
            if v==0x05 and b in (b"\x06",b"\x15"): continue
            if v==0x06 and b==b"\x05": continue
            raise ProbeError(f"unexpected control {b.hex()} expected {v:02x}")
        raise ProbeError(f"timeout control {v:02x}")
    def enter(self):
        if self.s.in_waiting: self.log("RX stale "+self.s.read(self.s.in_waiting).hex(" "))
        self.send(b"\x04"); self.control(0x05)
        self.send(b"\x16\x00\x00"); self.control(0x06)
    def leave(self): self.send(b"\x04")
    def request(self,function,address,length):
        req=frame(function,address,length); self.send(req)
        first=self.exact(1)
        if first==b"\x15": return {"status":"NACK","data":b"","command":None,"address":None}
        if first!=b"\x06": raise ProbeError("expected ACK/NACK")
        h=self.exact(2)
        if h[0]!=0x41 or not 1<=h[1]<=64: raise ProbeError("bad P300 header")
        msg=h+self.exact(h[1]+1)
        if checksum(msg[:-1])!=msg[-1]: raise ProbeError("bad P300 checksum")
        mtype=msg[2]&0x0F
        status="SUCCESS" if mtype==1 else ("ERROR" if mtype==3 else f"TYPE_{mtype:02x}")
        result={"status":status,"command":msg[3],"address":int.from_bytes(msg[4:6],"big"),
            "data":msg[7:-1],"frame":msg}
        self.send(b"\x06")
        return result

def snapshot(w:Wire,log):
    out={}
    for address,length in MONITORS:
        r=w.request(0x01,address,length)
        if r["status"]!="SUCCESS" or r["address"]!=address:
            raise ProbeError(f"monitor failed at 0x{address:04x}: {r['status']}")
        out[address]=r["data"]
        log(f"MONITOR 0x{address:04x} {r['data'].hex()}")
    return out
def snapshot_clean(base,after)->tuple[bool,str]:
    if after[0x5738] != b"\x00": return False,"current GFA fault nonzero"
    if len(after[0xA132])!=29 or after[0xA132][28] != 0: return False,"current alarm code nonzero"
    for a in HISTORY:
        if after[a] != base[a]: return False,f"fault-history changed at 0x{a:04x}"
    return True,"clean"

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--target",choices=TARGETS,required=True)
    ap.add_argument("--self-test",action="store_true")
    ap.add_argument("--compare",action="store_true",help="for ram0400/ram53f0: two Virtual_READ and two Physical_READ samples")
    args=ap.parse_args()
    if args.self_test:
        for k,(a,l) in TARGETS.items():
            assert frame(0x03,a,l)[3]==0x03
        print("SELFTEST=PASS"); return 0
    log=lambda s: print(time.strftime("%H:%M:%S"),s,flush=True)
    port=read_port_setting()
    states={u:active(u) for u in (SCHEDULE,PARTY,SPLITTER)}
    if not states[SPLITTER]: raise ProbeError("splitter not running before probe")
    changed=[]; w=None
    previous={sig:signal.signal(sig,lambda s,f: (_ for _ in ()).throw(ProbeError(f"signal {s}"))) for sig in ABORT}
    try:
        for u in (SCHEDULE,PARTY,SPLITTER):
            if states[u]: svc("stop",u); changed.append(u); log("STOPPED "+u)
        w=Wire(port,log)
        w.enter()
        ident=w.request(0x01,*IDENT)
        if ident["status"]!="SUCCESS" or ident["data"]!=bytes.fromhex("20 c2"):
            raise ProbeError("20C2 identity control failed")
        base=snapshot(w,log)
        if base[0x5738]!=b"\x00" or base[0xA132][28]!=0:
            raise ProbeError("baseline has active fault")
        address,length=TARGETS[args.target]
        if args.compare:
            if args.target not in COMPARE_TARGETS:
                raise ProbeError("--compare only allowed for ram0400/ram53f0")
            samples=[]
            for n,function in enumerate((0x01,0x03,0x03,0x01),1):
                label="Virtual_READ" if function==0x01 else "Physical_READ"
                log(f"COMPARE n={n} {label} function=0x{function:02x} address=0x{address:04x} len={length}")
                rr=w.request(function,address,length)
                log(f"COMPARE_RESULT n={n} status={rr['status']} data={rr['data'].hex()}")
                samples.append((function,rr))
                if function==0x03 and rr["status"]!="SUCCESS":
                    raise ProbeError(f"Physical_READ compare request failed n={n}")
                if function==0x01 and rr["status"] not in ("SUCCESS","ERROR","NACK"):
                    raise ProbeError(f"unexpected Virtual_READ outcome n={n}: {rr['status']}")
                time.sleep(0.15)
            v=[r for f,r in samples if f==0x01]
            ph=[r for f,r in samples if f==0x03]
            v_same=(v[0]["status"],v[0]["data"])==(v[1]["status"],v[1]["data"])
            ph_same=ph[0]["data"]==ph[1]["data"]
            cross_equal=(v[0]["status"]=="SUCCESS" and v[0]["data"]==ph[0]["data"])
            log(f"COMPARE_SUMMARY virtual_repeat_equal={v_same} virtual_statuses={v[0]['status']},{v[1]['status']} physical_repeat_equal={ph_same} cross_equal={cross_equal}")
        else:
            log(f"TEST Physical_READ 0x03 address=0x{address:04x} len={length}")
            test=w.request(0x03,address,length)
            log(f"TEST_RESULT status={test['status']} data={test['data'].hex()}")
        after=snapshot(w,log)
        ok,reason=snapshot_clean(base,after)
        log("FAULT_GUARD="+("PASS" if ok else "FAIL")+" "+reason)
        w.leave()
        return 0 if ok else 2
    finally:
        if w:
            try: w.close()
            except Exception: pass
        for u in reversed(changed):
            try: svc("start",u); log("RESTORED "+u)
            except Exception as e: log("RESTORE_ERROR "+str(e))
        for sig,h in previous.items(): signal.signal(sig,h)

if __name__=="__main__":
    raise SystemExit(main())