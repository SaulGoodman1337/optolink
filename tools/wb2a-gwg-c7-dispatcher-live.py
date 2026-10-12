#!/usr/bin/env python3
"""Short source-backed GWG C7 E2E live read through the REAL request parser.

The only bytes permitted ON WIRE are the historical EOT handshake and fixed
KW F7/GWG C7 identity reads already positively tested on this exact WB2A.
Requires an externally armed independent restore and STOPPED normal serial owner.
No writes to controller RAM/ROM, EEPROM, coding, pump or KM-Bus.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import logging
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
PORT = Path("/dev/serial/by-id/usb-Silicon_Labs_CP2102_USB_to_UART_Bridge_Controller_0001-if00-port0")
ORIGINAL = Path("/opt/optolink/settings_ini.py")
CONFIG_SHA = "e9a120ef37fe17236a7505ee713c8dd338d98d5093ed75dfb34629d7e8f5c42d"
EXPECTED_SOURCE_SHA = {
    "vs12_adapter.py": "67a760e925719225d61e375e9c976743b7bfb2d6bec8a9ea59d612397c4b3de2",
    "requests_util.py": "7cc01e2fb41a56adf0f395a86a2a352411c9632032744eeb59ebfd669c51f790",
}
EXPECTED_STAGE_FILES = {"vs12_adapter.py", "requests_util.py", "optolinkgwg.py"}
OUTPUT = Path("/tmp/wb2a-gwg-c7-dispatcher-live-20261012.json")
TIMER = "wb2a-gwg-c7-dispatcher-restore-20261012.timer"
EXPECTED_ID4 = bytes.fromhex("20c20003")
EXPECTED_ID8 = bytes.fromhex("20c2000300000103")
ALLOWED_FRAMES = frozenset({
    bytes((4,)),
    bytes.fromhex("01f700f804"), bytes.fromhex("01f700f808"),
    bytes.fromhex("01c7f80404"), bytes.fromhex("01c7f80804"),
    bytes.fromhex("01c7f90304"),
})
# One known KW baseline, GWG equivalent, KW return, GWG 8-byte, KW 8-byte,
# GWG interior three-byte view, and final KW response. Zero controller writes.
READS = (
    ("kw_baseline", "read;0x00f8;4", EXPECTED_ID4),
    ("gwg_original_2010", "gwgread;0xF8;4", EXPECTED_ID4),
    ("kw_after_gwg", "read;0x00f8;4", EXPECTED_ID4),
    ("gwg_block8", "gwgread;0xF8;8", EXPECTED_ID8),
    ("kw_block8", "read;0x00f8;8", EXPECTED_ID8),
    ("gwg_f9_overlap", "gwgread;0xF9;3", bytes.fromhex("c20003")),
    ("kw_final", "read;0x00f8;4", EXPECTED_ID4),
)


class Refused(RuntimeError):
    pass


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def active(unit: str) -> bool:
    return subprocess.run(["systemctl", "is-active", "--quiet", unit],
                          capture_output=True, timeout=8).returncode == 0


def prerequisites(stage: Path, output: Path) -> None:
    if os.geteuid() != 0:
        raise Refused("root required to check independent restore")
    if output != OUTPUT or output.exists():
        raise Refused("unexpected or existing output")
    if stage.resolve() == Path("/opt/optolink"):
        raise Refused("staging must not be production")
    if not stage.is_dir() or not PORT.is_char_device():
        raise Refused("missing prepared stage or CP2102")
    if sha(ORIGINAL) != CONFIG_SHA or b"vs1protocol = True" not in ORIGINAL.read_bytes():
        raise Refused("original VS1 configuration changed")
    for name, digest in EXPECTED_SOURCE_SHA.items():
        if sha(Path("/opt/optolink") / name) != digest:
            raise Refused("productive runtime source changed: " + name)
    if not EXPECTED_STAGE_FILES.issubset({p.name for p in stage.iterdir()}):
        raise Refused("incomplete staging")
    for name in EXPECTED_STAGE_FILES:
        if not (stage / name).is_file():
            raise Refused("staged module is not regular file")
    if not active(TIMER):
        raise Refused("independent systemd restoration NOT ARMED")
    if active("optolink-splitter.service"):
        raise Refused("productive serial owner still active")


class TracedPort:
    """No new serial owner; wrapper around the single pyserial open."""
    def __init__(self, ser):
        self.ser = ser
        self.events = []

    def event(self, direction, data: bytes) -> None:
        self.events.append({
            "time_utc": datetime.now(timezone.utc).isoformat(),
            "direction": direction, "bytes": data.hex()})

    def write(self, payload):
        raw = bytes(payload)
        if raw not in ALLOWED_FRAMES:
            raise Refused("WHITELIST_REJECTED_SERIAL_TX:" + raw.hex())
        self.event("tx", raw)
        return self.ser.write(raw)

    def read(self, count):
        raw = self.ser.read(count)
        if raw:
            self.event("rx", raw)
        return raw

    def read_all(self):
        raw = self.ser.read_all()
        if raw:
            self.event("rx", raw)
        return raw

    def flush(self):
        return self.ser.flush()

    def reset_input_buffer(self):
        return self.ser.reset_input_buffer()


def run(stage: Path, output: Path) -> int:
    prerequisites(stage, output)
    # The source modules are the staged, AST-validated patches of the actual
    # runtime. Import third-party dependencies from the unchanged live tree.
    import types
    stub = types.ModuleType("logger_util")
    stub.logger = logging.getLogger("gwg-limited-live")
    sys.modules["logger_util"] = stub
    sys.path[:0] = [str(stage), "/opt/optolink"]
    import serial
    import requests_util
    import vs12_adapter
    if Path(requests_util.__file__).parent.resolve() != stage.resolve():
        raise Refused("wrong request parser")
    if Path(vs12_adapter.__file__).parent.resolve() != stage.resolve():
        raise Refused("wrong adapter")
    if Path(vs12_adapter.optolinkgwg.__file__).parent.resolve() != stage.resolve():
        raise Refused("wrong GWG backend")
    if vs12_adapter.VS2:
        raise Refused("P300 incompatible with short VS1/GWG C7 read")

    evidence = {
        "experiment": "REAL_GWG_C7_ON_EXISTING_OWNER_DISPATCHER",
        "at_utc": datetime.now(timezone.utc).isoformat(),
        "device": "WB2A/VDensHO1 20C2/0103",
        "stage": str(stage), "configuration_sha256": sha(ORIGINAL),
        "controller_writes": 0, "flash_operations": 0,
        "requests": [], "raw_uart_events": [], "complete": False,
    }
    rc = 1
    try:
        with serial.Serial(str(PORT), baudrate=4800, bytesize=serial.EIGHTBITS,
                           parity=serial.PARITY_EVEN, stopbits=serial.STOPBITS_TWO,
                           timeout=0.025, write_timeout=0.5,
                           rtscts=False, dsrdtr=False, xonxoff=False,
                           exclusive=True) as ser:
            wire = TracedPort(ser)
            vs12_adapter.optolinkvs1.last_comm = float("-inf")
            for label, cmd, expected in READS:
                t = time.monotonic()
                value = requests_util.response_to_request(cmd, wire)
                record = {
                    "time_utc": datetime.now(timezone.utc).isoformat(),
                    "case": label, "command": cmd, "status": value[0],
                    "reply": bytes(value[1]).hex(), "response": value[3],
                    "elapsed_seconds": round(time.monotonic() - t, 3)}
                evidence["requests"].append(record)
                print(json.dumps(record, sort_keys=True), flush=True)
                if value[0] != 1 or bytes(value[1]) != expected:
                    raise Refused("known WB2A identity mismatch/timeout; stop: " + label)
                # Mimic main owner's per-request olbreath bookkeeping.
                vs12_adapter.reset_vs1sync()
                time.sleep(0.05)
            evidence["complete"] = True
            rc = 0
    except Exception as exc:
        evidence["failure"] = type(exc).__name__ + ": " + str(exc)
        print("LIVE_ABORT " + evidence["failure"], flush=True)
    finally:
        if "wire" in locals():
            evidence["raw_uart_events"] = wire.events
        evidence["ended_utc"] = datetime.now(timezone.utc).isoformat()
        with output.open("x", encoding="utf-8") as handle:
            json.dump(evidence, handle, indent=2, sort_keys=True)
            handle.write(chr(10))
        os.chmod(output, 0o600)
        print("EVIDENCE=" + str(output), flush=True)
    return rc


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--execute", action="store_true")
    ap.add_argument("--stage", type=Path)
    ap.add_argument("--output", type=Path)
    args = ap.parse_args()
    if not args.execute:
        print(json.dumps({"mode": "DRY_RUN", "commands": [x[1] for x in READS],
                          "controller_writes": 0, "serial_opens": 0,
                          "requires_independent_restore": True}, indent=2))
        return 0
    if args.stage is None or args.output is None:
        raise Refused("--execute requires exact --stage and --output")
    return run(args.stage, args.output)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Refused as exc:
        print("REFUSED:", exc, file=sys.stderr)
        sys.exit(2)
