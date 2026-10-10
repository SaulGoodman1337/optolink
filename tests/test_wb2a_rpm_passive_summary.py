"""Synthetic VS1 timeline is never P300 actual RPM."""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

SRC=Path(__file__).resolve().parents[1]/"tools"/"wb2a-rpm-passive-summary.py"
spec=importlib.util.spec_from_file_location("rpm_passive_summary",SRC)
a=importlib.util.module_from_spec(spec)
sys.modules[spec.name]=a
spec.loader.exec_module(a)


class SummaryTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.path=self.root/"vs1-2026-10-10.jsonl"

    def write(self,rows):
        data=[]
        for i,(kind,value,mono) in enumerate(rows):
            data.append({
                "schema":1,"source":a.SOURCE,
                "utc":f"2026-10-10T20:{i:02d}:00+00:00",
                "monotonic_s":mono,"metric":kind,
                "value_display":str(value),"retained":False})
        self.path.write_text("".join(json.dumps(x)+"\n" for x in data))

    def test_stable_nonzero_but_unproven_p300(self):
        self.write([("p06",0,1),("p06",900,7),("p09",30,8),
                    ("p06",1200,13),("p06",1200,19),("p06",0,25)])
        output=a.summarize(self.root)
        self.assertFalse(output["p300_rpm_verified"])
        self.assertEqual(output["p300_samples"],0)
        self.assertEqual(output["positive_p06_episodes"],1)
        self.assertEqual(output["max_positive_p06_published_display"],1200)
        self.assertEqual(output["by_metric"]["p09"],1)
        self.assertEqual(output["longest_positive_episodes"][0]["samples"],3)

    def test_positive_runs_separated_by_long_gap(self):
        self.write([("p06",300,1),("p06",300,7),("p06",900,100)])
        self.assertEqual(a.summarize(self.root)["positive_p06_episodes"],2)

    def test_no_messages_no_fake_positive(self):
        self.assertEqual(a.summarize(self.root)["positive_p06_episodes"],0)
        self.assertEqual(a.summarize(self.root)["records"],0)

    def test_retained_and_wrong_provenance_rejected(self):
        self.write([("p06",900,1)])
        lines=[json.loads(x) for x in self.path.read_text().splitlines()]
        for changed in ({"retained":True},{"source":"P300_RPM"}):
            bad=[dict(lines[0],**changed)]
            self.path.write_text("".join(json.dumps(x)+"\n" for x in bad))
            with self.assertRaises(ValueError):
                a.summarize(self.root)

    def test_out_of_order_monotonic_refused(self):
        self.write([("p06",0,2),("p06",90,1)])
        with self.assertRaisesRegex(ValueError,"nonmonotonic"):
            a.summarize(self.root)


if __name__=="__main__":
    unittest.main()
