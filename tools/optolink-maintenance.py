#!/opt/optolink/venv/bin/python
"""Guarded maintenance/service CLI for the verified WB2A / VDensHO1 profile.

The commands in this tool are intentionally limited to maintenance operations
that were hardware-verified on the local VDensHO1 / 20C2 / SW03 appliance.

Verified controller semantics:
  0x5721  R/W burner-runtime maintenance threshold, raw * 100 h
  0x5723  R/W maintenance interval, raw months (0..24)
           IMPORTANT: every write re-baselines 0x756C
  0x5724  maintenance state; verified maintenance reset sequence 1 -> 0
  0x756C  read-only LastCheckInterval reference (little-endian Unix seconds)
  0x7570  read-only LastBurnerCheck baseline (burner-runtime seconds)
  0x08A7  total burner runtime, seconds
  0x088A  total burner starts

This is not a generic raw Optolink writer. It rejects values and operations
outside the locally verified maintenance contract.
"""

from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import fcntl
import json
import os
import sys
import time
from dataclasses import dataclass
from typing import Any

APP_DIR = "/opt/optolink"
LOCK_PATH = "/run/lock/optolink-maintenance.lock"

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


class MaintenanceError(RuntimeError):
    pass


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


def connect(*, json_mode: bool) -> MqttSession:
    if not getattr(settings, "mqtt_listen", None):
        raise MaintenanceError("mqtt_listen is disabled")
    if not getattr(settings, "mqtt_respond", None):
        raise MaintenanceError("mqtt_respond is disabled")

    # connect_mqtt() emits human-readable status lines. Keep stdout clean when
    # --json is requested so callers can parse the JSON deterministically.
    redirect = contextlib.redirect_stdout(sys.stderr) if json_mode else contextlib.nullcontext()
    with redirect:
        client = connect_mqtt(retries=2, delay=1)

    if client is None:
        raise MaintenanceError("MQTT connection failed")

    responses: list[str] = []

    def on_message(client, userdata, message):  # noqa: ANN001
        if message.topic == settings.mqtt_respond:
            responses.append(message.payload.decode(errors="replace"))

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

    deadline = time.time() + timeout
    while time.time() < deadline:
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

    raise MaintenanceError(f"timeout waiting for response to: {command}")


def _payload(response: str, expected_addr: int) -> str:
    parts = response.split(";")
    if len(parts) < 3:
        raise MaintenanceError(f"malformed splitter response: {response!r}")
    if parts[0] != "1":
        raise MaintenanceError(f"splitter returned failure response: {response!r}")

    try:
        response_addr = int(parts[1], 0)
    except ValueError as exc:
        raise MaintenanceError(f"invalid response address: {response!r}") from exc

    if response_addr != expected_addr:
        raise MaintenanceError(
            f"unexpected response address 0x{response_addr:04X}; expected 0x{expected_addr:04X}"
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
            f"0x{address:04X}: expected {length} raw bytes, received {raw!r}"
        )
    try:
        bytes.fromhex(raw)
    except ValueError as exc:
        raise MaintenanceError(f"0x{address:04X}: invalid raw hex payload {raw!r}") from exc
    return raw


def read_uint_le(
    session: MqttSession,
    address: int,
    length: int,
    *,
    timeout: float,
    verbose: bool,
) -> tuple[int, str]:
    raw = read_raw(session, address, length, timeout=timeout, verbose=verbose)
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
        raise MaintenanceError(f"byte value out of range: {value}")
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
) -> str:
    ack_error: Exception | None = None
    try:
        write_byte(session, address, old_value, timeout=timeout, verbose=verbose)
    except Exception as exc:  # noqa: BLE001 - readback is authoritative
        ack_error = exc

    time.sleep(settle)
    try:
        restored, _ = read_uint_le(
            session, address, 1, timeout=timeout, verbose=verbose
        )
    except Exception as read_exc:  # noqa: BLE001
        if ack_error is not None:
            return f"rollback ACK failed ({ack_error}) and readback failed ({read_exc})"
        return f"rollback readback failed ({read_exc})"

    if restored == old_value:
        if ack_error is not None:
            return f"rollback verified despite ACK error ({ack_error})"
        return f"rollback verified ({restored})"

    if ack_error is not None:
        return (
            f"rollback ACK failed ({ack_error}); readback={restored}, "
            f"expected={old_value}"
        )
    return f"rollback readback={restored}, expected={old_value}"


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
        write_byte(session, address, new_value, timeout=timeout, verbose=verbose)
    except Exception as exc:  # noqa: BLE001 - controller may still have written
        ack_error = exc

    time.sleep(settle)

    try:
        actual, _ = read_uint_le(
            session, address, 1, timeout=timeout, verbose=verbose
        )
    except Exception as read_exc:  # noqa: BLE001
        rollback_note = ""
        if old_value is not None:
            rollback_note = "; " + _restore_byte(
                session,
                address,
                old_value,
                timeout=timeout,
                settle=settle,
                verbose=verbose,
            )
        raise MaintenanceError(
            f"0x{address:04X}: write could not be verified "
            f"(ACK error={ack_error!s}; readback error={read_exc!s}){rollback_note}"
        ) from read_exc

    if actual == new_value:
        # A missing/late ACK is acceptable only when the independent readback
        # proves the requested controller state.
        return actual

    rollback_note = ""
    if old_value is not None:
        rollback_note = "; " + _restore_byte(
            session,
            address,
            old_value,
            timeout=timeout,
            settle=settle,
            verbose=verbose,
        )

    ack_note = f"; ACK error={ack_error}" if ack_error is not None else ""
    raise MaintenanceError(
        f"0x{address:04X}: readback {actual} != requested {new_value}"
        f"{ack_note}{rollback_note}"
    )


def _utc_iso_from_epoch(value: int) -> str | None:
    if value <= 0:
        return None
    try:
        return dt.datetime.fromtimestamp(value, tz=dt.timezone.utc).isoformat().replace("+00:00", "Z")
    except (OverflowError, OSError, ValueError):
        return None


def snapshot(
    session: MqttSession,
    *,
    timeout: float,
    verbose: bool,
) -> dict[str, Any]:
    hours_threshold_raw, hours_threshold_hex = read_uint_le(
        session, ADDR_HOURS_THRESHOLD, 1, timeout=timeout, verbose=verbose
    )
    interval_months, interval_hex = read_uint_le(
        session, ADDR_INTERVAL_MONTHS, 1, timeout=timeout, verbose=verbose
    )
    maintenance_state, maintenance_hex = read_uint_le(
        session, ADDR_MAINTENANCE_STATE, 1, timeout=timeout, verbose=verbose
    )
    interval_reference, interval_reference_hex = read_uint_le(
        session, ADDR_INTERVAL_REFERENCE, 4, timeout=timeout, verbose=verbose
    )
    burner_reference, burner_reference_hex = read_uint_le(
        session, ADDR_BURNER_REFERENCE, 4, timeout=timeout, verbose=verbose
    )
    burner_total_seconds, burner_total_hex = read_uint_le(
        session, ADDR_BURNER_TOTAL, 4, timeout=timeout, verbose=verbose
    )
    burner_starts, burner_starts_hex = read_uint_le(
        session, ADDR_BURNER_STARTS, 4, timeout=timeout, verbose=verbose
    )

    burner_hours_since_maintenance: float | None = None
    if burner_reference > 0 and burner_total_seconds >= burner_reference:
        burner_hours_since_maintenance = (
            burner_total_seconds - burner_reference
        ) / 3600.0

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
                maintenance_state, f"Unbekannt ({maintenance_state})"
            ),
        },
        "interval_reference": {
            "address": "0x756C",
            "raw_hex": interval_reference_hex,
            "unix_seconds": interval_reference,
            "utc": _utc_iso_from_epoch(interval_reference),
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
        "burner_since_maintenance": {
            "hours": burner_hours_since_maintenance,
            "formula": "(0x08A7 - 0x7570) / 3600",
        },
        "burner_starts": {
            "address": "0x088A",
            "raw_hex": burner_starts_hex,
            "count": burner_starts,
        },
    }


def print_status(data: dict[str, Any]) -> None:
    print("Wartung / Service")
    print(
        f"  Brennerstunden-Grenzwert : {data['hours_threshold']['hours']} h "
        f"(raw 0x{data['hours_threshold']['raw_hex'].upper()})"
    )
    print(
        f"  Zeitintervall            : {data['interval']['months']} Monate "
        f"(raw 0x{data['interval']['raw_hex'].upper()})"
    )
    print(
        f"  Wartungsstatus           : {data['maintenance_state']['text']} "
        f"(raw 0x{data['maintenance_state']['raw_hex'].upper()})"
    )

    interval_ref = data["interval_reference"]
    print(
        "  Intervall-Referenz       : "
        + (
            f"{interval_ref['utc']} (raw 0x{interval_ref['raw_hex'].upper()})"
            if interval_ref["utc"]
            else f"nicht gesetzt (raw 0x{interval_ref['raw_hex'].upper()})"
        )
    )

    burner_ref = data["burner_reference"]
    print(
        f"  Brenner-Referenz         : {burner_ref['burner_seconds_baseline']} s "
        f"(raw 0x{burner_ref['raw_hex'].upper()})"
    )
    print(
        f"  Brenner gesamt           : {data['burner_total']['hours']:.1f} h "
        f"({data['burner_total']['seconds']} s)"
    )

    since = data["burner_since_maintenance"]["hours"]
    if since is None:
        print("  Brenner seit Wartung     : nicht ableitbar (Referenz nicht gesetzt)")
    else:
        print(f"  Brenner seit Wartung     : {since:.3f} h")

    print(f"  Brennerstarts gesamt     : {data['burner_starts']['count']}")


def command_status(session: MqttSession, args: argparse.Namespace) -> dict[str, Any]:
    return snapshot(session, timeout=args.timeout, verbose=args.verbose)


def command_set_hours(session: MqttSession, args: argparse.Namespace) -> dict[str, Any]:
    hours = args.hours
    if hours < 0 or hours > 10000 or hours % 100 != 0:
        raise MaintenanceError(
            "set-hours accepts 0..10000 h in exact 100 h steps"
        )
    requested_raw = hours // 100
    current_raw, current_hex = read_uint_le(
        session, ADDR_HOURS_THRESHOLD, 1, timeout=args.timeout, verbose=args.verbose
    )

    if current_raw == requested_raw and not args.force:
        return {
            "action": "set-hours",
            "changed": False,
            "reason": "already set; no write performed",
            "hours": hours,
            "raw_hex": current_hex,
            "status": snapshot(session, timeout=args.timeout, verbose=args.verbose),
        }

    write_verify_byte(
        session,
        ADDR_HOURS_THRESHOLD,
        requested_raw,
        old_value=current_raw,
        timeout=args.timeout,
        settle=args.settle,
        verbose=args.verbose,
    )

    return {
        "action": "set-hours",
        "changed": True,
        "previous_hours": current_raw * 100,
        "hours": hours,
        "raw": requested_raw,
        "status": snapshot(session, timeout=args.timeout, verbose=args.verbose),
    }


def command_set_months(session: MqttSession, args: argparse.Namespace) -> dict[str, Any]:
    months = args.months
    if months < 0 or months > 24:
        raise MaintenanceError("set-months accepts 0..24 months")

    current_raw, current_hex = read_uint_le(
        session, ADDR_INTERVAL_MONTHS, 1, timeout=args.timeout, verbose=args.verbose
    )

    if current_raw == months and not args.force:
        return {
            "action": "set-months",
            "changed": False,
            "reason": "already set; no write performed, interval reference preserved",
            "months": months,
            "raw_hex": current_hex,
            "status": snapshot(session, timeout=args.timeout, verbose=args.verbose),
        }

    if args.confirm_reference_reset != MONTH_REFERENCE_CONFIRMATION:
        raise MaintenanceError(
            "changing 0x5723 re-baselines the maintenance time reference at 0x756C; "
            f"repeat with --confirm-reference-reset {MONTH_REFERENCE_CONFIRMATION}"
        )

    before_ref, before_ref_hex = read_uint_le(
        session, ADDR_INTERVAL_REFERENCE, 4, timeout=args.timeout, verbose=args.verbose
    )

    write_verify_byte(
        session,
        ADDR_INTERVAL_MONTHS,
        months,
        old_value=current_raw,
        timeout=args.timeout,
        settle=args.settle,
        verbose=args.verbose,
    )

    after_ref, after_ref_hex = read_uint_le(
        session, ADDR_INTERVAL_REFERENCE, 4, timeout=args.timeout, verbose=args.verbose
    )

    return {
        "action": "set-months",
        "changed": True,
        "previous_months": current_raw,
        "months": months,
        "interval_reference_before": {
            "raw_hex": before_ref_hex,
            "unix_seconds": before_ref,
            "utc": _utc_iso_from_epoch(before_ref),
        },
        "interval_reference_after": {
            "raw_hex": after_ref_hex,
            "unix_seconds": after_ref,
            "utc": _utc_iso_from_epoch(after_ref),
        },
        "status": snapshot(session, timeout=args.timeout, verbose=args.verbose),
    }


def command_reset(session: MqttSession, args: argparse.Namespace) -> dict[str, Any]:
    if args.confirm != RESET_CONFIRMATION:
        raise MaintenanceError(
            f"maintenance reset requires --confirm {RESET_CONFIRMATION}"
        )

    before = snapshot(session, timeout=args.timeout, verbose=args.verbose)
    attempted_state_one = False
    primary_error: Exception | None = None

    try:
        # This exact 1 -> 0 sequence is the locally verified maintenance reset.
        # Set the guard before waiting for the response: if the ACK times out
        # after the controller already accepted the write, the finally block
        # still returns 0x5724 to Grundzustand.
        attempted_state_one = True
        write_byte(
            session,
            ADDR_MAINTENANCE_STATE,
            1,
            timeout=args.timeout,
            verbose=args.verbose,
        )
        time.sleep(args.settle)

        state_one, _ = read_uint_le(
            session,
            ADDR_MAINTENANCE_STATE,
            1,
            timeout=args.timeout,
            verbose=args.verbose,
        )
        if state_one != 1:
            raise MaintenanceError(
                f"0x5724 did not enter Wartung state; readback={state_one}"
            )
    except Exception as exc:  # noqa: BLE001 - safety restore must still run
        primary_error = exc
    finally:
        if attempted_state_one:
            restore_ack_error: Exception | None = None
            try:
                write_byte(
                    session,
                    ADDR_MAINTENANCE_STATE,
                    0,
                    timeout=args.timeout,
                    verbose=args.verbose,
                )
            except Exception as exc:  # noqa: BLE001 - verify independently
                restore_ack_error = exc

            time.sleep(args.settle)
            try:
                restored, _ = read_uint_le(
                    session,
                    ADDR_MAINTENANCE_STATE,
                    1,
                    timeout=args.timeout,
                    verbose=args.verbose,
                )
            except Exception as read_exc:  # noqa: BLE001
                raise MaintenanceError(
                    "SAFETY ERROR: could not verify 0x5724=0 after reset; "
                    f"ACK error={restore_ack_error!s}; readback error={read_exc!s}"
                ) from read_exc

            if restored != 0:
                raise MaintenanceError(
                    "SAFETY ERROR: 0x5724 restore readback="
                    f"{restored}, expected 0; ACK error={restore_ack_error!s}"
                )

    if primary_error is not None:
        raise MaintenanceError(
            f"maintenance reset aborted after safety restore: {primary_error}"
        ) from primary_error

    after = snapshot(session, timeout=args.timeout, verbose=args.verbose)

    warnings: list[str] = []
    if after["burner_total"]["seconds"] < before["burner_total"]["seconds"]:
        warnings.append("total burner-runtime counter decreased unexpectedly")
    if after["burner_starts"]["count"] < before["burner_starts"]["count"]:
        warnings.append("total burner-start counter decreased unexpectedly")

    burner_ref = after["burner_reference"]["burner_seconds_baseline"]
    burner_total = after["burner_total"]["seconds"]
    if burner_ref <= 0 or burner_ref > burner_total:
        warnings.append("new burner maintenance reference is not plausible")
    elif burner_total - burner_ref > 300:
        warnings.append(
            "new burner maintenance reference is more than 300 s behind total runtime"
        )

    ref_epoch = after["interval_reference"]["unix_seconds"]
    if ref_epoch <= 0:
        warnings.append("new interval reference is not set")
    elif abs(time.time() - ref_epoch) > 300:
        warnings.append(
            "new interval reference differs from system time by more than 300 s"
        )

    return {
        "action": "reset",
        "changed": True,
        "sequence": "0x5724: 1 -> 0",
        "before": before,
        "after": after,
        "warnings": warnings,
    }


def acquire_lock() -> Any:
    os.makedirs(os.path.dirname(LOCK_PATH), exist_ok=True)
    handle = open(LOCK_PATH, "a+", encoding="utf-8")
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as exc:
        handle.close()
        raise MaintenanceError(
            f"another optolink-maintenance process holds {LOCK_PATH}"
        ) from exc
    return handle


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Guarded WB2A / VDensHO1 maintenance CLI via Optolink-Splitter"
    )
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="show individual MQTT splitter requests and responses",
    )
    parser.add_argument("--timeout", type=float, default=4.0)
    parser.add_argument("--settle", type=float, default=1.0)

    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("status", help="read maintenance configuration and references")

    hours = sub.add_parser(
        "set-hours",
        help="set burner-runtime maintenance threshold (0..10000 h, 100 h steps)",
    )
    hours.add_argument("hours", type=int)
    hours.add_argument(
        "--force",
        action="store_true",
        help="write even when the requested value is already active",
    )

    months = sub.add_parser(
        "set-months",
        help="set maintenance interval (0..24 months); changes time reference",
    )
    months.add_argument("months", type=int)
    months.add_argument(
        "--confirm-reference-reset",
        metavar=MONTH_REFERENCE_CONFIRMATION,
        help="required when a write will re-baseline 0x756C",
    )
    months.add_argument(
        "--force",
        action="store_true",
        help="write even when the requested value is already active",
    )

    reset = sub.add_parser(
        "reset",
        help="reset maintenance references using verified 0x5724 1 -> 0 sequence",
    )
    reset.add_argument(
        "--confirm",
        metavar=RESET_CONFIRMATION,
        help="required explicit reset confirmation",
    )

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if args.timeout <= 0:
        parser.error("--timeout must be greater than zero")
    if args.settle < 0:
        parser.error("--settle must not be negative")

    lock_handle = None
    session = None
    try:
        lock_handle = acquire_lock()
        session = connect(json_mode=args.json)

        if args.command == "status":
            result = command_status(session, args)
        elif args.command == "set-hours":
            result = command_set_hours(session, args)
        elif args.command == "set-months":
            result = command_set_months(session, args)
        elif args.command == "reset":
            result = command_reset(session, args)
        else:
            raise MaintenanceError(f"unsupported command: {args.command}")

        if args.json:
            print(json.dumps(result, indent=2, sort_keys=True))
        elif args.command == "status":
            print_status(result)
        else:
            action = result.get("action", args.command)
            changed = result.get("changed", False)
            print(f"{action}: {'OK' if changed else 'NO-OP'}")
            if result.get("reason"):
                print(f"  {result['reason']}")
            if result.get("warnings"):
                for warning in result["warnings"]:
                    print(f"  WARN: {warning}")
            status = result.get("status") or result.get("after")
            if status:
                print()
                print_status(status)
        return 0

    except MaintenanceError as exc:
        if getattr(args, "json", False):
            print(json.dumps({"ok": False, "error": str(exc)}))
        else:
            print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    finally:
        if session is not None:
            session.close()
        if lock_handle is not None:
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)
            lock_handle.close()


if __name__ == "__main__":
    raise SystemExit(main())
