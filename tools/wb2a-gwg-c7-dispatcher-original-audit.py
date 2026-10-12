#!/usr/bin/env python3
"""Offline verification of the REAL WB2A/20C2 GWG C7 dispatcher acceptance log.

Checks TX/RX, EOT/ENQ pairs, seven exact identity responses and their
correspondence with historical known-good original readings. NO serial I/O.
The SHA pin applies ONLY to the original, unedited root-owned capture.
"""
from __future__ import annotations
import argparse
from collections import Counter
from datetime import datetime
import hashlib
import json
from pathlib import Path
import sys

CAPTURE = Path("/tmp/wb2a-gwg-c7-dispatcher-live-20261012.json")
ORIGINAL_SHA = "ee38ef08f950c999ed19da9630e789cc69b1f61642b932be5dca3101a163b824"
EXPECTED = (
    ("kw_baseline", "read;0x00f8;4", "01f700f804", "20c20003"),
    ("gwg_original_2010", "gwgread;0xF8;4", "01c7f80404", "20c20003"),
    ("kw_after_gwg", "read;0x00f8;4", "01f700f804", "20c20003"),
    ("gwg_block8", "gwgread;0xF8;8", "01c7f80804", "20c2000300000103"),
    ("kw_block8", "read;0x00f8;8", "01f700f808", "20c2000300000103"),
    ("gwg_f9_overlap", "gwgread;0xF9;3", "01c7f90304", "c20003"),
    ("kw_final", "read;0x00f8;4", "01f700f804", "20c20003"),
)
EXPECTED_TX = tuple(x for _, _, request, _ in EXPECTED for x in ("04", request))


class EvidenceRejected(ValueError):
    pass


def audit(content: bytes, *, pinned: bool = False) -> dict:
    actual_hash = hashlib.sha256(content).hexdigest()
    if pinned and actual_hash != ORIGINAL_SHA:
        raise EvidenceRejected("source hash changed")
    try:
        doc = json.loads(content)
    except (ValueError, UnicodeError) as exc:
        raise EvidenceRejected("invalid JSON") from exc
    if not doc.get("complete") or doc.get("failure"):
        raise EvidenceRejected("capture incomplete/failed")
    if doc.get("device") != "WB2A/VDensHO1 20C2/0103" or doc.get("controller_writes") != 0:
        raise EvidenceRejected("device identity or no-write assurance changed")
    if doc.get("configuration_sha256") != (
        "e9a120ef37fe17236a7505ee713c8dd338d98d5093ed75dfb34629d7e8f5c42d"
    ):
        raise EvidenceRejected("original configuration mismatch")
    records = doc.get("requests")
    events = doc.get("raw_uart_events")
    if not isinstance(records, list) or len(records) != len(EXPECTED):
        raise EvidenceRejected("missing or extra dispatched requests")
    if not isinstance(events, list):
        raise EvidenceRejected("UART trace missing")
    for row, (name, command, frame, result) in zip(records, EXPECTED):
        if not isinstance(row, dict) or (
            row.get("case"), row.get("command"), row.get("reply"), row.get("status")
        ) != (name, command, result, 1):
            raise EvidenceRejected("dispatcher reply mismatch: " + name)
        if row.get("elapsed_seconds", 999) > 15:
            raise EvidenceRejected("unbounded request duration")

    tx = [e.get("bytes") for e in events if e.get("direction") == "tx"]
    if tx != list(EXPECTED_TX):
        raise EvidenceRejected("unexpected transmission or altered order")
    if len(events) < 28:
        raise EvidenceRejected("insufficient raw RX/ENQ evidence")
    for e in events:
        if not isinstance(e, dict) or e.get("direction") not in ("tx", "rx"):
            raise EvidenceRejected("invalid trace direction")
        if not isinstance(e.get("bytes"), str) or len(e["bytes"]) % 2:
            raise EvidenceRejected("invalid hex payload")
        try:
            bytes.fromhex(e["bytes"])
            datetime.fromisoformat(e["time_utc"])
        except (ValueError, KeyError, TypeError) as exc:
            raise EvidenceRejected("invalid raw trace timestamp or hex") from exc

    # Pair each EOT to exactly one ENQ (0x05), then concatenate the response
    # chunks until the next EOT. Response split/byte timings are variable.
    index = 0
    for _, _, request, expected_data in EXPECTED:
        eot = events[index]
        if (eot["direction"], eot["bytes"]) != ("tx", "04"):
            raise EvidenceRejected("missing EOT at beginning of read")
        index += 1
        saw_enq = False
        while index < len(events) and events[index]["direction"] == "rx":
            if events[index]["bytes"] != "05" or saw_enq:
                raise EvidenceRejected("unexpected or duplicate ENQ payload")
            saw_enq = True
            index += 1
        if not saw_enq:
            raise EvidenceRejected("no ENQ before request")
        if index >= len(events) or (events[index]["direction"], events[index]["bytes"]) != ("tx", request):
            raise EvidenceRejected("wrong request frame after ENQ")
        index += 1
        answer = ""
        while index < len(events) and events[index]["direction"] == "rx":
            answer += events[index]["bytes"]
            index += 1
        if answer != expected_data:
            raise EvidenceRejected("raw UART reply differs from dispatcher: " + request)
    if index != len(events):
        raise EvidenceRejected("extra trailing serial bytes")

    start = datetime.fromisoformat(doc["at_utc"])
    end = datetime.fromisoformat(doc["ended_utc"])
    if not 0 <= (end - start).total_seconds() <= 75:
        raise EvidenceRejected("unbounded overall read experiment")
    return {
        "audit": "PASS",
        "source_sha256": actual_hash,
        "device": doc["device"],
        "reads": len(EXPECTED),
        "raw_events": len(events),
        "tx_frames": len(tx),
        "sync_pairs": len(EXPECTED),
        "recovered_rom_bytes": 0,
        "controller_writes": 0,
        "frame_counts": dict(Counter(tx)),
        "elapsed_s": round((end - start).total_seconds(), 3),
        "proof_scope": "GWG_C7_VIRTUAL_READ_VS1_INTEROPERABILITY_ONLY",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=CAPTURE)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--allow-unpinned-fixture", action="store_true")
    args = parser.parse_args()
    if args.allow_unpinned_fixture and args.input.resolve() == CAPTURE:
        parser.error("cannot bypass source SHA on the original hardware evidence")
    result = audit(args.input.read_bytes(), pinned=not args.allow_unpinned_fixture)
    if args.out:
        args.out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (EvidenceRejected, FileNotFoundError) as exc:
        print("REJECTED:", exc, file=sys.stderr)
        sys.exit(2)
