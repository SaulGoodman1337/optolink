#!/usr/bin/env bash
# Optolink WB2A research only. Do not touch /opt/optolink source files.
set -euo pipefail
umask 077
PROJECT=/root/p300-trial-work/project
cd "$PROJECT"
[[ "$(pwd -P)" == "$PROJECT" ]] || { echo "REFUSED: research checkout only" >&2; exit 1; }
[[ $# -le 2 ]] || { echo "Usage: plan | canary | start [1|2] | status | stop" >&2; exit 2; }
mode="${1:-plan}"
case "$mode" in
  canary|start)
    [[ "$mode" != "canary" || $# -eq 1 ]] || { echo "REFUSED: canary takes no hours" >&2; exit 2; }
    hours="${2:-1}"
    [[ "$hours" =~ ^[12]$ ]] || { echo "REFUSED: only 1 or 2 hours" >&2; exit 2; }
    [[ "$(git branch --show-current)" == "optolink-p300-migration" ]] || {
      echo "REFUSED: wrong research branch" >&2; exit 1;
    }
    git diff --quiet && git diff --cached --quiet || {
      echo "REFUSED: dirty tracked research checkout" >&2; exit 1;
    }
    git fetch --quiet origin optolink-p300-migration
    git merge --ff-only FETCH_HEAD
    PY=/opt/optolink/venv/bin/python
    "$PY" -m unittest discover -s tests -p 'test_p300_rpm_trigger.py' -v
    "$PY" -m unittest discover -s tests -p 'test_p300_temporal_logger.py' -v
    "$PY" -m unittest discover -s tests -p 'test_p300_p06_focus.py' -v
    "$PY" -m unittest discover -s tests -p 'test_p300_fullram_logger.py' -v
    "$PY" -m unittest discover -s tests -p 'test_p300_deep_logger.py' -v
    "$PY" -m unittest discover -s tests -p 'test_uart1_overnight.py' -v
    if [[ "$mode" == "canary" ]]; then
      exec "$PY" -u tools/wb2a-p300-rpm-trigger.py --canary
    fi
    exec "$PY" -u tools/wb2a-p300-rpm-trigger.py --start --hours "$hours"
    ;;
  plan)
    [[ $# -eq 1 || $# -eq 0 ]] || exit 2
    exec /opt/optolink/venv/bin/python tools/wb2a-p300-rpm-trigger.py
    ;;
  status)
    [[ $# -eq 1 ]] || exit 2
    exec /opt/optolink/venv/bin/python -u tools/wb2a-p300-rpm-trigger.py --status
    ;;
  stop)
    [[ $# -eq 1 ]] || exit 2
    exec /opt/optolink/venv/bin/python -u tools/wb2a-p300-rpm-trigger.py --stop
    ;;
  *) echo "Usage: plan | canary | start [1|2] | status | stop" >&2; exit 2 ;;
esac
