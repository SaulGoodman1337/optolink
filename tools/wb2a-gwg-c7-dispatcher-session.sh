#!/usr/bin/env bash
# Independently restored, source-pinned GWG C7 live dispatcher acceptance window.
# All runtime edits are confined to a PRIVATE mktemp staging directory.
set -Eeuo pipefail
PATH=/usr/local/bin:/usr/bin:/bin
B=/root/wb2a-vitotrol-dual-readonly-20261011
UNIT=wb2a-gwg-c7-dispatcher-restore-20261012
ROOT=/home/chatgpt-admin/optolink-vitotrol-rpm-20261010
PROD=/opt/optolink
PY="$ROOT/tools/wb2a-gwg-c7-dispatcher-live.py"
PATCH="$ROOT/tools/optolink-apply-gwg-readonly-patch.py"
OUTPUT=/tmp/wb2a-gwg-c7-dispatcher-live-20261012.json
EXACT_SHA=e9a120ef37fe17236a7505ee713c8dd338d98d5093ed75dfb34629d7e8f5c42d
ADAPTER_SHA=67a760e925719225d61e375e9c976743b7bfb2d6bec8a9ea59d612397c4b3de2
REQUESTS_SHA=7cc01e2fb41a56adf0f395a86a2a352411c9632032744eeb59ebfd669c51f790
if [ "$(id -u)" -ne 0 ] || [ "$#" -ne 1 ] || [ "$1" != "--execute" ]; then
  echo "REFUSED_ROOT_AND_EXPLICIT_EXECUTION_REQUIRED"; exit 80
fi
for path in "$B/restore.sh" "$B/settings_ini.before.py" "$PY" "$PATCH"; do
  test -r "$path" || { echo "REFUSED_MISSING:$path"; exit 81; }
done
test -x "$B/restore.sh"
test "$(sha256sum "$PROD/settings_ini.py" | cut -d ' ' -f1)" = "$EXACT_SHA"
test "$(sha256sum "$B/settings_ini.before.py" | cut -d ' ' -f1)" = "$EXACT_SHA"
test "$(sha256sum "$PROD/vs12_adapter.py" | cut -d ' ' -f1)" = "$ADAPTER_SHA"
test "$(sha256sum "$PROD/requests_util.py" | cut -d ' ' -f1)" = "$REQUESTS_SHA"
grep -qx 'vs1protocol = True' "$PROD/settings_ini.py"
test -c /dev/serial/by-id/usb-Silicon_Labs_CP2102_USB_to_UART_Bridge_Controller_0001-if00-port0
test ! -e "$OUTPUT"
for svc in optolink-splitter.service optolink-party-emulator.service optolink-schedule-manager.service optolink-service-programs.service optolink-maintenance-api.service; do
  systemctl is-active --quiet "$svc" || { echo "REFUSED_SERVICE_NOT_ACTIVE:$svc"; exit 82; }
done
if [ "$(systemctl show "$UNIT.timer" -p LoadState --value)" = loaded ]; then
  echo "REFUSED_RESTORE_TIMER_EXISTS"; exit 83
fi
STAGE="$(mktemp -d /tmp/wb2a-gwg-c7-stage-20261012.XXXXXXXX)"
chmod 700 "$STAGE"
cp "$PROD/vs12_adapter.py" "$PROD/requests_util.py" "$STAGE/"
echo "STAGE_PRIVATE_PATH=$STAGE"
python3 "$PATCH" --root "$STAGE" --apply
/opt/optolink/venv/bin/python "$PY" > /tmp/wb2a-gwg-c7-dispatcher-dryrun-20261012.json
echo "ARM_INDEPENDENT_RESTORE $(date -Iseconds)"
systemd-run --unit="$UNIT" --on-active=3min --timer-property=AccuracySec=1s /bin/bash "$B/restore.sh"
systemctl is-active --quiet "$UNIT.timer"
echo "RESTORE_TIMER_ARMED"
restore() {
  local rc=$?
  trap - EXIT
  echo "EXIT_RESTORE rc=$rc at $(date -Iseconds)"
  if /bin/bash "$B/restore.sh"; then
    echo "ORIGINAL_VS1_RESTORE_SCRIPT_SUCCEEDED"
    if systemctl is-active --quiet optolink-splitter.service &&
       test "$(sha256sum "$PROD/settings_ini.py" | cut -d ' ' -f1)" = "$EXACT_SHA"; then
      systemctl stop "$UNIT.timer" || true
      echo "ORIGINAL_SERVICE_AND_CONFIG_VERIFIED"
    else
      echo "RESTORE_POSTCHECK_FAILED_TIMER_REMAINS"
      rc=91
    fi
  else
    echo "RESTORE_FAILED_TIMER_REMAINS_ARMED"
    rc=90
  fi
  exit "$rc"
}
trap restore EXIT
echo "STOP_SINGLE_SERIAL_OWNER $(date -Iseconds)"
timeout 30 systemctl stop optolink-splitter.service
if systemctl is-active --quiet optolink-splitter.service; then
  echo "REFUSED_OWNER_STILL_RUNNING"; exit 84
fi
systemctl is-active --quiet "$UNIT.timer"
echo "BEGIN_DISPATCHER_HARDWARE_READS $(date -Iseconds)"
timeout --signal=TERM --kill-after=5 75 /opt/optolink/venv/bin/python "$PY" --execute --stage "$STAGE" --output "$OUTPUT"
echo "END_DISPATCHER_HARDWARE_READS $(date -Iseconds)"
