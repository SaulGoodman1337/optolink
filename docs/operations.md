# Betrieb und Troubleshooting

Diese Datei ist das Runbook für den laufenden `optolink-splitter-ha`-Container.

## 1. Normaler Updateweg

Im bestehenden Optolink-LXC als `root`:

```bash
update
```

Der aktive Update-Kanal wird ausschließlich über
`/etc/community-scripts-private.conf` bestimmt. Vor der einmaligen
Umstellung auf `main` ist es gewöhnlich `optolink-splitter-ha`;
danach liefert derselbe Befehl `update` den freigegebenen Stand aus
`main`. Der lokale Kanal ändert sich durch einen GitHub-Merge
**nicht** von selbst.

Einmalige Migration einer älteren Installation:

```bash
curl -fsSL https://raw.githubusercontent.com/SaulGoodman1337/optolink/optolink-splitter-ha/tools/optolink-splitter-ha-bootstrap.sh | bash
```

### Vor dem ersten Update aus `main`

Der Release-Pfad ist bewusst zweistufig:
zuerst Integration in `optolink-splitter-ha`, danach der
geprüfte Merge nach `main`. Erst wenn der dortige Updater und die
deutsche Hybrid-Dokumentation vorhanden sind, darf die LXC-Instanz
auf `main` umgestellt werden.

```bash
# Zuerst den aktuellen lokalen Update-Bezug kontrollieren:
grep -E '^COMMUNITY_SCRIPTS_(REPO|REF|TARGET)=' \
  /etc/community-scripts-private.conf

# Nur NACH der bestätigten main-Freigabe einmalig ausführen:
optolink-update-main-umstellen --freigeben

# Anschließend wie gewohnt:
update
```

Die Umstellung erstellt eine root-geschützte Sicherung der bisherigen
Update-Konfiguration und prüft vorab, ob `main` den vollständigen
Installer einschließlich Hybridmodulen und Betriebsanleitung enthält.
Sie führt **selbst kein Update aus**. Anschließend bleibt
`COMMUNITY_SCRIPTS_REF=main` persistent.

**Wichtig:** Der Upstream-Profil-Installer nutzt `git reset --hard`
auf die verifizierte Upstream-Revision. Lokal geänderte, getrackte
Dateien werden deshalb *vor* dem Reset mitsamt Patch und
Dateikopien unter `/var/backups/optolink-update/`
root-geschützt gesichert. Diese Sicherung ersetzt nicht die
fachliche Prüfung der lokalen Anpassungen:
nicht automatisch reproduzierbare Änderungen müssen vor dem
ersten `update` einzeln übernommen oder bewusst zurückgestellt
werden. Das ist insbesondere auf bestehenden LXC-Systemen mit
historischen Hotfixes wichtig.

Bei aktivem `optolink-hybrid-continuous-canary.service`
verweigert der Updater den Wechsel von Laufzeitbibliotheken.
Es findet keine automatische P300-Freigabe statt.

### Optionaler VS1/P300-Lesetest

Der Splitter bleibt standardmäßig in VS1. Für ein ausdrücklich
beaufsichtigtes, schreibgeschütztes P300-Fenster gilt:

```bash
optolink-hybrid status
sudo optolink-hybrid vorbereiten --kennung hybrid-check-01
sudo optolink-hybrid pruefen hybrid-check-01
sudo optolink-hybrid testen hybrid-check-01 \
  --telemetriepause-bestaetigt
```

Die Vorbereitung und Prüfung ändern keine produktive
Systemd-Unit. Nur der explizit bestätigte Test setzt
vorübergehend einen root-eigenen Systemd-Canary ein.
Der unabhängige `ExecStopPost`-Pfad stellt beim Testende
oder beim Ausfall des Canary-Supervisors die Originaldienste
wieder her. Details, Sperrmarker und Grenzen siehe
[VS1/P300-Protokollwechsel](hybrid-protokollwechsel.md).

## 2. Schnellcheck nach Update oder Reboot

```bash
systemctl --no-pager --full status optolink-splitter
systemctl --no-pager --full status optolink-party-emulator
systemctl --no-pager --full status optolink-schedule-manager
systemctl --no-pager --full status optolink-maintenance-api
systemctl --no-pager --full status optolink-clock-sync.timer
systemctl --no-pager --full status optolink-service-programs
optolink-maintenance status
```

Seriellen Adapter prüfen:

```bash
optolink-ports
grep '^port_optolink' /opt/optolink/settings_ini.py
```

Der produktive Code setzt **nicht** voraus, dass das Gerät `/dev/ttyUSB0` heißt. Maßgeblich ist `settings_ini.port_optolink`. Ein stabiler `/dev/serial/by-id/...`-Pfad ist vorzuziehen.

## 3. Logs

Splitter:

```bash
journalctl -u optolink-splitter -n 100 --no-pager
journalctl -u optolink-splitter -f
```

Zeitprogramme:

```bash
journalctl -u optolink-schedule-manager -n 100 --no-pager
```

Party-Emulation:

```bash
journalctl -u optolink-party-emulator -n 100 --no-pager
```

Wartungs-API:

```bash
journalctl -u optolink-maintenance-api -n 100 --no-pager
```

Zeitabgleich:

```bash
journalctl -u optolink-clock-sync.service -n 100 --no-pager
systemctl list-timers optolink-clock-sync.timer
```

Befüll-/Entlüftungsprogramme:

```bash
journalctl -u optolink-service-programs -n 100 --no-pager
```

## 4. Systemzeit der Therme

Nur lesen:

```bash
runuser -u optolink -- /usr/local/bin/optolink-clock-sync --check
```

Erzwungener, readback-verifizierter Sync:

```bash
runuser -u optolink -- /usr/local/bin/optolink-clock-sync --force
```

Automatisch wird alle 15 Minuten geprüft. Standardmäßig wird nur bei mehr als 30 Sekunden Drift oder inkonsistentem Wochentag geschrieben.

Der Write auf `0x088E` wurde am **2026-10-06 auf der realen 20C2/WB2A verifiziert**. Ein Write kann dabei Status `255` zurückgeben und trotzdem wirksam sein; maßgeblich ist der direkt folgende Readback.

Erwartete Rohstruktur von `0x088E`:

```text
CC YY MM DD WD hh mm ss
```

Alle Datums-/Zeitfelder außer dem Wochentag sind BCD-codiert; der Wochentag ist `1=Montag ... 7=Sonntag`.

## 5. Home-Assistant-Discovery

Aktives Profil:

```text
/opt/optolink/homeassistant_poll_list.py
```

Die Aktivierung erzeugt vor dem Publish einen Discovery-Dry-Run:

```text
/root/optolink-ha-discovery-dry-run.txt
```

Bei MQTT-Problemen zuerst prüfen:

```bash
grep -E '^(mqtt_broker|mqtt_topic|mqtt_listen|mqtt_respond)' /opt/optolink/settings_ini.py
systemctl status optolink-splitter --no-pager
```

Wenn der Splitter läuft, aber eine einzelne Entity `unknown` bleibt, ist Discovery in der Regel nicht das Problem. Dann den zugrunde liegenden Datenpunkt gezielt über MQTT/Debug lesen.

## 6. Debug-Client

Generischer Read über den laufenden Splitter:

```bash
optolink-debug request 'r;0x088E;8;raw;False'
```

Party-relevante Werte lesen:

```bash
optolink-debug party-snapshot
```

Der Debug-Client ist ein technisches Werkzeug. Schreibbefehle sollten nicht als Ersatz für die geschützten produktiven Manager verwendet werden.

## 7. Zeitprogramme

Produktive Änderungen laufen über `optolink-schedule-manager`, nicht als direkter `wraw`-Befehl.

Adressbereiche:

- Heizung M1: `0x2000 .. 0x2030`
- Warmwasser: `0x2100 .. 0x2130`
- Zirkulation: `0x2200 .. 0x2230`

Je Programm existieren sieben Tagesblöcke. Jeder Block ist acht Byte lang und enthält maximal vier Start-/End-Paare.

Details: [wb2a-schedule-blocks.md](wb2a-schedule-blocks.md)

## 8. Wartungswerte

CLI-Status:

```bash
optolink-maintenance status
```

Die Wartungsfunktionen verwenden explizite Bestätigungsphrasen für risikoreiche Operationen und verifizieren Schreibvorgänge. Details:

- [optolink-maintenance.md](optolink-maintenance.md)
- [optolink-maintenance-api.md](optolink-maintenance-api.md)

## 9. Befüllen und Entlüften

Status des Guarded Managers:

```bash
systemctl status optolink-service-programs --no-pager
journalctl -u optolink-service-programs -n 100 --no-pager
```

Controllerzustand direkt lesen:

```bash
optolink-debug request 'r;0x572F;1;1;False'
```

Zuordnung:

```text
0 = Aus
1 = Entlüftungsprogramm
2 = Befüllungsprogramm
```

Der vollständige Pfad wurde am **06.10.2026 auf der produktiven VDensHO1 / 20C2 / SW03 / WB2A live verifiziert**. Entlüftung und Befüllung ließen sich über die HA-/MQTT-Servicepfade aktivieren, der jeweilige Controllerzustand wurde zurückgelesen und anschließend wieder auf `0` beendet.

Für den realen Servicevorgang weiterhin die Hinweise in [service-programs.md](service-programs.md) und der Viessmann-Serviceanleitung beachten.

## 10. Party-Emulation

Status:

```bash
systemctl status optolink-party-emulator --no-pager
journalctl -u optolink-party-emulator -n 100 --no-pager
```

Persistenter Restore-State:

```text
/var/lib/optolink-party/state.json
```

Diese Datei nicht löschen, während eine emulierte Party aktiv ist: Sie enthält die Werte, auf die beim Ausschalten zurückgestellt wird.

## 10. Befüllungs- und Entlüftungsprogramm

Dienst prüfen:

```bash
systemctl status optolink-service-programs --no-pager
journalctl -u optolink-service-programs -n 100 --no-pager
```

Register rein lesend prüfen:

```bash
optolink-debug request 'r;0x572F;1;1;False'
```

Erwartet werden ausschließlich:

```text
0 = Aus
1 = Entlüftung
2 = Befüllung
```

Die Schalter im Diagnose-Dashboard enthalten Bestätigungsdialoge und einen Info-Dialog mit den Servicehandbuch-Hinweisen. Vor einer realen Aktivierung die hydraulischen bzw. sicherheitsrelevanten Vorbereitungsschritte aus der Serviceanleitung durchführen.

Details: [service-programs.md](service-programs.md)

## 11. HTTP 401 beim Update

Ältere Installationen konnten einen abgelaufenen PAT aus
`/etc/community-scripts-github-token` bevorzugen.

Aktueller Code lädt bei öffentlichem Repository ohne Authentifizierung und verwendet einen Token nur als Fallback.

Alten Token entfernen:

```bash
update --clear-token
update
```

## 12. Rollback

Der Profil-Helper erzeugt vor Änderungen Zeitstempel-Backups unter `/opt/optolink`. Bei einem Aktivierungsfehler versucht er automatisch, den vorherigen Stand zurückzustellen.

Vor manuellen Eingriffen zunächst vorhandene Backups anzeigen:

```bash
ls -lah /opt/optolink/*.bak-* 2>/dev/null
ls -ld /root/optolink-*-backup-* 2>/dev/null
```

`main` bleibt zusätzlich der unveränderte Repository-Snapshot vor der Branch-Aufräumaktion.

## 13. Fehlerdiagnose in sinnvoller Reihenfolge

1. Ist der konfigurierte serielle Pfad vorhanden?
2. Läuft `optolink-splitter.service`?
3. Ist MQTT verbunden?
4. Kommt ein direkter Read über `optolink-debug` zurück?
5. Läuft der zuständige Zusatzdienst?
6. Was steht im Journal dieses Dienstes?
7. Ist der zugrunde liegende Datenpunkt auf dieser Hardware tatsächlich verfügbar?
8. Erst danach Discovery/Dashboard untersuchen.

Diese Reihenfolge trennt Bus-, Transport-, Dienst- und UI-Probleme sauber voneinander.
