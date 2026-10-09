"""Linux PTY smoke tests: kernel byte streams, no physical serial device."""
from __future__ import annotations

import os
import pty
import sys
import termios
import time
import tty
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from handover_acceleration.coordinator import (  # noqa: E402
    ACK, DEVICE_ID, GFA, HandoverCoordinator, P300_ID, PortLease, ProtocolError,
)
from test_handover_acceleration import (  # noqa: E402
    FakeClock, expect_p300, expect_vs1, p300_reply,
)


class PTYFakePort:
    """Serial-like object with real kernel PTY I/O, scripted read-only peer."""
    def __init__(self, script):
        self.script = list(script)
        self.master, self.slave = pty.openpty()
        tty.setraw(self.master)
        tty.setraw(self.slave)
        os.set_blocking(self.master, False)
        os.set_blocking(self.slave, False)
        self.closed = False
        self.writes = []
        self.resets = 0

    def write(self, payload):
        if not self.script:
            raise AssertionError('unexpected transmit frame')
        expected, response = self.script.pop(0)
        if payload != expected:
            raise AssertionError(f'expected {expected.hex()}, got {payload.hex()}')
        self.writes.append(payload)
        if os.write(self.slave, payload) != len(payload):
            raise AssertionError('PTY TX short write')
        seen = bytearray()
        deadline = time.monotonic() + 1.0
        while len(seen) < len(payload):
            if time.monotonic() >= deadline:
                raise AssertionError('PTY TX deadline')
            try:
                seen.extend(os.read(self.master, len(payload) - len(seen)))
            except BlockingIOError:
                continue
        if seen != payload:
            raise AssertionError('PTY TX bytes corrupted')
        if response and os.write(self.master, response) != len(response):
            raise AssertionError('PTY RX short write')
        return len(payload)

    def read(self, count):
        try:
            return os.read(self.slave, count)
        except BlockingIOError:
            return b''

    def reset_input_buffer(self):
        self.resets += 1
        termios.tcflush(self.slave, termios.TCIFLUSH)

    def close(self):
        if not self.closed:
            os.close(self.master)
            os.close(self.slave)
            self.closed = True


class PTYTests(unittest.TestCase):
    def test_kernel_pty_roundtrip_single_enq_and_gfa(self):
        import tempfile
        with tempfile.TemporaryDirectory() as folder:
            fake = FakeClock()
            port = PTYFakePort(expect_vs1() + expect_p300() + expect_vs1(1)
                               + [(GFA['P06'], b'\x12')])
            # Add one extra permitted P300 identity transaction inside the
            # verified P300 phase, before returning to VS1.
            port.script = (expect_vs1() + expect_p300()
                           + [(P300_ID, p300_reply(0x00f8, DEVICE_ID)), (ACK, b'')]
                           + expect_vs1(1) + [(GFA['P06'], b'\x12')])
            m = HandoverCoordinator(lambda: port,
                                    PortLease(Path(folder) / 'serial.lock'),
                                    clock=fake.monotonic, sleep=fake.sleep)
            with m:
                self.assertEqual(m.p300_window(lambda c: c.p300_identity()), DEVICE_ID)
                self.assertEqual(m.gfa_read('P06'), b'\x12')
            self.assertTrue(port.closed)
            self.assertEqual(port.script, [])
            self.assertEqual(port.resets, 3)

    def test_pty_fails_closed_on_trailing_response(self):
        import tempfile
        with tempfile.TemporaryDirectory() as folder:
            fake = FakeClock()
            script = expect_vs1(p80=b'\x20\x11')
            port = PTYFakePort(script)
            m = HandoverCoordinator(lambda: port,
                                    PortLease(Path(folder) / 'serial.lock'),
                                    clock=fake.monotonic, sleep=fake.sleep)
            with self.assertRaisesRegex(ProtocolError, 'trailing response bytes'):
                with m:
                    pass
            self.assertTrue(port.closed)


if __name__ == '__main__':
    unittest.main()
