# Optolink-Wartungs-API über MQTT

Die Wartungs-API stellt die am realen Regler überprüften Funktionen
der **WB2A / VDensHO1** als abgesicherte MQTT-Schnittstelle bereit.

Home Assistant soll diese Schnittstelle nutzen und **keine rohen**
`w;0x....`-Befehle an den Splitter veröffentlichen.

## Architektur

```text
Home Assistant
      |
      v
openv/maintenance/cmnd
      |
      v
optolink-maintenance-api.service
      |
      v
optolink_maintenance_core.py
      |
      v
openv/cmnd + openv/resp
      |
      v
Optolink-Splitter / Heizungsregler
```

Die als Root ausgeführte CLI `optolink-maintenance`
verwendet dieselbe Implementierung
`optolink_maintenance_core.py`. API und CLI teilen
dieselbe Anwendungssperre:

```text
/opt/optolink/.maintenance.lock
```

Die Datei wird mit `0660 optolink:optolink` angelegt.
Eine CLI- und eine API-Wartungsaktion können daher
nicht gleichzeitig ablaufen.

## Lebenszyklus des Systemd-Dienstes

Der Wartungs-API-Dienst verwendet absichtlich weder
`PartOf=` noch `Requires=` für den Splitter.
Er besitzt lediglich Reihenfolge- und weiche Startabhängigkeiten:

```ini
After=network-online.target optolink-splitter.service
Wants=network-online.target optolink-splitter.service
Restart=always
```

Diese Entkopplung ist gewollt: Die API spricht mit dem Splitter
über MQTT und muss einen unabhängigen Neustart von
`optolink-splitter.service` überstehen. Während dessen
Ausfall können Controlleranfragen kontrolliert fehlschlagen.
Der API-Prozess und seine Home-Assistant-Verfügbarkeit
bleiben jedoch erhalten.

## Dienstverwaltung

```bash
systemctl status optolink-maintenance-api
journalctl -u optolink-maintenance-api -f
```

Der Dienst läuft als unprivilegierter Benutzer `optolink`.

Der Updatepfad aktiviert und startet die API nur dann neu,
wenn `settings.mqtt_broker` konfiguriert ist.
Bei einer Neuinstallation mit standardmäßig leerem Broker
bleibt sie deaktiviert.

## MQTT-Themen

Bei dem Standardpräfix `openv`:

| Thema | Richtung | Gespeichert (`retain`) | Zweck |
| --- | --- | --- | --- |
| `openv/maintenance/cmnd` | Client → API | nein | JSON-Befehle |
| `openv/maintenance/result` | API → Client | nein | Ergebnis pro Request |
| `openv/maintenance/state` | API → Clients | ja | letzter normierter Wartungszustand |
| `openv/maintenance/status` | API → Clients | ja | Status der API und Vormerkaktionen |
| `openv/maintenance/stage/hours/set` | HA → API | nein | Brennerstundenschwelle nur vormerken, kein Regler-Write |
| `openv/maintenance/stage/hours/state` | API → HA | ja | vorgemerkte Brennerstundenschwelle |
| `openv/maintenance/stage/months/set` | HA → API | nein | Monatswert nur vormerken, kein Regler-Write |
| `openv/maintenance/stage/months/state` | API → HA | ja | vorgemerkter Monatswert |
| `openv/maintenance/availability` | API → Clients | ja | `online` / `offline` nach sauberem Beenden |

Das Präfix stammt aus `settings.mqtt_topic`.

## Aufbau einer Anfrage

Jede Anfrage benötigt eine eindeutige `request_id`
und eine `action`.

```json
{
  "api_version": 1,
  "request_id": "ha-20260924-001",
  "action": "status"
}
```

Erlaubte Request-IDs entsprechen folgendem Muster:

```text
[A-Za-z0-9._:-]{1,128}
```

Die API hält die letzten **100 Ergebnisse** im Arbeitsspeicher.
Wird eine Request-ID erneut übermittelt, liefert der Dienst
das gespeicherte Ergebnis, anstatt die Regleraktion nochmals
auszuführen. Das schützt vor doppelten Schreibvorgängen
bei wiederholter MQTT-Zustellung oder Client-Reconnects.

Das Befehlsthema darf **niemals als Retained-State** verwendet
werden. Der Dienst ignoriert MQTT-Nachrichten mit gesetztem
`retain`-Flag. Ein früherer Schreib- oder Resetbefehl
kann dadurch nicht allein wegen eines Dienstneustarts
oder einer neuen Subscription wiederholt werden.

## Unterstützte Aktionen

### `status` – Status lesen

```json
{
  "api_version": 1,
  "request_id": "status-001",
  "action": "status"
}
```

Es wird kein Reglerwert geschrieben.

### `set_hours` – Brennerstunden-Schwelle setzen

```json
{
  "api_version": 1,
  "request_id": "hours-001",
  "action": "set_hours",
  "value": 3000,
  "confirm_reference_change": true
}
```

Einschränkungen:

- ganzzahlig 0–10.000 Stunden;
- ausschließlich 100-Stunden-Schritte;
- ohne `force: true` keine Änderung bei bereits gleichem Wert;
- jeder tatsächliche Write braucht `confirm_reference_change: true`;
- eine echte `0x5721`-Änderung kann `0x7570` neu referenzieren.

Das Ergebnis zeigt an, ob sich die Brennerreferenz
tatsächlich verändert hat.

### `set_months` – Wartungsintervall setzen

```json
{
  "api_version": 1,
  "request_id": "months-001",
  "action": "set_months",
  "value": 12,
  "confirm_reference_change": true
}
```

Einschränkungen:

- ganzzahlig 0–24 Monate;
- ohne `force: true` keine Änderung bei gleichem Wert;
- jeder Write braucht `confirm_reference_change: true`;
- jeder wirkliche Schreibzugriff auf `0x5723`
  setzt die `0x756C`-Referenz neu.

### `reset` – Wartung zurücksetzen

```json
{
  "api_version": 1,
  "request_id": "reset-001",
  "action": "reset",
  "confirm": true
}
```

Der Kern führt die überprüfte Folge aus:

```text
0x5724 = 1
Rücklesen == 1
0x5724 = 0
Rücklesen == 0
```

Wenn bereits in der ersten Phase eine mehrdeutige Antwort
eintrifft, versucht und überprüft der Sicherheits-/Abschlusspfad
trotzdem `0x5724 = 0`.

Die Auswirkungen auf beide Referenzen werden unabhängig
voneinander ausgegeben:

```json
{
  "reference_changes": {
    "interval_0x756C": true,
    "burner_0x7570": false
  }
}
```

Dies ist beabsichtigt: Die Wirkung auf `0x7570`
hängt nach Live-Tests vom Reglerzustand und der Konfiguration ab.

## Erfolgreiche Antwort

Beispiel:

```json
{
  "api_version": 1,
  "request_id": "hours-001",
  "ok": true,
  "action": "set_hours",
  "completed_at": "2026-09-24T20:00:00Z",
  "deduplicated": false,
  "data": {
    "action": "set-hours",
    "changed": true
  }
}
```

Die konkreten Aktionsdaten enthalten den Readback
und Informationen zu den Referenzänderungen aus dem
gemeinsamen Wartungskern.

## Fehlerantwort

```json
{
  "api_version": 1,
  "request_id": "hours-002",
  "ok": false,
  "action": "set_hours",
  "completed_at": "2026-09-24T20:00:00Z",
  "deduplicated": false,
  "error": "changing 0x5721 can re-baseline the burner-runtime maintenance reference at 0x7570",
  "code": "confirmation_required",
  "details": {
    "reference": "0x7570"
  }
}
```

Fehler bei der Schreibverifikation können außerdem
folgende Daten enthalten:

```json
{
  "configuration_restore": {
    "attempted": true,
    "verified": true
  },
  "reference_side_effects_reversible": false
}
```

**Achtung:** Ein erfolgreich wiederhergestellter Konfigurationswert
beweist nicht, dass Nebenwirkungen auf die Referenz ebenfalls
rückgängig gemacht wurden. Schreibzugriffe auf `0x5721`
und `0x5723` können eine Wartungsreferenz verändern,
selbst wenn ein späterer Rollback das Konfigurationsbyte
wiederherstellt.

## Gespeicherter Wartungszustand

`openv/maintenance/state` veröffentlicht nach dem
Dienststart und nach erfolgreichen Anfragen einen
normierten Zustandsdatensatz:

```json
{
  "api_version": 1,
  "hours_threshold": 0,
  "interval_months": 0,
  "maintenance_state": 0,
  "maintenance_state_text": "Grundzustand",
  "interval_reference_raw": "c988b56a",
  "interval_reference_uint": 1790281929,
  "burner_reference_raw": "134cce03",
  "burner_reference_seconds": 63851539,
  "burner_total_seconds": 63851541,
  "burner_total_hours": 17736.539,
  "burner_since_reference_hours": 0.000556,
  "burner_starts": 487380
}
```

`interval_reference_uint` bleibt ein roher Little-Endian-Wert.
Er darf **nicht** als bestätigter Unix-Zeitstempel angezeigt werden.

## Home Assistant: Werte zunächst vormerken

Das Produktionsprofil meldet zwei Konfigurationszahlen an:

- `number.vitodens_200_wb2a_wartung_brennerstunden_sollwert`;
- `number.vitodens_200_wb2a_wartung_zeitintervall_sollwert`.

Das Verstellen einer dieser Entities aktualisiert ausschließlich
das zugehörige Thema `maintenance/stage/*`.
Die API prüft den zulässigen Bereich und veröffentlicht
den vorgemerkten Zustand als Retained-Nachricht.
Dabei wird weder die Wartungssperre beansprucht
noch der Heizungsregler angesprochen.

Eine **wirkliche** Änderung erfolgt ausschließlich dann,
wenn das Dashboard eine JSON-Anfrage mit neuer Request-ID
und der passenden ausdrücklichen Bestätigung
an `maintenance/cmnd` sendet.

Nach einem erfolgreichen API-Aufruf spiegelt die API
den verifizierten Zustand außerdem in die vorhandenen,
nur lesenden Home-Assistant-Wartungsthemen.
So werden die Anzeigen sofort aktualisiert,
ohne auf die nächste RARE-Pollgruppe zu warten.

Im Dashboard werden zudem angezeigt:

- `sensor.vitodens_200_wb2a_wartung_brenner_seit_referenz`;
- `sensor.vitodens_200_wb2a_wartung_api_status`;
- `binary_sensor.vitodens_200_wb2a_wartung_api_verfuegbar`.

## Gestaltungsregel für Home Assistant

Gewünschte Werte werden zuerst in Hilfs-Entities
vorgemerkt. Die eigentliche API-Aktion darf
erst nach einer ausdrücklichen Übernehmen-/Reset-Bestätigung erfolgen.

Insbesondere darf eine direkt bedienbare MQTT-Zahl-Entity
**nicht** direkt mit `0x5721` oder `0x5723`
verbunden werden.

Empfohlener Ablauf:

```text
input_number
   -> ausdrückliche Schaltfläche „Übernehmen“
   -> Bestätigungsdialog
   -> MQTT-API-Anfrage
   -> Prüfen / Schreiben / Rücklesen im Wartungskern
   -> Ergebnis + gespeicherter Zustand
```

Eine VS1/P300-Lesefenster-Freigabe ersetzt keinen dieser
Wartungs-Sicherheitsmechanismen; der optionale Hybridmodus
sendet keine P300-Controller-Writes.
