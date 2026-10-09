"""Read-only audit of the original installed splitter Python dispatch seam.

Never imports production modules, settings, pySerial or systemd. Scans only
source structure; not a runtime/live health test. No data from settings files
is opened. A compatible source can be patched AS A COPY later, not in place.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re

try:
    from .dispatcher_patch import patch_dispatcher, PatchRejected
except ImportError:  # direct read-only CLI invocation from the research checkout
    from dispatcher_patch import patch_dispatcher, PatchRejected


class AuditRejected(RuntimeError):
    pass


MAX_SOURCE_BYTES = 2_000_000


def _source(path: Path) -> str:
    if path.is_symlink() or not path.is_file():
        raise AuditRejected('missing or symlinked Python source: ' + path.name)
    if path.stat().st_size > MAX_SOURCE_BYTES:
        raise AuditRejected('source too large for bounded audit: ' + path.name)
    try:
        return path.read_text(encoding='utf-8')
    except UnicodeError as exc:
        raise AuditRejected('invalid UTF-8 in Python source') from exc


def source_audit(main: str, requests: str, adapter: str) -> dict:
    """Return static source facts, never execute/import user-owned text."""
    if not all(isinstance(x, str) for x in (main, requests, adapter)):
        raise AuditRejected('text-only sources required')
    source_sha = hashlib.sha256(main.encode('utf-8')).hexdigest()
    count_poll = main.count('requests_util.response_to_request(item, ser)')
    count_secondary = main.count('requests_util.response_to_request(msg, serOptolink)')
    direct_vicon = 'viconn_util.get_vicon_request()' in main
    keepalive = 'vs12_adapter.read_datapoint_ext(0xf8, 2, serOptolink)' in main
    try:
        patch_dispatcher(main)
        can_patch,reason=True,'MATCHED_PINNED_SEAM_STRUCTURE'
    except (PatchRejected,SyntaxError) as exc:
        can_patch,reason=False,str(exc)[:180]
    return {
        'result':'SOURCE_AUDIT_ONLY_NO_HARDWARE_IO',
        'main_sha256':source_sha,
        'main_legacy_poll_calls':count_poll,
        'main_mqtt_tcp_calls':count_secondary,
        'main_direct_vitoconnect_branch':direct_vicon,
        'main_vs1_keepalive':keepalive,
        'legacy_request_parser_present':'def response_to_request(' in requests,
        'legacy_write_commands_present':all(t in requests for t in
            ('cmnd in ["write", "w"]','cmnd in ["writeraw", "wraw"]')),
        'legacy_gfa_patch_detected':bool(re.search(r'gfaread|read_gfa_ext',requests,re.I)),
        'adapter_static_protocol_flag':'VS2 = not settings.vs1protocol' in adapter,
        'shadow_source_copy_supported':can_patch,
        'shadow_reason':reason,
        'requires_independent_live_integration_review':True,
        'production_changes_performed':False,
    }


def audit_directory(root: Path) -> dict:
    if root.is_symlink() or not root.is_dir():
        raise AuditRejected('invalid or symlinked application root')
    return source_audit(*(_source(root/name) for name in
                          ('optolinkvs2_switch.py','requests_util.py','vs12_adapter.py')))


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=Path('/opt/optolink'))
    args=parser.parse_args(argv)
    report=audit_directory(args.root)
    print('DISPATCHER_COMPATIBILITY='+json.dumps(report,sort_keys=True))
    return 0  # structurally unsupported is a useful diagnostic, not execution failure


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (AuditRejected, OSError) as exc:
        print('DISPATCHER_AUDIT_ERROR='+type(exc).__name__+': '+str(exc))
        raise SystemExit(1)
