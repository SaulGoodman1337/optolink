# Architektur des Produktionszweigs

Diese Datei beschreibt den **produktiven** Branch `optolink-splitter-ha`. Sie soll erklären, wie die Komponenten zusammenarbeiten, bevor man einzelne Dateien liest oder ändert.

## 1. Zielbild

Der Branch betreibt genau eine lokale Anlage:

- Viessmann Vitodens 200-W WB2A
- Geräteprofil VDensHO1
- Geräte-ID `0x20C2`
- Softwareindex `0x03`
- Optolink-Splitter als alleiniger Besitzer der seriellen Optolink-Schnittstelle
- MQTT als interner Befehls-/Antwortbus für die Zusatzdienste
- Home Assistant als Visualisierung und Bedienoberfläche

Firmware-Reverse-Engineering, EEPROM/KBus-Experimente und andere Forschungswerkzeuge gehören in `optolink-research`. Optolink-Web gehört in `optolink-web`.

## 2. Datenfluss

```text
                         Home Assistant
                              |
                     MQTT Discovery / State
                              |
                              v
+----------------+     +----------------------+     +----------------------+
| Zusatzdienste  |<--->|   MQTT-Broker        |<--->| optolink-splitter    |
|                |     |                      |     | /opt/optolink        |
| schedule       |     | <base>/...           |     |                      |
| party          |     | <listen>             |     | einziger Besitzer    |
| maintenance    |     | <respond>            |     | des seriellen Ports  |
| clock sync     |     +----------------------+     +----------+-----------+
+----------------+                                          |
                                                            |
                                                            v
                                                  Optolink / P300 / VS1
                                                            |
                                                            v
                                                 Vitodens 200-W WB2A
```

**Wichtig:** Die produktiven Zusatzdienste öffnen den seriellen Adapter nicht selbst. Sie senden Befehle über die MQTT-Schnittstelle des laufenden Splitters. Dadurch bleibt der physische Buszugriff serialisiert.

## 3. Installiertes Laufzeitsystem

Der Upstream-Splitter liegt unter:

```text
/opt/optolink
```

Wichtige lokale Dateien:

| Pfad | Bedeutung |
| --- | --- |
| `/opt/optolink/settings_ini.py` | Maschinenlokale Konfiguration: serieller Port, MQTT, Topics |
| `/opt/optolink/homeassistant_poll_list.py` | Aktives WB2A/VDensHO1-HA-Profil aus diesem Repository |
| `/opt/optolink/.maintenance.lock` | Prozessübergreifende Sperre für geschützte Wartungsoperationen |
| `/var/lib/optolink-party/state.json` | Persistenter Zustand der Party-Emulation |
| `/root/optolink-ha-discovery-dry-run.txt` | Letzte vor Aktivierung validierte HA-Discovery-Ausgabe |

Der Upstream-Code wird vom Profil-Helper auf den hardwarevalidierten Stand
`c1ee204a1421447721603c5f21c6da7337fdac97` gebracht und anschließend mit zwei eng begrenzten Runtime-Patches ergänzt:

1. read-only VS1/GFA-Unterstützung;
2. phasenverschobener Poll-Scheduler.

## 4. Repository-Komponenten

### `config/optolink-splitter/vdensho1-20c2-wb2a-homeassistant.py`

Deklarative Quelle für:

- Poll-Datenpunkte und Poll-Gruppen;
- MQTT-/Home-Assistant-Discovery;
- schreibbare `number`, `select`, `switch`, `text` und `time`-Entities;
- diagnostische Hilfs-Entities;
- externe Status-Topics der Zusatzdienste.

Die Datei wird **nicht direkt ausgeführt**. Der Profil-Helper installiert sie als
`/opt/optolink/homeassistant_poll_list.py`.

### `tools/optolink-apply-vdensho1-ha-profile.sh`

Transaktionaler Aktivierungsweg für das Geräteprofil. Der Helper:

1. prüft die beiden Runtime-Patcher über deren Self-Tests;
2. erzeugt Backups;
3. aktualisiert/pinnt den Upstream-Splitter;
4. installiert und kompiliert das HA-Profil;
5. wendet die beiden Runtime-Patches an;
6. validiert Home-Assistant-Discovery;
7. startet den Splitter nur, wenn der konfigurierte serielle Port vorhanden ist;
8. publiziert Discovery nur bei aktivem MQTT;
9. versucht bei Fehlern einen Rollback.

### `tools/optolink-schedule-manager.py`

Geschützter Writer für die 21 verifizierten Tagesblöcke:

- Heizung;
- Warmwasser;
- Zirkulation;
- Montag bis Sonntag.

Ein Tagesblock besteht aus acht Bytes für maximal vier Zeitfenster. Der Manager validiert den kompletten Zielblock, schreibt ihn, liest ihn bytegenau zurück und stellt bei einem Mismatch den Originalblock wieder her.

### `tools/optolink-party-emulator.py`

Emuliert eine verlässlich fernschaltbare Party-Funktion, weil das native Einschalten über `0x2303` auf dieser Anlage nicht zuverlässig ist.

Die Emulation arbeitet mit:

- `0x2323` Betriebsart;
- `0x2306` normaler Raumsollwert;
- `0x2303` nativer Party-Status;
- `0x2308` Party-Raumsollwert;
- `0x27F2` Party-Zeitbegrenzung.

Vor dem Einschalten werden die zu restaurierenden Werte persistiert. Beim Ausschalten oder nach Ablauf werden sie wiederhergestellt.

### `optolink_maintenance_core.py`, CLI und MQTT API

Die Wartungslogik ist absichtlich zentralisiert:

```text
optolink-maintenance       \
                            -> optolink_maintenance_core.py -> MQTT -> Splitter
optolink-maintenance-api  /
```

Der Core enthält die eigentlichen Guardrails, Readbacks und Rollbacks. CLI und API sind nur Bedienoberflächen.

### `tools/optolink-clock-sync.py`

Synchronisiert die Regler-Systemzeit `0x088E` mit der lokalen Systemzeit des Splitter-Hosts.

Ablauf:

1. 8-Byte-BCD-Zeit lesen;
2. Drift und Wochentag prüfen;
3. unterhalb von 30 Sekunden nichts schreiben;
4. bei Bedarf kompletten 8-Byte-Wert schreiben;
5. erneut lesen;
6. nur innerhalb von 5 Sekunden Abweichung als erfolgreich werten.

Der systemd-Timer startet diesen Check alle 15 Minuten.

Der Schreibpfad ist auf der lokalen 20C2/WB2A am **2026-10-06 live verifiziert**: ein erzwungener 8-Byte-Write auf `0x088E` wurde unmittelbar mit korrekter Gerätezeit und `0 s` Drift zurückgelesen. Dabei lieferte der Transport für den Write Status `255`; der anschließende Readback war korrekt. Deshalb ist der Readback — nicht der ACK-Code — die Erfolgsinstanz.

## 5. Systemd-Dienste

| Unit | Typ | Aufgabe |
| --- | --- | --- |
| `optolink-splitter.service` | dauerhaft | eigentlicher Splitter und serieller Busbesitzer |
| `optolink-maintenance-api.service` | dauerhaft | geschützte Wartungs-API über MQTT |
| `optolink-schedule-manager.service` | dauerhaft | Zeitprogramm-Staging und -Writes |
| `optolink-party-emulator.service` | dauerhaft | Party-Emulation und Zustandswiederherstellung |
| `optolink-clock-sync.service` | oneshot | ein Zeitabgleich |
| `optolink-clock-sync.timer` | Timer | startet Clock-Sync alle 15 Minuten |

## 6. Schreibpfade und Sicherheitsmodell

Es gibt keinen generischen produktiven „write anything“-Dienst.

Jeder produktive Schreibpfad ist auf einen bekannten Zweck begrenzt:

| Bereich | Begrenzung |
| --- | --- |
| HA-Schreib-Entities | nur explizit deklarierte Adressen/Wertebereiche |
| Zeitprogramme | nur 21 bekannte 8-Byte-Blöcke, vollständige Validierung und Readback |
| Wartung | nur bekannte Wartungsregister, Confirm-Phrasen, Lock, Readback/Rollback |
| Party | nur definierte Party-/Betriebsart-/Sollwertregister, persistenter Restore-State |
| Systemzeit | nur `0x088E`, Drift-Schwelle und Readback |
| GFA | produktive Integration ist read-only |

Ein Transport-ACK gilt bei kritischen Multi-Byte-Schreibvorgängen **nicht** als alleiniger Erfolgsnachweis. Der gelesene Controllerzustand ist maßgeblich.

## 7. Update- und Deployment-Kette

```text
/usr/bin/update
  -> /usr/local/lib/community-scripts/private-update.sh
     -> tools/private-run.sh
        -> lädt optolink-splitter-ha als temporären Repository-Baum
           -> tools/optolink-splitter-update.sh
              -> installiert Helfer und Units
              -> aktiviert Profil
              -> startet/aktualisiert Zusatzdienste
              -> persistiert denselben Branch als Update-Kanal
```

Öffentliche GitHub-Downloads werden zuerst versucht. Ein gespeicherter PAT ist nur Fallback für ein künftig wieder privates Repository.

## 8. Wo Änderungen hingehören

- Produktiver, hardwareverifizierter Splitter-/HA-Code: **dieser Branch**
- Experimente, Reverse Engineering, Firmware, rohe Probes: **`optolink-research`**
- Browser-Webanwendung: **`optolink-web`**

Neue produktive Schreibfunktionen sollten erst nach dokumentiertem Read/Write/Readback-Test auf der realen Anlage aufgenommen werden.
