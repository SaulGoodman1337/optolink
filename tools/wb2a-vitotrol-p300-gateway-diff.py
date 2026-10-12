#!/usr/bin/env python3
"""Offline-only A/B P300 gateway readback comparison for WB2A 20C2.

Expected A: A0:0 B0:0, B1/B2: A0:2 B0:3.
Never connects to the boiler; detects incomplete tests and contradictory
controller readbacks rather than treating successful gateway reads as RX.
"""
import argparse
from collections import defaultdict
import json
from pathlib import Path
import re

PHASES=('baseline','remote1','remote2')
ANCHORS={
 'request;101;0x0000;8':8,
 'request;101;0x00f8;8':8,
 'request;99;0x0000;2':2,
 'request;3;0x0b60;32':32,
 'request;3;0x1660;32':32,
 'request;3;0x161a;32':32,
 'read;0x0a5c;4':4,
}
OPTIONAL_REMOTE={'read;0x089c;1':1}
RESPONSE=re.compile(r'^(.+?)\s+<- openv/resp:\s*([0-9]+);0x([0-9a-f]+);([0-9a-f]+)$')
REQ_ADDR=re.compile(r'^(?:request;(?:101|99|3);0x([0-9a-f]+);\d+|read;0x([0-9a-f]+);\d+)$')
class EvidenceRejected(ValueError):pass

def inspect(lines):
    if type(lines) is not list or len(lines)>3000:
        raise EvidenceRejected('bounded line list required')
    sets={k:{} for k in PHASES}
    phase=None
    observed={'a0_enable':False,'b0_enable':False,'a0_restore':False,'b0_restore':False}
    stamps=[]
    for line in lines:
        if not isinstance(line,str) or len(line)>600:
            raise EvidenceRejected('invalid line')
        if line=='BASELINE':phase='baseline';continue
        if line.startswith('REMOTE_SAMPLE_'):
            n=line.split()[0].removeprefix('REMOTE_SAMPLE_')
            if n not in ('1','2'):
                raise EvidenceRejected('unexpected sample')
            phase='remote'+n
            stamps.append(line)
            continue
        m=RESPONSE.match(line.strip())
        if not m:continue
        command,code,addr,payload=m.groups()
        if command.startswith('writeraw;'):
            if (command,code,payload) in (
                ('writeraw;0x27a0;02','1','02'),
                ('writeraw;0x27b0;03','1','03')):
                observed['a0_enable' if '27a0' in command else 'b0_enable']=True
            elif (command,code,payload) in (
                ('writeraw;0x27a0;00','1','00'),
                ('writeraw;0x27b0;00','1','00')):
                observed['a0_restore' if '27a0' in command else 'b0_restore']=True
            continue
        if phase not in sets or command not in (ANCHORS|OPTIONAL_REMOTE):
            continue
        if command in sets[phase]:
            raise EvidenceRejected('duplicate anchor in phase: '+command)
        if code!='1':
            raise EvidenceRejected('controller rejected: '+command)
        q=REQ_ADDR.fullmatch(command)
        if not q or int(addr,16)!=int(q[1] or q[2],16):
            raise EvidenceRejected('response address does not match request')
        data=bytes.fromhex(payload)
        size=(ANCHORS|OPTIONAL_REMOTE)[command]
        if len(data)!=size:raise EvidenceRejected('short or long read')
        sets[phase][command]=data.hex()
    for phase in PHASES:
        if set(ANCHORS)-sets[phase].keys():
            raise EvidenceRejected('missing anchors in '+phase)
    if len(stamps)!=2 or not all(observed.values()):
        raise EvidenceRejected('missing enabled/restore readback or both phases')
    compared={}
    for cmd in ANCHORS:
        v=[sets[p][cmd] for p in PHASES]
        compared[cmd]={
           'identical_across_3_phases':len(set(v))==1,
           'baseline_equals_remote1':v[0]==v[1],
           'baseline_equals_remote2':v[0]==v[2],
           'remote_samples_agree':v[1]==v[2],
           'hex_per_phase':dict(zip(PHASES,v)),
        }
    result={
      'controller_coding_acknowledged_and_restored':all(observed.values()),
      'samples':PHASES,
      'native_p300_kbus_gateway_read_0x65_supported':True,
      'gateway_data_changed_when_v300_requested':not all(
        compared[k]['identical_across_3_phases']
        for k in ('request;101;0x0000;8','request;101;0x00f8;8')),
      'indirect_read_changed':not compared['request;99;0x0000;2']['identical_across_3_phases'],
      'descriptor_0b6d_changed':len({
        sets[x]['request;3;0x0b60;32'][26:34] for x in PHASES})>1,
      'remote_swindex_nonzero_seen':any(
        sets[x]['read;0x0a5c;4']!='00000000' for x in PHASES[1:]),
      'remote_sensor_valid_seen':any(
        sets[x].get('read;0x089c;1') not in (None,'03') for x in PHASES[1:]),
      'km_bus_slave_rx_ingress_verified':False,
      'firmware_rx_commit_verified':False,
      'heating_settings_restored_by_later_independent_supervisor':False,
      'compared':compared,
    }
    return result

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('log',type=Path)
    args=p.parse_args()
    try:result=inspect(args.log.read_text().splitlines())
    except (OSError,EvidenceRejected) as e:p.error(str(e))
    print(json.dumps(result,indent=2,sort_keys=True))

if __name__=='__main__':main()
