"""Strictly offline analysis of completed WB2A handover campaign evidence.

This program NEVER opens a port, imports pySerial, reads current MQTT state,
starts services, or sends commands to the controller. Session files are
existing immutable measurements from a previously completed supervised run.

Focus: inclusive-vs-excluded idle costs, EOT/ENQ timing, and the surprising
second-EOT observation after each *failed* early handshake experiment.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from statistics import mean, median


class EvidenceError(ValueError):
    pass


def _number(item, name: str) -> float:
    if type(item) not in (int, float) or not math.isfinite(item):
        raise EvidenceError(name + ' must be a finite number')
    return float(item)


def _valid_run(state: dict, *, accepted_result: str, experiment: str):
    if not isinstance(state, dict):
        raise EvidenceError('summary is not an object')
    if state.get('experiment') != experiment:
        raise EvidenceError('unexpected experiment type')
    if state.get('result') != accepted_result:
        raise EvidenceError('unexpected result status')
    if state.get('services_restored') is not True or state.get('recovery_errors') != []:
        raise EvidenceError('production service recovery not verified')
    recovery = state.get('independent_recovery')
    if not isinstance(recovery, dict) or recovery.get('verified') is not True:
        raise EvidenceError('independent restore proof unavailable')


PHASE_LABELS = ('control_a','vs1_idle_400','vs1_idle_1100',
                'p300_idle_400','p300_idle_1100','both_idle_700','control_b')
PHASE_IDLES = ((0,0),(400,0),(1100,0),(0,400),(0,1100),(700,700),(0,0))


def summarize_sweep(summary: dict) -> dict:
    _valid_run(summary, accepted_result='PASS_VERIFIED_READ_ONLY_PHASE_SWEEP',
               experiment='phase_sweep')
    if summary.get('measurement_errors') != []:
        raise EvidenceError('phase sweep had measurement errors')
    trials=summary.get('trials')
    if not isinstance(trials, list) or len(trials) != 7:
        raise EvidenceError('seven verified rounds required')
    normalized=[]
    for x, (label,(expected_vs1,expected_p300)) in enumerate(zip(PHASE_LABELS,PHASE_IDLES)):
        t=trials[x]
        if not isinstance(t,dict) or t.get('label')!=label or t.get('verified') is not True:
            raise EvidenceError('missing verified '+label)
        if t.get('vs1_idle_ms')!=expected_vs1 or t.get('p300_idle_ms')!=expected_p300:
            raise EvidenceError('incorrect idle budget '+label)
        ms={key:_number(t.get(key),key) for key in
            ('handover_and_gfa_ms','p300_eot_enq_ms','vs1_eot_enq_ms',
             'to_p300_ms','to_vs1_ms','full_elapsed_after_vs1_idle_ms')}
        if any(v<=0 or v>30000 for v in ms.values()):
            raise EvidenceError('out of bounds time at '+label)
        if abs(ms['full_elapsed_after_vs1_idle_ms']-(ms['handover_and_gfa_ms']+expected_p300))>5:
            raise EvidenceError('partial inclusive time inconsistent at '+label)
        gfa=t.get('gfa')
        if not isinstance(gfa,dict) or gfa.get('P80')!='20' or not isinstance(gfa.get('P06'),str) or len(gfa['P06'])!=2 or gfa['P06'].lower()=='ff' or any(char not in '0123456789abcdefABCDEF' for char in gfa['P06']):
            raise EvidenceError('missing verified GFA at '+label)
        core=ms['handover_and_gfa_ms']
        incl=core+expected_vs1+expected_p300
        normalized.append({'label':label, 'core_ms':round(core,3),
                           'total_including_both_idle_ms':round(incl,3),
                           'p300_eot_enq_ms':ms['p300_eot_enq_ms'],
                           'vs1_eot_enq_ms':ms['vs1_eot_enq_ms'],
                           'vs1_idle_ms':expected_vs1,'p300_idle_ms':expected_p300})
    cores=[x['core_ms'] for x in normalized]
    inclusive=[x['total_including_both_idle_ms'] for x in normalized]
    enq=[x['p300_eot_enq_ms']+x['vs1_eot_enq_ms'] for x in normalized]
    best_core=min(normalized,key=lambda t:t['core_ms'])
    best_inclusive=min(normalized,key=lambda t:t['total_including_both_idle_ms'])
    return {'sample_count':len(normalized), 'trials':normalized,
            'core_mean_ms':round(mean(cores),3),'core_median_ms':round(median(cores),3),
            'core_min_ms':min(cores),'core_max_ms':max(cores),
            'inclusive_mean_ms':round(mean(inclusive),3),
            'best_core_label':best_core['label'],
            'best_inclusive_label':best_inclusive['label'],
            'mean_two_enq_waits_ms':round(mean(enq),3),
            'mean_non_enq_budget_ms':round(mean(a-b for a,b in zip(cores,enq)),3),
            'non_enq_cannot_all_be_removed': True,
            'warning':'Previous VS1 idle times must be included in actual wall time; the name full_elapsed_after_vs1_idle_ms excludes those times.'}


def trace_early_attempt(summary: dict, expected_experiment: str) -> dict:
    if expected_experiment not in ('early_p300_start','early_vs1_identity'):
        raise EvidenceError('unsupported early experiment')
    _valid_run(summary,accepted_result='FAIL_OR_NOT_VERIFIED',experiment=expected_experiment)
    errors=summary.get('measurement_errors')
    if not isinstance(errors,list) or len(errors)!=1:
        raise EvidenceError('expected exactly one clear negative-experiment error')
    if expected_experiment=='early_p300_start':
        if not errors[0].startswith('ProtocolError: RX deadline'):
            raise EvidenceError('unexpected P300 failure type')
    else:
        if errors[0]!='ProtocolError: EARLY_VS1_NO_IDENTITY_WITHIN_350MS':
            raise EvidenceError('unexpected early VS1 failure type')
    trace=summary.get('enq_trace')
    if not isinstance(trace,list) or len(trace)<3:
        raise EvidenceError('ENQ trace missing')
    pairs=[]
    for before,after in zip(trace,trace[1:]):
        if (isinstance(before,dict) and isinstance(after,dict) and
                before.get('enq_wait_ms')==[] and
                isinstance(after.get('enq_wait_ms'),list) and
                len(after['enq_wait_ms'])==2):
            first=_number(before.get('eot_t_monotonic'),'first EOT timestamp')
            second=_number(after.get('eot_t_monotonic'),'recovery EOT timestamp')
            recovery_enq=_number(after['enq_wait_ms'][0],'recovery ENQ wait')
            follow_enq=_number(after['enq_wait_ms'][1],'second recovery ENQ wait')
            if not first < second or not 0 < recovery_enq < follow_enq:
                raise EvidenceError('invalid EOT/ENQ chronology')
            delta=(second-first)*1000
            pairs.append({'experiment':expected_experiment,
                          'first_eot_to_recovery_eot_ms':round(delta,3),
                          'recovery_eot_to_first_enq_ms':round(recovery_enq,3),
                          'first_eot_to_first_observed_enq_ms':round(delta+recovery_enq,3),
                          'first_eot_to_second_observed_enq_ms':round(delta+follow_enq,3),
                          'eot_retransmission_delayed_nominal_enq_by_ms':round(delta+recovery_enq-2000,3)})
    if len(pairs)!=1:
        raise EvidenceError('expected exactly one early-EOT / recovery-EOT pair')
    return pairs[0]


def summarize_campaign(sweep: dict, vs1_early: dict, p300_early: dict|None=None) -> dict:
    phase=summarize_sweep(sweep)
    vs1=trace_early_attempt(vs1_early,'early_vs1_identity')
    results=[vs1]
    if p300_early is not None:
        results.insert(0,trace_early_attempt(p300_early,'early_p300_start'))
    return {'verdict':'NO_VALIDATED_SUB_4_SECOND_HANDOVER',
            'research_note':'Both tested early-before-ENQ commands were negative with service restoration. Do not infer impossibility of all other handshakes.',
            'phase_sweep':phase,'early_eot_observations':results,
            'sync_interpretation': ('When the second EOT was sent after about 376 ms, the first ENQ was still observed about 1998 ms after the first EOT. '
                                    'This is evidence of a continuing handshake cadence in those runs, not proof of a firmware-fixed timing rule.'),
            'test_scope':'EXISTING_ARCHIVED_RESULTS_ONLY_NO_SERIAL_NO_SERVICE_CHANGES'}


def _session_data(path:Path, *, require_recovery_json:bool=False) -> dict:
    if path.is_symlink() or not path.is_dir():
        raise EvidenceError('missing/symlink session directory: '+str(path))
    source=path/'summary.json'
    if source.is_symlink():
        raise EvidenceError('refusing symlink summary')
    try:
        summary=json.loads(source.read_text(encoding='utf-8'))
    except (OSError, ValueError) as exc:
        raise EvidenceError('invalid/missing saved summary: '+str(source)) from exc
    if require_recovery_json:
        recovery_file=path/'recovery.json'
        if recovery_file.is_symlink():
            raise EvidenceError('refusing symlink recovery file')
        try:
            recovery=json.loads(recovery_file.read_text(encoding='utf-8'))
        except (OSError,ValueError) as exc:
            raise EvidenceError('missing/invalid recovery.json: '+str(recovery_file)) from exc
        if (not isinstance(recovery,dict) or recovery.get('overall_verified') is not True
                or recovery.get('services_restored') is not True or recovery.get('errors') != []
                or not isinstance(recovery.get('independent_link_restore'),dict)
                or recovery['independent_link_restore'].get('verified') is not True):
            raise EvidenceError('unverified supervisor restore: '+str(recovery_file))
    return summary


def load_campaign(directory:Path) -> tuple[dict,dict]:
    if directory.is_symlink() or not directory.is_dir():
        raise EvidenceError('missing/symlink campaign directory')
    if (directory/'campaign.json').is_symlink():
        raise EvidenceError('refusing symlink campaign.json')
    try:
        campaign=json.loads((directory/'campaign.json').read_text(encoding='utf-8'))
    except (OSError,ValueError) as exc:
        raise EvidenceError('invalid campaign.json') from exc
    if campaign.get('result')!='EARLY_VS1_NEGATIVE_BUT_RESTORED':
        raise EvidenceError('this analysis requires completed negative but restored campaign')
    stages=campaign.get('stages')
    if not isinstance(stages,list) or len(stages)!=2 or [x.get('stage') for x in stages]!=['phase_sweep','early_vs1_identity']:
        raise EvidenceError('campaign stages do not match real experiment')
    if stages[0].get('classification')!='VERIFIED_SUCCESS' or stages[1].get('classification')!='HYPOTHESIS_NEGATIVE_RESTORED':
        raise EvidenceError('campaign evidence not sufficiently verified')
    if any(s.get('production_health_pass') is not True for s in stages):
        raise EvidenceError('campaign did not verify both production-health gates')
    outputs=[]
    for st in stages:
        target=Path(st['session'])
        if target.parent!=directory.parent or target.name.startswith('run-') is False:
            raise EvidenceError('unexpected session location')
        outputs.append(_session_data(target,require_recovery_json=True))
    return tuple(outputs)


def main(argv:list[str]|None=None) -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--campaign',type=Path,required=True)
    parser.add_argument('--early-p300-session',type=Path,default=None)
    args=parser.parse_args(argv)
    sweep,early_vs1=load_campaign(args.campaign)
    early_p300=_session_data(args.early_p300_session) if args.early_p300_session else None
    result=summarize_campaign(sweep,early_vs1,early_p300)
    print('OFFLINE_FORENSICS='+json.dumps(result,sort_keys=True))
    print('OFFLINE_FORENSICS_RESULT=COMPLETE_NO_HARDWARE_USED')
    return 0


if __name__=='__main__':
    try:
        raise SystemExit(main())
    except EvidenceError as exc:
        print('OFFLINE_FORENSICS_ERROR='+str(exc))
        raise SystemExit(1)
