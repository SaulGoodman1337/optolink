# WB2A P300 Temporal: Live-Checkpoint, verifizierte Vorlaeufe und Entscheidungsplan (09.10.2026)

**Nur Aufgabe 1.** WB2A / VDensHO1 20C2, SW 0103, GFA P80=20. Produktiver Checkout /opt/optolink bleibt unveraendert, PR #46 bleibt **Draft/unmerged**. Dieses Dokument entsteht **ohne Einfluss auf den aktuell laufenden und quellengepinnten Temporal-Full-Worker**; alle Hardwarebewertungen sind nach Messstatus getrennt.

## 1. Verifizierter Repository- und CI-Stand

- Entwicklungsbranch optolink-p300-migration, TEMPoral-Logger zum Hardwarestart an Commit **eb7a9549b812caa95f934950d32ce01b613e7d28** im Session-state.json gepinnt.
- Quelltext: [wb2a-p300-temporal-logger.py](../tools/wb2a-p300-temporal-logger.py); Wrapper: [wb2a-p300-temporal-logger.sh](../tools/wb2a-p300-temporal-logger.sh); [Deterministische Offline-Tests](../tests/test_p300_temporal_logger.py); [Workflow](../.github/workflows/validate-p300-temporal.yml); [detailliertes Runbook](p300-temporal-runbook-2026-10-09.md).
- Zur gepinnten Canary-/Full-Version drei GitHub-Workflows erfolgreich: Validate WB2A P300 Temporal Logger (Run **37933687156**), Validate WB2A P06 Focus Logger (Run **37933687173**), Validate WB2A Full RAM P06 Logger (Run **37933687091**).
- Die exakten Quellhashes wurden in den privaten Archiven gegen die gepinnten Sessionkopien mit SHA256 abgeglichen (jeweils ohne Fehler). **Nicht mitten im laufenden Full-Run per Git pull/merge, systemctl service restart oder neuen Logger eingreifen.**

## 2. Eigenstaendig auditierter P06-Fokuslauf (abgeschlossen)

- Privates Nutzerarchiv: p300-p06-focus-run-20261009T120043Z-212162-bundle.tar.gz; SHA256 **1e97b8ce75608c115fa40ca89980091cd865dacbabf3cd11ddfb6561a2a9eae9**.
- **42/42** im Manifest referenzierte Datei-Hashes und Dateilaengen stimmen. Exakter Sessionstand 8bd904a95a45d01d09228ecfb5915eae770834ae, Quellenhashes alle richtig.
- Lauf: 2026-10-09 12:00:43 bis 13:00:47 UTC, vom Logger regulär ohne Fehler beendet; **8 COMPLETE / 0 PARTIAL**, **3 STABLE_OFF, 1 STABLE_2490, 4 TRANSITION_OR_UNKNOWN, 0 STABLE_OTHER_POSITIVE**.
- 96/96 P300-FC03-Reads auf sechs erlaubten FC03/32-Blockadressen, 24/24 native Statusantworten, 16 protokollierte Protokollwechsel, 54.382 TX/RX-Traces, 26.936 VS1-Referenz-Logzeilen.
- Captures 4 und 7: echte P06-PRE jeweils 4410 RPM; POST ist **dynamisch** (3870, 3930, 3990, 4050 bzw. 4050, 4110, 4170, 4230 RPM). Beide RAM-Kandidaten 0x0F20 und 0x1C76 bleiben in beiden jeweiligen RAM-Runden **0x54**. **Das widerspricht einer simplen unmittelbaren P06+1-Kodierung als naheliegende Interpretation**, aber ist **kein strenger Ausschluss**: nie zeitgleiche Drehzahlmessung in P300; die Vorher-/Nachherklammer war nicht stabil.
- Capture 8: PRE/POST durchgehend P06=2490 RPM, beide RAM-Runden 0x54 an 0x0F20/0x1C76. Captures 1..3: PRE/POST P06=0, beide Kandidaten beide Runden 0x00. Capture 7 ist am nativen Byte7 0x60 statt 0x62, was fehlende allgemeine Statuskonstanz zwischen den dynamischen Captures zeigt.
- Worker-VS1-Restore true, 6/6 zuvor aktive Units wiederhergestellt, keine Recovery-Fehler, produktives P80/P06-Readback und non-FF bestaetigt; HA-Entity-Frische nicht verifiziert.
- **Wichtig:** Der Fokuslauf begruendet weiterhin **keinen freigegebenen echten P06-P300-Alias**.

## 3. Eigenstaendig auditierter Temporal-Fuenf-Minuten-Canary (abgeschlossen)

- Privates Nutzerarchiv: p300-temporal-run-20261009T130751Z-219194-bundle.tar.gz; SHA256 **9fdd0a9a5a286166edadcaceeca9c68aa7d61e48b2172868d6bb84229a66ad9b**.
- **23/23** Manifestdateien SHA256/Laenge richtig. Sessionquellen-/Gitstand **eb7a9549b812caa95f934950d32ce01b613e7d28** hashverifiziert.
- Modus canary, 300 Sekunden Budget inklusive Setup; P300-only-Stream **286,53 Sekunden**. **191 vollstaendige Kernzyklen** (lueckenlos 1..191), **852 P300-Frames**, 22 Kontextgruppen, **2 Protokollwechsel**, keine Packet-Fehler, **852/852 gemeldete Checksummen gueltig**.
- Volle Kern-Binaerdatei **12.224 Byte = 191 x 64**, alle belegten Core-/Kontext-Binaeroffsets passen zum gespeicherten SHA256. Alle 191 Zyklen mit Kandidaten 0x0F20=00, 0x1C76=00, keiner Mirror-Abweichung, nativer P87-Byte7=00 und keinem Flammenbit. Events.jsonl leer.
- Das ist ein **Transport-, Ressourcen- und Wiederherstellungs-Canary**, **kein** positiver Aktualisierungstest der Kandidaten. Bei konstant AUS gab es schlicht keinen natuerlichen Zustandswechsel.
- Worker-Restore, 6/6 Produktivdienste, P80/P06 non-FF verifiziert und keine Fehler. Erfuellt die obligatorischen Sicherheits-Gates zum Start der nachfolgenden Full-Session.

## 4. Aktive Zweistunden-Full-Session (nur bisheriger Nutzerstatus, kein Live-Zugriff von hier)

- Session run-20261009T131357Z-220351, Start ca. **13:13:57 UTC = 15:13:57 MESZ**. Konfigurationszeit **7200 s**, mode full. Der zuletzt uebermittelte Status 13:14:20 UTC / 15:14:20 MESZ (Anzeigeuhr 15:14:33) zeigt **UNIT_STATE=active**, **state=RUNNING_READ_ONLY**, **phase=P300_STREAM**, **complete_cycles=6**, **p300_packets=28**, **context_snapshots=1**, **candidate_changes=0**, **mirror_mismatches=0**, **native_flame_edges=0**, **native_p87_changes=0**, **within_pair_transitions=0**.
- **Keine Aussage zur spaeteren Entwicklung**: diese 23 s sind nur ein frueher Startbeleg. Die KI kann die LXC-Unit nicht autonom ueberwachen und wird keine unbekannten Werte erfinden.
- Naeherungsweises Zeitlimit **17:13:57 MESZ** (7200s vom Start des Workers inklusive PRE/P300-Wechsel), die systemd-Wiederherstellung und das Archiv folgen nach dem Ende; kein garantierter exakter Endzeitpunkt.
- Pro Messzyklus: FC01 0x55D3/11 Status A → FC03 0x0F20/32 → FC03 0x1C60/32 → FC01 0x55D3/11 Status B. Alle ca. 12s zusaetzlich vier bekannte FC03/32-Bloecke 0x0F00, 0x0F40, 0x1C40, 0x1C80.
- Normaler Zielabstand 1,5s, bei natuerlichem Flame/Lockout-Wechsel 0,5s Burst bis 35s, P87-Wechsel bis 20s, ausgepraegte Modulationsaenderung bis 8s. Echte Paket-/UTC-/Monotonic-Timestamps sind massgeblich; kein zeitgleicher GFA-P06 im P300-Stream.
- Session ist schreibgeschuetzt fuer Forschung: kein C9/09/07, keine EEPROM-, UART1-SFR-, Pumpen- oder Brennerwrites. Kein manueller Eingriff in P300/VS1 waehrend der laufenden Session.

## 5. Operatives Monitoring bis zum Ende

**Nur Status lesen:**

    bash /root/p300-trial-work/project/tools/wb2a-p300-temporal-logger.sh status

Relevante Trends: complete_cycles und p300_packets steigen; candidate_changes, native_flame_edges, native_p87_changes, within_pair_transitions und mirror_mismatches duerfen **nicht** blind als Erfolgs-/Fehlerflags interpretiert werden. Nullwerte ueber wenige Minuten koennen reinen AUS-Betrieb bedeuten. Stagnation bei UNIT_STATE=active bedarf Logdiagnostik, kein sofortiger zweiter Start:

    journalctl -u optolink-p300-temporal.service --since '2026-10-09 15:13:00' --no-pager -n 80

Nach beobachtetem natuerlichem Brennerzyklus ist die Zeitreihe fuer die eigentliche Kandidatenanalyse aussagekraeftig. Wenn keine natuerlichen Ereignisse auftreten, lautet das Ergebnis **INCONCLUSIVE**, nicht dass P06 garantiert fehlt. Kein erzwungenes Brenneranfordern.

**Geordneter manueller Stopp nur bei Bedienwunsch/Fehler:**

    bash /root/p300-trial-work/project/tools/wb2a-p300-temporal-logger.sh stop

SIGTERM wird zwischen vollstaendigen seriellen Transaktionen behandelt, danach VS1-Reentry, systemd ExecStopPost und P80/P06-Health. Ein vorzeitiger Stopp bleibt fuer den 2h-Erkenntnisnachweis unvollstaendig, selbst wenn die Recovery erfolgreich ist. **Nie systemctl kill -9 oder manuelles Reinitialisieren des Produktivcheckouts statt des dokumentierten Stops.**

## 6. Nach Laufende: Restore ist vor Dateninterpretation zu pruefen

Der *Dienststatus inactive allein reicht nicht*. Erwartete Dateien in /root/p300-trial-work/p300-temporal-results/run-20261009T131357Z-220351/:

- progress.json: state=RESTORED und p80_p06_production_health_verified=true. Bei RESTORE_NOT_VERIFIED zunaechst Recovery/Health diagnostizieren, **kein neuer Logger**.
- measurement.json: errors=[], observation_complete=true, data_quality=COMPLETE, worker_vs1_restored=true, stream.no_vs1_during_stream=true, counts und Endzeit. Ein Messfehler kann bei trotzdem erfolgreichem Restore PARTIAL ergeben; getrennt behandeln.
- recovery.json: services_restored=true, errors=[]; alle zuvor aktiven sechs Units (oder die tatsaechlich in state.json vermerkten) korrekt wiederhergestellt.
- health.json: production_main_verified=true, P80-GFA-Identitaet 20, P06 gueltig und **nicht FF**. HA-Entity-Frische ist separat zu bestaetigen und kann auch bei erfolgreichem MQTT-Readback ungeprueft bleiben.
- Neues privates Archiv /root/p300-trial-work/research-bundles/p300-temporal-run-20261009T131357Z-220351-bundle.tar.gz. Fuer die Ergebnisauswertung braucht es **nur diese eine Datei**, nicht die privaten Konfigurationen.

## 7. Deterministische Offline-Auswertung des Full-Archivs

1. **Sicherung und Provenienz:** nur in-memory eine allowlisted tar.gz auswerten, vor allen weiteren Schritten Session-ID, Hash, Manifest, alle relativen Dateipfade/Typen, Groessen, SHA256, Quellhashes und genauen Source-Commit pruefen. Keine Roh-Settings in Git/Chat kopieren.
2. **Packet-Forensik:** jedes packets.jsonl gegen echte TX/RX-Frames validieren (ACK, 41/Laenge, MessageID, FC01/FC03, Adresse, Datenlaenge, Checksumme), identische Reihenfolge und genau 4 + 4 je Kontextzyklus, getrennte Timeout-/Partial-Frames. Null unbekannte TX-Writes ist ein eigenes Audit-Gate.
3. **Binärzuordnung:** core-pairs.bin genau 64 Byte je COMPLETE-Kernzyklus, context-frames.bin genau 128 Byte je Kontextgruppe, JSONL-Offsets und SHA256 ueber jedes Sample pruefen. P300-Rohlesezeitpunkte sind NICHT gleichzeitig.
4. **Ereigniszeiten:** alle natürlichen Flammenbitwechsel und P87-Byte7-Kanten (sowie Byte0/9-Modulation, Verriegelung) auf einer UTC/Monotonic-Zeitachse vergleichen; nicht 1,5 oder 0,5s als exakt gemessen voraussetzen.
5. **Status-Paar-Qualitaet:** wenn Status A und B unterschiedlich (Flame/P87/Lockout), diesen Kernzyklus als Status-Transition kennzeichnen und nicht als atomaren Snapshot verwerten; Modulationsaenderungen getrennt auswerten.
6. **Mirror- und Kandidatenupdates:** 0x0F20↔0x1C76, 0x0F28↔0x1C7D, 0x0F29↔0x1C7E, RAM-0F29 gegen natives Statusbyte 7 innerhalb seines Zeitfensters; Cross-Lag mit bekannter Byte-Abtastversatz-Obergrenze abschaetzen. Datenkopien sind noch keine unabhaengigen Sensoren.
7. **Semantik trennen:** Kandidatenverlaeufe 00/54, >2 Werte, stale/aktualisierungsperioden gegen Flame/P87/Byte0/Byte9. P09 und P300-Statusmodulation sind keine echte Geblaese-Istdrehzahl.
8. **Uebergreifender Vergleich:** mit 79 VollRAM-Snapshots, 8 Fokus-Captures und 191 Canaryzyklen gruppieren; stabile VS1-P06=0 und 2490 RPM gelten als externe Referenz nur innerhalb ihres jeweiligen Fensters. Die beiden dynamischen Fokusaufnahmen mit PRE 4410 und POST 3870..4230 RPM duerfen nicht stillschweigend als zeitgleiche stabile Benchmarks gelten.
9. **Ergebnisgrenzen:** fuer einen echten P300-P06-Alias mindestens zwei unabhaengige **stabile positive** VS1-P06-Drehzahlreferenzniveaus, reproduzierbare richtige Rohwertskala, Traegheit/Anlauf/Auslauf und Unabhaengigkeit von P09, FC01, Statusflags sowie eigenen Optolink-Ringpuffern. Der Temporal-Stream allein liefert dies prinzipbedingt nicht.

## 8. Expliziter Entscheidungsbaum fuer Aufgabe 1

- **A: Flame/P87 wechselt mehrfach und beide RAM-Kandidaten bleiben 00 oder 54 passend nur zu EIN/AUS.** Status-/Prozesskopie wird wahrscheinlicher; kein P06-Alias. Keine zweite RAM-Vollmessung starten.
- **B: Natuerliche Flame/P87-Wechsel, Kandidaten bleiben konstant.** Dynamische Ist-RPM-Abbildung wird unplausibler. Auch hier kein positiver P06-Beweis.
- **C: Kandidaten zeigen eigenstaendige Mehrwertdynamik, insbesondere waehrend Modulation ohne Flammenwechsel.** Ein konkreter RPM-Forschungskandidat besteht; erst dann **kurzes, read-only, echtes VS1-P06-geklammertes Folgeexperiment** (mindestens zwei positive Plateaus) entwerfen und separat offline testen. Den P300-Stream nicht nachtraeglich als Ist-RPM labeln.
- **D: Keine natuerlichen Flame/P87-Ereignisse.** Fuer RPM-/Statusdifferenzierung **INCONCLUSIVE**; bei vorhandenen alten Uebergangsbelegen zunaechst bereits vorhandene Daten nutzen, nicht blind wieder zwei Stunden messen.
- **E: Recovery/Timeout/Manifest/Frame fehlerhaft.** Sofort Sicherheits-/Wiederherstellungsanalyse priorisieren; keine weitere Hardwaremessung freigeben.

**Bei A/B ohne Sensorbeweis:** als Aufgabe-1-Hauptpfad **Single-Owner Hybridarchitektur** P300 fuer primaere Telemetrie plus gezielte echte VS1-GFA-P06-Abfragefenster planen. Ca. 2,165s VS1→P300 plus ca. 4,327s P300→VS1 gemessene mittlere Wechselzeiten nicht ignorieren. Ein tragfaehiger Owner muss Portlocks, Service-/MQTT-Konsistenz, Failover/Watchdog, Frische-Timestamps, Schreibtransaktionsschutz, Clock Sync, Party, Schedules, Serviceprogramme und HA-Entity-Paritaet pruefen. **Keine P09-/55D3-Modulationswerte als P06 ersetzen**.

**RPC-Nebenpfad nur offline:** Vitosoft-v6-VDensHO1-Profilenthaelt 22 RPC-Events; erst Handler/Parameter/GFA-Bezug pruefen; keine unbekannten RPC-, C9-, EEPROM-, SFR- oder schreibenden Kesselversuche. KM-Bus-TX ist kein direkt verifizierter Hall-Tacho-Kanal; Task 2/3 warten.

## 9. Datensparsamkeit und Repositorypolitik

Im Git bleiben nur diese Auswerte-Fakten, Dateienamen/SHA256, die unveraenderten Logger, Tests und Runbooks. **Die kompletten privaten JSONL-/TX/RX-Archive werden nicht in Git committed.** Die aktive zweistuendige Full-Session ist **noch nicht als erfolgreich abgeschlossen belegt**; die neuen Erkenntnisse haengen von ihrer realen Enddatei ab.
