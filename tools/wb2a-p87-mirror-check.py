#!/usr/bin/env python3
"""Observe a P87/native-status hypothesis through the RUNNING VS1 splitter.

Default: inert plan. --execute: fixed MQTT READs only; never serial, service
control, P300, RAM, settings writes, heater triggers or HA discovery changes.
A supported comparison is evidence to investigate, not a production substitute.
"""
from __future__ import annotations

import argparse
import ast
from collections import Counter
import datetime as dt
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import ssl
import subprocess
import time
import uuid

VERSION = '1.0.0'
SETTINGS = Path('/opt/optolink/settings_ini.py')
ROOT = Path('/root/p300-trial-work/p87-results')
# Exact application commands, not free-form function/address parameters.
READS = {
    'device': ('r;0x00F8;2;raw;False', 0x00F8, 2),
    'software': ('r;0x778C;2;raw;False', 0x778C, 2),
    'native_type': ('r;0x7650;1;raw;False', 0x7650, 1),
    'p80': ('gfaread;0x4050;1;raw;False', 0x4050, 1),
    'p87': ('gfaread;0x4057;1;raw;False', 0x4057, 1),
    'native_status': ('r;0x55D3;11;raw;False', 0x55D3, 11),
}
ADDRESSES = frozenset(r[1] for r in READS.values())
INTERVAL = 5.0
MAX_BRACKET_SECONDS = 2.0
TIMEOUT = 8.0


class CheckError(RuntimeError):
    pass


def config(text: str) -> dict:
    """Read literal local settings without importing or executing their code."""
    keys = {'vs1protocol', 'port_vitoconnect', 'mqtt', 'mqtt_broker', 'mqtt_user',
            'mqtt_listen', 'mqtt_respond', 'mqtt_tls_enable', 'mqtt_tls_skip_verify',
            'mqtt_tls_ca_certs', 'mqtt_tls_certfile', 'mqtt_tls_keyfile',
            'data_hex_format', 'resp_addr_format', 'retcode_format'}
    tree = ast.parse(text)
    top = {id(n) for n in tree.body}
    values = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign, ast.NamedExpr)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            names = {n.id for target in targets for n in ast.walk(target)
                     if isinstance(n, ast.Name)} & keys
            if names:
                if id(node) not in top or not isinstance(node, ast.Assign) or any(
                        not isinstance(t, ast.Name) for t in targets):
                    raise CheckError('AMBIGUOUS_LOCAL_SETTINGS')
                try:
                    value = ast.literal_eval(node.value)
                except (TypeError, ValueError):
                    raise CheckError('NON_LITERAL_LOCAL_SETTINGS') from None
                for name in names:
                    values[name] = value
    if values.get('vs1protocol') is not True or values.get('port_vitoconnect', 'missing') is not None:
        raise CheckError('REQUIRES_ORIGINAL_SINGLE_PORT_VS1')
    if not values.get('mqtt_broker'):
        values['mqtt_broker'] = values.get('mqtt')
    broker = values.get('mqtt_broker')
    if not isinstance(broker, str) or ':' not in broker:
        raise CheckError('MQTT_BROKER_NOT_CONFIGURED')
    for key in ('mqtt_listen', 'mqtt_respond'):
        if not isinstance(values.get(key), str) or not values[key] or any(c in values[key] for c in '+#\x00'):
            raise CheckError('MQTT_TOPICS_NOT_EXACT')
    if values['mqtt_listen'] == values['mqtt_respond']:
        raise CheckError('MQTT_TOPICS_MUST_DIFFER')
    if values.get('resp_addr_format', 'x') != 'x' or values.get('retcode_format', 'd') != 'd':
        raise CheckError('UNREVIEWED_RESPONSE_FORMAT')
    if values.get('data_hex_format', '02x') not in ('02x', '02X'):
        raise CheckError('UNREVIEWED_HEX_FORMAT')
    if values.get('mqtt_tls_skip_verify', False):
        raise CheckError('INSECURE_TLS_NOT_ACCEPTED_BY_OBSERVER')
    return values


def command_address(text: str) -> int | None:
    fields = text.split(';')
    try:
        index = 2 if fields[0].lower() in ('req', 'request') else 1
        return int(fields[index], 0)
    except (IndexError, ValueError):
        return None


def response(raw: str, address: int, length: int) -> bytes:
    fields = raw.split(';')
    try:
        if len(fields) != 3 or int(fields[0], 10) != 1 or int(fields[1], 0) != address:
            raise ValueError
        if not re.fullmatch(r'[0-9a-fA-F]{' + str(length * 2) + '}', fields[2]):
            raise ValueError
        value = bytes.fromhex(fields[2])
    except ValueError:
        raise CheckError('INVALID_OR_FAILED_RESPONSE') from None
    if address in (0x4050, 0x4057) and value == b'\xff':
        raise CheckError('GFA_FF_IS_NOT_VALID_DATA')
    return value


class Receiver:
    """Strict pending read plus echoed-command check. Not a broker-level nonce.

Other clients must not query these addresses while this observer runs. A shared
response protocol without request IDs cannot prove sender attribution in every
possible race. Observed collisions abort rather than silently match by address.
"""
    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self.pending = None
        self.error = None
        self.retained_ignored = 0

    def begin(self, name: str) -> str:
        if name not in READS or self.pending is not None:
            raise CheckError('NOT_AN_ALLOWED_SINGLE_READ')
        cmd, addr, size = READS[name]
        self.pending = dict(name=name, command=cmd, address=addr, length=size,
                            sent=self.clock(), echo=False, value=None, received=None)
        return cmd

    def message(self, channel: str, payload: bytes, retained: bool = False) -> None:
        if retained:
            self.retained_ignored += 1
            return
        try:
            text = payload.decode('ascii')
        except UnicodeDecodeError:
            return  # Unrelated messages are neither recorded nor interpreted.
        if channel == 'command':
            address = command_address(text)
            if address not in ADDRESSES:
                return
            p = self.pending
            if p is None or text != p['command'] or p['echo']:
                self.error = 'CONCURRENT_TRACKED_COMMAND'
            else:
                p['echo'] = True
            return
        if channel != 'response':
            return
        fields = text.split(';')
        try:
            address = int(fields[1], 0)
        except (IndexError, ValueError):
            return
        if address not in ADDRESSES:
            return
        p = self.pending
        if p is None or address != p['address'] or not p['echo'] or p['value'] is not None:
            self.error = 'UNEXPECTED_OR_AMBIGUOUS_TRACKED_RESPONSE'
            return
        try:
            p['value'] = response(text, address, p['length'])
            p['received'] = self.clock()
        except CheckError as exc:
            self.error = str(exc)

    def finish(self) -> dict:
        if self.error:
            raise CheckError(self.error)
        p = self.pending
        if p is None or not p['echo'] or p['value'] is None:
            raise CheckError('READ_NOT_COMPLETE')
        self.pending = None
        return dict(name=p['name'], raw=p['value'].hex(), sent=p['sent'],
                    received=p['received'], latency_ms=(p['received']-p['sent'])*1000)


def bracket(before: dict, middle: dict, after: dict) -> dict:
    value = bytes.fromhex(middle['raw'])
    if len(value) != 11 or before['name'] != 'p87' or middle['name'] != 'native_status' or after['name'] != 'p87':
        raise CheckError('INVALID_BRACKET_INPUT')
    ordered = before['sent'] <= before['received'] <= middle['sent'] <= middle['received'] <= after['sent'] <= after['received']
    span = after['received'] - before['received']
    if not ordered or span < 0:
        raise CheckError('NON_MONOTONIC_BRACKET')
    if before['raw'] != after['raw']:
        verdict = 'TRANSITION_AMBIGUOUS'
    elif span > MAX_BRACKET_SECONDS:
        verdict = 'BRACKET_TOO_WIDE'
    elif value[7] != int(before['raw'], 16):
        verdict = 'STABLE_MISMATCH'
    else:
        verdict = 'STABLE_MATCH'
    return dict(verdict=verdict, p87_before=before['raw'], p87_after=after['raw'],
                native_b7=f'{value[7]:02x}', native_block=value.hex(),
                bracket_ms=span*1000, independent_acquisition_times_known=False,
                reads=[before, middle, after])


def summarize(rounds: list[dict]) -> dict:
    counts = Counter(r['verdict'] for r in rounds)
    states = sorted({r['p87_before'] for r in rounds if r['verdict'] == 'STABLE_MATCH'})
    if counts['STABLE_MISMATCH']:
        outcome = 'MISMATCH_OBSERVED_NEEDS_REVIEW'
    elif counts['STABLE_MATCH'] >= 10 and len(states) >= 3 and len(set(states) - {'00'}) >= 2:
        outcome = 'CANDIDATE_SUPPORTED_ON_SAMPLED_STATES'
    else:
        outcome = 'INCONCLUSIVE_STATE_COVERAGE'
    return dict(outcome=outcome, counts=dict(counts), matching_states=states,
                production_alias_verified=False, p300_freshness_verified=False,
                hidden_aba_transition_excluded=False)


class MQTT:
    def __init__(self, values: dict):
        import paho.mqtt.client as paho  # Lazy: never imported for plan/offline tests.
        self.receiver = Receiver()
        self.values = values
        self.subscribed = False
        self.stopping = False
        self.client = paho.Client(paho.CallbackAPIVersion.VERSION2,
                                  client_id='wb2a_p87_' + uuid.uuid4().hex,
                                  clean_session=True, protocol=paho.MQTTv311,
                                  reconnect_on_failure=False)
        self.client.connect_timeout = 4.0
        self.client.on_connect = self._connect
        self.client.on_subscribe = self._subscribe
        self.client.on_message = self._message
        self.client.on_disconnect = self._disconnect
        auth = values.get('mqtt_user')
        if auth and str(auth).lower() != 'none':
            try:
                user, password = str(auth).split(':', 1)
            except ValueError:
                raise CheckError('INVALID_LOCAL_MQTT_CREDENTIAL_FORMAT') from None
            self.client.username_pw_set(user, password)
        if values.get('mqtt_tls_enable', False):
            cert, key = values.get('mqtt_tls_certfile'), values.get('mqtt_tls_keyfile')
            if bool(cert) != bool(key):
                raise CheckError('INCOMPLETE_MTLS_CONFIGURATION')
            self.client.tls_set(ca_certs=values.get('mqtt_tls_ca_certs'),
                                certfile=cert, keyfile=key, cert_reqs=ssl.CERT_REQUIRED,
                                tls_version=ssl.PROTOCOL_TLS_CLIENT)
        host, port = values['mqtt_broker'].rsplit(':', 1)
        try:
            self.client.connect(host.strip('[]'), int(port), keepalive=30)
            self.wait(lambda: self.subscribed, 8.0)
            self.pump(.15)
        except BaseException:
            self.stopping = True
            self.client.disconnect()
            raise

    def _connect(self, client, userdata, flags, reason_code, properties):
        if reason_code.is_failure:
            self.receiver.error = 'MQTT_CONNECTION_REJECTED'
            return
        rc, self.mid = client.subscribe([(self.values['mqtt_listen'], 0), (self.values['mqtt_respond'], 0)])
        if rc != 0:
            self.receiver.error = 'MQTT_SUBSCRIBE_FAILED'

    def _subscribe(self, client, userdata, mid, codes, properties):
        if mid != self.mid or len(codes) != 2 or any(code.is_failure for code in codes):
            self.receiver.error = 'MQTT_SUBSCRIBE_NOT_GRANTED'
        else:
            self.subscribed = True

    def _message(self, client, userdata, msg):
        channel = 'command' if msg.topic == self.values['mqtt_listen'] else 'response'
        self.receiver.message(channel, msg.payload, msg.retain)

    def _disconnect(self, client, userdata, flags, reason_code, properties):
        if not self.stopping:
            self.receiver.error = 'MQTT_DISCONNECTED_NO_REPLAY'

    def tick(self):
        if self.client.loop(timeout=.05) != 0:
            raise CheckError('MQTT_LOOP_FAILED_NO_REPLAY')
        if self.receiver.error:
            raise CheckError(self.receiver.error)

    def wait(self, predicate, seconds):
        deadline = time.monotonic() + seconds
        while not predicate():
            if time.monotonic() >= deadline:
                raise CheckError('MQTT_READ_OR_SUBSCRIBE_TIMEOUT_NO_RETRY')
            self.tick()
        if self.receiver.error:
            raise CheckError(self.receiver.error)

    def pump(self, seconds):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            self.tick()

    def read(self, name: str) -> dict:
        self.pump(.05)
        cmd = self.receiver.begin(name)
        info = self.client.publish(self.values['mqtt_listen'], cmd, qos=0, retain=False)
        if info.rc != 0:
            raise CheckError('MQTT_READ_PUBLISH_FAILED')
        self.wait(lambda: self.receiver.pending['value'] is not None, TIMEOUT)
        self.pump(.05)  # Detect an immediate duplicate before retiring the read.
        return self.receiver.finish()

    def close(self):
        self.stopping = True
        self.client.disconnect()
        self.client.loop(timeout=.05)


def require(row: dict, expected: str) -> None:
    if row['raw'] != expected:
        raise CheckError('IDENTITY_MISMATCH_' + row['name'])


def preflight() -> dict:
    if os.geteuid() != 0:
        raise CheckError('RUN_IN_OPTOLINK_LXC_AS_ROOT')
    values = config(SETTINGS.read_text())
    cmd = ['systemctl', 'show', 'optolink-splitter.service', '-p', 'WorkingDirectory',
           '-p', 'ActiveState', '-p', 'SubState']
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=5, check=True)
    state = dict(line.split('=', 1) for line in result.stdout.splitlines() if '=' in line)
    if state != {'WorkingDirectory': '/opt/optolink', 'ActiveState': 'active', 'SubState': 'running'}:
        raise CheckError('ORIGINAL_SPLITTER_NOT_RUNNING')
    return values


def execute(seconds: int) -> int:
    values = preflight()
    lock = os.open('/run/lock/optolink-p87-mirror.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    if ROOT.is_symlink():
        raise CheckError('RESULT_ROOT_MUST_NOT_BE_SYMLINK')
    ROOT.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(ROOT, 0o700)
    stamp = dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    session = ROOT / ('run-' + stamp + '-' + str(os.getpid()))
    session.mkdir(mode=0o700)
    print('SESSION=' + str(session), flush=True)
    report = dict(schema_version=1, version=VERSION,
                  script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  transport='existing VS1 splitter via MQTT', rounds=[], errors=[],
                  protocol_switched=False, services_stopped=False, device_writes=False)
    client = None
    def interrupted(signum, frame):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, interrupted)
    signal.signal(signal.SIGHUP, interrupted)
    try:
        client = MQTT(values)
        opening = {}
        for name, expected in (('device', '20c2'), ('software', '0103'), ('p80', '20')):
            opening[name] = client.read(name)
            require(opening[name], expected)
        opening['native_type'] = client.read('native_type')
        report['opening'] = opening
        end = time.monotonic() + seconds
        with (session / 'pairs.jsonl').open('x', encoding='utf-8') as out:
            # At least 5 s between round starts, at most 4 reads per round.
            for index in range((seconds + 4) // 5):
                if time.monotonic() >= end:
                    break
                start = time.monotonic()
                require(client.read('p80'), '20')
                row = bracket(client.read('p87'), client.read('native_status'), client.read('p87'))
                row['index'] = index + 1
                row['utc'] = dt.datetime.now(dt.timezone.utc).isoformat()
                report['rounds'].append(row)
                out.write(json.dumps(row, sort_keys=True) + '\n')
                out.flush()
                print(json.dumps({k: row[k] for k in ('index', 'verdict', 'p87_before', 'native_b7', 'p87_after', 'bracket_ms')}), flush=True)
                client.pump(max(0.0, min(start + INTERVAL, end) - time.monotonic()))
        report['closing_p80'] = client.read('p80')
        require(report['closing_p80'], '20')
    except KeyboardInterrupt:
        report['errors'].append('STOPPED_BY_USER_NO_RESTORE_NEEDED')
    except (CheckError, OSError, ValueError) as exc:
        # Do not serialize broker credentials, OS paths or unreviewed payloads.
        report['errors'].append(str(exc) if isinstance(exc, CheckError) else type(exc).__name__)
    finally:
        if client is not None:
            try:
                report['retained_responses_ignored'] = client.receiver.retained_ignored
                client.close()
            except Exception:
                report['errors'].append('MQTT_CLOSE_FAILED')
        report['comparison'] = summarize(report['rounds'])
        if report['errors']:
            report['comparison']['outcome'] = 'INCOMPLETE_OR_FAILED'
        report['response_attribution_limit'] = 'No request IDs; no other clients may query these addresses. Observed collisions abort.'
        with (session / 'summary.json').open('x', encoding='utf-8') as out:
            json.dump(report, out, indent=2, sort_keys=True)
            out.write('\n')
        os.close(lock)
    print('RESULT=' + report['comparison']['outcome'], flush=True)
    print(json.dumps(report['comparison'], sort_keys=True), flush=True)
    for error in report['errors']:
        print('ERROR=' + error, flush=True)
    print('No protocol/service/settings change. Verify ordinary HA/MQTT freshness separately.')
    return int(bool(report['errors']))


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--execute', action='store_true')
    p.add_argument('--seconds', type=int, default=300)
    args = p.parse_args()
    if not 30 <= args.seconds <= 900:
        p.error('--seconds must be between 30 and 900')
    os.umask(0o077)
    if not args.execute:
        print('PLAN ONLY: P87 -> virtual 55D3/11 -> P87, guarded by GFA P80=20.')
        print('MQTT read-only, existing VS1 owner; 5-second rounds, no service stop, no P300/RAM/write.')
        print('Static 00 matches are INCONCLUSIVE; no automatic HA alias or production approval.')
        return 0
    return execute(args.seconds)


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (CheckError, OSError, ValueError, subprocess.SubprocessError) as exc:
        print('REFUSED_OR_FAILED=' + (str(exc) if isinstance(exc, CheckError) else type(exc).__name__))
        raise SystemExit(1)
