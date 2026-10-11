"""Trust-boundary regression tests for active Vitotrol P300 live evidence."""
from __future__ import annotations
import importlib.util
from pathlib import Path
import sys
import unittest

P=Path(__file__).resolve().parents[1]/"tools"/"wb2a-vitotrol-p300-live-compare.py"
spec=importlib.util.spec_from_file_location("vito_active_comparison_tests",P)
m=importlib.util.module_from_spec(spec)
sys.modules[spec.name]=m
spec.loader.exec_module(m)

def virt(a0="02",sw="00000000",room="c800",sensor="03"):
    return dict(a0=a0,b0="03",type="00",swindex=sw,
                room_raw=room,sensor=sensor,current_fault="00")
def row(a0="02",mstr="0100b10a01010106c731",
        rx="0001b10a010110fe23d8",index="01",
        sw="00000000",room="c800",sensor="03"):
    return dict(virtual=virt(a0,sw,room,sensor),rx_descriptor="42160afe",
        rx_descriptor_index=index,rx_metadata="060001",
        master_tx=dict(frame_at_zero=mstr),
        rx_candidate=dict(frame_at_two=rx))
def report(a0="02"):
    base=dict(a0="00",b0="00",type="00",current_fault="00")
    return dict(restore_ok=True,remote_accepted_by_regulator=False,
        baseline_virtual=base,after_restore=base,
        live_snapshots=[row(a0=a0,rx="0011b3100101f811f938fa01fb0a1db1"),
        row(a0=a0,mstr="1100330a0101f80449ef",index="0a")])
def follower_report():
    return dict(matched_remote_type_a0="02",original_rx_first16_restored=True,
        restored=dict(a0="00",b0="00",type="00",current_fault="00"),
        staged_frame_count=1,master_frame_counts=dict( **{"110033":1}),
        staged_frames=[dict(readback_exact=True,
            master="1100330a0101f80449ef",
            response="0011b3100101f811f938fa01fb0a1db1")],
        controller_acknowledged_remote=False,
        observed_while_active=[virt(),virt()])

class LiveCompareTests(unittest.TestCase):
    def test_preseed_matched_v300_discovery_and_natural_overwrite_not_acceptance(self):
        v=m.summarize_preseed(report(),"v300_original")
        self.assertEqual(v["a0"],"02")
        self.assertTrue(v["first_identity_overwritten"])
        self.assertEqual(v["indices_at_discovery"],["0a"])
        self.assertEqual(v["discovery_ram_views"],1)
        self.assertFalse(v["two_readbacks_acceptance"])
        self.assertFalse(v["rx_isr_verified"])
    def test_variants_enforce_exact_a0_model_identity(self):
        r=report("01")
        self.assertEqual(m.summarize_preseed(r,"v200_reference")["a0"],"01")
        with self.assertRaises(m.EvidenceRejected):
            m.summarize_preseed(r,"v300_original")
        with self.assertRaises(m.EvidenceRejected):
            m.summarize_preseed(r,"invented")
    def test_snapshot_outlier_cannot_create_false_acceptance(self):
        r=report()
        r["live_snapshots"][0]["virtual"].update(
            swindex="01000000",room_raw="ce00",sensor="00")
        self.assertFalse(m.summarize_preseed(r,"v300_original")[
            "two_readbacks_acceptance"])
        r["remote_accepted_by_regulator"]=True
        with self.assertRaises(m.EvidenceRejected):
            m.summarize_preseed(r,"v300_original")
    def test_two_positive_readbacks_still_no_irq_proof(self):
        r=report()
        for x in r["live_snapshots"]:
            x["virtual"].update(swindex="01000000",room_raw="ce00",sensor="00")
        out=m.summarize_preseed(r,"v300_original")
        self.assertTrue(out["two_readbacks_acceptance"])
        self.assertFalse(out["rx_isr_verified"])
    def test_reject_unrestored_or_faulting_heating_state(self):
        for field in ("restore_ok","after_restore","baseline_virtual"):
            r=report()
            if field=="restore_ok":r[field]=False
            else:r[field]["a0"]="02"
            with self.subTest(field=field),self.assertRaises(m.EvidenceRejected):
                m.summarize_preseed(r,"v300_original")
        r=report();r["after_restore"]["current_fault"]="bc"
        with self.assertRaises(m.EvidenceRejected):
            m.summarize_preseed(r,"v300_original")
    def test_follower_requires_crc_source_known_b3_and_real_restore(self):
        r=follower_report()
        out=m.summarize_follower(r)
        self.assertEqual(out["staged_ram_responses"],1)
        self.assertFalse(out["two_readbacks_acceptance"])
        self.assertFalse(out["physical_on_wire_reply_verified"])
        r["staged_frames"][0]["response"]="0001b10a010110fe23d8"
        with self.assertRaises(m.EvidenceRejected):
            m.summarize_follower(r)
    def test_wrong_follower_variant_or_unrestored_never_pass(self):
        for edit in ("a0","rx","coding","fault"):
            r=follower_report()
            if edit=="a0":r["matched_remote_type_a0"]="01"
            if edit=="rx":r["original_rx_first16_restored"]=False
            if edit=="coding":r["restored"]["b0"]="03"
            if edit=="fault":r["restored"]["current_fault"]="bc"
            with self.subTest(edit=edit),self.assertRaises(m.EvidenceRejected):
                m.summarize_follower(r)
    def test_false_positive_ack_rejected_even_if_raw_write_succeeded(self):
        r=follower_report();r["controller_acknowledged_remote"]=True
        with self.assertRaises(m.EvidenceRejected):
            m.summarize_follower(r)

if __name__=="__main__":
    unittest.main()

# Optional live-fixture replay executes only when exact, SHA-attested on-device
# recordings are available. CI without private evidence still runs all negative
# synthetic bounds above, and does not need hardware or secrets.
class ActualWb2a20261011LiveEvidence(unittest.TestCase):
    EVIDENCE=(
        ("legacy_v300_a0_01", "wb2a-vitotrol-rx-preseed-live-20261011-1004.json",
         "5067e57033525811c258ac5c3152ce74b5df88e67f3b3551cfdb7e18fea14797"),
        ("v300_original","wb2a-vitotrol-a0-02-v300-preseed-live-20261011.json",
         "ae5ae8bc80839a51800c5457e71b439f639665c911019e5415f15b9c2fcd0d32"),
        ("v200_reference","wb2a-vitotrol-a0-01-v200-preseed-live-20261011.json",
         "8fe7a8655d9aafa5f73a4961b5f6469b87503b96bddabdc9771ef66be6560d2b"),
    )
    FOLLOWERS=(
        ("wb2a-vitotrol-a0-02-v300-follower-live-20261011.json",
         "894e689d7a94a830385cde69ea5996eccf926d0b7528d16734f6db2f0d954fcb",3),
        ("wb2a-v300-a02-type74-follower-20261011.json",
         "17425393f505f09864c248749b64c5eb28d8c1ef4839d24b5f2031a1c5d2e5da",2),
    )
    def load_pinned(self,name,sha):
        import hashlib
        import json
        path=Path("/tmp")/name
        if not path.exists():
            self.skipTest("private on-device live evidence absent from CI")
        raw=path.read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(),sha)
        return json.loads(raw)
    def test_three_model_variants_real_sha_pinned_evidence(self):
        expected=[8,5,4]
        for i,(name,path,sha) in enumerate(self.EVIDENCE):
            with self.subTest(name=name):
                x=m.summarize_preseed(self.load_pinned(path,sha),name)
                self.assertEqual(x["samples"],expected[i])
                self.assertEqual(x["discovery_ram_views"],1)
                self.assertFalse(x["two_readbacks_acceptance"])
                self.assertTrue(x["original_state_restored"])
    def test_both_actual_matched_v300_follower_trials(self):
        for path,sha,count in self.FOLLOWERS:
            with self.subTest(file=path):
                x=m.summarize_follower(self.load_pinned(path,sha))
                self.assertEqual(x["staged_ram_responses"],count)
                self.assertFalse(x["two_readbacks_acceptance"])
                self.assertTrue(x["restored"])
