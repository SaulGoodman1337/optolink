"""Generate/inspect a *copy* of the pinned original main dispatcher, never install.

The application has exactly three synchronous request call sites:
  - poll item, MQTT request, TCP request.
Vitoconnect direct-forwarding and the keepalive remain untouched; this patch
refuses to run for a different structure instead of guessing replacement sites.
The ordinary shim stays legacy-only. The separately supervised test startup
may exercise a single fixed read-only in-process P300 batch and then exit.
No input enables recurring hybrid writes or dynamic generic addresses.
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
MQTT_CONNECT_ANCHOR = '                mod_mqtt.connect_mqtt()'
FORCED_READ_ANCHOR = ('                                retcode = do_poll_item('
                      'poll_data, serOptolink, item_index=force_refresh_index)'
                      '      # type: ignore')
FORCED_READ_COMPLETE = (
    '\n                                if getattr(mod_mqtt, "_hybrid_readback_ledger", None) is not None:'
    '\n                                    mod_mqtt._hybrid_complete_forced(retcode)'
)
MQTT_EPOCH_PRECONNECT = """
                # The automatic variant freezes BOTH asynchronous ingress paths
                # before any new write or delayed HA readback can be queued.
                # Explicit opt-in and enrollment are independently required.
                if (settings.vs1protocol and settings.port_vitoconnect is None
                        and os.environ.get('OPTO_RESEARCH_DISPATCH_SHADOW') == '1'):
                    _auto_requested = (
                        os.environ.get('OPTO_HYBRID_RUNTIME_AUTO') in
                        ('fenced-readonly', 'fenced-ondemand'))
                    if _auto_requested:
                        from handover_acceleration.ingress_epoch import IngressEpoch
                        from handover_acceleration.pending_refresh import install_before_mqtt_connect
                        global _hybrid_ingress
                        _hybrid_ingress = IngressEpoch()
                        mod_mqtt.on_message = _hybrid_ingress.wrap_mqtt_callback(mod_mqtt.on_message)
                        install_before_mqtt_connect(mod_mqtt)
                        c_tcpserver.TcpServer = _hybrid_ingress.tcp_class(c_tcpserver.TcpServer)
                    elif os.environ.get('OPTO_HYBRID_RUNTIME_DIAGNOSTIC') == '1':
                        from handover_acceleration.pending_refresh import install_before_mqtt_connect
                        install_before_mqtt_connect(mod_mqtt)
"""


SHIM = '''\n# RESEARCH_SHIM_V1: separate in-process request boundary, disabled by default.
_handover_dispatch_bridge = None
_handover_runtime_gate = None  # passive unless strict auto enrollment
_hybrid_ingress = None
_hybrid_auto = None

def handover_legacy_or_shim(request, ser):
    if _handover_dispatch_bridge is None:
        return requests_util.response_to_request(request, ser)
    if _handover_runtime_gate is not None:
        _handover_runtime_gate.observe_legacy(request)
    _result = _handover_dispatch_bridge.response_to_request(request, ser)
    if _handover_runtime_gate is not None:
        _handover_runtime_gate.observe_legacy_result(request, _result)
    if _hybrid_auto is not None and hasattr(_hybrid_auto, 'observe_original_result'):
        _hybrid_auto.observe_original_result(request, _result)
    return _result

'''

BOOT = '''
                # ONE-SHOT SELF-TERMINATING ACCEPTANCE ONLY; no production mode.
                # This executes before any poll / MQTT / TCP frame is dispatched.
                if os.environ.get('OPTO_HYBRID_BOOT_ONESHOT') == 'confirmed-readonly':
                    if not (settings.vs1protocol and settings.port_vitoconnect is None
                            and os.environ.get('OPTO_RESEARCH_DISPATCH_SHADOW') == '1'):
                        raise SystemExit(76)
                    from pathlib import Path as _HybridPath
                    from handover_acceleration.hybrid_boot import run_one_shot
                    try:
                        _report = run_one_shot(
                            serOptolink, settings, requests_util.response_to_request,
                            vs12_adapter.reset_vs1sync,
                            _HybridPath(os.environ['OPTO_HYBRID_REPORT_DIR']))
                        print('HYBRID_BOOT_RESULT=' + _report['status'], flush=True)
                    except BaseException as _error:
                        logger.exception('one-shot borrowed-port experiment failed')
                        print('HYBRID_BOOT_FAILURE=' + type(_error).__name__, flush=True)
                        raise SystemExit(78)
                    # Exit before starting any normal application dispatch loop.
                    raise SystemExit(0)
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
                    # Passive ownership/write-intent telemetry only. This is
                    # NOT an automatic scheduler and never opens another port.
                    from handover_acceleration.runtime_admission import RuntimeAdmissionGate
                    global _handover_runtime_gate
                    _handover_runtime_gate = RuntimeAdmissionGate()
'''


AUTO_BOOT = '''
                # Explicit shadow-only hybrid. A real demand is accepted only
                # through this trusted owner API; arbitrary MQTT/TCP commands
                # never become P300 FC03 or write operations.
                _hybrid_mode = os.environ.get('OPTO_HYBRID_RUNTIME_AUTO')
                if _hybrid_mode in ('fenced-readonly', 'fenced-ondemand'):
                    if not (settings.vs1protocol and settings.port_vitoconnect is None
                            and os.environ.get('OPTO_RESEARCH_DISPATCH_SHADOW') == '1'
                            and _hybrid_ingress is not None and mod_mqtt is not None):
                        raise SystemExit(76)
                    from handover_acceleration.runtime_enrollment import all_writers_attested
                    if not all_writers_attested():
                        logger.error('hybrid runtime refused: writer enrollment absent')
                        raise SystemExit(76)
                    from handover_acceleration.continuous_runtime import (
                        ContinuousReadonlyRuntime, OnDemandReadonlyRuntime)
                    global _hybrid_auto
                    _hybrid_runtime_cls = (
                        OnDemandReadonlyRuntime if _hybrid_mode == 'fenced-ondemand'
                        else ContinuousReadonlyRuntime)
                    _hybrid_auto = _hybrid_runtime_cls(
                        port=serOptolink,
                        legacy_dispatch=requests_util.response_to_request,
                        resume_vs1=vs12_adapter.reset_vs1sync,
                        mqtt=mod_mqtt,
                        tcp_state=lambda: (
                            tcp_server.pending_count() if tcp_server is not None
                            else (0 if settings.tcpip_port is None else 9999)),
                        ingress=_hybrid_ingress,
                        all_writers_attested=all_writers_attested,
                        min_interval_s=(60.0 if
                            os.environ.get('OPTO_HYBRID_CANARY_SESSION') and
                            os.environ.get('INVOCATION_ID')
                            else 120.0))
                    _handover_runtime_gate = _hybrid_auto.gate
                    if _hybrid_mode == 'fenced-ondemand':
                        _selftest = os.environ.get('OPTO_HYBRID_DEMAND_SELFTEST')
                        if _selftest is not None:
                            if not (
                                    _selftest == 'ram_0f20_32'
                                    and os.environ.get('OPTO_HYBRID_CANARY_SESSION')
                                    and os.environ.get('INVOCATION_ID')):
                                logger.error('unreviewed on-demand selftest refused')
                                raise SystemExit(76)
                            from handover_acceleration.scheduler import ReadKind
                            _hybrid_auto.submit_internal(
                                ReadKind.P300_RAM_0F20_32, ttl_s=90.0)
                    logger.info('hybrid shadow runtime admitted ' + _hybrid_mode)
'''

LIVE_KEEPALIVE_ANCHOR = ('                        retcode,_,_ = vs12_adapter.'
                         'read_datapoint_ext(0xf8, 2, serOptolink)     # type: ignore')
LIVE_KEEPALIVE_OBSERVE = (
    '\n                        if _hybrid_auto is not None:'
    '\n                            _hybrid_auto.note_keepalive(retcode)')
AUTO_TICK_ANCHOR = '                # let cpu take a breath if there was nothing to do'
AUTO_TICK = '''
                # At most one finite read-only FC03 batch per cooldown.
                # This runs on the same main serial thread BETWEEN VS1 frames.
                if _hybrid_auto is not None:
                    # Continuous normal polling updates last_vs1_comm and
                    # suppresses the separately scheduled KW keepalive.
                    # At each admission deadline explicitly query the REAL
                    # original VS1 identity instead of trusting a timer.
                    # One bounded read, same existing serial owner, no STX.
                    if (_hybrid_auto.clock() >= _hybrid_auto.next_due and
                            (not hasattr(_hybrid_auto, 'due') or _hybrid_auto.due())):
                        _id_rc, _id_addr, _id_data = vs12_adapter.read_datapoint_ext(
                            0xf8, 2, serOptolink)
                        _id_valid = (
                            _id_rc == 1 and
                            isinstance(_id_data, (bytes, bytearray)) and
                            bytes(_id_data) == bytes.fromhex('20c2'))
                        _hybrid_auto.note_keepalive(1 if _id_valid else 0)
                        if not _id_valid:
                            logger.warning('HYBRID_RUNTIME_VS1_IDENTITY_REJECTED')
                    _tick = _hybrid_auto.tick()
                    if (_tick.status == 'NOT_ADMITTED' and
                            os.environ.get('OPTO_HYBRID_CANARY_SESSION')):
                        logger.info('HYBRID_RUNTIME_REFUSAL ' + _tick.reason)
                    if _tick.status == 'VERIFIED_SWITCH':
                        _readings = {key: value for key, value in _tick.result.reads}
                        _event = {'status': _tick.status,
                                  'vs1_p80': _tick.result.p80_hex,
                                  'vs1_p06': _tick.result.p06_hex,
                                  'p300_fixed': _readings,
                                  'elapsed_ms': _tick.result.elapsed_ms}
                        if getattr(_tick, 'replies', ()):
                            _event['on_demand_raw'] = [
                                {'sequence':r.sequence,'kind':r.kind,
                                 'raw_hex':r.raw_hex,'origin':r.origin}
                                for r in _tick.replies]
                        mod_mqtt.publish_smart(
                            settings.mqtt_topic + '/hybrid/readonly',
                            json.dumps(_event), retain=False)
                        # Independent, session-tagged canary evidence.
                        # A P300 window is logged only AFTER verified VS1
                        # and the original GFA identity/RPM readbacks.
                        if os.environ.get('OPTO_HYBRID_CANARY_SESSION'):
                            _event['canary_session'] = os.environ['OPTO_HYBRID_CANARY_SESSION']
                            logger.info('HYBRID_RUNTIME_VERIFIED_SWITCH ' +
                                        json.dumps(_event, sort_keys=True))
'''
TCP_SPECIAL_ANCHOR = (
    '        tcp_server.command_callback = do_special_command        # type: ignore')
TCP_SPECIAL_FENCED = (
    '        tcp_server.command_callback = ('
    '_hybrid_ingress.wrap_tcp_command(do_special_command)'
    ' if _hybrid_ingress is not None else do_special_command)        # type: ignore')


def patch_dispatcher(source: str) -> str:
    if not isinstance(source, str) or 'RESEARCH_SHIM_V1' in source:
        raise PatchRejected('invalid or previously patched dispatcher')
    for needle, count in CALL_SITES:
        if source.count(needle) != count:
            raise PatchRejected('unexpected original call count: ' + needle)
    if (source.count(ANCHOR) != 1 or source.count(IMPORT_ANCHOR) != 1
            or source.count(MQTT_CONNECT_ANCHOR) != 1
            or source.count(FORCED_READ_ANCHOR) != 1
            or source.count(TCP_SPECIAL_ANCHOR) != 1
            or source.count(LIVE_KEEPALIVE_ANCHOR) != 1
            or source.count(AUTO_TICK_ANCHOR) != 1):
        raise PatchRejected('upstream startup/import layout changed')
    # Keep direct Vitoconnect forwarding outside this scope.
    for mandatory in ('viconn_util.get_vicon_request()',
                      'vs12_adapter.receive_telegr(True, True, serOptolink,',
                      'vs12_adapter.read_datapoint_ext(0xf8, 2, serOptolink)'):
        if source.count(mandatory) != 1:
            raise PatchRejected('direct/keepalive serial topology changed')
    patched = source.replace(IMPORT_ANCHOR, IMPORT_ANCHOR + 'import os\n' + SHIM, 1)
    patched = patched.replace(MQTT_CONNECT_ANCHOR,
                              MQTT_EPOCH_PRECONNECT + MQTT_CONNECT_ANCHOR, 1)
    patched = patched.replace(FORCED_READ_ANCHOR,
                              FORCED_READ_ANCHOR + FORCED_READ_COMPLETE, 1)
    patched = patched.replace(TCP_SPECIAL_ANCHOR,TCP_SPECIAL_FENCED,1)
    patched = patched.replace(LIVE_KEEPALIVE_ANCHOR,
                              LIVE_KEEPALIVE_ANCHOR+LIVE_KEEPALIVE_OBSERVE,1)
    patched = patched.replace(AUTO_TICK_ANCHOR,AUTO_TICK+AUTO_TICK_ANCHOR,1)
    for old, _ in CALL_SITES:
        patched = patched.replace(old, old.replace('requests_util.response_to_request',
                                                    'handover_legacy_or_shim'))
    patched = patched.replace(ANCHOR, ANCHOR + SETUP + BOOT + AUTO_BOOT, 1)
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
