"""Tests for the room-temperature feedback service (tools/optolink-room-control.py)."""
import datetime
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
            rc.ADDR_OPERATING_MODE: 2,
        }
        self.outside = 2.0
        # M1 time program: every day 05:20-22:00 (0x2A / 0xB0)
        self.schedule = {wd: "2ab0ffffffffffff" for wd in range(7)}
        self.mode_writes = []
        self.dhw_only_phase = 0  # 0x2500 phase reported while 0x2323 = 1
        self.mem.update(values)
        self.writes = []
        self.fail_write = False
        self.ignore_write = False
        self.unreachable = False
        self.phase = 2  # normal (schedule day window)
        # burner / pump state for the run-on before the night shutdown
        self.flame = False
        self.mem[rc.ADDR_DHW_CHARGING] = 0
        self.mem[rc.ADDR_PUMP_M1_OUTPUT] = 1
        self.kessel = 45.0
        self.soll = 40.0

    def read_bytes(self, addr, length):
        if self.unreachable:
            raise TimeoutError("boiler unreachable")
        if rc.ADDR_SCHEDULE_M1 <= addr < rc.ADDR_SCHEDULE_M1 + 56:
            assert length == 8 and (addr - rc.ADDR_SCHEDULE_M1) % 8 == 0
            return self.schedule[(addr - rc.ADDR_SCHEDULE_M1) // 8]
        if addr == rc.ADDR_BURNER_STATE:
            assert length == 9
            return bytes([0, 0, 0, 0, 0, 0x20 if self.flame else 0, 0, 0, 0]).hex()
        assert addr == rc.ADDR_OPERATING_STATE and length == rc.OPERATING_STATE_LEN
        data = bytearray(length)
        data[1] = self.dhw_only_phase if self.mem[rc.ADDR_OPERATING_MODE] == 1 else self.phase
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

    def read_scaled(self, addr, _length, _scale, _signed):
        if self.unreachable:
            raise TimeoutError("boiler unreachable")
        if addr == rc.ADDR_BOILER_TEMP:
            return self.kessel
        if addr == rc.ADDR_BOILER_SETPOINT:
            return self.soll
        assert addr == rc.ADDR_OUTSIDE_TEMP
        return self.outside

    def write_int(self, addr, _length, value):
        assert addr in (rc.ADDR_EXTERNAL_SETPOINT, rc.ADDR_OPERATING_MODE)
        if self.fail_write:
            raise TimeoutError("no response")
        if addr == rc.ADDR_OPERATING_MODE:
            assert value in (1, 2)
            self.mode_writes.append(value)
            self.mem[addr] = value
            return
        self.writes.append(value)
        if not self.ignore_write:
            self.mem[addr] = value


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


class Wall:
    """Local wall clock: Tuesday 2026-11-24 23:00 by default."""

    def __init__(self):
        self.dt = datetime.datetime(2026, 11, 24, 23, 0)

    def __call__(self):
        return self.dt.weekday(), self.dt.hour * 60 + self.dt.minute, self.dt.date()


def make(enabled=True, **cfg):
    io = FakeIO()
    clock = Clock()
    state = {"version": 1, "owned_command": 0,
             "config": rc.validate_config({"enabled": enabled, **cfg})}
    saved = []
    io.boosts = []
    ctl = rc.RoomController(io, state, save=lambda s: saved.append(dict(s)), clock=clock,
                            wallclock=Wall(), boost=lambda sec, why: io.boosts.append(sec))
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
        cfg = rc.validate_config({"toleranz_unten": 9, "toleranz_oben": 0.1, "max_korrektur": 99,
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

    def test_morning_boost_after_cold_night(self):
        ctl, io, clock = make(morgenboost=2, morgenboost_ausloesung=1.0, morgenboost_dauer=60)
        io.phase = 1
        feed(ctl, clock, a=18.5)
        self.assertEqual(ctl.tick()["state"], "nachtabsenkung")
        io.phase = 2  # schedule switches to day, room far below 20.5 - 1.0
        clock.t += 60
        feed(ctl, clock, a=18.5)
        status = ctl.tick()
        self.assertEqual(status["state"], "morgenboost")
        # regular +2 (gain 1 x 2 K, max 2) plus boost 2, written at once
        self.assertEqual(io.mem[rc.ADDR_EXTERNAL_SETPOINT], 25)
        # room reaches the band: boost ends, regular control steps down 1 K
        clock.t += 1200
        feed(ctl, clock, a=20.6)
        status = ctl.tick()
        self.assertEqual(status["state"], "aktiv")
        self.assertEqual(io.mem[rc.ADDR_EXTERNAL_SETPOINT], 25)  # rate limit right after boost
        clock.t += 400
        feed(ctl, clock, a=20.8)
        ctl.tick()
        self.assertEqual(io.mem[rc.ADDR_EXTERNAL_SETPOINT], 24)

    def test_morning_boost_time_limit_and_once(self):
        ctl, io, clock = make(morgenboost=1, morgenboost_dauer=10)
        io.phase = 1
        ctl.tick()
        io.phase = 2
        clock.t += 60
        feed(ctl, clock, a=18.0)
        self.assertEqual(ctl.tick()["state"], "morgenboost")
        clock.t += 11 * 60
        feed(ctl, clock, a=18.0)
        self.assertNotEqual(ctl.tick()["state"], "morgenboost")
        clock.t += 60
        feed(ctl, clock, a=18.0)
        self.assertNotEqual(ctl.tick()["state"], "morgenboost")

    def test_no_morning_boost_when_off_or_mild_night(self):
        for cfg, room in (({"morgenboost": 0}, 18.0), ({"morgenboost": 2}, 19.8)):
            ctl, io, clock = make(**cfg)
            io.phase = 1
            ctl.tick()
            io.phase = 2
            clock.t += 60
            feed(ctl, clock, a=room)
            self.assertNotEqual(ctl.tick()["state"], "morgenboost")
        # no boost without an observed night -> day transition (service restart)
        ctl, io, clock = make(morgenboost=2)
        feed(ctl, clock, a=18.0)
        self.assertNotEqual(ctl.tick()["state"], "morgenboost")

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
            state = {"version": 1, "owned_command": 22, "owned_mode": True,
                     "night": {"id": "2026-11-25", "switches": 2},
                     "config": rc.validate_config({"enabled": True, "toleranz_unten": 0.8})}
            rc.save_state(state, path)
            self.assertEqual(rc.load_state(path), state)


class NightShutdownLogicTests(unittest.TestCase):
    def setUp(self):
        self.cfg = rc.validate_config({"enabled": True, "nachtabschaltung": True})

    def decide(self, **kw):
        args = dict(active=False, room_c=20.0, reduced_c=18, outside_c=2.0, in_day=False,
                    minutes_to_day=300, config=self.cfg, switches_used=0)
        args.update(kw)
        return rc.night_decision(**args)[0]

    def test_decode_schedule_block(self):
        self.assertEqual(rc.decode_schedule_block("2ab0ffffffffffff"), [(320, 1320)])
        self.assertEqual(rc.decode_schedule_block("ffffffffffffffff"), [])
        self.assertEqual(rc.decode_schedule_block("90a02838ffffffff"),
                         [(300, 420), (1080, 1200)])
        with self.assertRaises(rc.RoomControlError):
            rc.decode_schedule_block("2a2affffffffffff")  # start == end
        with self.assertRaises(rc.RoomControlError):
            rc.decode_schedule_block("2ab0")

    def test_schedule_position(self):
        days = {wd: [(320, 1320)] for wd in range(7)}
        self.assertEqual(rc.schedule_position(days, 1, 23 * 60), (False, 380, 1))
        self.assertEqual(rc.schedule_position(days, 2, 60), (False, 260, 0))
        self.assertEqual(rc.schedule_position(days, 2, 600), (True, 0, 0))
        days[2] = []  # whole Wednesday reduced
        self.assertEqual(rc.schedule_position(days, 1, 23 * 60), (False, 380 + 1440, 2))
        self.assertEqual(rc.schedule_position({}, 1, 0), (False, None, None))

    def test_engage_thresholds(self):
        self.assertTrue(self.decide(room_c=19.5))
        self.assertFalse(self.decide(room_c=19.4))
        self.assertFalse(self.decide(outside_c=-5.1))
        self.assertTrue(self.decide(outside_c=-5.0))
        self.assertFalse(self.decide(minutes_to_day=60))   # vorlauf 30 + 30 min window
        self.assertFalse(self.decide(switches_used=3))
        self.assertFalse(self.decide(in_day=True))
        self.assertFalse(self.decide(minutes_to_day=None))
        self.assertFalse(self.decide(outside_c=None))

    def test_release_thresholds(self):
        self.assertTrue(self.decide(active=True, room_c=18.6))
        self.assertFalse(self.decide(active=True, room_c=18.5))
        self.assertTrue(self.decide(active=True, outside_c=-6.0))
        self.assertFalse(self.decide(active=True, outside_c=-6.1))
        self.assertFalse(self.decide(active=True, minutes_to_day=30))
        self.assertTrue(self.decide(active=True, minutes_to_day=31, switches_used=9))

    def test_config_keeps_gap(self):
        cfg = rc.validate_config({"nacht_ein": 1.0, "nacht_aus": 1.0})
        self.assertEqual(cfg["nacht_aus"], 0.5)
        self.assertFalse(rc.validate_config({})["nachtabschaltung"])


class NightShutdownControllerTests(unittest.TestCase):
    def night(self, room=20.0, **cfg):
        cfg.setdefault("nacht_nachlauf", 0)   # run-on has its own tests below
        ctl, io, clock = make(nachtabschaltung=True, **cfg)
        io.phase = 1
        feed(ctl, clock, a=room)
        return ctl, io, clock

    def step(self, ctl, clock, room, minutes=1):
        clock.t += 60 * minutes
        ctl.wallclock.dt += datetime.timedelta(minutes=minutes)
        feed(ctl, clock, a=room)
        return ctl.tick()

    def test_disabled_by_default(self):
        ctl, io, clock = make()
        io.phase = 1
        feed(ctl, clock, a=21.0)
        status = ctl.tick()
        self.assertEqual(status["state"], "nachtabsenkung")
        self.assertEqual(io.mode_writes, [])

    def test_shutdown_and_release_when_room_cools(self):
        ctl, io, clock = self.night(room=20.0)
        status = ctl.tick()
        self.assertEqual(io.mode_writes, [1])
        self.assertEqual(status["state"], "nachtabschaltung")
        self.assertTrue(status["nachtabschaltung_aktiv"])
        self.assertEqual(status["nacht_aus_c"], 18.5)
        self.assertEqual(status["minuten_bis_tag"], 380)
        self.assertTrue(ctl.state["owned_mode"])
        # boiler reports phase 0 while in "Nur WW": logic keeps running
        status = self.step(ctl, clock, 19.0)
        self.assertEqual(status["state"], "nachtabschaltung")
        self.assertEqual(io.mode_writes, [1])
        status = self.step(ctl, clock, 18.5)
        self.assertEqual(io.mode_writes, [1, 2])
        self.assertEqual(status["state"], "nachtabsenkung")
        self.assertFalse(ctl.state["owned_mode"])
        # hysteresis: not again at 19.0
        self.step(ctl, clock, 19.0)
        self.assertEqual(io.mode_writes, [1, 2])

    def test_vorlauf_before_day_and_morning_boost(self):
        ctl, io, clock = self.night(room=20.0, morgenboost=2, morgenboost_ausloesung=0.2)
        ctl.tick()
        self.assertEqual(io.mode_writes, [1])
        self.step(ctl, clock, 19.5, minutes=5 * 60 + 49)   # 04:49
        self.assertEqual(io.mode_writes, [1])
        status = self.step(ctl, clock, 19.5)                # 04:50 = 30 min before 05:20
        self.assertEqual(io.mode_writes, [1, 2])
        self.assertEqual(status["nacht_grund"], "Vorlauf vor Tagbeginn")
        io.phase = 2
        status = self.step(ctl, clock, 19.5, minutes=30)
        self.assertEqual(status["state"], "morgenboost")

    def test_no_shutdown_close_to_day(self):
        ctl, io, clock = self.night(room=21.0)
        ctl.wallclock.dt = datetime.datetime(2026, 11, 25, 4, 30)
        status = ctl.tick()
        self.assertEqual(io.mode_writes, [])
        self.assertEqual(status["nacht_grund"], "zu kurz bis Tagbeginn")

    def test_cold_outside(self):
        ctl, io, clock = self.night(room=21.0)
        io.outside = -8.0
        self.assertEqual(ctl.tick()["nacht_grund"], "zu kalt draußen")
        self.assertEqual(io.mode_writes, [])
        io.outside = -4.5
        self.step(ctl, clock, 21.0)
        io.outside = -5.5   # inside hysteresis
        self.step(ctl, clock, 21.0)
        self.assertEqual(io.mode_writes, [1])
        io.outside = -6.5
        self.step(ctl, clock, 21.0)
        self.assertEqual(io.mode_writes, [1, 2])

    def test_switch_budget_survives_midnight(self):
        ctl, io, clock = self.night(room=20.0, nacht_max_schaltungen=1)
        ctl.tick()
        self.step(ctl, clock, 18.4)
        self.assertEqual(io.mode_writes, [1, 2])
        status = self.step(ctl, clock, 21.0, minutes=120)   # 01:02 next date, same night
        self.assertEqual(io.mode_writes, [1, 2])
        self.assertEqual(status["nacht_grund"], "Schaltlimit dieser Nacht erreicht")
        self.assertEqual(ctl.state["night"], {"id": "2026-11-25", "switches": 1})

    def test_foreign_mode_change_is_respected(self):
        ctl, io, clock = self.night(room=20.0)
        ctl.tick()
        io.mem[rc.ADDR_OPERATING_MODE] = 4   # e.g. party emulator / user
        io.phase = 3
        self.step(ctl, clock, 20.0)
        self.assertEqual(io.mode_writes, [1])
        self.assertFalse(ctl.state["owned_mode"])
        self.assertEqual(io.mem[rc.ADDR_OPERATING_MODE], 4)

    def test_only_from_heating_dhw(self):
        ctl, io, clock = self.night(room=21.0)
        io.mem[rc.ADDR_OPERATING_MODE] = 3
        status = ctl.tick()
        self.assertEqual(io.mode_writes, [])
        self.assertIn("Betriebsart 3", status["nacht_grund"])

    def test_release_on_lost_sensors_disable_fault_and_switch_off(self):
        for case in ("sensors", "disabled", "fault", "night_off", "day"):
            ctl, io, clock = self.night(room=20.0)
            ctl.tick()
            self.assertEqual(io.mode_writes, [1], case)
            clock.t += 60
            if case == "sensors":
                clock.t += rc.SENSOR_MAX_AGE_S + 1
            else:
                feed(ctl, clock, a=20.0)
            if case == "disabled":
                ctl.state["config"]["enabled"] = False
            if case == "fault":
                io.mem[rc.ADDR_CURRENT_FAULT] = 0xB7
            if case == "night_off":
                ctl.state["config"]["nachtabschaltung"] = False
            if case == "day":
                io.dhw_only_phase = 2
            status = ctl.tick()
            self.assertEqual(io.mode_writes, [1, 2], case)
            self.assertFalse(status["nachtabschaltung_aktiv"], case)

    def test_resume_after_restart_keeps_ownership(self):
        ctl, io, clock = self.night(room=20.0)
        ctl.tick()
        ctl2 = rc.RoomController(io, ctl.state, save=lambda s: None, clock=clock,
                                 wallclock=ctl.wallclock)
        feed(ctl2, clock, a=18.0)
        ctl2.tick()
        self.assertEqual(io.mode_writes, [1, 2])

    def test_splitter_io_write_guard(self):
        sio = rc.SplitterIO.__new__(rc.SplitterIO)
        sio.request = lambda cmd, addr: "1"
        sio.write_int(rc.ADDR_OPERATING_MODE, 1, 1)
        sio.write_int(rc.ADDR_OPERATING_MODE, 1, 2)
        for value in (0, 3, 4):
            with self.assertRaises(rc.RoomControlError):
                sio.write_int(rc.ADDR_OPERATING_MODE, 1, value)
        with self.assertRaises(rc.RoomControlError):
            sio.write_int(rc.ADDR_REDUCED_SETPOINT, 1, 16)


class NightRunOnTests(unittest.TestCase):
    def night(self, room=20.0, **cfg):
        ctl, io, clock = make(nachtabschaltung=True, **cfg)
        io.phase = 1
        feed(ctl, clock, a=room)
        return ctl, io, clock

    def step(self, ctl, clock, room=20.0, seconds=10):
        clock.t += seconds
        ctl.wallclock.dt += datetime.timedelta(seconds=seconds)
        feed(ctl, clock, a=room)
        return ctl.tick()

    def test_default_ten_minutes(self):
        self.assertEqual(rc.validate_config({})["nacht_nachlauf"], 10)

    def test_waits_for_flame_then_runs_on_then_switches(self):
        ctl, io, clock = self.night()
        io.flame = True
        status = ctl.tick()
        self.assertEqual(io.mode_writes, [])
        self.assertEqual(status["state"], "nachlauf")
        self.assertEqual(status["nacht_grund"], "Nachlauf: warte auf Brenner aus")
        self.assertEqual(io.boosts, [])           # firing: pump guard decides itself
        io.flame = False
        status = self.step(ctl, clock, seconds=120)
        self.assertEqual(status["state"], "nachlauf")
        self.assertEqual(status["nachlauf_phase"], "laeuft")
        self.assertEqual(io.boosts, [rc.NACHLAUF_BOOST_TTL_S])
        self.assertEqual(status["nachlauf_rest_min"], 10)
        for _ in range(59):
            self.step(ctl, clock)
        self.assertEqual(io.mode_writes, [])
        status = self.step(ctl, clock)            # 600 s after the flame went off
        self.assertEqual(io.mode_writes, [1])
        self.assertEqual(status["state"], "nachtabschaltung")
        self.assertEqual(io.boosts[-1], 0)
        self.assertIsNone(ctl.nachlauf)
        self.assertEqual(ctl.state["night"]["switches"], 1)

    def test_ends_early_before_burner_restart(self):
        ctl, io, clock = self.night()
        ctl.tick()
        self.assertEqual(io.mode_writes, [])
        io.kessel = 37.6                          # soll 40 - 2.5 = 37.5
        self.step(ctl, clock)
        self.assertEqual(io.mode_writes, [])
        io.kessel = 37.5
        self.step(ctl, clock)
        self.assertEqual(io.mode_writes, [1])

    def test_pump_stopped_by_firmware_switches_at_once(self):
        ctl, io, clock = self.night()
        io.mem[rc.ADDR_PUMP_M1_OUTPUT] = 0         # e.g. A9 pump idle time
        ctl.tick()
        self.assertEqual(io.mode_writes, [1])
        self.assertEqual(io.boosts, [])

    def test_dhw_charge_waits(self):
        ctl, io, clock = self.night()
        io.mem[rc.ADDR_DHW_CHARGING] = 1
        ctl.tick()
        self.assertEqual(io.mode_writes, [])
        self.assertEqual(ctl.nachlauf["phase"], "warten")

    def test_burner_restart_restarts_run_on_and_total_limit(self):
        ctl, io, clock = self.night(nacht_nachlauf=5)
        ctl.tick()
        self.step(ctl, clock, seconds=200)
        io.flame = True
        self.step(ctl, clock)
        self.assertIsNone(ctl.nachlauf["run_since"])
        io.flame = False
        self.step(ctl, clock, seconds=200)
        self.assertEqual(io.mode_writes, [])       # new run-on, 5 min from now
        io.flame = True                            # burner never stops
        self.step(ctl, clock, seconds=int(rc.NACHLAUF_FLAME_WAIT_S))
        self.assertEqual(io.mode_writes, [1])

    def test_cancel_when_room_cools_or_day(self):
        ctl, io, clock = self.night()
        ctl.tick()
        self.assertIsNotNone(ctl.nachlauf)
        self.step(ctl, clock, room=18.4)
        self.assertIsNone(ctl.nachlauf)
        self.assertEqual(io.boosts[-1], 0)
        self.assertEqual(io.mode_writes, [])
        ctl, io, clock = self.night()
        ctl.tick()
        io.phase = 2
        self.step(ctl, clock)
        self.assertIsNone(ctl.nachlauf)
        self.assertEqual(io.mode_writes, [])

    def test_off_means_immediate(self):
        ctl, io, clock = self.night(nacht_nachlauf=0)
        io.flame = True
        ctl.tick()
        self.assertEqual(io.mode_writes, [1])


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
