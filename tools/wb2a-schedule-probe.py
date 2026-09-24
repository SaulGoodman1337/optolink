#!/opt/optolink/venv/bin/python
"""
Guarded WB2A / VDensHO1 schedule-block inspection and write probe.

This tool is intentionally narrow:
- only the verified daily schedule blocks at 0x2000..0x2230;
- strict 10-minute schedule validation;
- no arbitrary address writes;
- probe writes always attempt to restore the exact original 8-byte block.

It talks to the running optolink-splitter through its configured MQTT
command/response topics, so bus access stays serialized by the splitter.
"""

import argparse
import datetime as dt
import re
import sys
import time

APP_DIR = "/opt/optolink"
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from c_settings_adapter import settings  # type: ignore
from homeassistant_publish import connect_mqtt  # type: ignore


PROGRAMS = {
    "heating": ("Heizung M1", 0x2000),
    "dhw": ("Warmwasser", 0x2100),
    "circulation": ("Zirkulation", 0x2200),
}

PROGRAM_ALIASES = {
    "heating": "heating",
    "heizung": "heating",
    "m1": "heating",
    "dhw": "dhw",
    "warmwasser": "dhw",
    "ww": "dhw",
    "circulation": "circulation",
    "zirkulation": "circulation",
    "zirku": "circulation",
}

DAYS = [
    ("montag", "Mo"),
    ("dienstag", "Di"),
    ("mittwoch", "Mi"),
    ("donnerstag", "Do"),
    ("freitag", "Fr"),
    ("samstag", "Sa"),
    ("sonntag", "So"),
]

DAY_ALIASES = {
    "mo": 0, "mon": 0, "monday": 0, "montag": 0,
    "di": 1, "tue": 1, "tuesday": 1, "dienstag": 1,
    "mi": 2, "wed": 2, "wednesday": 2, "mittwoch": 2,
    "do": 3, "thu": 3, "thursday": 3, "donnerstag": 3,
    "fr": 4, "fri": 4, "friday": 4, "freitag": 4,
    "sa": 5, "sat": 5, "saturday": 5, "samstag": 5,
    "so": 6, "sun": 6, "sunday": 6, "sonntag": 6,
}

CONFIRM_PHRASE = "WRITE_AND_RESTORE"


def parse_num(value):
    s = str(value).strip()
    if s.lower().startswith("0x"):
        return int(s, 16)
    try:
        return int(s, 10)
    except ValueError:
        return int(s, 16)


def normalize_program(value):
    key = str(value).strip().lower()
    if key not in PROGRAM_ALIASES:
        raise argparse.ArgumentTypeError(
            "program must be heating/heizung, dhw/warmwasser or circulation/zirkulation"
        )
    return PROGRAM_ALIASES[key]


def normalize_day(value):
    key = str(value).strip().lower()
    if key not in DAY_ALIASES:
        raise argparse.ArgumentTypeError("unknown weekday")
    return DAY_ALIASES[key]


def address_for(program, day_index):
    return PROGRAMS[program][1] + day_index * 8


def parse_hex_block(value):
    s = str(value).strip().replace("0x", "").replace("0X", "")
    s = re.sub(r"[\s:_-]", "", s)
    if not re.fullmatch(r"[0-9A-Fa-f]{16}", s):
        raise ValueError("schedule block must be exactly 8 bytes / 16 hex characters")
    return bytes.fromhex(s)


def decode_time_byte(value):
    if value == 0xFF:
        return None

    hour = value >> 3
    minute10 = value & 0x07

    if hour == 24 and minute10 == 0:
        return "24:00"

    if hour > 23 or minute10 > 5:
        raise ValueError(f"invalid encoded time byte 0x{value:02X}")

    return f"{hour:02d}:{minute10 * 10:02d}"


def time_to_minutes(value):
    hour, minute = [int(x) for x in value.split(":", 1)]
    return hour * 60 + minute


def decode_block(raw):
    if len(raw) != 8:
        raise ValueError("schedule block must be exactly 8 bytes")

    intervals = []
    warnings = []

    for slot in range(4):
        start_raw = raw[slot * 2]
        end_raw = raw[slot * 2 + 1]

        if start_raw == 0xFF and end_raw == 0xFF:
            continue

        if start_raw == 0xFF or end_raw == 0xFF:
            warnings.append(
                f"slot {slot + 1}: partial unused pair "
                f"{start_raw:02X}/{end_raw:02X}"
            )
            continue

        try:
            start = decode_time_byte(start_raw)
            end = decode_time_byte(end_raw)
        except ValueError as exc:
            warnings.append(f"slot {slot + 1}: {exc}")
            continue

        if start == "24:00":
            warnings.append(f"slot {slot + 1}: 24:00 is not valid as a start time")
            continue

        if time_to_minutes(start) >= time_to_minutes(end):
            warnings.append(
                f"slot {slot + 1}: start {start} is not before end {end}"
            )

        intervals.append((start, end))

    for idx in range(1, len(intervals)):
        prev_end = time_to_minutes(intervals[idx - 1][1])
        cur_start = time_to_minutes(intervals[idx][0])
        if cur_start < prev_end:
            warnings.append(
                f"slot {idx + 1}: overlaps previous interval"
            )

    return intervals, warnings


def format_intervals(intervals):
    if not intervals:
        return "—"
    return ", ".join(f"{start}-{end}" for start, end in intervals)


def parse_time(value, allow_24=False):
    m = re.fullmatch(r"(\d{1,2}):(\d{2})", value.strip())
    if not m:
        raise ValueError(f"invalid time '{value}', expected HH:MM")

    hour = int(m.group(1))
    minute = int(m.group(2))

    if allow_24 and hour == 24 and minute == 0:
        return "24:00"

    if not (0 <= hour <= 23):
        raise ValueError(f"hour out of range in '{value}'")
    if minute not in (0, 10, 20, 30, 40, 50):
        raise ValueError(
            f"minute in '{value}' must be one of 00,10,20,30,40,50"
        )

    return f"{hour:02d}:{minute:02d}"


def encode_time(value, allow_24=False):
    normalized = parse_time(value, allow_24=allow_24)
    hour, minute = [int(x) for x in normalized.split(":", 1)]
    return (hour << 3) + (minute // 10)


def parse_schedule(value):
    s = str(value).strip()
    if s.lower() in ("", "none", "leer", "empty"):
        return []

    s = s.replace("–", "-").replace("—", "-")
    parts = [part.strip() for part in s.split(",") if part.strip()]

    if len(parts) > 4:
        raise ValueError("a daily block supports at most four intervals")

    intervals = []
    previous_end = -1

    for idx, part in enumerate(parts, start=1):
        if part.count("-") != 1:
            raise ValueError(
                f"slot {idx}: expected START-END, got '{part}'"
            )

        start_text, end_text = [x.strip() for x in part.split("-", 1)]
        start = parse_time(start_text, allow_24=False)
        end = parse_time(end_text, allow_24=True)

        start_minutes = time_to_minutes(start)
        end_minutes = time_to_minutes(end)

        if start_minutes >= end_minutes:
            raise ValueError(
                f"slot {idx}: start {start} must be before end {end}"
            )
        if start_minutes < previous_end:
            raise ValueError(
                f"slot {idx}: intervals must be ordered and must not overlap"
            )

        intervals.append((start, end))
        previous_end = end_minutes

    return intervals


def encode_schedule(value):
    intervals = parse_schedule(value)
    data = bytearray()

    for start, end in intervals:
        data.append(encode_time(start, allow_24=False))
        data.append(encode_time(end, allow_24=True))

    while len(data) < 8:
        data.append(0xFF)

    return bytes(data[:8])


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


def response_addr(response):
    parts = response.split(";")
    if len(parts) < 2:
        return None
    try:
        return parse_num(parts[1])
    except Exception:
        return None


def request(client, responses, command, expected_addr, label, timeout=5.0):
    responses.clear()
    print(f"{label:<22} -> {settings.mqtt_listen}: {command}")
    client.publish(settings.mqtt_listen, command).wait_for_publish()

    deadline = time.time() + timeout
    while time.time() < deadline:
        while responses:
            candidate = responses.pop(0)
            if response_addr(candidate) == expected_addr:
                print(f"{label:<22} <- {settings.mqtt_respond}: {candidate}")
                return candidate
        time.sleep(0.05)

    print(f"{label:<22} <- timeout")
    return None


def response_success(response):
    if not response:
        return False
    parts = response.split(";")
    if not parts:
        return False
    try:
        return parse_num(parts[0]) == 1
    except Exception:
        return False


def response_value(response):
    if not response:
        return None
    parts = response.split(";", 2)
    if len(parts) < 3:
        return None
    return parts[2].strip()


def read_raw(client, responses, addr, label="READ"):
    resp = request(
        client,
        responses,
        f"r;0x{addr:04X};8;raw;False",
        addr,
        label,
    )
    if not response_success(resp):
        raise RuntimeError(f"read failed for 0x{addr:04X}: {resp}")

    value = response_value(resp)
    if value is None:
        raise RuntimeError(f"missing read value for 0x{addr:04X}")

    return parse_hex_block(value)


def write_raw(client, responses, addr, raw, label="WRITE"):
    return request(
        client,
        responses,
        f"wraw;0x{addr:04X};{raw.hex().upper()}",
        addr,
        label,
    )


def print_decoded(raw):
    intervals, warnings = decode_block(raw)
    print(f"RAW      {raw.hex().upper()}")
    print(f"DECODED  {format_intervals(intervals)}")
    for warning in warnings:
        print(f"WARNING  {warning}")


def cmd_map(_args):
    for program, (label, base) in PROGRAMS.items():
        print(f"{program:<12} {label}")
        for idx, (day_name, short) in enumerate(DAYS):
            print(f"  {short} {day_name:<11} 0x{base + idx * 8:04X}")


def cmd_encode(args):
    raw = encode_schedule(args.schedule)
    print_decoded(raw)


def cmd_decode(args):
    raw = parse_hex_block(args.hex)
    print_decoded(raw)


def cmd_read(args):
    addr = address_for(args.program, args.day)
    label = PROGRAMS[args.program][0]
    day_name, short = DAYS[args.day]

    client, responses = connect()
    try:
        raw = read_raw(client, responses, addr, f"READ {label} {short}")
        print(f"PROGRAM  {label}")
        print(f"DAY      {day_name}")
        print(f"ADDRESS  0x{addr:04X}")
        print_decoded(raw)
    finally:
        client.loop_stop()
        client.disconnect()


def cmd_snapshot(args):
    programs = list(PROGRAMS)
    if args.program != "all":
        programs = [args.program]

    client, responses = connect()
    try:
        for program in programs:
            label, base = PROGRAMS[program]
            print(f"=== {label} ===")
            for idx, (day_name, short) in enumerate(DAYS):
                addr = base + idx * 8
                raw = read_raw(client, responses, addr, f"{short} 0x{addr:04X}")
                intervals, warnings = decode_block(raw)
                warn = f"  WARN: {'; '.join(warnings)}" if warnings else ""
                print(
                    f"{short} 0x{addr:04X}  {raw.hex().upper()}  "
                    f"{format_intervals(intervals)}{warn}"
                )
            print()
    finally:
        client.loop_stop()
        client.disconnect()


def cmd_probe(args):
    if args.confirm != CONFIRM_PHRASE:
        raise SystemExit(
            f"probe requires --confirm {CONFIRM_PHRASE}"
        )

    current_day = dt.datetime.now().weekday()
    if args.day == current_day and not args.allow_current_day:
        day_name = DAYS[args.day][0]
        raise SystemExit(
            f"refusing to probe the current weekday ({day_name}); "
            "choose another day or add --allow-current-day explicitly"
        )

    target = encode_schedule(args.schedule)
    addr = address_for(args.program, args.day)
    program_label = PROGRAMS[args.program][0]
    day_name, short = DAYS[args.day]

    client, responses = connect()
    original = None
    write_attempted = False
    test_readback = None
    restore_readback = None
    write_response = None
    restore_response = None

    try:
        print("=== ORIGINAL ===")
        original = read_raw(client, responses, addr, "READ ORIGINAL")
        print_decoded(original)

        if target == original:
            raise SystemExit(
                "test schedule equals current block; choose a different schedule "
                "so persistence can be proven"
            )

        print()
        print("=== TEST BLOCK ===")
        print(f"PROGRAM  {program_label}")
        print(f"DAY      {day_name} ({short})")
        print(f"ADDRESS  0x{addr:04X}")
        print_decoded(target)
        print()

        write_attempted = True
        write_response = write_raw(client, responses, addr, target, "WRITE TEST")
        time.sleep(args.settle)

        test_readback = read_raw(client, responses, addr, "READBACK TEST")
        print(f"TEST MATCH  {'YES' if test_readback == target else 'NO'}")

    finally:
        if original is not None and write_attempted:
            print()
            print("=== RESTORE ORIGINAL ===")
            try:
                restore_response = write_raw(
                    client, responses, addr, original, "WRITE RESTORE"
                )
                time.sleep(args.settle)
                restore_readback = read_raw(
                    client, responses, addr, "READBACK RESTORE"
                )
                print(
                    f"RESTORE MATCH  "
                    f"{'YES' if restore_readback == original else 'NO'}"
                )
            except Exception as exc:
                print(f"RESTORE ERROR  {exc}")

        client.loop_stop()
        client.disconnect()

    write_ack = response_success(write_response)
    restore_ack = response_success(restore_response)
    test_match = test_readback == target
    restore_match = (
        original is not None and restore_readback is not None
        and restore_readback == original
    )

    print()
    print("=== RESULT ===")
    print(f"WRITE RESPONSE OK   {'YES' if write_ack else 'NO'}")
    print(f"TEST READBACK OK    {'YES' if test_match else 'NO'}")
    print(f"RESTORE RESPONSE OK {'YES' if restore_ack else 'NO'}")
    print(f"RESTORE READBACK OK {'YES' if restore_match else 'NO'}")

    if not restore_match:
        raise SystemExit(
            "FAIL: original block was not confirmed restored; "
            "check the appliance schedule immediately"
        )

    if not test_match:
        raise SystemExit(
            "FAIL: test block did not persist even though restore succeeded"
        )

    if not write_ack or not restore_ack:
        raise SystemExit(
            "PARTIAL: readback proves data movement but one write response "
            "was not reported as success; inspect splitter logs"
        )

    print("PASS: full 8-byte schedule write/readback/restore verified.")


def build_parser():
    parser = argparse.ArgumentParser(
        description="Guarded WB2A schedule-block inspector/probe"
    )
    sub = parser.add_subparsers(dest="mode", required=True)

    sub.add_parser("map", help="Show the 21 verified schedule addresses")

    enc = sub.add_parser("encode", help="Strictly encode schedule text to 8 bytes")
    enc.add_argument(
        "schedule",
        help="e.g. '05:00-08:00,16:00-22:00'; use 'none' for no intervals",
    )

    dec = sub.add_parser("decode", help="Decode one 8-byte raw schedule block")
    dec.add_argument("hex", help="16 hex characters, e.g. 28A0FFFFFFFFFFFF")

    rd = sub.add_parser("read", help="Read and decode one live daily block")
    rd.add_argument("program", type=normalize_program)
    rd.add_argument("day", type=normalize_day)

    snap = sub.add_parser("snapshot", help="Read all live schedule blocks")
    snap.add_argument(
        "--program",
        default="all",
        type=lambda v: "all" if v.lower() == "all" else normalize_program(v),
        help="all, heating/heizung, dhw/warmwasser, circulation/zirkulation",
    )

    probe = sub.add_parser(
        "probe",
        help="Temporarily write one daily block, verify it, then restore it",
    )
    probe.add_argument("program", type=normalize_program)
    probe.add_argument("day", type=normalize_day)
    probe.add_argument(
        "schedule",
        help="strict schedule text, e.g. '05:00-19:50'",
    )
    probe.add_argument(
        "--confirm",
        required=True,
        help=f"must be exactly {CONFIRM_PHRASE}",
    )
    probe.add_argument("--settle", type=float, default=1.0)
    probe.add_argument(
        "--allow-current-day",
        action="store_true",
        help="allow a probe on today's schedule (normally refused)",
    )

    return parser


def main():
    args = build_parser().parse_args()

    if args.mode == "map":
        cmd_map(args)
    elif args.mode == "encode":
        cmd_encode(args)
    elif args.mode == "decode":
        cmd_decode(args)
    elif args.mode == "read":
        cmd_read(args)
    elif args.mode == "snapshot":
        cmd_snapshot(args)
    elif args.mode == "probe":
        cmd_probe(args)


if __name__ == "__main__":
    main()
