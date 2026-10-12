"""Offline safety checks for 2053 GWG EEPROM/PORT source-backed probes."""
from __future__ import annotations
import importlib.util
from pathlib import Path
import sys
import unittest

SRC = Path(__file__).resolve().parents[1] / "tools" / "wb2a-gwg-legacy-readtypes-live.py"
spec = importlib.util.spec_from_file_location("gwg_2053_historical_modes_offline", SRC)
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)


class Port:
    def __init__(self, reply):
        self.writes = []
        self.reply = reply
        self.ready = False
        self.pending = b""
    def reset_input_buffer(self):
        self.pending = b""
    def write(self, data):
        data = bytes(data)
        self.writes.append(data.hex())
        if data == bytes((4,)):
            self.ready = True
        elif data.hex() in mod.ALLOWED:
            self.pending = self.reply
        else:
            raise AssertionError("unexpected unsafe tx")
        return len(data)
    def flush(self):
        pass
    def read(self, n):
        if self.ready:
            self.ready = False
            return bytes((5,))
        return b""
    def read_all(self):
        r = self.pending
        self.pending = b""
        return r


class LegacyGWGReadTypeSafety(unittest.TestCase):
    def test_sources_are_exactly_two_historical_shapes(self):
        self.assertEqual(mod.ALLOWED, {
            "01f700f804", "01c7f80404", "01ae170204", "016e010104"})
        self.assertEqual(len(mod.CASES), 8)

    def test_no_write_opcodes_anywhere(self):
        self.assertTrue(all(bytes.fromhex(w)[1] in (0xF7, 0xC7, 0xAE, 0x6E)
                            for w in mod.ALLOWED))

    def test_exact_historical_2053_ae(self):
        p = Port(bytes.fromhex("1234"))
        row = mod.one(p, "01ae170204", 2)
        self.assertTrue(row["sync"])
        self.assertEqual(row["reply"], "1234")
        self.assertEqual(p.writes, ["04", "01ae170204"])

    def test_exact_historical_2053_6e(self):
        p = Port(bytes((0x7F,)))
        row = mod.one(p, "016e010104", 1)
        self.assertEqual(row["reply"], "7f")
        self.assertEqual(p.writes, ["04", "016e010104"])

    def test_ambiguous_idle_enq_quarantined(self):
        p = Port(bytes((5,)))
        row = mod.one(p, "016e010104", 1)
        self.assertEqual(row["outcome"], "AMBIGUOUS_IDLE_ENQ_OR_DATA_05")

    def test_partial_result_not_interpreted_semantically(self):
        p = Port(bytes.fromhex("12"))
        row = mod.one(p, "01ae170204", 2)
        self.assertEqual(row["outcome"], "UNEXPECTED_LENGTH")

    def test_unlisted_frame_rejected_without_io(self):
        p = Port(b"")
        with self.assertRaises(mod.Refused):
            mod.one(p, "01c8f80404", 4)
        self.assertEqual(p.writes, [])

    def test_unlisted_size_rejected_without_io(self):
        p = Port(b"")
        with self.assertRaises(mod.Refused):
            mod.one(p, "01ae170204", 8)
        self.assertEqual(p.writes, [])

    def test_requires_root_and_restoration(self):
        with self.assertRaises(mod.Refused):
            mod.checks(Path("/tmp/example-other-output"), False)

    def test_fixed_output_and_two_independent_kw_guards(self):
        self.assertEqual(mod.OUTPUT.name, "wb2a-gwg-legacy-readtypes-live-20261012.json")
        self.assertEqual(mod.CASES[0][0], "kw_before")
        self.assertEqual(mod.CASES[-1][0], "kw_after")
        self.assertEqual(mod.CASES[1][0], "gwg_before")
        self.assertEqual(mod.CASES[-2][0], "gwg_after")


if __name__ == "__main__":
    unittest.main()
