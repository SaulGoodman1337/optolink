"""Fully offline transport simulator for the observed 20C2 GWG C7 framing."""
from __future__ import annotations
import importlib.util
from pathlib import Path
import sys
import unittest

MODULE = Path(__file__).resolve().parents[1] / 'tools' / 'optolinkgwg.py'
spec = importlib.util.spec_from_file_location('optolinkgwg_test', MODULE)
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)


class Clock:
    now = 0.0

    def time(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


class SimulatedOwnerPort:
    def __init__(self, scenarios):
        self.scenarios = scenarios
        self.sends = []
        self.attempt = -1
        self.current = {}
        self.chunks = []
        self.sync_reads = 0
        self.flushes = 0
        self.reset_count = 0

    def reset_input_buffer(self):
        self.reset_count += 1

    def write(self, data):
        data = bytes(data)
        self.sends.append(data)
        if data == b'\x04':
            self.attempt += 1
            self.current = self.scenarios[self.attempt]
            self.chunks = []
            self.sync_reads = 0
            if self.current.get('sync_write_error'):
                return 0
        elif data.startswith(b'\x01\xC7'):
            self.chunks = list(self.current.get('replies', []))
            if self.current.get('frame_write_error'):
                return 0
        else:
            raise AssertionError('unexpected or unsafe serial bytes')
        return len(data)

    def flush(self):
        self.flushes += 1

    def read(self, n):
        self.sync_reads += 1
        if self.current.get('raise_on_read'):
            raise OSError('serial cable disconnected')
        return b'\x05' if self.current.get('sync', True) and self.sync_reads == 1 else b''

    def read_all(self):
        if self.current.get('raise_on_response'):
            raise OSError('serial disconnected mid-frame')
        return self.chunks.pop(0) if self.chunks else b''


def client(port, **kwargs):
    c = Clock()
    return mod.GWGProtocol(port, clock=c.time, sleep=c.sleep, **kwargs)


class FrameContract(unittest.TestCase):
    def test_exact_2010_frame(self):
        self.assertEqual(mod.GWGProtocol.frame(0xF8, 4).hex(), '01c7f80404')

    def test_8byte_frame(self):
        self.assertEqual(mod.GWGProtocol.frame(0xF8, 8).hex(), '01c7f80804')

    def test_f9_frame(self):
        self.assertEqual(mod.GWGProtocol.frame(0xF9, 3).hex(), '01c7f90304')

    def test_address_low_limit(self):
        self.assertEqual(mod.GWGProtocol.frame(0, 1).hex(), '01c7000104')

    def test_address_high_limit(self):
        self.assertEqual(mod.GWGProtocol.frame(255, 1).hex(), '01c7ff0104')

    def test_reject_20bit_address(self):
        with self.assertRaises(ValueError):
            mod.GWGProtocol.frame(0xF0000, 1)

    def test_reject_16bit_address(self):
        with self.assertRaises(ValueError):
            mod.GWGProtocol.frame(0x100, 1)

    def test_reject_negative_address(self):
        with self.assertRaises(ValueError):
            mod.GWGProtocol.frame(-1, 1)

    def test_reject_length_zero(self):
        with self.assertRaises(ValueError):
            mod.GWGProtocol.frame(0, 0)

    def test_reject_length_above_evidence(self):
        with self.assertRaises(ValueError):
            mod.GWGProtocol.frame(0, 9)

    def test_reject_window_wrap(self):
        with self.assertRaises(ValueError):
            mod.GWGProtocol.frame(0xFA, 8)

    def test_reject_bool_address(self):
        with self.assertRaises(ValueError):
            mod.GWGProtocol.frame(True, 1)

    def test_reject_bool_length(self):
        with self.assertRaises(ValueError):
            mod.GWGProtocol.frame(0, True)

    def test_every_possible_valid_frame_is_read_only(self):
        count = 0
        for addr in range(256):
            for size in range(1, mod.MAX_READ_LENGTH + 1):
                if addr + size > 256:
                    continue
                frame = mod.GWGProtocol.frame(addr, size)
                self.assertEqual(frame[1], 0xC7)
                self.assertEqual(frame[-1], 4)
                self.assertEqual(len(frame), 5)
                count += 1
        self.assertEqual(count, 2020)


class TransportContract(unittest.TestCase):
    def test_real_f8_4_fixture(self):
        p = SimulatedOwnerPort([{'replies': [bytes.fromhex('20c20003')]}])
        result = client(p).read_virtual(0xF8, 4)
        self.assertEqual(result.code, mod.SUCCESS)
        self.assertEqual(result.data.hex(), '20c20003')
        self.assertEqual(p.sends, [b'\x04', bytes.fromhex('01c7f80404')])

    def test_real_f8_8_fixture(self):
        p = SimulatedOwnerPort([{'replies': [bytes.fromhex('20c2000300000103')]}])
        result = client(p).read_virtual(0xF8, 8)
        self.assertEqual(result.data.hex(), '20c2000300000103')

    def test_real_f9_3_fixture_in_chunks(self):
        p = SimulatedOwnerPort([{'replies': [b'\xC2', b'\x00\x03']}])
        self.assertEqual(client(p).read_virtual(0xF9, 3).data, b'\xc2\x00\x03')

    def test_no_sync_no_query(self):
        p = SimulatedOwnerPort([{'sync': False}])
        result = client(p).read_virtual(0xF8, 4)
        self.assertEqual(result.code, mod.TIMEOUT)
        self.assertEqual(result.reason, 'enq_timeout')
        self.assertEqual(p.sends, [b'\x04'])

    def test_no_response_after_valid_enq(self):
        p = SimulatedOwnerPort([{'replies': []}])
        result = client(p).read_virtual(0xF8, 4)
        self.assertEqual(result.code, mod.TIMEOUT)
        self.assertEqual(result.reason, 'no_reply')

    def test_partial_response_never_success(self):
        p = SimulatedOwnerPort([{'replies': [b'\x20\xC2']}])
        result = client(p).read_virtual(0xF8, 4)
        self.assertEqual(result.code, mod.TIMEOUT)
        self.assertEqual(result.data, b'')
        self.assertEqual(result.received, b'\x20\xC2')
        self.assertEqual(result.reason, 'partial_reply')

    def test_overlong_response_rejected(self):
        p = SimulatedOwnerPort([{'replies': [bytes.fromhex('20c2000305')]}])
        result = client(p).read_virtual(0xF8, 4)
        self.assertEqual(result.code, mod.INVALID_FRAME)
        self.assertEqual(result.data, b'')

    def test_broken_sync_write(self):
        p = SimulatedOwnerPort([{'sync_write_error': True}])
        self.assertEqual(client(p).read_virtual(0xF8, 4).code, mod.TRANSPORT_LOST)

    def test_broken_frame_write(self):
        p = SimulatedOwnerPort([{'frame_write_error': True}])
        self.assertEqual(client(p).read_virtual(0xF8, 4).code, mod.TRANSPORT_LOST)

    def test_cable_disconnected(self):
        p = SimulatedOwnerPort([{'raise_on_read': True}])
        self.assertEqual(client(p).read_virtual(0xF8, 4).code, mod.TRANSPORT_LOST)

    def test_cable_disconnected_mid_response(self):
        p = SimulatedOwnerPort([{'raise_on_response': True}])
        self.assertEqual(client(p).read_virtual(0xF8, 4).code, mod.TRANSPORT_LOST)

    def test_invalid_input_causes_no_serial_io(self):
        p = SimulatedOwnerPort([])
        r = client(p).read_virtual(0xF0000, 4)
        self.assertEqual(r.code, mod.INVALID_FRAME)
        self.assertEqual(p.sends, [])

    def test_retry_after_no_enq_then_success(self):
        p = SimulatedOwnerPort([{'sync': False}, {'replies': [bytes.fromhex('20c20003')]}])
        r = client(p, retries=1).read_virtual(0xF8, 4)
        self.assertEqual(r.code, mod.SUCCESS)
        self.assertEqual(r.attempts, 2)
        self.assertEqual(p.sends, [b'\x04', b'\x04', bytes.fromhex('01c7f80404')])

    def test_retry_after_no_reply_then_success(self):
        p = SimulatedOwnerPort([{'replies': []}, {'replies': [bytes.fromhex('20c20003')]}])
        r = client(p, retries=1).read_virtual(0xF8, 4)
        self.assertEqual(r.code, mod.SUCCESS)
        self.assertEqual(r.attempts, 2)

    def test_no_retry_after_invalid_frame(self):
        p = SimulatedOwnerPort([{'replies': [b'abcdef']}])
        r = client(p, retries=1).read_virtual(0xF8, 4)
        self.assertEqual(r.code, mod.INVALID_FRAME)
        self.assertEqual(r.attempts, 1)

    def test_no_retry_after_serial_error(self):
        p = SimulatedOwnerPort([{'raise_on_read': True}])
        r = client(p, retries=1).read_virtual(0xF8, 4)
        self.assertEqual(r.code, mod.TRANSPORT_LOST)
        self.assertEqual(r.attempts, 1)

    def test_retries_restricted(self):
        with self.assertRaises(ValueError):
            client(SimulatedOwnerPort([]), retries=2)

    def test_sync_deadline_restricted(self):
        with self.assertRaises(ValueError):
            client(SimulatedOwnerPort([]), sync_timeout=30)

    def test_reply_deadline_restricted(self):
        with self.assertRaises(ValueError):
            client(SimulatedOwnerPort([]), reply_timeout=30)

    def test_trace_hex(self):
        p = SimulatedOwnerPort([{'replies': [bytes.fromhex('20c20003')]}])
        traces = []
        client(p, trace_hook=traces.append).read_virtual(0xF8, 4)
        self.assertEqual(traces[0]['requested_frame'], '01c7f80404')
        self.assertEqual(traces[0]['response'], '20c20003')
        self.assertEqual(traces[0]['sync_seen'], True)

    def test_trace_every_retry_with_timestamps(self):
        p = SimulatedOwnerPort([{'sync': False}, {'replies': [bytes.fromhex('20c20003')]}])
        records = []
        client(p, retries=1, trace_hook=records.append).read_virtual(0xF8, 4)
        self.assertEqual([x['attempts'] for x in records], [1, 2])
        self.assertEqual([x['status'] for x in records], ['FF', '01'])
        self.assertTrue(records[0]['at_utc'].endswith('+00:00'))

    def test_adapter_compat(self):
        p = SimulatedOwnerPort([{'replies': [bytes.fromhex('20c20003')]}])
        r = client(p).read_virtual(0xF8, 4)
        self.assertEqual(r.as_adapter_tuple(), (1, 0xF8, bytearray.fromhex('20c20003')))

    def test_module_never_constructs_serial_owner(self):
        src = MODULE.read_text()
        self.assertNotIn('serial.Serial(', src)
        self.assertNotIn('/dev/tty', src)
        self.assertNotIn('socket(', src)

    def test_module_offers_only_c7_frame(self):
        src = MODULE.read_text()
        self.assertNotIn('PHYSICAL_WRITE', src)
        self.assertNotIn('EEPROM_WRITE', src)
        self.assertNotIn('C8', src)
        self.assertNotIn('C4', src)


if __name__ == '__main__':
    unittest.main()
