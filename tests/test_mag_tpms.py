"""Tests for the BLE TPMS expansion-vessel decoder (tools/optolink-mag-tpms.py)."""
import importlib.util
from pathlib import Path
import unittest

SRC = Path(__file__).resolve().parents[1] / "tools" / "optolink-mag-tpms.py"
SPEC = importlib.util.spec_from_file_location("optolink_mag_tpms", SRC)
mt = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mt)

ADDR = "61:41:00:02:FF:B2"
# Live captures 2026-11-26 (Spedal cap on the MAG, boiler manometer ~1.3 bar)
UNPRESSURISED = "9e0055011500ff060ab2ff02004161"
ON_MAG = "a12758051500ff020ab2ff02004161"


class DecodeTest(unittest.TestCase):
    def test_live_capture_on_mag(self):
        v = mt.decode_itpms(bytes.fromhex(ON_MAG), ADDR)
        self.assertEqual(v["druck"], 1.23)
        self.assertEqual(v["druck_roh"], 39)
        self.assertEqual(v["temperatur"], 33)
        self.assertEqual(v["batterie_spannung"], 2.83)
        self.assertEqual(v["status"], 5)

    def test_unpressurised_capture(self):
        v = mt.decode_itpms(bytes.fromhex(UNPRESSURISED), ADDR)
        self.assertEqual(v["druck"], 0.0)
        self.assertEqual(v["temperatur"], 30)

    def test_ff_flag_does_not_switch_to_legacy_formula(self):
        # tpms_ble falls back to (b7-2)/103 when b6 is not 0/1 -> 0 bar
        v = mt.decode_itpms(bytes.fromhex(ON_MAG), ADDR)
        self.assertGreater(v["druck"], 1.0)

    def test_high_flag(self):
        data = bytearray.fromhex(ON_MAG)
        data[6] = 1
        self.assertEqual(mt.decode_itpms(bytes(data), ADDR)["druck_roh"], 256 + 39)

    def test_embedded_mac_must_match(self):
        self.assertIsNone(mt.decode_itpms(bytes.fromhex(ON_MAG), "61:41:00:02:FF:B3"))

    def test_short_payload(self):
        self.assertIsNone(mt.decode_itpms(b"\x01\x02", ADDR))

    def test_battery_percent_clamped(self):
        self.assertEqual(mt.battery_percent(3.3), 100)
        self.assertEqual(mt.battery_percent(2.75), 50)
        self.assertEqual(mt.battery_percent(2.0), 0)


class ExtractTest(unittest.TestCase):
    def adv(self, **kw):
        a = {"address": ADDR.lower(), "rssi": -95, "source": "CC:50:E3:80:B3:92",
             "time": 1795693287.2, "manufacturer_data": {"172": ON_MAG}}
        a.update(kw)
        return a

    def test_configured_cap(self):
        addr, v = mt.extract(self.adv(), {ADDR})
        self.assertEqual(addr, ADDR)
        self.assertEqual(v["rssi"], -95)
        self.assertEqual(v["empfaenger"], "CC:50:E3:80:B3:92")
        self.assertTrue(v["zuletzt"].endswith("+00:00"))

    def test_other_device_ignored(self):
        self.assertIsNone(mt.extract(self.adv(address="11:22:33:44:55:66"), {ADDR}))

    def test_without_payload_ignored(self):
        self.assertIsNone(mt.extract(self.adv(manufacturer_data={"76": "10"}), {ADDR}))

    def test_bad_hex_ignored(self):
        self.assertIsNone(mt.extract(self.adv(manufacturer_data={"172": "zz"}), {ADDR}))


class WindowTest(unittest.TestCase):
    def test_needs_an_hour_of_data(self):
        w = mt.PressureWindow()
        for i in range(30):
            w.add(i * 60.0, 1.2, 30)
        self.assertIsNone(w.summary()["druckhub"])
        self.assertEqual(w.summary()["proben"], 30)

    def test_one_sample_per_minute(self):
        w = mt.PressureWindow()
        self.assertTrue(w.add(0.0, 1.2, 30))
        self.assertFalse(w.add(30.0, 1.3, 31))
        self.assertTrue(w.add(60.0, 1.3, 31))

    def test_cold_warm_swing(self):
        w = mt.PressureWindow()
        # night cold 1.20 bar at 25 degC, day warm 1.60 bar at 55 degC
        for i in range(60):
            w.add(i * 60.0, 1.20, 25)
        for i in range(60, 120):
            w.add(i * 60.0, 1.60, 55)
        sm = w.summary()
        self.assertEqual(sm["druck_kalt"], 1.2)
        self.assertEqual(sm["druck_warm"], 1.6)
        self.assertEqual(sm["druckhub"], 0.4)
        self.assertAlmostEqual(sm["hub_pro_10k"], 0.133, places=3)

    def test_small_temperature_spread_gives_no_rate(self):
        w = mt.PressureWindow()
        for i in range(120):
            w.add(i * 60.0, 1.2 + (i % 2) * 0.03, 30 + (i % 2) * 5)
        self.assertIsNone(w.summary()["hub_pro_10k"])

    def test_window_pruned(self):
        w = mt.PressureWindow()
        w.add(0.0, 1.0, 20)
        w.add(mt.WINDOW_S + 120.0, 1.2, 30)
        self.assertEqual(len(w.samples), 1)

    def test_persistence(self):
        import tempfile, os
        w = mt.PressureWindow()
        w.add(0.0, 1.2, 30)
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "w.json")
            w.save(path)
            w2 = mt.PressureWindow()
            w2.load(path)
            self.assertEqual(w2.samples, [[0.0, 1.2, 30.0]])
            w3 = mt.PressureWindow()
            w3.load(os.path.join(d, "missing.json"))
            self.assertEqual(w3.samples, [])


class DiscoveryTest(unittest.TestCase):
    def test_entities(self):
        msgs = dict(mt.discovery_messages("openv", {"address": ADDR, "id": "mag", "name": "MAG"}))
        druck = msgs["homeassistant/sensor/optolink_tpms_61410002ffb2/druck/config"]
        self.assertEqual(druck["unit_of_measurement"], "bar")
        self.assertEqual(druck["default_entity_id"], "sensor.mag_druck")
        self.assertEqual(druck["availability_topic"], "openv/tpms/mag/availability")
        self.assertEqual(len(msgs), len(mt.ENTITIES) + len(mt.EVAL_ENTITIES))
        hub = msgs["homeassistant/sensor/optolink_tpms_61410002ffb2/druckhub/config"]
        self.assertEqual(hub["state_topic"], "openv/tpms/mag/auswertung")
        ids = {m["unique_id"] for m in msgs.values()}
        self.assertEqual(len(ids), len(msgs))

    def test_self_test(self):
        self.assertEqual(mt.self_test(), 0)


if __name__ == "__main__":
    unittest.main()
