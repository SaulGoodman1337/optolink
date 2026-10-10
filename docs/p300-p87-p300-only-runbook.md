# P87-Kandidat: Statusaenderungen unter ausschliesslich P300 lesen

Stand: 2026-10-08. Werkzeug `tools/wb2a-p87-p300-check.py` 1.0.0.
**Implementiert und offline getestet; kein neuer Hardwarelauf durch diese Entwicklung.**

## Zweck und Abnahmegrenze

Der Nutzervergleich unter VS1 ergab 59 stabile Uebereinstimmungen von P87 mit
`Virtual_READ 55D3/11`, Byte 7 (achtes Byte), und einen uneindeutigen Uebergang.
Diese Beobachtungen bleiben erhalten: [VS1-Ergebnis](p300-p87-vs1-result-2026-10-08.md).
Jetzt wird die separate Frage geprueft: **Aendert sich dieser normale Statusblock
in einer durchgehend P300-lesenden Phase, ohne externe GFA-Abfragen?**

Eine Aenderung ist Evidenz fuer Aktualisierung waehrend dieser Phase. Sie ist
weder ein Nachweis gleichzeitiger P87-Gleichheit noch einer bestimmten Latenz,
kein Ersatz fuer P06/P09 und keine Freigabe der Pumpensteuerung. Ein statischer
Wert ist unentschieden, nicht automatisch der Nachweis eines eingefrorenen Caches.
Interne Kommunikation zwischen Regelung und Feuerungsautomat wird NICHT
unterbunden: ausgeschlossen werden die externen GFA-Auftraege ueber Optolink.

## Fester Ablauf

1. Originales VS1, bekannte Einstellungen und beendete Altversuche verlangen.
   Gemeinsame Locks verhindern Parallelbetrieb mit Handover, CANARY und dem
   P87-MQTT-Beobachter. Einstellungen werden per AST gelesen, nicht importiert.
2. Private Kopie des neuen Skripts und seines unveraenderten Handover-Helfers
   erzeugen. Der Helfer wird vor Benutzung mit SHA256
   `e419e0a32206a7398edadff2cb1f5f57ac1884df6532ee26c3b3e75e38cd1269` geprueft.
   Gehashtes Quellmaterial wird direkt kompiliert; kein fremder Bytecode geladen.
3. Temporaeren Systemd-Worker einschliesslich ExecStopPost registrieren,
   BEVOR die bisher aktiven Dienste angehalten werden. Stop-/Restore-Absichten
   werden jeweils vor dem Stop persistent gespeichert.
4. Bekannte Zusatzdienste/Timer, zuletzt den VS1-Splitter pausieren. Exklusives
   Oeffnen mit pyserial und TIOCEXCL, zusaetzliche Pruefung sichtbarer Portbesitzer.
5. Konservative Zwei-ENQ-VS1-Referenz: 20c2, 0103 und GFA P80/P06/P09/P87 lesen.
6. Einmal auf P300 wechseln und 20c2/0103 mit FC01 bestaetigen. Danach waehrend
   des Beobachtungsfensters **nur FC01 55D3/11**, plus zugehoerige ACKs senden.
   Auch erneuter EOT, VS1/F7, VS1/6B und C9 sind in dieser Phase im Sender gesperrt.
7. Nach jeder vollstaendigen Statusantwort mindestens eine Sekunde warten;
   damit hoechstens ein Statusread pro Sekunde, keine Nachholbursts.
   Alle fuenf Samples die pausierten Dienste und sichtbaren Portbesitzer pruefen.
   Falscher Frame, Timeout, ungeklaertes FF-Statusbyte oder neu gestarteter
   Produktionsdienst beendet die Beobachtung; kein versteckter Reconnect/Retry.
8. Abschliessend separat auf dem bestaetigten Zwei-ENQ-Weg nach VS1 zurueck,
   Identitaet/Software und denselben GFA-Block lesen; Port schliessen.
9. ExecStopPost stellt die zuvor aktiven Dienste wieder her. Originalsplitter
   zuerst; seine aktuelle Invocation muss die Hauptschleife erreichen. Bei
   Fehler keine blinde Wiederaufnahme der Writer. Timer zuletzt.

**Keine Physical_READ/WRITE, EEPROM-/RAM-/Parameterwrites, kein C9, kein neues
Serviceprogramm und keine Betriebsart-/Sollwertaenderung zum Erzwingen einer
Reaktion.** Der neue feste Statusframe lautet `41 05 00 01 55 D3 0B 39`.
Er ist ein normaler Datenpunktread, kein physischer Speicherzugriff. Identische
Adresse/Laenge unter VS1 ist bereits beobachtet; Annahme und Frische unter P300
sind genau Gegenstand dieses Tests, nicht vorher als hardwarebestaetigt behauptet.

Der Prober bietet weder MQTT- noch TCP-Server und keine generischen Kommandos.
Er aendert keine Dateien in `/opt/optolink`, keine produktive Unit, kein
HA-Profil und keinen Updatekanal. Die bekannten Dienste behalten beim Stop/Start
ihre eigenen normalen Lebenszyklen: nicht waehrend aktiver Party-, Wartungs-,
Zeitplan-Schreib- oder Serviceprogrammoperation ausfuehren.

## Vorbereitung

Als root in der bestehenden Optolink-LXC. Zuerst den im zugehoerigen
PR-Kommentar genannten geprueften Commit per Fast-forward holen. Keine lokalen
Aenderungen durch Reset/Force beseitigen. Die beiden Dateien im Projekt bleiben
beisammen; keine Kopie in den alten P300-Kandidaten und kein erneuter Stager.

```bash
cd /root/p300-trial-work/project
/opt/optolink/venv/bin/python -m unittest discover -s tests -p test_p87_p300_check.py -v
/opt/optolink/venv/bin/python tools/wb2a-p87-p300-check.py
```

Erwartung: **37 Tests erfolgreich**, danach `PLAN ONLY`.
Ohne `--execute` keine seriellen, MQTT- oder Systemd-Aufrufe und keine
Ergebnisdateien. Die unveraenderte lokale Helferquelle wird trotzdem verifiziert.
Der Test ist eigenstaendig; den alten C9-CANARY NICHT aktivieren und seine
GFA-Schutzpruefung NICHT entfernen.

## Einmalige Beobachtung

Der vorige P87-MQTT-Beobachter muss beendet sein. Keine Updates, weitere
Diagnoseclients oder Bedien-/Schreibversuche waehrend dieses Fensters.
Am aussagekraeftigsten ist eine ohnehin bevorstehende natuerliche Zustandsaenderung.
Keinen Brennerstart durch dieses Werkzeug oder zusaetzliche Sollwerte erzwingen.

```bash
/opt/optolink/venv/bin/python -u \
  /root/p300-trial-work/project/tools/wb2a-p87-p300-check.py \
  --execute --seconds 300
```

**Anders als beim vorherigen MQTT-Vergleich sind die normale HA-/MQTT-Telemetrie
und Zusatzdienste fuer dieses Fenster pausiert.** Sonst wuerden deren GFA-Reads
unseren Test verfaelschen. `--seconds 300` ist die Beobachtungsdauer nach dem
P300-Einstieg; Aufbau und Wiederherstellung kommen hinzu. Erlaubt: 30..600 s.

Die Unit heisst `optolink-p87-p300-check.service`. Bei 300 s Beobachtung hat
sie `RuntimeMaxSec=420` und `TimeoutStopSec=180`; das sind getrennte Limits,
KEINE garantierte gesamte Ausfallzeit. Fehler von Systemd, Kernel, USB, Strom
oder ein administrativer Eingriff koennen erfolgreiche Wiederherstellung
verhindern. Sichtbare Port-/Dienstpruefungen sind keine allumfassende Kontrolle
anderer Namespaces oder weiterer physischer Adapter.

`systemd-run --wait` zeigt die Zusammenfassung nach Ende. Aus einer zweiten
Konsole lassen sich die Statuszeilen live sehen:

```bash
journalctl -fu optolink-p87-p300-check.service
```

Strg+C dort beendet nur die Journalansicht. Das Schliessen der startenden
SSH-Konsole ist kein definierter Abbruch des ueberwachten Workers.

## Abbrechen und Wiederherstellung

Aus einer zweiten LXC-Konsole:

```bash
systemctl stop optolink-p87-p300-check.service
```

Nicht den alten CANARY-/Handover-Abbruchbefehl benutzen: dies ist eine andere
Unit. Der Stop veranlasst Link-Recovery und ExecStopPost. Auch nach negativem
Leseergebnis wird Wiederherstellung versucht; Fehler werden nicht zum PASS.

Nach abgeschlossenem Worker kontrollieren:

```bash
systemctl show optolink-splitter.service -p WorkingDirectory -p ActiveState -p SubState
optolink-debug request 'gfaread;0x4050;1;raw;False' --timeout 8
optolink-debug request 'gfaread;0x4006;1;raw;False' --timeout 8
```

Erwartet: Originaldienst `/opt/optolink`, active/running, P80=20/Status1 und
zustaendiger gueltiger P06-Wert. Auch HA-Frische und zuvor aktive Dienste pruefen.
Diese externen Kontrollabfragen nicht parallel in die P300-Beobachtung senden.

Notweg: zuerst den neuen Worker stoppen und dessen Ende bestaetigen, dann
`systemctl start optolink-splitter.service` und `journalctl -u optolink-splitter.service -n 80 --no-pager`.
Zusatzdienste nur gemaess `state.json`/`recovery.json` wiederherstellen, nicht
pauschal alle einschalten. Der Prober verweigert neue Versuche, wenn eine
vorherige Restore-Absicht noch ohne erfolgreichen Wiederherstellungsbericht ist.
Reports nicht zum Umgehen dieser Sperre loeschen; erst die Ursache klaeren.

## Ergebnislabels

- `CHANGES_OBSERVED_WITHOUT_EXTERNAL_GFA`: nach dem ersten 10-s-Abschnitt wurde
  zwischen zwei spaeteren Samples eine Aenderung beobachtet und der neue Wert
  in drei aufeinanderfolgenden Samples ueber mindestens 1,5 s bestaetigt.
- `INCONCLUSIVE_NO_LATE_STATUS_CHANGE`: keine solche spaete Aenderung. Das gilt
  auch fuer konstant 62, lauter Nullen oder ausschliesslich eine Startaenderung.
- `INCONCLUSIVE_UNCONFIRMED_CHANGE`: spaete Aenderung sichtbar, aber ohne diese
  Bestaetigung, etwa direkt am Messende.
- `FAILED_OR_INCOMPLETE`: Protokoll-/Abbruch-/Wiederherstellungsfehler oder
  unvollstaendige Ausfuehrung. Partielle Daten bleiben erhalten.

10 s und drei Samples sind bewusst gewaehlte Forschungskriterien, kein belegter
Cache-Timeout oder mathematischer Beweis von Echtzeit. Eine spaete bestaetigte
Aenderung stuetzt Aktualisierung OHNE externe GFA-Reads in diesem Fenster.
Sie schliesst nicht jeden denkbaren internen Cache/anderen Updateausloeser aus.
Eine fehlende gleichzeitige P87-Referenz wird nicht erfunden; genaue Latenz und
Gleichheit schneller Zwischenzustaende bleiben offen. P06/P09 werden nicht ersetzt.

Separat: `LINK_AND_SERVICE_RESTORE=PASS` bestaetigt die Link- und
Dienstwiederherstellung des Werkzeugs, nicht allein MQTT-/HA-Datenfrische.
`GFA_AFTER` zeigt den abschliessend ueber VS1 gelesenen GFA-Block.

## Ergebnisdateien

Ausgegebener `SESSION`-Pfad unter `/root/p300-trial-work/p87-p300-results/run-...`:
`measurement.json` (Referenzen, gesamte P300-Zeitreihe, TX/RX-Spur, Auswertung,
Fehler), `samples.jsonl` (laufend geflushte Samples, auch bei hartem Workerende),
`state.json` (Stop-/Restore-Absichten und Quellhashes), `recovery.json` sowie die
beiden privaten Skriptkopien. Verzeichnisse 0700, Dateien 0600. Es werden keine
MQTT-Zugangsdaten kopiert. Technische Telemetrie vor Weitergabe pruefen.

Bei beendetem Test reichen zunaechst Konsole und nachfolgende P80/P06-Antworten;
bei Fehlern oder fuer genaue Verlaufsanalyse measurement.json, samples.jsonl
und recovery.json beilegen. Kein automatischer Upload und keine Endlosschleife.

## Verifikation und Quellen

37 neue Offline-Tests: phase-spezifische TX-Sperren, feste Frames/Pruefsummen,
fragmentierte Antworten, 16 Fehlerarten ohne Replay, Identitaetsfehler, fehlende
Referenz, konkurrierende Dienste, Rate-Limit, fruehe/statische/spaete Aenderungen,
Abbruch und selektive Wiederherstellung sowie Supervision vor Dienststop.
Die bisherige Handover-Implementierung bleibt bytegleich und hash-gepinnt.
60 bestehende Handover-Tests lokal erfolgreich; bei der bestehenden P300-Suite
ist lokal ein Adaptertest mangels Laufzeitabhaengigkeit uebersprungen. CI muss
alle 29 bestehenden P300-Tests einschliesslich dieses Adaptertests ausfuehren.
Commit-bezogene CI-Ergebnisse stehen im PR-Kommentar. Kein echter Broker-,
Systemd-, USB- oder Heizungszugriff durch die Offline-Entwicklung.

- [Implementierung](../tools/wb2a-p87-p300-check.py), [Tests](../tests/test_p87_p300_check.py)
- [Vorheriges P87-Ergebnis](p300-p87-vs1-result-2026-10-08.md)
- [GFA-Quellenabgleich](p300-gfa-source-candidates-2026-10-08.md)
- [OpenV P300-Drahtformat](https://github.com/openv/openv/wiki/Protokoll-300), am 2026-10-08 geprueft: FC01, Antwortlaenge, ACK, additive Pruefsumme; keine Zusage der WB2A-Statusfrische.
- [pyserial API](https://pyserial.readthedocs.io/en/latest/pyserial_api.html), am 2026-10-08 geprueft: Timeout-/Exclusive-Semantik; zusaetzliche Linux-TIOCEXCL-/Owner-Pruefung aus dem gepinnten Helfer.
