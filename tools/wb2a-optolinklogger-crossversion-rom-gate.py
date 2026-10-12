#!/usr/bin/env python3
"""Two original OpenV OptoLinkLogger releases: SHA-pinned .NET IL dump audit.

Derives actual 2-byte VS1 address and 1-byte size setters in *both* historical
executables, including their different MethodDef tokens and field locations.
No .exe runs; every byte comes from PE metadata. No hardware/serial I/O.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
PARSER = ROOT / "tools" / "wb2a-optolinklogger-cli-metadata-audit.py"
BASE = Path("/home/chatgpt-admin/research/gwg-artifacts/target-unpacked")
SOURCES = {
    "2010-02-06_v0.0.1": {
        "path": BASE / "5478defe086d4de67698fc95378ad2ee5e76eea7_OptoLinkLogger_v0.0.1" / "OptoLinkLogger.exe",
        "sha": "cb3323cb0c079c8218cc17d4fc25038d349b997c730189547458aa58c7cd1dc5",
        "size": 118784,
        "methods": {
            "SetReadAddr": "7e5000000417021e6320ff0000005fd29c7e50000004180220ff0000005fd29c2a",
            "GetReadAddr": "7e50000004179120000100005a7e500000041891582a",
            "SetReadLen": "7e50000004190220ff0000005fd29c2a",
            "GetReadLen": "7e5000000419912a",
        },
    },
    "2011-01-23_v0.0.4": {
        "path": BASE / "bc7ca87707c24d1826bcb6ba71b5172f5f5f73c9_OptoLinkLogger_v0.0.4" / "OptoLinkLogger.exe",
        "sha": "9f01cb85bb9e4c6982ac405cee2bc7e67a534e9bc95d3e7a637882c3768976ff",
        "size": 131072,
        "methods": {
            "SetReadAddr": "7e5d00000417021e6420ff0000005fd29c7e5d000004180220ff0000005fd29c2a",
            "GetReadAddr": "7e5d000004179120000100005a7e5d0000041891582a",
            "SetReadLen": "7e5d000004190220ff0000005fd29c2a",
            "GetReadLen": "7e5d00000419912a",
        },
    },
}


class CrossVersionRejected(ValueError):
    pass


def model_original_vs1_address_setter(address: int, length: int) -> dict:
    """Pure byte-level model of the two exact IL setter bodies, no I/O."""
    if not isinstance(address, int) or not 0 <= address <= 0xFFFFF:
        raise CrossVersionRejected("address must be 20-bit unsigned integer")
    if not isinstance(length, int) or not 1 <= length <= 0xFE:
        raise CrossVersionRejected("bounded read length expected")
    # Original SetReadAddr: address >> 8 & 0xFF, address & 0xFF;
    # Original SetReadLen: length & 0xFF (one byte).
    hi, lo, n = (address >> 8) & 0xFF, address & 0xFF, length & 0xFF
    return {"source_cpu_address": f"0x{address:05X}",
            "actual_wire_address": f"0x{((hi << 8) | lo):04X}",
            "source_upper_4_bits_lost": bool(address >> 16),
            "actual_address_and_length_field_hex": bytes((hi, lo, n)).hex()}


def parser_module():
    s = importlib.util.spec_from_file_location("openv_net_cli_method_parser", PARSER)
    if not s or not s.loader:
        raise CrossVersionRejected("missing source-pinned CLI parser")
    p = importlib.util.module_from_spec(s)
    sys.modules[s.name] = p
    s.loader.exec_module(p)
    return p


def source_verification(tag, b, cli):
    if tag not in SOURCES:
        raise CrossVersionRejected("unknown historical binary revision")
    spec = SOURCES[tag]
    if len(b) != spec["size"] or hashlib.sha256(b).hexdigest() != spec["sha"]:
        raise CrossVersionRejected("original executable identity changed: " + tag)
    to_file, streams, sections = cli.file_rva_reader(b)
    rows, counts = cli.method_directory(streams)
    names = {}
    for row in rows:
        if row["name"] in set(spec["methods"]) | {"TS_DumpAll"}:
            if row["name"] in names:
                raise CrossVersionRejected("duplicate method " + row["name"])
            body, _ = cli.read_method_body(b, to_file, row["rva"])
            names[row["name"]] = {
                "token": int(row["token"], 16),
                "il": body,
                "rva": row["rva"],
            }
    expected = set(spec["methods"]) | {"TS_DumpAll"}
    if set(names) != expected:
        raise CrossVersionRejected("required original dump method missing")
    for key, hex_body in spec["methods"].items():
        if names[key]["il"] != bytes.fromhex(hex_body):
            raise CrossVersionRejected("source-attested accessor body mutated: " + key)
    il = names["TS_DumpAll"]["il"]
    # 0x28: CIL 'call' with 4-byte metadata token. MethodDef IDs differ
    # between releases, so resolve MethodDef names before comparison.
    calls = {
        key: il.count(bytes((0x28,)) + names[key]["token"].to_bytes(4, "little"))
        for key in spec["methods"]
    }
    if any(value != 1 for value in calls.values()):
        raise CrossVersionRejected("DumpAll doesn't call all four VS1 accessors once")
    if il.count(bytes.fromhex("20fe000000")) != 1:
        raise CrossVersionRejected("unrecognized 254-byte chunk plan")
    strings = [entry["value"] for entry in cli.tokens_from_il(il, streams["#US"])]
    if strings.count("Dump supports protocol VS1 only.") != 1:
        raise CrossVersionRejected("missing/ambiguous VS1 protocol gate")
    return {
        "version": tag,
        "exe_sha256": spec["sha"],
        "exe_size": len(b),
        "method_defs": counts[6],
        "TS_DumpAll_rva": hex(names["TS_DumpAll"]["rva"]),
        "TS_DumpAll_il_sha256": hashlib.sha256(il).hexdigest(),
        "accessor_method_tokens": {
            name: f"0x{body['token']:08X}" for name, body in names.items()
            if name != "TS_DumpAll"},
        "accessor_call_counts_in_dump": calls,
        "dump_via_vs1_only": True,
        "max_direct_vs1_address": "0xFFFF",
        "request_address_bits": 16,
        "read_length_bits": 8,
        "chunk_limit_literal": 254,
        "20_bit_rom_program_read_proven": False,
        "method_setters_exact_source_backed": True,
        "byteorder": "big_endian_address_indices_1_2",
    }


def audit(read_bytes=None):
    cli = parser_module()
    analyses = {}
    for label, item in SOURCES.items():
        b = read_bytes(label) if read_bytes else item["path"].read_bytes()
        analyses[label] = source_verification(label, b, cli)
    return {
        "audit": "PASS",
        "original_revisions_attested": len(analyses),
        "controller_memory_reads": 0,
        "controller_memory_writes": 0,
        "controller_rom_bytes_extracted": 0,
        "rom_transfer_with_optolinklogger_achievable": False,
        "conclusion": "BOTH_HISTORICAL_OPENV_DUMPS_ARE_VS1_16_BIT_VIRTUAL_ADDRESS_READERS",
        "upper_address_alias_examples": [
            model_original_vs1_address_setter(a, 8)
            for a in (0x00000, 0x0FFFF, 0xE0000, 0xF23FF, 0xFFFFF)
        ],
        "revisions": analyses,
    }


def main():
    args = argparse.ArgumentParser(description=__doc__)
    args.add_argument("--out", type=Path)
    v = args.parse_args()
    result = audit()
    output = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if v.out:
        v.out.write_text(output, encoding="utf-8")
    print(output, end="")


if __name__ == "__main__":
    try:
        main()
    except (OSError, CrossVersionRejected, ValueError) as e:
        print("SOURCE_REJECTED:", e, file=sys.stderr)
        sys.exit(2)
