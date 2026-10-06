#!/usr/bin/env bash
set -euo pipefail

CONF="/etc/community-scripts-private.conf"
TOKEN_FILE="/etc/community-scripts-github-token"

[[ -r "$CONF" ]] || { echo "Missing $CONF" >&2; exit 2; }
# shellcheck disable=SC1090
source "$CONF"

: "${COMMUNITY_SCRIPTS_TARGET:?COMMUNITY_SCRIPTS_TARGET is missing in $CONF}"
REPO="${COMMUNITY_SCRIPTS_REPO:-SaulGoodman1337/optolink}"
REF="${COMMUNITY_SCRIPTS_REF:-optolink-web}"

TOKEN="${COMMUNITY_SCRIPTS_GITHUB_TOKEN:-}"
if [[ -z "$TOKEN" && -r "$TOKEN_FILE" ]]; then
  IFS= read -r TOKEN <"$TOKEN_FILE" || true
fi

bootstrap="$(mktemp)"
trap 'rm -f "$bootstrap"' EXIT

if [[ -n "$TOKEN" ]]; then
  curl -fsSL \
    -H "Authorization: Bearer $TOKEN" \
    -H "Accept: application/vnd.github.raw+json" \
    -H "X-GitHub-Api-Version: 2022-11-28" \
    "https://api.github.com/repos/$REPO/contents/tools/private-run.sh?ref=$REF" \
    -o "$bootstrap"
else
  curl -fsSL "https://raw.githubusercontent.com/$REPO/$REF/tools/private-run.sh" -o "$bootstrap"
fi

COMMUNITY_SCRIPTS_GITHUB_TOKEN="$TOKEN" \
COMMUNITY_SCRIPTS_REPO="$REPO" \
COMMUNITY_SCRIPTS_REF="$REF" \
bash "$bootstrap" "$COMMUNITY_SCRIPTS_TARGET"
