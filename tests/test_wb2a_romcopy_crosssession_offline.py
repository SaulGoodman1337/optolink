"""Exact original/cross-day P300 evidence, artificial mutation controls."""
from __future__ import annotations
from copy import deepcopy
import importlib.util
import os
from pathlib import Path
import sys
import tempfile
import unittest

SRC=Path(__file__).resolve().parents[1]/"tools/wb2a-romcopy-crosssession-offline.py"
sp=importlib.util.spec_from_file_location("romcopy_crossover_study",SRC)
m=importlib.util.module_from_spec(sp)
sys.modules[sp.name]=m
sp.loader.exec_module(m)


def fake_archive_images():
    b=bytearray(b"\x00"*m.original.IMAGE_SIZE)
    base=m.original.BASE
    b[0x1DE5-base:0x1DE5-base+8]=bytes.fromhex("ab a2 0e 01 33 00 1d 00")
    b[0x1E6A-base:0x1E6A-base+8]=bytes.fromhex("05 07 00 7d b2 0f 07 00")
    b[0x3301-base:0x3301-base+29]=bytes(range(1,30))
    return [bytes(b)]*m.original.IMAGE_COUNT


def live_sample(images):
    first=images[0]
    base=m.original.BASE
    def get(addr,n):return first[addr-base:addr-base+n]
    def row(addr,n,override=None):
        data=get(addr,n) if override is None else override
        return {"address":f"0x{addr:04x}",
                "command":f"request;3;0x{addr:04x};{n}",
                "data":data.hex(),"valid_read":True,
                "controller_read_only":True}
    def guards():
        return [{"valid_read":True,"controller_read_only":True,
                 "data":"00","address":f"0x{addr:04x}",
                 "command":f"read;0x{addr:04x};1"}
                for addr in m.GUARD_ADDRESSES]
    ident={"data":m.IDENTITY,"controller_read_only":True,
           "address":"0x00f8","command":"read;0x00f8;8",
           "valid_read":True}
    changed=bytearray(get(0x2182,16));changed[2]^=1
    readings={}
    for name in ("contrast","dual","dual_high"):
        if name=="contrast":
            reads={"physical_1de5":row(0x1DE5,16),
                   "physical_3300":row(0x3300,32),
                   "physical_2182":row(0x2182,16,bytes(changed))}
            readings[name]={"mode":m.CONTRAST_MODE,"target":"20C2/0103",
                         "controller_writes":0,"identity":ident,
                         "preflight":guards(),"postflight":guards(),
                         "physical_high_rom_banks_addressable":False,
                         "cycles":[{"index":0,"reads":deepcopy(reads)},
                                   {"index":1,"reads":deepcopy(reads)}]}
        else:
            readings[name]={"mode":m.DUAL_MODE,"target":"20C2/0103",
                          "controller_writes":0,"identity":ident,
                          "baseline":guards(),"after":guards(),
                          "code_execution_or_rom_mapping_proven":False,
                          "copy_context":[row(0x1DE0,32),row(0x1E60,32),
                                          row(0x3300,32)]}
    return readings


class CrossSessionTests(unittest.TestCase):
    def test_synthetic_original_two_day_matches(self):
        images=fake_archive_images()
        r=m.compare(images,live_sample(images))
        self.assertEqual(r["audit"],"PASS")
        self.assertEqual(r["A_8byte_tuple_oct11_compared_observations"],4)
        self.assertEqual(r["A_29byte_target_oct11_compared_observations"],4)
        self.assertEqual(r["B_8byte_tuple_oct11_compared_observations"],2)
        self.assertEqual(r["oct11_tail_2182_16byte_differences_offset_lists"],[[2],[2]])
        self.assertFalse(r["ROM_to_RAM_copy_causality_proven"])
        self.assertEqual(r["real_ROM_bytes"],0)

    def test_missing_independent_session_rejected(self):
        images=fake_archive_images()
        sources=live_sample(images);del sources["dual_high"]
        with self.assertRaises(m.SourceMismatch):m.compare(images,sources)

    def test_modified_tuple_A_rejected(self):
        images=fake_archive_images();sources=live_sample(images)
        sources["contrast"]["cycles"][0]["reads"]["physical_1de5"]["data"]="00"*16
        with self.assertRaises(m.SourceMismatch):m.compare(images,sources)

    def test_modified_target_A_rejected(self):
        images=fake_archive_images();sources=live_sample(images)
        sources["dual"]["copy_context"][2]["data"]="00"*32
        with self.assertRaises(m.SourceMismatch):m.compare(images,sources)

    def test_modified_tuple_B_rejected(self):
        images=fake_archive_images();sources=live_sample(images)
        sources["dual_high"]["copy_context"][1]["data"]="00"*32
        with self.assertRaises(m.SourceMismatch):m.compare(images,sources)

    def test_read_only_bit_missing_rejected(self):
        images=fake_archive_images();sources=live_sample(images)
        sources["dual"]["copy_context"][0]["controller_read_only"]=False
        with self.assertRaises(m.SourceMismatch):m.compare(images,sources)

    def test_overstated_ROM_mapping_rejected(self):
        images=fake_archive_images();sources=live_sample(images)
        sources["dual"]["code_execution_or_rom_mapping_proven"]=True
        with self.assertRaises(m.SourceMismatch):m.compare(images,sources)

    def test_wrong_device_identity_rejected(self):
        images=fake_archive_images();sources=live_sample(images)
        sources["contrast"]["identity"]={**sources["contrast"]["identity"],"data":"00000000"}
        with self.assertRaises(m.SourceMismatch):m.compare(images,sources)

    def test_nonzero_controller_writes_rejected(self):
        images=fake_archive_images();sources=live_sample(images)
        sources["dual"]["controller_writes"]=1
        with self.assertRaises(m.SourceMismatch):m.compare(images,sources)

    def test_unverified_fault_guard_rejected(self):
        images=fake_archive_images();sources=live_sample(images)
        sources["contrast"]["postflight"][1]={**sources["contrast"]["postflight"][1],"data":"01"}
        with self.assertRaises(m.SourceMismatch):m.compare(images,sources)

    def test_missing_guard_rejected(self):
        images=fake_archive_images();sources=live_sample(images)
        sources["dual"]["baseline"]=sources["dual"]["baseline"][:-1]
        with self.assertRaises(m.SourceMismatch):m.compare(images,sources)

    def test_wrong_guard_address_rejected(self):
        images=fake_archive_images();sources=live_sample(images)
        sources["dual"]["baseline"][0]["address"]="0x27a1"
        with self.assertRaises(m.SourceMismatch):m.compare(images,sources)

    def test_wrong_identity_command_rejected(self):
        images=fake_archive_images();sources=live_sample(images)
        sources["dual_high"]["identity"]={
            **sources["dual_high"]["identity"],"command":"read;0x00f8;16"}
        with self.assertRaises(m.SourceMismatch):m.compare(images,sources)

    def test_corrupt_JSON_sha_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            file=Path(folder)/m.FILES["dual"][0]
            file.write_bytes(b" "*650)
            with self.assertRaises(m.SourceMismatch):
                m.original_json(file,m.FILES["dual"][0],m.FILES["dual"][1])

    def test_wrong_read_length_rejected(self):
        row={"address":"0x1de5","command":"request;3;0x1de5;16",
             "controller_read_only":True,"valid_read":True,
             "data":"AA"*8}
        with self.assertRaises(m.SourceMismatch):m._row(row,0x1de5,16)

    def test_actual_original_sources_if_available(self):
        archive=Path("/root/p300-trial-work/research-bundles/p300-fullram-run-20261009T083607Z-144293-bundle.tar.gz")
        if not os.access(archive,os.R_OK):
            self.skipTest("strictly private root-owned original RAM tar")
        r=m.audit(archive,Path("/tmp"))
        self.assertEqual(r["audit"],"PASS")
        self.assertEqual(r["oct11_verified_independent_original_JSON_sources"],3)
        self.assertEqual(r["oct11_tail_2182_16byte_differences_offset_lists"],[[2],[2]])
        self.assertTrue(r["Oct11_tail_0x2184_is_different_from_Oct9"])
        self.assertEqual(r["real_ROM_bytes"],0)

    def test_no_new_live_controller_io(self):
        code=SRC.read_text()
        for forbidden in ("subprocess.run(", "os.system(", "serial.Serial(",
                          "socket.socket(", "/dev/tty", "systemctl stop",
                          "systemctl start", "writeraw;"):
            self.assertNotIn(forbidden,code)


if __name__=="__main__":
    unittest.main()
