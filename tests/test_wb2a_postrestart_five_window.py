"""Offline controls for the exact WB2A five-window live reader and Oct 9 comparison."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]/"tools"
s=importlib.util.spec_from_file_location("fivewindow_audit_under_test",ROOT/"wb2a-postrestart-five-window-offline-audit.py")
a=importlib.util.module_from_spec(s)
sys.modules[s.name]=a
s.loader.exec_module(a)

def fake_images():
    src=bytearray([0])*a.m.IMAGE_SIZE
    b=a.m.BASE
    src[0x1de5-b:0x1de5-b+8]=bytes.fromhex("aba20e0133001d00")
    src[0x1e6a-b:0x1e6a-b+8]=bytes.fromhex("0507007db20f0700")
    src[0x3301-b:0x3301-b+29]=bytes(range(1,30))
    src[0x0705-b:0x0705-b+7]=bytes([0x64])*7
    src[0x2184-b]=0xc8
    return [bytes(src)]*79

def fake_capture(originals,*,changed=True):
    data=originals[0]
    b=a.m.BASE
    identity={"command":"read;0x00f8;8","address":"0x00f8","data":a.ID,
              "valid_read":True,"controller_read_only":True}
    guards=[{"command":f"read;0x{addr:04x};1","address":f"0x{addr:04x}",
             "data":"00","valid_read":True,"controller_read_only":True}
            for addr in a.CHECKS]
    cycles=[]
    for i in range(2):
        readings={}
        for name,(addr,n) in a.WINDOWS.items():
            payload=bytearray(data[addr-b:addr-b+n])
            if changed and name=="ram_3300":
                payload[5]^=0x80
                payload[7]^=0x10
                payload[10]^=0x40
                payload[13]^=0x40
                payload[22]^=0x80
                payload[25]^=0x80
                payload[28]^=0x24
            if changed and name=="ram_2180":payload[4]^=0x05
            if changed and name=="ram_1e60" and i==1:payload[0]^=0x01
            readings[name]={"command":f"request;3;0x{addr:04x};{n}",
                            "address":f"0x{addr:04x}","data":payload.hex(),
                            "valid_read":True,"controller_read_only":True}
        cycles.append({"index":i,"reads":readings})
    return {"schema":1,"mode":a.MODE,"target":"20C2/0103",
            "identity":identity,"preflight":guards,"postflight":guards,
            "cycles":cycles,"controller_writes":0,"controller_reads":19,
            "one_serial_owner":True,"ordinary_16bit_low_sram_FC03_only":True}

def encode_and_patch(cap):
    data=json.dumps(cap,sort_keys=True).encode()
    return data,patch.object(a,"PINNED_LIVE_SHA",hashlib.sha256(data).hexdigest())


class FiveWindowOfflineTests(unittest.TestCase):
    def test_windows_and_slices_exclusively_known_low_ram(self):
        self.assertEqual(len(a.WINDOWS),5)
        self.assertEqual([v[0] for v in a.WINDOWS.values()],
                         [0x1de0,0x1e60,0x3300,0x0700,0x2180])
        self.assertEqual(len(a.SLICES),5)
        self.assertTrue(all(0x400<=x<0x5400 and n==32 for x,n in a.WINDOWS.values()))

    def test_valid_synthetic_capture_detects_target_A_changes(self):
        images=fake_images();cap=fake_capture(images)
        source,pin=encode_and_patch(cap)
        with pin:r=a.compare(images,source)
        self.assertEqual(r["audit"],"PASS")
        self.assertEqual(r["candidate_fields"]["A_29byte_target"]["changed_relative_to_old_first"],[7,7])
        self.assertEqual(r["candidate_fields"]["A_8byte_descriptor"]["changed_relative_to_old_first"],[0,0])
        self.assertEqual(r["candidate_fields"]["B_8byte_descriptor"]["changed_relative_to_old_first"],[0,0])
        self.assertEqual(r["candidate_fields"]["B_7byte_target"]["changed_relative_to_old_first"],[0,0])
        self.assertEqual(r["candidate_fields"]["control_byte_2184"]["changed_relative_to_old_first"],[1,1])
        self.assertEqual(r["windows"]["ram_1e60"]["new_two_cycle_changed_addresses"],["0x1e60"])
        self.assertEqual(r["controller_writes"],0)
        self.assertEqual(r["program_ROM_bytes_recovered"],0)
        self.assertFalse(r["ROM_to_SRAM_transfer_proven"])

    def test_mutated_live_file_SHA_rejected(self):
        source,_=encode_and_patch(fake_capture(fake_images()))
        with self.assertRaises(a.SourceRejected):a.decode_capture(source)

    def test_non_readonly_physical_row_rejected(self):
        cap=fake_capture(fake_images())
        cap["cycles"][0]["reads"]["ram_3300"]["controller_read_only"]=False
        source,pin=encode_and_patch(cap)
        with pin:
            with self.assertRaises(a.SourceRejected):a.decode_capture(source)

    def test_wrong_device_identity_rejected(self):
        cap=fake_capture(fake_images());cap["identity"]["data"]="00"*8
        source,pin=encode_and_patch(cap)
        with pin:
            with self.assertRaises(a.SourceRejected):a.decode_capture(source)

    def test_wrong_mode_rejected(self):
        cap=fake_capture(fake_images());cap["mode"]="ROM_READ"
        source,pin=encode_and_patch(cap)
        with pin:
            with self.assertRaises(a.SourceRejected):a.decode_capture(source)

    def test_nonzero_controller_write_rejected(self):
        cap=fake_capture(fake_images());cap["controller_writes"]=1
        source,pin=encode_and_patch(cap)
        with pin:
            with self.assertRaises(a.SourceRejected):a.decode_capture(source)

    def test_command_out_of_bound_address_rejected(self):
        cap=fake_capture(fake_images())
        cap["cycles"][0]["reads"]["ram_3300"]["command"]="request;3;0xf3300;32"
        source,pin=encode_and_patch(cap)
        with pin:
            with self.assertRaises(a.SourceRejected):a.decode_capture(source)

    def test_bad_reply_length_rejected(self):
        cap=fake_capture(fake_images());cap["cycles"][0]["reads"]["ram_3300"]["data"]="00"
        source,pin=encode_and_patch(cap)
        with pin:
            with self.assertRaises(a.SourceRejected):a.decode_capture(source)

    def test_bad_fault_preflight_rejected(self):
        cap=fake_capture(fake_images());cap["preflight"][2]["data"]="c5"
        source,pin=encode_and_patch(cap)
        with pin:
            with self.assertRaises(a.SourceRejected):a.decode_capture(source)

    def test_bad_fault_postflight_rejected(self):
        cap=fake_capture(fake_images());cap["postflight"][3]["data"]="f9"
        source,pin=encode_and_patch(cap)
        with pin:
            with self.assertRaises(a.SourceRejected):a.decode_capture(source)

    def test_wrong_number_of_cycles_rejected(self):
        cap=fake_capture(fake_images());cap["cycles"]=cap["cycles"][:1]
        source,pin=encode_and_patch(cap)
        with pin:
            with self.assertRaises(a.SourceRejected):a.decode_capture(source)

    def test_extra_physical_read_rejected(self):
        cap=fake_capture(fake_images())
        cap["cycles"][0]["reads"]["extra_rom"]={"command":"request;3;0xf000;32"}
        source,pin=encode_and_patch(cap)
        with pin:
            with self.assertRaises(a.SourceRejected):a.decode_capture(source)

    def test_historical_pointer_original_must_still_match(self):
        imgs=fake_images()
        altered=bytearray(imgs[2]);altered[0x1de5-a.m.BASE]=0xFF
        imgs[2]=bytes(altered)
        source,pin=encode_and_patch(fake_capture(imgs))
        with pin:
            with self.assertRaises(a.SourceRejected):
                a.compare(imgs,source)

    def test_safe_script_command_surface(self):
        original=(ROOT/"wb2a-postrestart-five-window-readonly.py").read_text()
        compare_source=(ROOT/"wb2a-postrestart-five-window-offline-audit.py").read_text()
        wrapper=(ROOT/"wb2a-postrestart-five-window-session.sh").read_text()
        for forbidden in ("serial.Serial(","/dev/tty","request;2;",
                          "writeraw;", "0xF0000","flash_erase"):
            self.assertNotIn(forbidden,original)
            self.assertNotIn(forbidden,compare_source)
        self.assertIn("systemd-run --unit=",wrapper)
        self.assertLess(wrapper.index("INDEPENDENT_RESTORE_ARMED"),wrapper.index("systemctl stop optolink-splitter.service"))
        self.assertIn("trap rollback EXIT",wrapper)

    def test_original_archive_and_actual_new_capture_if_accessible(self):
        old=Path("/root/p300-trial-work/research-bundles/p300-fullram-run-20261009T083607Z-144293-bundle.tar.gz")
        new=Path("/tmp/wb2a-postrestart-five-window-live-20261012.json")
        if not os.access(old,os.R_OK) or not os.access(new,os.R_OK):
            self.skipTest("Private authentic capture files unavailable in GitHub CI")
        actual=a.compare(a.m.attested_images(old.read_bytes()),new.read_bytes())
        self.assertEqual(actual["audit"],"PASS")
        self.assertEqual(actual["candidate_fields"]["A_29byte_target"]["changed_relative_to_old_first"],[7,7])
        self.assertEqual(actual["candidate_fields"]["A_8byte_descriptor"]["changed_relative_to_old_first"],[0,0])
        self.assertEqual(actual["candidate_fields"]["B_8byte_descriptor"]["changed_relative_to_old_first"],[0,0])
        self.assertEqual(actual["controller_writes"],0)

if __name__=="__main__":
    unittest.main()
