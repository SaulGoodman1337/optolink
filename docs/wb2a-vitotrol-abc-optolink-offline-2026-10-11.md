# WB2A Vitotrol Optolink-only: Drei experimentelle Wege A/B/C

**Datum:** 11.10.2026, 19:20–19:30 CEST. **Heizung:** Vitodens WB2A, `VDensHO1 / 20C2 / 0103`. **Vorgabe:** keine neue Hardware, keine Platinen-/Boot-Pin-Arbeiten; aktuelle Aufgaben konzentrieren sich auf den Optolink-Diagnoseweg und die Vitotrol-Emulation. Die alternative Raumregelung `0x2321` bleibt ausgesetzt.

## 0. Nachweisstatus und produktiver Betrieb

Diese Runde hat **drei neue reine Offline-Programme** mit synthetischen Negativ-/Positivtests und den **originalen, SHA-gepinnten P300-Daten** implementiert. Kein neuer physischer UART-/DMA-/IRQ-Registerwrite, kein A0/B0-Write, kein KM-Bus-Slave-Frame-Write, keine zusätzliche serielle Verbindung und keine VS1/P300-Umschaltung.

Der echte VS1-Regler wurde vor dem Offline-Workflow **ausschließlich mit normalen Leseabfragen** überprüft:

```text
Virtual_READ 0x00F8/8 -> 20C2000300000103
Virtual_READ 0x27A0/1 -> 00
Virtual_READ 0x27B0/1 -> 00
Virtual_READ 0x5738/1 -> 00
Host-Datei /opt/optolink/settings_ini.py sha256:
e9a120ef37fe17236a7505ee713c8dd338d98d5093ed75dfb34629d7e8f5c42d
optolink-hybrid status: VS1_BETRIEB_OK
```

**Separater RPM-Recorder:** Beim abschließenden Systemd-Check war `optolink-wb2a-rpm-passive-20261010-v2.service` bereits **not-found/inactive**; der für 19:00 terminierte Stoppversuch scheiterte, weil dieser Unit-Name schon nicht mehr geladen war. Der Logger wurde von diesen A/B/C-Skripten weder verändert noch neu gestartet. Aussagen aus älteren Berichten, er sei weiterhin aktiv, beschreiben den damaligen Zustand, nicht den aktuellen. Das berührt nicht den aktiven produktiven Splitter.

## A: Natürlicher RX-Consumer / Vitotrol ohne ROM-Dump

**Quelldaten:**

- 79 vollständige, 20.480 Byte große RAM-Bilder (nicht atomare 32-Byte-P300-Blöcke), SHA256 `94d5842b6dc5759ecb446a4c617b60b72873b639885d116032f783abdef8431c`; manifest- und CRC-geprüft.
- 295 Deep-Kontexte, SHA256 `f0f015032edb94459ff2259a81ef2b84bf23253570d91cc6ba658c8160f5c2af`; blockweise prüfbare TX-/RX-Snapshots, nicht gleichzeitig.
- Zwei **bereits am Vormittag durchgeführte**, authentische Vitotrol-300-RAM-Preseed-Versuche (5 + 8 = 13 Snapshot-Zeitpunkte), originale JSONs mit SHA256 `ae5ae8bc80839a51800c5457e71b439f639665c911019e5415f15b9c2fcd0d32` und `5067e57033525811c258ac5c3152ce74b5df88e67f3b3551cfdb7e18fea14797`. **Die alten Preseed-Writes wurden nicht wiederholt.**

**Ergebnisse:**

| Merkmal | Offline-Messwert | Bedeutung |
| --- | --- | --- |
| Voll-RAM-RX bei `0x1642` | 78 normale Klasse01/B1, 1 Sonder-B1, **0 Klasse11** | Keine Vitotrol in den historischen natürlichen RAM-Frames |
| Deskriptor `0x0B6D` | `42160afe` **79/79** | Anhaltspunkt Pointer+Länge, **keine** nachgewiesene Queue-Struktur |
| Byte `0x0B6B` | `01`:72; `0A`:3; `0B`:4 | Ein möglicher Zustandscounter, noch ohne nachgewiesenen ISR-Consumer |
| Metadaten `0x166A..0x166C` | `060001` bei 78 RAM-Bildern; `0a0401` beim Sonder-B1 | Nur eine seltene Korrelation aus nicht-atomaren Daten |
| Deep-TX-CRC | 292 gültig, 3 wegen auseinanderliegender Reads nicht verifizierbar | Kein physikalischer KM-Bus-On-Wire-Beweis |
| **Zwei Preseed-Runs** | Anfangs originales CRC-valides Klasse11/B3 bei `0x1642`, nächster Read wieder Klasse01/B1 | Ein Schreiben in RAM allein erzeugt keinen von uns beobachteten RX-/Liveness-Commit |
| **Metadaten im unmittelbaren Preseed-Wechsel** | `060001 -> 060001` in **beiden** Versuchen | **Kein** beobachtetes ready/consumed-Signal in diesen drei Bytes |
| Zustand nach Preseed | `SWIndex_FB1=0`, keine akzeptierte Vitotrol | Kein wirksamer Dispatcher-Zugang entdeckt |

**Bedeutung:** Die Suche nach dem echten RX-Consumer bleibt sinnvoll. `0x166A/0x166B` dürfen aber nicht einfach als Queue-Ready-Flag behandelt oder geschrieben werden; die beobachtete B3→B1-Ersetzung änderte diese Metadaten nicht. `0x0B6B` bleibt ein Beobachtungskandidat, ist jedoch mit Masterstatus/speicherüberlappenden Vorgängen korreliert und **kein** bewiesener Receive-Ready-Trigger.

**Möglicher späterer Test:** Ein zeitlich enger, read-only P300-RX-Burst (`0x0B60`, `0x161A`, `0x1640`, `0x1660`, `S1RIC`) mit eigenständigem, vorher verifiziertem Restore und neuer Diensteinventur. Dieser neue Live-Burst wurde in **dieser** Runde **nicht** gestartet. Bis zum Nachweis des RX-Consumers keine RAM-/IRQ-Schreibaktionen.

Implementierung: `tools/wb2a-vitotrol-rx-consumer-offline.py`, `tests/test_wb2a_vitotrol_rx_consumer_offline.py`.

## B: 20-Bit-DMA-ROM-Quelle als rein synthetischer Transporttest

Die fünf bereits vorhandenen, SHA256 `d45c80d6c63786c67c6a9d338159fe409be8c0c8333d8aca0c0983181ead802f`-attestierten Hardware-SFR-Snapshots bleiben die Eingabe. Verifizierte echte Zuordnung:

| Channel | Source | Destination | Request | In 5 Samples DMAE=1 |
| --- | --- | --- | --- | --- |
| DMA0 / UART1-KM | `0x0161B/0x01621` | `0x003AA` (U1TB) | `0x0F` | 1 |
| DMA1 / UART0-Optolink | `0x019AF` | `0x003A2` (U0TB) | `0x0A` | 0 |

**Rein synthetische Simulation**, 16 Bytes aus dem *angenommenen* ROM-Quellfenster ab `0xF0000`, Beispielziel `0x3301` (nicht als freier Scratch-RAM bewiesen):

- Source-Inkrement / Destination-fix: **16** unterschiedliche ROM-Quellpositionen, aber **nur 1** RAM-Zielposition. Dort verbleibt der letzte synthetische Wert `0x02`.
- Source-fix / Destination-Inkrement: **1** Quellposition und **16** RAM-Zielpositionen, aber 16-mal dasselbe erste ROM-Byte.
- Beide Pointer-Inkremente gleichzeitig werden vom M16C/62P-DMA-Modell zurückgewiesen.

Die Hardware kann theoretisch mit 20-Bit-SAR auf internes ROM zugreifen. Das bedeutet **nicht**, dass wir einen sicheren, autonom rückstellbaren Transfer über P300 besitzen. Ein DMA0-Write kann KM-Bus-Slave-Kommunikation stören; DMA1-Write den **einzigen Optolink-Rückkanal** unterbrechen. Das Wiederherstellen nur der Host-Konfiguration reicht nicht, um einen überschriebenen Controller-DMA-Kanal zu reparieren.

**B-Gate:** Erst bei einem real belegten controllerseitigen Reservierungs-/Restore-Mechanismus, einem bestätigten konfliktfreien Zielpuffer und einem laufenden Optolink-Rückweg darf irgendein Live-DMA-Write erwogen werden. **Keine aktive DMA-Probe in dieser Runde.**

Implementierung: `tools/wb2a-vitotrol-dma-gated-simulator.py`, `tests/test_wb2a_vitotrol_dma_gated_simulator.py`.

## C: Neue substanzielle Korrektur – P300-Host maskiert FC und Adressbits

Hier liegt der wertvollste neue **quellcodeverifizierte** Befund.

Installierte Originalquelle `/opt/optolink/optolinkvs2.py`, SHA256 `12f649b6b3f15f4c707eae932fdf5b22925afffb476136bf75af1306c5d0a815`, Funktion `do_request`:

```python
outbuff[3] = fctcode & 0xff
outbuff[4] = (addr >> 8) & 0xff
outbuff[5] = addr & 0xff
outbuff[6] = rlen
```

`receive_telegr` teilt dasselbe Byte anschließend explizit in `msqn = (inbuff[3] & 0xe0) >> 5` und `fctcd = inbuff[3] & 0x1f` auf. Daraus folgt für die **Hostinterpretation**:

| Decimal-Name früherer Experimente | Request-FC-Byte | 5-Bit-FC | Sequenzbits | Hinweis |
| --- | --- | --- | --- | --- |
| `3` Physical_READ | `03` | `03` | 0 | Normaler Physical_READ |
| `99` sogenannter KBUS_INDIRECT_READ | `63` | `03` | 3 | Host-seitig **derselbe 5-Bit-FC** wie 3 |
| `5` EEPROM_READ | `05` | `05` | 0 | Normaler EEPROM_READ |
| `101` sogenannter KBUS_GATEWAY_READ | `65` | `05` | 3 | Host-seitig **derselbe 5-Bit-FC** wie 5 |

Dies ist **kein Beweis, dass der MCU-Dispatcher Sequenzbits ignoriert**, aber die zuvor dokumentierte FC03/FC99-Gegenüberstellung als zwei unabhängige RAM-/ROM-Lesedienste ist **nicht belastbar**. Unterschiedliche `0x54xx`-Werte an hohen FC03-/FC99-Adressen könnten aus zeitlich wechselnden internen Daten stammen; ein separater 20-Bit-Indirektdienst wurde nie nachgewiesen. Die 99/101-Namen in `optolinkvs2_switch.py` sind **auskommentierte Host-Code-Lexikoneinträge**, kein MCU-Funktionsbeweis.

**Noch wichtiger:** Die 20-Bit-ROM-Beispieladresse `0xF0000` wird im bestehenden Host-Serializer zu **`0x0000` abgeschnitten**. Rein offline erzeugtes exaktes VS2-Read-Telegramm:

```text
input FC03 addr 0xF0000 len 16 -> 41 05 00 03 00 00 10 18
input FC03 addr 0xF000  len 16 -> 41 05 00 03 F0 00 10 08
```

Das bedeutet: Durch Übergabe einer 20-Bit-Adresse an die bestehende `do_request`-Funktion entsteht **kein 20-Bit-ROM-Read**. Extra-Payload wird hostseitig zwar angehängt und in `payload length` berücksichtigt, ist aber controllerseitig **kein belegter 20-Bit-Bankselector**. Solche Requests werden ohne originale, geprüfte Protokollsemantik nicht am Kessel ausprobiert.

Implementierung: `tools/wb2a-vitotrol-p300-wire-alias-audit.py`, `tests/test_wb2a_vitotrol_p300_wire_alias_audit.py`. Der Auditor prüft die AST-Struktur der **genau SHA-gepinnten Originalquelle**, bildet Telegramme mitsamt Prüfsumme nur im lokalen RAM und öffnet keine serielle Verbindung.

## 4. Regression, private Ergebnisse und konkrete Fortsetzung

- **Neue Tests:** 9 A, 8 B, 8 C = **25 Testfälle**; sie decken ursprüngliche Hardwarequellen, CRC, Zeitfolge, Wire-FC-Sequenz-Aliasing, 16-Bit-Adressabschneidung und DMA-Grenzen ab.
- **Gesamtsuite** regulärer Forschungsuser: **689 Testfälle / 686 bestanden / 3 optionale private Datenzugriffe übersprungen**. Der gezielte A-Test mit root und allen attestierten Originaldaten: **9/9 bestanden**.
- Private Originaldaten verbleiben auf dem LXC, keine Controller-Trace-JSONs in GitHub:
  `/tmp/wb2a-vitotrol-path-a-rx-consumer-20261011.json`,
  `/tmp/wb2a-vitotrol-path-b-dma-model-20261011.json`,
  `/tmp/wb2a-vitotrol-path-c-wire-alias-20261011.json`.
- **Kein neuer ROM-Dump**, keine echte Vitotrol-Anmeldung und noch kein bestätigter interner RX-Consumer. Der ursprüngliche Scope bleibt **ausschließlich Optolink**.

**Nächste sinnvolle Gate-Abfolge ohne Wiederholungen:** (1) Den FC99/FC101-Host-Alias-Befund bei künftigen Berichten berücksichtigen, bevor „neue“ FC-Funktionen angenommen werden. (2) Nur mit abgesichertem, unabhängigen Restore gegebenenfalls einen kurzen rein lesenden P300-Statusburst zur zeitlichen `0x0B6B / 0x1642 / 0x166A`-Korrelation ausführen. (3) Keine RAM-Ready-, UART1-RX-, IRQ- oder DMA-Writes, solange Parser- und Restore-Semantik unklar sind. (4) Falls ein nachgewiesener ROM-Copy-Service auftaucht, zunächst genau ein reproduzierbares ROM-Wort lesen und mit M16C-Instruktion/Vektoren validieren.

Die Forschung liegt auf `feat/wb2a-vitotrol-rpm-20261010` / Draft-PR #52; `main` und produktive Anwendung wurden nicht verändert.
