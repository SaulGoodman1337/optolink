#!/usr/bin/env bash
set -euo pipefail

# Download a local working copy of the public WB2A service manual.
#
# The PDF is third-party copyrighted material and is intentionally not mirrored
# in Git. This helper only retrieves the public source chosen for the project.

URL="${WB2A_SERVICE_MANUAL_URL:-https://www.intec-heizung.de/media/pdf/c2/0c/64/Viessmann-Vitodens-200-WB2A-Serviceanleitung.pdf}"
DEST="${1:-docs/manuals/Viessmann-Vitodens-200-WB2A-Serviceanleitung.pdf}"

mkdir -p "$(dirname "$DEST")"
tmp="$(mktemp)"
trap 'rm -f "$tmp"' EXIT

curl -fL --retry 3 --connect-timeout 15 "$URL" -o "$tmp"

# Basic PDF signature check prevents accidentally saving an HTML error page.
if [[ "$(head -c 5 "$tmp")" != "%PDF-" ]]; then
  echo "Downloaded file is not a PDF: $URL" >&2
  exit 1
fi

mv "$tmp" "$DEST"
trap - EXIT
printf 'Saved WB2A service manual to %s\n' "$DEST"
printf 'Source: %s\n' "$URL"
