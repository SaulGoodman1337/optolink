#!/usr/bin/env python3
"""Extract device-specific low-level Vitosoft event metadata.

Validated against Vitosoft DataPointDefinitionVersion 0.0.26.4683.

Expected input files:
  DPDefinitions.xml
  ecnEventType.xml

Optional:
  Textresource_de.xml

Outputs:
  <device>-lowlevel-events.csv
  <device>-kbus-events.csv
  <device>-extract-summary.json

With --include-global-wilo:
  virtual-wilo-events.csv

The parser intentionally performs multiple streaming passes over
DPDefinitions.xml. The file is ~186 MB in the validated data set and its
records live inside a Microsoft DataSet/diffgram namespace.
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path
import xml.etree.ElementTree as ET


DP_NS = "http://tempuri.org/ECNDataSet.xsd"

FIELDS = [
    "event_id",
    "name",
    "name_de",
    "description",
    "description_de",
    "token",
    "event_type",
    "address",
    "parameter",
    "fc_read",
    "fc_write",
    "prefix_read",
    "prefix_write",
    "block_length",
    "byte_position",
    "byte_length",
    "bit_position",
    "bit_length",
    "data_type",
    "unit",
    "conversion",
    "conversion_factor",
    "conversion_offset",
    "access_mode",
    "value_list",
    "option_list",
    "mapping_type",
]

WILO_FIELDS = FIELDS + ["devices"]


def local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def children(element: ET.Element) -> dict[str, str]:
    return {local(child.tag): child.text or "" for child in element}


def iter_records(path: Path, record_name: str):
    """Yield rows for one DPDefinitions record type without clearing children early."""
    wanted = f"{{{DP_NS}}}{record_name}"
    schema_ns = "{http://www.w3.org/2001/XMLSchema}"
    for _event, elem in ET.iterparse(path, events=("end",)):
        if elem.tag == wanted:
            yield children(elem)
            elem.clear()
        elif isinstance(elem.tag, str) and elem.tag.startswith(schema_ns):
            elem.clear()


def find_device_id(dp_path: Path, token: str) -> int:
    for row in iter_records(dp_path, "ecnDatapointType"):
        if row.get("Address") == token:
            return int(row["Id"])
    raise SystemExit(f"device token not found in DPDefinitions.xml: {token}")


def load_device_event_ids(dp_path: Path, device_id: int) -> set[int]:
    result: set[int] = set()
    for row in iter_records(dp_path, "ecnDataPointTypeEventTypeLink"):
        try:
            if int(row.get("DataPointTypeId", "-1")) == device_id:
                result.add(int(row["EventTypeId"]))
        except (KeyError, ValueError):
            pass
    return result


def load_device_events(dp_path: Path, event_ids: set[int]) -> dict[int, dict[str, str]]:
    result: dict[int, dict[str, str]] = {}
    for row in iter_records(dp_path, "ecnEventType"):
        try:
            event_id = int(row.get("Id", "-1"))
        except ValueError:
            continue
        if event_id in event_ids:
            result[event_id] = row
    return result


def load_events_by_tokens(
    dp_path: Path, tokens: set[str]
) -> dict[int, dict[str, str]]:
    result: dict[int, dict[str, str]] = {}
    if not tokens:
        return result
    for row in iter_records(dp_path, "ecnEventType"):
        if row.get("Address", "") not in tokens:
            continue
        try:
            event_id = int(row.get("Id", "-1"))
        except ValueError:
            continue
        result[event_id] = row
    return result


def load_event_device_ids(
    dp_path: Path, event_ids: set[int]
) -> dict[int, set[int]]:
    result = {event_id: set() for event_id in event_ids}
    if not event_ids:
        return result
    for row in iter_records(dp_path, "ecnDataPointTypeEventTypeLink"):
        try:
            event_id = int(row.get("EventTypeId", "-1"))
            device_id = int(row.get("DataPointTypeId", "-1"))
        except ValueError:
            continue
        if event_id in result:
            result[event_id].add(device_id)
    return result


def load_device_tokens(
    dp_path: Path, device_ids: set[int]
) -> dict[int, str]:
    result: dict[int, str] = {}
    if not device_ids:
        return result
    for row in iter_records(dp_path, "ecnDatapointType"):
        try:
            device_id = int(row.get("Id", "-1"))
        except ValueError:
            continue
        if device_id in device_ids:
            result[device_id] = row.get("Address", "")
    return result


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


def normalized_row(
    event_id: int,
    event: dict[str, str],
    access: dict[str, dict[str, str]],
) -> dict[str, str | int]:
    token = event.get("Address", "")
    low = access.get(token, {})
    return {
        "event_id": event_id,
        "name": event.get("Name", ""),
        "name_de": "",
        "description": event.get("Description", ""),
        "description_de": "",
        "token": token,
        "event_type": event.get("Type", ""),
        "address": low.get("Address", ""),
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
        "data_type": low.get("DataType", low.get("SDKDataType", "")),
        "unit": low.get("Unit", ""),
        "conversion": low.get("Conversion", ""),
        "conversion_factor": low.get("ConversionFactor", ""),
        "conversion_offset": low.get("ConversionOffset", ""),
        "access_mode": low.get("AccessMode", ""),
        "value_list": low.get("ValueList", ""),
        "option_list": low.get("OptionList", ""),
        "mapping_type": low.get("MappingType", ""),
    }


def is_kbus(row: dict[str, object]) -> bool:
    for key in ("fc_read", "fc_write"):
        value = str(row.get(key, "")).upper()
        if value.startswith("KBUS_") or value.startswith("KMBUS_"):
            return True
    return False


def is_virtual_wilo(row: dict[str, object]) -> bool:
    return (
        str(row.get("fc_read", "")) == "Virtual_WILO_READ"
        or str(row.get("fc_write", "")) == "Virtual_WILO_WRITE"
    )


def write_csv(
    path: Path,
    rows: list[dict[str, object]],
    fieldnames: list[str] = FIELDS,
) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", required=True, type=Path)
    parser.add_argument("--device", default="VDensHO1")
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument(
        "--include-global-wilo",
        action="store_true",
        help=(
            "also inventory every global ecnEventType entry using "
            "Virtual_WILO_READ/Virtual_WILO_WRITE and map it to device types"
        ),
    )
    args = parser.parse_args()

    dp_path = args.data_dir / "DPDefinitions.xml"
    event_path = args.data_dir / "ecnEventType.xml"
    text_path = args.data_dir / "Textresource_de.xml"

    for required in (dp_path, event_path):
        if not required.exists():
            raise SystemExit(f"missing {required}")

    device_id = find_device_id(dp_path, args.device)
    event_ids = load_device_event_ids(dp_path, device_id)
    events = load_device_events(dp_path, event_ids)
    access = load_access(event_path)

    rows = [
        normalized_row(event_id, events[event_id], access)
        for event_id in sorted(event_ids)
        if event_id in events
    ]

    labels: set[str] = set()
    for row in rows:
        for key in ("name", "description"):
            value = str(row[key])
            if value.startswith("@@"):
                labels.add(value[2:])
    translations = load_translations(text_path, labels)
    for row in rows:
        row["name_de"] = translated(str(row["name"]), translations)
        row["description_de"] = translated(str(row["description"]), translations)

    kbus_rows = [row for row in rows if is_kbus(row)]
    device_wilo_rows = [row for row in rows if is_virtual_wilo(row)]

    args.out_dir.mkdir(parents=True, exist_ok=True)
    stem = args.device.lower()
    write_csv(args.out_dir / f"{stem}-lowlevel-events.csv", rows)
    write_csv(args.out_dir / f"{stem}-kbus-events.csv", kbus_rows)

    global_wilo_rows: list[dict[str, object]] = []
    if args.include_global_wilo:
        wilo_tokens = {
            token
            for token, low in access.items()
            if low.get("FCRead", "") == "Virtual_WILO_READ"
            or low.get("FCWrite", "") == "Virtual_WILO_WRITE"
        }
        wilo_events = load_events_by_tokens(dp_path, wilo_tokens)
        event_device_ids = load_event_device_ids(dp_path, set(wilo_events))
        all_device_ids = {
            device_id
            for device_ids in event_device_ids.values()
            for device_id in device_ids
        }
        device_tokens = load_device_tokens(dp_path, all_device_ids)

        global_wilo_rows = [
            {
                **normalized_row(event_id, wilo_events[event_id], access),
                "devices": ";".join(
                    sorted(
                        device_tokens.get(device_id, str(device_id))
                        for device_id in event_device_ids.get(event_id, set())
                    )
                ),
            }
            for event_id in sorted(wilo_events)
        ]

        wilo_labels: set[str] = set()
        for row in global_wilo_rows:
            for key in ("name", "description"):
                value = str(row[key])
                if value.startswith("@@"):
                    wilo_labels.add(value[2:])
        wilo_translations = load_translations(text_path, wilo_labels)
        for row in global_wilo_rows:
            row["name_de"] = translated(str(row["name"]), wilo_translations)
            row["description_de"] = translated(
                str(row["description"]), wilo_translations
            )

        write_csv(
            args.out_dir / "virtual-wilo-events.csv",
            global_wilo_rows,
            WILO_FIELDS,
        )

    missing_access = sum(
        1 for row in rows if not row["fc_read"] and not row["fc_write"]
    )
    summary = {
        "device": args.device,
        "datapoint_type_id": device_id,
        "event_count": len(rows),
        "access_missing": missing_access,
        "kbus_event_count": len(kbus_rows),
        "virtual_wilo_event_count": len(device_wilo_rows),
        "fc_read_counts": dict(Counter(str(row["fc_read"] or "<blank>") for row in rows)),
        "fc_write_counts": dict(Counter(str(row["fc_write"] or "<blank>") for row in rows)),
    }
    if args.include_global_wilo:
        summary["global_virtual_wilo_event_count"] = len(global_wilo_rows)
        summary["global_virtual_wilo_read_count"] = sum(
            1
            for row in global_wilo_rows
            if row["fc_read"] == "Virtual_WILO_READ"
        )
        summary["global_virtual_wilo_write_count"] = sum(
            1
            for row in global_wilo_rows
            if row["fc_write"] == "Virtual_WILO_WRITE"
        )
        summary["global_virtual_wilo_devices"] = sorted(
            {
                device
                for row in global_wilo_rows
                for device in str(row["devices"]).split(";")
                if device
            }
        )
    (args.out_dir / f"{stem}-extract-summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
