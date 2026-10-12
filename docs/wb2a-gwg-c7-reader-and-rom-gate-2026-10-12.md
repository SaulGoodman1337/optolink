# WB2A 20C2: Historische GWG-Befehle, C7-Reader und verbliebene 20-Bit-ROM-Barriere

**Forschungsstand: 12.10.2026.** Ziel bleibt der *echte* Programmspeicher der Viessmann WB2A/VDensHO1, Gerätekennung `20C2`, Software `0103`, ausschließlich über den vorhandenen optischen Optolink-Anschluss. Der funktionale GWG-C7-Reader ist ein Zwischenergebnis, **kein Firmwaredumper**.

## 1. Quellenbewertung

1. **Originale OpenV-Wiki, `Protokoll-GWG.md`:** 4800 8E2; EOT `04`, periodisches ENQ `05`; GWG-Telegramm `01 <Typ> <Addr8> <Len8> 04`. Dokumentiert zwölf historische Opcodes, aber nicht deren Unterstützung durch eine 20C2-WB2A.
   https://github.com/openv/openv/wiki/Protokoll-GWG
2. **OpenV Issue #10, Originaldiskussion vom 01.11.2010:** `01 C7 F8 04 04` -> `20 98 00 02` auf **Vitotronic 200 KW2**. Die GWG-Identifikation durch `voIdent` ist nicht selbst ein Firmware-Lesedienst.
   https://github.com/openv/openv/issues/10
3. **OpenV Wiki `KM-Bus`, KarlKoch (2010):** Autor berichtet von ca. 128 KiB Code der **V200KW2/M30612MC**, ausgelesen über Optolink, ca. 57.000 Zeilen Disassembly. **Weder der originale ROM-Dump noch die notwendigen TX/RX-Kommandos sind bislang wiedergefunden.** Ein Protokollbeweis für eine andere WB2A-Controllerrevision ist das nicht.
   https://github.com/openv/openv/wiki/KM-Bus
4. **Alte `vcontrold_204D.xml`-GWG-Makros:** C7, CB, C5, AE, 9E, 6E, 43 im historischen GWG-Makrokatalog. Der 204D-GWG-Katalog und die frei parametrisierbaren Leseabfragen sind **keine WB2A-Service-Freigabe**. `GETBADDR 0x9E` gehört zu `bget`, in `vito.xml` ausdrücklich als **Bedienteil-Adresse** beschrieben. Damit gibt es keinen Beleg für die Spekulation, das „BE“ stehe für eine Bankerweiterung. Auch der dortige `init`-Frame `16 00 00` ist einem *anderen* Geräteprofil zugeordnet und wird nicht unbesehen an 20C2 übertragen.
   Quelle: OpenV/vcontrold-Originale, lokale Berichte `/home/chatgpt-admin/research/gwg-artifacts/reports/vcontrold-send-history.txt` und `lowlevel-user-command-mappings.txt`.
5. **WB2A-Originalmitschnitte vom 12.10.2026:** zwei unabhängige Livefenster, zusammen 16 Abfragen, mit erfolgreichem Restore; Details in `docs/wb2a-v200kw2-legacy-gwg-live-compatibility-2026-10-12.md`. Roharchive unter `/tmp` auf dem LXC, zugeordnet über die in der Übergabe dokumentierten SHA256-Werte.

## 2. Opcode-Inventur: Quelle, Evidenz und nächster sinnvoller Test

| Opcode | Quelle / historische Bedeutung | Adressfeld | Auf alter Steuerung belegt | An eigener WB2A 20C2 | Nächster quellenbasierter Schritt |
| --- | --- | --- | --- | --- | --- |
| `C7` | GWG `VIRTUAL_READ` | 8 Bit | **Ja**, 2010 V200KW2 `F8/4` -> `20980002` | **Ja**, `F8/4` 2/2 -> `20C20003`, `F8/8` -> `20C2000300000103`, `F9/3` -> `C20003` | Reader im einzigen Serial-Owner; später kontrollierte Längen-/Adressgrenzen prüfen |
| `CB` | GWG `PHYSICAL_READ` | 8 Bit | Dokumentiertes GWG-Beispiel `6F/1` -> `13` auf älterer GWG-Steuerung, **nicht** V200KW2-KarlKoch-Dump | `6F/1` und `F8/1` je 2/2 **ohne Antwort** | Selektor-/Adresssemantik aus 20C2- oder Original-Trace nachweisen, erst dann neue Hardwareprobe |
| `C5` | GWG `PHYSICAL_XRAM_READ` | 8 Bit | Historischer Opcode-Katalog, keine nachweislich entsprechende KW2-ROM-Antwort | `6F/1` und `F8/1` je 2/2 **ohne Antwort** | Erst originalen erfolgreichen XRAM-Zugriff samt Controllerkennung suchen |
| `AE` | GWG `EEPROM_READ` | 8 Bit | Im alten 204D-GWG-Makrokatalog, kein ROM-Lese-Beweis | **Nicht getestet** | Unterschied EEPROM/Programm-ROM nachweisen, keine ROM-Behauptung |
| `9E` | GWG `PHYSICAL_BE_READ` | 8 Bit | 204D-Makro `GETBADDR`; `bget` = **Bedienteil-Adresse** | **Nicht getestet** | Wegen BE=Bedienteil keine ROM-Bank-Hypothese daraus ableiten |
| `6E` | GWG `PHYSICAL_PORT_READ` | 8 Bit | GWG-Dokumentation / 204D-Makro | **Nicht getestet** | Nur passiv; Port-Register-Reads können Hardwarezustände haben |
| `33` | GWG `PHYSICAL_KMBUS_RAM_READ` | 8 Bit | GWG-Wiki-Dokumentation | **Nicht getestet** | Originales KM-Bus-Profil und Rückgabeformat beschaffen; kein CPU-ROM |
| `43` | GWG `PHYSICAL_KMBUS_EEPROM_READ` | 8 Bit | GWG-Wiki / 204D-Makro `GETKMADDR` | **Nicht getestet** | KM-Bus-EEPROM von MCU-Programm-ROM trennen |
| `F7` | KW/VS1 `VIRTUAL_READ` | 16 Bit | KW2-Protokolldokumentation | **Ja**, `00F8/4` -> `20C20003` | Sichere Vorher-/Nachher-ID-Baseline |
| `03`, `05` | P300 `PHYSICAL_READ` bzw. `EEPROM_READ` | 16 Bit im normalen Hostformat | Andere Protokollfamilie | Mit aliasbehafteten Funktionsbytes `63`/`65` an Stichproben identische Antworten, **kein ROM** | Nur 20-Bit-Nachweis oder ROM-Fenster erlaubt neue Dump-Interpretation |
| `C4`, `C8`, `AD`, `C3`, `6D`, `9D` | Historische GWG-Schreibbefehle | 8 Bit | Alte Definitionen | **Nicht getestet und nicht vorgesehen** | Kein unbekannter Controllerwrite |

**Bewertung:** `C7` ist praktisch kompatibel, aber `C7` trägt kein 20-Bit-Adressfeld. `CB/C5` sind an zwei konkret getesteten 8-Bit-Adressen negativ, **nicht global ausgeschlossen**. Bei `9E` ist der historische Gerätename eine bekannte Falle: „BE“ bedeutet hier **Bedienteil**, nicht „Bank Extended“.

## 3. Implementiertes Forschungsartefakt: C7-Reader

`tools/optolinkgwg.py` implementiert ausschließlich `01 C7 <addr8> <len8> 04`; pro Lesevorgang EOT `04` und begrenztes Warten auf ENQ `05`. Er akzeptiert vorerst nur `1..8` Bytes und `addr + length <= 0x100` — dies entspricht der **größten an 20C2 verifizierten Antwortlänge**, nicht dem gesamten theoretischen GWG-Protokoll. Die normalen 8-Bit-Grenzen verbieten insbesondere die irrtümliche Serialisierung von `0xF0000 -> 0x0000`.

Der Reader wird mit einem bereits geöffneten, vom Original-Splitter **exklusiv besessenen** `ser`-Objekt aufgerufen; er konstruiert **niemals** selbst `serial.Serial` und besitzt keinen alternativen Raw-/Write-Entry-Point. Antwortcodes: `01` valide und längengenau, `FF` Timeout/Teilantwort, `FD` ungültige Länge, Adresse oder zu viele Antwortbytes, `AA` Transportfehler. **Keine Teilantwort wird als Messwert akzeptiert.** Maximal ein optionaler Retry. TX/RX-Hex und Status sind über einen `trace_hook` verfügbar.

`tools/optolink-apply-gwg-readonly-patch.py` enthält einen **nur offline/staging-fähigen** Patch für die vorhandene `vs12_adapter.py` und `requests_util.py`: neues explizites MQTT-/TCP-Kommando `gwgread;0xF8;4` oder `gwgread;0xF8;8;1`; dynamische Weiterleitung an denselben Serial-Owner, nur bei `VS1` aktiviert. Nach jedem GWG-Request wird der nächste KW-/GFA-/Write-Zugriff auf den vorhandenen regulären KW-EOT/ENQ-Synchronisierungsweg gezwungen, um Protokollvermischung zu vermeiden.

Das Patchwerkzeug vergleicht die **exakten** SHA256 der beiden vorhandenen produktiven Python-Module, bevor es seine Änderungen in eine **separate** Stagingkopie einträgt. **Es verweigert ausdrücklich `/opt/optolink` als Ziel**; keine Hotpatches, keine weiteren seriellen Portbesitzer, kein automatischer Moduswechsel. Der echte Splitter ist **nicht** geändert oder neu gestartet worden. Das vollständige Staging auf dem realen Runtime-Baumbestand wurde hier noch nicht ausgeführt; bis dahin ist dies eine geprüfte Offline-Integration, keine bereits live aktivierte Erweiterung.

### Testnachweis

```bash
python3 -m unittest discover -s tests -q
# 60 Tests erfolgreich im isolierten Prototyp:
# 38 Core-GWG-Rahmen-/Serial-Fakes und 22 Patch-Integrations-/Negativtests
```

Darunter exakte Wiederholung der archivierten Antwortmuster, alle **2020** zulässigen 8-Bit-Adress-/Länge-Framekombinationen ohne Schreibopcode, Ablehnung 16-/20-Bit-Eingaben, fehlendes `05`, fehlende Antworten, Teilframes, Überlänge, serielle Ausnahmen, Retry-Deckel, Idempotenz, Staging-SHA-Gates und Produktions-Write-Blocker. Dies sind **lokale Fakes**, keine zusätzlichen Heizungs-Hardwaremessungen.

## 4. ROM-Forschung: offen vs. widerlegt

- **Nachgewiesen:** Dieselbe `C7`-Kommandoform, die die echte V200KW2 2010 beantwortete, funktioniert auf der echten 20C2. Auch echte benachbarte Byteadressen und acht Bytes pro Telegramm sind kompatibel.
- **Nicht nachgewiesen:** ein 20-Bit-ROM-Read, Flash-Ausleseweg über UART0/Optolink, ein Bank-/Page-Selektor, ROM-zu-RAM-Kopierdienst oder der genaue KarlKoch-Kommandotrace. Alte `CB/C5`-Missantworten geben kein allgemeines Funktionsverbot her.
- **Ausgeschlossen als unmittelbare Abkürzung:** `9E/BE` ist in `vito.xml` ein Bedienteil-Zugriff, **kein** dokumentiertes Page-/Bank-Read; ebenso sind KMBus-EEPROM und CPU-Program-ROM nicht dasselbe.
- **Prüfkriterium vor Dump:** zwei oder mehr identische Bytefenster mit eindeutiger oberer 20-Bit-ROM-Adresse, Plausibilität als M16C-Maschineninstruktionen oder Vektoren, Unterscheidung von RAM/EEPROM/virtual und kein 16-Bit-Adressalias.

## 5. Technisch begründete nächste Versuche

1. **Quellenarbeit fortsetzen:** insbesondere originalen KarlKoch-TX/RX-Trace, 2010er OpenV-SVN-Revisionsdaten, 204D- vs. 2098- und 20C2-Gerätedienste, alte `voIdent`-Dateien. Alte untersuchte ZIPs nicht ohne neue Hypothese neu scannen.
2. **C7-Integrationsgate:** Reader zunächst nur in isolierter Runtime-Stagingkopie gegen simulierten Serial-Owner testen, mit Negativfällen und VS1->GWG->VS1-Resynchronisierung. Anschließend Hardware-Baseline mit unabhängigem systemd-Restore und maximal einem begrenzten `C7 F8/4`-Versuch — keine automatische Umstellung von `main`.
3. **Gezielte Längenprobe:** wenn Staging-Abnahme grün und Hardware-restore garantiert, zunächst historisch belegtes `C7 F8/8`, danach *nur unter gesondertem Testfenster* `C7 F0/8` und `C7 FF/1` zur Charakterisierung des 8-Bit-Adressraums. Ein erfolgloser Read bleibt ein Timeout, kein ROM-Nachweis.
4. **CB/C5/AE/33/43 nur bei neuem Quellennachweis:** besonders ein dokumentierter vorausgehender reiner Lese- oder Selektionszustand und eine klar erkennbare zugehörige Programm-ROM-Antwort. Keiner dieser Opcodes wird ohne neue Hypothese freigeschaltet.
5. **KM-Bus/Vitotrol erst bei echten Program-ROM-Bytes:** UART1-RX-Dispatcher/ISR/Teilnehmer-State-Commit aus echten Bytes bestimmen. Eine erneute alleinige RAM-Injektion in `0x1642` testet diesen Blocker nicht.

**Betriebssicherheit:** keine Änderungen an `main`, keine Controller-Schreibkommandos, kein Hardware-Flasher, keine Boot-/Reset-Sequenz, kein zusätzlicher serieller Prozess. Auf dem LXC blieb bei der letzten Fernabfrage der produktive VS1-Splitter samt allen fünf Services aktiv; diese Aussage bezieht sich nur auf den Zeitpunkt der Abfrage.
