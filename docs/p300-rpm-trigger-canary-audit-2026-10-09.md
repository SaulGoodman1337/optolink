# Hardware-Canary freigegeben: RPM-Triggerlogger 9.10.2026

**Nur Aufgabe 1; PR #46 Draft/unmerged, Produktivweg VS1 unveraendert.** Dieser Bericht entstand aus einer unabhängigen Offline-Forensik des von Nutzer hochgeladenen Canary-Tarballs. Er beinhaltet **keine Live-LXC-Steuerung und keine weiteren GFA-Abfragen**.

## Provenienz / SHA256

- Private Datei: `p300-rpm-trigger-run-20261009T173532Z-292700-bundle.tar.gz`.
- Archiv-SHA256: `1107c9e99f1dc3ca0a12218a2f8c51016d922ab1974e0602bcd63e1f585bf30e`, **300.382 Bytes**.
- **24/24** Manifestdateien mit exakter Dateilaenge + SHA256 geprueft; 25 Tar-Mitglieder inklusive Manifest. Keine Doppelpfade/Symlinks/unzulaessigen Tar-Mitglieder. **7/7** in state.json verankerte Python-Quellhashes passend.
- Effektiver Git-/Sessionstand: `b795e9b4ad89ff7ce854746d588b5bfcd1818b08`, Modus `canary`, 300 Sekunden, eigener Systemd-Dienst `optolink-p300-rpm-trigger.service`.

## Unabhaengiger Raw-Frame-Audit

- **231** lueckenlose vollstaendige Messzyklen, **924/924** P300-Response-Frames. Je Zyklus FC01 `55D3/11` Status A, FC03 `0F20/32`, FC03 `1C60/32`, FC01 `55D3/11` Status B.
- **924/924** Anfragen: STX, FC, 16-bit Adresse, Laenge und Checksumme geprueft. **924/924** Antworten: ACK, STX, Framegroesse, MessageID 01, FC, Adresse, Laenge, Payload und Checksumme geprueft; Zeit-/Zyklus-/Ordinals korrekt.
- Core-BIN exakt **14.784 Bytes** = 231×64; fuer alle Zyklen direkte Payload-Gleichheit und SHA256 geprueft.
- `vs1.jsonl` 56 Eintraege, `trace.jsonl` 2914 Eintraege, `switch.jsonl` 2, `triggers.jsonl` leer. Alle beobachteten TX-Befehle entsprechen bereits dokumentierten VS1-Identitaets-/GFA-Leseoperationen, P300 FC01/FC03 plus P300-Identitaet und Steuerbytes EOT/Start/ACK. **Keine unbekannten Writes**.
- Alle 231 Zyklen: Kandidatenwerte `0F20=00`, `1C76=00`, Flame AUS; kein natuerlicher HIGH-Trigger. Das ist **kein RPM-Negativbefund**, sondern hinreichend fuer den konservativen Transport-/Restore-Canary.

## Abschluss / Freigabe

- Messstart 2026-10-09 **17:35:32 UTC**; Endzeit **17:40:41 UTC** (19:35–19:40 MESZ).
- Konfigurationsbudget 300s, Laufzeit insgesamt **309,142s**, P300-Stream **288,777s** (**>= 240s**), **231 Zyklen** (**>=30**).
- `observation_complete=true`, `data_quality=COMPLETE`, `errors=[]`, `signal=null`, `trigger_count=0`, `writes_issued=false`, `worker_vs1_restored=true`.
- VS1→P300 **2,186s**, P300→VS1 **4,323s**; beide `identity_verified=true`, `result=OK`.
- `recovery.json`: `systemd_result=success`, `services_restored=true`, `errors=[]`; genau sechs zuvor aktive Units/Timer wiederhergestellt (Splitter zuerst).
- `progress.json`: `state=RESTORED`, `p80_p06_production_health_verified=true`.
- Produktives MQTT nach Restore: GFA P80=`20`, GFA P06=`00` (gueltiger Stillstand, **nicht FF**). **HA-Entity-Frische nicht verifiziert**.
- **Entscheid: GO fuer manuellen Langlauf `bash tools/wb2a-p300-rpm-trigger.sh start 2`**, falls seit dem Canary kein konkurrierender Logger gestartet wurde und der lokale Produktiv-Health weiterhin besteht. Der Wrapper prueft vormaligen Canary/Exclusive Port/Source-Hashes nochmals. Kein Automatismus, keine globale RPM-Freigabe.

## Nachrangige Latenzforschungsnotiz fuer neuen, ISOLIERTEN Branch

**Nicht in laufende Task-1-Session eingreifen.** In dieser Canaryspur werden die Umschaltzeiten wieder ~2,186s VS1→P300 und ~4,323s P300→VS1 bestaetigt. Die Forschung vom 8.10.2026 ist bereits deutlich spezifischer:
- [Basis-/Single-ENQ-Live-Resultat](p300-goals-and-single-enq-result-2026-10-08.md): Zwei-ENQ-Vergleich **6,862980s**, nach **erfolgreichem einem ENQ** **4,610091s** im Mittel (~32,827% kuerzer, drei reale Runden, VS1/GFA nach Restore gueltig). Dieser wichtige dokumentierte Ein-ENQ-Weg fehlt noch im konservativen `DEEP.DeepWire.identify_vs1()`-Pfad der produktionsgetrennten Research-Logger: dort steht explizit `self.w.enter_vs1(2)`.
- [Baseline mit separater Zeitaufteilung](p300-handover-baseline-result-and-single-enq.md): EOT→erste ENQ in jeder Richtung ~1,998s; Zusatz-ENQ fuer Rueckweg ~2,238s. Im Prober wurden 4800 Baud/8E2, pyserial `timeout=0`, 1ms Polling bei leerem Empfang verwendet; die 2s stammen **nicht aus einem expliziten 2s sleep im Python-Handover-Code**. Eine Firmware-/Elektronikursache ist plausibel, aber nicht ohne weiteres nachgewiesen.
- [Idle-ENQ-Vergleich](p300-idle-enq-result-2026-10-08.md): EOT/Ein-ENQ ~4,610s; natuerliches ENQ ohne EOT ~5,628s, also **+1,018s langsamer**. Diesen negativen Zweig **nicht blind wiederholen**.
- Der vorliegende `trace.jsonl`-Serializer `base.UART1Wire.record` **bündelt RX-Bytes bis zum naechsten TX** und schreibt den Zeitstempel des *ersten* RX-Bytes fuer den ganzen Block. So erscheint beim Rueckweg `RX 060505` mit einem einzigen fruehen Zeitpunkt, obwohl die nachfolgenden `05` vermutlich spaeter eintreffen. **Nicht** die 4,228s TX-Luecke blind als Python-Sleep interpretieren; vorrangig die alten segmentierten ENQ-Messwerte verwenden.
- Nachrangiger Designansatz: neuer Worktree + neuer Branch fuer **offline Quell-/Trace-/Bottleneck-Analyse**, ueber `optolinkvs1.py`, `optolinkvs2.py`, `wb2a-handover-probe.py`, `UART1Wire`, Vitosoft VSKO, Adapter CP2102 und pyserial lesen, dann begruendeter Entscheid **Fork vs. Owner/Adapter vs. verifizierte Handshakeoptimierung**. Keine neue Hardwareprobe ohne eigene Freigabe; aktuelle Langmessung und `/opt/optolink` unberuehrt lassen.
