#!/opt/optolink/venv/bin/python
"""Room-temperature feedback for the WB2A heating circuit A1/M1.

Home Assistant publishes the current values of one or more room temperature
sensors to ``<mqtt_topic>/room_control/sensors``. This service combines them
(mean, minimum or maximum), compares the result with a comfort band around
the room target that the boiler's own weekly schedule currently applies and
adjusts the WB2A *external normal room setpoint* ``0x2321``. The boiler then
shifts its flow setpoint along the configured heating curve exactly as if
the room target had been changed.

The base target follows the schedule: the service reads the current
operating phase from ``0x2500`` (byte 1: 0 off, 1 reduced, 2 normal,
3 permanent normal). In the normal phase the base is the normal room target
``0x2306`` (day temperature) and the band is ``base - toleranz_unten`` ..
``base + toleranz_oben``. In the reduced phase (night) the base is
``0x2307``; ``0x2321`` has no effect there (live test 2026-11-24 22:00:
external 23 °C left the reduced target at 18.0 °C and the flow setpoint at
36.5 °C), so the service only monitors and releases any override.

Hardware basis (VDensHO1 / 20C2 / SW 0103, live A/B/A tests 2026-10-11):
external room setpoint 20 / 21 / 22 °C at normal target 21 °C produced
flow setpoints 35.0 / 35.5 / 37.4 °C. Writing ``0x2321 = 0`` returns
control to the regular room target ``0x2306``.

Safety model:

* all controller traffic goes through the running splitter (MQTT
  request/response); this service never opens the serial port;
* only ``0x2321`` (0 or 10..30 °C) and, for the optional night shutdown,
  ``0x2323`` (only 2 -> 1 and back 1 -> 2) are ever written, always with
  readback verification;
* the service only releases a value it wrote itself (ownership is persisted
  in ``/var/lib/optolink-room-control/state.json``); a foreign value is
  left untouched and reported;
* no fresh sensor data, disabled control, active boiler fault or a coded
  real room influence (0x27A0/0x27B0) release the override immediately;
* the correction is limited (``max_korrektur``) and changes at most 1 K per
  step with a minimum interval between steps;
* ``--release`` is run by systemd ``ExecStopPost`` so even a crashed
  service hands control back to the regular room target;
* unreachable boiler or splitter only produce an error status; the service
  keeps running and retries.

Dynamic night shutdown (``nachtabschaltung``, default off): in the reduced
phase the heating circuit is switched from "Heizen + WW" (``0x2323 = 2``) to
"Nur WW" (``1``) while the room is at least ``nacht_ein`` K above the night
target ``0x2307`` and the outside temperature ``0x0800`` is not below
``nacht_min_aussen``. It goes back to 2 as soon as the room has cooled to
night target + ``nacht_aus``, it gets colder outside (1 K hysteresis),
``nacht_vorlauf`` minutes before the next day window of the M1 time program
(``0x2000`` + 8 * weekday, host clock which optolink-clock-sync keeps in
step with the boiler), on missing sensors, fault, disabled control, a
foreign mode change and on service stop (``--release`` in ExecStopPost).
``0x2323`` is a persistent setting, so the number of shutdowns per night is
limited (``nacht_max_schaltungen``, two writes each). The boiler's own frost
protection stays active in "Nur WW".

Pump run-on before the shutdown (``nacht_nachlauf`` minutes, default 10,
0 = switch at once): "Nur WW" stops the heating pump immediately, so the heat
still stored in the boiler would stay there. Before writing ``0x2323 = 1``
the service therefore waits until the flame (``0x55D3`` byte 5) is off and no
DHW charge (``0x650A``) runs, then keeps "Heizen + WW" while the heating pump
runs and asks the pump guard for 100 % (MQTT ``pump_guard/extern/set``,
expiring request). It switches once the run-on time is over or the boiler
(``0x0810``) has cooled to NACHLAUF_END_BELOW_SOLL_K below the effective boiler
setpoint (``0x555A``), i.e. before the burner would restart (start
differential 4 K). If the firmware has stopped the heating pump itself
(``0x7663`` bit 0 off, e.g. the A9 pump idle time after the setpoint drop at
the start of the reduced phase) no run-on is possible and it switches at once.
A burner restart during the run-on starts the run-on again; after
NACHLAUF_FLAME_WAIT_S + ``nacht_nachlauf`` in total it switches in any case.
"""
from __future__ import annotations

import argparse
import ast
import datetime
import json
import math
import os
import queue
import signal
import sys
import threading
import time

APP_DIR = "/opt/optolink"
STATE_DIR = os.environ.get("OPTOLINK_ROOM_CONTROL_STATE_DIR", "/var/lib/optolink-room-control")
STATE_FILE = os.path.join(STATE_DIR, "state.json")

# Hardware-verified controller datapoints. The write surface is 0x2321 only.
ADDR_EXTERNAL_SETPOINT = 0x2321
ADDR_NORMAL_SETPOINT = 0x2306
ADDR_REDUCED_SETPOINT = 0x2307
ADDR_NATIVE_PARTY = 0x2303
ADDR_OPERATING_STATE = 0x2500   # 22 bytes: [1] phase, [12:13] current room target x0.1
OPERATING_STATE_LEN = 22
ADDR_FLOW_SETPOINT = 0x2544
ADDR_CURRENT_FAULT = 0x5738
ADDR_ROOM_INFLUENCE = (0x27A0, 0x27B0)
ADDR_OPERATING_MODE = 0x2323    # 0 off, 1 DHW only, 2 heating + DHW, 3/4 permanent
ADDR_OUTSIDE_TEMP = 0x0800      # 2 bytes signed, 0.1 °C
ADDR_SCHEDULE_M1 = 0x2000       # 8 bytes per weekday, Monday first
ADDR_BURNER_STATE = 0x55D3      # 9 bytes, byte 5 bit 0x20 = flame
ADDR_DHW_CHARGING = 0x650A      # 1 = DHW charge active
ADDR_PUMP_M1_OUTPUT = 0x7663    # 2 bytes, bit 0 = heating circuit pump output on
ADDR_BOILER_TEMP = 0x0810       # 2 bytes signed, 0.1 °C
ADDR_BOILER_SETPOINT = 0x555A   # effective boiler setpoint, 2 bytes signed, 0.1 °C
MODE_DHW_ONLY = 1
MODE_HEATING_DHW = 2

EXTERNAL_MIN_C = 10
EXTERNAL_MAX_C = 30
SENSOR_MIN_C = 5.0
SENSOR_MAX_C = 35.0

CYCLE_SECONDS = 60.0
SENSOR_MAX_AGE_S = 600.0
MIN_STEP_INTERVAL_S = 300.0
MORNING_WINDOW_S = 1800.0  # boost may start within 30 min after the day phase began
HYSTERESIS_K = 0.75   # between correction levels
EXIT_MARGIN_K = 0.2   # how far back inside the band before releasing
INFLUENCE_CHECK_S = 1800.0
SCHEDULE_CACHE_S = 900.0
NIGHT_OUTSIDE_HYSTERESIS_K = 1.0
NIGHT_MIN_WINDOW_MIN = 30   # do not shut down for less than this
NIGHT_RELEASE_AFTER_ERRORS = 3
REQUEST_TIMEOUT = 8.0
NACHLAUF_CYCLE_S = 10.0          # control cycle while the run-on is pending
NACHLAUF_FLAME_WAIT_S = 1200.0   # how long to wait for the burner on top of the run-on
NACHLAUF_END_BELOW_SOLL_K = 2.5  # end before the burner restarts at setpoint - 4 K
NACHLAUF_BOOST_TTL_S = 90        # pump guard boost request, renewed every cycle
NACHLAUF_BOOST_REASON = "Nachlauf Nachtabschaltung"

AGGREGATIONS = ("Mittelwert", "Minimum", "Maximum")

# 0x2500 byte 1 -> phase name
PHASES = {0: "abschalt", 1: "reduziert", 2: "normal", 3: "dauernd_normal"}

# name: (type, minimum, maximum, default)
PARAMETERS = {
    # comfort band relative to the currently scheduled room target
    "toleranz_unten": (float, 0.2, 3.0, 0.5),
    "toleranz_oben": (float, 0.2, 3.0, 0.5),
    # user decides; the hard bound is the external setpoint range 10..30 C
    "verstaerkung": (float, 0.1, 20.0, 1.0),
    "max_korrektur": (int, 1, 20, 2),
    # morning boost: extra K on top of the regular correction after the
    # night setback if the room cooled down too much (0 = off)
    "morgenboost": (int, 0, 20, 0),
    "morgenboost_ausloesung": (float, 0.2, 10.0, 1.0),
    "morgenboost_dauer": (int, 10, 480, 90),
    # dynamic night shutdown (0x2323 -> Nur WW), see module docstring
    "nacht_ein": (float, 0.5, 5.0, 1.5),
    "nacht_aus": (float, 0.0, 4.5, 0.5),
    "nacht_min_aussen": (float, -20.0, 15.0, -5.0),
    "nacht_vorlauf": (int, 0, 240, 30),
    "nacht_max_schaltungen": (int, 1, 10, 3),
    "nacht_nachlauf": (int, 0, 30, 10),
}
NIGHT_MIN_GAP_K = 0.5  # nacht_aus must stay at least this far below nacht_ein

DEFAULT_CONFIG = {
    "enabled": False,
    "nachtabschaltung": False,
    "aggregation": "Mittelwert",
    **{name: spec[3] for name, spec in PARAMETERS.items()},
}


class RoomControlError(RuntimeError):
    pass


def log(message):
    print(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {message}", flush=True)


# ---------------------------------------------------------------------------
# Pure logic (unit tested without MQTT or hardware)
# ---------------------------------------------------------------------------

def parse_sensor_payload(payload, now):
    """Return ``{name: (temperature_c, received_at)}`` for plausible values.

    Accepted: ``{"sensors": {"sensor.x": 21.3, ...}}`` or a flat object
    ``{"sensor.x": 21.3}``. Non-numeric/unavailable values are skipped.
    """
    if isinstance(payload, (bytes, bytearray)):
        payload = payload.decode("utf-8", errors="replace")
    if len(payload) > 8192:
        raise RoomControlError("sensor payload too large")
    try:
        data = json.loads(payload)
    except json.JSONDecodeError as exc:
        # Home Assistant may render a dict as Python literal ('...').
        try:
            data = ast.literal_eval(payload.strip())
        except (ValueError, SyntaxError, MemoryError, RecursionError):
            raise RoomControlError("sensor payload is not JSON") from exc
    if isinstance(data, dict) and isinstance(data.get("sensors"), dict):
        data = data["sensors"]
    if not isinstance(data, dict):
        raise RoomControlError("sensor payload must be an object")
    result = {}
    for name, value in list(data.items())[:32]:
        if not isinstance(name, str) or not name or len(name) > 120:
            continue
        if isinstance(value, bool):
            continue
        try:
            value = float(value)
        except (TypeError, ValueError):
            continue
        if math.isfinite(value) and SENSOR_MIN_C <= value <= SENSOR_MAX_C:
            result[name] = (round(value, 2), now)
    return result


def fresh_values(samples, now, max_age=SENSOR_MAX_AGE_S):
    return {
        name: value
        for name, (value, at) in samples.items()
        if 0 <= now - at <= max_age
    }


def aggregate(values, mode):
    if not values:
        return None
    vals = list(values)
    if mode == "Minimum":
        return min(vals)
    if mode == "Maximum":
        return max(vals)
    return sum(vals) / len(vals)


def validate_config(config):
    cfg = dict(DEFAULT_CONFIG)
    cfg.update({k: v for k, v in (config or {}).items() if k in DEFAULT_CONFIG})
    cfg["enabled"] = bool(cfg["enabled"])
    cfg["nachtabschaltung"] = bool(cfg["nachtabschaltung"])
    if cfg["aggregation"] not in AGGREGATIONS:
        cfg["aggregation"] = DEFAULT_CONFIG["aggregation"]
    for name, (kind, lo, hi, default) in PARAMETERS.items():
        try:
            value = kind(cfg[name])
        except (TypeError, ValueError):
            value = default
        if not (lo <= value <= hi):
            value = default
        cfg[name] = round(value, 2) if kind is float else value
    if cfg["nacht_aus"] > cfg["nacht_ein"] - NIGHT_MIN_GAP_K:
        cfg["nacht_aus"] = round(max(0.0, cfg["nacht_ein"] - NIGHT_MIN_GAP_K), 2)
    return cfg


def decode_schedule_block(raw_hex):
    """M1 time program day block (8 bytes) -> sorted ``[(start_min, end_min)]``.

    Byte = hour << 3 | minute / 10, ``0xFF`` = unused slot, pairs on/off.
    """
    try:
        data = bytes.fromhex(raw_hex.strip())
    except ValueError as exc:
        raise RoomControlError(f"schedule block is not hex: {raw_hex[:40]!r}") from exc
    if len(data) != 8:
        raise RoomControlError(f"schedule block has {len(data)} bytes, expected 8")
    intervals = []
    for i in range(0, 8, 2):
        on, off = data[i], data[i + 1]
        if on == 0xFF or off == 0xFF:
            continue
        start = (on >> 3) * 60 + (on & 7) * 10
        end = (off >> 3) * 60 + (off & 7) * 10
        if (on & 7) > 5 or (off & 7) > 5 or start >= end or end > 1440:
            raise RoomControlError(f"implausible schedule slot {on:#04x}/{off:#04x}")
        intervals.append((start, end))
    return sorted(intervals)


def schedule_position(days, weekday, minute):
    """Where ``minute`` of ``weekday`` (0 = Monday) lies in the time program.

    ``days`` maps weekday -> intervals. Returns ``(in_day, minutes_to_day,
    day_offset)``: ``minutes_to_day`` is the time to the next day window
    start (None if the program has none), ``day_offset`` how many days ahead
    that start lies (identifies the night).
    """
    for start, end in days.get(weekday, ()):
        if start <= minute < end:
            return True, 0, 0
    for offset in range(0, 8):
        for start, _end in days.get((weekday + offset) % 7, ()):
            delta = offset * 1440 + start - minute
            if delta > 0:
                return False, delta, offset
    return False, None, None


def night_decision(*, active, room_c, reduced_c, outside_c, in_day, minutes_to_day,
                   config, switches_used):
    """Should the heating circuit be off ("Nur WW") right now? -> (bool, reason)."""
    if in_day or minutes_to_day is None:
        return False, "Tagphase laut Zeitprogramm" if in_day else "kein Tagfenster im Zeitprogramm"
    if minutes_to_day <= config["nacht_vorlauf"]:
        return False, "Vorlauf vor Tagbeginn"
    if room_c is None or reduced_c is None:
        return False, "keine Raum- oder Solldaten"
    if outside_c is None:
        return False, "keine Außentemperatur"
    if active:
        if room_c <= reduced_c + config["nacht_aus"]:
            return False, "Raum abgekühlt"
        if outside_c < config["nacht_min_aussen"] - NIGHT_OUTSIDE_HYSTERESIS_K:
            return False, "zu kalt draußen"
        return True, "Raum warm genug"
    if switches_used >= config["nacht_max_schaltungen"]:
        return False, "Schaltlimit dieser Nacht erreicht"
    if outside_c < config["nacht_min_aussen"]:
        return False, "zu kalt draußen"
    if minutes_to_day <= config["nacht_vorlauf"] + NIGHT_MIN_WINDOW_MIN:
        return False, "zu kurz bis Tagbeginn"
    if room_c >= reduced_c + config["nacht_ein"]:
        return True, "Raum warm genug"
    return False, "Raum nicht warm genug"


def parse_operating_state(raw_hex):
    """Decode 0x2500 (22 bytes, hex) into ``(phase, current_target_c)``.

    ``phase`` is one of ``PHASES`` (or ``"unbekannt_<n>"``); the current
    target is the room setpoint the boiler is using right now.
    """
    try:
        data = bytes.fromhex(raw_hex.strip())
    except ValueError as exc:
        raise RoomControlError(f"0x2500 is not hex: {raw_hex[:60]!r}") from exc
    if len(data) < 14:
        raise RoomControlError(f"0x2500 too short ({len(data)} bytes)")
    phase = PHASES.get(data[1], f"unbekannt_{data[1]}")
    current = int.from_bytes(data[12:14], "little", signed=True) / 10.0
    return phase, current


def comfort_band(base_c, config):
    return (round(base_c - config["toleranz_unten"], 2),
            round(base_c + config["toleranz_oben"], 2))


def band_correction(room_c, lower_c, upper_c, gain, max_k):
    """Correction in K of the room target; 0 inside the comfort band.

    Below the lower threshold the room target is raised (more flow
    temperature), above the upper threshold it is lowered.
    """
    if room_c < lower_c:
        deviation = lower_c - room_c
    elif room_c > upper_c:
        deviation = upper_c - room_c
    else:
        return 0.0
    return max(-max_k, min(max_k, gain * deviation))


def morning_boost_command(target_c, room_c, config):
    """External setpoint during the morning boost (jumps, no 1 K steps)."""
    lower, upper = comfort_band(target_c, config)
    corr = band_correction(room_c, lower, upper, config["verstaerkung"], config["max_korrektur"])
    regular = max(1, int(math.floor(corr + 0.5))) if corr > 0 else 0
    return max(EXTERNAL_MIN_C, min(EXTERNAL_MAX_C, target_c + regular + config["morgenboost"]))


def next_command(*, target_c, room_c, current_cmd, config, now, last_step_at):
    """Next external setpoint to write (0 = regular room target).

    ``current_cmd`` is the value this service owns (0 if none). Changes are
    limited to 1 K per step and ``MIN_STEP_INTERVAL_S`` between steps. Any
    room temperature outside the band gives at least 1 K; hysteresis between
    levels and an exit margin inside the band avoid toggling.
    """
    lower, upper = comfort_band(target_c, config)
    corr = band_correction(
        room_c,
        lower,
        upper,
        config["verstaerkung"],
        config["max_korrektur"],
    )
    raw = target_c + corr
    effective = current_cmd if current_cmd else target_c
    if corr == 0.0:
        # Back inside the band: keep an active correction until the room is
        # clearly inside (EXIT_MARGIN_K), so it does not toggle at the edge.
        raising = current_cmd and current_cmd > target_c
        lowering = current_cmd and current_cmd < target_c
        if (raising and room_c < lower + EXIT_MARGIN_K) or (lowering and room_c > upper - EXIT_MARGIN_K):
            wanted = effective
        else:
            wanted = target_c
    else:
        # Outside the band always means at least 1 K correction.
        magnitude = max(1, int(math.floor(abs(corr) + 0.5)))
        wanted = target_c + (magnitude if corr > 0 else -magnitude)
        same_side = (effective - target_c) * corr > 0
        if current_cmd and same_side and abs(raw - effective) < HYSTERESIS_K:
            wanted = effective
    wanted = max(EXTERNAL_MIN_C, min(EXTERNAL_MAX_C, wanted))
    if wanted == effective:
        return current_cmd
    if last_step_at is not None and now - last_step_at < MIN_STEP_INTERVAL_S:
        return current_cmd
    step = effective + (1 if wanted > effective else -1)
    return 0 if step == target_c else step


# ---------------------------------------------------------------------------
# State persistence
# ---------------------------------------------------------------------------

def load_state(path=None):
    path = path or STATE_FILE
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        if data.get("version") != 1:
            raise ValueError("unsupported state version")
    except FileNotFoundError:
        data = {"version": 1}
    except Exception as exc:
        log(f"WARNING: cannot read {path}: {exc}; using defaults")
        data = {"version": 1}
    owned = data.get("owned_command", 0)
    if type(owned) is not int or not (owned == 0 or EXTERNAL_MIN_C <= owned <= EXTERNAL_MAX_C):
        owned = 0
    night = data.get("night") if isinstance(data.get("night"), dict) else {}
    switches = night.get("switches", 0)
    return {
        "version": 1,
        "owned_command": owned,
        # True while this service switched 0x2323 from 2 to 1
        "owned_mode": data.get("owned_mode") is True,
        "night": {
            "id": str(night.get("id", ""))[:20],
            "switches": switches if type(switches) is int and 0 <= switches <= 100 else 0,
        },
        "config": validate_config(data.get("config")),
    }


def save_state(state, path=None):
    path = path or STATE_FILE
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(state, handle, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)


# ---------------------------------------------------------------------------
# Controller (hardware access injected as ``io``)
# ---------------------------------------------------------------------------

class RoomController:
    """One control cycle per ``tick``. ``io`` provides read_int/write_int."""

    def __init__(self, io, state, *, save=save_state, clock=time.monotonic,
                 wallclock=None, boost=None):
        self.io = io
        # boost(seconds, reason): ask the pump guard for 100 % (0 ends it)
        self.boost = boost or (lambda _seconds, _reason: None)
        self.nachlauf = None         # pending pump run-on before "Nur WW"
        # (weekday 0=Monday, minute of day, datetime.date) in local time
        self.wallclock = wallclock or _local_wallclock
        self.state = state
        self.save = save
        self.clock = clock
        self.samples = {}
        self.last_step_at = None
        self.next_influence_check = 0.0
        self.influence_coded = False
        self.status = {"state": "start"}
        self.resumed = False
        self.schedule_info = {}
        self.last_phase = None
        self.day_started_at = None   # observed reduced/off -> normal transition
        self.boost_until = None      # morning boost active until (clock)
        self.boost_done = False      # at most one boost per morning
        self.schedule_cache = {}     # weekday -> (read_at, intervals)
        self.night_info = {}
        self.night_handled = False
        self.error_streak = 0
        state.setdefault("owned_mode", False)
        state.setdefault("night", {"id": "", "switches": 0})

    @property
    def config(self):
        return self.state["config"]

    @property
    def owned(self):
        return self.state["owned_command"]

    def set_owned(self, value):
        if value != self.state["owned_command"]:
            self.state["owned_command"] = value
            self.save(self.state)

    def update_samples(self, parsed):
        self.samples.update(parsed)
        # forget sensors that HA no longer reports
        now = self.clock()
        self.samples = {
            k: v for k, v in self.samples.items() if now - v[1] <= SENSOR_MAX_AGE_S * 2
        }

    @property
    def owned_mode(self):
        return self.state["owned_mode"]

    def set_owned_mode(self, value):
        if value != self.state["owned_mode"]:
            self.state["owned_mode"] = value
            self.save(self.state)

    def write_verified(self, value, addr=ADDR_EXTERNAL_SETPOINT):
        self.io.write_int(addr, 1, value)
        last = None
        for delay in (0.3, 0.9, 1.8):
            self.io.sleep(delay)
            last = self.io.read_int(addr, 1)
            if last == value:
                return
        raise RoomControlError(f"0x{addr:04X} readback {last}, expected {value}")

    # -- dynamic night shutdown ------------------------------------------

    def night_release(self, reason):
        """Back to "Heizen + WW" if (and only if) we switched to "Nur WW"."""
        if not self.owned_mode:
            return False
        mode = self.io.read_int(ADDR_OPERATING_MODE, 1)
        if mode != MODE_DHW_ONLY:
            log(f"0x2323={mode} was changed externally; not touching it ({reason})")
            self.set_owned_mode(False)
            return False
        self.write_verified(MODE_HEATING_DHW, ADDR_OPERATING_MODE)
        self.set_owned_mode(False)
        log(f"night shutdown ended ({reason}): 0x2323 1 -> 2")
        return True

    def schedule_now(self, now):
        weekday, minute, date = self.wallclock()
        days = {}
        for offset in range(8):
            wd = (weekday + offset) % 7
            if wd in days:
                continue
            cached = self.schedule_cache.get(wd)
            if cached is None or now - cached[0] > SCHEDULE_CACHE_S:
                raw = self.io.read_bytes(ADDR_SCHEDULE_M1 + 8 * wd, 8)
                cached = (now, decode_schedule_block(raw))
                self.schedule_cache[wd] = cached
            days[wd] = cached[1]
            if any(start > (minute if offset == 0 else -1) for start, _e in days[wd]):
                break
        in_day, minutes, offset = schedule_position(days, weekday, minute)
        # The night is named after the date its day window starts on, so the
        # switch budget does not reset at midnight.
        night_id = (date + datetime.timedelta(days=offset or 0)).isoformat()
        return in_day, minutes, night_id

    def night_step(self, now, room):
        """Run the night shutdown logic during the reduced phase."""
        self.night_handled = True
        cfg = self.config
        info = {"nachtabschaltung": cfg["nachtabschaltung"]}
        mode = self.io.read_int(ADDR_OPERATING_MODE, 1)
        if self.owned_mode and mode != MODE_DHW_ONLY:
            log(f"0x2323={mode} was changed externally during night shutdown; ownership dropped")
            self.set_owned_mode(False)
        if not cfg["nachtabschaltung"]:
            self.night_release("night shutdown disabled")
            self.night_info = {**info, "nacht_grund": "ausgeschaltet"}
            return self.night_info
        if not self.owned_mode and mode != MODE_HEATING_DHW:
            self.night_info = {**info, "nacht_grund": f"Betriebsart {mode} statt Heizen + WW"}
            return self.night_info
        in_day, minutes, night_id = self.schedule_now(now)
        night = self.state["night"]
        if night.get("id") != night_id:
            self.state["night"] = night = {"id": night_id, "switches": 0}
            self.save(self.state)
        outside = self.io.read_scaled(ADDR_OUTSIDE_TEMP, 2, 0.1, True)
        if not -40.0 <= outside <= 50.0:
            outside = None
        reduced = self.schedule_info.get("reduced_target_c")
        if reduced is not None and not 3 <= reduced <= 37:
            reduced = None
        want, reason = night_decision(
            active=self.owned_mode, room_c=room, reduced_c=reduced, outside_c=outside,
            in_day=in_day, minutes_to_day=minutes, config=cfg,
            switches_used=night["switches"])
        if not want or self.owned_mode:
            self.nachlauf_cancel(reason)
        run_on = None
        if want and not self.owned_mode:
            done, run_on = self.nachlauf_step(now)
            if not done:
                reason = run_on
        if want and not self.owned_mode and done:
            self.nachlauf_cancel(run_on or "switch")
            # Treat a begun write as possibly applied (release checks the value).
            self.set_owned_mode(True)
            night["switches"] += 1
            self.save(self.state)
            try:
                self.write_verified(MODE_DHW_ONLY, ADDR_OPERATING_MODE)
            except Exception:
                self.night_release("write failed")
                raise
            log(f"night shutdown started: room {room:.2f} °C >= {reduced} + {cfg['nacht_ein']} K, "
                f"outside {outside} °C, {minutes} min to day: 0x2323 2 -> 1"
                + (f" (run-on: {run_on})" if run_on else ""))
        elif not want and self.owned_mode:
            self.night_release(reason)
        self.night_info = {
            **info,
            "nachtabschaltung_aktiv": self.owned_mode,
            "nacht_grund": reason,
            "nacht_schaltungen": night["switches"],
            "minuten_bis_tag": minutes,
            "aussen_c": outside,
            "nacht_ein_c": None if reduced is None else round(reduced + cfg["nacht_ein"], 2),
            "nacht_aus_c": None if reduced is None else round(reduced + cfg["nacht_aus"], 2),
            "nacht_nachlauf": cfg["nacht_nachlauf"],
            "nachlauf_aktiv": self.nachlauf is not None,
        }
        if self.nachlauf is not None:
            self.night_info.update(self.nachlauf_info(now))
        return self.night_info

    # -- pump run-on before the night shutdown ---------------------------

    def nachlauf_step(self, now):
        """Advance the run-on; -> (switch_now, reason)."""
        minutes = self.config["nacht_nachlauf"]
        if minutes <= 0:
            return True, None
        nl = self.nachlauf
        if nl is None:
            nl = self.nachlauf = {"start": now, "run_since": None, "kessel": None, "soll": None}
            log(f"night shutdown pending: pump run-on first ({minutes} min)")
        if now - nl["start"] >= NACHLAUF_FLAME_WAIT_S + minutes * 60:
            return True, "Nachlauf-Höchstdauer erreicht"
        gfa = bytes.fromhex(self.io.read_bytes(ADDR_BURNER_STATE, 9).strip())
        if len(gfa) < 6:
            raise RoomControlError(f"0x55D3 too short ({len(gfa)} bytes)")
        if gfa[5] & 0x20 or self.io.read_int(ADDR_DHW_CHARGING, 1) == 1:
            if nl["run_since"] is not None:
                log("run-on interrupted: burner/DHW active again")
            nl["run_since"] = None
            nl["phase"] = "warten"
            return False, "Nachlauf: warte auf Brenner aus"
        if not self.io.read_int(ADDR_PUMP_M1_OUTPUT, 2) & 1:
            return True, "Heizkreispumpe aus, kein Nachlauf möglich"
        if nl["run_since"] is None:
            nl["run_since"] = now
            log("run-on started: burner off, heating pump on, pump guard boost requested")
        nl["phase"] = "laeuft"
        self.boost(NACHLAUF_BOOST_TTL_S, NACHLAUF_BOOST_REASON)
        kessel = self.io.read_scaled(ADDR_BOILER_TEMP, 2, 0.1, True)
        soll = self.io.read_scaled(ADDR_BOILER_SETPOINT, 2, 0.1, True)
        nl["kessel"] = kessel if 0 < kessel < 100 else None
        nl["soll"] = soll if 15 <= soll <= 90 else None
        if now - nl["run_since"] >= minutes * 60:
            return True, f"Nachlauf {minutes} min beendet"
        if nl["kessel"] is not None and nl["soll"] is not None \
                and nl["kessel"] <= nl["soll"] - NACHLAUF_END_BELOW_SOLL_K:
            return True, f"Nachlauf beendet, Kessel {nl['kessel']:.1f} °C abgekühlt"
        return False, "Nachlauf läuft"

    def next_delay(self):
        """Seconds until the next control cycle."""
        return NACHLAUF_CYCLE_S if self.nachlauf is not None else CYCLE_SECONDS

    def nachlauf_info(self, now):
        nl = self.nachlauf
        rest = None
        if nl.get("run_since") is not None:
            rest = max(0, round(self.config["nacht_nachlauf"] - (now - nl["run_since"]) / 60, 1))
        return {"nachlauf_phase": nl.get("phase"), "nachlauf_rest_min": rest,
                "nachlauf_kessel_c": nl.get("kessel"), "nachlauf_soll_c": nl.get("soll")}

    def nachlauf_cancel(self, reason):
        if self.nachlauf is None:
            return
        if self.nachlauf.get("run_since") is not None:
            self.boost(0, NACHLAUF_BOOST_REASON)
        log(f"run-on finished ({reason})")
        self.nachlauf = None

    def release(self, reason, also_owned=()):
        """Hand back to the regular room target if (and only if) we own 0x2321."""
        if not self.owned:
            return False
        current = self.io.read_int(ADDR_EXTERNAL_SETPOINT, 1)
        if current not in (0, self.owned, *also_owned):
            log(f"0x2321={current} was changed externally; not touching it ({reason})")
            self.set_owned(0)
            return False
        if current != 0:
            self.write_verified(0)
        log(f"external room setpoint {self.owned} released ({reason})")
        self.set_owned(0)
        self.last_step_at = self.clock()
        return True

    def _status(self, state, **extra):
        self.status = {
            "state": state,
            "enabled": self.config["enabled"],
            "external_setpoint_c": self.owned or None,
            "nachtabschaltung_aktiv": self.owned_mode,
            "nacht_nachlauf": self.config["nacht_nachlauf"],
            **extra,
        }
        # The boiler always works with some room target: the external one we
        # own, else the target its schedule applies. Show it in every state.
        for key, value in self.schedule_info.items():
            self.status.setdefault(key, value)
        base = self.status.get("base_target_c")
        if base is not None:
            self.status.setdefault("effective_target_c", self.owned or base)
        return self.status

    def read_schedule(self):
        """Phase and base target as the boiler's weekly schedule sets them now."""
        phase, current = parse_operating_state(
            self.io.read_bytes(ADDR_OPERATING_STATE, OPERATING_STATE_LEN))
        normal = self.io.read_int(ADDR_NORMAL_SETPOINT, 1)
        reduced = self.io.read_int(ADDR_REDUCED_SETPOINT, 1)
        party = self.io.read_int(ADDR_NATIVE_PARTY, 1)
        if party:
            phase = "party"
        if phase in ("normal", "dauernd_normal"):
            base = normal
        elif phase == "reduziert":
            base = reduced
        else:
            base = current if 3 <= current <= 37 else None
        if base is not None and not 3 <= base <= 37:
            base = None
        info = {
            "phase": phase,
            "normal_target_c": normal,
            "reduced_target_c": reduced,
            "boiler_target_c": current,
            "base_target_c": base,
        }
        if base is not None:
            lower, upper = comfort_band(base, self.config)
            info.update(schwelle_unten_c=lower, schwelle_oben_c=upper)
        self.schedule_info = info
        return phase, base

    def morning_boost(self, now, room, target):
        """External setpoint for an active morning boost, else 0."""
        cfg = self.config
        lower, _upper = comfort_band(target, cfg)
        if self.boost_until is not None:
            if now >= self.boost_until or room >= lower or not cfg["morgenboost"]:
                reason = "time limit" if now >= self.boost_until else (
                    "room reached the band" if room >= lower else "disabled")
                log(f"morning boost ended ({reason}), room {room:.2f} °C")
                self.boost_until = None
                self.last_step_at = now  # regular control steps down from here
                return 0
            return morning_boost_command(target, room, cfg)
        if (cfg["morgenboost"] and not self.boost_done and self.day_started_at is not None
                and now - self.day_started_at <= MORNING_WINDOW_S
                and room < lower - cfg["morgenboost_ausloesung"]):
            self.boost_done = True
            self.boost_until = now + cfg["morgenboost_dauer"] * 60
            log(f"morning boost started: room {room:.2f} °C < {lower - cfg['morgenboost_ausloesung']:.2f} °C")
            return morning_boost_command(target, room, cfg)
        return 0

    def tick(self):
        """One control cycle; the night shutdown is released on every path
        that does not run its logic (day, disabled, fault, no sensors, ...)."""
        self.night_handled = False
        try:
            status = self._tick()
            self.error_streak = 0
        except Exception:
            self.error_streak += 1
            if self.owned_mode and self.error_streak >= NIGHT_RELEASE_AFTER_ERRORS:
                try:
                    self.night_release(f"{self.error_streak} failed cycles")
                except Exception as exc:
                    log(f"WARNING: night shutdown release failed: {exc}")
            raise
        if not self.night_handled:
            self.nachlauf_cancel(f"state {status.get('state')}")
            self.night_info = {}
            if self.owned_mode:
                self.night_release(f"state {status.get('state')}")
                status["nachtabschaltung_aktiv"] = self.owned_mode
        return status

    def _tick(self):
        now = self.clock()
        cfg = self.config
        values = fresh_values(self.samples, now)
        room = aggregate(values.values(), cfg["aggregation"])
        info = {
            "room_c": None if room is None else round(room, 2),
            "sensors": {k: values[k] for k in sorted(values)},
            "sensor_count": len(values),
            "aggregation": cfg["aggregation"],
            "toleranz_unten": cfg["toleranz_unten"],
            "toleranz_oben": cfg["toleranz_oben"],
        }

        current = self.io.read_int(ADDR_EXTERNAL_SETPOINT, 1)
        if not self.resumed:
            self.resumed = True
            if self.owned and current != self.owned:
                log(f"stored ownership {self.owned} does not match 0x2321={current}; dropped")
                self.set_owned(0)
        if current != 0 and current != self.owned:
            return self._status("fremdbelegt", foreign_value_c=current, **info)

        phase, base = self.read_schedule()
        day = phase in ("normal", "dauernd_normal")
        if day and self.last_phase in ("reduziert", "abschalt"):
            self.day_started_at = now
            self.boost_done = False
        if not day:
            self.day_started_at = None
            self.boost_until = None
        self.last_phase = phase

        if not cfg["enabled"]:
            self.release("disabled")
            return self._status("aus", **info)

        if now >= self.next_influence_check:
            coded = [self.io.read_int(a, 1) for a in ADDR_ROOM_INFLUENCE]
            self.influence_coded = any(coded)
            self.next_influence_check = now + INFLUENCE_CHECK_S
        if self.influence_coded:
            self.release("room influence coded")
            return self._status("raumeinfluss_codiert", **info)

        fault = self.io.read_int(ADDR_CURRENT_FAULT, 1)
        if fault:
            self.release(f"boiler fault {fault:#04x}")
            return self._status("stoerung", fault=fault, **info)

        if phase not in ("normal", "dauernd_normal"):
            # 0x2321 only acts on the normal phase: night setback, off mode
            # and native party run on their own target; hand back and watch.
            self.release(f"phase {phase}")
            night_phase = phase == "reduziert" or (phase == "abschalt" and self.owned_mode)
            if night_phase and room is not None:
                night = self.night_step(now, room)
                state = ("nachtabschaltung" if self.owned_mode else
                         "nachlauf" if self.nachlauf is not None else "nachtabsenkung")
                return self._status(state, **night, **info)
            if night_phase:
                return self._status("keine_sensoren", **info)
            state = {"reduziert": "nachtabsenkung", "abschalt": "abschaltbetrieb",
                     "party": "party"}.get(phase, "fehler")
            return self._status(state, **info)

        if room is None:
            self.release("no fresh sensor data")
            return self._status("keine_sensoren", **info)

        if base is None:
            self.release("implausible normal setpoint")
            return self._status("fehler", error=f"0x2306={self.schedule_info.get('normal_target_c')}", **info)

        target = base
        boost = self.morning_boost(now, room, target)
        if boost:
            if boost != self.owned:
                previous = self.owned
                self.set_owned(boost if boost else previous)
                try:
                    self.write_verified(boost)
                except Exception:
                    self.release("boost write failed", also_owned=(previous,))
                    raise
                self.set_owned(boost)
                self.last_step_at = now
                log(f"morning boost: room {room:.2f} °C, target {target} °C: 0x2321 {previous} -> {boost}")
            return self._status(
                "morgenboost",
                effective_target_c=boost,
                boost_remaining_min=round((self.boost_until - now) / 60),
                **info,
            )

        cmd = next_command(
            target_c=target,
            room_c=room,
            current_cmd=self.owned,
            config=cfg,
            now=now,
            last_step_at=self.last_step_at,
        )
        if cmd != self.owned:
            # Treat a begun write as possibly applied so cleanup never
            # assumes the old value is still active.
            previous = self.owned
            self.set_owned(cmd if cmd else previous)
            try:
                self.write_verified(cmd)
            except Exception as write_error:
                try:
                    self.release("write failed", also_owned=(previous,))
                except Exception as release_error:
                    raise RoomControlError(
                        f"write failed ({write_error}); release unverified ({release_error})"
                    ) from write_error
                raise
            self.set_owned(cmd)
            self.last_step_at = now
            log(f"room {room:.2f} °C, target {target} °C: 0x2321 {previous} -> {cmd}")

        lower, upper = comfort_band(target, cfg)
        correction = band_correction(
            room, lower, upper, cfg["verstaerkung"], cfg["max_korrektur"],
        )
        state = "aktiv" if self.owned else "neutral"
        return self._status(
            state,
            correction_k=round(correction, 2),
            effective_target_c=self.owned or target,
            **info,
        )


# ---------------------------------------------------------------------------
# MQTT runtime
# ---------------------------------------------------------------------------

class SplitterIO:
    """Request/response access through the running splitter."""

    def __init__(self, client, listen_topic):
        self.client = client
        self.listen_topic = listen_topic
        self.cond = threading.Condition()
        self.seq = 0
        self.responses = []

    def sleep(self, seconds):
        time.sleep(seconds)

    def on_response(self, payload):
        with self.cond:
            self.seq += 1
            self.responses.append((self.seq, payload))
            self.responses = self.responses[-100:]
            self.cond.notify_all()

    @staticmethod
    def _addr(response):
        parts = response.split(";")
        try:
            return int(parts[1], 0)
        except (IndexError, ValueError):
            return None

    def request(self, command, addr, timeout=REQUEST_TIMEOUT):
        with self.cond:
            start = self.seq
        info = self.client.publish(self.listen_topic, command)
        info.wait_for_publish(timeout=timeout)
        deadline = time.monotonic() + timeout
        with self.cond:
            while True:
                for seq, resp in self.responses:
                    if seq > start and self._addr(resp) == addr:
                        parts = resp.split(";")
                        if parts[0] != "1" or len(parts) < 3:
                            raise RoomControlError(f"splitter error: {resp}")
                        return parts[2]
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError(f"no splitter response for {command}")
                self.cond.wait(timeout=remaining)

    def read_int(self, addr, length):
        raw = self.request(f"r;0x{addr:04X};{length};1;False", addr)
        try:
            return int(raw, 0)
        except ValueError:
            return int(float(raw))

    def read_bytes(self, addr, length):
        """Raw read; the splitter answers ``read`` with a hex string."""
        return self.request(f"read;0x{addr:04X};{length}", addr)

    def read_scaled(self, addr, length, scale, signed):
        raw = self.request(f"r;0x{addr:04X};{length};{scale};{bool(signed)}", addr)
        return float(raw)

    def write_int(self, addr, length, value):
        if length != 1 or addr not in (ADDR_EXTERNAL_SETPOINT, ADDR_OPERATING_MODE):
            raise RoomControlError("only 0x2321 and 0x2323 may be written")
        if type(value) is not int:
            raise RoomControlError(f"refusing value {value!r}")
        if addr == ADDR_EXTERNAL_SETPOINT and not (
                value == 0 or EXTERNAL_MIN_C <= value <= EXTERNAL_MAX_C):
            raise RoomControlError(f"refusing external setpoint {value}")
        if addr == ADDR_OPERATING_MODE and value not in (MODE_DHW_ONLY, MODE_HEATING_DHW):
            raise RoomControlError(f"refusing operating mode {value}")
        self.request(f"w;0x{addr:04X};{length};{value}", addr)


def _local_wallclock():
    t = datetime.datetime.now()
    return t.weekday(), t.hour * 60 + t.minute, t.date()


def _load_settings():
    if APP_DIR not in sys.path:
        sys.path.insert(0, APP_DIR)
    from c_settings_adapter import settings  # type: ignore
    for key in ("mqtt_broker", "mqtt_listen", "mqtt_respond", "mqtt_topic"):
        if not getattr(settings, key, None):
            raise RuntimeError(f"{key} is not configured in settings_ini.py")
    return settings


def _make_client(settings, client_id, base):
    import ssl
    from paho.mqtt import client as mqtt

    client = mqtt.Client(
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        client_id=client_id,
    )
    userpass = getattr(settings, "mqtt_user", None)
    if userpass and str(userpass).lower() != "none":
        user, password = str(userpass).split(":", 1)
        client.username_pw_set(user, password)
    if getattr(settings, "mqtt_tls_enable", False):
        skip = bool(getattr(settings, "mqtt_tls_skip_verify", False))
        client.tls_set(
            ca_certs=getattr(settings, "mqtt_tls_ca_certs", None),
            certfile=getattr(settings, "mqtt_tls_certfile", None),
            keyfile=getattr(settings, "mqtt_tls_keyfile", None),
            cert_reqs=ssl.CERT_NONE if skip else ssl.CERT_REQUIRED,
        )
        client.tls_insecure_set(skip)
    if base:
        client.will_set(f"{base}/room_control/availability", "offline", retain=True)
    client.reconnect_delay_set(min_delay=2, max_delay=60)
    host, port = settings.mqtt_broker.rsplit(":", 1)
    return client, host, int(port)


class Service:
    def __init__(self):
        self.settings = _load_settings()
        self.base = self.settings.mqtt_topic.rstrip("/")
        self.topic = f"{self.base}/room_control"
        self.events = queue.Queue()
        self.stop = threading.Event()
        self.connected = threading.Event()
        self.client, self.host, self.port = _make_client(
            self.settings, f"optolink-room-control-{os.getpid()}", self.base
        )
        self.io = SplitterIO(self.client, self.settings.mqtt_listen)
        self.controller = RoomController(self.io, load_state(), boost=self.pump_boost)
        self.client.on_connect = self.on_connect
        self.client.on_disconnect = self.on_disconnect
        self.client.on_message = self.on_message

    def pump_boost(self, seconds, reason):
        """Expiring 100 % request to the pump guard (runs inside the splitter)."""
        self.client.publish(f"{self.base}/pump_guard/extern/set", f"{int(seconds)};{reason}")

    # MQTT callbacks only enqueue; all controller work runs in the main loop.
    def on_connect(self, client, _userdata, _flags, reason_code, _props):
        if getattr(reason_code, "is_failure", False):
            log(f"MQTT connect failed: {reason_code}")
            return
        client.subscribe([
            (self.settings.mqtt_respond, 0),
            (f"{self.topic}/sensors", 0),
            (f"{self.topic}/+/set", 0),
        ])
        client.publish(f"{self.topic}/availability", "online", retain=True)
        self.connected.set()
        self.events.put(("publish_config", None))
        log("MQTT connected")

    def on_disconnect(self, _client, _userdata, _flags, reason_code, _props):
        self.connected.clear()
        log(f"MQTT disconnected: {reason_code}")

    def on_message(self, _client, _userdata, message):
        if message.topic == self.settings.mqtt_respond:
            self.io.on_response(message.payload.decode(errors="replace").strip())
            return
        if message.topic == f"{self.topic}/sensors":
            if message.retain:
                return  # retained values carry no freshness information
            self.events.put(("sensors", message.payload))
            return
        if message.topic.endswith("/set"):
            key = message.topic[len(self.topic) + 1:-len("/set")]
            self.events.put(("set", (key, message.payload.decode(errors="replace").strip())))

    def apply_setting(self, key, value):
        cfg = dict(self.controller.config)
        if key in ("enabled", "nachtabschaltung"):
            cfg[key] = value.lower() in ("1", "on", "true", "ein")
        elif key == "aggregation":
            if value not in AGGREGATIONS:
                log(f"ignoring aggregation {value!r}")
                return
            cfg["aggregation"] = value
        elif key in PARAMETERS:
            try:
                cfg[key] = PARAMETERS[key][0](float(value))
            except ValueError:
                log(f"ignoring {key}={value!r}")
                return
        else:
            return
        new = validate_config(cfg)
        if new[key] != cfg[key] and not (
                isinstance(cfg[key], float) and abs(new[key] - cfg[key]) < 0.005):
            log(f"rejected {key}={value!r} (out of range)")
        else:
            self.controller.state["config"] = new
            save_state(self.controller.state)
            log(f"setting {key} = {new[key]}")
        self.publish_config()

    def publish_config(self):
        cfg = self.controller.config
        for key in ("toleranz_unten", "toleranz_oben", "verstaerkung", "max_korrektur",
                    "morgenboost", "morgenboost_ausloesung", "morgenboost_dauer",
                    "nacht_ein", "nacht_aus", "nacht_min_aussen", "nacht_vorlauf",
                    "nacht_max_schaltungen", "nacht_nachlauf", "aggregation"):
            self.client.publish(f"{self.topic}/{key}/state", str(cfg[key]), retain=True)
        for key in ("enabled", "nachtabschaltung"):
            self.client.publish(f"{self.topic}/{key}/state", "1" if cfg[key] else "0", retain=True)

    def publish_status(self, status):
        payload = dict(status)
        payload["updated"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        self.client.publish(f"{self.topic}/status", json.dumps(payload, sort_keys=True), retain=True)

    def handle_events(self, timeout):
        try:
            kind, data = self.events.get(timeout=timeout)
        except queue.Empty:
            return False
        if kind == "sensors":
            try:
                self.controller.update_samples(parse_sensor_payload(data, time.monotonic()))
            except RoomControlError as exc:
                log(f"WARNING: ignoring sensor payload: {exc}")
        elif kind == "set":
            self.apply_setting(*data)
            return True
        elif kind == "publish_config":
            self.publish_config()
        return False

    def run(self):
        signal.signal(signal.SIGTERM, lambda *_: self.stop.set())
        signal.signal(signal.SIGINT, lambda *_: self.stop.set())
        while not self.stop.is_set():
            try:
                self.client.connect(self.host, self.port, keepalive=30)
                break
            except OSError as exc:
                log(f"MQTT broker unreachable ({exc}); retrying in 10 s")
                self.stop.wait(10)
        self.client.loop_start()
        next_tick = time.monotonic() + 5
        try:
            while not self.stop.is_set():
                changed = self.handle_events(timeout=0.5)
                if changed:
                    next_tick = min(next_tick, time.monotonic() + 1)
                if time.monotonic() < next_tick:
                    continue
                started = time.monotonic()
                next_tick = started + CYCLE_SECONDS
                if not self.connected.is_set():
                    continue
                try:
                    status = self.controller.tick()
                    # decided after the tick: a run-on that just began needs 10 s cycles
                    next_tick = started + self.controller.next_delay()
                except Exception as exc:  # boiler/splitter unreachable etc.
                    log(f"WARNING: control cycle failed: {exc}")
                    status = self.controller._status("fehler", error=str(exc)[:200])
                    next_tick = time.monotonic() + (
                        NACHLAUF_CYCLE_S if self.controller.nachlauf is not None else 30)
                self.publish_status(status)
        finally:
            try:
                if self.connected.is_set():
                    self.controller.release("service stop")
                    self.controller.nachlauf_cancel("service stop")
                    self.controller.night_release("service stop")
                    self.publish_status(self.controller._status("aus", stopped=True))
            except Exception as exc:
                log(f"WARNING: release on stop failed: {exc}; ExecStopPost retries")
            self.client.publish(f"{self.topic}/availability", "offline", retain=True)
            time.sleep(0.3)
            self.client.loop_stop()
            self.client.disconnect()


def release_only():
    """ExecStopPost fallback: release an owned override after any stop/crash."""
    state = load_state()
    if not state["owned_command"] and not state["owned_mode"]:
        log("release: no owned external room setpoint or night shutdown, nothing to do")
        return 0
    log(f"release: handing back owned external room setpoint {state['owned_command']}, "
        f"night shutdown {state['owned_mode']}")
    settings = _load_settings()
    client, host, port = _make_client(settings, f"optolink-room-release-{os.getpid()}", None)
    io = SplitterIO(client, settings.mqtt_listen)
    client.on_message = lambda _c, _u, m: io.on_response(m.payload.decode(errors="replace").strip())
    client.on_connect = lambda c, *_: c.subscribe(settings.mqtt_respond, 0)
    client.connect(host, port, keepalive=30)
    client.loop_start()
    try:
        time.sleep(0.5)
        controller = RoomController(io, state)
        controller.resumed = True
        failed = None
        try:
            controller.release("ExecStopPost")
        except Exception as exc:
            failed = exc
        controller.night_release("ExecStopPost")
        if failed:
            raise failed
        return 0
    finally:
        client.loop_stop()
        client.disconnect()


def self_test():
    cfg = validate_config({"enabled": True})
    assert parse_operating_state("0201000000006d0101000001b4000000006d0100b400") == ("reduziert", 18.0)
    assert comfort_band(21, cfg) == (20.5, 21.5)
    assert band_correction(21.0, 20.5, 21.5, 1.0, 2) == 0.0
    assert band_correction(19.5, 20.5, 21.5, 1.0, 2) == 1.0
    assert band_correction(23.5, 20.5, 21.5, 1.0, 2) == -2.0
    assert next_command(target_c=21, room_c=19.0, current_cmd=0, config=cfg,
                        now=0, last_step_at=None) == 22
    assert next_command(target_c=21, room_c=21.0, current_cmd=22, config=cfg,
                        now=1000, last_step_at=0) == 0
    assert aggregate([20.0, 22.0], "Mittelwert") == 21.0
    assert decode_schedule_block("2ac0ffffffffffff") == [(320, 1440)]
    assert schedule_position({0: [(320, 1440)], 1: [(320, 1440)]}, 0, 60) == (False, 260, 0)
    want, _ = night_decision(active=False, room_c=20.0, reduced_c=18, outside_c=0.0,
                             in_day=False, minutes_to_day=300, config=cfg, switches_used=0)
    assert want
    print("optolink-room-control self-test OK")
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--release", action="store_true",
                        help="release an owned 0x2321 override and exit")
    parser.add_argument("--self-test", action="store_true",
                        help="run pure logic self-test and exit")
    args = parser.parse_args()
    if args.self_test:
        return self_test()
    if args.release:
        return release_only()
    Service().run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
