"""Static checks for the Kamin Home Assistant blueprints and dashboards."""

import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
BP_DIR = ROOT / "config" / "optolink-splitter" / "homeassistant-blueprints"
DASHBOARDS = [
    ROOT / "config" / "optolink-splitter" / "homeassistant-dashboard.yaml",
    ROOT / "config" / "optolink-splitter" / "homeassistant-dashboard-dev.yaml",
]


class _Input(str):
    pass


class _Loader(yaml.SafeLoader):
    pass


_Loader.add_constructor("!input", lambda loader, node: _Input(loader.construct_scalar(node)))


def _walk(node):
    if isinstance(node, dict):
        for value in node.values():
            yield from _walk(value)
    elif isinstance(node, list):
        for value in node:
            yield from _walk(value)
    else:
        yield node


def _load(name):
    with open(BP_DIR / name, encoding="utf-8") as handle:
        return yaml.load(handle, _Loader)


class KaminBlueprintTest(unittest.TestCase):
    def check_blueprint(self, name):
        data = _load(name)
        inputs = data["blueprint"]["input"]
        used = {v for v in _walk({k: v for k, v in data.items() if k != "blueprint"}) if isinstance(v, _Input)}
        self.assertTrue(used, name)
        self.assertEqual(set(), used - set(inputs), f"{name}: undefined !input")
        self.assertEqual(set(), set(inputs) - used, f"{name}: unused input")
        self.assertEqual("automation", data["blueprint"]["domain"])
        self.assertIn("triggers", data)
        self.assertIn("actions", data)
        return data

    def test_erkennung(self):
        data = self.check_blueprint("kamin_erkennung.yaml")
        ids = {t.get("id") for t in data["triggers"]}
        self.assertTrue({"kalt", "lange_an", "sensor_weg", "takt", "start"} <= ids)

    def test_raum_pause_never_turns_thermostats_off(self):
        data = self.check_blueprint("kamin_raum_pause.yaml")
        text = (BP_DIR / "kamin_raum_pause.yaml").read_text(encoding="utf-8")
        self.assertNotIn("set_hvac_mode", text)
        self.assertNotIn("climate.turn_off", text)
        self.assertGreaterEqual(data["blueprint"]["input"]["pause_temperatur"]["selector"]["number"]["min"], 5)

    def test_dashboards_have_kamin_section(self):
        for path in DASHBOARDS:
            with open(path, encoding="utf-8") as handle:
                dash = yaml.safe_load(handle)
            view = next(v for v in dash["views"] if v.get("title") == "Raumregelung")
            headings = [s["cards"][0].get("heading") for s in view["sections"]]
            self.assertIn("Kamin", headings, path.name)
            text = path.read_text(encoding="utf-8")
            for room in ("wohnzimmer", "flur", "gaste_wc", "buro"):
                self.assertIn(f"input_boolean.kamin_pause_{room}", text)

    def test_room_control_package_skips_kamin_sensors(self):
        text = (ROOT / "config" / "optolink-splitter" / "homeassistant-room-control-package.yaml").read_text(encoding="utf-8")
        self.assertIn("kamin_label: optolink_kamin_eg", text)
        self.assertIn("reject('in', ns2.x if kamin_an else [])", text)


if __name__ == "__main__":
    unittest.main()
