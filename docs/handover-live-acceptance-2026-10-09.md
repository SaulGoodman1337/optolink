# WB2A read-only Hardware-Akzeptanz: Single-owner Fast-Return v1

**AUSDRUECKLICHER GERÄTETEST: NIE automatisch durch CI.** Nur nach ausdrücklicher Betreiberfreigabe. Die normale Ausführung ohne `--execute` ist inert. **Kein Test bei laufendem RPM-/P300-Logger**. Der Prober verweigert den Start, bevor der erste Dienst gestoppt wird, wenn Forschungseinheiten/Prozesse aktiv sind. Keine unbekannten OpCodes und keine Schreibkommandos.

## Ziel und Änderungen gegenüber dem bereits geprüften 4,610-s-Prober

- **Ein vollständiger Durchgang** aus ursprünglich produktivem VS1 nach verifiziertem P300 und zurück nach verifiziertem VS1; kein repetitives Dreifach-Messen.
- P300-Identität `20C2` und Software `0103` werden in `verify_p300()` exakt geprüft. Der zweite unmittelbar nachfolgende **redundante** P300-Identitätsread entfällt.
- VS1-Rückkehr mit **einem ENQ** (bereits erfolgreich auf dieser WB2A gemessen). **Gerätekennung, Software, P80 und P06** werden im VS1-Rückweg geprüft. P80/P06 werden nur aus dieser **unmittelbar vorangegangenen** Verifikation in die Ergebniszeile übernommen (Alter höchstens 0,75 s); weitere separate Reads erfolgen für P09/P87. Keine wiederverwendeten alten Sitzungen nach EOT.
- Zeitstempel pro *einzelnem* `0x05` aus dem ungebündelten Reader und für Phasen. Hostzeiten einschließlich USB/Kernel/Jitter, **keine Leitungs-/Controller-Uhr**. Der alte zusammengefasste `RX 060505` wird nicht als simultan interpretiert.
- Cold Setup und unabhängiger Recovery-Pfad benötigen weiterhin konservativ **zwei ENQs**. Fehler in Fast-Return werden nicht als Erfolg mit stiller Recovery maskiert.
- Genau bekannte feste Telegramme (VS1-Identität, Software, GFA P80/P06/P09/P87, P300-Identität, Software und EOT/START/ACK). **Keine** RAM-Reads/Writes, RPCs, Codierungen, Gas-/Pumpenkommandos oder GFA-C9-Versuche.

Der Gewinn durch entfernte doppelte Reads ist **eine Software-Hypothese** und kein gemessener Gerätevorteil. Der Test kann über/unter 4,61 s liegen, weil der Umfang der Identitäts- und GFA-Verifikation gegenüber dem historischen Probeformat unterschiedlich segmentiert ist. **Keine neue ENQ-Umgehung und kein erwarteter sub-4-s-Effekt.**

## Vorbedingungen und Zustandsabsicherung

- Nur Optolink LXC mit produktivem unverändertem VS1 unter `/opt/optolink` und bereits installiertem pySerial. Original `/opt/optolink` wird **nicht** beschrieben.
- `/root/p300-trial-work/project` und `optolink-p300-migration` bleiben unangetastet. Auf separatem GitHub-Forschungsbranch testen, nicht aus einem laufenden RPM-Checkout.
- Der Vorcheck verweigert laufende/unklare P300-/RPM-Systemd-Units oder Prozessnamen, eine nicht passende Originaldienst-Workdir, einen anderen/aktiven Portbesitzer nach dem kontrollierten Dienststopp, fehlende Python-Venv oder geänderte Runtime-Settings.
- Bereits aktive Originaldienste werden vor dem Stopp in einer privaten Session festgehalten; Stop-Intent liegt vor jedem Stopp persistent auf Platte. Supervisor via `systemd-run --wait` registriert **ExecStopPost vor** jeglichem Service-Stopp. Ein separater Prozess stellt auch nach Worker-Crash/SIGKILL mit zwei ENQs wieder VS1 her und startet Originalsplitter **vor** Hilfsdiensten. Er meldet den Fehler, wenn dies scheitert.
- Der Worker hält ein Linux-Serial `exclusive=True` sowie `TIOCEXCL` und eine kooperative Port-Lease. `flock` allein verhindert keine fremden Prozesse; echte Owner-Prüfung erfolgt vor und nach Portöffnung.
- SIGTERM wird nicht mitten im aktuellen Telegramm als Python-Exception geworfen; der Supervisor läuft unabhängig vom Worker.
- Der *absolute* Testschluss ist erst erfolgreich, wenn nach ExecStopPost auch produktive MQTT-GFA-P80/P06-Reads frisch validiert werden. Keine bloße `active`-Meldung als Healthbeleg.

## Einmalige Ausführung

Im Optolink LXC als root, **nur wenn kein anderer Logger läuft**. Die genaue, durch CI grün bestätigte Commit-SHA muss vor Ausführung festgelegt sein. Nie blind `git pull` in den aktiven RPM-Worktree; einen neuen temporären Checkout verwenden.

```bash
# Der Betreiber ersetzt PINNED_SHA durch den im Chat genannten CI-grünen Commit.
set -euo pipefail
d=$(mktemp -d /tmp/optolink-handover-real.XXXXXX)
git clone -q --depth 1 --single-branch -b optolink-handover-acceleration \
  https://github.com/SaulGoodman1337/optolink.git "$d/repo"
cd "$d/repo"
test "$(git rev-parse HEAD)" = PINNED_SHA
/opt/optolink/venv/bin/python -m unittest discover -s tests -p 'test_handover*.py' -q
/opt/optolink/venv/bin/python -u tools/handover_acceleration/live_probe.py --execute --accept-telemetry-pause
```

Ohne `--execute --accept-telemetry-pause` zeigt der Prober lediglich einen Plan. Mit den Flags werden Dienste zeitweilig **bewusst pausiert**, nur wenn keine Konkurrenzforschung läuft. Vorher unbedingt laufenden RPM-Logger regulär beenden lassen. **Nicht stoppen, nur um diesen Versuch schneller auszuführen.**

## Ergebnisartefakte und Abbruch

Unter `/root/p300-trial-work/handover-acceleration-live-results/run-*` liegen `state.json`, `measurement.json`, `recovery.json`, `summary.json`, source SHA256 Manifest und ENQ-Ereignisse. Console `RESULT=PASS_VERIFIED_READ_ONLY_REAL_HANDOVER` verlangt gültige Identitäten und GFA, bestätigten VS1-Link, wiederhergestellte ursprüngliche Dienste sowie frische MQTT-Reads. `RESULT=FAIL_OR_NOT_VERIFIED` ist ein Stop-Signal, **nicht** erneut identisch ausführen; zuerst Recoveryprotokoll auswerten.

Bei unerwartetem `FAIL`, fehlender `summary.json` oder blockierter Recovery **keinen zweiten seriellen Prozess öffnen**. Eine separate Konsolenprüfung von `systemctl` und der Session-Protokolle durchführen, vor allem laufende Portbesitzer ausschließen. Ein fehlgeschlagener Restore kann manuell ein konservatives Backup-/Service-Restore-Runbook erfordern. Kein automatischer Loop von Hardwareversuchen.

## Test- und Quellenverweise

Offline Regression: `python -m unittest discover -s tests -p 'test_handover*.py' -q` (lokal 77/77 vor CI). Neben aktuellen Tests werden originale konservative Restorebausteine aus dem unveränderten, **Git-Blob-gepinnten** `tools/wb2a-handover-probe.py` (`006c3c75f6e5e0dc3f564156985912bffb1d9bdc`) in `tools/handover_acceleration/legacy_probe.py` kopiert. Dieser Quellstand wurde aus dem Forschungsbranch gelesen, **ohne** ihn zu verändern.

Weitere Messbelege: `docs/handover-acceleration-research-2026-10-09.md`, `docs/handover-timed-peer-offline-2026-10-09.md`. Ein erfolgreicher Offline-/HW-Test ist keine Produktivfreigabe, Pumpen-RAM-Kontrollfreigabe oder Hinweis auf einen unbekannten Fast-Switch-Befehl.
