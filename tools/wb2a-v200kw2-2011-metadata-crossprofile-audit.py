#!/usr/bin/env python3
"""Check if 2011 'V200KW2_extended' programming/ROM rows really belong to KW2.

Strictly offline, no boiler I/O. Cross-join exact signed VitoSoft device
membership instead of believing a generic XML file's misleading filename.
The 2010-2011 issue #10 is an independent human testimony, NOT byte-attested
by this script: https://github.com/openv/openv/issues/10 .
"""
from __future__ import annotations
import argparse
from collections import Counter
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import xml.etree.ElementTree as ET
import zipfile

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location(
    "wb2a_kw2_vitosoft_exact_source", HERE/"wb2a-vitotrol-vitosoft-static.py")
if spec is None or spec.loader is None:raise RuntimeError("required VitoSoft SHA verifier missing")
v=importlib.util.module_from_spec(spec)
sys.modules[spec.name]=v
spec.loader.exec_module(v)

ZIP_SHA="f800bc22537556b096afb43c199311f0bd682698e499fbe6bfbd6bfbbbfa55a3"
ARCHIVE_MEMBERS={
    "vito_V200KW2.xml":("25b248ddda3eaed8047cb07ad82ba0fbe7b67d96fffd753f1912f9d26fc0d0f5",578),
    "vito_V200KW2_extended.xml":("3caf96cef5edadfb75c87e2e4590cf99b0779f2d125cdf635ae2f51f1f9d8c53",1796),
}
KW2_TYPES={"26":"V200KW2","161":"V200KW2_4","167":"V200KW2_5","172":"V200KW2_6"}
WB2A_TYPES={"60":"VDensHO1"}
SUSPICIOUS={
    "ChecksummeROMBerechnet~0x08F0":("0x08F0","2"),
    "NRF_ChecksummeROMLinker~0x08F4":("0x08F4","2"),
    "SC100_ProgrammierstellungEin~0x0C04":("0x0C04","1"),
    "SC100_ProgrammierstellungAus~0x0C05":("0x0C05","1"),
}
ALLOWED_SUSPECT_PROFILES={
    "ChecksummeROMBerechnet~0x08F0":{"VBC550S","VBC550P","Ecotronic","Ecotronic_100"},
    "NRF_ChecksummeROMLinker~0x08F4":{"VBC550S","VBC550P","Ecotronic","Ecotronic_100"},
    "SC100_ProgrammierstellungEin~0x0C04":{"VBC550S","VBC550P"},
    "SC100_ProgrammierstellungAus~0x0C05":{"VBC550S","VBC550P"},
}


class SourceRejected(ValueError):pass


def check_zip(archive:bytes)->dict:
    if (type(archive) is not bytes or len(archive)>150000 or
        hashlib.sha256(archive).hexdigest()!=ZIP_SHA):
        raise SourceRejected("not original TerminatorIII Jan-2011 public ZIP")
    results={}
    with zipfile.ZipFile(io.BytesIO(archive)) as z:
        if set(z.namelist())!=set(ARCHIVE_MEMBERS):
            raise SourceRejected("unexpected filenames or archive entries")
        for name,(sha,count) in ARCHIVE_MEMBERS.items():
            info=z.getinfo(name)
            if info.file_size>600000:raise SourceRejected("unbounded XML archive member")
            raw=z.read(info)
            if hashlib.sha256(raw).hexdigest()!=sha:raise SourceRejected("wrong XML member")
            root=ET.fromstring(raw)
            entries=root.findall(".//datapoint")
            if len(entries)!=count:raise SourceRejected("wrong archived datapoint count")
            rows={}
            for el in entries:
                x=el.get("ID","")
                if x in (q.split("~")[0] for q in SUSPICIOUS):
                    if x in rows:raise SourceRejected("ambiguous archival datapoint")
                    rows[x]={"address":"0x"+(el.findtext("addr") or "").lower(),
                             "length":el.findtext("len")}
            results[name]={"sha256":sha,"datapoints":count,"suspected_fields":rows}
    if results["vito_V200KW2.xml"]["suspected_fields"]:
        raise SourceRejected("normal 2011 KW2 source unexpectedly contains candidates")
    expected={x.split("~")[0]:{"address":a.lower(),"length":n} for x,(a,n) in SUSPICIOUS.items()}
    if results["vito_V200KW2_extended.xml"]["suspected_fields"]!=expected:
        raise SourceRejected("archived extended XML candidate interpretation changed")
    return {
       "archive_sha256":ZIP_SHA,"original_files":results,
       "extended_is_cross_device_compilation":True,
       "filename_alone_is_a_device_support_proof":False,
    }


def compare_real_catalog(dp:bytes,event_xml:bytes)->dict:
    # Original XML hashes and size limits must be checked before parsing.
    try:
        v._hash_attest(dp,v.DP_SHA,v.MAX_DP_BYTES)
        v._hash_attest(event_xml,v.EVENT_SHA,v.MAX_EVENT_BYTES)
    except v.SourceRejected as e:
        raise SourceRejected("VitoSoft source checks failed") from e
    prof=v._rows(dp,b"ecnDatapointType")
    types={x["Id"]:x.get("Address","") for x in prof}
    for key,value in {**KW2_TYPES,**WB2A_TYPES}.items():
        if types.get(key)!=value:
            raise SourceRejected("target device-profile identity no longer valid")
    links=v._rows(dp,b"ecnDataPointTypeEventTypeLink")
    events=v._rows(dp,b"ecnEventType")
    alias_to_id={x["Address"]:x["Id"] for x in events}
    if len(alias_to_id)!=len(events):raise SourceRejected("ambiguous event aliases")
    root=ET.fromstring(event_xml)
    descs={x.findtext("ID"):{c.tag:(c.text or "") for c in x}
           for x in root.findall("EventType")}
    candidates=[]
    for name,(addr,length) in sorted(SUSPICIOUS.items()):
        event_id=alias_to_id.get(name)
        fields=descs.get(name)
        if event_id is None or fields is None or fields.get("Address","").lower()!=addr.lower():
            raise SourceRejected("historical alias absent from original VitoSoft")
        if fields.get("BlockLength")!=length:
            raise SourceRejected("archived KW2 and VitoSoft byte widths differ")
        linked=sorted({x["DataPointTypeId"] for x in links if x["EventTypeId"]==event_id})
        names=sorted(types.get(x,"UNKNOWN") for x in linked)
        if set(names)!=ALLOWED_SUSPECT_PROFILES[name]:
            raise SourceRejected("unexpected old programming service device family")
        if any(x in KW2_TYPES or x in WB2A_TYPES for x in linked):
            raise SourceRejected("wrongly attribute cross-device programming to heater")
        candidates.append({
            "alias":name,"address":addr,"length":length,
            "FCRead":fields.get("FCRead"),"FCWrite":fields.get("FCWrite"),
            "exact_device_profiles":names,
            "includes_V200KW2_any_revision":False,
            "includes_VDensHO1_20C2":False,
        })
    summaries={}
    for id_,name in {**KW2_TYPES,**WB2A_TYPES}.items():
        match=[x for x in links if x["DataPointTypeId"]==id_]
        summaries[name]={"type_id":id_,"linked_events":len(match),
                         "suspected_program_rom_endpoints_present":False}
    return {
        "dpdefinitions_sha256":v.DP_SHA,
        "ecneventtype_sha256":v.EVENT_SHA,
        "verified_exact_device_profiles":summaries,
        "cross_family_suspect_service_descriptors":candidates,
        "no_original_KW2_or_WB2A_programming_mode_command_evidenced":True,
        "no_original_KW2_or_WB2A_ROM_bank_selector_evidenced":True,
    }


def complete(archive:bytes,dp:bytes,event_xml:bytes)->dict:
    old=check_zip(archive)
    cur=compare_real_catalog(dp,event_xml)
    return {
        "mode":"OFFLINE_PINNED_KW2_2011_EXTENDED_METADATA_DEVICE_ATTRIBUTION",
        "historical_archive":old,"manufacturer_catalog":cur,
        "supported_historical_GWG_virtual_read_2010_from_issue10":True,
        "2010_GWG_virtual_read_is_independent_unpinned_issue_testimony":True,
        "2011_ordinary_KW_address_above_0x8000_empty_from_issue10":True,
        "2010_2011_reports_do_not_prove_classic_read_can_dump_128k":True,
        "actual_rom_monitor_function_identified":False,
        "MCU_flash_code_bytes_obtained":False,
        "original_optolink_firmware_dump_sequence_recovered":False,
        "controller_io":0,"controller_writes":0,
    }


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("2011_TerminatorIII_zip",type=Path)
    ap.add_argument("DPDefinitions_xml",type=Path)
    ap.add_argument("ecnEventType_xml",type=Path)
    ap.add_argument("--out",type=Path)
    opt=ap.parse_args()
    paths=(opt.__dict__["2011_TerminatorIII_zip"],opt.DPDefinitions_xml,opt.ecnEventType_xml)
    if any(p.is_symlink() or not p.is_file() for p in paths):
        ap.error("only existing regular original archived files")
    if (paths[0].stat().st_size>150000
        or paths[1].stat().st_size>v.MAX_DP_BYTES
        or paths[2].stat().st_size>v.MAX_EVENT_BYTES):
        ap.error("original source size exceeds safe limits")
    result=complete(*(p.read_bytes() for p in paths))
    output=json.dumps(result,sort_keys=True,indent=2)+"\n"
    if opt.out:opt.out.write_text(output)
    print(output)


if __name__=="__main__":main()
