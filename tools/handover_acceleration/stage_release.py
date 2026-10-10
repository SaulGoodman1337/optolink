"""Stage exact-source checked hybrid runtime files WITHOUT changing systemd.

Creates a side-by-side, immutable-at-rest candidate directory:
  main/optolinkvs2_switch.py   original single-owner dispatcher + guarded hooks
  bin/<4 writers>              complete logical transaction wrappers
  src/optolink_maintenance_core.py  exception/readback guarded module
  tools/handover_acceleration/*.py   reviewed coordinator and lease logic
  stage-manifest.json          hashes of original and generated inputs

This is deliberately NOT an installer or a proof of running producer
enrollment. Systemd, MQTT, live /opt files, RAM, and serial stay untouched.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import tempfile

try:
    from .dispatcher_patch import patch_dispatcher
    from .producer_boundary_patch import patch_producer
    from .hybrid_acceptance import _verify_original
except ImportError:
    from dispatcher_patch import patch_dispatcher
    from producer_boundary_patch import patch_producer
    from hybrid_acceptance import _verify_original

SOURCE_MAP = {
    "party":Path("/usr/local/bin/optolink-party-emulator"),
    "schedule":Path("/usr/local/bin/optolink-schedule-manager"),
    "service-programs":Path("/usr/local/bin/optolink-service-programs"),
    "clock-sync":Path("/usr/local/bin/optolink-clock-sync"),
    "maintenance":Path("/opt/optolink/optolink_maintenance_core.py"),
}
ORIGINAL_MAIN = Path("/opt/optolink/optolinkvs2_switch.py")
TOOLS_DIR = Path(__file__).resolve().parent


class StageRejected(RuntimeError):
    pass


def _digest(raw:bytes)->str:
    return hashlib.sha256(raw).hexdigest()


def stage(*, target:Path, source_map=SOURCE_MAP, original_main=ORIGINAL_MAIN,
          tools_dir=TOOLS_DIR)->dict:
    """Unprivileged staging is acceptable; production source remains readonly."""
    if not isinstance(target,Path) or not target.is_absolute():
        raise StageRejected("absolute stage directory required")
    if target.exists() or target.is_symlink():
        raise StageRejected("never overwrite an existing staged release")
    if set(source_map)!={"party","schedule","service-programs","clock-sync","maintenance"}:
        raise StageRejected("exactly five source roles required")
    if not tools_dir.is_dir():
        raise StageRejected("missing release source package")

    source_bytes={}
    for role,path in source_map.items():
        if path.is_symlink() or not path.is_file():
            raise StageRejected("unsafe writer source: "+role)
        source_bytes[role]=path.read_bytes()
    if original_main.is_symlink() or not original_main.is_file():
        raise StageRejected("original dispatcher source absent")
    main_bytes=original_main.read_bytes()
    main_text=main_bytes.decode("utf-8").replace("\r\n","\n")
    generated_main=patch_dispatcher(main_text)
    generated_writers={
        role:patch_producer(source_bytes[role].decode("utf-8"),role)
        for role in source_map
    }
    # Validate every source compilation and exact expected wrapper marker
    # BEFORE creating a staging directory.
    compile(generated_main,"shadow-main","exec")
    for role,content in generated_writers.items():
        compile(content,"producer-"+role,"exec")
        if content.count("# HYBRID_PRODUCER_EPOCH_V1") != 1:
            raise StageRejected("missing producer wrapper: "+role)
    package=sorted(
        (p for p in tools_dir.glob("*.py")
         if not p.is_symlink() and p.is_file()),
        key=lambda p:p.name)
    for p in package:
        compile(p.read_text(),p.name,"exec")
    manifest={
        "schema":1,"state":"STAGED_ONLY_NOT_DEPLOYED",
        "normalized_main_sha256":_digest(main_text.encode()),
        "raw_main_sha256":_digest(main_bytes),
        "writer_sources":{r:{"raw_sha256":_digest(source_bytes[r]),
                             "source":str(source_map[r])}
                          for r in sorted(source_map)},
        "generated_files":{},
        "prod_services_changed":False,
    }

    # Stage first in a private sibling and rename only after all writes pass.
    target.parent.mkdir(parents=True,exist_ok=True)
    temp=Path(tempfile.mkdtemp(prefix=".hybrid-staging-",dir=target.parent))
    try:
        os.chmod(temp,0o700)
        staged={
            "main/optolinkvs2_switch.py":generated_main.encode(),
            **{("src" if role=="maintenance" else "bin")+"/"+source_map[role].name:
               generated_writers[role].encode() for role in source_map},
        }
        for p in package:
            staged["tools/handover_acceleration/"+p.name]=p.read_bytes()
        for rel,raw in staged.items():
            dest=temp/rel
            dest.parent.mkdir(parents=True,exist_ok=True)
            dest.write_bytes(raw)
            os.chmod(dest,0o600)
            manifest["generated_files"][rel]=_digest(raw)
        (temp/"stage-manifest.json").write_text(
            json.dumps(manifest,sort_keys=True,indent=2)+"\n")
        os.chmod(temp/"stage-manifest.json",0o600)
        temp.rename(target)
    except BaseException:
        shutil.rmtree(temp,ignore_errors=True)
        raise
    return manifest


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target",type=Path,required=True)
    args=parser.parse_args(argv)
    data=stage(target=args.target)
    print(json.dumps({"status":"STAGED_ONLY","target":str(args.target),
                      "generated_files":len(data["generated_files"]),
                      "raw_main_sha256":data["raw_main_sha256"],
                      "normalized_main_sha256":data["normalized_main_sha256"],
                      "production_changed":False},sort_keys=True))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
