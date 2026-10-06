#!/usr/bin/env bash
set -euo pipefail

CONF="/etc/community-scripts-private.conf"
TOKEN_FILE="/etc/community-scripts-github-token"

[[ -r "$CONF" ]] || { echo "Missing $CONF" >&2; exit 2; }
# shellcheck disable=SC1090
source "$CONF"

: "${COMMUNITY_SCRIPTS_TARGET:?COMMUNITY_SCRIPTS_TARGET is missing in $CONF}"
REPO="${COMMUNITY_SCRIPTS_REPO:-SaulGoodman1337/optolink}"
REF="${COMMUNITY_SCRIPTS_REF:-optolink-splitter-ha}"

save_token() {
  local token
  printf 'GitHub token: ' >/dev/tty
  read -rs token </dev/tty
  printf '\n' >/dev/tty
  [[ -n "$token" ]] || { echo "A GitHub token is required." >&2; exit 2; }
  umask 077
  printf '%s\n' "$token" >"$TOKEN_FILE"
  chmod 600 "$TOKEN_FILE"
  chown root:root "$TOKEN_FILE"
  echo "GitHub token saved in $TOKEN_FILE (root-only)."
}

case "${1:-}" in
  --save-token) save_token; exit 0 ;;
  --forget-token|--clear-token) rm -f "$TOKEN_FILE"; echo "Saved GitHub token removed."; exit 0 ;;
esac

TOKEN="${COMMUNITY_SCRIPTS_GITHUB_TOKEN:-}"
if [[ -z "$TOKEN" && -r "$TOKEN_FILE" ]]; then
  IFS= read -r TOKEN <"$TOKEN_FILE" || true
fi

bootstrap="$(mktemp)"
trap 'rm -f "$bootstrap"' EXIT

# Prefer the unauthenticated raw URL. A stale/expired saved token must not
# break updates while the repository is public. Authentication is only the
# fallback for a private repository.
if curl -fsSL \
  "https://raw.githubusercontent.com/$REPO/$REF/tools/private-run.sh" \
  -o "$bootstrap"; then
  :
elif [[ -n "$TOKEN" ]]; then
  rm -f "$bootstrap"
  curl -fsSL \
    -H "Authorization: Bearer $TOKEN" \
    -H "Accept: application/vnd.github.raw+json" \
    -H "X-GitHub-Api-Version: 2022-11-28" \
    "https://api.github.com/repos/$REPO/contents/tools/private-run.sh?ref=$REF" \
    -o "$bootstrap"
else
  echo "Could not download tools/private-run.sh from $REPO @ $REF." >&2
  exit 3
fi

COMMUNITY_SCRIPTS_GITHUB_TOKEN="$TOKEN" \
COMMUNITY_SCRIPTS_REPO="$REPO" \
COMMUNITY_SCRIPTS_REF="$REF" \
bash "$bootstrap" "$COMMUNITY_SCRIPTS_TARGET"
