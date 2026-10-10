"""Validate candidate KM-Bus Vitotrol identity frames; never use controller IO."""
from __future__ import annotations
import ast
import importlib.util
from pathlib import Path
import sys
import unittest

SRC=Path(__file__).resolve().parents[1]/"tools"/"wb2a-vitotrol-offline.py"
spec=importlib.util.spec_from_file_location("wb2a_vitotrol_offline",SRC)
sim=importlib.util.module_from_spec(spec)
sys.modules[spec.name]=sim
spec.loader.exec_module(sim)


class VitotrolOfflineTests(unittest.TestCase):
    def test_exact_wb2a_proven_master_query_crc(self):
        for slot,text in enumerate(sim.KNOWN_MASTER_HEX,start=1):
            frame=bytes.fromhex(text)
            with self.subTest(slot=slot):
                self.assertEqual(sim.crc16_kermit(frame),0)
                self.assertEqual(sim.decode_master_identity_query(frame).slot,slot)
                self.assertEqual(frame[2:4],b"\x33\x0a")
                self.assertEqual(frame[6:8],b"\xf8\x04")

    def test_known_v200_reference_response_exact(self):
        result=sim.model_identity_reply(bytes.fromhex(sim.KNOWN_MASTER_HEX[0]))
        self.assertEqual(result.hex(),"0011b3100101f811f934fa00fb050664")
        self.assertEqual(sim.crc16_kermit(result),0)

    def test_v300_identity_is_explicit_sample_not_proven_hardware(self):
        query=bytes.fromhex(sim.KNOWN_MASTER_HEX[1])
        result=sim.model_identity_reply(query,identity=sim.IDENTITY_V300_SAMPLE)
        decoded=sim.decode_candidate_slave_reply(result)
        self.assertEqual(decoded["slot"],2)
        self.assertEqual(decoded["identity_bytes"],"11380011")
        self.assertFalse(decoded["physical_uart1_rx_verified"])

    def test_crc_roundtrip(self):
        for frame in (bytes.fromhex("0011b3100101f811f934fa00fb05"),
                      b"\x11\x00\x33\x0a\x01\x01\xf8\x04"):
            with self.subTest(frame=frame):
                packet=sim.append_crc(frame)
                self.assertEqual(sim.crc16_kermit(packet),0)
                self.assertEqual(sim.validate_frame(packet),packet)

    def test_corrupt_crc_refuses(self):
        raw=bytearray.fromhex(sim.KNOWN_MASTER_HEX[0])
        raw[-1]^=0x01
        with self.assertRaises(sim.FrameRejected):
            sim.decode_master_identity_query(bytes(raw))

    def test_bad_total_length_refuses_even_if_crc_valid(self):
        frame=bytearray.fromhex(sim.KNOWN_MASTER_HEX[0][:16])
        frame[3]=12
        with self.assertRaises(sim.FrameRejected):
            sim.decode_master_identity_query(sim.append_crc(bytes(frame)))

    def test_not_a_vitotrol_query_rejected(self):
        frame=bytearray.fromhex(sim.KNOWN_MASTER_HEX[0][:16])
        for index,bad in ((0,0x20),(1,0x11),(2,0xB3),(4,0x03),
                          (5,0x00),(6,0x00),(7,0x05)):
            with self.subTest(index=index):
                changed=bytearray(frame)
                changed[index]=bad
                with self.assertRaises(sim.FrameRejected):
                    sim.decode_master_identity_query(sim.append_crc(bytes(changed)))

    def test_bad_slave_identity_rejected(self):
        query=bytes.fromhex(sim.KNOWN_MASTER_HEX[0])
        for bad in (b"",b"\x20\x34\x00\x05",b"\x11\x34\x00"):
            with self.subTest(bad=bad),self.assertRaises(sim.FrameRejected):
                sim.model_identity_reply(query,identity=bad)

    def test_fake_slave_response_opcode_rejected(self):
        good=sim.model_identity_reply(bytes.fromhex(sim.KNOWN_MASTER_HEX[0]))
        corrupted=bytearray(good[:-2])
        corrupted[2]=0x33
        with self.assertRaises(sim.FrameRejected):
            sim.decode_candidate_slave_reply(sim.append_crc(bytes(corrupted)))

    def test_incorrect_register_pairs_rejected(self):
        good=sim.model_identity_reply(bytes.fromhex(sim.KNOWN_MASTER_HEX[0]))
        corrupted=bytearray(good[:-2])
        corrupted[8]=0xF1
        with self.assertRaises(sim.FrameRejected):
            sim.decode_candidate_slave_reply(sim.append_crc(bytes(corrupted)))

    def test_no_controller_or_protocol_writer_in_module(self):
        tree=ast.parse(SRC.read_text())
        modules=set()
        calls=set()
        for node in ast.walk(tree):
            if isinstance(node,ast.Import):
                modules.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node,ast.ImportFrom):
                modules.add((node.module or "").split(".")[0])
            elif isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute):
                calls.add(node.func.attr)
        self.assertFalse(modules & {"serial","paho","socket","subprocess"})
        self.assertFalse(calls & {"write","send","publish","connect","open"})

    def test_invalid_type_rejected(self):
        for value in (None,[1,2],bytearray.fromhex(sim.KNOWN_MASTER_HEX[0])):
            with self.subTest(value=value),self.assertRaises(sim.FrameRejected):
                sim.decode_master_identity_query(value)


    def test_pong_matches_independent_slot_one_and_two_examples(self):
        slot1=bytes.fromhex("1100000801010888")
        self.assertEqual(sim.decode_master_ping(slot1),1)
        self.assertEqual(sim.model_pong(slot1).hex(),"001180080101f95c")
        slot2=sim.append_crc(bytes.fromhex("110000080201"))
        self.assertEqual(sim.model_pong(slot2).hex(),"0011800802019176")

    def test_room_temperature_215c_exact_known_crc(self):
        self.assertEqual(
            sim.model_room_temp_record(1,215).hex(),
            "0011bf0c0101207daaaa6f33")
        self.assertEqual(
            sim.model_room_temp_record(1,200).hex(),
            "0011bf0c01012062aaaa3dfc")

    def test_slot_and_heating_circuit_are_distinct(self):
        self.assertEqual(
            sim.model_room_temp_record(1,215,heating_circuit=3).hex(),
            "0011bf0c0101227daaaa190a")
        with self.assertRaises(sim.FrameRejected):
            sim.model_room_temp_record(2,215,heating_circuit=4)

    def test_state_discovery_then_temperature_then_pong(self):
        state=sim.OfflineVitotrolState(slot=1)
        ping=bytes.fromhex("1100000801010888")
        state.update_temperature(215,at_s=0)
        self.assertIsNone(state.respond(ping,at_s=0))
        reply=state.respond(bytes.fromhex(sim.KNOWN_MASTER_HEX[0]),at_s=0)
        self.assertEqual(reply.hex(),"0011b3100101f811f934fa00fb050664")
        self.assertEqual(state.respond(ping,at_s=1),
                         sim.model_room_temp_record(1,215))
        self.assertEqual(state.respond(ping,at_s=10),
                         sim.model_pong(ping))
        self.assertEqual(state.respond(ping,at_s=31),
                         sim.model_room_temp_record(1,215))

    def test_stale_temperature_stops_reply_not_fake_liveness(self):
        state=sim.OfflineVitotrolState(slot=1,stale_after_s=45)
        query=bytes.fromhex(sim.KNOWN_MASTER_HEX[0])
        ping=bytes.fromhex("1100000801010888")
        state.respond(query,at_s=10)
        state.update_temperature(200,at_s=12)
        self.assertIsNotNone(state.respond(ping,at_s=15))
        self.assertIsNone(state.respond(ping,at_s=58))
        state.update_temperature(215,at_s=59)
        self.assertEqual(state.respond(ping,at_s=59),
                         sim.model_room_temp_record(1,215))

    def test_wrong_slot_and_bad_crc_cannot_answer(self):
        state=sim.OfflineVitotrolState(slot=1)
        query2=bytes.fromhex(sim.KNOWN_MASTER_HEX[1])
        self.assertIsNone(state.respond(query2,at_s=1))
        self.assertFalse(state.discovered)
        broken=bytearray.fromhex(sim.KNOWN_MASTER_HEX[0])
        broken[-1]^=1
        with self.assertRaises(sim.FrameRejected):
            state.respond(bytes(broken),at_s=1)

    def test_controller_status_record_accepted_but_never_inferred(self):
        state=sim.OfflineVitotrolState(slot=1)
        record=sim.append_crc(bytes.fromhex("1100bf0a01011d00"))
        self.assertIsNone(state.respond(record,at_s=2))
        self.assertFalse(state.discovered)
        self.assertEqual(state.last_status_record["record"],0x1d)
        self.assertFalse(state.last_status_record["decoded_status_verified"])
        self.assertIsNone(state.respond(bytes.fromhex("1100000801010888"),at_s=3))

    def test_status_rejects_invalid_record_or_crc(self):
        state=sim.OfflineVitotrolState()
        for record in (0x19,0x20):
            frame=sim.append_crc(bytes([0x11,0,0xbf,10,1,1,record,0]))
            with self.assertRaises(sim.FrameRejected):
                state.respond(frame,at_s=1)
        good=bytearray(sim.append_crc(bytes.fromhex("1100bf0a01011c00")))
        good[-1]^=1
        with self.assertRaises(sim.FrameRejected):
            state.respond(bytes(good),at_s=1)

    def test_clock_rewind_does_not_refresh_temperature_or_state(self):
        state=sim.OfflineVitotrolState()
        query=bytes.fromhex(sim.KNOWN_MASTER_HEX[0])
        state.respond(query,at_s=10)
        state.update_temperature(215,at_s=10)
        for clock in (9,):
            with self.assertRaises(sim.FrameRejected):
                state.respond(query,at_s=clock)
            with self.assertRaises(sim.FrameRejected):
                state.update_temperature(220,at_s=clock)
        self.assertEqual(state.temperature,215)
        self.assertEqual(state.updated_at,10)

    def test_bounded_temp_and_monotonic_age(self):
        state=sim.OfflineVitotrolState(slot=1)
        for value in (None,True,49,351,21.5):
            with self.subTest(value=value),self.assertRaises(sim.FrameRejected):
                state.update_temperature(value,at_s=10)
        for t in (-1,float("inf"),float("nan")):
            with self.subTest(t=t),self.assertRaises(sim.FrameRejected):
                state.respond(bytes.fromhex(sim.KNOWN_MASTER_HEX[0]),at_s=t)


if __name__=="__main__":
    unittest.main()
