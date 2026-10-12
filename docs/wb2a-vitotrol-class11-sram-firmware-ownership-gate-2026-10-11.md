# WB2A 20C2/0103 – Class11 im gesamten RAM, Firmware-Schatten und UART1-RX-Owner

**11.10.2026, Stand nach 21:40 CEST.** Fortsetzung Plan A: echte Vitotrol 200/300 ausschließlich über Optolink. Keine externe KM-Bus-Hardware, keine UART-/DMA-/IRQ-/RAM-/A0-/B0-Schreibversuche. Raumregelungs-Plan pausiert. Die Heizung blieb während dieser Phase permanent in VS1 und der Single-Owner-Splitter wurde nicht verändert.

## 1. Originalquellen und strenge Grenzen

- **79 originale, vollständige, SHA/Manifest-geprüfte RAM-Abbilder**, je 20.480 Byte, physikalischer Bereich `0x0400..0x53FF`, archivierter Stand 09.10.2026. Vollarchiv-SHA256 `94d5842b6dc5759ecb446a4c617b60b72873b639885d116032f783abdef8431c`. Insgesamt **1.617.920 Bytes** erneut untersucht.
- **VitoSoft-XML** `DPDefinitions.xml` (186.559.004 Byte; SHA `efec27568d398021c767771af016143bd51fc196d2d408dbb80faff84d0b19e3`) und `ecnEventType.xml` (SHA `2338beb0e8544b6149bc4b2433ecabd9509edcdafc2e8e91f00182eba1aff7ba`) erneut exakt auf das Gerät `VDensHO1/20C2`, DatapointType-ID 60 gejoint.
- Unabhängige spätere reine FC03-Lesedaten am **11.10.2026** (beide SHA256-geprüften lokalen JSON-Quellen): `/tmp/wb2a-vitotrol-dual-readonly-live-20261011.json` SHA `e12a10b500cedbc41cc76e8b54ccba78eecc708c9c71f2e14075a25098bf393e`, `/tmp/wb2a-vitotrol-dual-readonly-high-live-20261011.json` SHA `c2896229323eba347620b225ac36263a04ac9b59f9e56d94589e68a6a72d7116`.
- Keine der Quellen ist ein Programm-ROM-Abbild oder eine elektrische KM-Bus-Drahtaufzeichnung. Alte vollständige RAM-Bilder bestehen selbst aus zeitversetzten FC03-Blöcken, nicht aus einer atomaren CPU-Speichersicherung.

## 2. Exhaustiver CRC-sensitiver Class11-Suchlauf (neue positive Gegenkontrolle)

Neuer Offline-Auditor: `tools/wb2a-vitotrol-class11-fullram-and-stability-audit.py`. In **jedem Byteoffset des gesamten RAMs** werden die beiden Header `00 01` und `00 11` gesucht. Anschließend müssen die Telegrammlängen `8..32` vollständig im ursprünglichen Speicherbild liegen und die **CRC16/Kermit über das ganze Telegramm** muss null sein. Anders als beim bisherigen `0x1642`-Only-Audit werden **beliebige** Opcode-Bytes und **alle RAM-Fundadressen** berücksichtigt. Die echten Original-V300-B1/PONG-Frames sind als synthetisch eingesetzte **Positivkontrollen** im Test vorhanden.

| Prüfmenge über alle 79 RAM-Snapshots | Klasse `0x01` | Klasse `0x11` (Vitotrol) |
| --- | ---: | ---: |
| Bloße Header `00 01` bzw. `00 11` | **5.920** | **184** |
| Kandidaten mit zulässiger Gesamtlänge 8–32 Byte | **549** | **20** |
| CRC-ungültige vollständige Kandidaten | **470** | **20** |
| **CRC-gültige ganze Telegramme** | **79** | **0** |

Alle **79** gültigen Klasse-01-Telegramme liegen **ausschließlich am Byteoffset `0x1642`**: 78× `00 01 B1 0A 01 01 10 FE 23 D8`, 1× `00 01 B1 0A 01 01 00 00 43 53`. Der gesamte RAM enthält bei diesen natürlichen Aufnahmen **keinen** einzigen CRC-validen Klasse-11-Restframe an einer anderen Adresse. Die Quelle enthält **keine** nachträglich per Preseed eingespritzten Klasse-11-Daten; frühere ausdrücklich aktive RAM-Preseed-Versuche sind separat dokumentiert.

**Grenze:** Die 79 Bilder erfassen nur bestimmte Zeitpunkte. Diese negative Aussage schließt eine kurzlebige Klasse-11-Nachricht zwischen P300-Abfragen oder einen gar nicht im RAM abgelegten Hardware-RX-Zustand **nicht** aus. Sie identifiziert auch noch keinen RX-Consumer oder IRQ.

## 3. Neues SRAM-Merkmal: 12.926 Byte vollständig stabile, hochentropische Endregion

Der gleiche SHA-geprüfte Bildvergleich ermittelte den **längsten vom RAM-Ende rückwärts vollständig unveränderten Bereich**:

| Eigenschaft | Beobachtung |
| --- | --- |
| CPU-Adressbereich | **`0x2182..0x53FF`** (einschließlich) |
| Konstante Länge über 79/79 Bilder | **12.926 Bytes** |
| Byte-Entropie im einen Originalbild | **7,86814 Bit/Byte** |
| One-Bit-Anteil | **0,518442** |
| Komprimierte Länge zlib Level 9 | **12.845 Bytes** (gegenüber 12.926 roh) |
| SHA256 der gesamten statischen Folge | `0c5bdb65afe5fa5576b71d30357e32398ed21f34fef37bd377dc19ec0653d862` |

Der Bereich ist nahezu nicht komprimierbar und enthält keine erkennbare, aus den vorliegenden Quellen belegte ROM- oder Interruptvektor-Adresszuordnung. Die bytegleiche Wiederholung über 79 Samples spricht für **Stabilität**, nicht automatisch für Programmcode. Er wäre ebenso mit ungenutztem/power-up-seitig bereits gefülltem RAM, unverändert initialisierten Tabellen oder einem bislang unbekannten Datenblock vereinbar. **Explizit kein Firmwaredump.**

Eine **unabhängige später erhobene** `FC03 0x3300/32`-Kopie am 11.10. in beiden o.g. JSON-Quellen war **jeweils 32/32 Bytes identisch** mit Original-Snapshot 1 vom 09.10. Beispielbytes `38361eccb44ddf8ef8efabb787fffe798728084823321183b9a6d4110e3e57cf`. Das bestätigt die Stabilität an dieser Teiladresse auch außerhalb des ursprünglichen 79er-Mitschnitts, nicht aber eine ROM-Abbildung oder einen 20-Bit-Programmzugriff.

Die bereits früher im kompletten RAM identifizierten Little-Endian-Literalstellen `6A 16` bei `0x2185` und `0x51A1` **liegen beide innerhalb dieser unveränderlichen hochentropischen Endregion**. Ein statischer Pointer kann grundsätzlich durchaus auf volatile RAM-Daten verweisen; jedoch lassen solche wiederkehrenden Bytepaare in einem hochentropischen Speicherbereich auch eine zufällige Übereinstimmung zu. Ohne Typ- oder Dereferenzierungsbeleg bleibt die Deutung offen. Es wurde **kein** Program-Code-Xref daraus abgeleitet.

## 4. Gerätgenauer VitoSoft-RPC-Check und P300-Wire-Grenze

Die exakt nach VDensHO1-ID 60 gefilterten **22 RPCs** bestehen aus **17× LON-Teilnehmerliste** (`0xA010`), **3× Reset** (`0xA050/0xA051`), **1× Fehlerhistorie löschen** (`0xA029`) und **1× LON-Mitgliederliste löschen** (`0xA009`). Die Host-Katalog-Adressen `0x1642`, `0x164C`, `0x166A`, `0x166B`, `0x0B6D` besitzen **keinen** exakten Eintrag in diesem Zielprofil. Ein belegter `Class11-RX-Inject`, ROM-Dump- oder UART1-Consumer-RPC fehlt.

Die allgemeinen VitoSoft-Kommandonamen `KMBUS_RAM_READ=65`, `KBUS_TRANSPARENT_READ=85`, `KBUS_DIRECT_READ=97`, `KBUS_INDIRECT_READ=99`, `KBUS_GATEWAY_READ=101` können nicht ungeprüft in spezifische WB2A-Services übersetzt werden: Der vorhandene VS2-P300-Hostdecoder interpretiert nur die **unteren fünf Funktionsbits** und die oberen drei Bits als **Sequenznummer**. Schon `FC99` und `FC03` teilen damit die unteren fünf Funktionsbits. Dieser Hostbefund sagt **nicht**, ob die MCU alle Kommandos identisch dispatcht; wegen der fehlenden Geräteprofil-Verknüpfung werden keine neuen mutmaßlich wirksamen KBUS-/Write-/Injected-Kommandos gesendet.

**Prozessorfamilie und Vector Gate:** Der offizielle [Renesas M16C/62P Hardware Guide](https://www.renesas.com/en/document/mah/m16c62p-group-m16c62p-m16c62pt-hardware-manual) dokumentiert den verschiebbaren Interrupttable-Base-Registerwert `INTB` und den UART1-RX-Vektor über `INTB + 0x50`. Die bisherigen UART1-SFR-Reads an unserer WB2A sind real, aber `INTB` und zugehöriger Code **wurden nicht ausgelesen**. Aus den bloßen Adressliteralen lässt sich daher noch keine echte RX-ISR bestimmen. Auch die konkrete Chipbestellnummer ist weiterhin nicht gesichert.

## 5. Priorisierter nächster Schritt – keine weitere gleichförmige P300-RAM-Abtastung

1. **Quelle eines 20-Bit-Programmabbilds oder eines nachweislich 20-Bit-fähigen Optolink-Monitors** aus echten Original-P300-Paketen, OEM-Tools oder Code gewinnen. Gewöhnliche 16-Bit-`FC03`-Reads können `0xC0000..0xFFFFF` nicht automatisch adressieren. Frühere FC99-/High-RAM-/DMA-Experimente belegen keinen ROM-Zugang. Ohne neue Quellbelege sind zufällige Adress-Sweeps nicht zielführend.
2. Erst nach einer **verifizierten echten 20C2-Codequelle** `INTB`/UART1 RX (unter Vorbehalt MCU-Mapping), `0x1642` und `0x166A/0x166B` mit der Parser- und Teilnehmer-Commit-Routine korrelieren. Die früheren Stände `0A04`, `0A07`, `0A08` und die beobachtete `0A08→0600`-Transition sind Zeitmarken, keine Einstiegspunkte.
3. Eine etwaige **Klasse-11-Emulation** erfordert einen realen Optolink-erreichbaren Eingang dieser Routine, korrekte Identitäts-/Watchdog-/Raumtemperaturzustände und überprüfbaren `SWIndex_FB1`-Commit. Die bekannten früheren Klasse11-B3-RAM-Preseeds erzeugten einen solchen Commit **nicht**. Bis zur Attribution keinerlei `0x166A/B`-, SFR-, IRQ- oder DMA-Schreibversuche.

**Akzeptanz:** Ein neuer Firmwarefund muss einen reproduzierbaren stabilen Program-ROM-Ausschnitt liefern, einschließlich nachvollziehbarer CPU-Adressabbildung oder Vektoren, nicht lediglich hohe Entropie oder RAM-Adress-Literalvorkommen. Ein Vitotrol-Nachweis muss Klasse-11-RX und Teilnehmer-Commit am **echten** Regler belegen. Beides ist aktuell offen.

## 6. Reproduzierbarkeit

```sh
cd /home/chatgpt-admin/optolink-vitotrol-rpm-20261010
sudo python3 tools/wb2a-vitotrol-class11-fullram-and-stability-audit.py \
  /root/p300-trial-work/research-bundles/p300-fullram-run-20261009T083607Z-144293-bundle.tar.gz \
  --output /tmp/wb2a-vitotrol-class11-exhaustive-fullram-audit-20261011.json
python3 -m unittest discover -s tests -p test_wb2a_vitotrol_class11_fullram_and_stability_audit.py -v
sudo python3 -m unittest discover -s tests -p test_wb2a_vitotrol_class11_fullram_and_stability_audit.py -v
```

Root-Originaltest überprüft die P300-Archiv-SHA, jedes Manifestmitglied, die positive 79er-RX-Kontrolle, alle Klasse11-CRC-Negativkandidaten, beide Metapaarzähler und den kompletten stabilen RAM-Tail. Alle privaten RAM-Rohdaten bleiben auf dem LXC. Dieser Lauf ist **rein offline**: `controller_io=0`, `controller_writes=0`.
