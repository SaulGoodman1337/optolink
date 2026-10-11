#!/usr/bin/env python3
"""SHA-attested offline audit for 20-bit ROM monitor candidates in VitoSoft RPCs.

This inspects HOST metadata, not a controller's executable firmware. A long
PrefixRead is not necessarily a 20-bit address; its command family, semantic
name, and exactly matching device profile are independently checked.
No live serial access or controller writes.
"""
from __future__ import annotations
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET

SOURCE_SHA256 = "2338beb0e8544b6149bc4b2433ecabd9509edcdafc2e8e91f00182eba1aff7ba"
MAX_EVENT_BYTES = 12_000_000
RX_ADDR = re.compile(r"^0[xX][0-9a-fA-F]+$")
RPC = "Remote_Procedure_Call"
ROM_TERM = re.compile(r"(?:ChecksummeROM|Firmware|Bootloader|Programmspeicher|ROM_Read|Flash_Read)", re.I)


class CatalogRejected(ValueError):
    pass


def as_prefix(value: str) -> bytes | None:
    if not value:
        return b""
    raw = value[2:] if value.lower().startswith("0x") else value
    if len(raw) % 2 or not re.fullmatch(r"[0-9a-fA-F]*", raw):
        return None
    return bytes.fromhex(raw)


def audit(data: bytes, *, sha_verified: bool = True) -> dict:
    if type(data) is not bytes or not 100 <= len(data) <= MAX_EVENT_BYTES:
        raise CatalogRejected("bounded catalog data required")
    sha = hashlib.sha256(data).hexdigest()
    if sha_verified and sha != SOURCE_SHA256:
        raise CatalogRejected("unknown VitoSoft host-catalog source revision")
    try:
        root = ET.fromstring(data)
    except ET.ParseError as exc:
        raise CatalogRejected("malformed catalog") from exc
    if root.tag != "EventTypes":
        raise CatalogRejected("unexpected catalog root")

    ids: set[str] = set()
    all_read_prefix: Counter[int] = Counter()
    rpc_read_prefix: Counter[int] = Counter()
    rpc_write_prefix: Counter[int] = Counter()
    rpc_three = []
    rpc_write_two = []
    over16 = []
    padded = []
    invalid_addr = []
    invalid_prefix = []
    read_long_by_fc: Counter[str] = Counter()
    named = []
    rpc_count = rpc_read_count = rpc_write_count = 0
    for event in root.findall("EventType"):
        row = {child.tag:(child.text or "") for child in event}
        name = row.get("ID","")
        if not name or name in ids:
            raise CatalogRejected("empty/duplicate VitoSoft event ID")
        ids.add(name)
        fc_read, fc_write = row.get("FCRead", ""), row.get("FCWrite", "")
        is_rpc = fc_read == RPC or fc_write == RPC
        addr = row.get("Address", "")
        if addr:
            if RX_ADDR.fullmatch(addr):
                integer = int(addr,16)
                if integer > 0xFFFF:
                    over16.append({"id":name,"address":addr,"value":integer})
                if len(addr.removeprefix("0x").removeprefix("0X")) > 4:
                    padded.append({"id":name,"address":addr,
                                   "numeric_value":f"0x{integer:04x}"})
            else:
                invalid_addr.append({"id":name,"address":addr})
        if is_rpc:
            rpc_count += 1
            rpc_read_count += int(fc_read == RPC)
            rpc_write_count += int(fc_write == RPC)
        for field, read_mode in (("PrefixRead",True),("PrefixWrite",False)):
            decoded = as_prefix(row.get(field,""))
            if decoded is None:
                invalid_prefix.append({"id":name,"field":field})
                continue
            if not decoded:
                continue
            if read_mode:
                all_read_prefix[len(decoded)] += 1
                if len(decoded)>=3:
                    read_long_by_fc[fc_read] += 1
            if is_rpc:
                counter = rpc_read_prefix if read_mode else rpc_write_prefix
                counter[len(decoded)] += 1
                if read_mode and len(decoded)==3:
                    rpc_three.append({"id":name,"address":addr,
                                      "prefix_read_hex":decoded.hex(),
                                      "fc_read":fc_read})
                if not read_mode and len(decoded)==2:
                    rpc_write_two.append({"id":name,"address":addr,
                                          "prefix_write_hex":decoded.hex(),
                                          "fc_write":fc_write})
        if ROM_TERM.search(name):
            named.append({"id":name,"address":addr,"fc_read":fc_read,
                          "fc_write":fc_write,
                          "note":"name-only match, never a firmware-read proof"})
    groups = Counter((r["address"].lower(),r["fc_read"],
                      r["id"].split("~")[0].rstrip("0123456789"))
                     for r in rpc_three)
    write_groups = Counter((r["address"].lower(),r["fc_write"],
                            r["id"].split("~")[0].rstrip("0123456789"))
                           for r in rpc_write_two)
    return {
        "source_kind":"SHA_ATTESTED_VITOSOFT_GLOBAL_HOST_XML",
        "source_sha256":sha,"sha256_verified":sha_verified,
        "event_count":len(ids),
        "rpc_rows":rpc_count,"rpc_read_rows":rpc_read_count,
        "rpc_write_rows":rpc_write_count,
        "rpc_read_prefix_bytes":dict(sorted(rpc_read_prefix.items())),
        "rpc_write_prefix_bytes":dict(sorted(rpc_write_prefix.items())),
        "global_read_prefix_bytes":dict(sorted(all_read_prefix.items())),
        "global_read_prefix_at_least_3_by_fc":dict(sorted(read_long_by_fc.items())),
        "rpc_three_byte_prefix_read_count":len(rpc_three),
        "rpc_three_byte_groups":[{"address":addr,"fc":fc,
                                  "id_base":base,"rows":n}
                                 for (addr,fc,base),n in sorted(groups.items())],
        "rpc_three_byte_examples":rpc_three[:5],
        "rpc_two_byte_prefix_write_count":len(rpc_write_two),
        "rpc_two_byte_write_groups":[{"address":a,"fc":fc,"id_base":base,"rows":n}
                                     for (a,fc,base),n in sorted(write_groups.items())],
        "rpc_two_byte_write_examples":rpc_write_two[:3],
        "numeric_event_addresses_above_0xffff":over16,
        "hex_event_addresses_with_leading_padding":padded,
        "unparsed_address_count":len(invalid_addr),
        "unparsed_address_examples":invalid_addr[:8],
        "malformed_prefix_count":len(invalid_prefix),
        "malformed_prefix_examples":invalid_prefix[:8],
        "rom_or_firmware_name_matches":named,
        "any_20bit_rom_memory_service_proven":False,
        "any_unknown_firmware_monitor_opcode_tested":False,
        "live_controller_io":False,
    }


def join_target_profile(global_report: dict, profile: dict) -> dict:
    if (not global_report.get("sha256_verified")
        or not profile.get("sha256_pinned")
        or profile.get("source_kind") != "VITOSOFT_HOST_XML_STATIC_ONLY"
        or profile.get("device") != "VDensHO1"
        or profile.get("device_id") != "20C2"
        or profile.get("target_datapoint_type") != 60
        or profile.get("source_sha256",{}).get("event")
           != global_report.get("source_sha256")):
        raise CatalogRejected("exact controller host profile not provenance-verified")
    entries = profile["rpcs_named"]
    if len(entries)!=profile["rpcs_in_device_profile"]:
        raise CatalogRejected("truncated exact profile RPC names")
    if any(not RX_ADDR.fullmatch(x["address"]) for x in entries):
        raise CatalogRejected("unparsable device RPC address")
    output = dict(global_report)
    addresses = sorted({f"0x{int(x['address'],16):04x}" for x in entries})
    output["exact_target_profile"] = {
        "device":"VDensHO1 / 20C2 / SW0103",
        "event_count":profile["matched_profile_descriptors"],
        "rpc_rows":len(entries),"rpc_addresses":addresses,
        "mbus_a095_membership":0xA095 in {int(x["address"],16) for x in entries},
        "any_rom_copy_monitor_label":any(
            re.search(r"(?:ROM_READ|FLASH_READ|COPY_ROM|MONITOR|BOOTLOADER)",x["id"],re.I)
            for x in entries),
        "can_call_global_rpc_on_local_20c2_based_on_catalog":False,
    }
    return output


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("events",type=Path)
    parser.add_argument("--vdens-summary",type=Path)
    parser.add_argument("--output",type=Path)
    args = parser.parse_args()
    if args.events.is_symlink() or args.events.stat().st_size>MAX_EVENT_BYTES:
        parser.error("bounded regular event catalog required")
    report=audit(args.events.read_bytes())
    if args.vdens_summary:
        profile=json.loads(args.vdens_summary.read_text())
        report=join_target_profile(report,profile)
    serialized=json.dumps(report,sort_keys=True,indent=2)+"\n"
    if args.output:
        args.output.write_text(serialized)
    print(serialized)


if __name__ == "__main__":
    main()
