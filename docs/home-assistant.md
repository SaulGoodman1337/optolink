# Home-Assistant-Modell

## 1. Quelle der Entities

Die Datei

```text
config/optolink-splitter/vdensho1-20c2-wb2a-homeassistant.py
```

ist die produktive Discovery-/Poll-Definition. Beim Aktivieren wird sie als

```text
/opt/optolink/homeassistant_poll_list.py
```

installiert.

Der Gerätepräfix lautet:

```text
vitodens_200_wb2a_
```

Dadurch entstehen beispielsweise:

```text
sensor.vitodens_200_wb2a_kesseltemperatur
number.vitodens_200_wb2a_warmwasser_solltemperatur
sensor.vitodens_200_wb2a_systemzeit_anzeige
```

## 2. Aufbau der Profil-Datei

`poll_list["domains"]` enthält Home-Assistant-Domainblöcke.

Ein Block definiert gemeinsame Discovery-Eigenschaften wie:

- `domain`;
- Einheit und Device Class;
- Icon;
- Wertebereich;
- Templates;
- Command Topic;
- Entity Category.

Darunter gibt es zwei grundsätzliche Quellen.

### `poll`

Der Splitter liest den Datenpunkt selbst.

Typisches numerisches Beispiel:

```python
("NORMAL", "warmwasser_solltemperatur", 0x6300, 1, 1, False)
```

Bedeutung:

- Poll-Gruppe;
- interner Datenpunktname;
- Optolink-Adresse;
- Länge;
- Skalierung bzw. Format;
- je nach Datentyp weitere Decoder-Parameter.

Formatierte Datenpunkte verwenden statt einer numerischen Skalierung beispielsweise
`"raw"`, `"vdatetime"` oder `"schedvdens"`.

### `nopoll`

Die Entity bekommt ihren Zustand von einem anderen MQTT-Produzenten. Beispiele:

- Maintenance API;
- Schedule Manager;
- Party Emulator;
- Clock Sync;
- Service-Program Manager (Befüllen / Entlüften).

Damit kann Home Assistant einen einheitlichen Geräteknoten darstellen, obwohl ein Teil der Zustände nicht direkt vom Poll-Loop stammt.

## 3. Poll-Gruppen

| Gruppe | Zweck |
| --- | --- |
| `ONCE` | einmal beim Prozessstart |
| `FAST` | jeder vollständige Poll-Zyklus |
| `NORMAL` | etwa jeder fünfte FAST-Zyklus |
| `DIAG` | interne Reglerdiagnostik |
| `SLOW` | langsam veränderliche Sensor-/Konfigurationswerte |
| `RARE` | Zähler, Fehlerhistorie, Systemzeit und ähnliche Langzeitwerte |
| `DISABLED` | nicht produktiv abfragen |

Der lokale Scheduler-Patch verteilt die langsameren Gruppen über ihre Periode, damit keine großen Request-Bursts entstehen.

## 4. Schreibbare Entities

Eine schreibbare HA-Entity ist nur dann produktiv enthalten, wenn der adressierte Vorgang begrenzt und für diese Anlage vertretbar ist.

Beispiele:

| Entity-Funktion | Adresse / Mechanismus |
| --- | --- |
| Raum Tag | `0x2306` |
| Raum reduziert | `0x2307` |
| Party-Soll | `0x2308` |
| Betriebsart | `0x2323` |
| WW Tag | `0x6300` |
| WW 2. Sollwert / Nacht | Codieradresse 58 → `0x6758` |
| Zirkulationsintervall | `0x6773` |
| Zeitprogramme | über Schedule Manager |
| Wartung | über Maintenance API |
| Party | über Party Emulator |
| Entlüftungsprogramm | Codieradresse 2F / `0x572F=1`, über Service-Program Manager |
| Befüllungsprogramm | Codieradresse 2F / `0x572F=2`, über Service-Program Manager |

Komplexe Operationen werden **nicht** direkt aus einem HA-Template auf den Bus geschrieben, sondern über einen spezialisierten Dienst mit Validierung und Readback geführt.

## 5. Warmwasser Tag / Nacht

Die produktiven Reglerwerte sind:

- `0x6300`: normaler Warmwasser-Sollwert;
- `0x6758`: Codieradresse 58, zweiter Trinkwassertemperatur-Sollwert.

Die bestehende Entity-ID des zweiten Sollwerts bleibt aus Kompatibilitätsgründen:

```text
number.vitodens_200_wb2a_warmwasser_solltemperatur_reduziert
```

Das Dashboard bezeichnet sie als **Warmwasser Nachttemperatur**. Fachlich ist es der zweite WW-Sollwert; die WB2A verwendet ihn im Original-Zeitprogramm für die dafür vorgesehene Warmwasser-Phase.

## 6. Befüllungs- und Entlüftungsprogramm

Die WB2A-Servicefunktion **Codieradresse 2F / Optolink `0x572F`** wird über einen eigenen Guarded Manager in Home Assistant abgebildet.

Entities:

```text
switch.vitodens_200_wb2a_entlueftungsprogramm
switch.vitodens_200_wb2a_befuellungsprogramm
sensor.vitodens_200_wb2a_serviceprogramm_status
```

Controllerzustände:

- `0` = aus;
- `1` = Entlüftungsprogramm;
- `2` = Befüllungsprogramm.

Obwohl Home Assistant zwei Schalter zeigt, existiert im Controller nur ein gemeinsames Drei-Zustands-Register. `optolink-service-programs` verhindert deshalb widersprüchliche Zustände und verifiziert jede Änderung über einen neuen Read von `0x572F`.

**Hardware-Verifikation 06.10.2026:** Beide produktiven Übergänge wurden auf der realen VDensHO1 / 20C2 / SW03 / WB2A erfolgreich getestet. Sowohl `0 → 1 → 0` (Entlüften) als auch `0 → 2 → 0` (Befüllen) funktionierten und wurden durch Controller-Readback bestätigt.

Das Dashboard enthält zusätzlich Sicherheits-/Ablaufinformationen aus der WB2A-Serviceanleitung. Die HA-Schalter ersetzen nicht die dort beschriebenen mechanischen und hydraulischen Arbeitsschritte.

## 7. Systemzeit-Diagnose

Der Controller liefert seine Zeit über `0x088E`.

HA-Entities:

```text
sensor.vitodens_200_wb2a_systemzeit_anzeige
sensor.vitodens_200_wb2a_systemzeit_abweichung
sensor.vitodens_200_wb2a_systemzeit_sync_status
```

- **Systemzeit Anzeige**: tatsächlicher Controller-Read;
- **Abweichung**: beim letzten Clock-Sync gemessene Differenz zur Hostzeit;
- **Sync Status**: Synchron, Korrigiert, Nur geprüft oder Fehler.

## 8. Befüllungs- und Entlüftungsschalter

Home Assistant stellt das gemeinsame Controllerregister `0x572F` als zwei
bedienbare Schalter dar:

```text
switch.vitodens_200_wb2a_entlueftungsprogramm
switch.vitodens_200_wb2a_befuellungsprogramm
sensor.vitodens_200_wb2a_serviceprogramm_status
```

Die Schalter schreiben nicht direkt auf den Splitter. Ihre Topics führen zu
`optolink-service-programs`, das den aktuellen Modus liest, den gewünschten
Zielwert 0/1/2 schreibt und den Controllerzustand erneut verifiziert.

Da beide Schalter dasselbe Drei-Zustands-Register repräsentieren, kann nur ein
Serviceprogramm aktiv sein. Der Dienst verhindert außerdem, dass ein OFF-Befehl
des bereits inaktiven Schalters das jeweils andere aktive Programm beendet.

Die Diagnose-Ansicht enthält für beide Schalter einen Bestätigungsdialog sowie
einen Info-Dialog mit Ablauf und Sicherheitshinweisen aus der WB2A-
Serviceanleitung.

## 9. Zeitprogramm-Editor

Home Assistant schreibt die 8-Byte-Blöcke nicht direkt.

UI-Ablauf:

```text
HA Editor
  -> staging topics
  -> optolink-schedule-manager
  -> Validierung des gesamten Tages
  -> 8-Byte Write
  -> bytegenauer Readback
  -> bei Fehler Restore des Originals
```

Die `select`-/`time`-/`switch`-Entities im Editor sind daher Staging-State und keine direkten Controllerregister.

## 10. Dashboard

Die vollständige Dashboard-Konfiguration liegt in:

```text
config/optolink-splitter/homeassistant-dashboard.yaml
```

Sie verwendet unter anderem folgende HACS-Abhängigkeiten:

- button-card;
- Mushroom Cards;
- lovelace-multiple-entity-row;
- card-mod;
- background-graph-entities;
- datetime-spinner-card.

Das Dashboard ist eine Darstellungsschicht. Die fachliche Quelle für Entitäten und Register bleibt die Python-Profil-Datei.

## 11. DEV-Dashboard für UI-Tests

Neben dem produktiven Dashboard existiert:

```text
config/optolink-splitter/homeassistant-dashboard-dev.yaml
```

Diese Datei ist eine vollständige, getrennte Testversion. Sie kann als zweites
Home-Assistant-Dashboard geladen werden, ohne
`homeassistant-dashboard.yaml` zu verändern.

Die aktuelle DEV-Version modernisiert insbesondere:

- die Hauptseite als **Heizung DEV**;
- die Anlagenübersicht mit Mushroom-Chips und kompakten Statusgruppen;
- die Thermostatventile als übersichtliche Raumgruppen;
- den Verlauf mit `background-graph-entities`;
- Tag-/Nacht-Sollwerte als gemeinsame visuelle Gruppe aus Überschrift und zwei responsiven Mushroom-Sliderkarten;
- die Seite Nachtabsenkung mit derselben visuellen Gruppierung.

Die Slider bleiben technisch getrennte Entities. Sie werden direkt nebeneinander unter einer gemeinsamen Gruppenüberschrift dargestellt; damit vermeidet die DEV-Version verschachtelte interaktive Karten, die im Sections-Layout zu Clipping führen können. Das ist ausschließlich eine Darstellungsänderung. Die
zugrunde liegenden Entities und Controlleradressen bleiben getrennt und
unverändert.

Für ein separates YAML-Dashboard kann die Datei beispielsweise nach
`/config/dashboards/optolink-dev.yaml` kopiert und als eigener
`lovelace.dashboards`-Eintrag registriert werden.

Änderungen werden erst nach visueller Prüfung bewusst aus DEV nach
`homeassistant-dashboard.yaml` übernommen.

## 12. Entity-ID-Stabilität

Bei Adresskorrekturen sollte der interne Datenpunktname nach Möglichkeit stabil bleiben, wenn die semantische Bedeutung der Entity identisch bleibt. So bleiben Home-Assistant-Registry, Dashboards und Automationen erhalten.

Beispiel: Die Korrektur des zweiten WW-Sollwerts von einem falschen Adresskandidaten auf `0x6758` behielt den Namen
`warmwasser_solltemperatur_reduziert` bei.

Ein Name darf dagegen nicht aus Kompatibilitätsgründen erhalten bleiben, wenn er fachlich eine andere Funktion vortäuschen würde.

## 13. Neue Entity hinzufügen

Vor einem produktiven Merge:

1. Datenpunktquelle dokumentieren;
2. Adresse/Länge/Format bestimmen;
3. Read auf der realen WB2A prüfen;
4. bei Writes: Ausgangswert sichern;
5. Write gezielt testen;
6. Readback prüfen;
7. ursprünglichen Zustand wiederherstellen;
8. Poll-Gruppe passend zur Änderungsrate wählen;
9. Discovery-Dry-Run prüfen;
10. Dashboard nur ergänzen, wenn die Entity stabil ist;
11. CI-Guard ergänzen, wenn der Datenpunkt betriebsrelevant ist.

Research-Ergebnisse vor diesem Reifegrad bleiben auf `optolink-research`.
