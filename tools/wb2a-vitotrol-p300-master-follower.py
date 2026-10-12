#!/usr/bin/env python3
"""Active Optolink-P300 follower for real Vitotrol F8 discovery/master frames.

Uses the SINGLE existing native P300 Optolink splitter. Samples the real
KM-Bus master-TX RAM 0x161A; for VALID class11/slot1 master messages, places
a matching CRC-valid original-V300-format slave reply into RX candidate RAM
0x1642 via Physical_WRITE. This is NOT an on-wire KM-Bus slave or verified
UART1 receive interrupt. Master RAM snapshots have no definitive send times.
"""
from __future__ import annotations

import argparse
from collections import Counter
import importlib.util
import json
from pathlib import Path
import sys
import time

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location(
    "vitotrol_native_p300_bridge_follower",
    HERE / "wb2a-vitotrol-p300-bridge.py")
if spec is None or spec.loader is None:
    raise RuntimeError("native P300 transport missing")
bridge=importlib.util.module_from_spec(spec)
sys.modules[spec.name]=bridge
spec.loader.exec_module(bridge)
model=bridge.model
TX_RAM=0x161A
MAX_READS=250
MAX_SECONDS=180.0


def parse_master_tx_snapshot(data: bytes) -> bytes | None:
    """Decode precisely a CRC-valid frame located at buffer start.

    Inactive/stale or different-master-class snapshots are observations,
    not permission to send to the boiler.
    """
    if type(data) is not bytes or len(data)!=32:
        raise bridge.BridgeRejected("exact master-TX FC03/32 expected")
    length=data[3]
    if not 8<=length<=32:
        return None
    frame=data[:length]
    try:
        model.validate_frame(frame)
    except model.FrameRejected:
        return None
    return frame


class NativeP300MasterFollower:
    def __init__(self, client, *, now=time.monotonic, pause=time.sleep):
        self.client=client
        self.now=now
        self.pause=pause

    def poll_once(self, remote, *, at_s: float) -> dict:
        packet=self.client.request("request;3;0x161a;32",TX_RAM).data
        master=parse_master_tx_snapshot(packet)
        if master is None:
            return {"master_status":"INVALID_OR_NONATOMIC_RAM_VIEW",
                    "staged":False}
        signature=master[:3].hex()
        out=None
        if master[:2] == bytes.fromhex("1100") and master[4]==1:
            try:
                out=remote.respond(master,at_s=at_s)
            except model.FrameRejected:
                return {"master_status":"UNSUPPORTED_CLASS11_MASTER_SHAPE",
                        "master":master.hex(),"staged":False}
        if out is None:
            return {"master_status":signature,"master":master.hex(),"staged":False}
        # Limit the active firmware-facing operation to exact known frames.
        bridge.validate_v300_frame(out)
        self.client.physical_write(bridge.RX_START,out)
        readback=self.client.physical_read()
        if readback[2:2+len(out)]!=out:
            raise bridge.BridgeRejected("response staged but physical readback mismatch")
        return {"master_status":signature,"master":master.hex(),
                "response":out.hex(),"staged":True,
                "readback_exact":True,"uart_receive_isr_proven":False}

    def run(self, *, duration_s: float, configure_type: bool = False) -> dict:
        if (type(duration_s) not in (int,float) or isinstance(duration_s,bool)
                or not 1 <= duration_s <= MAX_SECONDS):
            raise bridge.BridgeRejected("1..180 seconds bounded native experiment")
        initial, ram=bridge.VitotrolP300Stager(self.client).check_preflight()
        counts=Counter()
        observations=[]
        staged=[]
        engaged=False
        started=self.now()
        remote=model.original_v300_offline_profile(stale_after_s=300)
        remote.update_temperature(206,at_s=started)
        try:
            engaged=True
            if configure_type:
                self.client.write_config(0x7342,0x74)
            # Exact VDensHO1 coding: A0=2 expects Vitotrol 300 (ID 11 38).
            # The older A0=1 attempts expected Vitotrol 200 (ID 11 34);
            # using an actual V300 response with A0=1 was a model mismatch.
            self.client.write_config(0x27A0,2)
            self.client.write_config(0x27B0,3)
            while self.now()-started<duration_s and sum(counts.values())<MAX_READS:
                result=self.poll_once(remote,at_s=self.now())
                counts[result["master_status"]]+=1
                if result["staged"]:
                    staged.append(result)
            # The actual controller state matters more than frame staging.
            observations.append(bridge.monitor(self.client))
            self.pause(.5)
            observations.append(bridge.monitor(self.client))
        finally:
            if engaged:
                errors=[]
                for step in (lambda:self.client.write_config(0x27B0,0),
                             lambda:self.client.write_config(0x27A0,0),
                             lambda:self.client.write_config(0x7342,0),
                             lambda:self.client.physical_write(
                                 bridge.RX_START,ram[2:32])):
                    try:
                        step()
                    except Exception as exc:
                        errors.append(str(exc)[:140])
                if errors:
                    raise bridge.BridgeRejected(
                        "native master-follower failed its local restore: "+
                        ", ".join(errors))
        after=bridge.monitor(self.client)
        checked=self.client.physical_read()[2:18]==ram[2:18]
        if (after["a0"]!="00" or after["b0"]!="00"
                or after["type"]!="00" or not checked):
            raise bridge.BridgeRejected("native P300 master-follower restore mismatch")
        candidate=all(bridge.acceptance(s)["candidate_participant_and_room_acknowledgement"]
                      for s in observations)
        return {
            "model":"REAL_LIVE_NATIVE_P300_MASTER_TX_POLL_RAM_STAGE",
            "start_relative_duration_s":round(self.now()-started,3),
            "requested_duration_s":duration_s,
            "matched_remote_type_a0":"02",
            "master_frame_counts":dict(sorted(counts.items())),
            "staged_frame_count":len(staged),
            "staged_frames":staged[:100],
            "observed_while_active":observations,
            "last_active_acceptance_candidate":candidate,
            "restored":after,
            "original_rx_first16_restored":checked,
            "physical_controller_uart1_rx_interrupt_verified":False,
            "master_frame_wire_send_timestamp_proven":False,
            "meaningful_slave_reply_deadline_proven":False,
            "controller_acknowledged_remote":candidate,
            "external_watchdog_required":True,
            "no_second_optolink_serial_owner":True,
        }


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--execute",action="store_true")
    p.add_argument("--duration-seconds",type=float,default=60.0)
    p.add_argument("--configure-type",action="store_true")
    args=p.parse_args()
    if not args.execute:
        print(json.dumps({"mode":"PLAN_ONLY_NO_HARDWARE_IO",
                          "poll_ram":"0x161a/32",
                          "stage_ram":"0x1642",
                          "model":"original-v300-F8-B1-BF-PONG",
                          "controller_writes":0},sort_keys=True))
        return 0
    bridge.require_native_p300()
    report=NativeP300MasterFollower(
        bridge.OptolinkP300Client()).run(duration_s=args.duration_seconds,
                                        configure_type=args.configure_type)
    print(json.dumps(report,sort_keys=True,indent=2))
    return 0 if report["controller_acknowledged_remote"] else 4


if __name__=="__main__":
    raise SystemExit(main())
