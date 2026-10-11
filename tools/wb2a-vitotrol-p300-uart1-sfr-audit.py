#!/usr/bin/env python3
"""Offline audit: actual WB2A native P300 M16C UART1 register observations.

Read back S1RIC/U1C1 without ever writing MCU UART/DMA/SFRs.
Crucially, the receiver and IRQ priority can be active even with A0=00.
Do not infer causality between A0 codings and UART1 RX sampling phases.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import re

ALLOWED = {
    'request;3;0x0054;1': (0x0054, 1),
    'request;3;0x03ac;2': (0x03ac, 2),
    'request;3;0x03a8;2': (0x03a8, 2),
    'request;3;0x0020;16': (0x0020, 16),
    'request;3;0x0030;16': (0x0030, 16),
    'request;3;0x161a;32': (0x161a, 32),
    'request;3;0x1640;32': (0x1640, 32),
    'read;0x0a5c;4': (0x0a5c, 4),
    'read;0x089c;1': (0x089c, 1),
    'read;0x5738;1': (0x5738, 1),
}
PATTERN=re.compile(r'^(.+?)\s+<- openv/resp:\s*(\d+);0x([\da-fA-F]+);([^\s]+)$')
PRIORITY_MASK=0x07
IR_MASK=0x08
RE_MASK=0x04
RI_MASK=0x08
ALLOWED_SFR={'request;3;0x0054;1','request;3;0x03ac;2'}
V300='A0_02_B0_03'
NONE='A0_00_B0_00'
MAX_LOG=100_000


class SfrEvidenceRejected(ValueError):pass


def _parse_phase(line: str) -> str | None:
    if line=='BASELINE':
        return 'BASELINE'
    if line.startswith('V300_SFR_SAMPLE_'):
        k=line.split(' ',1)[0].removeprefix('V300_SFR_SAMPLE_')
        if k not in ('1','2','3'):
            raise SfrEvidenceRejected('unexpected Vitotrol sample id')
        return 'V300_SFR_'+k
    if line.startswith('PHASE '):
        q=line.split()
        if len(q)<3 or not re.fullmatch(r'[A-Z0-9_]+',q[1]):
            raise SfrEvidenceRejected('malformed phase')
        return q[1]
    return None


def summarize(logs: list[tuple[str,str]]) -> dict:
    if not isinstance(logs,list) or not 1<=len(logs)<=4:
        raise SfrEvidenceRejected('bounded nonempty source list required')
    all_records=[]
    per_source={}
    for name,text in logs:
        if not isinstance(name,str) or not name or type(text) is not str or not 80<len(text)<=MAX_LOG:
            raise SfrEvidenceRejected('bounded named log required')
        if name in per_source:
            raise SfrEvidenceRejected('duplicate log source')
        records=[]
        seen=set()
        phase=None
        rows={}
        enabled=Counter()
        writes={'a0_0':0,'a0_1':0,'a0_2':0,'b0_0':0,'b0_3':0}
        for line in text.splitlines():
            phase_new=_parse_phase(line)
            if phase_new is not None:
                if phase_new in seen:
                    raise SfrEvidenceRejected('repeated phase')
                seen.add(phase_new)
                phase=phase_new
                rows[phase]={}
                continue
            m=PATTERN.fullmatch(line.strip())
            if m is None:
                continue
            command,rc,address_hex,payload=m.groups()
            if command.startswith('writeraw;'):
                # A returned code alone only acknowledges a command; it is
                # not evidence that a UART RX interrupt was generated.
                if rc!='1':
                    raise SfrEvidenceRejected('coding command failed')
                if command.startswith('writeraw;0x27a0;'):
                    v=int(command.rsplit(';',1)[1],16)
                    if v not in (0,1,2) or int(payload,16)!=v:
                        raise SfrEvidenceRejected('unexpected A0 value')
                    writes['a0_'+str(v)]+=1
                elif command.startswith('writeraw;0x27b0;'):
                    v=int(command.rsplit(';',1)[1],16)
                    if v not in (0,3) or int(payload,16)!=v:
                        raise SfrEvidenceRejected('unexpected B0 value')
                    writes['b0_'+str(v)]+=1
                continue
            if command not in ALLOWED:
                continue
            if phase is None:
                raise SfrEvidenceRejected('read before phase')
            if command in rows[phase]:
                raise SfrEvidenceRejected('duplicate read in phase')
            addr,count=ALLOWED[command]
            if int(address_hex,16)!=addr or rc!='1':
                raise SfrEvidenceRejected('controller address/return mismatch')
            try:
                raw=bytes.fromhex(payload)
            except ValueError as e:
                raise SfrEvidenceRejected('not a hex controller reply') from e
            if len(raw)!=count:
                raise SfrEvidenceRejected('response length mismatch')
            rows[phase][command]=raw
        for name_phase,vals in rows.items():
            if not ALLOWED_SFR.issubset(vals):
                raise SfrEvidenceRejected('missing UART1 SFR reads in '+name_phase)
            siric=vals['request;3;0x0054;1'][0]
            ctrl=vals['request;3;0x03ac;2']
            u1c0,u1c1=ctrl
            info={
              'source':name,'phase':name_phase,
              's1ric_hex':f'{siric:02x}',
              's1ric_priority':siric&PRIORITY_MASK,
              's1ric_irq_pending_observed':bool(siric&IR_MASK),
              'u1c0_hex':f'{u1c0:02x}',
              'u1c1_hex':f'{u1c1:02x}',
              'u1c1_rx_enabled':bool(u1c1&RE_MASK),
              'u1c1_rx_complete_observed':bool(u1c1&RI_MASK),
              'u1c1_tx_enabled':bool(u1c1&1),
              'uart1_mode_baud_control_hex':vals.get('request;3;0x03a8;2',b'').hex() or None,
              'swindex_hex':vals.get('read;0x0a5c;4',b'').hex() or None,
            }
            records.append(info)
            all_records.append(info)
        per_source[name]={'records':len(records),'acked_config_writes':dict(writes)}
    if not all_records:
        raise SfrEvidenceRejected('no validated UART1 controls')
    observed_off=any(r['s1ric_priority']==0 and not r['u1c1_rx_enabled']
                     for r in all_records)
    observed_on=any(r['s1ric_priority']>0 and r['u1c1_rx_enabled']
                    for r in all_records)
    none_active=any(r['u1c1_rx_enabled'] and
        (r['phase']=='BASELINE' or r['phase'].startswith(NONE))
        for r in all_records)
    remote_off=any(not r['u1c1_rx_enabled'] and
        (r['phase'].startswith(V300) or r['phase'].startswith('V300_SFR_'))
        for r in all_records)
    irq_seen=any(r['s1ric_irq_pending_observed'] or
                 r['u1c1_rx_complete_observed'] for r in all_records)
    result={
      'target':'ACTUAL_WB2A_20C2_PHYSICAL_READ_SFR',
      'm16c62p_uart1_register_layout_correlated_to_live_hardware':True,
      'exact_mcu_laser_marking_derived_from_these_sfr_reads':False,
      'physical_rx_irq_pending_event_directly_captured':irq_seen,
      'uart1_rx_gate_on_sampled':observed_on,
      'uart1_rx_gate_off_sampled':observed_off,
      'uart1_rx_enabled_even_without_vitotrol':none_active,
      'uart1_rx_disabled_during_remote_enabled_sample':remote_off,
      'uart1_rx_exclusively_enabled_by_a0_coding_proven':False,
      'sampled_sfr_reads_do_not_identify_firmware_rx_handler':True,
      'interrupt_cannot_be_requested_by_writing_1_to_s1ric_ir':True,
      'software_int_vector20_callsite_exposed_via_optolink':False,
      'real_vitotrol_registered':False,
      'serial_connections_opened':0,
      'controller_sfr_writes_sent':0,
      'sample_count':len(all_records),
      'sources':per_source,
      'samples':all_records,
    }
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('logs',nargs='+',type=Path)
    a=p.parse_args()
    try:
        r=summarize([(x.name,x.read_text()) for x in a.logs])
    except (OSError,SfrEvidenceRejected) as e:
        p.error(str(e))
    print(json.dumps(r,indent=2,sort_keys=True))


if __name__=='__main__':
    main()
