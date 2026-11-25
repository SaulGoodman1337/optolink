# Betrieb und Fehlerdiagnose

Diese Datei ist das Runbook für den laufenden `optolink-splitter-ha`-Container.

## 1. Normaler Updateweg

Im bestehenden Optolink-LXC als `root`:

```bash
update
```

**Achtung:** `update` aktualisiert Betriebssystem- und Pythonpakete, kann Dienste neu starten und einen Uhrzeitabgleich ausführen. Es ist kein nebenwirkungsfreier Prüfaufruf.

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

Der Release-Pfad war bewusst zweistufig:
zuerst Integration in `optolink-splitter-ha`, danach der
geprüfte Merge nach `main`. Beide Schritte sind seit dem
13.10.2026 abgeschlossen (PR #49, #51, #53); `main` ist
der aktuelle Kanal (siehe [Branch-Übersicht](branches.md)). Erst wenn der dortige Updater und die
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

Für separate manuelle, lokal nur von Root autorisierte On-Demand-Diagnosen
existieren die Kommandos `optolink-hybrid anfordern`, `ergebnis` und
`abbrechen`. Sie funktionieren **ausschließlich im explizit gestarteten,
überwachten `fenced-ondemand`-Shadow-Betrieb**, nicht in normalem VS1.
Bedienung, Sitzungskennung, Ergebnisnachweis und die in C3 bestandene
echte Hardwareabnahme: [Root-On-Demand-API](p300-root-lese-api.md).
Keiner dieser Befehle schaltet Controller-Writes frei.

## 2. Schnellcheck nach Update oder Reboot

```bash
systemctl --no-pager --full status optolink-splitter
systemctl --no-pager --full status optolink-party-emulator
systemctl --no-pager --full status optolink-schedule-manager
systemctl --no-pager --full status optolink-maintenance-api
systemctl --no-pager --full status optolink-clock-sync.timer
systemctl --no-pager --full status optolink-service-programs
systemctl --no-pager --full status optolink-room-control
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

Raumregelung (Vorlauf nach Raumtemperatur, siehe [raumregelung.md](raumregelung.md)):

```bash
journalctl -u optolink-room-control -n 100 --no-pager
optolink-debug request "read;0x2321;1"   # 00 = normaler Raumsollwert
```

### Therme nicht erreichbar (Link-Recovery)

Der Splitter schreibt sein eigenes Log nach
`/opt/optolink/optolinkvs2_switch.log` (das Journal enthält nur die
Konsolenausgabe). Ist die Therme bzw. der Optolink-Kopf nicht erreichbar,
erscheint dort zunächst `Timeout waiting for 0x05`. Seit dem
Link-Recovery-Patch (`tools/optolink-apply-link-recovery-patch.py`) gilt:

- Nach 60 s ohne gültige VS1-Antwort meldet der Splitter
  `Optolink link lost ... re-open serial port and re-init protocol` und
  öffnet die serielle Schnittstelle neu (ein frisch geöffneter Port hat im
  Feld zuverlässig geholfen, das reine Weiterwarten auf demselben Handle nicht).
- Scheitert die Initialisierung, versucht er es endlos weiter: fünfmal im
  Abstand von `restart_delay` (10 s), danach mit Backoff bis maximal 120 s
  (`Optolink still not available after N re-starts - keep trying`). Früher
  beendete sich der Prozess nach fünf Versuchen mit Exit-Code 0, und
  `Restart=on-failure` startete ihn nicht mehr.
- Die Unit steht zusätzlich auf `Restart=always` und
  `StartLimitIntervalSec=0`; nur ein explizites `systemctl stop` hält den
  Splitter an.

```bash
grep -E "link lost|still not available|protocol initialized" /opt/optolink/optolinkvs2_switch.log | tail
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

## 12a. Protokoll: VS1 oder Dauer-P300

Standard ist VS1. Dauer-P300 ist die Grundlage für die ausfallsichere
Pumpensteuerung per RAM-Override (E7-Arbeitskopie `0x20A5`), denn
RAM-Schreibzugriffe gibt es nur unter P300.

```bash
# auf P300 umstellen (wirkt beim nächsten update)
echo p300 | sudo tee /etc/optolink/protocol
update

# zurück auf VS1
echo vs1 | sudo tee /etc/optolink/protocol   # oder Datei löschen
update
```

Im P300-Betrieb gilt:

- Die VS1-only-GFA-Werte P06 (Gebläse), P09, P80 und P87 werden nicht gepollt
  (die WB2A weist GFA über P300 ab). Im Dashboard sind sie als „nur VS1“
  markiert; ihr letzter Wert bleibt stehen.
- Der Link-Watchdog (60 s ohne gültige Antwort → Port neu öffnen) gilt für
  beide Protokolle, dazu kommt ein P300-Keep-Alive auf `0x00F8` nach 5 s
  Leerlauf.
- Alle anderen Datenpunkte, MQTT-/TCP-Befehle und Zusatzdienste laufen
  unverändert. Gemessen am 24.11.2026: alle 81 unter VS1 laufend
  aktualisierten Topics außer den 4 GFA-Werten auch unter P300, keine
  Fehler, Write mit Readback OK.

## 12b. Fail-safe Pumpensteuerung (nur Dauer-P300)

Grundidee: E7 (0x27E7, Mindestdrehzahl Heizkreispumpe) bleibt **dauerhaft auf
100 %** codiert. Der Pumpen-Wächter (`/opt/optolink/pump_guard.py`, im
Splitter-Hauptloop) senkt nur die RAM-Arbeitskopie 0x20A5 auf die
Normaldrehzahl, solange alles gesund ist. Die Firmware lädt den codierten Wert
etwa alle 2,1–2,7 s neu; der Wächter schreibt dann sofort wieder den
Normalwert. Hört er auf (Boost, Fehler, Splitter/MQTT/HA weg), läuft die Pumpe
nach spätestens ~3 s wieder mit 100 %. E7 selbst wird nie geschrieben.

| Bedingung | Zustand | Pumpe |
| --- | --- | --- |
| Schalter aus | AUS | 100 % |
| Zustand älter als 5 s, E7 ≠ 100, Störung/Verriegelung | GESPERRT | 100 % |
| Warmwasser, Ventil nicht Heizen, Startsequenz (0x55D3 Byte 6/7), Flamme, Nachlauf (optional), Vorboost (optional) | BOOST | 100 % |
| unerwarteter RAM-Wert, Ausnahme | FEHLER (bis Schalter aus/ein) | 100 % |
| sonst | ABGESENKT | Normaldrehzahl |

Hinweis: Ein Virtual_READ von 0x27E7 liefert die aktive RAM-Kopie, nicht den
codierten Wert. Der Wächter liest E7 deshalb nur außerhalb der Absenkung; beim
Absenken beweist jeder Firmware-Reload auf 100 die Codierung.

**Vorboost (Phase 3):** Der Wächter liest zusätzlich Kesseltemperatur
(0x0810) und effektives Kesselsoll (0x555A). Bei jedem Brennerstart merkt er
sich, wie weit der Kessel unter dem Soll lag (gelernte Startschwelle, gleitender
Mittelwert, Startwert 4 K = Codierstecker „Einschaltdifferenz“). Mit
`vorboost_aktiv` = ON und `vorboost` = X K (Standard 1 K) geht die Pumpe schon
auf 100 %, sobald der Kessel weniger als X K von dieser Schwelle entfernt ist
(Freigabe 0,5 K darunter). Standard: aus.

**Nachlauf:** Mit `nachlauf_aktiv` = ON (Standard) bleibt die Pumpe nach
Brenner aus noch `nachlauf` Minuten (Standard 3) auf 100 %. Aus = sofort
zurück auf die Normaldrehzahl.
Veraltete Temperaturen (> 10 s) schalten nur den Vorboost ab, nicht die
Absenkung.

**Messergebnis A/B-Test (25.11.2026, 00:10–03:50, Soll 36,5 °C, 28 Zyklen):**
Abwechselnd nach jedem Brennerstopp Nachlauf 3 min bzw. 12 min (Pumpe 100 %
über die ganze Pause). Brenndauer in beiden Fällen ~34 s, Kessel beim Start
immer 32,5 °C (Soll − 4 K). Die Pause war mit 100 % Pumpe im Mittel ~80 s
länger (≈ 516 s statt 435 s in den ersten 20 Zyklen), also rund 15 % weniger
Brennerstarts. Der Nutzer wollte das aber nicht dauerhaft (Pumpe fast immer
auf 100 %); seit 1.3.0 gilt wieder Nachlauf 3 min, der Boost folgt nur dem
normalen Brennerzyklus. Die kurze Brenndauer selbst
kommt von der Volllast-Startphase und lässt sich über die Pumpe nicht beheben.
Die Taktsperre (0x55E0 Byte 14) dauert nur ~4 min (Codierstecker
Mindestpausenzeit = 4), der Rest der Pause ist temperaturbegrenzt.

**Brenner-Kennlinie (1.4.0, optional, Standard aus):** Messung 25.11.2026
(57 Brennerläufe): nach der Startphase moduliert der Brenner praktisch immer an
der Untergrenze (33 %), eine Kennlinie über die Modulation wäre daher konstant.
Die Kennlinie richtet sich deshalb nach dem Abstand zur gelernten
Ausschalttemperatur (Kesseltemperatur bei den letzten Heiz-Brennerstopps):
nach `kurve_start_s` (Standard 60 s) läuft die Pumpe mit `kurve_min`
(Standard 60 %), ab `kurve_voll_k` + 5 K vor Aus steigt sie linear (5-%-Schritte)
und erreicht `kurve_voll_k` (Standard 3 K) vor Aus 100 %. Warmwasser, Ventil
nicht Heizen, veraltete Temperatur oder noch keine gelernte Ausschalttemperatur
ergeben 100 %. Zustand `KENNLINIE` zählt wie `ABGESENKT` als Absenkung
(gleicher fail-safe RAM-Mechanismus). Achtung: weniger Durchfluss in der
Brennphase lässt den Kessel schneller die Ausschalttemperatur erreichen, die
Brenndauer wird also eher kürzer. Nur per A/B-Vergleich einsetzen.
MQTT: `kurve_aktiv`, `kurve_min`, `kurve_voll_k`, `kurve_start_s` (…/set, …/state).

**Boost während Taktsperre** (1.2.x) wurde in 1.3.0 wieder entfernt; der
Wächter liest 0x55E0 nicht mehr.

MQTT (unter `openv/pump_guard/`): `enabled/set` ON|OFF, `low/set` 20–100,
`nachlauf_aktiv/set` ON|OFF, `nachlauf/set` 0–30 min, `vorboost_aktiv/set`
ON|OFF, `vorboost/set` 0–10 K, jeweils retained `…/state`; `status` (JSON),
`zustand`, `protocol`. HA: Schalter „Pumpensteuerung aktiv“, „Nachlauf aktiv“,
„Vorboost aktiv“, Zahlen „Normaldrehzahl“, „Nachlauf“, „Vorboost“, Sensoren
Zustand/Grund/RAM-E7/Korrekturen/Kessel unter Soll/Startschwelle.

Installation: der Profil-Helfer installiert Modul und Hook
(`tools/optolink-apply-pump-guard-patch.py`). Unter VS1 ist der Hook inaktiv.
Sofort-Rückfall: Schalter aus, oder `systemctl stop optolink-splitter`.

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