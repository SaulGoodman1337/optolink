"""Adversarial, fixture-based GWG/VS1/P300 firmware-oracle audit tests."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import re
import sys
import tempfile
import unittest

SOURCE=Path(__file__).resolve().parents[1]/"tools"/"wb2a-gwg-vs1-p300-generation-oracle-audit.py"
sp=importlib.util.spec_from_file_location("wb2a_gwg_vs1_p300_crossgen_oracle",SOURCE)
m=importlib.util.module_from_spec(sp)
sys.modules[sp.name]=m
sp.loader.exec_module(m)


def good_slices(*, fc="KMBUS_EEPROM_READ",address="0x00A0",
                length=10, prefix="030000000101"):
    return [
        {"ID":f"synthetic_alarm_{i}","AccessMode":"Read",
         "FCRead":fc,"Address":address,"BlockLength":str(length),
         "BytePosition":str(i),"ByteLength":"1","PrefixRead":prefix}
        for i in range(length)
    ]


def cs_source():
    return (
       "private async Task<CCommRequReturn> ReadData300(int addr, byte len)\n"
       "{\noutbuff[0] = STX;\noutbuff[2] = cbREQ;\n"
       "outbuff[3] = cbREAD;\n"
       "outbuff[4] = (byte)((addr >> 8) & 0xFF);\n"
       "outbuff[5] = (byte)((addr) & 0xFF);\n"
       "outbuff[6] = len;\n}\n"
       "private async Task<CCommRequReturn> WriteData300(int addr, byte[] data) {}\n"
       "private async Task<CCommRequReturn> ReadDataKW(int addr, byte len)\n"
       "{\noutbuff[0 + offs] = 0xF7;\n"
       "outbuff[1 + offs] = (byte)((addr >> 8) & 0xFF);\n"
       "outbuff[2 + offs] = (byte)(addr & 0xFF);\n"
       "outbuff[3 + offs] = len;\n}\n"
       "private async Task<CCommRequReturn> WriteDataKW(int addr, byte[] data) {}\n"
    )


def wiki_source():
    return ("VIRTUAL READ | 01 | C7\n"
            "PHYSICAL READ | 03 | CB\n"
            "PHYSICAL KMBUS EEPROM READ | 67 | 43\n")


def legacy_source():
    bt=chr(96)
    return f"{bt}GFA_Read{bt} = {bt}0x6B{bt} and {bt}PROZESS_READ{bt} = {bt}0x7B{bt}"


class CrossGenerationOracles(unittest.TestCase):
    def test_expected_original_5_sources_have_sha256(self):
        self.assertEqual(len(m.SOURCES),5)
        self.assertEqual(sum(x[2] for x in m.SOURCES.values()),196557939)
        self.assertTrue(all(len(v[1])==64 for v in m.SOURCES.values()))

    def test_source_fake_sha_rejected(self):
        with tempfile.TemporaryDirectory(prefix="wb2a-crossgen-") as d:
            file=Path(d)/"f.txt"
            file.write_bytes(b"x"*13)
            with self.assertRaises(m.Rejected):
                m.sha_original(file,"a"*64,13)

    def test_source_symlink_rejected(self):
        with tempfile.TemporaryDirectory(prefix="wb2a-crossgen-") as d:
            origin=Path(d)/"origin"
            link=Path(d)/"link"
            origin.write_bytes(b"abc")
            link.symlink_to(origin)
            with self.assertRaises(m.Rejected):
                m.sha_original(link,"a"*64,3)

    def test_non_rom_labels_not_misread_as_code(self):
        for fake in ("HO2B_Stromverbrauch_Akt_Jahr~0x9390",
                     "Stromversorgung","GWG_FA_Historie_StoerDiagnose_05~0x00AA",
                     "K8B_KonfiEEPROM_Status~0x778B"):
            self.assertFalse(m.code_oracle_label(fake),fake)

    def test_checksum_firmware_and_rom_labels_match(self):
        for name in ("ChecksummeROMBerechnet~0x08F0",
                     "NRF_ChecksummeROMLinker~0x08F4",
                     "HO2B_LAN_Card_Firmware~0xD069",
                     "FlashRead","BootloaderVersion"):
            self.assertTrue(m.code_oracle_label(name),name)

    def test_bad_label_type_rejected(self):
        with self.assertRaises(m.Rejected):
            m.code_oracle_label(None)

    def test_synthetic_eeprom_block_host_slices(self):
        result=m.object_slice(good_slices(),"KMBUS_EEPROM_READ","0x00A0",10)
        self.assertEqual(result["logical_descriptors"],10)
        self.assertEqual(result["slice_offsets"],list(range(10)))
        self.assertEqual(result["prefixes"],["030000000101"])
        self.assertFalse(result["parameter_selects_memory_bank_proven"])
        self.assertFalse(result["independent_controller_registers_proven"])

    def test_identical_base_does_not_become_ten_bank_selectors(self):
        data=m.object_slice(good_slices(),"KMBUS_EEPROM_READ","0x00A0",10)
        self.assertEqual(data["different_slice_start_offsets"],10)
        self.assertEqual(data["block_length"],10)
        self.assertFalse(data["parameter_selects_memory_bank_proven"])

    def test_invalid_event_byte_offset_rejected(self):
        rows=good_slices()
        rows[1]["BytePosition"]="10"
        with self.assertRaises(m.Rejected):
            m.object_slice(rows,"KMBUS_EEPROM_READ","0x00A0",10)

    def test_invalid_event_byte_width_rejected(self):
        rows=good_slices()
        rows[1]["ByteLength"]="12"
        with self.assertRaises(m.Rejected):
            m.object_slice(rows,"KMBUS_EEPROM_READ","0x00A0",10)

    def test_missing_source_block_rejected(self):
        with self.assertRaises(m.Rejected):
            m.object_slice(good_slices(),"GFA_READ","0x4000",10)

    def test_writer_not_a_read_only_host_block(self):
        rows=good_slices()
        rows[0]["AccessMode"]="ReadWrite"
        self.assertFalse(m.object_slice(rows,"KMBUS_EEPROM_READ","0x00A0",10)["uniform_read_only"])

    def test_parse_xml_rows_with_entities_and_tags(self):
        raw=b"<x><Name>A&amp;B</Name><BytePosition>3</BytePosition></x>"
        rows=list(m.rowgen(raw,re.compile(rb"<x>(.*?)</x>",re.S)))
        self.assertEqual(rows,[{"Name":"A&B","BytePosition":"3"}])

    def test_repeated_xml_field_rejected(self):
        raw=b"<x><Id>1</Id><Id>1</Id></x>"
        with self.assertRaises(m.Rejected):
            list(m.rowgen(raw,re.compile(rb"<x>(.*?)</x>",re.S)))

    def test_truncated_xml_row_rejected(self):
        raw=b"<x><Item>broken & garbage</Item></x>"
        with self.assertRaises(m.Rejected):
            list(m.rowgen(raw,re.compile(rb"<x>(.*?)</x>",re.S)))

    def test_member_only_in_exact_link_not_other_host_family(self):
        types={"60":"VDensHO1","76":"GWG_VBEM_00"}
        eid={"1":"ChecksummeROMBerechnet~0x08F0",
             "2":"GWG_FA_Historie_StoerCode_01~0x00A0"}
        links={"60":{"1"},"76":{"2"}}
        defs={eid[k]:{"ID":eid[k]} for k in eid}
        wb=m.rows_for(types,eid,links,defs,"VDensHO1")
        gw=m.rows_for(types,eid,links,defs,"GWG_VBEM_00")
        self.assertNotIn(gw[0],wb)
        self.assertEqual(wb[0]["ID"],"ChecksummeROMBerechnet~0x08F0")

    def test_unknown_device_name_rejected(self):
        with self.assertRaises(m.Rejected):
            m.rows_for({"60":"VDensHO1"},{},{},{},"NewMadeUpController")

    def test_crossprotocol_positive_fake_source(self):
        result=m.check_public_reader(cs_source(),wiki_source(),legacy_source())
        self.assertEqual(result["public_reader_source_address_bytes"],2)
        self.assertEqual(result["VS1_GFA_read_fc_hex"],"0x6B")
        self.assertEqual(result["VS1_PROZESS_read_fc_hex"],"0x7B")
        self.assertEqual(result["old_GWG_KMBUS_EEPROM_read_fc_hex"],"0x43")
        self.assertFalse(result["community_reader_has_direct_upper_ROM_bank_selector_proven"])

    def test_p300_fake_bank_byte_rejected(self):
        code=cs_source().replace(
            "outbuff[4] = (byte)((addr >> 8) & 0xFF);",
            "outbuff[4] = (byte)((addr >> 16) & 0xFF);")
        with self.assertRaises(m.Rejected):
            m.check_public_reader(code,wiki_source(),legacy_source())

    def test_vs1_fake_address_serializer_rejected(self):
        code=cs_source().replace(
            "outbuff[1 + offs] = (byte)((addr >> 8) & 0xFF);",
            "outbuff[1 + offs] = (byte)((addr >> 24) & 0xFF);")
        with self.assertRaises(m.Rejected):
            m.check_public_reader(code,wiki_source(),legacy_source())

    def test_gwg_changed_opcode_rejected(self):
        with self.assertRaises(m.Rejected):
            m.check_public_reader(cs_source(),
                  wiki_source().replace("READ | 67 | 43","READ | 67 | 99"),
                  legacy_source())

    def test_legacy_gfa_op_removed_rejected(self):
        with self.assertRaises(m.Rejected):
            m.check_public_reader(cs_source(),wiki_source(),
                                 legacy_source().replace("0x6B","0x6F"))

    def test_sha_attested_full_real_catalog_when_locally_available(self):
        if not all(v[0].is_file() for v in m.SOURCES.values()):
            self.skipTest("Private 186MB original VitoSoft catalog absent on GitHub CI")
        r=m.audit()
        self.assertEqual(r["audit"],"PASS")
        self.assertEqual(r["catalog_counts"],{
            "all_type_count":399,
            "all_link_count":104339,
            "all_event_definition_count":11582,
        })
        info=r["generation_comparison"]
        self.assertEqual(info["selected_host_profiles"],90)
        self.assertEqual(info["selected_profile_event_links"],39263)
        self.assertEqual(info["unique_selected_event_descriptors"],2314)
        self.assertEqual(info["profiles"]["VDensHO1"]["descriptors"],581)
        self.assertEqual(info["profiles"]["GWG_VBEM_00"]["descriptors"],220)
        self.assertEqual(info["profiles"]["VDensHO1_4"]["shared_exact_event_aliases_with_WB2A"],558)
        self.assertEqual(info["profiles"]["VScotHO1_200_01"]["shared_exact_event_aliases_with_WB2A"],546)
        self.assertEqual(info["wb2a_gfa_read_descriptors"],94)
        self.assertEqual(info["old_gwg_kmbus_eeprom_descriptors"],54)
        self.assertTrue(info["no_named_ROM_checksum_in_WB2A_profile"])
        self.assertTrue(info["no_host_KMBUS_EEPROM_READ_in_WB2A_profile"])
        self.assertEqual(r["firmware_program_ROM_bytes_recovered"],0)
        self.assertFalse(r["ready_to_attempt_WB2A_ROM_read"])
        self.assertEqual(r["controller_reads"],0)
        self.assertEqual(r["controller_writes"],0)

    def test_not_an_optolink_live_tool(self):
        src=SOURCE.read_text(encoding="utf-8")
        for bad in ("serial.Serial(", "subprocess.run(", "os.system(", "/dev/tty",
                    "systemctl stop","systemctl restart","socket.socket(", "writeraw;",
                    "flash_erase", "flash_write"):
            self.assertNotIn(bad,src)


if __name__=="__main__":
    unittest.main()
