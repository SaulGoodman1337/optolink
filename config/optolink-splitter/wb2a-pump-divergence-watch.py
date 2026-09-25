#!/opt/optolink/venv/bin/python
"""Read-only WB2A internal-pump divergence watcher.

Waits for a state in which the physical/internal pump speed (0x7660[1])
differs from the A1 pump demand (0x7663[1]) and captures 0x0A3C at the same
time. This is intended to discriminate whether 0x0A3C follows the final
internal-pump command or the A1 demand.

No writes are performed.
"""

import argparse
import sys
import time
from datetime import datetime

APP_DIR = "/opt/optolink"
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from c_settings_adapter import settings  # type: ignore
from homeassistant_publish import connect_mqtt  # type: ignore


def connect():
    if not getattr(settings, "mqtt_listen", None):
        raise SystemExit("mqtt_listen is disabled")
    if not getattr(settings, "mqtt_respond", None):
        raise SystemExit("mqtt_respond is disabled")

    client = connect_mqtt(retries=2, delay=1)
    if client is None:
        raise SystemExit("MQTT connection failed")

    responses = []

    def on_message(client, userdata, message):
        if message.topic == settings.mqtt_respond:
            responses.append(message.payload.decode(errors="replace"))

    client.on_message = on_message
    client.subscribe(settings.mqtt_respond)
    time.sleep(0.4)
    return client, responses


def request(client, responses, address, length, timeout=3.0):
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
            try:
                data = bytes.fromhex(parts[2])
            except ValueError as exc:
                raise RuntimeError(f"{address}: bad payload {response}") from exc
            if len(data) < length:
                raise RuntimeError(
                    f"{address}: short payload {data.hex()}, expected {length} bytes"
                )
            return data[:length]
        time.sleep(0.005)

    raise TimeoutError(command)


def snapshot(client, responses):
    a3a = request(client, responses, "0x0A3A", 1)[0]
    a3b = request(client, responses, "0x0A3B", 1)[0]
    a3c = request(client, responses, "0x0A3C", 1)[0]
    p7660 = request(client, responses, "0x7660", 2)
    p7663 = request(client, responses, "0x7663", 2)
    ww = request(client, responses, "0x650A", 1)[0]
    uv = request(client, responses, "0x0A10", 1)[0]
    gfa = request(client, responses, "0x55D3", 11)
    return {
        "a3a": a3a,
        "a3b": a3b,
        "a3c": a3c,
        "out7660": p7660[0],
        "speed7660": p7660[1],
        "out7663": p7663[0],
        "speed7663": p7663[1],
        "ww": ww,
        "uv": uv,
        "flame": int(bool(gfa[5] & 0x20)),
        "modulation": gfa[9],
        "gfa_b5": gfa[5],
        "gfa_b7": gfa[7],
    }


def constraint_snapshot(client, responses):
    """Capture static/slow selector inputs at the divergence time.

    These are read only when a divergence is captured so the normal watcher
    loop stays lightweight. 0x1070 byte 5 is source-mapped as GWG75, the
    coding-plug minimum internal-pump speed.
    """
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
        "gwg70_76_raw": gwg.hex(),
        "gwg75": gwg[5],
    }


def fmt_constraints(s):
    return (
        f"K30={s['k30']:02X} "
        f"K31={s['k31']:3d}% "
        f"E7={s['e7']:3d}% "
        f"6C={s['k6c']:3d}% "
        f"GWG75={s['gwg75']:3d}% "
        f"1070={s['gwg70_76_raw']}"
    )


def fmt(s):
    relation_internal = (
        "A3C=7660"
        if s["a3c"] == s["speed7660"]
        else "A3C!=7660"
    )
    relation_a1 = (
        "A3A=7663"
        if s["a3a"] == s["speed7663"]
        else "A3A!=7663"
    )
    timing = ""
    if s.get("flame_age_s") is not None:
        timing = f" FLAME_AGE={s['flame_age_s']:.1f}s"
    elif s.get("post_flame_s") is not None:
        timing = f" POST_FLAME={s['post_flame_s']:.1f}s"

    return (
        f"A3A={s['a3a']:3d}% A3B={s['a3b']:3d}%  "
        f"A3C={s['a3c']:3d}%  "
        f"7660={s['out7660']:02X}/{s['speed7660']:3d}%  "
        f"7663={s['out7663']:02X}/{s['speed7663']:3d}%  "
        f"WW=0x{s['ww']:02X}  UV=0x{s['uv']:02X}  "
        f"FLAME={s['flame']} MOD={s['modulation']:3d}%  "
        f"GFA5=0x{s['gfa_b5']:02X} GFA7=0x{s['gfa_b7']:02X}"
        f"{timing}  {relation_a1} {relation_internal}"
    )


def main():
    parser = argparse.ArgumentParser(
        description="Watch WB2A for 0x7660/0x7663 pump-speed divergence"
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=0.5,
        help="minimum seconds between snapshots (default: 0.5)",
    )
    parser.add_argument(
        "--burst",
        type=int,
        default=10,
        help="extra snapshots after first divergence (default: 10)",
    )
    parser.add_argument(
        "--keep-running",
        action="store_true",
        help="continue after the first divergence burst",
    )
    args = parser.parse_args()

    client, responses = connect()
    last_key = None
    previous_flame = None
    flame_on_mono = None
    flame_off_mono = None

    print("WB2A pump divergence watcher")
    print("============================")
    print("Loop reads: 0A3A, 0A3B, 0A3C, 7660, 7663, 650A, 0A10, 55D3")
    print("On divergence: +5730/K30, 5731/K31, 27E7/E7, 676C/6C, 1070/GWG75")
    print("Trigger:   7660[1] != 7663[1]")
    print("Writes:    none")
    print("Ctrl-C beendet")
    print()

    try:
        while True:
            started = time.monotonic()
            try:
                s = snapshot(client, responses)
            except Exception as exc:
                print(
                    f"{datetime.now().isoformat(timespec='milliseconds')} "
                    f"READ_ERROR {exc}",
                    file=sys.stderr,
                )
                time.sleep(1.0)
                continue

            now_mono = time.monotonic()
            flame_now = bool(s["flame"])

            if previous_flame is None:
                previous_flame = flame_now
                if flame_now:
                    flame_on_mono = now_mono
            elif flame_now != previous_flame:
                if flame_now:
                    flame_on_mono = now_mono
                    flame_off_mono = None
                    print(
                        f"{datetime.now().isoformat(timespec='milliseconds')} "
                        "EVENT      FLAME_ON"
                    )
                else:
                    flame_off_mono = now_mono
                    print(
                        f"{datetime.now().isoformat(timespec='milliseconds')} "
                        "EVENT      FLAME_OFF"
                    )
                previous_flame = flame_now

            if flame_now and flame_on_mono is not None:
                s["flame_age_s"] = now_mono - flame_on_mono
                s["post_flame_s"] = None
            elif (not flame_now) and flame_off_mono is not None:
                s["flame_age_s"] = None
                s["post_flame_s"] = now_mono - flame_off_mono
            else:
                s["flame_age_s"] = None
                s["post_flame_s"] = None

            key = tuple(
                s[k] for k in (
                    "a3a", "a3b", "a3c",
                    "out7660", "speed7660", "out7663", "speed7663",
                    "ww", "uv", "flame", "modulation", "gfa_b5", "gfa_b7"
                )
            )
            divergent = s["speed7660"] != s["speed7663"]

            if divergent or key != last_key:
                tag = "DIVERGENCE" if divergent else "STATE"
                print(
                    f"{datetime.now().isoformat(timespec='milliseconds')} "
                    f"{tag:<10} {fmt(s)}"
                )
                last_key = key

            if divergent:
                print()
                print("=== DIVERGENCE CAPTURE ===")
                try:
                    constraints = constraint_snapshot(client, responses)
                    print(
                        f"{datetime.now().isoformat(timespec='milliseconds')} "
                        f"constraints: {fmt_constraints(constraints)}"
                    )
                except Exception as exc:
                    print(f"constraints: READ_ERROR {exc}", file=sys.stderr)
                for i in range(args.burst):
                    try:
                        b = snapshot(client, responses)
                        print(
                            f"{datetime.now().isoformat(timespec='milliseconds')} "
                            f"burst {i+1:02d}: {fmt(b)}"
                        )
                    except Exception as exc:
                        print(f"burst {i+1:02d}: READ_ERROR {exc}", file=sys.stderr)
                    time.sleep(0.1)
                print("=== END CAPTURE ===")
                print()

                if not args.keep_running:
                    return 0

            elapsed = time.monotonic() - started
            if elapsed < args.interval:
                time.sleep(args.interval - elapsed)

    except KeyboardInterrupt:
        return 130
    finally:
        client.loop_stop()
        client.disconnect()


if __name__ == "__main__":
    raise SystemExit(main())
