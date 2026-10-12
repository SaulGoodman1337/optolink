# Echter Kompatibilitätsnachweis: V200KW2/GWG Originalbefehle an WB2A 20C2 über Optolink

**Datum:** 12. Oktober 2026, 07:17–07:22 CEST. Projekt Plan A: native, **nur optische** Vitotrol-200/300-Emulation an Vitodens WB2A mit VDensHO1 **20C2/0103**, ursprüngliche M16C-Programm-ROM-Auslesung als Forschungsziel. Zwei **echte, eng begrenzte** Hardwaretestfenster mit 16 ausdrücklich als Leseanforderungen dokumentierten Originalprotokoll-Telegrammen. **Kein Controller-RAM-, EEPROM-, UART-, DMA-, SFR-, Codierungs-, Modus- oder Programmspeicher-Write**; die seriell übertragenen `0x04`-Bytes sind lediglich Protokoll-EOT/Synchronisierung.

**Wichtigste Erkenntnis:** Es war zu pessimistisch, die alte GWG-KW2-Familie wegen des anderen M16C-MCU-Modells im Vorfeld auszuschließen. **Der exakte historische GWG-VIRTUAL_READ-Frame `01 C7 F8 04 04` funktioniert unverändert auf der echten WB2A**, liefert 2/2 die korrekte eigene `20C20003`-ID. Auch längere GWG-Lesefenster ab `0xF8` und verschobene ab `0xF9` funktionieren. Die alten **GWG-PHYSICAL-READ- und XRAM-READ-Frames `CB`/`C5` antworteten jedoch an den beiden geprüften 8-Bit-Adressen `0x6F` und `0xF8` nicht.** Damit ist weder allgemeine Unverträglichkeit der GWG-Familie noch ein vollständiger ROM-Dump belegt.

## 1. Originale historische Quellen und Quellunterscheidung

Die konkrete **V200KW2** hat laut [OpenV Issue #10, Original-Frage vom 01.11.2010](https://github.com/openv/openv/issues/10) auf `01 C7 F8 04 04` mit `20 98 00 02` geantwortet. In derselben Originaldiskussion beschreibt [vitoopen](https://github.com/openv/openv/issues/10#issuecomment-339370647) die **GWG-Geräteidentifikation als allgemein unterstützten Vorlauf** vor dem Wechsel auf KW/P300 (`voIdent`). Datumsangaben entstammen den ursprünglichen Wikispaces-Nachrichtenköpfen; GitHub `created_at=2017` ist nur das Importdatum. Beide Meldungen sind im SHA-pinned [V200KW2-GWG-Historiendossier](wb2a-vitotrol-200kw2-gwg-issue10-rom-gate-2026-10-12.md) verarbeitet.

Die ursprüngliche [OpenV-Dokumentation `Protokoll-GWG`](https://github.com/openv/openv/wiki/Protokoll-GWG) definiert exakt `01 <opcode> <8bit_addr> <count> 04` mit `C7`=Virtual Read, `CB`=Physical Read, `C5`=Physical XRAM Read und als physischen Lesebeispiel `01 CB 6F 01 04`. Die *zusätzlich* im zweiten Fenster verwendete `CB/F8`-Variante stammt aus einer [öffentlich erhaltenen GWG-VBEM-Konfiguration für Gerät 2053](https://community.viessmann.de/t5/Konnektivitaet/Optolink-GWG-Protokoll/m-p/510430): `01CBF80104`, dort als Systemidentifikation bezeichnet. **Dieser 2053-Konfigurationsbeleg ist kein V200KW2- oder WB2A-Funktionsnachweis**; deshalb wurde er gezielt hardwareseitig geprüft und sein negativer Befund nicht übergeneralisiert.

### Bytegenaue Baseline

Beide Fenster begannen und endeten mit demselben auf unserer WB2A seit Langem bestätigten **VS1/KW-Lesezugriff** auf `0x00F8/4`, wodurch Geräteidentität, synchrones Antwortverhalten und anschließender kontrollierter Rückweg bestätigt wurden:

```text
VS1/KW TX:   01 F7 00 F8 04
WB2A RX:     20 C2 00 03
```

Zusätzlich per unveränderter Produktiv-MQTT-Schnittstelle nach beiden Fenstern bestätigt: `read;0x00f8;8 = 20c2000300000103`, `read;0x5738;1 = 00`, `read;0x0a5c;4 = 00000000`.

## 2. Livefenster 1 – EXAKTE originalen C7-, CB- und C5-Befehle

**Zeit:** 07:17:23–07:17:40 CEST; unabhängiger 3-Minuten-Restore-Timer `wb2a-v200kw2-gwg-legacy-restore-20261012.timer` **vor** dem vorübergehenden Stoppen des einzigen produktiven Serial-Owners aktiviert. Direkter exklusiver CP2102-Zugriff mit **4800 Baud, 8-E-2**, vor jedem Frame `0x04 → 0x05`-Handshake, maximal 0,63 s Antwortfenster. Ausgeführt wurde nur die genaue, fest whitelisted Liste:

| Nummer | GWG/KW-Befehl (TX) | Echte WB2A-Antwort (RX) | Wiederholungen |
| --- | --- | --- | --- |
| 1 | `01 F7 00 F8 04` (KW-ID-Kontrolle) | `20 C2 00 03` | 1/1 |
| 2 | **`01 C7 F8 04 04`** (V200KW2 Original von 2010) | **`20 C2 00 03`** | **2/2 gleich** |
| 3 | `01 CB 6F 01 04` (GWG Physical Read Außentemperaturbeispiel) | **0 Bytes** | 2/2 |
| 4 | `01 C5 6F 01 04` (GWG XRAM Read, gleiche Adresse) | **0 Bytes** | 2/2 |
| 5 | `01 F7 00 F8 04` (KW-ID-Nachkontrolle) | `20 C2 00 03` | 1/1 |

**8/8 gültige 0x05-Synchronisierungen und 8/8 gesendete bekannte Leseanforderungen**, davon **vier nicht-leere Datenantworten**. Unterschied zwischen „keine Controllerantwort“ und „Gerätekennung 00“ wird sauber erfasst. Die zwei Nichtantworten pro altem CB/C5-Befehl können auf nicht unterstützte Opcodefamilien oder falsche Speicherkartierung bei **dieser einen Adresse** hindeuten. **Nicht** daraus schließen, CB/C5 seien an allen Adressen, mit allen Längen oder in jedem Zustand unmöglich.

SHA256 des unveränderten Originalmitschnitts `/tmp/wb2a-v200kw2-gwg-legacy-readonly-20261012.json`:
`37721acbbc7c503f6214f163142d4df2743f78ca8286ba8afbb8160ec6b652cf`.
Originale TX/RX-Reihenfolge und Codevarianten sind im strikt offline analysierenden `tools/wb2a-v200kw2-gwg-live-original-audit.py` fest verankert.

## 3. Livefenster 2 – Blocklänge, Adressoffset und alternative physische Adresse

**Zeit:** 07:21:41–07:21:59 CEST; eigener, zusätzlich unabhängiger 3-Minuten-Restore-Timer `wb2a-v200kw2-gwg-followup-restore-20261012.timer`; der Testclient verweigerte neue Hardwareabfragen ohne originalen, SHA-pinned **positiven ersten** C7-Originalmitschnitt. Derselbe einzelne exklusive CP2102-Port, dasselbe serielle Format, keine im Produktiv-Splitter persistent veränderte Funktionalität.

| TX | Echte WB2A-RX | Ergebnis |
| --- | --- | --- |
| `01 F7 00 F8 04` | `20 C2 00 03` | KW-Baseline bestanden |
| **`01 C7 F8 08 04`** | **`20 C2 00 03 00 00 01 03`** | **GWG-8-Byte-Block deckungsgleich mit KW `0x00F8/8`** |
| **`01 C7 F9 03 04`** | **`C2 00 03`** | **GWG-Adressinkrement auf `0xF9` funktioniert** |
| `01 CB F8 01 04` | **0 Bytes**, 2/2 | Alte **physische** ID-Abfrage nicht beantwortet |
| `01 C5 F8 01 04` | **0 Bytes**, 2/2 | Alte **XRAM**-Variante nicht beantwortet |
| `01 F7 00 F8 04` | `20 C2 00 03` | KW-Nachkontrolle bestanden |

**8/8 gültige 0x05-Synchronisierungen und 8/8 bekannte Leseanfragen, vier mit positiver Antwort**; bei beiden CB-/C5-Varianten keine Antwort. Das ist zusätzlicher Nachweis, dass die kompatible `C7`-Routine nicht lediglich einen einzigen vier Byte langen Identitätspaket-String zurückgibt: **Sie adressiert bei `F8` und `F9` tatsächlich die überlappenden virtuellen Datenbytes.**

Originalmessung `/tmp/wb2a-v200kw2-gwg-followup-20261012.json` SHA256:
`a9b6e5c846aacc99bc5183ffde922ef9891117e97872a278c35cec48520ad95d`. Gemeinsamer SHA-basiert validierender Offline-Auditor: `tools/wb2a-v200kw2-gwg-followup-original-audit.py`, erstellt `/tmp/wb2a-v200kw2-gwg-dual-forensic-20261012.json`. Er bestätigt die korrekte Reihenfolge und exakten Antworten **aller 16 Controller-Leseabfragen**, lehnt manipulierte Originale ab und bewahrt die Negativbefunde.

## 4. Technische Schlussfolgerung und konkrete verbleibende ROM-Barriere

### Nachgewiesene Interoperabilität

```text
           2010 echte V200KW2              2026 echte WB2A/20C2
           GWG 01 C7 F8 04 04      →       01 C7 F8 04 04
           ID: 20 98 00 02                 ID: 20 C2 00 03
                                          
           GWG-Virtual_READ 0xF8           GWG C7 0xF8/8 und 0xF9/3
                                          identisch zum KW/VS1-Datenfenster
```

Damit ist **ein gemeinsamer direkter Legacy-Optolink-Leseweg** jenseits bloßer Protokollähnlichkeit für die WB2A belegt. Die heute produktiv genutzte VS1-Implementierung kann GWG-Probes nicht ohne zusätzliche Synchronisierung anbieten; die zwei kurzen separaten Captures waren bewusst **keine parallel geöffneten seriellen Ports**.

### Nicht nachgewiesenes ROM-Gate

Die alten GWG-Requests benutzen nur **ein Adressbyte**. Dass `0xC7` an den Geräten identisch funktioniert, bedeutet **nicht**, dass er bereits eine 128-KiB-Programm-ROM-Adresse transportieren kann. `0xCB` (Physical Read) und `0xC5` (XRAM Read) hatten bei **`0x6F` und `0xF8`** keine Antwort, jeweils zweimal. Das ist ein Gegenbeleg für die ganz einfache Hypothese „beliebiger alter GWG-Physical-Read-Frame funktioniert 1:1 an jeder alten Adresse auf der WB2A“, **kein Ausschluss** eines verborgenen GWG-Receivers, spezieller Status-/Bank-Sequenz oder eines Controller-ROM-Kopierdienstes.

**Nächster echter Mehrwert:** Belegbare **mehrstufige** 2010er KarlKoch/GWG- oder Viessmann-Servicesequenz suchen, vor allem (1) `GWG`-Legacy-Frontend **plus** Bank-/Page-State, (2) controllerinterne ROM→LowRAM-Copy-Prozedur, (3) Multibyte-Selector via KW/P300 RPC an einem **20C2-verifizierten** Endpoint. Alte Originaltelegramme dafür nicht pauschal ausschließen. Sobald eine konkrete quellenbelegte sichere Lesefunktion vorliegt, ein kleines ROM-Fenster mehrfach prüfen, danach M16C-UART1-/KM-Bus-Parser und Vitotrol-Teilnehmer-Commit disassemblieren.

### Sicherheits- und Restore-Befund

- Beide Fenster: separater **vorab gestarteter** unabhängiger Systemd-Restore-Timer plus EXIT-Restore; Single-Owner und POSIX exklusiver USB-Seriell-Port; **0 Controller-Speicherwrites**.
- Zwischen und nach den Fenstern: `VS1_BETRIEB_OK`, `vs1protocol=True`, Konfigurations-SHA256 `e9a120ef37fe17236a7505ee713c8dd338d98d5093ed75dfb34629d7e8f5c42d`, alle fünf produktiven Dienste aktiv.
- Abschluss 07:18+ und 07:22+ CEST: Geräte-ID `20c2000300000103`, Fehler `5738=00`, Teilnehmerindex `0a5c=00000000` (erstes vollständiges Nachfenster); Restore-Timer wieder inaktiv.
- **Kein Firmwaredump**, **kein 20-Bit-ROM-Bankzugang**, **keine Vitotrol-Registrierung**. `main` unverändert, Forschung ausschließlich PR #52.

## 5. Wiederholbare Prüfprogramme

```sh
cd /home/chatgpt-admin/optolink-vitotrol-rpm-20261010
python3 tools/wb2a-v200kw2-gwg-live-original-audit.py \
  /tmp/wb2a-v200kw2-gwg-legacy-readonly-20261012.json
python3 tools/wb2a-v200kw2-gwg-followup-original-audit.py \
  /tmp/wb2a-v200kw2-gwg-legacy-readonly-20261012.json \
  /tmp/wb2a-v200kw2-gwg-followup-20261012.json
python3 -m unittest discover -s tests -q
```

Die Python-Liveprogramme starten ohne `--execute` nur eine Dry-Run-Zusammenfassung und verweigern unbekannte Serial-Geräte, ungeprüfte `settings_ini.py`, nicht aktiven unabhängigen Rückstell-Timer, aktive produktive Schnittstellenbelegung oder unbekannte Opcodes. Die Original-JSON-Dateien bleiben auf dem LXC, das GitHub-PR enthält Quellcode, Tests und erklärende Dokumentation.
