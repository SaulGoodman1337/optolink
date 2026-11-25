# Raumregelung: Vorlauftemperatur nach Raumtemperatur

`optolink-room-control` passt die Vorlauftemperatur des Heizkreises A1/M1
an die gemessene Raumtemperatur an. Dazu kombiniert der Dienst einen oder
mehrere Raumtemperatursensoren aus Home Assistant, vergleicht das Ergebnis
mit einem Komfortband um den Raumsollwert, den das **Zeitprogramm der
Therme gerade vorgibt**, und setzt den **externen Raumsollwert Normal** der
WB2A an Adresse `0x2321`.
Die Therme verschiebt den Vorlauf-Sollwert dann entlang der eingestellten
Heizkennlinie (D3/D4), genau so, als wäre der Raumsollwert geändert worden.
Mit `0x2321 = 0` gilt wieder der normale Raumsollwert `0x2306`.

Das ist **keine** angemeldete Vitotrol und kein echter Raumfühler im Sinne
der Firmware (KM-Bus). Es ist ein über den Splitter geschriebener
Stellwert, der live in beide Richtungen verifiziert wurde.

## Live-Nachweis (VDensHO1 / 20C2 / SW 0103, 11.10.2026)

Normaler Raumsollwert 21 °C, Ausgang Vorlauf-Soll 35,5 °C. Jeder Versuch
wurde per A/B/A durchgeführt und auf `0x2321 = 0` zurückgestellt.

| `0x2321` (extern) | Vorlauf-Soll `0x2544` |
| --- | --- |
| 20 °C | 35,0 °C |
| 21 °C | 35,5 °C (neutral) |
| 22 °C | 37,4 °C |
| 0 (aus) | 35,5 °C |

Die Kennlinie ist nicht linear und hängt von Außentemperatur und Heizkurve ab.

## Tag und Nacht nach Wochenplan

Der Dienst liest jeden Zyklus aus `0x2500` (22 Byte), in welcher Phase die
Therme laut ihrem Zeitprogramm gerade ist (Byte 1: 0 Abschaltbetrieb,
1 Reduziert, 2 Normal, 3 Dauernd Normal; Byte 12/13: aktueller Raumsoll
× 0,1). Daraus ergibt sich der **Basis-Sollwert**:

| Phase | Basis | Regelung |
| --- | --- | --- |
| Normal / Dauernd Normal (Heizzeit) | Tagestemperatur `0x2306` | korrigiert über `0x2321` |
| Reduziert (außerhalb der Heizzeit) | Nachttemperatur `0x2307` | nur Anzeige, `0x2321` freigegeben |
| Abschaltbetrieb, native Party (`0x2303`) | – | nur Anzeige, `0x2321` freigegeben |

Die Heizzeiten pflegst du wie bisher im Zeitprogramm (Dashboard
„Zeitprogramme“ oder am Gerät); die Regelung folgt automatisch.

Live geprüft am 24.11.2026 um 22:00 (Absenkphase, Nachttemperatur 18 °C,
außen −0,3 °C): `0x2321 = 23` ließ den aktuellen Raumsoll bei 18,0 °C und den
Vorlauf-Soll bei 36,5 °C. Der externe Sollwert wirkt also nur in der
Normalphase. Eine Nachtkorrektur ginge nur über Schreiben von `0x2307`
(EEPROM, deine Einstellung) und ist bewusst nicht eingebaut.

## Datenfluss

```text
HA-Sensoren mit Label "Optolink Raumregelung"
   │  Automation, jede Minute, nicht retained
   ▼
openv/room_control/sensors  {"sensors": {"sensor.wohnzimmer": 20.4, ...}}
   │
   ▼
optolink-room-control  ── Mittelwert / Minimum / Maximum
   │                     ── Komfortband, Verstärkung, max. Korrektur
   ▼  w;0x2321;1;<°C>  (über den Splitter, mit Readback)
Optolink-Splitter ──► WB2A: Raumsoll wirksam ──► Vorlauf-Soll
```

## Regelgesetz

```text
untere Schwelle = Basis − Toleranz unten,  obere Schwelle = Basis + Toleranz oben
Raum < untere Schwelle:  Korrektur = +Verstärkung × (untere Schwelle − Raum)
Raum > obere Schwelle:   Korrektur = −Verstärkung × (Raum − obere Schwelle)
sonst:                   Korrektur = 0  → 0x2321 = 0 (Sollwert laut Zeitprogramm)

Korrektur auf ± "max. Korrektur" begrenzt
externer Sollwert = runden(Basis + Korrektur), 10..30 °C
```

* Änderungen erfolgen in Schritten von höchstens **1 K**, frühestens alle
  **5 Minuten**. Damit springt der Vorlauf nicht.
* Liegt der Raum außerhalb des Bandes, korrigiert die Regelung immer um
  mindestens 1 K. Zurückgenommen wird erst, wenn der Raum 0,2 K innerhalb des
  Bandes liegt. Zwischen den Korrekturstufen gilt eine Hysterese von 0,75 K.
* Phase, Tages- und Nachttemperatur werden jeden Zyklus neu gelesen. Eine
  Änderung am Regler, im Dashboard, im Zeitprogramm oder durch die
  Party-Emulation wird also übernommen.

Standardwerte: Toleranz unten 0,5 K, Toleranz oben 0,5 K (bei 21 °C also
20,5..21,5 °C),
Verstärkung 1,0 K/K, max. Korrektur 2 K, Mittelung „Mittelwert“.
Die Regelung startet **ausgeschaltet** und wird im Dashboard aktiviert.
Die Einstellungen bleiben in `/var/lib/optolink-room-control/state.json`
erhalten.

## Morgenboost

Ist der Raum nach der Nachtabsenkung zu stark ausgekühlt, hebt der
Morgenboost den Raumsoll **zusätzlich** zur normalen Korrektur an:

```text
Start:  nur in den ersten 30 min nach Wechsel Reduziert → Normal,
        Raum < untere Schwelle − Auslösung, höchstens einmal pro Morgen
Wert:   Basis + normale Korrektur (mind. 1 K) + Morgenboost, sofort geschrieben
Ende:   Raum ≥ untere Schwelle, Höchstdauer erreicht oder Morgenboost = 0
danach: normale Regelung, zurück in 1-K-Schritten alle 5 min
```

Standard: Morgenboost 0 K (aus), Auslösung 1,0 K, Höchstdauer 90 min. Nach
einem Neustart des Dienstes während der Heizzeit gibt es an diesem Morgen
keinen Boost, weil der Phasenwechsel nicht beobachtet wurde.

## Sicherheitsregeln

* Der Dienst öffnet keine serielle Schnittstelle. Er schreibt
  ausschließlich `0x2321`, nur mit 0 oder 10..30 °C und immer mit Readback.
* Er gibt nur einen Wert frei, den er selbst geschrieben hat. Steht in
  `0x2321` ein fremder Wert, meldet er „Extern belegt“ und schreibt nichts.
* Sofortige Freigabe (`0x2321 = 0`) bei: Regelung aus, keine frischen
  Sensordaten (älter als 10 Minuten), aktive Störung (`0x5738`), codierter
  Raumeinfluss (`0x27A0`/`0x27B0` ≠ 0), Dienststopp.
* `ExecStopPost=optolink-room-control --release` gibt den Wert auch nach
  einem Absturz des Dienstes frei.
* Ist die Therme oder der Splitter nicht erreichbar, meldet der Dienst
  „Fehler“ und versucht es im nächsten Zyklus erneut. Er beendet sich nicht.
  Der zuletzt geschriebene Wert bleibt in dieser Zeit in der Therme stehen
  und wird freigegeben, sobald sie wieder antwortet und ein Freigabegrund
  vorliegt.
* Der externe Sollwert wirkt nur auf den Normalbetrieb. In der reduzierten
  Phase (Nachtabsenkung) gibt der Dienst `0x2321` frei und zeigt nur an.

## Home Assistant einrichten

1. Das Paket
   [`config/optolink-splitter/homeassistant-room-control-package.yaml`](../config/optolink-splitter/homeassistant-room-control-package.yaml)
   nach `<config>/packages/optolink_raumregelung.yaml` kopieren.
   `configuration.yaml` muss Pakete laden:
   `homeassistant: packages: !include_dir_named packages`.
2. Unter *Einstellungen → Bereiche, Labels & Zonen → Labels* das Label
   **„Optolink Raumregelung“** (ID `optolink_raumregelung`) anlegen.
3. Das Label allen Raumtemperatursensoren (`sensor.*`) oder Thermostaten
   (`climate.*`, verwendet `current_temperature`) zuweisen, die einfließen
   sollen. Alternativ das Label an das **Gerät** hängen (z. B. Shelly H&T):
   dann werden alle Temperatursensoren dieses Geräts (`device_class:
   temperature`) verwendet, die Luftfeuchte nicht. Sensoren hinzufügen oder
   entfernen heißt später nur: Label setzen oder entfernen.
4. Home Assistant neu starten.
5. Im Dashboard die Ansicht **Raumregelung** öffnen, Schwellen prüfen und
   die Regelung einschalten.

## Entities

| Entity | Bedeutung |
| --- | --- |
| `switch.vitodens_200_wb2a_raumregelung_aktiv` | Regelung ein/aus |
| `number.vitodens_200_wb2a_raumregelung_toleranz_unten` | Abstand der unteren Schwelle unter dem Basis-Sollwert (0,2..3 K) |
| `number.vitodens_200_wb2a_raumregelung_toleranz_oben` | Abstand der oberen Schwelle über dem Basis-Sollwert (0,2..3 K) |
| `sensor.vitodens_200_wb2a_raumregelung_phase` | Tag (Normal) / Nacht (Reduziert) / Abschaltbetrieb / Party, laut Zeitprogramm |
| `sensor.vitodens_200_wb2a_raumregelung_basis_sollwert` | Tages- bzw. Nachttemperatur, je nach Phase |
| `sensor.vitodens_200_wb2a_raumregelung_untere_schwelle` / `_obere_schwelle` | daraus berechnetes Komfortband in °C |
| `number.vitodens_200_wb2a_raumregelung_verstaerkung` | K Sollwertkorrektur je K Abweichung (0,1..20, frei wählbar) |
| `number.vitodens_200_wb2a_raumregelung_max_korrektur` | maximale Korrektur (1..20 K, frei wählbar; harte Grenze bleibt 0x2321 = 10..30 °C) |
| `number.vitodens_200_wb2a_raumregelung_morgenboost` | zusätzliche K beim Morgenboost (0 = aus) |
| `number.vitodens_200_wb2a_raumregelung_morgenboost_ausloesung` | Boost startet, wenn der Raum so viele K unter der unteren Schwelle liegt |
| `number.vitodens_200_wb2a_raumregelung_morgenboost_dauer` | Höchstdauer des Boosts (10..480 min) |
| `select.vitodens_200_wb2a_raumregelung_mittelung` | Mittelwert / Minimum / Maximum |
| `sensor.vitodens_200_wb2a_raumregelung_raumtemperatur` | kombinierte Raumtemperatur, Attribute: Einzelsensoren und `anzahl` der frischen Werte, die beim Dienst angekommen sind |
| `sensor.vitodens_200_wb2a_raumregelung_wirksamer_raumsollwert` | Raumsoll, mit dem die Therme gerade rechnet |
| `sensor.vitodens_200_wb2a_raumregelung_status` | Aus / Aktiv / Morgenboost / Im Komfortband / Nachtabsenkung – nur Anzeige / Abschaltbetrieb / Party / Keine Sensordaten / Extern belegt / Störung / Fehler |
| `sensor.optolink_raumregelung_sensoren` | optional, nur mit dem HA-Paket: Anzahl gefundener Sensoren, Attribut `entities` |

MQTT-Themen unter `openv/room_control/`: `sensors` (Eingang),
`<parameter>/set` und `<parameter>/state` für `enabled`, `toleranz_unten`,
`toleranz_oben`, `verstaerkung`, `morgenboost`, `morgenboost_ausloesung`,
`morgenboost_dauer`, `max_korrektur`, `aggregation`, sowie
`status` (JSON, retained) und `availability`.

## Betrieb

```bash
systemctl status optolink-room-control --no-pager
journalctl -u optolink-room-control -n 100 --no-pager
cat /var/lib/optolink-room-control/state.json
optolink-debug request "read;0x2321;1"      # 00 = normaler Sollwert
```

Manuell freigeben (nur wenn der Dienst den Wert besitzt):

```bash
systemctl stop optolink-room-control      # Stop gibt frei, ExecStopPost sichert ab
```
