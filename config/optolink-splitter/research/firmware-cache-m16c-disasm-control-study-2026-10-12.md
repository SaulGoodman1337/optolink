# WB2A/20C2: SRAM-Firmware-Schatten mit echtem M16C/60-Disassembler falsifizierbar prüfen

**12. Oktober 2026 (CEST), Experiment ausschließlich OFFLINE.** Oberziel: **Programm-ROM des laufenden eigenen Heizgeräts über die vorhandene Optolink-Schnittstelle rekonstruieren**, auch wenn nie eine 20-Bit-Adresse auf dem Kabel erscheint. Die Arbeit an einer Vitotrol-RX-Emulation ist bis dahin nachrangig. Dieser Bericht ist im bereits vorhandenen Branch `optolink-research`, kein neues Repository und keine Änderung an `main`.

## 1. Neue Fragestellung und warum die bisherigen 79 RAM-Bilder eine echte Chance sind

Vorherige Beweisstücke auf derselben 20C2/0103-Anlage:
- P300 `FC03 Physical_READ` liefert die **echten** 20.480 Low-SRAM-Bytes bei `0x0400..0x53FF`; alte 79 vollständige Aufnahmen und das zugehörige Byte-/Metadatenmanifest sind kryptographisch verifiziert.
- Davon bleiben 18.955 Bytes über die **79 nacheinander aufgenommenen, nicht atomaren** Bilder unverändert. Der letzte zusammenhängende Block `0x2182..0x53FF`, genau 12.926 Bytes, hat eine Originalentropie von 7,868 Bit/Byte, kaum komprimierbar. Das wurde bereits am 11.10. berichtet, ist **kein** neuer RAM-Fund.
- In einem unabhängigen echten P300-Fenster am 11.10. unterschied sich **ein einzelnes Byte** der ersten 16 Bytes des Blocks gegenüber dem 79er Archiv: `0x2184: C8 -> CB`. Der Block war also nicht universell invariant. Der benachbarte `0x3300/32`-Bereich blieb vollständig identisch.
- Im selben SRAM existieren **mehrere echte 20-Bit-aussehende Pointer** auf `0xF5239`, `0xF5281`, `0xF531E`, `0xF5C28` sowie **nicht verifizierte** potenzielle ROM→RAM-Tupel `0xEA2AB -> 0x3301/29`, `0xFB27D -> 0x0705/7`. Frühere eigene Analysen zeigten, dass die ersteren stark nach Scheduler-Callbacks aussehen; bei den letzteren ist keine reale Copy-Operation nachgewiesen.

**Andere ROM-Zugangsstrategie:** Können die über Optolink lesbaren SRAM-Bytes **direkt Programmcode** oder zumindest eine ursprüngliche ROM-initialisierte Tabelle enthalten? Dann brauchten wir nicht unbedingt einen neuen hohen Adressbereich für **diese** Bytes. Ein guter Befund müsste aber gegenüber byte-statistisch passenden reinen Zufallsordnungen und mit plausibler Codeherkunft bestehen.

## 2. Reale Toolchain – offizieller M16C/60-Prozessor, keine erfundene Opcode-Tabelle

Auf dem LXC wurde am 12.10. eine getrennte, private und nirgends im Produktivpfad registrierte Workbench installiert:

| Originalquelle | Hersteller bzw. Herkunft | SHA256 |
|---|---|---|
| `ghidra_12.1.4_PUBLIC_20260921.zip` (**569.649.598 Bytes**) | [NationalSecurityAgency/Ghidra – Release 12.1.4](https://github.com/NationalSecurityAgency/ghidra/releases/tag/Ghidra_12.1.4_build) | `ddac49f903da9d5bac833e5cc79395098b9c33cfd3279be5f31bd00387d2d4db` |
| Temurin JDK 25.0.4.1+1 (**141.329.719 Bytes**, TAR) | Eclipse Adoptium JDK 25 offizielle API | `dbb698396d478e7fa2b1e50f4103324b2a99b90569ee27c33f2261f9215cf41e` |
| `raw_2182_53ff_real.bin` (**12.926 Bytes**, privater echter SRAM-Ausschnitt) | Manifest-/SHA-validiertes Original-P300-`FC03`-Archiv vom 09.10. | `0c5bdb65afe5fa5576b71d30357e32398ed21f34fef37bd377dc19ec0653d862` |
| 79-Bilder-Original-TAR `p300-fullram-run-20261009T083607Z-144293-bundle.tar.gz` | Nur lokal im Forschungs-LXC | `94d5842b6dc5759ecb446a4c617b60b72873b639885d116032f783abdef8431c` |

**Geprüft:** Gesamt-TAR-SHA, innere Manifest-SHA und vollständige Snapshots `s00001..s00079`, genaue Gerätekennung `20C2/0103`. Vor und nach dem privaten Extraction-Prozess war der `0x2182..0x53FF`-Ausschnitt in Bild 1 und Bild 79 **vollständig bitidentisch**. Der aus dem Archiv extrahierte Ausschnitt wird im Git nicht veröffentlicht.

M16C-Disassembly wurde tatsächlich mit der in Ghidra 12.1.4 enthaltenen Sprache **`M16C/60:LE:16:default`** ausgeführt, nicht mit x86, M68k, händischem String-Filter oder einem namensähnlichen Prozessor. Loader: `BinaryLoader`, Basiskarte `0x2182`, Code-Autoverifikation ausdrücklich **`-noanalysis`**; der Ghidra-Skriptprober setzt maximal **134 identische Startkandidaten** im Abstand **97 Bytes**. Solche künstlichen Starts sind eine Kontrolldichte, **keine** validierten CPU-Programmzähler.

Originales privates Toolverzeichnis (EXEs, JDK, Archivfenster und vollständige Ghidra-Logfiles bleiben außerhalb Git):

```text
/home/chatgpt-admin/research/firmware-m16c-workbench-20261012/
```

Ein unabhängiger Kontrolllauf auf realen `0x0400..0x2181`-RAM zeigte mit blinder Opcode-Deutung massenhaft falsche `BRK`/`JMP.S`-Sequenzen in Füllwerten. **Das beweist, dass „Ghidra kann irgendetwas disassemblieren“ kein Nachweis eines ausführbaren Firmwareabbilds ist.**

## 3. Strenger Gegenbeweis zu unbedachter Codeinterpretation: zehn histogrammgleiche Byteshuffles

**Kontrolldesign:** Die gleichen **12.926 Originalbytes** werden zehnmal deterministisch mit `random.Random(seed).shuffle()` permutiert. Seed `20261012..20261021`, ohne jede Veränderung an Bytehäufigkeiten, Bildlänge, virtueller Startadresse, Ghidra-Version oder 134 Startoffsets. Dadurch prüft der M16C-Decoder vergleichbare Opcode-Häufigkeiten; nur die räumliche Anordnung ist zerstört. Eine **gleichverteilte** Zufallsbytesimulation wäre für diese Fragestellung eine schlechte Kontrolle, weil bereits die Original-Byteverteilung ganz anders ist.

| Original-Real-SRAM vs. zehn Shuffle-Kontrollen | Original | Controls min..max | Control-Ø |
|---|---:|---:|---:|
| Code-Abdeckung nach disassemble(97er Seeds) | **32,10 %** | **28,86–35,91 %** | **32,137 %** |
| Künstlich entschlüsselte `CALL`-Opcode-Anzahl | **61** | **48–74** | **61,1** |
| Interpretierte M16C-Instruktionen | **1810** | **1588–1966** | **1767,2** |
| Interne Sprung-/Call-Ziele innerhalb der 12.926 RAM-Bytes | **119** | **119–146** | **134,2** |
| Bloß nach numerischem Bereich `0xC0000..0xFFFFF` erscheinende `getFlows()`-Ziele | **4** | **6–12** | **8,5** |

**Realer Befund:** Der angeblich geschützte RAM-Code liegt in der realen Ghidra-Decode-Dichte praktisch **auf dem Durchschnitt** der histogrammgleichen Shuffle-Kontrollen. Alle 61 vermeintlichen Calls können als bloßes Decoderartefakt nicht ausgeschlossen werden; schon die künstlichen Kontrollen erzeugten 48–74 Calls und noch **mehr** numerische „High-ROM-Targets“.

Die für ein echtes Code-Disassembly nötige **PC-/ISR-/Vektoren-Provenienz und reale Flusszuordnung** fehlt. Die zehn negativen Kontrollen reichen nicht zu einem statistisch universellen Beweis, dass in keinem Teilabschnitt echter Code liegt. Sie widerlegen aber die **bestehende einfache Begründung „stabile hochentropische Bytes sind wohl ROM-Code, weil Disassembler Befehle und Far-Sprünge findet“**. **ROM-Abbild: noch nicht belegt.** Die nachgewiesenen Bytes stammen ausschließlich aus optisch lesbarem SRAM; ihre ursprüngliche Program- oder Datenquelle ist unbekannt.

## 4. Was das für die indirekte Firmware-Extraktion ändert

**Aufgeben:** Den gesamten stabilen 12,9-KiB-SRAM-Tail als Firmware-Blob behandeln, willkürliche Ghidra-Funktionen von `0x2182` ableiten oder durch zufällige mutmaßliche ROM-`CALL`-Ziele einen beliebigen Monitor erfinden.

**Weiter verfolgen:**
1. **Natürliche ROM→RAM-Initialisierung nach Boot/Reset**: Ein aus ursprünglich verschiedenen Kaltstarts bestimmbar identischer echter SRAM-Ausschnitt könnte eine geladene Tabelle enthalten, wenn zusätzlich die zugehörige ROM-Quelle oder der Copy-Code belegbar ist. Am 12.10. wurde die Heizung wegen C5/F9 vom Betreiber zurückgesetzt; **es existiert bislang kein darüber hinaus gehender, SHA-verifizierter kompletter FC03-RAM-Mitschnitt danach**. Keine neue P300-Sitzung ohne archivgestützte Fehlerwache.
2. **Speziell die auffälligen 20-Bit-Tupel und die `0x3301/29`-Datenquelle** unterscheiden: Erst ein natürlicher, zustandsabhängiger Zielinhaltwechsel *bei stabilem Quellpointer* oder ein nachvollziehbarer ROM-Code-Match würde sie als Kopierservice qualifizieren. Die 79 bisherigen Bilder haben das nicht geliefert; weitere identische Standbilder würden es nicht ändern.
3. **ROM-Code muss nicht auf dem Kabel adressierbar sein**: weiter nach einer variabel parametrierbaren, sicher lesenden ROM-Checksum-/Lookup-Funktion oder einer untergeordneten Lese-/Diagnose-Ausgabe im ursprünglichen Host-Code suchen. Der bereits getestete rein synthetische CRC16-Präfix-Orakel beweist die Mathematik, **nicht** seine Existenz in der WB2A.
4. **P300 FC01 Startadressfilter** von echten ROM-Lookup-Tabellen unterscheiden: überlange `Virtual_READ`s lieferten einzelne innenliegende Datenpunktbytes trotz Fehler bei direktem Start. Das war im Original belegt, aber **kein** allgemeiner physischer Dump.

Die öffentliche [Renesas M16C/26 In-Circuit-Debugger-Firmware-Notiz](https://www.renesas.com/en/document/apn/firmware-requirements-circuit-debugger) beschreibt bei M30624-Beispielen die private RAM-Reserve `0x5380..0x53FF` für einen **zusätzlich installierten** ROM-Monitor. Eine solche reservierte obere RAM-Zone ist **kein** Beweis, dass genau auf der WB2A ein ROM-Monitor installiert ist oder dass dieser Optolink-UART0 bedient; erst echter Code und UART-Vector/Memmap-Bindung würde das erlauben.

## 5. Sicherheitslage und nächste Umsetzung

**Nach dem gemeldeten realen Pumpen-KM-Bus-Fehler C5 und Gebläsestörung F9 vom 12.10. wurden hier keinerlei neue physische/virtuelle Optolink-Anfragen geschickt.** Es wurde lediglich der 8,4-MB-Originalarchiv-Datenstrom erneut geprüft und daraus **lokale, nicht ausgeführte** Bitfolgen für den öffentlichen M16C-Decoder vorbereitet. Ghidra und JDK wurden **nur** als private Forschungsdateien installiert, ohne neue Systemdienste oder Host-Optolink-Konfigurationsänderung.

Jeder spätere **selbst nur lesende** P300-Protokollwechsel ist nach `wb2a-c5-f9-fault-incident-2026-10-12.md` an einen vollständigen System-/GFA-Fehlerarchiv-Vorher-/Nachher-Vergleich inkl. T+5/T+15/T+75 gebunden. Dass ein Host-Restore läuft, kann einen Kessel-SFR-/DMA-Eingriff **nicht** rückgängig machen.

**Echte extrahierte WB2A-Programm-ROM-Bytes: 0.**

## 6. Prüftools und reproduzierbare Auswertung

Die neuen Git-Quellen:

```text
tools/Wb2aM16cCacheProbe.java                Ghidra 12.1.4 Headless-ISA-Messung
tools/wb2a-m16c-cache-disasm-audit.py        SHA-/Histogramm-/Negativkontrollvergleich
tests/test_wb2a_m16c_cache_disasm_audit.py   Fake-/Mutation-/Originalprüfungen
```

```bash
cd /home/chatgpt-admin/optolink-wb2a-research-20261010

python3 tools/wb2a-m16c-cache-disasm-audit.py \
  --workbench /home/chatgpt-admin/research/firmware-m16c-workbench-20261012 \
  --out /tmp/wb2a-m16c-cache-disasm-audit-20261012.json

python3 -m unittest discover -s tests -p 'test_wb2a_m16c_cache_disasm_audit.py' -v
python3 -m unittest discover -s tests -q
```

**Methodik zum Neumessen (nur offline):** Im verifizierten privaten Workbench-Dateibaum: `JAVA_HOME=unpacked/jdk-25.0.4.1+1`, `support/analyzeHeadless <private_project_dir> <unique_name> -import <fixed_12926_byte_image> -processor 'M16C/60:LE:16:default' -cspec default -loader BinaryLoader -loader-baseAddr 0x2182 -noanalysis -scriptPath <research_tools_dir> -postScript Wb2aM16cCacheProbe.java -deleteProject -max-cpu 2`. Alle zehn `raw_tail_shuffle_SEED.bin` werden aus dem **Originalbytearray** mit bekanntem Seed erzeugt; der Parser lehnt andere Inhalte, Ghidra-Skriptfehler, falsch gewählte Programmadressen, veränderte Source-/Tool-SHAs, falsche Decoder-Sprache und ungültige Code-Abdeckungsangaben ab.

**Nicht im Git:** Heizungsspeicher-Abbilder, installierte Ghidra-/JDK-Pakete, private Rohlogs oder angebliche Firmware. `main` bleibt unangetastet.
