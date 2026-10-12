#!/usr/bin/env python3
"""Read-only WB2A fault archive gate; baseline/compare via original VS1 owner.

For all live hardware research: capture before intervention; restore *using the
independent existing hardware-session rollback*; then capture immediately and
again later. Compare COMPLETE system and GFA archives, not just GFA status
0x5738, which can be 00 even if a C5 system fault occurred.

No direct CP2102 open; only whitelisted VS1 Virtual_READ through existing
optolink-debug MQTT client. No reset, serial protocol switch, controller write,
systemd stop, or device service installation. Baselines are private (mode 0600).
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

DEVICE_ID = "20c2000300000103"
CONFIG = Path("/opt/optolink/settings_ini.py")
CONFIG_SHA = "e9a120ef37fe17236a7505ee713c8dd338d98d5093ed75dfb34629d7e8f5c42d"
DEBUG = Path("/usr/local/bin/optolink-debug")
SYSTEM = tuple((f"system_{i+1:02d}", 0x7507 + i * 9, 9) for i in range(10))
GFA = tuple((f"gfa_{i+1:02d}", 0x7590 + i * 9, 9) for i in range(20))
CONTROLS = (("device_id", 0x00F8, 8),
            ("gfa_current", 0x5738, 1),
            ("system_current", 0x0A82, 1))
PLAN = CONTROLS + SYSTEM + GFA
EXPECTED_NAMES = tuple(t[0] for t in PLAN)
MAX_BYTES = 100_000
LINE = re.compile(r"^read;0x([0-9a-f]+);([0-9]+)\s+<- openv/resp: ([0-9]+);0x([0-9a-f]+);([0-9a-f]*)$", re.I)


class SafetyAlarm(RuntimeError):
    pass


def read_reply(output: str, addr: int, length: int) -> str:
    if not isinstance(output, str):
        raise SafetyAlarm("missing original owner response")
    matches = []
    for line in output.splitlines():
        candidate = LINE.fullmatch(line.strip())
        if candidate:
            matches.append(candidate)
    if len(matches) != 1:
        raise SafetyAlarm(f"ambiguous/missing MQTT read 0x{addr:04X}")
    request, request_len, status, returned, payload = matches[0].groups()
    if (int(request, 16) != addr or int(returned, 16) != addr
            or int(request_len) != length or int(status) != 1
            or len(payload) != length * 2):
        raise SafetyAlarm(f"wrong address/length/status in 0x{addr:04X}")
    try:
        bytes.fromhex(payload)
    except ValueError as err:
        raise SafetyAlarm("nonhex response") from err
    return payload.lower()


def check_host():
    if not DEBUG.is_file() or not CONFIG.is_file():
        raise SafetyAlarm("missing original VS1 owner or client")
    if hashlib.sha256(CONFIG.read_bytes()).hexdigest() != CONFIG_SHA:
        raise SafetyAlarm("original VS1 config revision changed")
    service = subprocess.run(["systemctl", "is-active", "--quiet", "optolink-splitter.service"],
                             capture_output=True, timeout=6, check=False)
    if service.returncode != 0:
        raise SafetyAlarm("VS1 original serial owner is not active")


def request(addr: int, length: int) -> str:
    if (addr, length) not in {(a, size) for _, a, size in PLAN}:
        raise SafetyAlarm(f"unapproved fault gate read: 0x{addr:04X}/{length}")
    command = f"read;0x{addr:04x};{length}"
    process = subprocess.run([str(DEBUG), "request", command, "--timeout", "7"],
                             capture_output=True, text=True, timeout=10, check=False)
    if process.returncode != 0:
        raise SafetyAlarm(f"VS1 read failed on 0x{addr:04X}: code={process.returncode}")
    return read_reply(process.stdout, addr, length)


def snapshot(reader=request, *, include_gfa_history=True):
    plan = PLAN if include_gfa_history else CONTROLS + SYSTEM
    result = {}
    begun = datetime.now(timezone.utc)
    for name, addr, length in plan:
        result[name] = reader(addr, length)
    assert set(result) == {x[0] for x in plan}
    report = {
        "schema": 1,
        "captured_at_utc": datetime.now(timezone.utc).isoformat(),
        "began_at_utc": begun.isoformat(),
        "owner": "optolink-splitter.service",
        "access": "single_owner_VS1_VIRTUAL_READ_ONLY",
        "checked_all_system_slots": True,
        "checked_all_gfa_slots": include_gfa_history,
        "controller_writes": 0,
        "values": result,
    }
    if result["device_id"] != DEVICE_ID:
        raise SafetyAlarm("different controller identity or SW revision")
    report["active_fault_at_capture"] = (
        result["gfa_current"] != "00" or result["system_current"] != "00"
    )
    return report


def archive_display(raw: str, *, gfa: bool = False):
    if not isinstance(raw, str) or len(raw) != 18 or not re.fullmatch(r"[0-9a-f]{18}", raw):
        raise SafetyAlarm("invalid 9-byte archive")
    date = raw[2:]
    if date == "ffffffffffffffff":
        return {"raw": raw, "code": raw[:2], "controller_time": None, "empty_timestamp": True}
    parts = [date[:4], date[4:6], date[6:8],
             date[8:10], date[10:12], date[12:14], date[14:16]]
    if not all(x.isdecimal() for x in parts):
        raise SafetyAlarm("invalid fault BCD timestamp")
    try:
        datetime(int(parts[0]), int(parts[1]), int(parts[2]),
                 int(parts[4]), int(parts[5]), int(parts[6]))
    except ValueError as exc:
        raise SafetyAlarm("unparseable fault BCD timestamp") from exc
    return {
        "raw": raw,
        "code": raw[:2].upper(),
        "controller_time": f"{parts[0]}-{parts[1]}-{parts[2]}T{parts[4]}:{parts[5]}:{parts[6]}",
        "code_meaning_verified": False if gfa else raw[:2].lower() in {"c5", "f9", "bc"},
    }


def validate(report):
    if not isinstance(report, dict) or report.get("schema") != 1:
        raise SafetyAlarm("invalid snapshot format")
    if report.get("controller_writes") != 0 or report.get("owner") != "optolink-splitter.service":
        raise SafetyAlarm("unsafe or wrong-owner snapshot")
    if report.get("access") != "single_owner_VS1_VIRTUAL_READ_ONLY":
        raise SafetyAlarm("untrusted acquisition")
    values = report.get("values")
    if not isinstance(values, dict):
        raise SafetyAlarm("missing fault values")
    expected = list(CONTROLS) + list(SYSTEM)
    if report.get("checked_all_gfa_slots") is True:
        expected += list(GFA)
    if not report.get("checked_all_system_slots") or set(values) != {v[0] for v in expected}:
        raise SafetyAlarm("partial/unknown snapshot cannot pass")
    for name, _, size in expected:
        value = values[name]
        if not isinstance(value, str) or len(value) != size * 2 or re.fullmatch(r"[0-9a-f]+", value) is None:
            raise SafetyAlarm("malformed read result " + name)
        if name in {row[0] for row in SYSTEM + GFA}:
            archive_display(value, gfa=name.startswith("gfa_"))
    if values["device_id"] != DEVICE_ID:
        raise SafetyAlarm("invalid device id")
    for k in ("captured_at_utc", "began_at_utc"):
        try:
            dt = datetime.fromisoformat(report[k])
            if dt.tzinfo is None:
                raise ValueError("timezone absent")
        except (KeyError, ValueError, TypeError) as err:
            raise SafetyAlarm("invalid timestamp") from err
    return values


def compare(before, after) -> dict:
    old = validate(before)
    new = validate(after)
    if set(old) != set(new):
        raise SafetyAlarm("baseline/post mismatch (do not call clean)")
    first = datetime.fromisoformat(before["captured_at_utc"])
    second = datetime.fromisoformat(after["captured_at_utc"])
    interval = (second - first).total_seconds()
    if not 0 <= interval <= 4 * 3600:
        raise SafetyAlarm("stale or time-reversed baseline")
    alarms = []
    for name in ("gfa_current", "system_current"):
        if old[name] != "00":
            alarms.append({"field": name, "kind": "PREEXISTING_ACTIVE_FAULT", "raw": old[name]})
        if new[name] != "00":
            alarms.append({"field": name, "kind": "POST_ACTIVE_FAULT", "raw": new[name]})
    for name in sorted(set(old) - {"device_id", "gfa_current", "system_current"}):
        if old[name] != new[name]:
            alarms.append({
                "field": name, "kind": "FAULT_ARCHIVE_CHANGED",
                "before": archive_display(old[name], gfa=name.startswith("gfa_")),
                "after": archive_display(new[name], gfa=name.startswith("gfa_")),
            })
    return {
        "verdict": "ALARM" if alarms else "NO_CHANGE_OBSERVED",
        "complete_system_archive_checked": True,
        "complete_gfa_archive_checked": bool(before["checked_all_gfa_slots"] and after["checked_all_gfa_slots"]),
        "new_or_active_faults": alarms,
        "sample_age_seconds": round(interval, 3),
        "device": DEVICE_ID,
        "controller_memory_writes": 0,
        "no_change_is_not_guarantee_of_future_healthy_controller": True,
    }


def save(path: Path, result: dict):
    if not path.is_absolute():
        raise SafetyAlarm("write reports to an explicit absolute path")
    encoded = (json.dumps(result, indent=2, sort_keys=True) + "\n").encode("utf-8")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    handle = os.open(path, flags, 0o600)
    try:
        with os.fdopen(handle, "wb") as out:
            out.write(encoded)
    except BaseException:
        raise


def load(path):
    if not path.is_file() or not 32 <= path.stat().st_size <= MAX_BYTES:
        raise SafetyAlarm("missing or oversized snapshot")
    return json.loads(path.read_bytes())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["plan", "snapshot", "compare"])
    parser.add_argument("--baseline", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--system-only", action="store_true",
                        help="skip 20 GFA history slots; result is partial-GFA, not complete")
    args = parser.parse_args()
    if args.action == "plan":
        print(json.dumps({"VS1_read_commands": [
            f"read;0x{addr:04x};{length}" for _, addr, length in
            (CONTROLS + SYSTEM if args.system_only else PLAN)],
            "hardware_writes": 0, "protocol_switch": False,
            "requires_existing_VS1_owner": True}, indent=2))
        return 0
    if args.output is None:
        parser.error("snapshot and compare require --output absolute path")
    check_host()
    now = snapshot(include_gfa_history=not args.system_only)
    validate(now)
    if args.action == "snapshot":
        save(args.output, now)
        if now["active_fault_at_capture"]:
            print("ALERT: active controller fault; baseline saved, experiment forbidden",
                  file=sys.stderr)
            return 25
        print("FAULT_BASELINE_COMPLETE " + str(args.output))
        return 0
    if args.baseline is None:
        parser.error("compare requires --baseline")
    before = load(args.baseline)
    verdict = compare(before, now)
    save(args.output, {"before_sha256": hashlib.sha256(args.baseline.read_bytes()).hexdigest(),
                       "post_snapshot": now, "comparison": verdict})
    print(json.dumps(verdict, indent=2, sort_keys=True))
    if verdict["verdict"] != "NO_CHANGE_OBSERVED":
        print("ALERT: fault status/archive changed; stop further hardware research; report to user",
              file=sys.stderr)
        return 25
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (SafetyAlarm, OSError, subprocess.TimeoutExpired, json.JSONDecodeError) as exc:
        print("ALERT_UNVERIFIED: " + str(exc), file=sys.stderr)
        sys.exit(26)
