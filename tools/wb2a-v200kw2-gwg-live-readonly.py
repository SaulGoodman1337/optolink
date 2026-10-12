#!/usr/bin/env python3
"""Bounded historical GWG/KW read-only cross-generation test on WB2A 20C2/0103.

MUST be launched ONLY after external, independent systemd original-owner
restore armed and original optolink-splitter stopped. No mode switch, no
controller writes, no serial open without explicit root --execute argument.
The first and last request are actual KW/VS1 F7 00F8 4 ID baseline controls.
GWG legacy requests are public, historical READ opcodes C7, CB and C5 only.
They do not provide full high-ROM bank/address access.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import time

PORT="/dev/serial/by-id/usb-Silicon_Labs_CP2102_USB_to_UART_Bridge_Controller_0001-if00-port0"
EXPECTED_INI_SHA="e9a120ef37fe17236a7505ee713c8dd338d98d5093ed75dfb34629d7e8f5c42d"
EXPECTED_ID=bytes.fromhex("20c20003")
TIMER="wb2a-v200kw2-gwg-legacy-restore-20261012.timer"
OUTPUT="/tmp/wb2a-v200kw2-gwg-legacy-readonly-20261012.json"
PROBE_CASES={
 "kw_baseline_before":bytes.fromhex("01 f7 00 f8 04"),
 "historical_2010_gwg_c7_id":bytes.fromhex("01 c7 f8 04 04"),
 "gwg_cb_legacy_outside_temp_example":bytes.fromhex("01 cb 6f 01 04"),
 "gwg_c5_legacy_xram_6f":bytes.fromhex("01 c5 6f 01 04"),
 "kw_baseline_after":bytes.fromhex("01 f7 00 f8 04"),
}
REPEATS={
 "kw_baseline_before":1,
 "historical_2010_gwg_c7_id":2,
 "gwg_cb_legacy_outside_temp_example":2,
 "gwg_c5_legacy_xram_6f":2,
 "kw_baseline_after":1,
}
EXPECTED_RESPONSE_LENS={
 "kw_baseline_before":4,
 "historical_2010_gwg_c7_id":4,
 "gwg_cb_legacy_outside_temp_example":1,
 "gwg_c5_legacy_xram_6f":1,
 "kw_baseline_after":4,
}
READ_ONLY_OPCODES={0xf7,0xc7,0xcb,0xc5}
assert set(PROBE_CASES)==set(REPEATS)==set(EXPECTED_RESPONSE_LENS)
assert all(v[1] in READ_ONLY_OPCODES for v in PROBE_CASES.values())
assert all(v[0]==1 and len(v)==5 for v in PROBE_CASES.values())


class Refused(RuntimeError):pass


def plan()->dict:
    return {
        "mode":"PINNED_HISTORICAL_GWG_READONLY_PROBE",
        "port":PORT,
        "original_config_sha256":EXPECTED_INI_SHA,
        "cases":{key:{"wire":wire.hex(),"repeats":REPEATS[key],
                      "expected_data_bytes_if_accepted":EXPECTED_RESPONSE_LENS[key]}
                 for key,wire in PROBE_CASES.items()},
        "physical_ROM_high_banks_addressable":False,
        "controller_writes":0,
        "controller_eeprom_writes":0,
        "only_historical_GWG_READ_opcodes":True,
        "systemd_restore_must_be_active_before_serial_open":True,
    }


def validate_host(*,execute=False,systemctl=None,config:bytes|None=None,
                  root=False,port_exists=False):
    if not execute or not root or not port_exists:
        raise Refused("root, exact existing CP2102 and --execute required")
    if type(config) is not bytes or hashlib.sha256(config).hexdigest()!=EXPECTED_INI_SHA:
        raise Refused("original production configuration SHA must be exact")
    if b"vs1protocol = True" not in config:
        raise Refused("original VS1 config flag missing")
    if not systemctl or not systemctl("is-active","--quiet",TIMER):
        raise Refused("independent restore timer was NOT armed")
    if systemctl("is-active","--quiet","optolink-splitter.service"):
        raise Refused("production serial owner still active")


def sync_and_probe(port,wire:bytes,expected_length:int,*,now=time.monotonic,sleep=time.sleep)->dict:
    # Reestablish standard historical 4800 8E2 synchronous KW / GWG state.
    # This 0x04 is EOT/frame synchronization, not a memory-write opcode.
    if wire not in PROBE_CASES.values() or len(wire)!=5 or wire[1] not in READ_ONLY_OPCODES:
        raise Refused("out-of-whitelist or potentially write-bearing frame")
    if expected_length not in (1,4):
        raise Refused("only documented bounded request lengths")
    port.reset_input_buffer()
    n=port.write(bytes([0x04]))
    if n!=1:raise Refused("failed to issue historical EOT")
    port.flush()
    start=now()
    sync_trace=bytearray()
    found=False
    while now()-start<3.0:
        b=port.read(1)
        if b:
            sync_trace.extend(b)
            if b==b"\x05":
                found=True
                break
        else:sleep(0.005)
    if not found:
        return {"tx_hex":wire.hex(),"sync_ok":False,"sync_bytes":sync_trace.hex(),
                "response_hex":"","response_bytes":0,"response_candidate":False}
    port.reset_input_buffer()
    if port.write(wire)!=len(wire):raise Refused("short historical read request")
    port.flush()
    reply=bytearray()
    start=now()
    latest=start
    while now()-start<0.63:
        b=port.read_all()
        if b:
            reply.extend(b);latest=now()
        elif reply and now()-latest>=0.08:break
        else:sleep(0.006)
    return {
        "tx_hex":wire.hex(),"sync_ok":True,"sync_bytes":sync_trace.hex(),
        "response_hex":reply.hex(),"response_bytes":len(reply),
        # This is a *candidate*; opcodes CB/C5 lack a known WB2A expected value.
        "response_candidate":len(reply)==expected_length,
    }


def run(port)->dict:
    report=plan()
    report["status"]="INCOMPLETE"
    report["actual_io"]=0
    report["records"]=[]
    for name,wire in PROBE_CASES.items():
        for rep in range(REPEATS[name]):
            row=sync_and_probe(port,wire,EXPECTED_RESPONSE_LENS[name])
            row["name"]=name;row["rep"]=rep
            report["records"].append(row)
            report["actual_io"]+=int(row["sync_ok"])
            print(json.dumps(row,sort_keys=True),flush=True)
            if name=="kw_baseline_before":
                if not row["sync_ok"] or row["response_hex"]!=EXPECTED_ID.hex():
                    raise Refused("known WB2A VS1 identity baseline failed; no GWG probes")
            if name=="kw_baseline_after":
                if not row["sync_ok"] or row["response_hex"]!=EXPECTED_ID.hex():
                    raise Refused("post-probe WB2A KW identity no longer verified")
    byname=lambda key:[x for x in report["records"] if x["name"]==key]
    c7=byname("historical_2010_gwg_c7_id")
    report["real_WB2A_GWG_C7_direct_read_confirmed"]=(
        len(c7)==2 and all(x["response_hex"]==EXPECTED_ID.hex() and x["sync_ok"] for x in c7)
    )
    report["other_legacy_responses"]={k:[x["response_hex"] for x in byname(k)]
        for k in ("gwg_cb_legacy_outside_temp_example","gwg_c5_legacy_xram_6f")}
    report["GWG_CB_read_family_supported_proven"]=False
    report["GWG_C5_read_family_supported_proven"]=False
    # Even if a 1-byte answer appears, avoid unproven physical-ROM inference.
    report["ROM_20bit_bank_access_proven"]=False
    report["actual_program_ROM_bytes_recovered"]=False
    report["status"]="BOUNDED_READONLY_COMPLETED"
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute",action="store_true")
    parser.add_argument("--output",type=Path)
    args=parser.parse_args()
    if not args.execute:
        print(json.dumps(plan(),indent=2,sort_keys=True))
        return
    if not args.output or str(args.output)!=OUTPUT:
        parser.error("live output must be private, exact pinned /tmp path")
    import subprocess
    def active(*cmd):
        return subprocess.run(["systemctl",*cmd],capture_output=True,timeout=5).returncode==0
    validate_host(execute=True,systemctl=active,
        config=Path("/opt/optolink/settings_ini.py").read_bytes(),
        root=os.geteuid()==0,port_exists=Path(PORT).is_char_device())
    import serial
    # PySerial exclusive ensures a second POSIX port owner cannot silently join.
    with serial.Serial(PORT,baudrate=4800,bytesize=8,
        parity=serial.PARITY_EVEN,stopbits=serial.STOPBITS_TWO,
        timeout=0.07,write_timeout=1.0,exclusive=True) as port:
        try:
            result=run(port)
        finally:
            # Leave the controller in ordinary VS1 sync mode before systemd
            # original owner relaunches (no memory/controller state writes).
            port.write(bytes([0x04]));port.flush()
    args.output.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    print(json.dumps({"status":result["status"],
        "GWG_C7_success":result["real_WB2A_GWG_C7_direct_read_confirmed"],
        "other_response_candidates":result["other_legacy_responses"],
        "controller_writes":0},sort_keys=True))


if __name__=="__main__":main()
