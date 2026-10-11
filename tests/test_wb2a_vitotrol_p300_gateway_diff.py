import importlib.util
from pathlib import Path
import sys
import unittest
P=Path(__file__).resolve().parents[1]/'tools'/'wb2a-vitotrol-p300-gateway-diff.py'
spec=importlib.util.spec_from_file_location('gateway_diff_test',P)
m=importlib.util.module_from_spec(spec);sys.modules[spec.name]=m;spec.loader.exec_module(m)

REQ=[
 ('request;101;0x0000;8','0x00','06f955aacb346a95'),
 ('request;101;0x00f8;8','0xf8','00ffcb34b8476a95'),
 ('request;99;0x0000;2','0x00','ff00'),
 ('request;3;0x0b60;32','0xb60','0064646464646464646464010542160afe050000ff230f64646401006464f001'),
 ('request;3;0x1660;32','0x1660','0000000000000000000006000100000000000000000000000000000000000000'),
 ('request;3;0x161a;32','0x161a','0100b10a01010106c7314d8e0411051006310723297d00000000000000000000'),
 ('read;0x0a5c;4','0xa5c','00000000')
]
def captured():
    lines=['BASELINE']
    for cmd,addr,data in REQ:lines.append(f'{cmd} <- openv/resp: 1;{addr};{data}')
    lines+=['writeraw;0x27a0;02 <- openv/resp: 1;0x27a0;02',
            'writeraw;0x27b0;03 <- openv/resp: 1;0x27b0;03']
    for i in (1,2):
        lines.append(f'REMOTE_SAMPLE_{i} 2026-10-11T10:33:12+02:00')
        for cmd,addr,data in REQ:
            lines.append(f'{cmd} <- openv/resp: 1;{addr};{data}')
        lines.append('read;0x089c;1 <- openv/resp: 1;0x89c;03')
    lines+=['writeraw;0x27b0;00 <- openv/resp: 1;0x27b0;00',
            'writeraw;0x27a0;00 <- openv/resp: 1;0x27a0;00']
    return lines

class GatewayDiffTests(unittest.TestCase):
    def test_live_original_when_present(self):
        live=Path('/tmp/wb2a-vitotrol-gateway-diff-20261011.log')
        if not live.exists():self.skipTest('optional local original live log')
        d=m.inspect(live.read_text().splitlines())
        self.assertFalse(d['gateway_data_changed_when_v300_requested'])
        self.assertFalse(d['indirect_read_changed'])
        self.assertFalse(d['descriptor_0b6d_changed'])
        self.assertFalse(d['remote_swindex_nonzero_seen'])
        self.assertFalse(d['remote_sensor_valid_seen'])
        self.assertTrue(d['controller_coding_acknowledged_and_restored'])
    def test_synthetic_full_three_phase_evidence(self):
        d=m.inspect(captured())
        self.assertFalse(d['gateway_data_changed_when_v300_requested'])
        self.assertFalse(d['km_bus_slave_rx_ingress_verified'])
        self.assertFalse(d['firmware_rx_commit_verified'])
    def test_changed_gateway_detected_without_claiming_acceptance(self):
        lines=captured()
        idx=lines.index('REMOTE_SAMPLE_1 2026-10-11T10:33:12+02:00')+1
        lines[idx]=lines[idx].replace('06f955aa','07f955aa')
        d=m.inspect(lines)
        self.assertTrue(d['gateway_data_changed_when_v300_requested'])
        self.assertFalse(d['km_bus_slave_rx_ingress_verified'])
    def test_no_valid_restore_rejected(self):
        with self.assertRaises(m.EvidenceRejected):
            m.inspect(captured()[:-1])
    def test_missing_phase_or_truncated_block_rejected(self):
        x=captured()
        x.remove('REMOTE_SAMPLE_2 2026-10-11T10:33:12+02:00')
        with self.assertRaises(m.EvidenceRejected):m.inspect(x)
        x=captured();x[x.index('REMOTE_SAMPLE_1 2026-10-11T10:33:12+02:00')+1]=            x[x.index('REMOTE_SAMPLE_1 2026-10-11T10:33:12+02:00')+1].replace('06f955aacb346a95','06')
        with self.assertRaises(m.EvidenceRejected):m.inspect(x)
    def test_wrong_read_address_and_rejected_code(self):
        x=captured();idx=x.index('REMOTE_SAMPLE_1 2026-10-11T10:33:12+02:00')+1
        x[idx]=x[idx].replace('1;0x00;','1;0x01;')
        with self.assertRaises(m.EvidenceRejected):m.inspect(x)
        x=captured();x[idx]=x[idx].replace('1;0x00;','3;0x00;')
        with self.assertRaises(m.EvidenceRejected):m.inspect(x)
    def test_duplicate_sample_rejected(self):
        x=captured();idx=x.index('REMOTE_SAMPLE_1 2026-10-11T10:33:12+02:00')+1
        x.insert(idx,x[idx])
        with self.assertRaises(m.EvidenceRejected):m.inspect(x)

if __name__=='__main__':unittest.main()
