#!/usr/bin/env bash
# WB2A 20C2/0103: P300 FC03 read-only two-cycle / five known RAM windows.
# Independent existing VS1 restore timer MUST arm before altering host config.
# Safe on premature exit; no controller memory write, reset, SFR, DMA, UART1.
set -Eeuo pipefail
umask 077
PATH=/usr/local/bin:/usr/bin:/bin
B=/root/wb2a-vitotrol-dual-readonly-20261011
UNIT=wb2a-postrestart-5win-restore-20261012
ORIGINAL=/opt/optolink/settings_ini.py
RESEARCH=/home/chatgpt-admin/optolink-wb2a-research-20261010
PROBE="$RESEARCH/tools/wb2a-postrestart-five-window-readonly.py"
GATE=/home/chatgpt-admin/optolink-vitotrol-rpm-20261010/tools/wb2a-experiment-fault-gate.py
BASE=/tmp/wb2a-5win-fault-baseline-20261012.json
OUTPUT=/tmp/wb2a-postrestart-five-window-live-20261012.json
SHA=e9a120ef37fe17236a7505ee713c8dd338d98d5093ed75dfb34629d7e8f5c42d
if [ "$(id -u)" -ne 0 ] || [ "$#" -ne 1 ] || [ "$1" != "--execute" ]; then
  echo "ROOT_AND_EXPLICIT_EXECUTE_REQUIRED";exit 80
fi
for f in "$B/settings_ini.before.py" "$B/restore.sh" "$PROBE" "$GATE" "$BASE";do
  test -f "$f" && test ! -L "$f"
done
test -x "$B/restore.sh"
test ! -e "$OUTPUT"
test "$(sha256sum "$ORIGINAL" | cut -d' ' -f1)" = "$SHA"
test "$(sha256sum "$B/settings_ini.before.py" | cut -d' ' -f1)" = "$SHA"
grep -qx 'vs1protocol = True' "$ORIGINAL"
for s in optolink-splitter.service optolink-party-emulator.service optolink-schedule-manager.service optolink-service-programs.service optolink-maintenance-api.service; do
 systemctl is-active --quiet "$s"
done
test "$(systemctl show "$UNIT.timer" -p LoadState --value)" != loaded
python3 - "$GATE" "$BASE" <<'PY'
import importlib.util, json, sys
from datetime import datetime,timezone
from pathlib import Path
sp=importlib.util.spec_from_file_location("fivewin_original_fault_gate",sys.argv[1])
m=importlib.util.module_from_spec(sp);sys.modules[sp.name]=m;sp.loader.exec_module(m)
raw=Path(sys.argv[2]).read_bytes()
if not 32<=len(raw)<=m.MAX_BYTES:raise SystemExit("FAIL_PRECHECK_UNTRUSTED_BASELINE_SIZE")
baseline=json.loads(raw)
m.validate(baseline)
age=(datetime.now(timezone.utc)-datetime.fromisoformat(baseline["captured_at_utc"])).total_seconds()
if not 0<=age<=900:raise SystemExit(f"FAIL_PRECHECK_STALE_BASELINE_AGE_{age}")
if baseline.get("active_fault_at_capture") is not False:raise SystemExit("FAIL_PRECHECK_ACTIVE_HEATER_FAULT")
if baseline.get("checked_all_gfa_slots") is not True:raise SystemExit("FAIL_PRECHECK_NO_COMPLETE_GFA_HISTORY")
print("FULL_FAULT_ARCHIVE_PRECHECK_PASSED",round(age,1),"seconds",flush=True)
PY
echo "ARMING_INDEPENDENT_VS1_RESTORE $(date -Iseconds)"
systemd-run --unit="$UNIT" --on-active=3min --timer-property=AccuracySec=1s /bin/bash "$B/restore.sh"
systemctl is-active --quiet "$UNIT.timer"
echo "INDEPENDENT_RESTORE_ARMED"
rollback() {
  local rc=$?
  trap - EXIT
  echo "RESTORE_ON_EXIT rc=$rc $(date -Iseconds)"
  if timeout 50 /bin/bash "$B/restore.sh"; then
    echo "RESTORE_SCRIPT_RETURNED_OK"
    if test "$(sha256sum "$ORIGINAL" | cut -d' ' -f1)" = "$SHA" &&
       systemctl is-active --quiet optolink-splitter.service;then
      systemctl stop "$UNIT.timer" || :
      echo "VS1_RESTORE_CONFIRMED"
    else
      echo "VS1_RESTORE_VERIFY_FAILED: INDEPENDENT_WATCHDOG_KEPT_ARMED"
      rc=86
    fi
  else
    echo "RESTORE_SCRIPT_FAILED: INDEPENDENT_WATCHDOG_KEPT_ARMED"
    rc=86
  fi
  exit "$rc"
}
trap rollback EXIT
echo "STOPPING_EXISTING_SINGLE_OWNER"
timeout 25 systemctl stop optolink-splitter.service
python3 - "$ORIGINAL" <<'PY'
from pathlib import Path
import sys
p=Path(sys.argv[1])
s=p.read_text()
assert s.count("vs1protocol = True")==1
p.write_text(s.replace("vs1protocol = True","vs1protocol = False",1))
PY
echo "RESTART_SAME_OWNER_IN_NATIVE_P300"
timeout 25 systemctl start optolink-splitter.service
sleep 3
grep -qx 'vs1protocol = False' "$ORIGINAL"
echo "READING_FIVE_LOW_SRAM_WINDOWS_TWICE"
timeout --signal=TERM --kill-after=5 100 /opt/optolink/venv/bin/python "$PROBE" --execute --output "$OUTPUT"
echo "FIVE_WINDOW_P300_CAPTURE_COMPLETE $(date -Iseconds)"
