"""fan_p06: VS1-window schedule, read allowlist, fail-closed handling and the switch patch."""
import importlib.util
import json
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


fp = _load("fan_p06", ROOT / "config/optolink-splitter/fan_p06.py")
patcher = _load("fan_p06_patch", ROOT / "tools/optolink-apply-fan-p06-patch.py")


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


class FakeBackend:
    def __init__(self, clock):
        self.clock = clock
        self.mode = "P300"
        self.calls = []
        self.gfa_values = {fp.GFA_P80: 0x20, fp.GFA_P06: 0x93, fp.GFA_P09: 0x55, fp.GFA_P87: 0x00}
        self.vs1_ok = True
        self.p300_ok = [True, True]
        self.flame_byte = 0x20

    def do_request(self, fc, addr, n, data=b""):
        assert self.mode == "P300"
        self.calls.append(("p300", fc, addr, n))
        assert (fc, addr, n) == fp.READ_STATUS
        return 0x01, addr, bytearray([0, 0, 0, 0, 0, self.flame_byte, 0, 0, 0])

    def to_vs1(self):
        self.calls.append(("to_vs1",))
        self.clock.t += 4.0
        if self.vs1_ok:
            self.mode = "VS1"
        return self.vs1_ok

    def gfa(self, addr):
        assert self.mode == "VS1", "GFA only in VS1"
        self.calls.append(("gfa", addr))
        self.clock.t += 0.05
        return 0x01, bytes([self.gfa_values[addr]])

    def to_p300(self):
        self.calls.append(("to_p300",))
        self.clock.t += 2.0
        ok = self.p300_ok.pop(0) if self.p300_ok else True
        if ok:
            self.mode = "P300"
        return ok


class FakeMqtt:
    def __init__(self):
        self.pub = []
        self.on_connect = None
        self.on_message = None

    def subscribe(self, *a, **k):
        pass

    def publish(self, topic, payload, retain=False):
        self.pub.append((topic, payload, retain))

    def last(self, topic):
        for t, p, _ in reversed(self.pub):
            if t == topic:
                return p
        return None


def make(flame_fn=None):
    clock = Clock()
    be = FakeBackend(clock)
    mq = FakeMqtt()
    settings = types.SimpleNamespace(vs1protocol=False, mqtt_topic="openv", mqtt_broker=None)
    obj = fp.FanP06(settings, logging.getLogger("t"), be, flame_fn=flame_fn,
                    mqtt_factory=lambda: mq, clock=clock)
    return obj, be, mq, clock


class FanP06Tests(unittest.TestCase):
    def run_for(self, obj, clock, seconds, step=1.0):
        end = clock.t + seconds
        while clock.t < end:
            obj.tick()
            clock.t += step

    def test_first_window_after_start_delay_then_interval(self):
        obj, be, mq, clock = make(flame_fn=lambda: True)
        self.run_for(obj, clock, fp.START_DELAY_S - 2)
        self.assertNotIn(("to_vs1",), be.calls)
        self.run_for(obj, clock, 5)
        self.assertEqual(be.calls.count(("to_vs1",)), 1)
        self.assertEqual(mq.last("openv/geblaesedrehzahl_gfa_p06"), str(0x93 * 30))
        self.assertEqual(mq.last("openv/gfa_modulationssollwert_p09"), str(round(0x55 * 0.3922, 1)))
        self.assertEqual(be.mode, "P300")
        self.run_for(obj, clock, obj.interval_s - 20)
        self.assertEqual(be.calls.count(("to_vs1",)), 1)
        self.run_for(obj, clock, 30)
        self.assertEqual(be.calls.count(("to_vs1",)), 2)
        st = json.loads(mq.last("openv/fan_p06/status"))
        self.assertEqual(st["state"], fp.OK)
        self.assertEqual(st["rpm"], 0x93 * 30)

    def test_no_window_without_flame_and_zero_after_off(self):
        flame = {"v": True}
        obj, be, mq, clock = make(flame_fn=lambda: flame["v"])
        self.run_for(obj, clock, 60)
        self.assertEqual(be.calls.count(("to_vs1",)), 1)
        flame["v"] = False
        self.run_for(obj, clock, fp.OFF_ZERO_S + 5)
        self.assertEqual(mq.last("openv/geblaesedrehzahl_gfa_p06"), "0")
        self.run_for(obj, clock, 3600)
        self.assertEqual(be.calls.count(("to_vs1",)), 1)

    def test_new_burn_gets_its_own_first_window(self):
        flame = {"v": True}
        obj, be, mq, clock = make(flame_fn=lambda: flame["v"])
        self.run_for(obj, clock, 60)
        flame["v"] = False
        self.run_for(obj, clock, 100)
        flame["v"] = True
        self.run_for(obj, clock, fp.START_DELAY_S + 3)
        self.assertEqual(be.calls.count(("to_vs1",)), 2)

    def test_disabled_never_switches(self):
        obj, be, mq, clock = make(flame_fn=lambda: True)
        obj.enabled = False
        self.run_for(obj, clock, 3600)
        self.assertNotIn(("to_vs1",), be.calls)

    def test_only_allowlisted_gfa_reads(self):
        obj, be, mq, clock = make(flame_fn=lambda: True)
        self.run_for(obj, clock, 50)
        addrs = [c[1] for c in be.calls if c[0] == "gfa"]
        self.assertEqual(addrs, [fp.GFA_P80, fp.GFA_P06, fp.GFA_P09, fp.GFA_P87])

    def test_wrong_p80_is_not_published_and_returns_to_p300(self):
        obj, be, mq, clock = make(flame_fn=lambda: True)
        be.gfa_values[fp.GFA_P80] = 0x21
        self.run_for(obj, clock, 50)
        self.assertIsNone(mq.last("openv/geblaesedrehzahl_gfa_p06"))
        self.assertEqual(be.mode, "P300")
        self.assertEqual(obj.state, fp.FEHLER)

    def test_ff_is_not_published(self):
        obj, be, mq, clock = make(flame_fn=lambda: True)
        be.gfa_values[fp.GFA_P06] = 0xFF
        self.run_for(obj, clock, 50)
        self.assertIsNone(mq.last("openv/geblaesedrehzahl_gfa_p06"))

    def test_p300_return_retried_once(self):
        obj, be, mq, clock = make(flame_fn=lambda: True)
        be.p300_ok = [False, True]
        self.run_for(obj, clock, 50)
        self.assertEqual(be.calls.count(("to_p300",)), 2)
        self.assertEqual(be.mode, "P300")
        self.assertEqual(obj.state, fp.OK)

    def test_p300_return_failure_reports_ff(self):
        obj, be, mq, clock = make(flame_fn=lambda: True)
        be.p300_ok = [False, False]
        clock.t += fp.START_DELAY_S
        obj.tick()               # flame seen
        clock.t += fp.START_DELAY_S
        self.assertEqual(obj.tick(), 0xFF)
        self.assertEqual(obj.state, fp.FEHLER)

    def test_repeated_failures_block(self):
        obj, be, mq, clock = make(flame_fn=lambda: True)
        be.vs1_ok = False
        obj.interval_s = 60
        self.run_for(obj, clock, 400)
        self.assertEqual(be.calls.count(("to_vs1",)), fp.MAX_FAILS)
        self.assertEqual(obj.state, fp.GESPERRT)
        self.assertEqual(be.mode, "P300")

    def test_own_status_read_without_flame_fn(self):
        obj, be, mq, clock = make(flame_fn=None)
        self.run_for(obj, clock, 60)
        self.assertIn(("p300",) + fp.READ_STATUS, be.calls)
        self.assertEqual(be.calls.count(("to_vs1",)), 1)

    def test_inactive_in_vs1(self):
        obj, be, mq, clock = make(flame_fn=lambda: True)
        obj.active = False
        self.run_for(obj, clock, 600)
        self.assertEqual(be.calls, [])

    def test_mqtt_interval_and_enable(self):
        obj, be, mq, clock = make(flame_fn=lambda: True)
        msg = types.SimpleNamespace(topic="openv/fan_p06/interval/set", payload=b"2", retain=False)
        obj._on_message(mq, None, msg)
        self.assertEqual(obj.interval_s, 120)
        msg = types.SimpleNamespace(topic="openv/fan_p06/interval/set", payload=b"99", retain=False)
        obj._on_message(mq, None, msg)
        self.assertEqual(obj.interval_s, 120)
        msg = types.SimpleNamespace(topic="openv/fan_p06/enabled/set", payload=b"OFF", retain=False)
        obj._on_message(mq, None, msg)
        self.assertFalse(obj.enabled)
        self.assertEqual(mq.last("openv/fan_p06/enabled/state"), "OFF")


class PatchTests(unittest.TestCase):
    def test_self_test(self):
        self.assertEqual(patcher.self_test(), 0)


if __name__ == "__main__":
    unittest.main()
