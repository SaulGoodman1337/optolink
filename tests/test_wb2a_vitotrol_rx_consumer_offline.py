"""A: deterministic RX/consumer-state negative controls and pinned-live audit."""
from __future__ import annotations
import copy
import importlib.util
import json
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/"tools/wb2a-vitotrol-rx-consumer-offline.py"
spec=importlib.util.spec_from_file_location("wb2a_vt_rx_consumer_offline_test",SRC)
m=importlib.util.module_from_spec(spec)
sys.modules[spec.name]=m
spec.loader.exec_module(m)
FULL=Path("/root/p300-trial-work/research-bundles/p300-fullram-run-20261009T083607Z-144293-bundle.tar.gz")
DEEP=Path("/root/p300-trial-work/research-bundles/p300-deep-run-20261009T070505Z-130246-bundle.tar.gz")
PRE=Path("/tmp/wb2a-vitotrol-a0-02-v300-preseed-live-20261011.json")
EARLIER=Path("/tmp/wb2a-vitotrol-rx-preseed-live-20261011-1004.json")


def synth_frame(value):
    f=bytes.fromhex(value)
    return (bytes(2)+f).ljust(32,b"\x00").hex()


def sample(index,frame,metadata="060001",desc_index="01"):
    return {
        "rx_candidate":{"raw":synth_frame(frame)},
        "master_tx":{"raw":bytes.fromhex("0100b10a01010106c731").ljust(32,b"\x00").hex()},
        "rx_metadata":metadata,"rx_descriptor":m.DESC,
        "rx_descriptor_index":desc_index,
        "sample_s":100+index*5,
    }


def doc():
    return {
        "remote_accepted_by_regulator":False,
        "controller_rx_isr_or_parser_invocation_proven":False,
        "km_bus_phy_is_not_emulated":True,
        "restore_ok":True,"rx_physical_write_readback_exact":True,
        "live_snapshots":[sample(0,m.ORIGINAL_B3),sample(1,m.NATURAL_B1),
                          sample(2,m.NATURAL_B1,desc_index="0a"),
                          sample(3,m.NATURAL_B1)]
    }


class RxConsumerOfflineTests(unittest.TestCase):
    def test_no_consumer_signal_created_by_ram_content_alone(self):
        r=m.preseed_analysis(doc(),"v300_initial_preseed")
        self.assertTrue(r["initial_class11_B3_found_in_ram"])
        self.assertTrue(r["next_class01_B1_replaced_B3"])
        self.assertTrue(r["metadata_unchanged_across_replacement"])
        self.assertEqual(r["preceding_descriptor_byte_values"],{"0x01":3,"0x0a":1})
        self.assertFalse(r["actual_controller_vitotrol_registered"])
        self.assertFalse(r["controller_state_writes_authorized_by_this_audit"])

    def test_metadata_may_change_without_becoming_ready_flag(self):
        x=doc()
        x["live_snapshots"][2]["rx_metadata"]="0a0401"
        r=m.preseed_analysis(x,"v300_earlier_preseed")
        self.assertFalse(r["all_metadata_equal"])
        self.assertTrue(r["metadata_unchanged_across_replacement"])
        self.assertFalse(r["actual_controller_vitotrol_registered"])

    def test_crc_invalid_rejected(self):
        x=doc()
        raw=bytearray.fromhex(x["live_snapshots"][0]["rx_candidate"]["raw"])
        raw[10]^=1
        x["live_snapshots"][0]["rx_candidate"]["raw"]=raw.hex()
        with self.assertRaises(m.EvidenceRejected):
            m.preseed_analysis(x,"v300_initial_preseed")

    def test_order_reversal_rejected(self):
        x=doc()
        x["live_snapshots"][1]["sample_s"]=x["live_snapshots"][0]["sample_s"]
        with self.assertRaises(m.EvidenceRejected):
            m.preseed_analysis(x,"v300_initial_preseed")

    def test_unrecognized_reply_and_wrong_snapshot_count(self):
        x=doc()
        x["live_snapshots"][1]["rx_candidate"]["raw"]=synth_frame(m.ORIGINAL_B3)
        with self.assertRaises(m.EvidenceRejected):
            m.preseed_analysis(x,"v300_initial_preseed")
        x=doc()
        x["live_snapshots"]=x["live_snapshots"][:2]
        with self.assertRaises(m.EvidenceRejected):
            m.preseed_analysis(x,"v300_initial_preseed")

    def test_no_invalid_restore_or_unsupported_readback(self):
        for field,bad in [("remote_accepted_by_regulator",True),
                          ("restore_ok",False),
                          ("rx_physical_write_readback_exact",False),
                          ("controller_rx_isr_or_parser_invocation_proven",True)]:
            x=doc()
            x[field]=bad
            with self.subTest(field=field),self.assertRaises(m.EvidenceRejected):
                m.preseed_analysis(x,"v300_initial_preseed")

    def test_private_sources_pinned_and_observational_when_available(self):
        try:
            original={k:p.read_bytes() for k,p in [
                ("full",FULL),("deep",DEEP),("pre",PRE),("earlier",EARLIER)]}
        except (FileNotFoundError,PermissionError):
            self.skipTest("authentic private root-only research capture unavailable")
        r=m.run(original["full"],original["deep"],
                {"v300_initial_preseed":original["pre"],
                 "v300_earlier_preseed":original["earlier"]})
        self.assertEqual(r["fullram"]["snapshots"],79)
        self.assertEqual(r["deep"]["paired_contexts"],295)
        self.assertEqual(r["total_preseed_snapshots"],13)
        self.assertEqual(r["fullram"]["preceding_byte_0b6b_counts"],
                         {"01":72,"0a":3,"0b":4})
        self.assertEqual(r["fullram"]["descriptor_0b6d_counts"],
                         {"42160afe":79})
        self.assertEqual(len(r["fullram"]["rx_by_descriptor_preceding_and_166a"]),4)
        self.assertEqual(r["fullram"]["class11_rx_buffer_samples"],0)
        self.assertEqual(r["deep"]["tx_crc_validity"],
                         {"VALID":292,"UNVERIFIED_NONATOMIC":3})
        self.assertTrue(r["preseed_b3_then_b1_without_166a_state_change"])
        self.assertFalse(r["rx_ready_flag_identified"])
        self.assertFalse(r["consumer_dispatcher_or_vitotrol_commit_proven"])
        self.assertEqual(r["controller_writes"],0)

    def test_invalid_source_hash_rejected(self):
        with self.assertRaises(m.EvidenceRejected):
            m.run(b"not an archive",b"also invalid",{
                "v300_initial_preseed":b"{}",
                "v300_earlier_preseed":b"{}"})
        with self.assertRaises(m.EvidenceRejected):
            m.pinned_file(PRE,"00"*32,25_000)

    def test_no_device_io_imports(self):
        import ast
        imports=set()
        for n in ast.walk(ast.parse(SRC.read_text())):
            if isinstance(n,ast.Import):
                imports.update(a.name.split(".")[0] for a in n.names)
            if isinstance(n,ast.ImportFrom) and n.module:
                imports.add(n.module.split(".")[0])
        self.assertFalse(imports & {"subprocess","serial","socket","paho","requests"})


if __name__=="__main__":unittest.main()
