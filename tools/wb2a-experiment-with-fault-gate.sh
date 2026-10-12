#!/usr/bin/env bash
# Run a reviewed existing WB2A READ-ONLY session with complete fault-history
# BEFORE/AFTER checks and delayed observation. Does not replace the session's
# independent restore timer. Never automatically resets/clears controller.
set -Eeuo pipefail
umask 077
ROOT="$(cd "$(dirname "$0")/.." && pwd -P)"
GUARD="$ROOT/tools/wb2a-experiment-fault-gate.py"
if [ "$#" -ne 2 ] || [ "$1" != "--execute" ]; then
  echo "Usage: bash $0 --execute tools/REVIEWED-LIVE-SESSION.sh" >&2
  echo "Dry-run safe read list: python3 $GUARD plan" >&2
  exit 64
fi
case "$2" in
  tools/wb2a-gwg-c7-dispatcher-session.sh|\
  tools/wb2a-gwg-legacy-readtypes-session.sh|\
  tools/wb2a-v200kw2-gwg-followup-session.sh|\
  tools/wb2a-v200kw2-gwg-live-session.sh|\
  tools/wb2a-vitotrol-p300-fc-sequence-alias-session.sh|\
  tools/wb2a-vitotrol-rom-bridge-contrast-session.sh)
    SESSION="$ROOT/$2" ;;
  *)
    echo "REFUSE_UNREVIEWED_EXPERIMENT: $2" >&2
    exit 65 ;;
esac
if [ ! -f "$SESSION" ] || [ -L "$SESSION" ] || [ ! -f "$GUARD" ]; then
  echo "REFUSE_UNKNOWN_OR_SYMLINKED_SESSION" >&2
  exit 66
fi
if [ -e "$ROOT/.git/MERGE_HEAD" ]; then
  echo "REFUSE_REPOSITORY_MID_MERGE" >&2
  exit 67
fi
OUT="$(mktemp -d /tmp/wb2a-experiment-fault-gate-20261012-XXXXXX)"
BASE="$OUT/baseline.json"
BASELINE_READY=0
POST_STARTED=0
WATCH_CONCLUDED=0
on_exit() {
  local rc=$?
  trap - EXIT
  if [ "$BASELINE_READY" -eq 1 ] && [ "$WATCH_CONCLUDED" -ne 1 ]; then
    if [ "$POST_STARTED" -ne 1 ]; then
      # A cancelled experiment still needs an immediate post-restore read.
      python3 "$GUARD" compare --baseline "$BASE" --output "$OUT/abnormal-exit-post.json" \
        > "$OUT/abnormal-exit-post.log" 2>&1 || true
    fi
    echo "ALARM_UNVERIFIED: 75-minute post-test observation interrupted: $OUT" >&2
    logger -t wb2a-experiment-fault-gate "POSTWATCH_INCOMPLETE session=$(basename "$SESSION") audit=$OUT"
    if [ "$rc" -eq 0 ]; then rc=26; fi
  fi
  exit "$rc"
}
trap on_exit EXIT
echo "AUDIT_DIR=$OUT"
echo "PRECHECK=13_system_and_20_gfa_history_slots"
if ! python3 "$GUARD" snapshot --output "$BASE" > "$OUT/pre.log" 2>&1; then
  cat "$OUT/pre.log" >&2
  echo "ALARM: cannot confirm healthy baseline; intervention NOT started" >&2
  logger -t wb2a-experiment-fault-gate "PRECHECK_FAILED session=$(basename "$SESSION") audit=$OUT"
  exit 68
fi
BASELINE_READY=1
echo "PRECHECK_OK; runner must arm independent controller restore BEFORE switch"
RUNNER_RC=0
sudo -n bash "$SESSION" --execute > "$OUT/experiment.log" 2>&1 || RUNNER_RC=$?
echo "EXPERIMENT_RETURN=$RUNNER_RC; runner's independent restore must already have completed"
POST_STARTED=1
echo "POSTCHECK_T0"
POST_RC=0
if ! python3 "$GUARD" compare --baseline "$BASE" --output "$OUT/post-0.json" > "$OUT/post-0.log" 2>&1; then
  POST_RC=25
  cat "$OUT/post-0.log" >&2
  echo "ALARM: post-test fault archive changed or health check failed" >&2
fi
if [ "$POST_RC" -eq 0 ]; then
  echo "NO_CHANGE_T0; delayed 5-minute fault watch, VS1 normal operation continues"
  sleep 300
  if ! python3 "$GUARD" compare --baseline "$BASE" --output "$OUT/post-5min.json" > "$OUT/post-5min.log" 2>&1; then
    POST_RC=25
    cat "$OUT/post-5min.log" >&2
    echo "ALARM: delayed fault by T+5m" >&2
  fi
fi
if [ "$POST_RC" -eq 0 ]; then
  echo "NO_CHANGE_T5; delayed 15-minute fault watch"
  sleep 600
  if ! python3 "$GUARD" compare --baseline "$BASE" --output "$OUT/post-15min.json" > "$OUT/post-15min.log" 2>&1; then
    POST_RC=25
    cat "$OUT/post-15min.log" >&2
    echo "ALARM: delayed fault by T+15m" >&2
  fi
fi
if [ "$POST_RC" -eq 0 ]; then
  echo "NO_CHANGE_T15; delayed 75-minute fault watch"
  sleep 3600
  if ! python3 "$GUARD" compare --baseline "$BASE" --output "$OUT/post-75min.json" > "$OUT/post-75min.log" 2>&1; then
    POST_RC=25
    cat "$OUT/post-75min.log" >&2
    echo "ALARM: delayed fault by T+75m" >&2
  fi
fi
WATCH_CONCLUDED=1
if [ "$POST_RC" -ne 0 ]; then
  logger -t wb2a-experiment-fault-gate "FAULT_DETECTED_OR_HEALTH_UNVERIFIED session=$(basename "$SESSION") audit=$OUT"
  echo "FAULT_DETECTED_OR_HEALTH_UNVERIFIED; no further hardware tests" >&2
  exit 25
fi
if [ "$RUNNER_RC" -ne 0 ]; then
  logger -t wb2a-experiment-fault-gate "EXPERIMENT_FAILED_ANCESTOR session=$(basename "$SESSION") rc=$RUNNER_RC audit=$OUT"
  echo "EXPERIMENT_FAILED; current archive unchanged in watched window but test itself did not pass" >&2
  exit "$RUNNER_RC"
fi
echo "POSTWATCH_NO_CHANGE_IN_DEFINED_75MIN_WINDOW; not a guarantee beyond observation"
logger -t wb2a-experiment-fault-gate "POSTWATCH_NO_CHANGE_IN_DEFINED_WINDOW session=$(basename "$SESSION") audit=$OUT"
