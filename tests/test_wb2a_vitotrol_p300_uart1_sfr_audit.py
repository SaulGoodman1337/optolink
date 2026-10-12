"""Proven UART1 M16C SFR bits, temporal-vs-causal bounds, no SFR writes."""
from __future__ import annotations
import ast
import importlib.util
from pathlib import Path
import sys
import unittest

SCRIPT=Path(__file__).resolve().parents[1]/'tools'/'wb2a-vitotrol-p300-uart1-sfr-audit.py'
s=importlib.util.spec_from_file_location('uart1_audit_test',SCRIPT)
m=importlib.util.module_from_spec(s);sys.modules[s.name]=m;s.loader.exec_module(m)

ROOT=Path('/tmp')
REAL=[
 ROOT/'wb2a-vitotrol-uart1-readonly-20261011.log',
 ROOT/'wb2a-vitotrol-uart1-a0-factor-20261011.log',
]

def reading(addr,n,val):
    return f'request;3;0x{addr:04x};{n} <- openv/resp: 1;0x{addr:x};{val}'

def snapshot(phase,s1ric,u1c1):
    return '\n'.join((phase,reading(0x54,1,s1ric),
                     reading(0x3ac,2,'1d'+u1c1)))

def small_fixture():
    return '\n'.join([
        snapshot('BASELINE','40','03'),
        'writeraw;0x27a0;02 <- openv/resp: 1;0x27a0;02',
        'writeraw;0x27b0;03 <- openv/resp: 1;0x27b0;03',
        snapshot('V300_SFR_SAMPLE_1 2026-10-11T14:10:17+02:00','41','07'),
        'writeraw;0x27b0;00 <- openv/resp: 1;0x27b0;00',
        'writeraw;0x27a0;00 <- openv/resp: 1;0x27a0;00'
    ])

class SfrAuditTests(unittest.TestCase):
    def test_local_real_two_logs_attested_when_available(self):
        if not all(x.is_file() for x in REAL):
            self.skipTest('only the private LXC contains the original logs')
        r=m.summarize([(x.name,x.read_text()) for x in REAL])
        self.assertEqual(r['sample_count'],11)
        self.assertTrue(r['uart1_rx_gate_on_sampled'])
        self.assertTrue(r['uart1_rx_gate_off_sampled'])
        self.assertTrue(r['uart1_rx_enabled_even_without_vitotrol'])
        self.assertTrue(r['uart1_rx_disabled_during_remote_enabled_sample'])
        self.assertFalse(r['physical_rx_irq_pending_event_directly_captured'])
        self.assertFalse(r['uart1_rx_exclusively_enabled_by_a0_coding_proven'])
        self.assertFalse(r['real_vitotrol_registered'])
        self.assertEqual(r['controller_sfr_writes_sent'],0)
        self.assertEqual(r['sources'][REAL[0].name]['records'],4)
        self.assertEqual(r['sources'][REAL[1].name]['records'],7)
        self.assertEqual(
            [(x['s1ric_hex'],x['u1c1_hex']) for x in r['samples'][:4]],
            [('40','03'),('41','07'),('41','07'),('41','07')]
        )

    def test_two_states_mean_receiver_and_irq_priority_change(self):
        r=m.summarize([('synthetic',small_fixture())])
        a,b=r['samples']
        self.assertEqual(a['s1ric_priority'],0)
        self.assertFalse(a['u1c1_rx_enabled'])
        self.assertEqual(b['s1ric_priority'],1)
        self.assertTrue(b['u1c1_rx_enabled'])
        self.assertFalse(r['physical_rx_irq_pending_event_directly_captured'])
        self.assertFalse(r['uart1_rx_exclusively_enabled_by_a0_coding_proven'])
        self.assertFalse(r['real_vitotrol_registered'])

    def test_active_baseline_forbids_a0_causal_inference(self):
        log=small_fixture().replace(
            snapshot('BASELINE','40','03'),snapshot('BASELINE','41','07'))
        report=m.summarize([('fixture',log)])
        self.assertTrue(report['uart1_rx_enabled_even_without_vitotrol'])
        self.assertFalse(report['uart1_rx_exclusively_enabled_by_a0_coding_proven'])

    def test_remote_while_disabled_forbids_constant_rx_assumption(self):
        log=small_fixture().replace(
            snapshot('V300_SFR_SAMPLE_1 2026-10-11T14:10:17+02:00','41','07'),
            snapshot('V300_SFR_SAMPLE_1 2026-10-11T14:10:17+02:00','40','03'))
        report=m.summarize([('fixture',log)])
        self.assertTrue(report['uart1_rx_disabled_during_remote_enabled_sample'])
        self.assertFalse(report['real_vitotrol_registered'])

    def test_u1c1_ri_and_s1ric_irq_are_distinct_from_enable(self):
        log=small_fixture().replace(reading(0x54,1,'41'),reading(0x54,1,'49'))
        report=m.summarize([('fixture',log)])
        self.assertTrue(report['physical_rx_irq_pending_event_directly_captured'])
        self.assertEqual(report['samples'][1]['s1ric_priority'],1)
        self.assertTrue(report['samples'][1]['s1ric_irq_pending_observed'])

    def test_wrong_return_address_or_length_rejected(self):
        for bad in (reading(0x54,1,'40').replace('0x54;40','0x55;40'),
                    reading(0x54,1,'4000'),
                    reading(0x54,1,'40').replace('resp: 1;', 'resp: 3;')):
            with self.subTest(bad=bad):
                log=small_fixture().replace(reading(0x54,1,'40'),bad)
                with self.assertRaises(m.SfrEvidenceRejected):
                    m.summarize([('fixture',log)])

    def test_duplicate_sfr_read_rejected(self):
        log=small_fixture().replace(reading(0x54,1,'40'),
                                    reading(0x54,1,'40')+'\n'+reading(0x54,1,'40'))
        with self.assertRaisesRegex(m.SfrEvidenceRejected,'duplicate'):
            m.summarize([('fixture',log)])

    def test_missing_sfr_read_rejected(self):
        log=small_fixture().replace(reading(0x3ac,2,'1d03'),'')
        with self.assertRaisesRegex(m.SfrEvidenceRejected,'missing'):
            m.summarize([('fixture',log)])

    def test_unknown_v300_sample_id_and_duplicate_phase_rejected(self):
        for log in (small_fixture().replace('V300_SFR_SAMPLE_1','V300_SFR_SAMPLE_4'),
                    small_fixture()+'\nBASELINE'):
            with self.subTest(log=log[-45:]),self.assertRaises(m.SfrEvidenceRejected):
                m.summarize([('fixture',log)])

    def test_malformed_prephase_and_source_rejected(self):
        with self.assertRaises(m.SfrEvidenceRejected):
            m.summarize([('a',reading(0x54,1,'40')+'\n'+small_fixture())])
        with self.assertRaises(m.SfrEvidenceRejected):
            m.summarize([('same',small_fixture()),('same',small_fixture())])
        with self.assertRaises(m.SfrEvidenceRejected):
            m.summarize([])

    def test_only_offline_imports_no_mqtt_or_sfr_access(self):
        tree=ast.parse(SCRIPT.read_text())
        mods=set()
        for n in ast.walk(tree):
            if isinstance(n,ast.Import):
                mods.update(x.name.split('.')[0] for x in n.names)
            if isinstance(n,ast.ImportFrom) and n.module:
                mods.add(n.module.split('.')[0])
        self.assertFalse(mods & {'serial','socket','paho','subprocess','os','ctypes'})
        for instruction in ('request;3;0x0054;1','request;3;0x03ac;2'):
            self.assertIn(instruction,m.ALLOWED)
        self.assertFalse(any(x.startswith('writeraw') for x in m.ALLOWED))


if __name__=='__main__':
    unittest.main()
