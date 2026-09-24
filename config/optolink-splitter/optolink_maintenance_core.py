"""Shared guarded maintenance core for VDensHO1 / 20C2 / SW03.

This module is the single implementation used by both the root-operated CLI
and the MQTT maintenance API. It intentionally exposes only the controller
operations that were verified on the local WB2A appliance.
"""

from __future__ import annotations

import contextlib
import fcntl
import os
import sys
import time
from dataclasses import dataclass
from typing import Any, Callable

APP_DIR = "/opt/optolink"
LOCK_PATH = os.path.join(APP_DIR, ".maintenance.lock")

if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from c_settings_adapter import settings  # type: ignore  # noqa: E402
from homeassistant_publish import connect_mqtt  # type: ignore  # noqa: E402

ADDR_HOURS_THRESHOLD = 0x5721
ADDR_INTERVAL_MONTHS = 0x5723
ADDR_MAINTENANCE_STATE = 0x5724
ADDR_INTERVAL_REFERENCE = 0x756C
ADDR_BURNER_REFERENCE = 0x7570
ADDR_BURNER_TOTAL = 0x08A7
ADDR_BURNER_STARTS = 0x088A

RESET_CONFIRMATION = "RESET-WARTUNG"
MONTH_REFERENCE_CONFIRMATION = "RESET-ZEITREFERENZ"
HOURS_REFERENCE_CONFIRMATION = "RESET-BRENNERREFERENZ"


class MaintenanceError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        code: str = "maintenance_error",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.details = details or {}


@dataclass
class MqttSession:
    client: Any
    responses: list[str]

    def close(self) -> None:
        self.client.loop_stop()
        self.client.disconnect()


def _command_addr(command: str) -> int | None:
    parts = command.split(";")
    if len(parts) < 2:
        return None
    try:
        return int(parts[1], 0)
    except ValueError:
        return None


def _response_addr(response: str) -> int | None:
    parts = response.split(";")
    if len(parts) < 2:
        return None
    try:
        return int(parts[1], 0)
    except ValueError:
        return None


def connect(*, quiet: bool = False) -> MqttSession:
    if not getattr(settings, "mqtt_listen", None):
        raise MaintenanceError("mqtt_listen is disabled", code="mqtt_disabled")
    if not getattr(settings, "mqtt_respond", None):
        raise MaintenanceError("mqtt_respond is disabled", code="mqtt_disabled")

    redirect = contextlib.redirect_stdout(sys.stderr) if quiet else contextlib.nullcontext()
    with redirect:
        client = connect_mqtt(retries=2, delay=1)

    if client is None:
        raise MaintenanceError("MQTT connection failed", code="mqtt_connect_failed")

    responses: list[str] = []

    def on_message(client, userdata, message):  # noqa: ANN001
        if message.topic == settings.mqtt_respond:
            responses.append(message.payload.decode(errors="replace"))
            if len(responses) > 100:
                del responses[:-100]

    client.on_message = on_message
    client.subscribe(settings.mqtt_respond)
    time.sleep(0.4)
    return MqttSession(client=client, responses=responses)


def request(
    session: MqttSession,
    command: str,
    *,
    timeout: float,
    verbose: bool,
    label: str | None = None,
) -> str:
    session.responses.clear()
    expected_addr = _command_addr(command)
    prefix = label or command

    if verbose:
        print(f"{prefix:<24} -> {settings.mqtt_listen}: {command}", file=sys.stderr)

    session.client.publish(settings.mqtt_listen, command).wait_for_publish()

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        while session.responses:
            candidate = session.responses.pop(0)
            if expected_addr is None or _response_addr(candidate) == expected_addr:
                if verbose:
                    print(
                        f"{prefix:<24} <- {settings.mqtt_respond}: {candidate}",
                        file=sys.stderr,
                    )
                return candidate
        time.sleep(0.05)

    raise MaintenanceError(
        f"timeout waiting for response to: {command}",
        code="splitter_timeout",
        details={"command": command},
    )


def _payload(response: str, expected_addr: int) -> str:
    parts = response.split(";")
    if len(parts) < 3:
        raise MaintenanceError(
            f"malformed splitter response: {response!r}",
            code="malformed_response",
        )
    if parts[0] != "1":
        raise MaintenanceError(
            f"splitter returned failure response: {response!r}",
            code="splitter_failure",
        )

    try:
        response_addr = int(parts[1], 0)
    except ValueError as exc:
        raise MaintenanceError(
            f"invalid response address: {response!r}",
            code="malformed_response",
        ) from exc

    if response_addr != expected_addr:
        raise MaintenanceError(
            f"unexpected response address 0x{response_addr:04X}; "
            f"expected 0x{expected_addr:04X}",
            code="unexpected_response",
        )
    return parts[2].strip()


def read_raw(
    session: MqttSession,
    address: int,
    length: int,
    *,
    timeout: float,
    verbose: bool,
) -> str:
    response = request(
        session,
        f"r;0x{address:04X};{length};raw;False",
        timeout=timeout,
        verbose=verbose,
        label=f"READ 0x{address:04X}",
    )
    raw = _payload(response, address).lower()
    if len(raw) != length * 2:
        raise MaintenanceError(
            f"0x{address:04X}: expected {length} raw bytes, received {raw!r}",
            code="invalid_raw_length",
        )
    try:
        bytes.fromhex(raw)
    except ValueError as exc:
        raise MaintenanceError(
            f"0x{address:04X}: invalid raw hex payload {raw!r}",
            code="invalid_raw_payload",
        ) from exc
    return raw


def read_uint_le(
    session: MqttSession,
    address: int,
    length: int,
    *,
    timeout: float,
    verbose: bool,
) -> tuple[int, str]:
    raw = read_raw(
        session,
        address,
        length,
        timeout=timeout,
        verbose=verbose,
    )
    return int.from_bytes(bytes.fromhex(raw), "little", signed=False), raw


def write_byte(
    session: MqttSession,
    address: int,
    value: int,
    *,
    timeout: float,
    verbose: bool,
) -> str:
    if not 0 <= value <= 0xFF:
        raise MaintenanceError(
            f"byte value out of range: {value}",
            code="invalid_value",
        )
    return request(
        session,
        f"w;0x{address:04X};1;{value}",
        timeout=timeout,
        verbose=verbose,
        label=f"WRITE 0x{address:04X}",
    )


def _restore_byte(
    session: MqttSession,
    address: int,
    old_value: int,
    *,
    timeout: float,
    settle: float,
    verbose: bool,
) -> dict[str, Any]:
    ack_error: Exception | None = None
    try:
        write_byte(
            session,
            address,
            old_value,
            timeout=timeout,
            verbose=verbose,
        )
    except Exception as exc:  # noqa: BLE001
        ack_error = exc

    time.sleep(settle)
    try:
        restored, _ = read_uint_le(
            session,
            address,
            1,
            timeout=timeout,
            verbose=verbose,
        )
    except Exception as read_exc:  # noqa: BLE001
        return {
            "attempted": True,
            "verified": False,
            "readback": None,
            "message": (
                f"rollback ACK failed ({ack_error}) and readback failed ({read_exc})"
                if ack_error is not None
                else f"rollback readback failed ({read_exc})"
            ),
        }

    verified = restored == old_value
    if verified and ack_error is not None:
        message = f"rollback verified despite ACK error ({ack_error})"
    elif verified:
        message = f"rollback verified ({restored})"
    elif ack_error is not None:
        message = (
            f"rollback ACK failed ({ack_error}); readback={restored}, "
            f"expected={old_value}"
        )
    else:
        message = f"rollback readback={restored}, expected={old_value}"

    return {
        "attempted": True,
        "verified": verified,
        "readback": restored,
        "message": message,
    }


def write_verify_byte(
    session: MqttSession,
    address: int,
    new_value: int,
    *,
    old_value: int | None,
    timeout: float,
    settle: float,
    verbose: bool,
) -> int:
    ack_error: Exception | None = None
    try:
        write_byte(
            session,
            address,
            new_value,
            timeout=timeout,
            verbose=verbose,
        )
    except Exception as exc:  # noqa: BLE001
        ack_error = exc

    time.sleep(settle)

    try:
        actual, _ = read_uint_le(
            session,
            address,
            1,
            timeout=timeout,
            verbose=verbose,
        )
    except Exception as read_exc:  # noqa: BLE001
        restore = None
        if old_value is not None:
            restore = _restore_byte(
                session,
                address,
                old_value,
                timeout=timeout,
                settle=settle,
                verbose=verbose,
            )
        raise MaintenanceError(
            f"0x{address:04X}: write could not be verified",
            code="write_verification_failed",
            details={
                "address": f"0x{address:04X}",
                "requested": new_value,
                "ack_error": str(ack_error) if ack_error is not None else None,
                "readback_error": str(read_exc),
                "configuration_restore": restore,
                "reference_side_effects_reversible": False,
            },
        ) from read_exc

    if actual == new_value:
        return actual

    restore = None
    if old_value is not None:
        restore = _restore_byte(
            session,
            address,
            old_value,
            timeout=timeout,
            settle=settle,
            verbose=verbose,
        )

    raise MaintenanceError(
        f"0x{address:04X}: readback {actual} != requested {new_value}",
        code="write_readback_mismatch",
        details={
            "address": f"0x{address:04X}",
            "requested": new_value,
            "readback": actual,
            "ack_error": str(ack_error) if ack_error is not None else None,
            "configuration_restore": restore,
            "reference_side_effects_reversible": False,
        },
    )


def snapshot(
    session: MqttSession,
    *,
    timeout: float,
    verbose: bool,
) -> dict[str, Any]:
    hours_threshold_raw, hours_threshold_hex = read_uint_le(
        session,
        ADDR_HOURS_THRESHOLD,
        1,
        timeout=timeout,
        verbose=verbose,
    )
    interval_months, interval_hex = read_uint_le(
        session,
        ADDR_INTERVAL_MONTHS,
        1,
        timeout=timeout,
        verbose=verbose,
    )
    maintenance_state, maintenance_hex = read_uint_le(
        session,
        ADDR_MAINTENANCE_STATE,
        1,
        timeout=timeout,
        verbose=verbose,
    )
    interval_reference, interval_reference_hex = read_uint_le(
        session,
        ADDR_INTERVAL_REFERENCE,
        4,
        timeout=timeout,
        verbose=verbose,
    )
    burner_reference, burner_reference_hex = read_uint_le(
        session,
        ADDR_BURNER_REFERENCE,
        4,
        timeout=timeout,
        verbose=verbose,
    )
    burner_total_seconds, burner_total_hex = read_uint_le(
        session,
        ADDR_BURNER_TOTAL,
        4,
        timeout=timeout,
        verbose=verbose,
    )
    burner_starts, burner_starts_hex = read_uint_le(
        session,
        ADDR_BURNER_STARTS,
        4,
        timeout=timeout,
        verbose=verbose,
    )

    burner_hours_since_reference: float | None = None
    if burner_reference > 0 and burner_total_seconds >= burner_reference:
        burner_hours_since_reference = (
            burner_total_seconds - burner_reference
        ) / 3600.0

    since_reference = {
        "hours": burner_hours_since_reference,
        "formula": "(0x08A7 - 0x7570) / 3600",
    }

    return {
        "hours_threshold": {
            "address": "0x5721",
            "raw_hex": hours_threshold_hex,
            "raw": hours_threshold_raw,
            "hours": hours_threshold_raw * 100,
        },
        "interval": {
            "address": "0x5723",
            "raw_hex": interval_hex,
            "months": interval_months,
        },
        "maintenance_state": {
            "address": "0x5724",
            "raw_hex": maintenance_hex,
            "raw": maintenance_state,
            "text": {0: "Grundzustand", 1: "Wartung"}.get(
                maintenance_state,
                f"Unbekannt ({maintenance_state})",
            ),
        },
        "interval_reference": {
            "address": "0x756C",
            "raw_hex": interval_reference_hex,
            "raw_uint_le": interval_reference,
            "conversion": "LastCheckInterval",
            "note": (
                "32-bit reference storage; exact wall-clock conversion "
                "is not yet reconstructed"
            ),
        },
        "burner_reference": {
            "address": "0x7570",
            "raw_hex": burner_reference_hex,
            "burner_seconds_baseline": burner_reference,
        },
        "burner_total": {
            "address": "0x08A7",
            "raw_hex": burner_total_hex,
            "seconds": burner_total_seconds,
            "hours": burner_total_seconds / 3600.0,
        },
        "burner_since_reference": since_reference,
        # Compatibility alias for the first CLI JSON version.
        "burner_since_maintenance": since_reference,
        "burner_starts": {
            "address": "0x088A",
            "raw_hex": burner_starts_hex,
            "count": burner_starts,
        },
    }


def _acquire_lock() -> Any:
    handle = open(LOCK_PATH, "a+", encoding="utf-8")
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as exc:
        handle.close()
        raise MaintenanceError(
            "maintenance interface busy",
            code="busy",
            details={"lock_path": LOCK_PATH},
        ) from exc
    return handle


def _with_session(
    operation: Callable[[MqttSession], dict[str, Any]],
    *,
    quiet: bool,
) -> dict[str, Any]:
    lock_handle = None
    session = None
    try:
        lock_handle = _acquire_lock()
        session = connect(quiet=quiet)
        return operation(session)
    finally:
        if session is not None:
            session.close()
        if lock_handle is not None:
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)
            lock_handle.close()


def get_status(
    *,
    timeout: float = 4.0,
    verbose: bool = False,
    quiet: bool = False,
) -> dict[str, Any]:
    return _with_session(
        lambda session: snapshot(
            session,
            timeout=timeout,
            verbose=verbose,
        ),
        quiet=quiet,
    )


def set_hours(
    hours: int,
    *,
    confirm_reference_change: bool = False,
    force: bool = False,
    timeout: float = 4.0,
    settle: float = 1.0,
    verbose: bool = False,
    quiet: bool = False,
) -> dict[str, Any]:
    if hours < 0 or hours > 10000 or hours % 100 != 0:
        raise MaintenanceError(
            "set-hours accepts 0..10000 h in exact 100 h steps",
            code="invalid_hours",
        )

    def operation(session: MqttSession) -> dict[str, Any]:
        requested_raw = hours // 100
        current_raw, current_hex = read_uint_le(
            session,
            ADDR_HOURS_THRESHOLD,
            1,
            timeout=timeout,
            verbose=verbose,
        )

        if current_raw == requested_raw and not force:
            return {
                "action": "set-hours",
                "changed": False,
                "reason": (
                    "already set; no write performed, burner reference preserved"
                ),
                "hours": hours,
                "raw_hex": current_hex,
                "status": snapshot(
                    session,
                    timeout=timeout,
                    verbose=verbose,
                ),
            }

        if not confirm_reference_change:
            raise MaintenanceError(
                "changing 0x5721 can re-baseline the burner-runtime "
                "maintenance reference at 0x7570",
                code="confirmation_required",
                details={
                    "required_confirmation": HOURS_REFERENCE_CONFIRMATION,
                    "reference": "0x7570",
                },
            )

        before_ref, before_ref_hex = read_uint_le(
            session,
            ADDR_BURNER_REFERENCE,
            4,
            timeout=timeout,
            verbose=verbose,
        )

        write_verify_byte(
            session,
            ADDR_HOURS_THRESHOLD,
            requested_raw,
            old_value=current_raw,
            timeout=timeout,
            settle=settle,
            verbose=verbose,
        )

        after_ref, after_ref_hex = read_uint_le(
            session,
            ADDR_BURNER_REFERENCE,
            4,
            timeout=timeout,
            verbose=verbose,
        )

        return {
            "action": "set-hours",
            "changed": True,
            "previous_hours": current_raw * 100,
            "hours": hours,
            "raw": requested_raw,
            "burner_reference_changed": after_ref != before_ref,
            "burner_reference_before": {
                "raw_hex": before_ref_hex,
                "burner_seconds_baseline": before_ref,
            },
            "burner_reference_after": {
                "raw_hex": after_ref_hex,
                "burner_seconds_baseline": after_ref,
            },
            "status": snapshot(
                session,
                timeout=timeout,
                verbose=verbose,
            ),
        }

    return _with_session(operation, quiet=quiet)


def set_months(
    months: int,
    *,
    confirm_reference_change: bool = False,
    force: bool = False,
    timeout: float = 4.0,
    settle: float = 1.0,
    verbose: bool = False,
    quiet: bool = False,
) -> dict[str, Any]:
    if months < 0 or months > 24:
        raise MaintenanceError(
            "set-months accepts 0..24 months",
            code="invalid_months",
        )

    def operation(session: MqttSession) -> dict[str, Any]:
        current_raw, current_hex = read_uint_le(
            session,
            ADDR_INTERVAL_MONTHS,
            1,
            timeout=timeout,
            verbose=verbose,
        )

        if current_raw == months and not force:
            return {
                "action": "set-months",
                "changed": False,
                "reason": (
                    "already set; no write performed, interval reference preserved"
                ),
                "months": months,
                "raw_hex": current_hex,
                "status": snapshot(
                    session,
                    timeout=timeout,
                    verbose=verbose,
                ),
            }

        if not confirm_reference_change:
            raise MaintenanceError(
                "changing 0x5723 re-baselines the maintenance time "
                "reference at 0x756C",
                code="confirmation_required",
                details={
                    "required_confirmation": MONTH_REFERENCE_CONFIRMATION,
                    "reference": "0x756C",
                },
            )

        before_ref, before_ref_hex = read_uint_le(
            session,
            ADDR_INTERVAL_REFERENCE,
            4,
            timeout=timeout,
            verbose=verbose,
        )

        write_verify_byte(
            session,
            ADDR_INTERVAL_MONTHS,
            months,
            old_value=current_raw,
            timeout=timeout,
            settle=settle,
            verbose=verbose,
        )

        after_ref, after_ref_hex = read_uint_le(
            session,
            ADDR_INTERVAL_REFERENCE,
            4,
            timeout=timeout,
            verbose=verbose,
        )

        return {
            "action": "set-months",
            "changed": True,
            "previous_months": current_raw,
            "months": months,
            "interval_reference_changed": after_ref != before_ref,
            "interval_reference_before": {
                "raw_hex": before_ref_hex,
                "raw_uint_le": before_ref,
            },
            "interval_reference_after": {
                "raw_hex": after_ref_hex,
                "raw_uint_le": after_ref,
            },
            "status": snapshot(
                session,
                timeout=timeout,
                verbose=verbose,
            ),
        }

    return _with_session(operation, quiet=quiet)


def reset_maintenance(
    *,
    confirm: bool = False,
    timeout: float = 4.0,
    settle: float = 1.0,
    verbose: bool = False,
    quiet: bool = False,
) -> dict[str, Any]:
    if not confirm:
        raise MaintenanceError(
            "maintenance reset requires explicit confirmation",
            code="confirmation_required",
            details={"required_confirmation": RESET_CONFIRMATION},
        )

    def operation(session: MqttSession) -> dict[str, Any]:
        before = snapshot(
            session,
            timeout=timeout,
            verbose=verbose,
        )
        attempted_state_one = False
        primary_error: Exception | None = None

        try:
            attempted_state_one = True
            write_byte(
                session,
                ADDR_MAINTENANCE_STATE,
                1,
                timeout=timeout,
                verbose=verbose,
            )
            time.sleep(settle)

            state_one, _ = read_uint_le(
                session,
                ADDR_MAINTENANCE_STATE,
                1,
                timeout=timeout,
                verbose=verbose,
            )
            if state_one != 1:
                raise MaintenanceError(
                    f"0x5724 did not enter Wartung state; readback={state_one}",
                    code="reset_state_mismatch",
                )
        except Exception as exc:  # noqa: BLE001
            primary_error = exc
        finally:
            if attempted_state_one:
                restore_ack_error: Exception | None = None
                try:
                    write_byte(
                        session,
                        ADDR_MAINTENANCE_STATE,
                        0,
                        timeout=timeout,
                        verbose=verbose,
                    )
                except Exception as exc:  # noqa: BLE001
                    restore_ack_error = exc

                time.sleep(settle)
                try:
                    restored, _ = read_uint_le(
                        session,
                        ADDR_MAINTENANCE_STATE,
                        1,
                        timeout=timeout,
                        verbose=verbose,
                    )
                except Exception as read_exc:  # noqa: BLE001
                    raise MaintenanceError(
                        "SAFETY ERROR: could not verify 0x5724=0 after reset",
                        code="reset_safety_restore_failed",
                        details={
                            "ack_error": (
                                str(restore_ack_error)
                                if restore_ack_error is not None
                                else None
                            ),
                            "readback_error": str(read_exc),
                        },
                    ) from read_exc

                if restored != 0:
                    raise MaintenanceError(
                        "SAFETY ERROR: 0x5724 did not return to 0",
                        code="reset_safety_restore_failed",
                        details={
                            "readback": restored,
                            "ack_error": (
                                str(restore_ack_error)
                                if restore_ack_error is not None
                                else None
                            ),
                        },
                    )

        if primary_error is not None:
            raise MaintenanceError(
                f"maintenance reset aborted after safety restore: {primary_error}",
                code="reset_aborted",
            ) from primary_error

        after = snapshot(
            session,
            timeout=timeout,
            verbose=verbose,
        )

        warnings: list[str] = []
        if after["burner_total"]["seconds"] < before["burner_total"]["seconds"]:
            warnings.append(
                "total burner-runtime counter decreased unexpectedly"
            )
        if after["burner_starts"]["count"] < before["burner_starts"]["count"]:
            warnings.append(
                "total burner-start counter decreased unexpectedly"
            )

        burner_ref_before = before["burner_reference"][
            "burner_seconds_baseline"
        ]
        burner_ref_after = after["burner_reference"][
            "burner_seconds_baseline"
        ]
        burner_total = after["burner_total"]["seconds"]
        burner_reference_changed = burner_ref_after != burner_ref_before

        if burner_ref_after > burner_total:
            warnings.append(
                "burner maintenance reference is above total runtime"
            )
        elif burner_ref_after > 0 and burner_total - burner_ref_after > 300:
            warnings.append(
                "burner maintenance reference is more than 300 s "
                "behind total runtime"
            )

        ref_after = after["interval_reference"]["raw_uint_le"]
        ref_before = before["interval_reference"]["raw_uint_le"]
        interval_reference_changed = ref_after != ref_before
        if ref_after <= 0:
            warnings.append("new interval reference is not set")
        elif not interval_reference_changed:
            warnings.append(
                "interval reference did not change during maintenance reset"
            )

        notes: list[str] = []
        if burner_reference_changed:
            notes.append("0x7570 burner reference was re-baselined")
        elif before["hours_threshold"]["hours"] == 0:
            notes.append(
                "0x7570 burner reference remained unchanged while the "
                "burner-hours maintenance threshold was 0 h; this is an "
                "observed valid controller state"
            )
        else:
            notes.append(
                "0x7570 burner reference remained unchanged despite a "
                "nonzero burner-hours maintenance threshold"
            )

        if interval_reference_changed:
            notes.append("0x756C interval reference was re-baselined")

        return {
            "action": "reset",
            "changed": True,
            "sequence": "0x5724: 1 -> 0",
            "reference_changes": {
                "interval_0x756C": interval_reference_changed,
                "burner_0x7570": burner_reference_changed,
            },
            "before": before,
            "after": after,
            "notes": notes,
            "warnings": warnings,
        }

    return _with_session(operation, quiet=quiet)
