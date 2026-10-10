# WB2A On-Demand P300: Hardware- und Recovery-Abnahme vom 10.10.2026

## Ergebnis

**Erfolgreich ist der zweite Versuch (C2)**: eine ausdruecklich angeforderte,
vollstaendig lesende P300-Diagnose innerhalb des bereits bestehenden seriellen
Optolink-Hauptprozesses. Danach echte Original-VS1-GFA-Pruefung und
unabhaengiger Systemd-Rollback. Die Produktivanlage laeuft wieder VS1.
**Kein RPM-Nachweis aus P300, keine Controller-RAM-Writes, kein Main-Merge.**

| Kriterium | Verifiziertes Ergebnis |
| --- | --- |
| Geraet | Vitodens 200-W WB2A / VDensHO1 / 20C2 |
| Feature-Release | `wb2a-demand-c2-20261010` |
| Canary-Session | `run-20261010T185043Z-324904` |
| Ziel | Genau 1 Read-only P300-FC03-Diagnosefenster |
| P300-RAW-Leseart | `p300_ram_0f20_32`, 32 Bytes |
| Durchlaufzeit | **5157.098 ms** |
| VS1-GFA nach Rueckkehr | P80=`20`, P06=`00` (0 rpm korrekt) |
| Canary-Journal | `PASS_ONE_VERIFIED_DEMAND_WINDOW`, `event_count=1` |
| Unabhaengiger Recovery-Bericht | `PASS_ORIGINAL_SERVICES_RESTORED`, `errors=[]` |
| Finaler `optolink-hybrid status` | `VS1_BETRIEB_OK`, Sperre `FREI`, Automatik aus |

Der Erfolg umfasst die in der originalen Dispatcher-Hauptschleife ausgefuehrte
serielle Diagnose, die vollstaendige urspruengliche VS1-Rueckkehr sowie die
Wiederherstellung aller sechs zuvor aktiven Dienste und Timer.

## 1. Vollstaendige RAW- und GFA-Evidenz

Die verifizierte FC03-Rohantwort des neuen On-Demand-Auftrags:
```text
sequence=1
kind=p300_ram_0f20_32
origin=P300_RAW_DIAGNOSTIC_NOT_ACTUAL_RPM
raw_hex=000900a3a40000010000006464580df50e18006408020000440ac2016b0d6b0d
vs1_p80=20
vs1_p06=00
elapsed_ms=5157.098
```

Das Feld `0x0F20` ist **kein bewiesener Drehzahl-Istwert**. Die Bytes duerfen
nicht als P06 oder RPM angezeigt werden. Der P300-Geraetehandshake erfolgte
innerhalb der bewiesenen bestehenden `HandoverCoordinator`-Funktion.
Nach Rueckkehr wurden die echten GFA-Reads P80 und P06 gelesen.

Ein erster Admissionversuch wurde mit `REAL_GFA_P06_NOT_FRESH` verweigert.
Das ist korrektes Fail-closed-Verhalten vor dem erfolgreichen Fenster.
Zusaetzlich wurden vor und nach dem supervisierten Canary gueltige VS1-GFA-
Antworten P80=`20` und P06=`00` registriert.

Gespeicherte unveraenderte Sitzungsquellen im LXC:
```text
/var/lib/optolink-hybrid/canary-sessions/run-20261010T185043Z-324904/
  continuous-measurement.json
  measurement.json
  recovery.json
  state.json
```

## 2. Fehlversuch C1 und konkrete Codekorrektur

Der erste Canary `wb2a-demand-c1-20261010`,
Session `run-20261010T184737Z-324115`, scheiterte reproduzierbar mit
`PlanRejected: not-yet-arrived jobs cannot be planned`.

Ursache: `BoundedDemandBatcher` plante bereits mit absoluten monotonen
Zeitstempeln in Millisekunden. Die Bridge rief den Planer ein zweites Mal
mit dem Default `now_ms=0` auf. Dadurch waren die bereits eingereihten
Tickets aus Sicht des zweiten Planers angeblich noch nicht angekommen.
Da der Transfer bereits begonnen hatte, loeste der Fehler die persistent
abgesicherte P300-Sperre und den unabhaengigen Canary-Abbruch aus.

C1 war **kein erfolgreicher P300-Test**, doch der Systemd-Rollback lieferte
`PASS_ORIGINAL_SERVICES_RESTORED`, echte VS1-GFA-P80=`20`, P06=`00`,
sechs wieder aktive Units sowie geleerten erst nach GFA-Readback
freigegebenen Producer-Marker.

Korrektur in `runtime_admission.py`, `dispatcher_bridge.py` und
`continuous_runtime.py`: der **gleiche monotone Zeit-Nullpunkt** und der
gueltige P06-Alterswert werden explizit an die Vorplanung und den
eigentlichen Phasenexecutor uebergeben. Der bisherige relative Standardpfad
bleibt aus Kompatibilitaetsgruenden unveraendert.

Eine eigens neue Testprobe verwendet FakeClock >1.234.567 Sekunden;
die P300-Demand-Anfrage inklusive Rueckweg besteht offline. C2 hat diesen
Fehler auf realer Hardware nicht mehr gezeigt.

## 3. Post-Recovery-Paritaet (read-only)

Nach C2 wurde `optolink-hybrid status` erneut ohne Nebenwirkung abgefragt:
alle sechs Standarddienste und Timer `active`, Canary und Pumpenoverride
`inactive`, `enrollment_vorhanden=false`, Producer-Lease `FREI`.
Nur der neue normale Original-Splitter besitzt das CP2102-Serial-Handle.

Eine eigene passive MQTT-Subscription ueber 16 Sekunden protokollierte
**594 eingegangene Nachrichten**, davon **294 echte neu veroeffentlichte**
und 300 Retained-Werte; **69 verschiedene aktiv aktualisierte Topics**.
`openv/geblaesedrehzahl_gfa_p06` wurde **10-mal neu** veroeffentlicht.
Die Subscription sendete **keine** Controllerkommandos.
Zusaetzliche explizite MQTT-Reads ueber den vorhandenen Splitter:
`gfaread;0x4050;1;raw;False -> 1;0x4050;20` und
`gfaread;0x4006;1;raw;False -> 1;0x4006;00`.

Dies beweist aktuelle MQTT-Verteilung, aber nicht unabhaengig,
dass Home Assistant jeden Topic-Wert zu einer Entity verarbeitet.

## 4. Automatik, Sicherheit und verbliebener Scope

- Die `demand-one`-Session wurde nur in einem root-eigenen, hashsicher
  vorbereiteten Shadow-Release aktiviert, mit expliziter Telemetrie-Pause.
- Canary Watchzeit 105 s, eigener Systemd-Timeout 210 s,
  `ExecStopPost` stellt Originalsystem auch ohne intakten Python-Supervisor
  wieder her. Es gab keinen langen unbeaufsichtigten Soak.
- Der normale `update`-Befehl und `main` wurden nicht veraendert;
  aus einem Hardware-Lesetest folgt **keine** Freigabe fuer P300-Writes.
- `OnDemandReadonlyRuntime.submit_internal()` ist ein strikt typisierter
  interner Weg. Ein allgemeiner externer MQTT-/TCP-P300-Endpunkt
  wurde **nicht** freigeschaltet.
- Vor der Freigabe eines produktiven Dienstpfads bleiben Schutz vor
  unerlaubten Request-Quellen, Fehler-/Timeout-Ereignislieferung und
  HA-Sensordarstellung gesondert zu begutachten.

## 5. Reproduzierbare Offline-Regression

```bash
cd /home/chatgpt-admin/optolink-wb2a-next-phase-20261010
python3 -m unittest discover -s tests -p 'test_*.py' -q
optolink-hybrid status
```

Nach Korrektur und vor C2: **315/315** Tests bestanden.
Der automatische `update`-Kanal bleibt bewusst auf dem bestehenden
stabilen `main`. Der Feature-Branch dient als getrennte PR-Basis.


## 6. Dritter Canary C3: manueller Root-Socket-Auftrag mit Ergebniskanal

Die zweite bestandene physische Abnahme am **10.10.2026** prüft nun nicht
nur den ursprünglichen internen Selbsttest, sondern die vollständige,
authentifizierte Operator-Schnittstelle.

| Prüfgegenstand | Tatsächliches Ergebnis |
| --- | --- |
| Root-eigenes Shadow-Release | `wb2a-manual-rpc-c3-20261010` |
| Canary-Session | `run-20261010T192559Z-327016` |
| Aufnahme | `sudo ... optolink-hybrid.py anfordern p300_ram_0f20_32 ...` |
| Request-ID | `eee42b270dac733e49a1811bdce929be` |
| Root-Gateway-Session | `a9cefcf93a25e4cec24660736eda0e3f` |
| Annahme | `ok=true`, `state=queued` |
| Endstatus per eigenem Root-CLI | `state=completed`, `verified_vs1=true` |
| Echte P300-FC03-Diagnose | `0x0F20`, genau 32 Bytes |
| Gemessener Protokollwechsel | **5180,292 ms** |
| Original-VS1-GFA nach Return | P80 `20`, P06 `00` |
| Sitzungsevents im echten Journal | **exakt 1** |
| Unabhängige Supervisorprüfung | `PASS_ONE_VERIFIED_DEMAND_WINDOW` |
| ExecStopPost-Rollback | `PASS_ORIGINAL_SERVICES_RESTORED`, `errors=[]` |
| Finaler Anlagenstatus | `VS1_BETRIEB_OK`, Writer-Sperre frei |

Vom Hardware-C3 erhaltener Rohblock:

```text
000900aeab00000100000064648d05f50e18006408020000440ac2016b0d6b0d
```

Die Rohdaten wurden sowohl vom originalen Hauptprozess protokolliert als
auch von `optolink-hybrid.py ergebnis` authentifiziert zurückgegeben.
Sie sind **kein** verifizierter Drehzahl-Istwert. Der neue lokale Socket
(`/run/optolink-hybrid/p300-demand.sock`, Datei `0600`,
systemd-`RuntimeDirectory` `0700`) wurde nach dem Canary wieder entfernt.
Es blieb kein Enrollment und kein temporäres systemd-Drop-in zurück.
Der ursprüngliche CP2102-Port gehört wieder dem originalen Splitter.
Die ursprünglichen sechs Dienste/Timer sind aktiv; Canary und
Pumpenoverride inaktiv.

Gespeicherte root-eigene Abnahmebelege:

```text
/var/lib/optolink-hybrid/canary-sessions/run-20261010T192559Z-327016/
  continuous-measurement.json
  measurement.json
  recovery.json
  state.json
```

Der exakte Root-Only-Request-Vertrag mit Allowlist, Peer-Prüfung,
TTL und expliziten Einsatzgrenzen ist in
[WB2A Root-On-Demand API](wb2a-root-on-demand-api-2026-10-10.md)
beschrieben.

Die ursprünglichen Angaben zu C1 (Abbruch plus funktionierender Recovery)
und C2 (bestandener interner Selbsttest) bleiben als getrennte,
unveränderte Versuchsnachweise gültig. Die 315 historischen Tests im
Abschnitt davor entsprechen dem Stand **vor C3**. Nach Ergänzung der
Root-Socket-Integration wurden **362/362** Offline-Regressionstests
erfolgreich durchgeführt.
