#!/usr/bin/env python3
"""WB2A P80-only diagnostic. No coding, setpoint, process or GFA writes.

Default: print the plan; --execute deliberately pauses the running splitter.
Requires Linux, systemd, root and pyserial 3.5 for live operation.
--self-test needs only the Python standard library and never opens a port.

Protocol provenance: research/vitosoft/private-archive-2026-09-23-analysis.md.
Only P300 Virtual_READ 00F8/2 and VS1 GFA_READ 4050/1 are implemented.
Interface-control/acknowledgement bytes are transmitted, not parameter writes.
SIGINT/SIGTERM/SIGHUP enter cleanup. SIGKILL, power loss, a disconnected USB
adapter or a failed systemd restart cannot be repaired by a finally block.
"""
from __future__ import annotations

import argparse
import ast
import datetime as dt
import fcntl
import os
from pathlib import Path
import signal
import stat
import subprocess
import sys
import termios
import time

VERSION = '1.0.0'
SPLITTER = 'optolink-splitter.service'
PARTY = 'optolink-party-emulator.service'
SETTINGS = Path('/opt/optolink/settings_ini.py')
IDENT_REQUEST = bytes.fromhex('41 05 00 01 00 f8 02 00')
P80_REQUEST = bytes.fromhex('01 6b 40 50 01')
ALLOWED_TX = frozenset((b'\x04', b'\x16\x00\x00', b'\x06',
                        IDENT_REQUEST, P80_REQUEST))
VARIANTS = {0x20: 'GFA', 0x21: 'SCOT', 0x22: 'DOVER', 0x23: 'CES'}
ABORT_SIGNALS = (signal.SIGINT, signal.SIGTERM, signal.SIGHUP)


class ProbeError(RuntimeError):
    pass


class Log:
    def __init__(self, path: Path):
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        self.file = os.fdopen(fd, 'w', encoding='utf-8', buffering=1)
        self.path = path

    def __call__(self, message: str):
        text = dt.datetime.now().astimezone().isoformat(timespec='milliseconds') + ' ' + message
        try:
            self.file.write(text + '\n')
        except OSError:
            pass
        try:
            print(text, flush=True)
        except (BrokenPipeError, OSError):
            pass  # Losing stdout must not interrupt protocol/service cleanup.

    def close(self):
        self.file.close()


def read_settings(path: Path) -> str:
    """Parse only literal assignments; do not import or execute settings_ini.py."""
    names = {'port_optolink', 'port_vitoconnect', 'vs1protocol'}
    values = {}
    tree = ast.parse(path.read_text(encoding='utf-8-sig'), filename=str(path))
    for node in ast.walk(tree):
        targets = []
        if isinstance(node, ast.Assign):
            targets = node.targets
        elif isinstance(node, (ast.AnnAssign, ast.AugAssign)):
            targets = [node.target]
        if any(isinstance(t, ast.Name) and t.id in names for t in targets):
            if node not in tree.body or not isinstance(node, ast.Assign):
                raise ProbeError('Conditional/annotated/augmented port settings are unsupported.')
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id in names:
                if target.id in values:
                    raise ProbeError('Ambiguous duplicate setting: ' + target.id)
                try:
                    values[target.id] = ast.literal_eval(node.value)
                except (ValueError, TypeError) as exc:
                    raise ProbeError('Setting is not a literal: ' + target.id) from exc
    if values.get('vs1protocol') is not False:
        raise ProbeError('Require explicit vs1protocol = False; settings are never modified.')
    if 'port_vitoconnect' not in values or values['port_vitoconnect'] is not None:
        raise ProbeError('This first probe requires port_vitoconnect = None.')
    port = values.get('port_optolink')
    if not isinstance(port, str) or not port.startswith('/dev/'):
        raise ProbeError('Require a literal local /dev/ port_optolink path.')
    return port


def decode_ident_frame(frame: bytes) -> bytes:
    if len(frame) < 8 or frame[0] != 0x41 or len(frame) != frame[1] + 3:
        raise ProbeError('P300 frame boundary/length mismatch: ' + frame.hex(' '))
    if sum(frame[1:-1]) & 255 != frame[-1]:
        raise ProbeError('P300 checksum mismatch: ' + frame.hex(' '))
    if frame[2] != 1 or (frame[3] & 0x1f) != 1:
        raise ProbeError('P300 non-success message/function: ' + frame.hex(' '))
    if frame[4:7] != b'\x00\xf8\x02' or len(frame[7:-1]) != 2:
        raise ProbeError('P300 response is not Virtual_READ 00F8/2: ' + frame.hex(' '))
    return frame[7:-1]


class Wire:
    def __init__(self, serial_port, log, clock=time.monotonic):
        self.port, self.log, self.clock = serial_port, log, clock
        self.touched = False

    def send(self, data: bytes):
        if data not in ALLOWED_TX:
            raise ProbeError('TX blocked by fixed read-only allowlist.')
        self.log('TX ' + data.hex(' '))
        self.touched = True
        if self.port.write(data) != len(data):
            raise ProbeError('Partial serial write; no automatic retransmission.')

    def exact(self, count: int, timeout: float = 2.0) -> bytes:
        until = self.clock() + timeout
        result = bytearray()
        while len(result) < count and self.clock() < until:
            result.extend(self.port.read(count - len(result)))
        if result:
            self.log('RX ' + result.hex(' '))
        if len(result) != count:
            raise ProbeError(f'RX timeout: expected {count} byte(s), got {len(result)}.')
        return bytes(result)

    def control(self, expected: int, timeout: float = 5.0):
        until = self.clock() + timeout
        while self.clock() < until:
            data = self.port.read(1)
            if not data:
                continue
            self.log('RX control ' + data.hex(' '))
            if data == bytes([expected]):
                return
            # Vitosoft's interface detection tolerates ACK/NACK before ENQ.
            if expected == 5 and data in (b'\x06', b'\x15'):
                continue
            # A periodic ENQ can already be queued when VS2 initialization starts.
            if expected == 6 and data == b'\x05':
                continue
            raise ProbeError(f'Unexpected control byte {data.hex()}, expected {expected:02x}.')
        raise ProbeError(f'Timeout waiting for control {expected:02x}.')

    def discard_stale(self):
        size = self.port.in_waiting
        if size > 4096:
            raise ProbeError('Excessive queued serial traffic; aborting.')
        if size:
            self.log('RX stale/discard ' + self.port.read(size).hex(' '))

    def p300_ident(self) -> bytes:
        self.discard_stale()
        self.send(b'\x04')
        self.control(5)
        self.send(b'\x16\x00\x00')
        self.control(6)
        self.send(IDENT_REQUEST)
        if self.exact(1) != b'\x06':
            raise ProbeError('P300 request was not acknowledged.')
        header = self.exact(2)
        if header[0] != 0x41 or not 5 <= header[1] <= 64:
            raise ProbeError('Invalid P300 response header: ' + header.hex(' '))
        frame = header + self.exact(header[1] + 1)
        ident = decode_ident_frame(frame)
        self.send(b'\x06')
        self.log('P300 identity = ' + ident.hex())
        return ident

    def p80(self) -> int:
        self.discard_stale()
        self.send(b'\x04')
        self.control(5)  # Interface detection after leaving VS2.
        self.log('Waiting for fresh VS1 synchronization ENQ.')
        self.control(5)  # Fresh ENQ, as in VS1::createVS1Connection.
        self.send(P80_REQUEST)  # STX + GFA_READ, sent together to avoid a scheduling gap.
        value = self.exact(1)[0]
        # Reject trailing frames/echoes rather than taking their first byte as P80.
        tail = self.port.read(1)
        if tail:
            self.log('RX unexpected trailing ' + tail.hex(' '))
            raise ProbeError('P80 response has unexpected trailing data.')
        if value not in VARIANTS:
            raise ProbeError(f'Unconfirmed P80 0x{value:02x}; not one of the four source-defined variants.')
        self.log(f'P80 sample = 0x{value:02x} ({VARIANTS[value]})')
        return value


class Services:
    @staticmethod
    def command(*args: str) -> str:
        try:
            proc = subprocess.run(['systemctl', '--no-pager', '--no-ask-password', *args],
                                  capture_output=True, text=True, timeout=25, check=False)
        except subprocess.TimeoutExpired as exc:
            raise ProbeError('systemctl timeout: ' + ' '.join(args)) from exc
        if proc.returncode:
            raise ProbeError('systemctl failed: ' + ' '.join(args) + ': ' + proc.stderr.strip())
        return proc.stdout

    def state(self, unit: str) -> dict:
        output = self.command('show', unit, '-p', 'LoadState', '-p', 'ActiveState', '-p', 'SubState')
        return dict(line.split('=', 1) for line in output.splitlines() if '=' in line)

    def stop(self, unit: str):
        self.command('stop', unit)
        state = self.state(unit)
        if state.get('ActiveState') != 'inactive':
            raise ProbeError('Service did not become inactive: ' + unit)

    def start(self, unit: str):
        self.command('start', unit)
        # Detect an immediate crash; this is not a Home Assistant/MQTT health check.
        time.sleep(2)
        state = self.state(unit)
        if state.get('ActiveState') != 'active' or state.get('SubState') != 'running':
            raise ProbeError('Service did not stay running: ' + unit)


def check_port_owners(port: str):
    """Check existing file descriptors, including opens made without flock."""
    device = os.stat(port)
    if not stat.S_ISCHR(device.st_mode):
        raise ProbeError('Serial path is not a character device: ' + port)
    owners = []
    for process in Path('/proc').iterdir():
        if not process.name.isdigit() or int(process.name) == os.getpid():
            continue
        try:
            descriptors = list((process / 'fd').iterdir())
        except FileNotFoundError:
            continue
        except PermissionError as exc:
            raise ProbeError('Cannot inspect process descriptors: ' + process.name) from exc
        for descriptor in descriptors:
            try:
                info = descriptor.stat()
            except FileNotFoundError:
                continue
            except PermissionError as exc:
                raise ProbeError('Cannot inspect descriptor: ' + str(descriptor)) from exc
            if stat.S_ISCHR(info.st_mode) and info.st_rdev == device.st_rdev:
                owners.append(process.name)
                break
    if owners:
        raise ProbeError('Serial port still open by PID(s): ' + ', '.join(owners))


def open_port(port: str, serial_module):
    check_port_owners(port)
    connection = serial_module.Serial(port=port, baudrate=4800, bytesize=8, parity='E',
                                      stopbits=2, timeout=0.05, write_timeout=2,
                                      xonxoff=False, rtscts=False, dsrdtr=False, exclusive=True)
    try:
        fcntl.ioctl(connection.fileno(), termios.TIOCEXCL)
        check_port_owners(port)  # Excludes our PID; closes the check/open race for existing owners.
    except BaseException:
        connection.close()
        raise
    return connection


def run_guarded(services, opener, log, wire_factory=Wire) -> int:
    """Dependency-injected orchestration, also exercised by the offline self-test."""
    state = services.state(SPLITTER)
    if state.get('LoadState') != 'loaded' or state.get('ActiveState') != 'active' or state.get('SubState') != 'running':
        raise ProbeError('Require the splitter to be loaded and running before this test.')
    party = services.state(PARTY)
    party_active = party.get('LoadState') == 'loaded' and party.get('ActiveState') == 'active'
    if party.get('ActiveState') in ('activating', 'deactivating', 'reloading'):
        raise ProbeError('Party emulator is in transition; aborting before any service change.')
    to_stop = ([PARTY] if party_active else []) + [SPLITTER]
    changed, samples, failures = [], [], []
    restarted = set()
    wire = None
    restored = False
    try:
        for unit in to_stop:
            # Record BEFORE stop: a timeout/signal may occur after systemd accepted it.
            changed.append(unit)
            log('Stopping ' + unit)
            services.stop(unit)
        wire = wire_factory(opener(), log)
        if wire.p300_ident() != b'\x20\xc2':
            raise ProbeError('Baseline device is not 20C2; no GFA command sent.')
        for _ in range(2):
            samples.append(wire.p80())
        if samples[0] != samples[1]:
            raise ProbeError('P80 samples differ; no confirmed identity.')
    except BaseException as exc:
        failures.append(str(exc) or type(exc).__name__)
        log('PROBE FAILED: ' + failures[-1])
    finally:
        previous = {sig: signal.signal(sig, signal.SIG_IGN) for sig in ABORT_SIGNALS}
        try:
            if wire is not None:
                try:
                    if wire.touched:
                        for attempt in range(1, 3):
                            try:
                                log(f'Restoring P300 and verifying 00F8/2, attempt {attempt}.')
                                restored = wire.p300_ident() == b'\x20\xc2'
                                if not restored:
                                    raise ProbeError('Restored P300 identity is not 20C2.')
                                break
                            except Exception as exc:
                                log('P300 restoration attempt failed: ' + str(exc))
                        if not restored:
                            failures.append('P300 restoration could not be verified.')
                finally:
                    try:
                        wire.port.close()
                        log('Serial port closed.')
                    except Exception as exc:
                        failures.append('Serial close failed: ' + str(exc))
            for unit in reversed(changed):
                try:
                    log('Restoring running state: ' + unit)
                    services.start(unit)
                    restarted.add(unit)
                    log('SERVICE_RESTORED=' + unit + ' running')
                except Exception as exc:
                    failures.append('Restart failed: ' + unit + ': ' + str(exc))
                    log(failures[-1])
        finally:
            for sig, handler in previous.items():
                signal.signal(sig, handler)
    confirmed = len(samples) == 2 and samples[0] == samples[1]
    log('P80_RESULT=' + (f'0x{samples[0]:02x} {VARIANTS[samples[0]]}' if confirmed else 'UNCONFIRMED'))
    log('P300_RESTORED=' + ('yes' if restored else 'NOT_VERIFIED'))
    log('SPLITTER_RESTARTED=' + ('yes' if SPLITTER in restarted else 'NOT_VERIFIED'))
    log('RESULT=' + ('PASS' if confirmed and restored and not failures else 'FAIL'))
    for failure in failures:
        log('ERROR: ' + failure)
    return 0 if confirmed and restored and not failures else 1


def self_test() -> int:
    """Standard-library-only tests: no systemctl, serial import or live device."""
    import tempfile
    import unittest

    class FakePort:
        def __init__(self, values=(0x20, 0x20), ident=b'\x20\xc2'):
            self.values, self.ident = iter(values), ident
            self.rx, self.tx = bytearray(), []
            self.enq, self.closed, self.t = False, False, 0.0
        @property
        def in_waiting(self):
            return len(self.rx)
        def clock(self):
            return self.t
        def write(self, data):
            self.tx.append(data)
            if data == b'\x04':
                self.enq = True
                self.rx.extend(b'\x05')
            elif data == b'\x16\x00\x00':
                self.enq = False
                self.rx.extend(b'\x06')
            elif data == IDENT_REQUEST:
                frame = b'\x41\x07\x01\x01\x00\xf8\x02' + self.ident
                self.rx.extend(b'\x06' + frame + bytes([sum(frame[1:]) & 255]))
            elif data == P80_REQUEST:
                self.enq = False
                value = next(self.values)
                if value is not None:
                    self.rx.extend(bytes([value]))
            return len(data)
        def read(self, count):
            self.t += 0.05
            if not self.rx and self.enq:
                self.rx.extend(b'\x05')
            result = bytes(self.rx[:count])
            del self.rx[:count]
            return result
        def close(self):
            self.closed = True

    class FakeServices:
        def __init__(self, party=True, stop_fail=False):
            self.active = {SPLITTER: True, PARTY: party}
            self.calls, self.stop_fail = [], stop_fail
        def state(self, unit):
            return {'LoadState': 'loaded', 'ActiveState': 'active' if self.active[unit] else 'inactive',
                    'SubState': 'running' if self.active[unit] else 'dead'}
        def stop(self, unit):
            self.calls.append(('stop', unit))
            self.active[unit] = False
            if self.stop_fail and unit == SPLITTER:
                raise ProbeError('Simulated stop timeout after acceptance.')
        def start(self, unit):
            self.calls.append(('start', unit))
            self.active[unit] = True

    class Tests(unittest.TestCase):
        def exercise(self, port=None, service=None, opener=None):
            port = port or FakePort()
            service = service or FakeServices()
            lines = []
            code = run_guarded(service, opener or (lambda: port), lines.append,
                               lambda p, log: Wire(p, log, p.clock))
            return code, port, service, lines
        def test_fixed_frames(self):
            self.assertEqual(IDENT_REQUEST.hex(), '4105000100f80200')
            self.assertEqual(P80_REQUEST.hex(), '016b405001')
        def test_good_frame(self):
            self.assertEqual(decode_ident_frame(bytes.fromhex('41 07 01 01 00 f8 02 20 c2 e5')), b'\x20\xc2')
        def test_bad_checksum(self):
            with self.assertRaises(ProbeError):
                decode_ident_frame(bytes.fromhex('41 07 01 01 00 f8 02 20 c2 e4'))
        def test_empty_frame(self):
            with self.assertRaises(ProbeError):
                decode_ident_frame(b'')
        def test_wrong_response(self):
            frame = bytes.fromhex('41 07 03 01 00 f8 02 20 c2')
            with self.assertRaises(ProbeError):
                decode_ident_frame(frame + bytes([sum(frame[1:]) & 255]))
        def test_allowlist_blocks_writes(self):
            wire = Wire(FakePort(), lambda _: None)
            for frame in (b'\x68\x40\x50\x01\x20', b'\xf4', b'\x02', b'\x01\x6b\x40\x06\x01'):
                with self.assertRaises(ProbeError):
                    wire.send(frame)
            self.assertFalse(wire.touched)
        def test_happy_path(self):
            code, port, service, lines = self.exercise()
            self.assertEqual(code, 0)
            self.assertTrue(port.closed)
            self.assertTrue(all(service.active.values()))
            self.assertEqual(port.tx.count(P80_REQUEST), 2)
            self.assertTrue(all(x in ALLOWED_TX for x in port.tx))
            self.assertIn('P300_RESTORED=yes', lines)
            self.assertEqual(service.calls[-2:], [('start', SPLITTER), ('start', PARTY)])
        def test_unknown_p80(self):
            code, port, service, lines = self.exercise(FakePort(values=(0x05,)))
            self.assertEqual(code, 1)
            self.assertIn('P300_RESTORED=yes', lines)
            self.assertTrue(all(service.active.values()))
            self.assertEqual(port.tx.count(P80_REQUEST), 1)
        def test_p80_timeout(self):
            code, port, service, lines = self.exercise(FakePort(values=(None,)))
            self.assertEqual(code, 1)
            self.assertIn('P300_RESTORED=yes', lines)
            self.assertTrue(port.closed)
        def test_p80_mismatch(self):
            code, _, _, lines = self.exercise(FakePort(values=(0x20, 0x21)))
            self.assertEqual(code, 1)
            self.assertIn('P80_RESULT=UNCONFIRMED', lines)
        def test_other_known_variant(self):
            code, _, _, lines = self.exercise(FakePort(values=(0x21, 0x21)))
            self.assertEqual(code, 0)
            self.assertIn('P80_RESULT=0x21 SCOT', lines)
        def test_wrong_device_no_gfa(self):
            code, port, _, _ = self.exercise(FakePort(ident=b'\x20\xcb'))
            self.assertEqual(code, 1)
            self.assertNotIn(P80_REQUEST, port.tx)
        def test_stop_failure_still_restores(self):
            code, _, service, _ = self.exercise(service=FakeServices(stop_fail=True))
            self.assertEqual(code, 1)
            self.assertTrue(all(service.active.values()))
        def test_open_failure_still_restores(self):
            def fail():
                raise OSError('Simulated serial open failure.')
            code, _, service, _ = self.exercise(opener=fail)
            self.assertEqual(code, 1)
            self.assertTrue(all(service.active.values()))
        def test_inactive_party_stays_inactive(self):
            code, _, service, _ = self.exercise(service=FakeServices(party=False))
            self.assertEqual(code, 0)
            self.assertFalse(service.active[PARTY])
            self.assertNotIn(('start', PARTY), service.calls)
        def test_keyboard_interrupt_restores(self):
            class Interrupted(FakePort):
                def write(self, data):
                    if data == P80_REQUEST:
                        raise KeyboardInterrupt()
                    return super().write(data)
            code, port, service, lines = self.exercise(Interrupted())
            self.assertEqual(code, 1)
            self.assertTrue(port.closed)
            self.assertTrue(all(service.active.values()))
            self.assertIn('P300_RESTORED=yes', lines)
        def test_recovery_failure_still_restarts(self):
            class BrokenAfterP80(FakePort):
                def write(self, data):
                    if data == b'\x04' and self.tx.count(P80_REQUEST) == 2:
                        raise OSError('Simulated USB disconnect during recovery.')
                    return super().write(data)
            code, port, service, lines = self.exercise(BrokenAfterP80())
            self.assertEqual(code, 1)
            self.assertTrue(port.closed)
            self.assertTrue(all(service.active.values()))
            self.assertIn('P300_RESTORED=NOT_VERIFIED', lines)
        def test_close_failure_still_restarts(self):
            class BadClose(FakePort):
                def close(self):
                    super().close()
                    raise OSError('Simulated close error.')
            code, _, service, _ = self.exercise(BadClose())
            self.assertEqual(code, 1)
            self.assertTrue(all(service.active.values()))
        def test_restart_failure_reported(self):
            class BadStart(FakeServices):
                def start(self, unit):
                    if unit == SPLITTER:
                        raise ProbeError('Simulated restart failure.')
                    super().start(unit)
            code, _, service, lines = self.exercise(service=BadStart())
            self.assertEqual(code, 1)
            self.assertTrue(service.active[PARTY])
            self.assertIn('SPLITTER_RESTARTED=NOT_VERIFIED', lines)
        def test_refuse_stopped_splitter(self):
            service = FakeServices()
            service.active[SPLITTER] = False
            with self.assertRaises(ProbeError):
                self.exercise(service=service)
            self.assertEqual(service.calls, [])
        def test_no_enq_timeout_sends_no_gfa(self):
            class NoEnq(FakePort):
                def read(self, count):
                    self.t += 0.5
                    return b''
            code, port, service, _ = self.exercise(NoEnq())
            self.assertEqual(code, 1)
            self.assertNotIn(P80_REQUEST, port.tx)
            self.assertTrue(all(service.active.values()))
        def test_trailing_data_rejected(self):
            class Trailing(FakePort):
                def write(self, data):
                    result = super().write(data)
                    if data == P80_REQUEST:
                        self.rx.extend(b'\x20')
                    return result
            code, _, service, _ = self.exercise(Trailing())
            self.assertEqual(code, 1)
            self.assertTrue(all(service.active.values()))
        def test_literal_settings_only(self):
            with tempfile.TemporaryDirectory() as root:
                path = Path(root) / 'settings.py'
                path.write_text("port_optolink = '/dev/ttyUSB0'\nport_vitoconnect = None\nvs1protocol = False\nraise Exception('must not execute')\n")
                self.assertEqual(read_settings(path), '/dev/ttyUSB0')
                with path.open('a') as f:
                    f.write("if True:\n    port_optolink = '/dev/ttyUSB2'\n")
                with self.assertRaises(ProbeError):
                    read_settings(path)
                path.write_text("port_optolink = '/dev/ttyUSB0'\nport_vitoconnect = None\nvs1protocol = True\n")
                with self.assertRaises(ProbeError):
                    read_settings(path)
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(Tests)
    return 0 if unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful() else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--execute', action='store_true', help='Explicitly pause services and run the live read-only diagnostic.')
    group.add_argument('--self-test', action='store_true', help='Offline tests only; no live actions.')
    args = parser.parse_args()
    if args.self_test:
        return self_test()
    if not args.execute:
        print(f'WB2A GFA P80 probe {VERSION}: no action without --execute.\n'
              'Live plan: read configured port; pause running splitter/active party emulator;\n'
              'P300 00F8/2 baseline; two independent VS1 P80 reads; verified P300 restore;\n'
              'close port and restart previously running services. No settings edits.\n'
              'Use --self-test for offline validation.')
        return 0
    if os.geteuid() != 0:
        print('ERROR: --execute requires root.', file=sys.stderr)
        return 1
    log = None
    lock_fd = None
    previous = {}
    try:
        import serial  # Fail before touching services if pyserial is unavailable.
        port = read_settings(SETTINGS)
        if not stat.S_ISCHR(os.stat(port).st_mode):
            raise ProbeError('Configured port is not a character device.')
        lock_fd = os.open('/run/lock/wb2a-gfa-p80-probe.lock',
                          os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        stamp = dt.datetime.now().strftime('%Y%m%d-%H%M%S')
        log = Log(Path('/root') / f'wb2a-gfa-p80-{stamp}-{os.getpid()}.log')
        log(f'WB2A P80-only probe {VERSION}; LOG={log.path}')
        log(f'Configured port: {port}; resolved: {os.path.realpath(port)}; 4800 8E2.')
        log('No parameter writes. Normal MQTT/TCP polling is paused during this test.')
        def abort(signum, _frame):
            raise ProbeError('Interrupted by signal ' + str(signum) + '; entering cleanup.')
        previous = {sig: signal.signal(sig, abort) for sig in ABORT_SIGNALS}
        return run_guarded(Services(), lambda: open_port(port, serial), log)
    except Exception as exc:
        if log:
            log('ERROR: ' + str(exc))
        else:
            print('ERROR: ' + str(exc), file=sys.stderr)
        return 1
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)
        if lock_fd is not None:
            os.close(lock_fd)
        if log:
            log('LOG=' + str(log.path))
            log.close()


if __name__ == '__main__':
    raise SystemExit(main())
