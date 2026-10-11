"""Synthetic-only master TX RAM classifier, not physical-wire evidence."""
from __future__ import annotations
import ast
import importlib.util
from pathlib import Path
import sys
import unittest

SOURCE=Path(__file__).resolve().parents[1]/'tools'/'wb2a-vitotrol-optolink-tx-audit.py'
spec=importlib.util.spec_from_file_location('wb2a_tx_audit_testmod',SOURCE)
audit=importlib.util.module_from_spec(spec)
sys.modules[spec.name]=audit
spec.loader.exec_module(audit)

SLOT1=bytes.fromhex('1100330a0101f80449ef')
SLOT2=bytes.fromhex('1100330a0201f80484ca')


def block(frame):
    return frame.ljust(32,b'\x00')


class TxAuditTests(unittest.TestCase):
    def test_real_historical_master_discoveries_match_crc_and_slots(self):
        for frame,slot in ((SLOT1,1),(SLOT2,2)):
            with self.subTest(slot=slot):
                r=audit.audit_window(block(frame))
                self.assertTrue(r['crc16_kermit_valid'])
                self.assertTrue(r['km_bus_master_format_plausible'])
                self.assertTrue(r['vitotrol_discovery_shape'])
                self.assertEqual(r['discovery_slot'],slot)
                self.assertEqual(r['candidate_register'],'f8')
                self.assertEqual(r['candidate_register_length'],4)
                self.assertFalse(r['physical_km_bus_wire_observed'])
                self.assertFalse(r['controller_vitotrol_acceptance_verified'])
                self.assertFalse(r['ram_write_or_irq_injection_authorized'])

    def test_live_20261011_0826_tx_class20_b3_crc_valid_not_vitotrol(self):
        # Captured in a gated FC03/32 diagnostic while controller B0=03.
        # Context is bounded live evidence, not proof of physical bus output.
        actual=bytes.fromhex('2000b30cee0110c21100aaf1041105080622070405ac00000000000000000000')
        report=audit.audit_window(actual)
        self.assertTrue(report['crc16_kermit_valid'])
        self.assertTrue(report['km_bus_master_format_plausible'])
        self.assertEqual(report['destination_class'],'20')
        self.assertEqual(report['source_class'],'00')
        self.assertEqual(report['command_byte'],'b3')
        self.assertEqual(report['candidate_frame_hex'],'2000b30cee0110c21100aaf1')
        self.assertFalse(report['vitotrol_discovery_shape'])
        self.assertFalse(report['participant_class_semantics_verified'])
        self.assertFalse(report['physical_km_bus_wire_observed'])

    def test_crc_corruption_never_promoted_to_wire_frame(self):
        x=bytearray(block(SLOT1));x[9]^=1
        r=audit.audit_window(bytes(x))
        self.assertFalse(r['crc16_kermit_valid'])
        self.assertFalse(r['vitotrol_discovery_shape'])
        self.assertIsNone(r['discovery_slot'])

    def test_torn_buffer_length_too_short_does_not_claim_discovery(self):
        for length in (0,7,33,255):
            with self.subTest(length=length):
                x=bytearray(block(SLOT1));x[3]=length
                r=audit.audit_window(bytes(x))
                self.assertIsNone(r['candidate_frame_hex'])
                self.assertFalse(r['vitotrol_discovery_shape'])

    def test_trailing_stale_buffer_bytes_are_not_synthetic_reply(self):
        data=SLOT2+bytes.fromhex('f801fb010110fe23d8')
        r=audit.audit_window(block(data))
        self.assertTrue(r['vitotrol_discovery_shape'])
        self.assertEqual(r['candidate_frame_hex'],SLOT2.hex())
        self.assertNotIn('f801fb01',r['candidate_frame_hex'])

    def test_nondescriptor_frame_must_not_pass_vitotrol_filter(self):
        # CRC-valid class-01 response, not a master-issued Vitotrol request.
        slave=bytes.fromhex('0001b10a010110fe23d8')
        r=audit.audit_window(block(slave))
        self.assertTrue(r['crc16_kermit_valid'])
        self.assertFalse(r['km_bus_master_format_plausible'])
        self.assertFalse(r['vitotrol_discovery_shape'])

    def test_only_exact_32_byte_block_admitted(self):
        for raw in (None,True,'a'*64,b'',b'\x00'*31,b'\x00'*33):
            with self.subTest(raw=repr(raw)[:40]),self.assertRaises(audit.TxAuditRejected):
                audit.audit_window(raw)

    def test_no_io_modules_loaded_by_standalone_classifier(self):
        tree=ast.parse(SOURCE.read_text())
        imports=set()
        for n in ast.walk(tree):
            if isinstance(n,ast.Import):
                imports.update(x.name.split('.')[0] for x in n.names)
            elif isinstance(n,ast.ImportFrom) and n.module:
                imports.add(n.module.split('.')[0])
        self.assertFalse(imports & {'socket','serial','requests','subprocess',
                                     'paho','smbus','ctypes'})


if __name__=='__main__':
    unittest.main()
