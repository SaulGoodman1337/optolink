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
            rc.ADDR_CURRENT_FAULT: 0,
            0x27A0: 0,
            0x27B0: 0,
        }
        self.mem.update(values)
        self.writes = []
        self.fail_write = False
        self.ignore_write = False
        self.unreachable = False

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

    def test_config_validation(self):
        cfg = rc.validate_config({"schwelle_min": 22, "schwelle_max": 21, "max_korrektur": 9,
                                  "aggregation": "foo"})
        self.assertEqual((cfg["schwelle_min"], cfg["schwelle_max"]), (20.5, 21.5))
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
        # 0.6 K below lower threshold -> raw 21.6, within hysteresis of 21 -> stay neutral
        self.assertEqual(rc.next_command(target_c=21, room_c=19.9, current_cmd=0, config=cfg,
                                         now=0, last_step_at=None), 0)
        self.assertEqual(rc.next_command(target_c=21, room_c=19.7, current_cmd=0, config=cfg,
                                         now=0, last_step_at=None), 22)


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
        status = make()[0].tick()
        self.assertEqual(status["state"], "keine_sensoren")
        self.assertEqual(status["effective_target_c"], 21)

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
                     "config": rc.validate_config({"enabled": True, "schwelle_min": 20})}
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
