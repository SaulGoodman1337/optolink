#!/usr/bin/env bash
set -euo pipefail
umask 077

# Reversible read-only P300 canary: no persistent systemd unit or settings edit.
# A transient timer automatically restores the prior VS1 unit.
MAIN=optolink-splitter.service
ORIGINAL=/opt/optolink
CANDIDATE=/opt/optolink-p300-candidate
STATE=/run/optolink-p300-trial
DROP_DIR=/run/systemd/system/optolink-splitter.service.d
DROP=$DROP_DIR/95-p300-canary.conf
SELF=/usr/local/sbin/optolink-p300-trial

writers=(optolink-clock-sync.timer optolink-clock-sync.service
  optolink-service-programs.service optolink-maintenance-api.service
  optolink-schedule-manager.service optolink-party-emulator.service)

say() { printf '[P300 trial] %s\n' "$*" >&2; }
die() { say "REFUSED: $*"; exit 1; }
require_root() { [[ $EUID -eq 0 ]] || die "run as root"; }

validate_candidate() {
  [[ -f "$CANDIDATE/optolinkvs2_switch.py" && -f "$CANDIDATE/optolink_p300.py" &&
     -f "$CANDIDATE/homeassistant_poll_list.py" ]] || die "candidate not staged"
  [[ -x "$ORIGINAL/venv/bin/python" ]] || die "production Python venv missing"
  [[ "$(stat -c '%U' "$CANDIDATE")" == optolink ]] ||
    die "candidate directory must be owned by optolink"
  [[ "$(stat -c '%U:%a' "$CANDIDATE/settings_ini.py")" == optolink:600 ]] ||
    die "candidate settings must be owned by optolink and mode 0600"
  python3 - "$CANDIDATE/settings_ini.py" "$ORIGINAL/settings_ini.py" <<'PY'
import ast, pathlib, sys
def values(path):
    result = {}
    tree = ast.parse(pathlib.Path(path).read_text())
    for n in tree.body:
        if isinstance(n, ast.Assign) and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name):
            try:
                result[n.targets[0].id] = ast.literal_eval(n.value)
            except (ValueError, TypeError):
                pass
    return result
p300, prod = map(values, sys.argv[1:])
required = dict(vs1protocol=False, p300_experimental=True,
                p300_virtual_write=False, p300_ram_read=False, port_vitoconnect=None)
if any(p300.get(key, object()) != value for key, value in required.items()):
    raise SystemExit("P300 candidate is not read-only")
for key in ("port_optolink", "mqtt_broker", "mqtt_listen", "mqtt_respond"):
    if p300.get(key) != prod.get(key):
        raise SystemExit("Settings differ in " + key)
if not p300.get("port_optolink") or not p300.get("mqtt_broker"):
    raise SystemExit("Configured serial port and MQTT broker required")
print("P300_CANDIDATE_PREFLIGHT=PASS")
PY
}

rollback() {
  say "Restoring original VS1 splitter..."
  systemctl stop "$MAIN" >/dev/null 2>&1 || true
  rm -f "$DROP"
  systemctl daemon-reload
  if ! systemctl restart "$MAIN" || ! systemctl is-active --quiet "$MAIN"; then
    say "VS1 restart failed; inspect journalctl -u $MAIN"
    return 1
  fi
  if [[ -f "$STATE/services" ]]; then
    while IFS= read -r unit; do
      [[ -z "$unit" ]] || systemctl start "$unit" || say "Restore failed for $unit"
    done < "$STATE/services"
  fi
  if [[ -f "$STATE/timer" ]]; then
    systemctl stop "$(cat "$STATE/timer").timer" >/dev/null 2>&1 || true
  fi
  rm -rf "$STATE"
  say "VS1 unit restored. Verify MQTT value freshness separately."
}

on_error() {
  trap - ERR INT TERM
  say "Activation failed or interrupted; rolling back."
  rollback || true
  exit 1
}

activate() {
  local seconds="$1"
  [[ "$seconds" =~ ^[0-9]+$ ]] || die "duration must be a number"
  (( seconds >= 120 && seconds <= 900 )) || die "duration must be 120..900 seconds"
  [[ ! -e "$STATE" && ! -e "$DROP" ]] || die "trial already present"
  systemctl is-active --quiet "$MAIN" || die "original VS1 splitter must be active"
  validate_candidate
  mkdir -p "$STATE" "$DROP_DIR"
  : > "$STATE/services"
  for unit in "${writers[@]}"; do
    if systemctl is-active --quiet "$unit"; then
      printf '%s\n' "$unit" >> "$STATE/services"
    fi
  done
  install -m 0755 "$0" "$SELF"
  local timer="optolink-p300-revert-$(date +%s)-$$"
  printf '%s\n' "$timer" > "$STATE/timer"
  # Arm rollback BEFORE interrupting VS1. The timer survives SSH disconnect.
  if ! systemd-run --quiet --unit="$timer" --on-active="${seconds}s" "$SELF" rollback; then
    rm -rf "$STATE"
    die "could not arm rollback timer"
  fi
  trap on_error ERR INT TERM
  for unit in "${writers[@]}"; do
    systemctl stop "$unit" >/dev/null 2>&1 || true
  done
  cat > "$DROP" <<'UNIT'
[Service]
WorkingDirectory=/opt/optolink-p300-candidate
ExecStart=
ExecStart=/opt/optolink/venv/bin/python /opt/optolink-p300-candidate/optolinkvs2_switch.py
UNIT
  systemctl daemon-reload
  systemctl restart "$MAIN"
  sleep 3
  systemctl is-active --quiet "$MAIN" || die "P300 service did not stay active"
  trap - ERR INT TERM
  say "Read-only P300 canary started, auto-rollback in ${seconds}s."
  say "Do not run update during the trial."
  say "Use journalctl -u $MAIN -n 80 --no-pager and optolink-debug."
  say "For early rollback: $SELF rollback"
}

status() {
  if [[ -f "$DROP" ]]; then say "P300 canary drop-in is present."; else say "No P300 drop-in."; fi
  systemctl show "$MAIN" -p WorkingDirectory -p ExecStart -p ActiveState --no-pager
  if [[ -f "$STATE/timer" ]]; then
    systemctl list-timers "$(cat "$STATE/timer").timer" --no-pager || true
  fi
}

require_root
mkdir -p /run/lock
exec 9>/run/lock/optolink-p300-trial.lock
flock -x 9
case "${1:-}" in
  activate) activate "${2:-300}" ;;
  rollback)
    if [[ -d "$STATE" || -e "$DROP" ]]; then rollback; else say "No active trial."; fi
    ;;
  status) status ;;
  *) echo "Usage: $0 activate [120..900 seconds] | rollback | status" >&2; exit 2 ;;
esac
