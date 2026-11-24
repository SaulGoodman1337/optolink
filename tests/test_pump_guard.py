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
        self.ram = bytearray(32)
        self.ram[5] = 100
        self.next_reload = 2.3
        self.log = []
        self.alive = True

    def advance(self, dt):
        self.t += dt
        while self.t >= self.next_reload:
            self.ram[5] = self.e7
            self.next_reload += 2.3

    def request(self, fc, addr, n, data):
        self.log.append((fc, addr, n, bytes(data)))
        if not self.alive:
            return 0xFF, addr, bytearray()
        if fc == 0x04:
            assert addr == 0x20A5 and n == 1
            self.ram[5] = data[0]
            return 0x01, addr, bytearray()
        values = {
            (0x01, 0x55D3): self.gfa, (0x01, 0x650A): bytes([self.ww]),
            (0x01, 0x0A10): bytes([self.valve]), (0x01, 0x5738): bytes([self.fault]),
            # live finding: 0x27E7 reads the active RAM copy, not the coded value
            (0x01, 0x27E7): bytes([self.ram[5]]), (0x03, 0x20A0): bytes(self.ram),
        }
        return 0x01, addr, bytearray(values[(fc, addr)])


def make_guard(boiler, enabled=True, low=30):
    settings = types.SimpleNamespace(vs1protocol=False, mqtt_topic="openv", mqtt_broker=None)
    g = pg.PumpGuard(settings, logging.getLogger("pg-test"), boiler.request)
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

    def test_blocked_write_value(self):
        b = FakeBoiler()
        g = make_guard(b)
        with self.assertRaises(RuntimeError):
            g._write_ram(55)
        with self.assertRaises(RuntimeError):
            g._read((0x01, 0x27E6, 1))


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
        g._on_message(client, None, msg("enabled/state", "OFF"))  # non-retained echo ignored
        self.assertTrue(g.logic.enabled)


class PatchTest(unittest.TestCase):
    def test_selftest(self):
        self.assertEqual(patcher.self_test(), 0)

    def test_tick_anchor_is_p300_runtime_output(self):
        self.assertIn(patcher.SWITCH_REPLACEMENTS[2][1].strip("\n"), p300rt.SWITCH_REPLACEMENTS[2][2])


if __name__ == "__main__":
    unittest.main()
