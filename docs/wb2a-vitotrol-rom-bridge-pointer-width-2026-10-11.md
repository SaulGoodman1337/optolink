# WB2A / VDensHO1 20C2: ROM-Zugriff und RX-nahe Zeigerformat-Pruefung

**11. Oktober 2026.** Forschungszweig Plan A / Vitotrol ueber bestehenden Optolink-Zugang. Die alternative Raumregelung (0x2321) bleibt pausiert. Dies ist eine **rein lesende/offline** Auswertung; weder ein Regler-Write noch ein Protokollwechsel oder ein produktiver Serviceeingriff erfolgte.

## 1. Quelle / Beweisschranke

- Originalarchiv: `/root/p300-trial-work/research-bundles/p300-fullram-run-20261009T083607Z-144293-bundle.tar.gz`
- SHA256: `94d5842b6dc5759ecb446a4c617b60b72873b639885d116032f783abdef8431c`.
- SHA-/Manifestgeprueft: 79 vollstaendige 20.480-Byte-SRAM-Abbilder, Bereich `0x0400..0x53FF`, WB2A `20C2/0103`.
- Die lokal liegende `s00080.partial.bin` ist *kein* attestiertes komplettes Bild und wurde nicht ausgewertet.
- Die urspruenglichen FC03-Lesebloecke wurden nacheinander statt atomar gelesen. Eine Gleichzeitigkeit von UART-Telegramm, Descriptor und ISR kann daher nicht abgeleitet werden.

## 2. Neu: 24-Bit-Lookalikes gegen 32-Bit-Kandidaten getestet

| SRAM-Position | Haeufigstes LE32-Rohwort | Anzahl | Mit 32-Bit-nullaufgefuelltem 20-Bit-Adressmuster kompatible Beobachtungen |
| --- | --- | ---: | ---: |
| `0x0B51` | `3F 20 0F 00` (0xF203F) | 75/79 | 75/79 |
| `0x0B55` | `B6 CB 0F 00` (0xFCBB6) | 75/79 | 75/79 |
| `0x0B5C` | `20 24 0F 00` (0xF2420) | 75/79 | 76/79 |
| `0x0B74` | `FF 23 0F 64` (LE24 0xF23FF) | 79/79 | 0/79 |
| `0x0B7E` | `F0 01 0E 64` (LE24 0xE01F0) | 79/79 | 0/79 |

Die Zaehlung rechts erfordert **gleichzeitig** viertes Byte `00` und den LE24-Wert im angenommenen `0xC0000..0xFFFFF`-ROM-Bereich. Sie behauptet nicht, dass der Wert tatsaechlich eine Funktion adressiert.

Die bereits historisch untersuchten UART0-/Scheduler-Anker `0x18F8` (`0xF5239`) und `0x1A7D` (`0xF5C28`) haben jeweils **79/79** nullaufgefuellte 32-Bit-Woerter. Damit besitzen `0x0B51`, `0x0B55` und `0x0B5C` ein **strukturell vergleichbares Kandidatenformat**; bei `0x0B74/0x0B7E` fehlt dieser vierte Nullbyte-Nachweis.

Die volatile Dreiergruppe weicht ausschliesslich in den Images **1, 41, 60 und 62** gemeinsam ab. In den Images **1 und 62** steht an `0x0B5C` die Folge `42 16 0A 00`, deren erste drei Bytes mit dem konstanten Descriptor `0x0B6D: 42 16 0A FE` uebereinstimmen. **Prefix-Echo 2/79** ist ein Hinweis auf ueberlappende/temporaere Kommunikationsstruktur oder Speicherwiederverwendung, kein Parser-Aufrufnachweis. `0x0B6B=0A` steht bei drei dieser vier Abweichungen, bei der vierten `01`; keine kausale Gleichsetzung mit UART-RX.

## 3. ROM-Bridge: was aus Quelle und Hardware folgt

- Die P300-Hostadresse ist regulär 16 Bit; der angenommene M30624-Programm-ROM-Bereich liegt dagegen bei `0xC0000..0xFFFFF`. Ein `Physical_READ 0xF000` adressiert **nicht automatisch** `0xF0000`.
- Ein passender ROM-Zugriff benoetigte einen belegten *separaten* 20-Bit-Adressuebermittler: Monitor, Page/Bank-Selector oder ROM-to-RAM-Copy.
- Der alte Host-Proxy `0xA400` (VitosorpAccessController) belegt nur einen Sekundaeradress-Mechanismus fuer **16 Bit**, keine 20-Bit-Flash-Bruecke der lokalen WB2A.
- Fuer `VDensHO1/20C2` wurden im gesicherten VitoSoft-Profil zuvor 581 Events/22 RPCs ohne nachgewiesenen ROM-, KM-RX- oder Codeausfuehrungsservice gefunden. Das ist **keine** Aussage ueber undokumentierte MCU-Firmwarefunktionen.
- Auf dem Renesas M16C/62P ist `INTB` ein **20-Bit-CPU-Register** und kein regulaer speicheradressiertes UART-/DMA-SFR. Die Vektoradresse `INTB + 0x50` liefert **ohne ausgelesenes INTB und ohne Programm-ROM** keine gueltige 20C2-UART1-ISR-Adresse. Auch ein intakter SRAM-Descriptor ersetzt keinen UART1-Interrupt.
- Die historisch nachgewiesene Lesbarkeit von M30612-Software ueber Optolink bezieht sich auf **Vitotronic 200 KW2** und dokumentiert den konkreten Mechanismus nicht; sie beweist diesen nicht fuer die WB2A.

Quellen: [Renesas M16C/62P Hardware Manual](https://www.renesas.com/en/document/mah/m16c62p-group-m16c62p-m16c62pt-hardware-manual); [OpenV: KM-Bus](https://github.com/openv/openv/wiki/KM-Bus); historische interne Berichte `firmware-optolink-readout-research-2026-09-25.md`, `firmware-20bit-bridge-static-2026-09-26.md` und `gwg-firmware-readout-deep-dive-2026-09-26.md`.

## 4. Neue lokale Firmwarequellen-Inventur

Zusaetzlich wurden **116 lokal vorhandene ZIP-Archive (3180 Member)** aus `/home/chatgpt-admin/research` und dem frueheren WB2A-Research-Checkout zentralverzeichnisbasiert nach typischen 110-350-KiB-ROM-Formaten und den Schluesselwoertern `M30612/M30624/20C2/VDensHO1` durchsucht: **0 Kandidaten, 0 ZIP-Lesefehler**. Ein Dateinamens-/Groessen-Audit ist kein Inhaltsbeweis: umbenannte, verschluesselte, verschachtelte oder anders abgelegte Images werden damit nicht ausgeschlossen. Eine nachweislich zur eigenen `20C2/0103` passende Programm-ROM-Quelle wurde **nicht** gefunden.

## 5. Software-/Teststand

Die bestehende `tools/wb2a-vitotrol-near-rx-rom-candidates.py` wurde um LE32-Rohworthaeufigkeiten, streng gezaehlte nullaufgefuellte ROM-Bereich-Kandidaten und den genau gezaehlten RX-Descriptor-Prefix-Echo erweitert. Tests in `tests/test_wb2a_vitotrol_near_rx_rom_candidates.py` pruefen diese Felder und negative synthetische Gegenbeispiele.

- **10/10** gezielte Tests als root mit SHA-geprueftem privatem Originalarchiv: erfolgreich.
- **621 Tests** der gesamten Regression erfolgreich, **1 optionale Quelle** fuer den normalen User uebersprungen.
- Keine Controller-Operation durch die Auswertungssoftware, kein neuer serieller Besitzer, kein A0/B0-/UART-/IRQ-/RAM-Write.
- Echte Vitotrol: weiterhin **NICHT registriert** (`0x0A5C`-State-Commit fehlt).

## 6. Naechster technisch beweiskraeftiger Test

**Zuerst** eine authentische, zur `20C2/0103` zuordenbare Program-ROM-Quelle oder einen exakt belegten lesenden Optolink-Monitor/Selector/Copy-Service finden. Bei verfuegbarem ROM: die 5 vermuteten Codeziele und `INTB + 0x50` getrennt disassemblieren, nach Zugriff auf `0x1642`, `0x0B6D`, Klasse `0x11` sowie Teilnehmer-Commit/Kennung/Temperatur suchen. Ein echtes Empfangstelegramm muss den State-Commit von `0x0A5C`, `0x089C` und `0x0896` ausloesen. Erneute blinde FC04- oder UART-IRQ-Manipulation waere kein gueltiger Test.

Der unveraenderte produktive VS1-Splitter und der separate RPM-Logger sind ausserhalb dieses Forschungscheckout belassen.
