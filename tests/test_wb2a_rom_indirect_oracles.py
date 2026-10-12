"""Adversarial and positive tests for strictly offline checksum byte-oracle."""
import binascii
import hashlib
import importlib.util
from pathlib import Path
import sys
import unittest

SRC = Path(__file__).resolve().parents[1] / "tools/wb2a-rom-indirect-oracles.py"
spec = importlib.util.spec_from_file_location("wb2a_indirect_rom_oracle", SRC)
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
spec.loader.exec_module(m)


def prefix_series(secret: bytes, start: int = 0, initial: int = 0xffff):
    first = binascii.crc_hqx(secret[:start], initial)
    return first, [
        {"length": n, "crc": binascii.crc_hqx(secret[:n], initial)}
        for n in range(start + 1, len(secret) + 1)
    ]


def gate(**overrides):
    kwargs = dict(device="20C2/0103", measured=False, read_only=False,
                  same_start=False, selectable_length=False,
                  known_crc16_ccitt=False, sequential_prefix_responses=False,
                  controller_identity_verified=True)
    kwargs.update(overrides)
    return m.candidate_gate(**kwargs)


class OfflineRomOracleTests(unittest.TestCase):
    def test_known_crc16_ccitt_false_vector(self):
        self.assertEqual(binascii.crc_hqx(b"123456789", 0xffff), 0x29b1)

    def test_complete_synthetic_512byte_secret(self):
        # Private, pseudo-random artificial data; NEVER a controller ROM.
        secret = b"".join(hashlib.sha256(str(i).encode()).digest()
                          for i in range(16))
        first, values = prefix_series(secret)
        self.assertEqual(len(values), 512)
        self.assertEqual(m.recover_contiguous_prefix_oracle(
            values, first_length=0, first_crc=first), secret)

    def test_recover_suffix_without_exposing_initial_prefix(self):
        secret = b"unknown-prefix-" + bytes(range(100))
        start = 15
        first, values = prefix_series(secret, start)
        self.assertEqual(m.recover_contiguous_prefix_oracle(
            values, first_length=start, first_crc=first), secret[start:])

    def test_modifying_any_observed_checksum_fails_closed(self):
        secret = b"ABCDEF"
        first, values = prefix_series(secret)
        # CRC-16 of one new byte has only 256 of 65536 possible results.
        reachable = {binascii.crc_hqx(bytes([b]), values[0]["crc"])
                     for b in range(256)}
        unreachable = next(v for v in range(65536) if v not in reachable)
        values[1]["crc"] = unreachable
        with self.assertRaises(m.OracleRejected):
            m.recover_contiguous_prefix_oracle(
                values, first_length=0, first_crc=first)

    def test_wrong_algorithm_response_rejected(self):
        first, values = prefix_series(b"abc")
        values[0]["crc"] = 0xBAD
        if 0xBAD in {binascii.crc_hqx(bytes([v]), first)
                     for v in range(256)}:
            values[0]["crc"] = 0xA5A5
        with self.assertRaises(m.OracleRejected):
            m.recover_contiguous_prefix_oracle(
                values, first_length=0, first_crc=first)

    def test_gap_or_reordered_prefix_lengths_rejected(self):
        first, values = prefix_series(b"ABCDEFGHIJKLMN")
        for badlen in (0, 3, 999, True, "2"):
            tampered = [dict(x) for x in values]
            tampered[1]["length"] = badlen
            with self.subTest(badlen=badlen), self.assertRaises(m.OracleRejected):
                m.recover_contiguous_prefix_oracle(
                    tampered, first_length=0, first_crc=first)

    def test_missing_samples_rejected(self):
        with self.assertRaises(m.OracleRejected):
            m.recover_contiguous_prefix_oracle(
                [], first_length=0, first_crc=0xffff)

    def test_invalid_crc_word_rejected(self):
        for bad in (-1, 65536, True, None, 1.5, "ABCD"):
            with self.subTest(bad=bad), self.assertRaises(m.OracleRejected):
                m.recover_appended_byte(bad, 0xabcd)

    def test_crc_requires_exact_sample_shape(self):
        for bad in ({}, {"length": 1, "crc": 42, "source": "real"}, [1, 2]):
            with self.subTest(bad=bad), self.assertRaises(m.OracleRejected):
                m.recover_contiguous_prefix_oracle(
                    [bad], first_length=0, first_crc=0xffff)

    def test_default_gate_exposes_missing_real_evidence(self):
        result = gate()
        self.assertFalse(result["hypothesis_passes_evidence_gate"])
        self.assertFalse(result["live_read_allowed_by_this_audit"])
        self.assertIn("selectable_prefix_length_N", result["missing_requirements"])

    def test_even_perfect_paper_gate_never_authorizes_live(self):
        result = gate(measured=True, read_only=True, same_start=True,
                      selectable_length=True, known_crc16_ccitt=True,
                      sequential_prefix_responses=True,
                      controller_identity_verified=True)
        self.assertTrue(result["hypothesis_passes_evidence_gate"])
        self.assertFalse(result["live_read_allowed_by_this_audit"])
        self.assertEqual(result["missing_requirements"], [])

    def test_wrong_device_rejected(self):
        self.assertIn("exact_20C2_identity",
                      gate(device="2098/0002")["missing_requirements"])

    def test_gate_rejects_fake_string_flags(self):
        with self.assertRaises(m.OracleRejected):
            gate(measured="True")

    def test_huge_prefix_and_truncated_data_rejected(self):
        with self.assertRaises(m.OracleRejected):
            m.recover_contiguous_prefix_oracle(
                [{"length": 1048577, "crc": 1}],
                first_length=1048576, first_crc=0)

    def test_only_bounded_offline_source_code(self):
        source = SRC.read_text()
        for forbidden in ("serial.Serial(", "/dev/tty", "socket.socket(",
                          "subprocess.run(", "os.system(", "systemctl ",
                          "writeraw;", "flash_erase", "flash_write"):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
