# WB2A Vitotrol: Original-300-Profil und verschärfter Optolink-RAM-Xref-Audit

**Stand 10.10.2026, ausschließlich offline.** Verbindliche Architektur:
Vitotrol **nur über Optolink/P300** auf dem vorhandenen seriellen
Hauptprozess. Kein zusätzlicher KM-Bus-Slave/Mikrocontroller, kein neuer
Portbesitzer, keine unbekannten Controller-RAM- oder SFR-Schreibzugriffe.
Während des laufenden RPM-v2-Loggers erfolgte kein neuer P300-Wechsel.

## 1. Warum das zweite V300-Profil wichtig ist

Das bestehende Emulator-Modell kannte vorher nur die hypothetische
`IDENTITY_V300_SAMPLE = 11 38 00 11` aus einem anderen
Projektkontext. Eine **originale** Vitotrol 300 antwortete jedoch
im veröffentlichten UART-TX-Mitschnitt von `boblegal31` (2018)
mit der bytegenauen Identität `11 38 01 0A`.

Daher jetzt explizit getrennt:

| Identitätsvariante | Rohbytes F8..FB | Herkunft / Aussage |
| --- | --- | --- |
| `v200` | `11 34 00 05` | Öffentlicher Vitotrol-200-Nachbau, kein Original-20C2-RX |
| `v300_sample` | `11 38 00 11` | Frühes öffentliches Vergleichsbeispiel, **kein** eigenes Originalgerät |
| **`v300_original`** | **`11 38 01 0A`** | **Original-V300-UART-TX**, OpenV Issue #387 / `log.zip` |

Der V300-Originalfall hat darüber hinaus den in genau diesem
originalen TX-Archiv belegten Antwortwert `register_00 = 0x12`.
Dies ist **keine** geräte- oder revisionsübergreifende Konstante.
Das neue Factory-Modell `original_v300_offline_profile()` erzeugt
nur eine **Slot-1**-Simulation mit genau dieser Identität, diesem
Wert und der vorhandenen strikten Raumtemperatur-Frischeprüfung.
Slot 2 wird nicht als originale Vitotrol 300 ausgegeben.

### Exakt reproduzierte Originaltelegramme (mit Gegenbeispielen)

Die folgenden **von einer echten Vitotrol 300 ausgesendeten**
Telegramme werden nun vom vorhandenen Modell bytegenau
rekonstruiert; ihre Übertragung an unsere WB2A ist weiterhin **nicht**
nachgewiesen:

```text
Originale Identität F8..FB:
00 11 B3 10 01 01 F8 11 F9 38 FA 01 FB 0A 1D B1

Originales Register 00:
00 11 B1 0A 01 01 00 12 19 D5

Originaler PONG:
00 11 80 08 01 01 F9 5C

Originale Raumtemperatur 20,0 °C:
00 11 BF 0C 01 01 20 62 AA AA 3D FC

Originale Raumtemperatur 20,6 °C:
00 11 BF 0C 01 01 20 64 AA AA E4 2A
```

Zuordnungen für Discovery/PING bzw. `0x31` werden anhand der
separat dokumentierten öffentlichen Masterbeispiele **modelliert**,
nicht aus diesem Slave-only-Archiv extrapoliert. Insbesondere
kann aus dem Originalarchiv **keine** tatsächliche Anfragezeit,
Antwortlatenz oder PONG-Zeitabstand rekonstruiert werden.

Testfall simuliert Discovery → Register-00-Abfrage → ersten
Temperaturrecord → PONG → nach 30 s anderen Temperaturrecord.
Auch veraltete Raumtemperatur (keine gefälschte Liveness),
Fehlerslot und CRC-Abweichungen werden negativ getestet.

## 2. 448 Original-Frames nochmals vollständig geprüft

Öffentliche Quelle:
[OpenV Issue #387, Original-V300-TX-Binärlog](https://github.com/openv/openv/issues/387#issuecomment-435796559).

Belege:

```text
ZIP SHA256:
eb398ec9b4b174354425d2615f7d76937acaf5e0e1cde4df154fee78425bab93

log.bin SHA256:
b6d5b0526d0b0a96e5bc3369de639763ef95db9786ee51a1c0b26ecbb229d068
```

`tools/wb2a-vitotrol-original-sequence.py` kontrolliert das
unveränderte Originalarchiv und arbeitet zusätzlich zum bisherigen
Frame-/CRC-Auditor die Frame-Reihenfolge ab. Jede vollständige
Framegrenze wird geprüft, **ohne Resynchronisation** bei Fehlern.
Ergebnis:

| Gruppe | Originale Frames | Bytegenau offline generiert |
| --- | ---: | ---: |
| Identität `B3/F8..FB` | 1 | **1** |
| Register `B1/00` | 1 | **1** |
| `80/PONG` | 416 | **416** |
| `BF/20` (20,0 und 20,6 °C) | 2 | **2** |
| `BF/15` (opaque Steuer-/Statusrecord) | 28 | **0**; nur lesender Decoder |
| **Summe** | **448** | **420** |

**420/448 = 93,75 % der aufgezeichneten Telegramminstanzen,
nicht 93,75 % aller Vitotrol-Funktionen.** Insbesondere entfallen
**416 der 420 Treffer auf genau denselben PONG**. Es sind nur
die oben genannten **vier Antwortfamilien** implementiert.
Die echte Vitotrol-Firmware, Watchdog-Abfolge, Zeitsteuerung und
controllerseitige Annahme sind damit nicht rekonstruiert.

Das Archiv endet mit vier Bytes `00 11 80 08` eines
unvollständigen PONG; die 448 vollständigen Frames haben
alle eine gültige CRC16/Kermit-Prüfung.

### Unbekanntes Original-Record `BF/15`

**28/28** `BF/15`-Records besitzen unterschiedliche Payloads.
Der neue Auditor berechnet eine ausdrücklich **rein algebraische**
XOR-`AA`-Ansicht der acht Record-Nutzbytes (keine nachgewiesene
Bedeutungszuordnung). Die Anzahl unterschiedlicher Werte nach
Payload-Position 0..7 ist:

```text
Index          0   1   2   3   4   5   6   7
Werte         26   1   9  10   4   3   2   1
Konstant          01                       00
```

Die ersten XOR-projizierten Bytes der letzten sieben Records
stehen in dieser beobachteten **Reihenfolge**:
`0B 0C 0D 0E 0F 09 0A`.
Das könnte zu einem zyklischen/rollierenden Zustand passen,
ist aber ebenso mit bislang ungeklärter Eingabesemantik
vereinbar. **Kein** Rolling-Code-Verfahren ist bewiesen.
Es werden ausdrücklich **keine `BF/15`-Telegramme generiert**,
keine Stellwerte interpretiert und keine Schreibfunktionen
freigeschaltet.

## 3. Erweitertes RAM-Xref-Audit – 0x0B6D ist nicht eindeutig

Die 79 vollständigen privaten 20-KiB-P300-Snapshots wurden
nochmals vollständig auf das Little-Endian-Adressenpaar
`42 16` (`0x1642`, RX-Kandidat) sowie `1A 16`
(`0x161A`, bekannter TX-Puffer) untersucht. Im Gegensatz zu
einer einzelnen festen Adresse erfasst der neue Scanner **alle
Bytepositionen**, einschließlich ungerader Offsets. Ergebnis:

| Gesuchte Bytefolge | Fundadresse im RAM | Anzahl von 79 Snapshots |
| --- | --- | ---: |
| `42 16` (RX-Kandidat) | `0x0B6D` | **79** |
| `42 16` | `0x33A3` | **79** |
| `42 16` | `0x0B5C` | 2 |
| `42 16` | `0x0FB8` | 1 |
| `42 16` | `0x1199` | 1 |
| `1A 16` (TX-Beginn) | `0x0ADE` | **65** |
| `1A 16` | `0x0B00` | **64** |
| `1A 16` | `0x0ADB` | 11 |
| `1A 16` | `0x0AD1` | 3 |

`0x0B6D..0x0B70` bleibt in allen 79 Samples `42 16 0A FE`.
Die Kombination eines numerisch passenden RAM-Wortes und des
nachfolgenden Längenbytes `0A` ist **kompatibel mit** einer
Pufferdeskriptorstruktur. Aber: Schon `0x33A3` enthält in **79/79**
Snapshots ebenfalls `42 16`, und weitere zufällige oder andere
strukturierte Treffer existieren. **Ein Bytepaar allein beweist
keine Referenz und noch weniger den UART1-ISR-Parser.**

Auch das beobachtete Statuspaar `0x166A/0x166B` und die Variation
der CRC-gültigen Klasse-`01`-Frames bei `0x1642` erlauben keine
sichere Schlussfolgerung über Buffer-Ownership oder
Schreib-/Commit-Semantik.

### Reproduktionskommandos (rein offline)

```bash
cd /home/chatgpt-admin/optolink-vitotrol-rpm-20261010

python3 tools/wb2a-vitotrol-offline.py --variant v300_original

python3 tools/wb2a-vitotrol-original-sequence.py \
  /tmp/wb2a-vitotrol-public-sources-20261010/original-vitotrol300-log.zip

sudo cat /root/p300-trial-work/research-bundles/p300-fullram-run-20261009T083607Z-144293-bundle.tar.gz \
  | python3 tools/wb2a-vitotrol-optolink-rx-context.py --kind fullram

python3 -m unittest discover -s tests -p 'test_*.py' -q
```

Code und Regressionen:
`tools/wb2a-vitotrol-offline.py`,
`tools/wb2a-vitotrol-original-sequence.py`,
`tools/wb2a-vitotrol-optolink-rx-context.py`,
`tests/test_wb2a_vitotrol_v300_original_profile.py`,
`tests/test_wb2a_vitotrol_original_sequence.py`,
`tests/test_wb2a_vitotrol_rx_context.py`.

## 4. Technischer Gate vor einer echten Optolink-Emulation

1. **Lokal spezifische Firmware/ISR:** Gesucht ist `INTB` und
   UART1-RX-Vektor 20 samt Code, welcher `U1RB` empfängt und CRC,
   Klassen-/Slotzuordnung sowie Vitotrol-State verarbeitet.
2. **Kontrollierter Optolink-State-Commit:** `FC03/Physical_READ`
   und gültige RAM-Bytes sind ein Diagnosebeleg, nicht die Erlaubnis,
   UART1-Eingangszustände oder Watchdogs zu überschreiben.
3. **Ende-zu-Ende-Tests erst mit Nachweis:** Vitotrol-Abbildung auf
   `0x0A5C` (Fernbedienungs-Softwareindex), `0x0896` (Raumtemp),
   `0x089C` (Status), plus `BC`-Fehlerfreiheit, in einem
   abgesicherten echten Hardwarefenster. Keine Aktivierung von
   `0x27A0=1` ohne validierte Antwortverarbeitung.

Die aus Host-VitoSoft rekonstruierte exakte VDensHO1-Eventliste
hat bisher **keinen** katalogisierten KM-Bus-RX-Inject-RPC und
keinen lokalen Flash-/ROM-Read-Bridge-Pfad gezeigt. Auch der
im alten Research dokumentierte lesende P300-Funktionscode
`0x41 / KMBUS_RAM_READ` beweist keinen solchen Write-/ISR-Pfad.
Ohne authentischen Controller-Firmware- oder Servicebeleg bleibt
dieser Punkt eine offene Forschungsabhängigkeit.

**Produktivstatus:** `main`/VS1 bleibt unverändert, RPM-v2-Logger
läuft unverändert im bestehenden Dienst. PR #52 bleibt Draft.

## 5. Vorbereitung einer spaeteren, sicheren Abnahme

Die quellgebundenen Original-V300-Antworten lassen sich jetzt auch gegen eine [rein synthetische Vitotrol-Abnahmeteststrecke](wb2a-vitotrol-acceptance-offline-2026-10-10.md) einordnen. Dort werden die spaeter benoetigten Controller-Readbacks, stabile Softwarekennung, mehrstufige Temperaturuebernahme, BC- und Fehlerhistorienfreiheit sowie eine vollstaendige Rueckstellung einschliesslich Nachlauf als Regressionen modelliert. **Dies beweist keine echte Erkennung an der WB2A**: der Optolink-interne UART1-RX-/Commit-Mechanismus ist weiterhin unbekannt. Es wurden weder die Codierung aktiviert noch Controller-RAM-Writes oder neue P300-Hardwarefenster ausgefuehrt.
