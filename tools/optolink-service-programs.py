#!/opt/optolink/venv/bin/python
"""Guarded manager for the WB2A filling/venting service programs.

The Viessmann WB2A service manual defines coding address 2F as one shared
three-state service function:

  0 = service program off
  1 = venting program
  2 = filling program

For the local VDensHO1/20C2 profile, coding address 2F maps to Optolink
address 0x572F. This follows the same coding-memory mapping already used by
this project (for example 21 -> 0x5721, 23 -> 0x5723, 30 -> 0x5730) and is
also documented by public OpenV parameter tables.

Why a daemon instead of two direct Home Assistant writes?
----------------------------------------------------------
Home Assistant presents two switches because that is convenient for humans,
but the controller owns only one byte. This daemon is the single translation
layer between those two switches and the real three-state register. It:

- reads the current controller mode before every operation;
- never lets an OFF command for one switch cancel the *other* active mode;
- writes only the values 0, 1 or 2 to 0x572F;
- verifies every write with controller readback;
- restores the previous value if verification fails;
- polls the register so the automatic 20-minute controller reset is reflected
  back into Home Assistant;
- keeps all physical bus access serialized through the running
  optolink-splitter MQTT command/response interface.

The service manual states that both programs are service functions for trained
personnel. The Home Assistant dashboard therefore carries explicit safety and
operating notes; this daemon intentionally does not hide or weaken those
requirements.
"""

from __future__ import annotations

import argparse
import json
import queue
import sys
import threading
import time
from datetime import datetime, timezone
from typing import Any

APP_DIR = "/opt/optolink"
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from c_settings_adapter import settings  # type: ignore  # noqa: E402
from homeassistant_publish import connect_mqtt  # type: ignore  # noqa: E402

ADDR_SERVICE_PROGRAM = 0x572F

MODE_OFF = 0
MODE_VENTING = 1
MODE_FILLING = 2
VALID_MODES = {MODE_OFF, MODE_VENTING, MODE_FILLING}

REQUEST_TIMEOUT = 5.0
READBACK_DELAYS = (0.25, 0.75, 1.50)
POLL_SECONDS = 5.0
ACTION_QUEUE_SIZE = 20

MODE_TEXT = {
    MODE_OFF: "Aus",
    MODE_VENTING: "Entlüftung",
    MODE_FILLING: "Befüllung",
}
MODE_SLUG = {
    MODE_OFF: "off",
    MODE_VENTING: "venting",
    MODE_FILLING: "filling",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def log(message: str) -> None:
    print(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {message}", flush=True)


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


def parse_bool(payload: str) -> bool:
    value = payload.strip().lower()
    if value in {"1", "on", "true", "ein"}:
        return True
    if value in {"0", "off", "false", "aus"}:
        return False
    raise ValueError(f"unsupported switch payload: {payload!r}")


class ServiceProgramManager:
    """Translate two HA switches into the single guarded 0x572F mode byte."""

    def __init__(self) -> None:
        if not getattr(settings, "mqtt_broker", None):
            raise RuntimeError("MQTT is disabled in settings_ini.py")
        if not getattr(settings, "mqtt_listen", None):
            raise RuntimeError("mqtt_listen is disabled")
        if not getattr(settings, "mqtt_respond", None):
            raise RuntimeError("mqtt_respond is disabled")
        if not getattr(settings, "mqtt_topic", None):
            raise RuntimeError("mqtt_topic is not configured")

        self.base_topic = settings.mqtt_topic.rstrip("/")

        self.venting_command_topic = (
            f"{self.base_topic}/service_programs/venting/set"
        )
        self.filling_command_topic = (
            f"{self.base_topic}/service_programs/filling/set"
        )
        self.venting_state_topic = (
            f"{self.base_topic}/service_programs/venting/state"
        )
        self.filling_state_topic = (
            f"{self.base_topic}/service_programs/filling/state"
        )
        self.status_topic = f"{self.base_topic}/service_programs/status"
        self.availability_topic = (
            f"{self.base_topic}/service_programs/availability"
        )

        self.client = None
        self.actions: queue.Queue[tuple[str, bool]] = queue.Queue(
            maxsize=ACTION_QUEUE_SIZE
        )
        self.response_cond = threading.Condition()
        self.response_seq = 0
        self.responses: list[tuple[int, str]] = []
        self.stop_event = threading.Event()

        self.last_mode: int | None = None
        self.last_operation = "startup"
        self.last_message = "Noch kein Controller-Read"

    def connect(self) -> None:
        self.client = connect_mqtt(retries=10, delay=3)
        if self.client is None:
            raise RuntimeError("MQTT connection failed")

        self.client.on_message = self.on_message
        self.client.subscribe(
            [
                (settings.mqtt_respond, 0),
                (self.venting_command_topic, 0),
                (self.filling_command_topic, 0),
            ]
        )
        time.sleep(0.5)
        self.client.publish(
            self.availability_topic, "online", retain=True
        ).wait_for_publish()

        log(
            "service-program manager active; "
            f"venting={self.venting_command_topic}; "
            f"filling={self.filling_command_topic}; "
            f"address=0x{ADDR_SERVICE_PROGRAM:04X}"
        )

    def disconnect(self) -> None:
        if self.client is None:
            return
        try:
            self.client.publish(
                self.availability_topic, "offline", retain=True
            ).wait_for_publish()
        except Exception:
            pass
        try:
            self.client.loop_stop()
        finally:
            self.client.disconnect()

    def on_message(self, client, userdata, message) -> None:  # noqa: ANN001
        payload = message.payload.decode(errors="replace").strip()

        if message.topic == settings.mqtt_respond:
            with self.response_cond:
                self.response_seq += 1
                self.responses.append((self.response_seq, payload))
                if len(self.responses) > 100:
                    self.responses = self.responses[-100:]
                self.response_cond.notify_all()
            return

        if getattr(message, "retain", False):
            log(f"WARNING: ignoring retained command on {message.topic}")
            return

        if message.topic == self.venting_command_topic:
            kind = "venting"
        elif message.topic == self.filling_command_topic:
            kind = "filling"
        else:
            return

        try:
            enabled = parse_bool(payload)
        except ValueError as exc:
            log(f"WARNING: {exc}")
            return

        try:
            self.actions.put_nowait((kind, enabled))
        except queue.Full:
            log("WARNING: service-program action queue is full; command ignored")

    def request(
        self,
        command: str,
        *,
        expected_addr: int = ADDR_SERVICE_PROGRAM,
        timeout: float = REQUEST_TIMEOUT,
    ) -> str:
        # mqtt_respond is shared by all local helpers. Remember the response
        # sequence at send time and accept only a newer response for 0x572F.
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
                        f"timeout waiting for 0x{expected_addr:04X} "
                        f"after {command}"
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

    def read_mode(self) -> int:
        response = self.request(
            f"r;0x{ADDR_SERVICE_PROGRAM:04X};1;1;False"
        )
        raw = self.response_value(response)
        try:
            value = int(raw, 0)
        except ValueError as exc:
            raise RuntimeError(
                f"unexpected 0x{ADDR_SERVICE_PROGRAM:04X} payload: {raw!r}"
            ) from exc

        if value not in VALID_MODES:
            raise RuntimeError(
                f"unexpected service-program value {value} at "
                f"0x{ADDR_SERVICE_PROGRAM:04X}; expected 0, 1 or 2"
            )
        return value

    def write_mode(self, target: int, *, old_mode: int) -> int:
        if target not in VALID_MODES:
            raise ValueError(f"invalid service-program mode: {target}")

        ack_error: Exception | None = None
        response: str | None = None

        try:
            response = self.request(
                f"w;0x{ADDR_SERVICE_PROGRAM:04X};1;{target}"
            )
            if not response.startswith("1;"):
                ack_error = RuntimeError(
                    f"non-success transport response: {response}"
                )
        except Exception as exc:  # noqa: BLE001
            ack_error = exc

        for delay in READBACK_DELAYS:
            time.sleep(delay)
            try:
                actual = self.read_mode()
            except Exception as exc:  # noqa: BLE001
                log(f"WARNING: service-program readback failed: {exc}")
                continue

            if actual == target:
                if ack_error is not None:
                    log(
                        "write verified by controller readback despite "
                        f"transport warning: {ack_error}"
                    )
                return actual

        # The controller state is authoritative. If the target could not be
        # proven, restore the value observed before the attempted transition.
        restore_error: Exception | None = None
        try:
            self.request(
                f"w;0x{ADDR_SERVICE_PROGRAM:04X};1;{old_mode}"
            )
            time.sleep(0.5)
            restored = self.read_mode()
            if restored != old_mode:
                restore_error = RuntimeError(
                    f"restore readback={restored}, expected={old_mode}"
                )
        except Exception as exc:  # noqa: BLE001
            restore_error = exc

        details = []
        if ack_error is not None:
            details.append(f"transport={ack_error}")
        if response is not None:
            details.append(f"response={response}")
        if restore_error is not None:
            details.append(f"restore={restore_error}")

        suffix = "; ".join(details) if details else "no matching readback"
        raise RuntimeError(
            f"0x{ADDR_SERVICE_PROGRAM:04X}: mode {target} could not be "
            f"verified ({suffix})"
        )

    def publish_state(
        self,
        mode: int,
        *,
        operation: str | None = None,
        message: str | None = None,
    ) -> None:
        if operation is not None:
            self.last_operation = operation
        if message is not None:
            self.last_message = message

        payload: dict[str, Any] = {
            "state": MODE_SLUG[mode],
            "mode": mode,
            "text": MODE_TEXT[mode],
            "address": f"0x{ADDR_SERVICE_PROGRAM:04X}",
            "venting": mode == MODE_VENTING,
            "filling": mode == MODE_FILLING,
            "updated_at": utc_now(),
            "last_operation": self.last_operation,
            "message": self.last_message,
            "manual_coding_address": "2F",
        }

        self.client.publish(
            self.venting_state_topic,
            "ON" if mode == MODE_VENTING else "OFF",
            retain=True,
        ).wait_for_publish()
        self.client.publish(
            self.filling_state_topic,
            "ON" if mode == MODE_FILLING else "OFF",
            retain=True,
        ).wait_for_publish()
        self.client.publish(
            self.status_topic,
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
            retain=True,
        ).wait_for_publish()

        self.last_mode = mode

    def publish_error(self, message: str) -> None:
        payload = {
            "state": "error",
            "mode": self.last_mode,
            "text": "Fehler",
            "address": f"0x{ADDR_SERVICE_PROGRAM:04X}",
            "updated_at": utc_now(),
            "last_operation": self.last_operation,
            "message": message,
            "manual_coding_address": "2F",
        }
        self.client.publish(
            self.status_topic,
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
            retain=True,
        ).wait_for_publish()

    def apply_action(self, kind: str, enabled: bool) -> None:
        requested_mode = (
            MODE_VENTING if kind == "venting" else MODE_FILLING
        )
        label = MODE_TEXT[requested_mode]
        current = self.read_mode()

        if enabled:
            target = requested_mode
            operation = f"{kind}_on"
        else:
            # One register backs both switches. An OFF event must not stop the
            # other mode if Home Assistant sends it while that other mode is
            # currently active.
            if current != requested_mode:
                self.publish_state(
                    current,
                    operation=f"{kind}_off_noop",
                    message=(
                        f"{label} war nicht aktiv; Controller unverändert"
                    ),
                )
                return
            target = MODE_OFF
            operation = f"{kind}_off"

        if current == target:
            self.publish_state(
                current,
                operation=f"{operation}_noop",
                message=f"Controller bereits auf {MODE_TEXT[current]}",
            )
            return

        log(
            f"service-program transition: {MODE_TEXT[current]} ({current}) "
            f"-> {MODE_TEXT[target]} ({target})"
        )
        actual = self.write_mode(target, old_mode=current)
        self.publish_state(
            actual,
            operation=operation,
            message=(
                f"2F:{actual} ({MODE_TEXT[actual]}) durch Readback bestätigt"
            ),
        )

    def run(self) -> None:
        self.connect()
        next_poll = 0.0

        try:
            while not self.stop_event.is_set():
                timeout = max(0.1, min(1.0, next_poll - time.monotonic()))
                try:
                    kind, enabled = self.actions.get(timeout=timeout)
                except queue.Empty:
                    kind = None
                    enabled = None

                if kind is not None and enabled is not None:
                    try:
                        self.apply_action(kind, enabled)
                    except Exception as exc:  # noqa: BLE001
                        log(f"ERROR: service-program command failed: {exc}")
                        self.publish_error(str(exc))
                    next_poll = 0.0

                now = time.monotonic()
                if now >= next_poll:
                    try:
                        mode = self.read_mode()
                        if mode != self.last_mode:
                            reason = (
                                "Controllerzustand gelesen"
                                if self.last_mode is None
                                else "Controllerzustand geändert"
                            )
                            self.publish_state(
                                mode,
                                operation="poll",
                                message=reason,
                            )
                    except Exception as exc:  # noqa: BLE001
                        log(f"WARNING: service-program poll failed: {exc}")
                        self.publish_error(str(exc))
                    next_poll = now + POLL_SECONDS
        finally:
            self.disconnect()


def self_test() -> int:
    assert parse_bool("ON") is True
    assert parse_bool("ein") is True
    assert parse_bool("0") is False
    assert MODE_TEXT[MODE_OFF] == "Aus"
    assert MODE_TEXT[MODE_VENTING] == "Entlüftung"
    assert MODE_TEXT[MODE_FILLING] == "Befüllung"
    assert ADDR_SERVICE_PROGRAM == 0x572F
    print("SERVICE_PROGRAM_SELF_TESTS=7/7")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Guarded WB2A filling/venting service-program manager "
            "for coding address 2F / Optolink 0x572F"
        )
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="run pure parser/mapping self-tests and exit",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.self_test:
        return self_test()

    manager = ServiceProgramManager()
    try:
        manager.run()
    except KeyboardInterrupt:
        return 0
    except Exception as exc:
        log(f"FATAL: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
