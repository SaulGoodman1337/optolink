#!/usr/bin/env python3
"""Offline attested audit of 2026-10-12 WB2A C5/F9 fault-history chronology.

Input is a bounded privacy-filtered ORIGINAL systemd-journal excerpt, not a
synthesized heater trace. The first JOURNAL read of an archive entry is later
than the fault time encoded in the ECU's 9-byte history slot. This auditor
preserves that difference and never claims to have proven root cause.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timedelta
import hashlib
import json
from pathlib import Path
import re
import sys

ORIGINAL = Path("/tmp/wb2a-c5-f9-incident-journal-20261012.txt")
SHA256 = "88e8987a53e850dd91c36a4b16c3089b64d37220b6a8084ae66831b99250fb79"
TEST_END_LOCAL = datetime.fromisoformat("2026-10-12T11:18:42+02:00")
EXPECTED_FAULTS = {
    "f92026101201024208": "2026-10-12T02:42:08+02:00",
    "c52026101201112240": "2026-10-12T11:22:40+02:00",
    "f92026101201122224": "2026-10-12T12:22:24+02:00",
}
MATCH = re.compile(
    r"^(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d[+-]\d\d:\d\d) "
    r".*?: rx ((?:[0-9a-f]{2} ){8}[0-9a-f]{2})$",
    re.I,
)


class IncidentRejected(ValueError):
    pass


def decode_slot(encoded):
    if not re.fullmatch("[0-9a-f]{18}", encoded):
        raise IncidentRejected("invalid 9-byte slot")
    payload = encoded[2:]
    parts = [payload[:4], payload[4:6], payload[6:8], payload[8:10],
             payload[10:12], payload[12:14], payload[14:16]]
    if not all(x.isdecimal() for x in parts):
        raise IncidentRejected("invalid BCD date")
    try:
        local = datetime(int(parts[0]), int(parts[1]), int(parts[2]),
                         int(parts[4]), int(parts[5]), int(parts[6]),
                         tzinfo=TEST_END_LOCAL.tzinfo)
    except ValueError as err:
        raise IncidentRejected("invalid controller date") from err
    return {"code": encoded[:2].upper(), "fault_at_controller_time": local.isoformat(),
            "raw9": encoded, "weekday_raw": parts[3]}


def analyze(raw: bytes, *, pin: bool = True):
    digest = hashlib.sha256(raw).hexdigest()
    if pin and digest != SHA256:
        raise IncidentRejected("original journal sha256 mismatch")
    if not 100 <= len(raw) <= 45_000:
        raise IncidentRejected("journal excerpt missing or too large")
    text = raw.decode("utf-8")
    entries = {}
    warnings = 0
    timeouts = 0
    for line in text.splitlines():
        if "[WARNING]: GFA_READ" in line:
            warnings += 1
        if "rx telegr timeout" in line or "Timeout waiting for 0x05" in line:
            timeouts += 1
        m = MATCH.fullmatch(line)
        if not m:
            continue
        observed, payload = m.groups()
        rawhex = payload.lower().replace(" ", "")
        if rawhex not in EXPECTED_FAULTS:
            raise IncidentRejected("unknown fault archive event in original journal")
        controller = decode_slot(rawhex)
        if controller["fault_at_controller_time"] != EXPECTED_FAULTS[rawhex]:
            raise IncidentRejected("wrong controller BCD")
        seen = datetime.fromisoformat(observed)
        if seen.tzinfo is None:
            raise IncidentRejected("missing host observer timezone")
        event = entries.setdefault(rawhex, {"controller": controller,
                                            "first_observed_host_iso": seen.isoformat(),
                                            "last_observed_host_iso": seen.isoformat(),
                                            "observations": 0})
        event["observations"] += 1
        event["last_observed_host_iso"] = seen.isoformat()
    if set(entries) != set(EXPECTED_FAULTS):
        raise IncidentRejected("three distinct original fault events not all present")
    if not warnings or not timeouts:
        raise IncidentRejected("journal timing and protocol recovery evidence missing")
    for rawhex, event in entries.items():
        actual = datetime.fromisoformat(event["first_observed_host_iso"])
        occurred = datetime.fromisoformat(event["controller"]["fault_at_controller_time"])
        if actual < occurred:
            raise IncidentRejected("first-observed log predates encoded controller fault")
        event["logger_capture_delay_s"] = int((actual - occurred).total_seconds())
        event["seconds_since_test_end"] = round((occurred - TEST_END_LOCAL).total_seconds(), 3)
    if entries["f92026101201024208"]["seconds_since_test_end"] >= 0:
        raise IncidentRejected("older F9 must predate today's specific GWG test")
    if not 0 < entries["c52026101201112240"]["seconds_since_test_end"] < 900:
        raise IncidentRejected("C5 not in documented delayed interval")
    if not 3600 < entries["f92026101201122224"]["seconds_since_test_end"] < 4500:
        raise IncidentRejected("F9 not in documented one-hour delayed interval")
    return {
        "audit": "PASS",
        "device": "WB2A/VDensHO1/20C2",
        "historical_f9_before_last_gwg_test": True,
        "new_c5_roughly_4_minutes_after_last_gwg_test": True,
        "new_f9_roughly_64_minutes_after_last_gwg_test": True,
        "cause_established": False,
        "journal_sha256": digest,
        "test_end_local": TEST_END_LOCAL.isoformat(),
        "distinct_fault_events": [entries[k] for k in EXPECTED_FAULTS],
        "gfa_fast_retry_warnings_in_excerpt": warnings,
        "optolink_transport_timeouts_in_excerpt": timeouts,
        "controller_writes_from_this_audit": 0,
        "safety_note": "0x5738 is GFA status, not an audit of archived system C5/F9",
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input", type=Path, default=ORIGINAL)
    p.add_argument("--output", type=Path)
    args = p.parse_args()
    out = analyze(args.input.read_bytes(), pin=True)
    text = json.dumps(out, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(text, encoding="utf-8")
    print(text, end="")


if __name__ == "__main__":
    try:
        main()
    except (OSError, IncidentRejected, UnicodeError) as exc:
        print("INCIDENT_AUDIT_REJECTED:", exc, file=sys.stderr)
        sys.exit(2)
