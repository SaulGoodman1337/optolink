# WB2A/VDensHO1 20C2: ROM-Dump-Priorität – Original-VitoSoft native GWG-Implementierung und 20-Bit-IL-Audit

**12. Oktober 2026.** **Ziel:** echte Programm-ROM-Bytes des eigenen WB2A/20C2/0103-Mikrocontrollers **über den bereits vorhandenen Optolink-UART0-Anschluss** auslesen, ohne Kesselfunktionen anzuhalten, umzuprogrammieren oder mit fraglichen SFR-/DMA-Writes zu manipulieren. Vitotrol-Emulation und RPM-Auswertung sind nachgeordnet. Dieses Dokument liegt im bestehenden `optolink-research`-Branch des vorhandenen Repositories; kein neuer Branch oder Herstellercode-Commit.

## 1. Schon nachgewiesen – nicht erneut probieren

- GWG wurde **bereits am eigenen Gerät getestet**: Der historische Fünfbyte-Request `01 C7 F8 04 04` lieferte die richtige `20 C2 00 03`-Kennung. Alte `CB`- und `C5`-Requests an `0x6F`/`0xF8` lieferten keine Antwort; `6E 01 01` lieferte `00`; `AE 17 02` lieferte keine Antwort. Das beweist GWG-Kompatibilität für eine *konkrete* virtuelle Leseart, nicht allgemeinen EEPROM-/ROM-Zugriff. Bestehende Originalnachweise im anderen Feature-Branch dokumentiert, z. B. `wb2a-v200kw2-legacy-gwg-live-compatibility-2026-10-12.md`, `wb2a-gwg-c7-dispatcher-live-2026-10-12.md` und `wb2a-gwg-legacy-readtypes-live-2026-10-12.md`.
- Die vorhandene P300/VS1-Transportabfrage trägt **zwei Adressbytes**; historische GWG-Lesetelegramme **ein Adressbyte**. Damit kann ein direktes `Physical_READ 0xF000` eine hypothetische Program-ROM-Quelle bei `0xF0000` nicht ausdrücken. Frühere High-16bit-Reads lieferten nicht konstante bzw. wiederholte `54xx`-Wörter, **keinen M16C-Programmcode**.
- Die beiden real verwendeten 20-Bit-DMA-Kanäle treiben Optolink/UART0 und KM-Bus/UART1. Ihre bloße Fähigkeit, auf ROM zuzugreifen, ist noch **kein** optolinkseitiger Kopierdienst. Ein Eingriff kann den einzigen Rückstellkanal verlieren lassen.
- OpenV-KarlKochs **historische** Oktober-2010-Aussage über rund 128 KiB eines `M30612MC` auf **Vitotronic 200KW2/2098** und rund 57.000 Disassembly-Zeilen wurde bereits in den ursprünglichen Wiki-Historydaten verifiziert. Es gibt dazu im bekannten Archiv weiterhin **keinen originalen übertragbaren 20-Bit-Wire-Trace oder ROM-Dump**. Eine andere Kessel-/CPU-Generation ist kein Nachweis für das eigene `20C2/0103`.
- Ein gewöhnlicher Renesas-M16C-**Hardware**-Bootloader benötigt zusätzliche Boot-/Reset-Beschaltung und andere UART-Leitungen als der normale Optolink-Weg. Kein Versuch am aktiven Gasheizgerät.

## 2. Neue unabhängige OEM-Originalquelle, jetzt erstmals bis zum Maschinenbefehl untersucht

Am 12.10.2026 von der Viessmann-Herstellerseite privat bezogener **unveränderter** `Vitosoft300SID1_Setup.exe`-Installer: **425.114.319 Bytes**, SHA256
`d02434e002369fc0d30adf45285fd6878ab978dea4e3d1310933e93bc0492116`. Original-Download:

```text
https://connectivity.viessmann-climatesolutions.com/content/dam/public-micro/connectivity/vitosoft/de/Vitosoft300SID1_Setup.exe/_jcr_content/renditions/original.media_file.download_attachment.file/Vitosoft300SID1_Setup.exe
```

Der Installer wurde **nur mit 7z als Datenarchiv gelesen und teilweise entpackt**, nicht gestartet. In der Original-Runtime `data/OFFLINE/3C8BB38F/CEE8DEB9` liegen:

| Originaldatei | Größe | SHA256 |
|---|---:|---|
| `vsmGWG99Native.dll` | 431.104 Bytes | `b4c0f19d56d8e4b9ece830dc8ab78194debaee67480472bbf94fec0eb1d7f4a2` |
| `vsmInterfaceCore.dll` | 368.640 Bytes | `1653fa1346bd37b3e599cdf55fe8eb053d985f8efb8a007c18b94996a575f90d` |

**Konkreter nativer Maschinen-Code-Befund**: Die originale native x64-`vsmGWG99Native.dll` exportiert ausschließlich `CheckGWG` (RVA `0x1080`) und `TestCall_GWG99Native` (RVA `0x1040`). Unter `CheckGWG` wird das Optolink-`0x05`-Start-/Antwortfenster verwendet. Die aufgerufene Send-Hilfsroutine schreibt eine 3-Byte-Nutzlast an den Windows-COM-Port. Bei RVA `0x1683/0x1688/0x168D` wird diese Nutzlast als **`C7 F8 04`** erzeugt, wobei `F8` eine **8-Bit-Datenpunktadresse**, `04` die Leselänge ist. Achtung: **nicht** gleichsetzen mit dem separaten von OpenV dokumentierten vollständigen Fünfbyte-Frame `01 C7 F8 04 04`; die beiden Reader benutzen verschiedene Host-Framings. Die realen `CheckGWG`-Bytes werden zuerst als drei Byte bei RVA `0x169C` zum internen Send-Wrapper (`0x15B0`) übergeben; dieser ruft Win32 `WriteFile` auf.

Nach dem Lesen prüft `CheckGWG` an RVA `0x1205` auf Antwortbyte0 `20`, Antwortbyte1 `53` **oder** `54`. Es erkennt damit die historischen Typkennungen **`2053` und `2054`**, *nicht* die WB2A-Gerätekennung `20C2`. **Dieser originale OEM-Nativeinstieg ist ein Gerätekennungsdetektor, kein Firmware-ROM-Dumper.** Das schließt nicht kategorisch andere private native interne Routinen oder unbekannte Controllerdienste aus.

**Reproduktionswerkzeug** `tools/wb2a-oem-native-gwg-rom-gate.py` prüft Dateigrößen + SHA256 beider Original-DLLs, die exakten PE-RVA-Bytefolgen, die tatsächlich exportierten Namen und die CLR-Binärmetadaten. Die Bytefolgen wurden vor der Implementierung durch `objdump -d` und `pefile` auf dem unveränderten DLL gegengeprüft.

## 3. Neues strukturelles Full-IL-Gate: echte 32-Bit-Serializer statt verführerischer Funktionsnamen

Die originale `vsmInterfaceCore.dll` umfasst **206 CLR-Typen**, **2571 MethodDefs** und **2490 verifizierbar decodierbare echte IL-Methodenkörper**. Der Auditor hat *sämtliche 2490* mit privaten `dnfile`/`dncil`-Parsern analysiert und jeweils echte CLR-Instruktionsgrenzen verwendet, nicht angrenzende Codebytes als Treffer gewertet.

| Indikator | Originalbefund |
|---|---|
| `BitConverter.GetBytes(Int32)` (MemberRef `0x0A0000E7`, Signatur `00011d0508`) | **Exakt 2 Call-Sites**: `ConvertRpcToDevice_RPCSetImpulseCounter_IO_EM_DE` und `ConvertRpcToDevice_RPCSetGrenzwertLONKanalAlarm`; keine namentlich adressierte ROM-Leseroutine |
| `BitConverter.GetBytes(Int16)` (MemberRef `0x0A0000F9`, `00011d0507`) | Vorhanden u. a. in `VitosorpAccessController`-RPC `0xA400/0xA401`; **16-Bit-Sekundäradresse** |
| `ldc.i4 16/24` unmittelbar vor `shl/shr/shr.un` | **0** in 2490 Bodies |
| Immediate-Konstanten im hypothetischen ROM-Bereich `0xC0000..0xFFFFF` | **1**: Dezimal-`999999` = `0xF423F`, und zwar in `SerialPortValidator.DoWork`. Keine belegte Code-/ROM-Adresse |
| Feldbus-`RDAP.AddressLength` / `FieldBusAddress` | Variable **Feldbus-Routingadresse**, kein bewiesener M16C-Programmpointer |
| **ROM-Dump über OEM-Lesepfad** | **0 Bytes** |

Zusätzlicher Metadatenscan der **28 eigenständigen Viessmann/ecn/vsm-/MobileClient-/FlowCalibration-.NET/-Native-Binaries** zeigte **keine** passend benannten `ROMRead`, `FlashRead`, `Bootloader`, `FirmwareUpload`, `MemoryDump` oder `ProgramROM`-Klassen/Methoden. Ein reiner Methodennamenscan ist ausdrücklich **kein** Ausschluss eines undokumentierten Calls im Maschinencode.

**Aussagegrenze:** Diese Negativbefunde gelten für **die genau geprüften OEM-PC-Binärdateien, deren sichtbare Formate und die konkreten IL-Muster**. Es kann einen undokumentierten Firmwaremonitor mit anderem Namen, sequentieller Bankauswahl, verschleiertem Service oder völlig anderer PC-Clientimplementierung geben. Die Firmware der eigenen WB2A wurde durch diese Studie **nicht** ausgelesen.

## 4. Sicherheit, lokaler Projektstatus und reproduzierbare Tests

- **Kein** optischer Live-Protokollwechsel, keine neuen Diagnose-Reads/Writes, kein Reset/Flash/EEPROM-/DMA-/UART-Register-Schreiben, kein Splitter-/Serviceeingriff. Die zwei OEM-Binärmodule wurden nie unter Windows ausgeführt.
- Alle privaten Original-EXE/DLL/Wheel-Artefakte ausschließlich unter `/home/chatgpt-admin/research/vitosoft-oem-original-20261012/`, **nicht auf GitHub hochladen**.
- Das Research-Repository des Nutzers wird **nur im bereits bestehenden `optolink-research`-Branch** ergänzt; `main`, bestehender Feature-PR #52 und die produktive Installation `/opt/optolink` bleiben unberührt.

```bash
cd /home/chatgpt-admin/optolink-wb2a-research-20261010
python3 tools/wb2a-oem-native-gwg-rom-gate.py \
  --out /tmp/wb2a-native-oem-20bit-rom-gate-20261012.json
python3 -m unittest discover -s tests -p 'test_wb2a_oem_native_gwg_rom_gate.py' -v
python3 -m unittest discover -s tests -q
```

**17 Tests** mit positiven Originalnachweisen und adversarialen Fälschungen (falscher C7-Opcode, falscher Produkt-ID-Vergleich, längeres Sendframe, erdachter ROM-Export, neuer 20-Bit-Shift, neuer `GetBytes(Int32)`-Call-Site, gefälschter ROM-Literal-Treffer, manipulierte Datei) sichern die Schlussfolgerung gegen versehentliche Umdeutung ab. Optionaler echter Originalaudit überspringt sich in GitHub-CI nur dann, wenn die privaten Viessmann-Binärbytes dort fehlen.

## 5. Nächster ROM-Dump-Schritt / harte Entscheidung

**NICHT** erneut die bereits falsifizierten 8/16-Bit-Anfragen, Prefix-Aliase, `A400`-Int16-Proxy oder die bereits getesteten GWG-CB/C5-Adressen wiederholen. Hohe Priorität hat eine **unabhängige Quelle**, die entweder (a) einen **an 20C2 verfügbaren ROM-Monitor/RPC mit 20-Bit-Quelladresse**, (b) den **sicher bankumschaltenden ROM-Page-Selector** oder (c) einen **Controller-seitig kontrollierten ROM→LowRAM-Copy-Dienst** vollständig (Kommandocode, Payload, Rückgabe, Grenzen) belegt.

Ein echter Erfolg muss **zweimal unabhängig dieselben adressierten Bytes einer plausiblen 20-Bit-M16C-Program-ROM-Region** liefern, über ein definiertes Low-RAM-/Optolink-Transportfenster unverändert zurücktransportiert werden, sich von vorhandenen `54xx`-Bus-/SRAM-Kandidaten unterscheiden und die M16C-Code-/Vektorplausibilität erfüllen. **Erst dann** Segmentdump samt mehrfachen Hash-/Sektorvergleich durchführen. Ohne diesen Quellenbeweis würde ein erneuter aktiver Gasheizungsversuch nur die bereits dokumentierten Fault-/Kommunikationsrisiken reproduzieren.

**Unverändert offene Kernfrage:** Ein funktionierender **20-Bit-ROM-Quelladressierungsdienst** am *existierenden Optolink-UART0* des *eigenen* WB2A/20C2. **Aktueller ROM-Dump: 0 Byte.**
