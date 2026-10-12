#!/usr/bin/env bash
# Short, original-owner-free historical GWG read-only vs WB2A KW direct serial.
# Independently armed original VS1 restoration before stopping production owner.
set -Eeuo pipefail
PATH=/usr/local/bin:/usr/bin:/bin
B=/root/wb2a-vitotrol-dual-readonly-20261011
UNIT=wb2a-v200kw2-gwg-legacy-restore-20261012
ROOT=/home/chatgpt-admin/optolink-vitotrol-rpm-20261010
PY="$ROOT/tools/wb2a-v200kw2-gwg-live-readonly.py"
ORIGINAL=/opt/optolink/settings_ini.py
EXACT_SHA=e9a120ef37fe17236a7505ee713c8dd338d98d5093ed75dfb34629d7e8f5c42d
OUTPUT=/tmp/wb2a-v200kw2-gwg-legacy-readonly-20261012.json
if [ "$(id -u)" -ne 0 ] || [ "$#" -ne 1 ] || [ "$1" != "--execute" ]; then
    echo "REFUSED: root and explicit --execute required"
    exit 80
fi
test -r "$PY"
test -x "$B/restore.sh"
test -r "$B/settings_ini.before.py"
test "$(sha256sum "$ORIGINAL" | cut -d ' ' -f1)" = "$EXACT_SHA"
test "$(sha256sum "$B/settings_ini.before.py" | cut -d ' ' -f1)" = "$EXACT_SHA"
grep -qx 'vs1protocol = True' "$ORIGINAL"
for svc in optolink-splitter.service optolink-party-emulator.service optolink-schedule-manager.service optolink-service-programs.service optolink-maintenance-api.service; do
    systemctl is-active --quiet "$svc" || { echo "REFUSED_SERVICE_NOT_ACTIVE:$svc"; exit 81; }
done
if [ "$(systemctl show "$UNIT.timer" -p LoadState --value)" = loaded ]; then
    echo "REFUSED_RESTORE_UNIT_ALREADY_EXISTS"
    exit 82
fi
if [ -e "$OUTPUT" ]; then
    echo "REFUSED_OUTPUT_ALREADY_EXISTS"
    exit 83
fi
echo "ARM_INDEPENDENT_RESTORE $(date -Iseconds)"
systemd-run --unit="$UNIT" --on-active=3min --timer-property=AccuracySec=1s /bin/bash "$B/restore.sh"
systemctl is-active --quiet "$UNIT.timer"
echo "RESTORE_TIMER_ARMED"
restore() {
    local rc=$?
    trap - EXIT
    echo "EXIT_ORIGINAL_VS1_RESTORE rc=$rc at $(date -Iseconds)"
    if /bin/bash "$B/restore.sh"; then
        echo "ORIGINAL_RESTORE_COMPLETE"
        systemctl stop "$UNIT.timer" || true
    else
        echo "RESTORE_FAILED_INDEPENDENT_TIMER_STAYS_ARMED"
        rc=90
    fi
    exit "$rc"
}
trap restore EXIT
echo "STOP_ORIGINAL_SERIAL_OWNER"
timeout 30 systemctl stop optolink-splitter.service
if systemctl is-active --quiet optolink-splitter.service; then
    echo "REFUSED_OWNER_STILL_ACTIVE"
    exit 84
fi
grep -qx 'vs1protocol = True' "$ORIGINAL"
echo "BEGIN_EXACT_HISTORICAL_GWG_READ_ONLY"
timeout --signal=TERM --kill-after=5 110 /opt/optolink/venv/bin/python "$PY" --execute --output "$OUTPUT"
echo "GWG_READONLY_CAPTURE_COMPLETE"
