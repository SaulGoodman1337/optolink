"""Offline 20 KiB scanner: real V300-positive, CRC-negative and original data."""
from __future__ import annotations
import importlib.util
from pathlib import Path
import sys
import unittest

SRC=Path(__file__).resolve().parents[1]/"tools/wb2a-vitotrol-class11-fullram-and-stability-audit.py"
spec=importlib.util.spec_from_file_location("vt_fullram_class11_test",SRC)
m=importlib.util.module_from_spec(spec);sys.modules[spec.name]=m
spec.loader.exec_module(m)
ARCH=Path("/root/p300-trial-work/research-bundles/p300-fullram-run-20261009T083607Z-144293-bundle.tar.gz")
GOOD_REMOTE=bytes.fromhex("0011b10a0101001219d5")
GOOD_REMOTE_PONG=bytes.fromhex("001180080101f95c")
GOOD_EXISTING=bytes.fromhex("0001b10a010110fe23d8")


def image(packets=()):
    raw=bytearray(m.RAM_BYTES)
    for addr,frame in packets:
        raw[addr-m.LOW:addr-m.LOW+len(frame)]=frame
    return bytes(raw)


class ScanningTests(unittest.TestCase):
    def test_all_byte_offsets_and_valid_source11(self):
        x=image([(0x1642,GOOD_EXISTING),(0x1201,GOOD_REMOTE),
                 (0x3007,GOOD_REMOTE_PONG)])
        r=m.raw_frame_scan(x)
        self.assertEqual(r["valid_counts"],{"class01":1,"class11":2})
        self.assertEqual({x["physical_ram_address"] for x in r["valid_frames"]},
                         {"0x1642","0x1201","0x3007"})
        self.assertEqual({x["source"] for x in r["valid_frames"]},
                         {"class01","class11"})

    def test_wrong_crc_wrong_size_and_end_boundary_rejected(self):
        corrupt=bytearray(GOOD_REMOTE)
        corrupt[-1]^=1
        x=image([(0x1000,bytes(corrupt)),(0x2000,bytes.fromhex("0011b107")),
                 (0x53fb,bytes.fromhex("0011b10a01"))])
        r=m.raw_frame_scan(x)
        self.assertEqual(r["valid_counts"],{})
        self.assertGreaterEqual(r["plausible_length_counts"].get("class11",0),1)
        self.assertGreaterEqual(r["wrong_crc_counts"].get("class11",0),1)
        self.assertGreaterEqual(r["wrong_length_counts"].get("class11",0),2)

    def test_unknown_opcode_allowed_with_valid_checksum(self):
        # Every plausible sender-0x11 frame is checked, not only B1/B3/80/BF.
        body=bytes.fromhex("001188080101")
        crc=m.a.crc16_kermit(body)
        frame=body+crc.to_bytes(2,"little")
        self.assertEqual(m.a.crc16_kermit(frame),0)
        rows=m.raw_frame_scan(image([(0x1309,frame)]))["valid_frames"]
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]["opcode"],"0x88")
        self.assertEqual(rows[0]["source"],"class11")

    def test_static_tail_is_verified_over_multiple_images(self):
        x=image()
        arr=[x,bytearray(x),bytearray(x)]
        arr[1][0x2181-m.LOW]=1
        arr[2][0x2181-m.LOW]=2
        result=m.static_tail([arr[0],bytes(arr[1]),bytes(arr[2])])
        self.assertEqual(result["physical_ram_begin"],"0x2182")
        self.assertEqual(result["physical_ram_end"],"0x53ff")
        self.assertEqual(result["unchanged_bytes"],0x5400-0x2182)
        self.assertFalse(result["entropy_or_stability_proves_rom"])

    def test_wrong_size_type_or_unpinned_archive_rejected(self):
        with self.assertRaises(m.EvidenceRejected):m.raw_frame_scan(b"x"*512)
        with self.assertRaises(m.EvidenceRejected):m.raw_frame_scan(bytearray(m.RAM_BYTES))
        with self.assertRaises(m.EvidenceRejected):m.static_tail([bytes(m.RAM_BYTES)])
        with self.assertRaises(m.EvidenceRejected):m.original_archive(b"not original")
        with self.assertRaises(m.EvidenceRejected):m.analyze([image()]*78,sha=m.SOURCE_SHA)

    def test_real_source_if_authorized(self):
        try:original=ARCH.read_bytes()
        except (PermissionError,FileNotFoundError):
            self.skipTest("original root-only archive unavailable")
        r=m.original_archive(original)
        self.assertEqual(r["images"],79)
        self.assertEqual(r["total_scanned_bytes"],1_617_920)
        self.assertEqual(r["prefix_counts"]["class11"],184)
        self.assertEqual(r["plausible_length_counts"]["class11"],20)
        self.assertEqual(r["wrong_crc_counts"]["class11"],20)
        self.assertEqual(r["total_valid_class01"],79)
        self.assertEqual(r["total_valid_class11"],0)
        self.assertEqual(r["valid_frame_locations"],[
            {"source":"class01","ram":"0x1642","observations":79}])
        self.assertEqual(r["metadata_166a166b_counts"],{"0600":78,"0a04":1})
        self.assertTrue(r["physical_0x1642_known_rx_positive_control"])
        self.assertEqual(r["high_stability_sram_tail"]["physical_ram_begin"],"0x2182")
        self.assertEqual(r["high_stability_sram_tail"]["unchanged_bytes"],12926)
        self.assertFalse(r["firmware_binary_obtained"])
        self.assertEqual(r["controller_writes"],0)


if __name__=="__main__":unittest.main()
