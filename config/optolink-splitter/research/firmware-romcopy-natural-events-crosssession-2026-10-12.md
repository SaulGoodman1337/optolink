# WB2A/20C2: Natürliche Brennerereignisse und unabhängige Oktober-Mitschnitte als ROM→RAM-Kopierprüfung

**Abgeschlossen am 12.10.2026.** Alle neuen Operationen waren **rein offline** auf bereits archivierten, kryptographisch verifizierten Host-/Controller-Messungen. Ziel bleibt unverändert: den echten Programm-ROM-Inhalt des laufenden WB2A-Hauptreglers über Optolink gewinnen, auch falls kein direkter 20-Bit-ROM-Lesebefehl existiert.

**Wichtigster Befund:** Die vermeintlichen Far-ROM→Low-SRAM-Deskriptoren bei `0x1DE5` und `0x1E6A` sind zwar real und langfristig stabil, aber die vorhandenen Daten **sprechen nicht für einen während des Brennerbetriebs aktiven Kopierdienst**. Die frühere Einstufung von Kandidat A als stärkere „ROM-Kopie wegen Ziel-Einzigartigkeit“ ist statistisch **nicht gerechtfertigt**. Kandidat B zeigt ausschließlich wiederholte Füllbytes am angeblichen Ziel.

## 1. 79 Original-RAM-Abbilder enthalten bereits echte natürliche Last-/Flammenwechsel

Attestierte Quelle (wie vorher): `/root/p300-trial-work/research-bundles/p300-fullram-run-20261009T083607Z-144293-bundle.tar.gz`, **SHA256 `94d5842b6dc5759ecb446a4c617b60b72873b639885d116032f783abdef8431c`**, original **8.404.258 Bytes**. Manifest und alle 79 originalen 20.480-Byte-SRAM-Images einschließlich zugehöriger JSON-Metadaten wurden vor Auswertung erneut einzeln SHA256-geprüft.

CPU: `20C2/0103`. Optolink-Transport: ursprünglich `P300 FC03 Physical_READ` aus Low-SRAM `0x0400..0x53FF`. Jede Archiv-Aufnahme besteht aus **640 nacheinander übertragenen 32-Byte-P300-Reads, nicht aus einer atomaren RAM-Snapshot-Operation**; ihre Zustandsmetadaten werden deshalb nur als zeitliches Kontrollfenster und nicht als punktgenau gesicherter Zustand jedes Bytes interpretiert.

Archivzeit: **09.10.2026 08:36:14–11:24:03 UTC**. Bei jedem der 79 Originalbilder ist `snapshot_id`, Vollständigkeit, `software=0103`, `device_id=20c2`, `atomic_ram_image=false`, SHA und Laufzeitklassifikation überprüft.

| Vom historischen Logger bereits klassifizierter Zustand | Aufnahmen |
|---|---:|
| `STABLE_BRACKET_OFF` | **48** |
| `STABLE_BRACKET_RUNNING` | **11** |
| `TRANSITION_OR_UNKNOWN` | **20** |
| `flame_seen=true` | **26** |
| `flame_transition_seen=true` | **8** |
| Scanrichtung vorwärts / rückwärts | **40 / 39** |

Somit muss ein eventuell bei **natürlichem Brennerstart** aktivierter Kopierdienst nicht mit neuen Hardware-Stimuli provoziert werden: sein Einfluss auf die beiden vorgeschlagenen RAM-Tupel und Ziele hätte in diesen historischen wechselnden Lastphasen sichtbar sein können.

### Eigentliche Datenkorrelation

| Beobachtung über alle 79 verifizierten Bilder | Kandidat A | Kandidat B |
|---|---:|---:|
| Mutmaßliches 8-Byte-Tupel | `0x1DE5 = AB A2 0E 01 33 00 1D 00` | `0x1E6A = 05 07 00 7D B2 0F 07 00` |
| Hypothetische Quelle (3-Byte-Little-Endian-Interpretation) | `0xEA2AB` | `0xFB27D` |
| Hypothetisches Ziel | `0x3301 /29` | `0x0705 /7` |
| Unterschiedliche Tupel | **1** | **1** |
| Unterschiedliche komplette Zielblockinhalte | **1** | **1** |
| Unterschiedliche 24-Byte-Nachbarschaften `[Start-8..Start+15]` | **1** | **75** |
| Aufeinanderfolgende Nachbarschaftswechsel | **0/78** | **78/78** |
| Verschiedene Tupel / Zielinhalte in 48 stabilen Aus-Aufnahmen | **1 / 1** | **1 / 1** |
| Verschiedene Tupel / Zielinhalte in 11 stabilen Betrieb-Aufnahmen | **1 / 1** | **1 / 1** |
| Quell-ROM-Adresse nachweislich vom Controller dereferenziert | **Nein** | **Nein** |

Zusatz: Der alte 26.09.-Forschungsbericht enthält bereits einen **historisch mit 77 Probes echten, durch erhöhten Heizsollwert provozierten Brennerstart** samt Vorlauf, Flammenbildung und Modulation; auch dabei änderten sich die beiden Tupel und Ziele nicht. Der Original-Rohstream dieser älteren Session wurde in dieser Runde **nicht separat rekonstituiert**. Wir behandeln seine Aussage als bestehenden Dokumentationsbefund, **nicht** als neue unabhängige instrumentierte Kontrolle.

## 2. B-Pointer `0x1E6A`: Das angebliche Ziel ist nur ein Füllmuster

In dem Originalbild enthält `0x0705..0x070B` genau **`64 64 64 64 64 64 64`**. Es liegt vollständig in einem **407 Byte** langen, ununterbrochenen `0x64`-Bereich bei **`0x06DF..0x0875`**.

Dasselbe Sieben-Byte-Muster erscheint **1.296 Mal** im 20.480-Byte-Originalbild, wenn man überlappende Positionen korrekt mitzählt. Die angebliche siebenbyteige Zielkopie ist somit **keine eindeutige ROM-Quelle-Signatur**.

Der starke Kontrast ist trotzdem real: Während das Acht-Byte-Tupel in 79/79 Bildern unverändert bleibt, ändert sich seine unmittelbare 24-Byte-Nachbarschaft zwischen **78 von 78** aufeinanderfolgenden Bildpaaren. Das ist mit einer ständig genutzten Task-/Stackumgebung und einer eingebetteten konstanten Struktur vereinbar, **aber kein Beweis für eine ausgeführte Copy-Funktion**. B als unmittelbaren ROM-Dump-Hebel deutlich niedriger priorisieren.

## 3. A-Pointer `0x1DE5`: Ziel-Einzigartigkeit ist kein Herkunftsnachweis

Die früher besonders hervorgehobenen 29 Zielbytes bei `0x3301..0x331D` sind im echten RAM nur einmal vorhanden und in 79/79 Bildern konstant. Dies erschien zunächst als Argument für eine ROM-Kopie. Die vollständige Kontrollverteilung zeigt jedoch:

| 29-Byte-Kontext im exakt selben Originalabbild | Befund |
|---|---:|
| Über alle RAM-Adressen mögliche Fenster | **20.452** |
| Über alle 79 Images vollständig stabile Fenster | **16.697** = **81,64 %** |
| Davon mit einzigartiger vollständiger 29-Byte-Folge | **14.427** = **86,40 %** |
| Gleich langer Block an derselben Position in 300 vollständigen, bytehistogrammgleichen Shuffle-Kontrollen einzigartig | **300/300** |

Die tatsächliche 29-Byte-Folge bleibt privat und wird weder in Git noch in den JSON-Ausgabedaten veröffentlicht. **Einzigartigkeit eines langen, hochdiversen RAM-Fensters ist schon für normale Daten erwartbar** und darf nicht als Kopierursprung `0xEA2AB` etikettiert werden.

Beide angeblichen Quellzahlen kommen im ursprünglichen SRAM als exakte **3-Byte-Little-Endian-Folge je einmal** vor, als **mit Null auf vier Byte verlängerte Far-Adresse überhaupt nicht**. Das ist ein Format-/Layout-Hinweis, kein Ausschluss einer echten 24-Bit-Adresse (M16C kennt mehrere Pointerrepräsentationen).

## 4. Unabhängiger Abgleich mit drei realen 11.10.-P300-Sessions

Diese ältere Live-Daten wurden am 12.10. **nur von der Festplatte gelesen**. Jeder Quell-JSON wurde vor Parsing exakt mit SHA256 gebunden und gegen den originalen `20C2/0103`-Identitätsblock, `controller_writes=0`, lesende und vollständig validierte P300-Request-Telegramme und die zugehörigen vier Vorher-/Nachher-Guards geprüft. Dateien bleiben auf `/tmp`, **kein** Controllerzugriff für diese Auswertung.

| Oktober-11-Originalquelle | Original SHA256 |
|---|---|
| `wb2a-vitotrol-rom-contrast-p300-20261011.json` (2 echte `Physical_READ`-Zyklen) | `f5a31879fedf8c0af780f020c29e50c47cb7727c15e6305c955e6ae8f05935d1` |
| `wb2a-vitotrol-dual-readonly-live-20261011.json` | `e12a10b500cedbc41cc76e8b54ccba78eecc708c9c71f2e14075a25098bf393e` |
| `wb2a-vitotrol-dual-readonly-high-live-20261011.json` | `c2896229323eba347620b225ac36263a04ac9b59f9e56d94589e68a6a72d7116` |

Der Abgleich verwendet exakt adressierte, 32-Byte-P300-Antworten `0x1DE0`, `0x1E60` und `0x3300` bzw. `0x1DE5/16`, `0x3300/32`, `0x2182/16`. Er prüft die **relativen Byte-Offsets** aus denselben ursprünglichen Images:

- **A-Tupel identisch** in **4 von 4** späteren Originalmessungen.
- **A-Ziel 29/29 Bytes identisch** in **4 von 4** späteren Originalmessungen.
- **B-Tupel identisch** in **2 von 2** späteren Originalmessungen. Das **B-Ziel wurde dabei nicht unabhängig erneut gelesen**; keine falsche Vollständigkeitsbehauptung.
- **Positive Zeit-/Zustandskontrolle:** Der ganz andere SRAM-Anfang `0x2182/16` unterscheidet sich in beiden echten 11.10.-Kontrastzyklen bei **genau Offset 2 = CPU-Adresse `0x2184`**, gegenüber dem ursprünglichen 09.10.-Archiv **`C8 -> CB`**. Diese Änderung beweist, dass die gesamten RAM-Abbilder **nicht trivial identisch** geblieben sind.
- Im zum realen C5-/F9-Vorfall gehörigen **Controller-Neustart am 12.10.** wurde **kein neues vollständiges P300-RAM-Image** aufgenommen. Somit existiert noch **kein Kaltstart-/Neuboot-Beleg** für ROM→SRAM-Initialisierung der beiden Kandidaten.

**Ergebnis nach mehreren Tagen:** Die Quelle-Ziel-aussehenden Zahlen sind tatsächlich langfristig konstant, und andere Controller-RAM-Bytes ändern sich durchaus. **Kein beobachteter Transfer, keine Quellbytes aus ROM, kein Serviceaufruf.**

## 5. Methoden, Tests und Reproduktionspfad

Zwei neue strikt lesende Offlineauditoren und adversariale Testreihen sind im vorhandenen Branch `optolink-research` gespeichert:

```text
tools/wb2a-romcopy-natural-event-correlation.py
tests/test_wb2a_romcopy_natural_event_correlation.py

tools/wb2a-romcopy-crosssession-offline.py
tests/test_wb2a_romcopy_crosssession_offline.py
```

```bash
cd /home/chatgpt-admin/optolink-wb2a-research-20261010
A=/root/p300-trial-work/research-bundles/p300-fullram-run-20261009T083607Z-144293-bundle.tar.gz

sudo -n python3 tools/wb2a-romcopy-natural-event-correlation.py \
    --original-archive "$A" --out /tmp/wb2a-romcopy-natural-events-20261012.json

sudo -n python3 tools/wb2a-romcopy-crosssession-offline.py \
    --original-archive "$A" --json-directory /tmp \
    --out /tmp/wb2a-romcopy-crosssession-20261012.json

python3 -m unittest discover -s tests -q
sudo -n python3 -m unittest discover -s tests \
    -p 'test_wb2a_romcopy_natural_event_correlation.py' -q
sudo -n python3 -m unittest discover -s tests \
    -p 'test_wb2a_romcopy_crosssession_offline.py' -q
```

Die Tests enthalten echte Originaldatenabnahme (nur lokal unter root) und Negativfälle für manipuliertes Archiv/JSON, falschen Speicherbereich, ein abweichendes Targetbyte, fehlende GFA-/Statusguards, gefälschte Controller-Identität, unzulässige Schreibvorgänge, umsortierte Snapshots und andere hypothetische Transferbehauptungen. In GitHub-CI ohne private Quelldaten überspringen sich ausschließlich die eigentlichen Originaldaten-Abnahmen.

## 6. Entscheidung und konkret nächster ROM-Dump-Forschungsschritt

**A/B sind jetzt RESEARCH-LEADS, kein Kandidat für ein kontrolliertes ROM-Dump-Experiment.** Wiederholtes passives Abfragen derselben Tupel, ein neuer 16-Bit-Sweep oder gar Änderungen an DMA-/UART-/Task-Scheduler-Registern bringen voraussichtlich keinen neuen Erkenntnisgewinn. Beide Fragestellungen könnten erst durch ein ROM-Quellarchiv, einen echten Boot-Copy-Trace oder einen nachgewiesenen Controller-eigenen ROM-Dienst positiv aufgelöst werden.

**Jetzt höherer Erkenntniswert:**

1. **Bestehende Controller-Anwendungsfunktionen nach indirektem Inhaltsorakel durchsuchen:** originale, klar zur `20C2/0103`-Firmware gehörende Diagnose-/Firmware-/Tabellen-/Softwarestand-Ausgaben. Kandidat muss eine ROM-abhängige, wechselbar indizierte Antwort und möglichst einen kontrollierbaren Anzeigebereich liefern. Reine feste Prüfsumme/Versionsnummer reicht nicht.
2. **Unterschiedliche Empfangsobjektsemantik statt beliebiger Speicheradresse:** die bereits bewiesene P300-`Virtual_READ`-Innenbyte/Startgate-Asymmetrie als Anker nehmen, aber ausschließlich innerhalb tatsächlich definierter, gültiger Ausgangsobjekte und ohne unspezifizierte Overreads.
3. **Passiver Quell-/Boot-Kontrast erst mit echtem vorhandenen Post-Neustart-Material:** Alt-Snapshot/Neu-Snapshot-Delta **über eine real bereits geloggte Restart-Grenze**. In den hier verifizierten Originalen fehlt dieser direkte Paarbeleg; keinen unbeaufsichtigten Reset oder neuen P300-Protokollwechsel dafür ausführen.
4. Ein echter ROM-Fund braucht zwei unabhängige bytegleiche, quellklar zugeordnete Programm-ROM-Datenabschnitte, plausible M16C-Code-/Vektorprüfung und anschließend segmentierte Wiederholungs-/Hashabnahme. **Stand: 0 verifizierte Programm-ROM-Bytes.**

**Sicherheitsstatus:** Keine neue Live-Anfrage, keine Controller-Writes, keine neuen Systemdienste, keine Änderung an der produktiven VS1-Konfiguration. C5/F9 und die fehlende sofortige Vollarchiv-Störungswache bleiben ein Risiko. Ein späterer echter P300-Test benötigt zuerst ein **konkretes ROM-Orakel**, den Vollarchiv-Fehlervergleich vor/nach mit T+5/T+15/T+75 sowie eine unabhängige Optolink-Host-Restore-Schiene. Keine Reset-, SFR-, DMA- oder Boot-Pin-Experimente am aktiven Gasgerät. `main` und Draft-PR #52 unverändert; alle Forschung im bestehenden Branch `optolink-research`.
