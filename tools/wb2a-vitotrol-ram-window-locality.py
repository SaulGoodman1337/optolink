#!/usr/bin/env python3
"""Reproduce only SRAM-neighborhood statistics from a pinned historical archive.

No serial port, network, MQTT, Optolink command, production config, or write.
Not a UART1-RX, ISR, INTB, or Vitotrol-participant acceptance proof.
"""
from __future__ import annotations

import argparse
import importlib.util
import io
import json
from pathlib import Path
import stat
import sys
import tarfile

HELPER = Path(__file__).with_name("wb2a-vitotrol-optolink-rx-context.py")
spec = importlib.util.spec_from_file_location("wb2a_vitotrol_window_helper", HELPER)
if spec is None or spec.loader is None:
    raise RuntimeError("offline context helper missing")
context = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = context
spec.loader.exec_module(context)
audit = context.audit


def inspect_archived_fullram(raw: bytes) -> dict:
    """Verify exact original archive/hash/metadata before comparing 79 RAM images."""
    if type(raw) is not bytes or not 0 < len(raw) <= audit.MAX_ARCHIVE_BYTES:
        raise audit.EvidenceRejected("bounded private archive bytes required")
    baseline = audit.audit_bundle("fullram", raw)
    images = []
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:gz") as archive:
        manifest = audit._manifest(archive, "p300-fullram")
        for i in range(1, 80):
            prefix = f"snapshots/s{i:05d}"
            meta = json.loads(audit._verified(
                archive, manifest, "p300-fullram", prefix+".json", max_size=8000))
            image = audit._verified(
                archive, manifest, "p300-fullram", prefix+".bin", max_size=20480)
            if (meta.get("marker") != "COMPLETE" or meta.get("complete") is not True
                or meta.get("device_id") != "20c2"
                or meta.get("software") != "0103"
                or meta.get("bytes_stored") != 20480
                or meta.get("range_start") != "0x0400"
                or meta.get("range_last_inclusive") != "0x53ff"
                or meta.get("direction") not in ("ascending","descending")
                or len(image) != 20480):
                raise audit.EvidenceRejected("invalid historical fullram image metadata")
            images.append(image)
    return {
        "source_type": "PINNED_HISTORICAL_P300_FULLRAM_20C2_0103",
        "archive_sha256": baseline["archive_sha256"],
        "fullram_images_verified": len(images),
        "read_only": True,
        "live_controller_io": False,
        "vitotrol_accepted_by_controller": False,
        "locality": context.window_locality(images),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", required=True,
                        help="locally accessible pinned historical fullram tar.gz")
    args = parser.parse_args()
    path = Path(args.archive)
    if (path.suffixes[-2:] != [".tar", ".gz"] or path.is_symlink()
        or not stat.S_ISREG(path.stat().st_mode)
        or path.stat().st_size > audit.MAX_ARCHIVE_BYTES):
        raise audit.EvidenceRejected("regular, bounded local .tar.gz file required")
    raw = path.read_bytes()
    print(json.dumps(inspect_archived_fullram(raw), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
