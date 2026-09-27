#!/opt/optolink/venv/bin/python
"""Fixed read-only probe for the 11-byte scheduler/callback table near 0x18f6.

No writes, no arbitrary address input. Uses existing identity/fault guards.
"""
from __future__ import annotations
import argparse, fcntl, importlib.util, os, signal, time
from pathlib import Path

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location("physical_ram_snapshot",HERE/"physical-ram-snapshot.py")
m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)

START=0x18E0
CHUNKS=(0x18E0,0x1900,0x1920)
NODES=(0x18F6,0x1901,0x190C,0x1917)
COUNT=12

def parse_node(buf:bytes,addr:int):
    off=addr-START
    d=buf[off:off+11]
    return {
        "next":int.from_bytes(d[0:2],"little"),
        "callback":int.from_bytes(d[2:6],"little"),
        "tick":int.from_bytes(d[6:8],"little"),
        "period":int.from_bytes(d[8:10],"little"),
        "flag":d[10],
    }
def unwrap(vals):
    out=[vals[0]]
    for v in vals[1:]:
        x=v
        while x<out[-1]:
            x+=65536
        out.append(x)
    return out

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--execute",action="store_true")
    ap.add_argument("--self-test",action="store_true")
    args=ap.parse_args()
    if args.self_test:
        for a in CHUNKS:
            assert m.frame(0x03,a,m.CHUNK)[3]==0x03
        fake=bytes(96)
        assert parse_node(fake,0x18F6)["callback"]==0
        print("SELFTEST=PASS"); return 0
    if not args.execute:
        print("plan only; use --execute for fixed read-only scheduler probe"); return 0

    fd=os.open(m.LOCK,os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600)
    fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
    states={u:m.active(u) for u in (m.SCHEDULE,m.PARTY,m.SPLITTER)}
    if not states[m.SPLITTER]:
        raise m.ProbeError("splitter not running before probe")
    changed=[]; w=None
    previous={sig:signal.getsignal(sig) for sig in m.ABORT}
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

        samples=[]; t0=time.monotonic()
        for n in range(COUNT):
            ts=time.monotonic()-t0
            buf=b"".join(w.request(0x03,a,m.CHUNK)["data"] for a in CHUNKS)
            nodes=[parse_node(buf,a) for a in NODES]
            samples.append((ts,nodes))
            log("SCHED n=%02d t=%.6f %s" % (n,ts," | ".join(
                f"{NODES[i]:04x}:next={x['next']:04x},cb={x['callback']:05x},"
                f"tick={x['tick']:04x},period={x['period']},flag={x['flag']}"
                for i,x in enumerate(nodes))))
            if (n+1)%4==0: m.guard_current(w)
            time.sleep(0.08)
        for idx,addr in enumerate(NODES):
            ticks=unwrap([s[1][idx]["tick"] for s in samples])
            rates=[]
            for i in range(1,len(samples)):
                dt=samples[i][0]-samples[i-1][0]
                rates.append((ticks[i]-ticks[i-1])/dt)
            n0=samples[0][1][idx]
            log(f"SUMMARY addr=0x{addr:04x} callback=0x{n0['callback']:05x} "
                f"period={n0['period']} flag={n0['flag']} "
                f"mean_tick_hz={sum(rates)/len(rates):.3f}")

        after=m.monitor_snapshot(w)
        if after[0x5738]!=b"\x00" or after[0xA132][28]!=0:
            raise m.ProbeError("final active fault")
        for a in m.HISTORY:
            if after[a]!=base[a]:
                raise m.ProbeError(f"fault history changed at 0x{a:04x}")
        log("FAULT_GUARD=PASS")
        w.leave(); return 0
    finally:
        if w:
            try: w.close()
            except Exception: pass
        for unit in reversed(changed):
            try: m.svc("start",unit); log("RESTORED "+unit)
            except Exception as exc: log("RESTORE_ERROR "+str(exc))
        for sig,h in previous.items(): signal.signal(sig,h)
        os.close(fd)

if __name__=="__main__":
    raise SystemExit(main())