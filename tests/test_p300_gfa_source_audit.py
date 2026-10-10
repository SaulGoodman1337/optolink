"""Tests for offline source membership and hypothesis boundaries; no device I/O."""
import importlib.util
from pathlib import Path
import unittest

p = Path(__file__).parents[1] / 'tools/audit-p300-gfa-sources.py'
spec = importlib.util.spec_from_file_location('gfa_audit', p)
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


def event(eid='8395', devices='VDensHO1', device_ids='60', **extra):
    row = {k: '' for k in audit.EXPORT_FIELDS}
    row.update(event_id=eid, devices=devices, device_ids=device_ids,
               fc_read='Virtual_READ', address='0x7650')
    row.update(extra)
    return row


def links(*ids):
    return [dict(device='VDensHO1', device_id='60', event_id=i) for i in ids]


class SourceAuditTests(unittest.TestCase):
    def test_exact_membership(self):
        self.assertTrue(audit.is_target(event()))
        self.assertTrue(audit.is_target(event(devices='Other;VDensHO1;X')))

    def test_family_substring_is_not_membership(self):
        self.assertFalse(audit.is_target(event(devices='VDensHO1_100')))

    def test_gfa_label_does_not_make_virtual_read(self):
        row = event('8230', fc_read='GFA_READ', name_de='Geblaese Drehzahl Ist')
        out = audit.summarize_metadata([row], links('8230'))
        self.assertEqual(out['label_search']['exact_target_matches'], 0)
        self.assertEqual(out['target_read_function_counts'], {'GFA_READ': 1})

    def test_foreign_fan_is_not_local(self):
        row = event('4722', devices='VBC550S', device_ids='100', name_de='Drehzahl Geblaese Ist')
        out = audit.summarize_metadata([row], [])
        self.assertEqual(out['label_search']['global_matches'], 1)
        self.assertEqual(out['label_search']['exact_target_matches'], 0)
        self.assertFalse(out['selected_events'][0]['exact_target_member'])

    def test_missing_schema_rejected(self):
        with self.assertRaises(ValueError): audit.summarize_metadata([{'event_id': '1'}], [])

    def test_link_disagreement_rejected(self):
        with self.assertRaises(ValueError): audit.summarize_metadata([event()], [])

    def test_duplicate_event_ids_rejected(self):
        with self.assertRaises(ValueError): audit.summarize_metadata([event(), event()], links('8395'))

    def test_profile_id_mismatch_rejected(self):
        with self.assertRaises(ValueError):
            audit.summarize_metadata([event(device_ids='61')], links('8395'))

    def test_same_address_different_functions_kept_separate(self):
        rows = [event('8178', address='0x4009', fc_read='GFA_READ', conversion_factor='30'),
                event('8259', address='0x4009', fc_read='GFA_READ', conversion_factor='0.3922')]
        out = audit.summarize_metadata(rows, links('8178', '8259'))
        self.assertEqual(out['target_event_links'], 2)
        self.assertEqual(out['target_address_count'], 1)
        self.assertEqual(len(out['selected_events']), 2)

    def test_consecutive_duplicates_only(self):
        self.assertEqual(audit.collapse(['00','20','20','60','20']), ['00','20','60','20'])

    def test_missing_private_input_not_called_negative(self):
        self.assertNotIn('serial', audit.__dict__)
        self.assertNotIn('subprocess', audit.__dict__)


if __name__ == '__main__': unittest.main()
