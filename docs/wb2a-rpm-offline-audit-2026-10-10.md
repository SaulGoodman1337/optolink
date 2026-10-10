# WB2A P300-RPM: neuer unabhängiger Offline-Audit (10.10.2026)

**Nur Forschung. Keine Controllerabfrage, kein Protokollwechsel, keine Writes und keine Freigabe eines P300-Istdrehzahl-Datenpunktes.** Getrennt vom Produktionsbranch `feat/wb2a-next-phase-20261010`.

## Methode

Das neue Skript `tools/wb2a-rpm-offline-audit.py` liest die bereits gespeicherten JSONL-Dateien und prüft optional die **SHA256-Prüfsummen jedes einzelnen 64-Byte-`core-pairs.bin`-Blocks**. Zusätzlich werden fortlaufende Cycle-IDs, monotone Zeitstempel, Bytebereiche und native FC01-Statusklammern geprüft. Nur fest bekannte Kandidaten `0x0F20` und `0x1C76` werden ausgewertet.

Ein Hochwert-Paar gilt im Archiv **lediglich als möglicher Trigger** bei beiden Kandidaten ≥136, maximal vier Rohbyteeinheiten Abweichung, Flamme in beiden FC01-Klammern EIN, kein Lockout, keine instabile Statusklammer. Dies ersetzt keine wirkliche VS1-P06-Referenz.

Die reine Funktion `classify_plateau()` bewertet künstlich beziehungsweise unabhängig chronologisch geklammerte `P300 → echte VS1-P06-Werte → P300`-Plateaus. Selbst sechs konstante gültige P06-Werte und perfekter numerischer Treffer liefern maximal `NUMERICALLY_CONSISTENT_NOT_VERIFIED`. Verwerfungsfälle umfassen `FF`, instabile Kandidaten, Wechsel der Flamme, fehlende Werte, falsche Kopie und deutlichen numerischen Widerspruch. **Keine automatische Dekodierung von RPM aus FC01, 0F20, 1C76 oder P09.**

## Gegen real archivierte Messungen geprüft

| Prüfpunkt | Temporal Full-Run | Trigger Full-Run |
| --- | ---: | ---: |
| Datum der Aufzeichnung | 09.10.2026 | 09.10.2026 |
| Vollständige Zyklen / geprüftes Core-SHA256 | 5224 / 5224 | 2185 / 2185 |
| Unterschiedliche `0F20`-Werte | 29 | 2 |
| `0F20`-Änderungen | 60 | 2 |
| `0F20=1C76` | 5209 | 2183 |
| Native Statusklammer kohärent | 5200 | 2183 |
| Einzelne geeignete Hochwertzyklen | 21 | 0 |
| Zusammenhängende Hochwertserien (mindestens zwei) | 4 | 0 |
| Gültige P06-Referenz-Reads | 44 | 23 |
| **Positive** P06-Referenzwerte im selben Run | **0** | **0** |
| Kürzester Abstand Hochwert zu echtem P06 | **2714,472 Sekunden** | n/a |

Temporal-Archiv: `/root/p300-trial-work/p300-temporal-results/run-20261009T131357Z-220351`.

Trigger-Archiv: `/root/p300-trial-work/p300-rpm-trigger-results/run-20261009T174812Z-293099`.

**Interpretation:** Die vier Hochwertserien im Temporal-Archiv können rückblickend als interessante Kandidatenfenster eingegrenzt werden; es gibt in deren zeitlicher Nähe aber **keinen** stabilen positiven P06-Istwert. Der Triggerlauf hatte überhaupt keinen Hochwert. Beide Versuche bleiben `INCONCLUSIVE_NO_TIMED_POSITIVE_P06_BRACKET`. Die im älteren Fokuslauf dokumentierten hohen P06-Vorwerte bei anschließend `0F20=84` bleiben eine separate, **zeitversetzte** Gegenbeobachtung ohne synchronen Nachweis.

## Test und Wiederholbarkeit

```bash
python3 -m unittest discover -s tests -p 'test_wb2a_rpm_offline_audit.py' -v

p=/root/p300-trial-work/p300-temporal-results/run-20261009T131357Z-220351
sudo python3 tools/wb2a-rpm-offline-audit.py \
  --cycles "$p/cycles.jsonl" --vs1 "$p/vs1.jsonl" --core "$p/core-pairs.bin"
```

Am 10.10.2026: **14/14** synthetische Regressionstests bestanden und beide obigen realen Archive vollständig offline ausgewertet. Die Skriptausgabe beinhaltet ausdrücklich `p300_actual_p06_verified=false` und `p300_rpm_value=null`.

## Entscheidung / nächste Research-Arbeit

Keine weiteren ungezielten RAM-Sweeps. Als nächste mögliche wissenschaftliche Klärung dient nur eine **kurze, kontrollierte** natürliche Hochwert-Gegenmessung mit echten P06-Werten in der zeitlichen Klammer, nach separater Betriebs-/Recovery-Prüfung. Bis dahin ist die technisch sauberere Produktentwicklung ein VS1-basierter **Single-Owner-Hybrid mit bedarfsgesteuerten P300-Lesebatches**, dessen Offline-Scheduler separat im Feature-Branch entwickelt wird. Controller-RAM-Writes und Serviceänderungen sind nicht freigegeben.
