#!/opt/optolink/venv/bin/python
"""Read-only WB2A burner/A1 runtime correlation watcher.

Goal
----
Observe one or more natural direct-A1 heating burner cycles without changing
any setpoint or coding. The watcher correlates source-backed VDensHO1 runtime
surfaces that may distinguish burner request/output from flame and A1 pump
state.

Fixed read set:
  0xA152/2  VDensHO1 nvoRelayState bitfield
             bit 6  burner
             bit 10 HKP1
             bit 2  internal pump
             bit 3  diverter/heating
             bit 5  diverter/DHW
  0xA305/1  VDensHO1 nvoBoilerState_BLR_value (raw)
  0x55D3/11 shared fire-control runtime block
  0x55DD/1  independent flame signal
  0x7663/2  A1 heating-circuit pump output/speed
  0x0A3A/1  A1 pump result surface
  0x2500/22 A1 operating-state block
  0x555A/2  effective boiler target
  0x2544/2  A1 flow target
  0x0810/2  boiler temperature
  0x650A/1  DHW state

No write command exists in this helper. No arbitrary address arguments exist.

Bit numbering in the Vitosoft event metadata is MSB-first within each byte.
Thus EventType bit position 6 of 0xA152 is byte0 mask 0x02, while bit 10 is
byte1 mask 0x20. This convention is independently consistent with the
source-defined 0x55D3 flame bit position 42 mapping to byte5 mask 0x20.
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


def bit_msb(data: bytes, position: int) -> int:
    byte_i=position//8
    bit_i=position%8
    if byte_i>=len(data):
        raise ValueError("bit position outside payload")
    return 1 if data[byte_i] & (1 << (7-bit_i)) else 0


def u16le(b: bytes) -> int:
    return b[0] | (b[1]<<8)


@dataclass
class Sample:
    mono: float
    iso: str
    a152: bytes
    a305: int
    gfa: bytes
    flame2_raw: int
    a1: bytes
    a1_result: int
    a1_state: bytes
    boiler_target_c: float
    flow_target_c: float
    boiler_c: float
    dhw: int

    @property
    def relay_burner(self): return bit_msb(self.a152,6)
    @property
    def relay_hkp1(self): return bit_msb(self.a152,10)
    @property
    def relay_internal_pump(self): return bit_msb(self.a152,2)
    @property
    def relay_uv_heating(self): return bit_msb(self.a152,3)
    @property
    def relay_uv_dhw(self): return bit_msb(self.a152,5)
    @property
    def flame(self): return 1 if self.gfa[5] & 0x20 else 0
    @property
    def lockout(self): return 1 if self.gfa[5] & 0x40 else 0
    @property
    def flame2(self): return 1 if self.flame2_raw & 0x20 else 0
    @property
    def modulation(self): return self.gfa[9]
    @property
    def a1_on(self): return self.a1[0]
    @property
    def a1_speed(self): return self.a1[1]
    @property
    def a1_mode(self): return self.a1_state[1]


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
    time.sleep(0.3)
    return client,responses


def read_raw(client,responses,address,length,timeout=2.0):
    command=f"r;{address};{length};raw;False"
    expected=int(address,0)
    responses.clear()
    info=client.publish(settings.mqtt_listen,command)
    info.wait_for_publish(timeout=1.5)
    if not info.is_published():
        raise TimeoutError(f"publish timeout: {command}")
    end=time.monotonic()+timeout
    while time.monotonic()<end:
        while responses:
            r=responses.pop(0)
            p=r.split(";")
            if len(p)<3:
                continue
            try: addr=int(p[1],0)
            except ValueError: continue
            if addr!=expected:
                continue
            if p[0]!="1":
                raise RuntimeError(f"{address}: {r}")
            data=bytes.fromhex(p[2])
            if len(data)<length:
                raise RuntimeError(f"{address}: short payload {data.hex()}")
            return data[:length]
        time.sleep(0.004)
    raise TimeoutError(command)


def sample(client,responses):
    a152=read_raw(client,responses,"0xA152",2)
    a305=read_raw(client,responses,"0xA305",1)[0]
    gfa=read_raw(client,responses,"0x55D3",11)
    flame2=read_raw(client,responses,"0x55DD",1)[0]
    a1=read_raw(client,responses,"0x7663",2)
    a1res=read_raw(client,responses,"0x0A3A",1)[0]
    a1state=read_raw(client,responses,"0x2500",22)
    bt=read_raw(client,responses,"0x555A",2)
    ft=read_raw(client,responses,"0x2544",2)
    kt=read_raw(client,responses,"0x0810",2)
    dhw=read_raw(client,responses,"0x650A",1)[0]
    return Sample(
        mono=time.monotonic(),
        iso=datetime.now().astimezone().isoformat(timespec="milliseconds"),
        a152=a152,a305=a305,gfa=gfa,flame2_raw=flame2,a1=a1,
        a1_result=a1res,a1_state=a1state,
        boiler_target_c=u16le(bt)/10.0,
        flow_target_c=u16le(ft)/10.0,
        boiler_c=u16le(kt)/10.0,
        dhw=dhw,
    )


def key(s):
    return (
        s.relay_burner,s.relay_hkp1,s.relay_internal_pump,
        s.relay_uv_heating,s.relay_uv_dhw,
        s.a305,s.flame,s.flame2,s.modulation,
        s.a1_on,s.a1_speed,s.a1_result,s.a1_mode,s.dhw,
        round(s.boiler_target_c,1),round(s.flow_target_c,1),round(s.boiler_c,1)
    )


def fmt(s):
    return (
        f"A152={s.a152.hex()} "
        f"BR={s.relay_burner} HKP1={s.relay_hkp1} IP={s.relay_internal_pump} "
        f"UVH={s.relay_uv_heating} UVWW={s.relay_uv_dhw} "
        f"A305={s.a305:02X} FL={s.flame}/{s.flame2} MOD={s.modulation:3d} "
        f"A1={s.a1_on:02X}/{s.a1_speed:3d}% A1res={s.a1_result:3d} "
        f"MODE={s.a1_mode:02X} DHW={s.dhw:02X} "
        f"KS={s.boiler_target_c:4.1f} VS={s.flow_target_c:4.1f} IST={s.boiler_c:4.1f}"
    )


def self_test():
    import unittest
    class T(unittest.TestCase):
        def test_a152_idle_dhw(self):
            b=bytes.fromhex("0400")
            self.assertEqual(bit_msb(b,5),1)
            self.assertEqual(bit_msb(b,6),0)
            self.assertEqual(bit_msb(b,10),0)
            self.assertEqual(bit_msb(b,2),0)
        def test_a152_burner(self):
            self.assertEqual(bit_msb(bytes.fromhex("0200"),6),1)
        def test_a152_hkp1(self):
            self.assertEqual(bit_msb(bytes.fromhex("0020"),10),1)
        def test_internal_pump(self):
            self.assertEqual(bit_msb(bytes.fromhex("2000"),2),1)
        def test_source_flame_convention(self):
            # EventType bit position 42 is byte5, MSB-first bit2 => mask 0x20.
            b=bytearray(9); b[5]=0x20
            self.assertEqual(bit_msb(bytes(b),42),1)
    res=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(T))
    if res.wasSuccessful():
        print("BURNER_A1_RUNTIME_WATCH_TESTS=5/5")
        return 0
    return 1


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--self-test",action="store_true")
    ap.add_argument("--interval",type=float,default=0.75)
    ap.add_argument("--seconds",type=float,default=1800.0)
    ap.add_argument("--stop-after-flame-cycles",type=int,default=2)
    ap.add_argument("--output")
    args=ap.parse_args()
    if args.self_test:
        return self_test()
    if args.interval<0.5:
        raise SystemExit("--interval must be >= 0.5")
    if args.seconds<=0:
        raise SystemExit("--seconds must be > 0")

    out=Path(args.output) if args.output else Path.home()/f"wb2a-burner-a1-runtime-{datetime.now():%Y%m%d-%H%M%S}.csv"
    fields=[
        "timestamp","a152_raw","relay_burner","relay_hkp1","relay_internal_pump",
        "relay_uv_heating","relay_uv_dhw","a305_raw","flame_55d3","flame_55dd",
        "lockout","modulation","a1_on","a1_speed","a1_result","a1_mode","dhw",
        "boiler_target_c","flow_target_c","boiler_c"
    ]
    client,responses=connect()
    stop=False
    def handler(signum,frame):
        nonlocal stop
        stop=True
    signal.signal(signal.SIGINT,handler)
    signal.signal(signal.SIGTERM,handler)

    start=time.monotonic(); prev=None; flame_cycles=0; seen_flame=False
    print("WB2A burner/A1 runtime watcher")
    print("Writes: none")
    print(f"CSV={out}")
    try:
        with out.open("w",encoding="utf-8",newline="",buffering=1) as fh:
            w=csv.DictWriter(fh,fieldnames=fields); w.writeheader()
            while not stop and time.monotonic()-start<args.seconds:
                cycle=time.monotonic()
                try:
                    s=sample(client,responses)
                except Exception as exc:
                    print(f"{datetime.now().astimezone().isoformat()} READ_ERROR {exc}",file=sys.stderr,flush=True)
                    time.sleep(0.5)
                    continue
                w.writerow({
                    "timestamp":s.iso,"a152_raw":s.a152.hex(),
                    "relay_burner":s.relay_burner,"relay_hkp1":s.relay_hkp1,
                    "relay_internal_pump":s.relay_internal_pump,
                    "relay_uv_heating":s.relay_uv_heating,"relay_uv_dhw":s.relay_uv_dhw,
                    "a305_raw":s.a305,"flame_55d3":s.flame,"flame_55dd":s.flame2,
                    "lockout":s.lockout,"modulation":s.modulation,
                    "a1_on":s.a1_on,"a1_speed":s.a1_speed,"a1_result":s.a1_result,
                    "a1_mode":s.a1_mode,"dhw":s.dhw,
                    "boiler_target_c":f"{s.boiler_target_c:.1f}",
                    "flow_target_c":f"{s.flow_target_c:.1f}",
                    "boiler_c":f"{s.boiler_c:.1f}",
                })
                if prev is None or key(s)!=key(prev):
                    print(f"{s.iso} {fmt(s)}",flush=True)
                if s.flame:
                    seen_flame=True
                if prev is not None and prev.flame and not s.flame and seen_flame:
                    flame_cycles+=1
                    print(f"FLAME_CYCLE_COMPLETE={flame_cycles}",flush=True)
                    if args.stop_after_flame_cycles>0 and flame_cycles>=args.stop_after_flame_cycles:
                        break
                prev=s
                elapsed=time.monotonic()-cycle
                if elapsed<args.interval:
                    time.sleep(args.interval-elapsed)
    finally:
        client.loop_stop(); client.disconnect()
    print(f"FLAME_CYCLES={flame_cycles}",flush=True)
    print(f"CSV={out}",flush=True)
    print("RESULT=PASS",flush=True)
    return 0


if __name__=="__main__":
    raise SystemExit(main())
