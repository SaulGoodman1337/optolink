# Optolink-Splitter mit Home Assistant

Dieses Repository stellt eine geprüfte Home-Assistant-Integration
für die **Viessmann Vitodens 200-W WB2A / VDensHO1 / 20C2 / SW03**
bereit. Der Zweig `optolink-splitter-ha` ist der Integrationszweig
für produktive Komponenten. Nach der geprüften Freigabe
werden dessen Änderungen auch in `main` übernommen.

Firmware-Reverse-Engineering, EEPROM- und KM-Bus-Versuche,
einmalige Datensammlungen und experimentelle Pumpenregister
gehören ausdrücklich **nicht** in diesen Produktivzweig,
sondern nach `optolink-research`.
Die Weboberfläche wird getrennt auf `optolink-web` entwickelt.

## Dokumentation

Empfohlene Reihenfolge für Betrieb und Wartung:

1. [Dokumentationsindex](docs/README.md) – alle Betriebsanleitungen und Quellen der Wahrheit.
2. [Systemarchitektur](docs/architecture.md) – Komponenten, Datenflüsse und technische Sicherheitsgrenzen.
3. [Betrieb und Fehlerdiagnose](docs/operations.md) – Update, Status, Logs und Wiederherstellung.
4. [Home Assistant](docs/home-assistant.md) – MQTT-Entities, Zeitprogramme und Dashboard.
5. [Optionaler VS1/P300-Protokollwechsel](docs/hybrid-protokollwechsel.md) – Bedienung, Voraussetzungen und Rückfallpfad.
6. [Entwicklungsleitfaden](docs/development.md) – Regeln für Änderungen, Tests und Hardwareabnahme.
7. [Wartungs-CLI](docs/optolink-maintenance.md) und [MQTT-Wartungs-API](docs/optolink-maintenance-api.md).
8. [WB2A-Zeitprogrammblöcke](docs/wb2a-schedule-blocks.md).
9. [WB2A-Anlagenschema und Anlagenkonfiguration](docs/anlagenschema.md).
10. [VControl-/Adresszuordnung](config/optolink-splitter/vcontrol-mapping.md).

Vereinfachter Laufzeitpfad:

```text
Home Assistant
      |
      v
MQTT-Broker <---- Zusatzdienste: Zeitprogramm, Party, Wartung, Uhrzeit
      |
      v
Optolink-Splitter (einziger serieller Eigentümer)
      |
      v
USB-/Optolink-Lesekopf
      |
      v
Viessmann Vitodens 200-W WB2A
```

Zusatzdienste sprechen über MQTT mit dem Splitter.
**Kein Zusatzdienst** darf neben ihm eigenständig den seriellen
Optolink-Port öffnen.

## Systemübersicht

![Optolink-Systemübersicht](docs/images/optolink-system-overview.svg)

![Dienstekommunikation und Sicherheitsmodell](docs/images/service-communication-security.svg)

### Optionaler VS1/P300-Protokollwechsel

![Überwachter VS1/P300-Protokollwechsel](docs/images/vs1-p300-wechsel.svg)

Die Diagramme liegen als skalierbare SVG-Dateien vor.
Der VS1-Betrieb bleibt Standard. `optolink-hybrid` ermöglicht
ausschließlich ausdrücklich angeforderte, über Systemd
überwachte P300-**Lese**fenster; kein permanenter
Protokollwechsel und keine P300-Controller-Writes.
Die Details stehen in
[der Hybrid-Betriebsanleitung](docs/hybrid-protokollwechsel.md).

## Umfang des Produktivzweigs

Enthalten sind:

- der angepasste Upstream `philippoo66/optolink-splitter`;
- das am Regler geprüfte WB2A-/VDensHO1-Home-Assistant-Profil;
- MQTT-Discovery, gespeicherte Zustände und Dashboard-Konfiguration;
- die abgesicherte Wartungs-CLI und Wartungs-MQTT-API;
- Zeitprogrammverwaltung für die verifizierten WB2A-Tagesblöcke;
- Party-Modus-Emulation mit Wiederherstellung;
- geschützte Serviceprogramme zum Befüllen und Entlüften
  über Codieradresse 2F (`0x572F`);
- Zeitsynchronisierung und Diagnosedaten;
- Proxmox-LXC-Neuinstallation und der produktive Updater;
- geprüfte Laufzeit-Patches und eine **standardmäßig deaktivierte**
  optionale Hybridbibliothek.

Nicht enthalten sind ungeprüfte Steuerregister,
Firmwareabbilder, EEPROM-Dumps, Roh-RAM-Schreibprogramme,
VitoTest-Archive, Forschungs-Logger, experimentelle
Pumpen-Minimum-Overrides und die separate Weboberfläche.

## Sicherheits- und Update-Modell

Der Profil-Installer fixiert den geprüften Upstream-Stand
`c1ee204a1421447721603c5f21c6da7337fdac97`.
Anschließend setzt er die validierte
VS1-/GFA-Unterstützung und den mehrphasigen Poll-Scheduler
ein. Die Patcher prüfen sich vor Änderungen selbst;
der Installer legt datierte Sicherungen an und versucht
bei fehlgeschlagener Aktivierung ein Rollback.

Die optionale VS1/P300-Laufzeit wird **erst nach**
dem regulären Profil-Schritt installiert.
Sie ist nicht automatisch aktiviert und stellt einen
eigenständigen, nach Prüfsummen gebundenen Laufzeitkandidaten
bereit. Während einer aktiven Hybrid-Sitzung wird eine
Aktualisierung abgewiesen.

**Wichtig für bereits veränderte LXC-Installationen:**
Der Upstream-Teil des Profil-Installers führt vor dem erneuten
Patchen einen `git reset --hard` auf die validierte Revision
aus. Lokale Änderungen müssen zuvor überprüft und gesichert
werden. Details zur Sicherung stehen unter
[Betrieb und Updates](docs/operations.md).

## Bestehende LXC-Installation: Update mit `update`

Die einmalige Einrichtung des Produktionskanals für
den bisherigen `optolink-splitter-ha`-Zweig erfolgt
als `root` im existierenden LXC:

```bash
curl -fsSL https://raw.githubusercontent.com/SaulGoodman1337/optolink/optolink-splitter-ha/tools/optolink-splitter-ha-bootstrap.sh | bash
```

Der Bootstrap kontrolliert die vorhandene Installation,
holt die freigegebene Repository-Snapshot-Version,
führt den Update-Prozess aus und speichert:

```text
COMMUNITY_SCRIPTS_REPO=SaulGoodman1337/optolink
COMMUNITY_SCRIPTS_REF=optolink-splitter-ha
COMMUNITY_SCRIPTS_TARGET=tools/optolink-splitter-update.sh
```

Die gewöhnliche Folgeaktualisierung geschieht dann durch:

```bash
update
```

### Nach dem freigegebenen Merge: `update` aus `main`

Sobald zuerst die Hybridintegration in
`optolink-splitter-ha` **und danach** dieser
Produktionsstand in `main` gemergt wurde,
kann der lokale Kanal auf `main` umgestellt werden.
Ein GitHub-Merge ändert die LXC-Konfiguration nicht von selbst.

```text
COMMUNITY_SCRIPTS_REPO=SaulGoodman1337/optolink
COMMUNITY_SCRIPTS_REF=main
COMMUNITY_SCRIPTS_TARGET=tools/optolink-splitter-update.sh
```

Vor dem ersten Update muss die Kombination aus
`main`-Release und lokalen Anpassungen gesichert
und überprüft sein. Danach bleibt der Befehl
`update` unverändert. Die Schritt-für-Schritt-Anleitung
steht unter [Betrieb](docs/operations.md).

Bei einem öffentlichen Repository wird zunächst der
anonyme GitHub-Download versucht; ein alter oder
abgelaufener privater Zugangstoken verursacht dadurch
keine unnötigen HTTP-401-Fehler. Authentifizierung
bleibt als Fallback für private Repositories möglich.

## Zustandsprüfung nach Updates

```bash
systemctl status optolink-splitter --no-pager
systemctl status optolink-party-emulator --no-pager
systemctl status optolink-schedule-manager --no-pager
systemctl status optolink-maintenance-api --no-pager
systemctl status optolink-clock-sync.timer --no-pager
systemctl status optolink-service-programs --no-pager
optolink-maintenance status
optolink-hybrid status
journalctl -u optolink-splitter -n 100 --no-pager
```

Das aktive Home-Assistant-Profil liegt unter
`/opt/optolink/homeassistant_poll_list.py`.
Die vom Profil-Installer erstellte Discovery-Trockenprüfung
liegt unter `/root/optolink-ha-discovery-dry-run.txt`.

## WB2A-Systemzeit

Die Reglerzeit wird aus `0x088E` als
Viessmann-Datum/Uhrzeit im 8-Byte-BCD-Format gelesen.
Installierte Komponenten:

```text
/usr/local/bin/optolink-clock-sync
/etc/systemd/system/optolink-clock-sync.service
/etc/systemd/system/optolink-clock-sync.timer
```

Der Timer vergleicht alle 15 Minuten die Reglerzeit mit
der Systemzeit des Hosts. Nur bei mehr als 30 Sekunden
absoluter Abweichung oder einem zum Datum unpassenden
Wochentagsbyte wird das vollständige 8-Byte-Register
`0x088E` geschrieben und erneut gelesen.
Für eine bestätigte Korrektur muss die Reglerzeit danach
höchstens fünf Sekunden von der Hostzeit abweichen.

```bash
optolink-clock-sync --check
optolink-clock-sync --force
systemctl status optolink-clock-sync.timer --no-pager
journalctl -u optolink-clock-sync.service -n 50 --no-pager
```

Home Assistant erhält die Entities
`sensor.vitodens_200_wb2a_systemzeit_anzeige`,
`sensor.vitodens_200_wb2a_systemzeit_abweichung` und
`sensor.vitodens_200_wb2a_systemzeit_sync_status`.
Die Diagnoseansicht fasst sie unter **Systemzeit** zusammen.

## Home Assistant und Warmwasser

Das Produktionsprofil bildet die zwei nativen
Warmwasser-Sollwerte ab und erhält aus
Kompatibilitätsgründen die bestehenden MQTT-/Entity-IDs:

- **Warmwasser-Tagestemperatur:** `0x6300`,
  `warmwasser_solltemperatur`;
- **Warmwasser-Nachttemperatur beziehungsweise zweiter Sollwert:**
  Codieradresse 58, `0x6758`,
  `warmwasser_solltemperatur_reduziert`.

Codieradresse 58 bedeutet: `0` = Zusatzfunktion aus;
`10–60 °C` = zweiter Trinkwasser-Sollwert für die
vierte Warmwasser-Zeitphase.

Das Produktionsdashboard liegt unter
`config/optolink-splitter/homeassistant-dashboard.yaml`,
die getrennte Entwicklungsansicht unter
`config/optolink-splitter/homeassistant-dashboard-dev.yaml`.

Seit dem 07.10.2026 verwendet die Produktion
die responsive Layout-Card-Hauptansicht mit
Tag-/Nacht-Bedienelementen, Thermostat-Sollwerten,
aktiver WB2A-Störungsanzeige und geprüften Ansichtsregeln.
Die DEV-Variante enthält darüber hinaus
**Anlagenschema und Anlagenkonfiguration** mit
bestätigungspflichtigen Reglerwerten
`00`, `52`, `53`, `54` und `5B`.
Codieradresse `65` und interne Adressen
`0x7701` / `0x8851` bleiben nur lesbar.
Siehe [Anlagenschema](docs/anlagenschema.md).

Der Zeitprogramm-Manager akzeptiert nur die 21
verifizierten WB2A-Tagesblöcke und prüft die
vollständigen 8-Byte-Werte vor jedem Write.
Wartungsänderungen sind auf die freigegebenen
Aktionen des gemeinsamen Wartungskerns beschränkt.

## Befüllen und Entlüften

Die Servicefunktion **Codieradresse 2F** kennt:

- `2F:0` / `0x572F = 0`: aus;
- `2F:1` / `0x572F = 1`: Entlüftungsprogramm;
- `2F:2` / `0x572F = 2`: Befüllungsprogramm.

Home Assistant stellt zwei separate Schalter dar.
Der Dienst `optolink-service-programs` behandelt
sie als gemeinsames Drei-Zustands-Register.
Er liest vor Änderungen, schreibt ausschließlich 0/1/2,
bestätigt per neuem Controller-Readback und
versucht bei einer fehlgeschlagenen Verifikation
den Ausgangswert wiederherzustellen.

Die am 06.10.2026 durchgeführten Live-Tests
`0 → 1 → 0` und `0 → 2 → 0` wurden
erfolgreich über `0x572F` rückgelesen.
Die automatische Reglerabschaltung nach circa
20 Minuten wird durch regelmäßige Abfragen in HA sichtbar.

Siehe [Serviceprogramme](docs/service-programs.md).
Die Serviceanleitung eines Drittherstellers
wird nicht mitgeliefert; ihre Quellenangabe steht in
[docs/manuals/README.md](docs/manuals/README.md).
Ein lokaler Download-Helfer ist
`tools/fetch-wb2a-service-manual.sh`.

## Neuinstallation

Für einen neuen Proxmox-LXC-Container gilt:

```bash
csrun ct/optolink-splitter.sh
```

Bei direktem Aufruf der Repository-Skripte
muss `COMMUNITY_SCRIPTS_REF` auf den vorgesehenen,
freigegebenen Zweig gesetzt sein.

## Wiederherstellung

Der Profil-Installer legt zeitgestempelte
Sicherungen der geänderten Konfigurationen an und
versucht bei fehlerhafter Aktivierung ein Rollback.
Der Hybrid-Canary verwendet zusätzlich
einen unabhängig von seinem Python-Supervisor
ausgeführten Systemd-Rückfallpfad.

Für den Rückweg auf eine frühere Repository-Version
gilt die dokumentierte Git-Revisionsstrategie;
`main` ist nach seiner Integration **kein**
unveränderter Altstand mehr.

## Repository-Struktur

- `config/optolink-splitter/`: Produktionsprofil, Dienste, Dashboard, Wartungskern.
- `tools/`: Installer, Update, Serviceprogramme, Runtime-Patcher,
  optionale Hybridbibliothek und abgesicherte CLI.
- `install/`, `ct/`: Neuinstallation.
- `docs/`: deutsche Betriebs- und Entwicklerdokumentation.
- `json/`: Metadaten für Community Scripts.

## Fehlerbehebung: HTTP 401 bei `update`

Ältere Versionen verwendeten einen gespeicherten
GitHub-Token bevorzugt gegenüber dem öffentlichen Download.
Ein abgelaufener PAT konnte so `401 Unauthorized`
erzeugen, obwohl das Repository öffentlich ist.

Im aktuellen Updater haben öffentliche Downloads Vorrang.
Bei einem noch alten Updater hilft die erneute Installation
des Bootstraps oder das Entfernen des veralteten Tokens:

```bash
update --clear-token
update
```

Den Bootstrap für den aktuellen Zweig findet man
in `tools/optolink-splitter-ha-bootstrap.sh`.

## Erkennung der seriellen Schnittstelle

Produktionsprofil und Neuinstallationsroutine
nehmen nicht mehr pauschal `/dev/ttyUSB0` an,
sondern prüfen den in `/opt/optolink/settings_ini.py`
konfigurierten Wert `port_optolink`.
Damit werden stabile Pfade unter `/dev/serial/by-id/...`
unterstützt.

Der MQTT-Status und die Verfügbarkeit des seriellen
Optolink-Geräts werden getrennt behandelt.
Ein fehlendes serielles Gerät wird nicht irrtümlich
als „MQTT deaktiviert“ gemeldet.
