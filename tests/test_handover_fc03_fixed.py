"""Read-only fixed FC03 golden-wire, batching, CRC and recovery regressions."""
import sys
import tempfile
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from handover_acceleration.coordinator import (
    ACK, EOT, DEVICE_ID, GFA, HandoverCoordinator, Mode, P300_RAM_READS,
    PortLease, ProtocolError,
)
from handover_acceleration.phase_executor import execute_read_phases
from handover_acceleration.phase_planner import ReadJob, Budget, PlanRejected
from handover_acceleration.scheduler import GfaFreshnessLedger, ReadKind, StaleReading
from test_handover_acceleration import FakePort, FakeClock, expect_vs1, expect_p300


def frame(fc, addr, raw):
    body = bytes([1, fc, addr >> 8, addr & 255, len(raw)]) + raw
    return ACK + bytes([0x41, len(body)]) + body + bytes(((len(body) + sum(body)) & 255,))


def response(key, *, bad_crc=False, wrong_address=False, wrong_fc=False, raw=None):
    fc, addr, length, req = P300_RAM_READS[key]
    if raw is None:
        raw = bytes(range(length))
    payload = bytearray(frame(fc if not wrong_fc else 2,
                              addr if not wrong_address else addr + 1, raw))
    if bad_crc:
        payload[-1] ^= 0x80
    return [(req, bytes(payload)), (ACK, b'')]


def job(name, kind):
    return ReadJob(name, kind, duration_ms=85, deadline_ms=25000, independent=True)


class P300FC03ReadOnlyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.clock = FakeClock()

    def manager(self, script):
        port = FakePort(script)
        manager = HandoverCoordinator(lambda: port, PortLease(Path(self.tmp.name) / 'lease'),
                                      clock=self.clock.monotonic, sleep=self.clock.sleep)
        return manager, port

    def test_golden_request_bytes_and_whitelist(self):
        self.assertEqual(set(P300_RAM_READS), {'ram_0f20_32','ram_1c60_32','ram_1640_32'})
        self.assertEqual(P300_RAM_READS['ram_0f20_32'][3].hex(), '410500030f202057')
        self.assertEqual(P300_RAM_READS['ram_1c60_32'][3].hex(), '410500031c6020a4')
        self.assertEqual(P300_RAM_READS['ram_1640_32'][3].hex(), '410500031640207e')

    def test_uart1_rx_candidate_one_fixed_fc03_no_arbitrary_write(self):
        from handover_acceleration.runtime_admission import READONLY_PRESET
        # The pre-existing automatic batch MUST NOT silently add an RX probe.
        self.assertNotIn(ReadKind.P300_RAM_1640_32,
                         {kind for _,kind,_ in READONLY_PRESET})
        raw=bytes.fromhex('00000001b10a010110fe23d8fa01fb0122d1')
        raw=raw.ljust(32,b'\x00')
        seq=expect_vs1(2)+expect_p300()+response('ram_1640_32',raw=raw)+expect_vs1(1)
        manager,port=self.manager(seq)
        with manager:
            out=execute_read_phases(manager,
                     [job('p300_ram_1640_32',ReadKind.P300_RAM_1640_32)],
                     Budget(max_vs1_unavailable_ms=8500,
                            max_p06_age_ms=9000,max_queue_wait_ms=9000))
            self.assertEqual(manager.mode,Mode.VS1_VERIFIED)
        self.assertEqual(len(out.reads),1)
        self.assertEqual(out.reads[0].raw,raw)
        self.assertEqual(out.p300_entry_count,1)
        self.assertEqual(port.script,[])
        self.assertFalse(any(len(packet)>8 and packet.startswith(b'\x41\x05\x00\x04')
                             for packet in port.writes))

    def test_uart1_rx_candidate_corrupt_fc03_response_recovers(self):
        seq=(expect_vs1(2)+expect_p300()
             +response('ram_1640_32',bad_crc=True)[:1]+expect_vs1(2))
        manager,port=self.manager(seq)
        with self.assertRaises(ProtocolError):
            with manager:
                manager.to_p300()
                manager.p300_ram_read('ram_1640_32')
        self.assertEqual(manager.mode,Mode.DETACHED)
        self.assertEqual(port.script,[])

    def test_two_fc03_blocks_and_identity_in_one_p300_window(self):
        jobs = [job('before', ReadKind.VS1_P80),
                job('first', ReadKind.P300_RAM_0F20_32),
                job('id', ReadKind.P300_ID),
                job('second', ReadKind.P300_RAM_1C60_32),
                job('after', ReadKind.VS1_P06)]
        from test_handover_acceleration import p300_reply, P300_ID
        seq = (expect_vs1(2) + [(GFA['P80'],b'\x20'),(GFA['P06'],b'\x05')]
               + expect_p300() + response('ram_0f20_32')
               + [(P300_ID, p300_reply(0xf8, DEVICE_ID)), (ACK, b'')]
               + response('ram_1c60_32')
               + expect_vs1(1))
        manager, port = self.manager(seq)
        with manager:
            res = execute_read_phases(manager, jobs, Budget())
            self.assertEqual(manager.mode, Mode.VS1_VERIFIED)
        self.assertEqual(res.p300_entry_count, 1)
        self.assertEqual(port.writes.count(EOT), 3)
        self.assertEqual([r.name for r in res.reads],
                         ['before','after','first','id','second'])
        self.assertEqual([len(r.raw) for r in res.reads], [1,1,32,2,32])
        self.assertTrue(port.closed)
        self.assertEqual(port.script, [])

    def test_non_allowlisted_block_never_reaches_wire(self):
        manager, port = self.manager(expect_vs1(2) + expect_p300() + expect_vs1(1))
        with manager:
            manager.to_p300()
            before = len(port.writes)
            for name in ('ram_55d3_11','ram_0f29_32','', '0x0f20', 'FC04'):
                with self.subTest(name=name), self.assertRaises(ProtocolError):
                    manager.p300_ram_read(name)
                self.assertEqual(len(port.writes), before)
            manager.to_vs1_fast()
        self.assertEqual(port.script, [])

    def test_ram_not_a_gfa_sample_or_p06_substitute(self):
        ledger = GfaFreshnessLedger(clock=self.clock.monotonic)
        with self.assertRaises(Exception):
            ledger.record(ReadKind.P300_RAM_0F20_32, bytes(range(32)),
                          session_generation=1, vs1_verified=True)
        with self.assertRaises(StaleReading):
            ledger.fresh(ReadKind.VS1_P06, current_generation=1, max_age_s=99)

    def test_checksum_function_address_corruption_each_forces_recovery(self):
        for kw in ({'bad_crc': True}, {'wrong_address': True}, {'wrong_fc': True}):
            with self.subTest(kw=kw):
                script = expect_vs1(2) + expect_p300() + response('ram_0f20_32', **kw)[:1] + expect_vs1(2)
                manager, port = self.manager(script)
                with self.assertRaises(ProtocolError):
                    with manager:
                        manager.to_p300()
                        manager.p300_ram_read('ram_0f20_32')
                self.assertEqual(manager.mode, Mode.DETACHED)
                self.assertEqual(port.writes.count(EOT), 3)
                self.assertEqual(port.script, [])

    def test_reject_fc03_in_vs1_without_data_or_switched_transport(self):
        manager, port = self.manager(expect_vs1(2))
        with manager:
            before = len(port.writes)
            with self.assertRaises(ProtocolError):
                manager.p300_ram_read('ram_0f20_32')
            self.assertEqual(len(port.writes), before)
        self.assertEqual(port.script, [])

    def test_deadline_preflight_rejects_before_any_switch(self):
        manager, port = self.manager(expect_vs1(2))
        with manager:
            before = len(port.writes)
            with self.assertRaises(PlanRejected):
                execute_read_phases(manager, [job('ram',ReadKind.P300_RAM_0F20_32)],
                    Budget(max_p06_age_ms=2100,max_vs1_unavailable_ms=2100))
            self.assertEqual(len(port.writes), before)
        self.assertEqual(port.script, [])


if __name__ == '__main__':
    unittest.main()
