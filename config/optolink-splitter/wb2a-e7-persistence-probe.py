#!/opt/optolink/venv/bin/python
"""Controlled WB2A E7 persistence/status probe.

Purpose:
- observe K8B EEPROM status (0x778B) and K8E I2C EEPROM error flag (0x778E)
  immediately around a single E7 coding change;
- restore the original E7 value automatically.

Safety:
- aborts if burner flame is present;
- aborts if DHW is active;
- changes E7 by only one percentage point;
- always attempts to restore the original value in finally.
"""

import argparse
import signal
import sys
import time

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


def request(client, responses, command, timeout=3.0):
    responses.clear()
    client.publish(settings.mqtt_listen, command).wait_for_publish()
    deadline = time.monotonic() + timeout
    expected_addr = int(command.split(";")[1], 0)

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
            if addr == expected_addr:
                return response
        time.sleep(0.005)
    raise TimeoutError(command)


def read_raw(client, responses, addr, length=1):
    response = request(client, responses, f"r;{addr};{length};raw;False")
    parts = response.split(";")
    if parts[0] != "1":
        raise RuntimeError(f"{addr}: controller returned {response}")
    return bytes.fromhex(parts[2]), response


def write_value(client, responses, addr, value):
    response = request(client, responses, f"w;{addr};1;{value}")
    parts = response.split(";")
    if parts[0] != "1":
        raise RuntimeError(f"{addr}: write failed: {response}")
    return response


def snapshot(client, responses, label):
    e7, _ = read_raw(client, responses, "0x27E7")
    eeprom_status, _ = read_raw(client, responses, "0x778B")
    eeprom_error, _ = read_raw(client, responses, "0x778E")
    print(
        f"{label:<12} E7={e7[0]:3d}%  "
        f"778B=0x{eeprom_status[0]:02X}  778E=0x{eeprom_error[0]:02X}"
    )
    return e7[0], eeprom_status[0], eeprom_error[0]


def main():
    parser = argparse.ArgumentParser(
        description="Probe WB2A EEPROM-related status around one minimal E7 write"
    )
    parser.add_argument(
        "--samples",
        type=int,
        default=20,
        help="number of immediate 778B/778E samples after each write (default: 20)",
    )
    parser.add_argument(
        "--run",
        action="store_true",
        help="required acknowledgement that a temporary E7 write may be performed",
    )
    args = parser.parse_args()

    if not args.run:
        raise SystemExit("Refusing to write without --run")

    client, responses = connect()
    original = None
    restored = False

    def _signal_handler(signum, frame):
        raise KeyboardInterrupt

    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)

    try:
        flame_block, _ = read_raw(client, responses, "0x55D3", 11)
        ww, _ = read_raw(client, responses, "0x650A", 1)

        flame = bool(flame_block[5] & 0x20)
        if flame:
            raise SystemExit("ABORT: burner flame is ON")
        if ww[0] != 0:
            raise SystemExit(f"ABORT: DHW status is 0x{ww[0]:02X}, expected 0x00")

        original, b0, e0 = snapshot(client, responses, "BASELINE")
        if not 0 <= original <= 100:
            raise SystemExit(f"ABORT: implausible E7 value {original}")

        probe = original + 1 if original < 100 else original - 1
        print(f"Temporary E7 probe value: {original} -> {probe} -> {original}")

        t0 = time.monotonic()
        write_value(client, responses, "0x27E7", probe)
        print(f"+{time.monotonic()-t0:8.4f}s WRITE E7={probe}")

        seen_b = {b0}
        seen_e = {e0}
        for i in range(args.samples):
            b, _ = read_raw(client, responses, "0x778B")
            e, _ = read_raw(client, responses, "0x778E")
            seen_b.add(b[0])
            seen_e.add(e[0])
            print(
                f"+{time.monotonic()-t0:8.4f}s "
                f"sample {i+1:02d}: 778B=0x{b[0]:02X} 778E=0x{e[0]:02X}"
            )

        readback, _ = read_raw(client, responses, "0x27E7")
        print(f"+{time.monotonic()-t0:8.4f}s E7 readback={readback[0]}%")

        print("Restoring original E7...")
        write_value(client, responses, "0x27E7", original)
        restored = True

        for i in range(args.samples):
            b, _ = read_raw(client, responses, "0x778B")
            e, _ = read_raw(client, responses, "0x778E")
            seen_b.add(b[0])
            seen_e.add(e[0])
            print(
                f"+{time.monotonic()-t0:8.4f}s "
                f"restore {i+1:02d}: 778B=0x{b[0]:02X} 778E=0x{e[0]:02X}"
            )

        final, _, _ = snapshot(client, responses, "FINAL")
        if final != original:
            raise RuntimeError(
                f"RESTORE VERIFY FAILED: E7 is {final}, expected {original}"
            )

        print(f"Observed 778B values: {', '.join(f'0x{x:02X}' for x in sorted(seen_b))}")
        print(f"Observed 778E values: {', '.join(f'0x{x:02X}' for x in sorted(seen_e))}")

    finally:
        if original is not None and not restored:
            try:
                print(f"Emergency restore attempt: E7 -> {original}")
                write_value(client, responses, "0x27E7", original)
                check, _ = read_raw(client, responses, "0x27E7")
                print(f"Emergency restore readback: E7={check[0]}%")
            except Exception as exc:
                print(f"WARNING: emergency restore failed: {exc}", file=sys.stderr)

        client.loop_stop()
        client.disconnect()


if __name__ == "__main__":
    main()
