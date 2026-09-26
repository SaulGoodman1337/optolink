#!/opt/optolink/venv/bin/python
"""Read-only reproduction of the useful historical VitoTest protocol surface.

Frame generation is offline. Live execution is deliberately limited to the
already hardware-verified VDensHO1/20C2 Virtual_READ identity path.
"""

import argparse
import re
import sys
import time

APP_DIR = "/opt/optolink"
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

READ_ONLY = {"F7", "6B", "P300_01", "P300_41", "P300_43", "GWG_C7"}
WRITE_OPCODES = {0xF4, 0x68, 0x78, 0xC4, 0xC8, 0xC3, 0xAD, 0x9D, 0x6D}


def parse_int(value: str) -> int:
    return int(value, 0)


def fmt(frame: bytes) -> str:
    return frame.hex(" ").upper()


def kw_virtual_read(address: int, length: int, *, stx: bool = True) -> bytes:
    if not 0 <= address <= 0xFFFF or not 1 <= length <= 0xFF:
        raise ValueError("KW address/length out of range")
    body = bytes((0xF7, address >> 8, address & 0xFF, length))
    return (b"\x01" + body) if stx else body

def p300_checksum(frame_without_crc: bytes) -> int:
    if not frame_without_crc or frame_without_crc[0] != 0x41:
        raise ValueError("P300 frame must begin with 0x41")
    return sum(frame_without_crc[1:]) & 0xFF


def p300_read(function: int, address: int, length: int) -> bytes:
    if function not in (0x01, 0x41, 0x43):
        raise ValueError("P300 function is not in the read-only allowlist")
    if not 0 <= address <= 0xFFFF or not 1 <= length <= 0xFF:
        raise ValueError("P300 address/length out of range")
    body = bytes((0x41, 0x05, 0x00, function,
                  address >> 8, address & 0xFF, length))
    return body + bytes((p300_checksum(body),))


def p300_virtual_read(address: int, length: int) -> bytes:
    return p300_read(0x01, address, length)


def gfa_read(address: int, length: int = 1, *, stx: bool = True) -> bytes:
    if not 0 <= address <= 0xFFFF or length != 1:
        raise ValueError("GFA read requires a 16-bit address and length 1")
    body = bytes((0x6B, address >> 8, address & 0xFF, length))
    return (b"\x01" + body) if stx else body


def gwg_c7_read(address: int, length: int) -> bytes:
    if not 0 <= address <= 0xFF or not 1 <= length <= 0xFF:
        raise ValueError("GWG C7 address/length out of range")
    return bytes((0x01, 0xC7, address, length, 0x04))


def assert_read_only(frame: bytes) -> None:
    if any(op in frame for op in WRITE_OPCODES):
        raise ValueError("generated frame contains a known write opcode")


def self_test() -> None:
    cases = {
        "KW 00F8/2": (kw_virtual_read(0x00F8, 2), "01 F7 00 F8 02"),
        "P300 00F8/2": (p300_virtual_read(0x00F8, 2),
                         "41 05 00 01 00 F8 02 00"),
        "P300 KMBUS RAM 00F8/2": (p300_read(0x41, 0x00F8, 2),
                                  "41 05 00 41 00 F8 02 40"),
        "P300 KMBUS EEPROM 00F8/1": (p300_read(0x43, 0x00F8, 1),
                                     "41 05 00 43 00 F8 01 41"),
        "GFA P80": (gfa_read(0x4050), "01 6B 40 50 01"),
        "GWG C7 F8/4": (gwg_c7_read(0xF8, 4), "01 C7 F8 04 04"),
    }
    for name, (frame, expected) in cases.items():
        assert fmt(frame) == expected, (name, fmt(frame), expected)
        assert_read_only(frame)
        print(f"PASS {name}: {fmt(frame)}")

def live_identity(timeout: float) -> int:
    # Use the production splitters normal structured read path. In permanent
    # VS1 mode this maps to the already verified F7 00F8/2 read.
    from c_settings_adapter import settings  # type: ignore
    from homeassistant_publish import connect_mqtt  # type: ignore

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
    command = "r;0x00F8;2;raw;False"
    print(f"TX structured -> {command}")
    print(f"Equivalent VS1 frame -> {fmt(kw_virtual_read(0x00F8, 2))}")
    client.publish(settings.mqtt_listen, command).wait_for_publish()

    deadline = time.time() + timeout
    try:
        while time.time() < deadline:
            while responses:
                response = responses.pop(0)
                print(f"RX <- {response}")
                parts = response.split(";")
                if len(parts) >= 3:
                    try:
                        addr = int(parts[1], 0)
                    except ValueError:
                        continue
                    if addr == 0x00F8:
                        data = re.sub(r"\s+", "", parts[2]).lower()
                        if data == "20c2":
                            print("PASS live identity: VDensHO1 / 20C2")
                            return 0
                        raise SystemExit(f"unexpected identity: {data}")
            time.sleep(0.05)
        raise SystemExit("timeout waiting for 00F8 response")
    finally:
        client.loop_stop()
        client.disconnect()


def live_gfa_p80(timeout: float) -> int:
    from c_settings_adapter import settings  # type: ignore
    from homeassistant_publish import connect_mqtt  # type: ignore

    if not getattr(settings, "mqtt_listen", None) or not getattr(settings, "mqtt_respond", None):
        raise SystemExit("MQTT command/response topics are not configured")

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

    command = "gfaread;0x4050;1;raw;False"
    print(f"TX structured -> {command}")
    print(f"Equivalent VS1 frame -> {fmt(gfa_read(0x4050))}")
    client.publish(settings.mqtt_listen, command).wait_for_publish()

    deadline = time.time() + timeout
    try:
        while time.time() < deadline:
            while responses:
                response = responses.pop(0)
                print(f"RX <- {response}")
                parts = response.split(";")
                if len(parts) >= 3 and parts[1].lower() in ("0x4050", "16464"):
                    data = re.sub(r"\s+", "", parts[2]).lower()
                    if data == "20":
                        print("PASS live GFA P80: GFA variant 0x20")
                        return 0
                    raise SystemExit(f"unexpected P80 value: {data}")
            time.sleep(0.05)
        raise SystemExit("timeout waiting for GFA P80 response")
    finally:
        client.loop_stop()
        client.disconnect()


def main() -> int:
    p = argparse.ArgumentParser(description="Read-only VitoTest protocol helper")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("self-test")

    for name in ("kw-read", "p300-read", "gfa-read"):
        q = sub.add_parser(name)
        q.add_argument("address", type=parse_int)
        q.add_argument("length", type=parse_int)

    q = sub.add_parser("p300-fc-read")
    q.add_argument("function", type=parse_int, choices=(0x01, 0x41, 0x43))
    q.add_argument("address", type=parse_int)
    q.add_argument("length", type=parse_int)

    q = sub.add_parser("gwg-c7")
    q.add_argument("address", type=parse_int)
    q.add_argument("length", type=parse_int)
    q.epilog = "Frame generation only; this command never transmits."

    q = sub.add_parser("live-ident")
    q.add_argument("--timeout", type=float, default=4.0)

    q = sub.add_parser("live-gfa-p80")
    q.add_argument("--timeout", type=float, default=4.0)

    args = p.parse_args()
    if args.cmd == "self-test":
        self_test()
        return 0
    if args.cmd == "kw-read":
        frame = kw_virtual_read(args.address, args.length)
    elif args.cmd == "p300-read":
        frame = p300_virtual_read(args.address, args.length)
    elif args.cmd == "p300-fc-read":
        frame = p300_read(args.function, args.address, args.length)
    elif args.cmd == "gfa-read":
        frame = gfa_read(args.address, args.length)
    elif args.cmd == "gwg-c7":
        frame = gwg_c7_read(args.address, args.length)
    elif args.cmd == "live-ident":
        return live_identity(args.timeout)
    elif args.cmd == "live-gfa-p80":
        return live_gfa_p80(args.timeout)
    else:
        raise AssertionError(args.cmd)

    assert_read_only(frame)
    print(fmt(frame))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
