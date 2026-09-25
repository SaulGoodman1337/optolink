#!/opt/optolink/venv/bin/python
"""Read-only WB2A A1-withdrawal/internal-pump overrun watcher.

Research question
-----------------
When the A1 pump request (0x7663[1]) is withdrawn, does the internal-pump
result path continue at the coding-plug minimum GWG75 for approximately the
coding-plug overrun time GWG76?

The watcher uses only the permanent VS1/MQTT production path. It performs no
P300 switch, no writes and no service stop/start.

Trigger:
  previously 0x7663[1] > 0
  then       0x7663[1] == 0
  while      0x7660[1] > 0

At the trigger it captures K30, K31, E7, 6C and the full 0x1070 block. The
source-backed WB2A layout used by this project maps:
  0x1070[5] = GWG75, minimum internal-pump speed (%)
  0x1070[6] = GWG76, internal-pump overrun time (s)

It then samples until the internal pump stops or --max-after-trigger is
reached. Matching GWG75/GWG76 is classified as correlation only, never causal
proof.

No arbitrary address arguments are exposed.
"""
from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import sys
import time

APP_DIR = "/opt/optolink"
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from c_settings_adapter import settings  # type: ignore
from homeassistant_publish import connect_mqtt  # type: ignore


@dataclass
class Sample:
    mono: float
    iso: str
    a1_out: int
    a1_speed: int
    internal_out: int
    internal_speed: int
    a3c: int
    ww: int
    diverter: int
    flame: int
    modulation: int


def connect():
    if not getattr(settings, "mqtt_listen", None):
        raise SystemExit("mqtt_listen is disabled")
    if not getattr(settings, "mqtt_respond", None):
        raise SystemExit("mqtt_respond is disabled")

    client = connect_mqtt(retries=2, delay=1)
    if client is None:
        raise SystemExit("MQTT connection failed")

    responses: list[str] = []

    def on_message(client, userdata, message):
        if message.topic == settings.mqtt_respond:
            responses.append(message.payload.decode(errors="replace"))

    client.on_message = on_message
    client.subscribe(settings.mqtt_respond)
    time.sleep(0.4)
    return client, responses


def request(client, responses, address: str, length: int, timeout: float = 3.0) -> bytes:
    command = f"r;{address};{length};raw;False"
    expected = int(address, 0)
    responses.clear()
    client.publish(settings.mqtt_listen, command).wait_for_publish()
    deadline = time.monotonic() + timeout

    while time.monotonic() < deadline:
        while responses:
            response = responses.pop(0)
            parts = response.split(";")
            if len(parts) < 3:
                continue
            try:
                addr = int(parts[1], 0)
            except ValueError:
                continue
            if addr != expected:
                continue
            if parts[0] != "1":
                raise RuntimeError(f"{address}: {response}")
            data = bytes.fromhex(parts[2])
            if len(data) < length:
                raise RuntimeError(
                    f"{address}: short payload {data.hex()}, expected {length}"
                )
            return data[:length]
        time.sleep(0.005)

    raise TimeoutError(command)


def runtime_sample(client, responses) -> Sample:
    a1 = request(client, responses, "0x7663", 2)
    internal = request(client, responses, "0x7660", 2)
    a3c = request(client, responses, "0x0A3C", 1)[0]
    ww = request(client, responses, "0x650A", 1)[0]
    diverter = request(client, responses, "0x0A10", 1)[0]
    gfa = request(client, responses, "0x55D3", 11)
    return Sample(
        mono=time.monotonic(),
        iso=datetime.now().astimezone().isoformat(timespec="milliseconds"),
        a1_out=a1[0],
        a1_speed=a1[1],
        internal_out=internal[0],
        internal_speed=internal[1],
        a3c=a3c,
        ww=ww,
        diverter=diverter,
        flame=int(bool(gfa[5] & 0x20)),
        modulation=gfa[9],
    )


def constraint_snapshot(client, responses) -> dict[str, object]:
    k30 = request(client, responses, "0x5730", 1)[0]
    k31 = request(client, responses, "0x5731", 1)[0]
    e7 = request(client, responses, "0x27E7", 1)[0]
    k6c = request(client, responses, "0x676C", 1)[0]
    gwg = request(client, responses, "0x1070", 16)
    return {
        "k30": k30,
        "k31": k31,
        "e7": e7,
        "k6c": k6c,
        "gwg_raw": gwg.hex(),
        "gwg75": gwg[5],
        "gwg76": gwg[6],
    }


def trigger_transition(previous: Sample | None, current: Sample) -> bool:
    return bool(
        previous is not None
        and previous.a1_speed > 0
        and current.a1_speed == 0
        and current.internal_speed > 0
        and previous.ww == 0
        and current.ww == 0
    )


def classify(
    trigger_speed: int,
    duration_s: float | None,
    gwg75: int,
    gwg76: int,
    tolerance_s: float = 5.0,
) -> str:
    speed_match = trigger_speed == gwg75
    duration_match = (
        duration_s is not None
        and abs(duration_s - float(gwg76)) <= tolerance_s
    )
    if speed_match and duration_match:
        return "GWG75_GWG76_CORRELATION_MATCH"
    if speed_match:
        return "GWG75_SPEED_ONLY"
    if duration_match:
        return "GWG76_DURATION_ONLY"
    return "NO_GWG75_GWG76_MATCH"


def fmt(s: Sample, trigger_mono: float | None = None) -> str:
    age = "" if trigger_mono is None else f" T+{s.mono-trigger_mono:6.2f}s"
    return (
        f"A1={s.a1_out:02X}/{s.a1_speed:3d}% "
        f"INT={s.internal_out:02X}/{s.internal_speed:3d}% "
        f"A3C={s.a3c:3d}% WW={s.ww:02X} UV={s.diverter:02X} "
        f"FL={s.flame} MOD={s.modulation:3d}%{age}"
    )


def self_test() -> int:
    import unittest

    def sample(a1: int, internal: int) -> Sample:
        return Sample(
            mono=0.0, iso="", a1_out=int(a1 > 0), a1_speed=a1,
            internal_out=int(internal > 0), internal_speed=internal,
            a3c=internal, ww=0, diverter=3, flame=0, modulation=0,
        )

    class T(unittest.TestCase):
        def test_trigger(self):
            self.assertTrue(trigger_transition(sample(30, 50), sample(0, 50)))
            self.assertFalse(trigger_transition(sample(30, 50), sample(30, 50)))
            self.assertFalse(trigger_transition(sample(30, 50), sample(0, 0)))
            prev = sample(30, 50)
            curr = sample(0, 100)
            curr.ww = 1
            self.assertFalse(trigger_transition(prev, curr))

        def test_full_match(self):
            self.assertEqual(
                classify(50, 60.8, 50, 60),
                "GWG75_GWG76_CORRELATION_MATCH",
            )

        def test_speed_only(self):
            self.assertEqual(classify(50, 30.0, 50, 60), "GWG75_SPEED_ONLY")

        def test_duration_only(self):
            self.assertEqual(classify(40, 58.0, 50, 60), "GWG76_DURATION_ONLY")

        def test_no_match(self):
            self.assertEqual(classify(40, 20.0, 50, 60), "NO_GWG75_GWG76_MATCH")

    result = unittest.TextTestRunner(verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(T)
    )
    if result.wasSuccessful():
        print("A1_WITHDRAWAL_WATCH_TESTS=5/5")
        return 0
    return 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--interval", type=float, default=0.5)
    ap.add_argument("--max-wait", type=float, default=7200.0)
    ap.add_argument("--max-after-trigger", type=float, default=180.0)
    ap.add_argument("--tolerance", type=float, default=5.0)
    ap.add_argument("--output")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()

    if args.self_test:
        return self_test()

    if args.interval < 0.1:
        raise SystemExit("--interval must be >= 0.1")
    if args.max_wait <= 0 or args.max_after_trigger <= 0:
        raise SystemExit("timeouts must be > 0")

    out = (
        Path(args.output)
        if args.output
        else Path.home() / f"wb2a-a1-withdrawal-{datetime.now():%Y%m%d-%H%M%S}.csv"
    )

    client, responses = connect()
    previous: Sample | None = None
    seen_a1_active = False
    started = time.monotonic()
    trigger: Sample | None = None
    constraints: dict[str, object] | None = None
    stop_sample: Sample | None = None

    fields = [
        "timestamp", "phase", "seconds_from_trigger",
        "a1_out", "a1_speed", "internal_out", "internal_speed", "a3c",
        "ww", "diverter", "flame", "modulation",
    ]

    print("WB2A A1-withdrawal watcher")
    print("==========================")
    print("Trigger: A1 speed >0 -> 0 while internal pump remains >0")
    print("Reads only: 7663, 7660, 0A3C, 650A, 0A10, 55D3")
    print("Trigger snapshot: +5730, 5731, 27E7, 676C, 1070")
    print("Writes: none")
    print(f"CSV: {out}")

    try:
        with out.open("w", encoding="utf-8", newline="", buffering=1) as fh:
            writer = csv.DictWriter(fh, fieldnames=fields)
            writer.writeheader()

            while time.monotonic() - started <= args.max_wait:
                cycle = time.monotonic()
                try:
                    s = runtime_sample(client, responses)
                except Exception as exc:
                    print(f"{datetime.now().isoformat()} READ_ERROR {exc}", file=sys.stderr)
                    time.sleep(1.0)
                    continue

                if s.a1_speed > 0:
                    seen_a1_active = True

                if trigger is None and seen_a1_active and trigger_transition(previous, s):
                    trigger = s
                    constraints = constraint_snapshot(client, responses)
                    print()
                    print("=== A1 WITHDRAWAL TRIGGER ===")
                    print(s.iso, fmt(s, s.mono))
                    print(
                        "constraints "
                        f"K30={constraints['k30']:02X} "
                        f"K31={constraints['k31']}% "
                        f"E7={constraints['e7']}% "
                        f"6C={constraints['k6c']}% "
                        f"GWG75={constraints['gwg75']}% "
                        f"GWG76={constraints['gwg76']}s "
                        f"1070={constraints['gwg_raw']}"
                    )

                phase = "triggered" if trigger is not None else "waiting"
                writer.writerow({
                    "timestamp": s.iso,
                    "phase": phase,
                    "seconds_from_trigger": (
                        "" if trigger is None else f"{s.mono-trigger.mono:.3f}"
                    ),
                    "a1_out": s.a1_out,
                    "a1_speed": s.a1_speed,
                    "internal_out": s.internal_out,
                    "internal_speed": s.internal_speed,
                    "a3c": s.a3c,
                    "ww": s.ww,
                    "diverter": s.diverter,
                    "flame": s.flame,
                    "modulation": s.modulation,
                })

                if trigger is not None:
                    if s.internal_speed == 0:
                        stop_sample = s
                        break
                    if s.mono - trigger.mono >= args.max_after_trigger:
                        break

                key = None if previous is None else (
                    previous.a1_speed, previous.internal_speed, previous.a3c,
                    previous.ww, previous.flame
                )
                current_key = (s.a1_speed, s.internal_speed, s.a3c, s.ww, s.flame)
                if key != current_key or trigger is not None:
                    print(s.iso, fmt(s, None if trigger is None else trigger.mono))

                previous = s
                elapsed = time.monotonic() - cycle
                if elapsed < args.interval:
                    time.sleep(args.interval - elapsed)

    except KeyboardInterrupt:
        print("Interrupted; no controller state was changed.")
        return 130
    finally:
        client.loop_stop()
        client.disconnect()

    if trigger is None:
        print("RESULT=NO_A1_WITHDRAWAL_TRIGGER")
        return 2

    duration = None if stop_sample is None else stop_sample.mono - trigger.mono
    assert constraints is not None
    result = classify(
        trigger.internal_speed,
        duration,
        int(constraints["gwg75"]),
        int(constraints["gwg76"]),
        args.tolerance,
    )

    print()
    print("=== RESULT ===")
    print(f"trigger_internal_speed={trigger.internal_speed}%")
    print(f"GWG75={constraints['gwg75']}%")
    print(
        "duration_to_internal_off="
        + ("not_observed" if duration is None else f"{duration:.2f}s")
    )
    print(f"GWG76={constraints['gwg76']}s")
    print(f"CLASSIFICATION={result}")
    print("Interpretation: correlation only; not causal proof.")
    print(f"CSV={out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
