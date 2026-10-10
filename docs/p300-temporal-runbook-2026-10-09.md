# P300 Temporal: detailreicher RAM-/Status-Dynamiklogger und Experimentplan

> **Live-Update 9.10.2026, 15:14 MESZ:** Der Fokuslauf (8 COMPLETE, qualifiziert 3 OFF / 1 × 2490 RPM) und der 5-Minuten-Temporal-Canary (191 vollstaendige Kernzyklen, 852 valide Telegramme, Restore gesund) sind **abgeschlossen und die hochgeladenen Archive unabhaengig SHA256-validiert**. Der **2h Full-Run** `run-20261009T131357Z-220351` **laeuft bereits** mit eigenstaendig gepinntem Code. **Keinen zweiten Logger starten.** Siehe [Live-Checkpoint, Archive und Auswerte-/Entscheidungsplan](p300-temporal-live-checkpoint-and-decision-plan-2026-10-09.md). Die folgenden Startanweisungen sind das urspruengliche historische Runbook, nicht eine Aufforderung zum erneuten Start.

Stand 09.10.2026. **Ausschließlich Aufgabe 1, Gerät 20C2 / Software 0103 / P80=20.** Die Produktionsinstallation /opt/optolink wird nicht verändert; PR #46 bleibt Draft und wird nicht gemergt. Der aktuell laufende Fokuslogger muss zuerst vollständig beendet und gesund wiederhergestellt werden. Der Temporal-Logger ist ein neuer, erst offline zu testender experimenteller Protokollbesitzer, noch nicht live an der WB2A erprobt.

## 1. Ausgangsbefund und zentrale Änderung der Methode

Nach 2.268,621 Sekunden meldete der aktuelle Fokuslogger 6 COMPLETE, 0 PARTIAL, 3 STABLE_OFF, 0 STABLE_2490, 0 STABLE_OTHER_POSITIVE, 3 TRANSITION_OR_UNKNOWN, 72 FC03-Pakete und 12 Protokollwechsel. Aufnahme 6 hat PRE-P06 [2490] und POST-P06 [2460,2490]. Das vorab verlangte exakt stabile P06-Fenster ist während natürlicher Drehzahlschwankungen sehr streng. Ein neuer identischer VS1/P300-Pendel-Logger wäre wenig erkenntnisstark.

Der Voll-RAM-Logger hat dagegen 79 qualifizierte Abbilder geliefert. 0x0F20 == 0x1C76 in 79/79, 0x0F28 == 0x1C7D, 0x0F29 == 0x1C7E. Bei stabil AUS / 2490 rpm laut GFA-P06 gilt für das erste Paar 00/54; P06-RAW ist dagegen 00/53. Die Kopien legen Status-/Prozesspuffer nahe; eine echte Drehzahldekodierung ist unbewiesen.

**Neuer Ansatz:** Eine einzige längere P300-Sitzung ohne VS1-GFA-Abfragen zwischendurch, mit natürlichen Brennerzyklen und viel schnelleren RAM-Mikroreads. Das prüft Autonomie, Aktualisierungsreihenfolge und Strukturkopien. Es kann **keinen zeitgleichen echten P06-Wert unter P300** erzeugen und ersetzt deshalb keine eigenständige Ist-RPM-Validierung.

## 2. Exakte Hardware-Allowlist

Erlaubte P300-Pakete sind genau sieben bereits physisch getestete Leseformen:

| FC | Physische/virtuelle Adresse | Länge | Erfassungsmodus |
|---|---|---:|---|
| FC01 | 0x55D3 | 11 Byte | vor UND nach jedem Zweier-RAM-Paar |
| FC03 | 0x0F20 | 32 Byte | Hauptfenster, immer |
| FC03 | 0x1C60 | 32 Byte | Hauptfenster, immer |
| FC03 | 0x0F00 | 32 Byte | ergänzend circa alle 12s |
| FC03 | 0x0F40 | 32 Byte | ergänzend circa alle 12s |
| FC03 | 0x1C40 | 32 Byte | ergänzend circa alle 12s |
| FC03 | 0x1C80 | 32 Byte | ergänzend circa alle 12s |

Jeder Kernzyklus: Status A → RAM 0x0F20 → RAM 0x1C60 → Status B. Beide Statusframes, der rohe 64-Byte-RAM-Paarinhalt und alle einzelnen FC03-/FC01-Frames werden archiviert. Status A/B machen natürliche Flammenbit-/P87-Wechsel innerhalb eines Messzyklus sichtbar. Wenn eine Statusänderung die nichtatomare RAM-Paarlesung überlappt, wird der Zyklus als zeitlich nicht kohärent markiert und darf nicht als Momentaufnahme interpretiert werden.

Die zusätzlichen 4 × 32 Byte beschreiben die Nachbarschaft und alte doppelte Statusobjekte. Keine Reads bei 0x03AE/U1RB, kein SFR, kein FC04, C9, 09, fremdes P300-RPC oder irgendein physischer Write. Abgebildete RPM-Werte stammen nur aus VS1.

## 3. Zeitachsen, dynamische Trigger, natürliche Ereignisse

- Normales periodisches Zielintervall: **1,5 Sekunden** (keine Echtzeitgarantie).
- Natürlicher Flammen-/Lockout-Wechsel: bis zu 35s schneller Burst, Zielintervall **0,5 Sekunden**, begrenzt durch Drahtantwort-/Handshakezeit.
- Änderung des nativen Statusbytes 7 (P87-Indiz): bis zu 20s Burst.
- Große Modulationsänderung auf Byte0/9: 8s Burst; mindestens 60s zwischen solchen Modulations-Burst-Triggern.
- 32-Byte-RAM-Reads dauerten im vorherigen Vollscan ungefähr 138ms im Median, daher beanspruchen bereits die zwei Hauptreads ~0,28s und zwei Statusreads zusätzliche Zeit. Tatsächliche Zeitstempel und Frame-Dauer bleiben maßgeblich.
- Jeder Datensatz enthält Host-UTC und monotone Zeiten sowie alle Statusbytes, Request, ACK, vollständige Antwort, Checksumme, Adressen, Länge und Byte-SHA256.
- Kein künstliches Brenneranfordern, keine Änderung einer Pumpenkonfiguration, keine Vorhersage künstlicher Brennerzyklen.

**Wichtige Semantik:** P300-Statusbyte0, Byte9 und GFA-P09 sind (zum Teil) Stell-/Modulationsdiagnosen, keine unabhängige Gebläse-Istdrehzahl. P06 unter VS1: echtes GFA-RAW × 30 U/min, FF ungültig. Die Initial-/Final-Referenz P06/P09/P87/P80/P10/P84 beweist nur den Zustand in den jeweiligen VS1-Phasen, nicht in der Zwischenzeit.

## 4. Ein einziges serielles Besitzfenster und Wiederherstellung

Phase A: produktive Dienste konfiguriert und aktiv; Preflight prüft richtigen Forschungsbranch, exklusiven Port, Main-WorkingDirectory /opt/optolink, genügend Plattenreserve, freien Test-Unit-Slot sowie alte fokussierte Recovery- und Health-Dateien. Danach werden nur für die Forschung die zuvor aktiven OpenV-Dienste/Timer vorübergehend pausiert; die Heizungsregelung wird dabei nicht umprogrammiert.

Phase B: VS1 20C2/0103-Identität und **circa 6 Sekunden echte GFA-P06/P09/P87/P80/P10/P84-Referenz**, einschließlich P80=20, mindestens einem gültigen P06. Über den geprüften ENQ/EOT-Mechanismus in P300 wechseln.

Phase C: **ununterbrochener P300-Only-Status-/RAM-Stream**, kein erneuter VS1-GFA-Read in dieser Hauptphase. Fehler, Roh-RX und Transaktionszeit offen protokollieren; bei serieller Abweichung fail-closed aussteigen. SIGTERM erst zwischen kompletten Frames beachten.

Phase D: kontrolliert nach VS1 wechseln, Identität prüfen, erneut echte GFA-Referenz erfassen. Danach wird nochmals ein geprüfter P80/P06-Read im Worker vorgenommen. Der eigene systemd-ExecStopPost stellt die zuvor aktiven Originaldienste wieder her, **Hauptsplitter zuerst**, und prüft Produktiv-MQTT-P80/P06-Nicht-FF. Ein HA-Entity-Frischenachweis ist dadurch nicht automatisch gegeben. Fehlgeschlagene Messung und erfolgreiche Wiederherstellung bleiben getrennte Qualitätsmerkmale.

**Dauer:** zwingender 5-Minuten-Canary vor der ersten vollen Messung; anschließend Standard 2h, Startargument 1, 2 oder 3h, höchstens 24.000 Kernzyklen. Startreserve mindestens 768 MiB, Laufreserve mindestens 256 MiB; private Rohsession max. 192 MiB, Einzeldatei max. 96 MiB. Nur diese zwei bekannten RAM-Kandidaten plus Nachbarschaft; keine Wiederholung des früheren 640-Block-Vollscans.

## 5. Start-Gates und Bedienung – NICHT während des laufenden Fokusloggers

**Vorbedingung A:** der alte optolink-p300-p06-focus.service ist inactive. Die vorher aktive Produktionskonfiguration ist wiederhergestellt und in der neuesten Fokussession liegen recovery.json/services_restored=true und health.json mit production_main_verified=true, P80/P06 format_and_identity_verified und P06 p06_non_ff_verified=true. Privatarchiv des Fokusloggers vorhanden. Die neue Unit verweigert einen Start, solange die alte aktiv ist oder diese Daten fehlen/negativ sind.

**Vorbedingung B:** das Fokus-Endarchiv zuerst auf einen eigenständigen gültigen P06-Kanal prüfen. Falls dort entgegen dem Zwischenstand bereits zwei verschiedene positive stabile RPM-Level mit nachgewiesener unabhängiger Speichersemantik gefunden werden, die folgende Experimentfrage neu priorisieren statt routinemäßig 2h Betrieb zu pausieren.

**Vorbedingung C:** neuer CI-Lauf erfolgreich; tracked Git-Dateien sauber; nur Forschungscheckout und Fast-forward. Startwrapper führt sämtliche Test-Suiten lokal erneut aus.

Bedienung (nur nach erfolgreich abgeschlossenem Fokuslogger, niemals gleichzeitig):

~~~bash
# Plan ohne serielle oder systemd-Aktion
bash /root/p300-trial-work/project/tools/wb2a-p300-temporal-logger.sh plan

# Experimenteinsatz nur nach CI und Restore-Gates
cd /root/p300-trial-work/project
git fetch origin optolink-p300-migration
git merge --ff-only FETCH_HEAD
bash tools/wb2a-p300-temporal-logger.sh start 2

# Monitoring / geordneter Stopp:
bash tools/wb2a-p300-temporal-logger.sh status
bash tools/wb2a-p300-temporal-logger.sh stop
~~~

**Systemd-Unit:** optolink-p300-temporal.service. Keine automatische Aktivierung. Type=exec, Restart=no, TimeoutStopSec=300, KillMode=control-group; ExecStopPost führt den gesonderten Produktions-Restore aus. Die vollen Rohdaten bleiben nur in privaten Session-Verzeichnissen. Das Profil für HA/MQTT bleibt produktiv unangetastet.

### Zweistufige Hardware-Freigabe: zuerst kurzer Canary, dann Hauptlauf

**Vor dem ersten zweistündigen Lauf MUSS ein erfolgreicher fünfminütiger Canary erfolgen.** Der Code verlangt hierfür ausdrücklich eine zuvor angelegte Canarysitzung mit MODE=canary und DURATION_SECONDS=300, mindestens 30 vollständig protokollierten Kernzyklen, einer P300-only-Beobachtungszeit von mindestens 240 Sekunden, keinem Stoppsignal, measurement.observation_complete=true, worker_vs1_restored=true, keinen Workerfehlern, recovery.services_restored=true, produktiver P80-/P06-Nicht-FF-Health und vorhandenem Canary-Tar.gz-Archiv. Ein nur gestarteter oder vorzeitig abgebrochener Canary schaltet den Langlauf NICHT frei.

Reihenfolge nach vollständigem Fokus-Restore und Archivkontrolle:

~~~bash
# 0. Nur informationshalber, keine Geräte- oder Serviceaktion
bash tools/wb2a-p300-temporal-logger.sh plan

# 1. Erst fünf Minuten P300-Read-only-Canary, eigener geordneter VS1-Restore
bash tools/wb2a-p300-temporal-logger.sh canary

# 2. Den Canary bis Unit inactive, RESTORED, P80/P06-Health und Bundle abwarten
bash tools/wb2a-p300-temporal-logger.sh status

# 3. Erst wenn der Canary wirklich bestanden ist, Langzeitlogger
bash tools/wb2a-p300-temporal-logger.sh start 2

# 4. Status / manueller sicherer Stopp des jeweils aktiven Experiments
bash tools/wb2a-p300-temporal-logger.sh status
bash tools/wb2a-p300-temporal-logger.sh stop
~~~

Die Canary-Ausführung pausiert ebenfalls vorübergehend produktive Optolink-Telemetrie. Sie ist **kein** unabhängiger Tachonachweis; ihr Zweck ist die praktische Transportsicherheit, Datendichte und Recoveryprüfung der neuen Software. Ein Fehler im Canary verlangt zuerst Fehleranalyse und Wiederherstellung, nicht automatisches Weiterfahren mit zwei Stunden.

## 6. Reproduzierbare Rohdatenausgabe

| Sessiondatei | Auditinhalt |
|---|---|
| vs1.jsonl | getrennte echte PRE/POST-GFA-Referenzen mit Einzelzeitstempeln |
| switch.jsonl | reale Handover-Handshake-Timings, Identitätsstatus, Fehler |
| packets.jsonl | **jedes** P300-FC01-/FC03-Telegramm, inkl. roher Antwort und ungültiger RXs |
| cycles.jsonl | Status-Paar, Kontext, alle 0F20/1C76-Mirror-Bytes, Qualität, SHA/Offsets |
| events.jsonl | Flammen-/P87-/Modulations-/Kandidatenänderungen |
| core-pairs.bin | genau 64 Byte pro vollständig gemessenem Kernzyklus |
| context-frames.bin | je genau 128 Byte für ein vollständiges Kontext-Viererpaket |
| trace.jsonl | separate native Byte-TX-/RX-Aufzeichnung |
| state.json + gepinnte *.py | Quellversionen, SHA256, Historie und Dienste |
| measurement.json/progress.json | Gesamtzähler, limitierende Gründe, Signale |
| recovery.json/health.json | Produktivrecovery, Main-/P06/P80-Health |

Ein einziges privates Bundle: /root/p300-trial-work/research-bundles/p300-temporal-run-YYYYMMDDTHHMMSSZ-PID-bundle.tar.gz, mit SHA256-Manifest jeder Datei. Keine MQTT-Zugangsdaten oder Produktions-Settings werden aufgenommen. Es wird kein privates Roharchiv in Git gepusht.

## 7. Offline-Auswerteplan nach diesem Logger

1. **Forensik:** Manifest gegen jede Datei, Framing/ACK/FC01/FC03/Adresse/Len/Checksumme aller einzelnen P300-Frames, lückenlose Zyklusnummern, Binäroffsets/Payload-SHA256 gegen JSONL; unerwartete Writes müssen exakt null sein. Separat Ende, Wiederherstellung und echte GFA-P80/P06 prüfen.
2. **Ereignisse:** natürliche Flamme EIN/AUS, Zeitstempel und P87-Byte7-Zustandswechsel über mindestens ein vollständiges Brennerfenster; bei null Wechseln Ergebnis ausdrücklich INCONCLUSIVE, kein erfundener negativer Beweis.
3. **Doppelte Bytes:** 0F20 gegen 1C76; 0F28 gegen 1C7D; 0F29 gegen 1C7E und native Byte7; Häufigkeit und Richtung zeitlich versetzter Updates messen. Weil die Frames nacheinander kommen, müssen Zeitabweichungen vom Messversatz getrennt bleiben.
4. **Betriebszustand vs. Sollwert:** alle Kandidatenänderungen gegen native Flame/Lockout, Byte0/7/9 korrelieren. Änderungen der Ansteuerung sind kein Tachometernachweis; insbesondere nicht P09 als P06 ausgeben.
5. **Entscheidung P06:** nur 00/54 über mehrere *echte* Brennzyklen bei verändertem Status/Modulationssignal stützt die Hypothese Zustands-Flag. Unterschiedliche Kandidatenwerte erlauben weitere gezielte Untersuchung, beweisen aber immer noch keine echte Umdrehungszahl. Ein direkter RPM-Kanal benötigt einen unabhängigen echten P06-Benchmark bei mehreren positiven Niveaus.
6. **Wenn kein unabhängiger Fan-IST:** keine weitere ungerichtete RAM-Flut; stattdessen Single-Owner P300/VS1-GFA-Hybrid zur vollständigen Aufgabe-1-Funktionsparität vorbereiten. Alte Wechselzeit ist insgesamt ~6,5s, alle HA-/MQTT-/Service-/Frische-Readbacks prüfen. Die 22 VDensHO1-RPC-Events dürfen parallel nur offline auf GFA-Gateway-Evidenz untersucht werden.

**Weitere Aufgaben tabu:** keine Vitotrol-/KM-Bus-Task-2-Implementierung, keine Pumpenwrites aus Task 3. P300-P06 bleibt ungeklärt bis zum echten Hardware-Nachweis.
