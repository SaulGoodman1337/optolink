#!/usr/bin/env bash
# Independent systemd-run rollback of a temporary READ-ONLY native-P300 phase.
# Does not touch controller RAM, codings, UART/SFR, or MQTT/serial ownership.
set -uo pipefail
PATH=/usr/local/bin:/usr/bin:/bin
B=/root/wb2a-vitotrol-dual-readonly-20261011
exec >> "$B/restore.log" 2>&1
echo "ROLLBACK_START $(date -Iseconds)"
if ! test -f "$B/settings_ini.before.py"; then
  echo "FAIL_MISSING_ORIGINAL"; exit 70
fi
expected=$(sha256sum "$B/settings_ini.before.py" | awk '{print $1}')
current=$(sha256sum /opt/optolink/settings_ini.py | awk '{print $1}')
echo "ORIGINAL_SHA256=$expected CURRENT_SHA256=$current"
if [ "$expected" != "$current" ]; then
  echo "ORIGINAL_CONFIG_CHANGED: force exact snapshot restore"
  timeout 25 systemctl stop optolink-splitter.service || true
  if [ "$(systemctl show optolink-splitter.service -p ActiveState --value)" = "deactivating" ]; then
    systemctl kill --kill-whom=main --signal=SIGKILL optolink-splitter.service || true
    sleep 1
  fi
  cp -p "$B/settings_ini.before.py" /opt/optolink/settings_ini.py
  systemctl reset-failed optolink-splitter.service || true
  systemctl start optolink-splitter.service || true
fi
if ! systemctl is-active --quiet optolink-splitter.service; then
  echo "MAIN_NOT_ACTIVE_ATTEMPT_START"
  systemctl start optolink-splitter.service || true
fi
# These previously active services are stopped transitively when the main
# Splitter stops on this installation. Restore only the snapshotted active units.
if [ -r "$B/initial-services.txt" ]; then
  while read -r unit originally; do
    if [ "$originally" = "active" ] && [ "$unit" != "optolink-splitter.service" ]; then
      echo "RESTORE_DEPENDENCY $unit"
      systemctl start "$unit" || echo "WARNING_DEPENDENCY_START_FAILED $unit"
    fi
  done < "$B/initial-services.txt"
fi
sleep 3
flag=$(grep -E '^vs1protocol = ' /opt/optolink/settings_ini.py || true)
echo "FLAG=$flag"
systemctl is-active optolink-splitter.service || true
systemctl is-active optolink-wb2a-rpm-passive-resume-20261011.service || true
echo "READ_ONLY_POSTCHECK"
timeout 12 optolink-debug request 'read;0x00f8;8' --timeout 7 2>&1 |grep '<- openv/resp:' || true
timeout 12 optolink-debug request 'read;0x5738;1' --timeout 7 2>&1 |grep '<- openv/resp:' || true
actual=$(sha256sum /opt/optolink/settings_ini.py | awk '{print $1}')
if [ "$expected" != "$actual" ] || ! systemctl is-active --quiet optolink-splitter.service; then
  echo "FAIL_RESTORE_MISMATCH"; exit 71
fi
echo "ROLLBACK_OK $(date -Iseconds)"
