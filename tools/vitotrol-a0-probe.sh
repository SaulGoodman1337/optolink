#!/usr/bin/env bash
set -u

DBG="/usr/local/bin/optolink-debug"
DURATION="${DURATION:-60}"
INTERVAL="${INTERVAL:-10}"
LOG="${LOG:-/root/vitotrol-a0-probe-$(date +%Y%m%d-%H%M%S).log}"
ROLLBACK_NEEDED=0

exec > >(tee -a "$LOG") 2>&1

req() {
  "$DBG" request "$1"
}

snapshot() {
  echo
  echo "=== SNAPSHOT $(date '+%F %T') ==="
  req 'r;0x27A0;1;raw;False'
  req 'r;0x0A5C;4;raw;False'
  req 'r;0x0896;2;raw;False'
  req 'r;0x089C;1;raw;False'
  req 'r;0xA132;29;raw;False'
  req 'r;0x7507;9;raw;False'
  req 'r;0x5738;1;raw;False'
}

rollback() {
  if [[ "$ROLLBACK_NEEDED" -eq 1 ]]; then
    echo
    echo "=== AUTOMATIC ROLLBACK: 0x27A0 -> 00 ==="
    req 'writeraw;0x27A0;00' || true
    sleep 2
    echo "=== VERIFY ROLLBACK ==="
    req 'r;0x27A0;1;raw;False' || true
    ROLLBACK_NEEDED=0
  fi
}

trap rollback EXIT
trap 'exit 130' INT TERM

echo "Log: $LOG"
echo "Duration: ${DURATION}s, interval: ${INTERVAL}s"

echo "=== PRE-WRITE BASELINE ==="
snapshot

# Set rollback armed before the write in case the command succeeds but the
# client is interrupted before it can report the response.
ROLLBACK_NEEDED=1

echo
echo "=== WRITE A1/M1 REMOTE IDENTIFICATION: 0 -> 1 (Vitotrol 200) ==="
req 'writeraw;0x27A0;01'

sleep 2
echo "=== IMMEDIATE READBACK ==="
req 'r;0x27A0;1;raw;False'

elapsed=0
while [[ "$elapsed" -lt "$DURATION" ]]; do
  snapshot
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
