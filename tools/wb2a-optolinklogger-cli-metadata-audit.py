#!/usr/bin/env python3
"""Offline .NET CLI metadata audit of 2011 OpenV OptoLinkLogger.exe.

Locates the REAL managed methods and literal strings in PE/.NET metadata.
No executable is ever run. No networking, hardware commands, bootloader calls,
service changes, or firmware side effects.

Purpose: determine whether the historic "Ganzen Speicher auslesen" UI exposes a
20-bit ROM memory monitor or the known 16-bit KW/VS1 virtual read stream.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys

DEFAULT = Path("/home/chatgpt-admin/research/gwg-artifacts/target-unpacked/bc7ca87707c24d1826bcb6ba71b5172f5f5f73c9_OptoLinkLogger_v0.0.4/OptoLinkLogger.exe")
SHA = "9f01cb85bb9e4c6982ac405cee2bc7e67a534e9bc95d3e7a637882c3768976ff"
EXPECTED_BYTES = 131072
FAT_HEADER = 3
MAX_FILE_BYTES = 500_000


class MetadataRejected(ValueError):
    pass


def need(b, p, n):
    if p < 0 or n < 0 or p + n > len(b):
        raise MetadataRejected(f"truncated metadata at 0x{p:X}, need {n}")
    return b[p:p+n]


def u16(b, p):
    return struct.unpack("<H", need(b, p, 2))[0]


def u32(b, p):
    return struct.unpack("<I", need(b, p, 4))[0]


def u64(b, p):
    return struct.unpack("<Q", need(b, p, 8))[0]


def compressed(b, p):
    a = need(b, p, 1)[0]
    if a < 0x80:
        return a, p + 1
    if a < 0xC0:
        c = need(b, p, 2)
        return ((c[0] & 0x3F) << 8) | c[1], p + 2
    if a < 0xE0:
        c = need(b, p, 4)
        return ((c[0] & 0x1F) << 24) | (c[1] << 16) | (c[2] << 8) | c[3], p + 4
    raise MetadataRejected("invalid compressed uint")


def c_string(b, offset):
    if not 0 <= offset < len(b):
        raise MetadataRejected("string offset out of range")
    end = b.find(b"\0", offset)
    if end < 0:
        raise MetadataRejected("unterminated string")
    return b[offset:end].decode("utf-8")


def file_rva_reader(data):
    if need(data, 0, 2) != b"MZ":
        raise MetadataRejected("not PE MZ")
    pe = u32(data, 0x3C)
    if need(data, pe, 4) != b"PE\0\0":
        raise MetadataRejected("not PE signature")
    nsections = u16(data, pe + 6)
    optsize = u16(data, pe + 20)
    optional = pe + 24
    if u16(data, optional) != 0x10B or not 0 < nsections < 16:
        raise MetadataRejected("expected PE32 CLR executable")
    sections = []
    for i in range(nsections):
        p = optional + optsize + 40 * i
        sections.append({
            "name": need(data, p, 8).split(b"\0", 1)[0].decode("ascii"),
            "virtual_size": u32(data, p + 8),
            "rva": u32(data, p + 12),
            "raw_size": u32(data, p + 16),
            "raw": u32(data, p + 20),
        })

    def to_file(rva, size=1):
        for s in sections:
            if s["rva"] <= rva and rva + size <= s["rva"] + s["raw_size"]:
                o = s["raw"] + rva - s["rva"]
                need(data, o, size)
                return o
        raise MetadataRejected(f"RVA not present in physical PE section: 0x{rva:X}")

    cli_rva = u32(data, optional + 96 + 14 * 8)
    cli_size = u32(data, optional + 96 + 14 * 8 + 4)
    if not 0 < cli_size <= 200:
        raise MetadataRejected("missing CLI header")
    cli = to_file(cli_rva, cli_size)
    meta_rva = u32(data, cli + 8)
    meta_size = u32(data, cli + 12)
    if not 100 < meta_size < MAX_FILE_BYTES:
        raise MetadataRejected("invalid CLR metadata size")
    md = to_file(meta_rva, meta_size)
    if need(data, md, 4) != b"BSJB":
        raise MetadataRejected("not CLI BSJB metadata")
    version_len = u32(data, md + 12)
    cursor = (md + 16 + version_len + 3) & ~3
    nstreams = u16(data, cursor + 2)
    cursor += 4
    streams = {}
    for i in range(nstreams):
        offset = u32(data, cursor)
        size = u32(data, cursor + 4)
        name = c_string(data, cursor + 8)
        name_space = (len(name) + 1 + 3) & ~3
        cursor += 8 + name_space
        need(data, md + offset, size)
        streams[name] = data[md + offset:md + offset + size]
    required = {"#Strings", "#Blob", "#US"}
    if not required.issubset(streams) or not ({"#~", "#-"} & streams.keys()):
        raise MetadataRejected("required CLR metadata streams absent")
    return to_file, streams, sections


def method_directory(streams):
    data = streams.get("#~", streams.get("#-"))
    names = streams["#Strings"]
    pos = 0
    _reserve = u32(data, pos)
    heap = data[6]
    valid = u64(data, 8)
    counts = {}
    pos = 24
    for i in range(64):
        if (valid >> i) & 1:
            counts[i] = u32(data, pos)
            pos += 4

    def idx(table):
        return 4 if counts.get(table, 0) >= 65536 else 2

    def coded(tables, nbits):
        threshold = 1 << (16 - nbits)
        return 4 if max(counts.get(n, 0) for n in tables) >= threshold else 2

    str_i = 4 if heap & 1 else 2
    guid_i = 4 if heap & 2 else 2
    blob_i = 4 if heap & 4 else 2

    # All tables BEFORE MethodDef=6 as per ECMA-335 II.22.
    sizes = {
        0: 2 + str_i + 3 * guid_i,
        1: coded([0, 26, 35, 1], 2) + 2 * str_i,
        2: 4 + 2 * str_i + coded([1, 2, 27], 2) + idx(4) + idx(6),
        3: idx(4),
        4: 2 + str_i + blob_i,
        5: idx(6),
        6: 4 + 2 + 2 + str_i + blob_i + idx(8),
    }
    if not 0 < counts.get(6, 0) < 10000:
        raise MetadataRejected("invalid MethodDef count")
    for i in range(6):
        if counts.get(i):
            pos += counts[i] * sizes[i]
    width = sizes[6]
    results = []
    for index in range(counts[6]):
        row = pos + index * width
        rva = u32(data, row)
        flags = u16(data, row + 6)
        name_i = int.from_bytes(need(data, row + 8, str_i), "little")
        name = c_string(names, name_i)
        results.append({"token": f"0600{index+1:04x}", "name": name,
                        "rva": rva, "flags": flags})
    return results, counts


def user_string(stream, token):
    if token >> 24 != 0x70:
        raise MetadataRejected("not CLR #US token")
    offset = token & 0x00FFFFFF
    size, begin = compressed(stream, offset)
    if size < 1 or size > 6000:
        raise MetadataRejected("empty or oversized #US literal")
    raw = need(stream, begin, size)
    # CLR user strings are UTF16LE with an additional 1-byte flag at end.
    if (size - 1) % 2:
        raise MetadataRejected("invalid UTF16LE user string size")
    return raw[:-1].decode("utf-16-le", errors="strict")


def read_method_body(binary, to_file, rva):
    if not rva:
        return b"", {"header": "non-IL"}
    start = to_file(rva)
    kind = binary[start] & 0x3
    if kind == 2:
        header_size = 1
        size = binary[start] >> 2
    elif kind == FAT_HEADER:
        flags = u16(binary, start)
        header_size = (flags >> 12) * 4
        if not 12 <= header_size <= 64:
            raise MetadataRejected("unbounded fat method header")
        size = u32(binary, start + 4)
    else:
        raise MetadataRejected("invalid IL method header")
    if not 0 <= size <= 50000:
        raise MetadataRejected("unbounded CLR method size")
    return need(binary, start + header_size, size), {
        "header": "tiny" if kind == 2 else "fat", "il_bytes": size,
    }


def tokens_from_il(il, stream):
    strings = []
    # Conservative byte scan: a successful UTF-16 #US decode is evidence
    # that the actual method carries the literal token. False candidates that
    # happen to be operands are ignored; field/control-flow decode is separate.
    for i in range(max(0, len(il) - 4)):
        if il[i] != 0x72 or il[i+4] != 0x70:
            continue
        token = int.from_bytes(il[i+1:i+5], "little")
        try:
            decoded = user_string(stream, token)
        except (MetadataRejected, UnicodeError):
            continue
        strings.append({"il_offset": i, "token": f"0x{token:08x}",
                        "value": decoded})
    return strings


def constants_from_il(il):
    # Heuristic only; do not treat bytes inside operands as actual IL opcodes.
    found = []
    for i in range(max(0, len(il) - 4)):
        if il[i] != 0x20:
            continue
        v = int.from_bytes(il[i+1:i+5], "little")
        if v in (0x8000, 0xFFFF, 0x10000, 0xFFFFF, 0xE0000, 0xC0000):
            found.append({"il_offset_candidate": i, "value": f"0x{v:X}"})
    return found


TARGETS = {"TS_DumpAll", "TS_ReadData", "TS_Reader", "SetReadAddr",
           "GetReadAddr", "SetReadLen", "GetReadLen", "DumpStartAddr",
           "DumpLength", "ReadBuf", "ReadBytes"}

# Exact IL of real early-2011 OpenV binary; independently bound to the
# entire executable SHA256, not a constructed sample. Both accessors use
# two BYTE-array cells for address (index 1 high, index 2 low); length is
# a single BYTE-array cell (index 3). 0xFF is a mask, not a 20-bit page.
ADDR_IL = bytes.fromhex(
    "7e5d00000417021e6420ff0000005fd29c"
    "7e5d000004180220ff0000005fd29c2a")
LEN_IL = bytes.fromhex("7e5d000004190220ff0000005fd29c2a")
GET_ADDR_IL = bytes.fromhex(
    "7e5d000004179120000100005a7e5d0000041891582a")


def validate_2011_dump_contract(methods, *, strict):
    lookup = {method["name"]: method["body"] for method in methods
              if method["name"] in {"TS_DumpAll", "SetReadAddr",
                                    "GetReadAddr", "SetReadLen", "GetReadLen"}}
    if not {"TS_DumpAll", "SetReadAddr", "GetReadAddr", "SetReadLen",
            "GetReadLen"}.issubset(lookup):
        raise MetadataRejected("2011 dump accessor not present")
    bodies_match = (
        lookup["SetReadAddr"] == ADDR_IL
        and lookup["SetReadLen"] == LEN_IL
        and lookup["GetReadAddr"] == GET_ADDR_IL
    )
    # These are direct CIL call instructions (0x28 + 4-byte MethodDef token).
    # Requiring same method tokens as the verified pinned original excludes
    # coincidental x86 executable string matches.
    original_tokens = {
        "SetReadAddr": "25000006",
        "GetReadAddr": "26000006",
        "SetReadLen": "27000006",
        "GetReadLen": "28000006",
    }
    calls = {name: lookup["TS_DumpAll"].count(
             b"\x28" + bytes.fromhex(tok)) for name, tok in original_tokens.items()}
    chunk_254 = b"\x20\xfe\x00\x00\x00" in lookup["TS_DumpAll"]
    if strict and (not bodies_match or not all(v == 1 for v in calls.values())
                   or not chunk_254):
        raise MetadataRejected("original 2011 VS1 dump IL not as claimed")
    return {
        "address_setter_exact_original_il": bodies_match,
        "dump_calls_expected_accessors": calls,
        "dump_254_byte_chunk_literal_present": chunk_254,
        "vs1_primitive_wire_address_bytes": 2 if bodies_match else None,
        "vs1_primitive_wire_length_bytes": 1 if bodies_match else None,
        "max_direct_primitive_address": "0xFFFF" if bodies_match else None,
        "high_20bit_cpu_address_not_transmitted": bool(bodies_match),
    }


def audit(data: bytes, *, pinned: bool = True):
    checksum = hashlib.sha256(data).hexdigest()
    if len(data) > MAX_FILE_BYTES or len(data) < 2000:
        raise MetadataRejected("not bounded .NET binary")
    if pinned and (checksum != SHA or len(data) != EXPECTED_BYTES):
        raise MetadataRejected("historical binary SHA/length mismatch")
    rva, streams, _sections = file_rva_reader(data)
    methods, counts = method_directory(streams)
    names = {m["name"] for m in methods}
    found = {}
    raw_methods = []
    for m in methods:
        if m["name"] not in TARGETS and "Dump" not in m["name"]:
            continue
        il, info = read_method_body(data, rva, m["rva"])
        raw_methods.append({"name": m["name"], "body": il})
        info.update({
            "token": m["token"], "rva": f"0x{m['rva']:X}",
            "literals": tokens_from_il(il, streams["#US"]),
            "potential_width_constants_not_semantically_disassembled": constants_from_il(il),
            "il_sha256": hashlib.sha256(il).hexdigest(),
        })
        found.setdefault(m["name"], []).append(info)
    if pinned and not {"TS_DumpAll", "TS_ReadData"}.issubset(found):
        raise MetadataRejected("original dump methods absent")
    marker_strings = [v["value"] for group in found.values()
                      for meth in group for v in meth["literals"]]
    contract = validate_2011_dump_contract(raw_methods, strict=pinned)
    if pinned and "Dump supports protocol VS1 only." not in marker_strings:
        raise MetadataRejected("2011 dump VS1-only guard literal absent")
    # This is a negative ROM provenance check, not a proof no unknown
    # function exists in any earlier Viessmann firmware.
    return {
        "audit": "PASS",
        "original_sha256": checksum,
        "size_bytes": len(data),
        "file_kind": "MICROSOFT_NET_PE_PROGRAM_NOT_HEATER_ROM",
        "method_defs": counts[6],
        "target_methods": found,
        "vs1_dump_guard_literally_referenced": "Dump supports protocol VS1 only." in marker_strings,
        "verified_dump_wire_contract": contract,
        "controller_reads": 0,
        "controller_writes": 0,
        "program_rom_dump_bytes": 0,
        "twenty_bit_controller_rom_monitor_proven": False,
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input", type=Path, default=DEFAULT)
    p.add_argument("--output", type=Path)
    args = p.parse_args()
    result = audit(args.input.read_bytes(), pinned=True)
    encoded = json.dumps(result, sort_keys=True, indent=2) + "\n"
    if args.output:
        args.output.write_text(encoded, encoding="utf-8")
    print(encoded, end="")


if __name__ == "__main__":
    try:
        main()
    except (OSError, MetadataRejected) as exc:
        print("REJECTED:", exc, file=sys.stderr)
        sys.exit(2)
