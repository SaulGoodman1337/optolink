# Therme bei CO-/Gasalarm abschalten

Home-Assistant-Blueprint
[`config/optolink-splitter/homeassistant-blueprints/therme_gas_co_alarm.yaml`](../config/optolink-splitter/homeassistant-blueprints/therme_gas_co_alarm.yaml).
Er läuft komplett in Home Assistant und nutzt nur Entities, die der Splitter
ohnehin bereitstellt. Am Splitter selbst ändert sich nichts.

## Was passiert bei Alarm

1. Ein Melder (Binärsensor) geht auf `on`.
2. Die aktuelle Betriebsart wird in einem `input_text` gemerkt.
3. Eingetragene Gas-Absperrventile werden geschlossen (`valve.close_valve`
   oder `switch.turn_off`/`turn_on`, einstellbar).
4. Die Sperre (`input_boolean`) geht an.
5. Sofort eine Alarm-Push an alle gewählten Handys (Android: `ttl: 0`,
   `priority: high`, Kanal `alarm_stream`, also auch bei „Nicht stören“;
   iOS: kritische Mitteilung).
6. Partybetrieb aus (die Party-Emulation würde sonst `0x2323` wieder auf
   „Dauernd Normal“ setzen), dann Betriebsart **Abschalt** (`0x2323 = 0`).
   Bis zu 3 Versuche mit je 60 s Wartezeit auf die Rückmeldung.
7. Zweite Push: „Therme ist AUS“ oder „konnte NICHT abgeschaltet werden“.

## Sperre

Solange die Sperre an ist, wird jede Änderung der Betriebsart (Dashboard,
Zeitprogramm-Dienste, andere Automationen) und jedes Einschalten des
Partybetriebs sofort zurückgestellt, mit Push. Zusätzlich prüft die
Automation jede Minute und nach jedem HA-Start.

Die anderen Dienste schalten die Therme nicht wieder ein:

| Dienst | Verhalten bei Betriebsart 0 |
| --- | --- |
| `optolink-room-control` Nachtabschaltung | schreibt `0x2323` nur 2 → 1 und nur 1 → 2, wenn sie selbst auf 1 gestellt hat. Steht 0 da, gibt sie die Zuständigkeit ab und schreibt nichts. |
| `optolink-room-control` Tag | schreibt nur `0x2321` (Raumsollwert), wirkt im Abschaltbetrieb nicht. |
| Pumpenwächter | regelt nur die Pumpendrehzahl (RAM `0x20A5`), nie den Brenner. |
| Party-Emulation | würde `0x2323 = 4` setzen, deshalb schaltet die Automation Party aus und hält ihn aus. |

Die Sperre auch von Hand einschalten = Therme sofort aus (Not-Aus über HA).

## Aufheben

Sperre von Hand ausschalten. Meldet noch ein Melder Alarm, geht sie sofort
wieder an. Sonst wird die gemerkte Betriebsart wiederhergestellt (Fallback
„Heizen + WW“). **Ein Absperrventil wird nie automatisch geöffnet.**

## Test

Der `input_button` schickt nur eine Test-Push mit dem Zustand aller Melder;
die Therme bleibt an. Den echten Ablauf testet man mit der Sperre (von Hand
an, nach 1–2 Minuten wieder aus).

## Gas-Absperrventil nachrüsten

In der Automation (Einstellungen → Automationen → „Therme bei
CO-/Gasalarm abschalten“) das Feld **Gas-Absperrventil** füllen. Bei einem
`switch` angeben, ob „aus“ oder „ein“ schließt (stromlos geschlossene
Ventile: Ausschalten).

## Grenzen

- Abschaltbetrieb ist eine Software-Abschaltung über die Regelung. Der
  Frostschutz der Regelung bleibt aktiv (bei Außentemperatur unter ca.
  +1 °C läuft die Heizkreispumpe, bei sehr kalter Anlage kann der Brenner
  kurz starten). Das ersetzt kein Gas-Absperrventil.
- Ist der Splitter oder die Optolink-Verbindung weg, kann HA die Therme
  nicht abschalten. Die zweite Push meldet das.
- Ist ein Melder länger offline (Standard 30 min), kommt eine Warn-Push.

## Live-Installation (2026-11-26)

- Helfer: `input_boolean.therme_gas_co_sperre`,
  `input_text.therme_gasalarm_vorherige_betriebsart`,
  `input_button.therme_gasalarm_test`.
- Blueprint gespeichert als `blueprints/automation/optolink/therme_gas_co_alarm.yaml`.
- Automation `automation.therme_bei_co_gasalarm_abschalten` mit den Meldern
  `binary_sensor.kohlenmonoxid_explosivgasmelder_mit_farbdisplay_kohlenmonoxid`,
  `binary_sensor.kohlenmonoxid_explosivgasmelder_mit_farbdisplay_gas`
  (Tuya-Kombimelder) und `binary_sensor.hw_gas_sensor_gas` (Tuya-Gasmelder HW).
- Dashboard: roter Hinweis über der Kopfzeile + Badge „Gas-/CO-Sperre“,
  Abschnitt „Gas-/CO-Schutz“ in der Diagnose.
