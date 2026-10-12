"""Synthetic adversarial provenance tests for 2026-10-12 C5/F9 incident audit."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import unittest

SRC = Path(__file__).resolve().parents[1] / "tools/wb2a-c5-f9-incident-audit-offline.py"
spec = importlib.util.spec_from_file_location("wb2a_c5_f9_incident_audit_unit", SRC)
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
spec.loader.exec_module(m)


def fake_journal():
    return "\n".join([
        "2026-10-12T10:51:59+02:00 optolink-splitter python[1]: rx f9 20 26 10 12 01 02 42 08",
        "2026-10-12T11:20:00+02:00 optolink-splitter python[1]: 2026-10-12 11:20:00 [WARNING]: GFA_READ 0x4009 returned FF on fast attempt",
        "2026-10-12T11:43:15+02:00 optolink-splitter python[1]: rx c5 20 26 10 12 01 11 22 40",
        "2026-10-12T12:30:22+02:00 optolink-splitter python[1]: rx f9 20 26 10 12 01 12 22 24",
        "2026-10-12T12:33:33+02:00 optolink-splitter python[1]: rx telegr timeout",
    ]).encode() + b"\n"


class IncidentEvidenceOffline(unittest.TestCase):
    def test_synthetic_valid_exact_three_entries(self):
        result = m.analyze(fake_journal(), pin=False)
        self.assertEqual(result["audit"], "PASS")
        self.assertEqual(len(result["distinct_fault_events"]), 3)
        self.assertFalse(result["cause_established"])
        e = result["distinct_fault_events"]
        self.assertEqual(e[1]["controller"]["code"], "C5")
        self.assertEqual(e[1]["seconds_since_test_end"], 238)
        self.assertEqual(e[2]["seconds_since_test_end"], 3822)
        self.assertEqual(e[2]["logger_capture_delay_s"], 478)

    def test_exact_original_optional(self):
        try:
            b = m.ORIGINAL.read_bytes()
        except (FileNotFoundError, PermissionError):
            self.skipTest("LXC private journal not present")
        report = m.analyze(b, pin=True)
        self.assertEqual(report["journal_sha256"], m.SHA256)
        self.assertEqual(len(report["distinct_fault_events"]), 3)
        self.assertEqual(report["gfa_fast_retry_warnings_in_excerpt"], 31)
        self.assertEqual(report["optolink_transport_timeouts_in_excerpt"], 3)

    def test_fake_journal_sha_rejected(self):
        with self.assertRaises(m.IncidentRejected):
            m.analyze(fake_journal(), pin=True)

    def test_c5_falsified_date_rejected(self):
        b = fake_journal().replace(b"c5 20 26 10 12 01 11 22 40",
                                   b"c5 20 26 10 11 01 11 22 40")
        with self.assertRaises(m.IncidentRejected):
            m.analyze(b, pin=False)

    def test_missing_c5_rejected(self):
        b = fake_journal().replace(b"rx c5", b"not-c5")
        with self.assertRaises(m.IncidentRejected):
            m.analyze(b, pin=False)

    def test_missing_f9_new_rejected(self):
        b = fake_journal().replace(b"rx f9 20 26 10 12 01 12 22 24",
                                   b"rx ignored")
        with self.assertRaises(m.IncidentRejected):
            m.analyze(b, pin=False)

    def test_missing_old_f9_rejected(self):
        b = fake_journal().replace(b"rx f9 20 26 10 12 01 02 42 08",
                                   b"rx ignored")
        with self.assertRaises(m.IncidentRejected):
            m.analyze(b, pin=False)

    def test_injected_undocumented_fault_rejected(self):
        b = fake_journal() + b"2026-10-12T12:44:00+02:00 optolink-splitter python[1]: rx cd 20 26 10 12 01 12 24 00\n"
        with self.assertRaises(m.IncidentRejected):
            m.analyze(b, pin=False)

    def test_no_transport_warning_rejected(self):
        b = fake_journal().replace(b"[WARNING]: GFA_READ", b"[INFO]: GFA_READ")
        with self.assertRaises(m.IncidentRejected):
            m.analyze(b, pin=False)

    def test_missing_transport_timeout_rejected(self):
        b = fake_journal().replace(b"rx telegr timeout", b"rx ok")
        with self.assertRaises(m.IncidentRejected):
            m.analyze(b, pin=False)

    def test_host_observed_before_embedded_fault_rejected(self):
        b = fake_journal().replace(b"2026-10-12T11:43:15+02:00",
                                   b"2026-10-12T11:21:15+02:00")
        with self.assertRaises(m.IncidentRejected):
            m.analyze(b, pin=False)

    def test_not_device_error_same_as_legacy_gwg_opcode(self):
        row = m.decode_slot("c52026101201112240")
        self.assertEqual(row["code"], "C5")
        self.assertEqual(row["fault_at_controller_time"], "2026-10-12T11:22:40+02:00")

    def test_auditor_never_operates_heater(self):
        s = SRC.read_text()
        for forbidden in ("/dev/tty", "serial.Serial(", "systemctl stop",
                          "optolink-debug request", "writeraw;"):
            self.assertNotIn(forbidden, s)


if __name__ == "__main__":
    unittest.main()
