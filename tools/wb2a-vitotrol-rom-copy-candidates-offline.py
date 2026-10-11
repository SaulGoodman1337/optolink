#!/usr/bin/env python3
"""Offline 20C2 ROM->low-RAM-copy shaped tuple audit.

Observational only: the descriptor shape does not prove it is a copy
descriptor or a pointer to code. Every actual image must be verified
against the pinned historical full-SRAM tar manifest before use.
No serial, subprocess, network, MCU registers, writes or DMA triggers.
"""
from __future__ import annotations
from collections import Counter
import importlib.util
import io
import json
from pathlib import Path
import stat
import sys
import tarfile

BASE = 0x0400
SIZE = 20480
ROM_MIN, ROM_MAX = 0xC0000, 0xFFFFF
ARCHIVE_SHA256 = "94d5842b6dc5759ecb446a4c617b60b72873b639885d116032f783abdef8431c"
HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location(
    "wb2a_vitotrol_copy_audit_parent",
    HERE / "wb2a-vitotrol-near-rx-rom-candidates.py"
)
if spec is None or spec.loader is None:
    raise RuntimeError("pinned manifest checker module unavailable")
parent = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = parent
spec.loader.exec_module(parent)

CANDIDATES = {
    "A_1de5_to_3301_29": dict(start=0x1DE5, source_offset=0,
                              dest_offset=3, size_offset=6,
                              expected_source=0xEA2AB,
                              expected_target=0x3301, expected_size=29),
    "B_1e6a_to_0705_7": dict(start=0x1E6A, source_offset=3,
                             dest_offset=0, size_offset=6,
                             expected_source=0xFB27D,
                             expected_target=0x0705, expected_size=7),
}
# These nearby windows were reported as stack/task-like, not verified copy API.
NEIGHBOR_LEN = 24
NEIGHBOR_RELATIVE_OFFSET = -8


class InvalidEvidence(ValueError):
    pass


def field(image: bytes, address: int, length: int) -> bytes:
    pos = address - BASE
    if pos < 0 or pos + length > len(image):
        raise InvalidEvidence("field outside immutable 0x0400..0x53ff range")
    return image[pos:pos + length]


def inspect(images: list[bytes] | tuple[bytes, ...]) -> dict:
    if not isinstance(images, (list, tuple)) or not 1 <= len(images) <= 79:
        raise InvalidEvidence("1..79 snapshots required")
    if any(type(x) is not bytes or len(x) != SIZE for x in images):
        raise InvalidEvidence("complete immutable 20 KiB images required")
    findings = {}
    for label, c in CANDIDATES.items():
        records = []
        targets = Counter()
        near = Counter()
        for image in images:
            start = c["start"]
            raw = field(image, start, 8)
            source = int.from_bytes(raw[c["source_offset"]:c["source_offset"]+3], "little")
            target = int.from_bytes(raw[c["dest_offset"]:c["dest_offset"]+3], "little")
            length = int.from_bytes(raw[c["size_offset"]:c["size_offset"]+2], "little")
            if target < BASE or length <= 0 or target + length > BASE + SIZE:
                raise InvalidEvidence("candidate target/length outside attested SRAM")
            payload = field(image, target, length)
            records.append((source, target, length))
            targets[payload.hex()] += 1
            near[field(image, start+NEIGHBOR_RELATIVE_OFFSET, NEIGHBOR_LEN).hex()] += 1
        modes = Counter(records)
        modal, modal_count = modes.most_common(1)[0]
        modal_payload, payload_count = targets.most_common(1)[0]
        findings[label] = {
            "raw_source_20bit": f"0x{modal[0]:05x}",
            "dest_low_ram": f"0x{modal[1]:04x}",
            "count": modal[2],
            "modal_tuple_occurrences": modal_count,
            "different_tuple_count": len(modes),
            "source_in_assumed_program_rom": ROM_MIN <= modal[0] <= ROM_MAX,
            "matches_previous_reported_tuple": (
                modal == (c["expected_source"], c["expected_target"], c["expected_size"])
            ),
            "target_contents_distinct": len(targets),
            "modal_target_content_occurrences": payload_count,
            "target_all_bytes_64_samples": sum(
                n for raw, n in targets.items() if raw == "64" * modal[2]
            ) if len(modes) == 1 else None,
            "target_modal_prefix_hex": modal_payload[:64],
            "neighbor_window_different_count": len(near),
            "data_prove_rom_copy": False,
            "source_rom_bytes_available": False,
            "controller_side_copy_operation_proven": False,
        }
    return {
        "mode": "PINNED_OFFLINE_FULLRAM_ROM_COPY_TUPLE_AUDIT",
        "samples": len(images),
        "known_archival_snapshots_non_atomic": True,
        "candidate_findings": findings,
        "any_verified_controller_copy_service": False,
        "any_rom_contents_acquired": False,
        "live_io_requested": False,
        "controller_ram_sfr_or_rom_written": False,
    }


def from_manifest_attested_tar(data: bytes) -> dict:
    if type(data) is not bytes or not 0 < len(data) <= parent.audit.MAX_ARCHIVE_BYTES:
        raise InvalidEvidence("bounded tarball required")
    try:
        archive_info = parent.audit.audit_bundle("fullram", data)
    except parent.audit.EvidenceRejected as exc:
        raise InvalidEvidence("original full-RAM archive attestation failed") from exc
    if archive_info["archive_sha256"] != ARCHIVE_SHA256:
        raise InvalidEvidence("not the exact pinned original experiment")
    images = []
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as archive:
        manifest = parent.audit._manifest(archive, "p300-fullram")
        for number in range(1, 80):
            stem = f"snapshots/s{number:05d}"
            metadata = json.loads(parent.audit._verified(
                archive, manifest, "p300-fullram", stem + ".json", max_size=8000))
            blob = parent.audit._verified(
                archive, manifest, "p300-fullram", stem + ".bin", max_size=SIZE)
            if (metadata.get("marker") != "COMPLETE" or metadata.get("complete") is not True
                or metadata.get("device_id") != "20c2" or metadata.get("software") != "0103"
                or metadata.get("bytes_stored") != SIZE
                or metadata.get("range_start") != "0x0400"
                or metadata.get("range_last_inclusive") != "0x53ff"
                or len(blob) != SIZE):
                raise InvalidEvidence("untrusted/incomplete original image")
            images.append(blob)
    output = inspect(images)
    output["source_archive_sha256"] = archive_info["archive_sha256"]
    output["manifest_sha256s_all_verified"] = True
    return output


def main():
    import argparse
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--archive", type=Path, required=True)
    args = p.parse_args()
    if args.archive.is_symlink() or not stat.S_ISREG(args.archive.stat().st_mode):
        p.error("must use normal bounded original archive")
    if args.archive.stat().st_size > parent.audit.MAX_ARCHIVE_BYTES:
        p.error("tar exceeds safe size cap")
    print(json.dumps(from_manifest_attested_tar(args.archive.read_bytes()), sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
