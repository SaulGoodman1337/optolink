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
    a3c = request(client, responses, "0x0A3C", 1)[0]
    p7660 = request(client, responses, "0x7660", 2)
    p7663 = request(client, responses, "0x7663", 2)
    ww = request(client, responses, "0x650A", 1)[0]
    uv = request(client, responses, "0x0A10", 1)[0]
    return {
        "a3c": a3c,
        "out7660": p7660[0],
        "speed7660": p7660[1],
        "out7663": p7663[0],
        "speed7663": p7663[1],
        "ww": ww,
        "uv": uv,
    }


def fmt(s):
    relation = (
        "A3C=7660"
        if s["a3c"] == s["speed7660"]
        else "A3C!=7660"
    )
    return (
        f"A3C={s['a3c']:3d}%  "
        f"7660={s['out7660']:02X}/{s['speed7660']:3d}%  "
        f"7663={s['out7663']:02X}/{s['speed7663']:3d}%  "
        f"WW=0x{s['ww']:02X}  UV=0x{s['uv']:02X}  {relation}"
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

    print("WB2A pump divergence watcher")
    print("============================")
    print("Reads only: 0A3C, 7660, 7663, 650A, 0A10")
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

            key = tuple(s.values())
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
