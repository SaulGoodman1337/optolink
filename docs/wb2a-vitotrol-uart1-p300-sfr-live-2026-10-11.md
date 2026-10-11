# WB2A/20C2: echte M16C-UART1-Registermessung und ROM-nahe RX-Kandidaten

**11.10.2026, 14:09–14:17 CEST.** Optolink-only-Vitotrol-Emulation, realer Viessmann-Regler `VDensHO1 / 20C2 / 0103`. Dieser Nachtrag ist **kein** funktionierender KM-Bus-Slave und erhebt **keinen** Anspruch auf eine akzeptierte Vitotrol.

## 1. Ursprung der MCU-Zuordnung

Der exakte Chip-Laseraufdruck wurde in den bisherigen öffentlichen GG1/7187393-Fotos nicht gelesen. Es gibt aber **wesentlich mehr als eine bloße Fotovermutung**: Der **echte lokale Regler** gibt über nativen P300-`Physical_READ FC03` wiederholt SFR-/DMA-/UART-Daten heraus, die an mehreren voneinander unabhängigen M16C/62P-Registeradressen und -Werten mit dem Renesas-Handbuch übereinstimmen. Damit ist die M16C-UART1-Registerhypothese **direkt hardwarekorreliert**. Die exakte Verkaufs-/Maskenvariante des lokalen Chips folgt daraus allein nicht.

Renesas-Primärquelle: [M16C/62P Group Hardware Manual](https://www.renesas.com/en/document/mah/m16c62p-group-m16c62p-m16c62pt-hardware-manual), Kapitel Interrupts und UARTi. Die U1C1-Bits sind dort TE=b0, TI=b1, RE=b2, RI=b3. In S1RIC bilden b0..b2 die Interruptpriorität und b3 die Request-Flag; höhere Bits sind nicht zur Interpretation freigegeben.

## 2. Erster echter nativer P300-Hardwarelauf (14:10–14:11 Uhr)

Ein unabhängiger systemd-Restore-Timer wurde **vor** dem Protokollwechsel aktiviert. Nur der vorhandene Single-Owner-Splitter benutzte den Optolink-Port, in seinem **nativen P300-Modus**. Gerätesignatur `20c2000300000103` war erfolgreich auslesbar. Die Codierung wurde zunächst mit `A0/B0=00/00` gelesen, danach auf `A0=02/B0=03` gesetzt, dreimal zeitversetzt beobachtet und im Skript wieder `00/00` zurückgestellt.

| Wirklich gelesenes Register | Anfang A0:0/B0:0 | A0:2/B0:3 – Snapshot 1 | Snapshot 2 | Snapshot 3 |
| --- | --- | --- | --- | --- |
| `S1RIC 0x0054/1` | `40` | `41` | `41` | `41` |
| `U1C0/U1C1 0x03AC/2` | `1d03` | `1d07` | `1d07` | `1d07` |
| `U1MR/U1BRG 0x03A8/2` | `6598` | `6598` | `6598` | `6598` |
| `DMA0 SAR/DAR/TCR/CON 0x0020/16` | `1b160000aa0300000800000015000000` | `1b160000aa0300001400000015000000` | gleich | TCR `0800` |
| `SWIndex_FB1 Virtual_READ 0x0A5C/4` | `00000000` | `00000000` | `00000000` | `00000000` |
| `Sensorstatus Virtual_READ 0x089C/1` | nicht abgerufen | `03` | `03` | `03` |

Das ist **echte** UART1-Hardwarezustandsvariation, nicht nur die vorher schon geprüfte `0x1642`-RAM-Einspeisung. `U1C1 03 → 07` entspricht **RE ausgeschaltet → eingeschaltet**; `S1RIC 40 → 41` entspricht **IRQ-Priorität 0 → 1**. Der UART-Modus (`0x65`), Baudteiler (`0x98`) und DMA0-Ziel `U1TB=0x03AA` passen zum vorherigen realen UART1-Transmit-DMA-Nachweis.

**Beweisgrenze:** Die FC03-Abfragen erfolgten sequenziell, nicht atomar mit einem KM-Bus-Byte oder einem CPU-Interrupt. Insbesondere bedeutet das Auslesen von `RE=1` noch nicht, dass im Moment ein korrektes Slavebyte eingetroffen ist. `S1RIC`-IR und `U1C1`-RI (= Empfänger komplett) waren in diesen groben Schnappschüssen **nie als 1 beobachtet**; ein Mikrosekunden-/Milliksekundenereignis könnte zwischen den P300-Abfragen liegen.

## 3. Zweiter aktiver A0/B0-Differenzlauf (14:11–14:12 Uhr)

Um eine **falsche Kausalinterpretation** zu überprüfen, wurden die Einstellungen sofort und begrenzt in einer Serie variiert, ohne an UART-, DMA-, IRQ- oder RX-SFRs zu schreiben. Die aufeinanderfolgenden Momentaufnahmen:

| Codierungsphase | `S1RIC` | `U1C1` | RE | IRQ-Priorität |
| --- | --- | --- | --- | ---: |
| A0=0, B0=0, Start | `41` | `07` | ein | 1 |
| A0=1, B0=0, V200 | `41` | `07` | ein | 1 |
| A0=0, B0=0, zurück | `41` | `07` | ein | 1 |
| A0=2, B0=0, V300 | `41` | `03` | **aus** | 1 |
| A0=2, B0=3, Raumführung | `40` | `03` | **aus** | 0 |
| A0=2, B0=0, zurück | `41` | `07` | ein | 1 |
| A0=0, B0=0, Ende | `41` | `07` | ein | 1 |

**Wichtige Korrektur zum ersten Zeitfenster:** Beide Zustände (`03/40`, `07/41`) treten auch **ohne** Vitotrol beziehungsweise bei korrekt aktiver Vitotrol auf. Der Zustand korreliert daher **nicht eindeutig mit A0/B0**. Die Firmware verwaltet UART1-RE/Interruptpriorität offensichtlich auch aus dynamischen, noch nicht atomar gemessenen Kommunikationsbedingungen. Eine angeblich exklusive `A0`-Aktivierung wird ausdrücklich **nicht** behauptet.

Unsere stärkste aktuelle technische Arbeitshypothese ist eine *zeitfenster- oder zustandsabhängige* UART1-Empfangsroutine. Die bekannten originalen V300-Slaveframes nach `Physical_WRITE 0x1642` sind SRAM-Bytes, **keine** durch echte UART1-Hardware empfangenen Daten; deshalb fehlt die echte Parser-/Teilnehmer-Zustandsübernahme.

## 4. INT-Instruktion ≠ manipulierbares Interrupt-Flag

Das M16C-Handbuch beschreibt zwei relevante Mechanismen:

1. Das `S1RIC`-Interrupt-Request-Bit IR wird von der Peripherie gesetzt und darf **nicht durch Schreiben einer 1** erzwungen werden. Ein solcher Hardware-SFR-Versuch ist daher kein gültiger softwareseitiger Receive-Ersatz.
2. Der Prozessor kann per **`INT`-Maschineninstruktion** bestimmte Peripherie-Interrupt-Vektoren softwareseitig aufrufen. Dazu müsste **tatsächlich Code auf dem Controller ausgeführt** werden. Ein P300-`Physical_WRITE` auf einen RAM-Eingangsdatenpuffer führt diese Instruktion **nicht** aus. Außerdem verlangt die echte UART1-ISR möglicherweise Hardwaredaten aus `U1RB 0x03AE/03AF`, die kein bloßer `0x1642`-Schreibvorgang bereitstellt.

Der exakte, SHA-pinned VitoSoft-Hostkatalog `VDensHO1` enthält 581 Ereignisse, davon 22 RPCs (Konfig-Resets, LON-Listen, Fehlerhistorie), aber **keinen nachgewiesenen UART1-RX-Dispatcher- oder Codeausführungsdienst**. Eine anwendbare Software-`INT`-Einspeisung ist deshalb **noch kein** funktionierender Optolink-Weg. Es wurden **keine** SFR-/Programm-ROM-/Interrupt-Handler-Writes durchgeführt.

## 5. Neue Offline-Evidenz: 20-Bit-ROM-adressähnliche Werte neben RX

Das separate, schon archivierte vollständige 20-KiB-SRAM-Image wurde **79-mal** aus dem echten `20C2/0103` über P300 gewonnen. Die Bilder und das Quellenarchiv sind SHA256-attestiert: `94d5842b6dc5759ecb446a4c617b60b72873b639885d116032f783abdef8431c`. Alle 79 stammen aus **nicht atomaren** historischen FC03-Blockserien.

Neuer Audit `tools/wb2a-vitotrol-near-rx-rom-candidates.py` liest nur dieses gepinnte Archiv und interpretiert an festen, vorher festgelegten RAM-Adressen die jeweils ersten drei Bytes als Little-Endian-24-Bit-Zahl:

| RAM-Offset | Werte / Häufigkeit | Bedeutung |
| --- | --- | --- |
| `0x0B6D` | `42 16 0A FE`, **79/79** | Bereits bekannter möglicher RX-Deskriptor `0x1642` und Länge `0x0A` |
| `0x0B74` | `FF 23 0F` → **`0xF23FF`**, **79/79** | ROM-adressähnlich; nur 7 Byte nach RX-Deskriptor |
| `0x0B7E` | `F0 01 0E` → **`0xE01F0`**, **79/79** | Zweite ROM-adressähnliche Konstante unmittelbar daneben |
| `0x0B5C` | `0xF2420`, **75/79** | Dynamischere ROM-adressähnliche Nachbarstruktur |
| `0x1A7D` | `0xF5C28`, **79/79** | Vergleichswert aus dem bereits kartierten **Optolink/UART0**-Ring |
| `0x18F8` | `0xF5239`, **79/79** | Weitere Vergleichsstruktur, nicht als RX-Handler behauptet |

`0xF23FF` und `0xE01F0` liegen im für den angenommenen M30624 typischen Programmflashbereich `0xC0000..0xFFFFF`. Das ist ein **neuer forensischer Ansatz**, aber es ist **nicht** bewiesen, dass diese SRAM-Tripel wirklich Funktionsadressen, UART1-RX-ISR-Einsprünge oder ansteuerbare RX-Parserfunktionen sind. Der reale ROM-Code an diesen Zahlen ist nicht vorhanden. Es wurden keine Codezeiger geändert und kein Code über P300 gestartet.

## 6. Reproduzierbarkeit / Sicherheit / aktueller Zustand

Private komplette Livequellen bleiben ausschließlich auf dem LXC:

```text
/tmp/wb2a-vitotrol-uart1-readonly-20261011.log
/tmp/wb2a-vitotrol-uart1-a0-factor-20261011.log
/tmp/wb2a-vitotrol-uart1-sfr-summary-20261011.json
/tmp/wb2a-vitotrol-rom-looking-near-rx-20261011.json
```

Rein offline:

```bash
python3 tools/wb2a-vitotrol-p300-uart1-sfr-audit.py \
  /tmp/wb2a-vitotrol-uart1-readonly-20261011.log \
  /tmp/wb2a-vitotrol-uart1-a0-factor-20261011.log
sudo python3 tools/wb2a-vitotrol-near-rx-rom-candidates.py \
  --archive /root/p300-trial-work/research-bundles/p300-fullram-run-20261009T083607Z-144293-bundle.tar.gz
python3 -m unittest discover -s tests -p 'test_*.py' -q
```

Der aktive P300-Einsatz benutzte einen alleinigen Original-Splitter und einen vorab aktivierten unabhängigen Restore-Timer. **14:12:53 Uhr:** `A0/B0/Type=00/00/00`, aktueller Fehler `00`, Originaldienst `VS1_BETRIEB_OK`, passiver RPM-Recorder `active`, unabhängiger Timer nach Verifikation deaktiviert. Der Nutzerwunsch *P300 darf dauerhaft verwendet werden* bleibt unbestritten; die Rückstellung nach diesem Diagnosetest dient nur der unveränderten Betriebsfortführung.

Ein ergänzender A/B/A-Versuch an `Virtual_WRITE 0x2321` (externes Raumsoll) wurde **nicht ausgeführt**, weil die aktive Ausführung durch die Zugriffssicherung blockiert wurde. Der bereits vorbereitete unabhängige Rückstelltimer wurde ohne Controlleränderung wieder deaktiviert; `0x2321=00` und Störung `00` wurden anschließend bestätigt. Es gibt daher **noch keinen Live-Nachweis einer alternativen Raumtemperaturregelung**.

**Nächstes Engineering-Gate:** Zuordnung des 20C2-ROM-Inhalts und des dynamischen UART1-Scheduler-/RX-Queue-Dispatchers; nur über einen realen Code-/Dienstpfad kann ein rein optisch eingespeistes Telegramm ohne physisches UART-RX-Ereignis als Vitotrol gelten. Keine Verwechslung von einem statischen ROM-wertähnlichen Feld mit einer ohne Weiteres aufrufbaren Routine.
