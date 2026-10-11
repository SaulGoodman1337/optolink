# WB2A/20C2: Öffentliche KM-Bus-PCAP-Referenzen, neue Frameformen und RX-Strukturgate

**11.10.2026 – Nur Offline-Forschung zur Vitotrol-Emulation über Optolink.** Keine neuen Optolink-/P300-Livezugriffe, RAM-/SFR-/EEPROM-Writes oder Codierungsänderungen. Produktiver VS1-Splitter und passiver RPM-v2-Beobachter bleiben unangetastet. PR #52 bleibt Draft.

## 1. Unabhängige historische KM-Bus-Captures

Primärquelle: [OpenV Issue #387](https://github.com/openv/openv/issues/387), historische [KM-Bus-Protokollnotizen](https://github.com/openv/openv/wiki/KM-Bus).

Der neue rein passive Parser `tools/wb2a-vitotrol-public-pcap-audit.py` verarbeitet **vorher heruntergeladene** exakt SHA-gepinnte ZIP-Dateien mit genau einem erwarteten PCAPNG-Mitglied. Verifiziert werden PCAPNG-Block-/Trailerlängen, IDB-/Ethernet-Linktype, Timestampauflösung, monotone Erfassungszeiten, IPv4/UDP-Längen, Framegrenzen und CRC16/Kermit für jedes KM-Bus-Telegramm.

| Drittquelle | ZIP SHA-256 | PCAPNG SHA-256 | CRC-gültige Frames |
| --- | --- | --- | ---: |
| `Capture_busKM_1h.pcapng`, Januar 2018, nur **Master-Sicht** | `1672ec6a2a16396fcefa388feb327dccdc26aadda41d9fc4cedd029e3081a68c` | `1d813a6f2f8adddd149bac21acf6613694c33d7ef43b07a6f72e77fac60ff175` | **5269/5269** |
| `KM3.pcapng`, Oktober 2018, **experimenteller Emulator** | `54205e0c803de432676c3d252fdb4b3a827ebb53a128d34cf5cc6d866644fa13` | `5b72401e5e8b1d9ffba2ecb201150df54e26a836bb73db1c486a72d2d43407af` | **701/701** |

Lokale ZIP-Dateien: `original-bus-master-capture.zip` und `kmbus-captures.zip` unter `/tmp/wb2a-vitotrol-public-sources-20261010/`. Die Original-Binärdaten werden nicht in das GitHub-Repository kopiert. **Keines dieser PCAPs wurde an unserer WB2A/20C2 aufgenommen**; die echte Vitotrol-300-UART-TX-Aufzeichnung `log.bin` ist eine **andere**, zuvor separat ausgewertete Quelle.

### Capture 1: Master (5269 Telegramme, 3844,088441 Sekunden)

| Zielklasse / Quelle / Kommando | Anzahl |
| --- | ---: |
| `01 00 33` | 1966 |
| `01 00 B1` | 1158 |
| `01 00 31` | 772 |
| `11 00 00` (Vitotrol-Master-PING) | **681** |
| `11 00 BF` (Masterstatus) | **326** |
| `11 00 33` (F8/04-Identitätsabfrage) | **152**: Slot 2 und Slot 3 jeweils 76 |
| `20 00 B3` | 64 |
| Weitere Klassen und Nachrichten | weitere, im Parser vollständig gezählt |

Masterstatus `11 00 BF` teilt sich auf in **180 × Record-ID 0x11, Länge 40, Slot 1** und **146 × 0x1D, Länge 21, Slot 1**. Unverändertes CRC-gültiges Beispiel des Records `0x11`:

`11 00 BF 28 01 01 11 A5 AB AF A2 AA 98 98 96 BE BB BE A6 A8 AA AA AA AA AA AA AA AA A0 E0 BE E0 A0 AA A8 B4 A8 AA 1F 07`

Die **Geräteklasse 0x11** und die **Record-ID 0x11** sind strikt unterschiedliche Protokollfelder. Die bisherige Offline-State-Machine kannte die zweite Form nicht.

**Zeitreferenz:** Zwischen einem Masterstatus-`BF/11`-UDP-Paket und dem jeweils nächsten PING-UDP-Paket liegen 180 auswertbare Abstände, Median **0,094981 s**, Minimum **0,087806 s**, P90 **0,099367 s**, Maximum **2,148880 s**. Die Pcapng-Quelle enthält **Ethernet-Zeitstempel**, keine direkten physikalischen KM-Bus-Flanken, und keine Klasse-11-Slaveantworten. Die Zahlen liefern daher weder ein zulässiges Slave-Antwortdeadline-Limit noch eine WB2A-spezifische Latenz.

### Capture 2: Emulator (701 Telegramme, 553,380698 Sekunden)

Im experimentellen Slot-2-Mitschnitt sind **478** Master-`BF`-Records und **223** vom **Emulator** ausgesendete Slave-`BF`-Records enthalten:

| Richtung | Record | Slot | Länge | Anzahl |
| --- | --- | ---: | ---: | ---: |
| Master → Slave | `0x11` | 1 | 40 | 24 |
| Master → Slave | `0x12` | 2 | 40 | 111 |
| Master → Slave | `0x1A` | 2 | 11 | 277 |
| Master → Slave | `0x1D` | 1 | 21 | 33 |
| Master → Slave | `0x1E` | 2 | 21 | 33 |
| Emulator → Master | **`0x16`** | **2** | **12** | **223** |

Echte CRC-gültige Emulatordaten: `00 11 BF 0C 02 01 16 AA AA 4D C1 A8`, XOR-Daten nach `0xAA` sind `00 00 E7`. Die historischen [Python-Slave-Emulatoren im OpenV-Thread](https://github.com/openv/openv/issues/387) bezeichnen die Slot-1-Anfrage als Record `0x15` und die Slot-2-Variante als `0x16`. Das ist **kein originaler Vitotrol-300-Mitschnitt** und **keine** an unserer WB2A akzeptierte Slaveantwort.

### Erweiterter Offline-Emulator

`tools/wb2a-vitotrol-offline.py` nimmt die **Masterstatus-Records** `0x11` (40 B), `0x12` (40 B) und `0x1A` (11 B) neu als CRC-geprüfte, aber opaque Nachrichten entgegen. Sie verändern weder Raumtemperatur, Identität noch Heizungswerte und lösen keinen Write aus. Der neue `decode_candidate_slave_record_16` akzeptiert nur die belegte emulierte `00 11 BF ... 02 01 16`-Form (12 B) mit geprüftem CRC und XOR-Daten; `controller_write_authorized=false`.

Der synthetische Vitotrol-State-Machine-Replay wertet alle **478** Master-Statusnachrichten von Capture 2 als gültige Opaque-Statusdaten aus, ohne darauf zu antworten oder ungesicherte Steuerwerte zu übernehmen. Beim Master-Replay von Capture 1 erzeugt ein explizit modellierter Slot-2-Emulator **76 modellierte F8/04-Identitätsantworten** und keine Antworten auf Slot 3; das ist ausschließlich ein Test der bekannten Zuordnung, **nicht** eine hardwareerfolgreiche Teilnehmeranmeldung.

## 2. Lokaler 20C2-RAM-Suchkandidat `0x0B6D`

Das bereits SHA-verifizierte **private** P300-Gesamtspeicherarchiv `p300-fullram-run-20261009T083607Z-144293-bundle.tar.gz`, SHA256 `94d5842b6dc5759ecb446a4c617b60b72873b639885d116032f783abdef8431c`, umfasst 79 einzeln geprüfte vollständige 20.480-Byte-SRAM-Snapshots.

Der erweiterte rein offline berechnete Bericht `descriptor_0b6d_hypothesis` aus `tools/wb2a-vitotrol-optolink-rx-context.py` zeigt:

| Verifikation | Zahl |
| --- | ---: |
| `0x0B6D..0x0B70` = `42 16 0A FE` | **79/79** |
| Erstes LE16-Wort = `0x1642`, RX-Kandidat | **79/79** |
| Drittes Byte `0x0A` stimmt mit der bei `0x1642+3` gelesenen B1-Rahmenlänge überein | **79/79** |
| RX-Kandidat CRC-valides B1-Register `0x10` | 78 |
| RX-Kandidat CRC-valides B1-Register `0x00` | 1 |
| Vorangestelltes `0x0B6B` = `01 / 0A / 0B` | 72 / 3 / 4 |

Das ist eine **ausdrucksstarke Strukturhypothese**, jedoch kein nachgewiesener typisierter RX-Pointer, UART1-RX-ISR, Firmware-State-Commit oder ein P300-Schreibziel. Insbesondere besitzt das konstante letzte Byte `FE` keine gesichert bekannte Rolle. Der zusätzliche statische `0x1642`-Literaltreffer bei `0x33A3` belegt, warum bloße Byteübereinstimmungen nicht reichen. Die vollständigen SRAM-Images wurden nicht atomar, sondern über 640 nacheinander ausgeführte 32-Byte-Blöcke gewonnen.

Der um die Kandidaten ergänzte SHA-gepinnte VitoSoft-Profiljoin (`tools/wb2a-vitotrol-vitosoft-static.py`) prüft **genau VDensHO1 / DatapointType 60 / 581 Eventdefinitionen / 22 RPCs**. Keiner der Kandidaten `0x0B6B/0B6C/0B6D/0B6F/0B70`, `0x0ADE`, `0x0B00`, `0x161A`, `0x1640`, `0x1642`, `0x164C`, `0x166A/166B/166C` oder `0x7342` besitzt ein exakt zugeordnetes Hostprofil-Event. Die 22 RPCs stehen überwiegend für LON-Teilnehmerlisten sowie Reset-/Fehlerhistorienfunktionen. Der globale Begriff `XRAM_WRITE` oder fremdprofilierte KBUS-Schreibfunktionen beweisen **keinen** nutzbaren VDensHO1-RX-Dispatcher.

**Wichtig:** Ein fehlender Hostkatalog-Eintrag schließt einen nicht dokumentierten Firmware-/ROM-Service nicht aus. Ohne MCU-/ROM-/UART1-RX-ISR-Beleg für die **tatsächliche** 20C2 kann aus den RAM-Mustern aber **keine sichere Optolink-Injektionsadresse oder State-Commit-Funktion** abgeleitet werden.

## 3. Reproduzierbare Tests ohne aktive Heizung

Verifizierte öffentliche Quellen nur aus lokalen ZIPs:

    python3 tools/wb2a-vitotrol-public-pcap-audit.py master /tmp/wb2a-vitotrol-public-sources-20261010/original-bus-master-capture.zip
    python3 tools/wb2a-vitotrol-public-pcap-audit.py emulator /tmp/wb2a-vitotrol-public-sources-20261010/kmbus-captures.zip
    python3 -m unittest discover -s tests -p 'test_wb2a_vitotrol_public_pcap_audit.py' -q

Verifizierter privater RAM-Archivaudit (nicht exportieren):

    sudo python3 tools/wb2a-vitotrol-ram-window-locality.py --archive /root/p300-trial-work/research-bundles/p300-fullram-run-20261009T083607Z-144293-bundle.tar.gz
    python3 tools/wb2a-vitotrol-vitosoft-static.py /home/chatgpt-admin/research/vitosoft-lfs/DPDefinitions.xml /home/chatgpt-admin/research/vitosoft-lfs/ecnEventType.xml
    python3 -m unittest discover -s tests -p 'test_*.py' -q

CI ohne lokale private VitoSoft-/RAM-/öffentlich separat heruntergeladene ZIP-Dateien prüft das Protokoll mit synthetischen, gezielt korrumpierten PCAPNG-/CRC-/XML-/Descriptor-Fixtures. Eine echte Quellenbestätigung benötigt den abgeglichenen SHA256-Originaldatensatz.

## 4. Architekturentscheidung und aktuelles Entwicklungs-Gate

Die Protokoll-Syntax der Vitotrol-Klassen, Slot-2-Memory-Query, der Masterstatus und die F8/F9/FA/FB-Identität sind extern referenziert und offline überprüfbar. **Für die reale Emulation über Optolink fehlt weiterhin:**

1. Positiv zugeordnetes MCU- und Firmwareabbild des lokalen WB2A-Reglers, statt unbewiesener Übertragung von einer anderen VBC130- oder Vitotronic-Generation.
2. Nachweis des **KM-Bus/UART1-RX-ISR → Parser → Teilnehmer-Liveness/Softwarekennung/Sensorstatus/Temperaturübernahme**-Pfads.
3. Eine tatsächlich existierende, über den bestehenden einzigen Optolink-Serienbesitzer und ohne gefälschte RAM-IRQ-Aktionen sicher ansteuerbare Receive-/State-Commit-Funktion.
4. Vor erneuten Live-Shadow-Tests die separate Hardware-Qualifikation der nach dem Timeout nur offline gehärteten systemd-Recovery.

Das jüngste Live-A0/B0-Experiment erzeugte einen gespeicherten BC-Fehler und bestätigte keine Vitotrol. Weitere reine A0/B0-Umschaltungen oder geratenen `Physical_WRITE`-/`XRAM_WRITE`-/KM-Bus-Transparent-Calls würden **keinen neuen Funktionsnachweis liefern**. Daher keine weiteren Live-Schreibexperimente in dieser Runde. Projektziel bleibt **ausschließlich Optolink-only-Vitotrol-Emulation**; der laufende produktive VS1-Betrieb wird nicht ersetzt.
