"""Real original optional and adversarial synthetic M16C raw-SRAM benchmark tests."""
from __future__ import annotations

from pathlib import Path
import importlib.util
import sys
import unittest

P = Path(__file__).resolve().parents[1] / "tools" / "wb2a-m16c-cache-disasm-audit.py"
sp = importlib.util.spec_from_file_location("wb2a_m16c_cache_benchmark", P)
m = importlib.util.module_from_spec(sp)
sys.modules[sp.name] = m
sp.loader.exec_module(m)


def valid_log(filename="raw_2182_53ff_real.bin", **overrides):
    values = {
        "name": filename, "language": m.LANGUAGE, "base": "002182",
        "length": 12926, "seed_attempts": 134, "seed_success": 134,
        "instructions": 1810, "covered_bytes": 4149, "coverage": "0.3210",
        "jumps": 139, "calls": 61, "terminals": 21,
        "inner_targets": 119, "external_targets": 38,
        "highrom_targets": 4, "mnemonics": "MOV.B:S:203,ADD.B:S:106",
    }
    values.update(overrides)
    return ("INFO Wb2aM16cCacheProbe.java> WB2A_M16C_PROBE_RESULT "
            "filename={name} lang={language} base={base} len={length} "
            "seed_attempts={seed_attempts} seed_success={seed_success} "
            "instructions={instructions} covered_bytes={covered_bytes} "
            "coverage={coverage} jumps={jumps} calls={calls} terminals={terminals} "
            "inner_targets={inner_targets} external_targets={external_targets} "
            "highrom_targets={highrom_targets} mnemonic_top={mnemonics} (GhidraScript)\n").format(**values)


class CacheTests(unittest.TestCase):
    def test_checked_in_ghidra_java_source_is_pinned(self):
        script = P.parent / "Wb2aM16cCacheProbe.java"
        self.assertEqual(m.sha_path(script, m.PROBE_SHA256, m.PROBE_SIZE),
                         m.PROBE_SHA256)

    def test_source_controls_have_expected_count_and_span(self):
        self.assertEqual(len(m.CONTROL_SEEDS), 10)
        self.assertEqual(m.CONTROL_SEEDS[0], 20261012)
        self.assertEqual(m.CONTROL_SEEDS[-1], 20261021)
        self.assertEqual(m.REAL_LEN, 0x5400 - 0x2182)

    def test_reproducible_histogram_shuffling(self):
        sample = bytes([0, 1, 1, 2, 7] * 31)
        a = m.shuffle_control(sample, 20261012)
        b = m.shuffle_control(sample, 20261012)
        self.assertEqual(a, b)
        self.assertEqual(sorted(a), sorted(sample))
        self.assertNotEqual(a, sample)

    def test_different_controls_preserve_same_frequency(self):
        sample = bytes(range(256)) * 8
        out = [m.shuffle_control(sample, seed) for seed in m.CONTROL_SEEDS]
        self.assertEqual(len(set(out)), 10)
        self.assertTrue(all(sorted(x) == sorted(sample) for x in out))

    def test_unknown_permutation_seed_fails(self):
        with self.assertRaises(m.EvidenceRejected):
            m.shuffle_control(b"ABCD", 0)

    def test_original_must_be_original_sha(self):
        with self.assertRaises(m.EvidenceRejected):
            m.original_bytes(b"A" * m.REAL_LEN)

    def test_parse_real_like_ghidra_log(self):
        x = m.extract_probe(valid_log(), "raw_2182_53ff_real.bin")
        self.assertEqual(x["seed_attempts"], 134)
        self.assertEqual(x["instructions"], 1810)
        self.assertEqual(x["covered_bytes"], 4149)
        self.assertEqual(x["highrom_targets"], 4)
        self.assertEqual(x["coverage"], 0.3210)

    def test_wrong_processor_rejected(self):
        with self.assertRaises(m.EvidenceRejected):
            m.extract_probe(valid_log(language="M16C/80:LE:16:default"),
                            "raw_2182_53ff_real.bin")

    def test_wrong_processor_window_base_rejected(self):
        with self.assertRaises(m.EvidenceRejected):
            m.extract_probe(valid_log(base="002184"),
                            "raw_2182_53ff_real.bin")

    def test_wrong_read_source_file_rejected(self):
        with self.assertRaises(m.EvidenceRejected):
            m.extract_probe(valid_log(), "raw_2182_53ff_random_control.bin")

    def test_script_failure_rejected(self):
        with self.assertRaises(m.EvidenceRejected):
            m.extract_probe(valid_log() + "ERROR REPORT SCRIPT ERROR\n",
                            "raw_2182_53ff_real.bin")

    def test_duplicate_headless_marker_rejected(self):
        with self.assertRaises(m.EvidenceRejected):
            m.extract_probe(valid_log() + valid_log(),
                            "raw_2182_53ff_real.bin")

    def test_coverage_mismatch_rejected(self):
        with self.assertRaises(m.EvidenceRejected):
            m.extract_probe(valid_log(covered_bytes=6000),
                            "raw_2182_53ff_real.bin")

    def test_nonuniform_seed_attempt_rejected(self):
        with self.assertRaises(m.EvidenceRejected):
            m.extract_probe(valid_log(seed_attempts=133),
                            "raw_2182_53ff_real.bin")

    def test_invalid_covered_size_rejected(self):
        with self.assertRaises(m.EvidenceRejected):
            m.extract_probe(valid_log(covered_bytes=20000, coverage="1.5472"),
                            "raw_2182_53ff_real.bin")

    def test_single_match_no_firmware_proven(self):
        a = m.extract_probe(valid_log(), "raw_2182_53ff_real.bin")
        controls = [{**a, "coverage": 0.2886 + i * 0.008,
                     "calls": 49 + i, "highrom_targets": 4 + (i % 4),
                     "inner_targets": 119 + i * 3,
                     "instructions": 1600 + 25 * i} for i in range(10)]
        result = m.compare(a, controls)
        self.assertEqual(result["control_count"], 10)
        self.assertTrue(result["comparison"]["coverage"]["observed_within_control_range"])
        self.assertEqual(result["hex_bytes_recovered_directly_from_program_ROM"], 0)
        self.assertFalse(result["real_ram_m16c_executable_code_proven"])
        self.assertFalse(result["resident_flash_or_rom_image_proven"])

    def test_too_few_controls_rejected(self):
        a = m.extract_probe(valid_log(), "raw_2182_53ff_real.bin")
        with self.assertRaises(m.EvidenceRejected):
            m.compare(a, [a] * 4)

    def test_raw_metrics_mismatch_rejected(self):
        a = m.extract_probe(valid_log(), "raw_2182_53ff_real.bin")
        with self.assertRaises(m.EvidenceRejected):
            m.compare(a, [{"coverage": 0.3}] * 5)

    def test_full_source_files_if_locally_available(self):
        root = Path("/home/chatgpt-admin/research/firmware-m16c-workbench-20261012")
        if not (root / "ghidra-shuffle-20261021.log").is_file():
            self.skipTest("Private Ghidra/OEM images not available in GitHub CI")
        result = m.audit_workbench(root)
        self.assertEqual(result["audit"], "PASS")
        self.assertEqual(result["control_count"], 10)
        self.assertEqual(result["source"]["bytes"], 12926)
        self.assertEqual(result["real"]["covered_bytes"], 4149)
        self.assertEqual(result["live_heater_reads"], 0)
        self.assertEqual(result["live_heater_writes"], 0)

    def test_auditor_has_no_live_or_command_execution(self):
        source = P.read_text()
        for word in ("serial.Serial(", "/dev/tty", "subprocess.run(",
                     "os.system(", "systemctl ", "socket.socket(",
                     "GenUI.issueNewTurn", "writeraw;", "sshpass"):
            self.assertNotIn(word, source)


if __name__ == "__main__":
    unittest.main()
