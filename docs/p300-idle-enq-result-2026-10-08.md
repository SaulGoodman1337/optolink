# Idle-ENQ: Kommunikation bestanden, keine Beschleunigung

Stand: 2026-10-08. Branch: `optolink-p300-migration`.
**Entscheidung: `CLOSED_NO_SPEEDUP_FOR_IDLE_ENQ_VARIANT`. Keine Produktionsfreigabe.**

## 1. Ergebnis

Der Nutzer hat den vorbereiteten Vergleich mit Prober 1.2.0 erfolgreich ausgeführt. P300 lässt sich in diesem Ablauf auch nach einer natürlichen VS1-ENQ ohne vorausgehendes EOT starten. Der gesamte gemessene Ablauf wird dadurch jedoch **langsamer**, nicht schneller:

- Bisheriger EOT-/Ein-ENQ-Ablauf: **4,610 s** im Mittel.
- Natürliche ENQ ohne EOT: **5,628 s** im Mittel.
- Differenz: **+1,018 s bzw. +22,1 Prozent**.

Die Arbeitshypothese eines schnelleren Ausstiegs durch passives Warten hat sich in diesen Messungen nicht bestätigt. Dieser konkrete Optimierungszweig wird wie vor dem Test festgelegt abgeschlossen. Kein weiterer unveränderter `--idle-enq`-Lauf ist nötig.

## 2. Provenienz und Wiederherstellung

Quelle: Nutzerupload `Eingefügter Text(3).txt`, 155 Zeilen, SHA256 `d474b2581cd27a8a0494ffaa914d34cd39ad3a954695bbd275d795d2b22e25e1`.
Getesteter Commit: `099e3c1528de4f1d9f8aa101384586fbea473bbb`.
Session: `run-20261008T100802Z-124372` (10:08:02 UTC / 12:08:02 CEST am 8. Oktober 2026).

- Zeilen 112–120: 60 Offline-Tests erfolgreich und inerter Plan.
- Zeilen 121–133: tatsächlicher Lauf mit `--execute --idle-enq`, Systemd success, Exitstatus 0, Service-Laufzeit 30,459 s, `RESULT=PASS_READ_ONLY_IDLE_ENQ`.
- Zeilen 134–136: drei vollständige Messrunden, jeweils `entry_mode=natural-enq-no-eot`, `eot_sent=false`, Rückweg `enq_count=1`.
- Zeilen 144–154: originaler Splitter unter `/opt/optolink`, active/running; anschließend echte MQTT-Antworten P80=`20` und P06=`00`, jeweils mit Erfolgsstatus 1.

Die [maschinenlesbare Evidenz](evidence/p300-idle-enq-result-2026-10-08.json) erhält die Messzeilen unverändert als JSON-Objekte und kennzeichnet die abgeleiteten Mittelwerte getrennt. Sie ist eine Abschrift des Konsolentranskripts, **kein Import der vollständigen originalen measurement.json/recovery.json**. Diese Dateien müssen für die hier bereits belegte Schlussfolgerung nicht erneut angefordert werden. MQTT-Adresse und Zugangsdaten werden nicht übernommen.

Die in den Offline-Tests ausgegebenen simulierten Wiederherstellungsfehler gehören zu Negativtests; sie sind kein Fehler des anschließenden Hardwarelaufs. Die 30,459 s sind die von Systemd berichtete Service-Laufzeit, keine separat gemessene gesamte HA-Ausfallzeit.

## 3. Vergleich mit dem erfolgreichen Ein-ENQ-Lauf

Referenz: Nutzerupload `Eingefügter Text(2).txt`, SHA256 `c6cd3d485f5c58e8c0d00a0dc4afef11c79f425e7cc0ad7d397b5657ed8fab42`, Messzeilen 116–118; Session `run-20261008T094009Z-124230`, Prober 1.1.0, Commit `ff5504d7418b56dfcf9860ff20b2267582f73a9c`. Die Datensätze sind im [Ein-ENQ-Ergebnisbericht](p300-goals-and-single-enq-result-2026-10-08.md) erhalten.

Alle Tabellenwerte sind **arithmetische Mittel aus jeweils drei realen Konsolen-Datensätzen**, Angaben in Millisekunden. Keine gepaarte Zufallsstudie, keine Worst-Case- oder Dauerlaufgarantie.

| Phase | EOT + Ein-ENQ | Natürliche ENQ | Differenz |
| --- | ---: | ---: | ---: |
| VS1→P300: Warten auf ENQ | 1997,569 | 2971,356 | +973,787 |
| P300: Start bis ACK | 13,227 | 13,445 | +0,218 |
| P300-Einstieg einschließlich beider Reads | 2166,113 | 3135,856 | +969,743 |
| P300→VS1: Warten auf erste ENQ | 1997,891 | 1997,431 | −0,460 |
| VS1-Einstieg einschließlich Identität | 2029,425 | 2029,744 | +0,319 |
| GFA-Block P80/P06/P09/P87 | 414,499 | 462,584 | +48,085 |
| Gesamter Hin-/Rückweg bis VS1-ID | 4195,591 | 5165,651 | +970,060 |
| Gesamter Hin-/Rückweg inklusive GFA | **4610,091** | **5628,235** | **+1018,145** |

Der Idle-Gesamtwert reicht von 5611,368 bis 5637,236 ms. Alle drei Idle-Runden waren damit langsamer als jede der drei vorherigen EOT-/Ein-ENQ-Runden (4568,931 bis 4636,729 ms).

Die natürliche ENQ kam 2971,168–2971,620 ms nach Beginn des passiven Einstiegs. Gemessen ab dem letzten empfangenen VS1-Identitätsbyte waren es 2981,794–2982,241 ms, im Mittel **2982,056 ms**. Die Differenz von etwa 10,7 ms gehört zur vorgeschalteten Restdatenprüfung; die Wartezeit wurde nicht als vermeintliche Beschleunigung vor den Messbeginn verschoben.

Der überwiegende zusätzliche Zeitbedarf liegt beim Warten auf die natürliche ENQ. Der P300-Start selbst bleibt bei etwa 13 ms; der unveränderte EOT-basierte Rückweg bleibt bei etwa 1997 ms bis ENQ. Die kleinere Änderung der GFA-Blockdauer wird nicht ohne Rohspur einer bestimmten Ursache zugeschrieben.

## 4. Aussagegrenzen

**Direkt belegt:** Die vollständige Idle-ENQ-Nachrichtenfolge funktioniert in drei Messrunden, ist in diesen Runden langsamer, und VS1/GFA ist nach Abschluss wieder erreichbar.

**Technische Interpretation, nicht Firmwarebeweis:** Das Verhalten passt zu unterschiedlichen Zeitabläufen nach explizitem EOT und nach normalem Auslaufen einer VS1-Sitzung. Ein universell fester 2-s- oder 3-s-Firmwaretimer folgt daraus nicht. Host-, USB-, Kernel- und Schedulinganteile bleiben enthalten.

**Nicht belegt:** Ein nativer P300-GFA-Ersatz, ein autonom aktualisierter RAM-Spiegel, Schreibparität, Dauerbetriebsstabilität oder lückenarme Pumpensteuerung. Alle drei GFA-Blöcke lieferten P80=20 und P06/P09/P87=00. Das sind gültige Rohantworten, keine unabhängige Messung des Flammen-/Gebläsezustands. Eine FF-Retry-Rate lässt sich aus den kompakten Ergebniszeilen nicht bestimmen.

`PASS_READ_ONLY_IDLE_ENQ` bedeutet gültiger Ablauf und Wiederherstellung; es war nie als Geschwindigkeits-PASS definiert. Das positive Funktionsresultat und das negative Optimierungsresultat sind deshalb kein Widerspruch.

## 5. Konsequenz für Entwicklung und nächsten Test

1. **Idle-ENQ als Beschleunigungsvariante abschließen.** Kein gleichartiger weiterer Live-Test, kein Verkürzen von Timeouts, um lediglich früher zu scheitern. Der bisher schnellste validierte Vergleich bleibt EOT mit Ein-ENQ-Rückweg; auch er ist noch kein produktiver Hybridmanager.
2. **Keine dauerhafte Umschaltlösung für den Pumpen-Override freigeben.** Der aktuelle Ablauf hat keine genügend kurze Unterbrechung des RAM-Zugriffs nachgewiesen. Die in der Pumpenforschung beobachtete ungefähr 2,1-s-Nachladung ist asynchron; die gesamte Messrunde ist zudem nicht identisch mit dem zukünftigen Intervall zwischen zwei RAM-Zugriffen.
3. **Als nächsten Entwicklungsweg eine dauerhaft unter P300 lesbare GFA-Datenquelle priorisieren.** Zuerst statisch nach einer profilig passenden virtuellen Abbildung oder einem autonomen internen Spiegel suchen; keine neue Adresse allein aus ähnlichen Zahlenwerten ableiten. Die bisherige C9-Ablehnung und VSKO→VS1-Abbildung bleiben gültig.
4. Ein Kandidat muss die vorhandene Information liefern: insbesondere P06-Drehzahl nicht durch einen Modulationssollwert oder PWM ersetzen. Breite, Skalierung, Fehlerwerte, Geräte-/Brennervariante und Aktualisierung müssen belegt werden. Ein aus einer alten VS1-Antwort wiedergefundenes Byte ist kein eigenständig aktualisierter Sensor. Gerade die hier durchgehend gemessenen 00-/20-Werte erlauben noch keine Identifikation eines solchen Spiegels.
5. Ein neuer Hardwareversuch folgt erst aus einer konkreten Lesehypothese mit nachvollziehbarer Provenienz, festen Grenzen und Wiederherstellung. **Dieser Änderungssatz enthält keine neue Testvariante, keine RAM-/Parameterwrites und keine Produktivumstellung.** Die Suche ist weiter offen; ihr Erfolg wird nicht behauptet.

Eine gesonderte, quellenbegründete Untersuchung der Rückrichtung bleibt möglich. Sie ist nicht durch diesen VS1→P300-Vergleich widerlegt. Für die nächste Arbeitspriorität wird jedoch der direkte Datenweg bevorzugt, statt weitere Sekundenvarianten aneinanderzureihen.

## 6. Dokumentationsänderung und Quellen

Geändert werden nur dieser Bericht, seine JSON-Evidenz, der Dokumentationsindex und der historische Testverweis. Der Prober 1.2.0, seine Tests, die produktive Laufzeit, das HA-Profil, Installer und Updatekanal bleiben unverändert. Kein Zugriff auf die reale Anlage durch die Auswertung.

- [Exakt getestetes Idle-ENQ-Runbook](https://github.com/SaulGoodman1337/optolink/blob/099e3c1528de4f1d9f8aa101384586fbea473bbb/docs/p300-idle-enq-comparison.md), einschließlich vorher festgelegtem Abbruch dieses Optimierungszweigs bei fehlender Beschleunigung.
- [Getesteter Prober](https://github.com/SaulGoodman1337/optolink/blob/099e3c1528de4f1d9f8aa101384586fbea473bbb/tools/wb2a-handover-probe.py).
- [Ziele und Ein-ENQ-Ergebnis](p300-goals-and-single-enq-result-2026-10-08.md).
- [Direkte GFA-/VSKO-Quellenprüfung](p300-gfa-host-trace-2026-10-08.md).
- [Fork, Protokollwechsel und offene GFA-Alternativen](p300-fork-switching-gfa-options-2026-10-08.md).

Die Zahlen dieses Berichts stammen aus den übergebenen Nutzerdateien; Hypothesen und Arbeitsprioritäten sind ausdrücklich davon getrennt. Keine neuen externen Quellen oder neuen Firmwarefakten werden daraus abgeleitet.
