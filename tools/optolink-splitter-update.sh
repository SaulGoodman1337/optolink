#!/usr/bin/env bash
set -euo pipefail

APP_DIR="/opt/optolink"
CS_REPO="${COMMUNITY_SCRIPTS_REPO:-SaulGoodman1337/optolink}"
CS_REF="${COMMUNITY_SCRIPTS_REF:-optolink-splitter-ha}"
ROOT="${COMMUNITY_SCRIPTS_ROOT:-}"

info() { printf '[INFO] %s\n' "$*" >&2; }
ok()   { printf '[ OK ] %s\n' "$*" >&2; }
warn() { printf '[WARN] %s\n' "$*" >&2; }
die()  { printf '[FAIL] %s\n' "$*" >&2; exit 1; }

repo_file() {
  local rel="${1:?repo-relative path}"
  [[ -n "$ROOT" && -f "$ROOT/$rel" ]] || die "Repository file unavailable: $rel"
  printf '%s\n' "$ROOT/$rel"
}

install_repo_file() {
  local rel="${1:?repo-relative path}"
  local dest="${2:?destination}"
  local mode="${3:-0644}"
  install -D -m "$mode" "$(repo_file "$rel")" "$dest"
}

info "Optolink-Splitter + Home Assistant production update"
printf 'Repository: %s\nRef:        %s\n' "$CS_REPO" "$CS_REF" >&2

[[ -d "$APP_DIR/.git" && -f "$APP_DIR/settings_ini.py" ]] ||
  die "No Optolink-Splitter installation found in $APP_DIR"

info "Updating base system"
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get upgrade -y
ok "Base system updated"

info "Updating Python dependencies"
runuser -u optolink -- "$APP_DIR/venv/bin/pip" install --upgrade pip setuptools wheel pyserial paho-mqtt
ok "Python dependencies updated"

info "Installing production helpers"
install_repo_file tools/optolink-apply-vdensho1-ha-profile.sh /usr/local/bin/optolink-apply-vdensho1-ha-profile 0755
install_repo_file tools/optolink-debug.py /usr/local/bin/optolink-debug 0755
install_repo_file tools/optolink-party-test.sh /usr/local/bin/optolink-party-test 0755
install_repo_file config/optolink-splitter/optolink_maintenance_core.py "$APP_DIR/optolink_maintenance_core.py" 0644
install_repo_file tools/optolink-maintenance.py /usr/local/bin/optolink-maintenance 0750
install_repo_file tools/optolink-maintenance-api.py /usr/local/bin/optolink-maintenance-api 0750
install_repo_file tools/wb2a-schedule-probe.py /usr/local/bin/wb2a-schedule-probe 0750
install_repo_file tools/optolink-schedule-manager.py /usr/local/bin/optolink-schedule-manager 0755
install_repo_file tools/optolink-party-emulator.py /usr/local/bin/optolink-party-emulator 0755

ln -sf /usr/local/bin/optolink-debug /usr/bin/optolink-debug
ln -sf /usr/local/bin/optolink-party-test /usr/bin/optolink-party-test
ln -sf /usr/local/bin/optolink-maintenance /usr/bin/optolink-maintenance
ln -sf /usr/local/bin/wb2a-schedule-probe /usr/bin/wb2a-schedule-probe

chown root:optolink /usr/local/bin/optolink-maintenance-api

install_repo_file config/optolink-splitter/optolink-splitter.service /etc/systemd/system/optolink-splitter.service 0644
install_repo_file config/optolink-splitter/optolink-party-emulator.service /etc/systemd/system/optolink-party-emulator.service 0644
install_repo_file config/optolink-splitter/optolink-schedule-manager.service /etc/systemd/system/optolink-schedule-manager.service 0644
install_repo_file config/optolink-splitter/optolink-maintenance-api.service /etc/systemd/system/optolink-maintenance-api.service 0644
install_repo_file config/optolink-splitter/vcontrol-mapping.md /root/optolink-vcontrol-mapping.md 0644

touch "$APP_DIR/.maintenance.lock"
chown optolink:optolink "$APP_DIR/.maintenance.lock" "$APP_DIR/optolink_maintenance_core.py"
chmod 660 "$APP_DIR/.maintenance.lock"

systemctl daemon-reload
systemctl enable optolink-splitter.service >/dev/null 2>&1 || true

info "Activating validated VDensHO1/20C2 Home Assistant profile"
if COMMUNITY_SCRIPTS_ROOT="$ROOT" \
   COMMUNITY_SCRIPTS_GITHUB_TOKEN="${COMMUNITY_SCRIPTS_GITHUB_TOKEN:-}" \
   COMMUNITY_SCRIPTS_REPO="$CS_REPO" \
   COMMUNITY_SCRIPTS_REF="$CS_REF" \
   /usr/local/bin/optolink-apply-vdensho1-ha-profile; then
  ok "VDensHO1/20C2 Home Assistant profile active"
else
  die "Profile activation failed; helper attempted rollback"
fi

info "Configuring guarded maintenance MQTT API"
if runuser -u optolink -- "$APP_DIR/venv/bin/python" - <<'PY_MAINT_API'
import sys
sys.path.insert(0, "/opt/optolink")
from c_settings_adapter import settings
raise SystemExit(0 if getattr(settings, "mqtt_broker", None) else 1)
PY_MAINT_API
then
  systemctl enable optolink-maintenance-api.service >/dev/null 2>&1 || true
  systemctl restart optolink-maintenance-api.service
  ok "Maintenance MQTT API active"
else
  systemctl disable --now optolink-maintenance-api.service >/dev/null 2>&1 || true
  warn "Maintenance MQTT API disabled because mqtt_broker is not configured"
fi

info "Persisting production update channel"
install_repo_file tools/private-update.sh /usr/local/lib/community-scripts/private-update.sh 0755
cat >/etc/community-scripts-private.conf <<EOF
COMMUNITY_SCRIPTS_REPO=$CS_REPO
COMMUNITY_SCRIPTS_REF=$CS_REF
COMMUNITY_SCRIPTS_TARGET=tools/optolink-splitter-update.sh
EOF
chmod 600 /etc/community-scripts-private.conf
ln -sf /usr/local/lib/community-scripts/private-update.sh /usr/bin/update

ok "Optolink-Splitter + Home Assistant update completed"
printf '\nChecks:\n' >&2
printf '  systemctl status optolink-splitter --no-pager\n' >&2
printf '  systemctl status optolink-party-emulator --no-pager\n' >&2
printf '  systemctl status optolink-schedule-manager --no-pager\n' >&2
printf '  systemctl status optolink-maintenance-api --no-pager\n' >&2
printf '  optolink-maintenance status\n' >&2
