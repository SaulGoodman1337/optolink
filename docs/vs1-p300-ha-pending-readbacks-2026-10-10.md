# VS1/P300: verzögerte HA-Readbacks fail-closed verfolgen

**Forschungsbranch, 2026-10-10.** Die produktiven Dateien in `/opt/optolink` wurden nicht verändert. Der bereits reale, überprüfte **On-Demand-Switch** bleibt unverändert; diese Ergänzung betrifft ausschließlich eine später mögliche, durchgehend laufende Hybrid-Integration.

## Verifizierte Gefahrenstelle

Der Original-Splitter in `/opt/optolink/mqtt_util.py` plant nach einem `/set`-Write insgesamt vier Refresh-Aufträge nach 0,25 / 1,0 / 2,5 / 5,0 Sekunden. Bis der jeweilige Timer feuert, ist `lst_force_refresh` noch leer. Das ist **keine** Erlaubnis, jetzt den seriellen Port für einen mehrsekündigen P300-Batch zu beanspruchen.

Auch `is_forced()` bedeutet allein noch keinen Readback-Erfolg. Erst `do_poll_item(...)` meldet die Durchführung und ihren Rückgabecode.

## Implementierung

`tools/handover_acceleration/pending_refresh.py`:
- Registriert beim **Planen** eines HA-Timers ein eigenes Opaque-Ticket, eindeutig auch bei mehrfach identischem Datapointindex.
- Unterscheidet fremde Force-Polls ohne Ticket von bestätigten HA-/set-Rücklesungen.
- `is_forced()` markiert nur `inflight`; nach **vollendetem erfolgreichen** `do_poll_item()` bestätigt `_hybrid_complete_forced(retcode)` den Readback. Ein Timeout oder ungültiger Rückgabecode setzt `failed_closed`; das Ticket bleibt als Sperrgrund vorhanden.
- Geht ein Ticket bei einem bestehenden Refresh-Queue-Reset verloren, bleibt der Pending-Zähler >0, statt die Ruhefreigabe fälschlich zu erteilen. Es gibt **keine zeitbasierte automatische Entsperrung**.
- `require_idle_for_p300()` verweigert P300-Batches bei einem einzigen offenen oder fehlerhaften Readback.

`dispatcher_patch.py` erzeugt einen Quell-Schatten mit zwei exakt gepinnten Integrationsstellen:
1. `install_before_mqtt_connect(mod_mqtt)` **nur unter** `OPTO_RESEARCH_DISPATCH_SHADOW=1` und `OPTO_HYBRID_RUNTIME_DIAGNOSTIC=1`, bevor Paho die erste Callback-Nachricht verarbeiten kann.
2. Ein abgeschlossener Force-Poll meldet seinen echten Rückgabecode nach `do_poll_item()` an das Ledger. Bei einem normalen Originalbetrieb ohne Diagnostic-Flag bleibt dieser Block inert.

`hybrid_acceptance.py` kopiert und hasht die zusätzliche Moduldatei in die private, überwachte Test-Sitzung, damit die aktivierte Schattenkopie keine fehlenden Imports erhält.

## Tests / verbleibende Freigabesperren

Offline-Tests prüfen Timer-Wartezeit trotz leerer Queue, mehrere gleiche Indizes, verwaiste Queue-Einträge, falsche/duplizierte Tickets, echten Poll-Rückgabecode, Timeout-Fail-Closed, Installation **vor** MQTT-Connect sowie die unveränderte normale Dispatch-Strecke. Volle Suite: **426/426** auf Debian 13 / Python 3.13.

**Keine Behauptung eines produktionsreifen Dauerswitches.** Der zusätzliche Producer-/set-Zähler ist nur ein notwendiger Baustein. Vor produktiver P300-Zulassung müssen alle externen Party-/Schedule-/Maintenance-/Service-Programm-/Clock-Writer an dieselbe Transaktionssperre angeschlossen und direkte MQTT-/TCP-Aufträge im Snapshot atomar angehalten werden. Das Ledger allein darf niemals `external_writers_quiesced=True` oder `queue_admission_paused=True` behaupten.

Der bisherige, **überwacht lesende On-Demand-VS1/P300/VS1-Switch** war bereits zweimal auf realer WB2A erfolgreich und ist über Draft-PR #48 dokumentiert. Kein Merge ohne Betreiberfreigabe.
