#!/usr/bin/env bash
set -euo pipefail

# In-place production updater for an existing /opt/optolink installation.
#
# The repository has already been materialized by tools/private-run.sh and is
# passed in via COMMUNITY_SCRIPTS_ROOT. This updater installs only the
# production helpers/units, then delegates the risky runtime/profile changes to
# optolink-apply-vdensho1-ha-profile.sh. It deliberately does not deploy files
# from the research or web branches.
#
# Order matters:
#   1. update OS/Python prerequisites;
#   2. install versioned helper files and systemd units;
#   3. activate/validate the boiler profile transactionally;
#   4. enable optional MQTT-backed services;
#   5. persist this same branch as the future update channel.

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

# Never replace a library underneath an active supervised hardware window.
if systemctl is-active --quiet optolink-hybrid-continuous-canary.service; then
  die "Hybrid Canary aktiv: zuerst unabhaengige Rueckkehr zu VS1 pruefen."
fi

# Keep host packages current before changing the application runtime.
info "Updating base system"
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get upgrade -y
ok "Base system updated"

info "Updating Python dependencies"
runuser -u optolink -- "$APP_DIR/venv/bin/pip" install --upgrade pip setuptools wheel pyserial paho-mqtt
ok "Python dependencies updated"

# Copy immutable repository artifacts into their runtime locations. No helper
# below should fetch a different branch on its own during this update.
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
install_repo_file tools/optolink-clock-sync.py /usr/local/bin/optolink-clock-sync 0755
/usr/local/bin/optolink-clock-sync --self-test
install_repo_file tools/optolink-service-programs.py /usr/local/bin/optolink-service-programs 0755
/usr/local/bin/optolink-service-programs --self-test

ln -sf /usr/local/bin/optolink-debug /usr/bin/optolink-debug
ln -sf /usr/local/bin/optolink-party-test /usr/bin/optolink-party-test
ln -sf /usr/local/bin/optolink-maintenance /usr/bin/optolink-maintenance
ln -sf /usr/local/bin/wb2a-schedule-probe /usr/bin/wb2a-schedule-probe

chown root:optolink /usr/local/bin/optolink-maintenance-api

install_repo_file config/optolink-splitter/optolink-splitter.service /etc/systemd/system/optolink-splitter.service 0644
install_repo_file config/optolink-splitter/optolink-party-emulator.service /etc/systemd/system/optolink-party-emulator.service 0644
install_repo_file config/optolink-splitter/optolink-schedule-manager.service /etc/systemd/system/optolink-schedule-manager.service 0644
install_repo_file config/optolink-splitter/optolink-maintenance-api.service /etc/systemd/system/optolink-maintenance-api.service 0644
install_repo_file config/optolink-splitter/optolink-clock-sync.service /etc/systemd/system/optolink-clock-sync.service 0644
install_repo_file config/optolink-splitter/optolink-clock-sync.timer /etc/systemd/system/optolink-clock-sync.timer 0644
install_repo_file config/optolink-splitter/optolink-service-programs.service /etc/systemd/system/optolink-service-programs.service 0644
install_repo_file config/optolink-splitter/vcontrol-mapping.md /root/optolink-vcontrol-mapping.md 0644

touch "$APP_DIR/.maintenance.lock"
chown optolink:optolink "$APP_DIR/.maintenance.lock" "$APP_DIR/optolink_maintenance_core.py"
chmod 660 "$APP_DIR/.maintenance.lock"

systemctl daemon-reload
systemctl enable optolink-splitter.service >/dev/null 2>&1 || true

# Runtime patching, backups, discovery validation and rollback live in the
# profile helper so fresh installs and updates share exactly one activation path.
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

# Install only a reviewed, explicitly listed *runtime* library. No research
# probes, RAM-write helpers or continuous background service are installed.
# The CLI stages a hashed side-by-side release only upon an operator command.
info "Installing guarded read-only hybrid tools (default: disabled)"
hybrid_module_manifest="$(repo_file tools/optolink-hybrid-modules.txt)"
install -d -m 0755 /usr/local/lib/optolink-hybrid/handover_acceleration
hybrid_count=0
while IFS= read -r module || [[ -n "$module" ]]; do
  [[ "$module" =~ ^[a-z][a-z0-9_]*[.]py$ || "$module" == "__init__.py" ]] ||
    die "Unapproved hybrid module name in manifest"
  install_repo_file "tools/handover_acceleration/$module" \
    "/usr/local/lib/optolink-hybrid/handover_acceleration/$module" 0644
  hybrid_count=$((hybrid_count + 1))
done <"$hybrid_module_manifest"
[[ "$hybrid_count" -eq 20 ]] || die "Incomplete reviewed hybrid module set"
install_repo_file tools/optolink-hybrid.py /usr/local/bin/optolink-hybrid 0755
install_repo_file tools/optolink-update-main-umstellen.sh /usr/local/bin/optolink-update-main-umstellen 0750
ln -sf /usr/local/bin/optolink-hybrid /usr/bin/optolink-hybrid
PYTHONPATH=/usr/local/lib/optolink-hybrid "$APP_DIR/venv/bin/python" - <<'PY_HYBRID'
from handover_acceleration import continuous_canary, stage_release, release_rollout
assert continuous_canary.TARGET_WINDOWS == 3
assert continuous_canary.MAX_RUNTIME_SECONDS == 270
assert callable(stage_release.stage)
assert callable(release_rollout.stage_root_copy)
print("Hybrid-Laufzeitbibliothek: importierbar; physische Umschaltung bleibt aus.")
PY_HYBRID
ok "Optional hybrid CLI installed (optolink-hybrid status / vorbereiten / pruefen / testen)"

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

info "Configuring WB2A system clock synchronization"
if runuser -u optolink -- "$APP_DIR/venv/bin/python" - <<'PY_CLOCK'
import sys
sys.path.insert(0, "/opt/optolink")
from c_settings_adapter import settings
raise SystemExit(0 if getattr(settings, "mqtt_broker", None) else 1)
PY_CLOCK
then
  systemctl enable --now optolink-clock-sync.timer >/dev/null 2>&1 || true
  if systemctl is-active --quiet optolink-splitter.service; then
    if systemctl start optolink-clock-sync.service; then
      ok "WB2A system clock checked/synchronized; 15-minute timer active"
    else
      warn "Clock sync check failed; timer remains active for the next retry"
      journalctl -u optolink-clock-sync.service -n 20 --no-pager >&2 || true
    fi
  else
    warn "Clock sync timer enabled, but splitter is not active yet"
  fi
else
  systemctl disable --now optolink-clock-sync.timer >/dev/null 2>&1 || true
  warn "Clock sync disabled because mqtt_broker is not configured"
fi

# Make future `update` invocations stay on this production branch.
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
printf '  systemctl status optolink-clock-sync.timer --no-pager\n' >&2
printf '  systemctl status optolink-service-programs --no-pager\n' >&2
printf '  journalctl -u optolink-clock-sync.service -n 20 --no-pager\n' >&2
printf '  optolink-maintenance status\n' >&2
