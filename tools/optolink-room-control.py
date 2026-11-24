#!/opt/optolink/venv/bin/python
"""Room-temperature feedback for the WB2A heating circuit A1/M1.

Home Assistant publishes the current values of one or more room temperature
sensors to ``<mqtt_topic>/room_control/sensors``. This service combines them
(mean, minimum or maximum), compares the result with a configurable comfort
band (lower and upper threshold) and adjusts the WB2A *external normal room
setpoint* ``0x2321``. The boiler then shifts its flow setpoint along the
configured heating curve exactly as if the room target had been changed.

Hardware basis (VDensHO1 / 20C2 / SW 0103, live A/B/A tests 2026-10-11):
external room setpoint 20 / 21 / 22 °C at normal target 21 °C produced
flow setpoints 35.0 / 35.5 / 37.4 °C. Writing ``0x2321 = 0`` returns
control to the regular room target ``0x2306``.

Safety model:

* all controller traffic goes through the running splitter (MQTT
  request/response); this service never opens the serial port;
* only ``0x2321`` is ever written, only with 0 or 10..30 °C, always with
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
"""
from __future__ import annotations

import argparse
import ast
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
ADDR_FLOW_SETPOINT = 0x2544
ADDR_CURRENT_FAULT = 0x5738
ADDR_ROOM_INFLUENCE = (0x27A0, 0x27B0)

EXTERNAL_MIN_C = 10
EXTERNAL_MAX_C = 30
SENSOR_MIN_C = 5.0
SENSOR_MAX_C = 35.0

CYCLE_SECONDS = 60.0
SENSOR_MAX_AGE_S = 600.0
MIN_STEP_INTERVAL_S = 300.0
HYSTERESIS_K = 0.75
INFLUENCE_CHECK_S = 1800.0
REQUEST_TIMEOUT = 8.0

AGGREGATIONS = ("Mittelwert", "Minimum", "Maximum")

# name: (type, minimum, maximum, default)
PARAMETERS = {
    "schwelle_min": (float, 15.0, 25.0, 20.5),
    "schwelle_max": (float, 15.0, 26.0, 21.5),
    "verstaerkung": (float, 0.5, 3.0, 1.0),
    "max_korrektur": (int, 1, 5, 2),
}

DEFAULT_CONFIG = {
    "enabled": False,
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
    if cfg["aggregation"] not in AGGREGATIONS:
        cfg["aggregation"] = DEFAULT_CONFIG["aggregation"]
    for name, (kind, lo, hi, default) in PARAMETERS.items():
        try:
            value = kind(cfg[name])
        except (TypeError, ValueError):
            value = default
        if not (lo <= value <= hi):
            value = default
        cfg[name] = value
    if cfg["schwelle_min"] >= cfg["schwelle_max"]:
        cfg["schwelle_min"] = DEFAULT_CONFIG["schwelle_min"]
        cfg["schwelle_max"] = DEFAULT_CONFIG["schwelle_max"]
    return cfg


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


def next_command(*, target_c, room_c, current_cmd, config, now, last_step_at):
    """Next external setpoint to write (0 = regular room target).

    ``current_cmd`` is the value this service owns (0 if none). Changes are
    limited to 1 K per step and ``MIN_STEP_INTERVAL_S`` between steps; a
    hysteresis avoids toggling at rounding boundaries.
    """
    corr = band_correction(
        room_c,
        config["schwelle_min"],
        config["schwelle_max"],
        config["verstaerkung"],
        config["max_korrektur"],
    )
    raw = target_c + corr
    effective = current_cmd if current_cmd else target_c
    if corr == 0.0:
        wanted = target_c
    elif abs(raw - effective) < HYSTERESIS_K:
        wanted = effective
    else:
        wanted = int(math.floor(raw + 0.5))
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
    return {
        "version": 1,
        "owned_command": owned,
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

    def __init__(self, io, state, *, save=save_state, clock=time.monotonic):
        self.io = io
        self.state = state
        self.save = save
        self.clock = clock
        self.samples = {}
        self.last_step_at = None
        self.next_influence_check = 0.0
        self.influence_coded = False
        self.status = {"state": "start"}
        self.resumed = False
        self.last_normal_target = None

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

    def write_verified(self, value):
        self.io.write_int(ADDR_EXTERNAL_SETPOINT, 1, value)
        last = None
        for delay in (0.3, 0.9, 1.8):
            self.io.sleep(delay)
            last = self.io.read_int(ADDR_EXTERNAL_SETPOINT, 1)
            if last == value:
                return
        raise RoomControlError(f"0x2321 readback {last}, expected {value}")

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
            **extra,
        }
        # The boiler always works with some room target: the external one we
        # own, else the regular normal target. Show it in every state.
        normal = self.status.get("normal_target_c", self.last_normal_target)
        if normal is not None:
            self.status["normal_target_c"] = normal
            self.status.setdefault("effective_target_c", self.owned or normal)
        return self.status

    def tick(self):
        now = self.clock()
        cfg = self.config
        values = fresh_values(self.samples, now)
        room = aggregate(values.values(), cfg["aggregation"])
        info = {
            "room_c": None if room is None else round(room, 2),
            "sensors": {k: values[k] for k in sorted(values)},
            "sensor_count": len(values),
            "aggregation": cfg["aggregation"],
            "schwelle_min": cfg["schwelle_min"],
            "schwelle_max": cfg["schwelle_max"],
        }

        current = self.io.read_int(ADDR_EXTERNAL_SETPOINT, 1)
        if not self.resumed:
            self.resumed = True
            if self.owned and current != self.owned:
                log(f"stored ownership {self.owned} does not match 0x2321={current}; dropped")
                self.set_owned(0)
        if current != 0 and current != self.owned:
            return self._status("fremdbelegt", foreign_value_c=current, **info)

        normal = self.io.read_int(ADDR_NORMAL_SETPOINT, 1)
        self.last_normal_target = normal if 3 <= normal <= 37 else None

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

        if room is None:
            self.release("no fresh sensor data")
            return self._status("keine_sensoren", **info)

        target = self.io.read_int(ADDR_NORMAL_SETPOINT, 1)
        self.last_normal_target = target if 3 <= target <= 37 else None
        if not 3 <= target <= 37:
            self.release("implausible normal setpoint")
            return self._status("fehler", error=f"0x2306={target}", **info)

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

        correction = band_correction(
            room, cfg["schwelle_min"], cfg["schwelle_max"],
            cfg["verstaerkung"], cfg["max_korrektur"],
        )
        state = "aktiv" if self.owned else "neutral"
        return self._status(
            state,
            normal_target_c=target,
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

    def write_int(self, addr, length, value):
        if addr != ADDR_EXTERNAL_SETPOINT or length != 1:
            raise RoomControlError("only 0x2321 may be written")
        if type(value) is not int or not (value == 0 or EXTERNAL_MIN_C <= value <= EXTERNAL_MAX_C):
            raise RoomControlError(f"refusing external setpoint {value}")
        self.request(f"w;0x{addr:04X};{length};{value}", addr)


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
        self.controller = RoomController(self.io, load_state())
        self.client.on_connect = self.on_connect
        self.client.on_disconnect = self.on_disconnect
        self.client.on_message = self.on_message

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
        if key == "enabled":
            cfg["enabled"] = value.lower() in ("1", "on", "true", "ein")
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
        if new[key] != cfg[key] or new["schwelle_min"] != cfg["schwelle_min"] or new["schwelle_max"] != cfg["schwelle_max"]:
            log(f"rejected {key}={value!r} (range or min >= max)")
        else:
            self.controller.state["config"] = new
            save_state(self.controller.state)
            log(f"setting {key} = {new[key]}")
        self.publish_config()

    def publish_config(self):
        cfg = self.controller.config
        for key in ("schwelle_min", "schwelle_max", "verstaerkung", "max_korrektur", "aggregation"):
            self.client.publish(f"{self.topic}/{key}/state", str(cfg[key]), retain=True)
        self.client.publish(f"{self.topic}/enabled/state", "1" if cfg["enabled"] else "0", retain=True)

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
                next_tick = time.monotonic() + CYCLE_SECONDS
                if not self.connected.is_set():
                    continue
                try:
                    status = self.controller.tick()
                except Exception as exc:  # boiler/splitter unreachable etc.
                    log(f"WARNING: control cycle failed: {exc}")
                    status = self.controller._status("fehler", error=str(exc)[:200])
                    next_tick = time.monotonic() + 30
                self.publish_status(status)
        finally:
            try:
                if self.connected.is_set():
                    self.controller.release("service stop")
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
    if not state["owned_command"]:
        log("release: no owned external room setpoint, nothing to do")
        return 0
    log(f"release: handing back owned external room setpoint {state['owned_command']}")
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
        controller.release("ExecStopPost")
        return 0
    finally:
        client.loop_stop()
        client.disconnect()


def self_test():
    cfg = validate_config({"enabled": True})
    assert band_correction(21.0, 20.5, 21.5, 1.0, 2) == 0.0
    assert band_correction(19.5, 20.5, 21.5, 1.0, 2) == 1.0
    assert band_correction(23.5, 20.5, 21.5, 1.0, 2) == -2.0
    assert next_command(target_c=21, room_c=19.0, current_cmd=0, config=cfg,
                        now=0, last_step_at=None) == 22
    assert next_command(target_c=21, room_c=21.0, current_cmd=22, config=cfg,
                        now=1000, last_step_at=0) == 0
    assert aggregate([20.0, 22.0], "Mittelwert") == 21.0
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
