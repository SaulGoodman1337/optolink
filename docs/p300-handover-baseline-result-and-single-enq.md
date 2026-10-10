# WB2A: Basismessung bestanden, gezielter Ein-ENQ-Vergleich

Stand: 2026-10-08. Branch: `optolink-p300-migration`. Keine Produktionsfreigabe.

**Belegstatus:** Zwei-ENQ-Basis vom Nutzer an der echten WB2A erfolgreich ausgefuehrt. Ein-ENQ-Vergleich in Prober 1.1.0 implementiert und offline getestet, auf der echten Anlage noch NICHT getestet. Kein neuer Zugriff auf Therme oder LXC durch den Autor. Kein Fork, kein Merge in `optolink-splitter-ha`, kein Installer-/Runtimewechsel.

## 1. Quelle und bestehende Grenzen

Nutzertranskript zur Session `run-20261008T092711Z-124106`, getesteter Commit `d0e16a607b1b473fa1f5e921623b244b3e8b97b5`, Prober 1.0.0. Die UTC-Zeit im Sessionnamen entspricht 11:27:11 CEST am 8. Oktober 2026. Systemd meldete 34,241 s Service-Laufzeit und Exitstatus 0; der Prober `PASS_READ_ONLY_BASELINE`.

Die drei Konsolen-Datensaetze und anschliessenden MQTT-Antworten sind in [evidence/p300-handover-baseline-2026-10-08.json](evidence/p300-handover-baseline-2026-10-08.json) erhalten. Das ist eine Abschrift der Nutzerkonsole, **kein importiertes originales measurement.json oder recovery.json**. Die bereits hinreichenden Erfolgsdaten werden nicht erneut angefordert.

Alle drei Runden enthielten P80=20 und P06/P09/P87=00. Nach Ende antwortete der normale MQTT-Debugclient erneut mit `1;0x4050;20` und `1;0x4006;00`. Damit ist die echte VS1-GFA-Kommunikation nach Wiederherstellung bestaetigt. Die Nullen sind gueltige Rohantworten, aber kein unabhaengiger Nachweis von Flammen-/Geblaesestillstand. Ein Test bei laufendem Brenner, ein Dauerlauf und vollstaendige HA-/WRITE-Paritaet sind damit nicht belegt.

Die in der Ausgabe der Offline-Tests enthaltenen simulierten Restore-Fehler gehoeren zu Negativtests und sind nicht Fehler des anschliessenden Hardwarelaufs.

## 2. Messergebnis

Alle Angaben in Millisekunden, berechnet aus den drei Konsolen-Datensaetzen. Min/Max sind nur Stichprobenextrema, keine Worst-Case-Garantie.

| Phase | Minimum | Mittelwert | Maximum |
| --- | ---: | ---: | ---: |
| P300: EOT bis ENQ | 1996,049 | 1997,551 | 1998,914 |
| P300: Start bis ACK | 12,963 | 13,372 | 14,139 |
| P300: Identitaetsread | 62,689 | 63,176 | 63,543 |
| P300: Softwareread | 87,632 | 87,962 | 88,614 |
| P300 gesamt | 2161,371 | 2162,061 | 2162,613 |
| VS1: EOT bis erste ENQ | 1997,494 | 1997,936 | 1998,777 |
| VS1: erste bis zweite ENQ | 2237,470 | 2237,679 | 2237,899 |
| VS1: Identitaetsread | 31,254 | 32,367 | 33,278 |
| VS1 gesamt | 4266,456 | 4267,982 | 4269,953 |
| GFA-Block | 393,924 | 432,843 | 493,812 |
| Hin-/Rueckweg bis VS1-ID | 6428,993 | 6430,137 | 6432,227 |
| Hin-/Rueckweg inklusive GFA | 6823,114 | 6862,980 | 6922,806 |

Rund 91 Prozent der gemessenen Gesamtzeit liegen in den drei ENQ-Wartephasen. Das nahezu konstante Zweit-ENQ-Intervall von 2,238 s ist jetzt separat gemessen; vorher war seine Dauer unbekannt.

### Gesichert, plausibel und noch offen

- **Gesichert:** Der konkrete EOT-basierte Ablauf wartet in jeder Richtung etwa 2 s auf die erste ENQ. Der Prober verwendet nichtblockierendes Lesen, 1-ms-Warten bei leerem Empfang, 25-ms-Abstand zwischen Datenanfragen und 10-ms-Restdatenpruefung. Keine feste 2-s-Hostpause wird hier abgearbeitet.
- **Plausible Deutung:** Die Regelung wartet auf einen Kommunikations-/Synchronisationszustand oder Timeout. Die Daten sind Hostzeitstempel einschliesslich USB/Kernel/Scheduling, kein Logic-Analyzer-Nachweis einer festen Firmwarekonstante.
- **Nicht bewiesen:** Dass diese 2 s mit jedem moeglichen, quellenbelegten Wechselablauf unvermeidbar sind. Ebenso wenig ist bewiesen, dass das zweite ENQ entfallen darf.
- **GFA:** Alle ausgegebenen Werte sind gueltig. Ohne vollstaendige Rohspur koennen einmalige, vom Prober tolerierte FF-Retries nicht ausgeschlossen werden. Deshalb keine Behauptung einer gemessenen FF-Rate von null.

### Rechenhypothese, keine neue Messung

Wenn ausschliesslich die zweite ENQ entfaellt und alle anderen Phasen unveraendert bleiben:

`6862,980 - 2237,679 = 4625,301 ms` im Mittel.

Die drei entsprechend berechneten Werte liegen zwischen 4585,447 und 4685,336 ms. Ein erfolgreicher Ein-ENQ-Einstieg allein wuerde daher voraussichtlich NICHT die ca. 2,1-s-E7-RAM-Nachladung beherrschbar machen. Der genaue RAM-Ausfallabschnitt eines zukuenftigen Hybridmanagers muss gesondert gemessen werden; er ist nicht identisch mit dieser gesamten Basismessung. Die Nachladung ist asynchron und keine garantierte Haltezeit nach einem Write.

## 3. Genau eine Veraenderung fuer den naechsten Versuch

Prober 1.1.0 ergaenzt `--single-enq`. Nur bei den drei gemessenen Rueckwegen sendet er den identischen STX/F7-Identitaetsread schon nach der ersten gueltigen ENQ, ohne zuvor auf eine zweite zu warten. Dieselben P300-Reads, GFA-Adressen, Laengen, Guards, Abstaende und drei Runden bleiben bestehen.

**Erstaufbau und abschliessende VS1-Linkwiederherstellung bleiben explizit Zwei-ENQ.** Es gibt keinen stillen Rueckfall innerhalb einer Messrunde: Wenn der Ein-ENQ-Read fehlschlaegt, gilt der Versuch als fehlgeschlagen, weitere Runden entfallen, und erst der getrennte Recovery-Pfad benutzt wieder zwei ENQs. Null in `additional_enq_ms` ist allein kein Erfolgsbeleg; Identitaet, GFA und Wiederherstellung muessen ebenfalls bestehen.

Die TX-Allowlist ist unveraendert. Es gibt keine freien Adressen/Frames, kein C9, kein 09-Ersatzkommando, keine EOT-Auslassung, kein RAM, keinen GFA-/Konfigurationswrite und keine Kesselcodierung. Die bekannte Aufsicht und selektive Wiederherstellung durch `ExecStopPost` bleiben bestehen. Der Prober ist kein Sicherheitsregler der Heizung.

**Quellenbegruendung:** Der gepinnte Upstream `optolinkvs1.py::init_protocol()` wartet nach EOT einmal auf ENQ und sendet dann einen STX/F7-Identitaetsread. OpenV beschreibt 01 als Bestaetigung auf 05 und Folgeanfragen ohne neues 01. Das begruendet den Gegenversuch, garantiert aber nicht seinen Erfolg auf dieser WB2A. Quellen unten.

## 4. Vorbereitung und Ausfuehrung im Optolink-LXC

Als root, nur bei funktionierendem originalen VS1-Splitter, ohne laufende Party-/Wartungs-/Serviceprogrammoperation. Waehrenddessen keine Updates oder Bedien-/Schreibversuche. Der serielle Adapter darf nicht von einem weiteren Prozess bedient werden. Die normale HA-/MQTT-Telemetrie wird erneut fuer das begrenzte Testfenster pausiert.

Den im zugehoerigen PR-Kommentar genannten **geprueften Commit** in den bestehenden Checkout uebernehmen; bei lokalen Aenderungen oder fehlgeschlagenem Fast-forward abbrechen. Kein Force/Reset, kein Neu-Klonen, kein Stager und kein alter CANARY. Weder `/opt/optolink` noch der bestehende P300-Kandidat muessen aktualisiert werden.

Nach dem Aktualisieren nur Offline-Tests und Plan:

```bash
cd /root/p300-trial-work/project
/opt/optolink/venv/bin/python -m unittest discover \
  -s tests -p 'test_handover*.py' -v
/opt/optolink/venv/bin/python tools/wb2a-handover-probe.py --single-enq
```

Erwartung: 42 Tests erfolgreich, danach `PLAN ONLY` mit `single-ENQ`. Ohne `--execute` keine Service-/Portoperation. Die alten 32 Basistests bleiben unveraendert; 10 neue Tests pruefen Opt-in, korrekte Antwort, fehlende zweite ENQ, gescheiterten Ein-ENQ-Einstieg ohne versteckten Fallback, konservative Wiederherstellung und Variantenuebergabe an den Worker.

Erst danach **einmal**:

```bash
/opt/optolink/venv/bin/python -u \
  /root/p300-trial-work/project/tools/wb2a-handover-probe.py \
  --execute --single-enq
```

Die Ausgabe muss die Variante `single-enq-comparison` ausweisen. Bei vollstaendigem Erfolg:

```text
RESULT=PASS_READ_ONLY_SINGLE_ENQ
```

In den drei Runden: `vs1.enq_count=1`, `vs1.additional_enq_ms=0`, gueltige Identitaeten/GFA. Erwarte nicht einen bestimmten Gesamtzeitwert als Pflichtkriterium. Die 4,6 s sind nur die vorherige Rechenhypothese.

Abbruch aus zweiter Konsole:

```bash
systemctl stop optolink-handover-probe.service
```

Das veranlasst die bestehende Aufraeum-/Wiederherstellungsroutine. Nicht den alten CANARY-Rollbackhelfer verwenden. Die Grenzen `RuntimeMaxSec=90` und `TimeoutStopSec=90` sind keine Garantie fuer erfolgreiche oder in 90 Sekunden abgeschlossene Wiederherstellung bei Systemd-/Kernel-/USB-/Stromfehlern.

Nach beendetem Worker:

```bash
systemctl show optolink-splitter.service \
  -p WorkingDirectory -p ActiveState -p SubState
optolink-debug request 'gfaread;0x4050;1;raw;False' --timeout 8
optolink-debug request 'gfaread;0x4006;1;raw;False' --timeout 8
```

Erwartung: Originaldienst `/opt/optolink` aktiv, P80 mit Status 1/Wert 20, P06 gueltig und zustandsabhaengig. HA-Frische und vorher aktive Zusatzdienste kontrollieren. Bei Fehler nicht erneut unveraendert starten; `measurement.json` und `recovery.json` unter dem SESSION-Pfad enthalten Details. Wenn Recovery misslingt, erst Workerende/Portfreiheit sicherstellen, dann Originaldienst starten und anhand des gesicherten Manifests nur zuvor aktive Zusatzdienste wiederherstellen.

## 5. Was danach entschieden wird

- **Ein-ENQ korrekt:** als lokal bestaetigte Optimierung aufnehmen; danach die verbleibenden EOT-bis-ENQ-Phasen quellenbasiert untersuchen. Keine ungepruefte EOT-Auslassung, kein automatischer Hochfrequenzbetrieb.
- **Ein-ENQ fehlerhaft:** beim gemessenen Zwei-ENQ-Ablauf bleiben, Spur auswerten; kein heimlicher Fallback als Erfolg deklarieren.
- **In beiden Faellen:** Pumpen-RAM-Override weiterhin nicht freigegeben. Native P300-GFA-Quelle oder autonom frischer RAM-Spiegel bleiben eigene offene Forschung. Keine GFA-Entities streichen und keine Cachewerte als frische Messung tarnen.

## Quellen und Reproduzierbarkeit

- [Nutzer-Konsolenmesswerte](evidence/p300-handover-baseline-2026-10-08.json)
- [Prober](../tools/wb2a-handover-probe.py), [unveraenderte Basistests](../tests/test_handover_probe.py), [Ein-ENQ-Tests](../tests/test_handover_single_enq.py)
- [Gepinnter Upstream, VS1](https://github.com/philippoo66/optolink-splitter/blob/c1ee204a1421447721603c5f21c6da7337fdac97/optolinkvs1.py)
- [OpenV KW-Protokoll](https://github.com/openv/openv/wiki/Protokoll-KW), am 2026-10-08 erneut gelesen
- [pySerial API, nichtblockierendes timeout=0](https://pyserial.readthedocs.io/en/latest/pyserial_api.html), am 2026-10-08 erneut gelesen
- [Direkte GFA-Hostquellenpruefung](p300-gfa-host-trace-2026-10-08.md), [Messgrenzen](p300-switching-source-audit-2026-10-08.md)

Offline-Tests pruefen synthetische Peers, keine vollstaendige WB2A-Firmware. Zehn neue Tests und 32 alte Tests bestanden lokal. Aktuelle CI-Resultate und Commitzuordnung werden im PR-Kommentar festgehalten. Die exakten Messdaten sind oben erhalten; alle kuenftigen Ein-ENQ-Zeiten muessen vom neuen echten Lauf stammen.
