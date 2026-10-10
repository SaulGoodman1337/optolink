"""Synthetic and corrupted-evidence regression tests, no hardware access."""
from __future__ import annotations
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "tools" / "wb2a-rpm-offline-audit.py"
spec = importlib.util.spec_from_file_location("rpm_offline_audit", SCRIPT)
auditlib = importlib.util.module_from_spec(spec)
import sys
sys.modules[spec.name] = auditlib
spec.loader.exec_module(auditlib)


def candidate(x=84, y=84, flame=True, lockout=False, coherent=True):
    return auditlib.Candidate(x,y,flame,lockout,coherent)


def cycle(i, *, x=84, y=84, flame=True, status_change=False):
    t = float(i*2)
    a = dict(byte0=25,byte9=25,flame=flame,lockout=False,rx_monotonic=t+0.1)
    b = dict(a,rx_monotonic=t+0.4)
    changes = {"flame":False,"lockout":False,"modulation":status_change,"p87":False}
    return dict(cycle=i, start_monotonic=t,end_monotonic=t+0.5,
                candidates={"0f20":x,"1c76":y,"copies_equal":True},
                first_status=a,last_status=b,
                quality={"status_coherent":not status_change,
                         "native_status_changed_within_pair":changes},
                core_length=64,core_offset=(i-1)*64,core_sha256=hashlib.sha256(bytes([i])*64).hexdigest())


class OfflineEvidenceTests(unittest.TestCase):
    def test_strict_plateau_numeric_match_cannot_verify_rpm(self):
        status = auditlib.classify_plateau([candidate(),candidate()],
                                           [candidate(),candidate()],[83]*6)
        self.assertEqual(status,"NUMERICALLY_CONSISTENT_NOT_VERIFIED")

    def test_distinct_stable_mismatch_refutes_simple_formula(self):
        status = auditlib.classify_plateau([candidate(172,172),candidate(172,172)],
                                           [candidate(172,172),candidate(172,172)],
                                           [83]*6)
        self.assertEqual(status,"P06_PLUS_ONE_NUMERIC_MISMATCH")

    def test_candidate_change_across_vs1_gap_is_inconclusive(self):
        status = auditlib.classify_plateau([candidate(),candidate()],
                                           [candidate(172,172),candidate(172,172)],
                                           [83]*6)
        self.assertEqual(status,"TRANSITION_OR_UNKNOWN")

    def test_ff_is_invalid_not_a_match(self):
        self.assertEqual(auditlib.classify_plateau([candidate()]*2,
                          [candidate()]*2,[83,83,255,83,83,83]),"INVALID_P06_FF")

    def test_zero_is_not_a_positive_plateau(self):
        self.assertEqual(auditlib.classify_plateau([candidate(0,0)]*2,
                          [candidate(0,0)]*2,[0]*6),"NO_POSITIVE_PLATEAU")

    def test_partial_bracket_cannot_be_used(self):
        self.assertEqual(auditlib.classify_plateau([candidate()],
                          [candidate()]*2,[83]*6),"INSUFFICIENT_BRACKET")

    def test_lockout_and_status_shift_refuse(self):
        for item in (candidate(lockout=True),candidate(coherent=False),
                     candidate(84,93)):
            with self.subTest(item=item):
                self.assertEqual(auditlib.classify_plateau([candidate(),item],
                          [candidate()]*2,[83]*6),"TRANSITION_OR_UNKNOWN")

    def test_invalid_status_types_refuse(self):
        with self.assertRaises(auditlib.EvidenceError):
            auditlib.classify_plateau([candidate()]*2,
                          [candidate(coherent=1)]*2,[83]*6)

    def test_high_trigger_requires_two_independent_factors(self):
        row=cycle(1,x=172,y=172)
        self.assertTrue(auditlib.qualify_high(row))
        row["first_status"]["flame"]=False
        self.assertFalse(auditlib.qualify_high(row))
        row["first_status"]["flame"]=True
        row["quality"]["native_status_changed_within_pair"]["p87"]=True
        self.assertFalse(auditlib.qualify_high(row))

    def _files(self, rows, valid_p06=True):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        base=Path(tmp.name)
        cycles=base/"cycles.jsonl"
        vs1=base/"vs1.jsonl"
        core=base/"core-pairs.bin"
        cycles.write_text("".join(json.dumps(row)+"\n" for row in rows))
        vs1.write_text(json.dumps({"key":"P06","side":"PRE",
                                   "hex":"53" if valid_p06 else "ff",
                                   "valid":valid_p06,"t_monotonic":0.9})+"\n")
        core.write_bytes(b"".join(bytes([i])*64 for i in range(1,len(rows)+1)))
        return cycles,vs1,core

    def test_archive_shas_and_no_verified_rpm_output(self):
        files=self._files([cycle(1,x=172,y=172),cycle(2,x=172,y=172)])
        result=auditlib.audit(*files)
        self.assertEqual(result["cycles"],2)
        self.assertEqual(result["core_sha256_checked"],2)
        self.assertEqual(result["high_eligible_runs_min_two"],1)
        self.assertFalse(result["p300_actual_p06_verified"])
        self.assertIsNone(result["p300_rpm_value"])
        self.assertEqual(result["vs1_p06_valid_positive_levels"],[83])

    def test_sha_mismatch_rejected(self):
        c,v,core=self._files([cycle(1)])
        core.write_bytes(b"x"*64)
        with self.assertRaisesRegex(auditlib.EvidenceError,"SHA256 mismatch"):
            auditlib.audit(c,v,core)

    def test_missing_core_rejected(self):
        c,v,core=self._files([cycle(1)])
        core.unlink()
        with self.assertRaises(FileNotFoundError):
            auditlib.audit(c,v,core)

    def test_no_monotonic_gap_or_repeated_cycle_allowed(self):
        c,v,core=self._files([cycle(1),cycle(2)])
        rows=[cycle(1),cycle(1)]
        c.write_text("".join(json.dumps(x)+"\n" for x in rows))
        with self.assertRaisesRegex(auditlib.EvidenceError,"cycle IDs"):
            auditlib.audit(c,v,core)

    def test_invalid_json_never_accepted(self):
        c,v,core=self._files([cycle(1)])
        c.write_text("not json\n")
        with self.assertRaises(auditlib.EvidenceError):
            auditlib.audit(c,v,core)


if __name__ == "__main__":
    unittest.main()
