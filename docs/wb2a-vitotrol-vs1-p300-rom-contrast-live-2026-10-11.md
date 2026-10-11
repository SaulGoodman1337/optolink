# WB2A 20C2/0103 – neuer realer VS1/P300-ROM-Kontrast und zeitlich variable SRAM-Bytes

**11.10.2026, 21:55–21:58 CEST.** Ziel: eine bisher nicht belastbar verifizierte Adressraumgleichsetzung oder einen stabilen 20-Bit-ROM-Lesezugriff ausschließlich über das vorhandene Optolink zu identifizieren. Nur sichere, bekannte Virtual_READ-/P300 Physical_READ-Befehle, nie eine unbewiesene 20-Bit-/Monitor-/Write-Operation. Keine zusätzliche serielle Instanz oder KM-Bus-Hardware, keine UART-/DMA-/IRQ-/RAM-/Codierwrites. Die Raumtemperatur-Alternative bleibt pausiert.

## 1. Echte VS1-Testserie an produktiver WB2A

Um 21:55:18–21:55:36 CEST wurde mit **dem produktiven VS1-Splitter** über `optolink-debug request` eine begrenzte Serie von 13 festen **Virtual_READ**-Abfragen ausgeführt. Der Mitschnitt war CLI-Sitzungsausgabe; im Gegensatz zur untenstehenden P300-JSON existiert **keine separat SHA-gepinnte Original-VS1-Binärdatei**. Die Werte sind exakte unmittelbar protokollierte Beobachtungen, keine vom Archiv abgeleiteten Zahlen:

| Virtuelle VS1-Adresse | Read-Wert | Wiederholt |
| --- | --- | --- |
| `0x00F8/8` | `20C2000300000103` | zu Beginn und Ende |
| `0x5738/1` | `00` | zu Beginn und Ende |
| `0x3300/16` | **`FF040000FFFF14031419700101040000`** | 2/2 identisch |
| `0x2182/16` | `FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF` | 2/2 identisch |
| `0x1DE5/16` | `FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF` | 1/1 |
| `0xF000/8` | `FFFFFFFFFFFFFFFF` | 2/2 identisch |
| `0xFFF0/8` | `FFFFFFFFFFFFFFFF` | 2/2 identisch |

Die VitoSoft-XML-Daten, exakt auf Geräteprofil `VDensHO1/20C2` verknüpft (581 Ereignisse), **weisen `0x3300`, `0xF000` und `0x2182` nicht als ROM-Reader oder eigenes zielgebundenes Firmware-RPC aus**. Im globalen, *geräteübergreifenden* Katalog existieren zwar beispielsweise andere Gerätefunktionen bei `0x3300` und `0xF000`; das ist keine WB2A-Kompatibilitätszusage.

## 2. Passender echter nativer P300-Physical_READ-Vergleich

21:57:35 CEST unabhängigen **4-Minuten-systemd-Restore-Timer vorab aktiviert**, originalen einzigen Splitterprozess kurz gestoppt, unveränderte Host-Splitter-Installation im nativen P300-Modus gestartet, mit dem neuen fest whitelisted `tools/wb2a-vitotrol-rom-bridge-contrast-readonly.py` zweimal je fünf FC03-Adressen ausgelesen, Status/Codierung/Identität vor/nachher überprüft. **20/20** bestätigte Controller-Reads; Median **172,593 ms**, 0 Controllerwrites. Die fünf Produktivdienste und das ursprüngliche `vs1protocol=True` wurden um 21:57:48 CEST automatisch wiederhergestellt; unabhängiger Timer inaktiv, originaler SHA unverändert.

| Adresse | Native-P300-Physical_READ (zweimal identisch) | VS1-Virtual_READ gleiche Zahl |
| --- | --- | --- |
| `0x3300` | `38 36 1E CC B4 4D DF 8E F8 EF AB B7 87 FF FE 79 …` (32 Bytes) | `FF 04 00 00 FF FF 14 03 …` (16 Bytes) |
| `0x2182` | `16 E5 CB 6A 16 E5 16 E5 00 16 E5 00 BF B9 44 51` | 16× `FF` |
| `0x1DE5` | `AB A2 0E 01 33 00 1D 00 00 D0 C0 A1 C0 0F 00 02` | 16× `FF` |
| `0xF000` | `54 97 54 97 54 97 54 97` | 8× `FF` |
| `0xFFF0` | `54 98 54 98 54 98 54 98` | 8× `FF` |

**Interpretation:** 5/5 identisch nummerierte Adressen liefern im Virtual_READ- und Physical_READ-Pfad **verschiedene** Bytes. Die zwei Protokoll-/Adressräume sind nicht pauschal numerisch gleichzusetzen. Die high-16bit-FC03-Reads zeigen wiederholte Wörter `5497`/`5498`, aber **keinen nachgewiesenen** stabilen M16C-Programm-ROM-Code und erst recht keinen getrennten 20-Bit-Bankselector. Dass ein Wert in zwei direkt aufeinanderfolgenden Requests identisch ist, genügt für einen ROM-Nachweis nicht.

Private Original-P300-Quelle: `/tmp/wb2a-vitotrol-rom-contrast-p300-20261011.json`, SHA256 **`f5a31879fedf8c0af780f020c29e50c47cb7727c15e6305c955e6ae8f05935d1`**. Sie enthält alle 20 Einzelread-Antworten, zugehörige Befehle, Adressen, zeitliche Reihenfolge, Host-Monotonic-Timestamps, Geräte-ID, A0/B0/7342/5738 als 00, finalen Teilnehmerindex `00000000` und explizite `controller_writes=0`.

## 3. Wichtiger neuer Gegenbeleg zur angeblich unveränderlichen SRAM-Endregion

Der vorangegangene Original-FullRAM-Audit auf **79 vollständigen, SHA-/Manifest-verifizierten 20KiB-RAM-Abbildern vom 09.10.2026** hatte im Bereich `0x2182..0x53FF` **12.926 Bytes konstant in diesen 79 Bildern** gefunden. Der neue P300-Livetest zeigt nun bei `0x2182/16` eine **echte einzelne Differenz** gegenüber allen früheren Originalbildern:

| CPU-RAM-Adresse | Historische 79/79 Snapshots | Neuer P300 zweimal |
| --- | --- | --- |
| **`0x2184`** | **`C8`** | **`CB`** |

Die anderen 15 Bytes des unmittelbar geprüften 16-Byte-Fensters sind gleich geblieben. Das `0x3300/32`-Fenster ist weiterhin **32/32 bytes identisch** mit allen 79 Archivbildern; das `0x1DE5/16`-Fenster weiterhin **16/16 identisch**. Die früher formulierte Stabilitätsaussage bleibt **ausschließlich** auf die 79 damaligen Momentaufnahmen begrenzt. Eine regionsweite, über Tage garantierte Immutabilität ist anhand der neuen Evidenz widerlegt.

**Keine vorschnelle Erklärung:** Der `C8→CB`-Wechsel zeigt eine beobachtete Speicheränderung oder einen veränderten physical-read-Befund an genau einer Stelle; er beweist weder Firmware-Modifikation noch ISR-Beteiligung, Codekopie, Flash-Abbildung, bestimmte Temperaturbedeutung oder einen nutzbaren Dispatcher. Das statische Auftreten von 2-Byte-Adress-Literalen ist ebenfalls kein Xref-Beweis.

Der neue strikt **offline** prüfende Forensik-Auditor `tools/wb2a-vitotrol-optolink-rom-contrast-audit.py` verifiziert zugleich:

- SHA256 der **Live-P300-Originalquelle** `f5a31879fedf8c0af780f020c29e50c47cb7727c15e6305c955e6ae8f05935d1` und aller früheren Originalarchive mit FullRAM-SHA256 `94d5842b6dc5759ecb446a4c617b60b72873b639885d116032f783abdef8431c`;
- die **beiden** identischen, gültigen FC03-Reads für jedes der fünf festen Ziele, einschließlich exakter Länge/Adresse und originaler Statusguards;
- alle **79** durch das Originalmanifest gesicherten archivierten 16-Byte-Fenster bei `0x2182` sowie die 32-Byte-Fenster bei `0x3300` und die 16-Byte-Fenster bei `0x1DE5`;
- die einzige Veränderung im `0x2182`-Fenster exakt bei `0x2184` und Ausschluss der falschen Schlussfolgerungen `firmware_dump_obtained` oder `UART1_RX_parser_identified`.

Private maschinenlesbare Forensik liegt in `/tmp/wb2a-vitotrol-rom-contrast-forensic-20261011.json`; Original-Rohdaten bleiben ausschließlich im LXC. Die neuen synthetischen Positiv-/Negativtests verhindern freies FC-/Adressprobing, unbeschränkte Zyklen und ungültige Controller-Antworten. Das war ein bewusster Live-Lesetest, nicht nur eine Host-Paket-Simulation.

## 4. Gegenprüfung OpenV-Vorgeschichte und die tatsächliche nächste Chance

Historischer [OpenV-KM-Bus-Artikel](https://github.com/openv/openv/wiki/KM-Bus) erwähnt das **Auslesen von ungefähr 128 KiB Mask-ROM per Optolink** an **Vitotronic 200KW2 mit M30612MC**, jedoch **keine reproduzierbare Befehlssequenz** und keine bewiesene Übertragbarkeit auf den eigenen VDensHO1/20C2-Controller. Die bisherigen beiden vollständigen lokalen ROM-Monitor-Dossiers `firmware-optolink-readout-research-2026-09-25.md` und `gwg-firmware-readout-deep-dive-2026-09-26.md` schließen die gewöhnlichen 16-Bit-Reader, den Vitosorp-`0xA400`-Proxy (nur 16-Bit-Adresspayload), den FC99/FC03-Sequenzalias und die heute verfügbaren Public-Tool-Captures als **belegten** 20-Bit-Reader aus. Sie schließen **unbekannte** Firmwaremonitore nicht aus.

Technisch nächster echter Fortschritt: eine originale und der **WB2A 20C2/0103 zuordenbare** 20-Bit-Bank-/Monitor- oder ROM-zu-RAM-Copy-Semantik beschaffen. Vorher sind zusätzliche zufällige Virtual_READ-Hochadressblöcke, RAM-Preseeds oder Interrupt/DMA-Manipulationen nicht gerechtfertigt. Bei belegt sicherer, korrekt zugeordneter Bank wird zunächst ein winziger, mehrfach bestätigter ROM-Block unter Aufrechterhaltung des unabhängigen Restores angefragt. Erst nach echtem ROM-Befund M16C-RX-Vektor/Parser/Teilnehmer-Commit disassemblieren und echte Klasse11-Vitotrol-Vitotrol-Emulation über Optolink untersuchen.

**Status am Ende:** `VS1_BETRIEB_OK`, Geräte-ID `20c2000300000103`, Status `0x5738=00`, Vitotrol-Index `0x0A5C=00000000`, Konfigurations-SHA256 unverändert `e9a120ef37fe17236a7505ee713c8dd338d98d5093ed75dfb34629d7e8f5c42d`, alle fünf regulären produktiven Dienste aktiv, Restore-Timer inaktiv. Weiterhin kein Firmwaredump und keine angemeldete Vitotrol.
