# WB2A: instrumentierter VS1/P300-Handover-Basistest

Stand: 2026-10-08. Werkzeug: `tools/wb2a-handover-probe.py`, Version 1.0.0.
Status: **implementiert und offline getestet; dieser neue Test wurde noch NICHT an der Heizung ausgefuehrt**. Kein P300-Produktivwechsel und keine Freigabe fuer Pumpen-RAM-Overrides.

## Warum dieser Test als Naechstes?

Die [direkte Quellenpruefung](p300-gfa-host-trace-2026-10-08.md) bestaetigt den bekannten Vitosoft-Weg: abstrakt GFA_READ=C9, Uebersetzung nach VS1/6B und Interfacewechsel bei VSKO. Ein neuer nativer P300-GFA-Aufruf wurde nicht belegt. Der bisherige C9-CANARY wird nicht wiederholt.

Der alte Latenzhelfer meldete insgesamt 5990,3 ms, ohne die beiden ENQ-Wartephasen auf dem Rueckweg einzeln auszugeben. Vor seinem Messbeginn wurde keine frische VS1-Datenantwort nachgewiesen. Der neue Test zerlegt den Ablauf und bestaetigt vor JEDEM gemessenen Wechsel eine echte VS1-Identitaetsantwort.

**Die erste Runde bleibt bewusst beim bekannten Zwei-ENQ-Ablauf.** Eine Ein-ENQ-Variante ist hier weder implementiert noch freigegeben. Erst anhand der Teilzeiten wird entschieden, welche Wartephase in einem gezielten Gegenversuch veraendert werden soll. Drei Basismessungen sind keine Dauerlauf- oder Worst-Case-Zertifizierung.

## Genaue Abfolge

Das eigenstaendige Werkzeug wird NICHT in den vorhandenen P300-Kandidaten kopiert. Es benoetigt weder den Stager noch einen neuen Upstream-Checkout. Beide bisherigen Laufzeitverzeichnisse bleiben unveraendert.

1. Einstellungen ohne Import per AST lesen; originale VS1-Produktion, genau einen konfigurierten Optolink-Port und `port_vitoconnect=None` verlangen. Alten aktiven CANARY und parallelen Handover-Versuch ablehnen.
2. Den zuvor aktiven Zustand der bekannten sieben Dienste/Timer sichern. Eine private Kopie des eigenen Skripts und Wiederherstellungsdaten anlegen.
3. Einen temporaeren, von Systemd ueberwachten Worker samt `ExecStopPost`-Wiederherstellung registrieren, BEVOR Produktion angehalten wird.
4. Zuvor aktive Zusatzdienste/Timer anhalten, den Splitter zuletzt. Wiederherstellungsabsicht jeweils VOR dem Stop persistieren. Der Port wird erst nach geprueftem Stop und geprueften offenen Deskriptoren exklusiv geoeffnet.
5. Konservativ nach VS1 synchronisieren, `20C2`, `0103` und den bekannten GFA-Block pruefen.
6. Genau **drei** Runden: frischer F7-Identitaetsread, Wechsel nach P300, zwei validierte virtuelle Identitaetsreads, Rueckweg ueber zwei ENQs, validierter F7-Identitaetsread und echter GFA-Block unter VS1.
7. Bei Fehler keine weiteren Messrunden. Abschliessend konservativen VS1-Link wiederherstellen, Software/P80 pruefen und seriellen Port schliessen.
8. `ExecStopPost` stellt die zuvor aktiven Dienste wieder her, den originalen Splitter zuerst. Dessen aktuelle Systemd-Invocation muss die Hauptschleife erreicht haben. Bei fehlerhaftem Splitterstart werden Writer NICHT blind gestartet. Wiederherstellungsfehler und Absichten bleiben erhalten.
9. Ueber den normalen MQTT-Debugclient nach Abschluss P80/P06 erneut pruefen. Der Helfer behauptet keine MQTT-Frische allein aufgrund eines laufenden Dienstes.

## Feste Lesegrenzen

| Protokoll | Zugriff | Zweck |
| --- | --- | --- |
| VS1/F7 | 00F8 / 2 | Controllerkennung, muss 20c2 sein |
| VS1/F7 | 778C / 2 | Software, muss 0103 sein |
| P300/01 | 00F8 / 2 | Controllerkennung, vollstaendige Framepruefung |
| P300/01 | 778C / 2 | Software, vollstaendige Framepruefung |
| VS1/6B | 4050 / 1 | P80, muss 20 sein |
| VS1/6B | 4006 / 1 | P06, Rohwert |
| VS1/6B | 4009 / 1 | P09, Rohwert |
| VS1/6B | 4057 / 1 | P87, Rohwert |

Hinzu kommen nur notwendige Protokollsteuerbytes EOT, Start/Sync und ACK. Die TX-Allowlist ist auf diese konkreten Bytes begrenzt; es gibt keine freie Adress-, Funktions- oder Rohtelegrammoption. Ein GFA-FF wird einmal nach 150 ms wiederholt, danach abgebrochen. Ein anderer P80-Wert wird nicht passend interpretiert.

**Kein C9, kein Physical_READ/WRITE, kein EEPROM, kein GFA_WRITE, kein Sollwert-, Schema- oder Serviceprogramm-Write.** Das gilt fuer vom Prober gesendete Geraetekommandos. Die gestoppten/gestarteten Produktionsdienste behalten ihre eigenen normalen Lebenszyklen; deshalb keinen Versuch waehrend einer aktiven Party-, Wartungs- oder Serviceprogrammoperation beginnen.

## Vorbereitung im bereits eingerichteten Optolink-LXC

Als root in der **Optolink-LXC**, nicht am Proxmox-Host. Der alte CANARY muss beendet sein; der zuletzt nachgewiesene VS1-Rollback ist die Ausgangsbasis. Waehrend der Messung keine Updates, keine zweite serielle Software, keine Bedien-/Schreibtests und keine gezielt ausgeloesten Heizungsprogramme.

Die normale MQTT-/HA-Telemetrie und die pausierten Zusatzdienste sind fuer das Testfenster unterbrochen. Der Prober ist kein Sicherheitsregler der Heizung und ersetzt keine interne Schutzfunktion.

Vor einer Wiederholung immer den aktuellen dokumentierten Teststand lesen. Fuer reproduzierbare Ausfuehrung einen geprueften Commit benutzen; keine lokalen Aenderungen mit Reset/Force ueberschreiben.

```bash
cd /root/p300-trial-work/project

git status --short
git fetch origin optolink-p300-migration
git merge --ff-only origin/optolink-p300-migration
git rev-parse HEAD
```

Bei lokalen Aenderungen oder fehlgeschlagenem Fast-forward abbrechen und nicht blind weitermachen. Die konkrete gepruefte SHA steht im zugehoerigen PR-Kommentar beziehungsweise in der Freigabe fuer diesen Basistest.

Zuerst die **neuen** Offline-Tests und den inerten Plan ausfuehren:

```bash
cd /root/p300-trial-work/project

/opt/optolink/venv/bin/python -m unittest discover \
  -s tests -p test_handover_probe.py -v

/opt/optolink/venv/bin/python tools/wb2a-handover-probe.py
```

Erwartung: 32 neue Tests erfolgreich und danach `PLAN ONLY`. Ohne `--execute` spricht der Prober weder Systemd noch den seriellen Port an. Der Plan benoetigt kein pyserial-Import; die echte Ausfuehrung nutzt pyserial aus der bestehenden Produktions-venv.

**Nicht** nochmals `optolink-stage-p300.py` aufrufen und **nicht** den alten `optolink-p300-trial.sh activate` verwenden. Eine Aktualisierung des bisherigen Kandidatenverzeichnisses ist fuer diesen Test unnoetig.

## Einmalige Ausfuehrung

Nur nach bestandenen Offline-Tests und ohne laufende Service-/Wartungsaktion:

```bash
/opt/optolink/venv/bin/python -u \
  /root/p300-trial-work/project/tools/wb2a-handover-probe.py --execute
```

Das Werkzeug meldet zuerst einen `SESSION=`-Pfad. `systemd-run --wait` wartet auf den Worker und dessen Wiederherstellung; die eigentlichen Messdaten werden am Ende kompakt ausgegeben. Dass waehrenddessen nicht jeder empfangene Bytewert live im Terminal steht, ist beabsichtigt: Ausgabe soll die Zeitmessung nicht dominieren.

Der Worker bekommt `RuntimeMaxSec=90`. Bei Ende, Fehler oder Abbruch wird `ExecStopPost` fuer den Wiederherstellungsversuch verwendet. `TimeoutStopSec=90` begrenzt zusaetzlich die Stop-/Aufraeumphase. **90 Sekunden sind keine Garantie fuer die gesamte Telemetrie-Ausfallzeit**: Stop-, Start- und Wiederherstellungsschritte kommen hinzu. Bei Systemd-/Kernel-/USB-Fehlern oder Stromverlust ist erfolgreiche Wiederherstellung nicht garantiert.

Die Systemd-Unit heisst nur fuer diesen Versuch:

```text
optolink-handover-probe.service
```

Es wird kein dauerhafter Dienst aktiviert und keine produktive Unit ueberschrieben. `--collect` raeumt die temporaere Unit nach Abschluss auf; die privaten Ergebnisdateien bleiben bestehen.

## Manuell abbrechen

Aus einer zweiten LXC-Konsole:

```bash
systemctl stop optolink-handover-probe.service
```

Der Stop beendet den Worker und fuehrt dessen `ExecStopPost` aus. Nach Ende kontrollieren:

```bash
systemctl show optolink-splitter.service \
  -p WorkingDirectory -p ActiveState -p SubState

journalctl -u optolink-splitter.service -n 60 --no-pager
```

Erwartung: `WorkingDirectory=/opt/optolink`, aktiver laufender Originaldienst und frische Hauptschleife. Der alte CANARY-Rollbackhelfer ist **nicht** der Abbruchmechanismus dieses neuen Workers.

Wenn die Wiederherstellung misslingt: erst sicherstellen, dass `optolink-handover-probe.service` nicht mehr laeuft und kein zweiter serieller Besitzer vorhanden ist. Dann den Originaldienst starten und Logs pruefen:

```bash
systemctl start optolink-splitter.service
journalctl -u optolink-splitter.service -n 80 --no-pager
```

Die wiederherzustellenden zuvor aktiven Zusatzdienste stehen in `state.json` unter dem ausgegebenen SESSION-Pfad; `recovery.json` protokolliert, welche tatsaechlich wieder gestartet wurden. Nicht pauschal alle optionalen Dienste einschalten. Die Dateien nicht loeschen, bevor die Wiederherstellung geklaert ist. Wiederholter Teststart ist keine Reparaturmassnahme.

## Unmittelbare Kontrolle nach Abschluss

Erst nach abgeschlossenem Prober, durch den normalen MQTT-basierten Client:

```bash
optolink-debug request 'gfaread;0x4050;1;raw;False' --timeout 8
optolink-debug request 'gfaread;0x4006;1;raw;False' --timeout 8
```

P80 muss mit Erfolgsstatus `1` und Wert `20` antworten. P06 ist zustandsabhaengig; `00` ist im Stillstand plausibel, `FF` kein gueltiger Drehzahlmesswert. Diese Reads bestaetigen Kommunikation, aber noch keine vollstaendige HA-/Schreibfunktionsparitaet. Zusaetzlich aktuelle HA-Sensorwerte und die wiederhergestellten Dienste kontrollieren.

## Ergebnisse lesen

Ein vollstaendig erfolgreicher Basistest endet mit:

```text
RESULT=PASS_READ_ONLY_BASELINE
```

Das bedeutet: drei gueltige Runden, gepruefte VS1-Linkwiederherstellung im Worker und erfolgreicher Dienst-Wiederherstellungsbericht. Es bedeutet NICHT, dass der Wechsel schnell genug fuer den Pumpen-Override ist.

Ergebnisordner:

```text
/root/p300-trial-work/handover-results/run-<UTC-Zeit>-<PID>/
  probe.py          unveraenderte lokale Kopie genau des getesteten Probers
  state.json        gepruefter Port, vorherige Dienstzustaende, Restore-Absichten
  measurement.json  Teilzeiten, GFA-Rohwerte, begrenzte TX/RX-Spur, Fehler
  recovery.json     erfolgreiche/fehlgeschlagene Wiederherstellung
```

Dateien sind root-privat (Ordner 0700, Dateien 0600). Es werden keine MQTT-Zugangsdaten kopiert. Auch bereinigte technische Betriebsdaten nur bewusst weitergeben.

| Messfeld pro Runde | Bedeutung |
| --- | --- |
| `p300.enq_ms` | Vom ersten EOT bis zur P300-Erkennungs-ENQ |
| `p300.start_ack_ms` | Von ENQ bis zum ACK auf 16 00 00 |
| `p300.device_id_ms` | P300-Identitaetsread samt Hostpruefung/Antwort-ACK |
| `p300.software_ms` | Zusaetzlicher gepruefter Software-Read |
| `vs1.first_enq_ms` | EOT bis zur ersten ENQ des Rueckwegs |
| `vs1.additional_enq_ms` | Zusaetzliche Wartezeit von der ersten zur zweiten ENQ |
| `vs1.identity_ms` | Anschliessender STX/F7-Identitaetsread |
| `roundtrip_to_vs1_id_ms` | Gesamter gemessener Hin-/Rueckweg bis zur VS1-Identitaet |
| `gfa_block_ms` | Anschliessender echter VS1-GFA-Block P80/P06/P09/P87 |
| `roundtrip_with_gfa_ms` | Gesamter Weg einschliesslich dieses GFA-Blocks |

Es gelten monotone **Hostzeitstempel**, keine direkt am optischen Signal gemessenen elektrischen Zeitpunkte. Software-RX, USB-Latenz und Scheduling bleiben enthalten. Der Prober verwendet 25-ms-Abstand und eine 10-ms-Restdatenpruefung; diese erscheinen in den gemessenen Datenphasen. Der zusaetzliche P300-Software-Read unterscheidet sich ebenfalls vom alten Helfer. Deshalb nicht ausschliesslich alte und neue Gesamtsummen vergleichen.

Die Setup-/Dienststopzeiten und der abschliessende Recovery-Schritt liegen ausserhalb der drei Runden. Rohzeitwerte im Fake-Peer sind synthetische Testdaten und KEINE WB2A-Messwerte. Es wird weder ein schneller erster ENQ vorausgesetzt noch die benoetigte zweite ENQ aus dem Ergebnis herausgerechnet.

## Abbruch- und Folgekriterien

Bei `FAIL_OR_NOT_VERIFIED`, falscher Identitaet, erneutem GFA-FF, Controller-Reject, ungueltigem Frame oder Restore-Fehler zuerst Report und Wiederherstellung pruefen. Keine unveraenderte Schleife starten.

Wenn alle drei Runden korrekt sind, entscheidet `vs1.additional_enq_ms` zusammen mit der Verteilung der uebrigen Zeiten ueber den naechsten gezielten Gegenversuch. Eine grosse zusaetzliche ENQ-Wartezeit motiviert eine gesondert vorbereitete Ein-ENQ-Variante, beweist aber noch nicht, dass man sie auf diesem Geraet gefahrlos ueberspringen kann.

Auch eine kuerzere mittlere Gesamtdauer reicht nicht zur Pumpenfreigabe. Fuer einen kuenftigen Hybrid-Manager ist die maximale Phase ohne P300-RAM-Zugriff einschliesslich GFA, Queue und Rueckwechsel relevant. Die asynchrone E7-RAM-Nachladung von etwa 2,1 Sekunden ist kein synchrones Schreibzeitfenster.

## Offline-Pruefung

`tests/test_handover_probe.py`: 32 Tests, darunter Fragmentierung, feste TX-Allowlist, drei warme Runden, beide ENQ-Phasen, fehlende ENQ, Identitaets-/Softwarefehler, GFA-FF, P300-Framefehler, Timeouts, Stop-Intention vor Aktion, selektive Restore-Reihenfolge und Abweisung einer aktiven Restartschleife als Readiness.

Die Tests verwenden einen synthetischen seriellen Peer und ersetzte Service-/Journalfunktionen. Sie sind kein realer Systemd-/USB-/Thermentest und simulieren nicht vollstaendig die WB2A-Firmware. Die bestehende P300-Suite bleibt separat erhalten. CI fuehrt ausschliesslich Offline-Tests und den inerten Plan aus, niemals `--execute`.

## Quellen

- [Direkte GFA-/VSKO-Quellenpruefung](p300-gfa-host-trace-2026-10-08.md)
- [Alter Latenzhelfer, Messgrenzen und Upstream-Vergleich](p300-switching-source-audit-2026-10-08.md)
- [Implementierung](../tools/wb2a-handover-probe.py)
- [Offline-Tests](../tests/test_handover_probe.py)
- systemd.service: https://man7.org/linux/man-pages/man5/systemd.service.5.html (ExecStopPost, RuntimeMaxSec, TimeoutStopSec; Systemd-Projektdokumentation)
- pyserial: https://pyserial.readthedocs.io/en/latest/pyserial_api.html (Timeouts, exklusives Oeffnen; allein keine Garantie gegen fremde Portbesitzer)
