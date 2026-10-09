#!/usr/bin/env python3
"""WB2A read-only high-candidate P300 -> real VS1 GFA P06 -> P300 comparison.

Research only. Never claims a P300 true fan RPM. Separate systemd service,
pinned session sources, no boiler writes, no unknown P300 opcodes or SFR reads.
"""
from __future__ import annotations

import argparse
from collections import Counter
import datetime as dt
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import signal
import stat
import subprocess
import sys
import tarfile
import tempfile
import time

VERSION = "1.0.0-rpm-triggered-vs1-crosscheck"
PROJECT = Path("/root/p300-trial-work/project")
ROOT = Path("/root/p300-trial-work/p300-rpm-trigger-results")
BUNDLES = Path("/root/p300-trial-work/research-bundles")
PRIOR_TEMPORAL_ROOT = Path("/root/p300-trial-work/p300-temporal-results")
UNIT = "optolink-p300-rpm-trigger.service"
TEMPORAL_NAME = "wb2a-p300-temporal-logger.py"
PYTHON = "/opt/optolink/venv/bin/python"
DEFAULT_HOURS, MAX_HOURS = 1, 2
CANARY_SECONDS = 300
MIN_CANARY_CYCLES = 30
CANARY_MIN_STREAM_SECONDS = 240
VS1_REFERENCE_SECONDS = 2.0
BASE_INTERVAL = 1.25
HIGH_INTERVAL = 0.60
TRIGGER_RAW_MIN = 0x88
TRIGGER_PAIR_MAX_DIFF = 4
MIN_HIGH_CYCLES = 2
TRIGGER_COOLDOWN_SECONDS = 600
MAX_TRIGGERS = 4
MAX_CYCLES = 12000
PROGRESS_INTERVAL = 20
MIN_FREE_BYTES = 256 * 1024 * 1024
PREFLIGHT_FREE_BYTES = 768 * 1024 * 1024
MAX_SESSION_BYTES = 192 * 1024 * 1024
MAX_FILE_BYTES = 96 * 1024 * 1024
STATUS_SPEC = (1, 0x55D3, 11)
CORE_SPECS = ((3, 0x0F20, 32), (3, 0x1C60, 32))
ALLOWED_P300_SPECS = frozenset((STATUS_SPEC, *CORE_SPECS))


def utc():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def load_temporal(folder: Path):
    path = folder / ("temporal.py" if (folder / "temporal.py").is_file()
                     else TEMPORAL_NAME)
    if path.is_symlink() or not path.is_file():
        raise RuntimeError("TRIGGER_PINNED_TEMPORAL_MISSING")
    spec = importlib.util.spec_from_file_location("rpm_trigger_pinned_temporal", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


T = load_temporal(Path(__file__).resolve().parent)
F = T.F
FOCUS = T.FOCUS
# This worker, not another temporal/focus logger, owns all recording paths.
F.ROOT, F.BUNDLES, F.MAX_HOURS = ROOT, BUNDLES, MAX_HOURS


def frame(spec):
    if spec not in ALLOWED_P300_SPECS:
        raise ValueError("TRIGGER_UNREVIEWED_READ")
    return FOCUS.frame(spec)


class TriggerWire(FOCUS.FocusWire):
    @staticmethod
    def permitted(phase, raw, base):
        if phase != "p300":
            return FOCUS.FocusWire.permitted(phase, raw, base)
        return raw == b"\x06" or raw in {
            frame(spec) for spec in ALLOWED_P300_SPECS}

    def packet(self, spec):
        frame(spec)
        return super().packet(spec)


def resource_guard(session, streams=()):
    if shutil.disk_usage(session).free < MIN_FREE_BYTES:
        raise RuntimeError("TRIGGER_LOW_DISK")
    total = 0
    for p in session.rglob("*"):
        if p.is_symlink():
            raise RuntimeError("TRIGGER_UNSAFE_SYMLINK")
        if p.is_file():
            if p.stat().st_size > MAX_FILE_BYTES:
                raise RuntimeError("TRIGGER_LOG_TOO_LARGE")
            total += p.stat().st_size
    if total > MAX_SESSION_BYTES:
        raise RuntimeError("TRIGGER_SESSION_LIMIT")
    if any(not s.closed and s.tell() > MAX_FILE_BYTES for s in streams):
        raise RuntimeError("TRIGGER_STREAM_LIMIT")


def status_safe(value):
    a, b = value["first_status"], value["last_status"]
    q = value["quality"]
    return (q["status_coherent"] and a["flame"] and b["flame"] and
            not a["lockout"] and not b["lockout"])


def high_candidate(value):
    c = value["candidates"]
    return (status_safe(value) and c["0f20"] >= TRIGGER_RAW_MIN and
            c["1c76"] >= TRIGGER_RAW_MIN and
            abs(c["0f20"] - c["1c76"]) <= TRIGGER_PAIR_MAX_DIFF)


def trigger_eligible(window, last_trigger, now, used):
    """Require two consecutive real, coherent, naturally high candidate pairs."""
    if (len(window) < MIN_HIGH_CYCLES or used >= MAX_TRIGGERS or
            now - last_trigger < TRIGGER_COOLDOWN_SECONDS):
        return False
    return all(high_candidate(x) for x in window[-MIN_HIGH_CYCLES:])


def summarize_capture(trigger_pre, vs1, post):
    """Classification never promotes correlation to real fan tachometer."""
    result = {"quality": "TRANSITION_OR_UNKNOWN",
              "p300_actual_p06_verified": False,
              "predicted_rpm_hypothetical": None,
              "real_vs1_p06_rpm": vs1.get("p06_rpm_unique", []),
              "delta_real_minus_predicted_rpm": None}
    before = trigger_pre[-1]["candidates"]["0f20"]
    if before >= 1:
        result["predicted_rpm_hypothetical"] = (before - 1) * 30
    stable_vs1 = (vs1.get("identity_verified") and vs1.get("stable") and
                  vs1.get("p06_invalid_ff") == 0 and
                  len(vs1.get("p06_rpm_unique", [])) == 1 and
                  vs1["p06_rpm_unique"][0] > 0)
    candidates = [
        (v["candidates"]["0f20"], v["candidates"]["1c76"])
        for v in (trigger_pre + post)]
    values = [n for pair in candidates for n in pair]
    ram_constant = (len(post) == 2 and
                    max(values) - min(values) <= 2 and
                    all(status_safe(x) for x in trigger_pre + post))
    if not stable_vs1 or not ram_constant:
        return result
    real = vs1["p06_rpm_unique"][0]
    predicted = result["predicted_rpm_hypothetical"]
    result["delta_real_minus_predicted_rpm"] = real - predicted
    if abs(real-predicted) <= 30:
        result["quality"] = "NUMERICALLY_CONSISTENT_NOT_VERIFIED"
    else:
        result["quality"] = "P06_PLUS_ONE_NUMERIC_MISMATCH"
    return result


def record_cycle(session, wire, streams, serial_no, stage):
    # Temporal helper produces exactly two verified FC01, two verified FC03.
    value = T.observation_cycle(wire, streams, serial_no, use_context=False)
    offset = streams["corebin"].tell()
    streams["corebin"].write(value["core_payload"])
    F.write_jsonl(streams["cycles"], {
        **{k: v for k, v in value.items()
           if k not in ("core_payload", "context_payload")},
        "stage": stage, "core_offset": offset, "core_length": 64,
        "status_coherent": value["quality"]["status_coherent"]})
    return value


def crosscheck(session, wire, streams, trigger_no, before, counter,
               stop, deadline):
    """Persist even failed handovers; never invent a P06 sample."""
    now = time.monotonic()
    rec = {"trigger_no":trigger_no, "start_utc":utc(), "start_monotonic":now,
           "pre_cycle_ids":[v["cycle"] for v in before],
           "pre_values":[v["candidates"] for v in before],
           "pre_native":[v["last_status"] for v in before],
           "vs1":None, "post_cycle_ids":[], "post_values":[],
           "result":"PARTIAL", "p300_actual_p06_verified":False,
           "errors":[], "switch_back_to_p300":False}
    try:
        F.switch(wire, streams["switch"],
                 f"TRIGGER{trigger_no}_P300_TO_VS1", False)
        rec["vs1"] = F.reference(
            wire, streams["vs1"], trigger_no, "TRIGGER",
            stop=None, seconds=VS1_REFERENCE_SECONDS)
        F.sync_stream(streams["vs1"])
        if stop.signum is not None or time.monotonic() >= deadline:
            rec["result"] = "STOP_AFTER_SAFE_VS1_READ"
            return rec
        F.switch(wire, streams["switch"],
                 f"TRIGGER{trigger_no}_VS1_TO_P300", True)
        rec["switch_back_to_p300"] = True
        post=[]
        for _ in range(2):
            if stop.signum is not None or time.monotonic() >= deadline:
                break
            counter["CYCLES"] += 1
            item = record_cycle(session, wire, streams, counter["CYCLES"],
                                "TRIGGER_POST")
            counter["PACKETS"] += 4
            post.append(item)
            rec["post_cycle_ids"].append(item["cycle"])
            rec["post_values"].append(item["candidates"])
        if len(post) == 2:
            rec.update(summarize_capture(before, rec["vs1"], post))
            rec["result"] = "COMPLETE"
        else:
            rec["result"] = "PARTIAL_POST"
        return rec
    except BaseException as exc:
        rec["errors"].append(str(exc) or type(exc).__name__)
        raise
    finally:
        rec["end_utc"],rec["end_monotonic"]=utc(),time.monotonic()
        rec["duration_seconds"]=round(rec["end_monotonic"]-now,3)
        F.write_jsonl(streams["triggers"],rec)
        for out in streams.values(): F.sync_stream(out)


def validate_state(session):
    state = F.validate_state(session)
    for key,name in (("temporal_sha256","temporal.py"),
                     ("focus_sha256","focus.py"),
                     ("fullram_sha256","fullram.py")):
        F.DEEP.check_hash(session/name,state[key])
    mode, seconds = state.get("mode"), state.get("duration_seconds")
    if mode == "canary":
        if state["hours"] != 1 or seconds != CANARY_SECONDS:
            raise RuntimeError("TRIGGER_CANARY_STATE_INVALID")
    elif mode == "full":
        if (state["hours"] not in (1,2) or seconds!=state["hours"]*3600):
            raise RuntimeError("TRIGGER_FULL_STATE_INVALID")
    else:
        raise RuntimeError("TRIGGER_MODE_INVALID")
    return state


def progress(session,phase,counts,started,seconds,last_trigger=None):
    base=F.DEEP.load_local_base(Path(__file__).resolve().parent)
    base.h.atomic_json(session/"progress.json",{
        "state":"RUNNING_READ_ONLY","updated_utc":utc(),"phase":phase,
        "elapsed_s":round(time.monotonic()-started,3),
        "limit_seconds":seconds,
        "cycles":counts["CYCLES"], "p300_packets":counts["PACKETS"],
        "natural_high_cycles":counts["HIGH_CYCLES"],
        "candidate_transitions":counts["CANDIDATE_CHANGES"],
        "flame_edges":counts["FLAME_EDGES"],
        "trigger_crosschecks":counts["TRIGGERS"],
        "numerically_consistent_not_verified":counts["NUMERIC_MATCHES"],
        "p06_plus_one_mismatches":counts["NUMERIC_MISMATCHES"],
        "p300_actual_p06_verified":False,
        "last_crosscheck":last_trigger})


def run_worker(session):
    state=validate_state(session)
    base=F.DEEP.load_local_base(session)
    h=base.h
    started=time.monotonic()
    deadline=started+state["duration_seconds"]
    stopper=F.DEEP.DeferredStop()
    for sig in (signal.SIGTERM,signal.SIGINT,signal.SIGHUP):
        signal.signal(sig,stopper.on_signal)
    counts=Counter()
    streams={}
    handle=wire=None
    report={"version":VERSION,"mode":state["mode"],"source_commit":state["source_checkout_sha"],
            "start_utc":utc(),"duration_seconds":state["duration_seconds"],
            "errors":[],"observation_complete":False,"worker_vs1_restored":False,
            "p300_actual_p06_verified":False,"writes_issued":False,
            "trigger_count":0,"last_trigger":None,"signal":None,
            "initial_vs1":None,"final_vs1":None}
    last_update=started
    last_trigger_time=-1e12
    recent=[]
    previous=None
    last_probe=None
    p300_start=None
    try:
        live=h.read_settings(h.SETTINGS.read_text())
        if live["port_optolink"] != state["port"]:
            raise RuntimeError("TRIGGER_PORT_CHANGED")
        if h.unit_state(h.MAIN).get("WorkingDirectory") != "/opt/optolink":
            raise RuntimeError("TRIGGER_WRONG_PRODUCTIVE_WORKDIR")
        for unit,previous_state in state["services"].items():
            if (h.unit_state(unit).get("ActiveState")=="active") != previous_state:
                raise RuntimeError("TRIGGER_PRODUCTIVE_SERVICE_CHANGED_"+unit)
        h.pause_services(session,state)
        base.isolation(state["port"])
        handle=h.open_serial(state["port"])
        for name in ("vs1","switch","trace","packets","cycles","triggers"):
            streams[name]=(session/(name+".jsonl")).open("x")
        streams["corebin"]=(session/"core-pairs.bin").open("xb")
        delegate=base.UART1Wire(handle)
        delegate.trace_sink=streams["trace"]
        wire=TriggerWire(delegate)
        delegate.send=wire.send
        wire.identify_vs1()
        report["initial_vs1"]=F.reference(
            wire,streams["vs1"],0,"INITIAL",stop=stopper,
            seconds=VS1_REFERENCE_SECONDS)
        initial=report["initial_vs1"]
        if not initial.get("identity_verified") or initial.get("p06_valid",0)<1:
            raise RuntimeError("TRIGGER_INITIAL_VS1_GFA_UNVERIFIED")
        if stopper.signum is not None:
            raise RuntimeError("TRIGGER_OPERATOR_STOP_DURING_PRE")
        F.switch(wire,streams["switch"],"TRIGGER_INITIAL_VS1_TO_P300",True)
        p300_start=time.monotonic()
        progress(session,"P300_OBSERVE",counts,started,state["duration_seconds"])
        while (stopper.signum is None and time.monotonic()<deadline and
               counts["CYCLES"]<MAX_CYCLES):
            clock=time.monotonic()
            if clock-last_update >= PROGRESS_INTERVAL:
                resource_guard(session,streams.values())
                base.isolation(state["port"])
                progress(session,"P300_OBSERVE",counts,started,
                         state["duration_seconds"],last_probe)
                for s in streams.values(): F.sync_stream(s)
                last_update=time.monotonic()
            counts["CYCLES"] += 1
            value=record_cycle(session,wire,streams,counts["CYCLES"],"OBSERVE")
            counts["PACKETS"] += 4
            if high_candidate(value):counts["HIGH_CYCLES"]+=1
            if previous is not None:
                if previous["candidates"]!=value["candidates"]:
                    counts["CANDIDATE_CHANGES"]+=1
                if previous["last_status"]["flame"] != value["first_status"]["flame"]:
                    counts["FLAME_EDGES"]+=1
            recent.append(value)
            recent=recent[-MIN_HIGH_CYCLES:]
            previous=value
            if (state["mode"]=="full" and
                    trigger_eligible(recent,last_trigger_time,
                                     time.monotonic(),counts["TRIGGERS"])):
                counts["TRIGGERS"]+=1
                last_trigger_time=time.monotonic()
                trigger_no=counts["TRIGGERS"]
                try:
                    probe=crosscheck(session,wire,streams,trigger_no,
                                     list(recent),counts,stopper,deadline)
                except BaseException as exc:
                    report["errors"].append(
                        "CROSSCHECK_"+str(trigger_no)+":"+str(exc))
                    break
                last_probe={"trigger_no":trigger_no,"result":probe["result"],
                            "quality":probe.get("quality","TRANSITION_OR_UNKNOWN"),
                            "real_vs1_p06_rpm":probe.get("real_vs1_p06_rpm",[]),
                            "hypothetical_rpm":probe.get("predicted_rpm_hypothetical")}
                if probe.get("quality")=="NUMERICALLY_CONSISTENT_NOT_VERIFIED":
                    counts["NUMERIC_MATCHES"]+=1
                if probe.get("quality")=="P06_PLUS_ONE_NUMERIC_MISMATCH":
                    counts["NUMERIC_MISMATCHES"]+=1
                recent=[]
                previous=None
                progress(session,"P300_AFTER_VS1_CROSSCHECK",counts,started,
                         state["duration_seconds"],last_probe)
                if wire.phase != "p300":
                    break
                if counts["TRIGGERS"]>=MAX_TRIGGERS:
                    break
            remain=(HIGH_INTERVAL if high_candidate(value)
                    else BASE_INTERVAL)-(time.monotonic()-clock)
            if remain>0 and stopper.signum is None:
                time.sleep(min(remain,1.5))
        if wire.phase=="p300":
            F.switch(wire,streams["switch"],"TRIGGER_FINAL_P300_TO_VS1",False)
        report["final_vs1"]=F.reference(
            wire,streams["vs1"],0,"FINAL",stop=None,
            seconds=VS1_REFERENCE_SECONDS)
        final=report["final_vs1"]
        if not final.get("identity_verified") or final.get("p06_valid",0)<1:
            raise RuntimeError("TRIGGER_FINAL_VS1_GFA_UNVERIFIED")
        report["observation_complete"]=not report["errors"]
    except BaseException as exc:
        report["errors"].append(str(exc) or type(exc).__name__)
    finally:
        for sig in (signal.SIGTERM,signal.SIGINT,signal.SIGHUP):
            signal.signal(sig,signal.SIG_IGN)
        if wire:
            try:
                checks=wire.restore_final_gfa()
                report["restore_gfa"]=checks
                report["worker_vs1_restored"]=(
                    checks[0]["hex"]=="20" and checks[1]["valid"])
            except BaseException as exc:
                report["errors"].append("WORKER_VS1_RECOVERY:"+str(exc))
            try:
                wire.w.flush_trace()
                report["trace_records"]=wire.w.trace_records_written
            except BaseException as exc:
                report["errors"].append("TRACE_FLUSH:"+str(exc))
        for name,out in streams.items():
            try:F.sync_stream(out);out.close()
            except BaseException as exc: report["errors"].append("CLOSE_"+name+":"+str(exc))
        if handle:
            try:handle.close()
            except BaseException as exc:report["errors"].append("SERIAL_CLOSE:"+str(exc))
        report["end_utc"]=utc()
        report["duration_seconds_actual"]=round(time.monotonic()-started,3)
        report["p300_started"]=p300_start is not None
        report["p300_stream_seconds_approx"]=round(
            time.monotonic()-p300_start,3) if p300_start is not None else 0
        report["counts"]=dict(counts)
        report["trigger_count"]=counts["TRIGGERS"]
        report["last_trigger"]=last_probe
        report["signal"]=stopper.signum
        if state["mode"]=="canary" and (
                counts["CYCLES"]<MIN_CANARY_CYCLES or
                report["p300_stream_seconds_approx"]<CANARY_MIN_STREAM_SECONDS):
            report["errors"].append("TRIGGER_CANARY_TOO_SHORT")
            report["observation_complete"]=False
        report["data_quality"]=("COMPLETE" if report["observation_complete"]
                                else "PARTIAL")
        h.atomic_json(session/"measurement.json",report)
        h.atomic_json(session/"progress.json",{
            "state":"WORKER_EXITED_RECOVERY_PENDING","end_utc":utc(),
            "counts":dict(counts),"errors":report["errors"],
            "data_quality":report["data_quality"],
            "worker_vs1_restored":report["worker_vs1_restored"]})
    return int(not (report["observation_complete"] and
                    report["worker_vs1_restored"]))


def worker(session):
    with F.DEEP.load_local_base(session).locks():
        return run_worker(session)


def archive(session):
    if ROOT.is_symlink() or BUNDLES.is_symlink():
        raise RuntimeError("TRIGGER_UNSAFE_ARCHIVE_ROOT")
    BUNDLES.mkdir(parents=True,exist_ok=True,mode=0o700)
    os.chmod(BUNDLES,0o700)
    output=BUNDLES/("p300-rpm-trigger-"+session.name+"-bundle.tar.gz")
    if output.is_file() and not output.is_symlink():return output
    if output.exists() or output.is_symlink():
        raise RuntimeError("TRIGGER_UNSAFE_EXISTING_ARCHIVE")
    members=sorted(p for p in session.rglob("*") if p.is_file())
    manifest={"version":VERSION,"session":session.name,
              "read_only":True,"p300_actual_p06_verified":False,"files":{}}
    for path in members:
        info=path.lstat()
        if path.is_symlink() or not stat.S_ISREG(info.st_mode) or (
                info.st_uid!=0 or info.st_mode & 0o077):
            raise RuntimeError("TRIGGER_UNSAFE_ARCHIVE_MEMBER")
        rel=path.relative_to(session).as_posix()
        manifest["files"][rel]={"sha256":F.sha256(path),"size":info.st_size}
    if sum(v["size"] for v in manifest["files"].values())>MAX_SESSION_BYTES:
        raise RuntimeError("TRIGGER_ARCHIVE_TOO_LARGE")
    tmp=None
    try:
        with tempfile.NamedTemporaryFile(prefix="p300-rpm-trigger-",
                                         suffix=".tar.gz",dir=BUNDLES,
                                         delete=False) as file:
            tmp=Path(file.name)
        os.chmod(tmp,0o600)
        with tarfile.open(tmp,"w:gz") as tar:
            for path in members:
                tar.add(path,arcname="p300-rpm-trigger/"+path.relative_to(session).as_posix(),
                        recursive=False)
            raw=(json.dumps(manifest,sort_keys=True,indent=2)+"\n").encode()
            entry=tarfile.TarInfo("p300-rpm-trigger/bundle-manifest.json")
            entry.size,entry.mode=len(raw),0o600
            tar.addfile(entry,io.BytesIO(raw))
        os.replace(tmp,output)
    finally:
        if tmp:tmp.unlink(missing_ok=True)
    return output


def recover(session):
    state=validate_state(session)
    base=F.DEEP.load_local_base(session)
    h=base.h
    errors,units=[],[]
    with base.locks():
        if h.MAIN in state["restore"]:
            try:
                h.command(["systemctl","start",h.MAIN])
                h.wait_main_ready()
                units.append(h.MAIN)
            except BaseException as exc:
                errors.append("MAIN_NOT_READY_DEFER_HELPERS:"+str(exc))
        if not errors:
            for unit in reversed(state["restore"]):
                if unit==h.MAIN:continue
                try:
                    h.command(["systemctl","start",unit])
                    if unit!="optolink-clock-sync.service" and (
                            h.unit_state(unit).get("ActiveState")!="active"):
                        raise RuntimeError("UNIT_NOT_ACTIVE")
                    units.append(unit)
                except BaseException as exc:
                    errors.append(unit+":"+str(exc))
        h.atomic_json(session/"recovery.json",{
            "services_restored":not errors,"units_restored":units,
            "errors":errors,"systemd_result":os.getenv("SERVICE_RESULT","unknown")})
    try:
        health=F.DEEP.post_restore_health(base)
        h.atomic_json(session/"health.json",health)
        healthy=bool(
            health.get("production_main_verified") and
            health.get("gfa_reads",{}).get("P80",{}).get("format_and_identity_verified") and
            health.get("gfa_reads",{}).get("P06",{}).get("format_and_identity_verified") and
            health.get("gfa_reads",{}).get("P06",{}).get("p06_non_ff_verified"))
        prior=session/"progress.json"
        last=json.loads(prior.read_text()) if prior.is_file() else {}
        last.update(state="RESTORED" if healthy and not errors else "RESTORE_NOT_VERIFIED",
                    restored_utc=utc(),services_restored=not errors,
                    p80_p06_production_health_verified=healthy)
        h.atomic_json(prior,last)
        if not healthy:errors.append("PRODUCTION_P80_P06_NOT_VERIFIED")
    except BaseException as exc:
        errors.append("HEALTH:"+str(exc))
    try:
        file=archive(session)
        print("UPLOAD_ONE_FILE="+str(file),flush=True)
    except BaseException as exc:
        errors.append("ARCHIVE:"+str(exc))
    return int(bool(errors))


def competing(base):
    for unit in sorted({UNIT,T.UNIT,T.CURRENT_UNIT,FOCUS.UNIT,
                        F.UNIT,F.DEEP.UNIT,*F.DEEP.SELF_NAMED_SERVICE_UNITS}):
        if base.h.unit_state(unit).get("ActiveState") not in ("inactive","failed"):
            raise RuntimeError("TRIGGER_COMPETING_LOGGER_"+unit)


def previous_temporal_restored():
    root=PRIOR_TEMPORAL_ROOT
    if root.is_symlink() or not root.is_dir():
        raise RuntimeError("TRIGGER_PRIOR_TEMPORAL_RESULTS_MISSING")
    runs=sorted(p for p in root.glob("run-*") if p.is_dir() and not p.is_symlink())
    full=[]
    for p in runs:
        st=p/"state.json"
        if st.is_file() and json.loads(st.read_text()).get("mode")=="full":
            full.append(p)
    if not full:raise RuntimeError("TRIGGER_PRIOR_FULL_RESULT_MISSING")
    last=full[-1]
    summary=json.loads((last/"measurement.json").read_text())
    recovery=json.loads((last/"recovery.json").read_text())
    health=json.loads((last/"health.json").read_text())
    if not (summary.get("observation_complete") and
            summary.get("worker_vs1_restored") and not summary.get("errors") and
            recovery.get("services_restored") and
            health.get("production_main_verified") and
            health.get("gfa_reads",{}).get("P80",{}).get("format_and_identity_verified") and
            health.get("gfa_reads",{}).get("P06",{}).get("p06_non_ff_verified")):
        raise RuntimeError("TRIGGER_PRIOR_TEMPORAL_HEALTH_NOT_VERIFIED")
    bundle=BUNDLES/("p300-temporal-"+last.name+"-bundle.tar.gz")
    if bundle.is_symlink() or not bundle.is_file():
        raise RuntimeError("TRIGGER_PRIOR_TEMPORAL_ARCHIVE_MISSING")


def canary_qualified():
    if not ROOT.is_dir() or ROOT.is_symlink():return False
    for file in ROOT.glob("run-*/state.json"):
        try:
            session=file.parent
            state=json.loads(file.read_text())
            if state.get("mode")!="canary":continue
            report=json.loads((session/"measurement.json").read_text())
            restore=json.loads((session/"recovery.json").read_text())
            health=json.loads((session/"health.json").read_text())
            archive_file=BUNDLES/("p300-rpm-trigger-"+session.name+"-bundle.tar.gz")
            if (report.get("observation_complete") and
                report.get("worker_vs1_restored") and not report.get("errors") and
                report.get("signal") is None and
                report.get("counts",{}).get("CYCLES",0)>=MIN_CANARY_CYCLES and
                report.get("p300_stream_seconds_approx",0)>=CANARY_MIN_STREAM_SECONDS and
                restore.get("services_restored") and
                health.get("production_main_verified") and
                health.get("gfa_reads",{}).get("P06",{}).get("p06_non_ff_verified") and
                archive_file.is_file() and not archive_file.is_symlink()):
                return True
        except (OSError,ValueError,KeyError,TypeError):
            continue
    return False


def start(hours,canary=False):
    if os.geteuid()!=0:raise RuntimeError("TRIGGER_ROOT_REQUIRED")
    if type(hours) is not int or hours not in (1,2) or (canary and hours!=1):
        raise RuntimeError("TRIGGER_DURATION_MUST_BE_1_OR_2_HOURS")
    if any(p.is_symlink() for p in (PROJECT,ROOT,BUNDLES)):
        raise RuntimeError("TRIGGER_UNSAFE_PROJECT_ROOT")
    base=F.DEEP.load_local_base(PROJECT/"tools")
    h=base.h
    with base.locks():
        settings,services=h.preflight()
        competing(base)
        T.guard_finished_focus()
        previous_temporal_restored()
        if shutil.disk_usage(PROJECT).free<PREFLIGHT_FREE_BYTES:
            raise RuntimeError("TRIGGER_PREFLIGHT_NEEDS_768_MIB")
        ROOT.mkdir(parents=True,exist_ok=True,mode=0o700)
        os.chmod(ROOT,0o700)
        for old in ROOT.glob("run-*/state.json"):
            state=json.loads(old.read_text())
            if state.get("restore") and (
                not old.with_name("recovery.json").is_file() or
                not json.loads(old.with_name("recovery.json").read_text()).get(
                    "services_restored")):
                raise RuntimeError("TRIGGER_OLDER_RESTORE_UNRESOLVED")
        if not canary and not canary_qualified():
            raise RuntimeError("TRIGGER_SUCCESSFUL_5MIN_CANARY_REQUIRED")
        session=ROOT/("run-"+dt.datetime.now(dt.timezone.utc).strftime(
                      "%Y%m%dT%H%M%SZ")+"-"+str(os.getpid()))
        session.mkdir(mode=0o700)
        sources={"logger.py":Path(__file__).resolve(),
                 "temporal.py":PROJECT/"tools"/TEMPORAL_NAME,
                 "focus.py":PROJECT/"tools"/"wb2a-p300-p06-focus.py",
                 "fullram.py":PROJECT/"tools"/"wb2a-p300-fullram-logger.py",
                 "deep.py":PROJECT/"tools"/"wb2a-p300-deep-logger.py",
                 "base.py":PROJECT/"tools"/"wb2a-uart1-overnight.py",
                 "wb2a-handover-probe.py":PROJECT/"tools"/"wb2a-handover-probe.py"}
        hashes={}
        for name,source in sources.items():
            if source.is_symlink() or not source.is_file():
                raise RuntimeError("TRIGGER_SOURCE_INVALID_"+name)
            shutil.copyfile(source,session/name)
            os.chmod(session/name,0o600)
            hashes[name]=F.sha256(session/name)
        sha=h.command(["git","-C",str(PROJECT),"rev-parse","HEAD"]).strip()
        h.atomic_json(session/"state.json",{
            "version":VERSION,"source_checkout_sha":sha,"hours":hours,
            "mode":"canary" if canary else "full",
            "duration_seconds":CANARY_SECONDS if canary else hours*3600,
            "services":services,"restore":[],"port":settings["port_optolink"],
            "logger_sha256":hashes["logger.py"],
            "temporal_sha256":hashes["temporal.py"],
            "focus_sha256":hashes["focus.py"],
            "fullram_sha256":hashes["fullram.py"],
            "deep_sha256":hashes["deep.py"],
            "base_sha256":hashes["base.py"],
            "helper_sha256":hashes["wb2a-handover-probe.py"]})
    cmd=["systemd-run","--unit="+UNIT,"--no-block","--collect",
         "--property=Type=exec","--property=Restart=no",
         "--property=TimeoutStopSec=300","--property=KillMode=control-group",
         "--property=UMask=0077",
         "--property=ExecStopPost="+PYTHON+" -u "+str(session/"logger.py")+
             " --recover "+str(session),
         PYTHON,"-u",str(session/"logger.py"),"--worker",str(session)]
    result=subprocess.run(cmd,capture_output=True,text=True,check=False,timeout=30)
    if result.returncode:
        raise RuntimeError("TRIGGER_SYSTEMD_START_REFUSED:"+result.stderr[-500:])
    print("SESSION="+str(session),flush=True)
    print("UNIT="+UNIT,flush=True)
    print("MODE="+("canary" if canary else "full"),flush=True)
    print("DURATION_SECONDS="+str(CANARY_SECONDS if canary else hours*3600),flush=True)
    print("READ_ONLY=YES",flush=True)
    return 0


def latest():
    if ROOT.is_symlink() or not ROOT.is_dir():
        raise RuntimeError("TRIGGER_NO_SESSIONS")
    sessions=sorted(x for x in ROOT.glob("run-*") if x.is_dir() and not x.is_symlink())
    if not sessions:raise RuntimeError("TRIGGER_NO_SESSIONS")
    return sessions[-1]


def status():
    session=latest()
    base=F.DEEP.load_local_base(PROJECT/"tools")
    print("SESSION="+str(session))
    print("UNIT_STATE="+base.h.unit_state(UNIT).get("ActiveState","unknown"))
    for name in ("progress.json","recovery.json","health.json","measurement.json"):
        path=session/name
        if path.is_file():
            print(name.upper()+"="+path.read_text().strip())
    bundle=BUNDLES/("p300-rpm-trigger-"+session.name+"-bundle.tar.gz")
    if bundle.is_file(): print("UPLOAD_ONE_FILE="+str(bundle))
    return 0


def stop():
    session=latest()
    base=F.DEEP.load_local_base(PROJECT/"tools")
    active=base.h.unit_state(UNIT).get("ActiveState")
    if active in ("active","activating","deactivating"):
        result=subprocess.run(["systemctl","stop",UNIT],capture_output=True,
                              text=True,check=False,timeout=360)
        if result.returncode:
            print("SYSTEMD_STOP_FAILED="+result.stderr[-500:],file=sys.stderr)
    elif active not in ("inactive","failed"):
        raise RuntimeError("TRIGGER_UNKNOWN_UNIT_STATE_"+str(active))
    bundle=BUNDLES/("p300-rpm-trigger-"+session.name+"-bundle.tar.gz")
    for _ in range(45):
        if (session/"recovery.json").is_file() and bundle.is_file():
            break
        time.sleep(1)
    healthfile=session/"health.json"
    rfile=session/"recovery.json"
    h=json.loads(healthfile.read_text()) if healthfile.is_file() else {}
    r=json.loads(rfile.read_text()) if rfile.is_file() else {}
    good=(r.get("services_restored") and h.get("production_main_verified")
          and h.get("gfa_reads",{}).get("P80",{}).get("format_and_identity_verified")
          and h.get("gfa_reads",{}).get("P06",{}).get("p06_non_ff_verified"))
    print("RESTORE_AND_P06_HEALTH="+("PASS" if good else "NOT_VERIFIED"))
    print("UPLOAD_ONE_FILE="+str(bundle) if bundle.is_file()
          else "UPLOAD_ARCHIVE_NOT_VERIFIED")
    return 0 if good and bundle.is_file() else 1


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    group=parser.add_mutually_exclusive_group()
    for cmd in ("start","canary","status","stop"):
        group.add_argument("--"+cmd,action="store_true")
    group.add_argument("--worker",type=Path)
    group.add_argument("--recover",type=Path)
    parser.add_argument("--hours",type=int,default=DEFAULT_HOURS)
    args=parser.parse_args()
    os.umask(0o077)
    if args.worker or args.recover:
        if os.geteuid()!=0 or "INVOCATION_ID" not in os.environ:
            parser.error("supervised root systemd required")
        return worker(args.worker) if args.worker else recover(args.recover)
    if args.canary:return start(1,canary=True)
    if args.start:return start(args.hours)
    if args.status:return status()
    if args.stop:return stop()
    print("PLAN ONLY:",VERSION)
    print("Known P300 FC01 55D3/11 and FC03 0f20/1c60/32; real VS1 P06/P09 crosscheck.")
    print("At least 2 consecutive naturally high candidates >=0x88, flame on, no lockout.")
    print("Canary 5min (no triggers); full 1 or 2h; max 4 probes, 10min cooldown.")
    print("P06 actual RPM is NEVER assigned from P300. Read-only, pinned systemd restore.")
    return 0


if __name__=="__main__":
    try:raise SystemExit(main())
    except (RuntimeError,ValueError,OSError,subprocess.SubprocessError) as exc:
        print("REFUSED_OR_FAILED="+str(exc),file=sys.stderr)
        raise SystemExit(1)
