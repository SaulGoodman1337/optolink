"""Tests for the room-temperature feedback service (tools/optolink-room-control.py)."""
import importlib.util
from pathlib import Path
import unittest

SRC = Path(__file__).resolve().parents[1] / "tools" / "optolink-room-control.py"
SPEC = importlib.util.spec_from_file_location("optolink_room_control", SRC)
rc = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(rc)


class FakeIO:
    def __init__(self, **values):
        self.mem = {
            rc.ADDR_EXTERNAL_SETPOINT: 0,
            rc.ADDR_NORMAL_SETPOINT: 21,
            rc.ADDR_REDUCED_SETPOINT: 18,
            rc.ADDR_NATIVE_PARTY: 0,
            rc.ADDR_CURRENT_FAULT: 0,
            0x27A0: 0,
            0x27B0: 0,
        }
        self.mem.update(values)
        self.writes = []
        self.fail_write = False
        self.ignore_write = False
        self.unreachable = False
        self.phase = 2  # normal (schedule day window)

    def read_bytes(self, addr, length):
        assert addr == rc.ADDR_OPERATING_STATE and length == rc.OPERATING_STATE_LEN
        if self.unreachable:
            raise TimeoutError("boiler unreachable")
        data = bytearray(length)
        data[1] = self.phase
        target = self.mem[rc.ADDR_REDUCED_SETPOINT] if self.phase == 1 else (
            self.mem[rc.ADDR_EXTERNAL_SETPOINT] or self.mem[rc.ADDR_NORMAL_SETPOINT])
        data[12:14] = int(target * 10).to_bytes(2, "little")
        return data.hex()

    def sleep(self, _seconds):
        pass

    def read_int(self, addr, _length):
        if self.unreachable:
            raise TimeoutError("boiler unreachable")
        return self.mem[addr]

    def write_int(self, addr, _length, value):
        assert addr == rc.ADDR_EXTERNAL_SETPOINT
        if self.fail_write:
            raise TimeoutError("no response")
        self.writes.append(value)
        if not self.ignore_write:
            self.mem[addr] = value


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


def make(enabled=True, **cfg):
    io = FakeIO()
    clock = Clock()
    state = {"version": 1, "owned_command": 0,
             "config": rc.validate_config({"enabled": enabled, **cfg})}
    saved = []
    ctl = rc.RoomController(io, state, save=lambda s: saved.append(dict(s)), clock=clock)
    return ctl, io, clock


def feed(ctl, clock, **sensors):
    ctl.update_samples({k: (v, clock.t) for k, v in sensors.items()})


class PureLogicTests(unittest.TestCase):
    def test_sensor_payload_variants(self):
        parsed = rc.parse_sensor_payload(
            b'{"sensors": {"sensor.a": "21.4", "sensor.b": 19, "sensor.c": "unavailable",'
            b' "sensor.d": 80, "sensor.e": true}}', 5.0)
        self.assertEqual(parsed, {"sensor.a": (21.4, 5.0), "sensor.b": (19.0, 5.0)})
        self.assertEqual(rc.parse_sensor_payload('{"x": 20.0}', 1.0), {"x": (20.0, 1.0)})
        self.assertEqual(rc.parse_sensor_payload("{'sensors': {'x': 20.5}}", 1.0), {"x": (20.5, 1.0)})
        with self.assertRaises(rc.RoomControlError):
            rc.parse_sensor_payload(b"21.0x", 0)

    def test_aggregation(self):
        self.assertEqual(rc.aggregate([20, 21, 22], "Mittelwert"), 21)
        self.assertEqual(rc.aggregate([20, 21, 22], "Minimum"), 20)
        self.assertEqual(rc.aggregate([20, 21, 22], "Maximum"), 22)
        self.assertIsNone(rc.aggregate([], "Mittelwert"))

    def test_operating_state_decoding(self):
        # live frame 2026-11-24 22:00 (night setback, reduced target 18.0 C)
        self.assertEqual(rc.parse_operating_state("0201000000006d0101000001b4000000006d0100b400"),
                         ("reduziert", 18.0))
        frame = bytearray(22)
        frame[1] = 2
        frame[12:14] = (215).to_bytes(2, "little")
        self.assertEqual(rc.parse_operating_state(frame.hex()), ("normal", 21.5))
        with self.assertRaises(rc.RoomControlError):
            rc.parse_operating_state("0201")

    def test_comfort_band_follows_base_target(self):
        cfg = rc.validate_config({"toleranz_unten": 0.5, "toleranz_oben": 1.0})
        self.assertEqual(rc.comfort_band(21, cfg), (20.5, 22.0))
        self.assertEqual(rc.comfort_band(18, cfg), (17.5, 19.0))

    def test_config_validation(self):
        cfg = rc.validate_config({"toleranz_unten": 9, "toleranz_oben": 0.1, "max_korrektur": 9,
                                  "aggregation": "foo", "schwelle_min": 20})
        self.assertEqual((cfg["toleranz_unten"], cfg["toleranz_oben"]), (0.5, 0.5))
        self.assertNotIn("schwelle_min", cfg)
        self.assertEqual(cfg["max_korrektur"], 2)
        self.assertEqual(cfg["aggregation"], "Mittelwert")
        self.assertFalse(cfg["enabled"])

    def test_band_correction(self):
        self.assertEqual(rc.band_correction(21.0, 20.5, 21.5, 1, 2), 0.0)
        self.assertEqual(rc.band_correction(20.0, 20.5, 21.5, 2, 3), 1.0)
        self.assertEqual(rc.band_correction(25.0, 20.5, 21.5, 1, 2), -2.0)
        self.assertEqual(rc.band_correction(10.0, 20.5, 21.5, 1, 3), 3.0)

    def test_next_command_steps_and_rate_limit(self):
        cfg = rc.validate_config({"enabled": True, "max_korrektur": 3})
        kw = dict(target_c=21, config=cfg)
        # far too cold: wants 24, but goes up 1 K per step
        self.assertEqual(rc.next_command(room_c=17, current_cmd=0, now=0, last_step_at=None, **kw), 22)
        self.assertEqual(rc.next_command(room_c=17, current_cmd=22, now=100, last_step_at=0, **kw), 22)
        self.assertEqual(rc.next_command(room_c=17, current_cmd=22, now=400, last_step_at=0, **kw), 23)
        # inside band: step back down, reaching the target means release (0)
        self.assertEqual(rc.next_command(room_c=21, current_cmd=22, now=400, last_step_at=0, **kw), 0)
        # too warm: lower
        self.assertEqual(rc.next_command(room_c=23, current_cmd=0, now=0, last_step_at=None, **kw), 20)

    def test_hysteresis(self):
        cfg = rc.validate_config({"enabled": True})
        kw = dict(target_c=21, config=cfg, now=0, last_step_at=None)
        # any deviation outside the band acts with at least 1 K (live case 19.8 C)
        self.assertEqual(rc.next_command(room_c=20.4, current_cmd=0, **kw), 22)
        self.assertEqual(rc.next_command(room_c=19.8, current_cmd=0, **kw), 22)
        self.assertEqual(rc.next_command(room_c=21.6, current_cmd=0, **kw), 20)
        # between levels: 1.6 K deviation stays at +1 while owning 22
        self.assertEqual(rc.next_command(room_c=18.9, current_cmd=22, **kw), 22)
        # exit margin: just back inside the band keeps the correction
        self.assertEqual(rc.next_command(room_c=20.6, current_cmd=22, **kw), 22)
        self.assertEqual(rc.next_command(room_c=20.8, current_cmd=22, **kw), 0)
        self.assertEqual(rc.next_command(room_c=21.4, current_cmd=20, **kw), 20)
        self.assertEqual(rc.next_command(room_c=21.2, current_cmd=20, **kw), 0)


class ControllerTests(unittest.TestCase):
    def test_cold_room_raises_and_band_releases(self):
        ctl, io, clock = make()
        feed(ctl, clock, a=19.0, b=19.4)
        status = ctl.tick()
        self.assertEqual(status["state"], "aktiv")
        self.assertEqual(io.mem[rc.ADDR_EXTERNAL_SETPOINT], 22)
        self.assertEqual(ctl.owned, 22)
        clock.t += 400
        feed(ctl, clock, a=21.0, b=21.0)
        self.assertEqual(ctl.tick()["state"], "neutral")
        self.assertEqual(io.mem[rc.ADDR_EXTERNAL_SETPOINT], 0)
        self.assertEqual(ctl.owned, 0)

    def test_status_shows_regular_target_when_idle(self):
        ctl, io, clock = make(enabled=False)
        status = ctl.tick()
        self.assertEqual(status["state"], "aus")
        self.assertEqual(status["effective_target_c"], 21)
        self.assertEqual(status["phase"], "normal")
        self.assertEqual((status["schwelle_unten_c"], status["schwelle_oben_c"]), (20.5, 21.5))
        status = make()[0].tick()
        self.assertEqual(status["state"], "keine_sensoren")
        self.assertEqual(status["effective_target_c"], 21)

    def test_day_target_change_moves_band(self):
        ctl, io, clock = make()
        io.mem[rc.ADDR_NORMAL_SETPOINT] = 23  # e.g. changed at the panel
        feed(ctl, clock, a=21.4)  # fine for 21, too cold for 23
        status = ctl.tick()
        self.assertEqual(status["state"], "aktiv")
        self.assertEqual(status["base_target_c"], 23)
        self.assertEqual(io.mem[rc.ADDR_EXTERNAL_SETPOINT], 24)

    def test_night_setback_releases_and_monitors(self):
        ctl, io, clock = make()
        feed(ctl, clock, a=19.0)
        ctl.tick()
        self.assertEqual(io.mem[rc.ADDR_EXTERNAL_SETPOINT], 22)
        io.phase = 1  # schedule switches to reduced
        clock.t += 60
        feed(ctl, clock, a=19.0)
        status = ctl.tick()
        self.assertEqual(status["state"], "nachtabsenkung")
        self.assertEqual(io.mem[rc.ADDR_EXTERNAL_SETPOINT], 0)
        self.assertEqual(status["base_target_c"], 18)
        self.assertEqual(status["effective_target_c"], 18)
        self.assertEqual((status["schwelle_unten_c"], status["schwelle_oben_c"]), (17.5, 18.5))
        # morning: normal phase again, control resumes from the day target
        io.phase = 2
        clock.t += 400
        feed(ctl, clock, a=19.0)
        self.assertEqual(ctl.tick()["state"], "aktiv")
        self.assertEqual(io.mem[rc.ADDR_EXTERNAL_SETPOINT], 22)

    def test_off_mode_and_native_party_release(self):
        ctl, io, clock = make()
        feed(ctl, clock, a=19.0)
        ctl.tick()
        io.phase = 0
        self.assertEqual(ctl.tick()["state"], "abschaltbetrieb")
        self.assertEqual(io.mem[rc.ADDR_EXTERNAL_SETPOINT], 0)
        io.phase = 2
        io.mem[rc.ADDR_NATIVE_PARTY] = 1
        self.assertEqual(ctl.tick()["state"], "party")

    def test_disabled_releases(self):
        ctl, io, clock = make()
        feed(ctl, clock, a=18.0)
        ctl.tick()
        ctl.state["config"]["enabled"] = False
        self.assertEqual(ctl.tick()["state"], "aus")
        self.assertEqual(io.mem[rc.ADDR_EXTERNAL_SETPOINT], 0)

    def test_stale_sensors_release(self):
        ctl, io, clock = make()
        feed(ctl, clock, a=18.0)
        ctl.tick()
        clock.t += rc.SENSOR_MAX_AGE_S + 1
        self.assertEqual(ctl.tick()["state"], "keine_sensoren")
        self.assertEqual(io.mem[rc.ADDR_EXTERNAL_SETPOINT], 0)

    def test_foreign_value_is_never_touched(self):
        ctl, io, clock = make()
        io.mem[rc.ADDR_EXTERNAL_SETPOINT] = 23
        feed(ctl, clock, a=18.0)
        self.assertEqual(ctl.tick()["state"], "fremdbelegt")
        self.assertEqual(io.writes, [])

    def test_fault_and_room_influence_release(self):
        ctl, io, clock = make()
        feed(ctl, clock, a=18.0)
        ctl.tick()
        io.mem[rc.ADDR_CURRENT_FAULT] = 0xB1
        self.assertEqual(ctl.tick()["state"], "stoerung")
        self.assertEqual(io.mem[rc.ADDR_EXTERNAL_SETPOINT], 0)
        io.mem[rc.ADDR_CURRENT_FAULT] = 0
        io.mem[0x27A0] = 1
        ctl.next_influence_check = 0
        self.assertEqual(ctl.tick()["state"], "raumeinfluss_codiert")

    def test_unreachable_boiler_raises_but_keeps_ownership(self):
        ctl, io, clock = make()
        feed(ctl, clock, a=18.0)
        ctl.tick()
        io.unreachable = True
        with self.assertRaises(TimeoutError):
            ctl.tick()
        self.assertEqual(ctl.owned, 22)  # still known, released once reachable
        io.unreachable = False
        ctl.state["config"]["enabled"] = False
        ctl.tick()
        self.assertEqual(io.mem[rc.ADDR_EXTERNAL_SETPOINT], 0)

    def test_failed_readback_releases(self):
        ctl, io, clock = make()
        io.ignore_write = True
        feed(ctl, clock, a=18.0)
        with self.assertRaises(rc.RoomControlError):
            ctl.tick()
        self.assertEqual(ctl.owned, 0)

    def test_stale_ownership_dropped_on_start(self):
        ctl, io, clock = make()
        ctl.state["owned_command"] = 22  # state file says 22, controller shows 0
        feed(ctl, clock, a=21.0)
        ctl.tick()
        self.assertEqual(ctl.owned, 0)
        self.assertEqual(io.writes, [])

    def test_resume_owned_value_after_restart(self):
        ctl, io, clock = make()
        ctl.state["owned_command"] = 22
        io.mem[rc.ADDR_EXTERNAL_SETPOINT] = 22
        feed(ctl, clock, a=19.0)
        self.assertEqual(ctl.tick()["state"], "aktiv")
        self.assertEqual(io.writes, [])

    def test_state_roundtrip(self):
        import tempfile, os
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "state.json")
            state = {"version": 1, "owned_command": 22,
                     "config": rc.validate_config({"enabled": True, "toleranz_unten": 0.8})}
            rc.save_state(state, path)
            self.assertEqual(rc.load_state(path), state)


class HomeAssistantPackageTests(unittest.TestCase):
    """Guard the HA package structure (a broken edit once dropped the actions)."""

    def test_package_publishes_sensors(self):
        try:
            import yaml
        except ImportError:
            self.skipTest("pyyaml not installed")
        path = SRC.parents[1] / "config" / "optolink-splitter" / "homeassistant-room-control-package.yaml"
        pkg = yaml.safe_load(path.read_text(encoding="utf-8"))
        auto = pkg["automation"][0]
        self.assertEqual(auto["conditions"][0]["value_template"], "{{ kandidaten | count > 0 }}")
        action = auto["actions"][0]
        self.assertEqual(action["action"], "mqtt.publish")
        self.assertEqual(action["data"]["topic"], "openv/room_control/sensors")
        self.assertFalse(action["data"]["retain"])
        self.assertIn("label_devices(label_id)", auto["variables"]["kandidaten"])
        self.assertEqual(pkg["template"][0]["sensor"][0]["unique_id"], "optolink_raumregelung_sensoren")


if __name__ == "__main__":
    unittest.main()
