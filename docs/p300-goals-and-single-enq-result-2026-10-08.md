# Ziel, Abnahmekriterien und erfolgreicher Ein-ENQ-Vergleich

Stand: 2026-10-08. Branch: `optolink-p300-migration`. Keine Produktionsfreigabe, keine neue Runtime-Aenderung mit dieser Dokumentation.

## 1. Wozu die Entwicklung dient

Das Ziel ist **zusaetzlicher kontrollierter RAM-Zugriff bei Erhalt der bestehenden Optolink-/Home-Assistant-Funktionen**, nicht der Protokollname P300 und nicht ein Fork als Selbstzweck.

Die beiden urspruenglichen Anwendungsziele bleiben getrennt:

- **Pumpensteuerung:** Die interne Pumpe im gewuenschten Heizbetrieb gezielt auf hohe Leistung beziehungsweise 100 Prozent anfordern und anschliessend die normale Regelung wieder uebernehmen lassen. Gesucht ist eine Laufzeitloesung ohne fortlaufendes Umschreiben persistenter Codierungen. Zulaessiger Vor-/Nachlauf, Verhalten bei Fehlern und die tatsaechliche hydraulische Wirkung muessen vor einer Betriebsfreigabe festgelegt und geprueft werden. Eine Sollwertanzeige von 100 Prozent ist keine unabhaengige Volumenstrommessung.
- **Vitotrol-Forschung:** Pruefen, ob eine externe Raum-Isttemperatur einschliesslich des erforderlichen Gueltigkeits-/Teilnehmerzustands von der nativen Regelung akzeptiert werden kann. RAM-Zugriff ist ein Forschungswerkzeug, kein Nachweis einer funktionierenden Vitotrol-Emulation. Der alternative KM-BUS-Hardwareweg bleibt unabhaengig davon bestehen.

P300/RAM ist damit die technische Grundlage fuer moegliche neue Funktionen. Es ersetzt weder eine reale M2-Hydraulik noch beweist es die beiden Anwendungsziele.

## 2. Warum wir gerade Protokollwechsel messen

Der existierende Produktionspfad liest GFA nachweislich unter VS1/6B. Der konkrete direkte C9/P80-Aufruf wurde unter P300 abgewiesen. Die Original-Hostquellen zeigen den VSKO-Wechsel nach VS1. Physische RAM-Zugriffe sind in der vorhandenen Forschung ueber P300 nachgewiesen.

Daraus folgen zwei moegliche Architekturwege, noch keine Produktiventscheidung:

1. P300 bleibt aktiv, wenn eine gleichwertige, ausreichend frische Quelle fuer saemtliche erforderlichen GFA-Werte nachgewiesen wird.
2. Ein gemeinsamer serieller Besitzer verwaltet kurze P300-/VS1-Phasen. Dann muss die gesamte Unterbrechung des jeweils anderen Zugriffs einschliesslich Datenabfragen, Queues und Fehlerbehandlung akzeptabel bleiben.

Die Handover-Tests pruefen ausschliesslich, ob und wie schnell Weg 2 funktioniert. Der Einzelprober stoppt dazu fuer eine begrenzte Messung die Produktion. Das ist **nicht** die angestrebte Dauerbetriebsarchitektur; ein spaeterer Sitzungsmanager wuerde innerhalb eines laufenden Dienstes arbeiten.

Funktionsparitaet heisst nicht nur gleiche Entity-Namen: Messwertaktualitaet, GFA-Kanaele, normale Writes/Readbacks, Zeitprogramme, Party, Uhr, Wartung, Fehlerbehandlung und Wiederherstellung muessen erhalten beziehungsweise gesondert validiert sein.

## 3. Neuer Nutzerbefund: Ein-ENQ-Vergleich bestanden

Quelle: Nutzerupload `Eingefuegter Text(2).txt` (Originaldateiname mit Umlaut), Konsolentranskript mit 137 Zeilen. Das ist **kein importiertes originales measurement.json/recovery.json**. Die vollstaendigen Ergebnisdateien wurden fuer diese Auswertung nicht benoetigt und nicht erneut angefordert.

Getesteter Commit: `ff5504d7418b56dfcf9860ff20b2267582f73a9c`, Prober 1.1.0.
Session: `run-20261008T094009Z-124230` (09:40:09 UTC / 11:40:09 CEST am 8. Oktober 2026).

Transkript-Zuordnung:

- Zeilen 95-102: 42 Offline-Tests erfolgreich, anschliessend inerter Ein-ENQ-Plan.
- Zeilen 103-115: echte Ausfuehrung mit `--execute --single-enq`, Systemd-Ergebnis success, Status 0, Service-Laufzeit 27,579 s, `RESULT=PASS_READ_ONLY_SINGLE_ENQ`.
- Zeilen 116-118: drei vollstaendige Messrunden mit `enq_count=1` und `additional_enq_ms=0.0`.
- Zeilen 126-136: Originaldienst wieder unter `/opt/optolink`, active/running; normale MQTT-GFA-Reads erfolgreich mit P80=20 und P06=00.

Alle drei GFA-Bloecke liefern P80=20 und P06/P09/P87=00. Das sind gueltige Rohantworten, keine unabhaengige Messung des Flammenzustands oder Volumenstroms. Aus den kompakten Konsolenzeilen laesst sich eine FF-Retry-Rate nicht bestimmen.

### Erhaltene Messwerte

Die folgenden drei Objekte sind die Messzeilen der Nutzerkonsole, nicht simulierte Werte:

```json
{"gfa":{"P06":"00","P09":"00","P80":"20","P87":"00"},"gfa_block_ms":434.0780610218644,"index":1,"p300":{"device_id_ms":62.95402999967337,"enq_ms":1996.9262860249728,"software_ms":88.46891392022371,"start_ack_ms":12.879669084213674,"total_ms":2161.2288990290835},"roundtrip_to_vs1_id_ms":4190.53313403856,"roundtrip_with_gfa_ms":4624.6111950604245,"vs1":{"additional_enq_ms":0.0,"enq_count":1,"first_enq_ms":1997.6557079935446,"identity_ms":31.5970319788903,"total_ms":2029.252739972435}}
{"gfa":{"P06":"00","P09":"00","P80":"20","P87":"00"},"gfa_block_ms":372.5663929944858,"index":2,"p300":{"device_id_ms":63.118652906268835,"enq_ms":1998.9537069341168,"software_ms":91.31693607196212,"start_ack_ms":13.91130208503455,"total_ms":2167.3005979973823},"roundtrip_to_vs1_id_ms":4196.364835021086,"roundtrip_with_gfa_ms":4568.931228015572,"vs1":{"additional_enq_ms":0.0,"enq_count":1,"first_enq_ms":1998.1562299653888,"identity_ms":30.84382798988372,"total_ms":2029.0000579552725}}
{"gfa":{"P06":"00","P09":"00","P80":"20","P87":"00"},"gfa_block_ms":436.8530479259789,"index":3,"p300":{"device_id_ms":65.40010694880038,"enq_ms":1996.82713591028,"software_ms":94.69492803327739,"start_ack_ms":12.888645054772496,"total_ms":2169.8108159471303},"roundtrip_to_vs1_id_ms":4199.876369093545,"roundtrip_with_gfa_ms":4636.729417019524,"vs1":{"additional_enq_ms":0.0,"enq_count":1,"first_enq_ms":1997.8605279466137,"identity_ms":32.160261063836515,"total_ms":2030.0207890104502}}
```

### Auswertung

Berechnung: arithmetisches Mittel der drei jeweiligen Messfelder. Min/Max sind nur Stichprobenextrema.

| Messgroesse | Minimum ms | Mittel ms | Maximum ms |
| --- | ---: | ---: | ---: |
| P300 EOT bis ENQ | 1996,827 | 1997,569 | 1998,954 |
| VS1 EOT bis erste ENQ | 1997,656 | 1997,891 | 1998,156 |
| Rueckweg: zusaetzliche ENQ | 0 | 0 | 0 |
| Hin-/Rueckweg bis VS1-ID | 4190,533 | 4195,591 | 4199,876 |
| GFA-Block | 372,566 | 414,499 | 436,853 |
| Gesamter Weg inklusive GFA | 4568,931 | 4610,091 | 4636,729 |

Vergleich mit den drei vorherigen Zwei-ENQ-Runden: 6862,980 ms -> 4610,091 ms im Mittel, 2252,889 ms beziehungsweise 32,827 Prozent weniger. Die Differenz der Mittelwerte enthaelt auch normale Schwankungen der anderen Phasen; sie ist nicht exakt nur die gestrichene zweite ENQ.

**Nachgewiesener Fortschritt:** In diesen drei gemessenen Rueckwegen genuegte eine ENQ, mit nachfolgend gueltiger Identitaet/GFA und wiederhergestelltem VS1-Betrieb. Die bisherige Rechenhypothese von etwa 4,6 s ist damit in diesen Stichproben erreicht.

**Nicht nachgewiesen:** Dauerbetrieb, Verhalten unter allen Heizungszustaenden, maximale Ausfallzeiten, vollstaendige HA-/Write-Paritaet oder eine generelle unvermeidbare Zwei-Sekunden-Grenze. Die beiden ersten ENQ-Phasen bleiben mit diesem EOT-Ablauf jeweils bei etwa zwei Sekunden.

## 4. Warum das noch keine Loesung fuer den Pumpen-Override ist

Der untersuchte E7-RAM-Arbeitswert wird in der bisherigen Pumpenforschung ungefaehr alle 2,1 s nachgeladen. Das Nachladen ist asynchron und kein garantiertes Zeitfenster nach jedem externen Write.

Ein EOT-basierter Wechsel, bei dem allein die beiden ersten ENQ-Wartephasen zusammen etwa vier Sekunden beanspruchen, hat deshalb noch keinen hinreichend kurzen, lueckenarmen RAM-Zugriff fuer diesen Override nachgewiesen. Der komplette hier gemessene VS1->P300->VS1-Ablauf ist ausserdem nicht identisch mit dem exakt zu messenden P300-Ausfallfenster eines kuenftigen Hybridmanagers.

Die Messungen rechtfertigen keine Pumpen-RAM-Schreibfreigabe. Einzelne RAM-Diagnosen koennen dennoch von einem kuerzeren Wechsel profitieren; das ist ein eigener, weniger zeitkritischer Nutzen.

## 5. Naechste Entscheidung statt weiterer Testschleife

Auf die Frage nach dem eigentlichen Ziel folgt mit diesem Dokument **kein neuer Geraetetest und kein weiterer Runtime-Umbau**. Der Ein-ENQ-Vergleich ist abgeschlossen; denselben Versuch unveraendert zu wiederholen bringt aktuell keinen benoetigten Erkenntnisgewinn.

Weitere Entwicklung muss einen konkreten Nutzenpfad nachweisen:

- Quellenbelegter anderer Wechselablauf mit deutlich kleinerer Unterbrechung, bevor zeitkritische RAM-Arbeit diskutiert wird; oder
- validierte, unter P300 autonom frische GFA-Datenquelle, die den Wechsel entbehrlich macht; oder
- bewusste Beschraenkung auf gelegentliche RAM-Diagnose, ohne dies als Pumpensteuerungsloesung zu verkaufen.

Erst danach ist ein groesserer Fork-/Sitzungsmanagerumbau fuer die jeweiligen Anforderungen begruendet. Der Standardbetrieb bleibt VS1. Bestehende GFA-Entities werden nicht gestrichen oder durch alte Antwortpuffer ersetzt.

## Quellen und Abgrenzung

- Aktueller Nutzerupload, oben mit Transkriptzeilen und Session zugeordnet.
- [Vorheriges Basisergebnis und damaliger Ein-ENQ-Testplan](p300-handover-baseline-result-and-single-enq.md).
- [Basismesswerte](evidence/p300-handover-baseline-2026-10-08.json).
- [Direkte GFA-Hostquellenpruefung](p300-gfa-host-trace-2026-10-08.md).
- [Anwendungs-/Fork-Optionen](p300-fork-switching-gfa-options-2026-10-08.md).
- [Historischer Pumpen-RAM-Befund](https://github.com/SaulGoodman1337/optolink/blob/79f222c7f3a11b848a6a8ac8ece50e24deede823/docs/pump-min-override.md).

Nur Dokumentation und Auswertung vorhandener Nutzerdaten. Keine erneute externe Protokollrecherche, keine neuen Offline-/Hardwaretests, kein Merge in den HA-Produktionsbranch in diesem Arbeitsschritt.
