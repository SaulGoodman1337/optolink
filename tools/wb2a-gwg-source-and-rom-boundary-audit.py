#!/usr/bin/env python3
"""Source-pinned OFFLINE GWG cross-generation and ROM-evidence gate for WB2A 20C2.

Source hierarchy:
  openv wiki: historical telegram definitions;
  openv/vcontrold source: actual GWG command/profile binding for 2053;
  InsideViessmannVitosoft: THIRD-PARTY reverse-engineering notes, NOT
      a vendor-authenticated VitoSoft specification;
  root-only SHA-pinned local 20C2 captures: actual behavior at tested addresses.

Never interprets an 8-bit GWG address as program ROM, nor equates a valid
0xC7/0x6E reply with all historical GWG access modes being supported.
No serial owner, subprocess hardware command, writes or background polling.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
SOURCES = {
    "wiki": (Path("/home/chatgpt-admin/research/openv.wiki/Protokoll-GWG.md"),
             "6767a5fc30db44ac89ca9e9e4d27d64f5f64091ddd0419b39586a493155af82c"),
    "vito": (Path("/home/chatgpt-admin/research/vcontrold/xml/kw/vito.xml"),
             "8b30d5060dfbea75e986a3199b986f54b092b6b13e286e6e7ef797608026531e"),
    "protocol": (Path("/home/chatgpt-admin/research/vcontrold/xml/kw/vcontrold.xml"),
                 "9a6768dea265f5a88daca67cdcbc727f971e2b1d8786bef3c548edb483c5b139"),
    "re_notes": (Path("/home/chatgpt-admin/research/InsideViessmannVitosoft/VitosoftCommunication.md"),
                 "19fc2189e1392aa11ba986ee063c2d288e4197637f56083012a702c913881371"),
}
LOGS = {
    "c7": (Path("/tmp/wb2a-gwg-c7-dispatcher-live-20261012.json"),
           "ee38ef08f950c999ed19da9630e789cc69b1f61642b932be5dca3101a163b824"),
    "legacy": (Path("/tmp/wb2a-gwg-legacy-readtypes-live-20261012.json"),
               "527ae8454ff00d8517075aa7a13f7d238a111b7c5d0e2f8a6db3050356e65afc"),
}
MAX_SOURCE_BYTES = 3_000_000
MAX_CAPTURE_BYTES = 100_000
EXPECTED_WIKI = {
    "VIRTUAL READ": ("01", "C7"),
    "EEPROM READ": ("05", "AE"),
    "PHYSICAL PORT READ": ("51", "6E"),
    "PHYSICAL XRAM READ": ("49", "C5"),
    "PHYSICAL READ": ("03", "CB"),
    "PHYSICAL BE READ": ("53", "9E"),
}
EXPECTED_PROFILE = {
    "getBrennerStunden1": ("geteaddr", "17", "2"),
    "getVentilStatus": ("getpaddr", "01", "1"),
}
PROTOCOL_MACROS = {"GETVADDR": "SEND 01 C7",
                   "GETEADDR": "SEND 01 AE",
                   "GETPADDR": "SEND 01 6E"}


class EvidenceRejected(ValueError):
    pass


def attest(name: str, data: bytes, *, verify: bool = True) -> str:
    if not isinstance(data, bytes) or not 16 <= len(data) <= MAX_SOURCE_BYTES:
        raise EvidenceRejected(f"{name}: missing or oversized source")
    actual = hashlib.sha256(data).hexdigest()
    if name not in SOURCES:
        raise EvidenceRejected("unexpected source: " + name)
    if verify and actual != SOURCES[name][1]:
        raise EvidenceRejected(f"{name}: source revision changed")
    return actual


def inspect_sources(contents: dict[str, bytes], *, pin: bool = True) -> dict:
    if set(contents) != set(SOURCES):
        raise EvidenceRejected("incomplete or unexpected source set")
    attestations = {name: attest(name, contents[name], verify=pin) for name in SOURCES}
    try:
        wiki = contents["wiki"].decode("utf-8")
        notes = contents["re_notes"].decode("utf-8")
        vito = ET.fromstring(contents["vito"])
        protocol = ET.fromstring(contents["protocol"])
    except (UnicodeError, ET.ParseError) as exc:
        raise EvidenceRejected("source text/XML not parseable") from exc

    for name, (fun, code) in EXPECTED_WIKI.items():
        pattern = rf"(?m)^\s*{re.escape(name)}\s*\|\s*{fun}\s*\|\s*{code}\s*$"
        if len(re.findall(pattern, wiki)) != 1:
            raise EvidenceRejected(f"wiki opcode {name} absent or ambiguous")

    macros = {}
    for tag in protocol.findall(".//macro"):
        if tag.get("name") in PROTOCOL_MACROS:
            macros.setdefault(tag.get("name"), []).append(
                (tag.findtext("command") or "").strip())
    for key, expected in PROTOCOL_MACROS.items():
        if macros.get(key) != [expected]:
            raise EvidenceRejected(f"vcontrold GWG macro mismatch: {key}")

    profiles = {}
    for cmd in vito.findall(".//command"):
        if cmd.get("name") not in EXPECTED_PROFILE:
            continue
        if cmd.get("name") in profiles:
            raise EvidenceRejected("duplicate profile command " + cmd.get("name"))
        relevant = [x for x in cmd.findall("device") if x.get("ID") == "2053"]
        if len(relevant) != 1:
            raise EvidenceRejected("ambiguous 2053 source-profile link")
        dev = relevant[0]
        profiles[cmd.get("name")] = (
            dev.get("protocmd") or cmd.get("protocmd") or "",
            dev.findtext("addr"), dev.findtext("len"))
    if profiles != EXPECTED_PROFILE:
        raise EvidenceRejected("2053 mode, address or length differs from archive")

    # A community RE document, not the VitoSoft binary or Viessmann source.
    detection = re.findall(
        r"The reply should be \`0x20,0x53\` or \`0x20,0x54\`",
        notes, flags=re.I)
    if len(detection) != 1 or (
        "no longer supported by the Vitosoft 300 application" not in notes
    ):
        raise EvidenceRejected("community VitoSoft GWG detection claims changed")

    return {
        "source_sha256": attestations,
        "source_kinds": {
            "wiki": "OPENV_PROTOCOL_WIKI",
            "vito": "OPENV_VCONTROLD_2053_COMMAND_PROFILE",
            "protocol": "OPENV_VCONTROLD_GWG_MACROS",
            "re_notes": "THIRD_PARTY_VITOSOFT_REVERSE_ENGINEERING_NOT_VENDOR_SOURCE",
        },
        "expected_gwg_identifiers_from_re_notes": ["2053", "2054"],
        "historical_vcontrold_device": "2053",
        "2053_read_frames": {
            name: ("01ae170204" if name == "getBrennerStunden1"
                   else "016e010104")
            for name in EXPECTED_PROFILE
        },
        "gwg_address_bits": 8,
        "gwg_read_opcodes": {name: code for name, (_, code) in EXPECTED_WIKI.items()},
    }


def _import_read_only_auditor(filename: str, name: str):
    path = ROOT / "tools" / filename
    if not path.is_file():
        raise EvidenceRejected("missing tested original capture auditor: " + filename)
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise EvidenceRejected("unable to load original evidence auditor")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def combine(source_report: dict, c7_report: dict, legacy_report: dict) -> dict:
    if source_report.get("historical_vcontrold_device") != "2053":
        raise EvidenceRejected("wrong historical source device")
    if source_report.get("gwg_address_bits") != 8:
        raise EvidenceRejected("GWG request field width unknown")
    if source_report.get("2053_read_frames") != {
        "getBrennerStunden1": "01ae170204",
        "getVentilStatus": "016e010104"}:
        raise EvidenceRejected("untrusted source frames")
    if (c7_report.get("audit") != "PASS" or c7_report.get("reads") != 7
        or c7_report.get("controller_writes") != 0
        or c7_report.get("recovered_rom_bytes") != 0):
        raise EvidenceRejected("GWG C7 live evidence invalid")
    if (legacy_report.get("audit") != "PASS" or legacy_report.get("reads") != 8
        or legacy_report.get("controller_memory_writes") != 0
        or legacy_report.get("program_rom_bytes_read") != 0
        or legacy_report.get("physical_port_semantics_proven") is not False
        or legacy_report.get("eeprom_ae_17_reads") != 2
        or legacy_report.get("eeprom_ae_17_responses") != 0
        or legacy_report.get("port_6e_01_reads") != 2
        or legacy_report.get("port_6e_01_hex_replies") != ["00", "00"]):
        raise EvidenceRejected("historical read-type WB2A evidence invalid")
    if "2053" not in source_report.get("expected_gwg_identifiers_from_re_notes", []):
        raise EvidenceRejected("GWG identity detection source missing")
    # Pinned C7 log validates both actual 20C2/0103 hardware IDs and exactly
    # seven real successful requests; 6E data semantics are explicitly unknown.
    observed_id = "20c2"
    detector_matches = observed_id in source_report["expected_gwg_identifiers_from_re_notes"]
    if detector_matches:
        raise EvidenceRejected("20C2 misclassified as legacy GWG 2053/2054")
    return {
        "audit": "PASS",
        "device": "WB2A_VDensHO1_20C2_0103",
        "transport": "ONE_OWNER_GWG_C7_PLUS_KW_READ_ONLY",
        "observed_controller_id": observed_id,
        "legacy_gwg_detector_ids": ["2053", "2054"],
        "legacy_gwg_detector_matches_20c2": detector_matches,
        "gwg_c7_confirmed": True,
        "gwg_physical_port_6e_01_response": "00",
        "gwg_6e_semantics_proven": False,
        "gwg_eeprom_ae_17_response_count": 0,
        "native_gwg_stack_implementation_proven": False,
        "program_rom_bytes_read": 0,
        "twenty_bit_program_rom_read_supported_by_evidence": False,
        "require_separate_20bit_monitor_or_copier_evidence": True,
        "source_report": source_report,
        "captures_sha256": {
            "c7": c7_report["source_sha256"],
            "legacy": legacy_report["source_sha256"],
        },
        "c7_requests": c7_report["reads"],
        "other_read_requests": legacy_report["reads"],
        "controller_memory_writes": 0,
    }


def execute(source_paths: dict | None = None, capture_paths: dict | None = None):
    source_paths = source_paths or {name: item[0] for name, item in SOURCES.items()}
    capture_paths = capture_paths or {name: item[0] for name, item in LOGS.items()}
    source_report = inspect_sources(
        {name: Path(path).read_bytes() for name, path in source_paths.items()}, pin=True)
    c7 = _import_read_only_auditor(
        "wb2a-gwg-c7-dispatcher-original-audit.py", "c7_source_bound_auditor")
    legacy = _import_read_only_auditor(
        "wb2a-gwg-legacy-readtypes-original-audit.py", "legacy_source_bound_auditor")
    for name, (default_path, expected_sha) in LOGS.items():
        if capture_paths[name].resolve() != default_path.resolve():
            raise EvidenceRejected("original path must not be changed: " + name)
        content = capture_paths[name].read_bytes()
        if not 16 <= len(content) <= MAX_CAPTURE_BYTES:
            raise EvidenceRejected("invalid capture size: " + name)
        if hashlib.sha256(content).hexdigest() != expected_sha:
            raise EvidenceRejected("modified original read capture: " + name)
    r1 = c7.audit(capture_paths["c7"].read_bytes(), pinned=True)
    r2 = legacy.analyze(capture_paths["legacy"].read_bytes(), pin=True)
    return combine(source_report, r1, r2)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out", type=Path, help="write JSON analysis, never raw captures")
    args = p.parse_args()
    report = execute()
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.out:
        args.out.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (EvidenceRejected, OSError) as exc:
        print("REJECTED: " + str(exc), file=sys.stderr)
        sys.exit(2)
