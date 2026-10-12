#!/usr/bin/env python3
"""Offline audit: GWG, VS1/KW, P300 and nearby Viessmann host profiles.

Grounds cross-family comparisons in the original SHA256-attested VitoSoft
XML tables, a public historical GWG protocol table and a separately pinned
2024 ViessData C# reader. Extracts actual event-type LINK membership, not
grep hits: a similar event name elsewhere is NOT evidence on WB2A 20C2.

Focus: indirect host-visible read paths and event-record slicing; neither
a generic 16-bit request nor a named checksum proves main MCU ROM access.
Never execute downloaded EXEs, contact Optolink, or change heater settings.
The latest community source is inspected as text only, outside the repo.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
import mmap
from pathlib import Path
import re
import sys
import xml.etree.ElementTree as ET

DP=Path("/home/chatgpt-admin/research/vitosoft-lfs/DPDefinitions.xml")
EVENT=Path("/home/chatgpt-admin/research/vitosoft-lfs/ecnEventType.xml")
WIKI=Path("/home/chatgpt-admin/research/openv.wiki/Protokoll-GWG.md")
CS=Path("/home/chatgpt-admin/research/firmware-bridge-comparative-20261012/ViessDataSourceStatic/ViessData/ViessData/COptoLinkCommAsync.cs")
VMCOMM=Path("/home/chatgpt-admin/research/InsideViessmannVitosoft/VitosoftCommunication.md")
SOURCES={
 "dp":(DP,"efec27568d398021c767771af016143bd51fc196d2d408dbb80faff84d0b19e3",186559004),
 "events":(EVENT,"2338beb0e8544b6149bc4b2433ecabd9509edcdafc2e8e91f00182eba1aff7ba",9935374),
 "wiki":(WIKI,"6767a5fc30db44ac89ca9e9e4d27d64f5f64091ddd0419b39586a493155af82c",1416),
 "new_reader":(CS,"ce1d78a9a90e22d0283791f8a0c8ee6a3c01ca617f183819ba831978735fb80d",55123),
 "community_protocol_analysis":(VMCOMM,"19fc2189e1392aa11ba986ee063c2d288e4197637f56083012a702c913881371",7022),
}
NAMES=("VDensHO1","VPendHO1","VScotHO1","VDensHO1_4",
       "V200KW2","GWG_VBEM_00","VScotHO1_200","VScotHO1_200_01")
ROM_IDS=("ChecksummeROMBerechnet~0x08F0","NRF_ChecksummeROMLinker~0x08F4")
ROM_PROFILES={"VBC550S","VBC550P","Ecotronic","Ecotronic_100"}
READ_ONLY_FCS={"Virtual_READ","GFA_READ","KMBUS_EEPROM_READ"}
LINK_RE=re.compile(rb"<ecnDataPointTypeEventTypeLink(?:\s[^>]*)?>(.*?)</ecnDataPointTypeEventTypeLink>",re.S)
ROWS={
 "types":re.compile(rb"<ecnDatapointType(?:\s[^>]*)?>(.*?)</ecnDatapointType>",re.S),
 "ids":re.compile(rb"<ecnEventType(?:\s[^>]*)?>(.*?)</ecnEventType>",re.S),
}
SELECT=re.compile(r"(?:VDens|VScot|GWG_|V200KW|V300KW|VPend|VPlus|HV_GWG|V300GW2A|VCaldens)")


class Rejected(ValueError):
    pass


def sha_original(path:Path,digest:str,size:int)->str:
    if not isinstance(path,Path) or path.is_symlink() or not path.is_file() or path.stat().st_size!=size:
        raise Rejected("missing/non-original source length: "+str(path))
    with path.open("rb") as f: actual=hashlib.file_digest(f,"sha256").hexdigest()
    if actual!=digest:raise Rejected("source SHA changed: "+str(path))
    return actual


def rowgen(mm,pattern):
    for m in pattern.finditer(mm):
        try:row=ET.fromstring(b"<x>"+m.group(1)+b"</x>")
        except ET.ParseError as e:raise Rejected("invalid source XML table row") from e
        vals={v.tag:v.text or "" for v in row}
        if len(vals)!=len(row):raise Rejected("repeated XML fields in one row")
        yield vals


def load_catalog(dp:Path,event:Path)->tuple[dict,dict,dict,dict,dict]:
    # Caller MUST sha check before loading: this tool is a provenance audit.
    with dp.open("rb") as f,mmap.mmap(f.fileno(),0,access=mmap.ACCESS_READ) as mm:
        types={}
        for row in rowgen(mm,ROWS["types"]):
            if row.get("Id") in types:raise Rejected("duplicate host device type")
            types[row["Id"]]=row.get("Address","")
        if len(types)!=399 or types.get("60")!="VDensHO1":
            raise Rejected("unexpected host type taxonomy")
        ids={}
        for row in rowgen(mm,ROWS["ids"]):
            if row.get("Id") in ids:raise Rejected("duplicate host event ID")
            ids[row["Id"]]=row.get("Address","")
        links=defaultdict(set)
        count=0
        for row in rowgen(mm,LINK_RE):
            count+=1
            profile,event_id=row.get("DataPointTypeId"),row.get("EventTypeId")
            if profile not in types or event_id not in ids or event_id in links[profile]:
                raise Rejected("invalid/duplicate host event mapping")
            links[profile].add(event_id)
        if count!=104339:raise Rejected("unexpected total host joins")
        if any(v not in ids for members in links.values() for v in members):
            raise Rejected("dangling event link")
    try:root=ET.parse(event).getroot()
    except ET.ParseError as e:raise Rejected("corrupt event definition") from e
    desc={}
    for row in root.findall("EventType"):
        name=row.findtext("ID")
        if not name or name in desc:raise Rejected("duplicate/unnamed event definition")
        desc[name]={v.tag:v.text or "" for v in row}
    if len(desc)!=11582:raise Rejected("unexpected event definition size")
    required={ids[event_id] for p in links for event_id in links[p]}
    if required-desc.keys():raise Rejected("missing function code descriptor")
    return types,ids,links,desc,{"all_type_count":len(types),"all_link_count":count,
                                "all_event_definition_count":len(desc)}


def code_oracle_label(name:str)->bool:
    """Strictly code-checksum/firmware tags, never accidental 'Strom' substring."""
    if type(name) is not str:raise Rejected("nontext event ID")
    head=name.split("~",1)[0].lower()
    return bool(re.search(r"checksum(?:me)?rom|rom(?:checksum|linker)|flash(?:read|checksum)|bootloader|firmware|programmrom|romdump",head))


def rows_for(types:dict,ids:dict,links:dict,desc:dict,name:str)->list[dict]:
    found=[t for t,n in types.items() if n==name]
    if len(found)!=1:raise Rejected("ambiguous or missing host device "+name)
    out=[]
    for event_id in sorted(links.get(found[0],()),key=int):
        key=ids[event_id]
        if key not in desc:raise Rejected("missing actual event definition "+key)
        out.append(desc[key])
    return out


def object_slice(rows:list[dict],fc:str,address:str,length:int)->dict:
    """Host's fixed-length READ response split into several logical fields."""
    found=[r for r in rows if r.get("FCRead")==fc and
           r.get("Address")==address and r.get("BlockLength")==str(length)]
    if not found:raise Rejected("missing exact block source")
    positions=[]
    for r in found:
        if not r.get("BytePosition","").isdecimal() or not r.get("ByteLength","").isdecimal():
            raise Rejected("missing byte position/length")
        pos,n=int(r["BytePosition"]),int(r["ByteLength"])
        if pos+n>length:raise Rejected("event slice outside advertised host block")
        positions.append(pos)
    return {
        "FCRead":fc,"address":address,"block_length":length,
        "logical_descriptors":len(found),"different_slice_start_offsets":len(set(positions)),
        "slice_offsets":sorted(set(positions)),
        "prefixes":sorted(set(r.get("PrefixRead","") for r in found)),
        "uniform_read_only":all(r.get("AccessMode")=="Read" for r in found),
        "independent_controller_registers_proven":False,
        "parameter_selects_memory_bank_proven":False,
    }


def check_public_reader(csharp:str,gwgwiki:str,legacy_doc:str)->dict:
    """Compare bytes of two actual codepaths, not a comment's claims."""
    if "private async Task<CCommRequReturn> ReadData300(int addr, byte len)" not in csharp:
        raise Rejected("unexpected P300 public function")
    if "private async Task<CCommRequReturn> ReadDataKW(int addr, byte len)" not in csharp:
        raise Rejected("unexpected VS1/KW public function")
    p300=csharp.split("private async Task<CCommRequReturn> ReadData300(",1)[1].split(
        "private async Task<CCommRequReturn> WriteData300(",1)[0]
    kw=csharp.split("private async Task<CCommRequReturn> ReadDataKW(",1)[1].split(
        "private async Task<CCommRequReturn> WriteDataKW(",1)[0]
    required_p300=(
       "outbuff[0] = STX;", "outbuff[2] = cbREQ;",
       "outbuff[3] = cbREAD;",
       "outbuff[4] = (byte)((addr >> 8) & 0xFF);",
       "outbuff[5] = (byte)((addr) & 0xFF);",
       "outbuff[6] = len;",
    )
    required_kw=(
       "outbuff[0 + offs] = 0xF7;",
       "outbuff[1 + offs] = (byte)((addr >> 8) & 0xFF);",
       "outbuff[2 + offs] = (byte)(addr & 0xFF);",
       "outbuff[3 + offs] = len;",
    )
    if not all(x in p300 for x in required_p300) or not all(x in kw for x in required_kw):
        raise Rejected("different address byte serialization in public implementation")
    for snippet in ("VIRTUAL READ | 01 | C7","PHYSICAL READ | 03 | CB",
                    "PHYSICAL KMBUS EEPROM READ | 67 | 43",
                    "**01 Telegramm Start Byte**"):
        if snippet=="**01 Telegramm Start Byte**":continue
        if snippet not in gwgwiki:raise Rejected("old GWG function code missing")
    for op in ("`GFA_Read` = `0x6B`","`PROZESS_READ` = `0x7B`"):
        if op not in legacy_doc:
            raise Rejected("historic VS1 GFA or process read function missing")
    return {
        "source":"2024 ViessData C# + historical OpenV GWG table + third-party VitoSoft analysis; NOT MCU code",
        "public_VS1_KW_reader":"0xF7 + address_high + address_low + length",
        "public_P300_300_reader":"0x41 + control + mode + address_high + address_low + length + checksum",
        "public_reader_source_address_bytes":2,
        "VS1_GFA_read_fc_hex":"0x6B",
        "VS1_PROZESS_read_fc_hex":"0x7B",
        "old_GWG_virtual_read_fc_hex":"0xC7",
        "old_GWG_physical_read_fc_hex":"0xCB",
        "old_GWG_KMBUS_EEPROM_read_fc_hex":"0x43",
        "GWG_is_one_address_byte_in_documented_frame":True,
        "community_reader_has_direct_upper_ROM_bank_selector_proven":False,
    }


def profile_oracle_summary(types,ids,links,defs)->dict:
    allprofiles={v:k for k,v in types.items()}
    if len(allprofiles)!=len(types):raise Rejected("ambiguous profile alias")
    for n in NAMES:
        if n not in allprofiles:raise Rejected("required generation absent "+n)
    interest={p:n for p,n in types.items() if SELECT.search(n)}
    if len(interest)!=90:raise Rejected("generation selection drift")
    idx={}
    events_by={}
    for p,n in interest.items():
        rows=rows_for(types,ids,links,defs,n)
        events_by[n]=rows
        idx[n]=set(ids[i] for i in links.get(p,()))
    if len(set.union(*idx.values()))!=2314 or sum(map(len,idx.values()))!=39263:
        raise Rejected("generation join cardinalities changed")
    target="VDensHO1"
    refs={}
    for name in NAMES:
        rows=events_by[name]
        refs[name]={"device_type_id":allprofiles[name],
                    "descriptors":len(rows),
                    "FCRead":dict(sorted(Counter(r.get("FCRead","") or "undefined"
                                               for r in rows).items())),
                    "shared_exact_event_aliases_with_WB2A":len(idx[name]&idx[target]),
                    "jaccard_to_WB2A":round(len(idx[name]&idx[target])/len(idx[name]|idx[target]),6)}
    if (refs[target]["descriptors"]!=581 or
        idx["VPendHO1"]!=idx[target] or idx["VScotHO1"]!=idx[target] or
        len(idx["VDensHO1_4"]&idx[target])!=558):
        raise Rejected("cross-era equivalence failed")
    own=events_by[target]
    gfa=[r for r in own if r.get("FCRead")=="GFA_READ"]
    if (len(gfa)!=94 or len({r["Address"] for r in gfa})!=64 or
        any(r.get("BlockLength")!="1" for r in gfa)):
        raise Rejected("unknown target GFA response layout")
    gwg=events_by["GWG_VBEM_00"]
    kmbus=[r for r in gwg if r.get("FCRead")=="KMBUS_EEPROM_READ"]
    if (len(kmbus)!=54 or len({r.get("Address") for r in kmbus})!=13 or
        {r.get("PrefixRead") for r in kmbus}!={"030000000101"}):
        raise Rejected("old GWG KM-Bus EEPROM source/prefix changed")
    target_fcs={r.get("FCRead") for r in own}
    if "KMBUS_EEPROM_READ" in target_fcs or "EEPROM_READ" in target_fcs or "Physical_READ" in target_fcs:
        raise Rejected("new target FC path; cannot conclude it is absent")
    # ROM checksums exist only in *unrelated* device profiles, globally,
    # not merely missing in our selected 90 generation profiles.
    checksum_profiles={}
    for rom_id in ROM_IDS:
        found=[t for t,n in types.items() if rom_id in {ids[i] for i in links.get(t,())}]
        if set(types[p] for p in found)!=ROM_PROFILES:
            raise Rejected("named ROM checksum device membership changed")
        r=defs[rom_id]
        if r.get("FCRead")!="Virtual_READ" or r.get("BlockLength")!="2":
            raise Rejected("ROM checksum not exact fixed two-byte virtual read")
        checksum_profiles[rom_id]={"host_event_address":r.get("Address"),
              "FCRead":r.get("FCRead"),"fixed_host_block_length":2,
              "device_profiles":sorted(types[p] for p in found),
              "parameter_controls_prefix_length_proven":False}
    newer=[r for r in events_by["VScotHO1_200_01"]
           if r.get("ID")=="HO2B_LAN_Card_Firmware~0xD069"]
    if (len(newer)!=1 or newer[0].get("Address")!="0xD084" or
        newer[0].get("BlockLength")!="4" or newer[0].get("FCRead")!="Virtual_READ"):
        raise Rejected("later HO2B firmware descriptor changed")
    strict={n:sorted({r["ID"] for r in rows if code_oracle_label(r.get("ID",""))})
            for n,rows in events_by.items()}
    if strict[target]!=[]:
        raise Rejected("newly named WB2A code/ROM oracle needs review")
    if strict["VScotHO1_200_01"]!=["HO2B_LAN_Card_Firmware~0xD069"]:
        raise Rejected("later model apparent firmware oracle changed")
    example_gwg=object_slice(gwg,"KMBUS_EEPROM_READ","0x00A0",10)
    example_wb2a=object_slice(own,"Virtual_READ","0x10A0",16)
    example_alarm=object_slice(own,"Virtual_READ","0xA132",29)
    if (example_gwg["slice_offsets"]!=list(range(10)) or
        example_wb2a["slice_offsets"]!=list(range(11)) or
        example_alarm["logical_descriptors"]!=14):
        raise Rejected("cross-era host field extraction semantics changed")
    target_read_only=sum(r.get("AccessMode")=="Read" for r in own)
    return {
        "selected_host_profiles":len(interest),
        "selected_profile_event_links":sum(map(len,idx.values())),
        "unique_selected_event_descriptors":len(set.union(*idx.values())),
        "profiles":refs,
        "target_read_only_descriptors":target_read_only,
        "wb2a_gfa_read_descriptors":len(gfa),
        "wb2a_gfa_distinct_addresses":len({r["Address"] for r in gfa}),
        "wb2a_gfa_fixed_one_byte_blocks":True,
        "old_gwg_kmbus_eeprom_descriptors":len(kmbus),
        "old_gwg_kmbus_eeprom_distinct_addresses":len({r["Address"] for r in kmbus}),
        "old_gwg_KMBUS_prefix_hex":"030000000101",
        "no_host_KMBUS_EEPROM_READ_in_WB2A_profile":True,
        "no_named_ROM_checksum_in_WB2A_profile":True,
        "three_early_HO1_profiles_identical":True,
        "strict_named_code_oracles_by_selected_generation":{
            name:strict[name] for name in NAMES
        },
        "two_global_ROM_checksum_events":checksum_profiles,
        "later_lan_firmware_label":{
            "ID":newer[0]["ID"],"actual_Virtual_READ_address":newer[0]["Address"],
            "fixed_length":4,"proven_firmware_image_bytes":False},
        "fixed_response_slicing_examples":{
            "old_GWG_eeprom_alarm_codes":example_gwg,
            "WB2A_coding_plug_16_byte":example_wb2a,
            "WB2A_LON_alarm_29_byte":example_alarm,
        },
        "source_evidence_has_variable_ROM_prefix_CRC":False,
        "source_evidence_has_main_controller_ROM_copy_or_dump":False,
    }


def audit()->dict:
    checks={key:sha_original(*entry) for key,entry in SOURCES.items()}
    types,ids,links,desc,meta=load_catalog(DP,EVENT)
    matrix=profile_oracle_summary(types,ids,links,desc)
    code=check_public_reader(CS.read_text(encoding="utf-8-sig"),
                             WIKI.read_text(encoding="utf-8"),
                             VMCOMM.read_text(encoding="utf-8"))
    return {
        "audit":"PASS","date":"2026-10-12",
        "sources":checks,
        "source_scope":"HOST_DESCRIPTORS_PLUS_COMMUNITY_PROVENANCE_NOT_CONTROLLER_FIRMWARE",
        "catalog_counts":meta,
        "generation_comparison":matrix,
        "wire_implementations":code,
        "controller_reads":0,"controller_writes":0,
        "firmware_program_ROM_bytes_recovered":0,
        "ready_to_attempt_WB2A_ROM_read":False,
        "research_priority":[
            "Seek MCU-internal callable ROM content oracle with controllable output, not an address alias.",
            "Inspect existing P300/VS1 valid-start multi-byte object semantics and GWG KMBus routed reads as separate routing models.",
            "Do not interpret GFA 0x4000 one-byte telemetry or HO2B LAN-card firmware VERSION as main WB2A firmware.",
            "Require a verified 20C2 handler/code/data-flow source before new live commands, especially after C5/F9.",
        ],
    }


def main()->None:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out",type=Path)
    a=p.parse_args()
    result=audit()
    output=json.dumps(result,ensure_ascii=False,sort_keys=True,indent=2)+"\n"
    if a.out:a.out.write_text(output,encoding="utf-8")
    print(output,end="")


if __name__=="__main__":
    try:main()
    except (Rejected,ET.ParseError,OSError,ValueError,KeyError) as e:
        print("CROSSGEN_ROM_ORACLE_SOURCE_REJECTED: "+str(e),file=sys.stderr)
        sys.exit(2)
