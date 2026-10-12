#!/usr/bin/env bash
# Read-only, source-attested historical GWG EEPROM/PORT comparison window.
set -Eeuo pipefail
PATH=/usr/local/bin:/usr/bin:/bin
B=/root/wb2a-vitotrol-dual-readonly-20261011
ROOT=/home/chatgpt-admin/optolink-vitotrol-rpm-20261010
UNIT=wb2a-gwg-legacy-readtypes-restore-20261012
LIVE="$ROOT/tools/wb2a-gwg-legacy-readtypes-live.py"
ORIGINAL=/opt/optolink/settings_ini.py
EXPECT=e9a120ef37fe17236a7505ee713c8dd338d98d5093ed75dfb34629d7e8f5c42d
OUTPUT=/tmp/wb2a-gwg-legacy-readtypes-live-20261012.json
if [ "$(id -u)" -ne 0 ] || [ "$#" -ne 1 ] || [ "$1" != "--execute" ]; then
  echo REFUSED_ROOT_AND_EXPLICIT_EXECUTION; exit 80
fi
test -x "$B/restore.sh"
test -r "$B/settings_ini.before.py"
test -r "$LIVE"
test ! -e "$OUTPUT"
test "$(sha256sum "$ORIGINAL" | cut -d ' ' -f1)" = "$EXPECT"
test "$(sha256sum "$B/settings_ini.before.py" | cut -d ' ' -f1)" = "$EXPECT"
grep -qx 'vs1protocol = True' "$ORIGINAL"
for svc in optolink-splitter.service optolink-party-emulator.service optolink-schedule-manager.service optolink-service-programs.service optolink-maintenance-api.service; do
  systemctl is-active --quiet "$svc" || { echo "REFUSED_SERVICE:$svc"; exit 81; }
done
if [ "$(systemctl show "$UNIT.timer" -p LoadState --value)" = loaded ]; then
  echo REFUSED_TIMER_ALREADY_EXISTS; exit 82
fi
test -c /dev/serial/by-id/usb-Silicon_Labs_CP2102_USB_to_UART_Bridge_Controller_0001-if00-port0
python3 "$LIVE" > /tmp/wb2a-gwg-legacy-readtypes-dryrun-20261012.json
echo "RESTORE_ARMING $(date -Iseconds)"
systemd-run --unit="$UNIT" --on-active=3min --timer-property=AccuracySec=1s /bin/bash "$B/restore.sh"
systemctl is-active --quiet "$UNIT.timer"
echo RESTORE_ARMED
restore() {
  local rc=$?
  trap - EXIT
  echo "BEGIN_VS1_RESTORE rc=$rc $(date -Iseconds)"
  if /bin/bash "$B/restore.sh" &&
     systemctl is-active --quiet optolink-splitter.service &&
     test "$(sha256sum "$ORIGINAL" | cut -d ' ' -f1)" = "$EXPECT"; then
    echo VS1_RESTORE_VERIFIED
    systemctl stop "$UNIT.timer" || true
  else
    echo RESTORE_UNVERIFIED_TIMER_REMAINS
    rc=91
  fi
  exit "$rc"
}
trap restore EXIT
echo "STOP_SINGLE_OWNER $(date -Iseconds)"
timeout 30 systemctl stop optolink-splitter.service
if systemctl is-active --quiet optolink-splitter.service; then echo REFUSED_OWNER_RUNNING; exit 84; fi
systemctl is-active --quiet "$UNIT.timer"
echo "BEGIN_HISTORICAL_GWG_READTYPE_COMPARE $(date -Iseconds)"
timeout --signal=TERM --kill-after=5 65 /opt/optolink/venv/bin/python "$LIVE" --execute --output "$OUTPUT"
echo "END_READTYPE_COMPARE $(date -Iseconds)"
