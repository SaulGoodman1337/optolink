#!/usr/bin/env python3
"""Read-only OEM VitoSoft .NET provenance audit for WB2A ROM accessibility.

The 2025 OEM VitoSoft 300 SID1 installer and vsmInterfaceCore.dll are private
originals. This audits METHOD BODIES from dnfile + dncil; it never executes a
Windows EXE/DLL, opens Optolink, talks to a serial port, or modifies a heater.

"RDAPAddressLength" describes a fieldbus *routing address*, not a 20-bit
M16C source memory pointer. This distinction is source-attested.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

PRIVATE = Path("/home/chatgpt-admin/research/vitosoft-oem-original-20261012")
INSTALLER = PRIVATE / "Vitosoft300SID1_Setup.exe"
INSTALLER_SIZE = 425_114_319
INSTALLER_SHA = "d02434e002369fc0d30adf45285fd6878ab978dea4e3d1310933e93bc0492116"
CORE = PRIVATE / "extracted-readonly/data/OFFLINE/3C8BB38F/CEE8DEB9/vsmInterfaceCore.dll"
CORE_SIZE = 368_640
CORE_SHA = "1653fa1346bd37b3e599cdf55fe8eb053d985f8efb8a007c18b94996a575f90d"
LIBS = PRIVATE / "pydeps"
# Hashes of *entire native-method raw bodies*, including CLR method header.
METHODS = {
    "vsmInterfaceCore.vs.VS1Message.toByteArray":
        "066589f4027c15f1d108f031794c28ce4eafb1a2a78f62781c3d27ac4ae7e502",
    "vsmInterfaceCore.vs.VS1Message.getVS1MessageFromLDAPMessage":
        "13c77176913b37f33b1ba2ab2e386192f33172df1db394e7d0cecc1dc7d0e6c7",
    "vsmInterfaceCore.protocols.LDAPMessage.toByteArray":
        "94e79a50315944793100e12d69cc9f5f89a94b04208d9b96e9434c0ddf5f0d60",
    "vsmInterfaceCore.protocols.RDAPMessage.toByteArray":
        "15c50e7cc2aa4d5a57074b8a0209a401f545244733a15dc24741539c865ab299",
    "vsmInterfaceCore.protocols.RDAPMessage..ctor":
        "f0ef362be2b7663e46233654f7fcfce46736e896f4a15871525e96e3037a85dc",
    "vsmInterfaceCore.rpc.RPCConverter.ConvertReadRequestToDevice":
        "ec4d3490bac635cb0116173b29abeed9deb9fff6eccb5afa29f66860e078b6ae",
    "vsmInterfaceCore.rpc.RPCConverter.ConvertRpcToDevice_VitosorpAccessController":
        "d5ff9521de8db164b8ed94f25ae569da9400d3ded18ecc5c4669705a1432c416",
    "vsmInterfaceCore.rpc.RPCConverter.ConvertRpcFromDevice_VitosorpAccessController":
        "f16e5627465b7f8bc35cba0c12ed4f594cf5284bc271540c880976a7ded5a6ce",
}

# Exact CLR FieldDef entries, from the source-bound OEM class metadata.
VS1_FIELDS = {
    "_Command": 0x04000001,
    "_VirtuellReadADDRHighByte": 0x04000002,
    "_VirtuellReadADDRLowByte": 0x04000003,
    "_BlockLength": 0x04000004,
    "_Data": 0x04000005,
}
LDAP_FIELDS = {
    "ADDRHighByte": 0x0400013E,
    "ADDRLowByte": 0x0400013F,
    "Data": 0x04000140,
    "DataLength": 0x04000141,
}
RDAP_FIELDS = {
    "RoutingFlag": 0x04000146,
    "AddressIdentifier": 0x04000147,
    "AddressLength": 0x04000148,
    "FieldBusAddress": 0x04000149,
    "MessageList": 0x0400014B,
}
ROUTING_FIELDS = (0x04000148, 0x04000149)


class OemAuditRejected(ValueError):
    pass


def sha_ok(path: Path, expected_size: int, expected_sha: str) -> str:
    if not path.is_file() or path.stat().st_size != expected_size:
        raise OemAuditRejected("private OEM source absent or unexpected size")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != expected_sha:
        raise OemAuditRejected("OEM source changed; no conclusions")
    return digest


def address_model(cpu_address: int, size: int = 8) -> dict:
    """PURE simulation of P300/LDAP 2-byte address, not a hardware request."""
    if type(cpu_address) is not int or not 0 <= cpu_address <= 0xFFFFF:
        raise OemAuditRejected("20-bit unsigned input required")
    if type(size) is not int or not 1 <= size <= 254:
        raise OemAuditRejected("bounded synthetic size required")
    return {
        "requested_cpu_address": f"0x{cpu_address:05X}",
        "actual_ldap_address": f"0x{cpu_address & 0xFFFF:04X}",
        "upper_bank_nibble_lost": bool(cpu_address >> 16),
        "ldap_address_and_length_fields_hex": bytes(((cpu_address >> 8) & 255,
                                                    cpu_address & 255, size)).hex(),
    }


def check_field_contract(actual: dict, expected: dict, label: str):
    """Fail closed on inconsistent field token IDs or unspecific field layout."""
    if any(actual.get(name) != token for name, token in expected.items()):
        raise OemAuditRejected(f"{label} field ownership/token mapping changed")
    if len(set(expected.values())) != len(expected):
        raise OemAuditRejected("overlapping expected field token list")
    return True


def check_serializer_instructions(instructions: list, *, kind: str):
    """Strictly compare meaningful CLR field LOADS to real-class definitions."""
    def ref(ins, opcode):
        return {getattr(a.operand, "value", None)
                for a in ins if a.opcode.name == opcode}
    if kind == "ldap":
        fields = ref(instructions, "ldfld")
        if not set(LDAP_FIELDS.values()).issubset(fields):
            raise OemAuditRejected("LDAP missing address high/low/length fields")
        if len(fields & set(ROUTING_FIELDS)) != 0:
            raise OemAuditRejected("LDAP unexpectedly uses RDAP routing")
        return {"address_field_bytes": 2, "length_field_bytes": 1}
    if kind == "vs1":
        fields = ref(instructions, "ldfld")
        if not set(VS1_FIELDS.values()).issubset(fields):
            raise OemAuditRejected("VS1 lacks required byte address fields")
        return {"address_field_bytes": 2, "length_field_bytes": 1}
    if kind == "rdap":
        fields = ref(instructions, "ldfld")
        if not set(RDAP_FIELDS.values()).issubset(fields):
            raise OemAuditRejected("RDAP routing-field serializer no longer matches")
        if set(LDAP_FIELDS.values()) & fields:
            raise OemAuditRejected("RDAP address conflated with LDAP address")
        return {"fieldbus_address_is_byte_array": True,
                "rdap_route_not_mcu_memory_address_proven": True}
    raise OemAuditRejected("unknown serializer kind")


def check_vitosorp_reads(instructions: list, *, method_signature: bytes, getbytes_signature: bytes):
    """OEM RPC 0xA400/A401: resolves actual Address type + byte array encoding."""
    if method_signature != bytes.fromhex("200007"):  # instance Int16 get_Address()
        raise OemAuditRejected("OEM Request.Address is not expected Int16")
    if getbytes_signature != bytes.fromhex("00011d0507"):  # static byte[] GetBytes(Int16)
        raise OemAuditRejected("OEM BitConverter.GetBytes(Int16) changed")
    literals = [int(x.operand) for x in instructions
                if x.opcode.name in ("ldc.i4", "ldc.i4.s")]
    if literals.count(0xA400) != 1 or literals.count(0xA401) != 1:
        raise OemAuditRejected("RPC literal IDs changed")
    calls = [getattr(x.operand, "value", None) for x in instructions
             if x.opcode.name in ("call", "callvirt")]
    if calls.count(0x060000E7) != 2 or calls.count(0x0A0000F9) != 2:
        raise OemAuditRejected("RPC no longer reads Int16 address twice")
    if calls.count(0x060000E8) != 2:
        raise OemAuditRejected("RPC no longer writes 16-bit proxy addresses")
    if sum(x.opcode.name == "ldc.i4.3" for x in instructions) != 3 or sum(x.opcode.name == "newarr" for x in instructions) != 2:
        raise OemAuditRejected("RPC response/payload size layout changed")
    return {
        "rpc_code_read_hex": "0xA400",
        "rpc_code_write_hex": "0xA401",
        "request_address_type": "System.Int16",
        "bitconverter_signature": "System.Byte[] System.BitConverter.GetBytes(System.Int16)",
        "address_bytes": 2,
        "read_proxy_request_bytes": 3,
        "controller_program_rom_source_address_supported_proven": False,
    }


def audit(include_installer=True):
    sha_ok(CORE, CORE_SIZE, CORE_SHA)
    if include_installer:
        sha_ok(INSTALLER, INSTALLER_SIZE, INSTALLER_SHA)
    # Delay all third-party imports until after hashing original OEM source.
    if not LIBS.is_dir():
        raise OemAuditRejected("pinned private pure-Python dnfile/dncil modules not available")
    sys.path.insert(0, str(LIBS))
    import dnfile
    from dncil.cil.body import CilMethodBody
    from dncil.cil.body.reader import CilMethodBodyReaderBytes

    pe = dnfile.dnPE(str(CORE))
    if not pe.net or not pe.net.mdtables:
        raise OemAuditRejected("OEM library no longer CLR")
    types = pe.net.mdtables.TypeDef.rows
    methods = pe.net.mdtables.MethodDef.rows
    method_result = {}
    class_fields = {}
    class_methods = {}
    route_refs = {}
    class_targets = set()
    for x in METHODS:
        class_targets.add(x.rsplit(".", 1)[0])
    class_targets |= {"vsmInterfaceCore.vs.VS1Message",
                      "vsmInterfaceCore.protocols.LDAPMessage",
                      "vsmInterfaceCore.protocols.RDAPMessage"}
    for typ in types:
        name = str(typ.TypeNamespace) + "." + str(typ.TypeName)
        if name in class_targets:
            class_fields[name] = {
                str(field.row.Name): (0x04000000 + next(
                    i for i, original in enumerate(pe.net.mdtables.Field.rows, 1)
                    if original is field.row))
                for field in typ.FieldList if field.row
            }
        for field in typ.MethodList:
            row = field.row
            if row is None or not row.Rva:
                continue
            fq = name + "." + str(row.Name)
            if fq not in METHODS:
                continue
            if fq in method_result:
                raise OemAuditRejected("unexpected overloaded pinned method " + fq)
            body = CilMethodBody(CilMethodBodyReaderBytes(pe.get_data(row.Rva, 40000)))
            digest = hashlib.sha256(body.raw_bytes).hexdigest()
            if digest != METHODS[fq]:
                raise OemAuditRejected("critical OEM IL changed: " + fq)
            method_result[fq] = {
                "type": name, "method": str(row.Name), "RVA": f"0x{row.Rva:X}",
                "IL_code_bytes": body.code_size, "IL_body_SHA256": digest,
                "operations": body.instructions,
            }
    if set(method_result) != set(METHODS):
        raise OemAuditRejected("missing mandatory OEM method")

    check_field_contract(class_fields["vsmInterfaceCore.vs.VS1Message"], VS1_FIELDS, "VS1")
    check_field_contract(class_fields["vsmInterfaceCore.protocols.LDAPMessage"], LDAP_FIELDS, "LDAP")
    check_field_contract(class_fields["vsmInterfaceCore.protocols.RDAPMessage"], RDAP_FIELDS, "RDAP")

    def instructions(fq):
        return method_result[fq]["operations"]

    serializers = {
        "vs1": check_serializer_instructions(instructions(
            "vsmInterfaceCore.vs.VS1Message.toByteArray"), kind="vs1"),
        "ldap": check_serializer_instructions(instructions(
            "vsmInterfaceCore.protocols.LDAPMessage.toByteArray"), kind="ldap"),
        "rdap": check_serializer_instructions(instructions(
            "vsmInterfaceCore.protocols.RDAPMessage.toByteArray"), kind="rdap"),
    }
    member = pe.net.mdtables.MemberRef.rows[0xF9 - 1]
    method = methods[0xE7 - 1]
    if str(member.Name) != "GetBytes" or str(method.Name) != "get_Address":
        raise OemAuditRejected("OEM address/BitConverter methods renamed")
    proxy = check_vitosorp_reads(instructions(
        "vsmInterfaceCore.rpc.RPCConverter.ConvertRpcToDevice_VitosorpAccessController"),
        method_signature=bytes(method.Signature.value),
        getbytes_signature=bytes(member.Signature.value))

    # Count ONLY real parsed CIL ldfld/stfld operations, never scan arbitrary
    # 10-kB windows that accidentally include adjacent method bodies.
    routing_method_owners = set()
    parse_count = 0
    for typ in types:
        class_name = str(typ.TypeNamespace) + "." + str(typ.TypeName)
        for idx in typ.MethodList:
            row = idx.row
            if row is None or not row.Rva:
                continue
            body = CilMethodBody(CilMethodBodyReaderBytes(pe.get_data(row.Rva, 40000)))
            parse_count += 1
            if any(ins.opcode.name in ("ldfld", "stfld", "ldflda", "ldsfld", "stsfld")
                   and getattr(ins.operand, "value", None) in ROUTING_FIELDS
                   for ins in body.instructions):
                routing_method_owners.add(class_name + "." + str(row.Name))
    if routing_method_owners != {
        "vsmInterfaceCore.protocols.RDAPMessage..ctor",
        "vsmInterfaceCore.protocols.RDAPMessage.toByteArray",
    }:
        raise OemAuditRejected("unaccounted use of variable RDAP FieldBusAddress")

    return {
        "audit": "PASS",
        "scope": "original 2025 Viessmann VitoSoft SID1 host communications, not WB2A firmware",
        "installer_sha256_verified": bool(include_installer),
        "oem_core_sha256": CORE_SHA,
        "oem_core_size": CORE_SIZE,
        "controller_device_id_proven_in_library": False,
        "oem_core_clr_typedefs": len(types),
        "oem_core_clr_methoddefs": len(methods),
        "actual_cil_methods_parsed": parse_count,
        "attested_method_bodies": {
            k: {w: v for w, v in x.items() if w != "operations"}
            for k, x in method_result.items()
        },
        "verified_serializers": serializers,
        "rpc_vitosorp_read_write_contract": proxy,
        "rdap_fieldbus_routing_methods": sorted(routing_method_owners),
        "rdap_variable_address_carries_rom_pointer_proven": False,
        "alias_examples": [address_model(a) for a in (0x00000, 0xE0000, 0xF23FF, 0xFFFFF)],
        "hidden_20bit_monitor_absence_globally_proven": False,
        "20bit_oem_rom_monitor_proven": False,
        "controller_reads": 0,
        "controller_writes": 0,
        "firmware_bytes_extracted": 0,
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out", type=Path)
    p.add_argument("--no-installer-hash", action="store_true",
                   help="Only for CI, NEVER a full provenance conclusion")
    opts = p.parse_args()
    report = audit(include_installer=not opts.no_installer_hash)
    out = json.dumps(report, sort_keys=True, indent=2) + "\n"
    if opts.out:
        opts.out.write_text(out, encoding="utf-8")
    print(out, end="")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OemAuditRejected, OSError, ValueError, ImportError) as e:
        print("OEM_SOURCE_AUDIT_REJECTED: " + str(e), file=sys.stderr)
        sys.exit(2)
