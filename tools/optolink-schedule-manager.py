#!/opt/optolink/venv/bin/python
"""
Strict, readback-verified schedule writer for the local WB2A / VDensHO1.

Home Assistant never writes schedule blocks directly to openv/cmnd. Instead it
publishes a human-readable daily schedule to one of the guarded topics below:

  <mqtt_base>/schedule/set/heating/<weekday>
  <mqtt_base>/schedule/set/dhw/<weekday>
  <mqtt_base>/schedule/set/circulation/<weekday>

Accepted examples:

  05:00-20:00
  05:00-08:00,16:00-22:00
  05:00-08:00,10:00-12:00,14:00-16:00,18:00-24:00
  none

The manager validates the complete daily schedule, writes all eight bytes,
performs a byte-exact readback, and restores the original block on a mismatch.

This helper is intentionally appliance-specific. The allowed address set is
limited to the 21 hardware-verified WB2A schedule blocks.
"""

import json
import queue
import re
import sys
import threading
import time
from datetime import datetime, timezone

APP_DIR = "/opt/optolink"
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from c_settings_adapter import settings  # type: ignore
from homeassistant_publish import connect_mqtt  # type: ignore


PROGRAMS = {
    "heating": {
        "label": "Heizung M1",
        "base": 0x2000,
        "dp_prefix": "heizkreis_m1_zeitprogramm_",
    },
    "dhw": {
        "label": "Warmwasser",
        "base": 0x2100,
        "dp_prefix": "warmwasser_zeitprogramm_",
    },
    "circulation": {
        "label": "Zirkulation",
        "base": 0x2200,
        "dp_prefix": "zirkulation_zeitprogramm_",
    },
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

REQUEST_TIMEOUT = 5.0
READBACK_DELAYS = (0.20, 0.60, 1.20)


def log(message):
    print(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {message}", flush=True)


def utc_now():
    return datetime.now(tz=timezone.utc).isoformat()


def parse_response_addr(response):
    parts = response.split(";")
    if len(parts) < 2:
        return None
    try:
        return int(parts[1], 0)
    except ValueError:
        try:
            return int(parts[1], 16)
        except ValueError:
            return None


def parse_time(value, allow_24=False):
    match = re.fullmatch(r"(\d{1,2}):(\d{2})", value.strip())
    if not match:
        raise ValueError(f"Ungültige Uhrzeit '{value}', erwartet HH:MM")

    hour = int(match.group(1))
    minute = int(match.group(2))

    if allow_24 and hour == 24 and minute == 0:
        return "24:00"

    if not 0 <= hour <= 23:
        raise ValueError(f"Stunde außerhalb 00..23 in '{value}'")
    if minute not in (0, 10, 20, 30, 40, 50):
        raise ValueError(
            f"Minute in '{value}' muss 00,10,20,30,40 oder 50 sein"
        )

    return f"{hour:02d}:{minute:02d}"


def to_minutes(value):
    hour, minute = [int(part) for part in value.split(":", 1)]
    return hour * 60 + minute


def encode_time(value, allow_24=False):
    value = parse_time(value, allow_24=allow_24)
    hour, minute = [int(part) for part in value.split(":", 1)]
    return (hour << 3) + (minute // 10)


def parse_schedule(payload):
    value = str(payload).strip()

    # Safety rule: an empty MQTT/text payload must never be destructive.
    # Clearing a complete boiler day requires the explicit token "none".
    if not value:
        raise ValueError(
            "Leere Eingabe wird aus Sicherheitsgründen abgelehnt; "
            "zum Leeren eines Tages explizit 'none' verwenden"
        )

    if value.lower() == "none":
        return []

    value = value.replace("–", "-").replace("—", "-")
    parts = [part.strip() for part in value.split(",") if part.strip()]

    if len(parts) > 4:
        raise ValueError("Maximal vier Zeitfenster pro Tag sind zulässig")

    intervals = []
    previous_end = -1

    for index, part in enumerate(parts, start=1):
        if part.count("-") != 1:
            raise ValueError(
                f"Zeitfenster {index}: erwartet START-ENDE, erhalten '{part}'"
            )

        start_text, end_text = [item.strip() for item in part.split("-", 1)]
        start = parse_time(start_text, allow_24=False)
        end = parse_time(end_text, allow_24=True)

        start_minutes = to_minutes(start)
        end_minutes = to_minutes(end)

        if start_minutes >= end_minutes:
            raise ValueError(
                f"Zeitfenster {index}: Start {start} muss vor Ende {end} liegen"
            )

        if start_minutes < previous_end:
            raise ValueError(
                f"Zeitfenster {index}: Zeitfenster müssen sortiert sein "
                "und dürfen sich nicht überschneiden"
            )

        intervals.append((start, end))
        previous_end = end_minutes

    return intervals


def encode_schedule(payload):
    intervals = parse_schedule(payload)
    raw = bytearray()

    for start, end in intervals:
        raw.append(encode_time(start, allow_24=False))
        raw.append(encode_time(end, allow_24=True))

    while len(raw) < 8:
        raw.append(0xFF)

    return bytes(raw), intervals


def decode_time_byte(value):
    if value == 0xFF:
        return None

    hour = value >> 3
    minute10 = value & 0x07

    if hour == 24 and minute10 == 0:
        return "24:00"

    if hour > 23 or minute10 > 5:
        raise ValueError(f"Ungültiges Zeitbyte 0x{value:02X}")

    return f"{hour:02d}:{minute10 * 10:02d}"


def decode_block(raw):
    if len(raw) != 8:
        raise ValueError("Zeitprogrammblock muss genau acht Byte enthalten")

    intervals = []
    for slot in range(4):
        start_raw = raw[slot * 2]
        end_raw = raw[slot * 2 + 1]

        if start_raw == 0xFF and end_raw == 0xFF:
            continue
        if start_raw == 0xFF or end_raw == 0xFF:
            raise ValueError(
                f"Teilweise leerer Slot {slot + 1}: "
                f"{start_raw:02X}/{end_raw:02X}"
            )

        start = decode_time_byte(start_raw)
        end = decode_time_byte(end_raw)
        if start == "24:00":
            raise ValueError("24:00 ist als Startzeit ungültig")
        if to_minutes(start) >= to_minutes(end):
            raise ValueError(
                f"Ungültiges Zeitfenster {start}-{end} im Readback"
            )
        intervals.append((start, end))

    return intervals


def canonical_schedule(intervals):
    if not intervals:
        return "none"
    return ",".join(f"{start}-{end}" for start, end in intervals)


def splitter_schedule(intervals):
    values = [f"{start}-{end}" for start, end in intervals]
    while len(values) < 4:
        values.append("na-na")
    return ",".join(values[:4])


EDITOR_OFF = "Aus"


def editor_slots_from_intervals(intervals):
    slots = [[None, None] for _ in range(4)]
    for index, (start, end) in enumerate(intervals[:4]):
        slots[index] = [start, end]
    return slots


def editor_schedule_from_slots(slots):
    parts = []
    for index, (start, end) in enumerate(slots, start=1):
        if start is None and end is None:
            continue
        if start is None or end is None:
            raise ValueError(
                f"Zeitfenster {index} ist unvollständig; Start und Ende wählen"
            )
        parts.append(f"{start}-{end}")

    payload = ",".join(parts) if parts else "none"
    intervals = parse_schedule(payload)
    return canonical_schedule(intervals)


def time_plus_minutes(value, delta, *, allow_24=False):
    minutes = max(0, min(24 * 60, to_minutes(value) + delta))
    if minutes == 24 * 60:
        if allow_24:
            return "24:00"
        minutes = 23 * 60 + 50
    hour, minute = divmod(minutes, 60)
    return f"{hour:02d}:{minute:02d}"


class ScheduleManager:
    def __init__(self):
        if not getattr(settings, "mqtt_broker", None):
            raise RuntimeError("MQTT ist in settings_ini.py deaktiviert")
        if not getattr(settings, "mqtt_listen", None):
            raise RuntimeError("mqtt_listen ist deaktiviert")
        if not getattr(settings, "mqtt_respond", None):
            raise RuntimeError("mqtt_respond ist deaktiviert")
        if not getattr(settings, "mqtt_topic", None):
            raise RuntimeError("mqtt_topic ist nicht konfiguriert")

        self.base_topic = settings.mqtt_topic.rstrip("/")
        self.status_topic = f"{self.base_topic}/schedule_manager/status"

        self.command_map = {}
        for program, cfg in PROGRAMS.items():
            for day_index, (day_name, _short) in enumerate(DAYS):
                topic = (
                    f"{self.base_topic}/schedule/set/"
                    f"{program}/{day_name}"
                )
                self.command_map[topic] = (program, day_index)

        self.client = None
        self.actions = queue.Queue()
        self.response_cond = threading.Condition()
        self.response_seq = 0
        self.responses = []

        self.editor_status_topic = f"{self.base_topic}/schedule/editor/status"
        self.editor_load_topic = f"{self.base_topic}/schedule/editor/load"
        self.editor_apply_topic = f"{self.base_topic}/schedule/editor/apply"
        self.editor_clear_topic = f"{self.base_topic}/schedule/editor/clear"
        self.editor_reload_topic = f"{self.base_topic}/schedule/editor/reload"
        self.editor_slot_topics = {}
        for slot in range(4):
            for side in ("start", "end"):
                topic = (
                    f"{self.base_topic}/schedule/editor/"
                    f"slot{slot + 1}/{side}/set"
                )
                self.editor_slot_topics[topic] = (slot, side)

        self.editor_command_topics = {
            self.editor_load_topic,
            self.editor_apply_topic,
            self.editor_clear_topic,
            self.editor_reload_topic,
            *self.editor_slot_topics.keys(),
        }
        self.editor_target = None
        self.editor_slots = [[None, None] for _ in range(4)]

    def connect(self):
        self.client = connect_mqtt(retries=10, delay=3)
        if self.client is None:
            raise RuntimeError("MQTT-Verbindung fehlgeschlagen")

        self.client.on_message = self.on_message

        # Schedule command topics must never carry retained commands. A stale
        # retained payload would otherwise be replayed when this service
        # reconnects. Clear them before subscribing to the command topics.
        guarded_topics = set(self.command_map) | self.editor_command_topics
        for topic in guarded_topics:
            self.client.publish(topic, "", retain=True).wait_for_publish()

        subscriptions = [(settings.mqtt_respond, 0)]
        subscriptions.extend((topic, 0) for topic in sorted(guarded_topics))
        self.client.subscribe(subscriptions)
        time.sleep(0.5)

        self.publish_status(
            "idle",
            message="Schedule-Manager bereit",
        )
        self.publish_editor_slots()
        self.publish_editor_status(
            "idle",
            message="Programm und Wochentag auswählen",
        )
        log(
            f"listening on {len(self.command_map)} direct and "
            f"{len(self.editor_command_topics)} editor command topics; "
            f"Optolink commands={settings.mqtt_listen}"
        )

    def on_message(self, client, userdata, message):
        payload = message.payload.decode(errors="replace").strip()

        if message.topic == settings.mqtt_respond:
            with self.response_cond:
                self.response_seq += 1
                self.responses.append((self.response_seq, payload))
                if len(self.responses) > 200:
                    self.responses = self.responses[-200:]
                self.response_cond.notify_all()
            return

        retained = bool(getattr(message, "retain", False))

        if message.topic in self.editor_command_topics:
            if retained:
                log(
                    "WARNING: ignoring retained schedule editor command on "
                    f"{message.topic}: {payload!r}"
                )
                return
            if not payload:
                log(
                    "WARNING: ignoring empty schedule editor command on "
                    f"{message.topic}"
                )
                return
            self.actions.put(("editor", message.topic, payload))
            return

        target = self.command_map.get(message.topic)
        if target is not None:
            log(
                "COMMAND "
                f"{target[0]}/{DAYS[target[1]][0]} "
                f"retain={retained} payload={payload!r}"
            )
            if retained:
                log(
                    "WARNING: ignoring retained schedule command on "
                    f"{message.topic}: {payload!r}"
                )
                return
            if not payload:
                log(
                    "WARNING: ignoring empty schedule command on "
                    f"{message.topic}"
                )
                return
            self.actions.put(("schedule", target[0], target[1], payload))

    def publish_editor_slots(self):
        if self.client is None:
            return
        for slot, (start, end) in enumerate(self.editor_slots, start=1):
            self.client.publish(
                f"{self.base_topic}/schedule/editor/slot{slot}/start",
                start or EDITOR_OFF,
                retain=True,
            )
            self.client.publish(
                f"{self.base_topic}/schedule/editor/slot{slot}/end",
                end or EDITOR_OFF,
                retain=True,
            )

    def publish_editor_status(self, state, *, message=None, valid=None):
        if self.client is None:
            return

        payload = {
            "state": state,
            "timestamp": utc_now(),
        }
        if self.editor_target is not None:
            program, day_index = self.editor_target
            payload.update(
                {
                    "program": program,
                    "program_label": PROGRAMS[program]["label"],
                    "day": DAYS[day_index][0],
                    "day_short": DAYS[day_index][1],
                }
            )
            try:
                payload["preview"] = editor_schedule_from_slots(self.editor_slots)
                if valid is None:
                    valid = True
            except Exception as exc:
                payload["preview"] = None
                if message is None:
                    message = str(exc)
                if valid is None:
                    valid = False

        if valid is not None:
            payload["valid"] = bool(valid)
        if message is not None:
            payload["message"] = message

        self.client.publish(
            self.editor_status_topic,
            json.dumps(payload, separators=(",", ":"), ensure_ascii=False),
            retain=True,
        )

    @staticmethod
    def parse_editor_target(payload):
        try:
            data = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise ValueError("Editor-Ziel muss JSON sein") from exc

        program = str(data.get("program", "")).strip()
        day_name = str(data.get("day", "")).strip().lower()
        if program not in PROGRAMS:
            raise ValueError(f"Unbekanntes Programm: {program!r}")

        day_lookup = {name: index for index, (name, _short) in enumerate(DAYS)}
        if day_name not in day_lookup:
            raise ValueError(f"Unbekannter Wochentag: {day_name!r}")

        return program, day_lookup[day_name]

    def load_editor(self, program, day_index, *, state="ready", message=None):
        cfg = PROGRAMS[program]
        addr = cfg["base"] + day_index * 8
        self.editor_target = (program, day_index)
        self.publish_editor_status(
            "loading",
            message="Lese aktuellen Tagesblock vom Controller",
        )
        raw = self.read_block(addr)
        intervals = decode_block(raw)
        self.editor_slots = editor_slots_from_intervals(intervals)
        self.publish_editor_slots()
        self.publish_editor_status(
            state,
            message=message or "Aktueller Controller-Stand geladen",
            valid=True,
        )

    def set_editor_slot(self, slot, side, value):
        if self.editor_target is None:
            raise ValueError("Zuerst ein Programm und einen Wochentag auswählen")

        value = value.strip()
        if value == EDITOR_OFF:
            self.editor_slots[slot] = [None, None]
        elif side == "start":
            start = parse_time(value, allow_24=False)
            self.editor_slots[slot][0] = start
            end = self.editor_slots[slot][1]
            if end is None or to_minutes(end) <= to_minutes(start):
                self.editor_slots[slot][1] = time_plus_minutes(
                    start, 60, allow_24=True
                )
        else:
            end = parse_time(value, allow_24=True)
            if end == "00:00":
                raise ValueError("00:00 ist als Endzeit nicht sinnvoll")
            self.editor_slots[slot][1] = end
            start = self.editor_slots[slot][0]
            if start is None or to_minutes(start) >= to_minutes(end):
                self.editor_slots[slot][0] = time_plus_minutes(
                    end, -60, allow_24=False
                )

        self.publish_editor_slots()
        try:
            preview = editor_schedule_from_slots(self.editor_slots)
            self.publish_editor_status(
                "dirty",
                message=f"Entwurf geändert: {preview}",
                valid=True,
            )
        except Exception as exc:
            self.publish_editor_status(
                "dirty",
                message=str(exc),
                valid=False,
            )

    def clear_editor(self):
        if self.editor_target is None:
            raise ValueError("Zuerst ein Programm und einen Wochentag auswählen")
        self.editor_slots = [[None, None] for _ in range(4)]
        self.publish_editor_slots()
        self.publish_editor_status(
            "dirty",
            message="Entwurf geleert; Controller noch unverändert",
            valid=True,
        )

    def apply_editor(self):
        if self.editor_target is None:
            raise ValueError("Zuerst ein Programm und einen Wochentag auswählen")

        payload = editor_schedule_from_slots(self.editor_slots)
        program, day_index = self.editor_target
        self.publish_editor_status(
            "applying",
            message=f"Übernehme {payload}",
            valid=True,
        )
        if self.apply(program, day_index, payload):
            self.load_editor(
                program,
                day_index,
                state="ok",
                message="Bytegenauer Readback bestätigt",
            )
        else:
            self.publish_editor_status(
                "error",
                message="Übernahme fehlgeschlagen; Schreibstatus prüfen",
                valid=True,
            )

    def handle_editor_action(self, topic, payload):
        try:
            if topic == self.editor_load_topic:
                program, day_index = self.parse_editor_target(payload)
                self.load_editor(program, day_index)
            elif topic == self.editor_reload_topic:
                if self.editor_target is None:
                    raise ValueError(
                        "Zuerst ein Programm und einen Wochentag auswählen"
                    )
                self.load_editor(*self.editor_target)
            elif topic == self.editor_clear_topic:
                self.clear_editor()
            elif topic == self.editor_apply_topic:
                self.apply_editor()
            else:
                slot, side = self.editor_slot_topics[topic]
                self.set_editor_slot(slot, side, payload)
        except Exception as exc:
            log(f"EDITOR ERROR {topic}: {exc}")
            self.publish_editor_status(
                "error",
                message=str(exc),
                valid=False,
            )

    def publish_status(
        self,
        state,
        *,
        program=None,
        day_index=None,
        schedule=None,
        raw=None,
        original=None,
        transport_response=None,
        message=None,
    ):
        payload = {
            "state": state,
            "timestamp": utc_now(),
        }

        if program is not None:
            payload["program"] = program
            payload["program_label"] = PROGRAMS[program]["label"]
        if day_index is not None:
            payload["day"] = DAYS[day_index][0]
            payload["day_short"] = DAYS[day_index][1]
        if schedule is not None:
            payload["schedule"] = schedule
        if raw is not None:
            payload["raw"] = raw
        if original is not None:
            payload["original"] = original
        if transport_response is not None:
            payload["transport_response"] = transport_response
        if message is not None:
            payload["message"] = message

        self.client.publish(
            self.status_topic,
            json.dumps(payload, separators=(",", ":"), ensure_ascii=False),
            retain=True,
        )

    def request(self, command, expected_addr, timeout=REQUEST_TIMEOUT):
        with self.response_cond:
            start_seq = self.response_seq

        log(f"TX {command}")
        self.client.publish(settings.mqtt_listen, command).wait_for_publish()
        deadline = time.monotonic() + timeout

        with self.response_cond:
            while True:
                for seq, response in self.responses:
                    if seq <= start_seq:
                        continue
                    if parse_response_addr(response) == expected_addr:
                        log(f"RX {response}")
                        return response

                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError(
                        f"Timeout für 0x{expected_addr:04X} nach {command}"
                    )
                self.response_cond.wait(timeout=remaining)

    @staticmethod
    def response_value(response, require_success=True):
        parts = response.split(";", 2)
        if len(parts) < 3:
            raise RuntimeError(f"Ungültige Optolink-Antwort: {response}")

        if require_success and parts[0] != "1":
            raise RuntimeError(f"Optolink-Lesezugriff fehlgeschlagen: {response}")

        return parts[2].strip()

    def read_block(self, addr):
        response = self.request(
            f"r;0x{addr:04X};8;raw;False",
            expected_addr=addr,
        )
        value = self.response_value(response, require_success=True)
        if not re.fullmatch(r"[0-9A-Fa-f]{16}", value):
            raise RuntimeError(
                f"Unerwarteter 8-Byte-Readback für 0x{addr:04X}: {value!r}"
            )
        raw = bytes.fromhex(value)
        decode_block(raw)
        return raw

    def write_block(self, addr, raw):
        command = f"wraw;0x{addr:04X};{raw.hex().upper()}"
        try:
            return self.request(command, expected_addr=addr)
        except TimeoutError as exc:
            # For the verified VS1/KW path an eight-byte controller write can
            # persist even if the splitter times out waiting for wrlen response
            # bytes. The subsequent byte-exact readback is authoritative.
            log(f"WARNING: write transport timeout: {exc}")
            return None

    def readback_target(self, addr, target):
        last = None
        for delay in READBACK_DELAYS:
            time.sleep(delay)
            last = self.read_block(addr)
            if last == target:
                return last
        return last

    def publish_datapoint_state(self, program, day_index, intervals):
        cfg = PROGRAMS[program]
        day_name = DAYS[day_index][0]
        topic = f"{self.base_topic}/{cfg['dp_prefix']}{day_name}"
        value = splitter_schedule(intervals)
        self.client.publish(topic, value, retain=False)
        log(f"published verified state {topic}={value}")

    def apply(self, program, day_index, payload):
        cfg = PROGRAMS[program]
        day_name, short = DAYS[day_index]
        addr = cfg["base"] + day_index * 8

        try:
            target, intervals = encode_schedule(payload)
            canonical = canonical_schedule(intervals)
        except Exception as exc:
            message = str(exc)
            log(
                f"REJECT {cfg['label']} {short}: "
                f"{payload!r}: {message}"
            )
            self.publish_status(
                "error",
                program=program,
                day_index=day_index,
                schedule=payload,
                message=f"Validierung: {message}",
            )
            return False

        self.publish_status(
            "writing",
            program=program,
            day_index=day_index,
            schedule=canonical,
            raw=target.hex().upper(),
            message="Lese Ausgangsblock",
        )

        original = None
        transport_response = None

        try:
            original = self.read_block(addr)
            original_intervals = decode_block(original)

            if original == target:
                self.publish_datapoint_state(program, day_index, intervals)
                self.publish_status(
                    "ok",
                    program=program,
                    day_index=day_index,
                    schedule=canonical,
                    raw=target.hex().upper(),
                    original=original.hex().upper(),
                    message="Unverändert; Readback stimmt bereits überein",
                )
                return True

            self.publish_status(
                "writing",
                program=program,
                day_index=day_index,
                schedule=canonical,
                raw=target.hex().upper(),
                original=original.hex().upper(),
                message="Schreibe vollständigen 8-Byte-Tagesblock",
            )

            transport_response = self.write_block(addr, target)
            readback = self.readback_target(addr, target)

            if readback != target:
                observed = (
                    readback.hex().upper() if readback is not None else "NONE"
                )
                log(
                    f"ERROR readback mismatch 0x{addr:04X}: "
                    f"expected={target.hex().upper()} observed={observed}; "
                    "restoring original"
                )

                restore_transport = self.write_block(addr, original)
                restored = self.readback_target(addr, original)
                if restored != original:
                    restored_value = (
                        restored.hex().upper()
                        if restored is not None
                        else "NONE"
                    )
                    raise RuntimeError(
                        "Readback stimmt nicht und Original konnte nicht "
                        "bestätigt restauriert werden: "
                        f"readback={observed}, restore={restored_value}, "
                        f"restore_transport={restore_transport!r}"
                    )

                self.publish_datapoint_state(
                    program, day_index, original_intervals
                )
                raise RuntimeError(
                    "Readback stimmte nicht mit dem Zielblock überein; "
                    "Original wurde bytegenau restauriert"
                )

            self.publish_datapoint_state(program, day_index, intervals)
            self.publish_status(
                "ok",
                program=program,
                day_index=day_index,
                schedule=canonical,
                raw=target.hex().upper(),
                original=original.hex().upper(),
                transport_response=transport_response,
                message="Bytegenauer Readback bestätigt",
            )
            log(
                f"PASS {cfg['label']} {day_name}: "
                f"{target.hex().upper()} {canonical}"
            )
            return True

        except Exception as exc:
            log(f"ERROR {cfg['label']} {short}: {exc}")
            self.publish_status(
                "error",
                program=program,
                day_index=day_index,
                schedule=canonical,
                raw=target.hex().upper(),
                original=(
                    original.hex().upper()
                    if original is not None
                    else None
                ),
                transport_response=transport_response,
                message=str(exc),
            )
            return False

    def run(self):
        self.connect()
        try:
            while True:
                action = self.actions.get()
                if action[0] == "schedule":
                    _kind, program, day_index, payload = action
                    self.apply(program, day_index, payload)
                elif action[0] == "editor":
                    _kind, topic, payload = action
                    self.handle_editor_action(topic, payload)
        finally:
            if self.client is not None:
                self.client.loop_stop()
                self.client.disconnect()


def self_test():
    sample = parse_schedule(
        "05:00-08:00,10:00-12:00,14:00-16:00,18:00-24:00"
    )
    slots = editor_slots_from_intervals(sample)
    assert editor_schedule_from_slots(slots) == (
        "05:00-08:00,10:00-12:00,14:00-16:00,18:00-24:00"
    )
    slots[1] = [None, None]
    assert editor_schedule_from_slots(slots) == (
        "05:00-08:00,14:00-16:00,18:00-24:00"
    )
    assert time_plus_minutes("23:30", 60, allow_24=True) == "24:00"
    assert time_plus_minutes("00:30", -60) == "00:00"
    assert editor_schedule_from_slots([[None, None] for _ in range(4)]) == "none"
    print("schedule editor self-test OK")


def main():
    if sys.argv[1:] == ["--self-test"]:
        self_test()
        return
    ScheduleManager().run()


if __name__ == "__main__":
    main()
