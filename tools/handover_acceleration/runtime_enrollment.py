"""Fail-closed attestation of the FIVE deployed cooperative controller writers.

Never enable a continuous P300 window because a process merely *claims* to
be quiescent. Require a root-provisioned, pinned manifest, exact running
source hashes, actual systemd process cmdlines, and a persistent producer
lease with no write-failure marker. No service or serial actions here.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess

from .producer_fence import LEASE_PATH

MANIFEST_PATH = Path("/var/lib/optolink-hybrid/enrollment.json")
UNITS = {
    "party": "optolink-party-emulator.service",
    "schedule": "optolink-schedule-manager.service",
    "service-programs": "optolink-service-programs.service",
    "clock-sync": "optolink-clock-sync.service",
    "maintenance": "optolink-maintenance-api.service",
}
ORIGINAL_MAINTENANCE_API = Path("/usr/local/bin/optolink-maintenance-api")
RELEASE_ROOT = Path("/var/lib/optolink-hybrid/releases")
ORIGINAL_PATHS = {
    "party": Path("/usr/local/bin/optolink-party-emulator"),
    "schedule": Path("/usr/local/bin/optolink-schedule-manager"),
    "service-programs": Path("/usr/local/bin/optolink-service-programs"),
    "clock-sync": Path("/usr/local/bin/optolink-clock-sync"),
    "maintenance": Path("/opt/optolink/optolink_maintenance_core.py"),
}
TOKEN = "# HYBRID_PRODUCER_EPOCH_V1"
API_TOKEN = "# HYBRID_MAINTENANCE_API_SHADOW_V1"


class EnrollmentRejected(RuntimeError):
    pass


@dataclass(frozen=True)
class EnrollmentResult:
    accepted: bool
    reason: str
    checked_roles: tuple[str, ...] = ()


def _approved_path(role: str, name: str) -> Path:
    path = Path(name)
    if role not in UNITS or not path.is_absolute() or ".." in path.parts:
        raise EnrollmentRejected("unknown role or noncanonical source")
    if path == ORIGINAL_PATHS[role]:
        return path
    # Release bundles may only live under an administrator-owned directory.
    anchor = RELEASE_ROOT
    if (not path.is_relative_to(anchor)
            or len(path.relative_to(anchor).parts) != 3
            or path.relative_to(anchor).parts[-2]
                != ("src" if role == "maintenance" else "bin")
            or path.name != ORIGINAL_PATHS[role].name):
        raise EnrollmentRejected("unapproved writer source location")
    return path


def _approved_api_path(name: str, core: Path) -> Path:
    path=Path(name)
    if path == ORIGINAL_MAINTENANCE_API and core == ORIGINAL_PATHS["maintenance"]:
        return path
    if (not path.is_absolute() or not path.is_relative_to(RELEASE_ROOT)
            or not core.is_relative_to(RELEASE_ROOT)
            or len(path.relative_to(RELEASE_ROOT).parts)!=3
            or path.relative_to(RELEASE_ROOT).parts[-2:] !=
                ("bin","optolink-maintenance-api")
            or path.relative_to(RELEASE_ROOT).parts[0] !=
                core.relative_to(RELEASE_ROOT).parts[0]):
        raise EnrollmentRejected("maintenance API must use the exact matched release")
    return path


def _pinned_file(path: Path, expected: str, *, marker: bool,
                 marker_token: str = TOKEN) -> bool:
    if not isinstance(expected, str) or len(expected) != 64:
        return False
    try:
        if path.is_symlink():
            return False
        info=path.stat()
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            return False
        if info.st_uid not in (0,):
            return False
        raw=path.read_bytes()
    except OSError:
        return False
    if marker and marker_token.encode() not in raw:
        return False
    return hashlib.sha256(raw).hexdigest() == expected


def _show(unit: str, key: str) -> str:
    proc=subprocess.run(["systemctl","show",unit,"--property="+key,
                         "--value","--no-pager"],
                        text=True,capture_output=True,timeout=3,check=False)
    if proc.returncode != 0:
        raise EnrollmentRejected("systemd cannot prove " + unit)
    return proc.stdout.strip()


def _proc_start_epoch(pid: int) -> float:
    # Linux /proc/[pid]/stat field 22 = clock ticks since boot.
    tail=Path(f"/proc/{pid}/stat").read_text().rsplit(")",1)[-1].split()
    ticks=int(tail[19])
    uptime=float(Path("/proc/uptime").read_text().split()[0])
    return __import__("time").time()-uptime + ticks/os.sysconf("SC_CLK_TCK")


def _process_confirms(unit: str, path: Path, *, require_loaded_after: float) -> bool:
    try:
        if _show(unit,"ActiveState") != "active":
            return False
        pid=int(_show(unit,"MainPID"))
        if pid <= 0:
            return False
        args=Path(f"/proc/{pid}/cmdline").read_bytes().split(b"\0")
        if str(path).encode() not in args:
            return False
        return _proc_start_epoch(pid) >= require_loaded_after
    except (OSError,ValueError,EnrollmentRejected,subprocess.TimeoutExpired):
        return False


def verify_enrollment(manifest: Path = MANIFEST_PATH) -> EnrollmentResult:
    """Pure read-only operating-system evidence; any ambiguity denies P300."""
    checked=[]
    try:
        if manifest.is_symlink() or not manifest.is_file():
            raise EnrollmentRejected("no root-owned enrollment manifest")
        st=manifest.stat()
        if st.st_uid != 0 or st.st_mode & 0o007:
            raise EnrollmentRejected("unsafe manifest owner/permissions")
        data=json.loads(manifest.read_text())
        if (not isinstance(data,dict) or data.get("schema")!=1
                or data.get("producer_lock") != str(LEASE_PATH)
                or set(data.get("writers",{})) != set(UNITS)):
            raise EnrollmentRejected("manifest does not cover all five writers")
        for role,unit in UNITS.items():
            declared=data["writers"][role]
            if not isinstance(declared,dict) or declared.get("unit")!=unit:
                raise EnrollmentRejected("writer unit mismatch: "+role)
            path=_approved_path(role,declared.get("path",""))
            if not _pinned_file(path,declared.get("sha256",""),marker=True):
                raise EnrollmentRejected("unpatched or changed source: "+role)
            if role=="clock-sync":
                if _show("optolink-clock-sync.timer","ActiveState") != "active":
                    raise EnrollmentRejected("clock timer inactive")
                if str(path) not in _show(unit,"ExecStart"):
                    raise EnrollmentRejected("clock unit points to old binary")
            elif role=="maintenance":
                api_path=_approved_api_path(declared.get("api_path",""),path)
                api_marker=(api_path!=ORIGINAL_MAINTENANCE_API)
                if not _pinned_file(api_path,declared.get("api_sha256",""),
                                    marker=api_marker,marker_token=API_TOKEN):
                    raise EnrollmentRejected("maintenance API source not pinned")
                if not _process_confirms(
                        unit,api_path,
                        require_loaded_after=max(path.stat().st_mtime,
                                                 api_path.stat().st_mtime)):
                    raise EnrollmentRejected("maintenance API not executing pinned core")
            elif not _process_confirms(unit,path,require_loaded_after=path.stat().st_mtime):
                raise EnrollmentRejected("writer process not executing pinned source: "+role)
            checked.append(role)
        if LEASE_PATH.is_symlink() or not LEASE_PATH.is_file():
            raise EnrollmentRejected("persistent producer lock absent")
        st=LEASE_PATH.stat()
        if st.st_uid!=0 or st.st_mode&0o007 or st.st_size!=0:
            raise EnrollmentRejected("producer lease unsafe or failure latched")
    except (OSError,ValueError,TypeError,KeyError,
            EnrollmentRejected,subprocess.TimeoutExpired) as exc:
        return EnrollmentResult(False,str(exc),tuple(checked))
    return EnrollmentResult(True,"ALL_FIVE_PRODUCERS_ATTESTED",tuple(checked))


def all_writers_attested() -> bool:
    return verify_enrollment().accepted
