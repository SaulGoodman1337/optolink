# P87 gegen nativen Statusblock: rein lesender MQTT-Vergleich

Stand: 2026-10-08, Werkzeug `wb2a-p87-mirror-check.py` 1.0.0.
**Offline getestet, noch kein Geraeteergebnis.**

## Zweck

Die [Quellenanalyse](p300-gfa-source-candidates-2026-10-08.md) liefert die Hypothese
`GFA P87 == Virtual_READ 0x55D3, Byte 7 (nullbasiert)`.
Wir pruefen sie **zuerst im laufenden VS1-Betrieb**, nicht durch erneuten C9-
CANARY, nicht durch einen RAM-Scan und nicht durch einen weiteren Handover.

Der Beobachter benutzt die bestehende Produktions-venv und liest deren lokale
MQTT-Einstellungen per AST, ohne sie zu importieren. Er darf nur die sechs
festen READ-Kommandos fuer 00F8/2, 778C/2, 7650/1, P80/1, P87/1 und 55D3/11
veroeffentlichen. Kein `/set`, `w`, `request`, `reset`, `forcepoll` oder Rawframe.
Geraet 20c2 und Software 0103 werden vor GFA verlangt; P80 muss 20 sein.

**Kein Dienst wird gestoppt, kein serieller Port geoeffnet, kein Protokoll
umgestellt und keine Heizungseinstellung geschrieben.** Normale Produktion und
HA bleiben aktiv. Der Zusatzverkehr kann allerdings Antwort-/Pollzeiten erhoehen.
Es werden keine Betriebsarten oder Sollwerte zum Ausloesen eines Brennerstarts
veraendert. Ein aktiver Service-/Wartungstest ist kein geeigneter Messzeitpunkt.

## Vorbereitung

Als root in derselben Optolink-LXC mit funktionierender VS1-Produktion.
Den im aktuellen PR-Kommentar genannten geprueften Commit holen, lokale
Aenderungen nicht ueberschreiben. Kein Stager, keine Kopie nach `/opt/optolink`
oder `/opt/optolink-p300-candidate`, kein produktives `update`.

```bash
cd /root/p300-trial-work/project
/opt/optolink/venv/bin/python -m unittest discover -s tests -p test_p87_mirror_check.py -v
/opt/optolink/venv/bin/python tools/wb2a-p87-mirror-check.py
```

Erwartung: **33 erfolgreiche Tests**, danach `PLAN ONLY`.
Die Quellenaudit-Suite kann zusaetzlich separat mit
`-p test_p300_gfa_source_audit.py` geprueft werden (11 Tests).
Ohne `--execute` weder MQTT-Verbindung noch Systemd-Abfrage noch Dateiausgabe.

## Einmalige Beobachtung

Am aussagekraeftigsten ist ein **natuerlich** beginnender/geplanter Heizvorgang,
nicht ein zusaetzlich erzwungener Brennerstart. Die normale Regelung bleibt
zustaendig. Waehrenddessen keinen weiteren `optolink-debug`-Client fuer diese
Adressen benutzen und keine Update-/Wartungsaktion starten.

```bash
/opt/optolink/venv/bin/python -u \
  /root/p300-trial-work/project/tools/wb2a-p87-mirror-check.py \
  --execute --seconds 300
```

Standard-Beobachtungsfenster 300 s, zulaessig 30..900 s. Ein offener Read kann
bis acht Sekunden brauchen; Verbindungs-/Abschlusszeiten kommen hinzu.
Hoechstens alle fuenf Sekunden beginnt eine neue Runde mit vier READs. Kein
Nachhol-Burst, keine Wiederholung nach Timeout und keine automatische Reconnect-
Schleife. Die vorhandene Produktions-GFA-Implementierung behaelt ihren eigenen
bereits etablierten FF-Retry, der Beobachter verwirft ein erhaltenes FF.

Pro Runde:

```text
GFA P80 = 20 pruefen
GFA P87 vorher lesen
Virtual_READ 55D3 / 11 Byte lesen
GFA P87 nachher lesen
```

Der native Kandidat ist das achte Byte, Python-Index 7. Keine eigenstaendige
Abfrage auf die rechnerische Adresse 55DA.

Beispielausgabe (nur Schema, keine echte Messung):

```json
{"index": 1, "verdict": "STABLE_MATCH", "p87_before": "60", "native_b7": "60", "p87_after": "60", "bracket_ms": 600.0}
```

## Interpretation, nicht mit einer Produktionsfreigabe verwechseln

| Label | Bedeutung |
| --- | --- |
| STABLE_MATCH | P87 davor/danach gleich, native Byte 7 gleich, Klammer hoechstens 2 s |
| STABLE_MISMATCH | P87 davor/danach gleich, native Byte 7 abweichend, kurze Klammer |
| TRANSITION_AMBIGUOUS | P87 aendert sich waehrend der drei Reads; kein sauberer Gleichheitsvergleich |
| BRACKET_TOO_WIDE | Klammer laenger als 2 s; durch Scheduling/Queue/Dynamik zu unsicher |

Das Gesamtergebnis bleibt `INCONCLUSIVE_STATE_COVERAGE`, solange nicht mindestens
zehn stabile Matches, mindestens drei verschiedene Matching-Zustaende und davon
mindestens zwei Nichtnullzustaende vorliegen. Diese Schwellen sind bewusst
gewaehlte **Forschungskriterien**, keine Herstellerspezifikation oder statistische
Garantie. 100 gleiche Nullwerte bleiben unentschieden. Ein stabiler Mismatch
wird nicht durch Mehrheitsmatches verdeckt: `MISMATCH_OBSERVED_NEEDS_REVIEW`.

Auch `CANDIDATE_SUPPORTED_ON_SAMPLED_STATES` bedeutet nur, dass diese
Stichproben die Hypothese stuetzen. Ein unbeobachteter A->B->A-Wechsel innerhalb
der Klammer bleibt moeglich. Daten werden nacheinander gelesen, nicht atomar.

**Kein Ergebnis bestaetigt allein autonome Aktualisierung unter P300.** Die
GFA-Abfrage selbst koennte einen Cache aktualisieren. Dafuer waere spaeter eine
P300-only-Phase ohne zwischenzeitliche GFA-Reads erforderlich. Ebenso kann
P87 nicht die P06-Geblaesedrehzahl ersetzen.

## Nachrichten-Zuordnung und Stoerungen

Der bestehende Antwortkanal hat keine Request-IDs. Deshalb wartet der Client auf
Subscription-Bestaetigungen, ignoriert Retain-Daten, kontrolliert Befehls-Echo,
Adresse, Status und Bytezahl und verwirft beobachtete Fremdbefehle/Doppelantworten.
Das kann nicht jedes denkbare Rennen eines weiteren Clients beweisen/ausschliessen.
Keinen zweiten Diagnoseclient fuer dieselben Adressen parallel einsetzen.
Normale andere HA-Bedienfunktionen werden nicht technisch deaktiviert.

Bei `CONCURRENT_TRACKED_COMMAND`, `UNEXPECTED_OR_AMBIGUOUS_TRACKED_RESPONSE`,
Timeout oder Identitaetsfehler endet die Beobachtung ohne weiteren Pollversuch.
Ergebnisdateien bleiben erhalten. Keine Guards entfernen, kein endloses Retry.

## Abbruch, Ergebnisdateien und Rueckkehr

**Strg+C** in der Beobachterkonsole beendet nur diesen MQTT-Client. Es muss nichts
zurueckgerollt werden, weil kein Dienst/Protokoll/Parameter geaendert wurde.
Die alten Handover-/CANARY-Abbruchbefehle sind fuer diesen Beobachter irrelevant.

Ausgegebener `SESSION`-Ordner unter `/root/p300-trial-work/p87-results/`:

- `pairs.jsonl`: gueltige vollstaendige Klammermessungen mit Hostzeitstempeln;
- `summary.json`: Identitaetsreads, Ergebnisse, Fehler, Quellcodehash und Grenzen.

Ordner 0700, Dateien 0600. MQTT-Kennwort, Brokeradresse und TLS-Dateipfade werden
nicht in diese Berichte uebernommen. Der native Statusblock selbst ist technische
Geraetetelemetrie; Berichte vor einer Weitergabe pruefen.

Erst nach Ende separat normale Frische kontrollieren:

```bash
optolink-debug request 'gfaread;0x4050;1;raw;False' --timeout 8
optolink-debug request 'gfaread;0x4006;1;raw;False' --timeout 8
```

Diese beiden Requests gehoeren nicht parallel in das Beobachtungsfenster.
P80=20/Erfolgsstatus1 und ein gueltiger zustandsabhaengiger P06-Wert bestaetigen
die bisherige Kommunikation. Auch aktuelle HA-Werte pruefen. Bei Kommunikations-
stoerung zuerst den Beobachter stoppen und diagnostizieren, nicht den Splitter
blind auf P300 umstellen.

## Dokumentierte Tests und Implementierungsquellen

33 Offline-Tests mit synthetischen Nachrichten, simulated MQTT callbacks und
nachgebildetem Gesamtlauf. Kein realer Broker-/USB-/Geraetest durch die Entwicklung.

- [Implementierung](../tools/wb2a-p87-mirror-check.py)
- [Tests](../tests/test_p87_mirror_check.py)
- [Source audit](../tools/audit-p300-gfa-sources.py)
- Gepinnte Produktionsformate: `philippoo66/optolink-splitter` Commit
  `c1ee204a1421447721603c5f21c6da7337fdac97`, `c_settings_adapter.py`,
  `homeassistant_publish.py`; bestehendes Projekt `tools/optolink-debug.py`.
- Eclipse Paho Python 2 Callback-/Loop-API:
  https://eclipse.dev/paho/clients/python/docs/ (abgerufen 2026-10-08).
