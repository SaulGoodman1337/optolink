#!/usr/bin/env python3
"""SHA256-pinned, read-only VitoSoft HOST device-family contrast (not MCU code).

The exact VitoSoft DPDefinitions.xml is 186.6 MB. Stream SHA256 + memory map
the export; parse only ecnDatapointType rows rather than reading firmware or
opening any serial transport. Host profiles cannot prove ECU implementation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import mmap
from pathlib import Path
import re
import sys
import xml.etree.ElementTree as ET

DP = Path("/home/chatgpt-admin/research/vitosoft-lfs/DPDefinitions.xml")
DP_SHA = "efec27568d398021c767771af016143bd51fc196d2d408dbb80faff84d0b19e3"
MAX = 188_000_000
EXPECTED = {
    "VDensHO1": "60",
    "VDensHO1_4": "208",
    "GWG_VBEM_00": "76",
    "HV_GWG": "148",
}
PARSER = re.compile(rb"<ecnDatapointType(?:\s[^>]*)?>(.*?)</ecnDatapointType>", re.S)


class CatalogRejected(ValueError):
    pass


def parse_rows(payload, *, pinned: bool):
    by_id = {}
    by_name = {}
    for match in PARSER.finditer(payload):
        try:
            row = ET.fromstring(b"<item>" + match.group(1) + b"</item>")
        except ET.ParseError as e:
            raise CatalogRejected("malformed device profile XML") from e
        data = {x.tag: (x.text or "") for x in row}
        value, name = data.get("Id"), data.get("Address")
        if not value or not name or value in by_id or name in by_name:
            raise CatalogRejected("missing or duplicate VitoSoft device mapping")
        if not value.isdecimal():
            raise CatalogRejected("non-numeric device catalog row")
        by_id[value] = name
        by_name[name] = value
    if pinned and len(by_id) != 399:
        raise CatalogRejected(f"unexpected pinned device type count {len(by_id)}")
    if not by_id:
        raise CatalogRejected("no device profile rows found")
    for name, expected_id in EXPECTED.items():
        if by_name.get(name) != expected_id:
            raise CatalogRejected(f"device family identity mismatch: {name}")
    gwg_names = sorted(x for x in by_name if x.startswith("GWG_"))
    vbem = sorted(x for x in gwg_names if x.startswith("GWG_VBEM_"))
    if pinned and (len(gwg_names) != 21 or len(vbem) != 5):
        raise CatalogRejected("known host catalog profile count changed")
    if "VDensHO1" in gwg_names or "VDensHO1_4" in gwg_names:
        raise CatalogRejected("cross-family alias contamination")
    return {
        "host_profile_rows": len(by_id),
        "vdensho1_type_id": by_name["VDensHO1"],
        "vdensho1_4_type_id": by_name["VDensHO1_4"],
        "gwg_vbem_00_type_id": by_name["GWG_VBEM_00"],
        "hv_gwg_type_id": by_name["HV_GWG"],
        "gwg_prefixed_type_count": len(gwg_names),
        "gwg_vbem_type_count": len(vbem),
        "gwg_vbem_profiles": [{ "type_id": by_name[name], "alias": name } for name in vbem],
        "VDensHO1_is_not_GWG_host_profile": True,
        "GWG_2053_correspondence_to_a_specific_VitoSoft_type_proven": False,
        "MCU_ROM_access_inferred": False,
    }


def file_sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while True:
            block = stream.read(2 * 1024 * 1024)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def audit(path: Path = DP, *, verify_sha: bool = True):
    if not path.is_file() or not 64 <= path.stat().st_size <= MAX:
        raise CatalogRejected("catalog not a bounded regular file")
    sha = file_sha(path)
    if verify_sha and (sha != DP_SHA or path.stat().st_size != 186_559_004):
        raise CatalogRejected("unknown device catalog original SHA/size")
    with path.open("rb") as stream:
        with mmap.mmap(stream.fileno(), length=0, access=mmap.ACCESS_READ) as mm:
            report = parse_rows(mm, pinned=verify_sha)
    report.update({
        "audit": "PASS",
        "source_kind": "VITOSOFT_HOST_CATALOG_NOT_CONTROLLER_FIRMWARE",
        "source_sha256": sha,
        "source_size": path.stat().st_size,
        "target_controller": "WB2A/VDensHO1/20C2",
        "controller_read_operations": 0,
        "controller_writes": 0,
        "program_rom_bytes_read": 0,
    })
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    result = audit()
    content = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.out:
        args.out.write_text(content, encoding="utf-8")
    print(content, end="")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, CatalogRejected) as exc:
        print("REJECTED:", exc, file=sys.stderr)
        sys.exit(2)
