#!/usr/bin/env bash
# One entry point: operator-stopped read-only WB2A P300 logging via systemd.
set -euo pipefail
umask 077
PROJECT=/root/p300-trial-work/project
cd "$PROJECT"
if [[ "$(pwd -P)" != "$PROJECT" ]]; then
  echo "REFUSED: wrong research checkout" >&2
  exit 1
fi
if [[ $# -gt 1 ]]; then
  echo "Modes: start, stop, status, plan" >&2
  exit 2
fi
mode=plan
if [[ $# -eq 1 ]]; then mode="$1"; fi
case "$mode" in
  start)
    if [[ "$(git branch --show-current)" != optolink-p300-migration ]]; then
      echo "REFUSED: only research branch" >&2
      exit 1
    fi
    if ! git diff --quiet || ! git diff --cached --quiet; then
      echo "REFUSED: local research edits" >&2
      exit 1
    fi
    git fetch --quiet origin optolink-p300-migration
    git merge --ff-only FETCH_HEAD
    printf 'RESEARCH_HEAD=%s\n' "$(git rev-parse HEAD)"
    for suite in test_uart1_overnight.py test_uart1_dma0_cycle.py test_p87_p300_check.py 'test_handover*.py'; do
      /opt/optolink/venv/bin/python -m unittest discover -s tests -p "$suite" -v
    done
    exec /opt/optolink/venv/bin/python -u \
      "$PROJECT/tools/wb2a-uart1-overnight.py" --start
    ;;
  stop)
    # No Git fetch, no tests, no serial device. This must always work offline.
    exec /opt/optolink/venv/bin/python -u \
      "$PROJECT/tools/wb2a-uart1-overnight.py" --stop
    ;;
  status)
    exec /opt/optolink/venv/bin/python -u \
      "$PROJECT/tools/wb2a-uart1-overnight.py" --status
    ;;
  plan)
    exec /opt/optolink/venv/bin/python \
      "$PROJECT/tools/wb2a-uart1-overnight.py"
    ;;
  *)
    echo "REFUSED: modes start, stop, status, plan only" >&2
    exit 2
    ;;
esac
