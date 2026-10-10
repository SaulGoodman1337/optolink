"""Offline complete continuous VS1/P300 phase with simulated physical UART."""
from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import types
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from handover_acceleration.continuous_runtime import (
    ContinuousReadonlyRuntime, ContinuousRuntimeRejected)
from handover_acceleration.ingress_epoch import IngressEpoch
from handover_acceleration.pending_refresh import PendingReadbackLedger
from handover_acceleration.producer_fence import writer_transaction
from handover_acceleration.phase_planner import Budget
from test_handover_acceleration import (
    FakeClock, FakePort, expect_attached_vs1, expect_p300,
    p300_reply, P300_ID, DEVICE_ID, ACK, expect_vs1)
from test_handover_fc03_fixed import response


class ContinuousRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.producer=self.root/'producer.lock'
        self.producer.write_bytes(b'')
        self.producer.chmod(0o600)
        self.serial=self.root/'serial.lock'
        self.clock=FakeClock()
        self.ingress=IngressEpoch()
        self.enrolled=True
        self.packets=[]
        self.mqtt=types.SimpleNamespace(
            _hybrid_readback_ledger=PendingReadbackLedger(),
            cmnd_queue=[],lst_force_refresh=[])
        self.tcp=[]
        self.sync_calls=[]
        self.budget=Budget(max_vs1_unavailable_ms=8000,
                           max_p06_age_ms=9000)
        self.port=self.fake_port()
        self.runtime=ContinuousReadonlyRuntime(
            port=self.port,legacy_dispatch=self.legacy,
            resume_vs1=lambda:self.sync_calls.append('reset'),
            mqtt=self.mqtt,tcp_state=lambda:len(self.tcp),
            ingress=self.ingress,
            all_writers_attested=lambda:self.enrolled,
            lease_path=self.producer,serial_lease_path=self.serial,
            budget=self.budget,
            clock=self.clock.monotonic,sleep=self.clock.sleep)

    def fake_port(self,*,corrupt=False):
        sequence=(expect_attached_vs1()+expect_p300()+
                  [(P300_ID,p300_reply(0xF8,DEVICE_ID)),(ACK,b'')])
        if corrupt:
            sequence+=response('ram_0f20_32',bad_crc=True)[:1]+expect_vs1(2)
        else:
            sequence+=(response('ram_0f20_32')+
                       response('ram_1c60_32')+
                       expect_vs1(1,p06=b'\x53'))
        return FakePort(sequence)

    def legacy(self,request,serial):
        self.assertIs(serial,self.port)
        self.packets.append(request)
        value=b'\x20' if '4050' in request else b'\x53'
        return (1,bytearray(value),value.hex(),'1;0x0000;'+value.hex())

    def due(self):
        self.clock.sleep(120)
        self.runtime.note_keepalive(1)

    def test_verified_one_batch_and_cooldown_without_second_serial_open(self):
        self.due()
        outcome=self.runtime.tick()
        self.assertEqual(outcome.status,'VERIFIED_SWITCH')
        self.assertTrue(outcome.result.verified_vs1)
        self.assertEqual(outcome.result.p06_hex,'53')
        self.assertEqual(self.sync_calls,['reset'])
        self.assertEqual(self.port.script,[])
        self.assertFalse(self.port.closed)
        self.assertFalse(self.producer.read_bytes())
        self.assertEqual(self.runtime.tick().status,'NOT_DUE')

    def test_unenrolled_writers_refuse_before_any_uart_byte(self):
        self.enrolled=False
        self.due()
        out=self.runtime.tick()
        self.assertEqual(out.reason,'WRITER_ENROLMENT_NOT_ATTESTED')
        self.assertEqual(self.port.writes,[])
        self.assertFalse(self.serial.exists())

    def test_running_external_writer_excludes_entire_handover(self):
        self.due()
        with writer_transaction('party',path=self.producer):
            out=self.runtime.tick()
            self.assertEqual(out.reason,'WRITER_LEASE_BUSY_OR_UNVERIFIED')
            self.assertEqual(self.port.writes,[])
        self.clock.sleep(15)
        self.runtime.note_keepalive(1)
        self.assertEqual(self.runtime.tick().status,'VERIFIED_SWITCH')

    def test_pending_timers_and_mqtt_messages_refuse_until_complete(self):
        self.due()
        ledger=self.mqtt._hybrid_readback_ledger
        item=ledger.register(5)
        self.assertEqual(self.runtime.tick().reason,'HA_READBACK_PENDING')
        self.assertFalse(self.port.writes)
        ledger.consume(item)
        ledger.complete_forced(1)
        self.mqtt.cmnd_queue.append('r;0x4006;1;raw;False')
        self.clock.sleep(15)
        self.runtime.note_keepalive(1)
        out=self.runtime.tick()
        self.assertEqual(out.reason,'PENDING_LEGACY_WORK')
        self.mqtt.cmnd_queue.clear()
        self.clock.sleep(15)
        self.runtime.note_keepalive(1)
        self.assertEqual(self.runtime.tick().status,'VERIFIED_SWITCH')

    def test_failed_ha_readback_never_permits_p300(self):
        self.due()
        ledger=self.mqtt._hybrid_readback_ledger
        item=ledger.register(5)
        ledger.consume(item)
        ledger.complete_forced(255)
        out=self.runtime.tick()
        self.assertEqual(out.status,'FAIL_CLOSED')
        self.assertEqual(out.reason,'HA_READBACK_FAILED')
        self.assertEqual(self.port.writes,[])

    def test_opaque_legacy_write_is_not_silently_acked_by_time(self):
        self.runtime.observe_legacy('writeraw;0x2306;64')
        self.due()
        self.assertEqual(self.runtime.tick().reason,
                         'WRITE_READBACK_NOT_ACKNOWLEDGED')
        self.clock.sleep(900)
        self.runtime.note_keepalive(1)
        self.assertEqual(self.runtime.tick().reason,
                         'WRITE_READBACK_NOT_ACKNOWLEDGED')
        self.assertEqual(self.port.writes,[])

    def test_p300_bad_crc_fails_closed_even_after_vs1_recovery(self):
        self.port=self.fake_port(corrupt=True)
        self.runtime.port=self.port
        self.due()
        with self.assertRaises(Exception):
            self.runtime.tick()
        self.assertTrue(self.runtime.gate.failed_closed)
        self.assertEqual(self.producer.read_bytes(),b'P300_FAILED')
        self.assertEqual(self.runtime.tick().status,'FAIL_CLOSED')
        self.assertFalse(self.port.closed)

    def test_zero_keepalive_cannot_promote_old_state(self):
        self.due()
        self.runtime.note_keepalive(0xff)
        self.assertEqual(self.runtime.tick().reason,
                         'LEGACY_KEEPALIVE_NOT_FRESH')
        self.assertEqual(self.port.writes,[])


if __name__=='__main__':
    unittest.main()
