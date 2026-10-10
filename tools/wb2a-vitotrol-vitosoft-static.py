#!/usr/bin/env python3
"""SHA-attested, *offline* VitoSoft event catalog audit for VDensHO1.

Catalog entries are HOST descriptors, never proof of actual MCU ROM code,
undocumented Optolink commands or a safe way to inject Vitotrol RX bytes.
"""
from __future__ import annotations
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET

DP_SHA='efec27568d398021c767771af016143bd51fc196d2d408dbb80faff84d0b19e3'
EVENT_SHA='2338beb0e8544b6149bc4b2433ecabd9509edcdafc2e8e91f00182eba1aff7ba'
TARGET_TYPE=60
MAX_DP_BYTES=188_000_000
MAX_EVENT_BYTES=12_000_000
ADDRESS_LIST=('0x27a0','0x0a5c','0x0896','0x089c','0x1642')
FORBIDDEN_INFERENCE_CODES=('XRAM_WRITE','KBUS_TRANSPARENT_WRITE','KBUS_DIRECT_WRITE')

class SourceRejected(ValueError):
    pass


def _hash_attest(data:bytes,sha:str,max_size:int, *, verify=True):
    if type(data) is not bytes or not 10<=len(data)<=max_size:
        raise SourceRejected('bounded exact VitoSoft bytes required')
    if verify and hashlib.sha256(data).hexdigest()!=sha:
        raise SourceRejected('unrecognized VitoSoft catalog revision SHA256')


def _rows(blob:bytes,table:bytes):
    # Export is an .NET DataSet diffgram: records are contiguous plain XML.
    # Only named rows, not all 248,587 unrelated extension table values,
    # are selected. Non-greedy paired capture avoids large XML tree parsing.
    rx=re.compile(rb'<'+table+rb'(?:\s[^>]*)?>(.*?)</'+table+rb'>',re.S)
    result=[]
    for m in rx.finditer(blob):
        try:element=ET.fromstring(b'<item>'+m.group(1)+b'</item>')
        except ET.ParseError as exc:raise SourceRejected('invalid source XML row') from exc
        result.append({x.tag:(x.text or '') for x in element})
    return result


def catalog_audit(dp:bytes,events:bytes, *, verify_sha=True) -> dict:
    _hash_attest(dp,DP_SHA,MAX_DP_BYTES,verify=verify_sha)
    _hash_attest(events,EVENT_SHA,MAX_EVENT_BYTES,verify=verify_sha)
    # For synthetic test fixtures check the complete document, not only the
    # selected rows. Real 186-MB exports are integrity-attested via SHA256.
    if len(dp)<1_000_000:
        try:ET.fromstring(dp)
        except ET.ParseError as exc:raise SourceRejected('truncated XML source') from exc
    types=_rows(dp,b'ecnDatapointType')
    found=[x for x in types if x.get('Id')==str(TARGET_TYPE)]
    if len(found)!=1 or found[0].get('Address')!='VDensHO1':
        raise SourceRejected('missing exact VDensHO1 device profile id 60')
    links=_rows(dp,b'ecnDataPointTypeEventTypeLink')
    ids=[x['EventTypeId'] for x in links if x.get('DataPointTypeId')==str(TARGET_TYPE)]
    if not ids or len(set(ids))!=len(ids):
        raise SourceRejected('empty or duplicate exact profile event IDs')
    enames=_rows(dp,b'ecnEventType')
    id_to_alias={x['Id']:x.get('Address','') for x in enames if 'Id' in x}
    if len(id_to_alias)!=len(enames):
        raise SourceRejected('ambiguous numeric event identifiers')
    missing=[i for i in ids if i not in id_to_alias]
    if missing:raise SourceRejected('event metadata missing for exact profile')
    aliases={id_to_alias[i] for i in ids}
    if len(aliases)!=len(ids):
        raise SourceRejected('duplicate event aliases across profile')
    try:root=ET.fromstring(events)
    except ET.ParseError as exc:raise SourceRejected('invalid event definition XML') from exc
    definitions={}
    for row in root.findall('EventType'):
        key=row.findtext('ID')
        if key is None or key in definitions:
            raise SourceRejected('undefined or duplicate event ID in VitoSoft export')
        definitions[key]={el.tag:(el.text or '') for el in row}
    missing_alias=sorted(aliases-definitions.keys())
    if missing_alias:raise SourceRejected('exact profile alias lacks matching function-code descriptor')
    profile=[definitions[alias] for alias in sorted(aliases)]
    writes=Counter(x.get('FCWrite') or 'undefined' for x in profile)
    reads=Counter(x.get('FCRead') or 'undefined' for x in profile)
    rpcs=[x for x in profile if x.get('FCRead')=='Remote_Procedure_Call' or x.get('FCWrite')=='Remote_Procedure_Call']
    matches={}
    for address in ADDRESS_LIST:
        matches[address]=[{'id':x['ID'],'read':x.get('FCRead',''),'write':x.get('FCWrite',''),
                           'access':x.get('AccessMode','')}
                          for x in profile if x.get('Address','').lower()==address]
    risky=[{'id':x['ID'],'write':x.get('FCWrite')} for x in profile
           if x.get('FCWrite') in FORBIDDEN_INFERENCE_CODES]
    count_value=lambda k:sum(1 for x in profile if k.lower() in x.get('ID','').lower())
    return {
      'source_kind':'VITOSOFT_HOST_XML_STATIC_ONLY',
      'device':'VDensHO1','device_id':'20C2','target_datapoint_type':TARGET_TYPE,
      'source_sha256':{'dp':hashlib.sha256(dp).hexdigest(), 'event':hashlib.sha256(events).hexdigest()},
      'sha256_pinned':verify_sha,
      'device_type_event_ids':len(ids),
      'matched_profile_descriptors':len(profile),
      'read_function_codes':dict(sorted(reads.items())),
      'write_function_codes':dict(sorted(writes.items())),
      'rpcs_in_device_profile':len(rpcs),
      'rpcs_named':[{'id':x['ID'],'address':x.get('Address','')} for x in rpcs],
      'addresses':matches,
      'raw_rx_injection_alias_count':sum(count_value(k) for k in ('kmbus_receive','uart1_rx','kmbus_slave_rx','vitotrol_inject')),
      'dangerous_crossprofile_write_aliases':risky,
      'no_write_service_from_descriptor_is_not_rom_proof':True,
      'physical_uart1_isr_verified':False,
      'optolink_rx_injection_service_verified':False,
      'controller_write_authorized':False,
      'new_hardware_io':False,
    }


def audit_paths(dp:Path,events:Path):
    dp=Path(dp);events=Path(events)
    if dp.stat().st_size>MAX_DP_BYTES or events.stat().st_size>MAX_EVENT_BYTES:
        raise SourceRejected('oversize catalog source')
    return catalog_audit(dp.read_bytes(),events.read_bytes())


def main():
    import argparse
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('dp_definitions',type=Path)
    p.add_argument('ecn_event_type',type=Path)
    args=p.parse_args()
    print(json.dumps(audit_paths(args.dp_definitions,args.ecn_event_type),indent=2,sort_keys=True))

if __name__=='__main__':main()
