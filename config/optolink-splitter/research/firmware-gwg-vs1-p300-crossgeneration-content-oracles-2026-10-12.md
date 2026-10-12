# WB2A/20C2 – GWG, V1/VS1 und P300 im Generationenvergleich: indirekte Firmware-Inhaltsorakel

**Forschung vom 12.10.2026.** Ziel bleibt die Gewinnung **echter Programm-ROM-Bytes der WB2A/VDensHO1/20C2/0103 ausschließlich über das bereits vorhandene Optolink-Interface**. Ein direkter 20-Bit-ROM-Leseopcode ist dafür nicht grundsätzlich erforderlich: Auch ein ROM-Tabellenindex, ein ROM-CRC mit variabler Länge oder ein Anwendungsdienst, der Daten aus ROM in einen lesbaren Diagnosepuffer bringt, wäre denkbar. Dieses Dokument trennt aber strikt **Katalog-/Hostcode-Belege**, **bereits unabhängig gemessene 20C2-Fähigkeiten** und **noch unbewiesene Hypothesen**.

## 1. Verwendete originale und unabhängige Quellen

Der neue reproduzierbare, ausschließlich offline ausgeführte Auditor `tools/wb2a-gwg-vs1-p300-generation-oracle-audit.py` bindet **alle fünf tatsächlich verwendeten Quellen über Größe und SHA256**:

| Quelle | Größe | SHA256 | Rang |
|---|---:|---|---|
| Privates VitoSoft `DPDefinitions.xml` | 186.559.004 | `efec27568d398021c767771af016143bd51fc196d2d408dbb80faff84d0b19e3` | Original-Hostkatalog, nicht WB2A-Firmware |
| Privates VitoSoft `ecnEventType.xml` | 9.935.374 | `2338beb0e8544b6149bc4b2433ecabd9509edcdafc2e8e91f00182eba1aff7ba` | Originale Host-Funktionsdefinitionen |
| `openv.wiki/Protokoll-GWG.md` | 1.416 | `6767a5fc30db44ac89ca9e9e4d27d64f5f64091ddd0419b39586a493155af82c` | Historische OpenV-Kommandotabelle |
| Community-RE `InsideViessmannVitosoft/VitosoftCommunication.md` | 7.022 | `19fc2189e1392aa11ba986ee063c2d288e4197637f56083012a702c913881371` | Dritter unabhängiger Dokumentationsautor, kein Controllercode |
| Original-C# `COptoLinkCommAsync.cs` aus `philippoo66/ViessData21` | 55.123 | `ce1d78a9a90e22d0283791f8a0c8ee6a3c01ca617f183819ba831978735fb80d` | Tatsächliche Drittanbieter-KW/P300-Hostimplementierung |

Das C# stammt aus `ViessData_V2412_Sources.zip`, SHA256 `77f65616ed3911cc91440058c1d3db03f7c95b4795d3c66a1d15bbabd7b1dcaa`, im Repo `https://github.com/philippoo66/ViessData21`, bei dieser Analyse HEAD `80a2a8cf6e0506edcb93fd39659f044bc88a4c17`. Zusätzlich wurde dessen `DP_Listen_2.zip` (SHA `d2109b50aa65f0248eefcef13cd7cf9d816498b1b27bd6817d7119e0c73f923b`) **nur als Text** eingesehen. Darin finden sich Datenpunktlisten für `GWG_VBEM_00`, `V200KW2`, `VDensHO1` und mehrere neuere `VScotHO1_200`-Varianten. Kein fremdes Windows-EXE wurde ausgeführt.

Originale private Dateien, 1,8-MB-Leseindex und ausgepackte Fremdquellen liegen außerhalb Git unter `/home/chatgpt-admin/research/firmware-bridge-comparative-20261012/` und `/home/chatgpt-admin/research/vitosoft-lfs/`. Das Git-Tool selbst enthält **keine VitoSoft-Tabelleninhalte**, nur Prüfsummen, Selektions-/Analyseverfahren und zusammenfassende Ergebnisse.

## 2. VitoSoft-Generationendaten: 399 Profile, 104.339 Zuordnungen, 11.582 Eventtypen

Der Auditor traversiert echte `ecnDatapointType`, `ecnDataPointTypeEventTypeLink` und `ecnEventType`-Datensätze (mit XML-Fremdschlüsselprüfung), bindet deren Alias-IDs an die Definitionen aus `ecnEventType.xml` und erstellt eine **90-Profile-Familienmatrix** mit 39.263 eindeutigen Profil/Event-Zuordnungen, 2.314 unterschiedlichen Event-Definitionen. Nicht nur Namens-Grep.

| Originaler Hosttyp | Typ-ID | Eventtypen | `Virtual_READ` | `GFA_READ` | `Remote_Procedure_Call` | Historische Sonderleser |
|---|---:|---:|---:|---:|---:|---|
| **WB2A/VDensHO1** | **60** | **581** | **462** | **94** | **22** | keine `KMBUS_EEPROM_READ`-, `EEPROM_READ`- oder `Physical_READ`-Eventbindung |
| VDensHO1_4 | 208 | 560 | 442 | 94 | 21 | vergleichbarer älterer/abweichender HO1-Hoststand |
| VPendHO1 | 19 | 581 | 462 | 94 | 22 | 100 % gleiche Eventaliases wie WB2A |
| VScotHO1 | 131 | 581 | 462 | 94 | 22 | 100 % gleiche Eventaliases wie WB2A |
| **V200KW2** (ältere KW/V1-Familie) | **26** | **415** | **407** | **0** | **4** | andere Diagnose-Metadatenstruktur |
| **GWG_VBEM_00** (ältere GWG-Familie) | **76** | **220** | **6** | **0** | **0** | 54 KM-Bus-EEPROM-, 72 EEPROM-, 51 Physical-, 17 BE-, 12 XRAM-Reads |
| VScotHO1_200 (neuere HO2B-Klasse) | 424 | 945 | 810 | 104 | 22 | wesentlich mehr virtuelle Datenobjekte |
| VScotHO1_200_01 | 437 | 1.058 | 923 | 104 | 22 | u. a. vierbyteige LAN-Karten-Firmwaremetadaten |

**Besonders nützlich für die weitere Quellcode-Korrelation:** Die 581 tatsächlichen *Eventaliases* von `VDensHO1`, `VPendHO1` und `VScotHO1` sind **mengenidentisch**. Die angepassten `VDensHO1_4` übernehmen **558 von 581** und spätere `VScotHO1_200_01` **546 von 581**. Das deutet auf wiederverwendete PC-seitige Diagnosedienste hin. **Es beweist weder identische CPU, noch denselben ROM-Code noch, dass ein Sonderdienst überall ausgeführt werden kann.**

Die historische `V200KW2` hat nur 108 mit der WB2A gemeinsame Eventaliases; `GWG_VBEM_00` sogar nur vier. Ein funktionierender `C7`-Identitätstest auf WB2A macht sie **nicht** zu einem alten `2053/2054`-Controller.

## 3. Wichtigste Erkenntnis: Indirekte Speicher- und Diagnosedaten *werden* als Host-Objekte gekapselt

Das ist ein konkretes Funktionsprinzip aus VitoSoft, nicht nur eine Spekulation:

| Quelle | Ein einziger gekapselter Lesevorgang | Mehrere logisch benannte Felder |
|---|---|---|
| Älteres **GWG** | `KMBUS_EEPROM_READ` Basis `0x00A0`, feste Blocklänge **10 Bytes**, `PrefixRead=030000000101` | zehn benannte Fehlercodes durch `BytePosition=0..9` |
| **WB2A / VS1 / P300** | `Virtual_READ 0x10A0`, feste Blocklänge **16 Bytes** | elf GWG-Codierstecker-Felder an Position 0..10 |
| **WB2A / VS1 / P300** | `Virtual_READ 0xA132`, feste Blocklänge **29 Bytes** | 14 LON-Alarmfelder, 11 unterschiedliche Positionsstarts |

**Entscheidend:** Die vielen logischen Datenpunkte sind **keine vielen unabhängigen geräteseitigen Lesefunktionen**. Der Host lädt ein Antwortobjekt und interpretiert dessen Bytepositionen. Beim GWG-Beispiel werden die Bytes `0..9` im gleichen `0x00A0/10`-Block selektiert; darin steckt **kein** nachgewiesener Firmware-Bankselektor. Die einheitliche `PrefixRead`-Zeichenfolge bleibt ein Routing-/Datenbankbeleg, noch kein erforschter Byte-für-Byte-Slave-Monitor.

Dieser Mechanismus ist für die Firmwareforschung dennoch relevant: Ein **wirklich ROM-abgeleitetes, indizierbares Antwortobjekt** könnte ohne 20-Bit-Zeiger auf dem Optolink-Kabel echte ROM-Daten verraten. Es muss aber die ROM-Herkunft und eine frei variierbare Auswahl der Quellbytes nachweisbar tragen. Die geprüften Codierstecker-/LON-/KM-Bus-Historyblöcke tun das bislang nicht.

## 4. GFA_READ separat eingegrenzt, nicht mit ROM gleichgesetzt

Im WB2A-Hostprofil stehen **94 `GFA_READ`-Datenpunkte**, aber nur **64 verschiedene Hostadressen**; **alle 94 haben BlockLength=1**. Viele doppelte Adressen führen nur alternative Namen/Deutungen (z. B. `VSKO_Scot_CES_P0` / `VSKO_Scot_P0` bei `0x4000`, `VSKO_GFA_P89` bei `0x4059`), nicht verschiedene physische ROM-Ziele.

Im historischen **VS1** ist `GFA_READ` Funktioncode `0x6B`, `PROZESS_READ` `0x7B`; normales `Virtual_READ` `0xF7`. P300 kennt eine getrennte FC-Semantik; eine identische Zahl `0x4000` im VitoSoft-Katalog ist **nicht** automatisch SRAM-Adresse `0x4000`, geschweige denn Programm-ROM-Adresse.

Damit ist `GFA_READ` ein belegter funktionsorientierter Lesekanal, aber seine **1-Byte-Datenpunktantworten** sind kein direkt nutzbarer Firmware-Seitenleser. Die im anderen Forschungszweig beobachtete Gebläse-Drehzahl und der GFA-Parameter `P06` bleiben eine mögliche Anwendung dieses Telemetriepfads, aber nicht der Beweis einer Hauptcontroller-ROM-Quelle.

## 5. Echte neuere VS1/KW-/P300-Hostcode-Implementierung gegengeprüft

Aus dem originalen, nicht gestarteten öffentlichen ViessData-C#-Source `COptoLinkCommAsync.cs`:

- `ReadDataKW(int addr, byte len)`: sendet `0xF7`, **Adressbyte High**, **Adressbyte Low**, Blocklänge. Optionales `0x01`-Startbyte hängt vom Verbindungszustand ab.
- `ReadData300(int addr, byte len)`: sendet `0x41` (STX), Kontrollbytes/Funktionscode, **Adressbyte High**, **Adressbyte Low**, Blocklänge und Telegramm-Checksumme.
- Das beworbene **segmentierte Blocklesen mit Offset** aus dem ViessData-2.3-Release beschreibt eine Fähigkeit des *PC-Readers*, nicht eine neue belegte Bank- oder 20-Bit-ROM-Befehlsklasse. Die im Code tatsächlich untersuchten Standardleser bilden nur zwei Adressbytes.
- Das originale alte GWG-Wiki bestätigt die separaten einbyteigen `C7` (Virtual), `CB` (Physical) und `43` (KM-Bus-EEPROM)-Typen. Sie sind **nicht** VS1-`6B` und nicht automatisch P300-`FC03`.

Das ist ein direkter Sourcecodevergleich und keine Aussage über alle undokumentierten Controllerkommandos. Insbesondere könnte ein mehrstufiger Wartungsdienst oder ein ROM-Initialisierungsmechanismus ganz andere Nutzdaten und Zustandsfolgen besitzen.

## 6. Falsches Positiv bei „ROM-Prüfsumme“ generationengebunden aufgelöst

Über **alle 399 Profile** überprüft, nicht nur die 90 Familienkandidaten:

```text
ChecksummeROMBerechnet~0x08F0
NRF_ChecksummeROMLinker~0x08F4
```

Diese beiden echten **zweibyteigen `Virtual_READ`-Hostevents** sind **ausschließlich** diesen vier Profilen zugeordnet: `VBC550S`, `VBC550P`, `Ecotronic`, `Ecotronic_100`. **Nicht** `VDensHO1`, `V200KW2`, `VScotHO1` oder GWG-VBEM. Außerdem enthält keiner der beiden geprüften Event-Deskriptoren einen ausweisbaren Parameter, mit dem die berechnete ROM-Präfixlänge in Einzelschritten verstellt wird. Ein fester ROM-Gesamt-CRC reicht mathematisch nicht aus, um das Firmwareabbild zu rekonstruieren.

Die jüngere Familie `VScotHO1_200_01` hat ein anderes Objekt `HO2B_LAN_Card_Firmware~0xD069` (die **wirkliche** Host-Leseadresse ist `0xD084`, **4 Bytes**, `Virtual_READ`). Das ist zunächst **LAN-Karten-Firmware-Metadatenanzeige**, kein ROM-Dump des WB2A-Hauptcontrollers. Der Auditor schützt gegen „Stromverbrauch“ als irrtümlichen ROM-Namensfund.

## 7. Direkte technische Folge – neue Suchstrategie ohne redundanten Adresssweep

Nach der bereits erfolglosen Prüfung der direkten 16-Bit-Adressen, der 79 RAM-Snapshots und der zwei Far-Pointer-Lookalikes wird jetzt **nicht** erneut eine hypothetische CPU-20-Bit-Quelle über VS1-/P300-Standardreads adressiert.

Die konkreten nächsten Forschungsprüfungen sind:

1. **Funktions- statt Adresseinstieg:** Im OEM-`vsmInterfaceCore`-IL und bei alten, nachweislich kompatiblen Kommandowegen für **GWG/VS1/P300** nach mehrstufigen, **read-only** Controlleranwendungen suchen, deren Parameter auf eine geräteinterne Tabelle oder Prüfsumme angewendet werden. Unterscheiden: Transportfunktion, verschachteltes Routing, Byteposition-Hostfilter, Controllerinterne Datenverarbeitung.
2. **HO1-Familien-Querschnitt:** Identische frühere `VDensHO1/VPendHO1/VScotHO1`-Datenpunkte und Ausnahmen der `_4`- und späteren `_200`-Profile als Anker nehmen. Datenpunkte, die sich ändern, können auf eine geänderte *Diagnoseoberfläche* hinweisen; keine identische Firmwarefunktion behaupten.
3. **P300-/VS1-Objektstart-Falle:** Das früher live belegte `Virtual_READ 0x088E/8` ermöglicht ein gültiges Gesamtobjekt trotz ungültiger Einzel-Startadresse im Inneren. Deshalb zunächst ausschließlich bekannte gültige Objektstarts/-längen und tatsächlich belegte Antworttypen aus alten Traces auf ROM-Abhängigkeit untersuchen, nicht hochadressige aliasende „Overreads“.
4. **Authentischen ROM-Zugangsbeweis suchen:** historischer OpenV-M30612MC/KW2-Trace, Gerätedienst-Monitor, ROM-CRC-Präfix-Orakel oder programmseitige ROM-zu-low-SRAM-Kopie mit überprüfbarer Herkunft. Ohne Quellbeleg keine Live-SFR/DMA/UART-/Boot-Umstellungen an der aktiven Gasregelung.

Ein einziges echtes, bytegenau verifiziertes Programm-ROM-Fenster wäre der erste Erfolg. Erst nach wiederholbarer ROM-Quell-/Vektor-Plausibilität ist ein segmentierter, mehrfach kontrollierter Dump sinnvoll. **Aus dieser Runde wurden 0 echte WB2A-Programm-ROM-Bytes gewonnen.**

## 8. Reproduzierbare Checks und unveränderter Betriebszustand

```bash
cd /home/chatgpt-admin/optolink-wb2a-research-20261010

# ORIGINAL-Binär-/XML-Provenienz, 399 Profile, 90er Generationsvergleich:
python3 tools/wb2a-gwg-vs1-p300-generation-oracle-audit.py \
   --out /tmp/wb2a-crossgeneration-oracles-20261012.json

# Mutationen gegen falsche Herkunft, andere Prozesskommandos,
# Bytefeld-Out-of-Range, unbekannte Profile, 20-Bit-Serializer-Erfindungen:
python3 -m unittest discover -s tests \
   -p 'test_wb2a_gwg_vs1_p300_generation_oracle_audit.py' -v

# Sämtliche bestehenden lokalen Research-Tests:
python3 -m unittest discover -s tests -q
```

Teststatus: **24 gezielte Tests**, einschließlich einer echten SHA-geprüften Komplett-Auswertung der fünf Quellen, bestanden. CI ohne private Quellen überspringt nur die vollständige Originalprüfung und behält die adversarialen Tests. Das Originalarchiv, EXEs und XML wurden nicht in Git kopiert.

**Heizungsstatus:** Diese Analyse führt **keinen** Optolink-Lese-/Schreib-/Protokollwechsel durch; `controller_reads=0`, `controller_writes=0`; `main`, produktiver Splitter, Heizungsparameter und Draft-PR #52 bleiben unberührt. Die historischen Störungen C5/F9 sind weiterhin als Warnung für spätere Live-Experimente dokumentiert. Für einen echten neuen Hardwaretest ist vorab ein gerätespezifisch begründeter, ungefährlicher Leseweg plus Fehlerhistorie vor/nach inkl. Nachbeobachtung nötig.
