# Live-A/B/A-Forschung WB2A: P300-KBUS-Gateway vs. angeforderte Vitotrol 300

**11.10.2026, 10:32–10:34 Uhr CEST**. Aktueller Quellzweig: `feat/wb2a-vitotrol-rpm-20261010`. Das Gerät wurde über seinen **ursprünglichen einen Optolink-Splitter** direkt im nativen P300-Modus getestet. Kein neuer serieller Besitzer, keine Shadow-Instanz, kein unbekannter KBUS_WRITE, keine manipulierten UART-SFRs.

## Forschungsfrage

Frühere aktive Tests bewiesen, dass `Physical_WRITE (FC04)` originale Vitotrol-300-Slave-Frames bei `0x1642` im WB2A-SRAM ablegen kann, ohne dass der Regler sie als UART1-Slave-RX verarbeitet. Können die **global in VitoSoft benannten und am Gerät bereits lesbaren** P300-Funktionen `KBUS_GATEWAY_READ=0x65` und `KBUS_INDIRECT_READ=0x63` bei korrekt angeforderter Vitotrol 300 (`A0=02,B0=03`) eine Empfangs-/Teilnehmer-State-Veränderung sichtbar machen?

Diese Frage wurde mit einer **Baseline A0:00/B0:00** und **zwei Testfenstern A0:02/B0:03** beantwortet. Beobachtung und Controllerwerte sind nicht zeitgleich/atomar abgetastet. Für das Ergebnis bedarf es deshalb übereinstimmender wiederholter Beobachtungen.

## Vorbedingungen

Vorab bestätigt: `A0=00`, `B0=00`, Fernbedienungstyp `0x7342=00`, aktuelle Störung `0x5738=00`, produktiver VS1-Hauptdienst aktiv. Originale `settings_ini.py` byteidentisch mit dem unabhängigen Recovery-Backup. Ein *vor dem Moduswechsel* aktivierter unabhängiger systemd-Restore-Timer war scharf; nach dem eigentlichen Experiment wurden A0/B0 durch das Testskript und die Dienste samt Original-Konfiguration nochmals durch den unabhängigen Restore-Prozess bestätigt.

Der vorbestehende passive RPM-Recorder `optolink-wb2a-rpm-passive-resume-20261011.service` wurde **nicht** beendet und blieb aktiv; bei nativem P300 können allerdings währenddessen die alten VS1-MQTT-Messwerte fehlen.

## Echte P300-Antwortmatrix

| Native P300-Leseoperation | Baseline A0:00 | A0:02 / B0:03 Fenster 1 | A0:02 / B0:03 Fenster 2 |
| --- | --- | --- | --- |
| `FC0x65 KBUS_GATEWAY_READ 0x0000/8` | `06f955aacb346a95` | **identisch** | **identisch** |
| `FC0x65 KBUS_GATEWAY_READ 0x00F8/8` | `00ffcb34b8476a95` | **identisch** | **identisch** |
| `FC0x63 KBUS_INDIRECT_READ 0x0000/2` | `ff00` | **identisch** | **identisch** |
| `FC0x03 Physical_READ 0x0B60/32` | `0x0B6D=42160afe` | **gesamte 32 Bytes identisch** | **gesamte 32 Bytes identisch** |
| `FC0x03 Physical_READ 0x1660/32` | `0x166A=060001` | **gesamte 32 Bytes identisch** | **gesamte 32 Bytes identisch** |
| `FC0x03 Physical_READ 0x161A/32` | Klasse01/`B1` | Klasse20/`B3` | Klasse01/`B1` |
| `Virtual_READ 0x0A5C/4` | `00000000` | `00000000` | `00000000` |
| `Virtual_READ 0x089C/1` | nicht abgerufen | `03` | `03` |

Alle aufgeführten FC03/FC0x63/FC0x65-Aufrufe meldeten Controller-Rückgabecode `1`. Nicht verifiziert wurde die Semantik des 8-Byte-Gateway-Payloads; die Tatsache, dass er gleich bleibt, beweist **nicht**, dass die Funktion prinzipiell niemals KM-Bus-Slave-Daten liefern könnte. Bewiesen ist nur: Die beiden **bereits akzeptierten** Parameterpaare enthalten in diesen beiden korrekt konfigurierten Zeitfenstern **keine verwertbare Vitotrol-Teilnehmer-Liveness-Änderung**. `Physical_READ` zeigte weiterhin natürliche Mastertelegramme, nicht den vollständigen On-Wire-KM-Bus.

## Replay und Negativtests

- Private vollständige, echte Aufzeichnung auf dem LXC: `/tmp/wb2a-vitotrol-gateway-diff-20261011.log`. Nicht nach GitHub übertragen.
- Neu: `tools/wb2a-vitotrol-p300-gateway-diff.py`: reiner Offline-Parser, zulässige FC-/Längen-/Adressformen, A0/B0-Write-/Rollbackbestätigung und zwei getrennte Reglerphasen. Er klassifiziert semantisch: unveränderter Gateway, unverändertes indirektes Reading, kein Softwareindex, kein gültiger Raumfühler, **kein bewiesener Firmware-RX-Commit**.
- Neu: `tests/test_wb2a_vitotrol_p300_gateway_diff.py`: synthetische vollständige/fehlerhafte Vergleichslogs, geänderte Gatewaydaten ohne falsche Acceptance-Folgerung, fehlende Rollbacks, doppeltes Sample, falsche P300-Länge und falscher Controller-Rückgabecode. Die echte private Originalaufzeichnung wird zusätzlich geprüft, wenn sie auf dem Testhost vorhanden ist.

## Wiederherstellung

Am 11.10. **10:34:10 Uhr CEST** waren über den originalen Splitter nach unabhängigem Restore bestätigt:

- A0: `00`, B0: `00`, Remote-Type: `00`.
- Softwareindex `0x0A5C=00000000`; aktueller Fehler `0x5738=00`.
- `vs1protocol=True` und der originale ausführbare Hauptdienst, `VS1_BETRIEB_OK`.
- Alle regulären Nebenservices aktiv; der fortgesetzte RPM-MQTT-Recorder weiterhin `active`.
- Der separate Timer wurde **erst nach dem erfolgreichen Restore** beendet.

Hinweis: Das ältere, transiente Recorder-Unit `optolink-wb2a-rpm-passive-20261010-v2.service` existiert nicht mehr. Das gespeicherte ältere Messmaterial blieb erhalten und der **neue** `...-resume-20261011.service` ist die tatsächlich aktive Folgeaufzeichnung. Der zuvor verwendete unabhängige Restore versucht weiterhin, die ältere Unit zu starten und protokolliert deswegen eine Warnung; der aktuelle RPM-Recorder bleibt davon unberührt.

## Konsequenz für die Weiterentwicklung

Das **ursprüngliche Softwareproblem** ist klar eingegrenzt: Der Regler erkennt seine echten `11 00 33...`-Discovery-Masterframes, und unsere native P300-Software kann dazu vollständig CRC-gültige Original-Vitotrol-Frames physisch in seinen SRAM-RX-Kandidaten schreiben. Aber weder diese RAM-Operation noch der erprobte `KBUS_GATEWAY_READ`-Ausschnitt aktiviert erkennbar die Teilnehmer-Liveness. Weitere bloße `A0:02/B0:03`-Wiederholungen werden dies wahrscheinlich nicht auflösen.

Nächster technischer Gate: Ein **belegter** aktiver KM-Bus-Receive-Dispatcher über Optolink/P300, eine verifizierte Firmware-KM-Bus-Queue oder die physisch gesendete Slaveantwort auf dem Bus. Die oft angenommene M16C/62P-UART1-ISR-Adresse ist mangels bestätigtem WB2A-CPU-Typ **keine** belastbare Schreibadresse. Ohne konkreten 20C2-ROM-/MCU-Beleg ist eine Simulation des RX-IRQ nicht durch planloses Setzen von SFR-Flags zu ersetzen.
