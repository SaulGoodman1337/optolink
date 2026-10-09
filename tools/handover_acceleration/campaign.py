#!/usr/bin/env python3
"""Supervised WB2A read-only research campaign: phase sweep + ONE novel trial.

Default is plan-only. Explicit --execute --accept-telemetry-pause required.
Every physical stage calls the independently supervised live_probe entrypoint,
restores original services, and is followed by a fresh *MQTT-only* health gate.
A failure in the known-protocol stage or restoration always blocks the next
stage. An unsuccessful speculative early-VS1 reply is a negative scientific
observation, not a license to try any other unknown telegram.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
from pathlib import Path
import subprocess
import sys

try:
    from . import live_probe as live
except ImportError:
    import live_probe as live


class CampaignError(RuntimeError):
    pass


def interpret_stage(summary: dict, recovery: dict, rc: int,
                    *, speculative: bool = False) -> str:
    """Separate failed scientific hypothesis from *failure to restore*.

    For a negative, insist on independent recovery report AND an error trace.
    A failed `systemd-run` or absent recovery is never a valid observation.
    """
    restored = (recovery.get('services_restored') is True and
                recovery.get('overall_verified') is True and
                recovery.get('errors') == [] and
                isinstance(recovery.get('independent_link_restore'), dict) and
                recovery['independent_link_restore'].get('verified') is True and
                summary.get('services_restored') is True and
                summary.get('recovery_errors') == [])
    if not restored:
        return 'UNVERIFIED_RESTORE_STOP'
    if (rc == 0 and summary.get('result', '').startswith('PASS_VERIFIED_')
            and not summary.get('measurement_errors')):
        return 'VERIFIED_SUCCESS'
    if (speculative and rc != 0 and summary.get('result') == 'FAIL_OR_NOT_VERIFIED'
            and summary.get('experiment') == 'early_vs1_identity'
            and summary.get('measurement_errors')
            and summary.get('unit_rc') != 0):
        # Check for an expected identity/no-answer failure; unexpected
        # signals and arbitrary errors do not count as useful negatives.
        errors = summary['measurement_errors']
        if len(errors) == 1 and any(mark in errors[0] for mark in
           ('EARLY_VS1_NO_IDENTITY_WITHIN_350MS',
            'EARLY_VS1_WRONG_IDENTITY', 'EARLY_VS1_WRONG_SOFTWARE',
            'EARLY_VS1_P80_MISMATCH', 'EARLY_VS1_P06_FF')):
            return 'HYPOTHESIS_NEGATIVE_RESTORED'
    return 'INCONCLUSIVE_STOP'


def summarize_phase_effect(trials: list[dict]) -> dict:
    """Produce bounded facts, no firmware timers or statistical proof."""
    if not isinstance(trials, list) or len(trials) != len(live.PHASE_SWEEP):
        raise CampaignError('wrong number of phase-sweep trials')
    expected_labels = [x[0] for x in live.PHASE_SWEEP]
    if [x.get('label') for x in trials] != expected_labels:
        raise CampaignError('trial order or identity mismatch')
    for trial in trials:
        if trial.get('verified') is not True:
            raise CampaignError('a phase-sweep trial was not verified')
        for key in ('p300_eot_enq_ms','vs1_eot_enq_ms',
                    'to_p300_ms','to_vs1_ms'):
            value=trial.get(key)
            if type(value) not in (int,float) or not 0 < value < 20000:
                raise CampaignError('invalid measured timing: '+key)
    p300_waits=[x['p300_eot_enq_ms'] for x in trials]
    vs1_waits=[x['vs1_eot_enq_ms'] for x in trials]
    p300_span=max(p300_waits)-min(p300_waits)
    vs1_span=max(vs1_waits)-min(vs1_waits)
    return dict(
        trial_count=len(trials),
        p300_enq_wait_min_ms=round(min(p300_waits),3),
        p300_enq_wait_max_ms=round(max(p300_waits),3),
        p300_enq_spread_ms=round(p300_span,3),
        vs1_enq_wait_min_ms=round(min(vs1_waits),3),
        vs1_enq_wait_max_ms=round(max(vs1_waits),3),
        vs1_enq_spread_ms=round(vs1_span,3),
        potential_phase_dependency=(p300_span>250 or vs1_span>250),
        interpretation=('PHASE_DEPENDENCE_CANDIDATE_ONLY' if
                        (p300_span>250 or vs1_span>250) else
                        'NO_LARGE_PHASE_EFFECT_IN_THIS_SMALL_SAMPLE'),
        note=('Host RX timestamps and seven measurements do not establish '
              'a controller firmware timer or a guaranteed faster handshake.'))


def run_and_capture(command: list[str]) -> tuple[int, str | None]:
    """Mirror subprocess output in real time and capture exact session ID."""
    session=None
    with subprocess.Popen(command, stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT, text=True, bufsize=1) as proc:
        assert proc.stdout is not None
        for line in proc.stdout:
            print(line, end='', flush=True)
            if line.startswith('SESSION='):
                candidate=line.split('=',1)[1].strip()
                if candidate:
                    session=candidate
        status=proc.wait()
    return status, session


def stage_evidence(session_path: str | None) -> tuple[dict,dict]:
    if not session_path:
        raise CampaignError('supervisor did not disclose a session')
    path=Path(session_path)
    # Don't accept an arbitrary path printed by a different process.
    if (path.parent != live.BASE_DIR or not path.name.startswith('run-')
            or path.is_symlink()):
        raise CampaignError('invalid session root')
    try:
        return (json.loads((path/'summary.json').read_text()),
                json.loads((path/'recovery.json').read_text()))
    except (OSError,ValueError) as exc:
        raise CampaignError('missing or invalid postmortem JSON evidence') from exc


def verify_health() -> bool:
    """Require the actual reply values, not only a zero client exit code.

    The invoked helper uses the existing MQTT transport; it never opens
    the UART device or pauses original services.
    """
    args=[sys.executable,'-u',str(Path(live.__file__).resolve()),'--health-only']
    try:
        proc=subprocess.run(args, capture_output=True,text=True,
                            timeout=35, check=False)
    except (OSError,subprocess.TimeoutExpired) as exc:
        print('CAMPAIGN_HEALTH_ERROR='+type(exc).__name__,flush=True)
        return False
    for line in proc.stdout.splitlines():
        if line.startswith('PRODUCTION_HEALTH=') or line.startswith('PRODUCTION_HEALTH_JSON='):
            print(line,flush=True)
    status=[l for l in proc.stdout.splitlines() if l.startswith('PRODUCTION_HEALTH=')]
    json_lines=[l for l in proc.stdout.splitlines()
                if l.startswith('PRODUCTION_HEALTH_JSON=')]
    if proc.returncode != 0 or status != ['PRODUCTION_HEALTH=PASS'] or len(json_lines)!=1:
        return False
    try:
        values=json.loads(json_lines[0].split('=',1)[1])
    except ValueError:
        return False
    if set(values)!={'P80','P06'}:
        return False
    a,b=values['P80'],values['P06']
    if not all(isinstance(v,dict) and v.get('valid') is True
               and v.get('rc') == 0 and v.get('reason') == 'OK'
               for v in (a,b)):
        return False
    if a.get('response') != '1;0x4050;20':
        return False
    p06=b.get('response')
    return (isinstance(p06,str) and len(p06)==11 and
            p06.startswith('1;0x4006;') and p06[-2:].lower() != 'ff' and
            all(c in '0123456789abcdefABCDEF' for c in p06[-2:]))


def run_campaign(*, include_early_vs1: bool = False) -> int:
    if os.geteuid() != 0:
        raise CampaignError('campaign requires root in the Optolink LXC')
    # Run all safety/preflight gates BEFORE creating any remote worker.
    live.preflight()
    directory = live.BASE_DIR / ('campaign-' +
        dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ') +
        '-' + str(os.getpid()))
    directory.mkdir(parents=True,mode=0o700)
    output={'version':1,'stages':[],'result':'STARTED',
            'include_early_vs1':include_early_vs1,
            'start_utc':dt.datetime.now(dt.timezone.utc).isoformat()}

    def persist():
        live.base.atomic_json(directory/'campaign.json',output)

    persist()
    print('CAMPAIGN_DIR='+str(directory),flush=True)
    stages=[('phase_sweep','--experiment-phase-sweep')]
    if include_early_vs1:
        stages.append(('early_vs1_identity','--experiment-early-vs1-identity'))
    for stage,flag in stages:
        print('STAGE_BEGIN='+stage,flush=True)
        command=[sys.executable,'-u',str(Path(live.__file__).resolve()),
                 '--execute','--accept-telemetry-pause',flag]
        rc,session=run_and_capture(command)
        stage_record={'stage':stage,'return_code':rc,'session':session}
        output['stages'].append(stage_record)
        persist()
        try:
            summary,recovery=stage_evidence(session)
        except CampaignError as exc:
            output['result']='ABORT_EVIDENCE_MISSING';output['error']=str(exc)
            persist();print('CAMPAIGN='+output['result'],flush=True)
            return 1
        if summary.get('experiment') != stage:
            output['result']='ABORT_WRONG_EXPERIMENT';persist()
            print('CAMPAIGN='+output['result'],flush=True)
            return 1
        classification=interpret_stage(summary,recovery,rc,
                                      speculative=(stage=='early_vs1_identity'))
        stage_record['classification']=classification
        stage_record['measurement_errors']=summary.get('measurement_errors')
        if stage=='phase_sweep' and classification=='VERIFIED_SUCCESS':
            try:
                stage_record['phase_analysis']=summarize_phase_effect(summary.get('trials'))
                print('PHASE_ANALYSIS='+json.dumps(stage_record['phase_analysis'],sort_keys=True),flush=True)
            except CampaignError as exc:
                classification='INCONCLUSIVE_STOP'
                stage_record['classification']=classification
                stage_record['error']=str(exc)
        # Even after a known negative variant, never continue unless the
        # original VS1 service freshly answers both actual GFA channels.
        if classification not in ('UNVERIFIED_RESTORE_STOP','INCONCLUSIVE_STOP'):
            stage_record['production_health_pass']=verify_health()
        else:
            stage_record['production_health_pass']=False
        persist()
        print('STAGE_END='+stage+' STATUS='+classification,flush=True)
        if classification in ('UNVERIFIED_RESTORE_STOP','INCONCLUSIVE_STOP'):
            output['result']='STOP_UNVERIFIED_STATE';persist()
            print('CAMPAIGN='+output['result'],flush=True)
            return 1
        if not stage_record['production_health_pass']:
            output['result']='STOP_PRODUCTION_HEALTH_FAILED';persist()
            print('CAMPAIGN='+output['result'],flush=True)
            return 1
        if classification=='HYPOTHESIS_NEGATIVE_RESTORED':
            output['result']='EARLY_VS1_NEGATIVE_BUT_RESTORED';persist()
            print('CAMPAIGN='+output['result'],flush=True)
            return 0  # Scientific negative is expected; system is restored.
    output['result']='ALL_STAGES_VERIFIED_SUCCESS'
    persist();print('CAMPAIGN='+output['result'],flush=True)
    return 0


def main() -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute',action='store_true')
    parser.add_argument('--accept-telemetry-pause',action='store_true')
    parser.add_argument('--include-early-vs1',action='store_true',
                        help='after standard sweep and good health, ONE unverified early VS1 identity read')
    args=parser.parse_args()
    if not args.execute:
        if args.accept_telemetry_pause or args.include_early_vs1:
            raise CampaignError('campaign flags require --execute')
        print('PLAN ONLY: 7 documented handovers with timing offsets; then optional '
              'ONE early VS1 identity trial. No serial or services touched.')
        return 0
    if not args.accept_telemetry_pause:
        raise CampaignError('--execute also requires --accept-telemetry-pause')
    return run_campaign(include_early_vs1=args.include_early_vs1)


if __name__=='__main__':
    try:
        raise SystemExit(main())
    except (CampaignError,live.base.ProbeError,ValueError,OSError) as exc:
        print('CAMPAIGN_REFUSED_OR_FAILED='+str(exc),file=sys.stderr)
        raise SystemExit(1)
