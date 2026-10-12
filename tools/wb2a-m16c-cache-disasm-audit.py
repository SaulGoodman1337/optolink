#!/usr/bin/env python3
"""Manifest-attested SRAM cache region: M16C disassembly vs histogram controls.

This parser accepts ONLY Ghidra 12.1.4 fixed-seed headless IL/ISA metrics for
original target bytes and deterministic histogram-preserving shuffle controls.
It makes no executable-code attribution from disassembly density alone.
No serial interface, no controller I/O, no subprocess, no remote access.

The validated first 79 SRAM images are stored in a separate, SHA-pinned source
archive; the original 12926-byte window is SHA-attested below. The Ghidra
workbench itself is private (not included in git). Source-run provenance is
included only when the original complete Ghidra/JDK distributions match
official SHA256 declarations.
"""
from __future__ import annotations
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import random
import re
import statistics

ARCHIVE_SHA256 = "94d5842b6dc5759ecb446a4c617b60b72873b639885d116032f783abdef8431c"
REAL_SHA256 = "0c5bdb65afe5fa5576b71d30357e32398ed21f34fef37bd377dc19ec0653d862"
REAL_LEN = 12926
RAW_START = 0x2182
RAW_END_INCLUSIVE = 0x53FF
GHIDRA_SHA256 = "ddac49f903da9d5bac833e5cc79395098b9c33cfd3279be5f31bd00387d2d4db"
JDK_SHA256 = "dbb698396d478e7fa2b1e50f4103324b2a99b90569ee27c33f2261f9215cf41e"
GHIDRA_SIZE = 569649598
JDK_SIZE = 141329719
PROBE_SHA256 = "15984cedb3f0f0e5aced9b8334b622051deda7588bf5a9023428fa4d4fcfe65f"
PROBE_SIZE = 4025
CONTROL_SEEDS = tuple(range(20261012, 20261022))
LANGUAGE = "M16C/60:LE:16:default"
MARKER = re.compile(
    r"WB2A_M16C_PROBE_RESULT\s+"
    r"filename=(?P<name>\S+)\s+"
    r"lang=(?P<language>\S+)\s+"
    r"base=(?P<base>[0-9a-fA-F]+)\s+"
    r"len=(?P<length>\d+)\s+"
    r"seed_attempts=(?P<seed_attempts>\d+)\s+"
    r"seed_success=(?P<seed_success>\d+)\s+"
    r"instructions=(?P<instructions>\d+)\s+"
    r"covered_bytes=(?P<covered_bytes>\d+)\s+"
    r"coverage=(?P<coverage>\d+\.\d+)\s+"
    r"jumps=(?P<jumps>\d+)\s+"
    r"calls=(?P<calls>\d+)\s+"
    r"terminals=(?P<terminals>\d+)\s+"
    r"inner_targets=(?P<inner_targets>\d+)\s+"
    r"external_targets=(?P<external_targets>\d+)\s+"
    r"highrom_targets=(?P<highrom_targets>\d+)\s+"
    r"mnemonic_top=(?P<mnemonics>[\w.:,]+)"
)


class EvidenceRejected(ValueError):
    pass


def sha_path(path: Path, expected_sha: str, expected_len: int) -> str:
    if not path.is_file() or path.stat().st_size != expected_len:
        raise EvidenceRejected(f"missing/wrong length: {path.name}")
    with path.open("rb") as stream:
        actual = hashlib.file_digest(stream, "sha256").hexdigest()
    if actual != expected_sha:
        raise EvidenceRejected(f"modified/unknown source: {path.name}")
    return actual


def original_bytes(raw: bytes) -> bytes:
    if type(raw) is not bytes or len(raw) != REAL_LEN:
        raise EvidenceRejected("unexpected SRAM window length")
    if hashlib.sha256(raw).hexdigest() != REAL_SHA256:
        raise EvidenceRejected("unrecognized source-address SRAM window")
    return raw


def shuffle_control(raw: bytes, seed: int) -> bytes:
    if type(raw) is not bytes or not 1 <= len(raw) <= 20480:
        raise EvidenceRejected("non-byte original control")
    if type(seed) is not int or seed not in CONTROL_SEEDS:
        raise EvidenceRejected("control seed outside fixed public list")
    arr = list(raw)
    random.Random(seed).shuffle(arr)
    result = bytes(arr)
    if Counter(result) != Counter(raw) or len(result) != len(raw):
        raise EvidenceRejected("control not byte-histogram preserving")
    return result


def extract_probe(log: str, expected_filename: str) -> dict:
    if type(log) is not str or not log or len(log) > 1_000_000:
        raise EvidenceRejected("unbounded/headless output unavailable")
    if any(x in log for x in ("ERROR REPORT SCRIPT ERROR", "Failed to load", "SCRIPT FAILED", "Import failed")):
        raise EvidenceRejected("Ghidra import/disassembler failed")
    rows = list(MARKER.finditer(log))
    if len(rows) != 1:
        raise EvidenceRejected("not exactly one attested Ghidra script output")
    x = rows[0].groupdict()
    if x["name"] != expected_filename or x["language"] != LANGUAGE:
        raise EvidenceRejected("image name / M16C processor does not match pinned experiment")
    values = {k: int(v) for k, v in x.items() if k not in ("name", "language", "base", "coverage", "mnemonics")}
    if int(x["base"], 16) != RAW_START or values["length"] != REAL_LEN:
        raise EvidenceRejected("wrong data address or length")
    if values["seed_attempts"] != 134 or values["seed_success"] != 134:
        raise EvidenceRejected("non-equivalent disassembly seeding")
    if values["covered_bytes"] > values["length"] or values["covered_bytes"] <= 0:
        raise EvidenceRejected("impossible instruction coverage")
    if values["instructions"] <= 0 or values["calls"] < 0 or values["highrom_targets"] < 0:
        raise EvidenceRejected("unbounded opcode statistics")
    coverage = float(x["coverage"])
    if abs(coverage - values["covered_bytes"] / values["length"]) > 0.0001:
        raise EvidenceRejected("coverage percentage inconsistent with byte count")
    return {
        **values,
        "coverage": coverage,
        "top_mnemonics": x["mnemonics"],
    }


def compare(real: dict, controls: list[dict]) -> dict:
    if type(controls) is not list or len(controls) < 5:
        raise EvidenceRejected("too few histogram-matched negative controls")
    if not all(isinstance(x, dict) and set(x) == set(real) for x in controls):
        raise EvidenceRejected("incompatible headless metrics")
    fields = ("coverage", "calls", "highrom_targets", "inner_targets", "instructions")
    spans = {}
    for f in fields:
        nums = [x[f] for x in controls]
        if any(type(v) not in (int, float) for v in nums):
            raise EvidenceRejected("nonnumeric disassembly result")
        val = real[f]
        spans[f] = {
            "observed": val,
            "control_min": min(nums),
            "control_max": max(nums),
            "control_mean": round(statistics.mean(nums), 5),
            "control_std_population": round(statistics.pstdev(nums), 5),
            "observed_within_control_range": min(nums) <= val <= max(nums),
        }
    return {
        "comparison": spans,
        "control_count": len(controls),
        "real_ram_m16c_executable_code_proven": False,
        "resident_flash_or_rom_image_proven": False,
        "M16C_highrom_branch_targets_are_not_necessarily_real": True,
        "hex_bytes_recovered_directly_from_program_ROM": 0,
        "negative_controls_preserve_original_byte_frequencies": True,
        "limitations": "Sparse fixed-seed decode; unknown entrypoints/context; neither decode density nor p-like rankings establish executable provenance.",
    }


def audit_workbench(root: Path) -> dict:
    root = Path(root)
    if not root.is_dir():
        raise EvidenceRejected("private Ghidra workbench not found")
    sha_path(root / "ghidra.zip", GHIDRA_SHA256, GHIDRA_SIZE)
    sha_path(root / "jdk.tar.gz", JDK_SHA256, JDK_SIZE)
    sha_path(root / "Wb2aM16cCacheProbe.java", PROBE_SHA256, PROBE_SIZE)
    real = original_bytes((root / "raw_2182_53ff_real.bin").read_bytes())
    compare_samples = []
    samples = []
    actual = extract_probe((root / "ghidra-real-out-v2.log").read_text(),
                           "raw_2182_53ff_real.bin")
    for seed in CONTROL_SEEDS:
        if seed == 20261012:
            filename = "raw_2182_53ff_shuffled_control.bin"
            logname = "ghidra-shuffled_control.log"
        else:
            filename = f"raw_tail_shuffle_{seed}.bin"
            logname = f"ghidra-shuffle-{seed}.log"
        expected = shuffle_control(real, seed)
        p = root / filename
        if p.read_bytes() != expected:
            raise EvidenceRejected("control image not expected deterministic source permutation: " + filename)
        metrics = extract_probe((root / logname).read_text(), filename)
        samples.append({"seed": seed, "sha256": hashlib.sha256(expected).hexdigest(),
                        "coverage": metrics["coverage"],
                        "highrom_targets": metrics["highrom_targets"],
                        "calls": metrics["calls"]})
        compare_samples.append(metrics)
    stats = compare(actual, compare_samples)
    return {
        "audit": "PASS",
        "mode": "GHIDRA_12_1_4_M16C_60_HEADLESS_NOANALYSIS_HISTOGRAM_CONTROLS",
        "source": {
            "device": "20C2/0103",
            "read_source": "previous P300 FC03 low-RAM captures, not native firmware ROM",
            "original_archive_sha256": ARCHIVE_SHA256,
            "archive_manifest_attestation_required_before_extraction": True,
            "cpu_ram_start": f"0x{RAW_START:04x}",
            "cpu_ram_end": f"0x{RAW_END_INCLUSIVE:04x}",
            "bytes": REAL_LEN,
            "source_window_sha256": REAL_SHA256,
        },
        "tool_provenance": {"ghidra_12_1_4_release_sha256": GHIDRA_SHA256,
                            "jdk_25_tamper_check_sha256": JDK_SHA256,
                            "script_language": LANGUAGE,
                            "benchmarked_java_script_sha256": PROBE_SHA256,
                            "headless_automatic_analysis_disabled": True,
                            "seed_gap": 97, "seed_count": 134},
        "real": actual,
        "negative_controls": samples,
        **stats,
        "live_heater_reads": 0,
        "live_heater_writes": 0,
        "physical_reset_during_analysis": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workbench", type=Path, required=True)
    parser.add_argument("--out", type=Path)
    opts = parser.parse_args()
    report = audit_workbench(opts.workbench)
    result = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if opts.out:
        opts.out.write_text(result)
    print(result, end="")


if __name__ == "__main__":
    try:
        main()
    except (OSError, EvidenceRejected, ValueError) as exc:
        print("GHIDRA_EVIDENCE_REJECTED: " + str(exc))
        raise SystemExit(2)
