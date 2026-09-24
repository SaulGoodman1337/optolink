#!/opt/optolink/venv/bin/python
"""MQTT API for the guarded Optolink maintenance core."""

from __future__ import annotations

import json
import queue
import re
import signal
import sys
import threading
import time
from collections import deque
from datetime import datetime, timezone
from typing import Any

APP_DIR = "/opt/optolink"
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from c_settings_adapter import settings  # type: ignore  # noqa: E402
from homeassistant_publish import connect_mqtt  # type: ignore  # noqa: E402
from optolink_maintenance_core import (  # type: ignore  # noqa: E402
    MaintenanceError,
    get_status,
    reset_maintenance,
    set_hours,
    set_months,
)

API_VERSION = 1
REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
QUEUE_SIZE = 50
RESULT_CACHE_SIZE = 100


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def log(message: str) -> None:
    print(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {message}", flush=True)


def require_bool(payload: dict[str, Any], key: str, default: bool = False) -> bool:
    value = payload.get(key, default)
    if not isinstance(value, bool):
        raise MaintenanceError(
            f"{key} must be a JSON boolean",
            code="invalid_request",
            details={"field": key},
        )
    return value


def require_int(payload: dict[str, Any], key: str) -> int:
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise MaintenanceError(
            f"{key} must be a JSON integer",
            code="invalid_request",
            details={"field": key},
        )
    return value


class MaintenanceApi:
    def __init__(self) -> None:
        if not getattr(settings, "mqtt_broker", None):
            raise RuntimeError("MQTT is disabled in settings_ini.py")
        if not getattr(settings, "mqtt_topic", None):
            raise RuntimeError("mqtt_topic is not configured")

        self.base_topic = settings.mqtt_topic.rstrip("/")
        self.command_topic = f"{self.base_topic}/maintenance/cmnd"
        self.result_topic = f"{self.base_topic}/maintenance/result"
        self.state_topic = f"{self.base_topic}/maintenance/state"
        self.availability_topic = f"{self.base_topic}/maintenance/availability"

        self.client = None
        self.actions: queue.Queue[str] = queue.Queue(maxsize=QUEUE_SIZE)
        self.stop_event = threading.Event()
        self.recent_ids: deque[str] = deque()
        self.recent_results: dict[str, dict[str, Any]] = {}

    def connect(self) -> None:
        self.client = connect_mqtt(retries=10, delay=3)
        if self.client is None:
            raise RuntimeError("MQTT connection failed")

        self.client.on_message = self.on_message
        self.client.subscribe(self.command_topic)
        time.sleep(0.5)
        self.client.publish(self.availability_topic, "online", retain=True)
        log(
            f"listening on {self.command_topic}; "
            f"result={self.result_topic}; state={self.state_topic}"
        )

    def on_message(self, client, userdata, message) -> None:  # noqa: ANN001
        if message.topic != self.command_topic:
            return

        raw = message.payload.decode(errors="replace")
        try:
            self.actions.put_nowait(raw)
        except queue.Full:
            log("WARNING: maintenance request queue is full; dropping request")

    def cache_result(self, request_id: str, result: dict[str, Any]) -> None:
        if request_id not in self.recent_results:
            self.recent_ids.append(request_id)
        self.recent_results[request_id] = result

        while len(self.recent_ids) > RESULT_CACHE_SIZE:
            old = self.recent_ids.popleft()
            self.recent_results.pop(old, None)

    def publish_result(self, result: dict[str, Any]) -> None:
        self.client.publish(
            self.result_topic,
            json.dumps(result, sort_keys=True, separators=(",", ":")),
            retain=False,
        )

    def publish_state(self, status: dict[str, Any]) -> None:
        since = status["burner_since_reference"]["hours"]
        state = {
            "api_version": API_VERSION,
            "updated_at": utc_now(),
            "hours_threshold": status["hours_threshold"]["hours"],
            "hours_threshold_raw": status["hours_threshold"]["raw"],
            "interval_months": status["interval"]["months"],
            "maintenance_state": status["maintenance_state"]["raw"],
            "maintenance_state_text": status["maintenance_state"]["text"],
            "interval_reference_raw": status["interval_reference"]["raw_hex"],
            "interval_reference_uint": status["interval_reference"]["raw_uint_le"],
            "burner_reference_raw": status["burner_reference"]["raw_hex"],
            "burner_reference_seconds": status["burner_reference"][
                "burner_seconds_baseline"
            ],
            "burner_total_seconds": status["burner_total"]["seconds"],
            "burner_total_hours": status["burner_total"]["hours"],
            "burner_since_reference_hours": since,
            "burner_starts": status["burner_starts"]["count"],
        }
        self.client.publish(
            self.state_topic,
            json.dumps(state, sort_keys=True, separators=(",", ":")),
            retain=True,
        )

    def parse_request(self, raw: str) -> dict[str, Any]:
        if len(raw) > 16384:
            raise MaintenanceError(
                "request payload too large",
                code="invalid_request",
            )
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise MaintenanceError(
                "request payload is not valid JSON",
                code="invalid_json",
                details={"position": exc.pos},
            ) from exc

        if not isinstance(payload, dict):
            raise MaintenanceError(
                "request payload must be a JSON object",
                code="invalid_request",
            )

        version = payload.get("api_version", API_VERSION)
        if version != API_VERSION:
            raise MaintenanceError(
                f"unsupported api_version: {version!r}",
                code="unsupported_api_version",
                details={"supported": API_VERSION},
            )

        request_id = payload.get("request_id")
        if not isinstance(request_id, str) or not REQUEST_ID_RE.fullmatch(
            request_id
        ):
            raise MaintenanceError(
                "request_id must match [A-Za-z0-9._:-]{1,128}",
                code="invalid_request_id",
            )

        action = payload.get("action")
        if action not in {"status", "set_hours", "set_months", "reset"}:
            raise MaintenanceError(
                f"unsupported action: {action!r}",
                code="unsupported_action",
            )

        return payload

    def execute(self, payload: dict[str, Any]) -> dict[str, Any]:
        action = payload["action"]

        if action == "status":
            data = get_status(quiet=True)
            return {
                "action": action,
                "data": data,
                "status": data,
            }

        if action == "set_hours":
            value = require_int(payload, "value")
            data = set_hours(
                value,
                confirm_reference_change=require_bool(
                    payload,
                    "confirm_reference_change",
                ),
                force=require_bool(payload, "force"),
                quiet=True,
            )
            return {
                "action": action,
                "data": data,
                "status": data.get("status"),
            }

        if action == "set_months":
            value = require_int(payload, "value")
            data = set_months(
                value,
                confirm_reference_change=require_bool(
                    payload,
                    "confirm_reference_change",
                ),
                force=require_bool(payload, "force"),
                quiet=True,
            )
            return {
                "action": action,
                "data": data,
                "status": data.get("status"),
            }

        if action == "reset":
            data = reset_maintenance(
                confirm=require_bool(payload, "confirm"),
                quiet=True,
            )
            return {
                "action": action,
                "data": data,
                "status": data.get("after"),
            }

        raise MaintenanceError(
            f"unsupported action: {action}",
            code="unsupported_action",
        )

    def handle_raw_request(self, raw: str) -> None:
        request_id: str | None = None
        action: str | None = None

        try:
            payload = self.parse_request(raw)
            request_id = payload["request_id"]
            action = payload["action"]

            cached = self.recent_results.get(request_id)
            if cached is not None:
                log(f"duplicate request_id={request_id}; replaying cached result")
                replay = dict(cached)
                replay["deduplicated"] = True
                self.publish_result(replay)
                return

            executed = self.execute(payload)
            result = {
                "api_version": API_VERSION,
                "request_id": request_id,
                "ok": True,
                "action": action,
                "completed_at": utc_now(),
                "deduplicated": False,
                "data": executed["data"],
            }

            status = executed.get("status")
            if status:
                self.publish_state(status)

            self.cache_result(request_id, result)
            self.publish_result(result)
            log(f"request_id={request_id} action={action} OK")

        except MaintenanceError as exc:
            result = {
                "api_version": API_VERSION,
                "request_id": request_id,
                "ok": False,
                "action": action,
                "completed_at": utc_now(),
                "deduplicated": False,
                "error": str(exc),
                "code": exc.code,
                "details": exc.details,
            }
            if request_id is not None:
                self.cache_result(request_id, result)
            self.publish_result(result)
            log(
                f"request_id={request_id or '-'} action={action or '-'} "
                f"ERROR code={exc.code}: {exc}"
            )
        except Exception as exc:  # noqa: BLE001
            result = {
                "api_version": API_VERSION,
                "request_id": request_id,
                "ok": False,
                "action": action,
                "completed_at": utc_now(),
                "deduplicated": False,
                "error": str(exc),
                "code": "internal_error",
                "details": {},
            }
            if request_id is not None:
                self.cache_result(request_id, result)
            self.publish_result(result)
            log(
                f"request_id={request_id or '-'} action={action or '-'} "
                f"INTERNAL ERROR: {exc}"
            )

    def publish_initial_state(self) -> None:
        try:
            status = get_status(quiet=True)
            self.publish_state(status)
            log("published initial maintenance state")
        except Exception as exc:  # noqa: BLE001
            log(f"WARNING: initial maintenance status failed: {exc}")

    def run(self) -> None:
        self.connect()
        self.publish_initial_state()

        try:
            while not self.stop_event.is_set():
                try:
                    raw = self.actions.get(timeout=0.5)
                except queue.Empty:
                    continue
                self.handle_raw_request(raw)
        finally:
            if self.client is not None:
                try:
                    self.client.publish(
                        self.availability_topic,
                        "offline",
                        retain=True,
                    ).wait_for_publish()
                except Exception:
                    pass
                self.client.loop_stop()
                self.client.disconnect()

    def stop(self) -> None:
        self.stop_event.set()


def main() -> int:
    api = MaintenanceApi()

    def stop_handler(signum, frame) -> None:  # noqa: ANN001
        api.stop()

    signal.signal(signal.SIGTERM, stop_handler)
    signal.signal(signal.SIGINT, stop_handler)

    api.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
