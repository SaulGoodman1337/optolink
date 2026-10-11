# WB2A 20C2 – Firmwareauslesung: verifizierter M16C-Bootloader-Pfad und Stop-Gates

Stand: 11.10.2026. Projektziel ist die echte Vitotrol-Emulation über Optolink (Plan A). Die alternative Raumregelung 0x2321 bleibt pausiert.

## 1. Sauber zwischen Hardware und Hypothese unterscheiden

Der verbaute WB2A/GG1-Kessel meldet über Optolink `20C2/0103` und zeigt im Low-SFR-/UART-/DMA-Layout deutliche Übereinstimmung mit der Renesas-M16C/62P-Architektur. Das ist **kein** Beweis für die genaue Chipbestellnummer und insbesondere nicht für eine Flash- statt Mask-ROM-Variante. Die ältere Fotovorlage `7424735/VBC130` mit einem mutmaßlichen `M30624FGPFP` betrifft eine andere Viessmann-Steuerung. Die wahrscheinlich passendere GG1-Leiterplattenfamilie führt die Kennung `7187393`, deren Chipaufdruck auf den gesicherten Internetfotos aber bislang **nicht lesbar** ist.

Der Renesas M30624FGPFP ist laut offiziellem Produktdatenblatt ein **M16C/62P in einem 100-Pin-QFP mit 256 KiB Programm-Flash und 20 KiB RAM**. Falls diese Variante (oder eine kompatible) physisch bestätigt werden kann, liegt die 256-KiB-Anwendungs-Firmware im angenommenen Bereich `0xC0000..0xFFFFF`. Die im realen WB2A-SRAM gefundenen far-pointer-artigen Werte sind nicht per se ein ROM-Dump.

## 2. Echte neue Hardwarenegativtests

Am 11.10. wurden 123 echte, erfolgreiche native-P300-READ-Aufrufe in drei getrennten, unabhängig rückstellbaren Messfenstern durchgeführt:
- `FC03` an `0xE000,0xF000,0xFFF0`: häufig 8 x gleiche Zweibytewerte (`5497/5498`), zeitweise `4343/0800/f801`; kein stabiler, 20-Bit-adressierter Programmcode.
- `FC99` an SRAM-Adressen `0x0B51/0x0B74/0x0B7E`: Rückgabe der tatsächlichen ersten zwei RAM-Bytes statt einer belegten dereferenzierten ROM-Quelle.
- Gepaarte A/B/A-Abfragen FC03-vs-FC99 an den hohen Adressen: nur 3/9 Zweibytewerte stimmen zeitversetzt überein. Die abweichenden Daten sind ebenfalls nicht stabil.
- 4 RX-Snapshots mit UART1-SFR: keine verifizierten RX-IRQ-Pending-Events, `0x0A5C=00000000`, `0x089C=03`.

Damit sind **weder ein aufrufbarer Firmware-Dispatcher noch ein 20-Bit-Flash-Monitor auf dem getesteten P300-Weg belegt**. Ein gewöhnlicher 16-Bit-`Physical_READ 0xF000` ist nicht dasselbe wie die 20-Bit-Adresse `0xF0000`.

## 3. Verifizierte Linux-Auslesesoftware ohne Hardwareeingriff vorbereitet

Quellprojekt: https://github.com/truhy/m16c-flasher
Revisions-Pin (aktuelle abgeholte HEAD zum Testzeitpunkt): `cc8f1c387a5bb86ff25600eacb59a576b5312163`.

Auf dem Forschungshost **isoliert** ausgecheckt nach
`/home/chatgpt-admin/research/m16c-flasher-source-review-20261011`, mit
`g++ -std=gnu++20 -O2 -Wall -fexceptions` und den sieben erforderlichen `.cpp`-Quelldateien kompiliert. Binary:
`/home/chatgpt-admin/research/m16c-flasher-source-review-20261011/build-review/m16cflasher`
SHA256: `8b097885014d1ee082b6c66a58bfd51ce93b3e58abc64c349eddc6335d5784ce`.
Offline-Aufruf **ohne Parameter** lieferte `m16cflasher v1.3 – Jan 2026` und die Hilfetexte zu `ver`, `status`, `id_chk`, `read`; **kein serielles Device, kein Optolink-Aufruf, kein Bootloader-Zugriff, kein Controllerwrite**.

Die Quellcodeprüfung in `main.cpp` zeigt: `CMD_READ` kontrolliert zunächst den sieben Byte langen ID-Checkstatus und ruft erst bei positiver Verifikation den Page-Reader auf; `process_read_flash_to_file` verarbeitet 256-Byte-Seiten. Dies ist ein **Quellcode-Eignungstest**, kein Nachweis der Entsperrbarkeit oder Vollständigkeit des Dumps an der konkreten Viessmann-Platine.

Andere M16C-Projekte: `beroset/pico-puller` nennt die M16C/**62A**-Familie und synchrones Pico-Interface. Weder ein gesicherter 62P-Nachweis noch eine elektrisch sichere Direktverschaltung zur GG1 folgt daraus. Dieser Ansatz darf nicht als garantierter Entsperr-Workaround beworben werden.

## 4. Physikalische Zugangsbarrieren

Der M16C-Serienbootloader ist **nicht** derselbe P300/Optolink-Protokollpfad. Unsere P300-SRAM-/UART-Untersuchung korreliert den normalen Optolink-Verkehr mit **UART0** und den KM-Bus-RX/TX-Teil mit **UART1**. Der M16C/62P-Standard-Serial-Boot-Modus setzt dagegen Hardware-Reset mit passenden Pegeln an **CNVSS/CE/EPM** und danach UART1-Programmierkommunikation voraus. Für das aktive GG1-Heizgerät wäre ein Bootmodus-Reset keine akzeptable Online-Testmethode: die normale Brennerregelung würde angehalten. Renesas weist außerdem explizit auf vorübergehende Port-Pegel während Bootmode-Reset hin. Deshalb **nur an abgetrennter baugleicher Ersatzplatine mit kontrollierter Laborversorgung**.

WICHTIG: Bevor irgendeine Pinbelegung angewendet wird, muss der **exakte Aufdruck, die Gehäusevariante/100-Pin-Orientierung und die Versorgungsspannung** des lokalen Chips belegt sein. Für den *hypothetischen* rechteckigen M30624FP nennt der vorhandene `m30624-nondestructive-readout-plan.md` u.a. CNVSS Pin 9, RESET 12, TXD1 31, RXD1 32, SCLK1 33, BUSY 34, EPM 41, CE 46. Ein Pinout gilt nicht ohne positive Identifikation des vorliegenden ICs. Keine direkte 3,3-V-Pico-Verbindung mit unbekannten 5-V-Signalen, keine freihängenden Drähte im aktiven Kessel.

## 5. ID-Code als eigenständiger Erfolgs-Gate

Renesas M16C Flashgeräte können über **sieben ID-Code-Bytes** vor dem Serial-Read geschützt sein. Version/Status dürfen im Bootloader grundsätzlich ohne ID lesbar sein; Speicherzugriff benötigt ggf. ID-Check. Ein `VERx.xx`-Antworttelegramm ist **nur ein Verbindungstest** und noch kein ausgelesenes Firmwareimage. Ein unbekannter ID-Code ist eine echte Zugriffsschranke, nicht durch `FC99`-/`FC03`-Adressspiele lösbar. Keine massenhaften ID-Versuche oder Autoerase-/Blankcheck-/Flashprogrammieraktionen.

## 6. Beschlossene nächste Versuche (beweisgesteuert)

1. **Chipidentität lösen:** originale, ausreichend scharfe Makroaufnahme vom tatsächlich installierten GG1/7187393 oder einer identisch bestückten Ersatzplatine, inklusive Chip-Laseraufdruck, Platinenaufdruck und Pin-1-Marke. Bei Mask-ROM-Variante den Flash-Bootloader-Plan stoppen.
2. **Ersatzplatine, nicht den laufenden Kessel, elektrisch kartieren:** unbestromte Durchgangsmessung zwischen bestätigten MCU-Pins und Testpads/Steckern; danach galvanisch sichere und spannungsrichtig versorgte Testeinrichtung.
3. **Bootloader-Verbindung nur read-only verifizieren:** `ver`, `status`. Anschluss/Boot-Modus und Gerätetyp werden damit belegt, ohne die App-Firmware anzutasten.
4. **ID-Sperre klären:** verfügbare legitime Original-ID, bestätigte Default-ID *nur wenn angemessen*, sonst kein willkürliches Brute Force, Lösch- oder Flash-Verfahren.
5. **Nur bei freigegebenem Read:** 256-KiB-Nutzflash komplett in unabhängigen Leseläufen dumpen; Größen, Hashes, Fixed-Vector-Tabelle und den Speicherbereich aller far-pointer-Kandidaten prüfen. Anschließend M16C-Disassembly mit UART1-ISR/INTB/KM-Bus-Parser und Softwareindex-/Sensorstatus-Commit korrelieren.
6. **Parallel Plan A weiter**, aber nur mit echten externen Quellen: alter M30612/KarlKoch-Optolink-Firmwareausleseweg könnte einen separaten Anwendungs-Monitor enthalten; er stammt aus einer anderen, als Mask-ROM beschriebenen M16C/61-Gerätefamilie, deshalb keine automatische Übertragung auf die WB2A.

Quellen: https://github.com/truhy/m16c-flasher ; https://www.renesas.com/en/products/m16c-62p/part-details/m30624fgpfp-u3c ; https://www.manualslib.com/manual/1615929/Renesas-M16c-62p-Series.html ; https://www.renesas.com/en/document/tcu/m16c62-m16c6n-flash-memory-versions-precautions-boot-mode ; https://kb.segger.com/Renesas_M16C .

**Abschlusszustand:** kein geänderter produktiver Code, kein Controllerwrite, VS1-Splitter und RPM-Logger weiterhin aktiv. Der bestehende Vitotrol-Forschungs-PR #52 bleibt Draft.
