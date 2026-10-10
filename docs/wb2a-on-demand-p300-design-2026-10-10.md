# Entwicklung: bedarfsgesteuerte P300-Lesebatches im VS1-Hauptbetrieb

**Status 10.10.2026: Echtes einmaliges P300-On-Demand-Lesefenster am WB2A bestanden.** Die Einbindung erfolgt nur im separat überwachten, zeitlich begrenzten Shadow-Release. Die Funktion ist **standardmäßig deaktiviert** und noch kein allgemein zugänglicher MQTT-/TCP-P300-Aufruf. `main` und die installierten Quellen in `/opt/optolink` bleiben unverändert. Details: [Canary-Abnahme](wb2a-on-demand-canary-2026-10-10.md).

## Bereits verfügbare Sicherheitsbasis

Die bestehende Hybridlaufzeit verwendet ausschließlich denselben seriellen Originalbesitzer, blockiert parallele Write-/Readback-Gruppen, verifiziert die Rückkehr nach VS1 mit echten GFA-P80/P06-Werten und hat einen unabhängigen Systemd-Rückfallpfad. Der `ContinuousReadonlyRuntime` besitzt bereits ein periodisches, standardmäßig deaktiviertes P300-Lesefenster. Ergänzend wurde `OnDemandReadonlyRuntime` mit streng typisierter interner Read-only-API und eigener GFA-Provenienzprüfung hinzugefügt. Ungeprüfte externe MQTT-/TCP-Aufrufe werden nicht als P300-Tickets akzeptiert.

## Neuer Offline-Baustein `BoundedDemandBatcher`

Als additive Komponente im bereits paketierten Modul `tools/handover_acceleration/scheduler.py`:

- Nur `ReadKind.P300_ID` (FC01-Geräteidentität), `ReadKind.P300_RAM_0F20_32` und `ReadKind.P300_RAM_1C60_32`. Keine frei wählbaren RAM-Adressen, kein RAM-Write, keine GFA- oder RPC-Wire-Experimente.
- Thread-sichere Annahme von höchstens 16 wartenden Lesetickets (konfigurierbar 1–128), pro Planung maximal drei unterschiedliche freigegebene Diagnosen; gleiche Diagnosen werden zu einer physischen Leseoperation zusammengefasst.
- Jede Anfrage mit **endlicher TTL >0 und ≤300 Sekunden**. Ablauf, Abbruch, Queue-Überlast, ungültige Leseart und fehlende GFA-Frische führen zur Ablehnung oder `EXPIRED`; kein ungültiges altes Ergebnis darf als frisch gelten.
- Der ursprüngliche serielle Hauptthread allein darf einen Batch auswählen und reservieren. Die Auswahl erhält ein einmaliges, höchstens eine Sekunde gültiges Identitäts-/Zeit-Gate; gefälschte, verworfene oder verspätete Reservierungen scheitern.
- Die bestehende `plan_phase_windows()`-Simulation prüft vorab **einen** Wechsel VS1→P300→VS1 mit expliziter P06-Frische, Laufzeit-, Wartezeit- und Lese-Deadline. Die Budgets sind **Schätzwerte** und keine garantierten Hardware-Maxima.
- Nach einem erfolgreich bestätigten VS1-Rückweg wird die nächste P300-Phase durch Cooldown (standardmäßig 60 s, mindestens 30 s) begrenzt.
- `complete(success=True,verified_vs1=False)` ist **kein Erfolg**: alle reservierten Tickets `FAILED` und Batch dauerhaft `FAILED_CLOSED`. Selbst bei verifizierter Rückkehr sind verspätete Ticketantworten `EXPIRED`, nicht frisch.
- **Kein** Import von PySerial, MQTT, Systemd/Prozesssteuerung oder Optolink-Schreibfunktionen im neuen Batcher. Es wird kein serielles Byte gesendet.

## Integration und verbleibende Freigabegrenzen

1. **Eingang implementiert:** `OnDemandReadonlyRuntime.submit_internal()` nimmt nur erlaubte `ReadKind`-Diagnosen an. Der gepinnte `demand-one`-Canary darf genau einen `0x0F20/32`-Testauftrag intern einreihen. Eine externe allgemeine MQTT-/TCP-Anforderungsschnittstelle bleibt bewusst noch ausstehend.
2. **P06-Provenienz implementiert:** `OwnerGfaProvenance` liest den rohen Erfolg der synchronen Original-GFA-P80/P06-Anfrage aus dem Dispatcher; `0x00` ist gültig, `0xFF`, falsche P80, veraltete Generationen und MQTT-Skalierungen sind ausgeschlossen. `note_keepalive()` allein genügt nicht.
3. **Atomare Admission implementiert:** Innerhalb von `IngressEpoch.freeze()` und exklusiver `p300_window()`-Lease werden HA-Readbacks, normale Queues und `RuntimeAdmissionGate.decide()` erneut geprüft, erst dann wird reserviert. Bei Scheitern kein P300-Telegramm; bei Protokollfehler persistente Sperre und unabhängiger Systemd-Rückfall.
4. **Dispatch und Ergebnisprovenienz implementiert:** Derselbe Originalport und das vorhandene Bridge-Modul lesen ausschließlich allowlist-geprüfte `ReadJob`-Diagnosen. Erst nach echter bestätigter VS1-Rückkehr wird ein `DemandReply` mit Provenienz `P300_RAW_DIAGNOSTIC_NOT_ACTUAL_RPM` ausgegeben.
5. **Deadline-Korrektur aus echtem Canary:** Der erste Hardwarelauf wurde wegen gemischter absoluter und relativer Monotonic-Zeitstempel abgebrochen. Der Bridge-/Executor-Pfad verwendet nun den konsistenten Zeitbezug und hat eine eigene Regressionsprüfung mit fortgeschrittenem Fake-Takt. Der erste Canary hatte nachgewiesen funktionierende Recovery.
6. **Hardwarecanary bestanden:** Release `wb2a-demand-c2-20261010`, Session `run-20261010T185043Z-324904`: genau 1 echter 32-Byte-Read `0x0F20` in 5157,098 ms und VS1-GFA-P80=`20`, P06=`00`. `PASS_ONE_VERIFIED_DEMAND_WINDOW`, danach unabhängiges `PASS_ORIGINAL_SERVICES_RESTORED`. Weiterhin keine Freigabe für Controller-Writes, Dauerautomatik oder allgemeine externe On-Demand-Befehle.

## Lokal ausgeführte Tests

```bash
cd /home/chatgpt-admin/optolink-wb2a-next-phase-20261010
python3 -m unittest discover -s tests -p 'test_wb2a_on_demand*.py' -v
python3 -m unittest discover -s tests -p 'test_handover_*.py' -q
python3 -m unittest discover -s tests -p 'test_optolink_hybrid_production.py' -q
```

Lokaler vollständiger Testlauf am 10.10.2026: **315/315 Tests erfolgreich**, inklusive Original-Dispatcher-Shim, Fake-UART-End-to-End, P06-Provenienz, Zeit-/Deadline-Regressionsfällen, Canary-Ereignisvalidierung und unabhängiger Recovery. Nur beim gesondert dokumentierten realen Canary wurden tatsächlich P300-Lesetelegramme ausgegeben; Offline-Tests greifen nicht auf Controller oder Port zu.

Ein allgemeines neues `optolink-hybrid`-Kommando für On-Demand-Anfragen existiert derzeit **nicht**. Die Freigabe für einen einmaligen, ausdrücklich bestätigten und beaufsichtigten Shadow-Hardwarecanary ist keine produktive Aktivierung. Die normale Installation und `update` bleiben VS1-basiert. Forschung zur P300-Drehzahl steht separat im Branch `optolink-research` unter `docs/wb2a-rpm-offline-audit-2026-10-10.md`.
