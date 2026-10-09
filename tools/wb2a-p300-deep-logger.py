#!/usr/bin/env python3
"""WB2A 20C2 multi-hour VS1/P300 differential capture, read-only and supervised.

Unlike the old P300-only overnight run, this observes real VS1 GFA P06
repeatedly in dedicated VS1 phases. Short P300 phases sample only previously
read safe status, DMA0 and selected physical RAM. They are NEVER simultaneous.
No writes, no boiler control or new guessed function/address combination.
"""
from __future__ import annotations

import argparse
from collections import Counter
import contextlib
import datetime as dt
import fcntl
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import shutil
import signal
import stat
import subprocess
import sys
import tarfile
import tempfile
import time

VERSION = '1.0.0-p300-deep-multiprotocol'
PROJECT = Path('/root/p300-trial-work/project')
ROOT = Path('/root/p300-trial-work/p300-deep-results')
BUNDLES = Path('/root/p300-trial-work/research-bundles')
UNIT = 'optolink-p300-deep-logger.service'
PYTHON = '/opt/optolink/venv/bin/python'
BASE_FILE = 'wb2a-uart1-overnight.py'
HELPER_FILE = 'wb2a-handover-probe.py'
DEFAULT_HOURS = 4
MAX_HOURS = 8
VS1_WINDOW_S = 50.0
P300_WINDOW_S = 75.0
P300_INTERVAL_S = 1.0
VS1_INTERVAL_S = .35
DETAIL_EVERY = 6
PROGRESS_EVERY_S = 25
MIN_DISK_BYTES = 256 * 1024 * 1024
MAX_SINGLE_LOG = 256 * 1024 * 1024
FF = b'\xff'
EXTRA_GFA = {'P10':bytes.fromhex('6b400a01'), 'P84':bytes.fromhex('6b405401')}

# P300 reads: all lengths <=32 and all addresses in historical read-only logs.
# Physical SRAM 0x15E0..0x165F was inside the old 0x0400..0x53FF sweep.
# 0x18F8 and 0x1A70 were individually sampled in the 2026-09-26 research.
FAST_READS = ((1,0x55D3,11,'native_55d3'),
              (3,0x0020,16,'dma0'),
              (3,0x1600,32,'ram_1600'),
              (3,0x1620,32,'ram_1620'))
SLOW_READS = ((3,0x15E0,32,'ram_15e0'),
              (3,0x1640,32,'ram_1640'),
              (3,0x18F8,32,'ram_18f8'),
              (3,0x1A70,32,'ram_1a70'))
ALL_READS = FAST_READS + SLOW_READS
FLAME_BIT = 0x20
LOCKOUT_BIT = 0x40
SELF_NAMED_SERVICE_UNITS = (
    'optolink-uart1-overnight.service',
    'optolink-uart1-dma0-cycle.service',
    'optolink-uart1-p300-focus.service',
    'optolink-p87-p300-check.service',
    'optolink-p87-mirror.service',
    'optolink-handover-probe.service',
    'optolink-p300-trial.service',
)
# The two installed modules are copied and pinned into the per-session folder.
# In plan mode loading them must never read hardware.
BASE = None


def iso_utc():
    return dt.datetime.now(dt.timezone.utc).isoformat()


class DeferredStop:
    """Systemd stop only requests exit; never interrupt a half-read GFA or P300 frame."""
    def __init__(self):
        self.signum = None

    def on_signal(self, signum, frame):
        self.signum = signum

    def check(self):
        if self.signum is not None:
            raise RuntimeError('OPERATOR_STOP_SIGNAL_' + str(self.signum))


def load_local_base(directory: Path):
    global BASE
    if BASE is not None:
        return BASE
    path = directory / ('base.py' if (directory/'base.py').is_file() else BASE_FILE)
    if not path.is_file():
        raise RuntimeError('EXACT_PINNED_BASE_MISSING')
    spec = importlib.util.spec_from_file_location('wb2a_pinned_overnight_base',path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    BASE = module
    return module


def check_hash(path: Path, expected: str):
    if path.is_symlink() or not path.is_file():
        raise RuntimeError('PINNED_SOURCE_NOT_REGULAR_'+path.name)
    actual=hashlib.sha256(path.read_bytes()).hexdigest()
    if actual!=expected:
        raise RuntimeError('PINNED_SOURCE_MISMATCH_'+path.name)


def frame(fc: int, addr: int, length: int) -> bytes:
    if (fc,addr,length) not in {(f,a,n) for f,a,n,_ in ALL_READS}:
        raise ValueError('UNREVIEWED_P300_READ')
    data=bytes((0x41,5,0,fc,addr>>8,addr&255,length))
    return data + bytes((sum(data[1:])&255,))


def entry_config():
    return {'read_only':True, 'identity': '20c2', 'software':'0103',
            'reference_protocol':'VS1/GFA P06,P09,P87,P80,P10,P84',
            'native_protocol':'P300 FC01/FC03',
            'gfa_rpm_formula':'P06_byte * 30 (0xff invalid)',
            'live_raw_p06_p300_alias_verified':False,
            'no_write':True,
            'phase_windows_s':{'VS1':VS1_WINDOW_S,'P300':P300_WINDOW_S},
            'known_p300_reads':[
                {'fc':fc,'address':f'0x{addr:04x}','length':n,'name':label,
                 'request_hex':frame(fc,addr,n).hex()} for fc,addr,n,label in ALL_READS],
            'physical_ram_scope':'selected previously read SRAM, not full dump',
            'uart1_u1rb_read':False}


class DeepWire:
    """Wrapper around the exact copied overnight UART1Wire with stricter phases.

    The delegate supplies framing, serial exact/quiet, trace streaming and the
    tested 2-ENQ vs1/p300 transport. Only the known fixed requests are added.
    """
    def __init__(self, delegate):
        self.w = delegate
        self.w.phase='vs1'
        self.phase='vs1'
        self.latest_p06=None

    def set_phase(self, phase):
        if phase not in ('vs1','entry','p300','recovery'):
            raise ValueError('bad phase')
        self.phase=phase
        self.w.phase=phase

    @staticmethod
    def permitted(phase, raw, base):
        vs1={b'\x04',b'\x01'+base.h.VS1_ID,base.h.VS1_ID,
             base.h.VS1_SOFTWARE,*base.h.GFA.values(),*EXTRA_GFA.values()}
        entry={b'\x04',b'\x16\x00\x00',b'\x06',base.h.P300_ID,base.h.P300_SOFTWARE}
        approved={
            'vs1':vs1,'recovery':vs1,'entry':entry,
            'p300':{frame(fc,addr,n) for fc,addr,n,_ in ALL_READS}|{b'\x06'}}
        return raw in approved.get(phase,set())

    def send(self, raw):
        base=load_local_base(Path(__file__).resolve().parent)
        if not self.permitted(self.phase,raw,base):
            raise base.Error('DEEP_TX_FORBIDDEN_IN_'+self.phase+':'+raw.hex())
        self.w.record('TX',raw)
        if self.w.port.write(raw)!=len(raw):
            raise base.Error('DEEP_SHORT_SERIAL_WRITE')

    def vs1_read(self, name):
        base=load_local_base(Path(__file__).resolve().parent)
        if self.phase not in ('vs1','recovery'):
            raise base.Error('GFA_READ_FORBIDDEN_OUTSIDE_VS1')
        req=base.h.GFA.get(name) or EXTRA_GFA.get(name)
        if req is None:
            raise base.Error('UNKNOWN_GFA_PARAMETER')
        begin=self.w.clock()
        self.w.gap()
        self.send(req)
        answer=self.w.exact(1,self.w.clock()+2.0)
        self.w.quiet()
        stamp=self.w.clock()
        value=answer[0]
        attempts=1
        # The historical GFA stream sometimes returns FF transiently.
        # One bounded re-read is already used by the pinned source helper.
        if value==0xFF and name=='P80':
            self.w.sleep(.150)
            self.w.gap()
            self.send(req)
            answer=self.w.exact(1,self.w.clock()+2.0)
            self.w.quiet()
            stamp=self.w.clock()
            value=answer[0]
            attempts=2
        if name=='P80' and value!=0x20:
            raise base.Error('WRONG_GFA_TYPE_P80')
        self.latest_p06=value if name=='P06' and value!=255 else self.latest_p06
        return {
            'key':name,'rx_utc':iso_utc(),'t_monotonic':stamp,
            'duration_ms':round((stamp-begin)*1000,3),
            'hex':answer.hex(),'valid':value!=255,
            'attempts':attempts,
            'rpm':value*30 if name=='P06' and value!=255 else None,
            'percentage':(round(value*0.3922,3) if name=='P09' and value!=255 else None),
            'not_an_actual_rpm': name=='P09'
        }

    def identify_vs1(self):
        base=load_local_base(Path(__file__).resolve().parent)
        self.w.enter_vs1(2)
        self.w.vs1(base.h.VS1_SOFTWARE,2,base.h.SOFTWARE)

    def identify_p300(self):
        self.set_phase('entry')
        self.w.enter_p300()
        self.set_phase('p300')

    def restore_final_gfa(self):
        """Use verified VS1 without new EOT; switch back only if in P300."""
        base=load_local_base(Path(__file__).resolve().parent)
        prior=self.phase
        self.set_phase('recovery')
        if prior!='vs1':
            self.identify_vs1()
        final=[self.vs1_read(k) for k in ('P80','P06','P09','P87')]
        if final[0]['hex']!='20':
            raise base.Error('FINAL_GFA_P80_NOT_20')
        return final

    def read_native(self, spec):
        base=load_local_base(Path(__file__).resolve().parent)
        if self.phase!='p300':
            raise base.Error('P300_READ_OUTSIDE_P300')
        fc,addr,n,name=spec
        request=frame(fc,addr,n)
        self.w.gap()
        before=self.w.clock()
        self.send(request)
        deadline=self.w.clock()+3.0
        if self.w.exact(1,deadline)!=b'\x06':
            raise base.Error('P300_REQUEST_ACK_MISSING')
        first=b'\x06'
        for _ in range(8):
            first=self.w.exact(1,deadline)
            if first!=b'\x06':
                break
        if first!=b'\x41':
            raise base.Error('P300_STX_BAD')
        size=self.w.exact(1,deadline)[0]
        if size!=5+n:
            raise base.Error('P300_SIZE_INCORRECT')
        body=self.w.exact(size+1,deadline)
        if len(body)!=size+1 or (size+sum(body[:-1]))&255 != body[-1]:
            raise base.Error('P300_CHECKSUM_BAD')
        if (body[0] !=1 or body[1]!=fc or int.from_bytes(body[2:4],'big')!=addr
                or body[4]!=n or len(body[5:-1])!=n):
            raise base.Error('P300_FC_ADDRESS_OR_COUNT_MISMATCH')
        self.send(b'\x06')
        self.w.quiet()
        return {'key':name,'fc':fc,'address':f'0x{addr:04x}',
                'length':n,'hex':body[5:-1].hex(),
                'rx_utc':iso_utc(),'t_monotonic':self.w.clock(),
                'duration_ms':round((self.w.clock()-before)*1000,3)}


def resource_guard(folder,files):
    if shutil.disk_usage(folder).free<MIN_DISK_BYTES:
        raise RuntimeError('LOW_DISK_GUARD')
    for stream in files:
        if stream and stream.tell()>MAX_SINGLE_LOG:
            raise RuntimeError('LOG_SIZE_GUARD')


def write_line(stream, value):
    stream.write(json.dumps(value,separators=(',',':'),sort_keys=True)+'\n')


def summarize_files(folder):
    """No unbounded materialization of multi-hour time series."""
    out={'vs1_rounds':0,'p300_rounds':0,'p06_valid_nonzero':0,'p06_valid_zero':0,
         'p06_invalid_ff':0,'gfa_p80_wrong_or_ff':0,'native_flame_samples':0,
         'native_lockout_samples':0,'p300_read_counts':Counter(),
         'p06_raw_histogram':Counter(),'p300_status_byte7_histogram':Counter(),
         'transition_count':0,'phase_switch_durations_s':[],
         'sample_errors':[],'production_approved':False,
         'p06_rpm_alias_verified':False,'device_write_approved':False}
    for name in ('vs1.jsonl','p300.jsonl','switches.jsonl'):
        f=folder/name
        if not f.exists():
            continue
        with f.open(encoding='utf-8') as stream:
            for line in stream:
                if not line.strip():continue
                row=json.loads(line)
                if name=='vs1.jsonl':
                    out['vs1_rounds']+=1
                    for item in row['reads']:
                        if item['key']=='P06':
                            if not item['valid']:out['p06_invalid_ff']+=1
                            else:
                                out['p06_raw_histogram'][item['hex']]+=1
                                if item['rpm']:out['p06_valid_nonzero']+=1
                                else:out['p06_valid_zero']+=1
                        if item['key']=='P80' and item['hex']!='20':
                            out['gfa_p80_wrong_or_ff']+=1
                elif name=='p300.jsonl':
                    out['p300_rounds']+=1
                    status=bytes.fromhex(row['reads']['native_55d3']['hex'])
                    out['native_flame_samples']+=int(bool(status[5]&FLAME_BIT))
                    out['native_lockout_samples']+=int(bool(status[5]&LOCKOUT_BIT))
                    out['p300_status_byte7_histogram'][f'{status[7]:02x}']+=1
                    for key in row['reads']:out['p300_read_counts'][key]+=1
                else:
                    out['transition_count']+=1
                    out['phase_switch_durations_s'].append(row['duration_s'])
    out['p300_read_counts']=dict(out['p300_read_counts'])
    out['p06_raw_histogram']=dict(out['p06_raw_histogram'])
    out['p300_status_byte7_histogram']=dict(out['p300_status_byte7_histogram'])
    intervals=out.pop('phase_switch_durations_s')
    out['phase_switch_seconds']={
        'count':len(intervals),'max':max(intervals) if intervals else None,
        'mean':round(sum(intervals)/len(intervals),4) if intervals else None}
    return out


def validate_state(session):
    if session.parent!=ROOT or session.is_symlink() or not session.name.startswith('run-'):
        raise RuntimeError('INVALID_SESSION_PATH')
    info=session.stat()
    if info.st_uid!=0 or info.st_mode&0o077:
        raise RuntimeError('SESSION_PERMISSIONS_UNSAFE')
    statefile=session/'state.json'
    if statefile.is_symlink() or not statefile.is_file():
        raise RuntimeError('INVALID_STATE')
    state=json.loads(statefile.read_text())
    base=load_local_base(session)
    if set(state['services'])!=set(base.h.SERVICES):
        raise RuntimeError('SERVICE_MANIFEST_CHANGED')
    if any(type(x) is not bool for x in state['services'].values()):
        raise RuntimeError('SERVICE_MANIFEST_NOT_BOOL')
    if any(u not in base.h.SERVICES for u in state['restore']):
        raise RuntimeError('UNTRUSTED_SERVICE_RESTORE_INTENT')
    if len(set(state['restore']))!=len(state['restore']):
        raise RuntimeError('DUPLICATE_SERVICE_RESTORE_INTENT')
    if not 1<=state['hours']<=MAX_HOURS:
        raise RuntimeError('INVALID_DURATION')
    for key, file in (('deep_sha256','logger.py'),('base_sha256','base.py'),
                      ('helper_sha256',HELPER_FILE)):
        check_hash(session/file,state[key])
    return state


def safe_isolation(base,port):
    base.isolation(port)


def run_worker(session):
    base=load_local_base(session)
    h=base.h
    state=validate_state(session)
    report={'version':VERSION,'session':session.name,'errors':[],
            'began_utc':iso_utc(),'ended_utc':None,'source':entry_config(),
            'requested_hours':state['hours'],'vs1_link_restored':False,
            'natural_flame_cycles':0,'operator_stop':False,
            'observation_finished':False,'p300_only_sensor_alias_proven':False,
            'writes_performed':False}
    handle=wire=None
    streams={}
    last_progress=time.monotonic()
    counter=Counter()
    last_flame=None
    flame_confirmed=False
    on_streak=0
    off_streak=0
    stop_latch=DeferredStop()
    for sig in (signal.SIGTERM,signal.SIGINT,signal.SIGHUP):
        signal.signal(sig,stop_latch.on_signal)
    def progress(phase,last=None):
        base.h.atomic_json(session/'progress.json',{
            'phase':phase,'last_sample_utc':iso_utc(),'elapsed_s':round(time.monotonic()-start,2),
            'target_s':state['hours']*3600,'gfa_vs1_rounds':counter['vs1'],
            'p300_rounds':counter['p300'],'switch_count':counter['switch'],
            'burner_flame_now':last_flame,'natural_flame_cycles':report['natural_flame_cycles'],
            'recent':last,'p06_last_raw_hex':(f'{wire.latest_p06:02x}' if wire and wire.latest_p06 is not None else None),
            'state':'RUNNING_READ_ONLY'},)
    def safety():
        safe_isolation(base,state['port'])
        resource_guard(session,streams.values())
    def switch(label, to_p300):
        phase_before=wire.phase
        t=time.monotonic()
        started_utc=iso_utc()
        if to_p300:
            wire.identify_p300()
        else:
            wire.set_phase('recovery')
            wire.identify_vs1()
            wire.set_phase('vs1')
        secs=round(time.monotonic()-t,4)
        write_line(streams['switches'],{'index':counter['switch']+1,
            'started_utc':started_utc,'finished_utc':iso_utc(),
            'from':phase_before,'to':wire.phase,'reason':label,'duration_s':secs,
            'switch_start_t_monotonic':t,
            'switch_end_t_monotonic':time.monotonic(),'safe_2_enq_vs1':True})
        counter['switch']+=1
        streams['switches'].flush()
        print('SWITCH=%d %s->%s DURATION_S=%.3f REASON=%s'%(
            counter['switch'],phase_before,wire.phase,secs,label),flush=True)
    def vs1_window():
        nonlocal last_progress
        wire.set_phase('vs1')
        phase_start=time.monotonic()
        rise_since=None
        last_zero=None
        while time.monotonic()-phase_start<VS1_WINDOW_S and time.monotonic()<deadline:
            stop_latch.check()  # only at a safe boundary between complete GFA reads
            now=time.monotonic()
            n=counter['vs1']+1
            reads=[wire.vs1_read('P06'),wire.vs1_read('P09'),
                   wire.vs1_read('P87'),wire.vs1_read('P06')]
            if n%10==1:
                reads.extend([wire.vs1_read('P10'),wire.vs1_read('P84'),
                              wire.vs1_read('P80')])
            invalid_p80=any(x['key']=='P80' and x['hex']!='20' for x in reads)
            if invalid_p80:
                raise base.Error('GFA_P80_TYPE_GUARD')
            p06=[x for x in reads if x['key']=='P06']
            last_vs1_read[0]=p06[-1]['t_monotonic']
            if all(x['valid'] for x in p06):
                if last_zero is None:
                    last_zero=p06[-1]['rpm']==0
                if last_zero and p06[-1]['rpm']>0 and rise_since is None:
                    rise_since=time.monotonic()
                last_zero=p06[-1]['rpm']==0
            row={'index':n,'utc_start':reads[0]['rx_utc'],'utc_end':iso_utc(),
                 'phase_elapsed_s':round(time.monotonic()-phase_start,3),
                 'read_time_clamp_ms':round((reads[-1]['t_monotonic']-reads[0]['t_monotonic'])*1000,3),
                 'reads':reads,'gfa_rpm_same_bracket':(
                     p06[0]['hex']==p06[1]['hex'] and all(x['valid'] for x in p06)),
                 'source':'VS1-GFA only; no simultaneous P300 data'}
            write_line(streams['vs1'],row)
            counter['vs1']+=1
            if n%40==0:streams['vs1'].flush()
            if time.monotonic()-last_progress>PROGRESS_EVERY_S:
                safety(); progress('VS1',{'index':n,'p06_hex':p06[-1]['hex']})
                last_progress=time.monotonic()
            # Triggered crossover: capture 6 seconds of real rising-P06 before P300.
            if rise_since is not None and time.monotonic()-rise_since>=6:
                return 'VS1_P06_RISE_AFTER_6S'
            wire.w.sleep(max(0,VS1_INTERVAL_S-(time.monotonic()-now)))
        return 'VS1_PHASE_TIMER'

    def p300_window():
        nonlocal last_progress,last_flame,on_streak,off_streak,flame_confirmed
        phase_start=time.monotonic()
        edge_time=None
        while time.monotonic()-phase_start<P300_WINDOW_S and time.monotonic()<deadline:
            stop_latch.check()  # never abort an in-flight P300 request or response
            t=time.monotonic()
            round_idx=counter['p300']+1
            results={}
            for spec in FAST_READS:
                item=wire.read_native(spec)
                results[item['key']]=item
            if round_idx%DETAIL_EVERY==1:
                for spec in SLOW_READS:
                    item=wire.read_native(spec)
                    results[item['key']]=item
            status=bytes.fromhex(results['native_55d3']['hex'])
            dma=bytes.fromhex(results['dma0']['hex'])
            if status[7]==255:
                raise base.Error('NATIVE_STATUS_FF')
            if (int.from_bytes(dma[4:7],'little')&0xfffff)!=0x03aa:
                raise base.Error('DMA0_TARGET_NOT_UART1_U1TB')
            flame=bool(status[5]&FLAME_BIT)
            lockout=bool(status[5]&LOCKOUT_BIT)
            if flame:
                on_streak+=1
                off_streak=0
                if on_streak>=3:flame_confirmed=True
            else:
                on_streak=0
                if flame_confirmed:
                    off_streak+=1
                    if off_streak>=3:
                        report['natural_flame_cycles']+=1
                        flame_confirmed=False
                        off_streak=0
            if last_flame is not None and last_flame!=flame and edge_time is None:
                edge_time=time.monotonic()
            last_flame=flame
            row={'index':round_idx,'utc_start':results['native_55d3']['rx_utc'],
                 'utc_end':iso_utc(),'phase_elapsed_s':round(time.monotonic()-phase_start,3),
                 'reads':results,'native_flame':flame,'native_lockout':lockout,
                 'native_p87_hex':f'{status[7]:02x}',
                 'native_11_bytes':list(status),
                 'dma0_sar0':f"0x{int.from_bytes(dma[:3],'little')&0xfffff:05x}",
                 'dma0_dar0':f"0x{int.from_bytes(dma[4:7],'little')&0xfffff:05x}",
                 'dma0_tcr0':int.from_bytes(dma[8:10],'little'),
                 'gfa_p06_during_p300':None,
                 'since_vs1_last_gfa_s':round(time.monotonic()-last_vs1_read[0],3)
                        if last_vs1_read[0] is not None else None}
            write_line(streams['p300'],row)
            counter['p300']+=1
            if round_idx%25==0:streams['p300'].flush()
            if time.monotonic()-last_progress>PROGRESS_EVERY_S:
                safety();progress('P300',{'index':round_idx,'flame':flame,
                                         'byte7':f'{status[7]:02x}'})
                last_progress=time.monotonic()
            # After first observed native flame edge, make prompt real-P06
            # reference, but retain 4 seconds of P300 status first.
            if edge_time is not None and time.monotonic()-edge_time>=4:
                return 'P300_FLAME_EDGE_PLUS_4S'
            wire.w.sleep(max(0,P300_INTERVAL_S-(time.monotonic()-t)))
        return 'P300_PHASE_TIMER'
    last_vs1_read=[None]
    start=time.monotonic()
    deadline=start+state['hours']*3600
    try:
        current=h.read_settings(h.SETTINGS.read_text())
        if current['port_optolink']!=state['port']:
            raise base.Error('SERIAL_PATH_CHANGED')
        if h.unit_state(h.MAIN).get('WorkingDirectory')!='/opt/optolink':
            raise base.Error('PRODUCTION_PATH_CHANGED')
        for service,previous in state['services'].items():
            active=h.unit_state(service).get('ActiveState')=='active'
            if active!=previous:raise base.Error('SERVICE_STATE_CHANGED_'+service)
        h.pause_services(session,state)
        safe_isolation(base,state['port'])
        handle=h.open_serial(state['port'])
        for filename,key in (('vs1.jsonl','vs1'),('p300.jsonl','p300'),
                             ('switches.jsonl','switches'),('trace.jsonl','trace')):
            streams[key]=(session/filename).open('x',encoding='utf-8')
        delegate=base.UART1Wire(handle)
        delegate.trace_sink=streams['trace']
        wire=DeepWire(delegate)
        # Replace only transmit method; all RX exact/quiet remains from vetted base.
        delegate.send=wire.send
        wire.identify_vs1()
        ref=[wire.vs1_read(k) for k in ('P80','P06','P09','P87')]
        if ref[0]['hex']!='20':
            raise base.Error('INITIAL_GFA_IDENTITY_NOT_20')
        report['initial_gfa']=ref
        print('DEEP_LOGGER_STARTED=VS1_REFERENCE_ALTERNATING_P300',flush=True)
        progress('VS1')
        while time.monotonic()<deadline:
            stop_latch.check()
            safety()
            reason=vs1_window()
            if time.monotonic()>=deadline:break
            switch(reason,True)
            reason=p300_window()
            if time.monotonic()>=deadline:break
            switch(reason,False)
        report['observation_finished']=True
    except BaseException as exc:
        if str(exc)=='OPERATOR_STOP_SIGNAL_15':
            report['operator_stop']=True
            report['observation_finished']=True
        else:
            report['errors'].append(str(exc) or type(exc).__name__)
    finally:
        for sig in (signal.SIGTERM,signal.SIGINT,signal.SIGHUP):
            signal.signal(sig,signal.SIG_IGN)
        if wire:
            try:
                # Old SIGTERM handler cut P10 before RX; defer stop until a
                # completed read and avoid EOT when VS1 is already verified.
                final=wire.restore_final_gfa()
                report['final_gfa']=final
                report['vs1_link_restored']=True
            except BaseException as exc:
                report['errors'].append('VS1_RECOVERY:'+str(exc))
            try:
                wire.w.flush_trace()
                report['trace_count']=wire.w.trace_records_written
            except BaseException as exc:
                report['errors'].append('TRACE_FLUSH:'+str(exc))
        for k,stream in streams.items():
            try:
                stream.flush()
                os.fsync(stream.fileno())
                stream.close()
            except BaseException as exc:
                report['errors'].append('LOG_CLOSE_'+k+':'+str(exc))
        if handle:
            try:handle.close()
            except BaseException as exc:report['errors'].append('SERIAL_CLOSE:'+str(exc))
        report['duration_s']=round(time.monotonic()-start,3)
        report['ended_utc']=iso_utc()
        report['counts']=dict(counter)
        try:
            report['comparison']=summarize_files(session)
        except BaseException as exc:
            report['errors'].append('POST_SUMMARY:'+str(exc))
        h.atomic_json(session/'measurement.json',report)
        try:
            h.atomic_json(session/'progress.json',{
                'state':'WORKER_EXITED_RECOVERY_PENDING',
                'ended_utc':report['ended_utc'],
                'actual_duration_s':report['duration_s'],
                'counts':report['counts'],
                'natural_flame_cycles':report['natural_flame_cycles'],
                'worker_vs1_restored':report['vs1_link_restored'],
                'worker_errors':report['errors']})
        except BaseException as exc:
            report['errors'].append('FINAL_PROGRESS:'+str(exc))
            h.atomic_json(session/'measurement.json',report)
    return 0 if report['vs1_link_restored'] and report['observation_finished'] and not report['errors'] else 1


def worker(session):
    base=load_local_base(session)
    with base.locks():
        return run_worker(session)


def post_restore_health(base):
    """A formatted FF is not a real fan-speed sample or a positive health gate."""
    health=base.post_restore_health()
    p06=health.get('gfa_reads',{}).get('P06')
    if not p06:
        return health
    def decode_non_ff(text):
        found=re.findall(r'1;0x4006;([0-9a-fA-F]{2})\b',text or '',re.I)
        return bool(found) and found[-1].lower()!='ff'
    non_ff=(p06.get('returncode')==0 and decode_non_ff(p06.get('stdout','')))
    p06['p06_non_ff_verified']=non_ff
    if not non_ff and health.get('production_main_verified'):
        # One bounded read-only MQTT retry after a historically observed FF.
        try:
            time.sleep(.150)
            proc=subprocess.run(
                ['optolink-debug','request','gfaread;0x4006;1;raw;False',
                 '--timeout','8'],
                capture_output=True,text=True,timeout=14,check=False)
            p06['retry_returncode']=proc.returncode
            p06['retry_stdout']=proc.stdout[-600:]
            p06['retry_stderr']=proc.stderr[-300:]
            non_ff=proc.returncode==0 and decode_non_ff(proc.stdout)
            p06['p06_non_ff_verified']=non_ff
        except (OSError,subprocess.TimeoutExpired) as exc:
            p06['retry_error']=str(exc)
    p06['format_and_identity_verified']=bool(
        p06.get('format_and_identity_verified') and p06['p06_non_ff_verified'])
    health['gfa_p06_actual_rpm_quality_verified']=p06['format_and_identity_verified']
    return health


def bundle(session,base):
    if ROOT.is_symlink() or BUNDLES.is_symlink():
        raise RuntimeError('SESSION_OR_BUNDLE_SYMLINK')
    BUNDLES.mkdir(parents=True,exist_ok=True,mode=0o700)
    os.chmod(BUNDLES,0o700)
    path=BUNDLES/('p300-deep-'+session.name+'-bundle.tar.gz')
    if path.exists() or path.is_symlink():
        if path.is_symlink() or not path.is_file():
            raise RuntimeError('UNSAFE_EXISTING_BUNDLE')
        return path
    names=['state.json','progress.json','vs1.jsonl','p300.jsonl',
           'switches.jsonl','trace.jsonl','measurement.json',
           'recovery.json','health.json','logger.py','base.py',HELPER_FILE]
    hashes={}
    for name in names:
        f=session/name
        if not f.exists():
            continue
        inf=f.lstat()
        if not stat.S_ISREG(inf.st_mode) or inf.st_uid!=0 or inf.st_mode&0o077:
            raise RuntimeError('UNSAFE_BUNDLE_MEMBER_'+name)
        dig=hashlib.sha256()
        with f.open('rb') as reader:
            for block in iter(lambda:reader.read(1024*1024),b''):
                dig.update(block)
        hashes[name]={'sha256':dig.hexdigest(),'size_bytes':inf.st_size}
    manifest={'version':VERSION,'files':hashes,'session':session.name,
              'read_only':True,'gfa_p06_rpm_alias_verified':False,
              'production_p300_approved':False,'ram_write_approved':False,
              'source':entry_config()}
    temp=None
    try:
        with tempfile.NamedTemporaryFile(prefix='p300-deep-',suffix='.tar.gz',
                                         dir=BUNDLES,delete=False) as tmp:
            temp=Path(tmp.name)
        os.chmod(temp,0o600)
        with tarfile.open(temp,'w:gz') as tar:
            for name in hashes:
                tar.add(session/name,arcname='p300-deep/'+name,recursive=False)
            encoded=(json.dumps(manifest,indent=2,sort_keys=True)+'\n').encode()
            item=tarfile.TarInfo('p300-deep/bundle-manifest.json')
            item.size=len(encoded);item.mode=0o600;item.mtime=0
            tar.addfile(item,io.BytesIO(encoded))
        temp.rename(path)
    except BaseException:
        if temp:temp.unlink(missing_ok=True)
        raise
    return path


def recover(session):
    base=load_local_base(session)
    state=validate_state(session)
    h=base.h
    errs=[];restored=[]
    with base.locks():
        if state['restore']:
            try:
                if h.MAIN in state['restore']:
                    h.command(['systemctl','start',h.MAIN])
                h.wait_main_ready()
                if h.MAIN in state['restore']:restored.append(h.MAIN)
            except BaseException as exc:
                errs.append('VS1_MAIN_NOT_READY_DEFER_HELPERS:'+str(exc))
        if not errs:
            for name in reversed(state['restore']):
                if name==h.MAIN:continue
                try:
                    h.command(['systemctl','start',name])
                    if name!='optolink-clock-sync.service' and h.unit_state(name).get('ActiveState')!='active':
                        raise RuntimeError('SERVICE_NOT_ACTIVE_'+name)
                    restored.append(name)
                except BaseException as exc:
                    errs.append(name+':'+str(exc))
        h.atomic_json(session/'recovery.json',{
            'services_restored':not errs,'restored_units':restored,
            'errors':errs,'ha_entity_freshness_verified':False,
            'systemd_result':os.environ.get('SERVICE_RESULT','unknown')})
    try:
        health=post_restore_health(base)
        h.atomic_json(session/'health.json',health)
        path=session/'progress.json'
        state_progress=json.loads(path.read_text()) if path.is_file() else {}
        state_progress['state']=('RESTORED' if not errs else 'RESTORE_NOT_VERIFIED')
        state_progress['restored_utc']=iso_utc()
        state_progress['service_restore_verified']=not errs
        state_progress['post_restore_p06_non_ff_verified']=bool(
            health.get('gfa_reads',{}).get('P06',{}).get('p06_non_ff_verified'))
        h.atomic_json(path,state_progress)
        output=bundle(session,base)
        print('UPLOAD_ONE_FILE='+str(output),flush=True)
    except BaseException as exc:
        errs.append('ARCHIVE_OR_HEALTH:'+str(exc))
        print('RECOVERY_ARCHIVE_ERROR='+str(exc),flush=True)
    return int(bool(errs))


def verify_competing_services(base):
    for unit in (UNIT,*SELF_NAMED_SERVICE_UNITS):
        if base.h.unit_state(unit).get('ActiveState') not in ('inactive','failed'):
            raise RuntimeError('COMPETING_PROBE_ACTIVE_'+unit)


def start(hours):
    base=load_local_base(PROJECT/'tools')
    h=base.h
    if os.geteuid()!=0:
        raise RuntimeError('ROOT_REQUIRED')
    if type(hours) is not int or not 1<=hours<=MAX_HOURS:
        raise ValueError('HOURS_MUST_BE_1_TO_8')
    if PROJECT.is_symlink() or ROOT.is_symlink() or BUNDLES.is_symlink():
        raise RuntimeError('UNEXPECTED_SYMLINK')
    with base.locks():
        values,services=h.preflight()
        verify_competing_services(base)
        if shutil.disk_usage(PROJECT).free<MIN_DISK_BYTES:
            raise RuntimeError('PREFLIGHT_INSUFFICIENT_FREE_DISK')
        ROOT.mkdir(parents=True,exist_ok=True,mode=0o700)
        os.chmod(ROOT,0o700)
        for old in ROOT.glob('run-*/state.json'):
            rec=old.with_name('recovery.json')
            previous=json.loads(old.read_text())
            if previous.get('restore') and (not rec.exists() or
                    not json.loads(rec.read_text()).get('services_restored')):
                raise RuntimeError('PREVIOUS_UNRESOLVED_RECOVERY_'+old.parent.name)
        stamp=dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
        session=ROOT/('run-'+stamp+'-'+str(os.getpid()))
        session.mkdir(mode=0o700)
        copies={
            'logger.py':Path(__file__).resolve(),
            'base.py':PROJECT/'tools'/BASE_FILE,
            HELPER_FILE:PROJECT/'tools'/HELPER_FILE}
        fingerprints={}
        for name,source in copies.items():
            if not source.is_file() or source.is_symlink():
                raise RuntimeError('SOURCE_NOT_REGULAR_'+name)
            shutil.copyfile(source,session/name)
            os.chmod(session/name,0o600)
            fingerprints[name]=hashlib.sha256((session/name).read_bytes()).hexdigest()
        state={'version':VERSION,'hours':hours,'services':services,'restore':[],
               'port':values['port_optolink'],'deep_sha256':fingerprints['logger.py'],
               'base_sha256':fingerprints['base.py'],
               'helper_sha256':fingerprints[HELPER_FILE],
               'read_allowlist':entry_config(),'source_checkout_sha':None}
        h.atomic_json(session/'state.json',state)
    cmd=['systemd-run','--unit='+UNIT,'--no-block','--collect',
         '--property=Type=exec','--property=Restart=no',
         '--property=TimeoutStopSec=300','--property=KillMode=control-group',
         '--property=UMask=0077',
         f'--property=ExecStopPost={PYTHON} -u {session}/logger.py --recover {session}',
         PYTHON,'-u',str(session/'logger.py'),'--worker',str(session)]
    proc=subprocess.run(cmd,check=False,capture_output=True,text=True,timeout=30)
    if proc.returncode!=0:
        raise RuntimeError('SYSTEMD_START_REJECTED:'+proc.stderr[-500:])
    print('SESSION='+str(session),flush=True)
    print('SYSTEMD_LOGGER_START_ACCEPTED='+UNIT,flush=True)
    print('MAX_HOURS='+str(hours),flush=True)
    print('STATUS_CMD=bash '+str(PROJECT/'tools'/'wb2a-p300-deep-logger.sh')+' status',flush=True)
    print('STOP_CMD=bash '+str(PROJECT/'tools'/'wb2a-p300-deep-logger.sh')+' stop',flush=True)
    return 0


def latest_session():
    if ROOT.is_symlink() or not ROOT.is_dir():
        raise RuntimeError('NO_DEEP_LOGGER_SESSION')
    dirs=sorted(x for x in ROOT.glob('run-*') if x.is_dir() and not x.is_symlink())
    if not dirs:raise RuntimeError('NO_DEEP_LOGGER_SESSION')
    return dirs[-1]


def status():
    base=load_local_base(PROJECT/'tools')
    session=latest_session()
    unit=base.h.unit_state(UNIT)
    p=session/'progress.json'
    info=json.loads(p.read_text()) if p.is_file() else {'state':'STARTING'}
    print('SESSION='+str(session))
    print('UNIT_ACTIVE='+unit.get('ActiveState','unknown'))
    print('PROGRESS='+json.dumps(info,sort_keys=True))
    if (session/'recovery.json').is_file():
        print('RECOVERY='+ (session/'recovery.json').read_text().strip())
    return 0


def stop():
    base=load_local_base(PROJECT/'tools')
    h=base.h
    session=latest_session()
    old=h.unit_state(UNIT)
    if old.get('ActiveState') in ('active','activating','deactivating'):
        proc=subprocess.run(['systemctl','stop',UNIT],capture_output=True,text=True,
                            check=False,timeout=360)
        if proc.returncode:
            print('SYSTEMD_STOP_ERROR='+proc.stderr[-500:],flush=True)
    elif old.get('ActiveState') not in ('inactive','failed'):
        raise RuntimeError('UNEXPECTED_SERVICE_STATE')
    for _ in range(45):
        if (session/'recovery.json').is_file() and (session/'health.json').is_file():
            break
        time.sleep(1)
    rec=json.loads((session/'recovery.json').read_text()) if (session/'recovery.json').is_file() else {}
    measurement=json.loads((session/'measurement.json').read_text()) if (session/'measurement.json').is_file() else {}
    health=json.loads((session/'health.json').read_text()) if (session/'health.json').is_file() else {}
    archive=bundle(session,base)
    restored=bool(rec.get('services_restored'))
    valid_readback=bool(health.get('production_main_verified')) and all(
        health.get('gfa_reads',{}).get(name,{}).get('format_and_identity_verified')
        for name in ('P80','P06'))
    print('SESSION='+str(session),flush=True)
    print('SERVICE_RESTORE='+('PASS' if restored else 'NOT_VERIFIED'),flush=True)
    print('VS1_LINK_RESTORE='+('PASS' if measurement.get('vs1_link_restored') else 'NOT_VERIFIED'),flush=True)
    print('VS1_P80_P06_HEALTH='+('PASS' if valid_readback else 'NOT_VERIFIED'),flush=True)
    print('COUNTS='+json.dumps(measurement.get('comparison',{}),sort_keys=True),flush=True)
    print('UPLOAD_ONE_FILE='+str(archive),flush=True)
    return 0 if restored and valid_readback else 1


def main():
    p=argparse.ArgumentParser(description=__doc__)
    g=p.add_mutually_exclusive_group()
    g.add_argument('--start',action='store_true')
    g.add_argument('--stop',action='store_true')
    g.add_argument('--status',action='store_true')
    g.add_argument('--worker',type=Path)
    g.add_argument('--recover',type=Path)
    p.add_argument('--hours',type=int,default=DEFAULT_HOURS)
    args=p.parse_args()
    if args.worker or args.recover:
        if os.geteuid()!=0 or 'INVOCATION_ID' not in os.environ:
            p.error('worker/recover require supervised root systemd')
        return worker(args.worker) if args.worker else recover(args.recover)
    if args.start:return start(args.hours)
    if args.stop:return stop()
    if args.status:return status()
    print('PLAN ONLY: '+VERSION)
    print('Alternating VS1 50s real GFA P06/P09/P87 with P300 75s status/DMA/selected proven SRAM.')
    print('Status and read-only physical memory only. No U1RB, guessed fan-alias, or device writes.')
    print('Four-hour maximum by default, operator stop anytime; original VS1 services auto restored.')
    print('P300 samples are NOT concurrent with VS1 GFA readings.')
    return 0


if __name__=='__main__':
    try:raise SystemExit(main())
    except (RuntimeError,ValueError,OSError,subprocess.SubprocessError) as exc:
        print('REFUSED_OR_FAILED='+str(exc),file=sys.stderr)
        raise SystemExit(1)
