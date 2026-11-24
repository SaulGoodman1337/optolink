# Raumregelung: Vorlauftemperatur nach Raumtemperatur

`optolink-room-control` passt die Vorlauftemperatur des Heizkreises A1/M1
an die gemessene Raumtemperatur an. Dazu kombiniert der Dienst einen oder
mehrere Raumtemperatursensoren aus Home Assistant, vergleicht das Ergebnis
mit einem einstellbaren Komfortband (untere und obere Schwelle) und setzt
den **externen Raumsollwert Normal** der WB2A an Adresse `0x2321`.
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
Raum < untere Schwelle:  Korrektur = +Verstärkung × (untere Schwelle − Raum)
Raum > obere Schwelle:   Korrektur = −Verstärkung × (Raum − obere Schwelle)
sonst:                   Korrektur = 0  → 0x2321 = 0 (normaler Sollwert)

Korrektur auf ± "max. Korrektur" begrenzt
externer Sollwert = runden(Raumsoll normal + Korrektur), 10..30 °C
```

* Änderungen erfolgen in Schritten von höchstens **1 K**, frühestens alle
  **5 Minuten**. Damit springt der Vorlauf nicht.
* Eine Hysterese von 0,75 K verhindert Pendeln an der Rundungsgrenze.
* Der Raumsollwert normal (`0x2306`) wird jeden Zyklus neu gelesen. Eine
  Änderung am Regler, im Dashboard oder durch die Party-Emulation wird also
  übernommen.

Standardwerte: untere Schwelle 20,5 °C, obere Schwelle 21,5 °C,
Verstärkung 1,0 K/K, max. Korrektur 2 K, Mittelung „Mittelwert“.
Die Regelung startet **ausgeschaltet** und wird im Dashboard aktiviert.
Die Einstellungen bleiben in `/var/lib/optolink-room-control/state.json`
erhalten.

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
  Phase (Nachtabsenkung) gilt der reduzierte Sollwert.

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
| `number.vitodens_200_wb2a_raumregelung_schwelle_min` | untere Raumtemperatur-Schwelle (15..25 °C) |
| `number.vitodens_200_wb2a_raumregelung_schwelle_max` | obere Raumtemperatur-Schwelle (15..26 °C) |
| `number.vitodens_200_wb2a_raumregelung_verstaerkung` | K Sollwertkorrektur je K Abweichung (0,5..3) |
| `number.vitodens_200_wb2a_raumregelung_max_korrektur` | maximale Korrektur (1..5 K) |
| `select.vitodens_200_wb2a_raumregelung_mittelung` | Mittelwert / Minimum / Maximum |
| `sensor.vitodens_200_wb2a_raumregelung_raumtemperatur` | kombinierte Raumtemperatur, Attribute: Einzelsensoren und `anzahl` der frischen Werte, die beim Dienst angekommen sind |
| `sensor.vitodens_200_wb2a_raumregelung_wirksamer_raumsollwert` | Raumsoll, mit dem die Therme gerade rechnet |
| `sensor.vitodens_200_wb2a_raumregelung_status` | Aus / Aktiv / Im Komfortband / Keine Sensordaten / Extern belegt / Störung / Fehler |
| `sensor.optolink_raumregelung_sensoren` | Anzahl gefundener Sensoren (Entity- und Geräte-Label, aus dem HA-Paket), Attribut `entities` |

MQTT-Themen unter `openv/room_control/`: `sensors` (Eingang),
`<parameter>/set` und `<parameter>/state` für `enabled`, `schwelle_min`,
`schwelle_max`, `verstaerkung`, `max_korrektur`, `aggregation`, sowie
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
