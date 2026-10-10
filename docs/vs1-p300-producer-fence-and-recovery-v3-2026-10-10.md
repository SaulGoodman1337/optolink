# WB2A VS1/P300 – echte Writer-Grenzen und unabhängiger Recovery-Pfad (v3)

**Datum:** 2026-10-10. **Zweig:** `optolink-handover-acceleration`. **Status:** Entwicklung und Offline-Test, keine Installation unter `/opt/optolink`, kein produktiver VS1/P300-Umschaltversuch mit dieser Version.

## Verifizierte Ausgangslage

- Remote Desktop Commander: `chatgpt-admin`, UID 1000, Gruppen `dialout` und `optolink`; `sudo -n true` ergibt Exitcode 1. Root-Forschungsverzeichnis `/root/p300-trial-work` nicht lesbar. **Damit ist der ausdrücklich freigegebene überwachte reale One-Shot-Test von diesem Remote-Zugang aus nicht möglich**; es wurde weder systemd-run noch ein USB-Protokollwechsel durchgeführt.
- `optolink-splitter.service` aktiv; `optolink-pump-override.service` inaktiv und deaktiviert; Party-, Schedule-, Maintenance- und Service-Program-Dienste aktiv. Der Clock-Sync-Timer ist aktiv.
- Wirklicher Optolink-Pfad: `/dev/serial/by-id/usb-Silicon_Labs_CP2102_USB_to_UART_Bridge_Controller_0001-if00-port0` (Character Device im LXC; dort gibt es aktuell kein `/dev/ttyUSB0`). Protokollprofil: VS1, kein zweiter Vitoconnect-Port.
- Zwei **reale, unverändernde VS1-MQTT-Leseoperationen** über den produktiven Splitter: GFA P80 `1;0x4050;20`, P06 `1;0x4006;00`. P06=`00` entspricht einem gültigen Rohwert, keine nachgewiesene aktuelle Gebläsedrehzahl größer null.
- Der **bytegenaue** SHA256 von `/opt/optolink/optolinkvs2_switch.py` ist `f66b5a3eea0941f821c53bcf169b4cadff7a17418ec22dde05ed810b39cf1765`. Die reale Datei hat CRLF-Zeilenenden. Der **normalisierte UTF-8-Quelltext** hat SHA256 `e4be265db857d32486fd50aa7eee359e9a054b951e478d5847f17702a0ce7fac`, genau wie der gepinnte statische Dispatcher-Audit. Es handelt sich um eine Zeilenenden-Differenz, nicht um einen festgestellten Quellcodewechsel.

## Quellgeprüfte, nicht atomare Schreibabläufe

| Dienst / Pfad | Logische Mindest-Transaktion für eine Writer-Sperre | Wesentliche externe I/O |
|---|---|---|
| `/usr/local/bin/optolink-party-emulator` | `PartyEmulator.activate`, `deactivate`, `recover_startup`, `sync_emulated_controls` einschließlich aller `rollback_activation`-/`restore_emulation`-Zweige | Mehrere `r;...`, `w;...` an 0x2306/0x2323 (ggf. Party-State), verzögertes `verified_write`-Readback nach 0.35/0.9/1.8s |
| `/usr/local/bin/optolink-schedule-manager` | `ScheduleManager.apply` um komplette acht Byte; falls ungültiger Readback: Restore des **alten** Blocks einschließlich Verifikation | `r;...`, `wraw;...`, Rücklesungen nach 0.20/0.60/1.20s |
| `/usr/local/bin/optolink-service-programs` | `ServiceProgramManager.apply_action` einschließlich `write_mode` und Restore des alten Modus | MQTT Requests mit `write_mode`-Readback und Revert |
| `/opt/optolink/optolink_maintenance_core.py` | Gesamte `_with_session`-Operation, z. B. `set_hours`, `set_months`, `reset_maintenance` samt `write_verify_byte` und `_restore_byte` | MQTT-Mehrfachanforderungen und Rückrollen |
| `/usr/local/bin/optolink-clock-sync` | `ClockSync.synchronize` inklusive `0x088E`-Write und anschließender frischer Controller-Rücklesung | Clock-Sync-Timer wird unabhängig ausgelöst |
| `/opt/optolink/mqtt_util.py` | Kompletter `handle_set_topic`-Write mit allen vier `force_delayed`-Readbacks: 0.25, 1, 2.5, 5s | Timer-Threads: eine leere `lst_force_refresh` bedeutet NICHT, dass keine Refresh-Anforderung mehr aussteht |
| Hauptdispatcher MQTT/TCP | Jede direkte `write`/`writeraw`/opaque `raw`/generische `request`-Operation und ein darüber hinausgehender fremder Write-/Readback-Verbund | Haupt-Dispatcher seriell je Telegramm, aber **nicht** atomar über mehrere MQTT-Nachrichten |

**Folge:** Ein freies serielles Gerät oder eine leere MQTT-Warteschlange beweist keine logisch abgeschlossene Steuertransaktion. Ein 4-8s VS1-Ausfall kann sonst zwischen Write, Readback und Rollback geraten.

## Implementiert in Forschungsquelle

### 1. Prozessübergreifende Kooperationssperre

`tools/handover_acceleration/producer_fence.py` stellt `writer_transaction(...)` und `p300_window(...)` bereit. Beide verwenden auf derselben separaten Sperrdatei ein exklusives `fcntl.flock`. Ein Writer hält es *über die vollständige logische Read-before-Write/Write/Readback/Restore-Transaktion*, nicht pro Frame. Ein P300-Fenster ist strikt nichtblockierend: besetzt die Sperre ein Writer, bleibt VS1 unangetastet. Während eines P300-Fensters wartet ein neuer kooperierender Writer nur innerhalb einer expliziten Frist.

**Sicherheitsverhalten:** Die Sperrdatei wird NICHT automatisch angelegt. Fehlt ihre geprüfte Bereitstellung, wird abgelehnt. Symlinks, Hardlinks, unsichere Zugriffsrechte und nicht vertrauenswürdige Eigentümer werden abgewiesen. Das Test-Setup nutzt nur private Dateien in temporären Verzeichnissen. Ein späterer Rollout müsste den gemeinsamen Lock z. B. als `root:optolink 0660` unter `/run/lock/optolink-hybrid-producer-epoch.lock` bereitstellen; der Code führt diesen Schritt nicht aus.

`fenced_readonly_batch(...)` erwirbt erst diese OS-Sperre und ruft anschließend eine ausdrücklich vom ursprünglichen Mainloop bereitgestellte, vertrauenswürdige Snapshot-Funktion auf. Diese muss *nach* dem Sperrerwerb beweisen, dass neue MQTT/TCP-Kommandos abgehalten werden und alle anderen Writer teilnehmen. Erst dann darf die bereits bestehende `RuntimeAdmissionGate` die feste P300-ID und zwei feste FC03-Leseblöcke ausführen. Bei fehlender Evidenz wird ohne seriellen TX abgebrochen.

**Noch NICHT implementiert / nicht behaupten:** Die heutigen produktiven Party-/Schedule-/Service-/Maintenance-/Clock-Sync-Prozesse benutzen diese neue Sperre NICHT. Direkte MQTT-/TCP-Writes und die verspäteten HA-Poll-Timer sind noch nicht vollständig beim neuen Gate registriert. Der Mechanismus ist ein durch echte Cross-Process-Tests belegter Baustein, aber **noch keine produktive Garantie für wartungsfähigen Dauerbetrieb**. Im Schattenpatch bleiben wiederholte automatische P300-Umschaltungen deaktiviert.

### 2. Eigenständiger Recovery-Prozess

`hybrid_recovery.py` ist jetzt ein eigenes root-/systemd-gebundenes `ExecStopPost`-Entrypoint. Vor dem unveränderten, gepinnten `live_probe.recover(session)` erwirbt es erneut `/run/lock/physical-ram-snapshot.lock` und prüft, dass der Legacy-Pumpenoverride nicht aktiv oder im Zustandswechsel ist. Ein konkurrierender Owner darf die unabhängige VS1-Reinitialisierung nicht überlagern. Bei verweigerter Sperre wird **kein erfolgreicher Restore behauptet**; ein Fehlerprotokoll wird versucht. Das bedeutet im Konfliktfall möglicherweise ausbleibende automatische Dienstrückkehr; Eingriff durch Betreiber erforderlich.

Der Testlauncher `hybrid_acceptance.py` benennt seinen Release jetzt `inprocess-fc03-oneshot-v3-recovery-arbitration`, kopiert `hybrid_recovery.py` privat in die Sitzung und nimmt Datei-Hash und Root-Schutzrechte ins Stage-Manifest. `ExecStopPost` ruft die unabhängige Kopie auf. Das ursprüngliche `live_probe.py`-Recovery-Verhalten bleibt unverändert und ist weiterhin über einen gesonderten systemd-Abnahmeprozess abgesichert. Die Tests prüfen den **echt staged importierten** Recovery-Einstieg und verweigern nachträgliche Manipulation der Datei.

## Nächster Integrationsschritt

1. Alle sieben Writer-Klassen kontrolliert an den gemeinsamen Schreibepfad anbinden; zunächst als isolierte Kopie mit Fake-MQTT, dann mit einheitlichem Rollback. Keine bereits laufenden Dienste ungefragt verändern.
2. MQTT-`/set`-Timer transparent mitzählen; Snapshot-Aufruf muss in einer gesperrten, für neue Aufträge geschlossenen Epoche erfolgen. Nur so werden `pending_readbacks`, `queue_admission_paused` und `external_writers_quiesced` zu tatsächlicher Evidenz.
3. GitHub-CI für Python 3.11/3.12/3.13 und Tests des gepinnten Originaldispatchers beobachten. Der Python-3.13-Eintrag wurde diesem Entwicklungsstand hinzugefügt.
4. Den vom Betreiber genehmigten, ausschließlich lesenden One-Shot auf dem aktuellen Branch **nur in einer autorisierten Root-Sitzung** durchführen. Vorher Produktion-GFA prüfen, P300-Logger ausschließen, Staging-/Recovery-Hash prüfen und bestehende aktive Dienste dokumentieren. Danach unabhängige VS1-Rückkehr und echte MQTT-GFA prüfen. Ein FAIL niemals blind wiederholen.

**Wichtig:** Die Hardwareabnahme wurde bislang nicht real durchgeführt, weil der Remote-Agent `chatgpt-admin` keine Root-Rechte hat; Root-Privilegien wurden nicht umgangen.
