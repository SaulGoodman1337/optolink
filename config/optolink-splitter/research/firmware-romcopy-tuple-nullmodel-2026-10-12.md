# WB2A/20C2: statistischer Negativkontrolltest für zwei vermeintliche ROM→RAM-Kopierdeskriptoren

**12. Oktober 2026.** Projekt-Priorität 1 bleibt die echte Programm-ROM-Extraktion über **bestehendes Optolink**, ggf. ohne jemals eine volle 20-Bit-Adresse auf der Schnittstelle zu übertragen. Aus dem ursprünglichen RAM wurden im September zwei stabile Tupel erkannt, die formal wie eine Kombination aus weit adressierter M16C-Quelle, lokalem RAM-Ziel und kleiner Länge aussehen. Diese Struktur wurde jetzt erstmalig gegen **300 unabhängige, aber histogramm- und zeitstabilitätserhaltende** Kontrollpermutationen verglichen.

## 1. Originale Bildquelle

- SHA256 des unveränderten tar.gz-Gesamtoriginals: `94d5842b6dc5759ecb446a4c617b60b72873b639885d116032f783abdef8431c`.
- **79/79** komplette, nicht atomare, exakt **20.480 Byte** große FC03-P300-RAM-Aufnahmen vom 9.10.2026, CPU-Adressen `0x0400..0x53FF`, Identität `20C2/0103`.
- Privates Original: `/root/p300-trial-work/research-bundles/p300-fullram-run-20261009T083607Z-144293-bundle.tar.gz` (**8.404.258 Bytes**).
- Vor jeder statistischen Operation wurden SHA256 des gesamten Archivs, Manifest-SHA jedes der 79 Binärbilder und ihrer Metadaten sowie `COMPLETE`, identische Zielkennung, exakt 640 erfolgreiche 32-Byte-Blöcke und `atomic_ram_image=false` geprüft.
- Von 20.480 RAM-Byteadressen waren **18.955 über alle 79 Bilder identisch**. Andere dynamische Positionen wurden von der Kandidatensuche ausgeschlossen.

**Wichtig:** Das Archiv enthält **SRAM-Bytes**, nicht bereits per se Programm-ROM. Die 79 Aufnahmen stammen aus unterschiedlichen Zeitpunkten und sind selbst über 640 seriell ausgeführte 32-Byte-Reads nicht atomar. Das Nullmodell kann keine Quell-CPU- oder Code-Provenienz schaffen.

## 2. Genau definierte Kandidatenhypothese

Ausschließlich acht direkt aufeinanderfolgende, über 79/79 Aufnahmen **unveränderte** RAM-Bytes wurden nach diesen vorab aus der historischen Beobachtung übernommenen Formen geprüft:

```text
Form A  source(u24 little-endian) | target(u24 little-endian) | length(u16 little-endian)
Form B  target(u24 little-endian) | source(u24 little-endian) | length(u16 little-endian)
```

Als rein heuristisches Fenster für den `source` gilt `0xC0000..0xFFFFF`, als vollständig in den Archiv-RAM fallendes `target` der Bereich `0x0400..0x53FF`; `length=1..32`, `target+length<=0x5400`.

Die Suche fand **exakt** die zwei vorher bereits bekannten Formen:

| Tupel RAM-Adresse | Vermutete Quelle | Vermutetes Ziel | Länge | Orientierung |
|---|---|---|---:|---|
| `0x1DE5` | `0xEA2AB` | `0x3301` | 29 | Quelle zuerst |
| `0x1E6A` | `0xFB27D` | `0x0705` | 7 | Ziel zuerst |

Wie vorher: `0x3301/29` ist ein eindeutiges, über diese 79 Bilder konstantes 29-Byte-Fenster, `0x0705/7` dagegen sieben gleiche `64`-Bytes. Die beiden „Source“-Zahlen liegen nur numerisch in einem angenommenen Programmfenster. **Es ist unbewiesen, dass die CPU sie jemals als Quellzeiger einer ROM-Kopieroperation dereferenziert.** Die beiden Tupel könnten im Kontext des RAM-Scheduler- und Stackbereichs andere Datenstrukturen darstellen.

## 3. Das neue Nullmodell gegen Scheinzeiger

Einzelne randomisierte Ram-Dumps als Vergleich wären problematisch, da sie die Original-Byteverteilung und dynamischen Bytepositionen zerstören. Stattdessen:

1. Für jeden Seed `20261012..20261311` (genau **300** fest vorgegebene Seeds) wird eine Permutation aller 20.480 Adresspositionen erzeugt.
2. **Dieselbe Positionen-Permutation wird auf alle 79 RAM-Samples angewendet.** Es genügen die permutierten Bytes von Sample 1 und die exakt gleichzeitig permutierte Stabilitätsmaske; damit bleiben die Stabilitätsmitgliedschaften über die gesamte Zeitreihe erhalten.
3. Jede Kontrollanordnung besitzt **genau die Bytehäufigkeiten des Originalabbilds** und dieselbe Anzahl von stabilen/dynamischen Positionen, aber keine Originalfeld-Nachbarschaften.
4. Anschließend wird dieselbe 8-Byte-Suche ohne nachträgliche Fallunterscheidung ausgeführt.

| Anzahl Treffer in einem Kontrollbild | Anzahl von 300 Kontrollen |
|---|---:|
| **0** | **249** |
| **1** | **48** |
| **2** | **3** |
| **Mehr als 2** | **0** |

- Originalanzahl Treffer: **2**.
- Mittlere Anzahl pro Kontrollbild: **0,18**.
- Nur **3 von 300** Kontrollbildern enthalten mindestens zwei Kandidaten.
- Deskriptiver, +1-korrigierter Kontrollanteil: `(3+1)/(300+1) = 0,013289`.

**Wichtiger statistischer Vorbehalt:** Die Quell-/Ziel-/Längenform, die Programmfenstergrenzen und die beiden auffälligen RAM-Adressen wurden **nach ersten Originalbeobachtungen** gewählt. Das ist deshalb **kein gültiger confirmatorischer p-Wert** und keine quantitative Wahrscheinlichkeit, dass die Tupel echte ROM→RAM-Transferdeskriptoren sind. Es zeigt lediglich: Die beobachtete stabile *8-Byte-Struktur* ist bei genau diesem Nullmodell seltener als komplett umsortierte SRAM-Bilder. Ein solcher Befund ist mit echten Task-/Pointer-Strukturen ebenso vereinbar.

## 4. Entscheidung über weitere Forschung

Die Daten liefern einen begrenzten **positiven Strukturhinweis**, aber weiterhin **null echte Programm-ROM-Bytes**. Eine daraus abgeleitete Aktion wie das Setzen eines DMA-Quellregisters oder das Patchen des Scheduler-/TX-Deskriptors wäre sachlich **nicht** gerechtfertigt und birgt angesichts der heutigen realen C5-/F9-Fehler ein erhebliches Risiko.

**Sinnvolle nächste diskriminierende Messung, bevor irgendein ROM-Leser behauptet wird:**

- Die `0x1DE5`- und `0x1E6A`-Tupel mit **einigen wenigen bereits vorhandenen archivierten natürlichen Controller-Ereignissen** und angrenzenden Task-/Scheduler-Datensätzen korrelieren. Am aussagekräftigsten wäre ein **ohne Schreibbefehl** natürlicherweise ausgelöster Zielinhaltwechsel bei weiterhin stabilem Quellpointer, der sich an eine andere Controllerquelle oder Programmroutine binden lässt.
- Nicht denselben unveränderten Datensatz weitere 100-mal abfragen: Eine stabile Adresse und ein stabiles Ziel allein beweisen keinen Datenfluss.
- Andere Quelle eines **ROM-abhängigen Ausgabekanals** suchen: variabler Daten-/ROM-Prüfsummenalgorithmus mit Präfix, read-only ROM-Tabellenausgabe, zulässige Multi-Byte-Diagnoseobjekte oder originale mehrstufige Gerätewartungsroutinen. Diese brauchen eventuell gar keinen 20-Bit-Adressparameter im Optolink-Request.
- Erst nach eindeutiger Datenflussprovenienz einen **kurzen, rein lesenden** Test vorschlagen, unter vollständiger System-/GFA-Störungshistorie inklusive T+5/T+15/T+75 und unabhängiger Host-Rückstellung. Keine RAM-, SFR-, DMA- oder Bootmode-Schreibversuche.

## 5. Reproduktion & Git

Reproduzierbarer Auditor in **bestehendem** `optolink-research`:

- `tools/wb2a-romcopy-nullmodel-original.py`: Standardbibliothek, SHA/Manifest-TAR-Abnahme, 79-Bilder-Stabilitätsmaske, reale Tupel, deterministisches 300er Nullmodell. Kein Optolink-Zugriff.
- `tests/test_wb2a_romcopy_nullmodel_original.py`: synthetische Positive, instabile-Tupel-Gegenprobe, high-source-/length-Negative, Archivmanipulation und echte Originalarchiv-Reproduktion unter root. Nicht privilegierte CI überspringt exakt die zwei Originaltests.

```bash
cd /home/chatgpt-admin/optolink-wb2a-research-20261010

sudo -n python3 tools/wb2a-romcopy-nullmodel-original.py \
  --original-archive /root/p300-trial-work/research-bundles/p300-fullram-run-20261009T083607Z-144293-bundle.tar.gz \
  --out /tmp/wb2a-romcopy-nullmodel-20261012.json

python3 -m unittest discover -s tests \
  -p 'test_wb2a_romcopy_nullmodel_original.py' -v

sudo -n python3 -m unittest discover -s tests \
  -p 'test_wb2a_romcopy_nullmodel_original.py' -v

python3 -m unittest discover -s tests -q
```

Die private historische Vollarchivquelle und die 79 RAM-Images bleiben auf dem LXC. `main` und der produktive Optolink-Splitter sind unverändert, **0 neue Controllerreads und -writes** durch diese Runde. Forschungsstand nur `optolink-research`, kein Merge.
