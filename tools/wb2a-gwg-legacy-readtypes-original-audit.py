#!/usr/bin/env python3
"""Offline source-pinned audit: historical 2053 GWG read types on WB2A 20C2.

Only asserts the exact observed response bytes and absence of EEPROM replies.
A 00 reply to 6E/01 is not proof of WB2A physical port semantics.
No serial open, no controller reads/writes.
"""
from __future__ import annotations
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

CAPTURE = Path("/tmp/wb2a-gwg-legacy-readtypes-live-20261012.json")
ORIGINAL_SHA = "527ae8454ff00d8517075aa7a13f7d238a111b7c5d0e2f8a6db3050356e65afc"
EXPECTED = (
    ("kw_before", "01f700f804", "20c20003", "LENGTH_MATCH_NO_SEMANTIC_PROOF"),
    ("gwg_before", "01c7f80404", "20c20003", "LENGTH_MATCH_NO_SEMANTIC_PROOF"),
    ("2053_eeprom_burner_hours_first", "01ae170204", "", "NO_REPLY"),
    ("2053_port_valve_first", "016e010104", "00", "LENGTH_MATCH_NO_SEMANTIC_PROOF"),
    ("2053_port_valve_second", "016e010104", "00", "LENGTH_MATCH_NO_SEMANTIC_PROOF"),
    ("2053_eeprom_burner_hours_second", "01ae170204", "", "NO_REPLY"),
    ("gwg_after", "01c7f80404", "20c20003", "LENGTH_MATCH_NO_SEMANTIC_PROOF"),
    ("kw_after", "01f700f804", "20c20003", "LENGTH_MATCH_NO_SEMANTIC_PROOF"),
)


class AuditRejected(ValueError):
    pass


def analyze(raw: bytes, *, pin: bool = True) -> dict:
    sh = hashlib.sha256(raw).hexdigest()
    if pin and sh != ORIGINAL_SHA:
        raise AuditRejected("original SHA256 mismatch")
    try:
        doc = json.loads(raw)
    except (UnicodeError, ValueError) as exc:
        raise AuditRejected("not a valid JSON capture") from exc
    if doc.get("mode") != "GWG_2053_READ_OPCODE_COMPARISON_ON_WB2A":
        raise AuditRejected("experiment mismatch")
    if doc.get("device") != "WB2A VDensHO1 20C2/0103":
        raise AuditRejected("device mismatch")
    if doc.get("controller_memory_writes") != 0 or not doc.get("completed") or doc.get("error"):
        raise AuditRejected("write, incomplete session, or error")
    records = doc.get("records")
    if not isinstance(records, list) or len(records) != len(EXPECTED):
        raise AuditRejected("missing/extra records")
    for index, (row, (name, tx, rx, outcome)) in enumerate(zip(records, EXPECTED)):
        if not isinstance(row, dict):
            raise AuditRejected(f"invalid record {index}")
        if (row.get("case"), row.get("frame"), row.get("reply"), row.get("outcome")) != (
            name, tx, rx, outcome
        ):
            raise AuditRejected(f"request/result changed for {name}")
        if row.get("sync") is not True or row.get("raw_tx") != ["04", tx]:
            raise AuditRejected(f"invalid EOT/ENQ/TX for {name}")
        declared_size = int(tx[8:10], 16) if tx.startswith("01f7") else int(tx[6:8], 16)
        if row.get("requested_length") != declared_size:
            raise AuditRejected("requested length changed")
        got = row.get("raw_rx")
        if not isinstance(got, list) or not got or got[0] != "05":
            raise AuditRejected("missing ENQ in raw capture")
        if any(not isinstance(fragment, str) for fragment in got):
            raise AuditRejected("nonhex RX fragment")
        try:
            for fragment in got:
                bytes.fromhex(fragment)
            datetime.fromisoformat(row["time_utc"])
        except (ValueError, TypeError, KeyError) as exc:
            raise AuditRejected("malformed RX or timestamp") from exc
        if "".join(got[1:]) != rx:
            raise AuditRejected("raw bytes differ from logical reply")
        if row.get("requested_length") not in (1, 2, 4):
            raise AuditRejected("unexpected len")
    try:
        start = datetime.fromisoformat(doc["at_utc"])
        end = datetime.fromisoformat(doc["ended_utc"])
    except (ValueError, TypeError, KeyError) as exc:
        raise AuditRejected("bad experiment dates") from exc
    if start.tzinfo is None or end.tzinfo is None:
        raise AuditRejected("timestamps must be timezone-aware")
    elapsed = (end - start).total_seconds()
    if not 0 <= elapsed <= 65:
        raise AuditRejected("unbounded experiment")
    counts = Counter(row["frame"] for row in records)
    return {
        "audit": "PASS", "source_sha256": sh,
        "proof": "GWG_6E_ZERO_RESPONSE_2_OF_2;AE_NO_REPLY_2_OF_2",
        "device": doc["device"], "reads": len(records),
        "synchronized_frames": len(records),
        "eeprom_ae_17_reads": counts["01ae170204"],
        "eeprom_ae_17_responses": 0,
        "port_6e_01_reads": counts["016e010104"],
        "port_6e_01_hex_replies": ["00", "00"],
        "controller_memory_writes": 0, "program_rom_bytes_read": 0,
        "physical_port_semantics_proven": False,
        "elapsed_s": round(elapsed, 3),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=CAPTURE)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--allow-synthetic", action="store_true")
    args = parser.parse_args()
    if args.allow_synthetic and args.input.resolve() == CAPTURE:
        parser.error("do not bypass original SHA256 for root capture")
    result = analyze(args.input.read_bytes(), pin=not args.allow_synthetic)
    if args.out is not None:
        args.out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (AuditRejected, FileNotFoundError) as exc:
        print("REJECTED:", exc, file=sys.stderr)
        sys.exit(2)
