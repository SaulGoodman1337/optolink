# Entwicklung: bedarfsgesteuerte P300-Lesebatches im VS1-Hauptbetrieb

**Status 10.10.2026: Implementiert und offline getestet, aber ausdrücklich NICHT in den laufenden Dispatcher eingebunden und NICHT für produktive Hardwarefenster aktiviert.** `main` und `/opt/optolink` bleiben unverändert.

## Bereits verfügbare Sicherheitsbasis

Die bestehende Hybridlaufzeit verwendet ausschließlich denselben seriellen Originalbesitzer, blockiert parallele Write-/Readback-Gruppen, verifiziert die Rückkehr nach VS1 mit echten GFA-P80/P06-Werten und hat einen unabhängigen Systemd-Rückfallpfad. Der `ContinuousReadonlyRuntime` besitzt bereits ein periodisches, standardmäßig deaktiviertes P300-Lesefenster. Das ist **noch keine bedarfsorientierte Request-API**.

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

## Noch notwendige Integrationsschritte

1. **Vertrauenswürdige Eingangsgrenze:** Nur ein interner, geprüfter Read-only-Request-Weg darf Tickets erzeugen. Anfragen dürfen niemals unmittelbar aus unvalidierten MQTT-/TCP-Rohtelegrammen in physische FC03-Aufträge übersetzt werden. Die normale VS1-Queue und schreibende Transaktionen behalten Vorrang.
2. **Echter P06-Zeitstempel:** Die `ContinuousReadonlyRuntime.note_keepalive()`-GFA-/Identitätsprüfung ist **nicht** automatisch ein aktueller P06-Referenzbeweis für den neuen Planer. Vor Übergabe von `initial_p06_age_ms` muss die originale GFA-P06-Messung samt Zeitstempel/Generation im Hauptthread valide vorliegen; `FF` und alte Generation blockieren.
3. **Atomare Admission und Producer Fence:** `IngressEpoch.freeze()`, `p300_window()`, `RuntimeAdmissionGate.decide()`, HA-Readback-Ledger und Serienlease müssen vor `reserve()` dieselbe unveränderliche Schreibfreiheits-Situation beweisen. Bestehende externe Producer-Attestierung wiederverwenden.
4. **Dispatch und Ergebnisprovenienz:** Nur freigegebene `ReadJob`-Diagnosen an `RuntimeAdmissionGate.run_readonly_batch()`; Rückgabe an alle wartenden Anforderer erst nach echtem `verified_vs1` mit P80/P06. FC03-Daten ausdrücklich als RAW-Diagnose, niemals als gemessene Gebläsedrehzahl publizieren.
5. **Fehler-/Deadlinepfad:** Bei Transportabbruch, unbestätigter VS1-Identität, Signal/Timeout: kein weiterer Batch, persistente Producer-Markierung und unabhängige Recovery. Bei bloß verweigerter Admission **keine** Reservierung, Anfragen laufen regulär ab.
6. **Separater Hardwarecanary:** Erst nach Verknüpfung mit dem Hauptloop, Erweiterung der reproduzierbaren Produktionsinstallation, Hardware-/MQTT-Paritätstests, dokumentiertem Rollback und expliziter Betriebsfreigabe. Kein Langzeit-Soak nötig.

## Lokal ausgeführte Tests

```bash
cd /home/chatgpt-admin/optolink-wb2a-next-phase-20261010
python3 -m unittest discover -s tests -p 'test_wb2a_on_demand*.py' -v
python3 -m unittest discover -s tests -p 'test_handover_*.py' -q
python3 -m unittest discover -s tests -p 'test_optolink_hybrid_production.py' -q
```

Lokaler vollständiger Testlauf am 10.10.2026: **276/276 Tests erfolgreich**, darunter **24 neue On-Demand-/Fake-Port-Integrationstests**. Dabei wurden keine Hardwaretelegramme ausgegeben.

Es existiert aktuell **kein** neues `optolink-hybrid`-Kommando zum Aktivieren dieser On-Demand-Queue. Der normale Produktionsbetrieb bleibt VS1. Forschungsergebnisse zur P300-Drehzahl stehen getrennt in `optolink-research` unter `docs/wb2a-rpm-offline-audit-2026-10-10.md`.
