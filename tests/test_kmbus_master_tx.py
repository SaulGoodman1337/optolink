"""Fail-closed, purely offline checks for KM-Bus TX frame classification."""
import importlib.util
from datetime import datetime,timezone,timedelta
from pathlib import Path
import unittest

P=Path(__file__).resolve().parents[1]/'tools'/'audit-kmbus-master-tx.py'
spec=importlib.util.spec_from_file_location('master_kmbus',P)
m=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
V1=bytes.fromhex('1100330a0101f80449ef')
V2=bytes.fromhex('1100330a0201f80484ca')
X=bytes.fromhex('0100b10a01010106c731')
INTERNAL=bytes.fromhex('2000b30cee0110c211f9e49b')
CLOCK=bytes.fromhex('ff00b316000101200226031004080522065007452112')


def kermit(data):
    c=0
    for b in data:
        c^=b
        for _ in range(8):
            c=(c>>1)^(0x8408 if (c&1) else 0)
    return c


def row(i,frame,status=0):
    mem=bytearray(64)
    mem[m.KM_START:m.KM_START+len(frame)]=frame
    raw=bytearray(11)
    raw[5]=status
    return {
        'index':i,
        'utc':(datetime(2026,10,8,tzinfo=timezone.utc)+timedelta(seconds=3*i)).isoformat(),
        'native_block':raw.hex(),
        'ram_1600':mem[:32].hex(),
        'ram_1620':mem[32:].hex()
    }


class MasterTx(unittest.TestCase):
    def test_source_crc_vectors(self):
        for vector in (V1,V2,X,INTERNAL,CLOCK):
            with self.subTest(hex=vector.hex()):
                self.assertEqual(kermit(vector),0)

    def test_vitotrol_both_slots(self):
        out=m.classify_samples([row(1,V1),row(2,V2)],kermit)
        self.assertEqual(out['vitotrol_identity_query_crc_valid_snapshots'],2)
        self.assertEqual(set(out['vitotrol_identity_query_destinations']),{'0x01','0x02'})
        self.assertFalse(out['installed_vitotrol_verified'])
        self.assertFalse(out['uart1_slave_responses_or_rx_verified'])

    def test_consecutive_dwell_is_not_fabricated_bus_packets(self):
        out=m.classify_samples([row(1,V1),row(2,V1),row(3,V2),row(4,V1)],kermit)
        a=next(x for x in out['header_groups'] if x['header_hex']=='1100330a0101')
        self.assertEqual(a['crc_valid_samples'],3)
        self.assertEqual(a['valid_snapshot_episodes'],2)

    def test_correct_register_pairs(self):
        out=m.classify_samples([row(1,INTERNAL)],kermit)
        g=out['header_groups'][0]
        self.assertEqual(g['target_slot'],'0xee')
        self.assertEqual(g['register_pairs_when_crc_valid'],{'10=c2':1,'11=f9':1})

    def test_corrupted_crc_not_promoted(self):
        b=bytearray(V1)
        b[-1]^=0x40
        out=m.classify_samples([row(1,bytes(b))],kermit)
        self.assertEqual(out['vitotrol_identity_query_crc_valid_snapshots'],0)
        self.assertEqual(out['crc_invalid_or_bad_length_snapshots'],1)

    def test_flame_and_lockout_separate(self):
        r=m.classify_samples([row(1,V1,status=0x40),row(2,V1,status=0x20)],kermit)
        g=r['header_groups'][0]
        self.assertEqual(g['valid_samples_during_lockout'],1)
        self.assertEqual(g['valid_samples_during_flame'],1)

    def test_foreign_class_not_vitotrol(self):
        r=m.classify_samples([row(1,X)],kermit)
        self.assertFalse(r['observed_class_0x11_tx'])
        self.assertEqual(r['vitotrol_identity_query_crc_valid_snapshots'],0)

    def test_bad_geometry_fails(self):
        with self.assertRaises(ValueError):
            m.parse_tx_bytes(b'\x00'*20,kermit)

    def test_bad_sample_order_fails(self):
        with self.assertRaisesRegex(ValueError,'indices'):
            m.classify_samples([row(1,V1),row(3,V1)],kermit)

    def test_bad_time_order_fails(self):
        a=row(1,V1)
        b=row(2,V2)
        b['utc']=a['utc']
        with self.assertRaisesRegex(ValueError,'non-monotonic'):
            m.classify_samples([a,b],kermit)

    def test_no_write_and_no_rpm_claim(self):
        out=m.classify_samples([row(1,V1)],kermit)
        self.assertFalse(out['ram_write_or_thermostat_emulation_authorized'])
        self.assertFalse(out['gfa_p06_tachometer_alias_verified'])
        self.assertFalse(out['any_new_hardware_access_performed'])

    def test_broadcast_non_remote(self):
        out=m.classify_samples([row(1,CLOCK)],kermit)
        self.assertEqual(out['header_groups'][0]['purpose'],'MASTER_BROADCAST_DATA')
        self.assertFalse(out['observed_class_0x11_tx'])


if __name__=='__main__':
    unittest.main()
