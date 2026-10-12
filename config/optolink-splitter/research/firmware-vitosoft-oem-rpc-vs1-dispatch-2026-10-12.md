# WB2A/20C2: Original-VitoSoft-IL – Befehlsdispatcher, parametrierte RPCs und spätere GFA-Blöcke

**Stand 12.10.2026. Priorität 1: Programm-ROM der realen WB2A/VDensHO1/20C2/0103 über das bereits vorhandene Optolink auslesen.** Hier erfolgt eine neue, konkret quellverifizierte Untersuchung von **GWG, V1/VS1 und P300** sowie älteren und neueren Viessmann-Hostprofilen. Diese Etappe arbeitet **ausschließlich auf vorhandenen Binärdateien und XML-Katalogen**; die reale Gasregelung wurde **nicht** abgefragt oder verändert.

## 1. Originalquellen, Prüfsummen und Methodenbeweis

Quelle ist der bereits privat archivierte originale Viessmann-`Vitosoft300SID1_Setup.exe`-Installer. Er wurde **nicht ausgeführt**; nur bereits zuvor extrahierte Bibliotheksdateien wurden als Daten gelesen.

| Private Originaldatei | Länge | SHA256 |
|---|---:|---|
| `vsmInterfaceCore.dll` | 368.640 | `1653fa1346bd37b3e599cdf55fe8eb053d985f8efb8a007c18b94996a575f90d` |
| `vsmInterfaceCommon.dll` | 81.920 | `ac47b8ede5c4fc7e66eccf1d7f8b32c9c0c186093c7e5a49787a208675f5cb7f` |
| `DPDefinitions.xml` | 186.559.004 | `efec27568d398021c767771af016143bd51fc196d2d408dbb80faff84d0b19e3` |
| `ecnEventType.xml` | 9.935.374 | `2338beb0e8544b6149bc4b2433ecabd9509edcdafc2e8e91f00182eba1aff7ba` |

Der Auditor `tools/wb2a-vitosoft-rpc-dispatch-provenance-offline.py` attestiert **vier ganze Quelldateien per SHA256**; anschließend parst er mit lokal bereits installierten `dnfile`/`dncil` ausschließlich die **14 eindeutig identifizierten CLR-MethodDefs** und prüft deren **vollständige rohe IL-Methodenkörper** gegen 14 fixierte SHA256-Werte. Anders als einfache Byte-Grep-Treffer verifiziert er echte CLR-Befehlsgrenzen, Sprungziele, konkrete Aufruf-Token, Feld-Token, beide OEM-Enums und den vollständigen `ecnDatapointType`→`ecnDataPointTypeEventTypeLink`→`ecnEventType`-Join. Der Auditor bewertet **nur** diesen belegten PC-seitigen Pfad, nicht sämtliche undokumentierten MCU-Routinen.

## 2. Tatsächliche Funktionscode-Übersetzung

Die echte IL-Methode `VS1Message.getVS1MessageFromLDAPMessage` (MethodDef **`0x0600000D`**, SHA256 **`13c77176913b37f33b1ba2ab2e386192f33172df1db394e7d0cecc1dc7d0e6c7`**) enthält genau folgende **sechs belegten** internen Funktionscodes, deren Zweige jeweils die VS1-Befehlsbytes erzeugen:

| Intern in VitoSoft | Echte VS1-Ausgabe | Funktion |
|---:|---|---|
| `1` | `F7` | Virtual Read |
| `2` | `F4` | Virtual Write |
| `201` | `6B` | GFA Read |
| `202` | `68` | GFA Write |
| `123` | `7B` | Prozess Read |
| `120` | `78` | Prozess Write |

Beide originalen `vsmInterfaceCommon.dll`-Enums `FunctionCodes` und `VS1FunctionCode` bestätigen diese Konstanten **unabhängig von der Disassembly**. Intern gibt es auch `Remote_Procedure_Call=7` und `KMBUS_EEPROM_READ=67`; der konkret geprüfte OEM-`LDAP→VS1`-Konverter emittiert **keinen generischen VS1-RPC-7-Opcode**. Es ist falsch, daraus abzuleiten, der Controller kenne niemals andere private Dienste oder alte GWG-Kommandos: Die historischen `C7`-/`6E`-20C2-Messungen sind eigenständige Protokollspuren.

## 3. Originaler Dispatcher bis zum Optolink-Sender

Die belegten CLR-Call-Sites und Datenfelder ergeben folgende PC-seitige Kette:

```text
VitoSoft EventType (profilgebundene FCRead, Adresse, Länge, PrefixRead)
   |
   v
RequestCreator.CreateReadRequest
   |-- GetRequestIdentGroup: FC=7 → RPC- bzw. RPC-Block-Sonderpfad
   |-- RPCConverter.ConvertToDevice: kennt PrefixRead-Umwandlung
   v
MultiRequestDictionary.createMultiRequest
   |-- EventType.Address: 16-Bit-Adresse (conv.u2)
   |-- EventType.BlockLength: Byte (conv.u1)
   v
LDAPMessage.toByteArray
   |-- interner Funktionscode + zwei Adressbytes + Länge + ggf. Nutzdaten
   v
VSManager.sendLDAP
   |-- aktives VS1: getVS1MessageFromLDAPMessage → VS1.sendMessageAsynch
   '-- aktives VS2/P300: VS2.sendLDAP → DAPProtocol.createVS2LDAPTelegram
```

Die MethodDefs `0x06000671`, `0x06000672`, `0x06000358`, `0x060001F6`, `0x06000086`, `0x06000020` und `0x0600004D` sind einzeln anhand echter IL-Hashes und konkreter Aufruf-Token geprüft. **Der untersuchte Standardweg ist kein 20-Bit-ROM-Adressierer:** seine normalen Adressfelder sind 16 Bit und die `MultiRequest`-Bildung verkleinert die Adresse sogar ausdrücklich auf `conv.u2`.

**Wichtig:** `RPCConverter.ConvertRpcToDevice_Default` (MethodDef `0x06000216`) verarbeitet bei einem RPC-Read ein Host-`PrefixRead` als **gesendete Request-Nutzdatenbytes** und setzt die ausgehende Blocklänge zunächst auf die Anzahl dieser Bytes. Das ist ein **realer parametrierter Funktionsmechanismus**, aber weder eine freie ROM-Quelladresse noch der Nachweis, dass die Firmware diese Daten aus dem Programm-ROM liest. Der früher untersuchte `VitosorpAccessController`-`A400/A401`-Weg verwendet `BitConverter.GetBytes(System.Int16)`; eine dritte oder vierte Adressbytequelle wurde nicht belegt.

## 4. Echte WB2A-Host-RPC-Auswahl `0xA010` – keine ROM-Bank

Im vollständig über **399 Profile, 104.339 Links und 11.582 Eventdefinitionen** aufgelösten Originalkatalog enthält die konkrete `VDensHO1`-Familie **581 Eventtypen**, darunter:

- **462 × `Virtual_READ`**, **94 × `GFA_READ`**, **22 × `Remote_Procedure_Call`**, **3 × undefiniert**.
- **17 rein lesende RPC-Eventaliases** `Teilnehmerliste_LON_00..15~0xA010` sowie das zusätzliche `Teilnehmerliste_LON_0~0xA010`. Die **16 eindeutigen** Prefixwerte sind `00` bis `0F`; Host-Blocklänge **6 Bytes**. Die zusätzliche `_0`-Eventdefinition hat Prefix `00`, aber andere `BytePosition`.
- **Fünf weitere RPC-Einträge sind nicht eindeutig rein lesend**, darunter die *potenziell zustandsändernden* Adressen `A009` (Memberliste löschen), `A029` (Fehlerhistorie löschen), `A050` (Konfigurationsreset) und zweimal `A051` (Bedienparameterreset). **Nicht probeweise aufrufen.**
- **0** dem Profil zugewiesene `PROZESS_READ`- bzw. `KMBUS_EEPROM_READ`-Datenpunkte. In **allen** 399 Hostprofilen gehören die **30** `PROZESS_READ`-Events ausschließlich zu **`VSorp`**. Dagegen besitzt das ältere `GWG_VBEM_00` **54** `KMBUS_EEPROM_READ`-Zuordnungen.

**Vertiefung mit echtem CLR-String-/Sprungzielsvergleich:** Die Originalmethode `RPCConverter.ConvertReadRequestToDevice` (MethodDef `0x06000215`, SHA256 `ec4d3490bac635cb0116173b29abeed9deb9fff6eccb5afa29f66860e078b6ae`) enthält wörtliche `Teilnehmerliste_LON_00~0xA010` bis `_15~0xA010`-Fallunterscheidungen. Alle 16 Zweige führen zum selben Default-/Prefix-Umwandler bei IL-Offset **1589** → `ConvertRpcToDevice_Default`. Das andere Objekt `Vitocom_Neuron_ID~0xA010` führt bei IL-Offset **1580** zu **`ConvertRpcToDevice_A010_Vitocom_Neuron_ID`**. **Gleiche Hostadresse bedeutet somit nicht denselben Parameter- und Ergebnisvertrag.** Die zusätzliche WB2A-Katalogalias `Teilnehmerliste_LON_0~0xA010` wird in dieser konkreten OEM-Namenssprungtabelle **nicht** explizit aufgeführt; das ist eine Einschränkung des Host-Implementierungsbelegs, nicht der Beweis einer geheimen ROM-Funktion.

Fazit `A010`: **16 belegte LON-Teilnehmerindex-Werte, keine ROM-Seiten-, Programm-Adress- oder Präfix-CRC-Funktion.** Das derzeitige Offline-Audit autorisiert keinen Live-Request.

## 5. Interessanter Generationskontrast: neuere GFA-Kommandos tragen Blöcke

Die **94** WB2A-Host-`GFA_READ`-Events haben **alle BlockLength=1** und **64 unterschiedliche Adressen**. Dagegen besitzen zwei weitere VitoSoft-Profile `VScotHO1_200_10` und `VScotHO1_200_11` jeweils exakt **264** `GFA_READ`-Eventlinks:

| Host-BlockLength | Anzahl der Events je späterem Profil |
|---:|---:|
| 1 | 129 |
| 2 | 34 |
| 4 | 1 |
| 7 | 2 |
| **16** | **98** |

Die 98 16-Byte-Objekte sind mit `VSKO_FH_HC_*` bzw. `VSKO_FH_UC_*` bezeichnet. Achtung vor Hostnamen: `VSKO_FH_HC_01~0xA0F0` trägt als **tatsächliches `Address`-Feld `0xC0F0`**. Die Bezeichnung und die gesendete Zieladresse unterscheiden sich; beide sind hier Hostkatalogwerte und keine verifizierten M16C-ROM-Adressen.

Dies zeigt **belegtes mehrbyteiges GFA-Routing in neueren Hostprofilen**, nicht eine belegte 16-Byte-ROM-Seitenfunktion. **Eine solche Funktion auf WB2A/20C2 wurde nicht bestätigt.** Als sinnvolle spätere Quellcodefrage bleibt, ob diese neuen Blöcke von GFA-Telemetrie, Verlaufsspeichern oder tatsächlich ROM-hinterlegten Tabellen stammen. Auch die längerfristige P06/Gebläse-Forschung kann von einer präziseren GFA-Telegrammsemantik profitieren; die Firmware-Extraktion hat jedoch weiterhin Priorität.

## 6. Negative Gates, Testresultat und sinnvoller Folgeschritt

Neue Werkzeuge für diesen Forschungsstand:

```text
tools/wb2a-vitosoft-rpc-dispatch-provenance-offline.py
tests/test_wb2a_vitosoft_rpc_dispatch_provenance_offline.py
```

Offline-Originalabnahme:

```bash
cd /home/chatgpt-admin/optolink-wb2a-research-20261010
python3 tools/wb2a-vitosoft-rpc-dispatch-provenance-offline.py \
   --out /tmp/wb2a-vitosoft-rpc-dispatch-original-20261012.json
python3 -m unittest discover -s tests \
   -p 'test_wb2a_vitosoft_rpc_dispatch_provenance_offline.py' -v
python3 -m unittest discover -s tests -q
```

Zu den expliziten Negativfällen gehören geänderte OEM-SHA/Länge, falsche VS1-Opcode-Branchwerte, ein erfundener VS1-`RPC7`-Zweig, beschädigtes CLR-Token, eine manipulierte GFA-Blocklänge, ein gefälschtes ROM-Adressfeld, veränderte `A010`-Prefixwerte, falsche Profil-Links (`VSorp`→`WB2A`) und ein mit `Vitocom_Neuron_ID` vertauschtes LON-RPC-Sprungziel. Wenn die privaten Originalquellen in einer öffentlichen CI fehlen, darf **nur** die originaldatenabhängige Testsuite übersprungen werden.

**Keine neuen Controller-Reads/Writes, keine Hardwareänderungen, keine VS1-/P300-/GWG-Protokollwechsel, keine Brenner-/Pumpen-/DMA-/UART-Tests.** `main`, produktive VS1-Splitterkonfiguration und Draft-PR bleiben unberührt. Fehlersituation **C5/F9** bleibt für künftige Hardwareversuche zu berücksichtigen.

**Nächste beste Forschungsspur, nicht ein weiterer 16-Bit-Sweep:**
1. Bereits vorhandene **originale Controllerantwort-Traces** (inkl. VitoSoft-/OpenV-Altarchiv) nach **wechselbar indizierbaren, quellbelegt ROM-abhängigen** Diagnose- oder Tabellenrückgaben filtern; dabei gilt eine feste Versions-/CRC-Antwort nicht als Programmcode.
2. Für die **neueren `VSKO_FH_*`-Mehrbyteobjekte** zunächst nur die alten/neuen Datenpunkttypen und ihren *Geräte-/GFA-Auswahlmechanismus* vergleichen; keine Übertragung der neueren `C0F0`-Hostadresse auf 20C2 ohne Handlerbeleg.
3. Den 2010 historisch berichteten `M30612MC/V200KW2`-Firmwaretransfer nur dann als Vorlage verwenden, wenn **echte Request-/Responsebytes oder ein reproduzierbarer Monitor** wiedergefunden werden. Eine beliebige 20-Bit-Zahl in einem Host-Speicherpuffer reicht nicht.
4. Erst bei nachgewiesenem read-only-ROM-Inhaltsorakel inkl. Quellprovenienz einen kontrollierten, mehrfach verifizierten ROM-Segmentdump entwerfen; dazu Fehlerhistorie vor/nach sowie unabhängigen Restorepfad prüfen.

**Forschungsstatus: 0 sicher ausgelesene WB2A-Programm-ROM-Bytes. Kein neuer ROM-Dump-Dienst nachgewiesen.** Die Dispatcher- und Routingannahmen sind aber nun am OEM-Original-IL falsifizierbar dokumentiert.
