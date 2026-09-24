#!/opt/optolink/venv/bin/python
"""Guarded CLI wrapper for the shared Optolink maintenance core."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

APP_DIR = "/opt/optolink"
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from optolink_maintenance_core import (  # type: ignore  # noqa: E402
    HOURS_REFERENCE_CONFIRMATION,
    MONTH_REFERENCE_CONFIRMATION,
    RESET_CONFIRMATION,
    MaintenanceError,
    get_status,
    reset_maintenance,
    set_hours,
    set_months,
)


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
    if interval_ref["raw_uint_le"] == 0:
        print(
            f"  Intervall-Referenz       : nicht gesetzt "
            f"(raw 0x{interval_ref['raw_hex'].upper()})"
        )
    else:
        print(
            f"  Intervall-Referenz       : {interval_ref['raw_uint_le']} "
            f"(raw 0x{interval_ref['raw_hex'].upper()}, LastCheckInterval)"
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

    since = data["burner_since_reference"]["hours"]
    if since is None:
        print(
            "  Brenner seit Referenz    : "
            "nicht ableitbar (Referenz nicht gesetzt)"
        )
    else:
        print(f"  Brenner seit Referenz    : {since:.3f} h")

    print(f"  Brennerstarts gesamt     : {data['burner_starts']['count']}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Guarded WB2A / VDensHO1 maintenance CLI via Optolink-Splitter"
        )
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="emit machine-readable JSON",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="show individual splitter requests and responses",
    )
    parser.add_argument("--timeout", type=float, default=4.0)
    parser.add_argument("--settle", type=float, default=1.0)

    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser(
        "status",
        help="read maintenance configuration and references",
    )

    hours = sub.add_parser(
        "set-hours",
        help=(
            "set burner-runtime maintenance threshold "
            "(0..10000 h, 100 h steps)"
        ),
    )
    hours.add_argument("hours", type=int)
    hours.add_argument(
        "--confirm-reference-reset",
        metavar=HOURS_REFERENCE_CONFIRMATION,
        help="required when a write may re-baseline 0x7570",
    )
    hours.add_argument(
        "--force",
        action="store_true",
        help="write even when the requested value is already active",
    )

    months = sub.add_parser(
        "set-months",
        help="set maintenance interval (0..24 months); changes 0x756C",
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
        help=(
            "execute verified 0x5724 1 -> 0 maintenance reset "
            "and report reference effects"
        ),
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

    try:
        common = {
            "timeout": args.timeout,
            "verbose": args.verbose,
            "quiet": args.json,
        }

        if args.command == "status":
            result = get_status(**common)
        elif args.command == "set-hours":
            result = set_hours(
                args.hours,
                confirm_reference_change=(
                    args.confirm_reference_reset
                    == HOURS_REFERENCE_CONFIRMATION
                ),
                force=args.force,
                settle=args.settle,
                **common,
            )
        elif args.command == "set-months":
            result = set_months(
                args.months,
                confirm_reference_change=(
                    args.confirm_reference_reset
                    == MONTH_REFERENCE_CONFIRMATION
                ),
                force=args.force,
                settle=args.settle,
                **common,
            )
        elif args.command == "reset":
            result = reset_maintenance(
                confirm=args.confirm == RESET_CONFIRMATION,
                settle=args.settle,
                **common,
            )
        else:
            raise MaintenanceError(
                f"unsupported command: {args.command}",
                code="unsupported_action",
            )

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
            for note in result.get("notes", []):
                print(f"  INFO: {note}")
            for warning in result.get("warnings", []):
                print(f"  WARN: {warning}")
            status = result.get("status") or result.get("after")
            if status:
                print()
                print_status(status)
        return 0

    except MaintenanceError as exc:
        error = {
            "ok": False,
            "error": str(exc),
            "code": exc.code,
            "details": exc.details,
        }
        if args.json:
            print(json.dumps(error, sort_keys=True))
        else:
            print(f"ERROR: {exc}", file=sys.stderr)
            required = exc.details.get("required_confirmation")
            if required:
                print(
                    f"  required confirmation: {required}",
                    file=sys.stderr,
                )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
