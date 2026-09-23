#!/usr/bin/env python3
"""
Read-only analyzer for external dumps of WB2A coding plugs.

The tool never writes to a programmer or device. It only analyzes files that
were already dumped externally.

Typical use:
    python3 analyze-wb2a-coding-plug-dumps.py dump1.bin dump2.bin dump3.bin

Useful goals:
- prove repeatability of multiple reads;
- hash/archive each dump;
- show exact byte/bit differences;
- find known local identity bytes such as 20 15 02 01;
- find possible ASCII/BCD representations of the coding-plug part number;
- produce a machine-readable JSON report for later correlation work.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import statistics
from collections import Counter
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Iterable


KNOWN_PATTERNS = {
    "coding_card_identity_2015_0201": bytes.fromhex("20 15 02 01"),
    "part_number_ascii_7833971": b"7833971",
    # Packed BCD-like representations worth checking, without asserting that
    # the physical coding plug actually stores the number this way.
    "part_number_bcd_78_33_97_1f": bytes.fromhex("78 33 97 1f"),
    "part_number_bcd_07_83_39_71": bytes.fromhex("07 83 39 71"),
}


@dataclass
class DumpInfo:
    path: str
    size: int
    sha256: str
    byte_entropy: float
    unique_byte_values: int
    longest_ff_run: int
    longest_00_run: int
    printable_ascii_strings: list[dict]
    known_pattern_hits: dict[str, list[int]]


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def shannon_entropy(data: bytes) -> float:
    if not data:
        return 0.0
    counts = Counter(data)
    n = len(data)
    return -sum((c / n) * math.log2(c / n) for c in counts.values())


def longest_run(data: bytes, value: int) -> int:
    best = current = 0
    for b in data:
        if b == value:
            current += 1
            best = max(best, current)
        else:
            current = 0
    return best


def find_all(data: bytes, pattern: bytes) -> list[int]:
    hits: list[int] = []
    start = 0
    while True:
        idx = data.find(pattern, start)
        if idx < 0:
            break
        hits.append(idx)
        start = idx + 1
    return hits


def printable_strings(data: bytes, min_len: int = 4, max_results: int = 100) -> list[dict]:
    results: list[dict] = []
    start = None

    def flush(end: int) -> None:
        nonlocal start
        if start is None:
            return
        if end - start >= min_len:
            raw = data[start:end]
            results.append({
                "offset": start,
                "length": len(raw),
                "text": raw.decode("ascii", errors="replace"),
            })
        start = None

    for i, b in enumerate(data):
        if 0x20 <= b <= 0x7E:
            if start is None:
                start = i
        else:
            flush(i)
            if len(results) >= max_results:
                break
    if len(results) < max_results:
        flush(len(data))
    return results[:max_results]


def describe(path: Path, data: bytes) -> DumpInfo:
    return DumpInfo(
        path=str(path),
        size=len(data),
        sha256=sha256(data),
        byte_entropy=round(shannon_entropy(data), 6),
        unique_byte_values=len(set(data)),
        longest_ff_run=longest_run(data, 0xFF),
        longest_00_run=longest_run(data, 0x00),
        printable_ascii_strings=printable_strings(data),
        known_pattern_hits={
            name: find_all(data, pattern)
            for name, pattern in KNOWN_PATTERNS.items()
        },
    )


def bit_count(x: int) -> int:
    return x.bit_count()


def compare_pair(a_name: str, a: bytes, b_name: str, b: bytes, max_diffs: int) -> dict:
    common = min(len(a), len(b))
    byte_diffs = []
    bit_diffs = 0

    for i in range(common):
        if a[i] != b[i]:
            xor = a[i] ^ b[i]
            bit_diffs += bit_count(xor)
            if len(byte_diffs) < max_diffs:
                byte_diffs.append({
                    "offset": i,
                    "offset_hex": f"0x{i:08X}",
                    "a": a[i],
                    "a_hex": f"{a[i]:02X}",
                    "b": b[i],
                    "b_hex": f"{b[i]:02X}",
                    "xor_hex": f"{xor:02X}",
                    "changed_bits": bit_count(xor),
                })

    differing_bytes_total = sum(1 for i in range(common) if a[i] != b[i])
    trailing = abs(len(a) - len(b))
    return {
        "a": a_name,
        "b": b_name,
        "identical": a == b,
        "common_length": common,
        "size_a": len(a),
        "size_b": len(b),
        "differing_bytes_total": differing_bytes_total,
        "differing_bits_in_common_range": bit_diffs,
        "size_difference_bytes": trailing,
        "first_differences": byte_diffs,
    }


def consensus_map(blobs: list[bytes]) -> dict:
    if len(blobs) < 2:
        return {}
    min_len = min(map(len, blobs))
    differing_offsets = []
    stable = 0
    for i in range(min_len):
        vals = {b[i] for b in blobs}
        if len(vals) == 1:
            stable += 1
        else:
            differing_offsets.append({
                "offset": i,
                "offset_hex": f"0x{i:08X}",
                "values_hex": [f"{b[i]:02X}" for b in blobs],
            })
    return {
        "common_length": min_len,
        "stable_offsets": stable,
        "differing_offsets_total": len(differing_offsets),
        "first_differing_offsets": differing_offsets[:500],
    }


def hexdump_context(data: bytes, offset: int, radius: int = 16) -> dict:
    start = max(0, offset - radius)
    end = min(len(data), offset + radius + 1)
    return {
        "offset": offset,
        "window_start": start,
        "window_end": end,
        "hex": data[start:end].hex(" "),
    }


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Read-only analyzer for external WB2A coding-plug dumps."
    )
    ap.add_argument("dumps", nargs="+", type=Path, help="Raw dump files")
    ap.add_argument(
        "--json",
        type=Path,
        default=Path("coding-plug-dump-analysis.json"),
        help="Output JSON report path",
    )
    ap.add_argument(
        "--max-diffs",
        type=int,
        default=200,
        help="Maximum detailed byte differences per file pair",
    )
    ap.add_argument(
        "--context-offset",
        action="append",
        default=[],
        help="Additional byte offset to show context for; accepts decimal or 0x...",
    )
    args = ap.parse_args()

    paths: list[Path] = []
    blobs: list[bytes] = []

    for p in args.dumps:
        if not p.is_file():
            ap.error(f"not a file: {p}")
        paths.append(p)
        blobs.append(p.read_bytes())

    infos = [describe(p, b) for p, b in zip(paths, blobs)]

    comparisons = []
    for i in range(len(blobs)):
        for j in range(i + 1, len(blobs)):
            comparisons.append(
                compare_pair(
                    str(paths[i]), blobs[i],
                    str(paths[j]), blobs[j],
                    args.max_diffs,
                )
            )

    extra_offsets = []
    for raw in args.context_offset:
        extra_offsets.append(int(raw, 0))

    contexts = {}
    for p, b in zip(paths, blobs):
        per_file = {}
        # Include contexts around every known-pattern hit.
        interesting = set(extra_offsets)
        for pattern in KNOWN_PATTERNS.values():
            interesting.update(find_all(b, pattern))
        for off in sorted(interesting):
            if 0 <= off < len(b):
                per_file[f"0x{off:X}"] = hexdump_context(b, off)
        contexts[str(p)] = per_file

    report = {
        "format": 1,
        "purpose": "read-only WB2A coding-plug dump comparison",
        "known_patterns": {
            name: pattern.hex(" ")
            for name, pattern in KNOWN_PATTERNS.items()
        },
        "dumps": [asdict(x) for x in infos],
        "pairwise_comparisons": comparisons,
        "multi_dump_consensus": consensus_map(blobs),
        "contexts": contexts,
    }

    args.json.write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print("WB2A coding-plug dump analysis")
    print("=" * 34)
    for info in infos:
        print(f"{info.path}")
        print(f"  size:    {info.size} bytes")
        print(f"  SHA256:  {info.sha256}")
        print(f"  entropy: {info.byte_entropy:.4f} bits/byte")
        for name, hits in info.known_pattern_hits.items():
            if hits:
                print(
                    f"  hit {name}: "
                    + ", ".join(f"0x{x:X}" for x in hits)
                )

    if comparisons:
        print()
        print("Pairwise comparison")
        print("-" * 19)
        for cmp in comparisons:
            status = "IDENTICAL" if cmp["identical"] else "DIFFERENT"
            print(
                f"{cmp['a']} <-> {cmp['b']}: {status}; "
                f"{cmp['differing_bytes_total']} differing bytes in common range"
            )
            for d in cmp["first_differences"][:20]:
                print(
                    f"  {d['offset_hex']}: "
                    f"{d['a_hex']} -> {d['b_hex']} "
                    f"(xor {d['xor_hex']})"
                )
            if cmp["differing_bytes_total"] > 20:
                print("  ... see JSON report for more")

    print()
    print(f"JSON report: {args.json}")
    print()
    print("Safety: this tool only reads dump files; it performs no device/programmer writes.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
