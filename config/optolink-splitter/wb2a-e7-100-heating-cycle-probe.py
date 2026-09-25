#!/opt/optolink/venv/bin/python
"""Controlled WB2A E7=100 heating-cycle probe with automatic restore.

Version 1.0.1: bound MQTT publish waits so a broker/client stall cannot leave
the experimental write probe alive indefinitely without progressing.


Purpose
-------
Capture one natural space-heating burner cycle with A1 minimum pump speed E7
temporarily raised from the known local baseline 30 % to 100 %.

Safety / scope
--------------
- permanent VS1/MQTT path only; no P300 switch;
- waits for three consecutive safe samples with DHW inactive and flame off;
- requires baseline E7 == 30 %;
- writes only 0x27E7 and only values 100 and the original 30;
- verifies every E7 write by readback;
- logs pump/request/result, DHW/diverter, GFA flame/modulation and temperatures;
- restores E7 after the first complete flame ON -> OFF heating cycle;
- no other controller write exists in this program.

Opening radiators / creating heat demand is an external user action and is not
performed by this helper.
"""
from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import signal
import sys
import time

APP_DIR="/opt/optolink"
if APP_DIR not in sys.path:
    sys.path.insert(0,APP_DIR)

from c_settings_adapter import settings  # type: ignore
from homeassistant_publish import connect_mqtt  # type: ignore

BASELINE_E7=30
TARGET_E7=100


@dataclass
class S:
    mono: float
    iso: str
    e7: int
    a1_out: int
    a1_speed: int
    int_out: int
    int_speed: int
    a3c: int
    ww: int
    storage: int
    diverter: int
    flame: int
    modulation: int
    gfa_b5: int
    gfa_b6: int
    gfa_b7: int
    flow_target_c: float
    boiler_c: float


def connect():
    if not getattr(settings,"mqtt_listen",None) or not getattr(settings,"mqtt_respond",None):
        raise RuntimeError("MQTT command/response topics are not configured")
    client=connect_mqtt(retries=2,delay=1)
    if client is None:
        raise RuntimeError("MQTT connection failed")
    responses=[]
    def on_message(client,userdata,message):
        if message.topic==settings.mqtt_respond:
            responses.append(message.payload.decode(errors="replace"))
    client.on_message=on_message
    client.subscribe(settings.mqtt_respond)
    time.sleep(0.4)
    return client,responses


def request(client,responses,command,timeout=3.0):
    responses.clear()
    expected=int(command.split(";")[1],0)
    info=client.publish(settings.mqtt_listen,command)
    info.wait_for_publish(timeout=2.0)
    if not info.is_published():
        raise TimeoutError(f"MQTT publish timeout: {command}")
    end=time.monotonic()+timeout
    while time.monotonic()<end:
        while responses:
            r=responses.pop(0)
            p=r.split(";")
            if len(p)<3:
                continue
            try:
                addr=int(p[1],0)
            except ValueError:
                continue
            if addr==expected:
                return r
        time.sleep(0.005)
    raise TimeoutError(command)


def read_raw(client,responses,addr,length=1):
    r=request(client,responses,f"r;{addr};{length};raw;False")
    p=r.split(";")
    if p[0]!="1":
        raise RuntimeError(f"{addr}: {r}")
    b=bytes.fromhex(p[2])
    if len(b)<length:
        raise RuntimeError(f"{addr}: short payload {b.hex()}")
    return b[:length]


def write_e7(client,responses,value):
    if value not in (BASELINE_E7,TARGET_E7):
        raise RuntimeError(f"blocked E7 value {value}")
    r=request(client,responses,f"w;0x27E7;1;{value}")
    p=r.split(";")
    if p[0]!="1":
        raise RuntimeError(f"E7 write failed: {r}")
    rb=read_raw(client,responses,"0x27E7",1)[0]
    if rb!=value:
        raise RuntimeError(f"E7 verify failed: wrote {value}, read {rb}")
    return rb


def u16le(b):
    return b[0] | (b[1]<<8)


def sample(client,responses):
    e7=read_raw(client,responses,"0x27E7",1)[0]
    a1=read_raw(client,responses,"0x7663",2)
    internal=read_raw(client,responses,"0x7660",2)
    a3c=read_raw(client,responses,"0x0A3C",1)[0]
    ww=read_raw(client,responses,"0x650A",1)[0]
    storage=read_raw(client,responses,"0x6513",1)[0]
    diverter=read_raw(client,responses,"0x0A10",1)[0]
    gfa=read_raw(client,responses,"0x55D3",11)
    flow=read_raw(client,responses,"0x2544",2)
    boiler=read_raw(client,responses,"0x0810",2)
    return S(
        mono=time.monotonic(),
        iso=datetime.now().astimezone().isoformat(timespec="milliseconds"),
        e7=e7,a1_out=a1[0],a1_speed=a1[1],
        int_out=internal[0],int_speed=internal[1],a3c=a3c,
        ww=ww,storage=storage,diverter=diverter,
        flame=int(bool(gfa[5]&0x20)),modulation=gfa[9],
        gfa_b5=gfa[5],gfa_b6=gfa[6],gfa_b7=gfa[7],
        flow_target_c=u16le(flow)/10.0,
        boiler_c=u16le(boiler)/10.0,
    )


def safe_for_e7_write(s):
    return s.ww==0 and s.flame==0


def row(s,phase,start_mono,flame_start):
    return {
        "timestamp":s.iso,"phase":phase,
        "seconds_from_write":f"{s.mono-start_mono:.3f}",
        "seconds_from_flame_start":"" if flame_start is None else f"{s.mono-flame_start:.3f}",
        "e7":s.e7,
        "a1_out":s.a1_out,"a1_speed":s.a1_speed,
        "internal_out":s.int_out,"internal_speed":s.int_speed,
        "a3c":s.a3c,"ww":s.ww,"storage":s.storage,"diverter":s.diverter,
        "flame":s.flame,"modulation":s.modulation,
        "gfa_b5":f"0x{s.gfa_b5:02x}","gfa_b6":f"0x{s.gfa_b6:02x}","gfa_b7":f"0x{s.gfa_b7:02x}",
        "flow_target_c":f"{s.flow_target_c:.1f}","boiler_c":f"{s.boiler_c:.1f}",
    }


def self_test():
    import unittest
    class T(unittest.TestCase):
        def fake(self,ww=0,flame=0):
            return S(0,"",30,1,36,1,50,50,ww,0,1,flame,0,0,0,0,30,40)
        def test_safe(self):
            self.assertTrue(safe_for_e7_write(self.fake()))
            self.assertFalse(safe_for_e7_write(self.fake(ww=1)))
            self.assertFalse(safe_for_e7_write(self.fake(flame=1)))
        def test_write_allowlist(self):
            self.assertIn(BASELINE_E7,(30,100))
            self.assertIn(TARGET_E7,(30,100))
            self.assertNotIn(50,(BASELINE_E7,TARGET_E7))
        def test_row(self):
            r=row(self.fake(), "x", 0, None)
            self.assertEqual(r["e7"],30)
            self.assertEqual(r["internal_speed"],50)
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(T))
    if result.wasSuccessful():
        print("E7_100_HEATING_CYCLE_TESTS=3/3")
        return 0
    return 1


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--execute",action="store_true")
    ap.add_argument("--self-test",action="store_true")
    ap.add_argument("--interval",type=float,default=0.5)
    ap.add_argument("--safe-samples",type=int,default=3)
    ap.add_argument("--max-wait-safe",type=float,default=900.0)
    ap.add_argument("--max-wait-flame",type=float,default=900.0)
    ap.add_argument("--max-flame-seconds",type=float,default=1800.0)
    ap.add_argument("--output")
    args=ap.parse_args()
    if args.self_test:
        return self_test()
    if not args.execute:
        print("Plan only. Use --execute for the guarded 30->100->30 E7 cycle.")
        return 0
    if args.interval<0.2:
        raise SystemExit("--interval must be >= 0.2")

    out=Path(args.output) if args.output else Path.home()/f"wb2a-e7-100-cycle-{datetime.now():%Y%m%d-%H%M%S}.csv"
    fields=[
        "timestamp","phase","seconds_from_write","seconds_from_flame_start",
        "e7","a1_out","a1_speed","internal_out","internal_speed","a3c",
        "ww","storage","diverter","flame","modulation","gfa_b5","gfa_b6","gfa_b7",
        "flow_target_c","boiler_c",
    ]

    client,responses=connect()
    original=None
    target_written=False
    restore_verified=False
    stop_requested=False

    def handler(signum,frame):
        nonlocal stop_requested
        stop_requested=True

    signal.signal(signal.SIGINT,handler)
    signal.signal(signal.SIGTERM,handler)

    try:
        print("WB2A controlled E7=100 heating-cycle probe")
        print("Writes: only 0x27E7 30->100->30")
        print(f"CSV={out}")

        # Safe precondition window.
        safe_count=0
        deadline=time.monotonic()+args.max_wait_safe
        last=None
        while time.monotonic()<deadline:
            last=sample(client,responses)
            print(
                f"{last.iso} WAIT_SAFE WW={last.ww:02X} FL={last.flame} "
                f"E7={last.e7}% A1={last.a1_speed}% INT={last.int_speed}% A3C={last.a3c}%"
            )
            if safe_for_e7_write(last):
                safe_count+=1
            else:
                safe_count=0
            if safe_count>=args.safe_samples:
                break
            if stop_requested:
                raise KeyboardInterrupt
            time.sleep(max(0.0,args.interval))
        else:
            raise RuntimeError("safe precondition timeout")

        original=last.e7
        if original!=BASELINE_E7:
            raise RuntimeError(f"require E7 baseline {BASELINE_E7}, got {original}")

        print(f"SAFE_START confirmed; E7 {original} -> {TARGET_E7}")
        write_e7(client,responses,TARGET_E7)
        target_written=True
        write_mono=time.monotonic()
        print("E7_TARGET_READBACK=100")

        flame_seen=False
        flame_start=None
        flame_stop=None
        wait_flame_deadline=write_mono+args.max_wait_flame

        with out.open("w",newline="",encoding="utf-8",buffering=1) as fh:
            w=csv.DictWriter(fh,fieldnames=fields); w.writeheader()
            prev=None
            while True:
                cycle=time.monotonic()
                s=sample(client,responses)
                phase="flame" if s.flame else ("pre_flame" if not flame_seen else "post_flame")
                if s.ww!=0:
                    raise RuntimeError(f"DHW became active during heating probe: 0x{s.ww:02X}")
                if s.e7!=TARGET_E7:
                    raise RuntimeError(f"E7 changed unexpectedly to {s.e7}")

                if s.flame and not flame_seen:
                    flame_seen=True
                    flame_start=s.mono
                    print(f"{s.iso} FLAME_START")
                if flame_seen and prev is not None and prev.flame and not s.flame:
                    flame_stop=s.mono
                    print(f"{s.iso} FLAME_STOP")
                    w.writerow(row(s,"post_flame",write_mono,flame_start))
                    break

                w.writerow(row(s,phase,write_mono,flame_start))

                key=(s.a1_speed,s.int_speed,s.a3c,s.flame,s.modulation,round(s.boiler_c,1),round(s.flow_target_c,1))
                pkey=None if prev is None else (prev.a1_speed,prev.int_speed,prev.a3c,prev.flame,prev.modulation,round(prev.boiler_c,1),round(prev.flow_target_c,1))
                if key!=pkey:
                    age="" if flame_start is None else f" Tfl={s.mono-flame_start:.1f}s"
                    print(
                        f"{s.iso} E7={s.e7}% A1={s.a1_speed}% INT={s.int_speed}% "
                        f"A3C={s.a3c}% FL={s.flame} MOD={s.modulation}% "
                        f"VS={s.flow_target_c:.1f}C IST={s.boiler_c:.1f}C{age}"
                    )
                prev=s

                if not flame_seen and s.mono>=wait_flame_deadline:
                    raise RuntimeError("flame-start timeout")
                if flame_seen and flame_start is not None and s.mono-flame_start>=args.max_flame_seconds:
                    raise RuntimeError("flame remained on beyond max-flame-seconds")
                if stop_requested:
                    raise KeyboardInterrupt
                elapsed=time.monotonic()-cycle
                if elapsed<args.interval:
                    time.sleep(args.interval-elapsed)

        if flame_start is not None and flame_stop is not None:
            print(f"FLAME_DURATION={flame_stop-flame_start:.2f}s")

    finally:
        if original is not None and target_written:
            print(f"RESTORE_PENDING E7 -> {original}")
            # Preserve the same write safety rule: wait for flame off + DHW off.
            restore_deadline=time.monotonic()+900.0
            safe_count=0
            while time.monotonic()<restore_deadline:
                try:
                    s=sample(client,responses)
                except Exception as exc:
                    print(f"restore wait read error: {exc}",file=sys.stderr)
                    time.sleep(1.0)
                    continue
                if safe_for_e7_write(s):
                    safe_count+=1
                else:
                    safe_count=0
                if safe_count>=3:
                    write_e7(client,responses,original)
                    restore_verified=True
                    print(f"E7_RESTORED={original}")
                    break
                time.sleep(0.5)
            if not restore_verified:
                print(
                    f"CRITICAL: automatic safe restore not completed; E7 may still be {TARGET_E7}",
                    file=sys.stderr,
                )
        client.loop_stop()
        client.disconnect()

    print(f"CSV={out}")
    print("EXECUTION_RESULT=PASS" if restore_verified else "EXECUTION_RESULT=FAIL")
    return 0 if restore_verified else 1


if __name__=="__main__":
    raise SystemExit(main())
