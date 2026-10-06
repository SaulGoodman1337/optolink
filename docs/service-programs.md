# WB2A Befüllungs- und Entlüftungsprogramm

Dieses Dokument beschreibt die produktive Home-Assistant-Integration der
Viessmann-Servicefunktion **Codieradresse 2F**.

## Quelle

Maßgeblich ist die Viessmann-Serviceanleitung:

- **Vitodens 200, Typ WB2A, 8,8 bis 26,0 kW**
- Dokumentnummer **5681 573**
- Ausgabe **10/2006**
- Quelle: https://www.intec-heizung.de/media/pdf/c2/0c/64/Viessmann-Vitodens-200-WB2A-Serviceanleitung.pdf

Relevante Stellen:

- gedruckte Seite 7: Heizungsanlage füllen;
- gedruckte Seite 8/9: Heizungsanlage entlüften;
- gedruckte Seite 37: Codierung 1, `2F:0/1/2`;
- gedruckte Seite 42: Codierung 2, `2F:0/1/2`;
- gedruckte Seite 98/99: Funktionsbeschreibung Entlüftungs- und Befüllungsprogramm.

## Codierung und Optolink-Adresse

Die Serviceanleitung definiert:

| Codierung | Bedeutung |
| --- | --- |
| `2F:0` | Entlüftungs-/Befüllungsprogramm nicht aktiv |
| `2F:1` | Entlüftungsprogramm aktiv |
| `2F:2` | Befüllungsprogramm aktiv |

Im VDensHO1-Coding-Memory liegt Codieradresse 2F auf **Optolink `0x572F`**.

Diese Zuordnung ist konsistent mit dem bereits produktiv verwendeten Mapping
`21 -> 0x5721`, `23 -> 0x5723`, `30 -> 0x5730` und wird zusätzlich in
öffentlichen OpenV-Parametertabellen als `2F -> 572F` geführt.

## Entlüftungsprogramm

Bei `2F:1` beschreibt Viessmann folgenden Ablauf:

- Programmdauer maximal **20 Minuten**;
- Umwälzpumpe abwechselnd jeweils ca. **30 Sekunden EIN/AUS**;
- Umschaltventil wechselt zwischen Heizbetrieb und Trinkwassererwärmung;
- der **Brenner ist ausgeschaltet**;
- nach Ablauf setzt die Regelung Codieradresse 2F automatisch auf **0** zurück.

Für den beschriebenen Serviceablauf fordert die Anleitung vor Aktivierung des
Entlüftungsprogramms das **Schließen des Gasabsperrhahns**. Anschließend ist der
Anlagendruck zu prüfen.

## Befüllungsprogramm

Bei `2F:2` fährt das Umschaltventil in **Mittelstellung**, damit die Anlage
vollständig befüllt werden kann.

Wird bei eingeschalteter Regelung befüllt:

- Umschaltventil in Mittelstellung;
- interne Pumpe eingeschaltet;
- Brenner außer Betrieb;
- nach **20 Minuten** setzt die Regelung 2F automatisch wieder auf **0**.

Die Serviceanleitung enthält zusätzlich Vorgaben zu Füllwasserqualität,
Mindest-Anlagendruck und hydraulischen Absperrungen. Diese Arbeitsschritte
werden durch den HA-Schalter **nicht** ersetzt.

## Umsetzung im Projekt

Der Dienst:

```text
optolink-service-programs.service
  -> /usr/local/bin/optolink-service-programs
  -> MQTT
  -> optolink-splitter
  -> 0x572F
```

Home Assistant bekommt zwei Schalter:

```text
switch.vitodens_200_wb2a_entlueftungsprogramm
switch.vitodens_200_wb2a_befuellungsprogramm
```

und einen Statussensor:

```text
sensor.vitodens_200_wb2a_serviceprogramm_status
```

Intern bleibt es **ein einziges 3-Zustands-Register**.

## Sicherheitslogik

`optolink-service-programs`:

1. liest `0x572F` vor jeder Änderung;
2. akzeptiert ausschließlich Zielwerte `0`, `1`, `2`;
3. schreibt über die MQTT-Schnittstelle des Splitters, nie direkt seriell;
4. liest den Controllerzustand nach dem Write erneut;
5. wertet den Readback als maßgeblich, nicht nur den Transport-ACK;
6. versucht bei fehlgeschlagener Verifikation den vorherigen Wert
   wiederherzustellen;
7. pollt `0x572F` alle 5 Sekunden, damit die automatische 20-Minuten-
   Abschaltung sofort in HA sichtbar wird;
8. verhindert, dass ein OFF-Befehl des inaktiven HA-Schalters das jeweils
   andere aktive Programm beendet.

## MQTT Topics

| Topic | Richtung | Zweck |
| --- | --- | --- |
| `<base>/service_programs/venting/set` | HA -> Dienst | Entlüftung EIN/AUS |
| `<base>/service_programs/venting/state` | Dienst -> HA | bestätigter Zustand |
| `<base>/service_programs/filling/set` | HA -> Dienst | Befüllung EIN/AUS |
| `<base>/service_programs/filling/state` | Dienst -> HA | bestätigter Zustand |
| `<base>/service_programs/status` | Dienst -> HA | Modus, Raw-Wert, Diagnose |
| `<base>/service_programs/availability` | Dienst -> HA | online/offline |

## Manuelle Diagnose

Status des Dienstes:

```bash
systemctl status optolink-service-programs --no-pager
journalctl -u optolink-service-programs -n 100 --no-pager
```

Controllerwert nur lesen:

```bash
optolink-debug request 'r;0x572F;1;1;False'
```

Erwartete Werte:

```text
0 = Aus
1 = Entlüftung
2 = Befüllung
```

## Hinweis zur Serviceanleitung

Die vollständige Serviceanleitung ist urheberrechtlich geschütztes Material
von Viessmann. Dieses Repository verlinkt deshalb auf die öffentlich
zugängliche Quelldatei und spiegelt den vollständigen PDF-Inhalt nicht.

Für die lokale technische Ablage kann die Datei mit folgendem Helfer aus der
oben genannten Quelle geladen werden:

```bash
tools/fetch-wb2a-service-manual.sh
```
