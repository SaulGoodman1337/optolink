"""Pure historic-M16C-looking SRAM value classification, never a code call."""
from __future__ import annotations
import ast
import importlib.util
from pathlib import Path
import sys
import unittest

SCRIPT=Path(__file__).resolve().parents[1]/'tools'/'wb2a-vitotrol-near-rx-rom-candidates.py'
spec=importlib.util.spec_from_file_location('wb2a_near_rx_rom_pointers_test',SCRIPT)
m=importlib.util.module_from_spec(spec)
sys.modules[spec.name]=m
spec.loader.exec_module(m)
PRIVATE=Path('/root/p300-trial-work/research-bundles/p300-fullram-run-20261009T083607Z-144293-bundle.tar.gz')
EXPECTED_SHA='94d5842b6dc5759ecb446a4c617b60b72873b639885d116032f783abdef8431c'

def make_image(*,rom1=0xf23ff, rom2=0xe01f0, desc=b'\x42\x16\x0a\xfe',rxlen=10):
    image=bytearray(b'\x64'*20480)
    image[0x0b6d-0x400:0x0b6d-0x400+4]=desc
    image[0x1642-0x400+3]=rxlen
    for name,address in m.CANDIDATES.items():
        rom={'near_rx_descriptor_0b74':rom1,
             'near_rx_descriptor_0b7e':rom2}.get(name,0xf2420)
        image[address-0x400:address-0x400+3]=rom.to_bytes(3,'little')
        image[address-0x400+3]=0x64
    return bytes(image)

class PointerTests(unittest.TestCase):
    def test_original_archived_79_sram_images_when_available(self):
        try:
            accessible=PRIVATE.is_file()
        except OSError:
            accessible=False
        if not accessible:
            self.skipTest('original root-only P300 archive not available to this test account')
        try:
            contents=PRIVATE.read_bytes()
        except OSError:
            self.skipTest('original archive not readable by non-root CI runner')
        original=m.inspect_verified_archive(contents)
        self.assertEqual(original['source_zip_bundle_sha256'],EXPECTED_SHA)
        self.assertEqual(original['images'],79)
        self.assertEqual(original['descriptor_0b6d_fourbyte_counts'],{'42160afe':79})
        self.assertEqual(original['descriptor_rx_candidate_length_alignment_samples'],79)
        m1={x['label']:x for x in original['near_rx_far_address_lookalikes']}
        self.assertEqual(m1['near_rx_descriptor_0b74']['le24_hex_counts'],{'0xf23ff':79})
        self.assertEqual(m1['near_rx_descriptor_0b7e']['le24_hex_counts'],{'0xe01f0':79})
        self.assertEqual(m1['neighbor_0b5c']['le24_hex_counts']['0xf2420'],75)
        self.assertEqual(m1['neighbor_0b51']['le24_hex_counts']['0xf203f'],75)
        self.assertEqual(m1['neighbor_0b55']['le24_hex_counts']['0xfcbb6'],75)
        self.assertEqual(original['volatile_neighbor_all_three_cochange_indices'],
                         [1,41,60,62])
        self.assertEqual(original['volatile_neighbor_partial_cochange_indices'],[])
        self.assertEqual(original['scheduler_0b6b_in_cochange_samples'],
                         {'01':1,'0a':3})
        self.assertEqual(original['stable_neighbor_modal_sample_counts'],
                         {'0x0b74':79,'0x0b7e':79})
        self.assertTrue(original['non_atomic_fc03_snapshots'])
        self.assertFalse(original['isr_vector20_handler_resolved'])
        self.assertFalse(original['interrupt_can_be_injected_via_optolink'])
        self.assertFalse(original['controller_code_execution_requested'])
        self.assertFalse(original['serial_or_controller_io'])

    def test_stable_far_like_values_do_not_become_callbacks(self):
        result=m.inspect([make_image() for _ in range(3)])
        self.assertEqual(result['images'],3)
        self.assertEqual(result['descriptor_rx_candidate_length_alignment_samples'],3)
        p={x['label']:x for x in result['near_rx_far_address_lookalikes']}
        for name,val in [('near_rx_descriptor_0b74','0xf23ff'),
                         ('near_rx_descriptor_0b7e','0xe01f0')]:
            self.assertEqual(p[name]['le24_hex_counts'],{val:3})
            self.assertEqual(p[name]['m30624_program_address_range_sample_count'],3)
            self.assertEqual(p[name]['fourth_byte_counts'],{'64':3})
            self.assertFalse(p[name]['typed_as_executable_callback'])
            self.assertFalse(p[name]['proven_uart1_rx_parser_address'])
        self.assertTrue(result['candidate_addresses_are_not_call_targets'])

    def test_runtime_status_change_does_not_make_readable_rom(self):
        images=[make_image(),make_image(rom1=0x08000,rom2=0xe01f0)]
        result=m.inspect(images)
        p={x['label']:x for x in result['near_rx_far_address_lookalikes']}
        self.assertEqual(p['near_rx_descriptor_0b74']['m30624_program_address_range_sample_count'],1)
        self.assertEqual(p['near_rx_descriptor_0b74']['distinct_le24_values'],2)
        self.assertFalse(result['physical_rom_word_read_back_verified'])
        self.assertFalse(result['mcu_program_flash_image_present'])

    def test_neighbor_cochange_is_only_observational(self):
        normal=make_image()
        all_changed=bytearray(normal)
        for adr in m.VOLATILE_NEIGHBORS:
            offset=adr-0x400
            all_changed[offset:offset+3]=(0xf203f).to_bytes(3,'little')
        all_changed[m.STATUS_CANDIDATE-0x400]=10
        partial_changed=bytearray(normal)
        partial_changed[0x0b51-0x400:0x0b51-0x400+3]=(
            0xfcbb6).to_bytes(3,'little')
        partial_changed[m.STATUS_CANDIDATE-0x400]=1
        result=m.inspect([normal,bytes(all_changed),bytes(partial_changed)])
        self.assertEqual(result['volatile_neighbor_all_three_cochange_indices'],[2])
        self.assertEqual(result['volatile_neighbor_partial_cochange_indices'],[3])
        self.assertEqual(result['scheduler_0b6b_in_cochange_samples'],{'0a':1})
        self.assertEqual(result['stable_neighbor_modal_sample_counts'],
                         {'0x0b74':3,'0x0b7e':3})
        self.assertTrue(result['cochange_is_not_proof_of_scheduler_or_isr'])
        self.assertFalse(result['isr_vector20_handler_resolved'])

    def test_descriptor_length_mismatch_not_causality(self):
        result=m.inspect([make_image(rxlen=11)])
        self.assertEqual(result['descriptor_rx_candidate_length_alignment_samples'],0)
        self.assertEqual(result['descriptor_0b6d_fourbyte_counts'],{'42160afe':1})
        self.assertFalse(result['isr_vector20_handler_resolved'])

    def test_nonbytes_and_bad_length_rejected(self):
        for images in ([],[None],[b'\x00'*10],[bytearray(20480)],[b'\x00'*20480]*80):
            with self.subTest(item=str(type(images))[:30]),self.assertRaises(m.CandidateRejected):
                m.inspect(images)

    def test_wrong_unpinned_archive_rejected(self):
        with self.assertRaises((m.CandidateRejected,m.audit.EvidenceRejected)):
            m.inspect_verified_archive(b'does not match source hash')
        with self.assertRaises((m.CandidateRejected,m.audit.EvidenceRejected)):
            m.inspect_verified_archive(b'')

    def test_no_io_or_code_invocation_imports(self):
        tree=ast.parse(SCRIPT.read_text())
        imported=set()
        for n in ast.walk(tree):
            if isinstance(n,ast.Import):
                imported.update(x.name.split('.')[0] for x in n.names)
            if isinstance(n,ast.ImportFrom) and n.module:
                imported.add(n.module.split('.')[0])
        self.assertFalse(imported & {'socket','serial','paho','subprocess','ctypes'})
        self.assertEqual(m.ROM,(0xC0000,0xFFFFF))
        self.assertEqual(m.CANDIDATES['near_rx_descriptor_0b74'],0x0B74)

if __name__=='__main__':
    unittest.main()