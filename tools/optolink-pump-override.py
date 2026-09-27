#!/opt/optolink/venv/bin/python
"""Guarded WB2A heating-pump minimum-speed override.

MQTT arms the feature. On ON, the daemon temporarily takes ownership of the
Optolink serial port for the current space-heating burner cycle, enters P300,
and keeps only the confirmed volatile E7 cache byte 0x20A5 at 100. It writes
again only after observing the controller restore that byte to the configured
baseline. On flame-off, DHW, OFF, fault, signal, or error it restores the
baseline and returns serial ownership to the normal Optolink services.
"""
from __future__ import annotations

import fcntl
import json
import os
import queue
import signal
import subprocess
import sys
import threading
import time

APP_DIR = "/opt/optolink"
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

import serial
from c_settings_adapter import settings  # type: ignore
from homeassistant_publish import connect_mqtt  # type: ignore

RAM_E7 = 0x20A5
RAM_BLOCK = 0x20A0
IDENT = (0x00F8, 2)
ADDR_E7 = 0x27E7
ADDR_WW = 0x650A
ADDR_GFA = 0x55D3
ADDR_FAULT = 0x5738
ADDR_ALARM = 0xA132
BASELINE_REQUIRED = 30
OVERRIDE_VALUE = 100
POLL_SLEEP = 0.02
STATE_CHECK_SECONDS = 0.45
FAULT_CHECK_SECONDS = 8.0
MAX_OVERRIDE_SECONDS = 7200.0
LOCK = "/run/lock/physical-ram-snapshot.lock"
SPLITTER = "optolink-splitter.service"
PARTY = "optolink-party-emulator.service"
SCHEDULE = "optolink-schedule-manager.service"
MANAGED_SERVICES = (SCHEDULE, PARTY, SPLITTER)


def log(message):
    print(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {message}", flush=True)


def checksum(data: bytes) -> int:
    return sum(data[1:]) & 0xFF


def frame(function: int, address: int, length: int) -> bytes:
    allowed = {
        (0x01, *IDENT),
        (0x01, ADDR_E7, 1),
        (0x01, ADDR_WW, 1),
        (0x01, ADDR_GFA, 11),
        (0x01, ADDR_FAULT, 1),
        (0x01, ADDR_ALARM, 29),
        (0x03, RAM_BLOCK, 32),
    }
    if (function, address, length) not in allowed:
        raise RuntimeError(f"blocked P300 read 0x{function:02X}/0x{address:04X}/{length}")
    body = bytes((0x41, 0x05, 0x00, function, address >> 8, address & 0xFF, length))
    return body + bytes((checksum(body),))


def write_frame(value: int) -> bytes:
    if value not in (BASELINE_REQUIRED, OVERRIDE_VALUE):
        raise RuntimeError(f"blocked E7 RAM value {value}")
    body = bytes((0x41, 0x06, 0x00, 0x04, RAM_E7 >> 8, RAM_E7 & 0xFF, 1, value))
    return body + bytes((checksum(body),))


def active(unit: str) -> bool:
    return subprocess.run(["systemctl", "is-active", "--quiet", unit]).returncode == 0


def svc(action: str, unit: str):
    p = subprocess.run(["systemctl", action, unit], capture_output=True, text=True)
    if p.returncode:
        raise RuntimeError(f"systemctl {action} {unit}: {p.stderr.strip()}")


def read_port() -> str:
    return getattr(settings, "port_optolink", None) or "/dev/ttyUSB0"


class Wire:
    def __init__(self, port: str):
        self.s = serial.Serial(
            port=port,
            baudrate=4800,
            bytesize=8,
            parity="E",
            stopbits=2,
            timeout=0.05,
            write_timeout=2,
            xonxoff=False,
            rtscts=False,
            dsrdtr=False,
            exclusive=True,
        )

    def close(self):
        self.s.close()

    def exact(self, n: int, timeout=3.0) -> bytes:
        end = time.monotonic() + timeout
        out = bytearray()
        while len(out) < n and time.monotonic() < end:
            out.extend(self.s.read(n - len(out)))
        if len(out) != n:
            raise RuntimeError(f"serial timeout expected {n}, got {len(out)}")
        return bytes(out)

    def send(self, data: bytes):
        if self.s.write(data) != len(data):
            raise RuntimeError("partial serial write")

    def wait_control(self, want: int, timeout=5.0):
        end = time.monotonic() + timeout
        stray = bytearray()
        while time.monotonic() < end:
            b = self.s.read(1)
            if not b:
                continue
            if b == bytes((want,)):
                return
            if want == 0x05 and b in (b"\x06", b"\x15"):
                continue
            if want == 0x06 and b == b"\x05":
                continue
            stray.extend(b)
            if len(stray) > 64:
                raise RuntimeError("too much stray data during P300 init")
        raise RuntimeError(f"P300 init timeout waiting 0x{want:02X}; stray={stray.hex()}")

    def enter(self):
        time.sleep(1.0)
        self.s.reset_input_buffer()
        self.send(b"\x04")
        self.wait_control(0x05)
        self.send(b"\x16\x00\x00")
        self.wait_control(0x06)

    def leave(self):
        try:
            self.send(b"\x04")
        except Exception:
            pass

    def request(self, function: int, address: int, length: int):
        req = frame(function, address, length)
        self.send(req)
        first = self.exact(1)
        if first == b"\x15":
            return "NACK", b""
        if first != b"\x06":
            raise RuntimeError(f"expected ACK/NACK, got {first.hex()}")
        head = self.exact(2)
        if head[0] != 0x41 or not 1 <= head[1] <= 64:
            raise RuntimeError("bad P300 response header")
        msg = head + self.exact(head[1] + 1)
        if checksum(msg[:-1]) != msg[-1]:
            raise RuntimeError("bad P300 response checksum")
        typ = msg[2] & 0x0F
        self.send(b"\x06")
        if typ != 1:
            return f"ERROR_{msg[7:-1].hex()}", msg[7:-1]
        if int.from_bytes(msg[4:6], "big") != address:
            raise RuntimeError("P300 response address mismatch")
        return "SUCCESS", msg[7:-1]

    def pwrite_e7(self, value: int):
        req = write_frame(value)
        self.send(req)
        if self.exact(1) != b"\x06":
            raise RuntimeError("Physical_WRITE ACK failed")
        head = self.exact(2)
        msg = head + self.exact(head[1] + 1)
        if checksum(msg[:-1]) != msg[-1]:
            raise RuntimeError("Physical_WRITE checksum failed")
        self.send(b"\x06")
        if (msg[2] & 0x0F) != 1:
            raise RuntimeError(f"Physical_WRITE failed: {msg.hex()}")

    def read_virtual(self, address: int, length: int) -> bytes:
        status, data = self.request(0x01, address, length)
        if status != "SUCCESS" or len(data) != length:
            raise RuntimeError(f"Virtual_READ 0x{address:04X} failed: {status}")
        return data

    def read_e7_ram(self) -> int:
        status, data = self.request(0x03, RAM_BLOCK, 32)
        if status != "SUCCESS" or len(data) != 32:
            raise RuntimeError(f"Physical_READ E7 cache failed: {status}")
        return data[RAM_E7 - RAM_BLOCK]


class PumpOverrideDaemon:
    def __init__(self):
        if not getattr(settings, "mqtt_broker", None):
            raise RuntimeError("MQTT is disabled in settings_ini.py")
        if not getattr(settings, "mqtt_topic", None):
            raise RuntimeError("mqtt_topic is not configured")
        self.base_topic = settings.mqtt_topic.rstrip("/")
        self.command_topic = f"{self.base_topic}/pump_min_override/set"
        self.state_topic = f"{self.base_topic}/pump_min_override/state"
        self.status_topic = f"{self.base_topic}/pump_min_override/status"
        self.discovery_topic = "homeassistant/switch/optolink_pump_min_override/config"
        self.client = None
        self.actions = queue.Queue()
        self.stop_event = threading.Event()
        self.cancel_override = threading.Event()
        self.active_override = False

    def publish_discovery(self):
        payload = {
            "name": "Heating pump minimum override",
            "unique_id": "optolink_pump_min_override",
            "command_topic": self.command_topic,
            "state_topic": self.state_topic,
            "payload_on": "ON",
            "payload_off": "OFF",
            "state_on": "ON",
            "state_off": "OFF",
            "icon": "mdi:pump",
            "device": {
                "identifiers": ["optolink_splitter"],
                "name": "Optolink Splitter",
                "manufacturer": "OpenV / local integration",
            },
        }
        self.client.publish(self.discovery_topic, json.dumps(payload), retain=True).wait_for_publish()

    def publish_state(self, enabled: bool):
        self.client.publish(self.state_topic, "ON" if enabled else "OFF", retain=True).wait_for_publish()

    def publish_status(self, **fields):
        fields.setdefault("active", self.active_override)
        fields.setdefault("timestamp", int(time.time()))
        self.client.publish(self.status_topic, json.dumps(fields, sort_keys=True), retain=True).wait_for_publish()

    def on_message(self, client, userdata, message):
        if message.topic != self.command_topic:
            return
        payload = message.payload.decode(errors="replace").strip().lower()
        if payload in ("1", "on", "true", "ein"):
            self.cancel_override.clear()
            self.actions.put("ON")
        elif payload in ("0", "off", "false", "aus"):
            self.cancel_override.set()
            self.actions.put("OFF")
        else:
            log(f"ignoring invalid command payload {payload!r}")

    def connect(self):
        self.client = connect_mqtt(retries=10, delay=3)
        if self.client is None:
            raise RuntimeError("MQTT connection failed")
        self.client.on_message = self.on_message
        self.client.subscribe([(self.command_topic, 0)])
        time.sleep(0.4)
        self.publish_discovery()
        self.publish_state(False)
        self.publish_status(reason="ready")
        log(f"listening on {self.command_topic}")

    @staticmethod
    def safe_operating_state(wire: Wire):
        ww = wire.read_virtual(ADDR_WW, 1)[0]
        gfa = wire.read_virtual(ADDR_GFA, 11)
        flame = bool(gfa[5] & 0x20)
        return ww, flame

    @staticmethod
    def current_fault_clear(wire: Wire):
        fault = wire.read_virtual(ADDR_FAULT, 1)[0]
        alarm = wire.read_virtual(ADDR_ALARM, 29)
        return fault == 0 and len(alarm) == 29 and alarm[28] == 0

    def run_override_cycle(self):
        lock_fd = os.open(LOCK, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        stopped = []
        wire = None
        baseline = None
        writes = 0
        repairs = 0
        started = time.monotonic()
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            initial = {u: active(u) for u in MANAGED_SERVICES}
            if not initial[SPLITTER]:
                raise RuntimeError("splitter is not active before takeover")
            for unit in MANAGED_SERVICES:
                if initial[unit]:
                    svc("stop", unit)
                    stopped.append(unit)
                    log(f"stopped {unit}")

            wire = Wire(read_port())
            wire.enter()
            ident = wire.read_virtual(*IDENT)
            if ident != bytes.fromhex("20 c2"):
                raise RuntimeError(f"unexpected controller identity {ident.hex()}")
            if not self.current_fault_clear(wire):
                raise RuntimeError("current fault/alarm is nonzero")

            ww, flame = self.safe_operating_state(wire)
            baseline = wire.read_virtual(ADDR_E7, 1)[0]
            ram = wire.read_e7_ram()
            if baseline != BASELINE_REQUIRED or ram != BASELINE_REQUIRED:
                raise RuntimeError(f"require configured/working E7={BASELINE_REQUIRED}, got e7={baseline} ram={ram}")
            if ww != 0 or not flame:
                raise RuntimeError(f"override requires space-heating flame: ww={ww} flame={int(flame)}")

            self.active_override = True
            self.publish_state(True)
            self.publish_status(reason="engaged", baseline=baseline)
            wire.pwrite_e7(OVERRIDE_VALUE)
            writes += 1
            next_state_check = time.monotonic() + STATE_CHECK_SECONDS
            next_fault_check = time.monotonic() + FAULT_CHECK_SECONDS
            next_status = time.monotonic() + 2.0

            while not self.stop_event.is_set() and not self.cancel_override.is_set():
                if time.monotonic() - started >= MAX_OVERRIDE_SECONDS:
                    self.publish_status(reason="max_runtime_reached")
                    break
                ram = wire.read_e7_ram()
                if ram == baseline:
                    detected = time.monotonic()
                    wire.pwrite_e7(OVERRIDE_VALUE)
                    writes += 1
                    repairs += 1
                    self.publish_status(
                        reason="reload_repaired",
                        repairs=repairs,
                        writes=writes,
                        repair_ms=round((time.monotonic() - detected) * 1000, 1),
                    )
                elif ram != OVERRIDE_VALUE:
                    raise RuntimeError(f"unexpected E7 RAM value {ram}")

                now = time.monotonic()
                if now >= next_state_check:
                    ww, flame = self.safe_operating_state(wire)
                    if ww != 0:
                        self.publish_status(reason="dhw_started", ww=ww)
                        break
                    if not flame:
                        self.publish_status(reason="flame_off")
                        break
                    next_state_check = now + STATE_CHECK_SECONDS

                if now >= next_fault_check:
                    if not self.current_fault_clear(wire):
                        raise RuntimeError("fault/alarm became nonzero during override")
                    next_fault_check = now + FAULT_CHECK_SECONDS

                if now >= next_status:
                    self.publish_status(
                        reason="active",
                        repairs=repairs,
                        writes=writes,
                        runtime_seconds=round(now - started, 1),
                    )
                    next_status = now + 2.0
                time.sleep(POLL_SLEEP)

        finally:
            if wire is not None:
                try:
                    restore = baseline if baseline in (BASELINE_REQUIRED,) else BASELINE_REQUIRED
                    if wire.read_e7_ram() != restore:
                        wire.pwrite_e7(restore)
                    log(f"restored E7 RAM to {restore}")
                except Exception as exc:
                    log(f"WARNING: E7 RAM restore failed: {exc}")
                try:
                    wire.leave()
                except Exception:
                    pass
                try:
                    wire.close()
                except Exception:
                    pass
            for unit in reversed(stopped):
                try:
                    svc("start", unit)
                    log(f"restored {unit}")
                except Exception as exc:
                    log(f"ERROR restoring {unit}: {exc}")
            self.active_override = False
            try:
                self.publish_state(False)
                self.publish_status(
                    reason="released",
                    repairs=repairs,
                    writes=writes,
                    runtime_seconds=round(time.monotonic() - started, 1),
                )
            except Exception:
                pass
            os.close(lock_fd)

    def run(self):
        self.connect()
        while not self.stop_event.is_set():
            try:
                action = self.actions.get(timeout=0.5)
            except queue.Empty:
                continue
            if action == "OFF":
                self.cancel_override.set()
                if not self.active_override:
                    self.publish_state(False)
                    self.publish_status(reason="off")
                continue
            if action != "ON" or self.active_override:
                continue
            try:
                self.run_override_cycle()
            except BlockingIOError:
                self.publish_state(False)
                self.publish_status(reason="busy", error="physical probe lock is busy")
            except Exception as exc:
                log(f"override rejected/aborted: {exc}")
                self.publish_state(False)
                self.publish_status(reason="error", error=str(exc))
            finally:
                self.cancel_override.clear()


def main():
    if "--self-test" in sys.argv:
        assert write_frame(30).hex() == "4106000420a5011eee"
        assert write_frame(100).hex() == "4106000420a5016434"
        assert frame(0x03, 0x20A0, 32).hex() == "4105000320a020e8"
        try:
            frame(0x03, 0x20C0, 32)
            raise AssertionError("address allowlist failed")
        except RuntimeError:
            pass
        print("SELFTEST=PASS")
        return 0

    daemon = PumpOverrideDaemon()

    def stop(signum, frame_obj):
        daemon.stop_event.set()
        daemon.cancel_override.set()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    daemon.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
