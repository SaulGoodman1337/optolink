"""Pump guard: decision logic, allowlist, RAM repair loop and fail-safe release."""
import importlib.util
import logging
from pathlib import Path
import types
import unittest

ROOT = Path(__file__).resolve().parents[1]


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


pg = _load("pump_guard", ROOT / "config/optolink-splitter/pump_guard.py")
patcher = _load("pump_guard_patch", ROOT / "tools/optolink-apply-pump-guard-patch.py")
p300rt = _load("p300_runtime_patch_for_pg", ROOT / "tools/optolink-apply-p300-runtime-patch.py")

IDLE_GFA = bytes([0, 0, 0, 0, 0, 0x00, 0, 0, 0])
FLAME_GFA = bytes([0, 0, 0, 0, 0, 0x20, 0, 0, 0])
SEQ_GFA = bytes([0, 0, 0, 0, 0, 0x00, 0x02, 0x01, 0])


class FakeBoiler:
    """Emulates the P300 datapoints and the firmware's E7 RAM reload."""

    def __init__(self):
        self.t = 0.0
        self.gfa = IDLE_GFA
        self.ww, self.valve, self.fault, self.e7 = 0, 1, 0, 100
        self.kessel, self.soll = 36.0, 36.5
        self.abgas = 34.0
        self.rkr = bytearray(17)
        self.rkr[14] = 0x43               # Regelbetrieb / restart released (bit0 = 1)
        self.ram = bytearray(32)
        self.ram[5] = 100
        self.ram[4] = 100                 # E6 RAM copy (coded 100), reloaded together with E7
        self.e6 = 100
        self.next_reload = 2.3
        self.log = []
        self.alive = True

    def advance(self, dt):
        self.t += dt
        while self.t >= self.next_reload:
            self.ram[5] = self.e7
            self.ram[4] = self.e6
            self.next_reload += 2.3

    def request(self, fc, addr, n, data):
        self.log.append((fc, addr, n, bytes(data)))
        if not self.alive:
            return 0xFF, addr, bytearray()
        if fc == 0x04:
            assert (addr, n) in ((0x20A5, 1), (0x20A4, 2))
            self.ram[addr - 0x20A0:addr - 0x20A0 + n] = bytes(data)
            return 0x01, addr, bytearray()
        values = {
            (0x01, 0x55D3): self.gfa, (0x01, 0x650A): bytes([self.ww]),
            (0x01, 0x0A10): bytes([self.valve]), (0x01, 0x5738): bytes([self.fault]),
            (0x01, 0x0810): int(round(self.kessel * 10)).to_bytes(2, "little", signed=True),
            (0x01, 0x0816): int(round(self.abgas * 10)).to_bytes(2, "little", signed=True),
            (0x01, 0x555A): int(round(self.soll * 10)).to_bytes(2, "little", signed=True),
            (0x01, 0x55E0): bytes(self.rkr),
            # live finding: 0x27E7 reads the active RAM copy, not the coded value
            (0x01, 0x27E7): bytes([self.ram[5]]), (0x03, 0x20A4): bytes(self.ram[4:6]),
            (0x01, 0x27E6): bytes([self.ram[4]]),
        }
        return 0x01, addr, bytearray(values[(fc, addr)])


def make_guard(boiler, enabled=True, low=30):
    settings = types.SimpleNamespace(vs1protocol=False, mqtt_topic="openv", mqtt_broker=None)
    g = pg.PumpGuard(settings, logging.getLogger("pg-test"), boiler.request, boost_after_start=False)
    g.logic.enabled = enabled
    g.logic.low = low
    return g


def run(g, boiler, seconds, step=0.06):
    end = boiler.t + seconds
    samples = []
    while boiler.t < end:
        g.tick(boiler.t)
        boiler.advance(step)
        samples.append(boiler.ram[5])
    return samples


class LogicTest(unittest.TestCase):
    def fresh_logic(self, now=0.0):
        lg = pg.GuardLogic()
        lg.enabled = True
        for k, v in (("gfa", IDLE_GFA), ("ww", b"\0"), ("valve", b"\1"), ("fault", b"\0"), ("e7", b"\x64")):
            lg.update(k, v, now)
        return lg

    def test_normal_lowering(self):
        self.assertEqual(self.fresh_logic().decide(0.0)[0], pg.ABGESENKT)

    def test_boost_reasons(self):
        for key, val, reason in (("ww", b"\1", "Warmwasser"), ("valve", b"\0", "Ventil nicht Heizen"),
                                 ("gfa", FLAME_GFA, "Flamme"), ("gfa", SEQ_GFA, "Startsequenz")):
            lg = self.fresh_logic()
            lg.update(key, val, 0.0)
            self.assertEqual(lg.decide(0.0), (pg.BOOST, reason))

    def test_nachlauf_after_burner(self):
        lg = self.fresh_logic()
        lg.update("gfa", FLAME_GFA, 0.0)
        for t in (1.0, 2.0):
            for k, v in (("gfa", IDLE_GFA), ("ww", b"\0"), ("valve", b"\1")):
                lg.update(k, v, t)
        self.assertEqual(lg.decide(2.0), (pg.BOOST, "Nachlauf"))
        lg.nachlauf_s = 1.0
        self.assertEqual(lg.decide(2.0)[0], pg.ABGESENKT)

    def test_blocking(self):
        lg = self.fresh_logic()
        self.assertEqual(lg.decide(pg.STALE_S + 1)[0], pg.GESPERRT)
        lg = self.fresh_logic()
        lg.update("e7", b"\x1e", 0.0)
        self.assertEqual(lg.decide(0.0)[0], pg.GESPERRT)
        lg = self.fresh_logic()
        lg.update("fault", b"\x05", 0.0)
        self.assertEqual(lg.decide(0.0), (pg.GESPERRT, "Stoerung"))
        lg = self.fresh_logic()
        lg.enabled = False
        self.assertEqual(lg.decide(0.0)[0], pg.AUS)


class GuardTest(unittest.TestCase):
    def test_holds_low_and_repairs_reloads(self):
        b = FakeBoiler()
        g = make_guard(b)
        run(g, b, 3)                       # warm-up: all state read
        samples = run(g, b, 60)
        low_share = samples.count(30) / len(samples)
        self.assertGreater(low_share, 0.8)
        self.assertGreater(g.repairs, 20)
        self.assertIsNone(g.logic.error)

    def test_lowering_is_stable_although_e7_mirrors_ram(self):
        b = FakeBoiler()
        g = make_guard(b)
        run(g, b, 8)                       # first coded-E7 read happens before lowering
        states = set()
        end = b.t + 120
        while b.t < end:
            g.tick(b.t)
            b.advance(0.06)
            states.add(g.logic.decide(b.t)[0])
        self.assertEqual(states, {pg.ABGESENKT})

    def test_vorboost_learns_threshold_and_boosts_early(self):
        b = FakeBoiler()
        g = make_guard(b)
        g.logic.nachlauf_s = 0.0
        run(g, b, 8)
        # burner start at 3 K below setpoint -> learned threshold moves towards 3 K
        b.kessel = 33.5
        run(g, b, 6)
        b.gfa = SEQ_GFA
        b.soll = 16.5                                 # firmware drops the setpoint at the start
        run(g, b, 3)
        b.soll = 36.5
        b.gfa = IDLE_GFA
        b.kessel = 37.0
        run(g, b, 3)
        self.assertEqual(g.logic.start_margins, [3.0])
        self.assertAlmostEqual(g.logic.start_margin, 0.7 * 4.0 + 0.3 * 3.0)
        g.logic.vorboost_aktiv = True
        g.logic.vorboost_k = 1.0                      # trigger at 3.7 - 1.0 = 2.7 K below
        b.kessel = 34.0                               # 2.5 K below: still lowered
        run(g, b, 4)
        self.assertEqual(g.logic.decide(b.t)[0], pg.ABGESENKT)
        b.kessel = 33.7                               # 2.8 K below: pre-boost
        run(g, b, 4)
        self.assertEqual(g.logic.decide(b.t), (pg.BOOST, "Vorboost"))
        self.assertEqual(b.ram[5], 100)
        b.kessel = 33.9                               # hysteresis keeps it on
        run(g, b, 4)
        self.assertEqual(g.logic.decide(b.t), (pg.BOOST, "Vorboost"))
        b.kessel = 34.4                               # 2.1 K below: released
        run(g, b, 4)
        self.assertEqual(g.logic.decide(b.t)[0], pg.ABGESENKT)

    def test_vorboost_off_by_default_and_stale_temps(self):
        b = FakeBoiler()
        b.kessel = 20.0
        g = make_guard(b)
        run(g, b, 8)
        self.assertEqual(g.logic.decide(b.t)[0], pg.ABGESENKT)   # vorboost_aktiv = False
        g.logic.vorboost_aktiv = True
        g.logic.vorboost_k = 0.0                                 # 0 K also means off
        run(g, b, 3)
        self.assertEqual(g.logic.decide(b.t)[0], pg.ABGESENKT)
        g.logic.vorboost_k = 2.0
        run(g, b, 3)
        self.assertEqual(g.logic.decide(b.t)[1], "Vorboost")
        g.logic.ts["kessel"] = b.t - 60                          # stale temperature
        self.assertFalse(g.logic.vorboost(b.t))

    def test_nachlauf_switch(self):
        b = FakeBoiler()
        g = make_guard(b)
        g.logic.nachlauf_s = 60.0
        run(g, b, 8)
        b.gfa = FLAME_GFA
        run(g, b, 3)
        b.gfa = IDLE_GFA
        run(g, b, 3)
        self.assertEqual(g.logic.decide(b.t), (pg.BOOST, "Nachlauf"))
        g.logic.nachlauf_aktiv = False
        self.assertEqual(g.logic.decide(b.t)[0], pg.ABGESENKT)

    def test_defaults_follow_normal_burner_cycle(self):
        lg = pg.GuardLogic()
        self.assertTrue(lg.nachlauf_aktiv)
        self.assertEqual(lg.nachlauf_s, 180.0)
        self.assertFalse(lg.vorboost_aktiv)
        self.assertEqual(lg.vorboost_k, 1.0)
        self.assertNotIn((0x01, 0x55E0, 17), pg.ALLOWED_READS)

    def test_burner_curve(self):
        b = FakeBoiler()
        g = make_guard(b)
        g.logic.nachlauf_s = 0.0
        g.logic.kurve_aktiv = True
        g.logic.kurve_start_s = 5.0
        run(g, b, 8)
        # first heating burn: nothing learned yet -> 100 %; stops at 45.0 -> switch-off learned
        b.gfa = FLAME_GFA
        run(g, b, 8)
        self.assertEqual(g.logic.decide(b.t), (pg.BOOST, "Flamme"))
        b.kessel = 45.0
        run(g, b, 3)
        b.gfa = IDLE_GFA
        b.kessel = 33.0
        run(g, b, 3)
        self.assertEqual(g.logic.aus_temp, 45.0)
        # next burn: start hold 100 %, then curve value by headroom
        b.gfa = FLAME_GFA
        run(g, b, 2)
        self.assertEqual(g.logic.decide(b.t), (pg.BOOST, "Flamme"))
        b.kessel = 36.0                               # headroom 9 K >= 3 + 5 -> kurve_min
        samples = run(g, b, 8)
        self.assertEqual(g.logic.decide(b.t), (pg.KENNLINIE, "Brenner-Kennlinie 60 %"))
        self.assertGreater(samples[-60:].count(60), 40)
        b.kessel = 39.5                               # headroom 5.5 -> 100 - 0.5*40 = 80
        samples = run(g, b, 4)
        self.assertEqual(g.logic.decide(b.t)[1], "Brenner-Kennlinie 80 %")
        self.assertGreater(samples[-30:].count(80), 15)
        b.kessel = 42.5                               # within 3 K of switch-off -> 100 %
        run(g, b, 4)
        self.assertEqual(g.logic.decide(b.t), (pg.BOOST, "Flamme"))
        self.assertEqual(b.ram[5], 100)
        b.ww = 1                                      # DHW always 100 %
        b.kessel = 36.0
        run(g, b, 4)
        self.assertEqual(g.logic.decide(b.t), (pg.BOOST, "Warmwasser"))
        self.assertIsNone(g.logic.error)

    def test_burner_curve_off_by_default(self):
        lg = pg.GuardLogic()
        self.assertFalse(lg.kurve_aktiv)
        lg.flame, lg.flame_since, lg.aus_temp, lg.kessel = True, 0.0, 45.0, 30.0
        lg.ts["kessel"] = 100.0
        self.assertIsNone(lg.kurve(100.0))

    def test_abgas_spreizung_controller(self):
        b = FakeBoiler()
        g = make_guard(b)
        g.logic.nachlauf_s = 0.0
        g.logic.spreizung_aktiv = True
        g.logic.kurve_start_s = 5.0
        g.logic.kurve_min = 60
        g.logic.spreizung_soll = 5.0
        run(g, b, 8)
        b.gfa = FLAME_GFA
        b.kessel, b.abgas = 45.0, 43.0                # spread 2 K < 5 - 0.5 -> step down
        run(g, b, 3)
        self.assertEqual(g.logic.decide(b.t), (pg.BOOST, "Flamme"))     # start hold
        run(g, b, 4)
        self.assertEqual(g.logic.decide(b.t), (pg.KENNLINIE, "Abgas-Spreizung 95 %"))
        run(g, b, pg.SPREIZ_STEP_S * 3 + 1)
        self.assertEqual(g.logic.kurve_wert, 80)
        run(g, b, pg.SPREIZ_STEP_S * 10)
        self.assertEqual(g.logic.kurve_wert, 60)     # bounded by kurve_min
        samples = run(g, b, 4)
        self.assertGreater(samples.count(60), len(samples) // 2)
        b.abgas = 38.0                                # spread 7 K > 5.5 -> step up
        run(g, b, pg.SPREIZ_STEP_S + 3)
        self.assertEqual(g.logic.kurve_wert, 65)
        b.abgas = 40.5                                # within deadband -> hold
        run(g, b, pg.SPREIZ_STEP_S * 2 + 1)
        self.assertEqual(g.logic.kurve_wert, 65)
        g.logic.ts["abgas"] = b.t - 60                # stale flue gas -> 100 %
        self.assertEqual(g.logic.decide(b.t), (pg.BOOST, "Flamme"))
        self.assertIsNone(g.logic.error)

    def test_abgas_spreizung_switch_off_protection(self):
        lg = pg.GuardLogic()
        lg.spreizung_aktiv, lg.kurve_start_s = True, 0.0
        lg.flame, lg.flame_since, lg.aus_temp = True, 0.0, 45.0
        lg.kessel, lg.abgas = 43.0, 41.0              # 2 K before switch-off <= 3 K
        lg.ts.update(kessel=10.0, abgas=10.0)
        self.assertIsNone(lg.kurve(10.0))

    def test_restart_starts_with_nachlauf_boost(self):
        b = FakeBoiler()
        settings = types.SimpleNamespace(vs1protocol=False, mqtt_topic="openv", mqtt_broker=None)
        g = pg.PumpGuard(settings, logging.getLogger("pg-test"), b.request)
        g.logic.enabled = True
        g.logic.nachlauf_s = 60.0
        run(g, b, 8)
        self.assertEqual(g.logic.decide(b.t), (pg.BOOST, "Nachlauf"))
        run(g, b, 60)
        self.assertEqual(g.logic.decide(b.t)[0], pg.ABGESENKT)

    def test_implausible_temperature_ignored(self):
        lg = pg.GuardLogic()
        lg.update("kessel", (3000).to_bytes(2, "little", signed=True), 0.0)
        self.assertIsNone(lg.kessel)
        self.assertNotIn("kessel", lg.ts)

    def test_only_allowed_telegrams(self):
        b = FakeBoiler()
        g = make_guard(b)
        run(g, b, 30)
        b.gfa = FLAME_GFA
        run(g, b, 10)
        for fc, addr, n, data in b.log:
            if fc == 0x04:
                self.assertEqual((addr, n), (0x20A5, 1))
                self.assertIn(data[0], (30, 100))
            else:
                self.assertIn((fc, addr, n), pg.ALLOWED_READS)

    def test_boost_on_start_sequence_is_fast(self):
        b = FakeBoiler()
        g = make_guard(b)
        run(g, b, 10)
        self.assertEqual(b.ram[5], 30)
        b.gfa = SEQ_GFA
        t0 = b.t
        while b.ram[5] != 100 and b.t - t0 < 5:
            g.tick(b.t)
            b.advance(0.06)
        self.assertLess(b.t - t0, 1.6)
        samples = run(g, b, 20)
        self.assertTrue(all(s == 100 for s in samples))

    def test_failsafe_when_guard_stops(self):
        b = FakeBoiler()
        g = make_guard(b)
        run(g, b, 10)
        b.advance(3.0)                     # splitter dead: no ticks at all
        self.assertEqual(b.ram[5], 100)

    def test_link_dead_blocks_lowering(self):
        b = FakeBoiler()
        g = make_guard(b)
        run(g, b, 10)
        b.alive = False
        run(g, b, pg.STALE_S + 3)
        self.assertEqual(g.logic.decide(b.t)[0], pg.GESPERRT)
        self.assertEqual(b.ram[5], 100)

    def test_coded_e7_not_100_blocks(self):
        b = FakeBoiler()
        b.e7 = 30
        b.ram[5] = 30
        g = make_guard(b)
        run(g, b, 10)
        self.assertEqual(g.logic.decide(b.t)[0], pg.GESPERRT)
        self.assertFalse(any(fc == 0x04 for fc, *_ in b.log))

    def test_disabled_never_writes(self):
        b = FakeBoiler()
        g = make_guard(b, enabled=False)
        run(g, b, 20)
        self.assertFalse(any(fc == 0x04 for fc, *_ in b.log))

    def test_low_change_while_lowering(self):
        b = FakeBoiler()
        g = make_guard(b)
        run(g, b, 10)
        g.logic.low = 40
        run(g, b, 5)
        self.assertIsNone(g.logic.error)
        self.assertEqual(b.ram[5], 40)

    def test_unexpected_ram_value_stops(self):
        b = FakeBoiler()
        g = make_guard(b)
        run(g, b, 10)
        b.ram[5] = 55
        run(g, b, 2)
        self.assertEqual(g.logic.decide(b.t)[0], pg.FEHLER)
        run(g, b, 5)
        self.assertEqual(b.ram[5], 100)

    def test_vs1_inactive(self):
        b = FakeBoiler()
        settings = types.SimpleNamespace(vs1protocol=True, mqtt_topic="openv", mqtt_broker=None)
        g = pg.PumpGuard(settings, logging.getLogger("pg-test"), b.request)
        g.logic.enabled = True
        self.assertIsNone(g.tick(0.0))
        self.assertEqual(b.log, [])

    def test_slow_firmware_reload_does_not_starve_state_reads(self):
        b = FakeBoiler()
        g = make_guard(b)
        run(g, b, 5)
        b.next_reload = b.t + 8.0          # firmware takes 8 s for the next reload
        states = []
        end = b.t + 7.5
        while b.t < end:
            g.tick(b.t)
            b.advance(0.08)
            states.append(g.logic.decide(b.t)[0])
        self.assertNotIn(pg.GESPERRT, states)

    def test_reload_is_repaired_fast(self):
        b = FakeBoiler()
        g = make_guard(b, low=20)
        run(g, b, 5)
        samples = run(g, b, 30, step=0.02)
        # time per reload spent at 100 % (reload every 2.3 s, one telegram ~0.08 s)
        high = samples.count(100) * 0.02 / (30 / 2.3)
        self.assertLess(high, 0.2)

    def test_e6_off_by_default_never_touches_e6(self):
        b = FakeBoiler()
        g = make_guard(b)
        run(g, b, 30)
        self.assertFalse(g.logic.e6_aktiv)
        self.assertTrue(all(addr == 0x20A5 for fc, addr, n, d in b.log if fc == 0x04))
        self.assertEqual(b.ram[4], 100)

    def test_e6_lowered_together_with_e7(self):
        b = FakeBoiler()
        g = make_guard(b, low=20)
        g.logic.e6_aktiv = True
        run(g, b, 25)                      # coded E6 = 100 proven by the slow read first
        self.assertEqual(g.logic.e6, 100)
        e6 = []
        end = b.t + 60
        while b.t < end:
            g.tick(b.t)
            b.advance(0.06)
            e6.append(b.ram[4])
        self.assertGreater(e6.count(20) / len(e6), 0.8)
        self.assertGreater(g.repairs, 20)
        self.assertIsNone(g.logic.error)
        for fc, addr, n, data in b.log:
            if fc == 0x04:
                self.assertIn((addr, n), ((0x20A5, 1), (0x20A4, 2)))
                self.assertTrue(all(v in (20, 100) for v in data))
        # boost: both back to 100 quickly, fail-safe: firmware reload restores both
        b.gfa = SEQ_GFA
        t0 = b.t
        while (b.ram[4], b.ram[5]) != (100, 100) and b.t - t0 < 5:
            g.tick(b.t)
            b.advance(0.06)
        self.assertLess(b.t - t0, 1.6)
        b.gfa = IDLE_GFA
        g.logic.nachlauf_aktiv = False
        run(g, b, 10)
        self.assertEqual((b.ram[4], b.ram[5]), (20, 20))
        b.advance(3.0)
        self.assertEqual((b.ram[4], b.ram[5]), (100, 100))

    def test_e6_switched_off_while_lowered_is_restored(self):
        b = FakeBoiler()
        g = make_guard(b, low=20)
        g.logic.e6_aktiv = True
        run(g, b, 25)
        self.assertEqual(b.ram[4], 20)
        b.e6 = 77                          # pretend the coded E6 differs: the guard must
        g.logic.e6_aktiv = False           # not need the reload to undo its own lowering
        b.next_reload = b.t + 100
        run(g, b, 2)
        self.assertEqual(b.ram[4], 100)
        self.assertEqual(b.ram[5], 20)

    def test_e6_not_lowered_before_coded_value_is_proven(self):
        b = FakeBoiler()
        g = make_guard(b, low=20)
        g.logic.e6_aktiv = True
        run(g, b, 3)
        self.assertIsNone(g.logic.e6)
        self.assertEqual(b.ram[4], 100)

    def test_coded_e6_drift_blocks(self):
        b = FakeBoiler()
        g = make_guard(b, low=20)
        g.logic.e6_aktiv = True
        run(g, b, 25)
        self.assertEqual(b.ram[4], 20)
        b.e6 = 20                          # firmware took over the lowered value
        b.e7 = 100
        run(g, b, 5)
        # E6 is reloaded together with E7: at that moment ram6 is the coded value,
        # so even a drift to exactly the target value is caught
        state, reason = g.logic.decide(b.t)
        self.assertEqual(state, pg.GESPERRT)
        self.assertIn("E6 codiert 20", reason)
        self.assertEqual(b.ram[5], 100)

    def test_e6_mqtt_switch(self):
        b = FakeBoiler()
        g = make_guard(b)
        msg = types.SimpleNamespace(topic="openv/pump_guard/e6_aktiv/set", payload=b"ON", retain=False)
        pub = []
        client = types.SimpleNamespace(publish=lambda *a, **k: pub.append(a))
        g._on_message(client, None, msg)
        self.assertTrue(g.logic.e6_aktiv)
        self.assertIn(("openv/pump_guard/e6_aktiv/state", "ON"), pub)

    def test_blocked_write_value(self):
        b = FakeBoiler()
        g = make_guard(b)
        with self.assertRaises(RuntimeError):
            g._write_ram(55)
        with self.assertRaises(RuntimeError):
            g._write_ram(100, 55)
        with self.assertRaises(RuntimeError):
            g._read((0x01, 0x27E5, 1))


class MqttTest(unittest.TestCase):
    def test_set_and_retained_restore(self):
        published = []

        class Client:
            on_connect = None

            def subscribe(self, topics):
                self.topics = topics

            def publish(self, topic, payload, retain=False):
                published.append((topic, payload, retain))

        client = Client()
        settings = types.SimpleNamespace(vs1protocol=False, mqtt_topic="openv", mqtt_broker=None)
        g = pg.PumpGuard(settings, logging.getLogger("pg-test"), FakeBoiler().request, lambda: client)
        msg = lambda t, p, r=False: types.SimpleNamespace(topic="openv/pump_guard/" + t, payload=p.encode(), retain=r)
        g._on_message(client, None, msg("enabled/set", "ON"))
        self.assertTrue(g.logic.enabled)
        self.assertIn(("openv/pump_guard/enabled/state", "ON", True), published)
        g._on_message(client, None, msg("low/set", "10"))       # out of range: ignored
        self.assertEqual(g.logic.low, 30)
        g._on_message(client, None, msg("low/state", "45", True))
        self.assertEqual(g.logic.low, 45)
        g._on_message(client, None, msg("nachlauf/set", "5"))
        self.assertEqual(g.logic.nachlauf_s, 300.0)
        g._on_message(client, None, msg("nachlauf_aktiv/set", "OFF"))
        self.assertFalse(g.logic.nachlauf_aktiv)
        self.assertIn(("openv/pump_guard/nachlauf_aktiv/state", "OFF", True), published)
        g._on_message(client, None, msg("vorboost_aktiv/state", "ON", True))
        self.assertTrue(g.logic.vorboost_aktiv)
        g._on_message(client, None, msg("enabled/state", "OFF"))  # non-retained echo ignored
        self.assertTrue(g.logic.enabled)


class PatchTest(unittest.TestCase):
    def test_selftest(self):
        self.assertEqual(patcher.self_test(), 0)

    def test_tick_anchor_is_p300_runtime_output(self):
        self.assertIn(patcher.SWITCH_REPLACEMENTS[2][1].strip("\n"), p300rt.SWITCH_REPLACEMENTS[2][2])


if __name__ == "__main__":
    unittest.main()
