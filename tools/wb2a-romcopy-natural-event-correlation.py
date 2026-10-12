#!/usr/bin/env python3
"""Offline: correlate WB2A low-SRAM copy-shaped tuples with natural burner events.

SHA attest the original 79 P300 FC03 capture images AND their metadata using
the checked-in strict archive auditor, then quantify the strength/weakness
of copy candidates against ordinary stable windows and repeated SRAM filler.
Never contact the controller or export private raw RAM payloads to Git.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import random
import sys
import tarfile

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location(
    "wb2a_romcopy_natural_null_model",
    HERE / "wb2a-romcopy-nullmodel-original.py")
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("strict original source verifier is missing")
original = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = original
SPEC.loader.exec_module(original)

PHASES = ("STABLE_BRACKET_OFF", "STABLE_BRACKET_RUNNING",
          "TRANSITION_OR_UNKNOWN")
CANDIDATES = {
    "A": dict(tuple_start=0x1DE5, target_start=0x3301,
              target_count=29, source_value=0xEA2AB,
              layout="source_destination"),
    "B": dict(tuple_start=0x1E6A, target_start=0x0705,
              target_count=7, source_value=0xFB27D,
              layout="destination_source"),
}
B_FILL = 0x64
SHUFFLE_SEEDS = original.CONTROL_SEEDS


class FalseProvenance(ValueError):
    pass


def get(data: bytes, addr: int, count: int) -> bytes:
    offset = addr - original.BASE
    if (type(data) is not bytes or type(count) is not int or
        not 0 <= offset < len(data) or
        not 1 <= count <= len(data) - offset):
        raise FalseProvenance("read outside already archived low RAM image")
    return data[offset:offset+count]


def exact_occurrences(data: bytes, fragment: bytes) -> int:
    """Use overlapping positions; bytes.count would undercount filler."""
    if (type(data) is not bytes or type(fragment) is not bytes
        or not 1 <= len(fragment) <= len(data)):
        raise FalseProvenance("only bounded byte patterns")
    k = len(fragment)
    return sum(data[i:i+k] == fragment for i in range(len(data)-k+1))


def classify(images: list[bytes], metadata: list[dict]) -> dict:
    if (type(images) is not list or len(images) != original.IMAGE_COUNT or
        type(metadata) is not list or len(metadata) != len(images)):
        raise FalseProvenance("exact 79 images and 79 metadata records required")
    mask = original.stable_mask(images)
    raw = images[0]
    if original.scan_for_shape(raw, mask) != original.EXACT_EXPECTED:
        raise FalseProvenance("historical descriptor shapes changed")
    phase_counts = Counter()
    flame_seen = 0
    transition_seen = 0
    direction = Counter()
    for number, item in enumerate(metadata, 1):
        if (not isinstance(item, dict) or
            item.get("marker") != "COMPLETE" or
            item.get("complete") is not True or
            item.get("device_id") != "20c2" or
            item.get("software") != "0103" or
            item.get("atomic_ram_image") is not False or
            item.get("snapshot_id") != number or
            item.get("classification") not in PHASES or
            type(item.get("flame_seen")) is not bool or
            type(item.get("flame_transition_seen")) is not bool or
            item.get("direction") not in ("ascending", "descending") or
            item.get("sha256") != hashlib.sha256(images[number-1]).hexdigest()):
            raise FalseProvenance("unverified natural-event classification")
        phase_counts[item["classification"]] += 1
        flame_seen += item["flame_seen"]
        transition_seen += item["flame_transition_seen"]
        direction[item["direction"]] += 1

    candidates = {}
    for key, cfg in CANDIDATES.items():
        a, dst, n = cfg["tuple_start"], cfg["target_start"], cfg["target_count"]
        tuples = {get(img,a,8) for img in images}
        targets = {get(img,dst,n) for img in images}
        if len(tuples) != 1 or len(targets) != 1:
            raise FalseProvenance("tuple or target no longer constant")
        neighbors = [get(img,a-8,24) for img in images]
        groups = {}
        for phase in PHASES:
            indexes = [i for i,item in enumerate(metadata)
                       if item["classification"] == phase]
            groups[phase] = {
                "sample_count": len(indexes),
                "tuple_distinct": len({get(images[i],a,8) for i in indexes}),
                "target_distinct": len({get(images[i],dst,n) for i in indexes}),
                "neighbor_24_distinct": len({neighbors[i] for i in indexes}),
            }
        src = cfg["source_value"]
        candidates[key] = {
            "tuple_ram_address": f"0x{a:04x}",
            "hypothetical_source_address": f"0x{src:05x}",
            "target_ram_address": f"0x{dst:04x}",
            "target_count": n,
            "hypothetical_source_destination_layout": cfg["layout"],
            "tuple_variants": len(tuples),
            "target_variants": len(targets),
            "neighborhood_24byte_variants": len(set(neighbors)),
            "neighborhood_consecutive_changes": sum(
                neighbors[j]!=neighbors[j-1] for j in range(1,len(neighbors))),
            "by_natural_burner_state": groups,
            "3byte_source_literal_occurrences_in_original_SRAM":
                exact_occurrences(raw,src.to_bytes(3,"little")),
            "zero_extended_4byte_source_occurrences_in_original_SRAM":
                exact_occurrences(raw,src.to_bytes(4,"little")),
            "observed_source_dereference": False,
            "observed_ROM_to_RAM_copy": False,
        }

    # Target A uniqueness/stability is common for unrelated SRAM windows.
    n = CANDIDATES["A"]["target_count"]
    all_indices = range(len(raw)-n+1)
    fully_stable = [i for i in all_indices if all(mask[i:i+n])]
    hist = Counter(raw[i:i+n] for i in all_indices)
    A_offset=CANDIDATES["A"]["target_start"]-original.BASE
    A=raw[A_offset:A_offset+n]
    if hist[A]!=1 or not all(mask[A_offset:A_offset+n]):
        raise FalseProvenance("target A background assumption changed")
    stable_unique=sum(hist[raw[i:i+n]]==1 for i in fully_stable)
    shuffled_unique=0
    for seed in SHUFFLE_SEEDS:
        rearranged=list(raw)
        random.Random(seed).shuffle(rearranged)
        img=bytes(rearranged)
        shuffled_unique += exact_occurrences(img,img[A_offset:A_offset+n]) == 1
    candidates["A"].update({
        "target_29byte_exact_unique_in_original_SRAM": True,
        "all_possible_29byte_windows": len(raw)-n+1,
        "fully_stable_29byte_windows": len(fully_stable),
        "stable_29byte_windows_whose_payload_is_unique": stable_unique,
        "control_shuffles_29byte_payload_unique": shuffled_unique,
        "number_of_shuffle_controls": len(SHUFFLE_SEEDS),
        "uniqueness_is_not_ROM_source_provenance": True,
    })

    # Target B is all 0x64 inside a 407 byte filler run.
    dst=CANDIDATES["B"]["target_start"]
    n=CANDIDATES["B"]["target_count"]
    off=dst-original.BASE
    fragment=get(raw,dst,n)
    if fragment != bytes([B_FILL])*n:
        raise FalseProvenance("target B filler payload changed")
    lo=off
    hi=off+n
    while lo>0 and raw[lo-1] == B_FILL: lo-=1
    while hi<len(raw) and raw[hi] == B_FILL:hi+=1
    candidates["B"].update({
        "target_byte_value": f"0x{B_FILL:02x}",
        "containing_filler_run_start": f"0x{original.BASE+lo:04x}",
        "containing_filler_run_end": f"0x{original.BASE+hi-1:04x}",
        "containing_filler_run_length": hi-lo,
        "seven_byte_pattern_occurrences_overlapping": exact_occurrences(raw,fragment),
        "filler_match_cannot_identify_ROM_source": True,
    })
    return {
        "audit": "PASS",
        "mode": "PREEXISTING_P300_FULLRAM_NATURAL_BURNER_EVENT_ONLY",
        "identity": "20C2/0103",
        "source_original_sha256": original.ARCHIVE_SHA256,
        "complete_non_atomic_images": len(images),
        "image_size": original.IMAGE_SIZE,
        "stable_byte_positions": sum(mask),
        "phase_sample_counts": dict(phase_counts),
        "flame_seen_image_count": flame_seen,
        "flame_transition_seen_image_count": transition_seen,
        "scan_direction_count": dict(direction),
        "candidate_fields": candidates,
        "verified_program_ROM_bytes": 0,
        "controller_ROM_source_dereference_proven": False,
        "any_ROM_copy_service_proven": False,
        "live_controller_reads": 0,
        "live_controller_writes": 0,
        "limitations": (
            "640 sequential P300 FC03 subreads per image; not atomic. "
            "Burner states refer to bracketed capture windows, not exact "
            "byte-by-byte state. Far-source layouts chosen after seeing data."
        ),
    }


def study_original_archive(data: bytes) -> dict:
    # First attest archive checksum, manifest plus 79 complete binary+metadata
    # members through the separate, already tested strict source library.
    images=original.attested_images(data)
    with tarfile.open(fileobj=io.BytesIO(data),mode="r:gz") as archive:
        manifest=json.loads(archive.extractfile(
            original.PREFIX+"bundle-manifest.json").read())
        metadata=[
            json.loads(original._verified_member(
                archive,manifest,f"snapshots/s{i:05d}.json",8000))
            for i in range(1,original.IMAGE_COUNT+1)
        ]
    return classify(images,metadata)


def main() -> None:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--original-archive",type=Path,required=True)
    p.add_argument("--out",type=Path)
    a=p.parse_args()
    if a.original_archive.is_symlink() or not a.original_archive.is_file():
        p.error("pinned original RAM archive must be an ordinary local file")
    if a.original_archive.stat().st_size != original.ARCHIVE_SIZE:
        p.error("original tar size mismatch")
    result=study_original_archive(a.original_archive.read_bytes())
    output=json.dumps(result,indent=2,sort_keys=True)+"\n"
    if a.out:a.out.write_text(output,encoding="utf-8")
    print(output,end="")


if __name__ == "__main__":
    try:main()
    except (FalseProvenance,original.InvalidArchiveOrHypothesis,OSError,
            ValueError,tarfile.TarError) as exc:
        print("ROMCOPY_NATURAL_EVENT_EVIDENCE_REJECTED: "+str(exc),file=sys.stderr)
        raise SystemExit(2)
