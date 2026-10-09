# WB2A/20C2: umfangreiche Ein-Kommando-Handshake-Testkampagne

Datum: 2026-10-09. Forschungsbranch: `optolink-handover-acceleration`.

## 0. Bereits real getesteter EARLY-START: negatives Ergebnis

Betreibertranskript vom echten Optolink LXC, Commit
`6da76c3922be16ad6f8bbfd50ce8a67171f5910c`, Session
`run-20261009T194636Z-294918`:

- **130 lokale Offline-Tests bestanden** vor dem Hardwareaufruf.
- **Ein echter Versuch:** VS1 kalt mit zwei ENQs verifiziert, danach EOT und
  P300-START `16 00 00` bereits vor ENQ. **Keine rechtzeitige START-ACK**;
  `measurement_errors=["ProtocolError: RX deadline"]`, `unit_rc=1`.
  Der Versuch war **NEGATIV**, nicht ein schneller P300-Einstieg.
- Rückfall: `independent_recovery.attempted=true`, `.verified=true`,
  `services_restored=true`, `recovery_errors=[]`.
  Der Wiederherstellungsabschnitt im ENQ-Trace enthält ein separates
  **Zwei-ENQ** und ist **kein erfolgreicher normaler P300→VS1-Rückweg**.
- Nachher echte `PRODUCTION_HEALTH=PASS` über MQTT:
  P80 `1;0x4050;20`, P06 `1;0x4006;00`.
- Zwei ENQs in diesem Rückfall kamen **1621,454 ms** und **3859,414 ms**
  nach *dessen EOT*: Abstand **2237,960 ms**. Kaltsetup:
  **1744,381** und **3981,958 ms** nach seinem EOT. Der zeitliche Befund
  deutet auf Zustands-/Phasenabhängigkeit hin; daraus allein folgt keine
  firmwarefeste 2-s-Frist und keine Erlaubnis für beliebige Rohframes.
- `Service runtime: 18.083s` enthält Setup, Fehlversuch und
  Wiederherstellung und ist kein einzelner Protokollwechsel-Benchmark.

**Entscheidung:** `EARLY_P300_START_BEFORE_ENQ_350MS = NEGATIVE_ONE_RUN`.
Den identischen Early-START ohne neue Hypothese nicht wiederholen.

## 1. Was die neue Kampagne stattdessen misst

Die neue Kampagne kombiniert **zwei logisch verschiedene Hardwarestufen**.
Jede Stufe hat einen eigenen unabhängigen `systemd-run`-Supervisor,
`ExecStopPost`-Rollback und selektiven Restore; der zweite Versuch startet
nur nach dokumentiert erfolgreicher Stufe 1 *und* frischem produktivem
P80/P06-MQTT-Nachweis.

### Stufe A: 7 Kontrollmessungen ohne neue Telegramme

Eine offene, exklusiv besessene serielle Schnittstelle; zu Beginn einmal
konservativ VS1 mit **zwei ENQs** und identischen ID/SW/P80/P06-Checks.
Dann sieben gültige **VS1→P300→VS1**-Runden mit EOT/ENQ, P300-START/ACK,
P300-ID `20C2`/Software `0103`, einer ENQ auf dem bekannten VS1-Rückweg,
frischer VS1-ID/SW/GFA P80/P06 und separaten P09/P87-Reads.
Kein erfundener Frame, keine Parameteränderung.

| Versuch | zusätzliche Untätigkeit in VS1 **vor** EOT | zusätzliche Untätigkeit in P300 **vor** EOT |
|---|---:|---:|
| `control_a` | 0 ms | 0 ms |
| `vs1_idle_400` | 400 ms | 0 ms |
| `vs1_idle_1100` | 1100 ms | 0 ms |
| `p300_idle_400` | 0 ms | 400 ms |
| `p300_idle_1100` | 0 ms | 1100 ms |
| `both_idle_700` | 700 ms | 700 ms |
| `control_b` | 0 ms | 0 ms |

Unterschiedliche **EOT-Zeitpunkte** bei weiterhin bekannten Telegrammen
prüfen: Startet der beobachtete ENQ-Takt relativ zu EOT, oder läuft bereits
vor EOT ein anderes, phasenabhängiges Synchronisationsfenster? Ein
signifikanter Unterschied wäre ein Anhaltspunkt für einen gezielten
zeitversetzten Übergang, keine bereits bestätigte neue Fast-Switch-Lösung.

Es wird pro Runde in `measurement.json` protokolliert:
EOT→erste ENQ beider Richtungen (Host-Read-Zeit), Zeiten für P300-Einstieg,
VS1-Rückkehr, beide Untätigkeitsintervalle, Gesamtfenster sowie frische
GFA-Rohantworten. Der Quellcode verhindert eine Verwechslung des zweiten
Cold-Setup-ENQs mit einem ENQ aus den sieben Runden.
Alle sieben Runden müssen vollständig verifiziert sein; **jede**
Fehlantwort/CRC-/P80-/P06-/Timeout-/Stop-Bedingung bricht den laufenden
Durchgang sofort ab. Danach folgt die unabhängige Wiederherstellung.

### Stufe B: Genau eine andere experimentelle Hypothese

Nur wenn Stufe A inkl. Restore und produktivem MQTT-Healthcheck erfolgreich war:

1. Wieder konservativer VS1-Kaltstart (zwei ENQs).
2. Dokumentierter VS1→P300-Wechsel (EOT, ENQ, START, ACK, Geräte-/SW-ID).
3. **Experimenteller Rückweg:** EOT, 25 ms Pause, **bekannter VS1-STX/
   Geräte-ID-Lesebefehl unmittelbar vor ENQ**. Kein unbekannter Opcode.
4. Wenn innerhalb 350 ms exakte ID `20C2` empfangen wird:
   SW `0103`, P80 `20`, P06 gültig sowie P09/P87 streng lesen.
   Erst dann Erfolg und reale Messzeit dokumentieren.
5. Keine Identität / falscher Wert: negativer Versuch, einmaliger
   separater konservativer VS1-Restore (zwei ENQs), unabhängiger
   `ExecStopPost`-Supervisor und P80/P06-Nachprüfung.

Dies ist **nicht** der zuvor negative frühe P300-START. Unabhängige
Neustart-Aufnahme und Frischeprüfung nach jeder Stufe sind bewusst Teil der
Kampagne. **Keine automatischen Varianten-/Timeout-Retries**.

### Was die Befunde aussagen können

- Eingehende ENQs stets 1,9–2,1 s unabhängig vom vorherigen Idle-Offset:
  gestützt wäre ein EOT-/Sitzungs-relativer Timer oder eine diskrete andere
  Bedingung; **nicht** die universelle Unmöglichkeit von Fast-Switch.
- Deutliche verifizierte Abhängigkeit von Idle-/EOT-Phase:
  ein Kandidat für Timing-Optimierung. Erst nach Reproduzierbarkeit und
  Ausschluss von Host-/USB-Jitter als Verbesserung quantifizieren.
- Gültige frühe VS1-Identität, Software und GFA:
  eine schnellere Rückrichtung ist zumindest in diesem Lauf bewiesen;
  End-to-End-Zeit und Produktion müssen separat bestätigt werden.
- Frühe VS1-Identität bleibt aus: auch diese einzelne frühe
  Vor-ENQ-Variante ist negativ, **nicht** alle denkbaren Protokolleingänge.

## 2. Sicherheits- und Produktionsgrenzen

**Benutzergesteuerte Hardwareausführung:** Ohne die drei ausdrücklichen Flags
ist `campaign.py` inert und erläutert nur den Plan.

- Root-/LXC-Profil, korrektes Original-Workdir `/opt/optolink`, Einstellungen
  und aktive Dienste vor jedem Stopp prüfen.
- Kein laufender P300-/RPM-Logger oder konkurrierendes Research-Programm.
  Kein serielles Device gemeinsam öffnen. `exclusive=True`, `TIOCEXCL` und
  bestehende Prozess-/Portbesitzerkontrollen bleiben erhalten.
- Originaldienste vor dem ersten Stopp in persistenter, privater Session
  erfassen. Unabhängiges `systemd-run` mit `ExecStopPost` vor Stop-Intent;
  nach Recovery nur zuvor aktive Dienste wieder einschalten, Original-
  Splitter zuerst. Bei fehlender Bestätigung kein zweiter Hardwareversuch.
- Healthcheck verlangt **tatsächliche MQTT-Antworten** P80=`20`, P06
  Nicht-FF, Statuscode 1 und die korrekten Adressen; Exitcode 0 allein
  genügt nicht.
- Es gibt keine neuen freien Adressen, RAM-Writes, Rohkommandos,
  Codierungs- oder Heiz-/Pumpensteuerungseingriffe. `/opt/optolink`,
  `optolink-p300-migration` und PR #46 werden nicht aktualisiert.
- Auch eine dokumentierte Wiederherstellung kann nicht jede denkbare
  Firmware-, Kernel-, USB- oder Stromstörung vollständig ausschließen.

## 3. Ein Checkout, eine Testkampagne, ein Ergebnis

Der vollständige Befehl ist im zugehörigen Chat angegeben und enthält
**einen SHA-gepinnten Clone**, `unittest discover`, danach
`campaign.py --execute --accept-telemetry-pause --include-early-vs1`.
Kein ZIP, kein Copy/Paste einzelner Skripte, kein `git pull` im aktiven
RPM-Research-Worktree.

Ergebnisse unter
`/root/p300-trial-work/handover-acceleration-live-results/campaign-*/campaign.json`
und zugehörigen `run-*/{measurement,recovery,summary}.json`.

**Ergebnisetiketten:**

- `CAMPAIGN=ALL_STAGES_VERIFIED_SUCCESS`: beide Protokollhypothesen tatsächlich
  mit kompletter Geräte-/SW-/GFA- und Dienstprüfung erfolgreich.
- `CAMPAIGN=EARLY_VS1_NEGATIVE_BUT_RESTORED`: gültiger negativer
  experimenteller Befund, unabhängiger VS1-Restore und frischer
  produktiver MQTT-Health-Nachweis erfolgreich.
- `CAMPAIGN=STOP_*`, `CAMPAIGN=ABORT_*`: Zustand unsicher oder
  Protokoll-/Dienstprüfung nicht vollständig; keine automatische Fortsetzung.

## 4. Testqualität

Der gesamte ursprüngliche Forschungs-Testkorpus plus die neue
`tests/test_handover_campaign.py` deckt seriellen Frameablauf, falsche
Antworten, frühere und spätere EOTs, sieben in einer Sitzung abgewickelte
Runden, die Mehrfach-Worker-Übergabe, verlorenes/korruptes
Messprotokoll, unbestätigte Wiederherstellung, experimentelle
Negativbefunde, Restore ohne unnötiges zweites EOT sowie exaktes
Healthclient-Parsing ab. Zusätzlich sind 32 zufällig, aber deterministisch
variierte gültige siebenrundige P06-/P09-Pakete getestet.

**220/220 lokale Offline-Tests erfolgreich** (Python 3.13). Zusätzlich
muss die CI für den tatsächlich gepushten GitHub-Commit auf Python 3.11
und 3.12 erfolgreich sein, bevor der reale Befehl als verifiziert gilt.

Der Hardwareversuch ist naturgemäß **noch nicht durchgeführt**; keine
protokollseitige Beschleunigung behaupten, bis echte Geräteantworten
vorliegen. Physische Controller-/UART-Zeiten lassen sich mit
USB-/Hostmonotonzeiten nicht endgültig trennen.
