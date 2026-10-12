# WB2A/20C2: GWG-/Optolink-Spur und M16C-20-Bit-Bootloader – Labor-Readiness

**Stand: 12. Oktober 2026, 09:52 CEST.** Ziel: originale WB2A-Firmware gewinnen, um den KM-Bus-RX-Dispatcher fuer eine Vitotrol-200/300-Emulation ueber Optolink zu identifizieren. Diese Etappe fuehrte **ausschliesslich offline simulierte M16C-Bootloader-Tests** durch. Kein Bootmodus, kein Reset, kein Controller-Read/Write am aktiven Gasheizgeraet.

## 1. GWG nicht ausschliessen, aber drei unterschiedliche Schichten trennen

Der originale OpenV-Autor KarlKoch berichtete 2010, dass er ca. **128 KiB Firmware eines M30612MC** in einer Vitotronic 200KW2 ueber **Optolink** gewinnen konnte. Der **M30612MCA** ist eine Mask-ROM-Variante, nicht die untersuchte M16C/62P-Flashvariante mit dokumentiertem seriellen Flash-Programmierbootloader. Das historische GWG-/Optolink-Verfahren kann folglich nicht ohne Weiteres mit diesem Standard-Flashboot gleichgesetzt werden. Eine originale ROM-Dump-Sequenz KarlKochs wurde bisher nicht gefunden.

Der exakte historische GWG-C7-Virtual-Read `01 C7 F8 04 04` wurde am 12.10.2026 auf unserer echten WB2A **zweimal** positiv nachgewiesen (Antwort `20 C2 00 03`); auch `C7`-Blocklesen und verschobene virtuelle Adressen funktionierten. Die alten GWG-`CB`-Physical- und `C5`-XRAM-Read-Befehle antworteten an **nur zwei getesteten Adressen** `0x6F` und `0xF8` nicht. Darum bleibt GWG als potenzielles Legacy-Frontend interessant, es fehlt aber weiterhin eine **bewiesene 20-Bit-ROM-Bank-/Monitor-/Kopierfunktion**. Ohne sie erfasst das GWG-Grundformat lediglich eine 8-Bit-Adresse, normales KW/P300 nur 16 Bit.

Als weitere historische GWG-Read-Funktionscodes stehen in OpenV die Opcodes `AE` (EEPROM), `9E` (Physical BE), `33` (KM-Bus RAM) und `43` (KM-Bus EEPROM). Diese Dokumentation beweist **nicht**, dass sie auf WB2A unter Live-Bedingungen akzeptiert werden oder ein 20-Bit-ROM erschliessen. Nicht jede Bezeichnung 'physical' bedeutet Programmspeicher. Offene Spur: ein 2010er **mehrstufiger** Optolink-Aufruf oder ein Anwendungsmonitor. Quellen: https://github.com/openv/openv/wiki/Protokoll-GWG ; https://github.com/openv/openv/wiki/KM-Bus ; https://github.com/openv/openv/issues/10 .

## 2. Warum Standard-Renesas-Boot nicht ueber denselben Optolink-IR-Pfad erreichbar ist

Die auf der echten WB2A zuvor gelesenen DMA-/SFR-Werte zeigen **Optolink-TX bei UART0** (DMA1-Ziel `0x03A2`), aber **KM-Bus-TX bei UART1** (DMA0-Ziel `0x03AA`). Original-Hardwarebeweis: `/tmp/wb2a-vitotrol-dma-rom-occupancy-live-20261011.json`, SHA256 `d45c80d6c63786c67c6a9d338159fe409be8c0c8333d8aca0c0983181ead802f`. Die physische Leiterbahnzuordnung ist noch **nicht** per Durchgangsmessung bestaetigt.

Ein geeigneter **Flash**-M16C/62P verlangt nach Renesas-Dokumentation bei Hardware-Reset spezielle Bootstrap-Pegel und fuer den asynchronen Standard-Programmiermodus den **UART1** (`RXD1/TXD1`), meist **9600 Baud, 8N1**. Der normale optische CP2102 spricht die Viessmann-Anwendung ueber **UART0, 4800 Baud, 8E2** an. Weder neue Baudrate noch rohe Flashboot-Bytes ueber IR ersetzen eine fehlende Leitung oder den Bootmode-Hardware-Reset.

**Stoppkriterium:** Bootmodus auf der laufenden oder elektrisch mit der Heizung verbundenen GG1 ist **nicht fuer Tests vorgesehen**. Die normale Gas-/Brennerregelung wird angehalten, PIO-Zustaende beim Bootreset koennen ungewohnt sein, und die Host-VS1-Restore-Unit kann einen echten Bootmodus nicht zuverlaessig beenden. Nur eine ausgebaute, stromlose und von der Heizungsanlage **vollstaendig getrennte identisch bestueckte Ersatzplatine** darf nach eigener elektrischer Pruefung im Labor untersucht werden. Keine Bruecke auf der aktiven Kesselplatine und keine Pin-Nummern aus Fotos anderer Platinen uebernehmen.

## 3. Bootmode-Pegel nur fuer passend identifizierte M16C/62P-Flash-Laborplatine

Das prinzipielle Renesas-Schema (bei tatsaechlich kompatiblem Flash-Typ und bestaetigtem Pinout!) lautet:

- `CNVSS = MCU-VCC`, `CE/P5_0 = MCU-VCC`, `EPM/P5_5 = MCU-VSS`, `SCLK1/P6_5 = MCU-VSS` im asynchronen seriellen Modus.
- Pegel muessen **vor** einem kontrollierten Hardware-RESET anliegen; dies startet auf den entsprechenden Flash-Typen den Boot-ROM-Programmiermodus.
- Asynchroner Bootloader ueber **getrennt zugreifbares UART1 RXD1/TXD1**, nicht den normalen IR-Optolink-UART0. USB-UART-Pegel, Logik-VCC, Massebezugsverhaeltnisse und galvanische Trennung muessen am Laborboard ausgemessen sein.
- Bei einer als **Mask-ROM** identifizierten Variante den **Flashboot-Test stoppen**. Bei unbekanntem MCU-Aufdruck weder Pegel noch Pin-Nummern anlegen.
- Erste Labor-Kommunikation waeren `ver` (Version) und `status` (Status). Das ist noch **kein** ausgelesenes Flash. Serienread kann einen sieben Byte langen vom Hersteller gesetzten ID-Code verlangen. Ohne legitime ID weder raten noch Flash loeschen.

Renesas-Quellen: https://www.renesas.com/en/document/tcu/m16c62-m16c6n-flash-memory-versions-precautions-boot-mode ; https://www.manualslib.com/manual/1615929/Renesas-M16c-62p-Series.html . Entwickler-Flashprogramm: https://github.com/truhy/m16c-flasher .

## 4. Echte Flasher-Software erfolgreich gegen simulierten M16C getestet

Repo-Pin `truhy/m16c-flasher` Commit `cc8f1c387a5bb86ff25600eacb59a576b5312163`; lokal aus Quellcode gebauter Linux-Flasher SHA256 `8b097885014d1ee082b6c66a58bfd51ce93b3e58abc64c349eddc6335d5784ce`. **Keine echten seriellen Ports** wurden geoeffnet. Jeder Lauf erzeugte eine nur softwareseitig verbundene POSIX-PTY `/dev/pts/N` und startete das **unveraenderte** Programm dagegen.

- Version: reale Host-TX `b0fb`; synthetisches Boot-RX `b0` + `VER4.04`; Programm verarbeitet Antwort korrekt.
- Status: reale Host-TX `b070`; synthetisches Boot-RX `b0` + `000c`; Programm zeigt synthetischen Status `0x0c00`; **nicht** als ID-Freigabe unserer realen WB2A interpretieren.
- **End-to-End 20-Bit-Auslese-Emulation:** reale Host-TX `b07070ff000fff010f`. Darin nach Statusabfrage Page0 `ff000f` = ROM-Start `0xF0000`, Page1 `ff010f` = ROM-Start `0xF0100`; exakt **512 synthetische Bytes** aus zwei 256-Byte-Seiten korrekt in Temp-Binaerdatei gespeichert. SHA256 der Testbytes `1c7454fdb5783a77693d566de1ea54b3f3ba558f48aae8f782c199c84e355143`.
- Reales normal P300 `FC03/0xF0000` wuerde nur `0x0000` senden. **Der 20-Bit-Bootloader-Weg serialisiert die hohen Adressbits nachweislich; die bisherige Optolink-P300-Routine nicht.**

Neue SHA-/Quelle-gepruefte Offline-Skripte:

```sh
cd /home/chatgpt-admin/optolink-vitotrol-rpm-20261010
python3 tools/wb2a-m16c-boot-hardware-preflight-offline.py --out /tmp/wb2a-m16c-boot-preflight-20261012.json
python3 tools/wb2a-m16c-boot-fake-pty-check-offline.py --out /tmp/wb2a-m16c-fake-boot-pty-proof-20261012.json
python3 tools/wb2a-m16c-boot-fake-20bit-page-read-offline.py --out /tmp/wb2a-m16c-fake-20bit-read-20261012.json
python3 -m unittest discover -s tests -q
```

Alle drei Testprogramme enthalten ausdruecklich **keine echte Optolink-/UART-Hardwaregeraeteoeffnung**, null Controller-I/O und null Controllerwrites. Der erste liefert `NO_LIVE_BOOT_TRIGGER_PERMITTED` und `UNIDENTIFIED` fuer die noch nicht identifizierte WB2A-CPU. Offline-Tests: Preflight **7/7**, Boot-Version/Status-PTY **4/4**, 20-Bit-Page-Read-PTY **4/4**.

## 5. Technisch nuetzliche naechste Zusammenarbeit

1. **Makroaufnahme** des MCU-Chipaufdrucks und der **Pin-1-Markierung** auf einer tatsaechlich baugleichen, abgetrennten WB2A/GG1-**Ersatzplatine** (ggf. Platinenkennung/Revision, z. B. GG1/7187393). Modell M30624FGPFP einer **anderen** Viessmann VBC130-Platine ist nicht als WB2A-Teil identifiziert.
2. Bei **Flash-MCU**: aus Renesas-Datenblatt der *konkret vorhandenen* Part-/Package-Revision Testpads, Pinout und Spannungen fuer **UART1/Reset/Boot** identifizieren; nur mit sicherer getrennter Laborversorgung, Strombegrenzung und galvanischer Trennung arbeiten sowie den Rueckweg in den Normalmodus dokumentieren.
3. Nur im Labor erst `ver`/`status`; erst mit legitimer ID und nachgewiesener Leserlaubnis **eine** 256-Byte-Seite und danach zwei wiederholte komplette Program-FLASH-Auslesungen samt Hashvergleich. Keine erase/program/download/lock-Kommandos.
4. **GWG Plan A bleibt parallel aktiv**: KarlKochs historische Originalsequenz oder einen an 20C2 bestaetigten Optolink-Anwendungs-ROM-Dienst finden. Nicht mit der Flash-Programmier-Drahtverbindung verwechseln. Das volle Boot-ROM kann auch ohne ID nicht zwangslaufig den Anwendungs-ROM auslesen.

**Geratestatus nach diesen Offline-Tests:** produktiver VS1-Splitter blieb aktiv, keinerlei MCU-Reset/-Boot/-Flash-Wechsel, kein echter WB2A-ROM-Dump. Forschung ausschliesslich im Draft-PR #52; `main` unveraendert.
