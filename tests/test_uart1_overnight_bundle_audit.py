"""Pure offline regressions for KM-Bus identification and P300 trace checks."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

SCRIPT=Path(__file__).resolve().parents[1]/'tools'/'audit-uart1-overnight-bundle.py'
spec=importlib.util.spec_from_file_location('overnight_kmbus_audit', SCRIPT)
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

VECTORS=[
    '0100b10a01010106c731',
    '2000b30cee0110c211f9e49b',
    'ff00b316000101200226031004080522065007452112',
]


def wire_answer(function,address,data):
    n=len(data)
    body=bytes([1,function,address>>8,address&255,n])+data
    return bytes([6,65,5+n])+body+bytes([((5+n)+sum(body))&255])


def synthetic_trace():
    payload={
        'native_block':bytes.fromhex('00c2ba0000010000000001'),
        'dma0_0020':bytes.fromhex('1b160000aa0300000800000015000000'),
        'ram_1600':bytes.fromhex('ffffffffff000000ffffff84110000251d7f150f00e5942003000100b10a0101'),
        'ram_1620':bytes.fromhex('0106c731aaf10408052206500745211200000000000000000000000000000000')
    }
    sample={'index':1,**{key:value.hex() for key,value in payload.items()}}
    trace=[{'direction':'RX','hex':'05','t_monotonic':-1.0} for _ in range(24)]
    for i,(tx,fc,addr,size,key) in enumerate(module.FRAMES):
        t=i*10
        trace.extend([
            {'direction':'TX','hex':tx,'t_monotonic':t+1},
            {'direction':'RX','hex':wire_answer(fc,addr,payload[key]).hex(),'t_monotonic':t+2},
            {'direction':'TX','hex':'06','t_monotonic':t+3}
        ])
    trace += [{'direction':'RX','hex':'05','t_monotonic':100.0} for _ in range(14)]
    return sample,trace


class OfflineKMTests(unittest.TestCase):
    def test_three_real_crc_vectors(self):
        for message in VECTORS:
            with self.subTest(frame=message[:8]):
                self.assertEqual(module.kermit(bytes.fromhex(message)),0)

    def test_crc_detects_corruption(self):
        message=bytearray.fromhex(VECTORS[2])
        message[8]^=1
        self.assertNotEqual(module.kermit(message),0)

    def test_bcd_fields(self):
        for raw,expected in [(0x08,8),(0x09,9),(0x10,10),
                             (0x22,22),(0x23,23),(0x45,45),(0x59,59)]:
            self.assertEqual(module.bcd(raw),expected)

    def test_invalid_bcd(self):
        for raw in (0xFA,0x3A,0xAA):
            with self.assertRaises(ValueError):
                module.bcd(raw)

    def test_broadcast_time_structure(self):
        frame=bytes.fromhex(VECTORS[2])
        self.assertEqual(frame[:6],bytes.fromhex('ff00b3160001'))
        self.assertEqual(frame[6:20],bytes.fromhex('0120022603100408052206500745'))
        self.assertEqual(module.kermit(frame),0)

    def test_legal_trace_reconstructed(self):
        sample,trace=synthetic_trace()
        checked=module.verify_wire(trace,[sample])
        self.assertEqual(sum(checked.values()),4)

    def test_response_corruption_rejected(self):
        sample,trace=synthetic_trace()
        damaged=bytearray.fromhex(trace[25]['hex'])
        damaged[-1]^=1
        trace[25]['hex']=damaged.hex()
        with self.assertRaisesRegex(ValueError,'checksum'):
            module.verify_wire(trace,[sample])

    def test_unapproved_write_tx_rejected(self):
        sample,trace=synthetic_trace()
        trace[0]['direction']='TX'
        trace[0]['hex']='4105000216002000'
        with self.assertRaisesRegex(ValueError,'unexpected TX'):
            module.verify_wire(trace,[sample])

    def test_missing_sample_rejected(self):
        sample,trace=synthetic_trace()
        with self.assertRaisesRegex(ValueError,'incomplete'):
            module.verify_wire(trace,[])

    def test_flame_windows_and_lockout_independent(self):
        def item(raw):
            b=bytearray(11)
            b[5]=raw
            return {'native_block':bytes(b).hex(),'utc':'2026-10-09T05:00:00+00:00'}
        rows=[item(1),item(0x41),item(0x41),item(0x21),item(0x21),item(1)]
        self.assertEqual(module.group_windows(rows,0x40)[0]['rounds'],[2,3])
        self.assertEqual(module.group_windows(rows,0x20)[0]['rounds'],[4,5])

    def test_symlink_archive_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            a=Path(tmp)/'missing.tar.gz'
            with self.assertRaises(ValueError):
                module.read_bundle(a)

    def test_zero_crc_is_not_rpm_proof(self):
        self.assertEqual(module.kermit(bytes.fromhex(VECTORS[2])),0)
        self.assertEqual(module.FRAMES[0][2],0x55D3)


if __name__=='__main__':
    unittest.main()
