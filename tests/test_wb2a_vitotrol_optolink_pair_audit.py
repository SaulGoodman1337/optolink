"""Real copied read-only fixture bytes, with synthetic rejection cases."""
from __future__ import annotations
import ast
import importlib.util
from pathlib import Path
import sys
import unittest

SCRIPT=Path(__file__).resolve().parents[1]/'tools'/'wb2a-vitotrol-optolink-pair-audit.py'
spec=importlib.util.spec_from_file_location('wb2a_pair_audit_test',SCRIPT)
mod=importlib.util.module_from_spec(spec)
sys.modules[spec.name]=mod
spec.loader.exec_module(mod)

# 08:46:24 11-Oct-2026: verified 5394.409ms P300 FC03, A0=00 B0=00.
BASE=bytes.fromhex(
    '0100b10a01010106c731aaf10411050806410758c5de000000000000000000000000'
    '0001b10a010110fe23d8fa01fb0122d10000000000000000000000000000')
# 08:48:26 11-Oct-2026: verified 5314.338ms P300 FC03, A0=01 B0=03.
REMOTE=bytes.fromhex(
    '0100b10a01010106c7314d8e0411050806410758c5de000000000000000000000000'
    '0001b10a010110fe23d8fa01fb0122d10000000000000000000000000000')


class PairAudit(unittest.TestCase):
    def test_two_actual_paired_live_sessions_contain_class01_not_remote(self):
        for name,raw in (('A0_00_B0_00',BASE),('A0_01_B0_03',REMOTE)):
            with self.subTest(name=name):
                r=mod.inspect_pair(raw)
                self.assertEqual(len(raw),64)
                self.assertTrue(r['master_tx']['crc16_kermit_valid'])
                self.assertEqual(r['master_tx']['destination_class'],'01')
                self.assertTrue(r['candidate_rx_crc_valid'])
                self.assertEqual(r['candidate_rx']['src_class'],'01')
                self.assertFalse(r['candidate_vitotrol_class11_reply'])
                self.assertFalse(r['candidate_vitotrol_class11_discovery'])
                self.assertFalse(r['physical_km_bus_wire_capture'])
                self.assertFalse(r['remote_accepted_by_regulator'])
                self.assertFalse(r['controller_write_authorized'])

    def test_differential_does_not_infer_controlled_effect_from_same_frames(self):
        d=mod.compare_pair_reads(BASE,REMOTE)
        self.assertEqual(d['normal_master_class'],'01')
        self.assertEqual(d['remote_expected_master_class'],'01')
        self.assertEqual(d['normal_rx_source_class'],'01')
        self.assertEqual(d['remote_expected_rx_source_class'],'01')
        self.assertTrue(d['tx_master_frame_same'])
        self.assertTrue(d['rx_candidate_frame_same'])
        self.assertFalse(d['any_class11_seen_in_ram'])
        self.assertFalse(d['same_physical_bus_instant_for_both_reads'])
        self.assertFalse(d['actual_hardware_window_proven_by_offline_bytes'])
        self.assertFalse(d['controller_remote_acceptance_proven'])
        self.assertFalse(d['causal_effect_of_a0b0_coding_proven'])

    def test_crc_bad_rx_is_not_registered_or_remote(self):
        bad=bytearray(REMOTE)
        bad[32+11]^=0x80
        r=mod.inspect_pair(bytes(bad))
        self.assertIsNone(r['candidate_rx'])
        self.assertFalse(r['candidate_rx_crc_valid'])
        self.assertTrue(r['candidate_rx_rejection'])
        self.assertFalse(r['remote_accepted_by_regulator'])

    def test_invalid_length_nonbytes_and_swapped_blocks_refused(self):
        for raw in (None,'a'*128,True,BASE[:32],BASE[:63],BASE+b'\x00'):
            with self.subTest(input=repr(raw)[:20]),self.assertRaises(mod.PairRejected):
                mod.inspect_pair(raw)
        wrong=mod.inspect_pair(BASE[32:]+BASE[:32])
        self.assertFalse(wrong['master_tx']['km_bus_master_format_plausible'])
        self.assertIsNone(wrong['candidate_rx'])

    def test_unrelated_tx_discovery_cannot_independently_prove_acceptance(self):
        tx=bytes.fromhex('1100330a0101f80449ef').ljust(32,b'\x00')
        case=mod.inspect_pair(tx+BASE[32:])
        self.assertTrue(case['candidate_vitotrol_class11_discovery'])
        self.assertFalse(case['candidate_vitotrol_class11_reply'])
        self.assertFalse(case['remote_accepted_by_regulator'])

    def test_parser_no_network_controller_or_shell_modules(self):
        src=ast.parse(SCRIPT.read_text())
        imports=set()
        for item in ast.walk(src):
            if isinstance(item,ast.Import):
                imports.update(x.name.split('.')[0] for x in item.names)
            elif isinstance(item,ast.ImportFrom) and item.module:
                imports.add(item.module.split('.')[0])
        self.assertFalse(imports & {'socket','serial','paho','subprocess',
                                     'requests','os','ctypes'})


if __name__=='__main__':
    unittest.main()
