"""Deterministic constraints of the four-day MQTT-only observer."""
from __future__ import annotations
import ast
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest

SRC=Path(__file__).resolve().parents[1]/"tools"/"wb2a-rpm-passive-observer.py"
spec=importlib.util.spec_from_file_location("wb2a_rpm_passive",SRC)
observer=importlib.util.module_from_spec(spec)
sys.modules[spec.name]=observer
spec.loader.exec_module(observer)


class PassiveTests(unittest.TestCase):
    def setUp(self):
        self.obs=observer.PassiveRecorder("openv")

    def test_p06_display_only_never_P300(self):
        event=self.obs.record(
            "openv/geblaesedrehzahl_gfa_p06",b"2490",retained=False,
            mono=10.0,utc="2026-10-10T22:00:00+00:00")
        self.assertEqual(event["metric"],"p06")
        self.assertEqual(event["value_display"],"2490")
        self.assertEqual(event["source"],"VS1_MQTT_PUBLISHED_NOT_P300_RPM")
        self.assertEqual(self.obs.max_p06_published,2490.0)
        self.assertEqual(self.obs.p06_positive_samples,1)

    def test_retained_is_not_fresh(self):
        self.assertIsNone(self.obs.record(
            "openv/geblaesedrehzahl_gfa_p06",b"2490",retained=True,
            mono=2,utc="t"))
        self.assertEqual(self.obs.counts,{})

    def test_five_second_metric_sampling(self):
        self.assertIsNotNone(self.obs.record(
            "openv/geblaesedrehzahl_gfa_p06",b"0",retained=False,mono=1,utc="t"))
        self.assertIsNone(self.obs.record(
            "openv/geblaesedrehzahl_gfa_p06",b"123",retained=False,mono=5.9,utc="t"))
        self.assertIsNotNone(self.obs.record(
            "openv/geblaesedrehzahl_gfa_p06",b"100",retained=False,mono=6.0,utc="t"))
        self.assertEqual(self.obs.counts["p06"],2)
        self.assertEqual(self.obs.p06_positive_samples,1)

    def test_modulation_and_flame_are_only_context(self):
        self.assertEqual(self.obs.record(
            "openv/gfa_modulationssollwert_p09",b"37",retained=False,mono=1,utc="t")["metric"],"p09")
        self.assertEqual(self.obs.record(
            "openv/brenner_flamme",b"ON",retained=False,mono=1,utc="t")["metric"],"flame")
        self.assertIsNotNone(self.obs.record(
            "openv/brenner_flamme_gfa",b"0",retained=False,mono=7,utc="t"))
        self.assertEqual(self.obs.p06_positive_samples,0)

    def test_commands_response_and_foreign_topics_rejected(self):
        for topic in ("openv/cmnd","openv/resp","homeassistant/status",
                      "other/geblaesedrehzahl_gfa_p06",
                      "openv/foo/geblaesedrehzahl_gfa_p06","openv/#"):
            with self.subTest(topic=topic):
                self.assertIsNone(self.obs.record(topic,b"1",retained=False,mono=1,utc="t"))

    def test_malicious_payload_or_overlong_rejected(self):
        for raw in (b"1;w;0x4006",b'{"pass":"secret"}',
                    b"x"*40,b"",b"nan",b"\xff",b"1e200","ä".encode()):
            with self.subTest(raw=raw):
                self.assertIsNone(observer.finite_display_value(raw))
        self.assertEqual(self.obs.counts,{})

    def test_config_is_literal_only_without_running_python(self):
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/"settings.py"
            path.write_text("mqtt_broker='127.0.0.1:1883'\n"
                            "mqtt_user='name:private'\n"
                            "mqtt_topic='openv'\n")
            self.assertEqual(observer.read_config(path),
                             ("127.0.0.1",1883,"openv","name:private"))
            path.write_text("mqtt_broker=__import__('os').system('false')\n"
                            "mqtt_topic='openv'\n")
            with self.assertRaises((ValueError,TypeError)):
                observer.read_config(path)

    def test_world_readable_directory_denied(self):
        with tempfile.TemporaryDirectory(dir=Path.home()) as root:
            target=Path(root)/"observer"
            observer.protected_directory(target)
            self.assertEqual(target.stat().st_mode & 0o777,0o700)
            target.chmod(0o755)
            with self.assertRaises(ValueError):
                observer.protected_directory(target)

    def test_symlink_output_denied(self):
        with tempfile.TemporaryDirectory() as root:
            dest=Path(root)/"actual"
            dest.mkdir()
            link=Path(root)/"symlink"
            link.symlink_to(dest)
            with self.assertRaises(ValueError):
                observer.protected_directory(link)

    def test_tmp_is_not_allowed_as_public_output(self):
        with self.assertRaises(ValueError):
            observer.protected_directory(Path("/tmp/untrusted-vs1-data"))

    def test_safe_plan_has_no_live_actions(self):
        tree=ast.parse(SRC.read_text())
        self.assertIn("PLAN ONLY",SRC.read_text())
        imports=set()
        for node in ast.walk(tree):
            if isinstance(node,ast.Import):
                imports.update(item.name.split(".")[0] for item in node.names)
            if isinstance(node,ast.ImportFrom):
                imports.add((node.module or "").split(".")[0])
        self.assertFalse(imports & {"serial","subprocess","requests"})

    def test_metadata_denies_actual_rpm_verification(self):
        self.assertIn("p300_actual_rpm_verified",SRC.read_text())
        self.assertIn("mqtt_publishes_sent",SRC.read_text())
        self.assertIn("controller_writes_sent",SRC.read_text())


if __name__=="__main__":
    unittest.main()
