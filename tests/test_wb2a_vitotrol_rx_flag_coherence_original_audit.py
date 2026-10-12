"""79 historical WB2A RAM images: CRC validated RX flag discrimination, offline only."""
from __future__ import annotations
import importlib.util
from pathlib import Path
import sys
import unittest

P=Path(__file__).resolve().parents[1]/"tools/wb2a-vitotrol-rx-flag-coherence-original-audit.py"
s=importlib.util.spec_from_file_location("wb2a_rx_flag_offline_test",P)
m=importlib.util.module_from_spec(s);sys.modules[s.name]=m;s.loader.exec_module(m)


def build_fixture():
 images=[]
 for index in range(1,80):
  mem=bytearray(m.SIZE)
  def put(addr,raw):
   j=addr-m.BASE
   mem[j:j+len(raw)]=raw
  put(m.RX,m.RARE_RX if index==64 else m.BASELINE_RX)
  put(m.META,m.RARE_META if index==64 else m.BASELINE_META)
  put(m.DESC,m.DESC_BYTES)
  put(m.TX,bytes.fromhex("0100b10a"))
  if index in (1,41,62):
   put(m.STATE,bytes.fromhex("0a"))
  elif index in (26,31,33,58):
   put(m.STATE,bytes.fromhex("0b"))
  else:
   put(m.STATE,bytes.fromhex("01"))
  for addr,word in m.BASELINE_PTRS.items():
   if index in (1,41,60,62):
    put(addr,bytes.fromhex("11223300"))
   else:put(addr,word)
  images.append(bytes(mem))
 return images


class TestOffline(unittest.TestCase):
 def test_simulated_79_images_reproduces_negated_ready_byte_and_meta(self):
  report=m.classify(build_fixture())
  self.assertEqual(report["complete_RAM_images"],79)
  self.assertEqual(report["rx_crc_valid_samples"],79)
  self.assertEqual(report["rx_rare_sample_indices"],[64])
  self.assertEqual(report["metadata_rare_sample_indices"],[64])
  self.assertEqual(report["status_0b6b_counts"],{"01":72,"0a":3,"0b":4})
  self.assertEqual(report["status_0b6b_non01_indices"],[1,26,31,33,41,58,62])
  self.assertEqual(report["simultaneous_3_pointer_anomaly_indices"],[1,41,60,62])
  self.assertEqual(report["partial_3_pointer_anomaly_indices"],[])
  self.assertEqual(report["cochanged_pointer_triplet_when_0b6b_0a"],3)
  self.assertFalse(report["0b6b_abnormal_detects_rare_RX"])
  self.assertEqual(report["0b6b_abnormal_false_positive_count"],7)
  self.assertTrue(report["0b6b_default_when_only_rare_rx"])
  self.assertTrue(report["meta_166a_abnormal_is_only_rare_rx_same_image"])
  self.assertFalse(report["0b6b_writable_RX_ready_flag_proven"])
  self.assertFalse(report["166a_b_writable_RX_ready_flag_proven"])
  self.assertFalse(report["RX_consumer_callback_owner_proven"])
  self.assertFalse(report["rx_source_class_0x11_accepted"])
  self.assertTrue(report["no_new_live_controller_IO"])
  self.assertEqual(report["controller_writes"],0)

 def test_rare_meta_cannot_be_called_perfect_when_unpaired(self):
  images=build_fixture()
  blob=bytearray(images[65])
  idx=m.META-m.BASE
  blob[idx:idx+3]=m.RARE_META
  images[65]=bytes(blob)
  r=m.classify(images)
  self.assertFalse(r["meta_166a_abnormal_is_only_rare_rx_same_image"])
  self.assertEqual(r["metadata_rare_sample_indices"],[64,66])

 def test_false_positive_status_detects_unrelated_records(self):
  images=build_fixture()
  blob=bytearray(images[63])
  idx=m.STATE-m.BASE
  blob[idx]=10
  images[63]=bytes(blob)
  report=m.classify(images)
  self.assertTrue(report["0b6b_abnormal_detects_rare_RX"])
  self.assertFalse(report["0b6b_default_when_only_rare_rx"])
  self.assertEqual(report["0b6b_abnormal_false_positive_count"],7)
  self.assertFalse(report["0b6b_0a_only_at_pointer_triplet_anomaly"])

 def test_descriptor_and_ram_shape_fail_closed(self):
  images=build_fixture()
  with self.assertRaises(m.Refused):m.classify(images[:78])
  with self.assertRaises(m.Refused):m.classify([b""]*79)
  target=bytearray(images[2])
  target[m.DESC-m.BASE]=0x45
  images[2]=bytes(target)
  with self.assertRaises(m.Refused):m.classify(images)

 def test_unknown_crc_frame_and_meta_fail_closed(self):
  for addr in (m.RX,m.META,m.STATE):
   images=build_fixture()
   edit=bytearray(images[2])
   edit[addr-m.BASE]=0xff
   images[2]=bytes(edit)
   with self.subTest(addr=hex(addr)),self.assertRaises(m.Refused):
    m.classify(images)

 def test_real_private_archive_when_mounted_or_sudo_only(self):
  try:raw=Path(m.ORIG).read_bytes()
  except (FileNotFoundError,PermissionError):
   self.skipTest("original root-only completed RAM archive not mounted")
  r=m.source_verified(raw)
  self.assertEqual(r["complete_RAM_images"],79)
  self.assertEqual(r["source_original_sha256"],
                   "94d5842b6dc5759ecb446a4c617b60b72873b639885d116032f783abdef8431c")
  self.assertEqual(r["rx_rare_sample_indices"],[64])
  self.assertEqual(r["status_0b6b_non01_indices"],[1,26,31,33,41,58,62])
  self.assertFalse(r["0b6b_abnormal_detects_rare_RX"])


if __name__=="__main__":unittest.main()
