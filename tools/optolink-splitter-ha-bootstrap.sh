#!/usr/bin/env bash
set -euo pipefail

REPO="${COMMUNITY_SCRIPTS_REPO:-SaulGoodman1337/optolink}"
REF="${COMMUNITY_SCRIPTS_REF:-optolink-splitter-ha}"
TARGET="tools/optolink-splitter-update.sh"

die() { printf '[FAIL] %s\n' "$*" >&2; exit 1; }
info() { printf '[INFO] %s\n' "$*" >&2; }

[[ "${EUID:-$(id -u)}" -eq 0 ]] || die "Run this bootstrap as root."
[[ -d /opt/optolink/.git && -f /opt/optolink/settings_ini.py ]] ||
  die "No existing Optolink-Splitter installation found in /opt/optolink."

command -v curl >/dev/null 2>&1 || die "curl is required."
command -v tar >/dev/null 2>&1 || die "tar is required."

info "Switching Optolink deployment channel to $REPO @ $REF"

tmp="$(mktemp)"
trap 'rm -f "$tmp"' EXIT

curl -fsSL   "https://raw.githubusercontent.com/$REPO/$REF/tools/private-run.sh"   -o "$tmp"

COMMUNITY_SCRIPTS_REPO="$REPO" COMMUNITY_SCRIPTS_REF="$REF" bash "$tmp" "$TARGET"

printf '\n[ OK ] Production channel active: %s @ %s\n' "$REPO" "$REF" >&2
printf '[ OK ] Future updates: run "update"\n' >&2
