# WB2A 20C2 Vitotrol: optolink-only RX-Consumer und single-FC03-Fusionsfenster

**11. Oktober 2026, 19:59–20:08 CEST.** Forschung ausschliesslich über den vorhandenen Optolink-Splitter (keine Hardware, kein KM-Bus-Adapter, kein ESP32, kein Boot-Pin). Fernbedienungspriorität Vitotrol 200/300. Die Raumtemperatur-Alternative bleibt pausiert. Forschungs-PR #52 und `feat/wb2a-vitotrol-rpm-20261010`, `main` unberührt.

## 1. Gekapselte Live-Durchführung mit unabhängiger Rückstellung

Es wurden zwei voneinander getrennte, begrenzte, **ausschliesslich lesende** native-P300-Sitzungen ausgeführt. Keine Controller-`Physical_WRITE`-, `Virtual_WRITE`-, EEPROM-, DMA-, UART-, IRQ- oder Codierzugriffe.

- **Sitzung 1:** Beginn 19:59:14, Acht Zyklen, **57** erfolgreich bestätigte Read-Requests, eigentliche P300-Aufzeichnung **94,493 s**. `tools/wb2a-vitotrol-rx-burst-readonly.py` und `tools/wb2a-vitotrol-rx-burst-session.sh`. Das RX-/Meta-Readorder-Verfahren wechselte je Zyklus.
- **Sitzung 2:** Beginn 20:05:03, Acht Zyklen, **43** bestätigte Read-Requests, darunter **16 exakt 32-Byte-`FC03 0x164B/32`**. `tools/wb2a-vitotrol-fused-rx-window.py` und `tools/wb2a-vitotrol-fused-rx-session.sh`. Jede Runde: `0x164B/32`, `0x1640/32`, `0x1660/32`, `0x164B/32`. Zusätzlich Identität, Status und nachgelagert SWIndex/Sensor.
- **Beide Male:** vor der Umschaltung wurde per `systemd-run` ein **unabhängiger 4-Minuten-Restore-Timer** überprüfbar aktiviert, erst danach der exakt vorhandene serielle Owner für natives P300 temporär neu gestartet. `EXIT`-Restoration lief erfolgreich durch, unabhängiger Timer danach deaktiviert. Originalkonfiguration `vs1protocol = True`, SHA256 `e9a120ef37fe17236a7505ee713c8dd338d98d5093ed75dfb34629d7e8f5c42d` und produktive Dienste anschliessend unverändert. Postcheck `0x00F8=20C2000300000103`, `0x5738=00`; `optolink-hybrid status`: `VS1_BETRIEB_OK`, einzige serielle Verbindung ist der Splitter.
- Das alte Restore-Skript versuchte vorsorglich einen inzwischen nicht mehr vorhandenen **separaten** `optolink-wb2a-rpm-passive-resume-20261011.service` zu starten und protokollierte `WARNING_DEPENDENCY_START_FAILED`. Alle damals produktiven Splitter-/Party-/Schedule-/Service-/Maintenance-Units liefen korrekt wieder an, `ROLLBACK_OK`. Der RPM-Dienst war bereits vor diesen Sitzungen `not-found/inactive` und wurde nicht wiederhergestellt oder neu erstellt.

Private Rohdaten bleiben lokal auf dem Forschungs-LXC, **nicht** in Git:

| Quelle | Dateiname in `/tmp/` | SHA256 |
| --- | --- | --- |
| Live 1 | `wb2a-vitotrol-rx-burst-live-20261011.json` | `7d539f98f5861554bf325c981bae33d13263997f96bc7233d42f694b0f5de65f` |
| Live 2 | `wb2a-vitotrol-fused-rx-live-20261011.json` | `d22dfbc58cad99798be16aac9bf8b9c55598eeb35f25316b54690bffc5c3a258` |
| Historische 79 Bilder | `p300-fullram-run-20261009T083607Z-144293-bundle.tar.gz` (im privaten `/root/p300-trial-work/research-bundles/`) | `94d5842b6dc5759ecb446a4c617b60b72873b639885d116032f783abdef8431c` |

## 2. Ergebnis Live 1: natürliche B1-Varianten ohne generischen RX-Meta-Umschlag

Beide realen B1-Antworten sind `CRC16/Kermit`-gültig und stehen bei `0x1642` im bislang RX-artigen SRAM:

```text
5/8: 00 01 B1 0A 01 01 10 FE 23 D8
3/8: 00 01 B1 0A 01 01 10 00 D2 C6
```

Das natürliche `FE -> 00`-Umschalten findet zwischen Zyklen 4 und 5 statt. Gleichzeitig in den **zeitlich getrennten** Speicherreads:
- `0x166A..0x166C = 06 00 01` in **8/8**.
- `0x0B6D..0x0B70 = 42 16 0A FE` in **8/8**.
- `0x0B6B = 01` in **7/8**, `0B` erst in Zyklus 7. Keine nachgewiesene Auslösefolge.
- TX-Masterpuffer im jeweils separaten Block: CRC-gültiger `01 00 B1` in **7/8**, einmal `01 00 31`.
- `SWIndex 0x0A5C = 00000000` und `Raumsensor 0x089C = 03` in allen 8 Messrunden.

**Präzise zeitliche Grenze:** Das Medianintervall der *Mittelpunkte* von `FC03 0x1640/32` und `FC03 0x1660/32` betrug **1.698 ms (≈1,70 Sekunden)**; jede P300-Diagnoseanforderung braucht etwa 1,6–1,8 Sekunden. Die unmittelbare Host-Pause zwischen Requests von 0,02–0,11 ms ist **nicht** mit der zeitlichen Separation der controllerseitigen Speicherproben zu verwechseln. Der RX-Consumer/ISR könnte viel schneller reagieren.

**Folgerung:** `0x166A=06` ist **kein belegtes universelles „neuer Frame“-Flag**. Die normal verwendeten Klasse01-B1-Nutzwerte wechseln, ohne dass es sich verändert. `0x0B6D` bleibt eine statische, nur zeigerartig aussehende Struktur und kein verifizierter Receiver-Callback.

## 3. Neue Optolink-only-Idee: RX-Endbyte + Metadatenbyte in einem FC03-Read

Weil die **letzte** Stelle des zehnbyteigen RX-Frames bei `0x164B` liegt, das erste Metadatenbyte aber bei `0x166A`, ergibt sich diese **exakt 32 Byte breite** SRAM-Lücke:

```text
FC03 PhysREAD: Start 0x164B, Länge 32, Ende 0x166A
               |                                  |
               RX-CRC letztes Byte                Meta 0x166A
```

Das ist nicht die beliebige Vergrösserung auf 33–64 Bytes, die den nachgewiesenen 32-Byte-P300-Scratchbereich überschreiten könnte, sondern **ein normaler 32-Byte-Read** in bereits bekannten RAM-Adressen. Die Daten durchlaufen **denselben** Controller-Kopiervorgang; das ist noch keine vollständige CPU-/ISR-atomare Momentaufnahme.

## 4. Ergebnis Live 2: 16/16 fused-Window-Reads, seltenes Sonderpaar

| 32-Byte-Fenster `0x164B..0x166A` | Häufigkeit |
| --- | ---: |
| `C6 FA 01 FB 01 22 D1 [24×00] 06` | **15/16** |
| `53 FA 01 FB 01 22 D1 [24×00] 0A` | **1/16** |

Die vollständigen RX-Frame-Vergleichsreads in diesem Versuch enthielten **8/8** `00 01 B1 0A 01 01 10 00 D2 C6` (CRC gültig), die separaten Metadatenreads **8/8** `0x166A=06`. Nur der **späte Fusionsread in Zyklus 0** enthielt das seltene Paar `53|0A`. Der Voll-RX-Vergleich war wegen der dazwischenliegenden Aufrufe **nicht gleichzeitig**, deshalb konnte die komplette Sonderantwort nicht innerhalb derselben Probe bestätigt werden. `SWIndex=0`, `0x089C=03` nach der Sitzung, keine Vitotrol-Anmeldung.

Entscheidender zusätzlicher Test: Unter **allen 16 neuen 32-Byte-Fusionsreads** unterscheiden sich **nur zwei Bytepositionen** zwischen Normal- und Sonderfenster:

- `0x164B`: `C6` normal, `53` selten.
- `0x166A`: `06` normal, `0A` selten.
- Alle **30 Zwischenbytes** sind identisch. Die beiden Muster sind byteweise in einer einzelnen FC03-Response kopiert, nicht aus zwei Hostrequests zusammengesetzt.

## 5. Reproduktion über zwei unabhängige Messtage (SHA-attestiert)

Alle 79 historischen Images (20.480 Bytes, `0x0400..0x53FF`) wurden über gepinnte Archiv-SHA256 und manifeste Einzeldatei-Hashes überprüft. Exakt **ein** altes Sample, **Snapshot 64**, enthält das *gesamte* neue seltene 32-Byte-Fusionsfenster **bitidentisch**:

```text
53 FA 01 FB 01 22 D1 00 00 00 00 00 00 00 00 00
00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 0A
```

Der vollständige, aus den historischen RAM-Blöcken rekonstruierte Sonderframe lautet `00 01 B1 0A 01 01 00 00 43 53`, mit CRC16/Kermit-Residuum 0; sein benachbartes Triple bei `0x166A` ist `0A 04 01`. Dieser ältere Vergleich war **nicht atomar**, denn zwischen dessen `0x1660/32`- und `0x1640/32`-Read lagen ca. 161 ms. Die **neue** Einzel-FC03-Kopie bestätigt jetzt die früher getrennt gesehenen **zwei charakteristischen Bytes zeitnäher und in einem Block**.

Bei den 78 übrigen historischen Images gibt es das ältere normale Fusionsfenster `D8...06`. Die neuen 15 normalen Fusionsproben verwenden `C6...06`. Sie sind deshalb nicht vollständig byteidentisch mit den alten Normalsamples. Nur das seltene Fenster stimmt über die zwei Tage **32/32 Byte** überein.

Offline-Implementierungen:
- `tools/wb2a-vitotrol-rx-burst-audit.py`: strikter Zeitstempel-, RX-CRC-, Folgezustands- und Reply-Metadaten-Audit.
- `tools/wb2a-vitotrol-fused-rx-audit.py`: alle 43 Responses, 16 fused-Window-Copies, Positiv-/Negativvarianten, keine UART-Kausalität behauptet.
- `tools/wb2a-vitotrol-fused-rx-crossarchive.py`: zwingende SHA-Festlegung beider Originalquellen, Einzeldatei-Manifest und 32/32-Byte Crosscheck mit Snapshot 64.
- `tests/test_wb2a_vitotrol_rx_burst_readonly.py`, `tests/test_wb2a_vitotrol_rx_burst_audit.py`, `tests/test_wb2a_vitotrol_fused_rx_window.py`, `tests/test_wb2a_vitotrol_fused_rx_audit.py`, `tests/test_wb2a_vitotrol_fused_rx_crossarchive.py` mit gezielt erzwungenen falschen Antworten, verkehrtem Timing, unzulässigen Befehlen, längeren Datenblöcken und fehlendem Status.

**Abnahme:** Lokale Forschungs-Gesamtsuite: **716 Tests, 712 bestanden, 4 optionale (root-/private Quellen) übersprungen**. Der gezielte private Crossarchiv-Test als root: **4/4 bestanden**. Originale RAM-Captures werden nicht mit dem PR veröffentlicht.

## 6. Präzise neue Arbeitshypothese und nächste Optolink-Versuche

Belegt ist nun, dass die **Kombination** aus `0x164B` (Antwort-CRC-Endbyte) und `0x166A` (erster RX-Kontextwert) in einem einzigen FC03-Kopierfenster zeitlich zusammen beobachtet werden kann und seltene Muster über zwei Messtage wieder auftreten. **Eine Klasse11-Vitotrol-Antwort wurde dadurch nicht empfangen**. Wir kennen weiterhin nicht den tatsächlichen Controller-`UART1-RX`-ISR-/Parser-Aufruf, keine gültige RAM-Queue-Commit-Funktion und keinen echten 20-Bit-Programm-ROM-Read-Service.

Daraus folgen ohne weitere Befehlssuche diese nächsten Gates:

1. **Empfangsmetadaten semantisch auseinanderhalten:** `0x166A=06` umfasst beide normalen B1-Payloadvarianten `10 FE` und `10 00`, `0A` koexistiert mit dem Sonderpaar `...00 00 43 53`. Das spricht eher für frame-/verarbeitungsspezifische Metadaten als für ein universelles Receive-Ready-Flag; es ist noch kein Kausalitätsnachweis.
2. **Sonderantwort mit natürlichem Master-`0x31`-Kontext korrelieren:** Altes Deep-Event 145 hatte ungefähr gleichzeitig Master-Header `01 00 31` und den seltenen B1-Frame, aber die zusammengesetzte Master-CRC war wegen nicht-atomarer Reads nicht gültig. Das neue Fusionsfenster enthält keine TX-Daten; zunächst nur Offline-Korrelation und CRC-/Zeit-Attribution, **keine** Trigger- oder Übersteuerungswrites.
3. **Vitotrol-spezifischen Empfangspfad nachweisen:** Die bereits getestete direkte Klasse11/B3-RAM-Preseed-Injektion führte nicht zur Teilnehmeranmeldung. Ein weiterer RAM-Write an `0x166A` oder ein UART1-IRQ-Registerwrite ist **nicht** durch das aktuelle Ergebnis gerechtfertigt. Er würde Ursache und Effekt vermischen und könnte Kommunikation stören.
4. **ROM-Dump weiter nur über einen bestätigten Controller-Service** oder autonom sicher restaurierbaren Transport prüfen. Die belegten DMA0/1-Kanäle gehören KM-Bus bzw. Optolink und werden nicht experimentell umprogrammiert.

**Fazit:** Die Optolink-only-Passivforschung hat erstmals einen seltenen RX-/Metadaten-Koppelzustand über eine **einzige** FC03-Kopie mit einem historischen 32-Byte-Muster abgeglichen. Es ist ein echter neuer Beobachtungsanker für den Vitotrol-Parser, **noch keine Vitotrol-Emulation und kein ROM-Dump**.
