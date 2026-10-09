#!/usr/bin/env python3
"""WB2A P300-only temporal observation of already validated RAM/status bytes.

No boiler writes, no new FC/addresses, no GFA-C9. The real fan RPM is measured
only before/after the uninterrupted P300 interval in VS1. Continuous P300
sampling cannot be represented as contemporaneous actual fan RPM.
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

VERSION = "1.0.0-p300-temporal-candidate"
PROJECT = Path("/root/p300-trial-work/project")
ROOT = Path("/root/p300-trial-work/p300-temporal-results")
BUNDLES = Path("/root/p300-trial-work/research-bundles")
UNIT = "optolink-p300-temporal.service"
CURRENT_UNIT = "optolink-p300-p06-focus.service"
PYTHON = "/opt/optolink/venv/bin/python"
DEFAULT_HOURS, MAX_HOURS = 2, 3
REFERENCE_SECONDS = 6.0
MIN_FREE = 256 * 1024 * 1024
PREFLIGHT_FREE = 768 * 1024 * 1024
MAX_SESSION = 192 * 1024 * 1024
MAX_FILE = 96 * 1024 * 1024
MAX_CYCLES = 24000
STATUS_SPEC = (1, 0x55D3, 11)
CORE_SPECS = ((3, 0x0F20, 32), (3, 0x1C60, 32))
CONTEXT_SPECS = ((3, 0x0F00, 32), (3, 0x0F40, 32),
                 (3, 0x1C40, 32), (3, 0x1C80, 32))
SPECS = frozenset((STATUS_SPEC, *CORE_SPECS, *CONTEXT_SPECS))
CORE_ADDRESSES = (0x0F20, 0x1C76)
CONTEXT_EVERY_S = 12.0
PROGRESS_EVERY_S = 20.0
BASELINE_INTERVAL_S = 1.5
BURST_INTERVAL_S = 0.5
BURST_ON_FLAME_S = 35.0
BURST_ON_P87_S = 20.0
BURST_ON_MOD_S = 8.0
MOD_BURST_COOLDOWN_S = 60.0


def utc():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def load_focus(directory):
    root = Path(directory)
    source = root / ("focus.py" if (root / "focus.py").is_file()
                     else "wb2a-p300-p06-focus.py")
    if not source.is_file() or source.is_symlink():
        raise RuntimeError("TEMPORAL_PINNED_FOCUS_SOURCE_MISSING")
    spec = importlib.util.spec_from_file_location("temporal_pinned_focus", source)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


FOCUS = load_focus(Path(__file__).resolve().parent)
F = FOCUS.F
# The dependency is imported into this process only; never modifies sources.
F.ROOT = ROOT
F.BUNDLES = BUNDLES
F.MAX_HOURS = MAX_HOURS


def frame(spec):
    if spec not in SPECS:
        raise ValueError("TEMPORAL_UNREVIEWED_READ")
    return FOCUS.frame(spec)


def resource_guard(session, streams=()):
    if shutil.disk_usage(session).free < MIN_FREE:
        raise RuntimeError("TEMPORAL_LOW_DISK")
    total = 0
    for p in session.rglob("*"):
        if p.is_symlink():
            raise RuntimeError("TEMPORAL_SESSION_SYMLINK")
        if p.is_file():
            size = p.stat().st_size
            if size > MAX_FILE:
                raise RuntimeError("TEMPORAL_FILE_TOO_LARGE:" + p.name)
            total += size
    if total > MAX_SESSION:
        raise RuntimeError("TEMPORAL_SESSION_TOO_LARGE")
    for stream in streams:
        if not stream.closed and stream.tell() > MAX_FILE:
            raise RuntimeError("TEMPORAL_OPEN_FILE_TOO_LARGE")


def native(pkt):
    data = pkt["data"]
    if len(data) != 11:
        raise RuntimeError("TEMPORAL_NATIVE_LENGTH_INVALID")
    if data[7] == 255:
        raise RuntimeError("TEMPORAL_NATIVE_P87_FF")
    return {"flame": bool(data[5] & 0x20),
            "lockout": bool(data[5] & 0x40),
            "byte0": data[0], "byte5": data[5],
            "byte7": data[7], "byte9": data[9],
            "payload_hex": data.hex(), "rx_utc": pkt["rx_utc"],
            "rx_monotonic": pkt["rx_monotonic"]}


def candidate_bytes(core):
    one = core[0x0F20]
    two = core[0x1C60]
    if len(one) != 32 or len(two) != 32:
        raise RuntimeError("TEMPORAL_CORE_LENGTH_INVALID")
    # Known mirrors: 0f20==1c76; 0f28==1c7d; 0f29==1c7e.
    return {
        "0f20": one[0], "1c76": two[0x16],
        "0f27": one[7], "0f28": one[8], "0f29": one[9],
        "1c7d": two[0x1D], "1c7e": two[0x1E],
        "copies_equal": (one[0] == two[0x16] and
                         one[8] == two[0x1D] and
                         one[9] == two[0x1E])}


def status_changes(before, after):
    return {
        "flame": before["flame"] != after["flame"],
        "p87": before["byte7"] != after["byte7"],
        "modulation": before["byte0"] != after["byte0"] or
                      before["byte9"] != after["byte9"],
        "lockout": before["lockout"] != after["lockout"]}


def classify_temporal(status_a, status_b, data):
    """Quality of status bracketing, not P06; never a source of actual RPM."""
    changed = status_changes(status_a, status_b)
    status_coherent = not (changed["flame"] or changed["p87"] or changed["lockout"])
    return {
        "status_coherent": status_coherent,
        "native_status_changed_within_pair": changed,
        "gfa_p06_actual_rpm_available_during_p300": False,
        "p06_alias_verified": False,
        "candidate_0f20_equals_1c76": data["0f20"] == data["1c76"],
        "native_p87_copy_consistent_with_endpoint": (
            data["0f29"] == status_a["byte7"] or
            data["0f29"] == status_b["byte7"]),
    }


def update_burst(now, previous, a, b, samples, last_mod_burst):
    """Event-triggered fast sampling with bounded modulation trigger duty."""
    changes = status_changes(a, b)
    if previous:
        adjacent = status_changes(previous, a)
        changes = {k: changes[k] or adjacent[k] for k in changes}
    prior_until = samples.get("burst_until", 0.0)
    if changes["flame"] or changes["lockout"]:
        return max(prior_until, now + BURST_ON_FLAME_S), last_mod_burst
    if changes["p87"]:
        return max(prior_until, now + BURST_ON_P87_S), last_mod_burst
    if (changes["modulation"] and previous and
            max(abs(previous["byte0"] - a["byte0"]),
                abs(previous["byte9"] - a["byte9"])) >= 8 and
            now - last_mod_burst >= MOD_BURST_COOLDOWN_S):
        return max(prior_until, now + BURST_ON_MOD_S), now
    return prior_until, last_mod_burst


def read_packet(wire, streams, spec, cycle, ordinal):
    frame(spec)  # exact P300 FC/address/length whitelist before I/O
    try:
        packet = wire.packet(spec)
    except F.PacketError as exc:
        F.write_jsonl(streams["packets"], {
            "cycle": cycle, "ordinal": ordinal, "fc": spec[0],
            "address": f"0x{spec[1]:04x}", "length": spec[2],
            "request_hex": frame(spec).hex(),
            "rx_observed_hex": exc.received.hex(),
            "tx_utc": exc.tx_utc, "tx_monotonic": exc.tx_monotonic,
            "rx_utc": utc(), "rx_monotonic": time.monotonic(),
            "result": "ERROR", "error": str(exc), "retry_count": 0})
        raise
    F.write_jsonl(streams["packets"], {
        **F.emit_packet(packet, cycle, ordinal),
        "p300_only": True, "actual_p06_rpm_not_observed": True})
    return packet


def observation_cycle(wire, streams, cycle, use_context=False):
    """Two real native status samples bracket the known core RAM read pair."""
    tick = time.monotonic()
    a_pkt = read_packet(wire, streams, STATUS_SPEC, cycle, 0)
    one = read_packet(wire, streams, CORE_SPECS[0], cycle, 1)
    two = read_packet(wire, streams, CORE_SPECS[1], cycle, 2)
    b_pkt = read_packet(wire, streams, STATUS_SPEC, cycle, 3)
    a, b = native(a_pkt), native(b_pkt)
    core = {0x0F20: one["data"], 0x1C60: two["data"]}
    cand = candidate_bytes(core)
    context = None
    if use_context:
        context_raw = []
        for ordinal, spec in enumerate(CONTEXT_SPECS, 4):
            context_raw.append(read_packet(wire, streams, spec, cycle, ordinal)["data"])
        context = b"".join(context_raw)
    payload = one["data"] + two["data"]
    quality = classify_temporal(a, b, cand)
    return {
        "cycle": cycle, "start_monotonic": tick, "start_utc": a_pkt["tx_utc"],
        "end_monotonic": time.monotonic(), "end_utc": utc(),
        "duration_s": round(time.monotonic()-tick, 4),
        "first_status": a, "last_status": b, "candidates": cand,
        "quality": quality, "core_payload": payload,
        "context_payload": context,
        "core_sha256": hashlib.sha256(payload).hexdigest(),
        "context_sha256": hashlib.sha256(context).hexdigest() if context else None,
    }


def event_rows(previous, current, changed, t):
    events = []
    if previous:
        for key in ("flame", "byte7", "lockout", "byte0", "byte9"):
            if previous[key] != current[key]:
                events.append({"event": "NATIVE_CHANGE_" + key.upper(),
                               "old": previous[key], "new": current[key],
                               "at_monotonic": t})
    if changed.get("flame"):
        events.append({"event": "FLAME_CHANGED_DURING_PAIR", "at_monotonic": t})
    if changed.get("p87"):
        events.append({"event": "P87_CHANGED_DURING_PAIR", "at_monotonic": t})
    return events


def measurement_stream(session, wire, streams, stopper, deadline, counts,
                       pulse=None, checkpoint=None):
    """Entire stream has exactly one P300-entry and one P300-exit."""
    t0 = time.monotonic()
    prev, prev_cand = None, None
    last_progress = last_context = t0 - CONTEXT_EVERY_S
    burst_until, last_mod_burst = 0.0, -1e12
    core_out, context_out = streams["corebin"], streams["contextbin"]
    while (stopper.signum is None and time.monotonic() < deadline and
           counts["CYCLES"] < MAX_CYCLES):
        start = time.monotonic()
        if start-last_progress >= PROGRESS_EVERY_S:
            resource_guard(session, streams.values())
            if checkpoint: checkpoint("P300_STREAM", counts)
            for out in streams.values(): F.sync_stream(out)
            last_progress = time.monotonic()
        cycle = counts["CYCLES"] + 1
        context_due = start-last_context >= CONTEXT_EVERY_S
        # Every sampling transaction must finish before examining SIGTERM.
        value = observation_cycle(wire, streams, cycle, use_context=context_due)
        a, b = value["first_status"], value["last_status"]
        cand = value["candidates"]
        core_offset = core_out.tell()
        core_out.write(value["core_payload"])
        context_offset = None
        if value["context_payload"] is not None:
            context_offset = context_out.tell()
            context_out.write(value["context_payload"])
            last_context = time.monotonic()
            counts["CONTEXT"] += 1
        diff = (prev_cand is not None and
                {k:cand[k] for k in cand if k != "copies_equal"} !=
                {k:prev_cand[k] for k in prev_cand if k != "copies_equal"})
        if diff: counts["CANDIDATE_CHANGED"] += 1
        if not cand["copies_equal"]: counts["MIRROR_MISMATCH"] += 1
        if a["flame"]: counts["FLAME_SAMPLES"] += 1
        if a["lockout"] or b["lockout"]: counts["LOCKOUT_SAMPLES"] += 1
        if not value["quality"]["status_coherent"]:
            counts["TRANSITION_WITHIN_PAIR"] += 1
        changes = status_changes(a, b)
        burst_until,last_mod_burst = update_burst(
            time.monotonic(), prev, a, b, {"burst_until":burst_until},
            last_mod_burst)
        events=event_rows(prev, a, changes, time.monotonic())
        if prev_cand and diff:
            events.append({"event":"CANDIDATE_CHANGE",
                           "old":prev_cand,"new":cand,
                           "at_monotonic":time.monotonic()})
        for event in events:
            if event["event"] in ("NATIVE_CHANGE_FLAME","FLAME_CHANGED_DURING_PAIR"):
                counts["FLAME_EDGES_OBSERVED"] += 1
            if event["event"] == "NATIVE_CHANGE_BYTE7":
                counts["P87_CHANGES"] += 1
            F.write_jsonl(streams["events"],{"cycle":cycle,"utc":utc(),**event})
        F.write_jsonl(streams["cycles"],{
            **{k:v for k,v in value.items()
               if k not in ("core_payload","context_payload")},
            "core_offset":core_offset,
            "context_offset":context_offset,
            "core_length":64,
            "context_length":len(value["context_payload"] or b""),
            "burst": start < burst_until,
            "events":len(events),
        })
        counts["CYCLES"] += 1
        counts["PACKETS"] += 4 + (len(CONTEXT_SPECS) if context_due else 0)
        if start < burst_until: counts["BURST_CYCLES"] += 1
        if pulse: pulse(cycle, value)
        prev, prev_cand = b, cand
        # No fixed 0.5-s claim: serial I/O and scheduled contextual reads
        # take non-atomic time, and actual timestamps are authoritative.
        period = BURST_INTERVAL_S if time.monotonic() < burst_until else BASELINE_INTERVAL_S
        remaining = period - (time.monotonic()-start)
        if remaining > 0 and stopper.signum is None:
            time.sleep(min(remaining, 2.0))
    if checkpoint: checkpoint("P300_FINISHING",counts)
    return {"p300_only_duration_s":round(time.monotonic()-t0,3),
            "cycles":counts["CYCLES"],"flame_edges":counts["FLAME_EDGES_OBSERVED"],
            "p87_changes":counts["P87_CHANGES"],
            "no_vs1_during_stream":True,
            "actual_rpm_during_stream_measured":False}


def validate_state(session):
    data = FOCUS.validate_state(session)
    F.DEEP.check_hash(session/"focus.py",data["focus_sha256"])
    if not 1 <= data["hours"] <= MAX_HOURS:
        raise RuntimeError("TEMPORAL_HOURS_OUT_OF_RANGE")
    return data


def progress(session, phase, start, hours, counts, extra=None):
    base=F.DEEP.load_local_base(Path(__file__).resolve().parent)
    base.h.atomic_json(session/"progress.json",{
        "state":"RUNNING_READ_ONLY","phase":phase,"updated_utc":utc(),
        "elapsed_s":round(time.monotonic()-start,3),"limit_hours":hours,
        "complete_cycles":counts["CYCLES"],"p300_packets":counts["PACKETS"],
        "native_flame_edges":counts["FLAME_EDGES_OBSERVED"],
        "native_p87_changes":counts["P87_CHANGES"],
        "mirror_mismatches":counts["MIRROR_MISMATCH"],
        "candidate_changes":counts["CANDIDATE_CHANGED"],
        "context_snapshots":counts["CONTEXT"],
        "within_pair_transitions":counts["TRANSITION_WITHIN_PAIR"],
        "p06_actual_rpm_available_during_p300":False,
        "extra":extra or {}})


def run_worker(session):
    state=validate_state(session)
    base=F.DEEP.load_local_base(session)
    h=base.h
    started=time.monotonic()
    deadline=started+state["hours"]*3600
    stop=F.DEEP.DeferredStop()
    for sig in (signal.SIGTERM,signal.SIGINT,signal.SIGHUP):
        signal.signal(sig,stop.on_signal)
    wire=handle=None
    streams={}
    counts=Counter()
    report={"version":VERSION,"start_utc":utc(),"errors":[],
            "read_only":True,"writes_issued":False,
            "actual_rpm_p300_verified":False,
            "observation_complete":False,"worker_vs1_restored":False,
            "initial_vs1":None,"final_vs1":None,"p300_stream":None}
    try:
        live=h.read_settings(h.SETTINGS.read_text())
        if live["port_optolink"]!=state["port"]:
            raise RuntimeError("TEMPORAL_PORT_CHANGED")
        if h.unit_state(h.MAIN).get("WorkingDirectory")!="/opt/optolink":
            raise RuntimeError("TEMPORAL_WRONG_PRODUCTION_PATH")
        for unit, active in state["services"].items():
            if (h.unit_state(unit).get("ActiveState")=="active")!=active:
                raise RuntimeError("TEMPORAL_SERVICE_CHANGED_"+unit)
        h.pause_services(session,state)
        base.isolation(state["port"])
        handle=h.open_serial(state["port"])
        for name in ("vs1","switch","trace","packets","cycles","events"):
            streams[name]=(session/(name+".jsonl")).open("x")
        for name in ("corebin","contextbin"):
            streams[name]=(session/("core-pairs.bin" if name=="corebin"
                                  else "context-frames.bin")).open("xb")
        delegate=base.UART1Wire(handle)
        delegate.trace_sink=streams["trace"]
        wire=FOCUS.FocusWire(delegate)
        delegate.send=wire.send
        wire.identify_vs1()
        report["initial_vs1"]=F.reference(wire,streams["vs1"],0,"PRE",
                                          stop=stop,seconds=REFERENCE_SECONDS)
        if not report["initial_vs1"]["identity_verified"] or (
                report["initial_vs1"]["p06_valid"] < 1):
            raise RuntimeError("TEMPORAL_INITIAL_VS1_P06_INVALID")
        if stop.signum is not None:raise RuntimeError("TEMPORAL_STOP_DURING_PRE")
        progress(session,"VS1_TO_P300",started,state["hours"],counts)
        F.switch(wire,streams["switch"],"TEMPORAL_VS1_TO_P300",True)
        progress(session,"P300_STREAM",started,state["hours"],counts)
        report["p300_stream"]=measurement_stream(
            session,wire,streams,stop,deadline,counts,
            checkpoint=lambda phase,c: progress(session,phase,started,state["hours"],c))
        F.switch(wire,streams["switch"],"TEMPORAL_P300_TO_VS1",False)
        report["final_vs1"]=F.reference(wire,streams["vs1"],0,"POST",
                                        stop=None,seconds=REFERENCE_SECONDS)
        if not report["final_vs1"]["identity_verified"] or (
                report["final_vs1"]["p06_valid"] < 1):
            raise RuntimeError("TEMPORAL_FINAL_VS1_P06_INVALID")
        report["observation_complete"]=True
    except BaseException as exc:
        report["errors"].append(str(exc) or type(exc).__name__)
    finally:
        # Do not let a later systemd SIGTERM interrupt the recovery handshake.
        for sig in (signal.SIGTERM,signal.SIGINT,signal.SIGHUP):
            signal.signal(sig,signal.SIG_IGN)
        if wire:
            try:
                last=wire.restore_final_gfa()
                report["recovery_gfa"]=last
                report["worker_vs1_restored"]=(last[0]["hex"]=="20" and last[1]["valid"])
            except BaseException as exc:
                report["errors"].append("VS1_LINK_RECOVERY:"+str(exc))
            try:
                wire.w.flush_trace()
                report["trace_records"]=wire.w.trace_records_written
            except BaseException as exc:
                report["errors"].append("TRACE_FLUSH:"+str(exc))
        for name,stream in streams.items():
            try:
                F.sync_stream(stream)
                stream.close()
            except BaseException as exc:
                report["errors"].append("CLOSE_"+name+":"+str(exc))
        if handle:
            try:handle.close()
            except BaseException as exc:report["errors"].append("SERIAL_CLOSE:"+str(exc))
        report["end_utc"],report["duration_s"]=utc(),round(time.monotonic()-started,3)
        report["counts"]=dict(counts)
        report["signal"]=stop.signum
        report["data_quality"]="COMPLETE" if report["observation_complete"] else "PARTIAL"
        h.atomic_json(session/"measurement.json",report)
        h.atomic_json(session/"progress.json",{
            "state":"WORKER_EXITED_RECOVERY_PENDING","end_utc":utc(),
            "counts":dict(counts),"errors":report["errors"],
            "worker_vs1_restored":report["worker_vs1_restored"],
            "data_quality":report["data_quality"]})
    return 0 if report["worker_vs1_restored"] and report["observation_complete"] else 1


def worker(session):
    with F.DEEP.load_local_base(session).locks():
        return run_worker(session)


def archive(session):
    if ROOT.is_symlink() or BUNDLES.is_symlink():
        raise RuntimeError("TEMPORAL_UNSAFE_ARCHIVE_ROOT")
    BUNDLES.mkdir(parents=True,exist_ok=True,mode=0o700)
    os.chmod(BUNDLES,0o700)
    dest=BUNDLES/("p300-temporal-"+session.name+"-bundle.tar.gz")
    if dest.is_file() and not dest.is_symlink():
        return dest
    if dest.exists() or dest.is_symlink():
        raise RuntimeError("TEMPORAL_UNSAFE_ARCHIVE")
    members=sorted(p for p in session.rglob("*") if p.is_file())
    manifest={"version":VERSION,"session":session.name,
              "read_only":True,"actual_rpm_p300_verified":False,
              "files":{}}
    for f in members:
        st=f.lstat()
        if f.is_symlink() or not stat.S_ISREG(st.st_mode) or (
                st.st_uid!=0 or st.st_mode&0o077):
            raise RuntimeError("TEMPORAL_UNSAFE_MEMBER_"+f.name)
        rel=f.relative_to(session).as_posix()
        manifest["files"][rel]={"sha256":F.sha256(f),"size":st.st_size}
    if sum(v["size"] for v in manifest["files"].values())>MAX_SESSION:
        raise RuntimeError("TEMPORAL_ARCHIVE_TOO_LARGE")
    tmp=None
    try:
        with tempfile.NamedTemporaryFile(prefix="p300-temporal-",
                                         suffix=".tar.gz",dir=BUNDLES,
                                         delete=False) as h:
            tmp=Path(h.name)
        os.chmod(tmp,0o600)
        with tarfile.open(tmp,"w:gz") as out:
            for f in members:
                out.add(f,arcname="p300-temporal/"+f.relative_to(session).as_posix(),
                        recursive=False)
            raw=(json.dumps(manifest,sort_keys=True,indent=2)+"\n").encode()
            info=tarfile.TarInfo("p300-temporal/bundle-manifest.json")
            info.size,info.mode=len(raw),0o600
            out.addfile(info,io.BytesIO(raw))
        os.replace(tmp,dest)
    finally:
        if tmp:tmp.unlink(missing_ok=True)
    return dest


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
                errors.append("MAIN_UNAVAILABLE_DEFER_HELPERS:"+str(exc))
        if not errors:
            for unit in reversed(state["restore"]):
                if unit==h.MAIN:continue
                try:
                    h.command(["systemctl","start",unit])
                    if unit!="optolink-clock-sync.service" and (
                            h.unit_state(unit).get("ActiveState")!="active"):
                        raise RuntimeError("UNIT_INACTIVE")
                    units.append(unit)
                except BaseException as exc:errors.append(unit+":"+str(exc))
        h.atomic_json(session/"recovery.json",{
            "services_restored":not errors,"units_restored":units,
            "errors":errors,"systemd_result":os.getenv("SERVICE_RESULT","unknown")})
    try:
        health=F.DEEP.post_restore_health(base)
        h.atomic_json(session/"health.json",health)
        healthy=bool(health.get("production_main_verified") and
                     health.get("gfa_reads",{}).get("P80",{}).get("format_and_identity_verified") and
                     health.get("gfa_reads",{}).get("P06",{}).get("format_and_identity_verified") and
                     health.get("gfa_reads",{}).get("P06",{}).get("p06_non_ff_verified"))
        old=json.loads((session/"progress.json").read_text()) if (
            session/"progress.json").is_file() else {}
        old.update(state="RESTORED" if healthy and not errors else "RESTORE_NOT_VERIFIED",
                   restored_utc=utc(),services_restored=not errors,
                   p80_p06_production_health_verified=healthy)
        h.atomic_json(session/"progress.json",old)
        if not healthy:errors.append("PRODUCTION_P80_P06_NOT_VERIFIED")
    except BaseException as exc:errors.append("POST_RESTORE_HEALTH:"+str(exc))
    try:
        dest=archive(session)
        print("UPLOAD_ONE_FILE="+str(dest),flush=True)
    except BaseException as exc:errors.append("ARCHIVE:"+str(exc))
    return int(bool(errors))


def competing(base):
    banned={UNIT,CURRENT_UNIT,FOCUS.UNIT,F.UNIT,F.DEEP.UNIT,
            *F.DEEP.SELF_NAMED_SERVICE_UNITS}
    for unit in sorted(banned):
        if base.h.unit_state(unit).get("ActiveState") not in ("inactive","failed"):
            raise RuntimeError("TEMPORAL_COMPETING_LOGGER:"+unit)


def guard_finished_focus(root=None, bundles=None):
    root=(Path("/root/p300-trial-work/p300-p06-focus-results")
          if root is None else Path(root))
    bundles=BUNDLES if bundles is None else Path(bundles)
    if root.is_symlink():
        raise RuntimeError("TEMPORAL_FOCUS_ROOT_SYMLINK")
    if not root.exists():return
    matches=sorted(p for p in root.glob("run-*") if p.is_dir())
    if not matches:return
    recent=matches[-1]
    if recent.is_symlink():
        raise RuntimeError("TEMPORAL_FOCUS_SESSION_SYMLINK")
    rec=recent/"recovery.json"
    health=recent/"health.json"
    if not rec.is_file() or not health.is_file():
        raise RuntimeError("TEMPORAL_PREVIOUS_FOCUS_RECOVERY_NOT_COMPLETE")
    r=json.loads(rec.read_text())
    h=json.loads(health.read_text())
    if (not r.get("services_restored") or
        not h.get("production_main_verified") or
        not h.get("gfa_reads",{}).get("P80",{}).get("format_and_identity_verified") or
        not h.get("gfa_reads",{}).get("P06",{}).get("format_and_identity_verified") or
        not h.get("gfa_reads",{}).get("P06",{}).get("p06_non_ff_verified")):
        raise RuntimeError("TEMPORAL_PREVIOUS_FOCUS_VS1_HEALTH_UNRESOLVED")
    archive=bundles/("p300-p06-focus-"+recent.name+"-bundle.tar.gz")
    if archive.is_symlink() or not archive.is_file():
        raise RuntimeError("TEMPORAL_PREVIOUS_FOCUS_ARCHIVE_MISSING")


def start(hours):
    if os.geteuid()!=0:
        raise RuntimeError("TEMPORAL_ROOT_REQUIRED")
    if type(hours) is not int or not 1<=hours<=MAX_HOURS:
        raise RuntimeError("TEMPORAL_HOURS_MUST_BE_1_TO_3")
    if any(p.is_symlink() for p in (PROJECT,ROOT,BUNDLES)):
        raise RuntimeError("TEMPORAL_UNSAFE_ROOT")
    base=F.DEEP.load_local_base(PROJECT/"tools")
    h=base.h
    with base.locks():
        # No hardware or writer pause before these preflight gates.
        settings,services=h.preflight()
        competing(base)
        guard_finished_focus()
        if shutil.disk_usage(PROJECT).free<PREFLIGHT_FREE:
            raise RuntimeError("TEMPORAL_PREFLIGHT_REQUIRES_768MIB")
        ROOT.mkdir(parents=True,exist_ok=True,mode=0o700)
        os.chmod(ROOT,0o700)
        for f in ROOT.glob("run-*/state.json"):
            d=json.loads(f.read_text())
            rec=f.with_name("recovery.json")
            health=f.with_name("health.json")
            if d.get("restore") and (not rec.is_file() or
                  not json.loads(rec.read_text()).get("services_restored") or
                  not health.is_file()):
                raise RuntimeError("TEMPORAL_OLDER_RESTORE_UNRESOLVED")
        session=ROOT/("run-"+dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")+
                      "-"+str(os.getpid()))
        session.mkdir(mode=0o700)
        sources={"logger.py":Path(__file__).resolve(),
                 "focus.py":PROJECT/"tools"/"wb2a-p300-p06-focus.py",
                 "fullram.py":PROJECT/"tools"/FOCUS.FULL_NAME,
                 "deep.py":PROJECT/"tools"/FOCUS.DEEP_NAME,
                 "base.py":PROJECT/"tools"/FOCUS.BASE_NAME,
                 FOCUS.HELPER_NAME:PROJECT/"tools"/FOCUS.HELPER_NAME}
        hashes={}
        for name,src in sources.items():
            if src.is_symlink() or not src.is_file():
                raise RuntimeError("TEMPORAL_SOURCE_INVALID:"+name)
            shutil.copyfile(src,session/name)
            os.chmod(session/name,0o600)
            hashes[name]=F.sha256(session/name)
        commit=h.command(["git","-C",str(PROJECT),"rev-parse","HEAD"]).strip()
        h.atomic_json(session/"state.json",{
            "version":VERSION,"hours":hours,"services":services,"restore":[],
            "port":settings["port_optolink"],"source_checkout_sha":commit,
            "logger_sha256":hashes["logger.py"],"focus_sha256":hashes["focus.py"],
            "fullram_sha256":hashes["fullram.py"],"deep_sha256":hashes["deep.py"],
            "base_sha256":hashes["base.py"],
            "helper_sha256":hashes[FOCUS.HELPER_NAME]})
    command=["systemd-run","--unit="+UNIT,"--no-block","--collect",
             "--property=Type=exec","--property=Restart=no",
             "--property=TimeoutStopSec=300","--property=KillMode=control-group",
             "--property=UMask=0077",
             "--property=ExecStopPost="+PYTHON+" -u "+str(session/"logger.py")+
               " --recover "+str(session),
             PYTHON,"-u",str(session/"logger.py"),"--worker",str(session)]
    output=subprocess.run(command,capture_output=True,text=True,check=False,timeout=30)
    if output.returncode:
        raise RuntimeError("TEMPORAL_SYSTEMD_START_FAILED:"+output.stderr[-500:])
    print("SESSION="+str(session),flush=True)
    print("UNIT="+UNIT,flush=True)
    print("HOURS="+str(hours),flush=True)
    print("READ_ONLY_P300_TEMPORAL=YES",flush=True)
    return 0


def latest():
    if ROOT.is_symlink() or not ROOT.is_dir():
        raise RuntimeError("TEMPORAL_NO_SESSION")
    sessions=sorted(x for x in ROOT.glob("run-*") if x.is_dir() and not x.is_symlink())
    if not sessions:
        raise RuntimeError("TEMPORAL_NO_SESSION")
    return sessions[-1]


def status():
    session=latest()
    base=F.DEEP.load_local_base(PROJECT/"tools")
    print("SESSION="+str(session))
    print("UNIT_STATE="+base.h.unit_state(UNIT).get("ActiveState","unknown"))
    for name in ("progress.json","recovery.json","health.json"):
        file=session/name
        if file.is_file():
            print(name.upper()+"="+file.read_text().strip())
    file=BUNDLES/("p300-temporal-"+session.name+"-bundle.tar.gz")
    if file.is_file():print("UPLOAD_ONE_FILE="+str(file))
    return 0


def stop():
    session=latest()
    base=F.DEEP.load_local_base(PROJECT/"tools")
    phase=base.h.unit_state(UNIT).get("ActiveState")
    if phase in ("active","activating","deactivating"):
        result=subprocess.run(["systemctl","stop",UNIT],
                              capture_output=True,text=True,check=False,timeout=360)
        if result.returncode:
            print("SYSTEMCTL_STOP_FAILED="+result.stderr[-500:],file=sys.stderr)
    elif phase not in ("inactive","failed"):
        raise RuntimeError("TEMPORAL_SYSTEMD_STATE_UNKNOWN:"+str(phase))
    file=BUNDLES/("p300-temporal-"+session.name+"-bundle.tar.gz")
    for _ in range(45):
        if (session/"recovery.json").is_file() and file.is_file():break
        time.sleep(1)
    r=json.loads((session/"recovery.json").read_text()) if (
        session/"recovery.json").is_file() else {}
    h=json.loads((session/"health.json").read_text()) if (
        session/"health.json").is_file() else {}
    healthy=bool(r.get("services_restored") and
        h.get("production_main_verified") and
        h.get("gfa_reads",{}).get("P80",{}).get("format_and_identity_verified") and
        h.get("gfa_reads",{}).get("P06",{}).get("p06_non_ff_verified"))
    print("RESTORE_AND_P06_HEALTH="+("PASS" if healthy else "NOT_VERIFIED"))
    print("UPLOAD_ONE_FILE="+str(file) if file.is_file() else "ARCHIVE_UNAVAILABLE")
    return 0 if healthy and file.is_file() else 1


def main():
    p=argparse.ArgumentParser(description=__doc__)
    group=p.add_mutually_exclusive_group()
    for flag in ("start","stop","status"):group.add_argument("--"+flag,action="store_true")
    group.add_argument("--worker",type=Path)
    group.add_argument("--recover",type=Path)
    p.add_argument("--hours",type=int,default=DEFAULT_HOURS)
    args=p.parse_args()
    os.umask(0o077)
    if args.worker or args.recover:
        if os.geteuid()!=0 or "INVOCATION_ID" not in os.environ:
            p.error("supervised root systemd required")
        return worker(args.worker) if args.worker else recover(args.recover)
    if args.start:return start(args.hours)
    if args.status:return status()
    if args.stop:return stop()
    print("PLAN ONLY:",VERSION)
    print("VS1 references; exactly one P300 entry; FC01/11 before/after two FC03/32 blocks.")
    print("Optional four fixed RAM context blocks every 12 seconds; burst on natural flame/state transitions.")
    print("P06 actual RPM never inferred under P300; read-only, 1..3h, 24k-cycle cap.")
    print("Previous P06-focus restore+P80/P06 non-FF must pass before starting.")
    return 0


if __name__=="__main__":
    try:raise SystemExit(main())
    except (RuntimeError,ValueError,OSError,subprocess.SubprocessError) as exc:
        print("REFUSED_OR_FAILED="+str(exc),file=sys.stderr)
        raise SystemExit(1)
