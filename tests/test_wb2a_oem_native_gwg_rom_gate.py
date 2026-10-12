"""Safety and provenance tests for original OEM GWG native/CLR ROM gate."""
import collections
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import sys
import tempfile
import unittest

SRC = Path(__file__).resolve().parents[1] / "tools/wb2a-oem-native-gwg-rom-gate.py"
spec = importlib.util.spec_from_file_location("oem_rom_gate_20261012", SRC)
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
spec.loader.exec_module(m)


def ref(opcode: str, val=None):
    return SimpleNamespace(opcode=SimpleNamespace(name=opcode), operand=val,
                           offset=0x10)


def known_exports():
    return {"CheckGWG": 0x1080, "TestCall_GWG99Native": 0x1040}


def known_call_counts():
    return {x: collections.Counter({m.GETBYTES_INT32_TOKEN: 1})
            for x in m.INT32_RPC_NAMES}


def known_metadata():
    return {
        m.GETBYTES_INT32_TOKEN: ("GetBytes", m.GETBYTES_INT32_SIG),
        m.GETBYTES_INT16_TOKEN: ("GetBytes", m.GETBYTES_INT16_SIG),
    }


class NativeROMGateTests(unittest.TestCase):
    def test_gwg_native_original_contract(self):
        x = m.native_detection_contract(
            m.NATIVE_GWG_REQUEST, m.NATIVE_REQUEST_LENGTH,
            m.NATIVE_ID_GATE, known_exports())
        self.assertEqual(x["raw_send_bytes"], "c7f804")
        self.assertEqual(x["legacy_accepted_product_ids"], ["2053", "2054"])
        self.assertFalse(x["native_rom_dump_export_found"])
        self.assertFalse(x["wb2a_id_20c2_accepted_by_native_detector"])
        self.assertFalse(x["native_gwg_probe_sends_full_wiki_stx_eot_frame"])

    def test_corrupt_gwg_opcode_rejected(self):
        bad = bytearray(m.NATIVE_GWG_REQUEST)
        bad[4] = 0xC5
        with self.assertRaises(m.RejectUnproven):
            m.native_detection_contract(bytes(bad), m.NATIVE_REQUEST_LENGTH,
                                       m.NATIVE_ID_GATE, known_exports())

    def test_gwg_request_high_20bit_bank_not_misread_as_octet(self):
        self.assertEqual(m.NATIVE_GWG_REQUEST.count(b"\xc7"), 1)
        # C7 F8 04: one virtual 8-bit address byte F8 plus length byte 04.
        self.assertEqual(m.NATIVE_GWG_REQUEST[4], 0xC7)
        self.assertEqual(m.NATIVE_GWG_REQUEST[9], 0xF8)
        self.assertEqual(m.NATIVE_GWG_REQUEST[14], 0x04)

    def test_native_extended_request_len_rejected(self):
        bad = m.NATIVE_REQUEST_LENGTH.replace(b"\x03\x00\x00\x00", b"\x04\x00\x00\x00")
        with self.assertRaises(m.RejectUnproven):
            m.native_detection_contract(m.NATIVE_GWG_REQUEST, bad,
                                       m.NATIVE_ID_GATE, known_exports())

    def test_native_id_20c2_mutation_rejected(self):
        bad = bytearray(m.NATIVE_ID_GATE)
        bad = bad.replace(b"\x83\xf8\x54", b"\x83\xf8\xc2")
        with self.assertRaises(m.RejectUnproven):
            m.native_detection_contract(m.NATIVE_GWG_REQUEST, m.NATIVE_REQUEST_LENGTH,
                                       bytes(bad), known_exports())

    def test_native_new_exports_rejected(self):
        bad = known_exports()
        bad["ROM_Read"] = 0x1FFE
        with self.assertRaises(m.RejectUnproven):
            m.native_detection_contract(m.NATIVE_GWG_REQUEST,
                                       m.NATIVE_REQUEST_LENGTH, m.NATIVE_ID_GATE, bad)

    def test_original_bitconverter_calls(self):
        out = m.check_int32_calls(
            known_call_counts(), known_metadata(),
            {m.FAR_NON_ADDRESS_LITERAL: [m.FAR_NON_ADDRESS_OWNER]}, [])
        self.assertEqual(len(out["getbytes_int32_exact_calls"]), 2)
        self.assertEqual(out["high_bit_16_or_24_shifts"], 0)
        self.assertFalse(out["20bit_address_payload_serializer_demonstrated"])

    def test_20bit_rom_request_shifter_flagged(self):
        with self.assertRaises(m.RejectUnproven):
            m.check_int32_calls(
                known_call_counts(), known_metadata(),
                {m.FAR_NON_ADDRESS_LITERAL: [m.FAR_NON_ADDRESS_OWNER]},
                [{"method": "Fake20BitBank", "IL_offset": 22, "shift_bits": 16}])

    def test_added_int32_mem_reader_flagged(self):
        d = known_call_counts()
        d["AnotherHandler.WriteROMPageSelector"] = collections.Counter({
            m.GETBYTES_INT32_TOKEN: 1,
        })
        with self.assertRaises(m.RejectUnproven):
            m.check_int32_calls(d, known_metadata(),
                                {m.FAR_NON_ADDRESS_LITERAL: [m.FAR_NON_ADDRESS_OWNER]}, [])

    def test_missing_int32_ref_flagged(self):
        d = known_metadata()
        del d[m.GETBYTES_INT32_TOKEN]
        with self.assertRaises(m.RejectUnproven):
            m.check_int32_calls(known_call_counts(), d,
                                {m.FAR_NON_ADDRESS_LITERAL: [m.FAR_NON_ADDRESS_OWNER]}, [])

    def test_uint32_overload_change_flagged(self):
        d = known_metadata()
        d[m.GETBYTES_INT32_TOKEN] = ("GetBytes", bytes.fromhex("00011d0509"))
        with self.assertRaises(m.RejectUnproven):
            m.check_int32_calls(known_call_counts(), d,
                                {m.FAR_NON_ADDRESS_LITERAL: [m.FAR_NON_ADDRESS_OWNER]}, [])

    def test_rom_range_literal_flagged(self):
        with self.assertRaises(m.RejectUnproven):
            m.check_int32_calls(known_call_counts(), known_metadata(),
                                {0xF0000: ["SuspiciousROMReader"]}, [])

    def test_999999_decimal_not_misclassified(self):
        self.assertEqual(m.FAR_NON_ADDRESS_LITERAL, 0xF423F)
        self.assertIn("SerialPortValidator", m.FAR_NON_ADDRESS_OWNER)

    def test_shift16_scanner(self):
        self.assertEqual(m.high_shift_literals([ref("ldc.i4", 16), ref("shl")]),
                         [{"IL_offset": 0x10, "shift_bits": 16}])
        self.assertEqual(m.high_shift_literals([ref("ldc.i4", 24), ref("shr.un")]),
                         [{"IL_offset": 0x10, "shift_bits": 24}])
        self.assertEqual(m.high_shift_literals([ref("ldc.i4", 16), ref("ret")]), [])
        self.assertEqual(m.high_shift_literals([ref("ldc.i4", 15), ref("shr.un")]), [])

    def test_wrong_size_sha_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "fake.dll"
            p.write_bytes(b"MZ" * 10)
            with self.assertRaises(m.RejectUnproven):
                m.hash_source(p, m.ORIGINAL_HASHES["vsmGWG99Native.dll"])

    def test_originals_real_integrity_and_il_inventory(self):
        if not (m.CORE.exists() and m.NATIVE.exists() and m.PYDEPS.is_dir()):
            self.skipTest("Private Viessmann OEM original missing from CI environment")
        report = m.audit()
        self.assertEqual(report["audit"], "PASS")
        self.assertEqual(report["clr_methods_decoded"], 2490)
        self.assertEqual(report["native_gwg_detector"]["raw_send_bytes"], "c7f804")
        self.assertEqual(report["firmware_bytes_recovered"], 0)
        self.assertFalse(report["hidden_wb2a_application_rom_monitor_excluded"])
        self.assertFalse(report["ready_to_live_dump_program_rom"])

    def test_static_source_has_no_live_heater_action(self):
        contents = SRC.read_text()
        for forbidden in ("serial.Serial(", "/dev/tty", "writeraw;",
                          "subprocess.run", "socket.socket(",
                          "systemctl restart", "systemctl stop", "os.system(",
                          "flash_erase", "GenUI", "flash_write"):
            self.assertNotIn(forbidden, contents)


if __name__ == "__main__":
    unittest.main()
