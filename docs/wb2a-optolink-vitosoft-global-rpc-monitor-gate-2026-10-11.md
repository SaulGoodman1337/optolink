# WB2A 20C2 / Optolink-only: globaler VitoSoft-RPC-/Adressbank-Audit

**Stand: 11.10.2026.** Ziel bleibt die echte Vitotrol-200/300-Emulation ueber den bereits vorhandenen Optolink-Kanal. Der alternative externe Raumregler (`0x2321`) bleibt pausiert. **Keine externe Hardware, keine neuen Controller-Writes, keine Protokollumschaltung in diesem Arbeitsschritt.**

## Auftrag und gesicherte Quellen

Untersucht wird die fehlende 20-Bit-Quelladressen-Eingabe einer ROM-zu-RAM-Copy/Monitor-Routine. Der bereits hardware-verifizierte P300-`Physical_READ`-Pfad kann nur von einem **16-Bit-Quellwert** zum Scratch `0x1933`, TX-Body `0x19B5`, DMA1/UART0 kopieren. Fuer einen Code-Dump ueber `0xFFFF` fehlt der 20-Bit-Selector/Monitor. Falsch positive 20-Bit-Hinweise aus fremden Geraetefamilien duerfen nicht als `20C2`-Aufrufe interpretiert werden.

Authentische VitoSoft-Quellen:
- `/home/chatgpt-admin/research/vitosoft-lfs/ecnEventType.xml` – SHA256 `2338beb0e8544b6149bc4b2433ecabd9509edcdafc2e8e91f00182eba1aff7ba`.
- `/home/chatgpt-admin/research/vitosoft-lfs/DPDefinitions.xml` – SHA256 `efec27568d398021c767771af016143bd51fc196d2d408dbb80faff84d0b19e3`.
- Bereits getestete selektive Identifikation `VDensHO1 / 20C2 / Softwarestand 0103`, DataPointType **60**, 581 Event-Links / 22 RPC-Events.
- Original-Optolink-P300-Frames/RAM und DMA-Registerbeweise dokumentiert in `physical-read-scratch-map-2026-09-27.md` und `docs/wb2a-optolink-only-rom-dma-bridge-2026-10-11.md`.

**Code:** `tools/wb2a-vitotrol-global-rpc-monitor-audit.py` (nur XML und JSON, SHA-geprueft), `tests/test_wb2a_vitotrol_global_rpc_monitor_audit.py`. Komplette lokale Ergebnisdatei (nicht notwendig fuer die Git-Ausfuehrung): `/tmp/wb2a-vitotrol-global-rpc-monitor-audit-20261011.json`.

## 1. Globaler Katalog: kein belegtes Monitor-Adressfeld

| Messgroesse | Original-VitoSoft-Wert |
| --- | ---: |
| `EventType` Eintraege | **11.582** |
| Verschiedene RPC-Events (FCRead oder FCWrite) | **1.034** |
| `FCRead=Remote_Procedure_Call` | **1.010** |
| `FCWrite=Remote_Procedure_Call` | **888** |
| RPC-`PrefixRead` mit 1 Byte | **866** |
| RPC-`PrefixRead` mit 3 Bytes | **30** |
| RPC-`PrefixWrite` mit 1 Byte | **757** |
| RPC-`PrefixWrite` mit 2 Bytes | **16** |
| Numerisch geparste Adressen `>0xFFFF` | **0** |
| Ungueltige hexadezimale PrefixRead/PrefixWrite-Angaben | **0** |
| Nicht standardmaessig `0x...` geschriebene `Address`-Felder | **113** |

Die 113 nicht als `0x...` geschriebenen Address-Felder sind gesondert protokolliert (u.a. `0`, `0.1`, `127.1`); sie duerfen nicht als verifizierte 16-Bit-Optolink-Wireadressen gelten. **Einzige vermeintliche fuenfstellige hexadezimale Ausnahme** ist `0x0F120` bei `SM1_Sensor_10_GWG2015`: das ist dezimal 61.728 und gleich `0xF120`, also weiterhin 16 Bit.

### Alle echten RPC-PrefixRead-Werte mit 3 Bytes

Genau **30/30** Datensaetze haben:
- `Address=0xA095`
- `FCRead=Remote_Procedure_Call`
- IDs `mBusRPCReadDataHeader000` bis `mBusRPCReadDataHeader...`
- z.B. `PrefixRead=000000`, `000100`, `000200`, `010000`.

Das ist die **M-Bus-Datenheaderabfrage**, nicht ein ausgelesener Programm-ROM-Bank-Selector. Eine 3-Byte-Host-Metadatendefinition beweist weder eine bestimmte Wire-Serialisierung noch einen registrierten Service auf einer anderen Geraetefamilie.

Alle **16/16 zweibyteigen RPC-`PrefixWrite`** referenzieren `0xA066`, IDs `vlogRPCCreateLONChannel00..15` mit `0000..0F00`. Das ist **LON-Kanalerzeugung** und ein *Schreibdienst*, kein Firmwareausleseweg. Diese Funktion wird am Kessel nicht getestet.

Die uebrigen laengeren `PrefixRead`-Familien sind `KMBUS_EEPROM_READ` (90), `Virtual_MarktManager_READ` (58), `Virtual_MBUS` (17) sowie RPC (30). Ein langes Praefix ist grundsaetzlich moeglich; daraus folgt **nicht** automatisch ein 20-Bit-MCU-Adressfeld.

## 2. Exakte `VDensHO1 / 20C2`-Gegenprobe

Die getrennte SHA-verifizierte Join-Auswertung `DPDefinitions.xml -> ecnEventType.xml` ergibt erneut **581** passende Events und **22** RPC-Events in unserer Geraeteprofilfamilie.

| Eigene RPC-Adresse | Katalogisierte Bedeutung |
| --- | --- |
| `0xA009` | `vlogRPCClearMemberList` (Teilnehmerliste loeschen) |
| `0xA010` | `Teilnehmerliste_LON_...` (Liste) |
| `0xA029` | `valmRPCClearErrorHistoryTable` (Fehlerhistorie loeschen) |
| `0xA050` | `Konfi_FunktionReset_GWG` (Reset) |
| `0xA051` | `Bedienparameter...FunktionReset` (Reset) |

Keines der 22 Profil-RPC-Events nennt ROM/Flash, Bootloader, Monitor oder eine 20-Bit-Quelladresse. **`0xA095` und `0xA066` sind im `20C2`-Profil nicht vertreten.** Der hostseitige XML-Katalog kann undokumentierte MCU-Serviceroutinen nicht ausschliessen, liefert aber **keinen** abgesicherten Optolink-Aufruf dafuer. Die als Reset/Loeschung beschriebenen `0xA009/A029/A050/A051` bleiben fuer Experimente gesperrt.

Weitere nominal ROM-nahe XML-Namen (nur andere Geraetefamilien):
- `ChecksummeROMBerechnet~0x08F0` / `Virtual_READ` (Pruefsumme)
- `NRF_ChecksummeROMLinker~0x08F4` / `Virtual_READ` (hinterlegte Pruefsumme)
- `HO2B_LAN_Card_Firmware~0xD069` / `Virtual_READ` bei `0xD084` (Versionsinformationen).
Keines ist eine Funktion zum Auslesen von Programmcode oder hiermit als `20C2`-Adresse qualifiziert.

## 2a. Archivierter VitoSoft-CIL-Wire-Serializer: Praefix-Mechanismus belegt

Die alte, frueher direkt aus der originalen VitoSoft-Assembly hergestellte Disassemblierung wurde in `vitosoft/kmbus-read-memory-analysis-2026-09-24.md` (Abschnitt „Host-implementation recovery“) und `vitosoft/private-archive-2026-09-23-analysis.md` dokumentiert. Die **Originaldatei** `MobileClient_vsmInterfaceCore.dll.il` / `vsmInterfaceCore.dll` steht im derzeit zugaenglichen LXC-Forschungsverzeichnis nicht direkt zur erneuten Inline-Disassemblierung bereit. Die folgenden Feststellungen stammen folglich **aus dem bereits geprueften historischen CIL-Bericht**, nicht aus einer im aktuellen Arbeitsschritt erneut geoeffneten DLL:

- `EventType.FCRead -> MRKey.FunctionCode -> LDAPMessage.FunctionCode`, und `EventType.Address -> LDAPMessage.Address` sowie `EventType.BlockLength -> LDAPMessage.DataLength`.
- `LDAPMessage.toByteArray()` schreibt den normalen Nutzinhalt als `00 FCT ADDR_H ADDR_L DATA_LENGTH [DATA...]` und der DAP-Wrapper als `41 LEN 00 FCT ADDR_H ADDR_L DATA_LENGTH [DATA...] CRC`. Der Adressteil ist **zwei Byte** breit.
- `RPCConverter.IsFCReadRpc()` trifft nur auf `FCRead=0x07` zu. **Nur auf diesem Zweig** setzt `ConvertRpcToDevice_Default()` die decodierten `PrefixRead`-Bytes als `BlockDataToDevice` und ersetzt `BlockLength` durch die Prefix-Laenge.
- Gewoehnliche Non-RPC-Lese-Definitionen (z.B. `KMBUS_EEPROM_READ=0x43` mit scheinbar langem `PrefixRead`) durchlaufen diese Konvertierung **nicht**. Die rekonstruierte Standardanforderung bleibt deshalb ein **16-Bit**-Request ohne den im Katalog stehenden langen Praefix.
- Die fruehere Quelltext- und Call-Site-Auswertung fand keinen versteckten Non-RPC-Prefix-Lesecaller oder zweiten Serializer in den damaligen ServiceTool-Managed-Assemblies. Nicht gefundene private OEM-Monitore koennen dadurch logisch nicht ausgeschlossen werden.

**Konsequenz:** Die heute gefundenen `0xA095`-RPC-Praefixe belegen einen echten Host-Nutzdatentransport fuer M-Bus-Datenheader, **nicht** die Semantik einer 20-Bit-Flash-Leseanforderung fuer die WB2A. Das naechste belastbare Beweisstueck muesste eine zusaetzliche **20C2-spezifische OEM-Bytefolge oder einen bestaetigten MCU-seitigen Copy-/Monitor-Handler** sein.

## 3. Uebrige Artefakte (statische Triage, keine Ausfuehrung)

- `openv.wiki/files/vMon.jar`: 920 Java-Klassen, davon nur 3 projekt-spezifische `vMon/...`-Klassen. Der eingebettete Einstiegspunkt `vMon.Vmonitor` nennt Telnet/vcontrold-Remote-IP und OpenHAB-REST als Ausfuehrungsparameter. Das ist **kein Nachweis** eines MCU-ROM-Readers trotz des missverstaendlichen Namens `Vmonitor`.
- `openv.wiki/files/Viess-ion.exe` und `gwg-artifacts/vitotest-audit/VitoTest_V1.8/VitoTest.exe`: ein begrenzter statischer ASCII-/UTF-16-Stringfilter lieferte keine einschlaegigen ROM-/Firmware-Monitor-Bezeichner. Ein Stringfilter schliesst obfuskierten/undokumentierten Maschinencode **nicht** aus.
- KarlKochs OpenV-KM-Bus-Seite (2010) behauptet plausibel einen Optolink-Firmware-Readout fuer **Vitotronic 200 KW2 / M30612MC**, aber ohne ueberlieferte Bytefolge und fuer eine andere MCU/Reglerfamilie. Referenz: https://github.com/openv/openv/wiki/KM-Bus. Nicht ungeprueft auf `VDensHO1/20C2` uebertragen.

## 4. Experimenteller Entscheid

**Kein Live-ROM-Read ausgeloest:** Alle identifizierten Extended-Prefix-RPCs sind semantisch einer anderen Geraetefamilie zugeordnet, die `20C2`-RPCs sind Teilnehmerlisten-/Resetfunktionen. Ein `FC07`-Aufruf auf unbewiesene Adressen wuerde weder einen 20-Bit-Transfer nachweisen noch das Heizgeraet risikoarm halten.

Weiter nur Optolink:

1. Einen **authentischen 20C2-spezifischen** Anwendungs-/ROM-Monitor oder vollstaendige alte M30612-Readout-Bytefolge in originalen Traegerdateien/Traces sichern. **Nicht** nur indirekte Port-/Protokollfunktionen erraten.
2. Einen gefundenen Request offline auf seine gesendeten Bytefelder, Seitenselektion und die Reaktion des echten FC03-RAM-Scratch bei `0x192C..0x1952` modellieren.
3. Erst bei einer belegten Leseoperation: ein begrenztes einzelnes ROM-Wort, mindestens zweimal konsistent, gegen zeitvariante `0x5497/0x5498`-Servicewerte abgrenzen. Unabhaengiger Host-Restore, Target-ID- und Fehlerstatus-Guards bleiben Pflicht.
4. Danach P300-Dumper und UART1/Vitotrol-RX-Codeanalyse fortsetzen.

**Regression:** Acht neue gezielte Tests fuer echte Original-XML-Hash, Praefixlaenge, Zuordnung, falsche 20-Bit-Funde und falsch gepaarte Device-Profile. **664 Testfaelle, davon 662 bestanden und 2 optionale uebersprungen**. Die produktiven `main`-/LXC-Splitterdateien bleiben unveraendert; RPM-Logger bleibt aktiv, keine neuen Controller-Schreibzugriffe, PR #52 bleibt Draft.
