#!/usr/bin/env python3
"""Offline byte-exact verification of two guarded original live GWG windows.

Checks immutability of the ORIGINAL live 20C2 JSON captures and interlocks
without opening serial, importing pyserial or issuing MCU commands.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location(
    "wb2a_original_kw2_first_window_for_phase2_audit",
    HERE/"wb2a-v200kw2-gwg-live-original-audit.py")
if not spec or not spec.loader:raise RuntimeError("first source verifier missing")
first=importlib.util.module_from_spec(spec);sys.modules[spec.name]=first
spec.loader.exec_module(first)
FOLLOWUP_PATH="/tmp/wb2a-v200kw2-gwg-followup-20261012.json"
FOLLOWUP_SHA="a9b6e5c846aacc99bc5183ffde922ef9891117e97872a278c35cec48520ad95d"
ROWS={
 "kw_baseline_before":("01f700f804",["20c20003"]),
 "gwg_c7_f8_8bytes":("01c7f80804",["20c2000300000103"]),
 "gwg_c7_f9_3bytes":("01c7f90304",["c20003"]),
 "gwg_cb_f8_1byte":("01cbf80104",["",""]),
 "gwg_c5_f8_1byte":("01c5f80104",["",""]),
 "kw_baseline_after":("01f700f804",["20c20003"]),
}

class Refused(ValueError):pass


def audit(original_first:bytes,followup:bytes):
    pre=first.audit(original_first)
    if (type(followup) is not bytes or len(followup)>32000
        or hashlib.sha256(followup).hexdigest()!=FOLLOWUP_SHA):
        raise Refused("not SHA-attested second real 2026-10-12 source")
    report=json.loads(followup)
    if (report.get("mode")!="LEGACY_GWG_F8_ADDRESS_FOLLOWUP_READONLY"
        or report.get("prerequisite_proven_first_GWG_C7_sha256")!=first.SHA
        or report.get("device")!="WB2A VDensHO1 20C2/0103"
        or report.get("total_read_requests")!=8
        or report.get("controller_writes")!=0
        or report.get("controller_eeprom_writes")!=0
        or report.get("gwg_c7_8byte_id_matches_vs1") is not True
        or report.get("gwg_c7_f9_3byte_id_matches_vs1") is not True
        or report.get("gwg_cb_c5_proven_20bit_rom_service") is not False
        or report.get("program_rom_bytes_recovered") is not False
        or report.get("independent_restoration_of_original_owner_prearmed") is not True):
        raise Refused("second capture metadata does not match original interlocks")
    rows=report.get("records")
    if not isinstance(rows,list) or len(rows)!=8:
        raise Refused("missing complete second original record series")
    expected=[(name,wire,rx,j) for name,(wire,answers) in ROWS.items()
              for j,rx in enumerate(answers)]
    summary=[]
    for record,(name,wire,answer,repeat) in zip(rows,expected):
        if (record.get("case")!=name or record.get("wire")!=wire
            or record.get("reply")!=answer or record.get("rep")!=repeat
            or record.get("synced") is not True or record.get("sync")!="05"
            or record.get("bytes_received")!=len(bytes.fromhex(answer))
            or record.get("expected_bytes")!=(
                {"gwg_c7_f8_8bytes":8,"gwg_c7_f9_3bytes":3}.get(
                name,4 if name.startswith("kw_baseline") else 1))):
            raise Refused("a second real 20C2 frame was altered or misinterpreted")
        summary.append({"source":"2026-10-12-second-window",
                        "case":name,"tx":wire,"rx":answer})
    if (report.get("gwg_cb_f8_responses")!=["",""]
        or report.get("gwg_c5_f8_responses")!=["",""]):
        raise Refused("unexpected physical/XRAM response transcription")
    return {
        "mode":"OFFLINE_SHA_PINNED_DUAL_GWG_V200KW2_TO_WB2A_WIRE_AUDIT",
        "first_original_sha256":first.SHA,
        "second_original_sha256":FOLLOWUP_SHA,
        "original_authenticated_controller_read_requests":16,
        "former_2010_C7_exact_bytes_reproduced_in_WB2A":True,
        "C7_at_F8_8_bytes_matches_KW_VIRTUAL_READ":True,
        "C7_at_F9_3_bytes_matches_KW_VIRTUAL_READ":True,
        "C7_8bit_virtual_address_space_overlaps_known_KW_00F8":True,
        "legacy_CB_no_response_6F":True,
        "legacy_C5_no_response_6F":True,
        "legacy_CB_no_response_F8":True,
        "legacy_C5_no_response_F8":True,
        "unsupported_C5_CB_globally_proven":False,
        "existing_20bit_ROM_monitor_read_proven":False,
        "KW2_2010_programROM_dump_recovered":False,
        "ROM_dump_obtained":False,
        "controller_writes_in_sources":0,
        "new_controller_io_for_offline_audit":0,
        "verified_second_controller_record_sequence":summary,
        "first_record_count":pre["real_controller_synchronized_raw_read_telegrams"],
    }


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("first_original",type=Path)
    p.add_argument("second_original",type=Path)
    p.add_argument("--out",type=Path)
    a=p.parse_args()
    if (str(a.first_original)!=first.ORIGINAL or
        str(a.second_original)!=FOLLOWUP_PATH):
        p.error("only the two exact private original captures")
    for fp in (a.first_original,a.second_original):
        if fp.is_symlink() or not fp.is_file() or fp.stat().st_size>32000:
            p.error("missing or unexpected immutable real source")
    r=audit(a.first_original.read_bytes(),a.second_original.read_bytes())
    content=json.dumps(r,sort_keys=True,indent=2)+"\n"
    if a.out:a.out.write_text(content)
    print(content)


if __name__=="__main__":main()
