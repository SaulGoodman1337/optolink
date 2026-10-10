"""Exact real Vitotrol 300 original-TX golden reply tests (OFFLINE only)."""
from __future__ import annotations
import ast
import importlib.util
from pathlib import Path
import sys
import unittest

SOURCE=Path(__file__).resolve().parents[1]/'tools'/'wb2a-vitotrol-offline.py'
spec=importlib.util.spec_from_file_location('v300_original_test_core',SOURCE)
v=importlib.util.module_from_spec(spec)
sys.modules[spec.name]=v
spec.loader.exec_module(v)

DISCOVERY=bytes.fromhex('1100330a0101f80449ef')
REG00=bytes.fromhex('11003109010100ee4f')
PING=bytes.fromhex('1100000801010888')
RX_ORIGINAL_ID=bytes.fromhex('0011b3100101f811f938fa01fb0a1db1')
RX_ORIGINAL_REG00=bytes.fromhex('0011b10a0101001219d5')
RX_ORIGINAL_PONG=bytes.fromhex('001180080101f95c')
RX_ORIGINAL_TEMP_20=bytes.fromhex('0011bf0c01012062aaaa3dfc')
RX_ORIGINAL_TEMP_206=bytes.fromhex('0011bf0c01012064aaaae42a')


class OriginalV300GoldenTests(unittest.TestCase):
    def test_profile_uses_real_identity_not_earlier_emulator_guess(self):
        self.assertEqual(v.IDENTITY_V300_ORIGINAL,b'\x11\x38\x01\x0a')
        self.assertNotEqual(v.IDENTITY_V300_ORIGINAL,v.IDENTITY_V300_SAMPLE)
        self.assertEqual(v.REGISTER_00_V300_ORIGINAL,0x12)
        state=v.original_v300_offline_profile()
        self.assertEqual(state.slot,1)
        self.assertEqual(state.identity,v.IDENTITY_V300_ORIGINAL)
        self.assertEqual(state.register_00,0x12)

    def test_golden_discovery_and_reg00_exact_original_captured_bytes(self):
        state=v.original_v300_offline_profile()
        self.assertIsNone(state.respond(REG00,at_s=1))
        self.assertEqual(state.respond(DISCOVERY,at_s=2),RX_ORIGINAL_ID)
        self.assertEqual(state.respond(REG00,at_s=3),RX_ORIGINAL_REG00)
        self.assertEqual(v.crc16_kermit(RX_ORIGINAL_ID),0)
        self.assertEqual(v.crc16_kermit(RX_ORIGINAL_REG00),0)

    def test_golden_temp_then_pong_then_temp_at_interval(self):
        state=v.original_v300_offline_profile()
        self.assertIsNone(state.respond(PING,at_s=0))
        state.update_temperature(200,at_s=0)
        self.assertEqual(state.respond(DISCOVERY,at_s=0),RX_ORIGINAL_ID)
        self.assertEqual(state.respond(PING,at_s=1),RX_ORIGINAL_TEMP_20)
        state.update_temperature(206,at_s=2)
        self.assertEqual(state.respond(PING,at_s=10),RX_ORIGINAL_PONG)
        self.assertEqual(state.respond(PING,at_s=31),RX_ORIGINAL_TEMP_206)
        self.assertEqual(state.respond(PING,at_s=32),RX_ORIGINAL_PONG)
        self.assertEqual(v.crc16_kermit(RX_ORIGINAL_TEMP_206),0)

    def test_stale_temperature_excludes_forged_liveness(self):
        state=v.original_v300_offline_profile(stale_after_s=45)
        state.respond(DISCOVERY,at_s=0)
        state.update_temperature(200,at_s=0)
        self.assertEqual(state.respond(PING,at_s=1),RX_ORIGINAL_TEMP_20)
        self.assertIsNone(state.respond(PING,at_s=46))
        state.update_temperature(206,at_s=47)
        self.assertEqual(state.respond(PING,at_s=47),RX_ORIGINAL_TEMP_206)

    def test_profile_does_not_spoof_untested_slot_two(self):
        state=v.original_v300_offline_profile()
        slot2=bytes.fromhex(v.KNOWN_MASTER_HEX[1])
        self.assertIsNone(state.respond(slot2,at_s=1))
        self.assertFalse(state.discovered)

    def test_golden_model_never_opens_optolink_or_writes_hardware(self):
        imports=set()
        for node in ast.walk(ast.parse(SOURCE.read_text())):
            if isinstance(node,ast.Import):
                imports.update(x.name.split('.')[0] for x in node.names)
            if isinstance(node,ast.ImportFrom) and node.module:
                imports.add(node.module.split('.')[0])
        self.assertFalse(imports & {'serial','socket','requests','subprocess',
                                    'paho','ctypes'})
        self.assertFalse(v.original_v300_offline_profile().discovered)


if __name__=='__main__':
    unittest.main()
