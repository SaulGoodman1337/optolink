"""Operational READ-ONLY on-demand VS1 -> P300 -> VS1 snapshot command.

This is a SUPERVISED, SERVICE-PAUSING switch (typically tens of seconds),
not an always-on hybrid dispatcher. It uses the tested original-root source
shadow and systemd ExecStopPost restore. No controller writes or raw addresses.

Usage:
  python switchctl.py status
  sudo -n /opt/optolink/venv/bin/python switchctl.py snapshot --accept-telemetry-pause

A complete, independently verified VS1 return is mandatory for status PASS.
No implicit retry, periodic background process or automatic production merge.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys

try:
    from . import hybrid_acceptance
except ImportError:
    import hybrid_acceptance


class SwitchctlRejected(RuntimeError):
    pass


def _session_path(stdout: str, base: Path) -> Path | None:
    refs = [line.removeprefix("HYBRID_SESSION=")
            for line in stdout.splitlines() if line.startswith("HYBRID_SESSION=")]
    if len(refs) != 1:
        return None
    path = Path(refs[0])
    if (not path.is_absolute() or path.parent != base
            or re.fullmatch(r"run-inprocess-\d{8}T\d{6}Z-\d+", path.name) is None
            or path.is_symlink()):
        return None
    return path


def _read_private_json(path: Path) -> dict:
    if path.is_symlink() or not path.is_file():
        return {}
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return record if isinstance(record, dict) else {}


def switch_once(*, python: str = "/opt/optolink/venv/bin/python",
                cli_file: Path | None = None,
                timeout_s: int = 240) -> dict:
    """Run exactly ONE physical read-only hardware snapshot, no auto retry."""
    if os.geteuid() != 0:
        raise SwitchctlRejected("root required for supervised physical switch")
    script = Path(cli_file or hybrid_acceptance.__file__).resolve()
    if script.name != "hybrid_acceptance.py":
        raise SwitchctlRejected("unreviewed acceptance entrypoint")
    argv = [python, "-u", str(script), "--execute", "--accept-telemetry-pause"]
    try:
        proc = subprocess.run(argv, capture_output=True, text=True,
                              check=False, timeout=timeout_s)
    except subprocess.TimeoutExpired as exc:
        # The independent systemd unit must still perform its ExecStopPost;
        # a shell timeout is NOT a proof that the controller is back on VS1.
        return {"status": "NOT_VERIFIED_TIMEOUT", "exit_code": None,
                "verified": False,
                "reason": "acceptance supervisor timed out; inspect systemd and restore log"}
    except OSError as exc:
        return {"status": "LAUNCH_FAILURE", "exit_code": None,
                "verified": False, "reason": type(exc).__name__}

    session = _session_path(proc.stdout, hybrid_acceptance.BASE)
    if session is None:
        return {"status": "NO_VERIFIED_SESSION", "exit_code": proc.returncode,
                "verified": False, "reason": (proc.stderr or proc.stdout)[-800:]}
    summary = _read_private_json(session / "hybrid-summary.json")
    boot = _read_private_json(session / "hybrid-result.json")
    recovery = _read_private_json(session / "recovery.json")
    health = summary.get("production_health") or {}
    verified = (
        proc.returncode == 0
        and summary.get("result") == "PASS_VERIFIED_INPROCESS_FIXED_FC03"
        and summary.get("unit_rc") == 0
        and summary.get("boot_record_verified") is True
        and summary.get("worker_verified") is True
        and summary.get("services_restored") is True
        and summary.get("production_splitter_running") is True
        and (recovery.get("services_restored") is True
             and recovery.get("overall_verified") is True)
        and recovery.get("independent_link_restore", {}).get("verified") is True
        and set(health) == {"P80", "P06"}
        and all(v.get("valid") is True for v in health.values())
        and hybrid_acceptance._verified_boot_record(boot)
        and boot.get("no_device_write") is True
        and boot.get("no_second_serial_open") is True
    )
    return {
        "status": "PASS_VERIFIED_READONLY_SWITCH" if verified else "FAIL_OR_NOT_VERIFIED",
        "verified": verified,
        "exit_code": proc.returncode,
        "session": str(session),
        "vs1_restored": bool(recovery.get("overall_verified")),
        "services_restored": bool(recovery.get("services_restored")),
        "production_health": health,
        "time_ms": boot.get("time_ms") if verified else None,
        "vs1": ({"P80": boot.get("gfa_p80_hex"),
                 "P06": boot.get("gfa_p06_hex")} if verified else None),
        "p300": ({
            "identity_hex": boot["identity_hex"],
            "ram_0f20_32_hex": boot["ram_0f20_32_hex"],
            "ram_1c60_32_hex": boot["ram_1c60_32_hex"],
        } if verified else None),
        "worker_errors": summary.get("worker_errors", []),
    }


def inspect_status() -> dict:
    live = hybrid_acceptance._live()
    base = live.base
    state = {}
    for name in (base.MAIN, "optolink-pump-override.service",
                 "optolink-party-emulator.service",
                 "optolink-schedule-manager.service",
                 "optolink-maintenance-api.service",
                 "optolink-service-programs.service"):
        try:
            details = base.unit_state(name)
            state[name] = {"active": details.get("ActiveState"),
                           "substate": details.get("SubState")}
        except (OSError, ValueError, RuntimeError) as exc:
            state[name] = {"error": type(exc).__name__}
    try:
        health = live.read_health()
    except (OSError, ValueError, RuntimeError):
        health = {}
    healthy = (
        state.get(base.MAIN, {}).get("active") == "active"
        and state.get(base.MAIN, {}).get("substate") == "running"
        and set(health) == {"P80", "P06"}
        and all(isinstance(v, dict) and v.get("valid") is True
                for v in health.values())
    )
    return {"status": ("HEALTHY_READONLY_STATUS" if healthy
                       else "DEGRADED_READONLY_STATUS"),
            "healthy": healthy, "units": state, "gfa": health,
            "production_changed": False}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("status")
    snapshot = sub.add_parser("snapshot")
    snapshot.add_argument("--accept-telemetry-pause", action="store_true")
    args = parser.parse_args(argv)
    if args.command == "status":
        report = inspect_status()
    else:
        if not args.accept_telemetry_pause:
            raise SwitchctlRejected("snapshot requires --accept-telemetry-pause")
        report = switch_once()
    print(json.dumps(report, sort_keys=True))
    return 0 if report.get("status") in (
        "HEALTHY_READONLY_STATUS", "PASS_VERIFIED_READONLY_SWITCH") else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SwitchctlRejected as exc:
        print(json.dumps({"status": "REFUSED", "reason": str(exc),
                          "verified": False}), file=sys.stderr)
        raise SystemExit(1)
