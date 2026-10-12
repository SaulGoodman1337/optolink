"""Offline regression for Optolink external-room-setpoint control law and A/B/A."""
from __future__ import annotations
import ast
import importlib.util
from pathlib import Path
import subprocess
import sys
import unittest

P=Path(__file__).resolve().parents[1]/"tools/wb2a-external-room-influence.py"
spec=importlib.util.spec_from_file_location("external_room_controller_test",P)
m=importlib.util.module_from_spec(spec)
sys.modules[spec.name]=m
spec.loader.exec_module(m)

class FakeBoiler:
    def __init__(self, *, identity=m.ID,target=21,external=0,fault=0,
                 fail_first_write=False,wrong_readback=False):
        self.id=identity
        self.target=target
        self.external=external
        self.fault=fault
        self.writes=[]
        self.fail_first_write=fail_first_write
        self.wrong_readback=wrong_readback
    def read(self,a,n):
        assert (a,n) in {(0xf8,8),(0x2321,1),(0x2306,1),
                         (0x2544,2),(0x5738,1)}
        if a==0xf8:return self.id
        if a==0x2321:
            return bytes([self.external+int(self.wrong_readback and self.external!=0)])
        if a==0x2306:return bytes([self.target])
        if a==0x5738:return bytes([self.fault])
        if a==0x2544:
            # Simulated closed-loop response: real WB2A measured +18 deci-C
            # on VT-Soll for +1°C on external room target at target 21°C.
            raw=365+18*(self.external-21) if self.external else 365
            return raw.to_bytes(2,"little")
    def write_external(self,value):
        assert value in (0,*range(16,27))
        self.writes.append(value)
        if self.fail_first_write:
            self.fail_first_write=False
            raise m.RoomInfluenceRejected("synthetic transient write failure")
        self.external=value

class RoomControllerTests(unittest.TestCase):
    def test_room_error_increases_supply_and_restore_in_same_session(self):
        b=FakeBoiler()
        out=m.ExternalRoomController(b,sleep=lambda _:None).probe(
            room_c=20.0,target_c=21.0)
        self.assertEqual(out["before_supply_deci_c"],365)
        self.assertEqual(out["while_active"]["external_room_setpoint_c"],22)
        self.assertEqual(out["while_active"]["supply_first_deci_c"],383)
        self.assertEqual(out["while_active"]["supply_second_deci_c"],383)
        self.assertEqual(out["after_supply_deci_c"],365)
        self.assertTrue(out["external_room_override_restored"])
        self.assertEqual(b.writes,[22,0])
        self.assertEqual(b.external,0)
        self.assertFalse(out["vitotrol_registered_with_firmware"])
        self.assertFalse(out["actual_measured_room_source_connected"])
    def test_room_above_desired_reduces_setpoint(self):
        b=FakeBoiler()
        out=m.ExternalRoomController(b,sleep=lambda _:None).probe(
            room_c=22,target_c=21)
        self.assertEqual(out["while_active"]["external_room_setpoint_c"],20)
        self.assertLess(out["while_active"]["supply_first_deci_c"],
                        out["before_supply_deci_c"])
        self.assertEqual(out["after_supply_deci_c"],365)
    def test_saturation_and_no_unsafe_temperature_command(self):
        for measured,expected in ((10,24),(32,18),(21,21),(20.4,22),(21.6,20)):
            with self.subTest(measured=measured):
                self.assertEqual(m.compute_external_setpoint(21,measured),expected)
        self.assertEqual(m.compute_external_setpoint(24,10,2),26)
        self.assertEqual(m.compute_external_setpoint(17,32,2),16)
    def test_reject_nan_boolean_overshooting_and_outside_range(self):
        for target,measured,gain in (
            (float("nan"),20,1),(21,float("inf"),1),(False,20,1),
            (21,True,1),(25,20,1),(16,20,1),(21,9,1),(21,33,1),
            (21,20,0.1),(21,20,2.1),(21,20,float("nan"))):
            with self.subTest(v=(target,measured,gain)),self.assertRaises(
                m.RoomInfluenceRejected):
                m.compute_external_setpoint(target,measured,gain)
    def test_existing_external_override_or_heater_fault_is_not_overwritten(self):
        for kwargs in (dict(external=20),dict(fault=0xbc)):
            b=FakeBoiler(**kwargs)
            with self.assertRaises(m.RoomInfluenceRejected):
                m.ExternalRoomController(b).probe(room_c=20,target_c=21)
            self.assertEqual(b.writes,[])
    def test_missing_identity_and_normal_setpoint_divergence_fail_closed(self):
        for kwargs in (dict(identity=bytes(8)),dict(target=19)):
            b=FakeBoiler(**kwargs)
            with self.assertRaises(m.RoomInfluenceRejected):
                m.ExternalRoomController(b).probe(room_c=20,target_c=21)
            self.assertEqual(b.writes,[])
    def test_write_failure_still_restores_and_readback_mismatch_restores(self):
        for kwargs in (dict(fail_first_write=True),dict(wrong_readback=True)):
            b=FakeBoiler(**kwargs)
            with self.assertRaises(m.RoomInfluenceRejected):
                m.ExternalRoomController(b,sleep=lambda _:None).probe(
                    room_c=20,target_c=21)
            self.assertEqual(b.external,0)
            self.assertEqual(b.writes[-1],0)
    def test_invalid_hold_time_rejected_without_controller_io(self):
        for hold in (-1,31,True,"5",float('nan'),float('inf')):
            b=FakeBoiler()
            with self.subTest(hold=hold),self.assertRaises(m.RoomInfluenceRejected):
                m.ExternalRoomController(b).probe(room_c=20,target_c=21,
                                                  hold_s=hold)
            self.assertEqual(b.writes,[])
    def test_reply_parser_rejects_ambiguous_errors_address_and_bad_hex(self):
        self.assertEqual(m.parse_reply(
            "writeraw;0x2321;16 <- openv/resp: 1;0x2321;16",0x2321,1),b"\x16")
        for reply in ("3;0x2321;01","1;0x2322;16","1;0x2321;zz",
                      "1;0x2321;16\n<- openv/resp: 1;0x2321;16"):
            with self.subTest(reply=reply),self.assertRaises(m.RoomInfluenceRejected):
                m.parse_reply("<- openv/resp: "+reply,0x2321,1)
    def test_transport_command_whitelist_only_external_room_address(self):
        seen=[]
        def runner(argv,**kwargs):
            seen.append(argv[2])
            parts=argv[2].split(";")
            addr=int(parts[1],16)
            data="16" if parts[0]=="writeraw" else "00"
            return subprocess.CompletedProcess(argv,0,
                f"{argv[2]} <- openv/resp: 1;0x{addr:x};{data}\n","")
        client=m.NativeOptolinkClient(run=runner)
        client.write_external(22)
        self.assertEqual(client.read(0x2321,1),b"\x00")
        self.assertEqual(seen,["writeraw;0x2321;16","read;0x2321;1"])
        for action in (lambda:client.write_external(50),
                       lambda:client.write_external(0x74),
                       lambda:client.read(0x1642,10),
                       lambda:client.request("writeraw;0x27a0;01",0x27a0,1)):
            with self.assertRaises(m.RoomInfluenceRejected):action()
        self.assertEqual(len(seen),2)
    def test_safe_virtual_coding_read_addresses_available_for_feedback_preflight(self):
        observations=[]
        def runner(argv,**kwargs):
            observations.append(argv[2])
            addr=int(argv[2].split(';')[1],16)
            return subprocess.CompletedProcess(
                argv,0,f'{argv[2]} <- openv/resp: 1;0x{addr:x};00\n','')
        c=m.NativeOptolinkClient(run=runner)
        self.assertEqual(c.read(0x27A0,1),b'\x00')
        self.assertEqual(c.read(0x27B0,1),b'\x00')
        self.assertEqual(observations,['read;0x27a0;1','read;0x27b0;1'])
        with self.assertRaises(m.RoomInfluenceRejected):
            c.read(0x03ad,1)
        self.assertEqual(len(observations),2)

    def test_no_extra_serial_owner_or_mqtt_sensor_fabrication(self):
        tree=ast.parse(P.read_text())
        imports=set()
        for n in ast.walk(tree):
            if isinstance(n,ast.Import):
                imports.update(x.name.split(".")[0] for x in n.names)
            elif isinstance(n,ast.ImportFrom) and n.module:
                imports.add(n.module.split(".")[0])
        self.assertFalse(imports & {"serial","socket","paho","paramiko","ctypes"})

if __name__=="__main__":
    unittest.main()
