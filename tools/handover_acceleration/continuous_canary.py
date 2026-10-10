"""Real supervised, time-limited continuous VS1/P300/VS1 hardware canary.

Never an unattended rollout: short-lived systemd unit with RuntimeMaxSec,
independent ExecStopPost restoration, pinned root-owned release sources and
explicit human permission. Auto is enabled ONLY after running writer programs
are attested. Three verified read-only P300 windows are expected, otherwise
FAIL and original VS1 services are restored. No heater RAM writes.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

from . import shadow_canary as sh
from .release_rollout import ROOT, RELEASES, generate_enrollment, unit_dropins
from .runtime_enrollment import MANIFEST_PATH, verify_enrollment

UNIT = "optolink-hybrid-continuous-canary.service"
EXTRA_NAME = "99-optolink-hybrid-auto-canary.conf"
TARGET_WINDOWS = 3
WATCH_SECONDS = 225
MAX_RUNTIME_SECONDS = 270
# The extended profile is deliberately fixed: no arbitrary duration or
# caller-supplied job count can extend a production hardware experiment.
SOAK_WINDOWS = 8
SOAK_WATCH_SECONDS = 710
SOAK_MAX_RUNTIME_SECONDS = 800


class ContinuousCanaryRejected(RuntimeError):
    pass


def profile_limits(profile: str) -> tuple[int, int, int, str]:
    if profile == "standard":
        return (TARGET_WINDOWS, WATCH_SECONDS, MAX_RUNTIME_SECONDS,
                "PASS_THREE_VERIFIED_CONTINUOUS_WINDOWS")
    if profile == "soak-eight":
        return (SOAK_WINDOWS, SOAK_WATCH_SECONDS, SOAK_MAX_RUNTIME_SECONDS,
                "PASS_EIGHT_VERIFIED_CONTINUOUS_WINDOWS")
    raise ContinuousCanaryRejected("unknown immutable hardware canary profile")


def _extra_path() -> Path:
    return Path("/etc/systemd/system/optolink-splitter.service.d") / EXTRA_NAME


def _extra_content(session: Path) -> str:
    if not re.fullmatch(r"run-\d{8}T\d{6}Z-\d+", session.name):
        raise ContinuousCanaryRejected("unknown private session identifier")
    return ("[Service]\n"
            "Environment=OPTO_HYBRID_RUNTIME_AUTO=fenced-readonly\n"
            "Environment=OPTO_HYBRID_CANARY_SESSION=" + session.name + "\n")


def _expected_manifest(release: Path) -> bytes:
    return (json.dumps(generate_enrollment(release), sort_keys=True,
                       indent=2) + "\n").encode("utf-8")


def _write_enrollment(release: Path):
    expected = _expected_manifest(release)
    if MANIFEST_PATH.exists() or MANIFEST_PATH.is_symlink():
        raise ContinuousCanaryRejected("unreviewed writer enrollment already exists")
    import grp
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(MANIFEST_PATH, flags, 0o640)
    try:
        os.fchown(fd, 0, grp.getgrnam("optolink").gr_gid)
        os.fchmod(fd, 0o640)
        if os.write(fd, expected) != len(expected):
            raise ContinuousCanaryRejected("incomplete source attestation")
        os.fsync(fd)
    finally:
        os.close(fd)


def _collect_events(session: Path, start_epoch: int) -> tuple[list[dict], list[str]]:
    # Journal evidence originates from the *real* original VS1 owner's
    # successfully completed P300 window after original GFA verification.
    args = ["journalctl", "-u", sh.MAIN, "--since", "@" + str(start_epoch),
            "--no-pager", "-o", "cat", "--grep=HYBRID_RUNTIME_"]
    proc = subprocess.run(args, capture_output=True, text=True, timeout=8)
    # On systemd 257, journalctl -g returns exit 1 for a healthy query
    # with NO matches yet. That is expected at the beginning of a canary,
    # not a journal access failure. Stderr or any other nonzero code still
    # fails closed.
    if proc.returncode == 1 and not proc.stdout.strip() and not proc.stderr.strip():
        return [], []
    if proc.returncode:
        raise ContinuousCanaryRejected(
            "cannot independently read original main journal: "
            + proc.stderr[-160:])
    events, refusals = [], []
    for line in proc.stdout.splitlines():
        if "HYBRID_RUNTIME_REFUSAL " in line:
            refusals.append(line.split("HYBRID_RUNTIME_REFUSAL ", 1)[1][:120])
        if "HYBRID_RUNTIME_VERIFIED_SWITCH " not in line:
            continue
        raw = line.split("HYBRID_RUNTIME_VERIFIED_SWITCH ", 1)[1]
        try:
            event = json.loads(raw)
        except json.JSONDecodeError:
            raise ContinuousCanaryRejected("controller window journal corrupted")
        if event.get("canary_session") != session.name:
            continue
        if (event.get("status") != "VERIFIED_SWITCH"
                or event.get("vs1_p80") != "20"
                or not re.fullmatch(r"[0-9a-f]{2}", event.get("vs1_p06", ""))
                or event["vs1_p06"] == "ff"
                or not isinstance(event.get("elapsed_ms"), (float, int))
                or not 0 < event["elapsed_ms"] <= 8000):
            raise ContinuousCanaryRejected("invalid VS1 readback after live P300")
        raw_reads = event.get("p300_fixed")
        if (not isinstance(raw_reads, dict)
                or set(raw_reads) != {"p300_device", "ram_0f20_32",
                                     "ram_1c60_32"}
                or not re.fullmatch(r"[0-9a-f]{4}", raw_reads["p300_device"])
                or any(not re.fullmatch(r"[0-9a-f]{64}", raw_reads[name])
                       for name in ("ram_0f20_32", "ram_1c60_32"))):
            raise ContinuousCanaryRejected("live P300 fixed FC03 evidence absent")
        events.append(event)
    return events, refusals


def _read_lease_marker() -> bytes:
    from .producer_fence import LEASE_PATH
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(LEASE_PATH, flags)
    try:
        return os.pread(fd, 32, 0)
    finally:
        os.close(fd)


def verify_live_canary_epoch(main_pid: int, marker_since: float | None,
                             now: float) -> float | None:
    """Attest ALL writers even during a legitimate in-progress P300 window.

    The ordinary runtime attestor MUST fail on nonempty marker. A canary
    monitor alone can tolerate exactly P300_ACTIVE while the same original
    serial-owner process remains alive, never for more than 12 seconds.
    P300_FAILED, unowned leases, absent services or different source hashes
    are always fatal.
    """
    live_pid = int(sh.call(["systemctl","show",sh.MAIN,
                            "--property=MainPID","--value","--no-pager"],5))
    if main_pid <= 0 or live_pid != main_pid:
        raise ContinuousCanaryRejected("original serial-owner PID changed during P300")
    state = verify_enrollment()
    if state.accepted:
        return None
    if (state.reason == "producer lease unsafe or failure latched"
            and _read_lease_marker() == b"P300_ACTIVE"):
        when = now if marker_since is None else marker_since
        if 0 <= now - when <= 12.0:
            return when
        raise ContinuousCanaryRejected("P300_ACTIVE persisted beyond read-only budget")
    raise ContinuousCanaryRejected("producer/pump enrollment changed during canary: "
                                   + state.reason)


def worker(session: Path) -> int:
    sh.load(session)
    if os.geteuid() != 0 or not os.environ.get("INVOCATION_ID"):
        raise ContinuousCanaryRejected("root-owned systemd worker required")
    data = sh.load(session)
    release = Path(data["release"])
    target_windows, watch_seconds, _runtime_seconds, expected_result = (
        profile_limits(data.get("canary_profile", "standard")))
    # First perform the already REAL-HARDWARE-verified full shadow startup.
    # Every unexpected error exits the unit, triggering independent recovery.
    sh.worker(session)
    data = sh.load(session)
    data["phase"] = "ENROLLING_LIVE_WRITERS"
    sh.save(session/"state.json", data)
    _write_enrollment(release)
    report = verify_enrollment()
    if not report.accepted:
        raise ContinuousCanaryRejected("live writer attestation refused: " + report.reason)
    path = _extra_path()
    content = _extra_content(session)
    if path.exists() or path.is_symlink():
        raise ContinuousCanaryRejected("unknown auto-activation override")
    path.write_text(content, encoding="utf-8")
    os.chown(path, 0, 0)
    os.chmod(path, 0o644)
    with path.open("rb") as f:
        os.fsync(f.fileno())
    data["phase"] = "AUTO_HARDWARE_CANARY"
    sh.save(session/"state.json", data)
    sh.call(["systemctl", "daemon-reload"])
    since = int(time.time()) - 1
    sh.call(["systemctl", "restart", sh.MAIN], 40)
    if sh.status(sh.MAIN) != "active":
        raise ContinuousCanaryRejected("auto-enabled original serial owner not running")
    # Pin the ONLY original serial-owner PID; any restart during the
    # hardware window is a hard abort even when systemd reports active.
    auto_main_pid = int(sh.call(["systemctl","show",sh.MAIN,
                                 "--property=MainPID","--value","--no-pager"],5))
    if auto_main_pid <= 0:
        raise ContinuousCanaryRejected("serial-owner PID unavailable")
    # A clean, ordinary MQTT VS1 GFA check must still work before any P300.
    initial = sh.gfa(wait=30)
    events, refusals = [], []
    marker_since = None
    deadline = time.monotonic() + watch_seconds
    while time.monotonic() < deadline:
        if any(sh.status(name) != "active" for name in sh.ALL):
            raise ContinuousCanaryRejected("a productive service failed during P300 canary")
        if sh.status("optolink-pump-override.service") != "inactive":
            raise ContinuousCanaryRejected("pump owner activated during canary")
        marker_since = verify_live_canary_epoch(
            auto_main_pid, marker_since, time.monotonic())
        events, refusals = _collect_events(session, since)
        if len(events) >= target_windows:
            break
        time.sleep(3.0)
    post = sh.gfa(wait=25)
    measurement = {
        "result": (expected_result if len(events) >= target_windows
                   else "NO_VERIFIED_CONTINUOUS_WINDOWS"),
        "event_count": len(events), "events": events,
        "last_refusals": refusals[-15:],
        "gfa_initial": initial, "gfa_final": post,
        "live_producer_attested": verify_enrollment().accepted,
        "automatic_scope": "READ_ONLY_FIXED_FC03",
    }
    sh.save(session/"continuous-measurement.json", measurement)
    print("HYBRID_CONTINUOUS_CANARY=" + json.dumps({
        "result":measurement["result"],"event_count":len(events),
        "last_refusals":refusals[-5:]}, sort_keys=True), flush=True)
    if len(events) < target_windows:
        raise ContinuousCanaryRejected("required verified hardware windows not observed")
    return 0


def recover(session: Path) -> int:
    data = sh.load(session)
    release = Path(data["release"])
    errors = []
    extra = _extra_path()
    # Fully remove the auto-only override BEFORE ordinary shadow recovery
    # is permitted to restart the original main.
    if extra.exists() or extra.is_symlink():
        try:
            if (extra.is_symlink() or not extra.is_file()
                    or extra.read_text() != _extra_content(session)):
                raise ContinuousCanaryRejected("auto override unexpectedly changed")
            extra.unlink()
        except Exception as exc:
            errors.append("remove continuous auto override: " + str(exc)[:140])
    if errors:
        print("HYBRID_CONTINUOUS_RECOVERY_FAIL=" + str(errors), flush=True)
        return 1
    try:
        if MANIFEST_PATH.exists() or MANIFEST_PATH.is_symlink():
            if (MANIFEST_PATH.is_symlink() or not MANIFEST_PATH.is_file()
                    or MANIFEST_PATH.read_bytes() != _expected_manifest(release)):
                raise ContinuousCanaryRejected("enrollment manifest unexpectedly changed")
            MANIFEST_PATH.unlink()
    except Exception as exc:
        errors.append("remove canary enrollment: " + str(exc)[:150])
    # With the additional auto-activation overlay removed, the proven
    # shadow_canary.recover() can remove the six pinned base overrides,
    # reinitialize genuine VS1 and restore the preexisting live services.
    rc = sh.recover(session)
    if errors:
        print("HYBRID_CONTINUOUS_RECOVERY_WARNING=" + str(errors), flush=True)
    return int(rc != 0 or bool(errors))


def launch(release: Path, *, profile: str = "standard") -> int:
    if os.geteuid() != 0:
        raise ContinuousCanaryRejected("root required for hardware canary")
    target_windows, watch_seconds, max_runtime, expected_result = profile_limits(profile)
    before = sh.preflight(release)
    before["canary_profile"] = profile
    sh.SESSIONS.mkdir(mode=0o700, parents=True, exist_ok=True)
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    session = sh.SESSIONS / ("run-" + stamp + "-" + str(os.getpid()))
    session.mkdir(mode=0o700)
    sh.save(session/"state.json", before)
    env = str(release/"tools") + ":/opt/optolink"
    cmd = ["systemd-run", "--unit=" + UNIT, "--wait", "--collect",
           "--property=Type=exec",
           "--property=RuntimeMaxSec=" + str(max_runtime),
           "--property=TimeoutStopSec=120",
           "--property=KillMode=control-group",
           "--setenv=PYTHONPATH=" + env,
           "--property=ExecStopPost=" + sh.PYTHON +
           " -m handover_acceleration.continuous_canary --recover " + str(session),
           sh.PYTHON, "-u", "-m",
           "handover_acceleration.continuous_canary", "--worker", str(session)]
    print("HYBRID_CONTINUOUS_SESSION=" + str(session), flush=True)
    run = subprocess.run(cmd, check=False)
    try: measure = json.loads((session/"continuous-measurement.json").read_text())
    except (OSError, ValueError): measure = {}
    try: restored = json.loads((session/"recovery.json").read_text())
    except (OSError, ValueError): restored = {}
    success = (run.returncode == 0
               and measure.get("result") == expected_result
               and measure.get("event_count", 0) >= target_windows
               and restored.get("result") == "PASS_ORIGINAL_SERVICES_RESTORED")
    result = {"result":"PASS" if success else "FAIL_OR_NOT_VERIFIED",
              "profile":profile, "target_windows":target_windows,
              "session":str(session), "event_count":measure.get("event_count",0),
              "last_refusals":measure.get("last_refusals", [])[-10:],
              "recovery":restored, "run_rc":run.returncode}
    print("HYBRID_CONTINUOUS_RESULT=" + json.dumps(result,sort_keys=True),flush=True)
    return 0 if success else 1


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    choices = parser.add_mutually_exclusive_group(required=True)
    choices.add_argument("--plan", type=Path)
    choices.add_argument("--launch", type=Path)
    choices.add_argument("--worker", type=Path)
    choices.add_argument("--recover", type=Path)
    parser.add_argument("--accept-telemetry-pause", action="store_true")
    parser.add_argument("--soak-eight", action="store_true")
    args = parser.parse_args(argv)
    if args.plan is not None:
        return sh.main(["--plan",str(args.plan)])
    if args.launch is not None:
        if not args.accept_telemetry_pause:
            raise ContinuousCanaryRejected("explicit telemetry interruption approval required")
        return launch(args.launch, profile=("soak-eight" if args.soak_eight
                                            else "standard"))
    if args.soak_eight:
        raise ContinuousCanaryRejected("soak profile is chosen only by root launch")
    if os.geteuid() != 0 or not os.environ.get("INVOCATION_ID"):
        raise ContinuousCanaryRejected("only root systemd worker/recovery allowed")
    if args.worker is not None:
        return worker(args.worker)
    return recover(args.recover)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ContinuousCanaryRejected, sh.CanaryRejected, OSError, ValueError) as exc:
        print("HYBRID_CONTINUOUS_ERROR=" + type(exc).__name__ + ": "
              + str(exc)[:300], file=sys.stderr, flush=True)
        raise SystemExit(1)
