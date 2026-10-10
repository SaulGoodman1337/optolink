# Realauswertung und Korrektur des Produktions-GFA-Healthchecks (2026-10-09)

## Live-Messung (Commit c408f62, Session run-20261009T190552Z-294681)

Benutzerprotokoll: 77/77 lokale Offline-Tests bestanden; `systemd-run`
beendete den Worker erfolgreich (13,607 s Dienstlaufzeit). Der Worker
sendete ausschließlich die festen Lese-/Identitätstelegramme.
`measurement_errors=[]`, `recovery_errors=[]`,
`services_restored=true`, `unit_rc=0`; der reine
VS1→P300→VS1-Rundweg inklusive GFA dauerte **4666,291 ms**.

| Phase | Wert |
|---|---:|
| Unabhängiger VS1-Kaltstart (außerhalb des Rundwechsels) | 4365,844 ms |
| VS1→P300 inkl. ID/Software | 2175,657 ms |
| P300→VS1 inkl. ID/Software/P80/P06 | 2295,102 ms |
| Übrige GFA P09/P87 | 195,532 ms |
| Gesamt inklusive GFA | **4666,291 ms** |

Die jeweils erste ENQ nach EOT brauchte 2010,961 ms (P300) und
1998,460 ms (VS1). Beim initialen **Zwei-ENQ-Setup** erfolgte die
erste ENQ nach 1801,262 ms und die zweite nach **4039,479 ms
kumulativ seit EOT**, d. h. nach weiteren **2238,217 ms**.
Die Zeitstempel stammen aus der Host-Readeraufzeichnung, nicht einem
Logic Analyzer. Die Setup-Zeit zählt nicht zum eigentlichen Rundwechsel.

Gegenüber dem vorherigen n=3-Ein-ENQ-Hardware-Mittel von
4610,091 ms ist dieser n=1-Run **56,200 ms (+1,22 %) langsamer**.
Die Stichproben sind nicht gepaart und die Verifikationssegmente sind
unterschiedlich; daraus folgt kein nachgewiesener Geschwindigkeitsgewinn
oder belastbarer Nachteil.

## Fehlerursache der Abschlussprüfung

Das Ergebnis war `FAIL_OR_NOT_VERIFIED`, obwohl der Worker Erfolg
und das Service-Restore-Manifest Vollständigkeit meldeten.
Die P80/P06-Health-Objekte hatten `rc:0` aber `valid:false`.

Im verwendeten `read_health()` wurde fälschlich
`subprocess.stdout.strip().startswith('1;')` geprüft. Der tatsächlich
benutzte `optolink-debug` gibt *zuerst* eine MQTT-Verbindungszeile aus
und druckt die eigentliche Antwort später im Format
`gfaread;... <- <topic>: 1;0x4050;20`.
Dazu wurden nur die ersten 100 Zeichen archiviert, sodass die
eigentlichen Antwortzeilen verloren gingen.

**Festgestellt:** Ein Bug im Health-Parser erzeugt einen falschen
Negativbefund bei gültig formatierten Debugclient-Ausgaben. **Nicht
festgestellt:** Ob P80/P06 nach dieser konkreten Restore-Session
tatsächlich erfolgreich über die produktive MQTT-Verbindung gelesen
wurden – die dafür nötigen Original-stdout-Zeilen fehlen im gespeicherten
Bericht. Das historische Ergebnis bleibt deshalb **unverifiziert**,
nicht nachträglich auf PASS gesetzt.

## Korrektur ohne erneuten Handover

`parse_debug_health()` extrahiert eine einzelne, eindeutig zugeordnete
Antwortzeile, prüft Echo, Statuscode 1, exakte GFA-Adresse,
ein gültiges Nicht-FF-Rohbyte und P80=20. `rc=0` allein ist
**kein** Erfolgsnachweis: auch `<- timeout` wird verworfen.
Das Ergebnis speichert nur die extrahierte Antwort, nicht Broker-Banner,
Benutzernamen oder Serveradressen.

`live_probe.py --health-only` führt einen neuen, **separat datierten
post-hoc Nachweis** durch; dieser ist nicht gleichzusetzen mit einer
Messung unmittelbar nach dem historischen Hardwarelauf.
Der Modus verwendet ausschließlich den vorhandenen
`optolink-debug`-MQTT-Client und setzt eine laufende originale
VS1-Produktion und konfliktfreie Forschungsprozesse voraus.
**Kein systemd stop/start, kein Öffnen des seriellen Geräts, keine
EOT-/ENQ-Umschaltung, keine Wiederholung des Hardwaretests.**

Bei `PRODUCTION_HEALTH=FAIL_NOT_VERIFIED` nicht unverändert weiter
testen. Erst bestehende Splittergesundheit und den Brokerpfad prüfen.
Der Original-Live-Rundweg von 4666,291 ms bleibt unabhängig von einer
nachträglichen Health-Prüfung valide messbar.

## Separat nachgewiesener Produktionszustand (post-hoc)

Der Betreiber hat nach Einchecken des Parser-Fixes und nach erfolgreich
abgeschlossener Python-3.11/3.12-CI den gepinnten Commit
`9c1922a08cadb5525f9b177b525bf166ea759e1a` im LXC geladen und
`live_probe.py --health-only` ausgeführt.

Ergebnis aus der vom Betreiber geposteten Konsole:

```text
PRODUCTION_HEALTH=PASS
PRODUCTION_HEALTH_JSON={"P06": {"rc": 0, "reason": "OK", "response": "1;0x4006;00", "valid": true}, "P80": {"rc": 0, "reason": "OK", "response": "1;0x4050;20", "valid": true}}
```

**Interpretation:** Der bestehende produktive VS1-Splitter hat nach
dem Protokolltest beide echten GFA-Reads über den MQTT-Debugclient
bestätigt; P80=20 und P06-Rohwert 00 sind korrekt.
`--health-only` öffnet selbst keinen seriellen Port und stoppt keine
Dienste. Die Eingabe belegt keine veränderten Heizungswerte und keine
zusätzliche Handover-Beschleunigung.

**Beleggrenze:** Der Konsolenauszug hat keinen eigenen timestamp.
Dies ist ein *späterer* unabhängiger Produktions-Healthcheck, kein
Zeitstempel unmittelbar nach `run-20261009T190552Z-294681`.
Der ursprüngliche `summary.json`-Befund
`FAIL_OR_NOT_VERIFIED` bleibt unverändert; er darf nicht nachträglich
in einen erfolgreich abgeschlossenen ursprünglichen End-to-End-Test
umbenannt werden. Die on-wire-Messung selbst zeigte keine
`measurement_errors`, die Originaldienste wurden als wiederhergestellt
gemeldet. Eine nochmalige identische Hardwareprobe ist unnötig.

Beweisquelle: Betreiber-Konsolenausgabe im Forschungs-Chat, kein
unabhängig heruntergeladenes Roharchiv. Die normalisierte Einzeldokumentation
liegt in `docs/evidence/handover-production-health-posthoc-2026-10-09.json`.

## Sicherheitsgrenzen

Nur Branch `optolink-handover-acceleration`. Keine Änderung an
`/opt/optolink`, `optolink-p300-migration`, Draft-PR #46,
laufenden Loggern oder der Regelung. Alle experimentellen Schreibbefehle
bleiben ausgeschlossen. Eine erneute serielle Probe ist zur
Beseitigung dieses Parserfehlers weder notwendig noch vorgesehen.
