"""Patch a COPY of the Maintenance MQTT API to load the reviewed shadow core.

The original production API puts /opt/optolink first on sys.path. Merely
staging a patched maintenance core in a different directory would therefore
still load the UNFENCED original. Fix this only in the side-by-side API copy,
immediately before the existing import. The active original remains intact.
"""
from __future__ import annotations

import argparse
import ast
from pathlib import Path


class MaintenanceApiPatchRejected(RuntimeError):
    pass


ANCHOR = "from optolink_maintenance_core import ("
MARKER = "# HYBRID_MAINTENANCE_API_SHADOW_V1"
INJECT = '''
# HYBRID_MAINTENANCE_API_SHADOW_V1: injected into a COPY before core import
from pathlib import Path as _hybrid_Path
_hybrid_api_root = _hybrid_Path(__file__).resolve().parent.parent
_hybrid_core_path = _hybrid_api_root / "src" / "optolink_maintenance_core.py"
if (_hybrid_core_path.is_symlink() or not _hybrid_core_path.is_file()
        or not (_hybrid_api_root / "stage-manifest.json").is_file()):
    raise RuntimeError("hybrid maintenance release lacks an audited core")
# The original API inserted /opt/optolink; the approved patched module must
# override it for THIS process only. No production sys.path changes.
sys.path.insert(0, str(_hybrid_core_path.parent))
'''


def patch_maintenance_api(source: str) -> str:
    if not isinstance(source,str) or source.count(ANCHOR)!=1 or MARKER in source:
        raise MaintenanceApiPatchRejected("unreviewed or already patched maintenance API")
    try:
        tree=ast.parse(source)
    except SyntaxError as exc:
        raise MaintenanceApiPatchRejected("invalid Python API source") from exc
    # Require existing app path insertion and one exact imported maintenance
    # module before adding a second search path.
    if "sys.path.insert(0, APP_DIR)" not in source:
        raise MaintenanceApiPatchRejected("original application import order changed")
    imported=[n for n in ast.walk(tree) if isinstance(n,ast.ImportFrom)
              and n.module=="optolink_maintenance_core"]
    if len(imported)!=1:
        raise MaintenanceApiPatchRejected("maintenance core import topology changed")
    candidate=source.replace(ANCHOR,INJECT+"\n"+ANCHOR,1)
    compile(candidate,"<maintenance-api-shadow>","exec")
    return candidate


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args(argv)
    if args.source.resolve()==args.output.resolve() or args.source.is_symlink():
        raise MaintenanceApiPatchRejected("refuse in-place or symlink source changes")
    content=patch_maintenance_api(args.source.read_text())
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(content)
    print("HYBRID_MAINTENANCE_API_SHADOW=PASS")
    return 0


if __name__=="__main__":
    raise SystemExit(main())
