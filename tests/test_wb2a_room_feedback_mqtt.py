"""Fail-closed MQTT room sensor -> Optolink 0x2321 control, synthetic-only."""
from __future__ import annotations
import ast
import importlib.util
import math
from pathlib import Path
import sys
import unittest

SCRIPT=Path(__file__).resolve().parents[1]/'tools'/'wb2a-room-feedback-mqtt.py'
spec=importlib.util.spec_from_file_location('wb2a_mqtt_room_feedback_test',SCRIPT)
m=importlib.util.module_from_spec(spec)
sys.modules[spec.name]=m
spec.loader.exec_module(m)


class Clock:
    def __init__(self,t=100):self.t=t
    def __call__(self):return self.t
    def tick(self,dt):self.t+=dt


class DummyBoiler:
    def __init__(self):
        self.target=21
        self.external=0
        self.a0=0
        self.b0=0
        self.fault=0
        self.device=m.actuator.ID
        self.writes=[]
        self.refuse_write=False
        self.foreign_readback=False

    def read(self,addr,n):
        if addr==0xf8:return self.device
        if addr==0x27a0:return bytes((self.a0,))
        if addr==0x27b0:return bytes((self.b0,))
        if addr==0x2321:
            return bytes(((self.external+1) if self.foreign_readback and self.external else self.external,))
        if addr==0x2306:return bytes((self.target,))
        if addr==0x5738:return bytes((self.fault,))
        raise AssertionError((addr,n))

    def write_external(self,value):
        assert type(value) is int and value in (0,*range(16,27))
        self.writes.append(value)
        if self.refuse_write:raise m.FeedbackRejected('synthetic writer failure')
        self.external=value


class SampleTests(unittest.TestCase):
    def test_nonretained_plain_live_sensor(self):
        s=m.decode_live_sensor(b'20.2',retained=False,at_s=100.0)
        self.assertAlmostEqual(s.temperature_c,20.2)
        self.assertEqual(s.at_monotonic_s,100.0)

    def test_exact_one_key_json_temperature(self):
        for payload in (b'{"temperature":21.5}',b'{"temperature":20}',
                        b'20',b' 20.0 '):
            with self.subTest(payload=payload):
                self.assertEqual(m.decode_live_sensor(
                    payload,retained=False,at_s=200).temperature_c,
                    21.5 if b'21.5' in payload else 20)

    def test_retained_payload_rejected_even_with_plausible_number(self):
        with self.assertRaises(m.FeedbackRejected):
            m.decode_live_sensor(b'21.0',retained=True,at_s=100)

    def test_spoofed_extra_fields_are_rejected(self):
        for p in (b'{"temperature":21,"command":"set_boiler"}',
                  b'{"temp":22}',b'{"temperature":true}',b'{"temperature":"20"}',
                  b'null',b'false',b'22 C',b'',bytes(150),b'\xff',
                  b'NaN',b'1e309',b'{"temperature":9.9}',
                  b'{"temperature":32.1}'):
            with self.subTest(payload=repr(p)[:24]),self.assertRaises(
                m.FeedbackRejected):
                m.decode_live_sensor(p,retained=False,at_s=100)

    def test_nonfinite_timestamp_rejected(self):
        for t in (math.nan,math.inf,-math.inf):
            with self.assertRaises(m.FeedbackRejected):
                m.decode_live_sensor(b'20',retained=False,at_s=t)


class FeedbackControlTests(unittest.TestCase):
    def _new(self,**kw):
        c=DummyBoiler()
        for k,v in kw.items():setattr(c,k,v)
        clock=Clock()
        return m.FeedbackCore(c,now=clock),c,clock

    def test_normal_room_below_setpoint_corrections_and_release(self):
        r,b,clk=self._new()
        self.assertEqual(r.preflight(),21)
        r.update(m.RoomSample(20.0,clk()))
        self.assertTrue(r.tick())
        self.assertEqual(b.external,22)
        self.assertEqual(b.writes,[22])
        clk.tick(30)
        r.update(m.RoomSample(20.0,clk()))
        self.assertFalse(r.tick())
        r.shutdown()
        self.assertEqual(b.writes,[22,0])
        self.assertFalse(r.active)
        self.assertTrue(r.ended)

    def test_warm_room_lowers_effective_temperature(self):
        r,b,clock=self._new()
        r.preflight()
        r.update(m.RoomSample(23,clock()))
        r.tick()
        self.assertEqual(b.external,19)
        r.shutdown()
        self.assertEqual(b.external,0)

    def test_stale_sensor_releases_override(self):
        r,b,clock=self._new()
        r.preflight()
        r.update(m.RoomSample(20,clock()))
        r.tick()
        self.assertEqual(b.external,22)
        clock.tick(m.MAX_SENSOR_AGE_S+1)
        self.assertFalse(r.tick())
        self.assertEqual(b.external,0)
        self.assertEqual(b.writes,[22,0])
        r.shutdown()

    def test_no_sensor_never_writes_to_boiler(self):
        r,b,_=self._new()
        r.preflight()
        self.assertFalse(r.tick())
        self.assertEqual(b.writes,[])
        r.shutdown()
        self.assertEqual(b.writes,[])

    def test_sensor_updates_are_rate_limited(self):
        r,b,clock=self._new()
        r.preflight()
        r.update(m.RoomSample(20,clock()))
        self.assertTrue(r.tick())
        clock.tick(10)
        r.update(m.RoomSample(26,clock()))
        self.assertFalse(r.tick())
        self.assertEqual(b.external,22)
        clock.tick(30)
        r.update(m.RoomSample(26,clock()))
        self.assertTrue(r.tick())
        self.assertEqual(b.external,21)
        clock.tick(30)
        r.update(m.RoomSample(26,clock()))
        self.assertTrue(r.tick())
        self.assertEqual(b.external,20)
        r.shutdown()
        self.assertEqual(b.external,0)

    def test_concurrent_coding_or_fault_releases_and_aborts(self):
        for name,value in [('a0',2),('b0',3),('fault',0xbc),('target',20)]:
            with self.subTest(name=name):
                r,b,t=self._new()
                r.preflight()
                r.update(m.RoomSample(20,t()))
                r.tick()
                setattr(b,name,value)
                t.tick(30)
                r.update(m.RoomSample(20,t()))
                with self.assertRaises(m.FeedbackRejected):
                    r.tick()
                self.assertEqual(b.external,0)

    def test_controller_manual_takeover_not_overwritten(self):
        r,b,t=self._new()
        r.preflight()
        r.update(m.RoomSample(20,t()))
        r.tick()
        b.external=0
        t.tick(35)
        r.update(m.RoomSample(20,t()))
        with self.assertRaisesRegex(m.FeedbackRejected,'taken over'):
            r.tick()
        self.assertEqual(b.writes,[22])
        self.assertEqual(b.external,0)

    def test_no_authority_when_foreign_setpoint_already_exists(self):
        for k,v in [('external',22),('fault',1),('a0',2),('b0',3),
                    ('target',15),('device',bytes(8))]:
            with self.subTest(k=k):
                r,b,_=self._new(**{k:v})
                with self.assertRaises(m.FeedbackRejected):
                    r.preflight()
                self.assertEqual(b.writes,[])

    def test_dont_accept_stale_future_or_invalid_room_sample(self):
        r,b,t=self._new()
        r.preflight()
        for sample in (m.RoomSample(8,t()),m.RoomSample(50,t()),
                       m.RoomSample(21,t()+10),None):
            with self.subTest(sample=sample),self.assertRaises(m.FeedbackRejected):
                r.update(sample)
        self.assertEqual(b.writes,[])

    def test_successful_write_but_bad_readback_clears_actual_controller_override(self):
        r,b,t=self._new()
        r.preflight()
        r.update(m.RoomSample(20,t()))
        b.foreign_readback=True
        with self.assertRaisesRegex(m.FeedbackRejected,'readback mismatch'):
            r.tick()
        self.assertEqual(b.external,0)
        self.assertEqual(b.writes,[22,0])
        r.shutdown()

    def test_ambiguous_failed_write_still_attempts_zero_restore(self):
        r,b,t=self._new()
        r.preflight()
        r.update(m.RoomSample(20,t()))
        b.refuse_write=True
        with self.assertRaisesRegex(m.FeedbackRejected,'restore unverified'):
            r.tick()
        self.assertEqual(b.writes,[22,0])
        self.assertEqual(b.external,0)
        b.refuse_write=False
        r.shutdown()

    def test_restore_readback_failure_fails_closed(self):
        r,b,t=self._new()
        r.preflight()
        r.update(m.RoomSample(20,t()))
        r.tick()
        b.refuse_write=True
        with self.assertRaises(m.FeedbackRejected):
            r.shutdown()
        self.assertTrue(r.ended)
        self.assertFalse(r.active)
        self.assertEqual(b.external,22)
        # independent restore supervisor is required in real hardware.

    def test_ha_publisher_example_is_nonretained_and_avoids_boiler_command_topic(self):
        path=SCRIPT.parents[1]/'config/optolink-splitter/ha-optolink-room-feedback-example.yaml'
        text=path.read_text()
        self.assertIn('topic: "openv/room/temperature"',text)
        self.assertIn('retain: false',text)
        self.assertIn('minutes: "/1"',text)
        self.assertIn('sensor.temperatursensorwohnzimmer_temperatur',text)
        self.assertIn('mqtt.publish',text)
        self.assertNotIn('topic: "openv/cmnd"',text)

    def test_no_device_io_imports_or_second_serial_owner(self):
        ast_module=ast.parse(SCRIPT.read_text())
        names=set()
        for n in ast.walk(ast_module):
            if isinstance(n,ast.Import):
                names.update(x.name.split('.')[0] for x in n.names)
            elif isinstance(n,ast.ImportFrom) and n.module:
                names.add(n.module.split('.')[0])
        self.assertFalse(names & {'serial','socket','paramiko','ctypes'})
        self.assertEqual(m.actuator.EXTERNAL_ROOM_SETPOINT,0x2321)
        self.assertFalse(m.FeedbackCore(DummyBoiler()).active)

if __name__=='__main__':
    unittest.main()
