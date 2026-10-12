# Optolink-only ROM-Forschung: 2010 V200KW2-GWG-Lesen, 2011 Adressscan und falsche Programmier-Flags

**Stand:** 12.10.2026 ab ca. 06:58 CEST. Forschungsziel: an der WB2A/VDensHO1 `20C2/0103` die tatsächliche M16C-Program-ROM-Firmware ausschließlich über die vorhandene Optolink-Schnittstelle gewinnen, danach den UART1/KM-Bus-Empfangsdispatcher für echte Vitotrol-200/300-Klasse11-Emulation identifizieren. **Alle Tests in dieser Etappe offline, 0 neue Controller-Reads/Writes**. Keine externe KM-Bus-Hardware und keine blinden SFR-/DMA-/RAM-/EEPROM-/Mode-Schreiboperationen. Produktiver VS1-Splitter und `main` bleiben unverändert; PR #52 Draft.

## 1. Neue unabhängige frühe Primärquelle: KW2 akzeptiert wirklich GWG-VIRTUAL-READ

Offizielle damalige OpenV-Diskussion: [Issue #10, `V200KW2 Protokoll`](https://github.com/openv/openv/issues/10), **ursprüngliche Beitragserstellung 01.11.2010** durch `TerminatorIII`:

```text
Transkript von der V200KW2:
TX = 01 C7 F8 04 04
RX = 20 98 00 02
```

**GWG-Syntax (historisches `Protokoll-GWG`):** `01` ACK/Start, `C7` VIRTUAL READ, **einbyteige Adresse `F8`**, Leselänge `04`, Endbyte `04`. Antwort: Produkt-/Geräte-ID `2098`, Hardwareindex `00`, Softwareindex `02`. Die Quelle nennt ausdrücklich eigene Serialsniffer-Messungen.

**Technischer Beweisumfang:** Mindestens der GWG-VIRTUAL-READ-Opcode `C7` wurde von einer tatsächlich vorhandenen KW2 akzeptiert. Entgegen einer früher zu restriktiven Lesart schließen KW-Kennzeichnung und M30612MC die Verarbeitung älterer GWG-Telegramme nicht aus. **Nicht** daraus ableiten, dass die **anderen** GWG-Opcodes `CB` (Physical Read), `C5` (Physical XRAM Read), `9E` (Physical BE Read) oder gar undokumentierte ROM-Monitore akzeptiert wurden. Schon gar nicht ist der direkte Transfer auf die `20C2`-WB2A belegt.

Die [Antwort von `vitoopen`/Hanspeter vom 01.11.2010](https://github.com/openv/openv/issues/10#issuecomment-339370647) empfiehlt ausdrücklich, zuerst jede Steuerung über **GWG** zu identifizieren und erst danach ggf. zu **KW/300** zu wechseln; sein `voIdent` nutzt genau diese Strategie. Das ist eine **zweite plausible Erklärung** für den GWG-Link in KarlKochs Firmware-Text: Der Link kann den gemeinsamen Transport/Identifikationsweg ansprechen, nicht zwingend das eigentliche 128-KB-ROM-Dump-Kommando.

## 2. 02.11.2010 und 17.01.2011: Ein anderer Entwickler versuchte einen gewöhnlichen Dump

[`TerminatorIII` fragt am 02.11.2010](https://github.com/openv/openv/issues/10#issuecomment-339370668), ob jemand bereits den Bereich **0 bis 65536** ausgelesen habe, um darin die Firmware zu finden. Das ist **eine Frage/Hypothese**, keine bestätigte Firmwareauslesung.

In seiner [späteren Rückmeldung vom 17.01.2011](https://github.com/openv/openv/issues/10#issuecomment-339371859) schreibt er, dass ein selbst entwickelter Reader alle normalen Adressen in eine Binärdatei dumpen sollte; dabei habe er **oberhalb `0x8000` keine Daten** mehr bekommen. Der genaue verwendete Funktionscode pro Adresse ist im Kommentar **nicht** genannt. Darum bleibt die Erklärung *virtueller, nicht physischer Adressbereich* eine Hypothese, auch wenn sie gut zum inzwischen belegten Unterschied `VS1 Virtual_READ != P300 Physical_READ` unserer WB2A passt.

**Dieser normale Scanner war nicht KarlKoch**; das muss getrennt bleiben. KarlKochs Aussage vom 04./22.10.2010 über den **128-KiB-Code** und ~**57.000 Disassembly-Zeilen** ist eine eigenständige zeitgenössische Quellenbehauptung aus der [Original-`KM-Bus`-Wiki-Version](https://github.com/openv/openv/wiki/KM-Bus), deren zugehöriger Quellcode und exakte Optolink-Abfolge weiterhin fehlen.

## 3. Program-ROM-Bank: Architektur erlaubt, gewöhnlicher Read reicht nicht

Für ältere M16C/6x-Controller sind **1 MiB CPU-Adressraum** und 128-KiB-Programm-ROM oben im Adressraum (typisch `0xE0000..0xFFFFF`) dokumentiert; vergleiche [Renesas M16C/62 Originaldatenblatt](https://www.renesas.com/en/document/dst/m16c62-group-datasheet) und [M16C/62N Originaldatenblatt](https://www.renesas.com/en/document/dst/m16c62n-group-datasheet). Die alte 200KW2 ist als M30612MC der M16C/61-Generation beschrieben; die **exakte WB2A-MCU-Teilenummer und ROM-Größe sind nicht bestätigt**. Die öffentliche OpenV-Aussage nennt 128 KiB; nicht eine überprüfte, separat erhaltene ROM-Datei.

Eine gewöhnliche GWG-Abfrage wie `01 C7 F8 04 04` hat nur **8-Bit-Adresse**, KW Virtual_READ/VS1 bzw. normales P300-Physical_READ an der lokalen WB2A benutzen **16-Bit-Adresswerte**. Ein linearer 128-KiB-Programmraum kann damit **nicht ohne zusätzliche Auswahl-/Kopiersemantik** abgedeckt werden. Infrage kommen:
- **ROM-Page/Bank-Schalter** vor dem Read (mit verifizierter Controllerdienst-Semantik);
- **Monitor-/RPC-Bridge**, deren Payload die fehlenden Adressbits enthält;
- **ROM→Low-RAM-Kopierfunktion**, deren sichtbare Nutzbytes dann über physisches RAM auslesbar wären.

Diese Varianten sind **logische/architektonische Hypothesen**, bisher kein tatsächlich belegter Firmware-Befehl. Der bereits aus VitoSoft rekonstruierte `VitosorpAccessController 0xA400` demonstriert zwar Host-Proxy-Design, nimmt aber nur einen **16-Bit-Zielwert** und ist nicht für `20C2` verfügbar. `PROZESS_READ 0x7B` und normale `FC03/FC99` schließen die Lücke ebenfalls nicht. Die beiden belegten WB2A-UART-DMA-Kanäle sind produktiv belegt und dürfen nicht blind übernommen werden.

## 4. Das irreführende Januar-2011-ZIP: vier ROM-/Programmierdatenpunkte gehören zu Fremdreglern

Neu vollständig SHA-/Manifest-verifiziert: `files/TerminatorIII.zip` (Jan. 2011, historischer Archive-Hash `f800bc22537556b096afb43c199311f0bd682698e499fbe6bfbd6bfbbbfa55a3`) enthält
- `vito_V200KW2.xml`, **578** Datenpunkte – **keinen** der unten aufgezählten ROM-/Programmierwerte;
- `vito_V200KW2_extended.xml`, **1.796** Datenpunkte – enthält deren Namen, allerdings **geräteübergreifend**.

Streng gegen die beiden Hersteller-VitoSoft-Originalkataloge geprüft: `DPDefinitions.xml` SHA `efec27568d398021c767771af016143bd51fc196d2d408dbb80faff84d0b19e3`, `ecnEventType.xml` SHA `2338beb0e8544b6149bc4b2433ecabd9509edcdafc2e8e91f00182eba1aff7ba`, **unter Einschluss sämtlicher 200KW2-Revisionsprofile**.

| Scheinbarer Spezialdatenpunkt | Host-Adresse | **Tatsächliche** VitoSoft-Profilzuordnung |
| --- | --- | --- |
| `ChecksummeROMBerechnet` | `0x08F0` | VBC550S, VBC550P, Ecotronic, Ecotronic_100 |
| `NRF_ChecksummeROMLinker` | `0x08F4` | dieselben vier Fremdregler |
| `SC100_ProgrammierstellungEin` | `0x0C04` | nur VBC550S, VBC550P |
| `SC100_ProgrammierstellungAus` | `0x0C05` | nur VBC550S, VBC550P |

**Keine** dieser vier Funktionen ist im Originalkatalog an `V200KW2` (415 Ereignisse), `V200KW2_4` (370), `V200KW2_5` (370), `V200KW2_6` (398) oder `VDensHO1` (581) gebunden. Die vier Programme zeigen **Virtual_READ**; drei besitzen hostseitig **Virtual_WRITE** und sind deswegen als blinde Testadressen an einer produktiven Gasheizung besonders ungeeignet. **Ein Katalogeintrag ist kein beweisbarer Controller-Dispatcher.**

Exakt arbeitender Offline-Auditor `tools/wb2a-v200kw2-2011-metadata-crossprofile-audit.py`; Testmodul `tests/test_wb2a_v200kw2_2011_metadata_crossprofile_audit.py`, echte Hersteller-/ZIP-Quellen **5/5 Tests bestanden**.

## 5. Private Entwicklerforum-Überreste existieren noch in den 2017 nach GitHub importierten Kommentaren

Die [OpenV-Diskussion #245, Kommentar `339633725`](https://github.com/openv/openv/issues/245#issuecomment-339633725) vom **08.05.2015** zitiert eine konkrete Debatte aus dem **alten privaten OpenV-Forum vom 17.01.2009 um 22:31 Uhr**. In ihr wird die Original-GWG-Nachricht `01 AD 07 01 FB 04` für einen **EEPROM-Schreibversuch** und die Speicherung invertierter Folgebytes besprochen. Sie ist **keine** ROM-Auslesesequenz, demonstriert aber, dass einzelne technische Inhalte des geschlossenen Forums öffentlich in Zitaten überlebt haben.

Vollständige Github-REST-Originale vom 12.10.2026 lokal und privat unter `/tmp/wb2a-v200kw2-issue10-sources-20261012/` gespeichert (keine personenbezogenen Token):
- `issue10.json`, SHA `a30befa4e02f836f9c999db4bd573151af0de16c45f0d3aab989280df992eb87` (4693 Bytes);
- `issue10-comments.json`, SHA `62da745448cb3d2b5516cb7a1451ba34f34cb81efbca066f93099373ad4da1a0` (8542 Bytes, 3 Kommentare);
- `issue245-comments.json`, SHA `07d68392d4931453fda0e2f7ccc7fb96ead9174026fc61dbdab5ad8128ac18c0` (13.812 Bytes, 6 Kommentare).

**Wichtig zur Datierung:** GitHub `created_at` steht hier auf **2017** (Wiki-Import), die ursprünglichen Wiki-Diskussionsdaten **2010/2011/2015** wurden aus den erhaltenen `* Date:`-Nachrichtenköpfen ausgelesen. Der SHA-gepinnte Offline-Auditor `tools/wb2a-v200kw2-gwg-issue10-provenance-audit.py` mit fünf synthetischen/Echtdaten-Tests erzwingt diese Trennung und verbietet Aussagen, dass GWG-`CB`/`C5` auf der 200KW2 oder WB2A schon erfolgreich wären. Ein offline geprüfter Text ist **kein** Live-Controllerbeweis.

## 6. Bewertete nächste Experimente – mit Abbruchkriterien

| Ansatz | Evidenz | Technische Wahrscheinlichkeit / Risiko | Entscheidung |
| --- | --- | --- | --- |
| Alte V200KW2 über gewöhnliche GWG-`C7`-ID identifizieren | Echte 2010er Antwort `20980002` | Hohe historische Evidenz **nur für alten V200KW2**; keine neuen ROM-Daten | Architekturhinweis behalten, nicht planlos an WB2A wiederholen |
| Ungeprüften GWG-`CB` oder `C5` an WB2A senden | Nur GWG-Dokumentation, keine KW2/WB2A-Liveprobe | Unbekannter gerätespezifischer Dispatcher; keiner beweist 20-Bit-ROM-Zugriff | **Nicht ausführen**, solange kein vollständig belegter Leseweg |
| Alte `0x0C04/05`-Programmierstellung manipulieren | Historische XML enthält Namen, aber falsches Zielprofil | Potenzieller Moduswechsel auf Gassteuerung, keiner der Zielregler zugeordnet | **Ausgeschlossen** |
| Host-RPC-`0xA400`, `0x7B`, gewöhnliche `FC03/99` erneut blind probieren | Quellseitig nur 16 Bit oder Alias; schon negativ untersucht | Geringer Informationswert | Nur bei neuem eindeutigem Controllerdienst-Nachweis |
| Verlorene KarlKoch-Originalsequenz / alten Developer-Forum-Quelltext aus **noch nicht geprüften Zitaten/Anhängen** gewinnen | Echter 2010er Firmware-Bericht, 2009er Dev-Forum-Zitat erhalten | Höchster potentieller Erkenntnisgewinn, rein offline | **Priorität 1** |
| Belegter 20-Bit-Bank-, ROM-Kopie- oder Monitorservice, dann 16-Byte-ROM-Test | Bisher **kein** solcher Dienst verifiziert | Nur unter harten Restore-/Fehler-/Read-Only-Gates vertretbar | **Priorität 2 nach positiver Quelle** |

### Erfolgsgate

Ein echter ROM-Fortschritt verlangt **einen an `20C2/0103` belegten, reproduzierbar konstanten ROM-Ausschnitt mit plausibler M16C-Programm-Adressierung** (idealerweise Boot-/Interruptvektor oder Querverweis zu Code). Bloß wiederholte 16-Bit-Wörter an `0xF000/0xFFF0`, stabile SRAM-Inhalte oder exakt numerisch gleiche virtuelle und physische Adressen genügen nicht. Danach erst: M16C-UART1 RX-ISR und Klasse11-Parser, echte Vitotrol-Teilnehmeranmeldung bei `0x0A5C`.

### Offline-Reproduktion

```sh
cd /home/chatgpt-admin/optolink-vitotrol-rpm-20261010
python3 tools/wb2a-v200kw2-gwg-issue10-provenance-audit.py \
  /tmp/wb2a-v200kw2-issue10-sources-20261012 \
  --out /tmp/wb2a-v200kw2-gwg-issue10-audit-20261012.json
python3 tools/wb2a-v200kw2-2011-metadata-crossprofile-audit.py \
  /home/chatgpt-admin/research/gwg-artifacts/target-zips/ccbcc6ef4417c0dfd215c96ec8c991bd276f15ed_TerminatorIII.zip \
  /home/chatgpt-admin/research/vitosoft-lfs/DPDefinitions.xml \
  /home/chatgpt-admin/research/vitosoft-lfs/ecnEventType.xml \
  --out /tmp/wb2a-v200kw2-crossprofile-audit-20261012.json
python3 -m unittest discover -s tests -q
```

**Produktivzustand bei Beginn dieser offline Forschung:** `vs1protocol=True`, Konfigurations-SHA `e9a120ef37fe17236a7505ee713c8dd338d98d5093ed75dfb34629d7e8f5c42d`, `VS1_BETRIEB_OK`. Diese Forschung hat weder den laufenden seriellen Owner gestoppt noch Controller-Speicher oder Brennerwerte verändert. Keine Firmware oder Vitotrol-Anmeldung erhalten.
