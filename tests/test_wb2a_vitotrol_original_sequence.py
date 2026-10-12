"""CRC/ordering/regression fixtures for ORIGINAL Vitotrol 300 TX coverage."""
from __future__ import annotations
import ast
import importlib.util
from pathlib import Path
import sys
import unittest

SOURCE=Path(__file__).resolve().parents[1]/'tools'/'wb2a-vitotrol-original-sequence.py'
spec=importlib.util.spec_from_file_location('v300_sequence_tests',SOURCE)
sequence=importlib.util.module_from_spec(spec)
sys.modules[spec.name]=sequence
spec.loader.exec_module(sequence)

ID=bytes.fromhex('0011b3100101f811f938fa01fb0a1db1')
REG=bytes.fromhex('0011b10a0101001219d5')
PONG=bytes.fromhex('001180080101f95c')
T20=bytes.fromhex('0011bf0c01012062aaaa3dfc')
T206=bytes.fromhex('0011bf0c01012064aaaae42a')
RECORDS=tuple(bytes.fromhex(x) for x in (
    '0011bf11010115f9ab5aa0aaaa92aadf0d',
    '0011bf1101011566ab4dabaaaa92aa7a35',
    '0011bf11010115bfab4dabaaaa92aa126c',
))

class OriginalSequenceTests(unittest.TestCase):
    def test_exact_replay_of_external_source_backed_frames(self):
        stream=b''.join([ID,REG,*RECORDS,PONG,T20,PONG,T206,PONG])+bytes.fromhex('00118008')
        frames,tail=sequence.split_original_tx(stream)
        report=sequence.summarize_original_frames(frames,tail)
        self.assertEqual(report['total_complete_frames'],10)
        self.assertEqual(report['byte_exact_modelled_frame_count'],7)
        self.assertEqual(report['modelled_counts_by_command'],
                         {'80':3,'b1':1,'b3':1,'bf':2})
        self.assertEqual(report['unmodelled_counts_by_command_record'],{'bf/15':3})
        self.assertEqual(report['bf15_unique_8byte_xor_projections'],3)
        self.assertEqual(report['bf15_xor_constant_positions'],
                         {'1':'01','4':'00','5':'00','6':'38','7':'00'})
        self.assertFalse(report['bf15_emission_implemented'])
        self.assertFalse(report['rolling_code_semantics_proven'])
        self.assertFalse(report['optolink_injection_authorized'])
        self.assertFalse(report['wall_clock_timing_available'])
        self.assertFalse(report['external_master_queries_recorded'])
        self.assertTrue(report['no_hardware_io'])
        self.assertEqual(report['trailing_incomplete_hex'],'00118008')

    def test_original_archive_hashes_are_pinned(self):
        self.assertEqual(sequence.ZIP_SHA256,
          'eb398ec9b4b174354425d2615f7d76937acaf5e0e1cde4df154fee78425bab93')
        self.assertEqual(sequence.RAW_SHA256,
          'b6d5b0526d0b0a96e5bc3369de639763ef95db9786ee51a1c0b26ecbb229d068')

    def test_corrupt_original_crc_refuses_whole_sequence(self):
        damaged=bytearray(ID+PONG);damaged[4]=0
        with self.assertRaises(sequence.core.FrameRejected):
            sequence.split_original_tx(bytes(damaged))
        damaged=bytearray(ID+PONG);damaged[-1]^=1
        with self.assertRaises(sequence.core.FrameRejected):
            sequence.split_original_tx(bytes(damaged))

    def test_unknown_middle_byte_does_not_resynchronize(self):
        with self.assertRaises(sequence.core.FrameRejected):
            sequence.split_original_tx(ID+b'\xff'+PONG)

    def test_original_slot2_frame_is_not_a_slot1_capture(self):
        slot2=sequence.core.append_crc(bytes.fromhex('001180080201'))
        with self.assertRaises(sequence.core.FrameRejected):
            sequence.split_original_tx(slot2)

    def test_truncated_complete_frame_not_accepted_as_short_tail(self):
        data=ID+PONG[:5]
        frames,tail=sequence.split_original_tx(data)
        self.assertEqual(frames,(ID,))
        self.assertEqual(tail,PONG[:5])
        with self.assertRaises(sequence.core.FrameRejected):
            sequence.split_original_tx(ID+PONG[:7]+b'\x00')
        with self.assertRaises(sequence.core.FrameRejected):
            sequence.split_original_tx(ID+b'\xff\xaa\x80\x08')

    def test_mutated_identity_crc_valid_cannot_pass_golden(self):
        body=bytearray(ID[:-2]);body[9]=0x34
        fake=sequence.core.append_crc(bytes(body))
        frames,_=sequence.split_original_tx(fake)
        with self.assertRaises(sequence.core.FrameRejected):
            sequence.summarize_original_frames(frames,b'')

    def test_bf15_never_accepted_for_write_replay(self):
        frame=RECORDS[0]
        self.assertEqual(sequence.core.crc16_kermit(frame),0)
        decoded=sequence.core.decode_candidate_slave_record_15(frame)
        self.assertFalse(decoded['controller_write_authorized'])
        self.assertFalse(decoded['command_semantics_verified_for_wb2a'])
        self.assertFalse(hasattr(sequence.core,'model_record_15'))

    def test_no_external_controller_io_capability_in_source(self):
        imports=set()
        for node in ast.walk(ast.parse(SOURCE.read_text())):
            if isinstance(node,ast.Import):
                imports.update(x.name.split('.')[0] for x in node.names)
            if isinstance(node,ast.ImportFrom) and node.module:
                imports.add(node.module.split('.')[0])
        self.assertFalse(imports & {'socket','serial','paho','requests',
                                    'subprocess','ctypes','paramiko'})


if __name__=='__main__':
    unittest.main()
