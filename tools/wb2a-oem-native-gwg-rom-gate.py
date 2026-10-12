#!/usr/bin/env python3
"""Static OEM ROM transport gate: native GWG detector and all CLR IL methods.

Run against separately saved original Viessmann VitoSoft 300 SID1 modules.
NO Windows execution, serial/Optolink traffic, controller writes, or resets.
This is an *absence-of-source-evidence* assessment, not a proof that no hidden
20-bit ROM service exists inside the controller.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import sys

ORIGINALS = Path("/home/chatgpt-admin/research/vitosoft-oem-original-20261012")
ROOT = ORIGINALS / "extracted-readonly/data/OFFLINE/3C8BB38F/CEE8DEB9"
CORE = ROOT / "vsmInterfaceCore.dll"
NATIVE = ROOT / "vsmGWG99Native.dll"
PYDEPS = ORIGINALS / "pydeps"
ORIGINAL_HASHES = {
    "vsmInterfaceCore.dll":
        ("1653fa1346bd37b3e599cdf55fe8eb053d985f8efb8a007c18b94996a575f90d", 368640),
    "vsmGWG99Native.dll":
        ("b4c0f19d56d8e4b9ece830dc8ab78194debaee67480472bbf94fec0eb1d7f4a2", 431104),
}
# Real instructions from original PE at RVA 0x1683:
#   movb $0xC7, 0x24(%rsp)
#   movb $0xF8, 0x25(%rsp)
#   movb $0x04, 0x26(%rsp)
# ... then mov eax,3; store count; invoke local Win32 WriteFile wrapper.
NATIVE_GWG_REQUEST = bytes.fromhex(
    "c6442424c7 c6442425f8 c644242604"
)
NATIVE_REQUEST_LENGTH = bytes.fromhex(
    "b803000000 6689442440"
)
# RX byte0 0x20, RX byte1 0x53 or 0x54, not 0xC2 (WB2A).
NATIVE_ID_GATE = bytes.fromhex(
    "0fb6442464 83f820 751c "
    "0fb6442465 83f853 740a "
    "0fb6442465 83f854 7508"
)
GETBYTES_INT32_TOKEN = 0x0A0000E7
GETBYTES_INT32_SIG = bytes.fromhex("00011d0508")
GETBYTES_INT16_TOKEN = 0x0A0000F9
GETBYTES_INT16_SIG = bytes.fromhex("00011d0507")
INT32_RPC_NAMES = {
    "vsmInterfaceCore.rpc.RPCConverter.ConvertRpcToDevice_RPCSetImpulseCounter_IO_EM_DE",
    "vsmInterfaceCore.rpc.RPCConverter.ConvertRpcToDevice_RPCSetGrenzwertLONKanalAlarm",
}
# The one large (0xC0000..0xFFFFF) IL literal in the library happens
# to be 999999 decimal in SerialPortValidator, not a ROM address.
FAR_NON_ADDRESS_LITERAL = 999999
FAR_NON_ADDRESS_OWNER = "vsmInterfaceCore.connection.SerialPortValidator.DoWork"


class RejectUnproven(ValueError):
    pass


def hash_source(path: Path, expected: tuple[str, int]) -> str:
    digest, size = expected
    if not path.is_file() or path.stat().st_size != size:
        raise RejectUnproven(f"OEM original absent or unexpected length: {path.name}")
    with path.open("rb") as stream:
        real = hashlib.file_digest(stream, "sha256").hexdigest()
    if real != digest:
        raise RejectUnproven(f"original SHA256 mismatch: {path.name}")
    return real


def native_detection_contract(request_bytes: bytes, request_length: bytes,
                              id_gate: bytes, exports: dict[str, int]) -> dict:
    if request_bytes != NATIVE_GWG_REQUEST:
        raise RejectUnproven("native GWG identity frame not source-attested")
    if request_length != NATIVE_REQUEST_LENGTH:
        raise RejectUnproven("GWG detector does not use verified 3-byte write length")
    if id_gate != NATIVE_ID_GATE:
        raise RejectUnproven("GWG response ID gate changed")
    if exports != {"CheckGWG": 0x1080, "TestCall_GWG99Native": 0x1040}:
        raise RejectUnproven("different native DLL export surface")
    return {
        "raw_send_bytes": "c7f804",
        "read_only_identity_probe": True,
        "native_gwg_probe_sends_full_wiki_stx_eot_frame": False,
        "legacy_accepted_product_ids": ["2053", "2054"],
        "wb2a_id_20c2_accepted_by_native_detector": False,
        "export_names": sorted(exports),
        "native_rom_dump_export_found": False,
    }


def check_int32_calls(calls: dict[str, Counter], tokens: dict[int, tuple[str, bytes]],
                      far: dict[int, list[str]], high_shifts: list[dict]) -> dict:
    if tokens.get(GETBYTES_INT32_TOKEN) != ("GetBytes", GETBYTES_INT32_SIG):
        raise RejectUnproven("OEM Int32 BitConverter reference/signature changed")
    if tokens.get(GETBYTES_INT16_TOKEN) != ("GetBytes", GETBYTES_INT16_SIG):
        raise RejectUnproven("OEM Int16 BitConverter reference/signature changed")
    uses = {fq: count[GETBYTES_INT32_TOKEN] for fq, count in calls.items()
            if count[GETBYTES_INT32_TOKEN]}
    if uses != {x: 1 for x in INT32_RPC_NAMES}:
        raise RejectUnproven("unexamined GetBytes(Int32) callsite")
    if high_shifts:
        raise RejectUnproven("new high-bit shift may affect 20-bit addressability")
    if far != {FAR_NON_ADDRESS_LITERAL: [FAR_NON_ADDRESS_OWNER]}:
        raise RejectUnproven("unexamined ROM-range literal in original methods")
    return {
        "getbytes_int32_exact_calls": dict(sorted(uses.items())),
        "getbytes_int16_signature": GETBYTES_INT16_SIG.hex(),
        "high_bit_16_or_24_shifts": 0,
        "rom_range_literal_0xf423f_999999_owner": FAR_NON_ADDRESS_OWNER,
        "rom_address_literal_found_in_inspected_code": False,
        "20bit_address_payload_serializer_demonstrated": False,
    }


def validate_native(pe) -> dict:
    if not getattr(pe, "DIRECTORY_ENTRY_EXPORT", None):
        raise RejectUnproven("missing native export directory")
    exports = {
        x.name.decode("ascii"): x.address for x in pe.DIRECTORY_ENTRY_EXPORT.symbols
        if x.name
    }
    if pe.OPTIONAL_HEADER.Magic != 0x20B:
        raise RejectUnproven("native gateway not PE32+")
    data = pe.get_data(0x1683, len(NATIVE_GWG_REQUEST))
    request_len = pe.get_data(0x169C, len(NATIVE_REQUEST_LENGTH))
    idbytes = pe.get_data(0x1205, len(NATIVE_ID_GATE))
    return native_detection_contract(data, request_len, idbytes, exports)


def high_shift_literals(instructions: list) -> list[dict]:
    hits = []
    for i, op in enumerate(instructions[:-1]):
        if op.opcode.name not in ("ldc.i4", "ldc.i4.s") or type(op.operand) is not int:
            continue
        if op.operand in (16, 24) and instructions[i + 1].opcode.name in ("shl", "shr", "shr.un"):
            hits.append({"IL_offset": op.offset, "shift_bits": op.operand})
    return hits


def audit():
    for file, expected in ORIGINAL_HASHES.items():
        hash_source(ROOT / file, expected)
    if not PYDEPS.is_dir():
        raise RejectUnproven("private static dnfile/dncil/pefile parsers absent")
    sys.path.insert(0, str(PYDEPS))
    import dnfile
    import pefile
    from dncil.cil.body import CilMethodBody
    from dncil.cil.body.reader import CilMethodBodyReaderBytes

    native = pefile.PE(str(NATIVE), fast_load=False)
    gwg = validate_native(native)
    core = dnfile.dnPE(str(CORE))
    if not core.net or not core.net.mdtables:
        raise RejectUnproven("not expected CLR binary")
    tables = core.net.mdtables
    if len(tables.TypeDef.rows) != 206 or len(tables.MethodDef.rows) != 2571:
        raise RejectUnproven("OEM CLR table unexpected size")
    tokens = {
        (0x0A000000 + i): (str(ref.Name), bytes(ref.Signature.value))
        for i, ref in enumerate(tables.MemberRef.rows, 1)
        if str(ref.Name) == "GetBytes"
    }
    uses = {}
    far = defaultdict(list)
    shifts = []
    decoded = 0
    for typ in tables.TypeDef.rows:
        typename = str(typ.TypeNamespace) + "." + str(typ.TypeName)
        for index in typ.MethodList:
            r = index.row
            if not r or not r.Rva:
                continue
            fq = typename + "." + str(r.Name)
            body = CilMethodBody(CilMethodBodyReaderBytes(core.get_data(r.Rva, 40000)))
            decoded += 1
            calls = Counter(
                getattr(x.operand, "value", None)
                for x in body.instructions if x.opcode.name in ("call", "callvirt")
            )
            uses[fq] = calls
            for op in body.instructions:
                if op.opcode.name in ("ldc.i4", "ldc.i4.s") and type(op.operand) is int:
                    if 0xC0000 <= op.operand <= 0xFFFFF:
                        far[op.operand].append(fq)
            for entry in high_shift_literals(body.instructions):
                shifts.append({"method": fq, **entry})
    if decoded != 2490:
        raise RejectUnproven("unexamined CLR method bodies")
    conclusion = check_int32_calls(uses, tokens, dict(far), shifts)
    return {
        "audit": "PASS",
        "date": "2026-10-12",
        "original_oem_core_sha256": ORIGINAL_HASHES["vsmInterfaceCore.dll"][0],
        "original_oem_native_gwg_sha256": ORIGINAL_HASHES["vsmGWG99Native.dll"][0],
        "clr_methods_decoded": decoded,
        "native_gwg_detector": gwg,
        "host_20bit_serializer_scan": conclusion,
        "controller_writes": 0,
        "controller_reads": 0,
        "firmware_bytes_recovered": 0,
        "hidden_wb2a_application_rom_monitor_excluded": False,
        "ready_to_live_dump_program_rom": False,
        "next_required_evidence": "20C2-bound, source-attested ROM page/bank/monitor/copy endpoint",
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out", type=Path)
    o = p.parse_args()
    report = audit()
    output = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if o.out is not None:
        o.out.write_text(output, encoding="utf-8")
    print(output, end="")


if __name__ == "__main__":
    try:
        main()
    except (OSError, RejectUnproven, ImportError, ValueError) as exc:
        print("OEM_ROM_GATE_REJECTED: " + str(exc), file=sys.stderr)
        sys.exit(2)
