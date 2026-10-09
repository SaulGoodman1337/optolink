"""Inspect recorded per-call TX/RX host timestamps WITHOUT serial access.

A multi-byte RX record carries a single host timestamp for that chunk, not
separate UART arrival times. Output explicitly flags coalesced batches.
This is an offline investigator, not a firmware timing oracle.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path


class TraceRejected(ValueError):
    pass


def classify_tx(raw: bytes) -> str:
    if raw == b'\x04':
        return 'EOT_RESET'
    if raw == b'\x16\x00\x00':
        return 'P300_START'
    if raw == b'\x06':
        return 'P300_ACK'
    if raw.startswith(b'\x01\xf7'):
        return 'VS1_ID'
    if raw.startswith(b'\xf7'):
        return 'VS1_VIRTUAL_READ'
    if raw.startswith(b'\x6b'):
        return 'VS1_GFA_READ'
    if raw.startswith(b'\x41'):
        return 'P300_FRAMED_READ'
    return 'OTHER_UNKNOWN_TX'


def trace_attribution(events: list[dict]) -> dict:
    if not isinstance(events, list) or len(events) > 100000:
        raise TraceRejected('bounded list of event objects required')
    normalized=[]
    last_t=-float('inf')
    for i,event in enumerate(events):
        if not isinstance(event,dict) or event.get('direction') not in (
                'TX','RX','UNEXPECTED'):
            raise TraceRejected(f'bad event direction at index {i}')
        raw=event.get('hex')
        if not isinstance(raw,str) or not raw or len(raw)%2:
            raise TraceRejected('bad hex event')
        try:
            data=bytes.fromhex(raw)
        except ValueError as e:
            raise TraceRejected('bad hex event') from e
        if len(data)>4096:
            raise TraceRejected('unbounded serial event size')
        t=event.get('t_monotonic')
        if (type(t) not in (float,int) or not math.isfinite(t) or t < last_t):
            raise TraceRejected('missing or non-monotonic event timestamp')
        last_t=float(t)
        normalized.append((event['direction'],data,float(t)))
    if not normalized:
        raise TraceRejected('empty trace')
    transactions=[]
    gaps=[]
    batched=[]
    t_last_rx=None
    current=None
    eot_pending=None
    enq_first=[]
    unexpected=[]
    for direction,data,t in normalized:
        if direction=='TX':
            if current is not None:
                transactions.append(current)
            if t_last_rx is not None:
                gaps.append(round((t-t_last_rx)*1000,3))
            current={'tx':data.hex(),'operation':classify_tx(data),
                     't_tx':t,'rx_chunks':[], 'first_rx_wait_ms':None}
            if data==b'\x04':
                eot_pending=t
            elif data != b'\x04':
                eot_pending=None
        else:
            if len(data)>1:
                batched.append({'hex':data.hex(),'byte_count':len(data),'t_monotonic':t,
                                'warning':'Only first/observed read chunk timestamp is known'})
            if direction=='UNEXPECTED':
                unexpected.append({'hex':data.hex(),'t_monotonic':t})
            if current is not None:
                if current['first_rx_wait_ms'] is None:
                    current['first_rx_wait_ms']=round((t-current['t_tx'])*1000,3)
                current['rx_chunks'].append({'hex':data.hex(),'t_rx':t})
            if eot_pending is not None and direction=='RX' and data==b'\x05':
                enq_first.append({'eot_t':eot_pending,'enq_t':t,
                                  'wait_ms':round((t-eot_pending)*1000,3)})
            t_last_rx=t
    if current is not None:
        transactions.append(current)
    # Both ENQ0 and ENQ1 after the same EOT may appear in `enq_first`;
    # caller can group by shared eot_t. Do not conflate their intervals.
    time_gaps = sorted(gaps)
    return {
       'observation':'HOST_MONOTONIC_RX_READ_TIMESTAMPS_NOT_LOGIC_ANALYZER',
       'transactions':transactions,
       'eot_to_enq_host_ms':enq_first,
       'inter_request_rx_to_tx_ms':gaps,
       'sum_inter_request_gap_ms':round(sum(gaps),3),
       'max_inter_request_gap_ms':round(max(gaps) if gaps else 0,3),
       'batched_rx_without_per_byte_timestamps':batched,
       'unexpected_rx':unexpected,
       'interpretation_limits':[
          'EOT->ENQ durations include firmware, CP2102 USB/driver, scheduler and polling.',
          'RX->next TX gaps include required guards/quiet time and are NOT all removable.',
          'Multi-byte RX chunks are never treated as independently timestamped bytes.',
          'Absence of an ENQ trace is not proof of a successful early-start handshake.',
       ]
    }


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--measurement', type=Path, required=True,
                        help='previously saved read-only measurement.json')
    args=parser.parse_args(argv)
    data=json.loads(args.measurement.read_text(encoding='utf-8'))
    print(json.dumps(trace_attribution(data['events']),indent=2,sort_keys=True))
    return 0


if __name__=='__main__':
    raise SystemExit(main())
