#!/usr/bin/env bash
# Historical OpenV P300 FC01 length over-read, fully read-only, independent rollback.
set -Eeuo pipefail
PATH=/usr/local/bin:/usr/bin:/bin
B=/root/wb2a-vitotrol-dual-readonly-20261011
ORIG=/opt/optolink/settings_ini.py
UNIT=wb2a-vitotrol-p300-nonff-restore-20261012
PY=/home/chatgpt-admin/optolink-vitotrol-rpm-20261010/tools/wb2a-vitotrol-p300-nonff-overread-readonly.py
OUT=/tmp/wb2a-vitotrol-p300-nonff-live-20261012.json
VS1=/tmp/wb2a-vitotrol-p300-nonff-vs1-before-20261012.log
ORIGINAL_SHA=e9a120ef37fe17236a7505ee713c8dd338d98d5093ed75dfb34629d7e8f5c42d
VS1_SOURCE_SHA=d16967b41cf6717abb597cdea3e95b53f77d554b115262acc93e53f31799bd36
if [ "$(id -u)" -ne 0 ] || [ "$#" -ne 1 ] || [ "$1" != "--execute" ]; then
  echo REFUSE_ROOT_EXPLICIT_EXECUTION_REQUIRED
  exit 80
fi
test -f "$PY" && test -x "$B/restore.sh" && test -r "$B/settings_ini.before.py"
test ! -e "$OUT"
test "$(sha256sum "$VS1" | cut -d ' ' -f1)" = "$VS1_SOURCE_SHA"
test "$(sha256sum "$ORIG" | cut -d ' ' -f1)" = "$ORIGINAL_SHA"
test "$(sha256sum "$B/settings_ini.before.py" | cut -d ' ' -f1)" = "$ORIGINAL_SHA"
grep -qx 'vs1protocol = True' "$ORIG"
for svc in optolink-splitter.service optolink-party-emulator.service optolink-schedule-manager.service optolink-service-programs.service optolink-maintenance-api.service; do
  systemctl is-active --quiet "$svc" || { echo "REFUSE_$svc"; exit 81; }
done
if [ "$(systemctl show "$UNIT.timer" -p LoadState --value)" = loaded ]; then
  echo REFUSE_EXISTING_RESTORE_UNIT
  exit 82
fi
echo "ARM_INDEPENDENT_RESTORE $(date -Iseconds)"
systemd-run --unit="$UNIT" --on-active=4min --timer-property=AccuracySec=1s /bin/bash "$B/restore.sh"
systemctl is-active --quiet "$UNIT.timer"
echo "ARMED"
rollback() {
  local rc=$?
  trap - EXIT
  echo "EXIT_RESTORE rc=$rc $(date -Iseconds)"
  if /bin/bash "$B/restore.sh"; then
    echo "VERIFIED_ORIGINAL_RESTORE"
    systemctl stop "$UNIT.timer" || true
  else
    echo "ERROR_RESTORE_INDEPENDENT_TIMER_REMAINS_ARMED"
    rc=90
  fi
  exit "$rc"
}
trap rollback EXIT
echo "STOP_ORIGINAL_OWNER"
timeout 25 systemctl stop optolink-splitter.service
if systemctl is-active --quiet optolink-splitter.service; then
  echo REFUSE_PORT_OWNER_STILL_ACTIVE
  exit 83
fi
python3 - "$ORIG" <<'PY'
from pathlib import Path
import sys
p=Path(sys.argv[1])
s=p.read_text()
assert s.count('vs1protocol = True')==1
p.write_text(s.replace('vs1protocol = True','vs1protocol = False',1))
PY
echo "START_SAME_OWNER_P300"
timeout 25 systemctl start optolink-splitter.service
sleep 3
grep -qx 'vs1protocol = False' "$ORIG"
echo "BEGIN_P300_FC01_NONFF_27A8_EXACT_23_READS"
timeout --signal=TERM --kill-after=5 150 /opt/optolink/venv/bin/python "$PY" --execute --output "$OUT"
echo "SOURCE_CAPTURED"
