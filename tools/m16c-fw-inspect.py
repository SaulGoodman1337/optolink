#!/usr/bin/env python3
"""Static first-pass inspector for raw Renesas M16C/62P firmware dumps.

Designed around the M30624 256 KiB user-flash layout (0xC0000..0xFFFFF).
This tool is deliberately read-only: it never talks to hardware and never
modifies the input image.

It reports:
- raw image geometry and SHA-256
- M16C fixed-vector bytes near 0xFFFDC
- seven bootloader ID-code bytes
- reset-vector heuristic
- ASCII strings
- occurrences/clusters of known Optolink/Vitotrol state-address constants

The constant scan is only a correlation aid. A matching byte pattern is not a
code cross-reference until confirmed in a disassembler.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

M30624_FLASH_BASE = 0xC0000
M30624_FLASH_SIZE = 0x40000
ADDRESS_SPACE_SIZE = 0x100000

ID_ADDRESSES = (
    0xFFFDF,
    0xFFFE3,
    0xFFFEB,
    0xFFFEF,
    0xFFFF3,
    0xFFFF7,
    0xFFFFB,
)

FIXED_VECTORS = (
    ("undefined_instruction", 0xFFFDC),
    ("overflow", 0xFFFE0),
    ("brk", 0xFFFE4),
    ("address_match", 0xFFFE8),
    ("single_step", 0xFFFEC),
    ("watchdog", 0xFFFF0),
    ("dbc", 0xFFFF4),
    ("nmi", 0xFFFF8),
    ("reset", 0xFFFFC),
)

# Known runtime state from the WB2A / VDensHO1 research.
# These are controller datapoint addresses, not proven MCU absolute RAM addresses.
SEARCH_CONSTANTS = {
    0x0896: "room_actual_A1_M1",
    0x089C: "room_sensor_status_A1_M1",
    0x0A5C: "remote_sw_index_A1",
    0x27A0: "remote_configuration_A1_M1",
    0x37A0: "remote_configuration_M2",
    0x7340: "cross_profile_bde_type",
    0x7341: "cross_profile_remote_KK_type",
    0x7342: "cross_profile_remote_M1_type",
    0x7343: "cross_profile_remote_M2_type",
    0x779C: "lon_receive_heartbeat_config",
}

# Protocol byte sequences useful as secondary signatures. These are intentionally
# longer than a single byte to reduce noise.
PROTOCOL_SIGNATURES = {
    bytes.fromhex("1100330a0101f804"): "vitotrol_discovery_request_prefix",
    bytes.fromhex("001180080101"): "vitotrol_slot1_pong_prefix",
    bytes.fromhex("0011bf0c010120"): "vitotrol_hk1_room_record_prefix",
}


@dataclass
class Hit:
    name: str
    pattern_hex: str
    file_offset: int
    mapped_address: int | None


def mapped_address(offset: int, image_size: int, base: int) -> int | None:
    if image_size == M30624_FLASH_SIZE:
        return base + offset
    return None


def find_all(data: bytes, needle: bytes) -> Iterable[int]:
    start = 0
    while True:
        pos = data.find(needle, start)
        if pos < 0:
            return
        yield pos
        start = pos + 1


def printable_strings(data: bytes, minimum: int = 5) -> list[dict[str, object]]:
    out: list[dict[str, object]] = []
    start: int | None = None
    for i, b in enumerate(data + b"\x00"):
        printable = 0x20 <= b <= 0x7E
        if printable and start is None:
            start = i
        elif not printable and start is not None:
            if i - start >= minimum:
                raw = data[start:i]
                out.append({"offset": start, "text": raw.decode("ascii", "replace")})
            start = None
    return out


def slice_absolute(data: bytes, absolute: int, base: int) -> bytes | None:
    off = absolute - base
    if off < 0 or off >= len(data):
        return None
    return data[off:off + 4]


def inspect(path: Path, base: int = M30624_FLASH_BASE) -> dict[str, object]:
    data = path.read_bytes()
    sha256 = hashlib.sha256(data).hexdigest()

    result: dict[str, object] = {
        "file": str(path),
        "size": len(data),
        "sha256": sha256,
        "assumed_flash_base": f"0x{base:05X}" if len(data) == M30624_FLASH_SIZE else None,
        "geometry": {
            "matches_m30624_256k_user_flash": len(data) == M30624_FLASH_SIZE,
            "expected_size": M30624_FLASH_SIZE,
            "expected_range": "0xC0000..0xFFFFF",
        },
    }

    if len(data) == M30624_FLASH_SIZE:
        ids = []
        for addr in ID_ADDRESSES:
            off = addr - base
            ids.append(data[off] if 0 <= off < len(data) else None)
        result["id_code"] = {
            "addresses": [f"0x{x:05X}" for x in ID_ADDRESSES],
            "bytes": None if any(x is None for x in ids) else "".join(f"{x:02x}" for x in ids),
            "all_ff": all(x == 0xFF for x in ids if x is not None) and all(x is not None for x in ids),
            "all_00": all(x == 0x00 for x in ids if x is not None) and all(x is not None for x in ids),
        }

        vectors = []
        for name, addr in FIXED_VECTORS:
            raw = slice_absolute(data, addr, base)
            if raw is None or len(raw) != 4:
                continue
            word = int.from_bytes(raw, "little")
            vectors.append({
                "name": name,
                "address": f"0x{addr:05X}",
                "raw": raw.hex(),
                # Heuristic only; M16C vector interpretation must be confirmed
                # in Ghidra/IDA rather than trusted from this field.
                "little_endian_low20_heuristic": f"0x{word & 0xFFFFF:05X}",
            })
        result["fixed_vectors"] = vectors

    hits: list[Hit] = []
    for value, name in SEARCH_CONSTANTS.items():
        for encoding, suffix in (
            (value.to_bytes(2, "little"), "u16_le"),
            (value.to_bytes(2, "big"), "u16_be"),
        ):
            for off in find_all(data, encoding):
                hits.append(Hit(
                    name=f"{name}:{suffix}",
                    pattern_hex=encoding.hex(),
                    file_offset=off,
                    mapped_address=mapped_address(off, len(data), base),
                ))

    for needle, name in PROTOCOL_SIGNATURES.items():
        for off in find_all(data, needle):
            hits.append(Hit(
                name=name,
                pattern_hex=needle.hex(),
                file_offset=off,
                mapped_address=mapped_address(off, len(data), base),
            ))

    result["signature_hits"] = [
        {
            **asdict(hit),
            "file_offset_hex": f"0x{hit.file_offset:X}",
            "mapped_address_hex": None if hit.mapped_address is None else f"0x{hit.mapped_address:05X}",
        }
        for hit in hits
    ]

    strings = printable_strings(data)
    result["ascii_strings"] = strings
    return result


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("firmware", type=Path)
    ap.add_argument("--base", type=lambda x: int(x, 0), default=M30624_FLASH_BASE)
    ap.add_argument("--json", action="store_true", help="emit full JSON including strings")
    ap.add_argument("--strings", type=int, default=30, help="number of ASCII strings to show in text mode")
    args = ap.parse_args()

    result = inspect(args.firmware, args.base)
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0

    print(f"FILE={result['file']}")
    print(f"SIZE={result['size']}")
    print(f"SHA256={result['sha256']}")
    print(f"M30624_256K={result['geometry']['matches_m30624_256k_user_flash']}")

    if "id_code" in result:
        ident = result["id_code"]
        print(f"ID_CODE={ident['bytes']} all_ff={ident['all_ff']} all_00={ident['all_00']}")

    for vec in result.get("fixed_vectors", []):
        print(
            "VECTOR "
            f"{vec['name']} @{vec['address']} raw={vec['raw']} "
            f"low20={vec['little_endian_low20_heuristic']}"
        )

    hits = result["signature_hits"]
    print(f"SIGNATURE_HITS={len(hits)}")
    for hit in hits[:200]:
        print(
            f"HIT {hit['name']} pattern={hit['pattern_hex']} "
            f"off={hit['file_offset_hex']} mapped={hit['mapped_address_hex']}"
        )
    if len(hits) > 200:
        print(f"... {len(hits) - 200} additional signature hits omitted")

    strings = result["ascii_strings"]
    print(f"ASCII_STRINGS={len(strings)}")
    for item in strings[: max(args.strings, 0)]:
        print(f"STR off=0x{item['offset']:X} {item['text']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
