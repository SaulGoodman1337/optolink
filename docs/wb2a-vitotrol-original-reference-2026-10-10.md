# WB2A Vitotrol: originale Fremdaufzeichnung und Emulatorvergleich (10.10.2026)

**Forschungsstand, rein offline.** Kein KM-Bus-Anschluss, kein Optolink-
Write, kein P300-Fenster und kein Zugriff auf produktive RPM-Messungen.
Diese Erkenntnisse gelten zunaechst fuer eine **fremde Vitotrol 300**,
nicht automatisch fuer WB2A / VDensHO1 / 20C2.

## 1. Entscheidender Quellennachweis: ORIGINAL Vitotrol 300

`boblegal31` dokumentierte 2018 im [OpenV Issue #387, Kommentar 434866965](https://github.com/openv/openv/issues/387#issuecomment-434866965),
dass er eine *echte Vitotrol 300* von ihrer Grundplatte nahm, die
3,3-V-UART-TX-Leitung vor dem M-Bus-Wandler identifizierte und
**originale Slave-Telegramme** mitlas. Das ist nicht identisch mit der
spateren `boblegal31/Heater-remote`-Emulation des zweiten Slots.

Sein [Kommentar 435796559](https://github.com/openv/openv/issues/387#issuecomment-435796559)
verlinkt die Binardatei `log.bin` in
[`log.zip`](https://github.com/openv/openv/files/2553690/log.zip).
Die Datei wurde am 10.10.2026 **heruntergeladen und vollstaendig
nur offline analysiert**:

| Eigenschaft | Nachgemessener Wert |
| --- | --- |
| ZIP SHA-256 | `eb398ec9b4b174354425d2615f7d76937acaf5e0e1cde4df154fee78425bab93` |
| `log.bin` SHA-256 | `b6d5b0526d0b0a96e5bc3369de639763ef95db9786ee51a1c0b26ecbb229d068` |
| Rohgroesse | 3.858 Bytes |
| Vollstaendige, durchgehend CRC16/Kermit-gueltige Frames | **448** |
| `0x80` PONG | **416** |
| `0xBF / record 0x15` | **28** |
| `0xBF / record 0x20` | **2** |
| `0xB3 / F8..FB` | **1** |
| `0xB1 / register 0x00` | **1** |
| Letzter unvollstaendiger Frame | vier Bytes `00 11 80 08` |
| Vollstaendige Frames mit CRC-/Laengenfehler | **0** |

Der Parser hat **nicht** nach Fehlschlaegen zum naechsten Header
resynchronisiert; alle 448 aufeinanderfolgenden Frames passen bytegenau
und ohne Luecken. Die vier Schlussbytes sind ein unvollstaendiger
PONG-Frame, **kein** vier Byte langes KM-Bus-Telegramm.

Wichtige Grenze: Die Quelle enthaelt nur den Vitotrol-TX-Datenstrom,
**keine zugehoerigen Master-Anfragen oder Zeitstempel**. Genaue
Antwortlatenzen, Pollzyklen und die kausalen Masteranfragen sind aus
diesem Archiv nicht errechenbar. Ebenso wenig ist damit eine
Vitotrol-Antwort am lokalen WB2A-UART1-RX belegt.

### 1.1 Originalframes (exakte Bytes und Gueltigkeitspruefung)

| Herkunft | Originalframe | Sichere Aussage |
| --- | --- | --- |
| Vitotrol 300 `log.bin` | `00 11 B3 10 01 01 F8 11 F9 38 FA 01 FB 0A 1D B1` | Identitaetsbytes `11 38 01 0A` |
| Vitotrol 300 `log.bin` | `00 11 B1 0A 01 01 00 12 19 D5` | Register `0x00 = 0x12` in **diesem** Originalgeraet |
| Vitotrol 300 `log.bin` | `00 11 80 08 01 01 F9 5C` | PONG fuer Slot 1, 416 Wiederholungen |
| Vitotrol 300 `log.bin` | `00 11 BF 0C 01 01 20 62 AA AA 3D FC` | Raumtemperatur 20,0 C (`0x00C8`) |
| Vitotrol 300 `log.bin` | `00 11 BF 0C 01 01 20 64 AA AA E4 2A` | Raumtemperatur 20,6 C (`0x00CE`) |
| Vitotrol 300 `log.bin` | `00 11 BF 11 01 01 15 F9 AB 5A A0 AA AA 92 AA DF 0D` | `0x15`-Record; Feldbedeutung hier absichtlich NICHT behauptet |

Der andere, im OpenV-[Kommentar 434866965](https://github.com/openv/openv/issues/387#issuecomment-434866965)
dokumentierte Original-Temperaturframe
`00 11 BF 0C 01 01 20 78 AA AA D2 0A` entspricht 21,0 C.
Die Niedrig-/Hochbytes der Temperatur werden je mit `0xAA` XORiert.
Die 28 `0x15`-Records koennen als Originalbelege fuer Steuertelegramm-
*Syntax* verwendet werden, duerfen jedoch keine Boiler-Schreibbefehle
ausloesen; Adress-/Folgezustand und Revisionssemantik sind offen.

### 1.2 Register 0x00: Quelle statt vermeintlicher Konstante

- **Original-Binaerlog:** Register `0x00 = 0x12`; CRC stimmt.
- **WiFiVitotrol** `software/src/registers.cpp` (master `abf6de6`)
  verwendet heute `0x12`, geaendert in Commit `67196f7` (2025).
- **OpenV-KM-Bus-Wiki** berichtet fuer eine aeltere Vitotrol
  einen Wert `0x00`; weitere Emulatoren liefern `0x01`/`0x02`.
- **Heater-remote** emuliert Slot 2 mit Wert `0x02`; im OpenV-Issue
  antwortet ein anderes Emulatorbeispiel mit `0x01`.

Das ist kein stabiler gerateuebergreifender Wert. Die neue Offline-API
`model_register_00_reply(...,value=...)` erzwingt einen **expliziten**
Wert. Die State Machine antwortet auf `0x31 / reg00` nur, wenn
`register_00` ausdruecklich gesetzt und die Discovery modelliert ist.
Ohne Konfiguration bleibt der Pfad stumm (nicht als reale
WB2A-Emulationsrichtlinie freigegeben).

Auch die originalen Serienbytes `01 0A` unterscheiden sich von den
externen Quell-/Emulator-Samples `00 05` und `00 11`. Nur
Klasse/ID-Familie (`0x11 / 0x34 bzw. 0x38`) werden uebergreifend
gestuetzt. Das lokale WB2A-Firmwareprofil wurde nicht mit einer
echten Vitotrol identisch belegt.

## 2. Gegenpruefung anderer oeffentlicher Quellen

| Quelle | Evidenztyp | Aussage / Begrenzung |
| --- | --- | --- |
| [OpenV KM-Bus Wiki](https://github.com/openv/openv/wiki/KM-Bus) | Historische Originalgeraete-Messungen und teilweise Firmwareanalyse (Vitotronic 200KW2 / Vitotrol) | 1200 8E1, gerahmtes CRC16/Kermit, Vitotrol-Discovery, Original-Identitaetsbeispiel `11 38 00 05`; aelteres Geraet, **nicht 20C2** |
| [OpenV Issue #387](https://github.com/openv/openv/issues/387) | Primaerquelle inkl. realem TTL-TX-Log, Diskussionen, Quellarchive | Register 00, PING/PONG, `0xBF`, originaler Room-/Setpoint-Verkehr; Timing kritisch |
| [WiFiVitotrol](https://github.com/dumpfheimer/WiFiVitotrol) | Aktiver ESP8266/ESP32-M-Bus-*Nachbau* | Simuliert Klasse/ID, F8..FB, reg00, Ping/Record; `software/PROTOCOL.md` bezeichnet eigene Analyse als unvollstaendig |
| [Heater-remote](https://github.com/boblegal31/Heater-remote) | Unabhaengiger LPC-/NCN5150-Nachbau | Emuliert zweiten Slot neben echter V300; sein eigener B1-reg00-Wert ist `0x02` |
| [Timob0: kmBusAgent.py](https://github.com/openv/openv/issues/387#issuecomment-695110891) | Fremder Python-Softwareemulator und Mitschnitte am anderen Regler | Relevante Zustands-/Timing-Implementierung; **keine** Original-TX-Binaerdaten dieses Skripts |

Zu beachten: `WiFiVitotrol` ist fuer den physischen KM-Bus
entwickelt, **nicht fuer die Optolink/P300-Injektion**. Ein funktionierender
Nachbau auf einer Vitocal/Vitotronic ist kein Beleg fuer einen
funktionierenden internen Optolink-RX-Service der WB2A.

**Timing:** Der OpenV-Thread beschreibt eine sehr kurze zulaessige
Antwortlatenz (grob im Bereich 50-60 ms), kann aber aus der originalen
`log.bin` ohne Zeitstempel keine harte lokale Grenze belegen.
USB-/Linux-Userland-Latenzen sind fuer einen aktiven KM-Bus-Slave
deshalb riskant; ein isoliertes MCU-Interface mit lokalem
Antwortscheduler ist die technisch bessere physische Architektur.

## 3. Reproduzierbarer Offline-Test

Die Repo-Datei `tools/wb2a-vitotrol-public-capture-audit.py` nimmt
**nur eine bereits heruntergeladene ZIP-Datei** an. Es gibt keine
Netzwerk-, Serial-, MQTT-, RAM-/Codier- oder Schreibfunktion zum Kessel.
Das Originalarchiv wird nicht als Repo-Binaerblob dupliziert.

```bash
python3 tools/wb2a-vitotrol-public-capture-audit.py \
  /tmp/wb2a-vitotrol-public-sources-20261010/original-vitotrol300-log.zip \
  --expected-sha256 eb398ec9b4b174354425d2615f7d76937acaf5e0e1cde4df154fee78425bab93

python3 -m unittest discover -s tests -p 'test_wb2a_vitotrol*.py' -q
python3 -m unittest discover -s tests -p 'test_*.py' -q
```

Der Audit zaehlt B1/B3/BF/80, identifiziert das im Original benutzte
Register-00-Byte sowie die beiden Temperaturwerte, und verweigert
CRC-Fehler, unbekannte Framegrenzen, ungeeignete ZIP-Mitglieder und
grobe Trunkierung. Synthetische Test-Fixures basieren auf wenigen
**unveraenderten Originalframes**, nicht auf einem kompletten Kopieren
des Fremdarchivs.

## 4. Technische Entscheidung fuer unsere WB2A

**Protokollformat: hoch belegt (extern).** Originale V300-Slaveframes
und unsere lokal archivierten WB2A-Master-Discovery-Frames benutzen
denselben KM-Bus-Rahmen. Im Originalarchiv gibt es dennoch keine
an unsere eigene WB2A gesendete Antwort.

**Physischer Slave: aussichtsreichste reale Funktion.** Bestehende
Nachbauten beweisen Machbarkeit auf anderen Viessmann-Reglern.
Ein eigenstaendiger MCU-Slave braucht einen geprueften,
galvanisch geeigneten KM-Bus-Transceiver, passive lokale Busmessung
und gesonderte sichere Hardwareabnahme. Nicht einfach UART-TTL an
Klemme 145 anschliessen; der Bus arbeitet nicht mit TTL-Pegeln.

**Optolink-only: noch kein Empfangspfad.** Dieser Fund verraet weder
`INTB`/UART1-RX-ISR/Empfangspuffer unserer 20C2 noch ein legales
P300-RX-Injektions-RPC. Die Read-only-Hybridfreigabe bleibt unveraendert.

**Konkrete naechste Tasks:** (1) Offline-Abspieltest des kompletten
originalen Slave-Streams samt CRC/B1/Records, (2) Original-Records
`0x15` nur passiv und feldweise ohne Write-Effekte klassifizieren,
(3) Antwort-Timing in einem gesonderten synthetischen Bus-Harness
simulieren, (4) separat nach einem *geraetegenauen*
WB2A-Regler-Firmware-/UART1-RX-Nachweis suchen, (5) wenn die
Software-only-Hardwaregrenze bestehen bleibt, ein passives KM-Bus-
Messinterface und anschliessend einen begrenzten MCU-Slave
nur mit bewerteter elektrischer Sicherheit planen.

Die produktive VS1-Hauptschleife und laufende RPM-V2-Forschung
bleiben unberuehrt; PR #52 bleibt Draft.
