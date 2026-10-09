# WB2A: einmalige reale Abnahme des neuen Handover-Managers

**Status: VORBEREITET; NICHT AN DER HEIZUNG AUSGEFÜHRT.** Forschungsbranch `optolink-handover-acceleration`. Das Repository-/CI-Ergebnis ist kein Hardwareergebnis.

## Wozu dieser Versuch dient

Der erste echte Test des **neuen**, bisher nur mit Fake-Serial/PTY geprüften Single-Owner-Koordinators mit exakt einer vollständigen `VS1 -> P300 -> VS1`-Messrunde. Nicht Wiederholung des alten Probe-1.1.0-Quellcodes und **kein** Versuch eines unbekannten Fast-Switch-Kommandos. Er trennt drei ENQ-Phasen (zwei bei konservativer Kaltinitialisierung, eine für P300-Einstieg, eine beim schnellen Rückweg) durch einzelne `ReadOnlyWire.exact(1)`-Empfangszeitstempel. Die Kaltinitialisierung wird separat ausgewiesen, nicht als eingesparte Nutzzeit deklariert.

Die bekannten Hardwarewerte sind ~4,610 s für die frühere Ein-ENQ-Proberunde einschließlich GFA und ~6,863 s für die Zwei-ENQ-Baseline. Die neue Implementierung prüft zusätzlich Softwarekennung und P80/P06 beim VS1-Rückweg sowie einen zusätzlichen P300-Identitätsread; ihre absolute Zeit muss nicht identisch ausfallen. **Unter vier Sekunden ist kein begründeter Erwartungswert**. Ein Erfolg ist sichere Verifikation, eindeutige Phase-Timestamps und vollständig wiederhergestellter originaler VS1-Betrieb.

## Erlaubte Steuer-/Datenbytes

Nur die bestätigten EOT `04`, ENQ `05` als Empfang, P300 Start `16 00 00` / ACK `06`, P300 FC01-Identitäten (00F8/2→20C2, 778C/2→0103), VS1 `01 F7 00 F8 02` (20C2), VS1 `F7 77 8C 02` (0103), GFA/VS1 `6B 40 50 01`, `6B 40 06 01`, `6B 40 09 01`, `6B 40 57 01`. Prüfung vollständiger Frames, CRC, Bytezahl, Funktions-/Adress-/Softwareschlüssels und gültiger P80-/P06-Antwort. **Keine** unbekannten Opcode-, RPC-, RAM-, Regelungs- oder Schreibbefehle. P09 wird nicht als tatsächliche Drehzahl klassifiziert.

## Trennung von laufender Forschung

Dieser Probe-Runner hat einen separaten Ergebnisordner (`/root/p300-trial-work/handover-acceleration-live-results`), eigenen Systemd-Unit-Namen und neue Dateien. Er **verweigert** die Ausführung, wenn ein P300-/P06-/UART1-Logger per Unitstatus oder `/proc/.../cmdline` erkannt wird. Zusätzlich werden die vorhandenen Locks der bisherigen Handover-Forschung, der Portbesitzer-Scan, `pySerial(exclusive=True)` und Linux `TIOCEXCL` benutzt. Wenn eine Unklarheit oder Rennen auftritt: **abbrechen**, keinen Logger beenden, nicht einfach neu starten.

## Temporäre Dienstunterbrechung und unabhängige Recovery

Ein Hardwarewechsel erfordert exklusiven physischen Portbesitz. Für **diesen ausdrücklich auszulösenden einmaligen Versuch** werden ausschließlich die vorab dokumentierten und tatsächlich aktiven originalen Optolink-Units vorübergehend gestoppt; ihre vorherigen Zustände werden persistent gespeichert und in umgekehrter Reihenfolge wiederhergestellt. Keine Unit-Datei, Produktionsquelle oder Einstellung wird ersetzt. Der Haupteigentümer `/opt/optolink` wird als letzter gestoppt und als erster wiederhergestellt.

Der Live-Worker läuft als transienter Systemd-Dienst mit bereits beim Start registriertem **ExecStopPost**. Nach einem regulären Fehler oder SIGKILL führt ein **anderer Prozess** eine konservative 2-ENQ-VS1-Verifikation mit Originalgerätekennung/Software, P80=20 und gültigem P06 durch, sofern der Worker diese Rückkehr nicht bereits lückenlos bestätigt hat. Dann startet er den originalen Splitter, prüft dessen neue echte `enter main loop`-Bereitschaft und erst danach zuvor aktive Zusatz-/Writer-Dienste. Bei Recovery-Fehlern wird nicht als Erfolg gemeldet; writerabhängige Dienste werden bei fehlendem Splitter-Health nicht angefahren. System-/Kernel-/USB-Ausfälle oder Stromverlust lassen sich nicht absolut durch Software garantieren.

Anschließend werden frische produktive P80/P06-Reads über die bekannte `optolink-debug`-API versucht. Eine fehlgeschlagene Post-Restore-Abfrage macht das Gesamtresultat `FAIL_OR_NOT_VERIFIED`, auch wenn der Splitter als Prozess läuft.

## Abnahme vor Hardware-Zugriff

1. Nur beim Betreiber als root im LXC, wenn keine RPM-Messung läuft. Keine parallele Konsole darf den Port bedienen.
2. Download/Checkout des **exakt gepinnten** `optolink-handover-acceleration`-Commits in ein eigenes Verzeichnis (nicht `/opt/optolink` oder laufende Worktrees), Prüfung des Hashes.
3. Python-Offline-CI von `test_handover*.py`, einschließlich Test des Live-Workers und des separaten Recoverypfads: **grün** auf GitHub Actions Python 3.11 und 3.12 sowie lokal auf dem LXC.
4. Erst mit zwei ausdrücklichen Flags `--execute --accept-telemetry-pause` ist ein einzelner Hardware-Rundwechsel möglich. Ohne beide Flags nur `PLAN ONLY` bzw. Fehlerrückgabe.
5. Nach dem `systemd-run --wait`: Zustand und Ergebnisdateien ausgeben. **Kein automatischer zweiter Durchlauf nach einem Fehler**.

## Ergebnisartefakte

Pro privater Session: `state.json`, geprüfte Snapshots der ausführbaren Quellcodes, `measurement.json` (Stufenzeit, pro Byte empfangene `05`, alle erlaubten TX/RX, P06/P80), `recovery.json` (unabhängiger Link- und Dienst-Restore), `summary.json`. Diese bleiben in einem privaten `0700`-Ordner. Der Treiber erhält keinen neuen seriellen Schreibpfad jenseits bekannter Protokollkontrolltelegramme.

## Einschränkungen

Es gibt in dieser Umgebung **keine direkte SSH-/LXC-Verbindung** zum realen Gerät. Ein GitHub-Commit, CI-Lauf oder lokaler Fake-Test führt den Live-Aufruf nicht aus. Der Betreiber muss den freigegebenen, gepinnten Einzeiler am richtigen LXC auslösen. Eine Rückmeldung über `SUMMARY` und `RESULT` ist nötig, damit aus tatsächlichen Messwerten geschlossen werden kann. Keine Produktionseinbindung und kein PR-46-Merge.
