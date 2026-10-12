#!/usr/bin/env python3
"""Source-attested negative controls for supposed M16C far-source RAM-copy tuples.

Hypothesis (NOT validated): stable 8-byte SRAM structures encode far-ROM source
as little-endian u24, low-SRAM destination u24, then 16-bit length, OR the
reverse for source/dest. The scan is purely offline across 79 prior WB2A
snapshots, checked against 300 image-global byte-position permutations.

The byte permutation is common across ALL 79 images; it therefore preserves
per-position temporal stability and each original image's complete histogram.
Finding genuine tuples above the null distribution proves only nonrandom
STRUCTURE, NOT a working ROM->RAM copy or bytes originating in ROM.

Strict pinned tarball with per-entry SHA256 verification; no CLI support to
connect to Optolink, query the controller, run a command or alter memory.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import io
import json
from pathlib import Path
import random
import stat
import sys
import tarfile

ARCHIVE_SHA256 = "94d5842b6dc5759ecb446a4c617b60b72873b639885d116032f783abdef8431c"
ARCHIVE_SIZE = 8_404_258
PREFIX = "p300-fullram/"
BASE = 0x0400
IMAGE_SIZE = 20_480
IMAGE_COUNT = 79
SOURCE_START = 0xC0000
SOURCE_END = 0xFFFFF
COUNT_MAX = 32
CONTROL_SEEDS = tuple(range(20261012, 20261312))
EXACT_EXPECTED = [
    ("0x1de5", "source_destination", "0xea2ab", "0x3301", 29),
    ("0x1e6a", "destination_source", "0xfb27d", "0x705", 7),
]


class InvalidArchiveOrHypothesis(ValueError):
    pass


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _verified_member(archive: tarfile.TarFile, manifest: dict,
                     relative: str, cap: int) -> bytes:
    record = manifest["files"].get(relative)
    if not isinstance(record, dict) or set(record) != {"size", "sha256"}:
        raise InvalidArchiveOrHypothesis("missing authentic manifest entry " + relative)
    size = record["size"]
    if type(size) is not int or not 0 <= size <= cap:
        raise InvalidArchiveOrHypothesis("unbounded manifest entry " + relative)
    member = archive.getmember(PREFIX + relative)
    if not member.isfile() or member.size != size:
        raise InvalidArchiveOrHypothesis("unexpected archive member " + relative)
    f = archive.extractfile(member)
    if f is None:
        raise InvalidArchiveOrHypothesis("unreadable original archive member")
    blob = f.read(cap + 1)
    if len(blob) != size or _sha(blob) != record["sha256"]:
        raise InvalidArchiveOrHypothesis("original member SHA mismatch " + relative)
    return blob


def attested_images(data: bytes) -> list[bytes]:
    if type(data) is not bytes or len(data) != ARCHIVE_SIZE:
        raise InvalidArchiveOrHypothesis("wrong-size historical fullram tar")
    if _sha(data) != ARCHIVE_SHA256:
        raise InvalidArchiveOrHypothesis("non-original historical capture tar")
    images = []
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as archive:
        members = archive.getmembers()
        paths = [x.name for x in members]
        if len(paths) != len(set(paths)):
            raise InvalidArchiveOrHypothesis("duplicate archive paths")
        for member in members:
            name = member.name
            if (not name.startswith(PREFIX) or name.startswith("/") or
                "/../" in name or name.endswith("/..") or member.issym() or member.islnk()):
                raise InvalidArchiveOrHypothesis("unsafe private archive entry")
        info_member = archive.getmember(PREFIX + "bundle-manifest.json")
        if not info_member.isfile() or info_member.size > 180000:
            raise InvalidArchiveOrHypothesis("bad manifest size")
        manifest = json.loads(archive.extractfile(info_member).read())
        if not isinstance(manifest, dict) or not isinstance(manifest.get("files"), dict):
            raise InvalidArchiveOrHypothesis("no valid complete manifest")
        for number in range(1, IMAGE_COUNT + 1):
            stem = f"snapshots/s{number:05d}"
            meta = json.loads(_verified_member(archive, manifest, stem + ".json", 8000))
            blob = _verified_member(archive, manifest, stem + ".bin", IMAGE_SIZE)
            if (meta.get("marker") != "COMPLETE" or meta.get("complete") is not True
                or meta.get("atomic_ram_image") is not False
                or meta.get("device_id") != "20c2"
                or meta.get("software") != "0103"
                or meta.get("range_start") != "0x0400"
                or meta.get("range_last_inclusive") != "0x53ff"
                or meta.get("bytes_stored") != IMAGE_SIZE
                or meta.get("data_file") != f"s{number:05d}.bin"
                or meta.get("blocks_ok") != 640
                or meta.get("blocks_failed") != 0
                or meta.get("sha256") != _sha(blob)):
                raise InvalidArchiveOrHypothesis("inconsistent exact WB2A capture metadata")
            images.append(blob)
    if len(images) != IMAGE_COUNT:
        raise InvalidArchiveOrHypothesis("missing historical fullram images")
    return images


def stable_mask(images: list[bytes]) -> bytes:
    if (type(images) is not list or len(images) != IMAGE_COUNT
        or any(type(x) is not bytes or len(x) != IMAGE_SIZE for x in images)):
        raise InvalidArchiveOrHypothesis("expected exactly 79 complete original RAM snapshots")
    first = images[0]
    return bytes(all(img[i] == first[i] for img in images[1:]) for i in range(IMAGE_SIZE))


def scan_for_shape(first: bytes, is_stable: bytes, *,
                   limit: int = COUNT_MAX) -> list[tuple]:
    if (type(first) is not bytes or type(is_stable) is not bytes or
        len(first) != len(is_stable) or len(first) < 8 or len(first) > IMAGE_SIZE
        or type(limit) is not int or not 1 <= limit <= COUNT_MAX
        or any(x not in (0, 1) for x in is_stable)):
        raise InvalidArchiveOrHypothesis("only bounded byte-exact SRAM / stable mask")
    results = []
    for offset in range(len(first) - 7):
        if 0 in is_stable[offset:offset + 8]:
            continue
        a = int.from_bytes(first[offset:offset + 3], "little")
        b = int.from_bytes(first[offset + 3:offset + 6], "little")
        n = int.from_bytes(first[offset + 6:offset + 8], "little")
        if not 1 <= n <= limit:
            continue
        for source, target, layout in ((a, b, "source_destination"),
                                       (b, a, "destination_source")):
            if (SOURCE_START <= source <= SOURCE_END and
                BASE <= target <= BASE + len(first) - n):
                results.append((f"0x{BASE + offset:x}", layout,
                                f"0x{source:x}", f"0x{target:x}", n))
    return results


def shuffle_with_correlated_stability(first: bytes, mask: bytes, seed: int) -> tuple[bytes, bytes]:
    if (type(seed) is not int or seed not in CONTROL_SEEDS or
        type(first) is not bytes or type(mask) is not bytes or len(first) != len(mask)):
        raise InvalidArchiveOrHypothesis("out-of-range seed or inconsistent image")
    permutation = list(range(len(first)))
    random.Random(seed).shuffle(permutation)
    shuffled = bytes(first[i] for i in permutation)
    stable = bytes(mask[i] for i in permutation)
    if Counter(shuffled) != Counter(first) or sum(stable) != sum(mask):
        raise InvalidArchiveOrHypothesis("control destroyed histograms or temporal stability")
    return shuffled, stable


def null_model(images: list[bytes], *, seeds: tuple[int, ...] = CONTROL_SEEDS) -> dict:
    mask = stable_mask(images)
    first = images[0]
    real = scan_for_shape(first, mask)
    if real != EXACT_EXPECTED:
        raise InvalidArchiveOrHypothesis("original tuples drifted from independently known observations")
    if type(seeds) is not tuple or not seeds or len(set(seeds)) != len(seeds):
        raise InvalidArchiveOrHypothesis("nonempty unique fixed control seed set required")
    counts = []
    for seed in seeds:
        raw, ctrl_stable = shuffle_with_correlated_stability(first, mask, seed)
        counts.append(len(scan_for_shape(raw, ctrl_stable)))
    distribution = Counter(counts)
    upper = sum(n >= len(real) for n in counts)
    return {
        "audit": "PASS", "device": "20C2/0103",
        "historical_complete_nonatomic_RAM_images": len(images),
        "historical_image_bytes": IMAGE_SIZE,
        "historical_archive_sha256": ARCHIVE_SHA256,
        "source_memory_space": "P300_FC03_LOW_SRAM_ONLY",
        "rom_program_bytes_extracted": 0,
        "stable_bytes": sum(mask),
        "selector_min_assumed": f"0x{SOURCE_START:x}",
        "selector_max_assumed": f"0x{SOURCE_END:x}",
        "max_hypothesized_count": COUNT_MAX,
        "candidate_count": len(real),
        "candidates": [
            {"tuple_ram_address": x[0], "layout": x[1],
             "hypothetical_high_source": x[2],
             "hypothetical_low_destination": x[3],
             "count": x[4],
             "controller_rom_to_ram_copy_proven": False}
            for x in real
        ],
        "byte_permutation_control_count": len(counts),
        "byte_permutation_control_histogram": dict(sorted(distribution.items())),
        "byte_permutation_control_count_mean": round(sum(counts) / len(counts), 6),
        "byte_permutation_control_count_max": max(counts),
        "controls_with_at_least_real_count": upper,
        "descriptive_one_sided_permutation_tail_fraction": round(
            (upper + 1) / (len(counts) + 1), 6),
        "posthoc_selection_invalidates_formal_p_value": True,
        "controls_keep_79_sample_stability_membership": True,
        "any_program_rom_copy_safely_triggerable_proven": False,
        "actual_rom_source_dereferenced": False,
        "controller_read_requests_sent": 0,
        "controller_writes_sent": 0,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--original-archive", type=Path, required=True)
    parser.add_argument("--out", type=Path)
    o = parser.parse_args()
    p = o.original_archive
    if p.is_symlink() or not p.is_file() or not stat.S_ISREG(p.stat().st_mode):
        parser.error("expected pinned real regular archive")
    if p.stat().st_size != ARCHIVE_SIZE:
        parser.error("expected pinned original archive size")
    result = null_model(attested_images(p.read_bytes()))
    output = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if o.out is not None:
        o.out.write_text(output, encoding="utf-8")
    print(output, end="")


if __name__ == "__main__":
    try:
        main()
    except (InvalidArchiveOrHypothesis, OSError, ValueError, tarfile.TarError) as exc:
        print("ROMCOPY_NULL_MODEL_REJECTED: " + str(exc), file=sys.stderr)
        sys.exit(2)
