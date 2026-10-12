#!/usr/bin/env python3
"""Reproducible WB2A native-P300 Vitotrol response preseed experiment.

Experiments with the *previously proven* four original-V300 bytes in the
controller's physical RX RAM. The candidate B3 response is placed there
BEFORE remote expectation A0:1/B0:3 is enabled, not afterward. During the
following master polls, physically observe four RAM windows and virtual
status. This is NOT a verified KM-Bus wire response / UART1 ISR trigger.

Single existing optolink-splitter MQTT transport only, no additional serial
connection, fixed FC03 RAM addresses and fixed CRC16-valid original response.
All hardware writes are restricted to those already used in the previous
live test. Independent watchdog must be armed before --execute.
"""
from __future__ import annotations
import argparse
import importlib.util
import json
from pathlib import Path
import sys
import time

HERE=Path(__file__).resolve().parent
sp=importlib.util.spec_from_file_location("wb2a_rx_preseed_transport",
                                          HERE/"wb2a-vitotrol-p300-bridge.py")
if sp is None or sp.loader is None:
    raise RuntimeError("native P300 client unavailable")
bridge=importlib.util.module_from_spec(sp)
sys.modules[sp.name]=bridge
sp.loader.exec_module(bridge)
from typing import Callable

FIXED_RAM=(0x161A,0x1640,0x0B60,0x1660)
RX_TAG=0x1642
MAX_SNAPSHOTS=16

V200_REFERENCE_IDENTITY=bridge.model.model_identity_reply(
    bytes.fromhex("1100330a0101f80449ef"),
    identity=bridge.model.IDENTITY_V200)
VALID_VARIANTS={
    # Exact original Vitotrol 300 TX log: ID class11 subtype 0x38.
    "v300_original":(2,bridge.FRAME_ORIGINAL_B3),
    # Source-backed historic Vitotrol 200 class/subtype, not local original.
    "v200_reference":(1,V200_REFERENCE_IDENTITY),
}



def compact_frame(raw: bytes) -> dict:
    """CRC-check a 32-byte TX (start0) or RX (start2) snapshot."""
    if type(raw) is not bytes or len(raw)!=32:
        raise bridge.BridgeRejected("exact 32-byte fixed FC03 data required")
    def valid(offset: int):
        if raw[offset+3] not in range(8,33-offset):
            return None
        msg=raw[offset:offset+raw[offset+3]]
        try: bridge.model.validate_frame(msg)
        except bridge.model.FrameRejected: return None
        return msg.hex()
    return {"frame_at_zero":valid(0),"frame_at_two":valid(2),
            "raw":raw.hex()}


class PreseedProbe:
    def __init__(self, client, *, now=time.monotonic, sleep=time.sleep):
        self.client=client
        self.now=now
        self.sleep=sleep

    def snapshot(self, *, tag: str) -> dict:
        reads={}
        for addr in FIXED_RAM:
            val=self.client.request(f"request;3;0x{addr:04x};32",addr).data
            if len(val)!=32:raise bridge.BridgeRejected("truncated RAM window")
            reads[f"{addr:04x}"]=val
        regs=bridge.monitor(self.client)
        idx=reads["0b60"][0x0B6B-0x0B60]
        desc=reads["0b60"][0x0B6D-0x0B60:0x0B71-0x0B60]
        meta=reads["1660"][0x166A-0x1660:0x166D-0x1660]
        return {"tag":tag,"sample_s":round(self.now(),3),
                "master_tx":compact_frame(reads["161a"]),
                "rx_candidate":compact_frame(reads["1640"]),
                "rx_descriptor_index":f"{idx:02x}",
                "rx_descriptor":desc.hex(),
                "rx_metadata":meta.hex(),
                "virtual":regs,
                "gateway_read_was_not_run":True}

    def run(self, *, count: int, gap_s: float = .2,
            configure_type: bool = False,
            variant: str = 'v300_original') -> dict:
        if type(count) is not int or not 1<=count<=MAX_SNAPSHOTS:
            raise bridge.BridgeRejected("bounded 1..16 snapshots only")
        if type(gap_s) not in (int,float) or not 0<=gap_s<=3:
            raise bridge.BridgeRejected("bounded 0..3 sec pause")
        if variant not in VALID_VARIANTS:
            raise bridge.BridgeRejected("unknown exact Vitotrol model variant")
        expected_a0, identity=VALID_VARIANTS[variant]
        before,original=self.client_and_preflight()
        rows=[]
        restore_errors=[]
        configured=False
        started=self.now()
        try:
            # Crucial variable: RX valid B3 exists *before* enabling A0/B0.
            bridge.model.validate_frame(identity)
            if identity not in (bridge.FRAME_ORIGINAL_B3,V200_REFERENCE_IDENTITY):
                raise bridge.BridgeRejected("unsupported model identity")
            self.client.physical_write(RX_TAG,identity)
            staged=self.client.physical_read()
            if staged[2:2+len(identity)] != identity:
                raise bridge.BridgeRejected("preseeded response failed RAM readback")
            if configure_type:
                self.client.write_config(0x7342,0x74)
            configured=True
            self.client.write_config(0x27A0,expected_a0)
            self.client.write_config(0x27B0,3)
            for n in range(count):
                rows.append(self.snapshot(tag=f"armed_{n:02d}"))
                if n<count-1:self.sleep(gap_s)
            active=bridge.monitor(self.client)
        finally:
            for action in (lambda:self.client.write_config(0x27B0,0),
                           lambda:self.client.write_config(0x27A0,0),
                           lambda:self.client.write_config(0x7342,0),
                           lambda:self.client.physical_write(0x1642,original[2:32])):
                try:action()
                except Exception as exc: restore_errors.append(str(exc)[:130])
        if restore_errors:
            raise bridge.BridgeRejected("independent watchdog required: "+
                                        "; ".join(restore_errors))
        after=bridge.monitor(self.client)
        restored=self.client.physical_read()
        if (after["a0"]!="00" or after["b0"]!="00"
            or after["type"]!="00" or restored[2:18]!=original[2:18]):
            raise bridge.BridgeRejected("RX/remote coding restore unverified")
        sw=active["swindex"]
        sensor=active["sensor"]
        return {
            "protocol":"NATIVE_P300_PRESEEDED_EXACT_VARIANT_IDENTITY_ONLY",
            "identity_verified":True,
            "variant":variant,
            "a0_remote_model_expected":f"{expected_a0:02x}",
            "identity_frame":identity.hex(),
            "identity_source":"ORIGINAL_V300_LOG" if variant=="v300_original"
                              else "OPENV_V200_REFERENCE_MODEL",
            "rx_physical_write_readback_exact":True,
            "duration_s":round(self.now()-started,3),
            "baseline_virtual":before,
            "live_snapshots":rows,
            "active_final_virtual":active,
            "remote_accepted_by_regulator":(sw!="00000000" and
                                             sensor!="03" and
                                             active["room_raw"]!="c800"),
            "restore_ok":True,"after_restore":after,
            "controller_rx_isr_or_parser_invocation_proven":False,
            "requires_independent_watchdog":True,
            "km_bus_phy_is_not_emulated":True,
        }

    def client_and_preflight(self):
        return bridge.VitotrolP300Stager(self.client).check_preflight()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--execute",action="store_true")
    p.add_argument("--snapshots",type=int,default=8)
    p.add_argument("--gap-seconds",type=float,default=.2)
    p.add_argument("--configure-type",action="store_true")
    p.add_argument("--variant",choices=tuple(VALID_VARIANTS),
                   default="v300_original")
    p.add_argument("--out",type=Path)
    args=p.parse_args()
    if not args.execute:
        print(json.dumps({"mode":"PLAN_ONLY",
                          "read_ram":[hex(x) for x in FIXED_RAM],
                          "preseed_frame":VALID_VARIANTS[args.variant][1].hex(),
                          "a0_type":VALID_VARIANTS[args.variant][0],
                          "variant":args.variant,
                          "controller_io":False},sort_keys=True))
        return 0
    bridge.require_native_p300()
    report=PreseedProbe(bridge.OptolinkP300Client()).run(
        count=args.snapshots,gap_s=args.gap_seconds,
        configure_type=args.configure_type,variant=args.variant)
    output=json.dumps(report,sort_keys=True,indent=2)+"\n"
    if args.out:
        args.out.write_text(output,encoding="utf-8")
        print("P300_PRESEED_REPORT",args.out,
              "accepted",report["remote_accepted_by_regulator"],
              "snapshots",len(report["live_snapshots"]),
              "restored",report["restore_ok"])
    else:
        print(output)
    return 0 if report["remote_accepted_by_regulator"] else 4


if __name__=="__main__":
    raise SystemExit(main())
