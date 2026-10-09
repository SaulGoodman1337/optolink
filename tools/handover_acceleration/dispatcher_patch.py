"""Generate/inspect a *copy* of the pinned original main dispatcher, never install.

The application has exactly three synchronous request call sites:
  - poll item, MQTT request, TCP request.
Vitoconnect direct-forwarding and the keepalive remain untouched; this patch
refuses to run for a different structure instead of guessing replacement sites.
The shim stays legacy-only unless a FUTURE explicitly reviewed maint owner is
bound; environment opt-in enables only a transparent in-process dispatch shim.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import sys


class PatchRejected(RuntimeError):
    pass


CALL_SITES = (
    ('requests_util.response_to_request(item, ser)', 1),
    ('requests_util.response_to_request(msg, serOptolink)', 2),
)
ANCHOR = '                logger.info(f"{spr} protocol initialized")'
IMPORT_ANCHOR = 'import requests_util\n'

SHIM = '''\n# RESEARCH_SHIM_V1: separate in-process request boundary, disabled by default.
_handover_dispatch_bridge = None

def handover_legacy_or_shim(request, ser):
    if _handover_dispatch_bridge is None:
        return requests_util.response_to_request(request, ser)
    return _handover_dispatch_bridge.response_to_request(request, ser)

'''

SETUP = '''\n                # Optional transparent legacy-only diagnostic shim. No P300
                # transitions or extra serial opens are enabled here.
                if (settings.vs1protocol and settings.port_vitoconnect is None and
                        os.environ.get("OPTO_RESEARCH_DISPATCH_SHADOW") == "1"):
                    from handover_acceleration.dispatcher_bridge import InProcessDispatchBridge
                    global _handover_dispatch_bridge
                    _handover_dispatch_bridge = InProcessDispatchBridge(
                        serOptolink, requests_util.response_to_request,
                        vs1protocol=True, vitoconnect_port=None,
                        allow_maintenance=False)
'''


def patch_dispatcher(source: str) -> str:
    if not isinstance(source, str) or 'RESEARCH_SHIM_V1' in source:
        raise PatchRejected('invalid or previously patched dispatcher')
    for needle, count in CALL_SITES:
        if source.count(needle) != count:
            raise PatchRejected('unexpected original call count: ' + needle)
    if source.count(ANCHOR) != 1 or source.count(IMPORT_ANCHOR) != 1:
        raise PatchRejected('upstream startup/import layout changed')
    # Keep direct Vitoconnect forwarding outside this scope.
    for mandatory in ('viconn_util.get_vicon_request()',
                      'vs12_adapter.receive_telegr(True, True, serOptolink,',
                      'vs12_adapter.read_datapoint_ext(0xf8, 2, serOptolink)'):
        if source.count(mandatory) != 1:
            raise PatchRejected('direct/keepalive serial topology changed')
    patched = source.replace(IMPORT_ANCHOR, IMPORT_ANCHOR + 'import os\n' + SHIM, 1)
    for old, _ in CALL_SITES:
        patched = patched.replace(old, old.replace('requests_util.response_to_request',
                                                    'handover_legacy_or_shim'))
    patched = patched.replace(ANCHOR, ANCHOR + SETUP, 1)
    if patched.count('handover_legacy_or_shim(item, ser)') != 1:
        raise PatchRejected('poll seam not installed')
    if patched.count('handover_legacy_or_shim(msg, serOptolink)') != 2:
        raise PatchRejected('MQTT/TCP seams not installed')
    compile(patched, '<generated-shadow-optolinkvs2-switch>', 'exec')
    return patched


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source', type=Path, required=True)
    p.add_argument('--output', type=Path, help='write a COPY, never overwrite source')
    args = p.parse_args(argv)
    raw = args.source.read_text(encoding='utf-8')
    patched = patch_dispatcher(raw)
    if args.output:
        if args.output.resolve() == args.source.resolve():
            raise PatchRejected('refuse in-place modification')
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(patched, encoding='utf-8')
    print('UPSTREAM_DISPATCH_SEAM=PASS 3_CENTRAL_CALLS 0_NEW_HANDOVER_IO')
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (PatchRejected, OSError, SyntaxError) as exc:
        print('UPSTREAM_DISPATCH_SEAM=REFUSED ' + str(exc), file=sys.stderr)
        raise SystemExit(1)
