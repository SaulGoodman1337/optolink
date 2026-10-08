"""Regression tests for retained MQTT states in the VDensHO1 profile helper."""
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest


PROFILE_HELPER = (
    Path(__file__).resolve().parents[1]
    / "tools"
    / "optolink-apply-vdensho1-ha-profile.sh"
)
PROFILE_SOURCE = PROFILE_HELPER.read_text(encoding="utf-8")
SETTINGS_PATCH = re.search(
    r'if ! python3 - "\$APP_DIR/settings_ini.py" <<\'PY\'\n(.*?)\nPY\nthen',
    PROFILE_SOURCE,
    re.DOTALL,
)

CONFIG = (
    'port_vitoconnect = None\n'
    'vs1protocol = False\n'
    'olbreath = 0.05\n'
    'mqtt_retain = False\n'
    'mqtt_broker = "broker.example:1883"\n'
    'mqtt_user = "example-user"\n'
    'mqtt_topic = "openv"\n'
)


class RetainedMqttSettingsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if SETTINGS_PATCH is None:
            raise AssertionError("Cannot locate guarded settings patch in profile helper")
        cls.patch = SETTINGS_PATCH.group(1)

    def apply_settings(self, config):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "settings_ini.py"
            path.write_text(config, encoding="utf-8")
            proc = subprocess.run(
                [sys.executable, "-c", self.patch, str(path)],
                text=True,
                capture_output=True,
                check=False,
            )
            return proc, path.read_text(encoding="utf-8")

    def test_retain_and_runtime_settings_are_enforced(self):
        proc, updated = self.apply_settings(CONFIG)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("mqtt_retain = True\n", updated)
        self.assertIn("vs1protocol = True\n", updated)
        self.assertIn("olbreath = 0.025\n", updated)
        self.assertIn('mqtt_broker = "broker.example:1883"\n', updated)
        self.assertIn('mqtt_user = "example-user"\n', updated)
        self.assertIn('mqtt_topic = "openv"\n', updated)

    def test_idempotent_when_rerun_by_update(self):
        first, updated = self.apply_settings(CONFIG)
        self.assertEqual(first.returncode, 0, first.stderr)
        second, rerun = self.apply_settings(updated)
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertEqual(updated, rerun)

    def test_missing_setting_fails_without_modifying_config(self):
        missing = CONFIG.replace("mqtt_retain = False\n", "")
        proc, unchanged = self.apply_settings(missing)
        self.assertNotEqual(proc.returncode, 0)
        self.assertEqual(unchanged, missing)

    def test_duplicate_setting_fails_without_modifying_config(self):
        duplicate = CONFIG + "mqtt_retain = False\n"
        proc, unchanged = self.apply_settings(duplicate)
        self.assertNotEqual(proc.returncode, 0)
        self.assertEqual(unchanged, duplicate)

    def test_unsafe_vitoconnect_port_fails_without_modifying_config(self):
        invalid = CONFIG.replace("port_vitoconnect = None", 'port_vitoconnect = "/dev/ttyUSB1"')
        proc, unchanged = self.apply_settings(invalid)
        self.assertNotEqual(proc.returncode, 0)
        self.assertEqual(unchanged, invalid)


if __name__ == "__main__":
    unittest.main()
