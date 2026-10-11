#!/usr/bin/env python3
"""WB2A software room influence via original Optolink Virtual_WRITE 0x2321.

Independent of VS1/P300: talks only to the existing single-owner splitter
through optolink-debug/MQTT. Does not impersonate an accepted KM-Bus Vitotrol.

A bounded one-shot A/B/A *experiment*, not an unattended controller daemon.
Without --execute it performs no device I/O. With --execute an independent
systemd watchdog restoring the original setpoint must already be armed.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import re
import subprocess
import time

ID = bytes.fromhex("20c2000300000103")
EXTERNAL_ROOM_SETPOINT = 0x2321
NORMAL_ROOM_SETPOINT = 0x2306
SUPPLY_SETPOINT = 0x2544
CURRENT_FAULT = 0x5738
RESPONSE = re.compile(r"<- openv/resp:\s*([0-9]+);0x([0-9a-fA-F]+);([^\r\n]*)")

class RoomInfluenceRejected(RuntimeError):
    pass

def compute_external_setpoint(target_c: float, room_c: float,
                              gain: float = 1.0) -> int:
    """Room feedback command in whole °C, clamped to ±3 K target correction.

    A high room temperature lowers the external room *target* and thereby
    reduces the heating supply setpoint. No fabricated room sensor readings
    or direct writes to Vitotrol physical RX RAM are involved.
    """
    for v in (target_c,room_c,gain):
        if type(v) not in (int,float) or not math.isfinite(v):
            raise RoomInfluenceRejected("finite numeric room input required")
    if not 17 <= target_c <= 24:
        raise RoomInfluenceRejected("target outside protected comfort range")
    if not 10 <= room_c <= 32:
        raise RoomInfluenceRejected("measured room outside sensor plausibility")
    if not 0.2 <= gain <= 2.0:
        raise RoomInfluenceRejected("gain out of bounds")
    calculated = target_c + max(-3.0,min(3.0,gain*(target_c-room_c)))
    return min(26,max(16,int(math.floor(calculated + 0.5))))

def parse_reply(output: str, expected: int, size: int | None) -> bytes:
    if type(output) is not str:
        raise RoomInfluenceRejected("typed controller response required")
    matches=list(RESPONSE.finditer(output))
    if len(matches)!=1:
        raise RoomInfluenceRejected("missing or duplicate controller response")
    m=matches[0]
    if int(m[1])!=1 or int(m[2],16)!=expected:
        raise RoomInfluenceRejected("controller rejected or changed address")
    raw=m[3].strip().lower()
    try:
        data=b"" if raw=="none" else bytes.fromhex(raw)
    except ValueError as exc:
        raise RoomInfluenceRejected("invalid controller hex") from exc
    if size is not None and len(data)!=size:
        raise RoomInfluenceRejected("unexpected read response length")
    return data

class NativeOptolinkClient:
    def __init__(self, *, run=subprocess.run):
        self.run=run
    def request(self, command: str, expected: int, size: int | None) -> bytes:
        if type(command) is not str or not re.fullmatch(
            r"(?:read;0x[0-9a-f]{4};[0-9]+|writeraw;0x2321;[0-9a-f]{2})",
            command):
            raise RoomInfluenceRejected("command outside fixed read/write set")
        argv=["optolink-debug","request",command,"--timeout","7"]
        result=self.run(argv,capture_output=True,text=True,timeout=12,check=False)
        if result.returncode:
            raise RoomInfluenceRejected("optolink-debug failed")
        return parse_reply(result.stdout,expected,size)
    def read(self,addr: int,size: int) -> bytes:
        if (addr,size) not in {
            (0x00f8,8),(NORMAL_ROOM_SETPOINT,1),(EXTERNAL_ROOM_SETPOINT,1),
            (SUPPLY_SETPOINT,2),(CURRENT_FAULT,1),
            (0x27a0,1),(0x27b0,1)}:
            raise RoomInfluenceRejected("unlisted virtual read forbidden")
        return self.request(f"read;0x{addr:04x};{size}",addr,size)
    def write_external(self,value: int):
        if type(value) is not int or value not in (0,*range(16,27)):
            raise RoomInfluenceRejected("unlisted external room target")
        data=self.request(f"writeraw;0x2321;{value:02x}",
                          EXTERNAL_ROOM_SETPOINT,None)
        if data not in (b"",bytes([value])):
            raise RoomInfluenceRejected("unexpected write response payload")

class ExternalRoomController:
    def __init__(self, client: NativeOptolinkClient, *, sleep=time.sleep):
        self.client=client
        self.sleep=sleep
    def probe(self, *, room_c: float,target_c: float,gain: float=1.0,
              hold_s: float=5.0) -> dict:
        command=compute_external_setpoint(target_c,room_c,gain)
        if (type(hold_s) not in (float,int)
                or not math.isfinite(hold_s) or not 0<=hold_s<=30):
            raise RoomInfluenceRejected("finite bounded hold time 0..30 s required")
        if self.client.read(0x00f8,8)!=ID:
            raise RoomInfluenceRejected("wrong boiler model or software")
        existing=self.client.read(EXTERNAL_ROOM_SETPOINT,1)
        current_target=self.client.read(NORMAL_ROOM_SETPOINT,1)
        previous_fault=self.client.read(CURRENT_FAULT,1)
        if existing!=b"\x00" or previous_fault!=b"\x00":
            raise RoomInfluenceRejected("foreign room override or heating fault")
        if abs(current_target[0]-target_c)>0.01:
            raise RoomInfluenceRejected("target differs from boiler's actual setpoint")
        before=int.from_bytes(self.client.read(SUPPLY_SETPOINT,2),"little")
        active=None
        restoration_failure=None
        engaged=False
        try:
            engaged=True
            self.client.write_external(command)
            if self.client.read(EXTERNAL_ROOM_SETPOINT,1)!=bytes([command]):
                raise RoomInfluenceRejected("write not persisted")
            first=int.from_bytes(self.client.read(SUPPLY_SETPOINT,2),"little")
            self.sleep(hold_s)
            second=int.from_bytes(self.client.read(SUPPLY_SETPOINT,2),"little")
            active={"external_room_setpoint_c":command,
                    "supply_first_deci_c":first,
                    "supply_second_deci_c":second}
        finally:
            if engaged:
                try:self.client.write_external(0)
                except Exception as exc:restoration_failure=str(exc)[:180]
        if restoration_failure:
            raise RoomInfluenceRejected("external setpoint restoration failed: "+
                                        restoration_failure)
        if self.client.read(EXTERNAL_ROOM_SETPOINT,1)!=b"\x00":
            raise RoomInfluenceRejected("restoration not proven on controller")
        self.sleep(0.3)
        restored=int.from_bytes(self.client.read(SUPPLY_SETPOINT,2),"little")
        fault=self.client.read(CURRENT_FAULT,1)
        if fault!=b"\x00":
            raise RoomInfluenceRejected("controller fault after probe")
        return {
            "method":"EXTERNAL_ROOM_SETPOINT_A1M1_OVER_OPTOLINK_NOT_KM_BUS_SLAVE",
            "input_room_c":room_c,"target_c":target_c,"kp":gain,
            "controller_identity_verified":True,
            "normal_room_target_verified":current_target[0],
            "baseline_external_coding":"00",
            "before_supply_deci_c":before,
            "while_active":active,
            "after_supply_deci_c":restored,
            "external_room_override_restored":True,
            "actual_measured_room_source_connected":False,
            "vitotrol_registered_with_firmware":False,
            "physical_km_bus_reply_sent":False,
            "independent_rollback_required":True,
        }

def main():
    cli=argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--room-c",type=float,required=True)
    cli.add_argument("--target-c",type=float,required=True)
    cli.add_argument("--kp",type=float,default=1.0)
    cli.add_argument("--hold-seconds",type=float,default=5.0)
    cli.add_argument("--execute",action="store_true")
    cli.add_argument("--watchdog-armed",action="store_true",
                     help="operator independently verified systemd rollback")
    args=cli.parse_args()
    command=compute_external_setpoint(args.target_c,args.room_c,args.kp)
    if not args.execute:
        print(json.dumps({"mode":"PLAN_ONLY_NO_HEATER_IO",
            "external_room_target_c":command,"virtual_address":"0x2321",
            "current_real_room_sensor_connected":False},indent=2))
        return 0
    if not args.watchdog_armed:
        raise RoomInfluenceRejected("execute requires independent watchdog")
    report=ExternalRoomController(NativeOptolinkClient()).probe(
        room_c=args.room_c,target_c=args.target_c,gain=args.kp,
        hold_s=args.hold_seconds)
    print(json.dumps(report,indent=2,sort_keys=True))
    return 0

if __name__=="__main__":
    raise SystemExit(main())
