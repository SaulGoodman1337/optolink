#!/usr/bin/env bash
set -u

DBG="/usr/local/bin/optolink-debug"
DURATION="${DURATION:-60}"
INTERVAL="${INTERVAL:-10}"
LOG="${LOG:-/root/vitotrol-a0-probe-$(date +%Y%m%d-%H%M%S).log}"
ROLLBACK_NEEDED=0
FAULT_SEEN=0
REPLY=""

exec > >(tee -a "$LOG") 2>&1

capture_req() {
  local cmd="$1"
  REPLY=$("$DBG" request "$cmd" 2>&1)
  printf "%s\n" "$REPLY"
}

snapshot() {
  local alarm_reply history_reply
  echo
  echo "=== SNAPSHOT $(date '+%F %T') ==="

  capture_req 'r;0x27A0;1;raw;False'
  capture_req 'r;0x0A5C;4;raw;False'
  capture_req 'r;0x0896;2;raw;False'
  capture_req 'r;0x089C;1;raw;False'

  capture_req 'r;0xA132;29;raw;False'
  alarm_reply="$REPLY"

  capture_req 'r;0x7507;9;raw;False'
  history_reply="$REPLY"

  capture_req 'r;0x5738;1;raw;False'

  if printf '%s\n' "$alarm_reply" | grep -Eqi 'openv/resp: 1;0xa132;[0-9a-f]*(bc|bd)$'; then
    echo "*** REMOTE FAULT BC/BD DETECTED IN CURRENT ALARM BLOCK ***"
    FAULT_SEEN=1
  fi

  if printf '%s\n' "$history_reply" | grep -Eqi 'openv/resp: 1;0x7507;(bc|bd)'; then
    echo "*** REMOTE FAULT BC/BD DETECTED IN NEWEST FAULT SLOT ***"
    FAULT_SEEN=1
  fi
}

rollback() {
  if [[ "$ROLLBACK_NEEDED" -eq 1 ]]; then
    echo
    echo "=== AUTOMATIC ROLLBACK: 0x27A0 -> 00 ==="
    capture_req 'writeraw;0x27A0;00' || true
    sleep 2
    echo "=== VERIFY ROLLBACK ==="
    capture_req 'r;0x27A0;1;raw;False' || true
    ROLLBACK_NEEDED=0
  fi
}

trap rollback EXIT
trap 'exit 130' INT TERM

echo "Log: $LOG"
echo "Duration: ${DURATION}s, interval: ${INTERVAL}s"

echo "=== SAFETY CHECK: A0 MUST CURRENTLY BE 00 ==="
capture_req 'r;0x27A0;1;raw;False'
if ! printf '%s\n' "$REPLY" | grep -qi 'openv/resp: 1;0x27a0;00'; then
  echo "ABORT: 0x27A0 is not confirmed as 00."
  exit 1
fi

echo "=== PRE-WRITE BASELINE ==="
snapshot
if [[ "$FAULT_SEEN" -ne 0 ]]; then
  echo "ABORT: BC/BD already present in baseline."
  exit 1
fi

# Arm rollback before the write in case the write succeeds but the client is
# interrupted before its response reaches this shell.
ROLLBACK_NEEDED=1

echo
echo "=== WRITE A1/M1 REMOTE IDENTIFICATION: 0 -> 1 (Vitotrol 200) ==="
capture_req 'writeraw;0x27A0;01'

sleep 2
echo "=== IMMEDIATE READBACK ==="
capture_req 'r;0x27A0;1;raw;False'

elapsed=0
while [[ "$elapsed" -lt "$DURATION" ]]; do
  snapshot
  if [[ "$FAULT_SEEN" -ne 0 ]]; then
    echo "Stopping observation early because BC/BD was detected."
    break
  fi
  sleep "$INTERVAL"
  elapsed=$((elapsed + INTERVAL))
done

echo
echo "=== END OF OBSERVATION; ROLLBACK WILL RUN NOW ==="
rollback

echo
echo "=== POST-ROLLBACK SNAPSHOT ==="
snapshot

echo
echo "=== DONE ==="
echo "Log saved to: $LOG"
