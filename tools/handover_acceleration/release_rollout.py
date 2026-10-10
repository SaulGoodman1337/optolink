"""Reversible side-by-side rollout SPEC, no auto-deployment.

Produces deterministic systemd drop-ins and a manifest for the verified
five-writer release. All source files stay under a protected release root.
--plan is read-only; --stage-only creates a root-owned COPY without altering
any existing /opt/optolink source or systemd service.

The generated drop-ins are intentionally NOT installed. A separate
independently supervised apply/rollback process is still required before
experimental continuous P300 may be activated.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import tempfile

from .runtime_enrollment import (ORIGINAL_PATHS,ORIGINAL_MAINTENANCE_API,
                                 UNITS,LEASE_PATH)

PYTHON = "/opt/optolink/venv/bin/python"
ROOT = Path("/var/lib/optolink-hybrid")
RELEASES = ROOT/"releases"
SERVICE_MAIN = "optolink-splitter.service"
SOURCE_MAIN = Path("/opt/optolink/optolinkvs2_switch.py")


class RolloutRejected(RuntimeError):
    pass


def _sha(raw:bytes)->str:
    return hashlib.sha256(raw).hexdigest()


def validate_staging(source:Path)->dict:
    if source.is_symlink() or not source.is_dir():
        raise RolloutRejected("immutable prepared release directory required")
    meta=source/"stage-manifest.json"
    if meta.is_symlink() or not meta.is_file():
        raise RolloutRejected("verified stage manifest absent")
    try:
        data=json.loads(meta.read_text())
    except (OSError,ValueError) as exc:
        raise RolloutRejected("stage manifest invalid") from exc
    if (data.get("schema")!=1 or data.get("state")!="STAGED_ONLY_NOT_DEPLOYED"
            or data.get("prod_services_changed") is not False):
        raise RolloutRejected("unknown source release schema")
    hashes=data.get("generated_files")
    if not isinstance(hashes,dict) or len(hashes)<12:
        raise RolloutRejected("incomplete release bundle")
    mandatory={
        "main/optolinkvs2_switch.py","bin/optolink-maintenance-api",
        "src/optolink_maintenance_core.py",
        *(f"bin/{ORIGINAL_PATHS[r].name}" for r in UNITS if r!="maintenance"),
        "tools/handover_acceleration/coordinator.py",
        "tools/handover_acceleration/continuous_runtime.py",
        "tools/handover_acceleration/producer_fence.py",
    }
    if not mandatory.issubset(hashes):
        raise RolloutRejected("reviewed mandatory sources missing")
    actual={p.relative_to(source).as_posix() for p in source.rglob("*")
            if p.is_file()}
    if actual!={*hashes,"stage-manifest.json"}:
        raise RolloutRejected("unexpected extra or missing release files")
    for rel,expected in hashes.items():
        p=source/rel
        if (not isinstance(rel,str) or not rel or p.is_symlink()
                or not p.is_file() or p.resolve().parent == SOURCE_MAIN.parent
                or _sha(p.read_bytes())!=expected):
            raise RolloutRejected("release file changed: "+str(rel))
    if SOURCE_MAIN.is_file() and SOURCE_MAIN.read_text().encode():
        current_normalized=_sha(SOURCE_MAIN.read_text().encode())
        if data.get("normalized_main_sha256")!=current_normalized:
            raise RolloutRejected("production original changed since staging")
    return data


def unit_dropins(root:Path)->dict[str,str]:
    if (not root.is_absolute() or not root.is_relative_to(RELEASES)
            or len(root.relative_to(RELEASES).parts)!=1):
        raise RolloutRejected("unreviewed release target")
    pythonpath=f"{root}/tools:/opt/optolink"
    shared="[Service]\nEnvironment=PYTHONPATH="+pythonpath+"\n"
    program={
        SERVICE_MAIN:root/"main/optolinkvs2_switch.py",
        **{UNITS[role]:(root/("src" if role=="maintenance" else "bin")/
                         ORIGINAL_PATHS[role].name)
           for role in UNITS if role!="maintenance"},
        UNITS["maintenance"]:root/"bin/optolink-maintenance-api",
    }
    result={}
    for unit,path in program.items():
        if unit==SERVICE_MAIN:
            extra=("Environment=OPTO_RESEARCH_DISPATCH_SHADOW=1\n"
                   "Environment=OPTO_HYBRID_RUNTIME_AUTO=disabled\n")
        else:
            extra=""
        result[unit]=(
            shared+extra+"ExecStart=\n"
            f"ExecStart={PYTHON} -u {path}\n"
        )
    return result


def generate_enrollment(root:Path)->dict:
    if not root.is_relative_to(RELEASES) or len(root.relative_to(RELEASES).parts)!=1:
        raise RolloutRejected("enrollment requires reviewed release path")
    fields={}
    for role,unit in UNITS.items():
        p=root/("src" if role=="maintenance" else "bin")/ORIGINAL_PATHS[role].name
        content=p.read_bytes()
        fields[role]={"unit":unit,"path":str(p),"sha256":_sha(content)}
        if role=="maintenance":
            api=root/"bin/optolink-maintenance-api"
            fields[role]["api_path"]=str(api)
            fields[role]["api_sha256"]=_sha(api.read_bytes())
    return {"schema":1,"producer_lock":str(LEASE_PATH),"writers":fields}


def plan(source:Path,release_id:str)->dict:
    if (not release_id or len(release_id)>64
            or any(c not in "abcdefghijklmnopqrstuvwxyz0123456789-" for c in release_id)
            or release_id.startswith("-")):
        raise RolloutRejected("invalid release id")
    stage=validate_staging(source)
    target=RELEASES/release_id
    if target.exists() or target.is_symlink():
        raise RolloutRejected("target release already exists")
    dropins=unit_dropins(target)
    return {"result":"REVIEWED_STAGE_PLAN_NO_SYSTEMD_MUTATION",
            "target":str(target),"units":dropins,
            "files":len(stage["generated_files"]),
            "pending_merge":True,
            "required_independent_rollback":True}


def stage_root_copy(source:Path,release_id:str)->dict:
    if os.geteuid()!=0:
        raise RolloutRejected("root required for staging protected release")
    details=plan(source,release_id)
    dest=Path(details["target"])
    RELEASES.mkdir(mode=0o750,parents=True,exist_ok=True)
    os.chown(ROOT,0,__import__("grp").getgrnam("optolink").gr_gid)
    os.chmod(ROOT,0o750)
    os.chown(RELEASES,0,__import__("grp").getgrnam("optolink").gr_gid)
    os.chmod(RELEASES,0o750)
    group=__import__("grp").getgrnam("optolink").gr_gid
    temp=Path(tempfile.mkdtemp(prefix=".stage-",dir=RELEASES))
    try:
        shutil.copytree(source,temp,dirs_exist_ok=True,symlinks=False)
        for node in [temp,*temp.rglob("*")]:
            if node.is_symlink():
                raise RolloutRejected("release symlink is forbidden")
            os.chown(node,0,group)
            os.chmod(node,0o750 if node.is_dir() else 0o640)
        for node in (temp/"bin").iterdir():
            os.chmod(node,0o750)
        temp.rename(dest)
    except BaseException:
        shutil.rmtree(temp,ignore_errors=True)
        raise
    manifest=generate_enrollment(dest)
    (dest/"enrollment-draft.json").write_text(json.dumps(manifest,sort_keys=True,indent=2)+"\n")
    os.chown(dest/"enrollment-draft.json",0,group)
    os.chmod(dest/"enrollment-draft.json",0o640)
    # This is NOT yet the live root enrollment manifest and does NOT permit
    # automatic P300; no service or serial device is touched.
    details["result"]="ROOT_RELEASE_STAGED_NOT_ACTIVATED"
    return details


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source",type=Path,required=True)
    parser.add_argument("--release-id",required=True)
    parser.add_argument("--stage-only",action="store_true")
    args=parser.parse_args(argv)
    data=(stage_root_copy(args.source,args.release_id)
          if args.stage_only else plan(args.source,args.release_id))
    print(json.dumps(data,sort_keys=True))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
