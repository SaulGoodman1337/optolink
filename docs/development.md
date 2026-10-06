# Entwicklungsleitfaden

## 1. Grundregel

`optolink-splitter-ha` ist kein Experimentierzweig. Er soll jederzeit auf der realen Splitter-Maschine aktualisierbar bleiben.

Ein produktiver Commit sollte mindestens eine dieser Kategorien erfüllen:

- Fehlerbehebung;
- dokumentierte, hardwareverifizierte Gerätefunktion;
- Home-Assistant-Darstellung einer bereits verifizierten Funktion;
- Sicherheits-/Robustheitsverbesserung;
- Betriebs- oder Entwicklerdokumentation.

Firmware- und Protokollforschung gehört nach `optolink-research`.

## 2. Abhängigkeitsgrenze

Der Branch enthält nur lokale Integrationsschichten. Der eigentliche Splitter bleibt Upstream:

```text
philippoo66/optolink-splitter
```

Der produktiv validierte Upstream-Stand ist im Profil-Helper gepinnt. Lokale Patches werden als explizite Patch-Skripte geführt und müssen idempotent sowie selbsttestbar bleiben.

Keine umfangreichen lokalen Fork-Änderungen still in `/opt/optolink` einbauen, die nicht aus diesem Repository reproduzierbar sind.

## 3. Buszugriff

Produktive Zusatzdienste sollen den seriellen Port nicht selbst öffnen.

Bevorzugter Pfad:

```text
Dienst -> MQTT command topic -> optolink-splitter -> Controller
                              <- MQTT response topic <-
```

Vorteile:

- genau ein serieller Busbesitzer;
- reproduzierbare Request-Reihenfolge;
- keine exklusiven Port-Konflikte;
- einheitliche Logs;
- HA und Tools sehen denselben Controllerzustand.

## 4. Regeln für Reads

Für neue Reads dokumentieren:

- Adresse;
- Länge;
- Datentyp/Endianess/BCD/Skalierung;
- Quelle der Zuordnung;
- reales Beispiel vom Gerät;
- sinnvolle Poll-Frequenz;
- Verhalten bei P300-/VS1-Fehlern.

Nicht vorhandene Hardware nicht zyklisch pollen. Ein plausibler Defaultwert ist kein Beweis für einen realen Sensor.

## 5. Regeln für Writes

Ein positiver Transportstatus allein ist kein Funktionsnachweis.

Für neue produktive Writes:

1. aktuellen Wert lesen und sichern;
2. zulässigen Zielbereich begrenzen;
3. exakt einen bekannten Zielwert schreiben;
4. Ziel erneut lesen;
5. semantische Wirkung am Controller prüfen;
6. Ursprungswert wiederherstellen;
7. Restore ebenfalls lesen;
8. Timeout-/Mismatch-Verhalten definieren;
9. bei Mehrbyte-Strukturen vollständige Struktur validieren;
10. erst danach HA-Bedienung hinzufügen.

Wo sinnvoll, soll das Tool bei einem Mismatch selbständig den vorherigen Zustand restaurieren.

## 6. MQTT Request/Response-Korrelation

Mehrere Dienste teilen `mqtt_respond`. Deshalb darf ein Dienst nicht einfach „die nächste Antwort“ akzeptieren.

Die produktiven Manager merken sich die Sequenz vor dem Request und filtern Antworten mindestens nach der erwarteten Datenpunktadresse.

Dieses Muster beim Hinzufügen weiterer Dienste beibehalten.

## 7. Persistenter Zustand

Persistenter Zustand ist nur dort sinnvoll, wo er für einen sicheren Restore benötigt wird.

Beispiel:

```text
/var/lib/optolink-party/state.json
```

Dateien atomar schreiben: temporäre Datei, `fsync`, anschließend `os.replace`.

## 8. Systemd

Neue produktive Daemons laufen nach Möglichkeit als Benutzer `optolink`, nicht als root.

Bevorzugte Härtung:

- `NoNewPrivileges=true`;
- `PrivateTmp=true`;
- `ProtectHome=true`;
- `ProtectSystem=...`;
- nur ausdrücklich benötigte Schreibpfade.

Wenn ein Dienst vom Splitter abhängt, diese Beziehung in der Unit sichtbar machen.

## 9. Kommentare und Docstrings

Kommentare sollen das **Warum** erklären, nicht jede Python-Zeile paraphrasieren.

Besonders kommentieren:

- Hardware-Eigenheiten;
- Protokollannahmen;
- Sicherheitsgrenzen;
- Gründe für ungewöhnliche Timeouts/Retry-Pfade;
- warum ein ACK nicht genügt;
- warum eine Entity absichtlich nicht direkt schreibt;
- Restore-/Rollback-Logik.

Keine veralteten Research-Hypothesen als Kommentar in den Produktionscode übernehmen.

## 10. CI

Die Workflow-Datei

```text
.github/workflows/validate-maintenance-backend.yml
```

prüft unter anderem:

- Python-Compile;
- YAML-Parsing;
- Shell-Syntax;
- Clock-BCD-Selftest;
- vorhandene Deployment-Abhängigkeiten;
- Trennung vom Research-/Web-Baum;
- Branch-Pinning;
- öffentliche Updatepfade;
- WW-Tag/Nacht-Zuordnung;
- konfigurierte Serial-Port-Erkennung;
- Clock-Sync-Oberfläche;
- systemd-Verträge.

Bei neuen betriebsrelevanten Invarianten einen kleinen statischen Regression-Guard ergänzen.

## 11. Lokaler Review vor einem Commit

Mindestens:

```bash
python3 -m py_compile <geänderte Python-Dateien>
bash -n <geänderte Shell-Dateien>
```

Für Clock-Sync:

```bash
python3 tools/optolink-clock-sync.py --self-test
```

Für Dashboard:

```bash
python3 - <<'PY'
import yaml
with open("config/optolink-splitter/homeassistant-dashboard.yaml", encoding="utf-8") as f:
    yaml.safe_load(f)
print("OK")
PY
```

Danach GitHub Actions abwarten.

## 12. Hardware-Review nach einem Commit

Bei reinen Doku-/Kommentaränderungen genügt CI.

Bei Controllerreads:

- Update auf der realen Maschine;
- Read im Journal oder mit `optolink-debug` prüfen;
- HA-State prüfen.

Bei Writes zusätzlich:

- Ausgangswert dokumentieren;
- Ziel schreiben;
- Readback;
- physische/semantische Wirkung;
- Restore;
- erneuter Readback.

## 13. Branch-Policy

- `main`: unveränderter Ausgangssnapshot der Aufräumaktion;
- `optolink-splitter-ha`: produktiv;
- `optolink-research`: Forschung/Archiv;
- `optolink-web`: Web-Anwendung.

Keine kompletten Merges von Research nach Produktion. Einzelne Erkenntnisse gezielt und nachvollziehbar promoten.
