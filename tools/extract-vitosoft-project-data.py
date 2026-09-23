#!/usr/bin/env python3
"""Extract device-specific low-level Vitosoft event metadata.

Expected input files:
  DPDefinitions.xml
  ecnEventType.xml
  ecnDataPointType.xml (optional for identification cross-checks)

The script keeps the original Vitosoft fields needed for Optolink/KBus research
and emits a complete device CSV plus a KBUS/KMBUS-only CSV.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import xml.etree.ElementTree as ET


FIELDS = [
    "event_id",
    "name",
    "token",
    "address",
    "parameter",
    "type",
    "fc_read",
    "fc_write",
    "prefix_read",
    "prefix_write",
    "block_length",
    "byte_length",
    "byte_position",
    "bit_length",
    "bit_position",
    "conversion",
    "conversion_factor",
    "conversion_offset",
    "unit",
    "value_list",
]


def local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def children(element: ET.Element) -> dict[str, str]:
    out: dict[str, str] = {}
    for child in element:
        out[local(child.tag)] = child.text or ""
    return out


def int_or_none(value: str):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def load_dpdefinitions(path: Path):
    devices: dict[int, dict[str, str]] = {}
    events: dict[int, dict[str, str]] = {}
    links: list[tuple[int, int]] = []

    for _event, elem in ET.iterparse(path, events=("end",)):
        tag = local(elem.tag)
        if tag == "ecnDatapointType":
            row = children(elem)
            row_id = int_or_none(row.get("Id", ""))
            if row_id is not None:
                devices[row_id] = row
        elif tag == "ecnEventType":
            row = children(elem)
            row_id = int_or_none(row.get("Id", ""))
            if row_id is not None:
                events[row_id] = row
        elif tag == "ecnDataPointTypeEventTypeLink":
            row = children(elem)
            dp_id = int_or_none(row.get("DataPointTypeId", ""))
            event_id = int_or_none(row.get("EventTypeId", ""))
            if dp_id is not None and event_id is not None:
                links.append((dp_id, event_id))
        elem.clear()

    return devices, events, links


def load_access(path: Path):
    access: dict[str, dict[str, str]] = {}
    for _event, elem in ET.iterparse(path, events=("end",)):
        if local(elem.tag) not in ("EventType", "ecnEventType"):
            elem.clear()
            continue
        row = children(elem)
        row_id = row.get("ID") or row.get("Id")
        if row_id:
            access[row_id] = row
        elem.clear()
    return access


def find_device_id(devices: dict[int, dict[str, str]], token: str) -> int:
    for row_id, row in devices.items():
        if row.get("Address") == token or row.get("Name") == token:
            return row_id
    raise SystemExit(f"device token not found in DPDefinitions.xml: {token}")


def access_for_event(event: dict[str, str], access: dict[str, dict[str, str]]):
    raw = event.get("Address", "")
    candidates = [raw]
    if "~" in raw:
        candidates.append(raw.split("~", 1)[0])
    name = event.get("Name", "")
    if name:
        candidates.append(name)

    for candidate in candidates:
        if candidate in access:
            return candidate, access[candidate]
    return (raw.split("~", 1)[0] if raw else ""), {}


def normalized_row(event_id: int, event: dict[str, str], access: dict[str, dict[str, str]]):
    token, low = access_for_event(event, access)
    raw_address = low.get("Address", "")
    if not raw_address and "~" in event.get("Address", ""):
        raw_address = event["Address"].split("~", 1)[1]

    return {
        "event_id": event_id,
        "name": event.get("Name", ""),
        "token": token,
        "address": raw_address,
        "parameter": low.get("Parameter", event.get("Parameter", "")),
        "type": event.get("Type", ""),
        "fc_read": low.get("FCRead", ""),
        "fc_write": low.get("FCWrite", ""),
        "prefix_read": low.get("PrefixRead", ""),
        "prefix_write": low.get("PrefixWrite", ""),
        "block_length": low.get("BlockLength", ""),
        "byte_length": low.get("ByteLength", ""),
        "byte_position": low.get("BytePosition", ""),
        "bit_length": low.get("BitLength", ""),
        "bit_position": low.get("BitPosition", ""),
        "conversion": low.get("Conversion", ""),
        "conversion_factor": low.get("ConversionFactor", ""),
        "conversion_offset": low.get("ConversionOffset", ""),
        "unit": low.get("Unit", ""),
        "value_list": low.get("ValueList", ""),
    }


def is_kbus(row: dict[str, object]) -> bool:
    values = (str(row.get("fc_read", "")), str(row.get("fc_write", "")))
    return any(v.startswith("KBUS_") or v.startswith("KMBUS_") for v in values)


def write_csv(path: Path, rows: list[dict[str, object]]):
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", required=True, type=Path)
    parser.add_argument("--device", default="VDensHO1")
    parser.add_argument("--out-dir", required=True, type=Path)
    args = parser.parse_args()

    dp_path = args.data_dir / "DPDefinitions.xml"
    event_path = args.data_dir / "ecnEventType.xml"
    if not dp_path.exists():
        raise SystemExit(f"missing {dp_path}")
    if not event_path.exists():
        raise SystemExit(f"missing {event_path}")

    devices, events, links = load_dpdefinitions(dp_path)
    access = load_access(event_path)
    device_id = find_device_id(devices, args.device)
    event_ids = sorted(event_id for dp_id, event_id in links if dp_id == device_id)

    rows = [
        normalized_row(event_id, events[event_id], access)
        for event_id in event_ids
        if event_id in events
    ]
    kbus_rows = [row for row in rows if is_kbus(row)]

    args.out_dir.mkdir(parents=True, exist_ok=True)
    stem = args.device.lower()
    write_csv(args.out_dir / f"{stem}-lowlevel-events.csv", rows)
    write_csv(args.out_dir / f"{stem}-kbus-events.csv", kbus_rows)

    summary = {
        "device": args.device,
        "datapoint_type_id": device_id,
        "event_count": len(rows),
        "kbus_event_count": len(kbus_rows),
        "missing_access_metadata": sum(
            1 for row in rows if not row["fc_read"] and not row["fc_write"]
        ),
    }
    (args.out_dir / f"{stem}-extract-summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
