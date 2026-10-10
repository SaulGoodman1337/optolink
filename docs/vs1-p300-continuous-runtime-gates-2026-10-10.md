# WB2A VS1/P300: Continuous read-only hybrid integration — release gate

**Datum:** 2026-10-10. **Ziel:** echter kontinuierlicher Ein-Port-Betrieb mit originaler VS1-KW-Telemetrie, vorhandenen MQTT/TCP-Schreibfunktionen und kontrollierten P300-FC03-Lesefenstern.

## Bewiesen / erfolgreich

- Die WB2A hat zweimal echte VS1→P300→VS1-Lesesequenzen erfolgreich absolviert. GFA P80=20, P06=53, FC03-Blöcke 0F20/32 und 1C60/32; mit unabhängigem Systemd-Service-Restore. Die Übernahme einer bereits aktiven VS1-Sitzung sendet KEIN zweites STX.
- Der echte On-Demand-CLI-Switch ist nutzbar: `switchctl.py snapshot --accept-telemetry-pause`. Er setzt Originaldienste vorübergehend aus und funktioniert NICHT als nahtloser Dauerbetrieb.
- Die neue **automatische Laufzeit** liegt in `continuous_runtime.py`, an drei zentralen Legacy-Dispatchstellen und dem Keepalive/Ende der ursprünglichen main loop eingebunden durch `dispatcher_patch.py`. Sie ist **standardmäßig vollständig aus** und benötigt zwei explizite Environment-Flags sowie eine gültige, rootsignierte Dienstquellen-Zulassung. Es gibt weder ein zweites serielles Device noch generische RAM/RPC-Schreiboperationen.
- `ingress_epoch.py` blockiert MQTT-/TCP-Callback-Verarbeitung während P300 und speichert mehrere TCP-Kommandos in einer begrenzten FIFO statt des ursprünglichen verlustgefährdeten Einzel-Slots.
- `pending_refresh.py` registriert vier zeitversetzte HA-/set-Readbacks schon beim Anlegen der Timer; die Leseanforderung gilt erst nach tatsächlich erfolgreichem Original-Readback als abgeschlossen. Queue-Verlust, Timeout und unbekannte Tickets bleiben als Sperrgrund erhalten.
- `runtime_admission.py` interpretiert reine Original-VS1-Lesetelegramme weiterhin normal; ein bekannter Virtual_WRITE wird aber **nie allein durch ACK freigegeben**. Ein späterer erfolgreicher, bytegenauer Lesezugriff auf dieselbe Adresse und Datenlänge muss den geschriebenen Wert bestätigen; das gilt auch für Originalpoll-Listen. Für rohe oder unbekannte Telegramme bleibt ein absichtliches Sperrbit bestehen. Das zusätzliche Settlement ist mindestens 5,25 Sekunden.
- `producer_fence.py` schützt komplette Mehrtelegramm-Aktionen (inklusive Rollback) der externen Writer durch denselben `flock`, inklusive verschachtelter `apply_editor→apply`-Aufrufe. Ein SIGTERM/Crash hinterlässt einen fsync-festen ACTIVE-/FAILED-Marker. Das Sperrprotokoll verwendet `/var/lib/optolink-hybrid/producer-epoch.lock` und besitzt zusätzlich `P300_ACTIVE` / `P300_FAILED`. **P300 darf nur den Marker löschen, wenn die Original-VS1-GFA-Rückkehr bestätigt ist.** Solange ein P300-Marker besteht, werden auch neue externe Schreibtransaktionen verweigert.
- `producer_boundary_patch.py` erstellt ausschließlich **Kopien** für Party, Schedule, ServicePrograms, ClockSync und Maintenance, überprüft konkrete Funktionsnamen per AST und hält die Transaktionssperre bis zur Rücklesung.
- `runtime_enrollment.py` verweigert die Automatik ohne root-eigenes und lesbares Manifest, Source-Hashes der fünf Producer, aktualisierte echte systemd-Prozesse, aktive Uhr-Timer und leeren Persistenzmarker. Realer Host: `EnrollmentResult(accepted=False, reason='no root-owned enrollment manifest')` (beabsichtigter sicherer Zustand).
- `stage_release.py` erzeugte aus den echten installierten Quellen einen unveränderten Side-by-Side-Kandidaten mit 34 generierten Dateien unter `/home/chatgpt-admin/optolink-hybrid-candidate-20261010`. Stage-Hauptquelle stimmt in normalisierten Zeilenenden mit dem geprüften Original SHA256 `e4be265d…` überein. Rohdatei auf Datenträger durch CRLF: `f66b5a3e…`.
- Debian13 / Python3.13 Offline-Regression **464 Tests PASS** (`/tmp/optolink-continuous-finalreg-20261010.log`). Keine neue aktivierte Hardware-Automatik, denn alle realen Writer sind noch nicht installiert.

## Warum noch **nicht** produktionsreif

Der Root-Proof wird absichtlich noch nicht erstellt: alle fünf externen Writer müssen zunächst als eine gemeinsame Release-Einheit tatsächlich installiert, systemd-neugestartet, hashgepinnt und als lebende Prozesse nachgewiesen werden. Der Maintenance-Core ist ein separat importiertes Modul; die Programmdatei alleine zu ersetzen genügt nicht.

Zusätzlich müssen ein unabhängiger Watchdog/Recovery-Pfad für den **Dauerprozess** und der bei Neustart erhaltene HA-Readback-/Write-Zustand validiert werden. Der On-Demand-Recovery-Nachweis reicht nicht für unterbrechungsfreie Produktions-Watchdog-Anforderungen. Für einen echten P300-Absturz muss eine gesonderte VS1-Identitätsprüfung und Root-freigegebener Reset des `P300_FAILED`-Markers erfolgen, BEVOR wieder Schreiboperationen zugelassen werden.

**Die Ein-Port-Quelle bleibt vorerst der produktive unveränderte VS1-Splitter.** Der Pumpenoverride-Service bleibt inaktiv. Es wird nichts ohne ausdrückliche Betreiberfreigabe gemergt.

## Freigabekriterien für den Dauerswitch

1. Auf verifizierte Quellen gebundene parallele Installation aller Writer, Code-/Service-/Manifest-Backup und deterministischer Rollback.
2. Automatik zunächst in mit echten Quellen ausgeführtem Schattenbetrieb ohne Sendefenster: MQTT-/TCP-Stress und Party/Schedule/Clock/Service/Maintenance-Readbacks, inklusive SIGTERM während eines Schreibvorgangs.
3. Überwachter Hardware-Canary mit aktivierter read-only Automatik, initial mindestens drei saubere, wiederholte P300-Fenster. Dazwischen echte normale VS1-Telemetrie und Readback-Validierung; kein unerwarteter Fenster-Sprung über eine Schreibtransaktion.
4. Anlagengesundheit nach dem Canary: produktiver Splitter/HA-Dienste aktiv, GFA P80/P06 validiert, Service-Fehlerjournale geprüft; unabhängiger Restore bei jedem Fehler.
5. GitHub-CI in Python 3.11/3.12/3.13 und Betreiberfreigabe zum Merge **erst danach**.

Diese Dokumentation ist eine genaue Entwicklungs-/Abnahmeliste und **keine** Bestätigung eines fertigen Dauerbetriebs.
