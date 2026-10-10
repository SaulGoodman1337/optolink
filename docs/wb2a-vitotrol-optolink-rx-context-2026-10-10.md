# WB2A: historische UART1-RX-Korrelation / Speicherzuordnung (Optolink-only)

**Stand: 10.10.2026, vollständiger Offline-Audit zweier abgeschlossener P300-Archive.**
Keine produktiven Änderungen, keine neue P300-Lesesitzung, keine RAM-/SFR-Writes.
Der ausschließlich zulässige Forschungsweg ist **Optolink/P300 über den
vorhandenen originalen seriellen Besitzer**. Es wird kein Hardware-KM-Bus-Slave
gebaut oder benötigt.

## 1. Verifizierte, nicht atomare Speicheranordnung

In der realen VDensHO1 / WB2A, Kennung `20C2 / 0103`, liegen im vorhandenen
20-KiB-P300-RAM folgende belegte bzw. mögliche Komponenten:

```text
                  RAM (0x0400 bis 0x53FF)

0x161A  [KM-Bus-förmiger Master-TX-Puffer]   Verifiziert: DMA0-Quelle -> U1TB
          0x161A..163F                     Vorhandene, dynamische TX-Frames
0x1640  [00 00]                           Beobachtete, stabile Präfixbytes
0x1642  [00 01 B1 0A ... CRC16]             RX-Kandidat; gültiger Slave-Frame
0x164C  [FA 01 FB 01 22 D1]                Persistierte Restbytes
0x1652..1669 [00 .. 00]                   Im Audit unveränderter Zwischenbereich
0x166A  [06] / [0A]                       Kontextvariable unbekannter Bedeutung
0x166B  [00] / [04]                       Kontextvariable unbekannter Bedeutung
0x166C  [01]                              Im Audit konstantes Nachbarbyte

0x0B6D  [42 16 0A FE]                      79/79 konstantes 4-Byte-Muster;
                                           mögliches LE16-0x1642 + 0x0A,
                                           KEIN bewiesener Datenzeiger
```

Die gleichzeitige Existenz passender Bytes im RAM beweist **weder** das
UART1-RX-ISR-Ownership **noch**, dass irgendein P300-Schreibkommando diese
Kommunikation sicher aktualisiert. `0x0B6D` kann eine andere Konstante
oder eine anders interpretierte Datenstruktur sein.

Der Vorbefund über das M16C/62P-Registermodell bleibt: `U1RB` liegt bei
`0x03AE..0x03AF`, `S1RIC` bei `0x0054`, die relocatable Interrupttabelle
verwendet für UART1-RX/ACK1 den **Vektor 20**, also `INTB + 0x50..0x53`.
Der tatsächliche lokale `INTB`-Registerwert und der ISR-Code fehlen.
Weder Program-ROM noch eine Interrupttabelle wurde für 20C2 gesichert.
**Keine SFR-/UART1-RX-Registerreads am laufenden Heizgerät.**

Quellreferenzen:
- [M16C/62P Hardware Manual, Relocatable Vector Tables](https://docs.rs-online.com/a1c7/0900766b80a63c2a.pdf)
- [Historischer lokaler UART1/DMA0-TX-Nachweis](https://github.com/SaulGoodman1337/optolink/blob/optolink-p300-migration/docs/p300-uart1-dma0-natural-cycle-2026-10-08.md)
- [KM-Bus-Protokoll und geräteabhängige Rollen](https://github.com/openv/openv/wiki/KM-Bus)

## 2. Neue Statuskorrelation im vollständigen 20-KiB-RAM

**Archiv:** `p300-fullram-run-20261009T083607Z-144293-bundle.tar.gz`
SHA256: `94d5842b6dc5759ecb446a4c617b60b72873b639885d116032f783abdef8431c`.
Das Audit validiert alle 79 vollständigen Images samt Einzeldatei-Hashes,
20C2/0103, Abmessungen, Scanrichtung und die Rahmen-CRC.

| RX bei `0x1642` (10 Byte) | Nachbarbytes `0x166A..0x166C` | Voll-RAM-Aufnahmen |
| --- | --- | ---: |
| `00 01 B1 0A 01 01 10 FE 23 D8` | `06 00 01` | **78** |
| `00 01 B1 0A 01 01 00 00 43 53` | `0A 04 01` | **1** |

Diese **perfekte Kookkurrenz in 79 nicht atomaren Samples** ist interessant,
aber der seltene Fall ist nur **eine** Beobachtung; es gibt weder eine
kontrollierte Manipulation noch Nachweise über die semantische Bedeutung
`0x166A/B`. Insbesondere sollte `06` nicht automatisch als empfangene
Paketlänge oder `04` als IRQ-Flag bezeichnet werden.

Weitere unabhängige Quellprüfung: `0x0B6D..0x0B70` enthält in allen 79
Aufnahmen genau `42 16 0A FE`. Das 16-Bit-LE-Präfix entspräche
`0x1642` und das nächste Byte `0x0A` der beobachteten Paketlänge.
**Beide Zuordnungen sind Kandidaten**, weder dereferenzierter Programmzeiger
noch durch Firmware-/Registeranalyse validierte Struktur.

## 3. Exakte Einzelread-Zeitstempel: Besonderheit Snapshot 64

**Neuer unabhängiger Vollabgleich:** Das archivierte `blocks.jsonl`
wurde gegen sein eigenes Manifest gehasht. Für Snapshot 64 wurden
alle **640/640** Block-Datensätze erfasst und die vier relevanten
FC03-Payloads unabhängig gegen das archivierte 20-KiB-RAM-Image
verglichen. Die Scanrichtung war **absteigend**.

| Ereignis | Zeitpunkt (UTC) | Abstand zur ersten Probe |
| --- | --- | ---: |
| `FC03 0x1660/32` – enthält `0A 04 01` | 10:51:48.837415 | 0 ms |
| `FC03 0x1640/32` – enthält ungewöhnlichen B1-RX-Frame | 10:51:48.998687 | **+161,270 ms** |
| `FC03 0x1620/32` – zweite Master-TX-Hälfte | 10:51:49.159565 | **+322,138 ms** |
| `FC03 0x1600/32` – erste Master-TX-Hälfte | 10:51:49.325124 | **+487,706 ms** |

**Ergebnis:** Statusbytes und RX-Frame waren in derselben RAM-Scanepisode,
jedoch keinesfalls zur selben Zeit ausgelesen. Der Master-TX-Puffer darf
nicht stillschweigend über zwei aufeinanderfolgende Reads zu einem
On-Wire-Telegramm zusammengefasst werden.

## 4. Master-/RX-Korrelation aus dem anderen Archiv

**Archiv:** `p300-deep-run-20261009T070505Z-130246-bundle.tar.gz`
SHA256: `f0f015032edb94459ff2259a81ef2b84bf23253570d91cc6ba658c8160f5c2af`.
Alle 295 vollständigen Deep-Runden mit `FC03 0x1640/32` wurden gegen die
zeitversetzt gelesenen TX-Teile `0x1600/32` und `0x1620/32` geprüft.

- **295/295 RX-Felder CRC16/Kermit-gültig** (294 gewöhnliche, 1 seltenes).
- **292/295** über die getrennten TX-RAM-Blöcke rekonstruierten
  Master-Pufferansichten besitzen eine gültige CRC. **3/295 nicht**.
  Das sind insbesondere **keine 3 bewiesenen fehlerhaften Drahtpakete**;
  der TX-DMA-Puffer kann sich zwischen den FC03-Lesevorgängen ändern.
- In genau zwei der 295 gemeinsamen RAM-Ansichten steht der
  Master-Header `01 00 31` (Einzelregister-Anfrage). Die
  zugehörigen Details unterscheiden sich:

| Deep-Runde | Zusammengesetzter Master-Puffer | CRC über zusammengesetzten TX | RX bei `0x1642` | Zeit `0x1600` → `0x1640` |
| --- | --- | --- | --- | ---: |
| **145** | `01 00 31 09 01 01 01 07 4E` | **UNGÜLTIG**, Residuum `0x8A40` | `00 01 B1 0A 01 01 00 00 43 53` | 484,499 ms |
| **1417** | `01 00 31 09 01 01 10 A6 EA` | **GÜLTIG**, Residuum `0x0000` | `00 01 B1 0A 01 01 10 FE 23 D8` | 491,131 ms |

Das ist die wichtige Korrektur zur ersten Explorationsnotiz:
**Der seltene RX-Frame in Runde 145 darf keinem verifizierten
vollständigen Master-Lesetelegramm zugeordnet werden.** Lediglich
Master-Header, Status und ein gültiger RX-Kandidatenframe liegen im
nahezu gleichen, aber nicht atomaren Fenster.

## 5. Negativtest: Kein Vitotrol-RX in den 79 RAM-Images

Jedes vollständige 20.480-Byte-Image wurde über den **gesamten
adressierbaren Inhalt**, nicht nur am Offset `0x1642`, nach
vollständigen KM-Bus-Slave-Frames mit diesen expliziten Kriterien geprüft:

```text
Zielklasse      00  (Regler)
Quellklasse     11  (Vitotrol)
Befehl          80, B1, B3 oder BF
Gesamtlänge     8..32 Bytes
Zielslot        1, 2 oder 3
Quelle-Subklasse 1
CRC16/Kermit    Residuum 0000
```

**Resultat: 0 gültige Vitotrol-Slaveframes in 79 × 20.480
archivierten RAM-Bytes.** Der Test enthält synthetische
**positive** und negative Gegenproben mit einem tatsächlich aus
fremder Original-Vitotrol-300-Aufzeichnung bekannten CRC-gültigen
`00 11 80 ...`-Frame. Keine false-positive Rahmen durch
andere UART-/Optolink-Nutzdaten.

Diese Feststellung beschränkt sich ausschließlich auf die gespeicherten
**nicht atomaren** RAM-Aufnahmen und die geprüften Rahmenformen.
Sie sagt **nicht**, dass nie eine Klasse-11-Antwort auf dem externen
KM-Bus stattgefunden hat. Ebenso wenig erlaubt sie, Klasse-11-Bytes
in SRAM zu schreiben oder einen Interrupt zu simulieren.

## 6. Reproduzierbarer Offline-Auditor

Quellcode:
`tools/wb2a-vitotrol-optolink-rx-context.py`.
Synthetische Fuzz-/Zeit-/CRC-/Tamper-Fixtures:
`tests/test_wb2a_vitotrol_rx_context.py`.

Der Auditor verwendet den bereits validierten Archiv-Auditor
`wb2a-vitotrol-optolink-rx-audit.py`, erzwingt beide
**gepinnten** SHA256-Archivhashes, verifiziert die eingebetteten
Manifest-Einzeldateien, klassifiziert die 79 vollständigen
RAM-Snapshots und die 295 Deep-Kontexte und prüft die genaue
Blöcke-Abfolge des seltenen Falles. Der 80. partielle Snapshot
wird ausgeschlossen. Er verwendet nur lokale, abgeschlossene
Dateien; alle Ergebnis-Flags für `physical_uart1_rx_verified`,
`controller_write_authorized` und `new_hardware_io` bleiben `false`.

```bash
cd /home/chatgpt-admin/optolink-vitotrol-rpm-20261010

sudo cat /root/p300-trial-work/research-bundles/p300-fullram-run-20261009T083607Z-144293-bundle.tar.gz \
  | python3 tools/wb2a-vitotrol-optolink-rx-context.py --kind fullram

sudo cat /root/p300-trial-work/research-bundles/p300-deep-run-20261009T070505Z-130246-bundle.tar.gz \
  | python3 tools/wb2a-vitotrol-optolink-rx-context.py --kind deep

python3 -m unittest discover -s tests -p 'test_wb2a_vitotrol_rx_context.py' -q
python3 -m unittest discover -s tests -p 'test_*.py' -q
```

Private Tar-/RAM-Rohdaten werden nicht in Git oder ins README übertragen.
Das Repo erhält ausschließlich den Auditor, kleine synthetische
Fixtures, aggregierte Fakten und Zeitstempel.

## 7. Konsequenz für die Optolink-only-Vitotrol-Emulation

**Beweisstand:** Der Regler stellt Master-Discovery-Frames für die
Vitotrol-Slots bereit und besitzt einen **stark begründeten**
Slave-RAM-Pufferkandidaten. Für Klasse `0x01` findet sich eine
variierende, CRC-gültige Antwort. Das stärkt den Ansatz, den
reglerinternen KM-Bus-Empfangspfad über Optolink zu charakterisieren.

**Fehlendes notwendiges Glied:** Nur der exakte 20C2-/0103-Firmware-
oder Vektor-/Parser-Nachweis kann zeigen, **welcher Code die Klasse-11-
Antworten akzeptiert**, wann der Controller Raumtemperatur und
Teilnehmer-Liveness übernimmt und ob überhaupt eine **bereits
existierende, abgesicherte Optolink-Funktion** für diesen Zustands-
übergang erreichbar ist. P300 `Physical_READ` allein ist dafür
nicht ausreichend.

Bis dahin **kein blindes `Physical_WRITE`**, keine Pseudo-UART1-RX-
Interrupts, keine `0x27A0=1`-Vitotrol-Aktivierung ohne echte
emulierte, bestätigte Slave-Funktion. Der vorhandene explizite
`0x1640/32`-On-Demand-Read bleibt lediglich eine prüfbare
spätere passive Beobachtungsoption mit originalem VS1-Recovery-
Schutz – **nicht ausgeführt während der RPM-v2-Aufnahme**.

**Verbindliche Architektur:** ausschließlich Optolink/P300,
keine externe KM-Bus-Hardware, kein neuer serieller Besitzer,
PR #52 weiterhin Draft.
