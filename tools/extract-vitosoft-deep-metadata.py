#!/usr/bin/env python3
"""Build a reproducible Vitosoft metadata research bundle.

Target use case:
- exact device context (default: VDensHO1 / 20C2)
- all linked event metadata and low-level access definitions
- global protocol-function inventory
- global hidden/related events selected by research terms
- global KBUS/KMBUS access inventory
- device mappings for related events
- raw JSONL preservation of the selected metadata rows

This tool never talks to the heating controller and never modifies Vitosoft.
It only reads Vitosoft metadata files.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
import xml.etree.ElementTree as ET


DP_NS = "http://tempuri.org/ECNDataSet.xsd"

DEFAULT_TERMS = [
    # Exact device / protocol
    "VDensHO1", "20C2", "Optolink", "P300", "VS2",
    "KMBUS", "KM-BUS", "KM Bus", "KBUS", "LON",
    "Virtual_WILO", "WILO", "PLR",
    "EEPROM", "XRAM", "RAM_READ", "Remote_Procedure_Call",
    "MEMBERLIST", "MemberList", "sysblock",
    # Pump / hydraulics
    "Pumpe", "Pump", "IntPumpe", "PumpeIntern", "InternePumpe",
    "DrehzahlIntPumpe", "InternePumpeDrehzahl", "InternePumpeDrehzahl_res",
    "DigitalAusgang_InternePumpe", "SWIndex_IntPumpe", "KM_Error_PumpeIntern",
    "K30_KennungIntPumpe", "K30_KennungIntPumpeKM",
    "Grundfos", "UPM3", "G-HE", "GHE",
    "Heizkreispumpe", "Umschaltventil", "Ventil", "Hydraulik",
    # Burner / combustion / fan
    "Brenner", "Burner", "Flamme", "Flame", "Ionisation", "Ionization",
    "Geblaese", "Gebläse", "Fan", "Gas", "Zuendung", "Zündung", "Ignition",
    "Stabilisierung", "Stabilization", "Modulation",
    # Coding plug / service / firmware
    "Codierstecker", "Kodierstecker", "GWG", "CodingPlug", "Coding plug",
    "Firmware", "Bootrom", "Bootloader", "Flash", "Programming",
    "Software-Index", "Software Index", "SWIndex",
    "Aktorentest", "Actuator", "Service",
]

DEFAULT_ADDRESSES = [
    "0x0A35", "0x0A3C", "0x0A4C", "0x0A50", "0x0A54",
    "0x1010", "0x1030", "0x1040", "0x1070",
    "0x27E5", "0x27E6", "0x27E7", "0x27E8", "0x27E9",
    "0x5556", "0x55E0", "0x5730", "0x5731",
    "0x7500", "0x7660", "0x7663",
    "0x7751", "0x778A", "0x778B", "0x778E",
    "0xA152", "0xA395", "0xA0C2",
]

CORE_FIELDS = [
    "event_id", "name", "name_de", "name_en",
    "description", "description_de", "description_en",
    "token", "event_type",
    "address", "parameter", "fc_read", "fc_write",
    "prefix_read", "prefix_write", "block_length",
    "byte_position", "byte_length", "bit_position", "bit_length",
    "data_type", "sdk_data_type", "unit", "conversion",
    "conversion_factor", "conversion_offset", "access_mode",
    "value_list", "option_list", "mapping_type", "devices",
]


def local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def children(element: ET.Element) -> dict[str, str]:
    return {local(child.tag): child.text or "" for child in element}


def iter_records(path: Path, record_name: str):
    wanted = f"{{{DP_NS}}}{record_name}"
    schema_ns = "{http://www.w3.org/2001/XMLSchema}"
    for _event, elem in ET.iterparse(path, events=("end",)):
        if elem.tag == wanted:
            yield children(elem)
            elem.clear()
        elif isinstance(elem.tag, str) and elem.tag.startswith(schema_ns):
            elem.clear()


def load_access(path: Path) -> dict[str, dict[str, str]]:
    result: dict[str, dict[str, str]] = {}
    for _event, elem in ET.iterparse(path, events=("end",)):
        if local(elem.tag) != "EventType":
            continue
        row = children(elem)
        row_id = row.get("ID")
        if row_id:
            result[row_id] = row
        elem.clear()
    return result


def load_translations(path: Path | None, labels: set[str]) -> dict[str, str]:
    if path is None or not path.exists() or not labels:
        return {}
    result: dict[str, str] = {}
    for _event, elem in ET.iterparse(path, events=("end",)):
        label = elem.attrib.get("Label")
        if label in labels:
            result[label] = elem.attrib.get("Value", "")
        elem.clear()
    return result


def translated(value: str, translations: dict[str, str]) -> str:
    if value.startswith("@@"):
        return translations.get(value[2:], "")
    return value


def write_csv(path: Path, rows: list[dict[str, object]], fields: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_jsonl(path: Path, rows) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def canonical_address(value: str) -> str:
    value = (value or "").strip()
    if not value:
        return ""
    try:
        if value.lower().startswith("0x"):
            return f"0x{int(value, 16):04X}"
        if re.fullmatch(r"[0-9A-Fa-f]{1,4}", value):
            return f"0x{int(value, 16):04X}"
    except ValueError:
        pass
    return value


def normalized_row(
    event_id: int,
    event: dict[str, str],
    access: dict[str, dict[str, str]],
    devices: list[str] | None = None,
) -> dict[str, object]:
    token = event.get("Address", "")
    low = access.get(token, {})
    return {
        "event_id": event_id,
        "name": event.get("Name", ""),
        "name_de": "",
        "name_en": "",
        "description": event.get("Description", ""),
        "description_de": "",
        "description_en": "",
        "token": token,
        "event_type": event.get("Type", ""),
        "address": canonical_address(low.get("Address", "")),
        "parameter": low.get("Parameter", ""),
        "fc_read": low.get("FCRead", ""),
        "fc_write": low.get("FCWrite", ""),
        "prefix_read": low.get("PrefixRead", ""),
        "prefix_write": low.get("PrefixWrite", ""),
        "block_length": low.get("BlockLength", ""),
        "byte_position": low.get("BytePosition", ""),
        "byte_length": low.get("ByteLength", ""),
        "bit_position": low.get("BitPosition", ""),
        "bit_length": low.get("BitLength", ""),
        "data_type": low.get("DataType", ""),
        "sdk_data_type": low.get("SDKDataType", ""),
        "unit": low.get("Unit", ""),
        "conversion": low.get("Conversion", ""),
        "conversion_factor": low.get("ConversionFactor", ""),
        "conversion_offset": low.get("ConversionOffset", ""),
        "access_mode": low.get("AccessMode", ""),
        "value_list": low.get("ValueList", ""),
        "option_list": low.get("OptionList", ""),
        "mapping_type": low.get("MappingType", ""),
        "devices": ";".join(sorted(devices or [])),
    }


def row_haystack(event: dict[str, str], low: dict[str, str]) -> str:
    return "\n".join([*(event.values()), *(low.values())]).lower()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dp-definitions", required=True, type=Path)
    parser.add_argument("--event-types", required=True, type=Path)
    parser.add_argument("--textresource-de", type=Path)
    parser.add_argument("--textresource-en", type=Path)
    parser.add_argument("--device", default="VDensHO1")
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--term", action="append", default=[])
    parser.add_argument("--address", action="append", default=[])
    args = parser.parse_args()

    for required in (args.dp_definitions, args.event_types):
        if not required.exists():
            raise SystemExit(f"missing input: {required}")

    args.out_dir.mkdir(parents=True, exist_ok=True)

    terms = list(dict.fromkeys(DEFAULT_TERMS + args.term))
    addresses = {
        canonical_address(x)
        for x in (DEFAULT_ADDRESSES + args.address)
        if canonical_address(x)
    }
    term_lc = [x.lower() for x in terms]

    print("Loading low-level Vitosoft access definitions...")
    access = load_access(args.event_types)

    # Preserve all low-level access definitions: this is the protocol vocabulary.
    access_rows = []
    for token, row in sorted(access.items()):
        access_rows.append({"token": token, **row})
    all_access_fields = sorted({k for row in access_rows for k in row})
    write_csv(args.out_dir / "all-lowlevel-access.csv", access_rows, all_access_fields)
    write_jsonl(args.out_dir / "all-lowlevel-access.jsonl", access_rows)

    print("Loading Vitosoft device types...")
    device_tokens: dict[int, str] = {}
    device_names: dict[int, str] = {}
    target_device_id: int | None = None
    for row in iter_records(args.dp_definitions, "ecnDatapointType"):
        try:
            did = int(row.get("Id", "-1"))
        except ValueError:
            continue
        token = row.get("Address", "")
        device_tokens[did] = token
        device_names[did] = row.get("Name", "")
        if token == args.device:
            target_device_id = did

    if target_device_id is None:
        raise SystemExit(f"device token not found: {args.device}")

    device_rows = [
        {"device_id": did, "token": device_tokens.get(did, ""), "name": device_names.get(did, "")}
        for did in sorted(device_tokens)
    ]
    write_csv(args.out_dir / "device-types.csv", device_rows, ["device_id", "token", "name"])

    print(f"Target device {args.device}: datapoint type ID {target_device_id}")

    print("Loading target-device event links...")
    target_event_ids: set[int] = set()
    for row in iter_records(args.dp_definitions, "ecnDataPointTypeEventTypeLink"):
        try:
            if int(row.get("DataPointTypeId", "-1")) == target_device_id:
                target_event_ids.add(int(row["EventTypeId"]))
        except (KeyError, ValueError):
            continue

    print(f"Target links: {len(target_event_ids)} events")

    print("Loading global event definitions and selecting research-interest events...")
    all_events: dict[int, dict[str, str]] = {}
    target_events: dict[int, dict[str, str]] = {}
    interest_ids: set[int] = set()
    kbus_ids: set[int] = set()
    target_addresses: set[str] = set()

    # First pass: keep target and interest events. Keeping all_events enables
    # shared-address discovery without another 186 MB event pass.
    for row in iter_records(args.dp_definitions, "ecnEventType"):
        try:
            eid = int(row.get("Id", "-1"))
        except ValueError:
            continue
        token = row.get("Address", "")
        low = access.get(token, {})
        all_events[eid] = row

        if eid in target_event_ids:
            target_events[eid] = row
            addr = canonical_address(low.get("Address", ""))
            if addr:
                target_addresses.add(addr)

        fc_values = (low.get("FCRead", ""), low.get("FCWrite", ""))
        if any((fc or "").upper().startswith(("KBUS_", "KMBUS_")) for fc in fc_values):
            kbus_ids.add(eid)

        hay = row_haystack(row, low)
        addr = canonical_address(low.get("Address", ""))
        if addr in addresses or any(term in hay for term in term_lc):
            interest_ids.add(eid)

    shared_address_ids: set[int] = set()
    for eid, event in all_events.items():
        low = access.get(event.get("Address", ""), {})
        if canonical_address(low.get("Address", "")) in target_addresses:
            shared_address_ids.add(eid)

    selected_for_device_map = target_event_ids | interest_ids | kbus_ids | shared_address_ids

    print("Resolving device mappings for selected events...")
    event_devices: dict[int, set[int]] = defaultdict(set)
    for row in iter_records(args.dp_definitions, "ecnDataPointTypeEventTypeLink"):
        try:
            eid = int(row.get("EventTypeId", "-1"))
            did = int(row.get("DataPointTypeId", "-1"))
        except ValueError:
            continue
        if eid in selected_for_device_map:
            event_devices[eid].add(did)

    def device_labels(eid: int) -> list[str]:
        return [
            device_tokens.get(did, str(did))
            for did in sorted(event_devices.get(eid, set()))
        ]

    target_rows = [
        normalized_row(eid, target_events[eid], access, device_labels(eid))
        for eid in sorted(target_events)
    ]
    interest_rows = [
        normalized_row(eid, all_events[eid], access, device_labels(eid))
        for eid in sorted(interest_ids)
        if eid in all_events
    ]
    kbus_rows = [
        normalized_row(eid, all_events[eid], access, device_labels(eid))
        for eid in sorted(kbus_ids)
        if eid in all_events
    ]
    shared_rows = [
        normalized_row(eid, all_events[eid], access, device_labels(eid))
        for eid in sorted(shared_address_ids)
        if eid in all_events
    ]

    labels: set[str] = set()
    for rows in (target_rows, interest_rows, kbus_rows, shared_rows):
        for row in rows:
            for key in ("name", "description"):
                value = str(row[key])
                if value.startswith("@@"):
                    labels.add(value[2:])

    print(f"Loading translations for {len(labels)} labels...")
    de = load_translations(args.textresource_de, labels)
    en = load_translations(args.textresource_en, labels)
    for rows in (target_rows, interest_rows, kbus_rows, shared_rows):
        for row in rows:
            row["name_de"] = translated(str(row["name"]), de)
            row["name_en"] = translated(str(row["name"]), en)
            row["description_de"] = translated(str(row["description"]), de)
            row["description_en"] = translated(str(row["description"]), en)

    write_csv(args.out_dir / f"{args.device.lower()}-all-events.csv", target_rows, CORE_FIELDS)
    write_csv(args.out_dir / "global-interest-events.csv", interest_rows, CORE_FIELDS)
    write_csv(args.out_dir / "global-kbus-kmbus-events.csv", kbus_rows, CORE_FIELDS)
    write_csv(args.out_dir / "shared-address-events.csv", shared_rows, CORE_FIELDS)

    write_jsonl(
        args.out_dir / f"{args.device.lower()}-raw-events.jsonl",
        (
            {
                "event_id": eid,
                "event": target_events[eid],
                "access": access.get(target_events[eid].get("Address", ""), {}),
                "devices": device_labels(eid),
            }
            for eid in sorted(target_events)
        ),
    )
    write_jsonl(
        args.out_dir / "global-interest-raw-events.jsonl",
        (
            {
                "event_id": eid,
                "event": all_events[eid],
                "access": access.get(all_events[eid].get("Address", ""), {}),
                "devices": device_labels(eid),
            }
            for eid in sorted(interest_ids)
            if eid in all_events
        ),
    )

    function_rows = []
    fc_read_counter = Counter()
    fc_write_counter = Counter()
    for token, low in access.items():
        if low.get("FCRead"):
            fc_read_counter[low["FCRead"]] += 1
        if low.get("FCWrite"):
            fc_write_counter[low["FCWrite"]] += 1

    for fc in sorted(set(fc_read_counter) | set(fc_write_counter)):
        function_rows.append({
            "function": fc,
            "read_definition_count": fc_read_counter.get(fc, 0),
            "write_definition_count": fc_write_counter.get(fc, 0),
        })
    write_csv(
        args.out_dir / "protocol-function-inventory.csv",
        function_rows,
        ["function", "read_definition_count", "write_definition_count"],
    )

    # Exact target addresses with all global aliases/siblings at the same low-level address.
    by_addr = defaultdict(list)
    for row in shared_rows:
        by_addr[str(row["address"])].append(row)
    address_summary = []
    for addr in sorted(by_addr):
        rows = by_addr[addr]
        address_summary.append({
            "address": addr,
            "event_count": len(rows),
            "event_ids": ";".join(str(x["event_id"]) for x in rows),
            "names": " | ".join(sorted({str(x["name_de"] or x["name_en"] or x["name"]) for x in rows})),
            "devices": ";".join(sorted({
                d for x in rows for d in str(x["devices"]).split(";") if d
            })),
        })
    write_csv(
        args.out_dir / "shared-address-summary.csv",
        address_summary,
        ["address", "event_count", "event_ids", "names", "devices"],
    )

    summary = {
        "device": args.device,
        "device_id": target_device_id,
        "target_event_count": len(target_rows),
        "target_address_count": len(target_addresses),
        "global_interest_event_count": len(interest_rows),
        "global_kbus_kmbus_event_count": len(kbus_rows),
        "shared_address_event_count": len(shared_rows),
        "lowlevel_access_definition_count": len(access_rows),
        "device_type_count": len(device_rows),
        "terms": terms,
        "addresses": sorted(addresses),
        "fc_read_counts": dict(Counter(str(x["fc_read"] or "<blank>") for x in target_rows)),
        "fc_write_counts": dict(Counter(str(x["fc_write"] or "<blank>") for x in target_rows)),
    }
    (args.out_dir / "deep-metadata-summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
