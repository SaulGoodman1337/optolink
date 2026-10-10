# Vitodens 200 WB2A: Acht-Fenster-Live-Soak, MQTT/TCP-Last und SIGKILL-Recovery

**10. Oktober 2026, 18:19–18:32 CEST.**
Hardware `optolink-splitter` (Debian 13), originaler einziger Optolink-Portbesitzer:
`optolink-splitter.service`. Alle Controllertransaktionen in dieser
Abnahme waren **read-only**. Kein Heizungsparameter und kein RAM-Wert geschrieben,
kein GitHub-Merge, keine dauerhafte Aktivierung.

## A. Längerer Live-Soak: PASS

Root-eigene gestagte Quellen:
`/var/lib/optolink-hybrid/releases/premerge-20261010-soak8-v2`,
**39** SHA256-gebundene Laufzeitdateien, Original unter
`/opt/optolink` nicht überschrieben.
Eigene Session:
`/var/lib/optolink-hybrid/canary-sessions/run-20261010T161928Z-311617`.

Systemd-Canary mit festem Profil `--soak-eight`: Ziel acht verifizierte
automatische VS1→P300→VS1-Hardwarefenster; reine FC01-Identität
`20c2`, FC03 `0x0F20/32` und `0x1C60/32`, danach echte
VS1-GFA P80 und P06; unabhängiges `ExecStopPost` und
`RuntimeMaxSec=800` als harte Begrenzung.

| Nr. | Zeitpunkt CEST | Handover ms | P300-ID | P06 nach VS1 | FC03-Blockgrößen |
|---:|---|---:|---|---|---|
| 1 | 18:20:54 | 5324.969 | `20c2` | `00` | 32 + 32 Bytes |
| 2 | 18:21:59 | 5411.123 | `20c2` | `00` | 32 + 32 Bytes |
| 3 | 18:23:05 | 5468.655 | `20c2` | `00` | 32 + 32 Bytes |
| 4 | 18:24:11 | 5342.461 | `20c2` | `00` | 32 + 32 Bytes |
| 5 | 18:25:16 | 5390.016 | `20c2` | `00` | 32 + 32 Bytes |
| 6 | 18:26:22 | 5364.905 | `20c2` | `93` | 32 + 32 Bytes |
| 7 | 18:27:57 | 5316.966 | `20c2` | `53` | 32 + 32 Bytes |
| 8 | 18:29:03 | 5326.064 | `20c2` | `53` | 32 + 32 Bytes |

In allen acht Fenstern war VS1 P80 nach Handover `20`, P06
ungleich `FF`. Das tatsächliche Journal dokumentiert um
**18:27:22** und **18:27:37** zwei legitime Verweigerungen
`HYBRID_RUNTIME_REFUSAL PENDING_LEGACY_WORK`, während reguläre
MQTT-/TCP-Anfragen anstanden. Das siebte Fenster wurde nach deren
Abarbeitung nachgeholt, ohne eine neue serielle Verbindung zu eröffnen.

Resultat:
`PASS_EIGHT_VERIFIED_CONTINUOUS_WINDOWS`, `event_count=8`,
`live_producer_attested=true`; Launch-Ausgabe
`HYBRID_CONTINUOUS_RESULT.result=PASS`, Exitcode `0`,
Laufzeit **9 min 47,832 s**.

### Netzwerk-Leseprobe unter gleichzeitiger echter Last

Ein begrenzter, gesonderter Requestgenerator schickte ausschließlich
GFA-Leseanfragen P80 `0x4050` und P06 `0x4006` über den bestehenden
Splitter, ohne den seriellen Port zu öffnen:

- **31/31 MQTT-Abfragen** erfolgreich.
- **31/31 TCP-Abfragen** erfolgreich, an `localhost:65234`.
- **62/62 gesamt**, kein Fehler oder Timeout.
- Maximale beobachtete Antwortzeit **5350,1 ms**,
  Mittelwert **1137,6 ms**. Zeitmessung End-to-End am Client.
- Rohprotokoll:
  `/tmp/hybrid-soak8-v2-readload-20261010.ndjson`
  (62 NDJSON-Einträge); Laufprotokoll
  `/tmp/optolink-hybrid-soak8-v2-real-20261010.log`.
- Alle fünf externen Writer waren während der Abnahme
  root-eigenen Prozessquellen zugeordnet und SHA256-/PID-attestiert.
- Die synthetische Writer-Burst-Regression überprüfte separat
  **25 MQTT- und 25 TCP-Kommandos**, die während einer *simulierten*
  P300-Sperre zurückgehalten und danach FIFO-konform wieder freigegeben
  wurden. Diese Kommandos wurden **nicht** an die Heizung geschickt.

### Unabhängiger Erfolgs-Rollback

Nach dem achtfachen Soak meldete Systemd:
`PASS_ORIGINAL_SERVICES_RESTORED`, `errors=[]`.
Alle sechs hybriden Drop-ins entfernt, Enrollment-Manifest gelöscht,
persistenter P300-Marker leer. Splitter, Party-Emulator,
Schedule-Manager, Maintenance-API, Serviceprogramme und
Clock-Sync-Timer alle `active`; Pump-Override `inactive`.
Nach Rückkehr echte GFA: P80=`20`, P06=`53`.

## B. Crash-Test des separaten Supervisors: PASS

Die erste geplante Crash-Vorprüfung verweigerte den Test korrekt, weil
die produktive Clock-Sync-Einheit gerade lief. Es fand kein Eingriff statt.
Nach Ende des Clock-Sync-Fensters folgte eine neue isolierte
Standard-Canary-Session:
`/var/lib/optolink-hybrid/canary-sessions/run-20261010T163030Z-316575`.

- **18:30:50 CEST:** `hybrid read-only automatic dispatcher admitted`.
- **18:31:06 CEST:** nach Kontrolle von Zustand
  `AUTO_HARDWARE_CANARY`, leerem Lock und laufenden Diensten gezielt
  `systemctl kill --signal=SIGKILL --kill-whom=main optolink-hybrid-continuous-canary.service`.
- Getöteter PID **316591**, separater Python-Canary-Supervisor.
  Produktiver serieller Hauptprozess PID **316747** wurde **nicht** getötet.
  Kein P300-Fenster war bei diesem Versuch aktiv.
- Systemd protokollierte tatsächlichen abrupten Exit
  `code=killed, status=9/KILL`; `ExecStopPost` lief
  **ohne Einwirken des getöteten Python-Supervisors**.
- Recovery-Beleg `recovery.json`:
  `PASS_ORIGINAL_SERVICES_RESTORED`, `errors=[]`, P80=`20`,
  P06=`53` über originale GFA-Hardware.
- Anschließend wieder alle sechs produktiven Dienste/Timer `active`,
  Pump-Override `inactive`, keine Drop-ins oder Enrollment-Datei,
  persistenter Marker 0 Bytes. Tatsächliche erneute unabhängige
  MQTT-GFA-Abfragen P80=`20`, P06=`53` erfolgreich.

Das erwartete Systemd-Ergebnis der **getöteten Versuchseinheit** war
`Result=signal`, nicht ein erfolgreich beendeter Worker.
Der **unabhängige Recovery-Pfad** selbst hat bestanden. Dieser Test
beweist noch **nicht**, dass ein SIGKILL des seriellen Hauptprozesses
mitten in einem laufenden P300-Frame bzw. beim Reboot abgesichert ist.

## C. Entwicklungs- und Testbestand

- Neuer fester `--soak-eight`-Profilmodus (8 Fenster,
  `WATCH_SECONDS=710`, `RuntimeMaxSec=800`), Standardmodus unverändert.
- `journalctl --grep` unter Debian 13/systemd 257:
  Exitcode `1` ohne Treffer und ohne stderr ist **kein Journalfehler**.
  Der erste verlängerte Canary wurde dadurch fälschlich noch vor
  Hardware-I/O abgebrochen; eigenständige Wiederherstellung funktionierte.
  Version v2 behebt die Unterscheidung und liefert den obigen Hardware-PASS.
- Gesonderter simulierter 50-Request-Burst für
  die MQTT-/TCP-Eingangsbarriere; keine physischen Parameter-Schreibtests.
- Vollständige `test_handover*.py`-Regressionen auf Debian 13/Python 3.13:
  **495/495 PASS**.
- Drei geänderte Dateien:
  `tools/handover_acceleration/continuous_canary.py`,
  `tests/test_handover_continuous_canary.py`,
  `tests/test_handover_ingress_epoch.py`.
- Original-Hauptquelle unverändert SHA256
  `f66b5a3eea0941f821c53bcf169b4cadff7a17418ec22dde05ed810b39cf1765`.

## D. Stand der P300-Gebläsedrehzahl-Forschung

Bei den ersten fünf Fenstern: P06=`00` (0 rpm), P300-Byte
`0x0F20` und `0x1C76` jeweils `00`.
Fenster 6: nach Rückkehr P06=`93` (4410 rpm),
P300-Byte jeweils `54`. Fenster 7 und 8:
P06=`53` (2490 rpm), P300-Byte ebenfalls `54`.

Die beiden RAM-Bytes sind bislang konsistent zueinander, aber
`RAM = P06 + 1` ist **keine bestätigte allgemeine Formel**.
Die Umschaltdauer von ca. 5,3 s kann bei beschleunigenden/abbremsenden
Gebläsen unterschiedliche Zeitpunkte vergleichen. Sinnvoller
Folgetest: synchronisierte echte P06-GFA-Lesungen unmittelbar vor
und nach dem P300-Fenster mit enger zeitlicher Obergrenze;
keinen Datenpunkt als validierte P300-RPM ausgeben.

## Noch ausstehende Merge- und Dauerbetriebskriterien

Trotz acht bestandener Fenster und abruptem Supervisor-Kill ist
**keine unbeaufsichtigte 24h-Freigabe** gegeben. Für einen dauerhaften
Hybridbetrieb fehlen insbesondere: echte, freigegebene
Schreib-/Readback-/Rollback-Transaktionen unter Parallelbetrieb,
Restart/Reboot- und Hauptprozess-SIGKILL-Tests mit
`P300_ACTIVE`-Marker, vollständige unabhängige Recovery nach
Stromunterbrechung, und ein administrativer Kill-Switch.

**Branch bleibt Forschung, PR #48 Draft/unmerged, aktueller
Produktivmodus nach allen Tests: ursprüngliches VS1.**
