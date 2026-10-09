# VS1 ↔ P300: echte Beschleunigungswege und Early-START-Experiment

**9. Oktober 2026 · Forschungsbranch `optolink-handover-acceleration` · nur neuer Testcode; keine Produktionsintegration.**

## Kurzfazit

Die Grenze von vier Sekunden gilt **nur für die bislang erfolgreich geprüfte Nachrichtenfolge**. Die letzten WB2A-Messwerte ergeben 4666,291 ms je VS1→P300→VS1-Runde inklusive GFA. Davon entfallen nach den Hostzeitstempeln 2010,961 ms auf EOT→P300-ENQ und 1998,460 ms auf EOT→VS1-ENQ. **4009,421 ms (85,92 %) der Runde sind diese beiden beobachteten ENQ-Wartezeiten.** Weitere 656,870 ms sind Nutzdaten-/Prüf- und Hostzeit. Die tatsächlichen Zeitpunkte im Controller und auf der UART-Leitung sind nicht durch einen separaten Logic Analyzer gemessen worden.

**Eine schnellere Variante ist nicht ausgeschlossen, aber noch unbewiesen.** Firmware-/Controllercode wurde nicht verändert. Das Dokument bietet eine bewusst experimentelle Variante mit bekannten Steuerbytes zu einem bisher nicht bestätigten Zeitpunkt an: `16 00 00` nach `04`, **vor** dem periodischen `05`. Der dokumentierte P300-Standard fordert die umgekehrte Reihenfolge (erst ENQ, dann START). Diese Variante darf weder als protokollkonform noch als nachgewiesen schneller bezeichnet werden.

## Woher die 2 Sekunden wahrscheinlich kommen

- [OpenV P300](https://github.com/openv/openv/wiki/Protokoll-300): nach EOT `04` sendet die Steuerung **periodisch etwa alle 2 Sekunden** ENQ `05`. Erst danach soll `16 00 00` gesendet und `06` empfangen werden. Die START-Sequenz darf **innerhalb einer bestehenden P300-Sitzung** periodisch zur Verbindungserhaltung gesendet werden. Das legitimiert nicht ihre beliebige Verwendung während VS1.
- [OpenV KW/VS1](https://github.com/openv/openv/wiki/Protokoll-KW): ENQ `05` ist ein initiales Angebot der Vitotronic, ein folgendes `01` bestätigt es. Weitere KW/VS1-Anfragen derselben bestehenden Sitzung können ohne erneutes `01` folgen.
- Die lokale neue Implementierung verwendete **kein 2-Sekunden-Python-Sleep**, sondern `timeout=0` und ca. 1-ms-Leerread-Polling. Ein schnelleres Polling beseitigt kein ENQ, das vom Controller erst ~2 Sekunden später kommt.
- Hostzeit EOT→ENQ bleibt eine Überlagerung aus Controller, CP2102, Kernel und Scheduling. Das nahezu konstante Intervall legt Controller-/Protokoll-Taktung nahe, beweist aber keinen absolut festen Firmwaretimer.

## Bereits erledigte reale Varianten – nicht erneut unverändert testen

| Variante | Dauer inklusive vier GFA | Belegstatus |
|---|---:|---|
| Zweite ENQ auf VS1-Rückweg abwarten | 6862,980 ms (n=3) | Reale Baseline |
| VS1-Rückkehr **nach einem** ENQ mit Identität/GFA | 4610,091 ms (n=3) | Reale, sichere Einsparung 2252,889 ms bzw. 32,8 % |
| Natürliches ENQ statt EOT für P300-Einstieg | 5628,235 ms (n=3) | Reale negative Variante (+1018,144 ms) |
| Neuer verifizierender Handover-Koordinator | 4666,291 ms (n=1) | Echtgerät, kein zusätzlicher Geschwindigkeitsgewinn |

Quellen: `docs/p300-handover-baseline-result-and-single-enq.md`, `docs/p300-idle-enq-result-2026-10-08.md` aus `optolink-p300-migration` sowie der eigenständige [Live-Audit](handover-live-result-parser-fix-2026-10-09.md) mit später separatem, gültigem MQTT-P80/P06-Healthcheck.

## Welche Hypothesen offen sind

| Hypothese | Bedeutung | Evidenz | Risiko und Abbruchbedingung |
|---|---|---|---|
| A: START `16 00 00` sofort nach EOT **vor ENQ** | Könnte die P300-Einstiegswartezeit eliminieren (~2 s) | Nicht in OpenV dokumentiert, noch nicht an WB2A getestet | Kein ACK innerhalb 350 ms, NACK oder falsche Geräteidentität: **kein Erfolg**, gesonderter konservativer 2-ENQ-VS1-Restore |
| B: VS1-Identitätsread nach EOT **vor ENQ** | Könnte die VS1-Rückwegwartezeit eliminieren (~2 s) | Nicht dokumentiert; bisherige sichere erste ENQ wird abgewartet | Noch **nicht** als Live-Variante implementiert; nur falls Hypothese A und Quellenlage weitere Prüfung rechtfertigen |
| C: Wiederverwendung einer bestehenden P300-Sitzung | Spart zusätzliche P300-Inits **innerhalb derselben Sitzung** | Dokumentiert; fortlaufende P300-Daten ohne ENQ | Nach EOT/anderem Protokoll ist der alte Nachweis ungültig |
| D: Vollständigen Wechsel vermeiden | Spart 4,47+ s pro unabhängigem P300-Batch | Softwarearchitektur, nicht Firmwarevorteil | P06-Frische, Deadline, Reihenfolge und Freigaben müssen passen |
| E: Falschen zweiten ENQ abwarten | Spart 2,25 s | **Bereits bewiesen und umgesetzt** | Nicht mit anderen Änderungen vermischen |

Nicht zulässig als Beweis: das Senden von START ohne ENQ *und* eine Fehlermeldung als Erfolg interpretieren, eine alte Gerätekennung wiederverwenden, eine FF-GFA-Antwort zu akzeptieren oder P09/RAM als P06-Drehzahl auszugeben.

## Warum <4, <2 oder <1 Sekunde nicht rein durch Python-Sleep zu erreichen sind

Aus der einmaligen neuen Hardwaremessung gilt für genau diesen EOT/ENQ-Ablauf:

`T = 4009,421 ms (ENQ) + 656,870 ms (alles andere) = 4666,291 ms`.

- **Unter 4 s**: >666,291 ms Ersparnis erforderlich; die *beiden* aktuellen ENQ-Wartezeiten allein überschreiten 4 s bereits.
- **Unter 2 s**: >2666,291 ms Ersparnis erforderlich; eine vollständig vermiedene 2-s-Phase reicht noch nicht.
- **Unter 1 s**: >3666,291 ms Ersparnis erforderlich; bei unveränderten übrigen 656,870 ms dürften die gesamten Rest-ENQ-Warten zusammen nur noch <343,130 ms dauern.

Das ist eine konditionale Untergrenze für **genau diese bisherige Nachrichtenfolge** – kein Beweis gegen anders getaktete zulässige Framefolgen. Höhere Baudrate oder kürzere Host-Timeouts machen ein noch nicht eingetroffenes Controller-ENQ nicht früher; beide gefährden bei unbedachtem Einsatz den Erfolgsnachweis.

## Experiment A: nur frühes P300-START mit bekanntem Telegramm

In `coordinator.py` ist **nicht** der dokumentierte Handover geändert, sondern eine opt-in Methode `to_p300_early_start_experiment()` hinzugekommen. `live_probe.py --experiment-early-p300-start` aktiviert sie ausdrücklich; ohne Flag bleibt das Verhalten erhalten.

```text
Bestehende Produktivdienste         (zunächst unverändert)
           |
  Preflight: kein RPM-Logger / Forschungskonkurrent / fremder Portbesitzer
           |
  unabhängigen systemd-Supervisor und selektives Restore installieren
           |
  vorübergehender Stopp der originalen Dienste (nur bei explizitem Opt-in)
           |
  eigener VS1-Kaltstart: EOT + **zwei** ENQ + frische ID/SW/P80/P06
           |
  EIN experimenteller Übergang: EOT (04) + 25-ms-Leitungspause + START (16 00 00)
           |             **ohne vorheriges ENQ**
           +-- ACK 06 in <= 350 ms? -- nein --> FAIL / konservativer Restore
           |
           +-- ja: exakte P300-Gerätekennung 20C2 und Software 0103
                              |-- unpassend/CRC-falsch --> FAIL / Restore
                              +-- gültig --> dokumentierter VS1-Rückweg
                                             EOT + 1 ENQ + ID/SW/P80/P06
                                             danach GFA P09/P87
                                                    |
                                             separater Systemd-Restore
                                             frischer produktiver MQTT-Check
```

**Keine unbekannten GFA-/RPC-/RAM-Schreibbefehle.** Trotzdem ist das Senden der Synchronisationssequenz *vor* ENQ ein unbestätigter Controllerzustand: Bei Ablehnung kann die serielle Protokollsession für Sekunden gestört werden, und die Wiederherstellung muss erfolgreich sein. Daher ist dies nur ein **einzelnes explizites Hardwareexperiment**, niemals ein dauerhafter autonomer Versuch oder ein Produktionsmodus.

- Der unabhängige `ExecStopPost`-Recoverypfad ist bereits im Testharness vorhanden und wurde zuvor bei einem gültigen Hardwarelauf bestätigt. Er kann bei USB-/Firmwarefehlern keinen garantierten Erfolg versprechen.
- Kein laufender RPM-/P300-Logger wird angehalten; der Vorcheck verweigert dann die Ausführung.
- Bei Scheitern des frühen START wird nicht versteckt ein normales P300 gestartet; der Befund heißt fehlgeschlagen, und die konservative VS1-Wiederherstellung wird getrennt durchgeführt.
- Es darf nur eine bewusst genehmigte Einzelausführung geben, kein Retry-Loop.
- Kein Gerätedefekt ist aufgrund des Codes auszuschließen. Ausführungsentscheidung liegt beim Betreiber.

## Kostenbewusster Offline-Batch-Planer

`tools/handover_acceleration/phase_planner.py` ist **nur Offline-Planung**, nicht Hardwareausführung. Er verbindet den bekannten Budgetwert für VS1→P300 (2175,657 ms) und P300→VS1 mit nachzuweisenden Frische-/Deadline-Budgets. Die zu erwartenden 2-s-Wartezeiten verschwinden dabei nicht; ein P300-Fenster kann nur über mehrere unabhängige Aufträge amortisiert werden.

- Ohne ausdrücklich bestätigte `independent=True`-Eigenschaft bleibt die Reihenfolge erhalten. Kein Reordering über Schreib-/Readback-/Abhängigkeitsbarrieren.
- Mit 12 VS1- und 12 **unabhängigen** P300-Leseaufträgen kann ein Modell ein einziges P300-Fenster bilden statt drei bei der bisherigen 4-Request-Fairness.
- Bei einer erforderlichen echten VS1-P06-Frische von **2,1 s** wird bereits ein einziger P300-Zyklus mit den beobachteten 4,47 s Grundwechselzeit abgelehnt. Das zeigt, dass Batching allein ein solches Echtzeit-Lastenheft nicht erfüllen kann.
- Alle Ausführungsdauern sind engineering estimates (ein echter Worst Case wurde nicht gemessen); keine Lösung für einen sicherheitskritischen Echtzeit-Regelkreis.

`trace_attribution.py` zerlegt gespeicherte Host-TX/RX-Zeitstempel ohne Hardwarezugriff in EOT→ENQ, TX→erste RX-Bytes und RX→nächsten TX. Zusammengefasste RX-Chunks werden ausdrücklich nicht als einzeln getaktete UART-Bytes ausgewiesen. Das erlaubt gezielte Identifikation weiterer 10-/25-ms-Guard-Potenziale ohne unbegründete Sekundenbehauptungen.

## Forschungs- und Produktionsgrenze

Alles auf Branch `optolink-handover-acceleration`. `/opt/optolink`, `optolink-p300-migration`, PR #46, logger und aktuelle GFA-Kanäle werden nicht geändert. Ein positiver Early-START-Nachweis würde zunächst nur einen **neuen Lesepfad** verifizieren; ein produktiver In-Process-Manager benötigt weiterhin vollständige Requests-/Writes-/Readbacks- und unabhängige Recovery-Parität.
