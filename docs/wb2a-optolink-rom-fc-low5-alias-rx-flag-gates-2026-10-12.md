# WB2A Plan A: native-P300 FC-Low5/Sequenz-Alias gegen RX-Flag-Kohärenz

**Stand: 12.10.2026, 08:27–08:54 CEST.** Regler: Vitodens WB2A, VDensHO1 **`20C2`**, SW `0103`. Ziel: echte Vitotrol 200/300 über den vorhandenen Optolink-Splitter als Klasse11-KM-Bus-Slave erscheinen lassen. Zentrale Frage: Gibt es über P300 einen **nachweislich separaten** KM-Bus-Empfangs-/Gateway-Service oder eine 20-Bit-ROM-Brücke? Diese Etappe beantwortet zwei konkrete überprüfbare Teilfragen, nicht die gesamte Firmwareauslesung.

## 1. Original-P300-Host: Nur 16-Bit-Anforderung und FC-Unterbits

Exakt geprüfter produktiver Serializer `/opt/optolink/optolinkvs2.py` SHA256 **`12f649b6b3f15f4c707eae932fdf5b22925afffb476136bf75af1306c5d0a815`**. Der 300-Host erzeugt `0x41 LEN 00 FC addr_hi addr_lo len CHKSUM`, gibt zwar **das volle Funktionsbyte** `FC` aus, serialisiert aber ausschließlich `(addr >> 8) & 0xFF` und `addr & 0xFF`. Der Empfangsdecoder teilt `FC` in `(FC & 0x1F)` und Sequenznummer `(FC >> 5)`.

Die bereits vorhandene und bis dato absichtlich **ungetrackte** Offlineanalyse `tools/wb2a-vitotrol-p300-wire-alias-audit.py` lief erfolgreich gegen den originalen produktiven Host. Ihre echten synthetischen Wire-Bytes:

```text
Native FC03 adress=0xF0000/16 -> 41 05 00 03 00 00 10 18
Native FC03 adress=0x0F000/16 -> 41 05 00 03 F0 00 10 08
```

Der scheinbare 20-Bit-`0xF0000`-Read wird somit in Wirklichkeit an `0x0000` adressiert; **kein** ROM-Bank- oder M16C-Codezugang. Funktion `0x63` (dezimal 99, hostseitig irreführend `KBUS_INDIRECT_READ`) hat dieselben unteren 5 Bits wie `0x03`; `0x65` (dezimal 101, `KBUS_GATEWAY_READ`) dieselben wie `0x05`. Die MCU könnte höhere Bits prinzipiell getrennt auswerten; ein Host-Quellkommentar reicht nicht, das Gegenteil zu beweisen.

## 2. Experiment: Direktes A/B und B/A der *realen* WB2A

**12.10.2026 ca. 08:52 CEST**, nativer P300 über den **originalen einzigen Optolink-Splitter**. Vor Beginn: durchgehender `20C2000300000103`-ID-Check, `0x27A0=00`, `0x27B0=00`, `0x7342=00`, Störung `0x5738=00`. Nur feste lese-freigegebene P300 `FC01`, `FC03`, `FC05`, `FC0x63`, `FC0x65`, maximal 8 Byte, keine weiteren Parameter/zusätzliche Nutzbytes. Je fünf A/B-Paare mit **umgekehrter B/A-Reihenfolge** wiederholt, danach erneute ID-/Codier-/Störungskontrollen.

| Prüffall | Normaler Read | Sequenz-betonte Variante | Identische Antwort für **A–B–B–A** |
| --- | --- | --- | --- |
| EEPROM/service `0x0000/8` | `FC05` | `FC0x65` | **`639c8d72cc336a95`** (4/4) |
| EEPROM/service `0x00F8/8` | `FC05` | `FC0x65` | **`00ff1de2bc436a95`** (4/4) |
| EEPROM/service `0x0017/2` | `FC05` | `FC0x65` | **`fc5e`** (4/4) |
| RAM-Descriptor `0x0B6D/4` | `FC03` | `FC0x63` | **`42160afe`** (4/4) |
| RAM-ROM-aehnliches Feld `0x0B74/4` | `FC03` | `FC0x63` | **`ff230f64`** (4/4) |

Resultat: **30/30 echte Controller-Leseantworten erfolgreich**, 5/5 Paare durch A/B/B/A **wiederholt bytegleich**, 0 Fehler, 0 Controller-Writes, FC0x63/65 unter diesen Bedingungen **nicht als unabhängig gewirkte RAM-, ROM- oder KM-Bus-Servicefunktionen erkennbar**. `0x0B74=FF 23 0F 64` ist ein RAM-Rohfeld, **nicht die Bytes des per LE24-Muster nahegelegten ROM-Ziels**. Keine Klasse11-Registrierung.

**Beweisgrenze:** Gleichheit der Rückgabebytes auf **fünf getesteten Parameterpaaren** kann keine universelle Gleichheit der Firmware-Dispatcher beweisen. Auch die genaue physikalische Herkunft der EEPROM/service-Antwortbytes bleibt unbestimmt. Die heutige `0x0017/2=` `FC5E` unterscheidet sich beispielsweise vom schon am **27.09.2026** dokumentierten `FC3A`. Ebenso differieren die zuvor als vermeintliche Gateway-Werte bezeichneten `FC0x65`-Bytes `0x0000/8` und `0x00F8/8` zwischen Beobachtungszeiten. Diese nicht zeitgleichen Werte dürfen **nicht** als Beweis verschiedener Dienste gelesen werden; für die 30 aktuellen P300-Werte wurde **nur innerhalb desselben Fensters** Gleichheit nachgewiesen.

### Originalbeweissicherung

Nur auf dem privaten LXC, nicht auf GitHub:
- Original-Hardwareaufzeichnung `/tmp/wb2a-vitotrol-p300-fc-alias-live-20261012.json` SHA256 **`877c7b70cfe687841c42d14fc716024597f4e6408a581197b02233574c9f7c16`**.
- Skript mit **festem 30-Read-Whitelist-Plan** `tools/wb2a-vitotrol-p300-fc-sequence-alias-readonly.py`.
- Eigenständige Root-/systemd-Absicherung `tools/wb2a-vitotrol-p300-fc-sequence-alias-session.sh`.
- Offline-Originalauditor `tools/wb2a-vitotrol-p300-fc-sequence-alias-original-audit.py` prüft **jeden** der 30 belegten Requests, alle Status-/Längen-/Funktions-/Seqbits-/Adressfelder, erwartete Rohbytes, beide Abfragerichtungen und SHA von Original-Live-Log und produktivem Serializer.
- Regressionen: `tests/test_wb2a_vitotrol_p300_fc_sequence_alias_readonly.py` + `tests/test_wb2a_vitotrol_p300_fc_sequence_alias_original_audit.py`, zusammen 12 gezielte Tests, darunter falsche Adresszuordnung, Error-/Diagnosebytes, fehlender unabhängiger Restore, andere Geräte-ID, veränderte Originalbytes und falsche Dispatcher-Schlüsse.

Die unabhängige P300-Rückstellung wurde **vor dem Protokollwechsel** mit einem 4-Minuten-Systemd-Timer aktiviert. Nach `EXIT_RESTORE` war der Timer **inaktiv**, `vs1protocol=True`, `settings_ini.py` SHA256 **`e9a120ef37fe17236a7505ee713c8dd338d98d5093ed75dfb34629d7e8f5c42d`**. `optolink-hybrid status = VS1_BETRIEB_OK`; alle fünf regulären Dienste aktiv. Keinerlei Controller-RAM/EEPROM/Heizcodier-, UART-SFR-, DMA-, Flash-, IRQ- oder Reset-Write.

## 3. Historische WB2A-RAM-Originale: Kann 0x0B6B RX-ready bedeuten?

Anderes unabhängiges Quellarchiv: `/root/p300-trial-work/research-bundles/p300-fullram-run-20261009T083607Z-144293-bundle.tar.gz` **SHA256 `94d5842b6dc5759ecb446a4c617b60b72873b639885d116032f783abdef8431c`**. Vor dem Ergebnis wurden Manifest, 79 originale **vollständige** 20.480-Byte-RAM-Abbilder `0x0400..0x53FF`, Gerät `20C2/0103` und alle internen Einzeldateihashes unabhängig erneut geprüft. `s00080.partial.bin` ist ausgeschlossen. Die 640 einzelnen FC03-Reads pro Bild sind **nicht atomar**.

**Bytekorrelationen am unveränderten Live-Geräte-SRAM aus früherer Langzeitmessung:**

| Feld | Normal | Anomalien / exakte Bildnummern | Relevanz |
| --- | --- | --- | --- |
| RX-Kandidat `0x1642/10` | `0001b10a010110fe23d8` 78/79 | **`0001b10a010100004353` in Bild 64**, CRC16/Kermit gültig | Gespeicherter Klasse01-Slave-Rahmen, nicht nachweislich physischer UART-RX |
| Nachbarstatus `0x166A..0x166C` | `060001` 78/79 | **`0a0401` in Bild 64** | 79/79 perfekte Bildzuordnung zu RX-Variante, aber **nur ein seltenes Positivereignis** |
| `0x0B6B` | `01` 72/79 | `0A` Bilder **1, 41, 62**; `0B` Bilder **26, 31, 33, 58** | 7/79 abnormale Zustände **ohne** seltene RX-Variante; bei seltenem RX-Bild **64 blieb `01`** |
| Gemeinsam volatile ROM-Zeiger-**Lookalikes** `0x0B51/55/5C` | `3f200f00 / b6cb0f00 / 20240f00` 75/79 | **1, 41, 60, 62** alle 3 gemeinsam anders, **0** partielle Abweichungen | `0B6B=0A` bei 3/4, `0B6B=01` bei Bild 60; Kookkurrenz, kein Codepointer-/ISR-Nachweis |
| Descriptor-Muster `0x0B6D` | `42 16 0A FE` | **79/79 unverändert** | `42 16` wäre LE16-Adresse `0x1642`; `0A` passt zur beobachteten Rahmenlänge, aber keine bestätigte Zeigertypisierung |

**Harter Negativbefund:** Falls man **`0x0B6B != 01` als „neuer RX-Frame bereit“** interpretierte, ergäben die 79 abgeschlossenen Aufnahmen **sieben Fehlalarme und null Treffer** für die einzige gespeicherte RX-Variante. Daher **`0x0B6B` keinesfalls als RX-Ready-Flag schreiben oder triggern**. Das schließt andere echte RX-Ereignisse zwischen den nichtatomaren Blöcken nicht aus.

Die Korrelation von `0x166A/B=0A04` mit dem seltenen RX-Frame zeigt einen höher priorisierten **Lesekontextkandidaten**, aber **keinen** belastbaren Beweis, dass diese Bytes ein Receiver-Status, ein UART1-Interrupt-Flag oder schreibbares DMA-/Queue-Ownership wären. `0x0B6D` ist ebenfalls **kein** sicherer dereferenzierbarer RX-Zeiger. Die richtige Klassifikation ist *unbestimmter RX-naher Kommunikationszustand im SRAM*, bis Firmware bzw. ISR/CPU-INTB eindeutig vorliegt.

Neuer rein lesender, lokal SHA-gepinnter Datenquellen-Auditor `tools/wb2a-vitotrol-rx-flag-coherence-original-audit.py` mit synthetischen Positiv-/Negativ-Fällen `tests/test_wb2a_vitotrol_rx_flag_coherence_original_audit.py`. **6 gezielte Tests; 5 PASS und 1 bei fehlendem privaten Root-Archiv regulär übersprungen**. Originalarchiv selbst wurde als root mit vollständiger Manifest-/CRC-Prüfung verarbeitet: **79/79 Bilder CRC-gültig**, genau ein spezieller Frame in Bild 64, sieben `0x0B6B`-Fehlalarme. Rohdaten ausschließlich privat auf dem LXC, Summenbericht `/tmp/wb2a-vitotrol-rx-flag-coherence-offline-20261012.json`.

## 4. Konsequenzen und weitere konkrete Arbeitsschritte

1. **Ausgeschlossen als *nachgewiesener* neuer Service:** Gewöhnliche FC99-„Indirect“- und FC101-„Gateway“-A/B-Paarungen an den getesteten Adressen. Auch die ehemaligen FC03-`0xF000/0xFFF0`-High-Werte `5497/5498` sind keine 20-Bit-ROM-Dumps. Künftige Tests unterscheiden immer **Wire-FC-Low5, Seq-High3, Originalantworten und zeitliche Vergleichbarkeit**.
2. **Nicht verwechseln:** Das echte P300-Startadress-Überlesen aus [dem 2013er OpenV-Gate](wb2a-openv-2013-p300-startgate-virtual-overread-2026-10-12.md) deckt nachweislich **Innenbytes bekannter virtueller Datenpunkte** ab. Es schafft **keine zusätzliche 20-Bit-Firmwarebank** und ersetzt keinen originalen Renesas-Program-ROM-Monitor.
3. **Neue RX-Priorisierung:** `0x166A/B` als passiven Kontextmarker dokumentieren, `0x0B6B` als *nicht für „RX-ready“ belegt* ausscheiden. Falls künftig weitere **passive** gleichzeitige Frames vorliegen, zuerst in unabhängigen über mehrere Ereignisse erfassten Quellen vergleichen; **keine** ISR-/RAM-SFR-Injektion auf Verdacht.
4. **Weiteres Plan-A-Firmwaregate:** Ein spezifisch zur **WB2A/20C2** gehörender historischer **20-Bit-Bank-/Monitor-/ROM→RAM-Copy-Aufruf** bzw. echter Code-/ROM-Dump. Der erhaltene Originaltext von KarlKoch (04.10.2010) dokumentiert 128-KiB-M30612MC-Software einer *anderen* Vitotronic 200KW2 über Optolink, ohne den tatsächlichen Leseaufruf. Seine alte `GWG C7`-ID-Kompatibilität wurde auf der WB2A schon bestätigt, ersetzt aber den **fehlenden 20-Bit-Service** nicht. Archivprüfung der früheren `openv.wiki`-Git-Datenbank zeigt keine als M30612-/ROM-Image benannte Gitdatei; das ist ein **negatives Dateipfad-Indiz**, keine absolute Ausschlussaussage über unbekannte/verschachtelte Dateien.
5. **Erst nach bewiesener Codequelle:** M16C/UART1-RX-Vektor via **tatsächlichem INTB** und verifizierter MCU-Variante disassemblieren; echte Klasse11-Frameneingänge, Teilnehmerindex `0x0A5C`, Sensorstatus `0x089C` und Raumtemp `0x0896` prüfen. Der Stand heute ist **keine angemeldete echte Vitotrol** und **kein 20-Bit-ROM-Abbild**.

### Offline reproduzieren

```bash
cd /home/chatgpt-admin/optolink-vitotrol-rpm-20261010

python3 tools/wb2a-vitotrol-p300-fc-sequence-alias-original-audit.py \
  --out /tmp/wb2a-vitotrol-p300-fc-alias-offline-audit-20261012.json

sudo python3 tools/wb2a-vitotrol-rx-flag-coherence-original-audit.py \
  --out /tmp/wb2a-vitotrol-rx-flag-coherence-offline-20261012.json

python3 -m unittest discover -s tests -q
```

Die neue Forschung bleibt im dedizierten **Draft-PR #52**, nicht in produktivem `main` oder `/opt/optolink`. Die beiden vorbestehenden lokalen und ungetrackten P300-FC-Alias-Tools wurden absichtlich nicht verändert oder hinzugefügt.
