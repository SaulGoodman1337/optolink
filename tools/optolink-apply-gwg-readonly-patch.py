#!/usr/bin/env python3
"""OFFLINE/RESEARCH-only staging of third protocol GWG_C7 on existing owner.

--check only inspects; --apply requires a staging root other than /opt/optolink.
This tool intentionally cannot hotpatch the production gas-heating daemon.
"""
from __future__ import annotations
import argparse
import ast
import hashlib
import os
from pathlib import Path
import shutil
import sys
import tempfile

BASE_SHA256 = {
    "vs12_adapter.py": "67a760e925719225d61e375e9c976743b7bfb2d6bec8a9ea59d612397c4b3de2",
    "requests_util.py": "7cc01e2fb41a56adf0f395a86a2a352411c9632032744eeb59ebfd669c51f790",
}
MARK_ADAPTER = "# community-scripts: GWG C7 read-only third backend"
MARK_REQUESTS = "# community-scripts: GWG C7 read-only command"
CODE = Path(__file__).with_name("optolinkgwg.py")
ROOT_PRODUCTION = Path('/opt/optolink')


class UnsafePatch(RuntimeError):
    pass


def newline_of(text: str) -> str:
    return '\r\n' if '\r\n' in text else '\n'


def patch_adapter(source: str) -> str:
    if MARK_ADAPTER in source:
        return source
    nl = newline_of(source)
    import_marker = 'import optolinkvs1' + nl
    if source.count(import_marker) != 1:
        raise UnsafePatch('VS1 import marker absent/ambiguous')
    source = source.replace(import_marker, import_marker + 'import optolinkgwg' + nl, 1)
    logger_import = 'from c_settings_adapter import settings' + nl
    if source.count(logger_import) != 1:
        raise UnsafePatch('owner settings import marker absent/ambiguous')
    source = source.replace(logger_import, logger_import + 'from logger_util import logger' + nl, 1)
    old_read = nl.join([
        '    else:',
        '        return optolinkvs1.read_datapoint_ext(addr, rdlen, ser)',
    ])
    old_gfa = nl.join([
        '    if VS2:',
        '        return 0xAF, addr, bytearray()',
        '    return optolinkvs1.read_gfa_ext(addr, rdlen, ser)',
    ])
    old_write = nl.join([
        '    else:',
        '        return optolinkvs1.write_datapoint_ext(addr, data, ser)',
    ])
    for item in (old_read, old_gfa, old_write):
        if source.count(item) != 1:
            raise UnsafePatch('owner adapter markers absent/ambiguous')
    source = source.replace(old_read, nl.join([
        '    else:',
        '        _gwg_resync_kw_if_needed()',
        '        return optolinkvs1.read_datapoint_ext(addr, rdlen, ser)',
    ]), 1)
    source = source.replace(old_gfa, nl.join([
        '    if VS2:',
        '        return 0xAF, addr, bytearray()',
        '    _gwg_resync_kw_if_needed()',
        '    return optolinkvs1.read_gfa_ext(addr, rdlen, ser)',
    ]), 1)
    source = source.replace(old_write, nl.join([
        '    else:',
        '        _gwg_resync_kw_if_needed()',
        '        return optolinkvs1.write_datapoint_ext(addr, data, ser)',
    ]), 1)
    anchor = 'def init_protocol(ser:serial.Serial) -> bool:' + nl
    if source.count(anchor) != 1:
        raise UnsafePatch('owner adapter function insertion absent/ambiguous')
    addition = nl.join([
        MARK_ADAPTER,
        '# GWG and KW may share the operating mode, but their next sync framing',
        '# is not proven interchangeable. Force normal KW EOT/ENQ after GWG.',
        '_gwg_force_kw_sync = False',
        'GWG_DEFAULT_RETRIES = 0',
        '',
        'def _gwg_resync_kw_if_needed() -> None:',
        '    global _gwg_force_kw_sync',
        '    if _gwg_force_kw_sync:',
        '        optolinkvs1.last_comm = float("-inf")',
        '        _gwg_force_kw_sync = False',
        '',
        'def read_gwg_ext(addr:int, rdlen:int, ser:serial.Serial, retries:int=0) -> tuple[int, int, bytearray]:',
        '    global _gwg_force_kw_sync',
        '    if VS2:',
        '        return 0xAF, addr, bytearray()',
        '    if retries not in (0, 1):',
        '        return 0xFD, addr, bytearray()',
        '    try:',
        '        return optolinkgwg.read_datapoint_ext(',
        '            addr, rdlen, ser, retries=retries,',
        '            trace_hook=lambda row: logger.debug("GWG_C7 TX/RX %s", row))',
        '    finally:',
        '        _gwg_force_kw_sync = True',
        '',
        '',
    ]) + nl
    source = source.replace(anchor, addition + anchor, 1)
    ast.parse(source)
    return source


def patch_requests(source: str) -> str:
    if MARK_REQUESTS in source:
        return source
    nl = newline_of(source)
    anchor = '        elif(cmnd in ["write", "w"]):'
    if source.count(anchor) != 1:
        raise UnsafePatch('MQTT/TCP request parser anchor absent/ambiguous')
    addition = nl.join([
        '        ' + MARK_REQUESTS,
        '        elif(cmnd == "gwgread"):',
        '            # One serial owner, GWG C7 virtual read only; 8-bit address.',
        '            # Syntax: gwgread;0xF8;4[;0|1] (retries max 1).',
        '            if numelms not in (3, 4):',
        '                retcode, addr, data = 0xFD, 0, bytearray()',
        '            else:',
        '                addr = utils.get_int(parts[1])',
        '                rdlen = int(parts[2])',
        '                retries = int(parts[3]) if numelms == 4 else 0',
        '                retcode, addr, data = vs12_adapter.read_gwg_ext(addr, rdlen, serViDev, retries)',
        '            val = utils.arr2hexstr(data) if retcode == 1 else "?"',
        '            retstr = get_retstr(retcode, addr, val)',
        '',
    ]) + nl
    # Comment must be before elif, not between prior conditional and elif at wrong indent.
    source = source.replace(anchor, addition + anchor, 1)
    ast.parse(source)
    return source


def verify_root(root: Path) -> dict:
    report = {}
    for fname, base_hash in BASE_SHA256.items():
        path = root / fname
        if not path.is_file():
            report[fname] = 'missing'
            continue
        src = path.read_bytes()
        current = hashlib.sha256(src).hexdigest()
        marker = MARK_ADAPTER if fname == 'vs12_adapter.py' else MARK_REQUESTS
        if current == base_hash:
            report[fname] = 'pinned_base'
        elif marker.encode('utf-8') in src:
            report[fname] = 'already_patched'
        else:
            report[fname] = 'unknown_sha256:' + current
    report['optolinkgwg.py'] = 'present' if (root / 'optolinkgwg.py').exists() else 'absent'
    return report


def stage(root: Path) -> None:
    if root.resolve() == ROOT_PRODUCTION:
        raise UnsafePatch('production /opt/optolink is blocked in this offline patcher')
    status = verify_root(root)
    if any(status[n] not in ('pinned_base', 'already_patched') for n in BASE_SHA256):
        raise UnsafePatch('source SHA gates failed: ' + repr(status))
    updates = {}
    for fname, function in [('vs12_adapter.py', patch_adapter),
                            ('requests_util.py', patch_requests)]:
        original = (root / fname).read_bytes()
        # Maintain CRLF of upstream runtime.
        src = original.decode('utf-8')
        patched = function(src)
        ast.parse(patched)
        updates[fname] = patched.encode('utf-8')
    if not CODE.is_file():
        raise UnsafePatch('GWG C7 backend module unavailable')
    updates['optolinkgwg.py'] = CODE.read_bytes()
    for fname, data in updates.items():
        ast.parse(data.decode('utf-8'))
    # Atomic per-file staging. No open serial port or service restart.
    for fname, data in updates.items():
        path = root / fname
        if path.exists() and path.read_bytes() == data:
            continue
        fd, tmp = tempfile.mkstemp(prefix='.gwg-staged-', dir=root)
        try:
            with os.fdopen(fd, 'wb') as out:
                out.write(data)
                out.flush()
                os.fsync(out.fileno())
            os.chmod(tmp, (path.stat().st_mode & 0o777) if path.exists() else 0o644)
            os.replace(tmp, path)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)
    print('STAGED_GWG_C7_READONLY=PASS')
    print(verify_root(root))


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', type=Path, default=ROOT_PRODUCTION)
    p.add_argument('--apply', action='store_true')
    args = p.parse_args()
    if args.apply:
        stage(args.root)
    else:
        print(verify_root(args.root))
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except UnsafePatch as exc:
        print('REFUSED:', exc, file=sys.stderr)
        sys.exit(2)
