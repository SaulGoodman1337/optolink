# WB2A ROM-Forschung: Die historischen OptoLinkLogger-„Ganzen Speicher auslesen“-EXEs als 16-Bit-VS1-Reader nachgewiesen

**12. Oktober 2026 (CEST).** Weiterführende Original-Binäranalyse nach den C5-/F9-Ereignissen. Das Ziel ist weiterhin ein echter 20-Bit-Zugriff auf das **Programm-ROM der WB2A / VDensHO1 20C2/0103** über **die vorhandene Optolink-Schnittstelle**. Eine Quellenbehauptung, ein historischer Host-Dump oder die Erfolgsanzeige eines PC-Tools sind **kein** Ersatz für eindeutig aus der eigenen WB2A gelesene Programmbytes.

**Diese Etappe ist rein offline**: zwei historische Windows-.NET-Executable-Artefakte auf dem LXC wurden ausschließlich als Datenstrom geparst, NIEMALS ausgeführt; weder zusätzliche seriell gesendete Requests noch Firmware-/RAM-/SFR-/Codierungswrites, kein Protokollwechsel, kein Reset und kein produktiver Patch.

## 1. Warum diese Dateien untersucht wurden

Der originale OpenV-Wiki-Anhang `OptoLinkLogger_v0.0.4.zip` von vitoopen/hgy_ch enthält `OptoLinkLogger.exe` (131.072 Bytes) und `Readme.txt`. Die Windows-.NET-Anwendung stellt laut **im Programm eingebettetem Originaltext** die Funktion **„Ganzen Speicher auslesen (binäre Darstellung)“** bereit. In der Release-History der README steht am 29.12.2010 für **0.0.3** „Daten Dump mit konfigurierbaren Parametern (Start-Adr., Länge)“.

Historische Herkunft: [HaustechnikDialog, Vitotronic vom PC steuern/überwachen, hgy_ch vom 08.08.2010](https://www.haustechnikdialog.de/Forum/t/59578/Vitotronic-vom-PC-steuern-ueberwachen?PostSort=1&page=22) beschreibt die selbst entwickelte Software und verweist auf die OpenV-Wiki-Downloads. Ein „ganzer Speicher“ könnte oberflächlich zum von KarlKoch 2010 erwähnten **128-KiB-M30612MC-Programmcode** passen. Die beiden Hypothesen wurden bislang nicht durch Originalcode zusammengeführt.

**Strikte Quellenbezeichnung:** Das zweite Paket ist im Archiv als `OptoLinkLogger_v0.0.1` (118.784 Bytes) bezeichnet. Die darin tatsächlich enthaltene IL-Methodenmenge besitzt bereits `TS_DumpAll`, obwohl die spätere `Readme.txt` die als UI sichtbare Dump-Funktion erst mit Version 0.0.3 aufführt. Ohne authentifizierte interne Build-/Versionsressource wird aus der ZIP-Bezeichnung **keine präzise Kompilierungszeit** der EXE abgeleitet. Die im Test verwendeten Paketlabels dienen nur zur Zuordnung.

## 2. Dateifeste Originalbelege

| Archivetikett | Originalbytes | SHA256 der *EXE* | Tatsächlich gefundene .NET-MethodDef-Zeilen | `TS_DumpAll` IL-SHA256 |
|---|---:|---|---:|---|
| `OptoLinkLogger_v0.0.1` | 118784 | `cb3323cb0c079c8218cc17d4fc25038d349b997c730189547458aa58c7cd1dc5` | **199** | `a5da63350ea89d136a973e7c10af52afd03d2d081a770c33532ae12e111f46f1` |
| `OptoLinkLogger_v0.0.4` | 131072 | `9f01cb85bb9e4c6982ac405cee2bc7e67a534e9bc95d3e7a637882c3768976ff` | **220** | `124320250d1c20c127d5e6f409f88d8163f129dc986827d6f26d351ff8d8e72e` |

Privater Originalspeicherort (nicht nach GitHub übernehmen):

```text
/home/chatgpt-admin/research/gwg-artifacts/target-unpacked/
  5478defe086d4de67698fc95378ad2ee5e76eea7_OptoLinkLogger_v0.0.1/OptoLinkLogger.exe
  bc7ca87707c24d1826bcb6ba71b5172f5f5f73c9_OptoLinkLogger_v0.0.4/OptoLinkLogger.exe
```

Die Parser prüfen DOS `MZ`, PE32-/CLR-Metadata-RVA, BSJB-Header, `#~`-/`#Strings`-/`#US`-Heap, MethodDef-Namen, vollständige CIL-Methodenkörper, Byte-identische Funktion `SetReadAddr`/`GetReadAddr`/`SetReadLen`/`GetReadLen`, direkte `call MethodDef`-Instruktionen in `TS_DumpAll`, den `0xFE`-Blockgrößenkonstanten und die **wirklich aus dem `TS_DumpAll`-IL referenzierte** Fehlermeldung:

```text
Dump supports protocol VS1 only.
```

Es ist eine **.NET-PE-Datei eines PC-Programms**, **kein** aus der Heizung gewonnenes 128-KiB-M16C-Abbild.

## 3. Originaler Maschinen-/IL-Beweis statt Interpretation aus Funktionsnamen

`TS_DumpAll` ruft in **beiden** Versionen **exakt einmal je statischer CIL-Callstelle** die vier dazugehörigen Methoden `SetReadAddr`, `GetReadAddr`, `SetReadLen`, `GetReadLen` auf. Ihre unterschiedlichen CLR-Token werden aufgelöst – die Analyse sucht **nicht bloß Zeichenketten** in einem Binärfile.

| Codeteil | Im realen IL nachweisbare Wirkung | Konsequenz |
|---|---|---|
| `SetReadAddr` | Aufrufargument **>> 8 & 0xFF** nach Bytearray-Index **1**, **& 0xFF** nach Index **2**; `stelem.i1` | **Exakt 16 wirksame Adressbits**, kein fünftes ROM-Nibble und kein Bankselektor |
| `GetReadAddr` | `Byte[1] * 0x100 + Byte[2]` | Rücklesung derselben zwei Bytes; kein versteckter dritter Adressbyte |
| `SetReadLen` | Aufrufargument **& 0xFF** nach Bytearray-Index **3** | Nur **1 Byte Länge**, kein zusätzlicher ROM-Adressparameter |
| `TS_DumpAll` | Direkte Calls zu allen vier Methoden; `ldc.i4 0xFE`; VS1-only-Gate | Liest sequentiell konfigurierbare Abschnitte des **VS1-Adressraums** |

Kleine Release-Differenz: v0.0.1 `SetReadAddr` benutzt im Highbyte-Pfad `shr` (`0x63`); im späteren 0.0.4-Code steht `shr.un` (`0x64`). Nach Maskierung mit `0xFF` bleiben für gültige nichtnegative 20-Bit-Adressen beide Highbytes identisch. Unterschiedliche Feldtoken `0x04000050` und `0x0400005D` beweisen, dass wirklich **verschiedene** Assemblies untersucht wurden.

### Praktischer Gegenbeweis: 20-Bit-Adressen verlieren ihr oberes Nibble

Die Testfunktion `model_original_vs1_address_setter()` bildet ausschließlich die originalen IL-Setter mit Python nach (kein Controllerzugriff):

| Angeforderte gedachte M16C-Adresse | Übertragene 16-Bit-Adresse | 2-Byte-Adresse + 1-Byte-Länge (8) |
|---|---|---|
| `0x00000` | `0x0000` | `000008` |
| `0x0FFFF` | `0xFFFF` | `ffff08` |
| **`0xE0000`** | **`0x0000`** | **`000008`** |
| **`0xF23FF`** | **`0x23FF`** | **`23ff08`** |
| **`0xFFFFF`** | **`0xFFFF`** | **`ffff08`** |

Diese 3-Byte-Darstellung ist **Adress- und Längenfeld**, kein vollständiges Optolink-Telegramm. Tatsächlich versucht der originale historische Reader also **keine beliebige 20-Bit-Quelladresse**. Die dokumentierte alte Mask-ROM-Quelle bei z. B. `0xE0000` wäre **nicht** durch „Start-Adresse E0000“ in diesem Tool lesbar.

## 4. Bewertung und verbleibendes ROM-Extraktionsgate

**Belegt:** Die beiden konkret gefundenen OpenV-OptoLinkLogger-EXEs implementieren einen vollständigen **VS1-16-Bit-Reader** mit optionalen Windows-Dateidumps. Sie bieten **keinen dort gefundenen 20-Bit-ROM-Lesepfad**. Der Oberbegriff „Ganzen Speicher auslesen“ bezieht sich innerhalb `TS_DumpAll` auf den vom Reader erreichbaren Adressraum; daraus folgt kein M16C-Programm-ROM-Inhalt. Das widerlegt **diese eine Kandidatenklasse**.

**Nicht belegt:** Ein anderer historischer GWG-, KW-/P300- oder Mask-ROM-Service kann dennoch 20-Bit-Quellen adressieren. Ebenso bleiben der reale WB2A-MCU-Typ, der interne Monitor und der tatsächliche KarlKoch-Readout-Mechanismus unbekannt. Die originale OpenV-Aussage `M30612MC/200KW2: ~128 KiB per Optolink` bleibt ein realer Hinweis **für eine andere Anlage**, nicht das hier untersuchte PC-Programm.

Die drei sinnvollsten verbleibenden Ansätze:

1. **Quellenfund für höheren Adressselektor oder vollständigen Originaltrace** im historischen M30612-/OpenV-/PSHome-Kontext; streng zwischen 200KW2/2098 und WB2A/20C2 unterscheiden.
2. **Provenienzbelegte WB2A-/VitoSoft-RPC-/Monitor-Bridge** finden, deren Request **20-Bit-Quelladresse** oder einen sicher beobachtbaren ROM-zu-RAM-Transfer kodiert; gewöhnliche FC03-/GWG-/VS1-Adress-Aliase sind keine Alternative.
3. Ein echtes Original-Firmware-Abbild nur dann klassifizieren, wenn Quelle und Geräte-/Softwareindex, ROM-Adresse, zwei reproduzierbare Auslesungen und Code-/Vektorplausibilität nachweisbar sind. Das vorhandene Renesas-Serial-Boot-Verfahren benötigt andere Hardware-/Boot-Pins und ist **nicht** über den normalen Optolink-UART0-Anwendungsmodus nachgewiesen.

**Live-Testfreigabe: NICHT ERTEILT**, weil nach den belegten heutigen C5-/F9-Heizgerätstörungen noch immer kein quellenbasierter 20-Bit-Leserequest vorliegt. Keine neuen Blind-Opcode-/SFR-/DMA-Schreibtests und kein Modul, das den einzigen Serial-Port stiehlt, als vermeintliches ROM-Experiment. Der Anwender priorisiert das Firmwareziel; der vollständig digitale, bereits vorhandene Offline-Fund wird deshalb zuerst ausgeschöpft. Kein Widerspruch zum Forschungsziel.

## 5. Reproduzierbare Originaltests

```bash
cd /home/chatgpt-admin/optolink-vitotrol-rpm-20261010

python3 tools/wb2a-optolinklogger-cli-metadata-audit.py \
  --output /tmp/wb2a-optolinklogger-cli-metadata-audit-20261012.json

python3 tools/wb2a-optolinklogger-crossversion-rom-gate.py \
  --out /tmp/wb2a-optolinklogger-crossversion-rom-gate-20261012.json

python3 -m unittest discover -s tests -p 'test_wb2a_optolinklogger_cli_metadata_audit.py' -v
python3 -m unittest discover -s tests -p 'test_wb2a_optolinklogger_crossversion_rom_gate.py' -v

# Ganze bereits bestehende Regression, keine neuen Hardware-Tests:
python3 -m unittest discover -s tests -q

# Ergebnis ist strikt: controller_rom_bytes_extracted=0.
```

Der neue Python-Parser hat **keine Drittanbieter-Abhängigkeit** und läuft mit der vorhandenen Python-Standardbibliothek. Real-EXE-Manipulation, fehlende/gekürzte Dateien, fehlende CIL-Methodendefinitionen, falsche Token oder bekannte falsche IL-Körper werden testseitig abgewiesen. Original-EXEs bleiben lokal und werden **nicht** im Repository als Programm- oder Firmwaredump ausgegeben.

**Git-Routing:** Forschungsstand nur nach `feat/wb2a-vitotrol-rpm-20261010` / Draft-PR #52; später gezielt nach `optolink-research` (separater Integrationsbranch, keine gesamte Feature-Historie). `main` und Produktiv-Optolink bleiben unverändert.
