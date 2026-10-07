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
- die Anlagenübersicht mit kompakten Statusgruppen;
- die Thermostatventile als übersichtliche Raumgruppen;
- Tag-/Nacht-Sollwerte als gemeinsame visuelle Gruppe aus Überschrift und zwei responsiven Mushroom-Sliderkarten;
- die Seite Nachtabsenkung mit derselben visuellen Gruppierung.

Die Slider bleiben technisch getrennte Entities. Die DEV-Hauptseite verwendet jetzt `custom:grid-layout` aus **Layout Card** mit expliziten Breakpoints und einer begrenzten maximalen Inhaltsbreite. Innerhalb der Bediengruppen werden die Slider über responsive `auto-fit/minmax`-Grids angeordnet. Dadurch stehen sie bei genügend Platz nebeneinander und brechen auf schmalen Displays automatisch um.

Breakpoints der DEV-Hauptseite:

- **> 1200 px:** zwei Spalten, je maximal ca. 900 px, zentriert auf sehr breiten Displays;
- **701–1200 px:** eine Spalte;
- **≤ 700 px:** Mobile-Abstände und eine Spalte. Die Raum- und Warmwasser-Sollwertkarten wechseln zusätzlich auf Mushrooms `layout: vertical`: Name und Temperatur stehen oberhalb des Sliders, der Slider nutzt darunter die volle Kartenbreite.

Das ist ausschließlich eine Darstellungsänderung. Die zugrunde liegenden
Entities und Controlleradressen bleiben getrennt und unverändert.

Zusätzliche DEV-Abhängigkeit:

```text
HACS -> Frontend -> Layout Card
thomasloven/lovelace-layout-card
```

### Sichtbarkeit der DEV-Views

Die erste Ansicht **Heizung DEV** besitzt absichtlich keinen `visible:`-Block
und ist damit für alle Home-Assistant-Benutzer sichtbar.

Alle weiteren DEV-Views sind auf den vorgesehenen Administrator-Benutzer
beschränkt. Diese Navigationseinschränkung wird in CI strukturell aus dem YAML
geprüft: Der erste View muss öffentlich bleiben und jeder nachfolgende View muss
exakt den konfigurierten Benutzer in `visible:` enthalten.

Die View-Sichtbarkeit ist eine UI-/Navigationsbeschränkung und ersetzt keine
Home-Assistant-Berechtigungen auf Entities oder Services.

### Technische Infoboxen im DEV-Dashboard

Technische Einstellwerte mit eigener Infobox folgen einem einheitlichen Schema:

1. **Funktion** – was der Parameter grundsätzlich steuert;
2. **Wirkung/Ablauf** – wann und wie er in die Regelung eingreift;
3. **Bereich/Optionen** und **aktueller Wert**;
4. Abhängigkeiten und wichtige Einschränkungen;
5. **Codieradresse** der Viessmann-Regelung;
6. **Datenpunkt** des aktuellen Optolink-Profils;
7. **Quelle** bzw. Kennzeichnung, wenn die genaue Wirkung aus der
   Serviceanleitung nicht belastbar ableitbar ist.

Im Tab **Pumpen** sind die Dokumentationen nicht mehr nur über Long-Press
erreichbar. E6, E7, E8, E9, A9, 31, 60 und 62 besitzen sichtbare
Info-Schaltflächen. Zusätzlich sind die Gruppen 56/59/65 und 71/72 dokumentiert.

Für die WB2A sind dabei insbesondere zwei ähnlich klingende Zeitfunktionen zu
trennen:

- **A9 / `0x27A9`**: dimensionsloser Codierwert 0–15 für die
  Pumpenstillstandzeit nach einer Sollwertänderung. Der Wert ist **keine direkte
  Minutenangabe**.
- **62 / `0x6762`**: Nachlauf der Speicherladepumpe nach
  Warmwasser-Speicherbeheizung; `0` = kein Nachlauf, `1…15` = Minuten.

Das HA-Profil führt diese Werte deshalb in getrennten Number-Konfigurationen:
A9 ohne Einheit, 62 mit `min`.

### Thermostatventile im DEV-Dashboard

Jede Thermostatkarte behält die drei Betriebswerte sichtbar:

```text
Ventilöffnung | Isttemperatur | Solltemperatur
```

Darunter liegt ein echter Solltemperatur-Slider über Home Assistants native
Tile-Card-Funktion `target-temperature`. Diese verwendet den nativen
`ha-control-slider` und vermeidet damit den Mobilkonflikt, bei dem eine
horizontale Sliderbewegung gleichzeitig zum nächsten Dashboard-Tab wischt.

Die installationsspezifischen Climate-Entity-IDs werden nicht im Repository
geraten. Die Karte löst sie zur Laufzeit über die gemeinsame
`device_id` des Ventilöffnungs-Sensors und der Climate-Entity auf. Falls
diese Zuordnung nicht möglich ist, wird zusätzlich anhand des normalisierten
Raumnamens gesucht. Wenn weiterhin keine Climate-Entity gefunden wird, bleibt
die Statuskarte sichtbar, der Slider wird jedoch ausgeblendet und ein
Diagnosehinweis angezeigt.

Beim Wohnzimmer existieren zwei Ventilgeräte. Deshalb zeigt die DEV-Version
**Wohnzimmer links** und **Wohnzimmer rechts** jeweils mit eigenem Sollwert-
Slider; die gemeinsame Raum-Isttemperatur bleibt bei beiden sichtbar.

Der bestehende Boost-Button `script.climateboost` / **Alle Ventile öffnen**
bleibt unverändert erhalten.

Für Homematic/HmIP-Thermostate berücksichtigt die DEV-Karte außerdem den
Sonderwert **30,5 °C = ON**. Dieser Wert wird nicht als normale Raumtemperatur
dargestellt, sondern als eigener Button **ON · Voll auf** unter dem
Solltemperatur-Slider. Die Statuszeile zeigt bei einem Zielwert >= 30,5 °C
entsprechend **ON** statt `30,5 °C`.

Der ON-Button ruft gezielt `climate.set_temperature` mit `30.5` für genau
die zur Raumkarte aufgelöste Climate-Entity auf. Der HVAC-Modus wird dabei
nicht verändert. Ein späterer normaler Sliderwert setzt wieder einen regulären
Temperatur-Sollwert.

Die zuvor auf der Hauptseite duplizierte Sektion **Verlauf** wurde aus `Heizung DEV` entfernt. Zeitreihen und historische Diagnosewerte bleiben im separaten Diagnose-Tab gebündelt.

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
