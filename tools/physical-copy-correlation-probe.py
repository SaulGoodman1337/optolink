#!/opt/optolink/venv/bin/python
"""Bounded read-only correlation probe for far-source/low-RAM copy candidates.

Observes only fixed Physical_READ blocks and fixed Virtual_READ runtime anchors.
No write path and no arbitrary address/function input.
"""
from __future__ import annotations
import argparse, fcntl, importlib.util, os, signal, time
from pathlib import Path

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location("physical_ram_snapshot",HERE/"physical-ram-snapshot.py")
m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)

DURATION=60.0
EXTRA_VIRTUAL={(0x55D3,9),(0xA305,1),(0x0810,2),(0xA38F,2)}
ORIG_FRAME=m.frame

def fixed_frame(function:int,address:int,length:int)->bytes:
    if function==0x01 and (address,length) in EXTRA_VIRTUAL:
        b=bytes((0x41,0x05,0x00,0x01,address>>8,address&0xff,length))
        return b+bytes((m.checksum(b),))
    return ORIG_FRAME(function,address,length)

m.frame=fixed_frame
def parse_a(d:bytes):
    o=0x1DE5-0x1DE0
    return (int.from_bytes(d[o:o+3],"little"),
            int.from_bytes(d[o+3:o+6],"little"),
            int.from_bytes(d[o+6:o+8],"little"))

def parse_b(d:bytes):
    o=0x1E6A-0x1E60
    return (int.from_bytes(d[o+3:o+6],"little"),
            int.from_bytes(d[o:o+3],"little"),
            int.from_bytes(d[o+6:o+8],"little"))

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--execute",action="store_true")
    ap.add_argument("--self-test",action="store_true")
    args=ap.parse_args()
    if args.self_test:
        for addr,length in EXTRA_VIRTUAL:
            assert fixed_frame(0x01,addr,length)[3]==0x01
        print("SELFTEST=PASS"); return 0
    if not args.execute:
        print("plan only; use --execute for fixed 60-second read-only correlation"); return 0

    fd=os.open(m.LOCK,os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600)
    fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
    states={u:m.active(u) for u in (m.SCHEDULE,m.PARTY,m.SPLITTER)}
    if not states[m.SPLITTER]: raise m.ProbeError("splitter not running")
    changed=[]; w=None
    prev={sig:signal.getsignal(sig) for sig in m.ABORT}
    for sig in m.ABORT:
        signal.signal(sig,lambda s,f: (_ for _ in ()).throw(m.ProbeError(f"signal {s}")))
    log=lambda s: print(time.strftime("%H:%M:%S"),s,flush=True)
    try:
        for unit in (m.SCHEDULE,m.PARTY,m.SPLITTER):
            if states[unit]:
                m.svc("stop",unit); changed.append(unit); log("STOPPED "+unit)
        w=m.Wire(m.read_port(),log); w.enter()
        ident=w.request(0x01,*m.IDENT)
        if ident["status"]!="SUCCESS" or ident["data"]!=bytes.fromhex("20 c2"):
            raise m.ProbeError("20C2 identity failed")
        base=m.monitor_snapshot(w)
        if base[0x5738]!=b"\x00" or base[0xA132][28]!=0:
            raise m.ProbeError("baseline active fault")

        t0=time.monotonic(); n=0; last=None; transitions=0
        while time.monotonic()-t0 < DURATION:
            a=w.request(0x03,0x1DE0,32)["data"]
            b=w.request(0x03,0x1E60,32)["data"]
            d3300=w.request(0x03,0x3300,32)["data"]
            d0700=w.request(0x03,0x0700,32)["data"]
            v55=w.request(0x01,0x55D3,9)["data"]
            va3=w.request(0x01,0xA305,1)["data"]
            v81=w.request(0x01,0x0810,2)["data"]
            va38=w.request(0x01,0xA38F,2)["data"]
            ca=parse_a(a); cb=parse_b(b)
            flame=1 if len(v55)>=6 and (v55[5]&0x20) else 0
            rpm=int.from_bytes(v55[6:8],"big") if len(v55)>=8 else -1
            mod=(va3[0]/2) if va3 else -1
            kessel=int.from_bytes(v81[:2],"little",signed=True)/10 if len(v81)>=2 else -999
            cfdm=(va38[0]/2) if len(va38)>=2 else -1
            cfdm_on=(va38[1]&1) if len(va38)>=2 else -1
            destA=d3300[1:30]
            destB=d0700[5:12]
            state=(ca,cb,destA,destB,flame,rpm,mod,kessel,cfdm,cfdm_on)
            if last is not None and state!=last:
                transitions+=1
            log(f"CORR n={n:03d} t={time.monotonic()-t0:.3f} "
                f"A={ca[0]:05x}->{ca[1]:04x}/{ca[2]} B={cb[0]:05x}->{cb[1]:04x}/{cb[2]} "
                f"flame={flame} rpm={rpm} mod={mod:.1f} kessel={kessel:.1f} "
                f"cfdm={cfdm:.1f}/{cfdm_on} dA={destA.hex()} dB={destB.hex()}")
            last=state; n+=1
            if n%10==0: m.guard_current(w)
            time.sleep(0.15)
        log(f"SUMMARY samples={n} transitions={transitions}")
        after=m.monitor_snapshot(w)
        if after[0x5738]!=b"\x00" or after[0xA132][28]!=0:
            raise m.ProbeError("final active fault")
        for addr in m.HISTORY:
            if after[addr]!=base[addr]:
                raise m.ProbeError(f"fault history changed at 0x{addr:04x}")
        log("FAULT_GUARD=PASS")
        w.leave(); return 0
    finally:
        if w:
            try:w.close()
            except Exception:pass
        for unit in reversed(changed):
            try:m.svc("start",unit); log("RESTORED "+unit)
            except Exception as exc: log("RESTORE_ERROR "+str(exc))
        for sig,h in prev.items(): signal.signal(sig,h)
        os.close(fd)

if __name__=="__main__":
    raise SystemExit(main())