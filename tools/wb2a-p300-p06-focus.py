#!/usr/bin/env python3
"""Short read-only P300 candidate windows with *real* VS1 GFA-P06 brackets.

WB2A/VDensHO1 device 20C2, software 0103, P80=20. Never interpret
P09, 55D3 or RAM-state correlation as actual fan RPM. No boiler writes.
The single supervised serial owner pauses and later restores VS1 services.
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

VERSION = "1.0.0-p06-focus-bracket"
PROJECT = Path("/root/p300-trial-work/project")
ROOT = Path("/root/p300-trial-work/p300-p06-focus-results")
BUNDLES = Path("/root/p300-trial-work/research-bundles")
UNIT = "optolink-p300-p06-focus.service"
PYTHON = "/opt/optolink/venv/bin/python"
SELF_NAME = "wb2a-p300-p06-focus.py"
FULL_NAME = "wb2a-p300-fullram-logger.py"
DEEP_NAME = "wb2a-p300-deep-logger.py"
BASE_NAME = "wb2a-uart1-overnight.py"
HELPER_NAME = "wb2a-handover-probe.py"
DEFAULT_HOURS, MAX_HOURS = 1, 3
REFERENCE_SECONDS = 3.0
STATUS_SPEC = (1, 0x55D3, 11)
# All previously measured physical RAM, exactly six 32-byte ranges.
RAM_ADDRESSES = (0x0F00, 0x0F20, 0x0F40, 0x1C40, 0x1C60, 0x1C80)
RAM_SPECS = tuple((3, a, 32) for a in RAM_ADDRESSES)
ALLOWED_SPECS = frozenset((STATUS_SPEC, *RAM_SPECS))
CANDIDATES = (0x0F20, 0x0F29, 0x1C76)
ROUNDS_PER_CAPTURE = 2
MAX_CAPTURES = 100
PROGRESS_SECONDS = 20
MIN_FREE = 256 * 1024 * 1024
MAX_SESSION = 128 * 1024 * 1024
MAX_SINGLE_LOG = 64 * 1024 * 1024
PREFLIGHT_FREE = MIN_FREE + 2 * MAX_SESSION


def utc():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def load_fullram(directory: Path):
    path = Path(directory) / ("fullram.py" if (Path(directory)/"fullram.py").is_file() else FULL_NAME)
    if path.is_symlink() or not path.is_file():
        raise RuntimeError("FOCUS_PINNED_FULLRAM_MISSING")
    spec = importlib.util.spec_from_file_location("focus_pinned_fullram", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


F = load_fullram(Path(__file__).resolve().parent)
# Use existing tested low-level routines; no physical action at import time.
F.ROOT, F.BUNDLES = ROOT, BUNDLES


def frame(spec):
    if spec not in ALLOWED_SPECS:
        raise ValueError("FOCUS_UNREVIEWED_READ")
    return F.request_frame(*spec)


class FocusWire(F.FullRamWire):
    @staticmethod
    def permitted(phase, raw, base):
        if phase != "p300":
            return F.FullRamWire.permitted(phase, raw, base)
        return raw == b"\x06" or raw in {frame(s) for s in ALLOWED_SPECS}

    def packet(self, spec):
        frame(spec)  # fail closed before any I/O
        return super().packet(spec)


def select_level(pre, previous, now):
    """Do not consume serial time repeatedly on the already known 0/2490 bins."""
    if not pre.get("identity_verified") or not pre.get("stable"):
        return None
    rpm = pre.get("p06_rpm_unique", [])
    raw = pre.get("p06_raw_unique", [])
    if len(rpm) != 1 or len(raw) != 1 or not 0 <= rpm[0] <= 7620:
        return None
    if rpm[0] == 0:
        level, cap, cooldown = "OFF", 3, 300
    elif rpm[0] == 2490:
        level, cap, cooldown = "P06_2490", 3, 240
    elif rpm[0] > 2490:
        level, cap, cooldown = "HIGH_" + raw[0], 3, 20
    else:
        level, cap, cooldown = "OTHER_" + raw[0], 3, 40
    last, count = previous.get(level, (-1e12, 0))
    if count >= cap or now - last < cooldown:
        return None
    return level


def classify_capture(pre, post, status):
    if (not pre or not post or not pre.get("stable") or not post.get("stable")
            or not pre.get("identity_verified") or not post.get("identity_verified")
            or pre.get("p06_raw_unique") != post.get("p06_raw_unique")
            or len(pre.get("p06_rpm_unique", [])) != 1
            or len(post.get("p06_rpm_unique", [])) != 1
            or pre["p06_rpm_unique"] != post["p06_rpm_unique"]
            or len(status) != ROUNDS_PER_CAPTURE + 1
            or len({s["flame"] for s in status}) != 1):
        return "TRANSITION_OR_UNKNOWN"
    value = pre["p06_rpm_unique"][0]
    return "STABLE_OFF" if value == 0 else ("STABLE_2490" if value == 2490 else
                                            "STABLE_OTHER_POSITIVE")


def get_candidates(payload_by_addr):
    result = {}
    for addr in CANDIDATES:
        block = addr - (addr % 32)
        # 0x0F20, 0x0F29 and 0x1C76 all lie inside this fixed allowlist.
        if block not in payload_by_addr:
            raise RuntimeError("FOCUS_MISSING_CANDIDATE_BLOCK")
        result[f"0x{addr:04x}"] = f"{payload_by_addr[block][addr-block]:02x}"
    return result


def storage_guard(session, streams=()):
    if shutil.disk_usage(session).free < MIN_FREE:
        raise RuntimeError("FOCUS_LOW_DISK")
    total = 0
    for p in session.rglob("*"):
        if p.is_symlink():
            raise RuntimeError("FOCUS_UNEXPECTED_SYMLINK")
        if p.is_file():
            total += p.stat().st_size
    if total > MAX_SESSION:
        raise RuntimeError("FOCUS_SESSION_LIMIT")
    if any(s and not s.closed and s.tell() > MAX_SINGLE_LOG for s in streams):
        raise RuntimeError("FOCUS_STREAM_LIMIT")


def capture(session, wire, streams, ident, pre, stopper):
    """Never assert stable RPM when return-to-VS1 or P06 post reads fail."""
    name = f"c{ident:05d}"
    rec = {"id": ident, "version": VERSION, "start_utc": utc(),
           "start_monotonic": time.monotonic(), "pre": pre, "post": None,
           "marker": "PARTIAL", "classification": "TRANSITION_OR_UNKNOWN",
           "read_only": True, "p06_alias_verified": False,
           "rounds_complete": 0, "packets_ok": 0, "statuses": [], "rounds": [],
           "errors": [], "scope": [f"0x{x:04x}/32" for x in RAM_ADDRESSES]}
    try:
        F.switch(wire, streams["switch"], name + "_VS1_TO_P300", True)
        status = F.read_status(wire, streams["status"], ident, 0)
        if bytes.fromhex(status["payload_hex"])[7] == 0xFF:
            raise RuntimeError("FOCUS_STATUS_P87_INVALID_FF")
        rec["statuses"].append(status)
        for round_no in range(1, ROUNDS_PER_CAPTURE + 1):
            packets = []
            payload = {}
            tmp = session/"captures"/(f"{name}-r{round_no}.partial.bin")
            with tmp.open("xb") as out:
                for spec in RAM_SPECS:
                    # no mid-frame stop; deferred SIGTERM is inspected between requests
                    if stopper.signum is not None:
                        rec["stop_reason"] = "SIGNAL_AFTER_COMPLETE_SERIAL_FRAME"
                        break
                    pkt = wire.packet(spec)
                    rec["packets_ok"] += 1
                    data = pkt["data"]
                    payload[spec[1]] = data
                    out.write(data)
                    row = F.emit_packet(pkt, ident, rec["packets_ok"])
                    row.update(round=round_no, candidate_level=pre["p06_raw_unique"],
                               verified_rpm_during_p300=False)
                    F.write_jsonl(streams["ram"], row)
                    packets.append(row)
                F.sync_stream(out)
            if len(payload) != len(RAM_SPECS):
                break
            final = tmp.with_suffix("").with_suffix(".bin")
            os.replace(tmp, final)
            rec["rounds"].append({"round": round_no, "file": final.name,
                "sha256": F.sha256(final), "bytes": final.stat().st_size,
                "candidates": get_candidates(payload),
                "first_tx_utc": packets[0]["tx_utc"],
                "last_rx_utc": packets[-1]["rx_utc"]})
            rec["rounds_complete"] += 1
            status = F.read_status(wire, streams["status"], ident, round_no)
            if bytes.fromhex(status["payload_hex"])[7] == 0xFF:
                raise RuntimeError("FOCUS_STATUS_P87_INVALID_FF")
            rec["statuses"].append(status)
            if stopper.signum is not None:
                break
        # After a read-only serial transaction ends, a requested stop is allowed
        # to proceed via the known safe VS1 return rather than a new P300 read.
        F.switch(wire, streams["switch"], name + "_P300_TO_VS1", False)
        # One bounded post-reference, even if stop was requested during P300.
        rec["post"] = F.reference(wire, streams["vs1"], ident, "POST",
                                    stop=None, seconds=REFERENCE_SECONDS)
        if rec["rounds_complete"] == ROUNDS_PER_CAPTURE and len(rec["statuses"]) == 3:
            rec["classification"] = classify_capture(pre, rec["post"], rec["statuses"])
            rec["marker"] = "COMPLETE"
    except BaseException as exc:
        rec["errors"].append(str(exc) or type(exc).__name__)
        # Do not invent a post-P06 reference after failed P300->VS1 identification.
        raise
    finally:
        rec["end_utc"], rec["end_monotonic"] = utc(), time.monotonic()
        rec["duration_s"] = round(rec["end_monotonic"] - rec["start_monotonic"], 3)
        F.DEEP.load_local_base(Path(__file__).resolve().parent).h.atomic_json(
            session/"captures"/(name + ".json"), rec)
        for stream in streams.values():
            F.sync_stream(stream)
    return rec


def validate_state(session):
    state = F.validate_state(session)
    F.DEEP.check_hash(session/"fullram.py", state["fullram_sha256"])
    if not 1 <= state["hours"] <= MAX_HOURS:
        raise RuntimeError("FOCUS_INVALID_DURATION")
    return state


def progress(session, stage, elapsed, counts, last=None):
    base = F.DEEP.load_local_base(Path(__file__).resolve().parent)
    sw = session/"switch.jsonl"
    switch_count = sum(1 for line in sw.open() if line.strip()) if sw.exists() else 0
    base.h.atomic_json(session/"progress.json", {
        "state": "RUNNING_READ_ONLY", "stage": stage, "updated_utc": utc(),
        "elapsed_s": round(elapsed, 3), "captures_complete": counts["COMPLETE"],
        "captures_partial": counts["PARTIAL"], "stable_off": counts["STABLE_OFF"],
        "stable_2490": counts["STABLE_2490"],
        "stable_other_positive": counts["STABLE_OTHER_POSITIVE"],
        "transition_or_unknown": counts["TRANSITION_OR_UNKNOWN"],
        "reference_windows": counts["OBS"], "p300_ram_packets": counts["PACKETS"],
        "switch_count": switch_count, "last_capture": last})


def run_worker(session):
    base = F.DEEP.load_local_base(session)
    h = base.h
    state = validate_state(session)
    start = time.monotonic()
    deadline = start + state["hours"]*3600
    stopper = F.DEEP.DeferredStop()
    for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        signal.signal(sig, stopper.on_signal)
    counts, last_by_level = Counter(), {}
    streams = {}
    wire = handle = None
    report = {"version": VERSION, "start_utc": utc(), "errors": [],
              "worker_vs1_restored": False, "operator_stop": False,
              "observation_finished": False, "write_commands_issued": False,
              "p06_alias_verified": False, "captures": []}
    try:
        live = h.read_settings(h.SETTINGS.read_text())
        if live["port_optolink"] != state["port"]:
            raise RuntimeError("FOCUS_PORT_CHANGED")
        if h.unit_state(h.MAIN).get("WorkingDirectory") != "/opt/optolink":
            raise RuntimeError("FOCUS_WRONG_PRODUCTIVE_CHECKOUT")
        for u, previous in state["services"].items():
            if (h.unit_state(u).get("ActiveState") == "active") != previous:
                raise RuntimeError("FOCUS_SERVICE_STATE_CHANGED_" + u)
        h.pause_services(session, state)
        base.isolation(state["port"])
        handle = h.open_serial(state["port"])
        (session/"captures").mkdir(mode=0o700)
        for name in ("vs1", "ram", "status", "switch", "trace"):
            streams[name] = (session/(name + ".jsonl")).open("x")
        delegate = base.UART1Wire(handle)
        delegate.trace_sink = streams["trace"]
        wire = FocusWire(delegate)
        delegate.send = wire.send
        wire.identify_vs1()
        first = [wire.vs1_read(k) for k in ("P80", "P06")]
        if first[0]["hex"] != "20" or not first[1]["valid"]:
            raise RuntimeError("FOCUS_INITIAL_GFA_UNVERIFIED")
        report["initial_gfa"] = first
        progress(session, "VS1_OBSERVE", time.monotonic()-start, counts)
        print("FOCUS_LOGGER_STARTED=READ_ONLY_P06_CANDIDATES", flush=True)
        while (time.monotonic() < deadline and stopper.signum is None and
               counts["COMPLETE"] + counts["PARTIAL"] < MAX_CAPTURES):
            storage_guard(session, streams.values())
            base.isolation(state["port"])
            obs_id = counts["OBS"] + 1
            pre = F.reference(wire, streams["vs1"], obs_id, "OBS", stop=stopper,
                              seconds=REFERENCE_SECONDS)
            counts["OBS"] += 1
            for val in pre.get("p06_rpm_unique", []):
                if val > 0: counts["OBS_POSITIVE"] += 1
                else: counts["OBS_ZERO"] += 1
            if stopper.signum is not None or time.monotonic() >= deadline:
                break
            level = select_level(pre, last_by_level, time.monotonic())
            if level is not None:
                idx = counts["COMPLETE"] + counts["PARTIAL"] + 1
                last_by_level[level] = (time.monotonic(), last_by_level.get(level, (0,0))[1]+1)
                try:
                    record = capture(session, wire, streams, idx, pre, stopper)
                except BaseException as exc:
                    report["errors"].append("CAPTURE_" + str(idx) + ":" + str(exc))
                    counts["PARTIAL"] += 1
                    break
                counts[record["marker"]] += 1
                counts[record["classification"]] += 1
                counts["PACKETS"] += record["packets_ok"]
                report["captures"].append({"id": idx, "marker": record["marker"],
                    "classification": record["classification"], "pre_p06_rpm":pre["p06_rpm_unique"],
                    "post_p06_rpm":record["post"].get("p06_rpm_unique") if record["post"] else None})
            progress(session, "VS1_OBSERVE", time.monotonic()-start, counts,
                     report["captures"][-1] if report["captures"] else None)
        report["operator_stop"] = stopper.signum is not None
        report["observation_finished"] = not report["errors"]
    except BaseException as exc:
        report["errors"].append(str(exc) or type(exc).__name__)
    finally:
        for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
            signal.signal(sig, signal.SIG_IGN)
        if wire:
            try:
                last = wire.restore_final_gfa()
                report["final_gfa"] = last
                report["worker_vs1_restored"] = last[0]["hex"] == "20" and last[1]["valid"]
            except BaseException as exc:
                report["errors"].append("WORKER_RECOVERY:" + str(exc))
            try:
                wire.w.flush_trace()
                report["trace_events"] = wire.w.trace_records_written
            except BaseException as exc:
                report["errors"].append("TRACE_FLUSH:" + str(exc))
        for name, stream in streams.items():
            try:
                F.sync_stream(stream)
                stream.close()
            except BaseException as exc:
                report["errors"].append("LOG_CLOSE_" + name + ":" + str(exc))
        if handle:
            try: handle.close()
            except BaseException as exc: report["errors"].append("SERIAL_CLOSE:" + str(exc))
        report["end_utc"] = utc()
        report["elapsed_s"] = round(time.monotonic()-start, 3)
        report["counts"] = dict(counts)
        h.atomic_json(session/"measurement.json", report)
        h.atomic_json(session/"progress.json", {"state":"WORKER_EXITED_RECOVERY_PENDING",
            "end_utc":utc(), "counts":dict(counts), "errors":report["errors"],
            "worker_vs1_restored":report["worker_vs1_restored"]})
    return 0 if report["observation_finished"] and report["worker_vs1_restored"] else 1


def worker(session):
    base = F.DEEP.load_local_base(session)
    with base.locks():
        return run_worker(session)


def archive(session):
    if ROOT.is_symlink() or BUNDLES.is_symlink():
        raise RuntimeError("FOCUS_UNSAFE_ARCHIVE_ROOT")
    BUNDLES.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(BUNDLES, 0o700)
    dest = BUNDLES/("p300-p06-focus-" + session.name + "-bundle.tar.gz")
    if dest.exists():
        if dest.is_symlink() or not dest.is_file():
            raise RuntimeError("FOCUS_UNSAFE_EXISTING_ARCHIVE")
        return dest
    filenames = sorted(p for p in session.rglob("*") if p.is_file())
    manifest = {"version": VERSION, "session":session.name, "read_only": True,
                "p06_alias_verified": False, "files": {}}
    for file in filenames:
        st = file.lstat()
        if file.is_symlink() or not stat.S_ISREG(st.st_mode) or st.st_uid != 0 or st.st_mode&0o077:
            raise RuntimeError("FOCUS_UNSAFE_ARCHIVE_MEMBER_" + file.name)
        rel = file.relative_to(session).as_posix()
        manifest["files"][rel] = {"sha256":F.sha256(file), "size":st.st_size}
    if sum(row["size"] for row in manifest["files"].values()) > MAX_SESSION:
        raise RuntimeError("FOCUS_ARCHIVE_SIZE_LIMIT")
    tmp = None
    try:
        with tempfile.NamedTemporaryFile(prefix="p300-p06-focus-",suffix=".tar.gz",
                                         dir=BUNDLES,delete=False) as h:
            tmp = Path(h.name)
        os.chmod(tmp,0o600)
        with tarfile.open(tmp,"w:gz") as out:
            for path in filenames:
                out.add(path,arcname="p300-p06-focus/"+path.relative_to(session).as_posix(),
                        recursive=False)
            content = (json.dumps(manifest,sort_keys=True,indent=2)+"\n").encode()
            entry = tarfile.TarInfo("p300-p06-focus/bundle-manifest.json")
            entry.size,entry.mode=len(content),0o600
            out.addfile(entry,io.BytesIO(content))
        os.replace(tmp,dest)
    finally:
        if tmp: tmp.unlink(missing_ok=True)
    return dest


def recover(session):
    state = validate_state(session)
    base = F.DEEP.load_local_base(session)
    h = base.h
    errors, restored = [], []
    with base.locks():
        if h.MAIN in state["restore"]:
            try:
                h.command(["systemctl","start",h.MAIN])
                h.wait_main_ready()
                restored.append(h.MAIN)
            except BaseException as exc:
                errors.append("MAIN_NOT_READY_DEFER_HELPERS:"+str(exc))
        if not errors:
            for unit in reversed(state["restore"]):
                if unit == h.MAIN: continue
                try:
                    h.command(["systemctl","start",unit])
                    if unit != "optolink-clock-sync.service" and h.unit_state(unit).get("ActiveState")!="active":
                        raise RuntimeError("SERVICE_NOT_ACTIVE_"+unit)
                    restored.append(unit)
                except BaseException as exc:
                    errors.append(unit+":"+str(exc))
        h.atomic_json(session/"recovery.json", {"services_restored":not errors,
                      "units_restored":restored,"errors":errors,
                      "systemd_result":os.getenv("SERVICE_RESULT","unknown")})
    try:
        health = F.DEEP.post_restore_health(base)
        h.atomic_json(session/"health.json",health)
        progress_file = session/"progress.json"
        last = json.loads(progress_file.read_text()) if progress_file.is_file() else {}
        healthy = bool(health.get("production_main_verified") and all(
                     health.get("gfa_reads",{}).get(k,{}).get("format_and_identity_verified")
                     for k in ("P80","P06")))
        last.update(state="RESTORED" if not errors and healthy else "RESTORE_NOT_VERIFIED",
                    restored_utc=utc(),services_restored=not errors,
                    p80_p06_verified=healthy)
        h.atomic_json(progress_file,last)
        if not healthy:
            errors.append("PRODUCTIVE_P80_P06_HEALTH_NOT_VERIFIED")
    except BaseException as exc:
        errors.append("HEALTH:"+str(exc))
    try:
        dest=archive(session)
        print("UPLOAD_ONE_FILE="+str(dest),flush=True)
    except BaseException as exc:
        errors.append("ARCHIVE:"+str(exc))
    return int(bool(errors))


def verify_competing(base):
    for unit in (UNIT,F.UNIT,F.DEEP.UNIT,*F.DEEP.SELF_NAMED_SERVICE_UNITS):
        if base.h.unit_state(unit).get("ActiveState") not in ("inactive","failed"):
            raise RuntimeError("FOCUS_COMPETING_PROBE_"+unit)


def start(hours):
    if os.geteuid()!=0: raise RuntimeError("FOCUS_ROOT_REQUIRED")
    if type(hours) is not int or not 1<=hours<=MAX_HOURS:
        raise RuntimeError("FOCUS_HOURS_MUST_BE_1_TO_3")
    if any(p.is_symlink() for p in (PROJECT,ROOT,BUNDLES)):
        raise RuntimeError("FOCUS_UNSAFE_RESEARCH_ROOT")
    base=F.DEEP.load_local_base(PROJECT/"tools")
    h=base.h
    with base.locks():
        cfg,services=h.preflight()
        verify_competing(base)
        if shutil.disk_usage(PROJECT).free<PREFLIGHT_FREE:
            raise RuntimeError("FOCUS_PREFLIGHT_NEEDS_512MIB_FREE")
        ROOT.mkdir(parents=True,exist_ok=True,mode=0o700)
        os.chmod(ROOT,0o700)
        for old in ROOT.glob("run-*/state.json"):
            prev=json.loads(old.read_text())
            restore=old.with_name("recovery.json")
            if prev.get("restore") and (not restore.is_file() or
                not json.loads(restore.read_text()).get("services_restored")):
                raise RuntimeError("FOCUS_PREVIOUS_RESTORE_UNRESOLVED_"+old.parent.name)
        session=ROOT/("run-"+dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")+
                      "-"+str(os.getpid()))
        session.mkdir(mode=0o700)
        sources={"logger.py":Path(__file__).resolve(),"fullram.py":PROJECT/"tools"/FULL_NAME,
                 "deep.py":PROJECT/"tools"/DEEP_NAME,"base.py":PROJECT/"tools"/BASE_NAME,
                 HELPER_NAME:PROJECT/"tools"/HELPER_NAME}
        fingerprints={}
        for filename,source in sources.items():
            if source.is_symlink() or not source.is_file():
                raise RuntimeError("FOCUS_SOURCE_NOT_REGULAR_"+filename)
            shutil.copyfile(source,session/filename)
            os.chmod(session/filename,0o600)
            fingerprints[filename]=F.sha256(session/filename)
        src=h.command(["git","-C",str(PROJECT),"rev-parse","HEAD"]).strip()
        h.atomic_json(session/"state.json",{"version":VERSION,"hours":hours,
          "source_checkout_sha":src,"services":services,"restore":[],"port":cfg["port_optolink"],
          "logger_sha256":fingerprints["logger.py"],"fullram_sha256":fingerprints["fullram.py"],
          "deep_sha256":fingerprints["deep.py"],"base_sha256":fingerprints["base.py"],
          "helper_sha256":fingerprints[HELPER_NAME]})
    cmd=["systemd-run","--unit="+UNIT,"--no-block","--collect",
         "--property=Type=exec","--property=Restart=no","--property=TimeoutStopSec=300",
         "--property=KillMode=control-group","--property=UMask=0077",
         "--property=ExecStopPost="+PYTHON+" -u "+str(session/"logger.py")+
           " --recover "+str(session),PYTHON,"-u",str(session/"logger.py"),"--worker",str(session)]
    run=subprocess.run(cmd,capture_output=True,text=True,check=False,timeout=30)
    if run.returncode:
        raise RuntimeError("FOCUS_SYSTEMD_START_REFUSED:"+run.stderr[-500:])
    print("SESSION="+str(session),flush=True)
    print("UNIT="+UNIT,flush=True)
    print("MAX_HOURS="+str(hours),flush=True)
    print("STATUS_CMD=bash "+str(PROJECT/"tools"/"wb2a-p300-p06-focus.sh")+" status",flush=True)
    print("STOP_CMD=bash "+str(PROJECT/"tools"/"wb2a-p300-p06-focus.sh")+" stop",flush=True)
    return 0


def latest():
    if ROOT.is_symlink() or not ROOT.is_dir(): raise RuntimeError("FOCUS_NO_SESSION")
    sessions=sorted(p for p in ROOT.glob("run-*") if p.is_dir() and not p.is_symlink())
    if not sessions:raise RuntimeError("FOCUS_NO_SESSION")
    return sessions[-1]


def status():
    session=latest()
    base=F.DEEP.load_local_base(PROJECT/"tools")
    print("SESSION="+str(session))
    print("UNIT_STATE="+base.h.unit_state(UNIT).get("ActiveState","unknown"))
    for name in ("progress.json","recovery.json","health.json"):
        p=session/name
        if p.is_file(): print(name.upper()+"="+p.read_text().strip())
    dest=BUNDLES/("p300-p06-focus-"+session.name+"-bundle.tar.gz")
    if dest.is_file(): print("UPLOAD_ONE_FILE="+str(dest))
    return 0


def stop():
    session=latest()
    base=F.DEEP.load_local_base(PROJECT/"tools")
    phase=base.h.unit_state(UNIT).get("ActiveState")
    if phase in ("active","activating","deactivating"):
        proc=subprocess.run(["systemctl","stop",UNIT],capture_output=True,
                            text=True,check=False,timeout=360)
        if proc.returncode: print("SYSTEMD_STOP_ERROR="+proc.stderr[-500:])
    elif phase not in ("inactive","failed"):
        raise RuntimeError("FOCUS_UNEXPECTED_SYSTEMD_STATE_"+str(phase))
    dest=BUNDLES/("p300-p06-focus-"+session.name+"-bundle.tar.gz")
    for _ in range(45):
        if (session/"recovery.json").is_file() and dest.is_file():break
        time.sleep(1)
    rec=json.loads((session/"recovery.json").read_text()) if (session/"recovery.json").is_file() else {}
    health=json.loads((session/"health.json").read_text()) if (session/"health.json").is_file() else {}
    good=bool(rec.get("services_restored") and health.get("production_main_verified") and all(
        health.get("gfa_reads",{}).get(k,{}).get("format_and_identity_verified") for k in ("P80","P06")))
    print("SERVICE_RESTORE="+("PASS" if rec.get("services_restored") else "NOT_VERIFIED"))
    print("VS1_P80_P06_HEALTH="+("PASS" if good else "NOT_VERIFIED"))
    print("UPLOAD_ONE_FILE="+str(dest) if dest.is_file() else "UPLOAD_ARCHIVE_NOT_VERIFIED")
    return 0 if good and dest.is_file() else 1


def main():
    p=argparse.ArgumentParser(description=__doc__)
    g=p.add_mutually_exclusive_group()
    for name in ("start","status","stop"):
        g.add_argument("--"+name,action="store_true")
    g.add_argument("--worker",type=Path)
    g.add_argument("--recover",type=Path)
    p.add_argument("--hours",type=int,default=DEFAULT_HOURS)
    args=p.parse_args()
    os.umask(0o077)
    if args.worker or args.recover:
        if os.geteuid()!=0 or "INVOCATION_ID" not in os.environ:
            p.error("supervised systemd root required")
        return worker(args.worker) if args.worker else recover(args.recover)
    if args.start:return start(args.hours)
    if args.status:return status()
    if args.stop:return stop()
    print("PLAN ONLY: "+VERSION)
    print("VS1/P06 before and after 2 x six fixed FC03 RAM blocks; three FC01 status reads.")
    print("Only known 0x0f20 and 0x1c76 RAM candidates, read-only. P09 is NOT tachometer.")
    print("Default 1h, max 3h; preserve original VS1 service configuration via ExecStopPost.")
    return 0


if __name__=="__main__":
    try: raise SystemExit(main())
    except (RuntimeError,ValueError,OSError,subprocess.SubprocessError) as exc:
        print("REFUSED_OR_FAILED="+str(exc),file=sys.stderr)
        raise SystemExit(1)
