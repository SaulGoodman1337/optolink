# WB2A / VDensHO1 / 20C2: Modellrichtige aktive Vitotrol-Tests am 11.10.2026

**Stand:** 11.10.2026, 10:21:30 Uhr CEST. Alle Livevarianten und die letzte unabhängige Rückstellung abgeschlossen. **Ziel: vollständige Vitotrol-Emulation allein über den bestehenden Optolink/P300.** Kein separater KM-Bus-Adapter. Die hier verwendeten Schreibvorgänge wurden direkt auf der tatsächlich angeschlossenen WB2A ausgeführt und nachfolgend kontrolliert rückgestellt.

## 1. Entscheidende Korrektur: A0-Codierung und KM-Bus-Kennung müssen zusammenpassen

Die **exakten**, bereits lokal SHA-geprüften VDensHO1-VitoSoft-Datenpunktdefinitionen geben für Heizkreis A1/M1 an:

| Virtual_WRITE / Virtual_READ `0x27A0` | Erwarteter Teilnehmer | Identität F8–FB |
| --- | --- | --- |
| `00` | Keine Vitotrol | keine |
| `01` | **Vitotrol 200** | öffentlich dokumentiertes Referenzmodell `11 34 00 05` |
| `02` | **Vitotrol 300** | **Originalhardware-Aufzeichnung** `11 38 01 0A` |

Der Großteil der bisherigen Versuche hatte **A0=01 mit Original-Vitotrol-300-B3-Frame** kombiniert und konnte deshalb selbst bei vorhandener RX-Dispatcherfunktion am Modellabgleich scheitern. Dieser Typkonflikt wurde **nicht nur in Tests, sondern am Kessel überprüft**: A0=02 wurde von der WB2A erfolgreich angenommen. Die Quellstärke unterscheidet sich: Die 300er-Identität ist ein echtes OpenV-Original-Vitotrol-TX-Telegramm, die 200er-Identität stammt aus öffentlichen Protokoll-/Gerätebeispielen, nicht aus unserem eigenen ausgebauten Originalgerät.

Das rekonstruierte konkrete Original-V300-Telegramm ist:

```text
Anfrage WB2A-Master:  11 00 33 0A 01 01 F8 04 49 EF
Antwort Vitotrol 300: 00 11 B3 10 01 01 F8 11 F9 38 FA 01 FB 0A 1D B1
Antwort Vitotrol 200: 00 11 B3 10 01 01 F8 11 F9 34 FA 00 FB 05 06 64
```

Alle drei Frames sind CRC16/Kermit-validiert. Der physische UART-Empfangsinterrupt wird durch den P300-Request nicht nachweislich ausgelöst.

## 2. Native-P300-Implementierung (ohne Shadow oder periodischen VS1-Wechsel)

Der bestehende, einzige produktive `optolink-splitter.service` wurde für begrenzte Zeit direkt mit `vs1protocol = False` betrieben; die Optolink-P300-Gerätekennung `20c2000300000103` wurde aus dem echten Kessel zurückgelesen. Der bereits vorhandene `optolink-debug`-Kommandoweg steuert ausschließlich den Originalprozess an und öffnet **keine** zweite serielle Schnittstelle.

Der neue Code umfasst:

- `tools/wb2a-vitotrol-p300-bridge.py`: exakt bekannte Original-V300-Replies, P300-FC04 an RX-RAM `0x1642`, unmittelbarer FC03-RAM-Readback, echte virtuelle Teilnehmer-/Raumtemperatur-/Sensorstatusprüfungen, eingeschränkte originale Codierungen und wiederhergestellter SRAM-Snapshot.
- `tools/wb2a-vitotrol-p300-master-follower.py`: passiver FC03-Blick auf den aktuellen TX-Frame des Reglers `0x161A`, CRC-validiertes F8-Discovery-Matching, dynamische originale B3-Antwort direkt auf das konkret gesehene Mastertelegramm, `A0=02` für V300, danach vollständige Rückstellung.
- `tools/wb2a-vitotrol-p300-rx-preseed.py`: nur bekannte B3-Identitäten, **bereits vor dem Einschalten von A0/B0** physisch in `0x1642` geschrieben. Danach Snapshots bei `0x161A`, `0x1640`, `0x0B60` und `0x1660` sowie die virtuellen Register `0x27A0`, `0x27B0`, `0x7342`, `0x0A5C`, `0x0896`, `0x089C`, `0x5738`. Getrennte, quellenscharfe Varianten `--variant v300_original` (A0:2) und `--variant v200_reference` (A0:1).
- `tools/wb2a-vitotrol-p300-live-compare.py`: vollständig **offline** arbeitender Vergleich der originalen JSON-Liveberichte mit harten Rückstell-/Modell-/Softwareindex-/Sensorstatus-Prüfungen. Ein erfolgreicher physischer SRAM-Write ist **niemals** gleichbedeutend mit `remote_accepted`.

### 2.1 Tatsächlich gewonnene Livebelege

| Liveexperiment | A0 / B0 / Type | Beobachtungen | Ergebnis |
| --- | --- | --- | --- |
| V300-Original-B3 vor Remote-Aktivierung, **historisch falsche Codierung** | `01/03/74` | 8 RAM-/Datenpunkt-Snapshots; 1 Klasse11-Discovery-View; B3 nach dem ersten Snapshot durch Klasse01-B1 ersetzt | **Nicht registriert**; nachfolgend wieder `00/00/00` |
| Original-V300-B3 vor Remote-Aktivierung, **richtiges Gerät** | `02/03/00` | 5 Snapshots; 1 Klasse11-Discovery-View; B3 im ersten, danach normaler Klasse01-B1-RX-Frame | **Nicht registriert**; korrekt rückgestellt |
| Original-V300-B3 **nach echter Master-Discovery** dynamisch erzeugt | `02/03/00` | 3 identische CRC-validierte Discovery-TX-RAM-Views, 3 originale B3-FC04-Writes mit 3 identischen FC03-Readbacks | **Nicht registriert**; korrekt rückgestellt |
| Referenz-V200-Identität vor Remote-Aktivierung | `01/03/00` | 4 Snapshots; 1 echte Klasse11-Discovery-View; normales Klasse01-RX bereits beim ersten vollständigen Snapshot | **Nicht registriert**; korrekt rückgestellt |

**Harte Reglerprüfung bei allen vier Läufen:** `SWIndex_FB1/0x0A5C=00000000`; virtuelle Raumtemperatur `0x0896=c800` (20,0 °C Ersatzwert); virtueller Sensorstatus `0x089C=03`; nach Rückstellung Fehler `0x5738=00`. Der physische Empfangspuffer war nach P300-FC04 zunächst jeweils bytegenau schreibbar und wurde im späteren Betrieb durch normale Klasse01-Kommunikation überschrieben. Das belegt RAM-Zugriff, **nicht** dass ein KM-Bus-Slave-Telegramm zur korrekten Zeit auf dem Draht lag oder vom Hardware-UART empfangen wurde.

**Private JSON-Originalbelege auf dem LXC** (keine Binär-/Live-Dumps nach GitHub exportiert):

```text
/tmp/wb2a-vitotrol-rx-preseed-live-20261011-1004.json
/tmp/wb2a-vitotrol-a0-02-v300-preseed-live-20261011.json
/tmp/wb2a-vitotrol-a0-02-v300-follower-live-20261011.json
/tmp/wb2a-vitotrol-a0-01-v200-preseed-live-20261011.json
/tmp/wb2a-vitotrol-4way-comparison-20261011.json
```

Die fünfte Datei wurde ausschließlich offline aus den ersten vier erzeugt und ist reproduzierbar mit:

```bash
python3 tools/wb2a-vitotrol-p300-live-compare.py \
  --preseed legacy_v300_a0_01:/tmp/wb2a-vitotrol-rx-preseed-live-20261011-1004.json \
  --preseed v300_original:/tmp/wb2a-vitotrol-a0-02-v300-preseed-live-20261011.json \
  --preseed v200_reference:/tmp/wb2a-vitotrol-a0-01-v200-preseed-live-20261011.json \
  --follower /tmp/wb2a-vitotrol-a0-02-v300-follower-live-20261011.json
```

### 2.2 Aussagekraft der RX-/TX-Deskriptoren

In beiden 200/300-Preseed-Läufen standen in jedem RAM-Lesefenster bei `0x0B6D` weiterhin `42 16 0A FE`, in der Nähe `0x166A` `06 00 01`. Bei einer tatsächlichen Master-F8-Discovery zeigt die Standspeicherprobe `0x0B6B=0A` (mehrfach) oder `0B` (beim V200-Referenzlauf). Im historischen Archiv mit 79 vollständigen SRAM-Snapshots kommen dieselben Indexwerte allerdings **auch bei Klasse01-Masterframes vor**. Das ist allenfalls ein dynamischer Scheduler-/Queue-Hinweis, **noch kein RX-Ready-IRQ-Bit**.

Die wiederholte Original-Identität wird nach `Physical_WRITE` auf `0x1642` sichtbar und später von der natürlichen Klasse01-Busantwort `0001b10a010110fe23d8` ersetzt. Deshalb löst **bloßes SRAM-Preseeding** weder Teilnehmer-Liveness noch ein echtes UART-Receive-Ereignis aus.

## 3. Was der richtige nächste Funktionstest leisten muss

Wir haben nun am **konkreten lokalen WB2A-Master** die CRC-validierte Vitotrol-Klasse11-F8-Discovery gesehen und können die richtige Vitotrol-Antwort nachbilden und als RAM-Bytes ablegen. Was fehlt, ist der Übergang **RAM-Telegramm → Firmware-RX-Message-Queue/ISR → gültiger Klasse11-Teilnehmer → SWIndex/Sensor/Temperaturübernahme**. Frühere `A0:1`-Tests waren zusätzlich modellinkonsistent, aber der korrigierte `A0:2`-Test widerlegt den Modellfehler als alleinige Ursache.

Die **Firmware-Identität des tatsächlichen Controller-MCU**, sein UART1-RX-Vektor und ein von Optolink aufrufbarer KM-Bus-Receive-/Process-Commit-Dienst bleiben unbekannt. Weder die Bytefolge `42 16 0A FE` noch `0B6B=0A/0B` sind dokumentierte Schreib-/ISR-Trigger. Ein physisch korrekt getimter on-wire Slave wurde im gesamten Versuch **nicht** implementiert.

Nächster bewertbarer Entwicklungsschritt: Nachweis eines vorhandenen internen Firmware-/P300-Gateway-Dispatch-Eingangs für vollständige Klasse11-Slave-Frames oder einer zugänglichen RX-Ereignisqueue. Danach exakten Zustand bei zweimaligen Reglerauslesungen prüfen. Keine Verwechslung von Virtual_READ-Adresse und Physical_RAM-Ziel.

## 4. Wiederherstellung und Betrieb

Alle native-P300-Livefenster liefen mit unabhängigem, im Voraus aktiviertem systemd-Rückstelltimer. Nach der Testserie wurde der originale `optolink-splitter.service` wieder mit `vs1protocol=True` gestartet und `VS1_BETRIEB_OK` bestätigt. A0/B0/Type stehen bei `00/00/00`, aktuelle Störung `00`, die RX-Buffer-Originalbytes wurden mit FC04 restauriert. Der separate passive RPM-Recorder `optolink-wb2a-rpm-passive-resume-20261011.service` blieb aktiv. Die Timer wurden nach bestätigter Wiederherstellung deaktiviert. Das bisherige echte Produktions-§main§ wurde weder gemergt noch neu deployed.

Der vollständige RC-/CRC- und P300-Befehlspfad ist im Schwesterbericht [Native P300: aktive Vitotrol-Tests](wb2a-vitotrol-native-p300-active-2026-10-11.md) beschrieben.

## 5. Ergänzender Original-V300-Follower mit Remote-Type 74 (10:18–10:20 Uhr)

Auch die noch fehlende Kombination **A0=02 / B0=03 / Typ `0x7342=74`** wurde direkt an der WB2A erprobt. Der native P300-Follower beobachtete **2 CRC-gültige Klasse11-Discovery-TX-RAM-Ansichten**, erzeugte zweimal die vollständige originale V300-B3-Antwort, schrieb sie per P300-FC04 nach `0x1642` und bestätigte die Bytes mit FC03.

Master-TX-RAM-Zählung: Klasse `010031` einmal, `0100b1` 28-mal, `110033` zweimal, `2000b3` einmal. Die beiden Discovery-RAM-Ansichten können dasselbe Mastertelegramm wiedergeben und sind keine bestätigten zwei elektrischen KM-Bus-Anfragen.

**Beide nacheinander ausgeführten virtuellen Reglerprüfungen** unter `A0/B0/Type=02/03/74` ergaben **SWIndex_FB1 `00000000`**, **RTS `c800`**, **Sensor `03`**, **aktueller Fehler `00`**. Also weiterhin **keine akzeptierte Vitotrol**. Nachher A0/B0/Type `00/00/00` und originale erste 16 RX-Bytes bestätigt. Privates Live-JSON: `/tmp/wb2a-v300-a02-type74-follower-20261011.json`, negative Anmeldung = Exitcode 4.

**Letzte unabhängige Rückstellung:** 10:21:00–10:21:17 CEST. Der reguläre Einzelport-Splitter läuft wieder mit `vs1protocol=True`, `VS1_BETRIEB_OK`. A0/B0/Type `00/00/00`; SWIndex null; kein aktueller Fehler; fortgesetzter passiver RPM-Logger aktiv. Der zeitgesteuerte externe Rücksteller wurde erst nach erfolgreicher Verifikation deaktiviert.

## 6. Zusätzliche P300-Physical_READ-Prüfung hoher 16-Bit-Adressen

Die fest adressierten lesenden Requests `FC03/32` an `0x8000`, `0xE000`, `0xF000`, `0xFFE0` wurden vom Regler angenommen. Es kamen jedoch ausschließlich **16 identische Zweibyte-Wörter** zurück: `5498` × 16 bei `0x8000`, `0xE000` und `0xFFE0`, sowie `5497` × 16 bei `0xF000`. Das ist kein plausibel nachgewiesenes 20-Bit-MCU-Programm-ROM und **kein** UART1-Interruptvektor. Die positiven Read-Statuscodes beweisen nur, dass der P300-FC03-Dienst diese Adressen als Eingabe akzeptierte, nicht dass dort gültiger physischer ROM-Inhalt lag.
