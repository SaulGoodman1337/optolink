# WB2A/20C2 Optolink-ROM-Forschung: originaler Viessmann-VitoSoft-Hostcode und belegte Grenzen von VS1, LDAP, RDAP und 0xA400

**Datum:** 12. Oktober 2026. **Projekt:** echtes M16C-WB2A-/GG1-Programm-ROM über die vorhandene Optolink-Schnittstelle gewinnen; anschließend UART1/KM-Bus-Parser zur Vitotrol-200/300-Emulation rekonstruieren.

**Höchstrangiger neuer Quellenfund:** Die offiziellen **Viessmann VitoSoft 300 SID1** Windows-Installationsdateien sind am **12.10.2026 weiterhin direkt beim Hersteller abrufbar**. Bisherige Analysen hatten den alten Hersteller-XML-Katalog und historische Drittanbieter-Werkzeuge, nicht die originale Viessmann-Host-Kommunikationsbibliothek selbst ausgewertet. Die nun extrahierten, per SHA256 originalgesicherten .NET-Assemblies erlauben unmittelbare Prüfung der tatsächlichen CLR-Feldtypen, Methodensignaturen, Serialisierer und RPC-Transformationen.

Dies ist **Host-PC-Code**, **keine aus der WB2A gelesene Heizgeräte-Firmware**. OEM-Herkunft allein beweist keine spezifische Unterstützung von `VDensHO1/20C2`.

## 1. Originalquelle und strikte Provenienz

Offizielle Herstellerseite: [Viessmann Connectivity – VitoSoft](https://connectivity.viessmann-climatesolutions.com/de/mp-fp/vitosoft.html). Direkt dort verlinkter Original-Download:

```text
https://connectivity.viessmann-climatesolutions.com/content/dam/public-micro/connectivity/vitosoft/de/Vitosoft300SID1_Setup.exe/_jcr_content/renditions/original.media_file.download_attachment.file/Vitosoft300SID1_Setup.exe
```

| Artefakt | Größe | Original-SHA256 |
|---|---:|---|
| `Vitosoft300SID1_Setup.exe` | **425.114.319 Bytes** | `d02434e002369fc0d30adf45285fd6878ab978dea4e3d1310933e93bc0492116` |
| `vsmInterfaceCore.dll` aus `data/OFFLINE/3C8BB38F/CEE8DEB9/` | **368.640 Bytes** | `1653fa1346bd37b3e599cdf55fe8eb053d985f8efb8a007c18b94996a575f90d` |
| `MobileClient.exe` aus demselben Satz | **2.196.992 Bytes** | `f05e8ceef23eb94eaef0dca9c25ecbdd0fc83ae4e859d0fc7740f5bc78fd6136` |
| `vsmCommunicationInterface.dll` | 10.752 Bytes | `5514f4320f535f45db46c44a9d59d43c900b5bd2dd2e96362064df998ca6a83d` |

Die Datei war am 12.10.2026 über HTTP 200 erreichbar (Header `Last-Modified: 28 Nov 2025`). Ein Header-/Builddatum ist **nicht** automatisch die Produktversionsnummer. Die alten dokumentierten `update.vitosoft.de`-Links antworteten HTTP 525; die alte `update-vitosoft.viessmann.com`-Domain war nicht auflösbar.

Das Windows-EXE enthält ein ohne Ausführen lesbares **7z-Archiv** mit **7.651 Pfadeinträgen**, ca. 3,24 GB logischer unkomprimierter Dateigröße, überwiegend Hilfs-/Sprachdateien. Die beiden OEM-Runtime-Unterverzeichnisse wurden mit aus Debian-`7zip` ausschließlich **privat entpacktem** 7z-Binary extrahiert: **96 Dateien** mit den eigentlichen Host-Kommunikationsmodulen. Installer, MSI-Dateien, Windows-EXEs und DLLs wurden **niemals gestartet oder installiert**. Die privaten Originale und statischen IL-Auszüge liegen außerhalb des Git-Checkouts:

```text
/home/chatgpt-admin/research/vitosoft-oem-original-20261012/
/tmp/vitosoft-oem-2025-selected-real-IL-20261012.txt
/tmp/wb2a-vitosoft-oem-rom-wire-audit-20261012.json
```

Der Archivinhalts-Pathcheck fand **keine** benannten `firmware`, `bootloader`, `rom`, `*.hex` oder `*.s19`-Dateien. Das ist **nur eine Dateinamenanalyse**, kein positiver Ausschluss versteckter/anders benannter Firmwarebytes.

Zum statischen Interpretieren der CLR-Strukturen wurden in einem **privaten, nicht-systemweiten** Python-Verzeichnis die original SHA-geprüften Pure-Python-Wheels `dnfile 0.18.0` (`7579fe2d...`), `dncil 1.0.2` (`69d389e9...`) und `pefile 2024.8.26` (`76f8b485...`) abgelegt. Keine externe Host-/Controlleranwendung wurde ausgeführt und keine produktiven Python-Pakete geändert.

## 2. Vollständige CLR-Metadateninventur und gezielter Bytecodeaudit

Original `vsmInterfaceCore.dll`: **206 TypeDefs**, **2.571 MethodDefs**. Der Offline-Auditor `tools/wb2a-vitosoft-oem-rom-wire-audit.py` hat die **2.490 tatsächlichen IL-Methodenkörper** ohne Fehler decodiert, für acht kritische Methoden zusätzlich **deren vollständige Methodenkörper SHA256-gepinnt** und die relevanten FieldDef- und MethodRef-Tokens unabhängig nach Namen und Signatur aufgelöst. Es werden **keine** Bytes nach einem Methodenende als Code des vorherigen Methodenrumpfs mitgezählt.

Die markanten originalen Methodenkörper:

| Klasse/Methode | OEM-RVA | Tatsächlicher Befund |
|---|---|---|
| `VS1Message.toByteArray` | `0x20AC` | Opcode-Verzweigungen für `0x68/0x6B/0x78/0x7B/0xF4/0xF7`. Immer **Command + AddressHigh + AddressLow + Length**, optional Nutzdaten |
| `VS1Message.getVS1MessageFromLDAPMessage` | `0x21DC` | LDAP-Daten auf dieselben VS1-Zweibyte-Adressfelder umgesetzt |
| `LDAPMessage.toByteArray` | `0xA2FC` | `ADDRHighByte` + `ADDRLowByte` + **ein** `DataLength`-Byte, danach optionales `Data` |
| `RDAPMessage.toByteArray` | `0xA408` | Routingflag, variabel langes `FieldBusAddress: byte[]`, anschließend geroutete Message-Liste |
| `RPCConverter.ConvertReadRequestToDevice` | `0xC598` | **2.059 IL-Codebytes** umfassende Host-RPC-/Konvertierungsverzweigung; kein daraus belegter freier 20-Bit-ROM-Reader |
| `RPCConverter.ConvertRpcToDevice_VitosorpAccessController` | **`0xF814`** | Expliziter `0xA400`-Leseproxy und `0xA401`-Schreibproxy, **`Int16`-Adresse** per `BitConverter.GetBytes(Int16)` |
| `RPCConverter.ConvertRpcFromDevice_VitosorpAccessController` | `0xF778` | Hostseitige Kontrolle einer spezifischen Sechsbyteantwort; keine 20-Bit-Quelle bewiesen |

Das komplette Audit listet die SHA256-Hashes der acht Originalmethodenkörper, nicht den OEM-Bytecode selbst. Die Rechte/urheberrechtliche Herkunft des Herstellerprogramms bleiben gewahrt.

## 3. Wichtigster positiver Originalcodebeweis: `A400/A401` benutzt **Int16**

Der jetzt originale `ConvertRpcToDevice_VitosorpAccessController`-IL-Rumpf (`218` IL-Codebytes, RVA `0xF814`, SHA256 **`d5ff9521de8db164b8ed94f25ae569da9400d3ded18ecc5c4669705a1432c416`**) enthält eine Lese- und eine Schreibverzweigung:

- **Lese-RPC:** setzt wörtlich `0xA400` (dezimal 41984), ruft `Request.get_Address` (MethodDef `0x060000E7`, Signatur `instance Int16`) auf und wandelt den Wert mit `BitConverter.GetBytes(Int16)` (MemberRef `0x0A0000F9`) in **genau 2 Bytes**. Die drei Proxy-Payloadbytes bestehen aus vertauschter Zieladresse High/Low und einem `BlockLength`-Byte.
- **Schreib-RPC:** setzt wörtlich `0xA401` (41985) und bildet ebenfalls den Zwei-Byte-Zieladressprefix; hinter ihm stehen die Nutzdaten. Der vorhandene OEM-Schreib-RPC ist hier **nur analysiert, nicht benutzt**.
- Die genannten MethodDef-/MemberRef-Signaturen wurden aus **der realen .NET-Metadatentabelle** und **den echten IL-`call`-Tokens** ausgewertet. Ein geratenes `A400`-Bytefeld oder Strings-Suche wäre weniger aussagekräftig.

**Ergebnis:** `0xA400` ist ein belegter OEM-Host-Transportproxy, aber dieser ursprüngliche Viessmann-Aufruf übermittelt gerade **keine 20-Bit-Quelladresse**. Ein weiteres blindes Wiederholen von `0xA400` gegen die WB2A ist nicht sinnvoll. Eine nicht dokumentierte Controllerbank, die durch andere Kommandos selektiert wird, ist dadurch nicht logisch ausgeschlossen.

## 4. Die interessante `RDAP.AddressLength`-Falle ist aufgelöst

In `vsmInterfaceCore.protocols.RDAPMessage` existieren tatsächlich:

```text
RoutingFlag       FieldDef 0x04000146
AddressIdentifier FieldDef 0x04000147
AddressLength     FieldDef 0x04000148 : Byte
FieldBusAddress   FieldDef 0x04000149 : Byte[]
MessageList       FieldDef 0x0400014B : Message[]
```

Diese `FieldBusAddress` ist eine *variable Feldbus-Routingadresse*, **kein Zielregister der M16C-CPU**. Ein Bytearray mit potenziell mehr als zwei Bytes ist **allein kein ROM-20-Bit-Beweis**.

Besonders wichtig: Die vollständige Analyse der **2.490 tatsächlich decodierten IL-Methodenkörper** fand Verwendungen der `AddressLength`-/`FieldBusAddress`-Feldtoken **ausschließlich** in `RDAPMessage..ctor` und `RDAPMessage.toByteArray`. Weder `RPCConverter` noch ein sonstiger Host-RPC-Handler greifen direkt auf diese RDAP-Felder zu. Die inneren **LDAPMessage-Adressfelder sind getrennt** und bestehen weiterhin aus `ADDRHighByte` und `ADDRLowByte`.

Der Sender `DAPProtocol.createVS2RDAPTelegram` (RVA `0xA04C`) umhüllt lediglich die bereits gepackte `RDAPMessage` als VS2/Protokolltelegramm. Die transportierte *Routingadresse* darf nicht mit einem freigegebenen *CPU-ROM-Quellpointer* verwechselt werden.

## 5. Gegenprobe gegen die echte 20-Bit-Lücke

Die reine Python-Testabbildung von zwei LDAP-/VS1-Adressbytes plus einem Längenbyte (8) ergibt:

| Gedachte M16C-Adresse | Auf dem Host abbildbare Speicheradresse |
|---|---|
| `0x00000` | `0x0000` |
| **`0xE0000`** | **`0x0000`** |
| **`0xF23FF`** | **`0x23FF`** |
| **`0xFFFFF`** | **`0xFFFF`** |

Auch das Originalprogramm von 2010/2011 (vorheriger Bericht `wb2a-optolinklogger-2010-2011-cli-rom-gate-2026-10-12.md`) benutzte diesen Adressraum. Die OEM-Bibliothek bestätigt die Zwei-Byte-Grenze zusätzlich an zwei unabhängigen Formaten und an einem expliziten RPC.

**Negativer Beweisumfang:** Für **die genau untersuchten Standard-VS1-/LDAP-Lesetelegramme**, **RDAP-Routing-Semantik** und **VitosorpAccessController-`A400/A401`** gibt es **keinen nachgewiesenen ROM-Leseweg**.

**NICHT bewiesen:** Dass der OEM-Binärsatz insgesamt keinerlei andere Firmwaremonitore, gerätespezifische Sonderpayloads oder versteckte Zustandsschalter enthält. Ebenso nicht, dass der angezeigte VitoSoft-Build genau zur eigenen `20C2/0103`-MCU passt oder dass die ältere `M30612MC/2098`-Auslesung von KarlKoch 2010 widerlegt wäre.

## 6. Praktischer weiterer Weg ohne Zeitverlust durch Adress-Aliase

1. **Offline weiter rückverfolgen:** `RPCConverter.ConvertReadRequestToDevice` (2059 IL-Bytes), `RequestCreator.CreateRPC_ReadBlockRequest` (zwei überladene Methoden) und die tatsächlichen Request-Gruppen gegen die VitoSoft-Geräteprofile `VDensHO1` verknüpfen. Danach nur konkrete, für `20C2` profilegebundene **20-Bit-/Bank-/ROM-Copy-Services** als Livekandidaten zulassen. Kein generisches `RDAP` als mutmaßlichen ROM-Zugang deklarieren.
2. **Historischer Alternativnachweis:** echte Optolink-Transferbytes/Originaltools des KarlKoch-M30612MC-Dumps, historische Firmwarelieferungen oder ein nachweislich eigener WB2A-Programm-ROM-Dump. Ein Name „Memory“/„ReadBlock“ genügt nicht.
3. **Nur bei positivem Interfacebeleg**: kleines an oberen M16C-ROM-Adressen gerichtetes zweifaches Leseexperiment mit Daten-/Vektorplausibilität, vorher/nachher komplette Fehlerhistorie und unabhängige Rückstellung. Keine unbekannten CPU-Registerwrites am aktiv laufenden Gasgerät.

**Aktueller Hardwarestatus:** In dieser OEM-Studie **null neue Optolink-Anfragen**, **null neue Controller-Writes**, **kein Brenner-/Pumpen-/Protokollwechsel**. Die bei der Vorläuferstudie dokumentierten C5/F9-Vorfälle werden durch das OEM-Ergebnis weder bestätigt noch erklärt. Die Installationsdatei wird ausschließlich als nicht ausführbarer Quellenbeleg vorgehalten.

## 7. Vollständig reproduzierbarer Originalaudit

```bash
cd /home/chatgpt-admin/optolink-vitotrol-rpm-20261010

# Originaldateien und private Pure-Python-Parser liegen separat unter
# /home/chatgpt-admin/research/vitosoft-oem-original-20261012/
python3 tools/wb2a-vitosoft-oem-rom-wire-audit.py \
  --out /tmp/wb2a-vitosoft-oem-rom-wire-audit-20261012.json

python3 -m unittest discover -s tests \
  -p 'test_wb2a_vitosoft_oem_rom_wire_audit.py' -v

# Regression aller vorhandenen Forschungsfunktionen ohne neue Hardwareproben
python3 -m unittest discover -s tests -q

# Git-Dry-Run, keine Übernahme
python3 tools/wb2a-research-branch-transfer-preview.py \
  --out /tmp/wb2a-vitosoft-oem-research-transfer-preview-20261012.json
```

Die CI-Regression ohne private OEM-Dateien überspringt nur den Volloriginal-Audit als optionalen Test, besteht aber alle synthetischen Negativtests. Die bereits auf dem LXC vorhandenen Originalbytes ermöglichen eine echte SHA-verifizierte Quellenabnahme. **Original-OEM-EXEs und DLLs werden nicht in das Git-Repository kopiert**.

**Forschungsgit:** nur `feat/wb2a-vitotrol-rpm-20261010` / Draft-PR #52; spätere selektive Übernahme nach `optolink-research`. `main` und produktiver Optolink-Splitter bleiben unverändert.
