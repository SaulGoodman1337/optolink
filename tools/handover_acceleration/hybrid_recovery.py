"""Independent systemd ExecStopPost recovery with pump-owner arbitration.

No test/production action without --recover AND the original root-owned
systemd invocation. The ORIGINAL pinned live_probe recovery remains the
only component allowed to restore VS1 and restart previously-active services.

Unlike the worker, ExecStopPost runs in a NEW process and therefore does not
inherit the worker's flock. This wrapper reacquires the shared pump exclusion
BEFORE the independent recovery can open the serial device or restart VS1.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys

try:
    from .port_ownership import pump_lease, require_pump_inactive
except ImportError:
    try:
        from handover_acceleration.port_ownership import pump_lease, require_pump_inactive
    except ImportError:
        from port_ownership import pump_lease, require_pump_inactive


def _live():
    try:
        from . import live_probe
    except ImportError:
        try:
            from handover_acceleration import live_probe
        except ImportError:
            import live_probe
    return live_probe


class RecoveryRejected(RuntimeError):
    pass


def recover(session: Path) -> int:
    """Pump-inactive and original research locks must cover FULL restoration.

    Fail closed on a competing pump lease: never independently open the port
    over a second owner. Leave explicit on-disk evidence for diagnosis.
    """
    live = _live()
    # Validate exact private root-owned run-* session before writing anything.
    live.verify_session(session)
    try:
        with pump_lease():
            require_pump_inactive(live.base.unit_state)
            return live.recover(session)
    except BaseException as exc:
        # The original controller state cannot be called verified when
        # competing owners prevent an independent physical return.
        detail = type(exc).__name__ + ': ' + str(exc)
        report = {
            'services_restored': False,
            'overall_verified': False,
            'independent_link_restore': {
                'attempted': False, 'verified': False,
                'reason': 'RECOVERY_ARBITRATION_FAILED',
            },
            'errors': [detail],
            'pump_arbitration': 'FAILED_CLOSED',
        }
        try:
            evidence = session / 'recovery.json'
            if not evidence.exists() and not evidence.is_symlink():
                live.base.atomic_json(evidence, report)
        except BaseException as write_exc:
            print('HYBRID_RECOVERY_EVIDENCE_ERROR='
                  + type(write_exc).__name__, file=sys.stderr, flush=True)
        print('HYBRID_RECOVERY_ARBITRATION_FAILED=' + detail[:400],
              file=sys.stderr, flush=True)
        return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--recover', type=Path, required=True)
    args = parser.parse_args(argv)
    if os.geteuid() != 0 or not os.environ.get('INVOCATION_ID'):
        raise RecoveryRejected('only independent root-owned systemd recovery is allowed')
    return recover(args.recover)


def _entrypoint(argv: list[str] | None = None) -> int:
    """Preserve a real zero exit: never catch our own SystemExit(0)."""
    try:
        return main(argv)
    except Exception as exc:
        print('HYBRID_RECOVERY_REJECTED=' + type(exc).__name__
              + ': ' + str(exc)[:300], file=sys.stderr, flush=True)
        return 1


if __name__ == '__main__':
    raise SystemExit(_entrypoint())
