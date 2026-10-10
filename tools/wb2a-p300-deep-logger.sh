#!/usr/bin/env bash
# Reviewed development-only entry point for bounded multi-hour P06 vs P300 logging.
set -euo pipefail
umask 077
PROJECT=/root/p300-trial-work/project
cd "$PROJECT"
if [[ "$(pwd -P)" != "$PROJECT" ]]; then
  echo "REFUSED: wrong experimental checkout" >&2; exit 1
fi
if [[ $# -gt 2 ]]; then
  echo "Use: start [hours 1..8] | status | stop | plan" >&2; exit 2
fi
mode=plan
if [[ $# -ge 1 ]]; then mode="$1"; fi
case "$mode" in
  start)
    duration=4
    if [[ $# -eq 2 ]]; then duration="$2"; fi
    if [[ ! "$duration" =~ ^[1-8]$ ]]; then
      echo "REFUSED: hours must be 1..8" >&2; exit 2
    fi
    if [[ "$(git branch --show-current)" != "optolink-p300-migration" ]]; then
      echo "REFUSED: developer P300 migration branch required" >&2; exit 1
    fi
    if ! git diff --quiet || ! git diff --cached --quiet; then
      echo "REFUSED: local tracked developer edits" >&2; exit 1
    fi
    git fetch --quiet origin optolink-p300-migration
    git merge --ff-only FETCH_HEAD
    printf 'RESEARCH_HEAD=%s\n' "$(git rev-parse HEAD)"
    /opt/optolink/venv/bin/python -m unittest discover -s tests -p "test_p300_deep_logger.py" -v
    /opt/optolink/venv/bin/python -m unittest discover -s tests -p "test_uart1_overnight.py" -v
    /opt/optolink/venv/bin/python -m unittest discover -s tests -p "test_handover*.py" -v
    exec /opt/optolink/venv/bin/python -u tools/wb2a-p300-deep-logger.py \
      --start --hours "$duration"
    ;;
  status)
    exec /opt/optolink/venv/bin/python -u \
      tools/wb2a-p300-deep-logger.py --status
    ;;
  stop)
    # No git/network/test/serial; works even after an automatic 4h stop.
    exec /opt/optolink/venv/bin/python -u \
      tools/wb2a-p300-deep-logger.py --stop
    ;;
  plan)
    exec /opt/optolink/venv/bin/python tools/wb2a-p300-deep-logger.py
    ;;
  *)
    echo "REFUSED: use start [1..8], status, stop, plan" >&2; exit 2
    ;;
esac
