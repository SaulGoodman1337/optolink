#!/usr/bin/env python3
"""Source-backed GWG 0xAE/0x6E-only compatibility test on WB2A 20C2.

These types/addresses come from real vcontrold GWG profile of DEVICE 2053,
NOT from WB2A vendor evidence. Commands are reads only and do not expose a
program ROM service. Requires independent active systemd restore, exclusive
serial port, originally live KW owner stopped, and pin-matched VS1 settings.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

PORT = Path("/dev/serial/by-id/usb-Silicon_Labs_CP2102_USB_to_UART_Bridge_Controller_0001-if00-port0")
CONF = Path("/opt/optolink/settings_ini.py")
SHA = "e9a120ef37fe17236a7505ee713c8dd338d98d5093ed75dfb34629d7e8f5c42d"
TIMER = "wb2a-gwg-legacy-readtypes-restore-20261012.timer"
OUTPUT = Path("/tmp/wb2a-gwg-legacy-readtypes-live-20261012.json")
ID = "20c20003"
# Exactly the documented legacy 2053 EEPROM/PORT read shapes, never arbitrary
# type or address. Source: openv/vcontrold xml/kw/{vito,vcontrold}.xml.
CASES = (
    ("kw_before", "01f700f804", 4, ID),
    ("gwg_before", "01c7f80404", 4, ID),
    ("2053_eeprom_burner_hours_first", "01ae170204", 2, None),
    ("2053_port_valve_first", "016e010104", 1, None),
    ("2053_port_valve_second", "016e010104", 1, None),
    ("2053_eeprom_burner_hours_second", "01ae170204", 2, None),
    ("gwg_after", "01c7f80404", 4, ID),
    ("kw_after", "01f700f804", 4, ID),
)
ALLOWED = {f for _, f, _, _ in CASES}


class Refused(RuntimeError):
    pass


def is_active(unit):
    return subprocess.run(["systemctl", "is-active", "--quiet", unit],
                          timeout=5, capture_output=True).returncode == 0


def checks(output, execute):
    if not execute or os.geteuid() != 0:
        raise Refused("requires root and explicit execution")
    if output != OUTPUT or output.exists():
        raise Refused("output mismatch or already exists")
    if not PORT.is_char_device() or hashlib.sha256(CONF.read_bytes()).hexdigest() != SHA:
        raise Refused("missing CP2102 or modified original VS1")
    if not is_active(TIMER) or is_active("optolink-splitter.service"):
        raise Refused("independent restore not armed or serial owner still active")


def one(port, wire, size):
    if wire not in ALLOWED or size not in (1, 2, 4):
        raise Refused("unlisted read command rejected")
    frame = bytes.fromhex(wire)
    rec = {"frame": wire, "requested_length": size, "sync": False,
           "reply": "", "raw_tx": ["04"], "raw_rx": [],
           "time_utc": datetime.now(timezone.utc).isoformat()}
    port.reset_input_buffer()
    if port.write(bytes((4,))) != 1:
        raise Refused("failed sync write")
    port.flush()
    deadline = time.monotonic() + 3.0
    while time.monotonic() < deadline:
        sample = port.read(1)
        if sample:
            rec["raw_rx"].append(sample.hex())
        if sample == bytes((5,)):
            rec["sync"] = True
            break
    if not rec["sync"]:
        rec["outcome"] = "SYNC_TIMEOUT"
        return rec
    port.reset_input_buffer()
    if port.write(frame) != len(frame):
        raise Refused("failed fixed read frame write")
    rec["raw_tx"].append(wire)
    port.flush()
    result = bytearray()
    deadline = time.monotonic() + 0.80
    latest = time.monotonic()
    while time.monotonic() < deadline:
        incoming = port.read_all()
        if incoming:
            result.extend(incoming)
            rec["raw_rx"].append(incoming.hex())
            latest = time.monotonic()
            if len(result) > size + 1:
                break
        elif result and time.monotonic() - latest > 0.08:
            break
        else:
            time.sleep(0.005)
    rec["reply"] = result.hex()
    if not result:
        rec["outcome"] = "NO_REPLY"
    elif len(result) != size:
        rec["outcome"] = "UNEXPECTED_LENGTH"
    elif wire == "016e010104" and result == bytes((5,)):
        rec["outcome"] = "AMBIGUOUS_IDLE_ENQ_OR_DATA_05"
    else:
        rec["outcome"] = "LENGTH_MATCH_NO_SEMANTIC_PROOF"
    return rec


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--execute", action="store_true")
    ap.add_argument("--output", type=Path)
    args = ap.parse_args()
    if not args.execute:
        print(json.dumps({"mode": "DRY_RUN", "cases": CASES,
                          "controller_memory_writes": 0}, indent=2))
        return 0
    checks(args.output, execute=True)
    import serial
    result = {"mode": "GWG_2053_READ_OPCODE_COMPARISON_ON_WB2A",
              "device": "WB2A VDensHO1 20C2/0103", "at_utc": datetime.now(timezone.utc).isoformat(),
              "controller_memory_writes": 0, "records": [], "completed": False}
    rc = 1
    try:
        with serial.Serial(str(PORT), baudrate=4800, bytesize=serial.EIGHTBITS,
                           parity=serial.PARITY_EVEN, stopbits=serial.STOPBITS_TWO,
                           timeout=0.025, write_timeout=0.5, exclusive=True,
                           rtscts=False, dsrdtr=False, xonxoff=False) as port:
            for name, wire, size, expect in CASES:
                rec = one(port, wire, size)
                rec["case"] = name
                result["records"].append(rec)
                print(json.dumps(rec, sort_keys=True), flush=True)
                if expect is not None and (
                    not rec["sync"] or rec["reply"] != expect or rec["outcome"] != "LENGTH_MATCH_NO_SEMANTIC_PROOF"
                ):
                    raise Refused("known original WB2A GWG/KW identity mismatch: " + name)
            result["completed"] = True
            rc = 0
    except Exception as exc:
        result["error"] = type(exc).__name__ + ": " + str(exc)
        print("ABORT " + result["error"], flush=True)
    finally:
        result["ended_utc"] = datetime.now(timezone.utc).isoformat()
        with OUTPUT.open("x", encoding="utf-8") as out:
            json.dump(result, out, indent=2, sort_keys=True)
            out.write(chr(10))
        os.chmod(OUTPUT, 0o600)
        print("EVIDENCE=" + str(OUTPUT), flush=True)
    return rc


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Refused as err:
        print("REFUSED", err, file=sys.stderr)
        sys.exit(2)
