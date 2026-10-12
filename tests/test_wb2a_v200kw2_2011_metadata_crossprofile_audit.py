"""Proof that old KW2_extended XML programming/ROM flags belong to other devices.

No controller I/O, no service call; real manufacturer/archive sources SHA pinned.
"""
from __future__ import annotations
import importlib.util
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
P=ROOT/"tools/wb2a-v200kw2-2011-metadata-crossprofile-audit.py"
spec=importlib.util.spec_from_file_location("wb2a_v200kw2_crossprofile_tests",P)
m=importlib.util.module_from_spec(spec)
sys.modules[spec.name]=m;spec.loader.exec_module(m)
ZIP=Path("/home/chatgpt-admin/research/gwg-artifacts/target-zips/ccbcc6ef4417c0dfd215c96ec8c991bd276f15ed_TerminatorIII.zip")
DP=Path("/home/chatgpt-admin/research/vitosoft-lfs/DPDefinitions.xml")
EVENT=Path("/home/chatgpt-admin/research/vitosoft-lfs/ecnEventType.xml")


class LegacyCrossProfileTests(unittest.TestCase):
    def test_source_attestation_guards(self):
        self.assertEqual(len(m.ZIP_SHA),64)
        self.assertEqual(len(m.v.DP_SHA),64)
        self.assertEqual(len(m.v.EVENT_SHA),64)
        self.assertEqual(len(m.KW2_TYPES),4)
        self.assertEqual(len(m.SUSPICIOUS),4)
        for bad in (b"",b"invalid",b"{}"):
            with self.subTest(bad=bad[:7]),self.assertRaises(m.SourceRejected):
                m.check_zip(bad)
        with self.assertRaises(m.SourceRejected):
            m.compare_real_catalog(b"<bad/>",b"<bad/>")

    def test_no_2011_programming_endpoint_permitted(self):
        self.assertEqual(m.KW2_TYPES,{"26":"V200KW2","161":"V200KW2_4",
                                     "167":"V200KW2_5","172":"V200KW2_6"})
        self.assertEqual(m.WB2A_TYPES,{"60":"VDensHO1"})
        for key,profiles in m.ALLOWED_SUSPECT_PROFILES.items():
            with self.subTest(key=key):
                self.assertNotIn("V200KW2",profiles)
                self.assertNotIn("VDensHO1",profiles)
                self.assertTrue(all("V200KW2" not in name for name in profiles))

    def test_device_archive_compared_to_original_xml_if_available(self):
        try:zip_data=ZIP.read_bytes()
        except (FileNotFoundError,PermissionError):self.skipTest("private archived 2011 ZIP unavailable")
        r=m.check_zip(zip_data)
        src=r["original_files"]
        self.assertEqual(src["vito_V200KW2.xml"]["datapoints"],578)
        self.assertEqual(src["vito_V200KW2_extended.xml"]["datapoints"],1796)
        self.assertEqual(src["vito_V200KW2.xml"]["suspected_fields"],{})
        self.assertEqual(len(src["vito_V200KW2_extended.xml"]["suspected_fields"]),4)
        self.assertTrue(r["extended_is_cross_device_compilation"])

    def test_pinned_original_vitosoft_source_device_membership_if_available(self):
        try:dp=DP.read_bytes();events=EVENT.read_bytes()
        except (FileNotFoundError,PermissionError):self.skipTest("original private VitoSoft XML unavailable")
        r=m.compare_real_catalog(dp,events)
        self.assertEqual(len(r["cross_family_suspect_service_descriptors"]),4)
        for obj in r["cross_family_suspect_service_descriptors"]:
            self.assertFalse(obj["includes_V200KW2_any_revision"])
            self.assertFalse(obj["includes_VDensHO1_20C2"])
        self.assertEqual(
            next(x for x in r["cross_family_suspect_service_descriptors"]
                 if "ProgrammierstellungEin" in x["alias"])["exact_device_profiles"],
            ["VBC550P","VBC550S"])
        self.assertEqual(
            next(x for x in r["cross_family_suspect_service_descriptors"]
                 if "ChecksummeROMBerechnet" in x["alias"])["exact_device_profiles"],
            ["Ecotronic","Ecotronic_100","VBC550P","VBC550S"])
        self.assertEqual(r["verified_exact_device_profiles"]["V200KW2"]["linked_events"],415)
        self.assertEqual(r["verified_exact_device_profiles"]["VDensHO1"]["linked_events"],581)

    def test_original_triple_source_correspondence_if_available(self):
        try:blobs=(ZIP.read_bytes(),DP.read_bytes(),EVENT.read_bytes())
        except (FileNotFoundError,PermissionError):
            self.skipTest("real private sources unavailable")
        r=m.complete(*blobs)
        self.assertFalse(r["actual_rom_monitor_function_identified"])
        self.assertFalse(r["original_optolink_firmware_dump_sequence_recovered"])
        self.assertEqual(r["controller_io"],0)
        self.assertEqual(r["controller_writes"],0)
        self.assertFalse(r["historical_archive"]["filename_alone_is_a_device_support_proof"])


if __name__=="__main__":unittest.main()
