#!/usr/bin/env bash
# Independent restoration for a bounded, original-owner P300 RX-READ-only test.
# Does not require the already-expired RPM logger and never sends write requests.
set -Eeuo pipefail
PATH=/usr/local/bin:/usr/bin:/bin
B=/root/wb2a-vitotrol-dual-readonly-20261011
UNIT=wb2a-vitotrol-persistent-rx-restore-20261011
PY=/home/chatgpt-admin/optolink-vitotrol-rpm-20261010/tools/wb2a-vitotrol-persistent-mqtt-readonly.py
ORIGINAL=/opt/optolink/settings_ini.py
if [ "$(id -u)" -ne 0 ] || [ "$#" -ne 1 ] || [ "$1" != "--execute" ]; then
  echo ROOT_AND_EXPLICIT_EXECUTION_REQUIRED
  exit 80
fi
test -r "$B/settings_ini.before.py"
test -x "$B/restore.sh"
test -r "$PY"
test "$(sha256sum "$ORIGINAL" | cut -d ' ' -f1)" = "$(sha256sum "$B/settings_ini.before.py" | cut -d ' ' -f1)"
grep -qx 'vs1protocol = True' "$ORIGINAL"
systemctl is-active --quiet optolink-splitter.service
for u in optolink-party-emulator.service optolink-schedule-manager.service optolink-service-programs.service optolink-maintenance-api.service; do
  systemctl is-active --quiet "$u"
done
test "$(systemctl show "$UNIT.timer" -p LoadState --value)" != loaded
echo "ARMING_INDEPENDENT_RESTORE $(date -Iseconds)"
systemd-run --unit="$UNIT" --on-active=4min --timer-property=AccuracySec=1s /bin/bash "$B/restore.sh"
systemctl is-active --quiet "$UNIT.timer"
echo "RESTORE_TIMER_ACTIVE"
rollback() {
  local rc=$?
  trap - EXIT
  echo "RX_BURST_EXIT_RESTORE rc=$rc $(date -Iseconds)"
  if /bin/bash "$B/restore.sh"; then
    echo "RESTORE_VERIFIED"
    systemctl stop "$UNIT.timer" || true
  else
    echo "INDEPENDENT_TIMER_LEFT_ACTIVE"
    rc=81
  fi
  exit "$rc"
}
trap rollback EXIT
echo "TEMPORARILY_STOP_ORIGINAL_SERIAL_OWNER"
timeout 25 systemctl stop optolink-splitter.service
python3 - "$ORIGINAL" <<'PY'
from pathlib import Path
import sys
p=Path(sys.argv[1])
text=p.read_text()
assert text.count("vs1protocol = True")==1
p.write_text(text.replace("vs1protocol = True","vs1protocol = False",1))
PY
echo "RESTART_SAME_SPLITTER_IN_NATIVE_P300"
timeout 25 systemctl start optolink-splitter.service
sleep 3
grep -qx 'vs1protocol = False' "$ORIGINAL"
echo "BEGIN_WHITELIST_READS"
timeout --signal=TERM --kill-after=5 130 /opt/optolink/venv/bin/python "$PY" --execute --mode p300 --cycles 32 --output /tmp/wb2a-vitotrol-persistent-p300-live-20261011.json
echo "RX_BURST_COMPLETE"
