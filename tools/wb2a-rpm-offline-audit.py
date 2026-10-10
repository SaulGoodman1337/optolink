#!/usr/bin/env python3
"""Offline-only audit of already captured WB2A P300 RPM candidates.

No pyserial, MQTT, network, subprocess, write/restore or controller imports.
A crosscheck matching P06 is NEVER promoted to a verified P300 RPM source.
"""
from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path


class EvidenceError(ValueError):
    """Corrupt or insufficient archived evidence."""


@dataclass(frozen=True)
class Candidate:
    x: int
    y: int
    flame: bool
    lockout: bool
    coherent: bool


def _byte(value, label):
    if type(value) is not int or value < 0 or value > 255:
        raise EvidenceError(f"{label}: expected a byte")
    return value


def _finite(value, label):
    if type(value) not in (int, float) or not math.isfinite(value):
        raise EvidenceError(f"{label}: expected finite timestamp")
    return float(value)


def qualify_high(cycle):
    c = cycle["candidates"]
    a, b = cycle["first_status"], cycle["last_status"]
    x = _byte(c["0f20"], "0f20")
    y = _byte(c["1c76"], "1c76")
    return (x >= 0x88 and y >= 0x88 and abs(x-y) <= 4
            and a["flame"] is True and b["flame"] is True
            and a["lockout"] is False and b["lockout"] is False
            and cycle["quality"]["status_coherent"] is True
            and not any(cycle["quality"]["native_status_changed_within_pair"].values()))


def classify_plateau(before: list[Candidate], after: list[Candidate],
                     p06_raw: list[int]) -> str:
    """Evaluate one independently timestamped P300/VS1/P300 bracket.

    This function requires the calling code to establish chronological order
    and legitimate original GFA P06 provenance; it never creates an RPM value.
    Even perfect numeric agreement cannot establish physical tachometer origin.
    """
    if len(before) < 2 or len(after) < 2 or len(p06_raw) < 6:
        return "INSUFFICIENT_BRACKET"
    if any(not isinstance(c, Candidate) for c in before + after):
        raise EvidenceError("candidate records require explicit typed evidence")
    for c in before + after:
        _byte(c.x, "candidate 0f20")
        _byte(c.y, "candidate 1c76")
        if type(c.flame) is not bool or type(c.lockout) is not bool or type(c.coherent) is not bool:
            raise EvidenceError("candidate status evidence missing")
    for p in p06_raw:
        _byte(p, "P06 raw")
    if 0xff in p06_raw:
        return "INVALID_P06_FF"
    if (not all(c.flame and not c.lockout and c.coherent for c in before + after)
            or any(abs(c.x - c.y) > 2 for c in before + after)):
        return "TRANSITION_OR_UNKNOWN"
    xs = [c.x for c in before + after]
    ys = [c.y for c in before + after]
    if min(xs) == 0 or min(p06_raw) == 0:
        return "NO_POSITIVE_PLATEAU"
    if (max(xs)-min(xs) > 2 or max(ys)-min(ys) > 2
            or max(p06_raw) != min(p06_raw)):
        return "TRANSITION_OR_UNKNOWN"
    delta = abs((sum(xs) / len(xs) - 1) - p06_raw[0])
    if delta <= 1:
        return "NUMERICALLY_CONSISTENT_NOT_VERIFIED"
    if delta > 2:
        return "P06_PLUS_ONE_NUMERIC_MISMATCH"
    return "TRANSITION_OR_UNKNOWN"


def _load_jsonl(path: Path, max_rows: int):
    if not path.is_file():
        raise EvidenceError(f"missing input: {path}")
    with path.open("r", encoding="utf-8") as f:
        for i, line in enumerate(f, start=1):
            if i > max_rows:
                raise EvidenceError("row limit exceeded")
            try:
                row = json.loads(line)
            except (ValueError, TypeError) as exc:
                raise EvidenceError(f"invalid JSON line {i} in {path.name}") from exc
            if type(row) is not dict:
                raise EvidenceError(f"expected JSON object at line {i}")
            yield row


def audit(cycles_path: Path, vs1_path: Path, core_path: Path | None = None) -> dict:
    counts = Counter()
    values = Counter()
    seen, prev_cycle, prev_end, prev_x, high_run = 0, 0, -float("inf"), None, 0
    high_runs = []
    first_high_mono, last_high_mono = None, None
    high_timestamps = []
    checksum_checked = 0
    core = core_path.open("rb") if core_path is not None else None
    try:
        for row in _load_jsonl(cycles_path, 100_000):
            seq = row["cycle"]
            if type(seq) is not int or seq != prev_cycle + 1:
                raise EvidenceError("cycle IDs must be consecutive from 1")
            start = _finite(row["start_monotonic"], "start")
            end = _finite(row["end_monotonic"], "end")
            if start < prev_end or end < start:
                raise EvidenceError("nonmonotonic cycle timestamps")
            prev_end, prev_cycle = end, seq
            x = _byte(row["candidates"]["0f20"], "0f20")
            y = _byte(row["candidates"]["1c76"], "1c76")
            a, b = row["first_status"], row["last_status"]
            for status in (a,b):
                _finite(status["rx_monotonic"], "status timestamp")
                _byte(status["byte0"], "FC01 byte0")
                _byte(status["byte9"], "FC01 byte9")
                if type(status["flame"]) is not bool or type(status["lockout"]) is not bool:
                    raise EvidenceError("missing flame/lockout evidence")
            if a["rx_monotonic"] > b["rx_monotonic"]:
                raise EvidenceError("FC01 bracket inverted")
            if type(row["quality"]["status_coherent"]) is not bool:
                raise EvidenceError("status coherence not boolean")
            if core is not None:
                if row["core_length"] != 64 or row["core_offset"] != (seq-1)*64:
                    raise EvidenceError("invalid core pair offset/length")
                raw = core.read(64)
                if len(raw) != 64 or hashlib.sha256(raw).hexdigest() != row["core_sha256"]:
                    raise EvidenceError(f"core SHA256 mismatch: cycle {seq}")
                checksum_checked += 1
            seen += 1
            values[x] += 1
            counts["coherent"] += row["quality"]["status_coherent"] is True
            counts["mirrors_equal"] += row["candidates"]["copies_equal"] is True
            counts["candidate_equal"] += x == y
            counts["flame_on"] += a["flame"] is True and b["flame"] is True
            if prev_x is not None and prev_x != x:
                counts["candidate_changes"] += 1
            prev_x = x
            if qualify_high(row):
                counts["high_eligible_single"] += 1
                high_timestamps.append(end)
                if first_high_mono is None:
                    first_high_mono = end
                last_high_mono = end
                high_run += 1
            elif high_run:
                high_runs.append(high_run)
                high_run = 0
        if high_run:
            high_runs.append(high_run)
        if not seen:
            raise EvidenceError("no captured cycles")
        if core is not None and core.read(1):
            raise EvidenceError("core file has trailing bytes")
    finally:
        if core is not None:
            core.close()

    vs1_p06 = []
    sides = Counter()
    for row in _load_jsonl(vs1_path, 100_000):
        if row.get("key") != "P06":
            continue
        rawhex = row.get("hex")
        if not isinstance(rawhex, str) or len(rawhex) != 2:
            raise EvidenceError("invalid VS1 P06 raw byte")
        try:
            raw = int(rawhex,16)
        except ValueError as exc:
            raise EvidenceError("invalid VS1 P06 hex") from exc
        if not (0 <= raw <= 255):
            raise EvidenceError("invalid VS1 P06")
        stamp = _finite(row["t_monotonic"], "VS1 P06 timestamp")
        side = row.get("side")
        if not isinstance(side,str):
            raise EvidenceError("VS1 P06 side missing")
        sides[side] += 1
        if row.get("valid") is True and raw != 255:
            vs1_p06.append((stamp,raw,side))

    # An open P300 stream with separate PRE/POST reference samples cannot
    # establish any contemporaneous P06 match, even when a number happens to fit.
    # Never construct a P300 actual-RPM value from x/y or native FC01.
    nearest_gap = None
    if high_timestamps and vs1_p06:
        nearest_gap = min(abs(t - r[0]) for t in high_timestamps for r in vs1_p06)

    return {
        "classification": "INCONCLUSIVE_NO_TIMED_POSITIVE_P06_BRACKET",
        "p300_actual_p06_verified": False,
        "p300_rpm_value": None,
        "cycles": seen,
        "core_sha256_checked": checksum_checked,
        "candidate_0f20_counts": dict(sorted(values.items())),
        "candidate_0f20_distinct": len(values),
        "candidate_0f20_changes": counts["candidate_changes"],
        "candidate_0f20_equals_1c76": counts["candidate_equal"],
        "status_coherent_cycles": counts["coherent"],
        "status_copies_equal": counts["mirrors_equal"],
        "flame_both_on_cycles": counts["flame_on"],
        "high_eligible_single_cycles": counts["high_eligible_single"],
        "high_eligible_runs_min_two": sum(n >= 2 for n in high_runs),
        "high_eligible_max_consecutive": max(high_runs, default=0),
        "high_first_monotonic": first_high_mono,
        "high_last_monotonic": last_high_mono,
        "vs1_p06_valid_count": len(vs1_p06),
        "vs1_p06_valid_positive_levels": sorted({x for _,x,_ in vs1_p06 if x > 0}),
        "vs1_p06_reference_sides": dict(sorted(sides.items())),
        "high_to_nearest_p06_seconds": round(nearest_gap, 3) if nearest_gap is not None else None,
        "no_serial_actions": True,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cycles", type=Path, required=True)
    parser.add_argument("--vs1", type=Path, required=True)
    parser.add_argument("--core", type=Path, default=None)
    args = parser.parse_args()
    print(json.dumps(audit(args.cycles,args.vs1,args.core),indent=2,sort_keys=True))


if __name__ == "__main__":
    main()
