#!/opt/optolink/venv/bin/python
"""Synchronize the WB2A controller clock with the Optolink-Splitter host.

The controller clock is exposed at Optolink datapoint 0x088E as an 8-byte
Viessmann BCD date/time value:

  century, year, month, day, weekday(1=Mon..7=Sun), hour, minute, second

The helper reads the controller first and only writes when the absolute drift
exceeds DRIFT_THRESHOLD_SECONDS or the weekday byte disagrees with the date.
Every write is verified by a fresh readback; the transport ACK itself is not
treated as authoritative.

Hardware verification on the local 20C2/WB2A (2026-10-06) confirmed a forced
8-byte write to 0x088E followed by a successful readback at zero seconds host
drift. The controller returned transport status 255 for that write, which is
exactly why this helper treats post-write readback as authoritative.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import threading
import time
from datetime import datetime

APP_DIR = "/opt/optolink"

ADDR_SYSTEM_TIME = 0x088E
REQUEST_TIMEOUT = 5.0
DRIFT_THRESHOLD_SECONDS = 30
VERIFY_TOLERANCE_SECONDS = 5
VERIFY_DELAYS = (0.5, 1.0, 2.0)

WEEKDAYS = ("Mo", "Di", "Mi", "Do", "Fr", "Sa", "So")


def log(message: str) -> None:
    print(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {message}", flush=True)


def bcd_encode(value: int) -> int:
    if not 0 <= value <= 99:
        raise ValueError(f"BCD value outside 0..99: {value}")
    return ((value // 10) << 4) | (value % 10)


def bcd_decode(value: int) -> int:
    high = (value >> 4) & 0x0F
    low = value & 0x0F
    if high > 9 or low > 9:
        raise ValueError(f"invalid BCD byte 0x{value:02X}")
    return high * 10 + low


def encode_system_time(value: datetime) -> bytes:
    return bytes(
        [
            bcd_encode(value.year // 100),
            bcd_encode(value.year % 100),
            bcd_encode(value.month),
            bcd_encode(value.day),
            value.isoweekday(),
            bcd_encode(value.hour),
            bcd_encode(value.minute),
            bcd_encode(value.second),
        ]
    )


def decode_system_time(raw: bytes) -> tuple[datetime, int]:
    if len(raw) != 8:
        raise ValueError(f"system time must be exactly 8 bytes, got {len(raw)}")

    weekday = raw[4]
    if weekday not in range(1, 8):
        raise ValueError(f"invalid weekday byte: {weekday}")

    year = bcd_decode(raw[0]) * 100 + bcd_decode(raw[1])
    value = datetime(
        year,
        bcd_decode(raw[2]),
        bcd_decode(raw[3]),
        bcd_decode(raw[5]),
        bcd_decode(raw[6]),
        bcd_decode(raw[7]),
    )
    return value, weekday


def format_system_time(value: datetime) -> str:
    return (
        f"{WEEKDAYS[value.isoweekday() - 1]} "
        f"{value.day:02d}.{value.month:02d}.{value.year:04d} "
        f"{value.hour:02d}:{value.minute:02d}:{value.second:02d}"
    )


def parse_response_addr(response: str) -> int | None:
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


class ClockSync:
    def __init__(self) -> None:
        if APP_DIR not in sys.path:
            sys.path.insert(0, APP_DIR)

        from c_settings_adapter import settings  # type: ignore
        from homeassistant_publish import connect_mqtt  # type: ignore

        self.settings = settings
        self.connect_mqtt = connect_mqtt

        if not getattr(self.settings, "mqtt_broker", None):
            raise RuntimeError("MQTT is disabled in settings_ini.py")
        if not getattr(self.settings, "mqtt_listen", None):
            raise RuntimeError("mqtt_listen is disabled")
        if not getattr(self.settings, "mqtt_respond", None):
            raise RuntimeError("mqtt_respond is disabled")
        if not getattr(self.settings, "mqtt_topic", None):
            raise RuntimeError("mqtt_topic is not configured")

        self.base_topic = self.settings.mqtt_topic.rstrip("/")
        self.status_topic = f"{self.base_topic}/clock_sync/status"
        self.system_time_topic = f"{self.base_topic}/systemzeit"

        self.client = None
        self.response_cond = threading.Condition()
        self.response_seq = 0
        self.responses: list[tuple[int, str]] = []

    def on_message(self, client, userdata, message) -> None:  # noqa: ANN001
        if message.topic != self.settings.mqtt_respond:
            return
        response = message.payload.decode(errors="replace").strip()
        with self.response_cond:
            self.response_seq += 1
            self.responses.append((self.response_seq, response))
            if len(self.responses) > 100:
                self.responses = self.responses[-100:]
            self.response_cond.notify_all()

    def connect(self) -> None:
        self.client = self.connect_mqtt(retries=5, delay=2)
        if self.client is None:
            raise RuntimeError("MQTT connection failed")
        self.client.on_message = self.on_message
        self.client.subscribe(self.settings.mqtt_respond)
        time.sleep(0.4)

    def disconnect(self) -> None:
        if self.client is None:
            return
        try:
            self.client.loop_stop()
        finally:
            self.client.disconnect()

    def request(
        self,
        command: str,
        *,
        expected_addr: int = ADDR_SYSTEM_TIME,
        timeout: float = REQUEST_TIMEOUT,
    ) -> str:
        with self.response_cond:
            start_seq = self.response_seq

        log(f"TX {command}")
        self.client.publish(self.settings.mqtt_listen, command).wait_for_publish()
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
                        f"timeout waiting for 0x{expected_addr:04X} after {command}"
                    )
                self.response_cond.wait(timeout=remaining)

    @staticmethod
    def response_value(response: str, *, require_success: bool = True) -> str:
        parts = response.split(";")
        if len(parts) < 3:
            raise RuntimeError(f"malformed splitter response: {response}")
        if require_success and parts[0] != "1":
            raise RuntimeError(f"splitter request failed: {response}")
        return parts[2].strip()

    def read_clock(self) -> tuple[bytes, datetime, int]:
        response = self.request("r;0x088E;8;raw;False")
        value = self.response_value(response)
        if not re.fullmatch(r"[0-9A-Fa-f]{16}", value):
            raise RuntimeError(f"unexpected 0x088E readback: {value!r}")
        raw = bytes.fromhex(value)
        decoded, weekday = decode_system_time(raw)
        return raw, decoded, weekday

    def write_clock(self, raw: bytes) -> str | None:
        # A successful controller write is not guaranteed to produce splitter
        # response code 1. The live WB2A test returned 255; synchronize() always
        # decides success from a fresh decoded 0x088E readback instead.
        command = f"wraw;0x088E;{raw.hex().upper()}"
        try:
            return self.request(command)
        except TimeoutError as exc:
            # Some 8-byte VS1/KW writes can persist despite a short transport
            # response. The following readback is authoritative.
            log(f"WARNING: clock write transport timeout: {exc}")
            return None

    def publish_status(
        self,
        state: str,
        *,
        host_time: datetime,
        device_time: datetime | None,
        drift_seconds: float | None,
        corrected: bool,
        weekday_ok: bool | None,
        message: str,
    ) -> None:
        payload = {
            "state": state,
            "checked_at": datetime.now().astimezone().isoformat(),
            "host_time": host_time.isoformat(),
            "device_time": device_time.isoformat() if device_time else None,
            "drift_seconds": (
                round(drift_seconds, 3) if drift_seconds is not None else None
            ),
            "corrected": corrected,
            "weekday_ok": weekday_ok,
            "address": "0x088E",
            "message": message,
        }
        self.client.publish(
            self.status_topic,
            json.dumps(payload, separators=(",", ":"), ensure_ascii=False),
            retain=True,
        ).wait_for_publish()

        if device_time is not None:
            # Keep the normal splitter state topic fresh as well. This is the
            # exact text shape used by utils.vdatetime2str().
            self.client.publish(
                self.system_time_topic,
                format_system_time(device_time),
                retain=False,
            ).wait_for_publish()

    def synchronize(
        self,
        *,
        threshold: int = DRIFT_THRESHOLD_SECONDS,
        force: bool = False,
        check_only: bool = False,
    ) -> bool:
        raw, device_time, weekday = self.read_clock()
        host_time = datetime.now().replace(microsecond=0)
        drift = (device_time - host_time).total_seconds()
        weekday_ok = weekday == device_time.isoweekday()

        log(
            f"controller={format_system_time(device_time)} "
            f"host={format_system_time(host_time)} "
            f"drift={drift:+.0f}s weekday={'OK' if weekday_ok else 'MISMATCH'} "
            f"raw={raw.hex().upper()}"
        )

        if check_only:
            self.publish_status(
                "check",
                host_time=host_time,
                device_time=device_time,
                drift_seconds=drift,
                corrected=False,
                weekday_ok=weekday_ok,
                message="Read-only clock check",
            )
            return True

        if not force and abs(drift) <= threshold and weekday_ok:
            self.publish_status(
                "ok",
                host_time=host_time,
                device_time=device_time,
                drift_seconds=drift,
                corrected=False,
                weekday_ok=True,
                message=f"Clock within ±{threshold}s; no write required",
            )
            return True

        target_time = datetime.now().replace(microsecond=0)
        target_raw = encode_system_time(target_time)
        log(
            f"synchronizing controller clock to "
            f"{format_system_time(target_time)} raw={target_raw.hex().upper()}"
        )
        self.write_clock(target_raw)

        last_device = None
        last_drift = None
        last_weekday_ok = None
        for delay in VERIFY_DELAYS:
            time.sleep(delay)
            _, verify_time, verify_weekday = self.read_clock()
            verify_host = datetime.now().replace(microsecond=0)
            verify_drift = (verify_time - verify_host).total_seconds()
            verify_weekday_ok = verify_weekday == verify_time.isoweekday()

            last_device = verify_time
            last_drift = verify_drift
            last_weekday_ok = verify_weekday_ok

            if (
                abs(verify_drift) <= VERIFY_TOLERANCE_SECONDS
                and verify_weekday_ok
            ):
                self.publish_status(
                    "synced",
                    host_time=verify_host,
                    device_time=verify_time,
                    drift_seconds=verify_drift,
                    corrected=True,
                    weekday_ok=True,
                    message=(
                        "Controller clock synchronized and readback verified"
                    ),
                )
                log(
                    f"PASS clock synchronized: "
                    f"{format_system_time(verify_time)} "
                    f"drift={verify_drift:+.0f}s"
                )
                return True

        verify_host = datetime.now().replace(microsecond=0)
        self.publish_status(
            "error",
            host_time=verify_host,
            device_time=last_device,
            drift_seconds=last_drift,
            corrected=True,
            weekday_ok=last_weekday_ok,
            message=(
                "Clock write could not be verified within "
                f"±{VERIFY_TOLERANCE_SECONDS}s"
            ),
        )
        raise RuntimeError(
            "clock readback verification failed: "
            f"device={last_device!s} drift={last_drift!r}s"
        )


def self_test() -> int:
    sample = datetime(2026, 10, 6, 9, 1, 2)
    encoded = encode_system_time(sample)
    expected = bytes.fromhex("2026100602090102")
    if encoded != expected:
        raise AssertionError(
            f"encode mismatch: {encoded.hex().upper()} != {expected.hex().upper()}"
        )
    decoded, weekday = decode_system_time(encoded)
    if decoded != sample or weekday != 2:
        raise AssertionError(
            f"decode mismatch: decoded={decoded!r} weekday={weekday}"
        )
    if format_system_time(sample) != "Di 06.10.2026 09:01:02":
        raise AssertionError("display formatting mismatch")

    for bad in (bytes.fromhex("20261A0602090102"), bytes.fromhex("2026100608090102")):
        try:
            decode_system_time(bad)
        except ValueError:
            pass
        else:
            raise AssertionError(f"invalid clock payload accepted: {bad.hex()}")

    print("CLOCK_SYNC_SELF_TESTS=5/5")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Synchronize WB2A system time 0x088E with this host"
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="read and publish status without writing",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="write current host time even when drift is below threshold",
    )
    parser.add_argument(
        "--threshold",
        type=int,
        default=DRIFT_THRESHOLD_SECONDS,
        help="write when absolute drift exceeds this many seconds (default: 30)",
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="run pure codec self-tests and exit",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.self_test:
        return self_test()
    if args.threshold < 0:
        raise SystemExit("--threshold must be >= 0")

    sync = ClockSync()
    sync.connect()
    try:
        return 0 if sync.synchronize(
            threshold=args.threshold,
            force=args.force,
            check_only=args.check,
        ) else 1
    except Exception as exc:
        log(f"ERROR: {exc}")
        try:
            host_time = datetime.now().replace(microsecond=0)
            sync.publish_status(
                "error",
                host_time=host_time,
                device_time=None,
                drift_seconds=None,
                corrected=False,
                weekday_ok=None,
                message=str(exc),
            )
        except Exception:
            pass
        return 1
    finally:
        sync.disconnect()


if __name__ == "__main__":
    raise SystemExit(main())
