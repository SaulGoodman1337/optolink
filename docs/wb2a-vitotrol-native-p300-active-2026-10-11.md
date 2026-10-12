# WB2A / VDensHO1 / 20C2 – echte Vitotrol-RAM-Einspeisung über nativen Optolink-P300

**Datum:** 11.10.2026, Europe/Berlin, aktive WB2A-Hardwareversuche ab 09:23 Uhr. **Hauptziel ist allein die Vitotrol-Emulation über Optolink.** Die Unterscheidung zwischen VS1 und P300 ist für den Emulationsweg keine Priorität; **native P300-Nutzung ist explizit zugelassen**.

## 1. Aufbau und reproduzierbare Verbindung

Der bestehende **einzige** Hauptprozess `optolink-splitter.service` kann P300 direkt und dauerhaft benutzen, wenn `vs1protocol = False` in `/opt/optolink/settings_ini.py` steht. Der originale Splitter behandelt bereits `request;<FC>;<Adresse>;<Laenge>;<Hexdata>`. Kein zweiter USB-/Optolink-Serienbesitzer, kein KM-Bus-Mikrocontroller.

Im echten native-P300-Hardwarefenster antwortete die WB2A auf `read;0x00f8;8` mit `20c2000300000103`, `rc=1`. P300-`Physical_READ` `FC=0x03` lieferte bei `0x1640` folgenden 32-Byte-Bereich (zu Beginn 09:23:42):

    00 00 00 01 B1 0A 01 01 10 FE 23 D8 FA 01 FB 01
    22 D1 00 00 00 00 00 00 00 00 00 00 00 00 00 00

Der seit langem beobachtete **Klasse-01-KM-Bus-Slave-Frame** beginnt bei physischem P300-RAM-`0x1642`. Der separat gelesene UART1-Master-TX-RAM-`0x161A` enthielt unverändert eine Klasse-01-`B1`-Antwort. Das ist physisches SRAM, **kein direktes elektrisches KM-Bus-Pegelsignal**.

## 2. Erfolg: FC=04 schreibt echte Vitotrol-Telegramme in den Regler-RAM

Native P300 unterstützt `Physical_WRITE` `FC=0x04`. Eine exakte, konservative Probe mit **dem bereits vorhandenen CRC-validen** Klasse-01-Frame an `0x1642/10` antwortete `rc=1` und hatte identisches Readback. Anschließend wurden **wirkliche, in der OpenV-Issue-#387-Binärdatei `log.bin` original aufgezeichnete Vitotrol-300-Slaveframes** aktiv geschrieben:

| Original-V300-Antwort | Echt gesendeter FC04-Payload | Länge | Ergebnis |
| --- | --- | ---: | --- |
| Identity `B3`, Gerätekennung `11 38 01 0A` | `0011b3100101f811f938fa01fb0a1db1` | 16 | `rc=1`, SRAM-Rücklesung byteidentisch |
| Register 00 `B1` = `0x12` | `0011b10a0101001219d5` | 10 | `rc=1`, SRAM-Rücklesung byteidentisch |
| Raum 20,0 °C `BF/20` | `0011bf0c01012062aaaa3dfc` | 12 | `rc=1` |
| Raum 20,6 °C `BF/20` | `0011bf0c01012064aaaae42a` | 12 | `rc=1` |
| PONG `80` | `001180080101f95c` | 8 | `rc=1` |

Damit ist ein **benutzbarer Optolink→P300→SRAM-Transport** für präzise, gültige Original-Vitotrol-Telegramme bewiesen. **Nicht** bewiesen sind das tatsächliche Betreten einer UART1-Empfangs-Interrupt-Routine, die KM-Bus-Protokoll-State-Machine und die Registrierung der Vitotrol. Der erfolgreiche FC04-Return alleine darf niemals als Vitotrol-Anmeldung ausgegeben werden.

## 3. Aktive Fernbedienungsversuche und negative Acceptance-Grenze

Mehrere voneinander getrennte, jeweils nachher restaurierte Hardwareläufe:

1. `A0=01`, `B0=03`, anschließend **originale B3-Identität** nach `0x1642`; exakte Rücklesung, aber `SWIndex_FB1 (Virtual_READ 0x0A5C)=00000000`, `RTS (0x0896)=c800`, `SensorStatus (0x089C)=03`.
2. `A0=01` / `B0=03` und **sequenziell alle vier Originalantworten B3→B1→BF(20 °C)→PONG**; alle FC04-Requests `rc=1`, aber keine Teilnehmerkennung, keine neue gültige Raumtemperatur.
3. Zusätzlich zunächst `Remote-Type (Virtual_WRITE 0x7342)=74`, dann `A0=01`/`B0=03`, B3-Identität + B1-Reg00 + BF(20,6 °C). Type `74` bestätigte die WB2A tatsächlich; **trotzdem** `SWIndex_FB1=00000000`, `RTS=c800`, `SensorStatus=03` und aktueller Fehler `5738=00`.
4. Der neue [aktive native P300-Vitotrol-RAM-Bridge-Treiber](../tools/wb2a-vitotrol-p300-bridge.py) replizierte den kompletten Versuch **automatisch** um 09:35–09:36 Uhr, inklusive aller Originalframes, Prüfrücklesungen und **zweier** getrennter Acceptance-Beobachtungen. Ergebnis: **4/4 exakt in SRAM bestätigt**, aber `SWIndex_FB1=0`, `RTS=c800`, `SensorStatus=03` zu beiden Abtastungen. Abschließende Codierungen `A0/B0/Type=00/00/00` und die ersten 16 Bytes des alten RX-Puffers exakt wiederhergestellt. CLI markiert diese negative Hardwareabnahme durch Exitcode **4**, nicht durch einen grünen Emulatorstatus.

**Schlussfolgerung:** Wir haben endlich echte aktive KM-Bus-Slavebytes per Optolink in das relevante **RAM** eingespeist. **Der Controller verarbeitet sie auf diesem Weg jedoch noch nicht als gültige UART1-/KM-Bus-Slaveantwort.** Aktive Raumführung mit echter Vitotrol-Erkennung ist noch nicht gelungen.

### RAM-Status-/Index-Experimente

In den 79 SHA-verifizierten früheren Voll-RAM-Aufnahmen trat `0x0B6B` natürlich mit `01` (72-mal), `0A` (3-mal) und `0B` (4-mal) auf. Bei `0x166A..0x166C` war `06 00 01` typisch und `0A 04 01` ein einzelner seltener Zustand.

Aktiv durchgeführte Tests:

- `Physical_WRITE 0x166A/2 = 0A 04` `rc=1`, im nachfolgenden Lesefenster wieder `06 00 01`, keine Softwarekennung. Auch während `A0=01/B0=03` keine Übernahme.
- `Physical_WRITE 0x0B6B/1 = 0A` `rc=1`, nachfolgend `Physical_READ 0x0B60/32` aber bereits wieder `01`. Parallel eingespeiste originale B1-Registerantwort blieb im RX-Kandidatenbuffer.
- `Physical_WRITE 0x0B6B/1 = 0B` `rc=1`, `Physical_READ` bestätigte tatsächlich `0B`, aber weiter `SWIndex_FB1=0`, `RTS=c800`, `SensorStatus=03`, kein aktueller Fehler. Originalwert `01`, Metadaten `06 00` und Original-RX-Frame wurden in der Cleanup-Phase aktiv restauriert.

Diese Tests machen eine eigenständige RX-Verarbeitungsbedingung wahrscheinlicher. Eine statisch gesetzte Byteposition im SRAM ersetzt **keine** tatsächliche UART1-RX-Interrupt-Verarbeitung. Die Bedeutungen `0B6B` und `166A/B` sind weiterhin nicht eindeutig.

### Physisches RAM vs. virtuelle Datenpunkte sind NICHT identisch

Die **79 archivierten P300-Physical_READ-Images** zeigen:
- **Physisch `0x0896/2`:** 51-mal `08e8`, 28-mal `b608`, während **Virtual_READ `0x0896/2` = `c800`** (20,0 °C) ist.
- **Physisch `0x089C/1`:** 79-mal `00`; **Virtual_READ `0x089C/1` = `03`**.
- **Physisch `0x0A5C/4`:** 79-mal `64646464`; **Virtual_READ `0x0A5C/4` = `00000000`**.

Daher würde ein `Physical_WRITE` auf die numerische **virtuelle** Raumtemperatur- oder Softwareindexadresse völlig andere RAM-Bytes verändern. Solche schreibenden Experimente sind ohne Datenzuordnung unbrauchbar.

## 4. Zusätzliche live getestete P300-KM-/KBUS-Funktionscodes

Die Funktionsnamen stammen aus dem globalen VitoSoft-Befehlskatalog und sind **keine** belegt zum exakten VDensHO1-Eventprofil gehörenden Dienste.

| P300-Funktionscode, Bezeichnung im globalen Katalog | Live-Read-Request | Reglerantwort |
| --- | --- | --- |
| `0x03 Physical_READ` | `0x1640/32` | `rc1`, RAM-Frame |
| `0x04 Physical_WRITE` | `0x1642/10` und `/16` mit originalen Frames | `rc1`, RAM-Rücklesung bestätigt |
| `0x31 XRAM_READ` | `0x1642/10` | `rc3`, Fehler `05` |
| `0x41 KMBUS_RAM_READ` | `0x1642/10` | `rc3`, Fehler `01` |
| `0x41 KMBUS_RAM_READ` | `0x00F8/8` | `rc1`, Identität `20c2000300000103` |
| `0x5D KBUS_MEMBERLIST_READ` | `0x0000/3` und `0x0001/3` | `rc3`, Fehler `05` |
| `0x61 KBUS_DIRECT_READ` | `0x0001/2` | `rc3`, Fehler `01` |
| `0x63 KBUS_INDIRECT_READ` | `0x0000/2` | `rc1`, `ff00` |
| `0x65 KBUS_GATEWAY_READ` | `0x0000/8` | `rc1`, `0af547b8cb346a95` |
| `0x65 KBUS_GATEWAY_READ` | `0x00F8/8` | `rc1`, `00ffcb34b8476a95` |
| `0x65 KBUS_GATEWAY_READ` | `0x0A5C/4`, `0x1642/10`, `0x27A0/1`, `0x7342/1` | jeweils `rc3`, Fehler `3101` |

`0x65` ist also tatsächlich auf einzelnen Eingaben erreichbar und liefert reproduzierbare Daten. Das ist **kein** Nachweis einer RX-Slave-Einspeisemöglichkeit: Für die Kandidatenadressen liefert es Fehler. **Kein KBUS_*_WRITE-Funktionscode wurde auf der Liveheizung blind ausgeführt.**

## 5. Reproduzierbarer nativer P300-Bridge-Treiber

`tools/wb2a-vitotrol-p300-bridge.py`:
- Importiert die schon getestete CRC16/Kermit-Original-Vitotrol-Framebibliothek.
- Nutzt den **bereits laufenden Original-Splitter** über vorhandenes MQTT/`optolink-debug`; kein zweiter serieller Port und **keine implizite Protokollumschaltung**.
- Vor Hardwaretest: exakte `20C2/0103`-Identität, native-P300-Konfiguration und Ausgangsregister abgleichen.
- Zulässig sind nur die vier originalen, exakt CRC-validen Klasse-11-V300-Antworten und der feste physische P300-RAM-Puffer `0x1642`; keine variablen RAM-Adressen, keine unbekannten Fernbedienungsbefehle.
- Mehrfaches Readback `Physical_READ 0x1640/32` und zwei zeitlich getrennte Softwareindex-/Raumtemperatur-/Sensorstatuskontrollen.
- Rückstellung von `A0=0`, `B0=0`, `0x7342=0` und Original-RAM-Backup auch bei im Prozess gefangenen Ausnahmen. Für SIGKILL/Hostausfall ist ein **unabhängiger Recovery-Timer** nötig. Der Treiber schaltet kein VS1/P300 um.
- `--execute` sendet nach exakt überprüfter bereits aktiver P300-Konfiguration; `--configure-type` bezieht den zuvor getesteten Type `0x74` ein. Ohne `--execute` wird ausschließlich ein JSON-Plan ausgegeben.
- Exit 4 bedeutet: technisch korrekt durchgeführter RAM-Einspeisetest, aber **keine** nachgewiesene Vitotrol-Akzeptanz. Exit 0 ist an zweimalig bestätigten Teilnehmerstatus samt aktivem Raumtemperaturwert 20,6°C gebunden.
- Die Begleittests `tests/test_wb2a_vitotrol_p300_bridge.py` simulieren echte Kommandostrings, verweigerte ungeprüfte Adressen, CRC-Fehler, abweichende IDs, fehlende Teilnehmerbestätigung und Write-/Readback-/Cleanup-Fehler.

Beispiel ausschließlich während **bereits nativ aktivem P300** und unabhängig armierter Recovery:

    sudo /opt/optolink/venv/bin/python tools/wb2a-vitotrol-p300-bridge.py --execute --configure-type

**Vollständig echter Hardwaretest** am 11.10.2026: `/tmp/wb2a-vitotrol-native-p300-bridge-live-20261011.json` auf dem LXC; vom Testtreiber als Misserfolg der Vitotrol-Anmeldung erfasst. Kein geheimes Hardware-Mitschriftmaterial ins Repository.

### Betrieb und Wiederherstellung

Das erste P300-Fenster lief 09:23–09:28 Uhr über Original-Splitter mit `vs1protocol=False`, keine Shadow-Instanz. Bei der temporären Systemd-Dienstpause ging die Definition des **transienten** ursprünglichen RPM-v2-Loggers verloren. Seine **19.502** Events in `/var/lib/optolink-research/rpm-passive-20261010` blieben vollständig erhalten. Am 11.10. 09:31 Uhr wurde aus dem unveränderten Quellskript eine **neue** passive Root-MQTT-Aufnahme als `optolink-wb2a-rpm-passive-resume-20261011.service` gestartet, Daten in `/var/lib/optolink-research/rpm-passive-20261011-resume`. Beide Teildatensätze bleiben getrennt und können später zusammengefasst werden. Geplantes Laufzeitende weiter 14.10., ca. 21:53 Uhr. Der zweite native P300-Test ließ den rein passiven Recorder **aktiv**, statt ihn erneut zu entfernen.

Vor dem zweiten P300-Fenster wurde ein unabhängiger zeitgesteuerter Originalrestore eingerichtet. Der erste Test stellte Original-Codierungen `A0/B0=00/00`, Type `00`, gespeicherte RAM-Bytes und Original-VS1-Dienst bereits um 09:28 Uhr erfolgreich wieder her. **Keine Behauptung dauerhafter Vitotrol-Akzeptanz.**

## 6. Nächster tatsächlich entscheidender Schritt

**Der Schreibkanal existiert und ist bewiesen.** Der ausstehende Entwicklungsblock ist nicht ein Moduswechsel, sondern ein tatsächlich aktivierter **KM-Bus-RX-Parser-/Teilnehmer-State-Commit**. P300-SRAM-Writes bleiben ohne nachgewiesenen RX-Trigger unwirksam. Die nächste Untersuchung muss eine zusätzliche Firmware-RX-Pending-/Nachrichtenqueue-/Dispatcherbedingung oder eine Optolink-zugängliche äquivalente Teilnehmer-RPC identifizieren, ohne bloß virtuelle Datenpunktadressen mit physischen RAM-Adressen zu verwechseln. Physischer KM-Bus-Zusatzadapter bleibt außerhalb des Vorhabens.

## 7. Neue aktive Real-Discovery: erstmals Masterfrage erkannt und dynamisch beantwortet

Am 11.10.2026 **09:39:41–09:41:15 Uhr** lief ein zusätzlicher, zeitlich
begrenzter Python-Prototyp gegen **genau den bereits bestehenden nativen
P300-Splitter**. Unter real bestätigtem `A0=01 / B0=03 / Remote-Type=74`
wurde der **KM-Bus-Master-TX-RAM** bei `0x161A/32` wiederholt über
`Physical_READ (0x03)` abgefragt. Jedes Sample wurde auf CRC16/Kermit
und plausiblen Telegrammrahmen geprüft. Bei echter Klasse11-F8-Discovery
generierte die zuvor getestete originale V300-State-Machine die
B3-Identitätsantwort und legte sie mittels `Physical_WRITE (0x04)` im
SRAM-Empfangskandidaten `0x1642` ab; auf jeden tatsächlichen Write
folgte ein exakter physischer FC03-Rücklesevergleich.

**Gemessene RAM-TX-Header / Beobachtungen:**

| Framefamilie | Anzahl FC03-Messungen |
| --- | ---: |
| `01 00 B1` | **18** |
| `11 00 33` – **Vitotrol-Discovery!** | **2** |
| `20 00 B3` | **2** |
| Automatisch darauf erzeugte und rückbestätigte `00 11 B3`-Antworten | **2** |

Die **wirklich im eigenen WB2A-Master-TX-RAM beobachtete Anfrage** lautete:

    11 00 33 0A 01 01 F8 04 49 EF

Darauf antwortete unser Code jedes Mal mit dem originalen V300-Profil:

    00 11 B3 10 01 01 F8 11 F9 38 FA 01 FB 0A 1D B1

Beide Response-Bytes wurden bei `0x1642` vollständig zurückgelesen.
Die erste erkannte (von den aufgezeichneten FC03-RAM-Samples
**nicht** auf tatsächliche Draht-TX-Flanke rückführbare) Discovery wurde
nach **18,29 s** Beobachtungszeit registriert. Die Dauer der gesamten
gebundenen Untersuchung betrug rund **77,47 s** inklusive
Statusauslesen und Rückstellung. Es gilt nicht als zwei sicher separat
auf dem KM-Bus ausgesendete Anfragen: Das Master-TX-RAM könnte
dasselbe letzte Telegramm bei zwei Abtastungen gezeigt haben.
Ebenso ist die P300-Write-Latenz nicht mit einem physikalisch
gültigen KM-Bus-RX-Interrupt gleichzusetzen.

**Trotz exakter, auf eine reale Master-Discovery bezogener Antwort:**

    SWIndex_FB1 0x0A5C = 00 00 00 00
    RTS 0x0896          = C8 00    (Fallback 20,0 °C)
    Sensor 0x089C       = 03
    aktuelle Störung    = 00

Nach dem Versuch wurden `A0/B0/Type = 00/00/00` und der ursprüngliche
RX-Puffer vollständig zurückgeschrieben und verifiziert. Die
maschinenlesbaren privaten Live-Resultate liegen auf dem LXC in
`/tmp/wb2a-vitotrol-p300-master-poll-20261011.json`; das JSON zeigt
`staged_verified=2`, die beiden vollständigen Anfrage-/Antwort-Frames
und `no_uart1_rx_isr_verified=true`.

Der jetzt eingecheckte eigenständige Testtreiber
[`tools/wb2a-vitotrol-p300-master-follower.py`](../tools/wb2a-vitotrol-p300-master-follower.py)
enthält diese Reaktionslogik als reproduzierbaren Ablauf: nur
CRC-validierte Master-Slot1-Telegramme werden der State-Machine
übergeben; nur exakt bekannte Klasse11-Antwortframes dürfen
via FC04 bei `0x1642` ins RAM; anschließender Hardware- und
Teilnehmer-Readback und `finally`-Rollback. Ohne `--execute` ist
die CLI garantiert plan-only. Für abrupten Prozessabbruch ist
weiterhin ein unabhängiger Rückstelltimer zu schalten.
Synthetische Positiv-/Negativtests liegen unter
[`tests/test_wb2a_vitotrol_p300_master_follower.py`](../tests/test_wb2a_vitotrol_p300_master_follower.py).

**Technische Konsequenz:** Das fehlende Glied ist jetzt sehr präzise
isoliert: Die eigene WB2A-Discovery ist über P300 beobachtbar und
die richtige eigene Vitotrol-Antwort ist über P300-SRAM schreibbar.
Eine gültige Anmeldereaktion benötigt offenbar zusätzlich ein
firmwareseitiges **RX-Komplettsignal/ISR-/Queue-/State-Commit**, das
`Physical_WRITE` auf `0x1642` allein nicht auslöst.

Nach allen Phase-2-Tests lief `restore.sh` um **09:41:51–09:42:08 Uhr**
mit bestätigtem Original-Hauptdienst, `A0/B0/Type=00/00/00`,
SWIndex 0, aktueller Fehler `00`; die unabhängige Restore-Timer-
Reserve wurde erst nach bestätigter Rückstellung deaktiviert.
Der neue passive RPM-Beobachter blieb aktiv.

## Nachtrag: Die modellrichtigen Vitotrol-Hardwareversuche vom 11.10.2026

Die exakt zugeordnete VDensHO1-Codierung lautet **A0:1 = Vitotrol 200, A0:2 = Vitotrol 300**. Frühere V300-Frames bei A0:1 hatten daher einen Typkonflikt. Dies wurde direkt am Gerät aufgelöst: Original-V300-Antworten unter A0:2 sowohl vorausgefüllt als auch dynamisch nach Master-F8-Discovery; das V200-Referenzprofil unter A0:1, sowie V300-Follower unter A0:2/B0:3 **mit Typ `0x7342=74`**. In allen Varianten blieb die Controller-Fernbedienungskennung `00000000`, virtueller Raum `c800` und Sensor `03`. Es wurde weiterhin **kein tatsächlicher UART1-RX-Commit belegt**.

Der Kessel stand nach der letzten temporären nativen P300-Phase um **10:21:17 CEST** wieder im Originalbetrieb: `A0/B0/Type=00/00/00`, `vs1protocol=True`, `VS1_BETRIEB_OK`, passiver RPM-Logger aktiv. Vollständige Testmatrix einschließlich der durch den natürlichen Klasse01-Verkehr überschriebenen RX-Identitätsbytes: [wb2a-vitotrol-native-p300-variant-matrix-2026-10-11.md](wb2a-vitotrol-native-p300-variant-matrix-2026-10-11.md).
