# WB2A: echter Optolink-Stellweg fuer Raumtemperatur – positive Liveversuche

**11.10.2026, 14:32–14:35 Uhr CEST.** Zweimalige aktive Experimente
auf VDensHO1 / 20C2 / Software 0103. Keine Aenderung an
/opt/optolink, kein Merge nach main, keine zweite serielle Verbindung.

## 1. Echte Vitotrol vs. Raumfuehrung

Die richtige KM-Bus-Vitotrol 200/300 ist weiterhin **nicht angemeldet**:
Softwareindex 0x0A5C=00000000, Sensorstatus 0x089C=03,
Raumtemperaturanzeige 0x0896=c800. Der bereits real getestete
P300-Physical_WRITE auf RX-RAM 0x1642 und Original-V300-Slaveantworten
erreicht die Firmware-RX-ISR bzw. den Teilnehmerparser nicht.

**Ein anderer, real funktionierender Weg wurde jetzt gefunden:**
Virtual_WRITE des externen Raum-Sollwerts Normal HK1/A1/M1 an
Adresse **0x2321** ueber den existierenden Optolink-Splitter.
Mit dem Wert 00 gilt wieder die regulaere lokale Raumsollvorgabe.
Dies ist *keine* registrierte Vitotrol oder ein echter Raumfuehler,
aber ein wirksamer Raumtemperaturabhaengiger Stellkanal.

## 2. Originalzustand beider Experimente

Vor jedem Lauf am echten Heizgeraet ausgelesen:

| Controlleradresse | Live-Ruecklesung | Semantik |
| --- | --- | --- |
| 0x00F8/8 | 20c2000300000103 | Identifikation VDensHO1 |
| 0x2306/1 | 15 | 21 Grad C Raumsoll |
| 0x2321/1 | 00 | kein externer Sollwert |
| 0x2544/2 | 6301 | 35,5 Grad C Vorlauf-Soll |
| 0x5738/1 | 00 | keine aktuelle Stoerung |

### Heizanhebung A/B/A

Testannahme einer Raumtemperatur 20 Grad C bei Soll 21 Grad C;
nur fuer diesen Test errechneter externer Sollwert 22 Grad C.
Schreibbefehl Virtual_WRITE / optolink-debug:
writeraw;0x2321;16. Der Regler meldete 0x2321=16.

| Phase | Vorlauf-Soll |
| --- | --- |
| Ausgang | **35,5 Grad C** |
| 22 Grad C extern aktiv, erster Read | **37,4 Grad C** |
| 22 Grad C extern aktiv, zweiter Read | **37,4 Grad C** |
| Auf 00 zurueckgestellt | **35,5 Grad C** |

**Live-Ergebnis: +1,9 Grad C am Vorlauf-Soll.**

Privat vorhandene Maschine:
 /tmp/wb2a-vitotrol-external-room-live-20261011.json

### Heizabsenkung A/B/A

Testannahme einer Raumtemperatur 22 Grad C bei Soll 21 Grad C;
externer Sollwert 20 Grad C.
Schreibbefehl: writeraw;0x2321;14. Reglerantwort bestaetigte
den angenommenen Wert.

| Phase | Vorlauf-Soll |
| --- | --- |
| Ausgang | **35,5 Grad C** |
| 20 Grad C extern aktiv, erster Read | **35,0 Grad C** |
| 20 Grad C extern aktiv, zweiter Read | **35,0 Grad C** |
| Auf 00 zurueckgestellt | **35,5 Grad C** |

**Live-Ergebnis: -0,5 Grad C am Vorlauf-Soll.**

Privat vorhandene Maschine:
 /tmp/wb2a-vitotrol-external-room-cooling-live-20261011.json

### Neutrale Mitte als dritter Liveversuch (14:49 Uhr CEST)

In einer separat mit unabhängiger Rückstellung ausgeführten A/B/A-Probe
wurde der externe Sollwert bewusst genau auf den **normalen Sollwert
21 Grad C** gesetzt: writeraw;0x2321;15, angenommen bei einer
gedachten Raumtemperatur von 21 Grad C.

| Phase | Vorlauf-Soll |
| --- | --- |
| Vor dem Eingriff | **35,5 Grad C** |
| Extern 21 Grad C aktiv – 1. Rücklesung | **35,5 Grad C** |
| Extern 21 Grad C aktiv – 2. Rücklesung | **35,5 Grad C** |
| Nach Rückstellung 0x2321=00 | **35,5 Grad C** |

Der neutrale Punkt erzeugt **0,0 Grad C** Vorlauf-Sollwertänderung.
Privates Original-JSON:
 /tmp/wb2a-vitotrol-external-room-neutral-live-20261011.json

Damit ist die beobachtete Reihenfolge **20 / 21 / 22 Grad C externer
Raumsoll → 35,0 / 35,5 / 37,4 Grad C Vorlauf-Soll** an genau
dieser WB2A reproduziert. Die Steigung ist nicht linear.
Auch für den dritten Test wurden Reglercode, aktueller Fehler,
A0/B0 und wieder auf 00 gesetzter externer Sollwert kontrolliert,
bevor der unabhängige Restore-Timer deaktiviert wurde.

**Es sind echte, in beide Richtungen verifizierte Reglerreaktionen**,
nicht nur angenommene Unterschiede oder erfolgreich beantwortete
Schreibbefehle. Die asymmetrische Kennlinie ist eine Momentaufnahme
und keine universelle Heizkurvencharakteristik.

## 3. Aktive Einzelprobe und Qualitaetssicherung

Im Entwicklungszweig:
- tools/wb2a-external-room-influence.py
- tests/test_wb2a_external_room_influence.py
- tests/test_wb2a_external_room_live_evidence.py

Die Einzelprobe benutzt den Original-Splitter und dessen MQTT-/
optolink-debug-Kommandoweg, keine eigene serielle Verbindung.
Sie berechnet aus Messwert, Ziel und begrenztem P-Faktor:

    external_c = target_c + clip(kp * (target_c - room_c), -3, +3)

Auf 16–26 Grad C begrenzt, kein PI-Anteil, nur testweise.
Fuer jedes aktive Ausfuehren muss unabhaengige systemd-Rueckstellung
bereits vorab bewaffnet sein. Default ist Dry-Run.
Akzeptiert ausschliesslich den Zielcontroller, Ausgangsadresse 0,
normalen Sollwert und keine aktuelle Stoerung; aktive A/B/A-Phase
auf maximal 30 Sekunden begrenzt, ruecksetzen auf 00 mit Readback.
NaN/Unendlich als Haltedauer werden explizit zurueckgewiesen.
Die echte Heater-Response wurde in zwei privaten JSON-Berichten
geprueft, keine Vitotrol-Registrierung vorgetaeuscht.

## 4. Experimentelle, nicht gestartete MQTT-Raumrueckkopplung

Eine weiterentwickelte Komponente ist:
tools/wb2a-room-feedback-mqtt.py mit synthetischen Regressionstests
tests/test_wb2a_room_feedback_mqtt.py.

**Nicht als Produktivservice eingerichtet oder gestartet.**
Sie ist ein maximal einstündiger, nur durch --execute aktivierbarer
Experimenttreiber fuer eine **echte externe Raumtemperaturquelle**:

- Nur ein explizit gesetztes MQTT-Topic ohne Wildcards.
- Frische, nicht-retainierte numerische Messwerte 10–32 Grad C
  (oder streng genau ein JSON-Feld temperature).
- Ohne Messwert oder bei Ablauf von 90 Sekunden: setze 0x2321 auf 00.
- Rate-Limit mindestens 25 Sekunden zwischen Updates,
  begrenzter P-Regler und maximal 1 Grad C je Folgeupdate.
- Erkennt Stoerung, A0/B0-Aktivierung, Sollwertveraenderung
  und manuelle Uebernahme von 0x2321.
- Rueckstellung auf 00 bei Fehler oder normalem Ende,
  sofortiges readback nach jeder Stellwertuebergabe.
- Fuer SIGKILL, Hostausfall oder Netzwerkverlust ist zusaetzlich
  ein UNABHAENGIGER Wiederherstellungstimer notwendig.
- Kein direkter Brenner- oder Pumpenbefehl; keine unbekannten
  RAM-, SFR- oder KM-Bus-Schreiboperationen.

Im bestehenden Home-Assistant-Dashboard steht bereits die Entity
sensor.temperatursensorwohnzimmer_temperatur, aber sie ist
**keine nachgewiesene MQTT-Topic**. Ein passiver, authentisierter
MQTT-Broker-Audit fand in 388 Retained-Discovery-Konfigurationen
und gaengigen Sensor-Topicfamilien **keine sicher passende**
Wohnzimmertemperaturquelle. Es wurde deshalb **kein erfundener
Sensorwert als echter Messwert ins Livegeraet eingespeist**.

Das optionale, nicht in Home Assistant installierte Beispiel
config/optolink-splitter/ha-optolink-room-feedback-example.yaml
publiziert die schon im Dashboard vorhandene Sensor-Entity jede
Minute und bei Aenderungen als **non-retained** MQTT-Nutzwert
an openv/room/temperature. Es ist nur als Installationsvorlage
gedacht, nicht als automatisch ausgefuehrte HA-Konfiguration.
Der bestehende Optolink-Befehlsempfaenger openv/cmnd bleibt
davon unberuehrt.

Testbar ohne Controllerwrites:

    python3 tools/wb2a-room-feedback-mqtt.py \
      --sensor-topic openv/room/temperature

Nach wirklicher Sensor-Topic-Verifizierung sowie separat bewaffneter
Rueckstellung waere eine zeitlich begrenzte, beaufsichtigte
Ausfuehrung denkbar. Es wurde **kein** solcher Dauerlauftest
gestartet.

## 5. Echte Vitotrol-Teilnehmeranmeldung bleibt ein separates Gate

Der unabhängige C-Emulator
https://github.com/boblegal31/Heater-remote
(Repositorystand db1290705c1495d2f00f63aea844dda06914d3f4)
sendet echte physikalische Slot2-KM-Bus-Slaveantworten mit
eigener MCU, UART und Bus-Elektronik. Die Quelle bestaetigt
Original-Kommandoreihenfolge F8-Identitaet, Reg00 und PONG,
**liefert aber keinen ueber Optolink erreichbaren ROM-RX-Dispatcher
der lokalen WB2A**.

Der bereits real nachgewiesene Optolink-P300-Physical_WRITE FC04
auf den RX-RAM-Kandidaten 0x1642 liefert zwar bitgenaue
Vitotrol-300-Antworten, aber kein UART1-RX-Hardwareereignis
und keine Teilnehmeruebernahme. Diese Baustelle wird nicht als
abgeschlossen ausgegeben; die neue Raumrueckkopplung ist eine
**funktionale Alternative fuer Raumfuehrung**, kein Protokollemulator.

## 6. Abschliessende Reglerkontrollen

Beide A/B/A-Livetests wurden mit **zwei separat im Voraus
bewaffneten unabhängigen systemd-Restore-Timern** ausgefuehrt.
Timer jeweils **erst nach echtem Register-Readback** deaktiviert:

| Diagnose | Zustand am 11.10.2026 14:35 Uhr CEST |
| --- | --- |
| 0x2321 externer Raumsoll | 00 |
| Normalraum-Soll 0x2306 | 15 = 21 Grad C |
| Vorlauf-Soll 0x2544 | 6301 = 35,5 Grad C |
| Aktuelle Stoerung 0x5738 | 00 |
| A0 / B0 | 00 / 00 |
| Originaler Optolink-Splitter | active, vs1protocol=True |
| Aktiver passiver RPM-Recorder | active |

Kein Produktiv-Merge, keine Installation des neuen MQTT-Reglers,
kein Verwechseln der zwei technischen Ziele.
