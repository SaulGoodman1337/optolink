#!/usr/bin/env bash
# Research-only. Never start automatically or touch the production checkout.
set -euo pipefail
umask 077
PROJECT=/root/p300-trial-work/project
cd "$PROJECT"
[[ "$(pwd -P)" == "$PROJECT" ]] || { echo "REFUSED: research checkout required" >&2; exit 1; }
[[ $# -le 2 ]] || { echo "Usage: start [hours 1..3] | status | stop | plan" >&2; exit 2; }
mode="${1:-plan}"
case "$mode" in
  start)
    hours="${2:-1}"
    [[ "$hours" =~ ^[1-3]$ ]] || { echo "REFUSED: duration must be 1..3 hours" >&2; exit 2; }
    [[ "$(git branch --show-current)" == "optolink-p300-migration" ]] || {
      echo "REFUSED: wrong research branch" >&2; exit 1;
    }
    git diff --quiet && git diff --cached --quiet || {
      echo "REFUSED: dirty tracked research checkout" >&2; exit 1;
    }
    git fetch --quiet origin optolink-p300-migration
    git merge --ff-only FETCH_HEAD
    /opt/optolink/venv/bin/python -m unittest discover -s tests -p 'test_p300_p06_focus.py' -v
    /opt/optolink/venv/bin/python -m unittest discover -s tests -p 'test_p300_fullram_logger.py' -v
    /opt/optolink/venv/bin/python -m unittest discover -s tests -p 'test_p300_deep_logger.py' -v
    /opt/optolink/venv/bin/python -m unittest discover -s tests -p 'test_uart1_overnight.py' -v
    exec /opt/optolink/venv/bin/python -u tools/wb2a-p300-p06-focus.py --start --hours "$hours"
    ;;
  status)
    [[ $# -eq 1 ]] || exit 2
    exec /opt/optolink/venv/bin/python -u tools/wb2a-p300-p06-focus.py --status
    ;;
  stop)
    [[ $# -eq 1 ]] || exit 2
    exec /opt/optolink/venv/bin/python -u tools/wb2a-p300-p06-focus.py --stop
    ;;
  plan)
    exec /opt/optolink/venv/bin/python tools/wb2a-p300-p06-focus.py
    ;;
  *) echo "Usage: start [hours 1..3] | status | stop | plan" >&2; exit 2 ;;
esac
