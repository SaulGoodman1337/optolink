"""Offline synthetic tests for WB2A archive delta safety checks.

No Optolink access, no systemd transitions, and no physical heater commands.
"""
import copy
from datetime import datetime, timedelta, timezone
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

P = Path(__file__).resolve().parents[1] / "tools/wb2a-experiment-fault-gate.py"
spec = importlib.util.spec_from_file_location("wb2a_experiment_fault_gate_unit", P)
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
spec.loader.exec_module(m)


def fake(addr, length):
    if addr == 0x00f8:
        return "20c2000300000103"
    if addr in (0x5738, 0x0a82):
        return "00"
    if length == 9:
        return "00ffffffffffffffff"
    raise AssertionError(f"unknown unexpected hardware command {addr:x}/{length}")


def fresh():
    return m.snapshot(fake)


def delayed(before, minutes=8):
    out = copy.deepcopy(before)
    at = datetime.fromisoformat(out["captured_at_utc"]) + timedelta(minutes=minutes)
    out["captured_at_utc"] = at.isoformat()
    out["began_at_utc"] = at.isoformat()
    return out


class FaultGateOffline(unittest.TestCase):
    def test_all_10_system_and_20_gfa_slots_are_in_plan(self):
        self.assertEqual(len(m.SYSTEM), 10)
        self.assertEqual(len(m.GFA), 20)
        self.assertEqual(len(m.PLAN), 33)
        self.assertEqual(m.SYSTEM[0], ("system_01", 0x7507, 9))
        self.assertEqual(m.SYSTEM[-1], ("system_10", 0x7558, 9))
        self.assertEqual(m.GFA[0], ("gfa_01", 0x7590, 9))
        self.assertEqual(m.GFA[-1], ("gfa_20", 0x763B, 9))
        self.assertEqual(len({i[1] for i in m.PLAN}), 33)

    def test_full_snapshot_unmodified_controller(self):
        result = fresh()
        m.validate(result)
        self.assertEqual(result["values"]["device_id"], m.DEVICE_ID)
        self.assertEqual(result["controller_writes"], 0)
        self.assertTrue(result["checked_all_system_slots"])
        self.assertTrue(result["checked_all_gfa_slots"])

    def test_no_change_observed_not_health_guarantee(self):
        a = fresh()
        b = delayed(a)
        r = m.compare(a, b)
        self.assertEqual(r["verdict"], "NO_CHANGE_OBSERVED")
        self.assertTrue(r["no_change_is_not_guarantee_of_future_healthy_controller"])

    def test_c5_first_seen_with_zero_gfa_status_still_alarm(self):
        a = fresh()
        b = delayed(a, minutes=4)
        b["values"]["system_03"] = "c52026101201112240"
        r = m.compare(a, b)
        self.assertEqual(r["verdict"], "ALARM")
        self.assertEqual(r["new_or_active_faults"][0]["after"]["code"], "C5")
        self.assertEqual(r["new_or_active_faults"][0]["after"]["controller_time"],
                         "2026-10-12T11:22:40")
        self.assertEqual(b["values"]["gfa_current"], "00")
        self.assertEqual(b["values"]["system_current"], "00")

    def test_second_f9_after_c5_alarm_again(self):
        a = fresh()
        a["values"]["system_03"] = "c52026101201112240"
        b = delayed(a, minutes=64)
        b["values"]["system_02"] = "f92026101201122224"
        r = m.compare(a, b)
        self.assertEqual(r["verdict"], "ALARM")
        self.assertEqual(r["new_or_active_faults"][0]["after"]["code"], "F9")

    def test_changed_gfa_zero_code_is_also_a_real_record_delta(self):
        a = fresh()
        b = delayed(a)
        b["values"]["gfa_01"] = "002026101201112640"
        r = m.compare(a, b)
        self.assertEqual(r["verdict"], "ALARM")
        self.assertEqual(r["new_or_active_faults"][0]["field"], "gfa_01")
        self.assertFalse(r["new_or_active_faults"][0]["after"]["code_meaning_verified"])

    def test_active_fault_snapshot_can_be_preserved_for_alert(self):
        def active(addr, length):
            return "01" if addr == 0x0a82 else fake(addr, length)
        post = m.snapshot(active)
        self.assertTrue(post["active_fault_at_capture"])
        m.validate(post)

    def test_gfa_status_nonzero_alert(self):
        a = fresh()
        b = delayed(a)
        b["values"]["gfa_current"] = "f9"
        self.assertEqual(m.compare(a, b)["verdict"], "ALARM")

    def test_system_alarm_nonzero_alert(self):
        a = fresh()
        b = delayed(a)
        b["values"]["system_current"] = "01"
        self.assertEqual(m.compare(a, b)["verdict"], "ALARM")

    def test_missing_system_slot_rejected(self):
        a = fresh()
        del a["values"]["system_08"]
        with self.assertRaises(m.SafetyAlarm):
            m.validate(a)

    def test_missing_gfa_slot_rejected(self):
        a = fresh()
        del a["values"]["gfa_20"]
        with self.assertRaises(m.SafetyAlarm):
            m.validate(a)

    def test_wrong_controller_not_accepted(self):
        a = fresh()
        a["values"]["device_id"] = "2053000300000103"
        with self.assertRaises(m.SafetyAlarm):
            m.validate(a)

    def test_old_and_new_scope_mismatch_refused(self):
        a = fresh()
        b = m.snapshot(fake, include_gfa_history=False)
        b = delayed(b)
        with self.assertRaises(m.SafetyAlarm):
            m.compare(a, b)

    def test_partial_gfa_scope_explicitly_reported(self):
        a = m.snapshot(fake, include_gfa_history=False)
        b = delayed(a)
        r = m.compare(a, b)
        self.assertTrue(r["complete_system_archive_checked"])
        self.assertFalse(r["complete_gfa_archive_checked"])

    def test_stale_baseline_cannot_pass(self):
        a = fresh()
        b = delayed(a, minutes=241)
        with self.assertRaises(m.SafetyAlarm):
            m.compare(a, b)

    def test_reversed_time_cannot_pass(self):
        a = fresh()
        b = delayed(a, minutes=-1)
        with self.assertRaises(m.SafetyAlarm):
            m.compare(a, b)

    def test_bad_response_code_rejected(self):
        with self.assertRaises(m.SafetyAlarm):
            m.read_reply("read;0x5738;1  <- openv/resp: 255;0x5738;ff", 0x5738, 1)

    def test_wrong_returned_address_rejected(self):
        with self.assertRaises(m.SafetyAlarm):
            m.read_reply("read;0x5738;1  <- openv/resp: 1;0x0a82;00", 0x5738, 1)

    def test_short_response_rejected(self):
        with self.assertRaises(m.SafetyAlarm):
            m.read_reply("read;0x5738;1  <- openv/resp: 1;0x5738;", 0x5738, 1)

    def test_multi_response_ambiguous_rejected(self):
        row = "read;0x5738;1  <- openv/resp: 1;0x5738;00"
        with self.assertRaises(m.SafetyAlarm):
            m.read_reply(row + "\n" + row, 0x5738, 1)

    def test_actual_cli_shape_passes(self):
        self.assertEqual(m.read_reply(
            "request start\nread;0x7519;9  <- openv/resp: 1;0x7519;c52026101201112240",
            0x7519, 9), "c52026101201112240")

    def test_bcd_1970_slot_kept_not_misinterpreted_as_current(self):
        row = m.archive_display("b71970010104000000")
        self.assertEqual(row["controller_time"], "1970-01-01T00:00:00")

    def test_invalid_archive_date_rejected(self):
        with self.assertRaises(m.SafetyAlarm):
            m.archive_display("c52026109901112240")

    def test_invalid_snapshot_size_rejected(self):
        a = fresh()
        a["values"]["system_01"] = "c5"
        with self.assertRaises(m.SafetyAlarm):
            m.validate(a)

    def test_private_snapshot_nonoverwriting(self):
        with tempfile.TemporaryDirectory(prefix="wb2a-faultgate-test-") as td:
            p = Path(td) / "snap.json"
            m.save(p, fresh())
            self.assertEqual(p.stat().st_mode & 0o777, 0o600)
            self.assertEqual(m.load(p)["schema"], 1)
            with self.assertRaises(FileExistsError):
                m.save(p, fresh())

    def test_source_never_takes_hardware_port_or_writes(self):
        source = P.read_text()
        for verboten in ("/dev/tty", "serial.Serial(", "writeraw;", "systemctl stop",
                         "bootloader", "GFA_WRITE", "f4;"):
            self.assertNotIn(verboten, source)
        self.assertEqual({name for name, _, _ in m.PLAN}, set(m.EXPECTED_NAMES))


if __name__ == "__main__":
    unittest.main()
