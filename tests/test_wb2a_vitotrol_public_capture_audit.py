"""Fixture tests for an external, source-attributed ORIGINAL Vitotrol capture.

A compatible source is openv/openv#387 comment 435796559 (log.zip).
Tests never access a real boiler, serial port, MQTT broker or network.
"""
import ast
from io import BytesIO
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile

SRC=Path(__file__).resolve().parents[1]/'tools'/'wb2a-vitotrol-public-capture-audit.py'
spec=importlib.util.spec_from_file_location('wb2a_vitotrol_capture_audit',SRC)
audit=importlib.util.module_from_spec(spec)
sys.modules[spec.name]=audit
spec.loader.exec_module(audit)

# Each CRC-validated original from the public binary (NOT the local WB2A).
ORIGINAL_ID=bytes.fromhex('0011b3100101f811f938fa01fb0a1db1')
ORIGINAL_REG0=bytes.fromhex('0011b10a0101001219d5')
ORIGINAL_ROOM20=bytes.fromhex('0011bf0c01012062aaaa3dfc')
ORIGINAL_ROOM206=bytes.fromhex('0011bf0c01012064aaaae42a')
ORIGINAL_RECORD15=bytes.fromhex('0011bf11010115f9ab5aa0aaaa92aadf0d')
ORIGINAL_PONG=bytes.fromhex('001180080101f95c')


class OriginalCaptureAuditTests(unittest.TestCase):
    def test_external_frames_validate_and_report_evidence(self):
        data=(ORIGINAL_ID + ORIGINAL_REG0 + ORIGINAL_RECORD15
              + ORIGINAL_PONG + ORIGINAL_ROOM20 + ORIGINAL_ROOM206 +
              ORIGINAL_PONG + bytes.fromhex('00118008'))
        result=audit.parse_external_slave_tx(data)
        self.assertEqual(result['crc_valid_complete_frames'],7)
        self.assertEqual(result['command_counts'],{'80':2,'B1':1,'B3':1,'BF':3})
        self.assertEqual(result['bf_record_counts'],{'15':1,'20':2})
        self.assertEqual(result['f8_fb_identities'],['1138010a'])
        self.assertEqual(result['reg00_values'],[0x12])
        self.assertEqual(result['room_temp_tenths_c'],[200,206])
        self.assertEqual(result['trailing_incomplete_hex'],'00118008')
        self.assertFalse(result['physical_wb2a_slave_rx_verified'])
        self.assertFalse(result['timestamps_available'])

    def test_rejects_crc_mismatch_without_resynchronization(self):
        frame=bytearray(ORIGINAL_PONG)
        frame[-1]^=1
        for data in (bytes(frame),ORIGINAL_PONG + bytes(frame) + ORIGINAL_PONG):
            with self.subTest(data=data.hex()),self.assertRaises(audit.core.FrameRejected):
                audit.parse_external_slave_tx(data)

    def test_rejects_invalid_boundary_even_if_followed_by_valid_frames(self):
        for data in (b'\xff'+ORIGINAL_ID,ORIGINAL_PONG+b'\xff'+ORIGINAL_ID,
                     ORIGINAL_PONG+b'\x00\x12'):
            with self.subTest(data=data.hex()),self.assertRaises(audit.core.FrameRejected):
                audit.parse_external_slave_tx(data)

    def test_rejects_incomplete_large_frame(self):
        with self.assertRaises(audit.core.FrameRejected):
            audit.parse_external_slave_tx(ORIGINAL_PONG+ORIGINAL_RECORD15[:12])

    def test_zip_reader_validates_exact_member_and_provenance(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'external.zip'
            with zipfile.ZipFile(p,'w') as z:
                z.writestr('log.bin',ORIGINAL_ID+ORIGINAL_REG0)
            expected=audit.hashlib.sha256(p.read_bytes()).hexdigest()
            report=audit.audit_zip(p,expected_sha256=expected)
            self.assertEqual(report['crc_valid_complete_frames'],2)
            self.assertEqual(report['archive_sha256'],expected)
            with self.assertRaises(audit.core.FrameRejected):
                audit.audit_zip(p,expected_sha256='0'*64)
            with zipfile.ZipFile(p,'w') as z:
                z.writestr('not-a-capture',ORIGINAL_ID)
            with self.assertRaises(audit.core.FrameRejected):
                audit.audit_zip(p)

    def test_imports_remain_offline_and_without_device_writers(self):
        tree=ast.parse(SRC.read_text())
        modules=set()
        calls=set()
        for node in ast.walk(tree):
            if isinstance(node,ast.Import):
                modules.update(a.name.split('.')[0] for a in node.names)
            elif isinstance(node,ast.ImportFrom):
                modules.add((node.module or '').split('.')[0])
            elif isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute):
                calls.add(node.func.attr)
        self.assertFalse(modules & {'serial','paho','socket','subprocess','requests'})
        self.assertFalse(calls & {'write','send','publish','connect','open','extract','extractall'})


if __name__=='__main__':
    unittest.main()
