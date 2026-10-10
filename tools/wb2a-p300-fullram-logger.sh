#!/usr/bin/env bash
# Explicit entry, no implicit serial access. Run directly via bash.
set -euo pipefail
umask 077
PROJECT=/root/p300-trial-work/project
cd "$PROJECT"
[[ "$(pwd -P)" == "$PROJECT" ]] || { echo "REFUSED: experimental checkout required" >&2; exit 1; }
mode="${1:-plan}"
[[ $# -le 2 ]] || { echo "Usage: start [hours 1..8] | status | stop | plan" >&2; exit 2; }
case "$mode" in
  start)
    hours="${2:-4}"
    [[ "$hours" =~ ^[1-8]$ ]] || { echo "REFUSED: hours must be 1..8" >&2; exit 2; }
    [[ "$(git branch --show-current)" == "optolink-p300-migration" ]] || { echo "REFUSED: wrong branch" >&2; exit 1; }
    git diff --quiet && git diff --cached --quiet || { echo "REFUSED: dirty tracked checkout" >&2; exit 1; }
    git fetch --quiet origin optolink-p300-migration
    git merge --ff-only FETCH_HEAD
    /opt/optolink/venv/bin/python -m unittest discover -s tests -p 'test_p300_fullram_logger.py' -v
    /opt/optolink/venv/bin/python -m unittest discover -s tests -p 'test_p300_deep_logger.py' -v
    /opt/optolink/venv/bin/python -m unittest discover -s tests -p 'test_uart1_overnight.py' -v
    exec /opt/optolink/venv/bin/python -u tools/wb2a-p300-fullram-logger.py --start --hours "$hours"
    ;;
  status)
    [[ $# == 1 ]] || exit 2
    exec /opt/optolink/venv/bin/python -u tools/wb2a-p300-fullram-logger.py --status
    ;;
  stop)
    [[ $# == 1 ]] || exit 2
    exec /opt/optolink/venv/bin/python -u tools/wb2a-p300-fullram-logger.py --stop
    ;;
  plan)
    exec /opt/optolink/venv/bin/python tools/wb2a-p300-fullram-logger.py
    ;;
  *) echo "Usage: start [hours 1..8] | status | stop | plan" >&2; exit 2 ;;
esac
