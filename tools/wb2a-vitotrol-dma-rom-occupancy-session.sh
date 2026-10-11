#!/usr/bin/env bash
# Operator-authorized, bounded native P300 READ ONLY window.
# Two independent restoration paths: EXIT trap + systemd timer.
set -Eeuo pipefail
PATH=/usr/local/bin:/usr/bin:/bin
B=/root/wb2a-vitotrol-dual-readonly-20261011
UNIT=wb2a-vitotrol-dma-rom-read-restore-20261011
PY=/home/chatgpt-admin/optolink-vitotrol-rpm-20261010/tools/wb2a-vitotrol-dual-readonly-probe.py
ORIGINAL=/opt/optolink/settings_ini.py
if [ "$(id -u)" != 0 ] || [ "$#" -ne 1 ] || [ "$1" != "--execute" ]; then
  echo "ROOT_AND_EXPLICIT_EXECUTE_REQUIRED"; exit 80
fi
test -r "$B/settings_ini.before.py"
test -x "$B/restore.sh"
test -f "$PY"
test "$(sha256sum "$ORIGINAL" | cut -d ' ' -f1)" = "$(sha256sum "$B/settings_ini.before.py" | cut -d ' ' -f1)"
grep -qx 'vs1protocol = True' "$ORIGINAL"
systemctl is-active --quiet optolink-splitter.service
systemctl is-active --quiet optolink-wb2a-rpm-passive-resume-20261011.service
echo "ARMING_INDEPENDENT_SYSTEMD_RESTORE $(date -Iseconds)"
systemd-run --unit="$UNIT" --on-active=4min --timer-property=AccuracySec=1s /bin/bash "$B/restore.sh"
systemctl is-active --quiet "$UNIT.timer"
echo "WATCHDOG_TIMER_ACTIVE $(date -Iseconds)"
rollback() {
  local rc=$?
  trap - EXIT
  echo "READONLY_SESSION_ROLLBACK rc=$rc $(date -Iseconds)"
  if /bin/bash "$B/restore.sh"; then
    echo "READONLY_SESSION_MANUAL_RESTORE_OK"
    systemctl stop "$UNIT.timer" || true
  else
    echo "INDEPENDENT_WATCHDOG_LEFT_ARMED"
    rc=81
  fi
  exit "$rc"
}
trap rollback EXIT
echo "STOP_SINGLE_SERIAL_OWNER $(date -Iseconds)"
timeout 25 systemctl stop optolink-splitter.service
python3 - "$ORIGINAL" <<'PY'
import sys
from pathlib import Path
p=Path(sys.argv[1])
s=p.read_text()
assert s.count("vs1protocol = True")==1
p.write_text(s.replace("vs1protocol = True","vs1protocol = False",1))
PY
echo "START_SAME_OWNER_NATIVE_P300 $(date -Iseconds)"
systemctl start optolink-splitter.service
sleep 4
grep -qx 'vs1protocol = False' "$ORIGINAL"
echo "START_FC03_AND_FC99_READONLY_PROBES $(date -Iseconds)"
timeout --signal=TERM --kill-after=5 185 python3 "$PY" --execute --dma-only --cycles 5 --output /tmp/wb2a-vitotrol-dma-rom-occupancy-live-20261011.json
echo "READONLY_PROBES_FINISHED $(date -Iseconds)"
