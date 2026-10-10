# WB2A / 20C2: realer Optolink-B0:3-Canary (10.10.2026)

**Evidenzstatus: LIVE-VERIFIED (Codierung und Rückstellung), KEINE Vitotrol-Emulation.**
**Architektur:** ausschließlich der bestehende Optolink/VS1-Hauptprozess; keine
neuen seriellen Portbesitzer, keine P300-Umschaltung, keine unbekannten
RAM- oder SFR-Schreibzugriffe. Dies war ein kurzer, beaufsichtigter,
einmaliger Hardwareversuch auf ausdrückliche Nutzerfreigabe. Er wird
nicht unbeaufsichtigt wiederholt.

## 1. Vorbedingungen und reale Baseline

Zwischen 23:29:45 und 23:30:01 Uhr CEST wurden mit dem **vorhandenen**
`optolink-debug request` über die laufende MQTT-/VS1-Schnittstelle
folgende reale Controller-Register gelesen:

| Adresse | Readback | Aussage |
| --- | --- | --- |
| `0x27A0/1` | `00` | Keine A1/M1-Fernbedienung konfiguriert |
| `0x27B0/1` | `00` | B0:0, witterungsgeführter Betrieb |
| `0x27B2/1` | `08` | B2-Raumeinflussfaktor |
| `0x27B5/1` | `00` | Keine raumtemperaturabhängige Pumpenlogik |
| `0x27E2/1` | `32` | Raumtemperaturkorrektur, 0,0 K |
| `0x0A5C/4` | `00000000` | Keine Vitotrol-Softwarekennung |
| `0x0896/2` | `C800` | Unvalidierter 20,0-°C-Raum-Ersatzwert |
| `0x089C/1` | `03` | Kein bestätigter gültiger Raumtemperatursensor |
| `0xA132/29` | Fehlercode Byte 28: `00` | Kein aktueller Controlleralarm |
| `0x7507/9` | `F9 20 26 10 09 05 07 08 48` | Bestehender Historieneintrag, nicht als neuer BC gewertet |
| `0x0800/2` | `5B00` | Außentemperatur 9,1 °C |
| VS1-GFA P80 / P06 | `20` / `00` | Lesepfad verfügbar |

Laufende Dienste `optolink-splitter.service` und
`optolink-wb2a-rpm-passive-20261010-v2.service` waren `active`.
Der Hybridstatus meldete `VS1_BETRIEB_OK`, Automatik deaktiviert,
kein fremder serieller Portbesitzer.

Die Baseline wurde im autorisierten LXC als lokale Forschungsdatei
`/tmp/wb2a-vitotrol-live-baseline-20261010T2330.txt` gesichert;
das private Rohlog wird **nicht** ins öffentliche GitHub-Repository kopiert.

## 2. Hardware-Coding-Canary mit unabhängigem Rückfall

Vor dem einzigen B0-Write wurde ein separater transienter
`systemd-run`-Rückstellauftrag installiert und als **aktiv** geprüft:
`wb2a-vitotrol-b0-recovery-20261010.timer`, Startverzögerung 100 s.
Dieser unabhängige Prozess war auf die **eine bekannte** B0-Adresse
und den bekannten Ausgangswert `00` beschränkt, sollte erst den
aktuellen Wert prüfen und nur bei `03` (oder fehlendem Readback)
den bereits zuvor bekannten Rückstellwert schreiben.

| Uhrzeit CEST | Tatsächlicher Vorgang | Nachweis |
| --- | --- | --- |
| 23:31:27 | Original-Owner, RPM-v2 und Rückstell-Timer aktiv; Baseline A0/B0/B5 erneut gleich | PASS |
| **23:31:31** | `writeraw;0x27B0;03` | `1;0x27b0;03` |
| **23:31:32** | `read;0x27B0;1` | `1;0x27b0;03` |
| 23:31:34..23:31:40 | Readbacks `0x0A5C=00000000`, `0x089C=03`, `0xA132` aktueller Alarm Byte 28=`00` | Vitotrol weiter **nicht** erkannt |
| **23:31:44** | Unmittelbarer Rückstellaufruf `writeraw;0x27B0;00` | `1;0x27b0;00` |
| **23:31:46** | Rückstell-Readback `read;0x27B0;1` | `1;0x27b0;00`, `IMMEDIATE_ROLLBACK_VERIFIED` |
| **23:33:03** | Getrennter systemd-Rückstell-Service automatisch ausgeführt | Trigger nach ~100 s |
| **23:33:04** | Service liest selbst `0x27B0=00`; kein zusätzlicher Write erforderlich | `ROLLBACK_VERIFIED_B0_00`, Exit 0, Result=success |

Der Test dauerte ungefähr 15 Sekunden ab B0-Write bis zur bestätigten
Rückstellung. Beide Rückfallwege wurden **real**, nicht nur simuliert,
verifiziert. Das gilt für die **B0-Codierung**, nicht für eine
ungeprüfte P300-UART1-RAM-Injektion oder andere Controllerobjekte.

Post-Canary:

- `read;0x27B0;1` erneut `00` (auch nach unabhängiger Recovery);
- `0xA132` aktueller Alarm Byte 28 weiterhin `00`;
- `read;0x0810;2` liefert `FE01` = **51,0 °C Kesseltemperatur**;
- `optolink-hybrid status` weiterhin `VS1_BETRIEB_OK`;
- Produktiv-Splitter und passiver RPM-v2-Logger weiterhin `active`.

Rohlog-SHA-256 (nur lokaler Nachweis):
`3dfc1f9dd60d22ec0231d18f7938d30e52a3b5ac1ce528464784e3ab32accce9`.
Pfad: `/tmp/wb2a-vitotrol-b0-live-trial-20261010-2331.log`.
Die unabhängige Recovery ist über systemd-Journal mit eigener PID
und Exit-Code nachgewiesen.

## 3. Interpretation ohne Überbehauptung

`B0:3` ist der reale Regelungsparameter für Raumaufschaltung in
Normal- und Absenkbetrieb. **Der B0-Write allein ist weder
Vitotrol-Discovery noch Raumtemperatureinspeisung.** Bei
`0x27A0=00`, `0x0A5C=00000000`, `0x089C=03` lag
nach dem erfolgreichen B0-Readback weiterhin keine gültige
Fernbedienung vor. Während des 15-Sekunden-Fensters trat kein
aktueller BC-Fehler auf; daraus folgt weder allgemeine
BC-Sicherheit bei A0-Aktivierung noch ein Nachweis unveränderter
hydraulischer/thermischer Dynamik.

Viessmann beschreibt einen Kommunikationsverlust der Vitotrol als
**Regelbetrieb ohne Fernbedienung**. Das ist keine Garantie, dass
bei unkontrolliertem Raumtemperatur-Override alle Pumpen-
und Vorlauftemperaturen unverändert bleiben. Deshalb wurde die
vorherige B0:0-Einstellung nach dem einmaligen Canary
wiederhergestellt.

**Blocker bleibt unverändert:** Lokaler UART1-RX-Parser/
`INTB + 0x50`, kontrollierter Optolink-Receive-State-Commit
und tatsächlich akzeptierte Vitotrol-Klasse `0x11` sind weiterhin
nicht nachgewiesen. Die ursprüngliche Original-V300-Offlineantwort
kann bytegenau erzeugt werden, wird aber vom realen Kessel
noch **nicht** als virtuelle Fernbedienung akzeptiert.

Kein aktives `0x27A0=1`, keine neue BC-Provozierung,
keine Raumaufschaltung über Nacht und keine Writes
in nicht verifizierte Controller-RAM-Bereiche.

## 4. Naechste Forschungs-Gates

1. Nachweis eines Controller-RX-Diensts oder ISR-State-Commit
   aus authentischer VDensHO1/20C2-Firmware oder Optolink-Trace.
2. Genaue, vom bestehenden Single-Owner abgesicherte
   Injection- und Controller-Rollback-Semantik im Offline-Harness.
3. Erst dann ein zeitlich begrenzter echter Vitotrol-Canary,
   mit Regler-Softwareindex, Raumtemp-Readback, Alarmhistorie
   und Rückfallüberwachung; ein auftretender BC ist zwar keine
   automatische Brennersperre, aber keine erfolgreiche Anmeldung.
4. Unbeaufsichtigte Nachtforschung nur mit vorhandenen
   historischen Daten, Code- und Regressionstests im Draft PR #52.

**Produktiver `main`-Branch und RPM-Forschung unverändert.**
