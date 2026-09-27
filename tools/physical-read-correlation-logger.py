#!/opt/optolink/venv/bin/python
"""Bounded read-only P300 correlation logger for Physical_READ 0x0400/0x53F0.

Fixed targets only. No arbitrary address/function arguments and no write path.
"""
from __future__ import annotations
import argparse, ast, csv, os, signal, subprocess, time
from pathlib import Path

SPLITTER="optolink-splitter.service"
PARTY="optolink-party-emulator.service"
SCHEDULE="optolink-schedule-manager.service"
SETTINGS=Path("/opt/optolink/settings_ini.py")
IDENT=(0x01,0x00F8,2)
PHYS=(("phys0400",0x03,0x0400,16),("phys53f0",0x03,0x53F0,16))
OVERLAP=((0x03,0x0408,8),(0x03,0x53F8,8))
VIRT=(("kessel",0x01,0x0810,2),("mod",0x01,0xA305,1),
      ("setpoint",0x01,0xA307,2),("cfdm",0x01,0xA38F,2),
      ("gfa",0x01,0x55D3,9))
HISTORY=(0x7507,0x7510,0x7519,0x7522,0x752B,0x7534,0x753D,0x7546,0x754F,0x7558)
MONITORS=((0x5738,1),(0xA132,29),*((a,9) for a in HISTORY))
ABORT=(signal.SIGINT,signal.SIGTERM,signal.SIGHUP)
ALLOWED={(f,a,l) for _,f,a,l in (*PHYS,*VIRT)}
ALLOWED|=set(OVERLAP)
ALLOWED|={IDENT}
ALLOWED|={(0x01,a,l) for a,l in MONITORS}

class ProbeError(RuntimeError): pass

def checksum(b:bytes)->int: return sum(b[1:]) & 0xFF

def frame(function,address,length):
    if (function,address,length) not in ALLOWED:
        raise ProbeError(f"blocked request {function:02x}/{address:04x}/{length}")
    b=bytes((0x41,0x05,0x00,function,address>>8,address&255,length))
    return b+bytes((checksum(b),))
def settings_port():
    vals={}
    tree=ast.parse(SETTINGS.read_text(encoding="utf-8-sig"))
    for n in tree.body:
        if isinstance(n,ast.Assign):
            for t in n.targets:
                if isinstance(t,ast.Name) and t.id in {"port_optolink","port_vitoconnect","vs1protocol"}:
                    vals[t.id]=ast.literal_eval(n.value)
    if vals.get("vs1protocol") is not True or vals.get("port_vitoconnect") is not None:
        raise ProbeError("require permanent VS1 and no vitoconnect forwarding")
    p=vals.get("port_optolink")
    if not isinstance(p,str) or not p.startswith("/dev/"): raise ProbeError("invalid port")
    return p

def active(unit):
    return subprocess.run(["systemctl","is-active","--quiet",unit]).returncode==0

def svc(cmd,unit):
    p=subprocess.run(["sudo","-n","/usr/bin/systemctl",cmd,unit],capture_output=True,text=True)
    if p.returncode: raise ProbeError(f"systemctl {cmd} {unit}: {p.stderr.strip()}")

class Wire:
    def __init__(self,port):
        import serial
        self.s=serial.Serial(port=port,baudrate=4800,bytesize=8,parity="E",stopbits=2,
            timeout=.05,write_timeout=2,xonxoff=False,rtscts=False,dsrdtr=False,exclusive=True)
    def close(self): self.s.close()
    def send(self,b):
        if self.s.write(b)!=len(b): raise ProbeError("partial serial write")
    def exact(self,n,timeout=2.5):
        end=time.monotonic()+timeout; out=bytearray()
        while len(out)<n and time.monotonic()<end: out.extend(self.s.read(n-len(out)))
        if len(out)!=n: raise ProbeError(f"timeout expected={n} got={len(out)}")
        return bytes(out)
    def control(self,want,timeout=5):
        end=time.monotonic()+timeout
        while time.monotonic()<end:
            b=self.s.read(1)
            if not b: continue
            if b==bytes((want,)): return
            if want==5 and b in (b"\x06",b"\x15"): continue
            if want==6 and b==b"\x05": continue
            raise ProbeError(f"unexpected control {b.hex()} expected {want:02x}")
        raise ProbeError(f"timeout control {want:02x}")
    def enter(self):
        if self.s.in_waiting: self.s.read(self.s.in_waiting)
        self.send(b"\x04"); self.control(5)
        self.send(b"\x16\x00\x00"); self.control(6)
    def leave(self): self.send(b"\x04")
    def read(self,function,address,length):
        self.send(frame(function,address,length))
        first=self.exact(1)
        if first==b"\x15": raise ProbeError(f"NACK {function:02x}/{address:04x}")
        if first!=b"\x06": raise ProbeError("expected ACK")
        h=self.exact(2)
        if h[0]!=0x41 or not 1<=h[1]<=64: raise ProbeError("bad header")
        msg=h+self.exact(h[1]+1)
        if checksum(msg[:-1])!=msg[-1]: raise ProbeError("bad checksum")
        mtype=msg[2]&0x0f
        self.send(b"\x06")
        if mtype!=1: raise ProbeError(f"error response {function:02x}/{address:04x} data={msg[7:-1].hex()}")
        if msg[3]!=function or int.from_bytes(msg[4:6],"big")!=address:
            raise ProbeError("response echo mismatch")
        return msg[7:-1]

def snapshot(w):
    return {a:w.read(0x01,a,l) for a,l in MONITORS}

def guard(base,after):
    if after[0x5738]!=b"\x00": raise ProbeError("current GFA fault nonzero")
    if len(after[0xA132])!=29 or after[0xA132][28]!=0: raise ProbeError("current alarm nonzero")
    for a in HISTORY:
        if after[a]!=base[a]: raise ProbeError(f"fault history changed at {a:04x}")
def decode(row):
    k=int.from_bytes(row["kessel"],"little",signed=True)/10
    mod=row["mod"][0]/2
    sp=int.from_bytes(row["setpoint"],"little")/100
    cfdm=row["cfdm"][0]/2
    cfdm_on=bool(row["cfdm"][1]&1)
    g=row["gfa"]; flame=bool(g[5]&0x20); rpm=int.from_bytes(g[6:8],"big")
    return k,mod,sp,cfdm,cfdm_on,flame,rpm

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--samples",type=int,default=8)
    ap.add_argument("--interval",type=float,default=1.0)
    ap.add_argument("--self-test",action="store_true")
    ap.add_argument("--linearity",action="store_true",help="fixed overlap check inside the already-read 0x0400/0x53F0 blocks")
    args=ap.parse_args()
    if args.self_test:
        assert frame(0x03,0x0400,16).hex()=="410500030400101c"
        assert frame(0x03,0x53F0,16).hex()=="4105000353f0105b"
        assert frame(0x01,0xA305,1).hex()=="41050001a30501af"
        assert frame(0x03,0x0408,8).hex()=="410500030408081c"
        assert frame(0x03,0x53F8,8).hex()=="4105000353f8085b"
        print("SELFTEST=PASS"); return 0
    if not 2<=args.samples<=30 or not 0.5<=args.interval<=5:
        raise ProbeError("samples 2..30, interval 0.5..5")
    states={u:active(u) for u in (SCHEDULE,PARTY,SPLITTER)}
    if not states[SPLITTER]: raise ProbeError("splitter not running")
    changed=[]; w=None
    old={sig:signal.signal(sig,lambda s,f: (_ for _ in ()).throw(ProbeError(f"signal {s}"))) for sig in ABORT}
    stamp=time.strftime("%Y%m%d-%H%M%S")
    out=Path("/tmp")/f"physical-correlation-{stamp}.csv"
    try:
        for u in (SCHEDULE,PARTY,SPLITTER):
            if states[u]: svc("stop",u); changed.append(u)
        w=Wire(settings_port()); w.enter()
        if w.read(*IDENT)!=bytes.fromhex("20 c2"): raise ProbeError("identity mismatch")
        base=snapshot(w)
        if base[0x5738]!=b"\x00" or base[0xA132][28]!=0: raise ProbeError("baseline fault")
        if args.linearity:
            a1=w.read(0x03,0x53F0,16); time.sleep(.08)
            amid=w.read(0x03,0x53F8,8); time.sleep(.08)
            a2=w.read(0x03,0x53F0,16); time.sleep(.08)
            b1=w.read(0x03,0x0400,16); time.sleep(.08)
            bmid=w.read(0x03,0x0408,8); time.sleep(.08)
            b2=w.read(0x03,0x0400,16)
            print(f"LINEAR 53F0 first={a1.hex()} overlap={amid.hex()} second={a2.hex()} match1={amid==a1[8:]} match2={amid==a2[8:]}",flush=True)
            print(f"LINEAR 0400 first={b1.hex()} overlap={bmid.hex()} second={b2.hex()} static_tail_match1={all(bmid[i]==b1[8+i] for i in range(8) if i not in (0,1))} static_tail_match2={all(bmid[i]==b2[8+i] for i in range(8) if i not in (0,1))}",flush=True)
            after=snapshot(w); guard(base,after); print("FAULT_GUARD=PASS",flush=True)
            w.leave(); return 0
        fields=["n","t","phys0400","phys53f0","kessel_c","mod_pct","setpoint_c",
                "cfdm_pct","cfdm_on","flame","rpm"]
        with out.open("w",newline="") as fh:
            cw=csv.DictWriter(fh,fieldnames=fields); cw.writeheader()
            start=time.monotonic()
            for n in range(args.samples):
                raw={}
                for name,f,a,l in (*PHYS,*VIRT):
                    raw[name]=w.read(f,a,l); time.sleep(.08)
                k,mod,sp,cfdm,on,flame,rpm=decode(raw)
                row={"n":n,"t":round(time.monotonic()-start,3),
                     "phys0400":raw["phys0400"].hex(),"phys53f0":raw["phys53f0"].hex(),
                     "kessel_c":k,"mod_pct":mod,"setpoint_c":sp,
                     "cfdm_pct":cfdm,"cfdm_on":int(on),"flame":int(flame),"rpm":rpm}
                cw.writerow(row); fh.flush()
                print("SAMPLE",row,flush=True)
                deadline=start+(n+1)*args.interval
                if time.monotonic()<deadline: time.sleep(deadline-time.monotonic())
        after=snapshot(w); guard(base,after); print("FAULT_GUARD=PASS",flush=True)
        w.leave(); print("CSV="+str(out),flush=True)
        return 0
    finally:
        if w:
            try:w.close()
            except Exception:pass
        for u in reversed(changed):
            try:svc("start",u)
            except Exception as e:print("RESTORE_ERROR",u,e,flush=True)
        for sig,h in old.items(): signal.signal(sig,h)

if __name__=="__main__":
    raise SystemExit(main())