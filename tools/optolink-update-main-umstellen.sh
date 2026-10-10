#!/usr/bin/env bash
set -euo pipefail

# Einmalige, kontrollierte Umstellung des vorhandenen "update"-Befehls
# auf das freigegebene GitHub-Release aus dem Branch main.
# Das Skript installiert KEINE Pakete und startet KEINEN Heizungsdienst neu.

CONF=/etc/community-scripts-private.conf
ARCHIVE=/var/backups/optolink-update
REPO=SaulGoodman1337/optolink

if [[ ${EUID:-$(id -u)} -ne 0 ]]; then
  echo "Als root im Optolink-LXC ausfuehren." >&2
  exit 2
fi
if [[ "${1:-}" != "--freigeben" || $# -ne 1 ]]; then
  echo "Aufruf: optolink-update-main-umstellen --freigeben" >&2
  echo "Fuehrt nur die einmalige Kanalumstellung aus, kein update." >&2
  exit 2
fi
[[ -f "$CONF" && ! -L "$CONF" ]] || {
  echo "Update-Konfiguration fehlt oder ist ein Symlink." >&2
  exit 3
}
# Ausschliesslich die bekannte, erlaubte Production-Updatekonfiguration.
grep -qx "COMMUNITY_SCRIPTS_REPO=$REPO" "$CONF" || exit 3
grep -qx "COMMUNITY_SCRIPTS_TARGET=tools/optolink-splitter-update.sh" "$CONF" || exit 3
old_ref="$(sed -n 's/^COMMUNITY_SCRIPTS_REF=//p' "$CONF")"
[[ "$old_ref" == "optolink-splitter-ha" || "$old_ref" == "main" ]] || {
  echo "Unbekannter Update-Kanal: verweigert." >&2
  exit 3
}
if systemctl is-active --quiet optolink-hybrid-continuous-canary.service; then
  echo "Hybrid-Lesefenster aktiv: Umstellung verweigert." >&2
  exit 3
fi

# Das neue main muss den GEPRUEFTEN vollstaendigen Updatepfad enthalten;
# vor dem Merge liefern die URLs 404 und die Umstellung wird verweigert.
for rel in tools/private-run.sh tools/optolink-splitter-update.sh \
           tools/optolink-hybrid.py docs/hybrid-protokollwechsel.md; do
  if ! curl -fsSL --retry 1 \
       "https://raw.githubusercontent.com/$REPO/main/$rel" -o /dev/null; then
    echo "main-Release ist noch nicht vollstaendig: $rel" >&2
    exit 4
  fi
done

install -d -m 0700 "$ARCHIVE"
umask 077
stamp="$(date -u +%Y%m%dT%H%M%SZ)"
backup="$ARCHIVE/update-channel-before-main-$stamp.conf"
cp -p "$CONF" "$backup"
temp="$(mktemp /etc/.community-scripts-private.XXXXXXXX)"
trap 'rm -f "$temp"' EXIT
sed 's/^COMMUNITY_SCRIPTS_REF=.*/COMMUNITY_SCRIPTS_REF=main/' "$CONF" >"$temp"
chown root:root "$temp"
chmod 0600 "$temp"
mv -f "$temp" "$CONF"
trap - EXIT
echo "Update-Kanal geaendert: $old_ref -> main"
echo "Root-only-Sicherung: $backup"
echo "Ab jetzt laedt der bekannte Befehl update aus $REPO/main."
echo "Hinweis: update selbst wurde nicht ausgefuehrt; lokale Aenderungen vorher pruefen."
