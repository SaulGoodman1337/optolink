#!/usr/bin/env python3
"""Offline regression suite. Never opens a serial device or contacts MQTT.

Core/staging tests use only the standard library. Integration tests additionally
use the pinned upstream with pyserial/paho-mqtt installed (required by CI).
"""
from __future__ import annotations
import argparse
import ast
from collections import deque
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import optolink_p300 as p


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


stage_module = load('p300_stager', HERE / 'optolink-stage-p300.py')


def response(fc, addr, data, *, msg=1, declared=None):
    declared = len(data) if declared is None else declared
    body = bytes((5 + len(data), msg, fc, addr >> 8, addr & 255, declared)) + data
    return b'\x06\x41' + body + bytes((sum(body) & 255,))


class FakeSerial:
    """Byte-fragmenting serial peer with explicit faults, not a boiler simulator."""
    timeout = 0

    def __init__(self):
        self.incoming = bytearray()
        self.sent = []
        self.memory = {(1, 0x00F8): b'\x20\xc2', (1, 0x778C): b'\x01\x03',
                       (0xC9, 0x4050): b'\x20', (0xC9, 0x4006): b'\x64',
                       (0xC9, 0x4009): b'\x80', (0xC9, 0x4057): b'\x62'}
        self.gfa_values = deque()
        self.fault = None
        self.fragment = 1
        self.events = []

    def reset_input_buffer(self):
        self.incoming.clear()

    def read(self, count):
        count = min(count, self.fragment, len(self.incoming))
        out = bytes(self.incoming[:count])
        del self.incoming[:count]
        return out

    def write(self, data):
        data = bytes(data)
        self.sent.append(data)
        if data == b'\x04':
            self.incoming.extend(b'\x05')
        elif data == b'\x16\x00\x00':
            self.incoming.extend(b'\x06')
        elif data == b'\x06':
            self.events.append('host_ack')
        elif data[:1] == b'\x41':
            assert data[1] + 3 == len(data)
            assert sum(data[1:-1]) & 255 == data[-1]
            fc, addr, length = data[3], int.from_bytes(data[4:6], 'big'), data[6]
            payload = data[7:-1]
            self.events.append((fc, addr, length, payload))
            fault, self.fault = self.fault, None
            if fc in (2, 4):
                self.memory[(1 if fc == 2 else 3, addr)] = payload
                reply = response(fc, addr, b'', declared=length)
            else:
                result = self.memory.get((fc, addr), bytes(length))
                if fc == 0xC9 and addr != 0x4050 and self.gfa_values:
                    result = self.gfa_values.popleft()
                reply = response(fc, addr, result[:length].ljust(length, b'\0'))
            if fault == 'crc':
                reply = reply[:-1] + bytes((reply[-1] ^ 1,))
            elif fault == 'address':
                reply = response(fc, addr ^ 1, bytes(length))
            elif fault == 'function':
                reply = response(fc ^ 1, addr, bytes(length))
            elif fault == 'short':
                reply = response(fc, addr, bytes(max(0, length - 1)))
            elif fault == 'error':
                reply = response(fc, addr, b'\x05', msg=3)
            elif fault == 'message':
                reply = response(fc, addr, bytes(length), msg=2)
            elif fault == 'length':
                reply = b'\x06\x41\xff'
            elif fault == 'ack':
                reply = b'\x06\x06' + reply
            elif fault == 'nack':
                reply = b'\x15'
            elif fault == 'lost':
                reply = b''  # May already have applied the write above.
            elif fault == 'writecount':
                reply = response(fc, addr, b'', declared=length + 1)
            elif fault == 'shortwrite':
                return len(data) - 1
            self.incoming.extend(reply)
        else:
            raise AssertionError('unexpected outgoing bytes ' + data.hex())
        return len(data)

    @property
    def frames(self):
        return [x for x in self.sent if x[:1] == b'\x41']


class TransportTests(unittest.TestCase):
    def setUp(self):
        self.serial = FakeSerial()
        self.logs = []
        self.client = p.P300(self.serial, timeout=.01, gap=0, audit=self.logs.append)
        self.assertTrue(self.client.initialize())

    def test_01_golden_frame(self):
        self.assertEqual(p.request_frame(1, 0xF8, 2), bytes.fromhex('4105000100f80200'))
        self.assertEqual(p.request_frame(0xC9, 0x4050, 1), bytes.fromhex('410500c94050015f'))

    def test_02_identity_and_gfa_gate(self):
        self.assertEqual([(f[3], f[4:6].hex()) for f in self.serial.frames],
                         [(1, '00f8'), (1, '778c'), (0xC9, '4050')])
        self.assertTrue(self.client.ready)
        self.assertEqual(self.serial.sent.count(b'\x06'), 3)

    def test_03_fragmented_read(self):
        result = bytes(range(29))
        self.serial.memory[(1, 0xA132)] = result
        self.assertEqual(self.client.request(1, 0xA132, 29), (1, 0xA132, result))

    def test_04_response_validation(self):
        for fault, code in [('crc', p.CHECKSUM), ('address', p.LENGTH),
                            ('function', p.LENGTH), ('short', p.LENGTH),
                            ('message', p.LENGTH), ('length', p.LENGTH),
                            ('nack', 0x15), ('shortwrite', p.TIMEOUT), ('lost', p.TIMEOUT)]:
            with self.subTest(fault=fault):
                self.assertTrue(self.client.initialize())
                self.serial.fault = fault
                self.assertEqual(self.client.request(1, 0x0810, 2)[0], code)
                self.assertFalse(self.client.ready)

    def test_05_error_payload_preserved(self):
        self.serial.fault = 'error'
        self.assertEqual(self.client.request(1, 0x0810, 2), (3, 0x0810, b'\x05'))
        self.assertTrue(self.client.ready)

    def test_06_repeated_ack(self):
        self.serial.fault = 'ack'
        self.assertEqual(self.client.request(1, 0xF8, 2)[0], 1)

    def test_07_wrong_controller(self):
        self.serial.memory[(1, 0xF8)] = b'\x20\xcb'
        before = len(self.serial.frames)
        self.assertFalse(self.client.initialize())
        self.assertEqual(len(self.serial.frames) - before, 1)

    def test_08_wrong_software(self):
        self.serial.memory[(1, 0x778C)] = b'\x01\x04'
        self.assertFalse(self.client.initialize())

    def test_09_wrong_p80(self):
        self.serial.memory[(0xC9, 0x4050)] = b'\x11'
        self.assertFalse(self.client.initialize())
        self.assertFalse(self.client.ready)

    def test_10_lost_capability_gate(self):
        original = self.serial.write
        def missing_c9(data):
            if data[:4] == b'\x41\x05\x00\xc9':
                self.serial.fault = 'error'
            return original(data)
        self.serial.write = missing_c9
        self.assertFalse(self.client.initialize())

    def test_10a_init_error_reports_exact_stage(self):
        original = self.serial.write
        for fc, address, stage in (
                (1, 0x00F8, "virtual_device_id"),
                (1, 0x778C, "virtual_software"),
                (0xC9, 0x4050, "gfa_p80")):
            with self.subTest(stage=stage):
                self.logs.clear()
                def reject_at_step(data):
                    if (data[:1] == b'\x41' and len(data) >= 7
                            and data[3] == fc and int.from_bytes(data[4:6], "big") == address):
                        self.serial.fault = "error"
                    return original(data)
                self.serial.write = reject_at_step
                self.assertFalse(self.client.initialize())
                self.assertTrue(any(
                    "P300_INIT_STAGE_FAILED stage=" + stage in line
                    and "code=03 payload=05" in line for line in self.logs), self.logs)
        self.serial.write = original

    def test_11_gfa_retry_and_quarantine(self):
        with patch.object(p.time, 'sleep', lambda n: None):
            self.serial.gfa_values.extend([b'\xff', b'\x64'])
            before = len(self.serial.frames)
            self.assertEqual(self.client.request(0xC9, 0x4006, 1)[2], b'\x64')
            self.assertEqual(len(self.serial.frames) - before, 2)
            self.serial.gfa_values.extend([b'\xff', b'\xff'])
            before = len(self.serial.frames)
            code, _, data = self.client.request(0xC9, 0x4006, 1)
            self.assertEqual(code, p.TIMEOUT)
            self.assertEqual(data, b'')
            self.assertEqual(len(self.serial.frames) - before, 2)

    def test_12_gfa_full_function_byte(self):
        self.assertEqual(self.client.request(0xC9, 0x4006, 1)[0], 1)
        self.assertEqual(self.serial.frames[-1][3], 0xC9)
        self.assertNotIn(0x6B, [f[3] for f in self.serial.frames])

    def test_13_default_write_denied_without_io(self):
        before = len(self.serial.sent)
        self.assertEqual(self.client.request(2, 0x2306, 1, b'\x15')[0], p.DENIED)
        self.assertEqual(len(self.serial.sent), before)

    def test_14_virtual_write_sizes_and_readback(self):
        self.client.virtual_write = True
        for addr, data in [(0x2306, b'\x15'), (0x27D4, b'\x08\0'),
                           (0x088E, bytes.fromhex('2026100703180000')),
                           (0x2000, bytes.fromhex('303fffffffffffff'))]:
            with self.subTest(addr=addr):
                self.assertEqual(self.client.request(2, addr, len(data), data)[0], 1)
                self.assertEqual(self.client.request(1, addr, len(data))[2], data)

    def test_15_no_write_replay_after_lost_response(self):
        self.client.virtual_write = True
        self.serial.fault = 'lost'
        self.assertEqual(self.client.request(2, 0x2306, 1, b'\x16')[0], p.TIMEOUT)
        writes = [f for f in self.serial.frames if f[3] == 2]
        self.assertEqual(len(writes), 1)
        self.assertEqual(self.client.request(1, 0x2306, 1)[2], b'\x16')
        self.assertEqual(len([f for f in self.serial.frames if f[3] == 2]), 1)

    def test_16_unsupported_and_sfr_blocked(self):
        before = len(self.serial.sent)
        for args in [(4, 0x20A5, 1, b'\x64'), (6, 0x1000, 1, b'\x00'),
                     (0xCA, 0x4006, 1, b'\0'), (0x6B, 0x4050, 1),
                     (1, 0xF8, 56), (1, 0x10000, 1),
                     (0xC9, 0x4051, 1), (3, 0x0400, 32)]:
            self.assertEqual(self.client.request(*args)[0], p.DENIED)
        self.client.ram_read = True
        for address, length in [(0x3FF, 1), (0x53FF, 2), (0x5400, 1), (0x400, 33)]:
            self.assertEqual(self.client.request(3, address, length)[0], p.DENIED)
        self.assertEqual(len(self.serial.sent), before)

    def test_17_explicit_ram_read(self):
        self.client.ram_read = True
        for addr, size in [(0x400, 32), (0x53FF, 1)]:
            self.assertEqual(self.client.request(3, addr, size)[0], 1)

    def test_18_ram_write_default_closed(self):
        before = len(self.serial.sent)
        with self.assertRaises(PermissionError):
            self.client.compare_write_ram(0x2000, b'\x01', b'\x02')
        self.assertEqual(before, len(self.serial.sent))

    def test_19_exact_ram_rule_and_compare(self):
        self.client.write_rules = (p.RamWriteRule(0x2000, frozenset([b'\x01', b'\x02'])),)
        self.serial.memory[(3, 0x2000)] = b'\x01'
        self.assertEqual(self.client.compare_write_ram(0x2000, b'\x01', b'\x02'), b'\x02')
        self.assertEqual([f[3] for f in self.serial.frames[-3:]], [3, 4, 3])
        with self.assertRaises(p.TransportError):
            self.client.compare_write_ram(0x2000, b'\x01', b'\x02')
        self.assertEqual(len([f for f in self.serial.frames if f[3] == 4]), 1)
        with self.assertRaises(PermissionError):
            self.client.compare_write_ram(0x2000, b'\x02', b'\xff')

    def test_20_bad_write_reply_not_success(self):
        self.client.virtual_write = True
        self.serial.fault = 'writecount'
        self.assertEqual(self.client.request(2, 0x2306, 1, b'\x15')[0], p.LENGTH)

    def test_21_idle_revalidates_identity(self):
        self.client.last_io = 0
        self.serial.memory[(1, 0xF8)] = b'\x20\xcb'
        self.assertEqual(self.client.request(1, 0x0810, 2)[0], p.DENIED)
        self.assertFalse(self.client.ready)

    def test_22_nonblocking_and_geometry(self):
        self.serial.timeout = 1
        with self.assertRaises(ValueError):
            p.P300(self.serial)
        for args in [(1, -1, 1), (256, 1, 1), (1, 1, 0), (2, 1, 2, b'1')]:
            with self.assertRaises(ValueError):
                p.request_frame(*args)


UPSTREAM = os.getenv('P300_UPSTREAM_ROOT')


@unittest.skipUnless(UPSTREAM, 'set P300_UPSTREAM_ROOT to the pinned fixture')
class StagingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.path = Path(cls.temp.name)
        cls.candidate = cls.path / 'candidate'
        cls.inventory = stage_module.stage(Path(UPSTREAM), cls.candidate)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_23_profile_byte_identity_and_inventory(self):
        self.assertEqual((self.candidate / 'homeassistant_poll_list.py').read_bytes(),
                         stage_module.PROFILE.read_bytes())
        self.assertEqual(self.inventory['declared_entities'], 362)
        self.assertEqual(self.inventory['poll_entries'], 222)
        self.assertEqual(self.inventory['max_poll_length'], 29)
        self.assertEqual(len(self.inventory['gfa_entries']), 4)
        self.assertFalse(self.inventory['live_verified'])

    def test_24_defaults_are_isolated_readonly(self):
        values = {}
        exec((self.candidate / 'settings_ini.py').read_text(), values)
        for key in ['port_optolink', 'mqtt_broker', 'port_vitoconnect', 'tcpip_port']:
            self.assertIsNone(values[key])
        for key in ['vs1protocol', 'p300_virtual_write', 'p300_ram_read']:
            self.assertIs(values[key], False)
        self.assertEqual((self.candidate / 'settings_ini.py').stat().st_mode & 0o777, 0o600)

    def test_25_existing_output_refused(self):
        with self.assertRaises(ValueError):
            stage_module.stage(Path(UPSTREAM), self.candidate)

    def test_26_bad_upstream_hash_refused(self):
        bad = self.path / 'bad'
        shutil.copytree(UPSTREAM, bad)
        with (bad / 'optolinkvs2.py').open('a') as handle:
            handle.write('\n# unknown modification\n')
        with self.assertRaises(ValueError):
            stage_module.stage(bad, self.path / 'bad-output')

    def test_27_existing_patch_selftests(self):
        for name in ['optolink-apply-vs1-gfa-readonly-patch.py',
                     'optolink-apply-phased-poll-scheduler-patch.py',
                     'optolink-clock-sync.py', 'optolink-service-programs.py']:
            with self.subTest(name=name):
                run = subprocess.run([sys.executable, str(HERE / name), '--self-test'],
                                     capture_output=True, text=True)
                self.assertEqual(run.returncode, 0, run.stdout + run.stderr)

    def test_28_real_adapter_dispatch_and_discovery_parity(self):
        # CI installs the real dependencies; no device or broker is used.
        if importlib.util.find_spec('serial') is None or importlib.util.find_spec('paho') is None:
            if os.getenv('GITHUB_ACTIONS') == 'true':
                self.fail('CI must install pyserial and paho-mqtt')
            self.skipTest('real runtime dependencies absent locally; mandatory in CI')
        code = r'''
import ast, importlib.util, json, os, sys
from pathlib import Path
candidate, tests = sys.argv[1:]
sys.path.insert(0, candidate)
sys.path.insert(1, str(Path(tests).parent))
import settings_ini
settings_ini.p300_virtual_write = True
settings_ini.p300_ram_read = True
spec = importlib.util.spec_from_file_location('p300_tests_fixture', tests)
m = importlib.util.module_from_spec(spec); sys.modules[spec.name] = m; spec.loader.exec_module(m)
import vs12_adapter as a
import requests_util as r
import homeassistant_publish as h
from c_settings_adapter import settings
s = m.FakeSerial()
assert a.init_protocol(s)
a._p300_client.gap = 0
profile = ast.literal_eval(next(n.value for n in ast.parse(Path(candidate, 'homeassistant_poll_list.py').read_text()).body if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'poll_list' for t in n.targets)))
items = []
for domain in profile['domains']:
    for block in [domain] + domain.get('units', []):
        items += block.get('poll', [])
# Meaningful BCD and schedule bytes prevent codec errors unrelated to transport.
s.memory[(1, 0x088E)] = bytes.fromhex('2026100703180000')
for item in items:
    if item[4] == 'schedvdens': s.memory[(1, item[2])] = bytes.fromhex('303fffffffffffff')
    if item[4] in ('vdatetime', 'vcaldatetime'): s.memory[(1, item[2])] = bytes.fromhex('2026100703180000')[:item[3]]
for item in items:
    result = r.response_to_request(tuple(item[1:]), s)
    assert result[0] == 1, (item, result)
# Unchanged decoding path; compare P300 with the same bytes through the VS1 branch.
results = [r.response_to_request(tuple(i[1:]), s)[2:] for i in items]
a.VS2 = False
old_read, old_gfa = a.read_datapoint_ext, a.read_gfa_ext
a.read_datapoint_ext = lambda addr, size, ser: (1, addr, bytearray(s.memory.get((1, addr), bytes(size))[:size].ljust(size, b'\0')))
a.read_gfa_ext = lambda addr, size, ser: (1, addr, bytearray(s.memory[(0xC9, addr)]))
legacy_results = [r.response_to_request(tuple(i[1:]), s)[2:] for i in items]
assert legacy_results == results
# Compare actual discovery generator output under only a transport flag change.
# No MQTT network operations; dry-run uses the unchanged complete profile.
a.VS2 = True; a.read_datapoint_ext, a.read_gfa_ext = old_read, old_gfa
for command, expected in [('wraw;0x088e;2026100703180000', bytes.fromhex('2026100703180000')),
                          ('writeraw;0x2000;303fffffffffffff', bytes.fromhex('303fffffffffffff'))]:
    assert r.response_to_request(command, s)[0] == 1
    address = int(command.split(';')[1], 0)
    assert a.read_datapoint_ext(address, 8, s)[2] == expected
assert r.response_to_request('ramread;0x0400;32', s)[0] == 1
for command in ['raw;4105000100f80200', '4105000100f80200', 'request;4;0x2000;1;01;0', 'ramread;x;2']:
    before = len(s.sent)
    assert r.response_to_request(command, s)[0] == 175
    assert before == len(s.sent)
print('ADAPTER_PARITY_POLLS=' + str(len(items)))
'''
        run = subprocess.run([sys.executable, '-c', code, str(self.candidate), str(Path(__file__).resolve())],
                             cwd=self.candidate, capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        self.assertIn('ADAPTER_PARITY_POLLS=222', run.stdout)
        settings = self.candidate / 'settings_ini.py'
        original = settings.read_text()
        outputs = []
        for vs1 in [False, True]:
            settings.write_text(original + '\nvs1protocol = ' + str(vs1) + '\n')
            # Python bytecode timestamp caching must not mask the configuration change.
            for cache in (self.candidate / '__pycache__').glob('settings_ini*.pyc'):
                cache.unlink()
            result = subprocess.run([sys.executable, '-c', "import sys; import homeassistant_publish as h; from c_settings_adapter import settings; settings.mqtt_topic='openv'; settings.mqtt_listen='openv/cmnd'; h.time.sleep=lambda n:None; sys.argv=['homeassistant_publish.py','--console']; h.publish_ha_discovery()"],
                                    cwd=self.candidate, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            outputs.append(result.stdout)
        settings.write_text(original)
        self.assertEqual(outputs[0], outputs[1], 'HA discovery changed with transport flag')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    suite = unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    report = {'tests': result.testsRun, 'failures': len(result.failures),
              'errors': len(result.errors), 'skipped': len(result.skipped),
              'offline_only': True, 'live_verified': False,
              'backend_sha256': hashlib.sha256((HERE / 'optolink_p300.py').read_bytes()).hexdigest()}
    print(json.dumps(report, sort_keys=True))
    if args.report:
        args.report.write_text(json.dumps(report, indent=2) + '\n')
    raise SystemExit(not result.wasSuccessful())


if __name__ == '__main__':
    main()
