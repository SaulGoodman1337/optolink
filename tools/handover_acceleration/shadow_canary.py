"""Supervised, service-pausing, diagnostic-only hybrid shadow canary.

This test runs the newly generated main and five writer COPIES with automatic
P300 completely disabled. A separate systemd ExecStopPost removes every
temporary override, verifies real original GFA P80/P06 and restores the
original services. No root/production file is edited permanently.
"""
from __future__ import annotations
import argparse
import datetime as dt
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

from .release_rollout import ROOT, RELEASES, unit_dropins
from .runtime_enrollment import UNITS, LEASE_PATH

MAIN="optolink-splitter.service"
WRITERS=tuple(UNITS[k] for k in ("party","schedule","service-programs","maintenance"))
TIMER="optolink-clock-sync.timer"
ALL=(MAIN,*WRITERS,TIMER)
UNIT="optolink-hybrid-shadow-canary.service"
SESSIONS=ROOT/"canary-sessions"
DROPIN="98-optolink-hybrid-canary.conf"
SERIAL_LEASE=Path("/var/lib/optolink-hybrid/serial.lease")
PYTHON="/opt/optolink/venv/bin/python"


class CanaryRejected(RuntimeError):pass


def call(args,timeout=35):
    result=subprocess.run(args,capture_output=True,text=True,timeout=timeout)
    if result.returncode:
        raise CanaryRejected("command failed: "+str(args[:3])+" "+result.stderr[-220:])
    return result.stdout.strip()


def status(unit):
    return call(["systemctl","show",unit,"-p","ActiveState","--value"],5)


def dropin(unit):
    return Path("/etc/systemd/system")/(unit+".d")/DROPIN


def save(path,record):
    if path.is_symlink():raise CanaryRejected("unsafe canary report symlink")
    tmp=path.with_suffix(path.suffix+".new")
    if tmp.exists() or tmp.is_symlink():raise CanaryRejected("stale canary temp")
    with tmp.open("x") as handle:
        json.dump(record,handle,sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.chmod(tmp,0o600)
    tmp.replace(path)


def load(session):
    if (not session.is_absolute() or session.parent!=SESSIONS
            or not re.fullmatch(r"run-\d{8}T\d{6}Z-\d+",session.name)
            or session.is_symlink() or not session.is_dir()
            or session.stat().st_uid!=0 or session.stat().st_mode&0o077):
        raise CanaryRejected("invalid root-only canary session")
    path=session/"state.json"
    if path.is_symlink():raise CanaryRejected("unsafe canary state")
    return json.loads(path.read_text())


def gfa(wait=30):
    end=time.monotonic()+wait
    errors=[]
    while time.monotonic()<end:
        try:
            if status(MAIN)!="active":raise CanaryRejected("splitter inactive")
            got={}
            for address,name in (("0x4050","P80"),("0x4006","P06")):
                out=call(["optolink-debug","request",
                        "gfaread;"+address+";1;raw;False","--timeout","6"],9)
                match=re.search(r"openv/resp:\s*1;0x[0-9a-fA-F]+;([0-9a-fA-F]{2})",out)
                if not match:raise CanaryRejected("original GFA "+name+" failed")
                got[name]=match.group(1).lower()
            if got["P80"]!="20" or got["P06"]=="ff":
                raise CanaryRejected("identity or P06 invalid")
            return got
        except Exception as exc:
            errors.append(str(exc)[:120])
            time.sleep(.5)
    raise CanaryRejected("VS1 GFA not healthy: "+str(errors[-2:]))


def preflight(release):
    if os.geteuid()!=0:raise CanaryRejected("root required")
    if (release.parent!=RELEASES or release.is_symlink()
            or not release.is_dir()):
        raise CanaryRejected("unreviewed release path")
    manifest=json.loads((release/"stage-manifest.json").read_text())
    if manifest.get("state")!="STAGED_ONLY_NOT_DEPLOYED":
        raise CanaryRejected("unexpected candidate source")
    for rel,sha in manifest["generated_files"].items():
        p=release/rel
        if (p.is_symlink() or p.stat().st_uid!=0
                or p.stat().st_mode&0o022
                or hashlib.sha256(p.read_bytes()).hexdigest()!=sha):
            raise CanaryRejected("source hash or ownership wrong: "+rel)
    if status(UNIT) not in ("inactive","failed","not-found"):
        raise CanaryRejected("another supervised canary is active")
    if any(dropin(unit).exists() or dropin(unit).is_symlink()
           for unit in (MAIN,*WRITERS,UNITS["clock-sync"])):
        raise CanaryRejected("unrelated or stale dropin exists")
    if (ROOT/"enrollment.json").exists():
        raise CanaryRejected("continuous auto enrollment already present")
    if status("optolink-pump-override.service")!="inactive":
        raise CanaryRejected("pump override active")
    if status(UNITS["clock-sync"]) not in ("inactive","failed"):
        raise CanaryRejected("clock synchronization currently executing")
    states={name:status(name) for name in ALL}
    if any(states[name]!="active" for name in ALL):
        raise CanaryRejected("productive unit not healthy")
    return {"release":str(release),"before":states,"gfa_before":gfa(),
            "installed":{},"phase":"PREPARED"}


def provision_lock():
    """Idempotent creation only; never forgive a prior interrupted write."""
    import grp
    import stat
    group=grp.getgrnam("optolink").gr_gid
    if not LEASE_PATH.exists() and not LEASE_PATH.is_symlink():
        fd=os.open(LEASE_PATH,os.O_RDWR|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        try:
            os.fchown(fd,0,group)
            os.fchmod(fd,0o660)
            os.fsync(fd)
        finally:
            os.close(fd)
    st=LEASE_PATH.stat()
    if (LEASE_PATH.is_symlink() or not stat.S_ISREG(st.st_mode)
            or st.st_uid!=0 or st.st_gid!=group or st.st_mode&0o007
            or st.st_size!=0):
        raise CanaryRejected("producer lease unsafe or unverified")
    return LEASE_PATH


def provision_serial_lease():
    """Provision the *original VS1 owner*'s separate advisory lock.

    optolink.service runs as user optolink, but the root-managed persistent
    directory is not group-writable. PortLease validates st_uid==os.getuid()
    and owner-only 0600; a root-owned 0660 file fails that check. Create the
    inode before the unit restarts, do not change an unexpected existing one.
    """
    import pwd
    import stat
    owner = pwd.getpwnam("optolink").pw_uid
    group = __import__("grp").getgrnam("optolink").gr_gid
    path = SERIAL_LEASE
    if path.is_symlink():
        raise CanaryRejected("serial lease symlink not allowed")
    if not path.exists():
        flags = os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
        fd = os.open(path, flags, 0o600)
        try:
            os.fchown(fd, owner, group)
            os.fchmod(fd, 0o600)
            os.fsync(fd)
        finally:
            os.close(fd)
    record = path.stat()
    if (not stat.S_ISREG(record.st_mode) or record.st_nlink != 1
            or record.st_uid != owner or record.st_gid != group
            or stat.S_IMODE(record.st_mode) != 0o600
            or record.st_size != 0):
        raise CanaryRejected("serial lease owner, inode or permissions unsafe")
    return path


def worker(session):
    data=load(session)
    if not os.environ.get("INVOCATION_ID") or os.geteuid()!=0:
        raise CanaryRejected("only supervised root worker")
    unit_states=data["before"]
    data["phase"]="STOPPING"
    save(session/"state.json",data)
    call(["systemctl","stop",TIMER])
    call(["systemctl","stop",UNITS["clock-sync"]])
    for name in (*WRITERS,MAIN):
        call(["systemctl","stop",name])
    data["phase"]="OVERRIDING"
    save(session/"state.json",data)
    provision_lock()
    provision_serial_lease()
    for name,source in unit_dropins(Path(data["release"])).items():
        p=dropin(name)
        if p.exists() or p.is_symlink():
            raise CanaryRejected("override collision")
        data["installed"][name]=hashlib.sha256(source.encode()).hexdigest()
        save(session/"state.json",data)
        p.parent.mkdir(mode=0o755,parents=True,exist_ok=True)
        p.write_text(source)
        os.chown(p,0,0)
        os.chmod(p,0o644)
    call(["systemctl","daemon-reload"])
    data["phase"]="RUNNING_SHADOW_NO_AUTO"
    save(session/"state.json",data)
    call(["systemctl","start",MAIN])
    initial=gfa()
    for name in WRITERS:
        call(["systemctl","start",name])
    call(["systemctl","start",TIMER])
    time.sleep(8)
    if any(status(name)!="active" for name in ALL):
        raise CanaryRejected("a shadow writer failed")
    check=gfa()
    save(session/"measurement.json",{
        "status":"SHADOW_DIAGNOSTIC_PASS_NO_P300",
        "initial_gfa":initial,"post_writers_gfa":check,
        "all_producer_units_active":True})
    return 0


def clear_p300_after_gfa(got):
    if got.get("P80")!="20" or got.get("P06")=="ff":
        raise CanaryRejected("no P300 recovery evidence")
    if not LEASE_PATH.is_file() or LEASE_PATH.is_symlink():
        return False
    fd=os.open(LEASE_PATH,os.O_RDWR|os.O_NOFOLLOW)
    try:
        fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        value=os.pread(fd,200,0)
        if value.startswith(b"P300_"):
            os.ftruncate(fd,0)
            os.fsync(fd)
            return True
    finally:
        os.close(fd)
    return False


def recover(session):
    data=load(session)
    errors=[]
    actions=[]
    for name in (TIMER,UNITS["clock-sync"],*WRITERS,MAIN):
        try:
            call(["systemctl","stop",name],15)
        except Exception as exc:
            errors.append("stop "+name+": "+str(exc)[:90])
    # Inspect ALL potential override paths, not only the last persisted
    # write. A SIGKILL between file creation and session save must not
    # strand a process pointing to the experimental release.
    expected=unit_dropins(Path(data["release"]))
    for name,content in expected.items():
        try:
            p=dropin(name)
            if not p.exists() and not p.is_symlink():
                continue
            if (p.is_symlink() or not p.is_file()
                    or hashlib.sha256(p.read_bytes()).hexdigest()
                       !=hashlib.sha256(content.encode()).hexdigest()):
                raise CanaryRejected("drop-in unexpectedly changed")
            p.unlink()
            actions.append("removed:"+name)
        except Exception as exc:
            errors.append("remove "+name+": "+str(exc)[:90])
    try:
        call(["systemctl","daemon-reload"])
        if errors:raise CanaryRejected("rollback could not remove all dropins")
        call(["systemctl","start",MAIN])
        got=gfa(35)
        actions.append("original_gfa_confirmed")
        if clear_p300_after_gfa(got):
            actions.append("P300_marker_cleared_after_original_gfa")
        for name in WRITERS:
            if data["before"].get(name)=="active":
                call(["systemctl","start",name])
                actions.append("started:"+name)
        if data["before"].get(TIMER)=="active":
            call(["systemctl","start",TIMER])
        if any(status(name)!="active" for name in ALL):
            raise CanaryRejected("restored unit inactive")
        post=gfa(20)
    except Exception as exc:
        errors.append("restore: "+str(exc)[:180])
        post={}
    report={"result":"PASS_ORIGINAL_SERVICES_RESTORED" if not errors
                    else "FAIL_OR_NOT_VERIFIED",
            "errors":errors,"actions":actions,"gfa":post}
    save(session/"recovery.json",report)
    print("HYBRID_SHADOW_RECOVERY="+json.dumps(report,sort_keys=True),flush=True)
    return int(bool(errors))


def launch(release):
    data=preflight(release)
    SESSIONS.mkdir(mode=0o700,parents=True,exist_ok=True)
    os.chmod(SESSIONS,0o700)
    stamp=dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    session=SESSIONS/("run-"+stamp+"-"+str(os.getpid()))
    session.mkdir(mode=0o700)
    save(session/"state.json",data)
    env=str(release/"tools")+":/opt/optolink"
    argv=["systemd-run","--unit="+UNIT,"--wait","--collect",
          "--property=Type=exec","--property=RuntimeMaxSec=130",
          "--property=TimeoutStopSec=120","--property=KillMode=control-group",
          "--setenv=PYTHONPATH="+env,
          "--property=ExecStopPost="+PYTHON+" -m handover_acceleration.shadow_canary --recover "+str(session),
          PYTHON,"-m","handover_acceleration.shadow_canary","--worker",str(session)]
    print("HYBRID_SHADOW_SESSION="+str(session),flush=True)
    result=subprocess.run(argv,check=False)
    try:check=json.loads((session/"measurement.json").read_text())
    except Exception:check={}
    try:restore=json.loads((session/"recovery.json").read_text())
    except Exception:restore={}
    success=(result.returncode==0 and
             check.get("status")=="SHADOW_DIAGNOSTIC_PASS_NO_P300" and
             restore.get("result")=="PASS_ORIGINAL_SERVICES_RESTORED")
    print("HYBRID_SHADOW_RESULT="+json.dumps({
        "result":"PASS" if success else "FAIL_OR_NOT_VERIFIED",
        "measurement":check,"recovery":restore},sort_keys=True),flush=True)
    return 0 if success else 1


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    group=parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--plan",type=Path)
    group.add_argument("--launch",type=Path)
    group.add_argument("--worker",type=Path)
    group.add_argument("--recover",type=Path)
    parser.add_argument("--accept-telemetry-pause",action="store_true")
    args=parser.parse_args(argv)
    if args.plan is not None:
        print(json.dumps(preflight(args.plan),sort_keys=True))
        return 0
    if args.launch is not None:
        if not args.accept_telemetry_pause:
            raise CanaryRejected("explicit pause flag required")
        return launch(args.launch)
    if os.geteuid()!=0 or not os.environ.get("INVOCATION_ID"):
        raise CanaryRejected("only systemd ExecStopPost or worker allowed")
    return worker(args.worker) if args.worker else recover(args.recover)


if __name__=="__main__":
    try:raise SystemExit(main())
    except (CanaryRejected,OSError,ValueError) as exc:
        print("HYBRID_SHADOW_ERROR="+type(exc).__name__+": "+str(exc)[:300],
              file=sys.stderr,flush=True)
        raise SystemExit(1)
