#!/usr/bin/env bash
# Only for the research checkout. Must not be started while focus logger runs.
set -euo pipefail
umask 077
PROJECT=/root/p300-trial-work/project
cd "$PROJECT"
[[ "$(pwd -P)" == "$PROJECT" ]] || { echo "REFUSED: research checkout only" >&2; exit 1; }
[[ $# -le 2 ]] || { echo "Usage: plan | start [hours 1..3] | status | stop" >&2; exit 2; }
case "${1:-plan}" in
  start)
    hours="${2:-2}"
    [[ "$hours" =~ ^[1-3]$ ]] || { echo "REFUSED: hours must be 1..3" >&2; exit 2; }
    [[ "$(git branch --show-current)" == "optolink-p300-migration" ]] || {
      echo "REFUSED: wrong branch" >&2; exit 1;
    }
    git diff --quiet && git diff --cached --quiet || {
      echo "REFUSED: dirty tracked research checkout" >&2; exit 1;
    }
    git fetch --quiet origin optolink-p300-migration
    git merge --ff-only FETCH_HEAD
    PY=/opt/optolink/venv/bin/python
    "$PY" -m unittest discover -s tests -p 'test_p300_temporal_logger.py' -v
    "$PY" -m unittest discover -s tests -p 'test_p300_p06_focus.py' -v
    "$PY" -m unittest discover -s tests -p 'test_p300_fullram_logger.py' -v
    "$PY" -m unittest discover -s tests -p 'test_p300_deep_logger.py' -v
    "$PY" -m unittest discover -s tests -p 'test_uart1_overnight.py' -v
    exec "$PY" -u tools/wb2a-p300-temporal-logger.py --start --hours "$hours"
    ;;
  status)
    [[ $# -eq 1 ]] || exit 2
    exec /opt/optolink/venv/bin/python -u tools/wb2a-p300-temporal-logger.py --status
    ;;
  stop)
    [[ $# -eq 1 ]] || exit 2
    exec /opt/optolink/venv/bin/python -u tools/wb2a-p300-temporal-logger.py --stop
    ;;
  plan)
    [[ $# -eq 1 || $# -eq 0 ]] || exit 2
    exec /opt/optolink/venv/bin/python tools/wb2a-p300-temporal-logger.py
    ;;
  *) echo "Usage: plan | start [hours 1..3] | status | stop" >&2; exit 2 ;;
esac
