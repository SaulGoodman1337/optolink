# Vitotronic 200KW2/M30612MC als Forschungsquelle für WB2A/20C2 – kein pauschaler Ausschluss

**11. Oktober 2026, fortgesetzt ca. 22:10–22:15 CEST.** Projekt *Vitotrol 200/300 vollständig über Optolink*, Plan A. Keine externe KM-Bus-Hardware, keine RAM-/DMA-/UART-/IRQ-/Controller-Writes. Produktives `main` bleibt unangetastet, Forschungsstand in Draft-PR #52.

## 1. Kurzantwort auf die entscheidende Frage

**Die 200KW2 wurde bisher nur aus Vorsicht getrennt behandelt; ein technischer Ausschluss ihrer Optolink-Firmwareauslesemethode für die WB2A ist NICHT bewiesen.** Die Risiken sind real, aber betreffen besonders die konkrete Firmwarefunktion, den Geräteprofil-Kontext und die ROM-Abbildung; sie schließen einen funktional ähnlichen Zugriff nicht generell aus.

KarlKoch selbst, ursprünglicher OpenV-Autor, hat in einer Git-History-Version vom **22.10.2010** der [OpenV-KM-Bus-Seite](https://github.com/openv/openv/wiki/KM-Bus) festgehalten: Die Vitotronic 200KW2 arbeite mit **M30612MC**, ihr rund **128 KB großer Programmcode sei über Optolink auslesbar**, und seine darauf aufbauende Disassembly umfasse ungefähr **57.000 Zeilen**. Der eindeutige Git-Commit ist `a1d3f9c6dc35b1ca3099a6b452f9ea975e53b962`, SHA256 der historischen Markdown-Fassung `a248ec890d4832294c5fac2e85b6b82b9df5021b78d42dc89ddc5bcdf0c6a5bc`. Die Aussage stammt nicht aus späterer KI-Interpretation oder Übernahme in eine andere Anleitung.

**Evidenzqualität:** Das ist ein plausibler Primärzeugenbericht eines tatsächlichen Disassemblierers, aber **kein unabhängig reproduzierbarer Ausleseablauf**. In den öffentlich erhaltenen Wiki-Versionen fehlt die exakte Optolink-Request-Sequenz, ein originales 128-KB-Binärabbild und ein Transfer-Trace. Der Link vom Artikel führt auf die allgemeine **Protokoll-GWG**-Dokumentation, die ihre normal lesenden und schreibenden Funktionen beschreibt – **nicht** auf einen eigenständigen ROM-Dumper. Die damalige Dev-Forum-/OpenV.de-Forschung ist nur unvollständig archiviert.

## 2. Technischer Querschnitt: Gemeinsamkeiten und echte Portabilitätsrisiken

| Merkmal | 200KW2 2010 | Eigene WB2A VDensHO1/20C2 | Bewertung |
| --- | --- | --- | --- |
| CPU / Befehlssatz | M30612MC, Mitsubishi M16C/61, 128-KB-Mask-ROM | M16C-kompatible UART-/DMA-/SFR-Belege; exakte Chipvariante **nicht** bestätigt; M16C/62P nur Arbeitshypothese | Verwandte CPU-Architektur, aber SFR/ROM-Typ/Portbelegung/Boot-Verhalten sind nicht zwingend gleich |
| Programm-Raum | 128 KB bei älterem M30612MC typischerweise `0xE0000..0xFFFFF` | Beim *hypothetischen* 256-KB-M30624-FP `0xC0000..0xFFFFF`; **nicht als lokale Chip-/Speicherkarte bewiesen** | Auch gleicher 20-Bit-Adressraum garantiert nicht gleiche Codepositionen |
| Physikalischer Anschluss | Optolink, KW / 4800 8E2 | Optolink, produktives VS1, nativ P300 erfolgreich | **Kein Hardwareausschluss**, aber andere Protokoll-/Service-Implementierungen möglich |
| Adressen im normalen KW-Read | 16 Bit | VS1 16 Bit, FC03 P300 16 Bit nachgewiesen | Reichen allein **nicht** für vollständigen 128-/256-KB-Programmdump |
| KM-Bus-Familie | Klassen, Slots, CRC16/Kermit, `0x31/0xB1` und `0x33/0xB3` dokumentiert | Genau diese Art von KM-Bus-Framing aus natürlichen WB2A-RAM-Kopien und echten Vitotrol-300-Telegrammen nachgewiesen | **Starke Kompatibilität auf Nachrichten-/Busprotokollebene** |
| Optolink-Firmware-RPC | Vom Zeitzeugen behauptete Leseoperation; **Request-Bytes nicht überliefert** | Keine nachgewiesene 20-Bit-ROM-Service-/Monitor-Semantik | **Entscheidender noch offener Punkt** |

Die entscheidende Unterscheidung lautet: **Ähnlicher MCU-Befehlssatz und gemeinsamer KM-Bus-Frametyp belegen weder gleiche Firmware-Adressen noch gleichen Optolink-Firmware-Dispatcher.** Umgekehrt ist das andere MCU-Modell allein **kein** Beleg für Unmöglichkeit.

### Address-width-Gate

128 KiB benötigen für byteweise eindeutig adressiertes ROM **17 Adressbits**, ein gewöhnlicher VS1-/P300-Read aber nur einen **16-Bit-Startadresswert**. Falls KarlKoch tatsächlich den ganzen Code via Optolink übertrug, muss beim Transfer **irgendeine zusätzliche Semantik** existiert haben: z.B. Bank/Page, Quell-Pointer in Servicepayload, zeitabhängiger Monitor-Modus, Umschalten des Adressfensters oder ROM→RAM-Kopierdienst. Dies ist eine logische Schlussfolgerung aus Adressbreite und beanspruchter Dumpgröße, **nicht** die Identifikation eines konkreten 2010er Befehls. Alternativ könnte der Zeitzeugenbegriff Optolink einen speziellen, nicht dokumentierten Zugriffspfad umfassen.

Die frühere negative WB2A-Forschung grenzt gewöhnliche 16-Bit-Wege ein: `FC03/FC99` sind keine unabhängig bewiesenen ROM-Dienste (untere fünf Host-Funktionsbits teilen sich einen Code), `PROZESS_READ 0x7B` serialisiert nur eine 16-Bit-Zieladresse, der Vitosorp-RPC-Proxy `0xA400` überträgt ebenfalls nur 16-Bit-Adressen und besitzt keine bestätigte VDensHO1-RPC-Bindung. FC03 an `0xF000/0xFFF0` liefert wiederholt `5497/5498`, keine bewiesenen ROM-Vektoren. Keine dieser Negativproben widerlegt einen bislang **undokumentierten** Service.

## 3. Exakte, reproduzierbare Dreiquellen-Protokollprüfung

Neue rein offline Arbeit: `tools/wb2a-vitotrol-kw2-crossgeneration-wire-audit.py` mit `tests/test_wb2a_vitotrol_kw2_crossgeneration_wire_audit.py`.

**Authentifizierte Quellen:**
1. KarlKochs historische OpenV-Git-Fassung vom 22.10.2010: Commit `a1d3f9c6dc35b1ca3099a6b452f9ea975e53b962`, Markdown-SHA256 `a248ec890d4832294c5fac2e85b6b82b9df5021b78d42dc89ddc5bcdf0c6a5bc`.
2. Echte Vitotrol 300, originaler TX-UART-Logger von `boblegal31`, 06.11.2018, [OpenV Issue #387](https://github.com/openv/openv/issues/387#issuecomment-435796559): ursprüngliches ZIP SHA256 `eb398ec9b4b174354425d2615f7d76937acaf5e0e1cde4df154fee78425bab93`, enthaltene Binärdatei SHA256 `b6d5b0526d0b0a96e5bc3369de639763ef95db9786ee51a1c0b26ecbb229d068`.
3. Eigene WB2A am 11.10.2026: erster natürlicher, CRC-validierter `0x31`/Register-`0x00`-Master und danach separat gelesener B1/00-RX-Puffer, SHA256 `26669707fbd572f25a384b865740c730ec9f4b7e1035cde33cbb142ae99d2e27`, 134 reine Leseanfragen, eventueller Bus-ISR weiterhin unbeobachtet.

**Technische Ergebnisse:** Die ursprüngliche 2010er Firmwaretabelle enthält ausdrücklich `0x11` mit Slots **1, 2, 3** und zulässigem zweitem ID-Byte **0x34 bzw. 0x38** sowie `0x01`/Slot 1; die Befehls-Paare **`0x31 → 0xB1`** und **`0x33 → 0xB3`**.

| Framequelle | Exakte Hexbytes / Aussage |
| --- | --- |
| 2010 KW2 Beispiel: Master liest Klasse11/Slot3 ID | `11 00 33 0A 03 01 F8 04 3F D6` |
| **Nur rechnerisch abgeleitet**, auf Slot 1 umgerechnet, CRC neu | `11 00 33 0A 01 01 F8 04 49 EF` (**kein Beweis für dieses Mastertelegramm auf dem eigenen KM-Bus**) |
| 2010 KW2 Beispiel: Klasse01/Slot1 ID | `01 00 33 0A 01 01 F8 04 31 B4` |
| 2018 echte Vitotrol 300 ID-Antwort, Klasse11 | `00 11 B3 10 01 01 F8 11 F9 38 FA 01 FB 0A 1D B1` (Identität `11 38 01 0A`) |
| 2018 echte Vitotrol 300 Register 00 | `00 11 B1 0A 01 01 00 12 19 D5` |
| 2026 eigener WB2A-Master, **Klasse01** Register 00 | `01 00 31 09 01 01 00 27 FA` |
| 2026 eigener WB2A-RX-Puffer, **Klasse01** Register 00 | `00 01 B1 0A 01 01 00 00 43 53` |

Alle **acht hinterlegten Einzel-Referenztelegramme** (einschließlich Original-Vitotrol-PONG und rechnerischer ID-Abfrage) erfüllen **jeweils deklarierte Länge und CRC16/Kermit-Gesamtrest = 0**. Der 2018er Originalstream wurde unabhängig vollständig als **448 aufeinanderfolgende CRC-gültige Slaveframes** plus vier Schlussbytes dekodiert, ohne Zwischenlücken oder resynchronisierende Reparaturen: 416× PONG, 30× BF, 1× B3, 1× B1. Die externe V300-ID `11 38 01 0A` erfüllt die von KarlKoch 2010 dokumentierte Geräteklasse und ID2 `38`.

**Beweisumfang:** Identität der verwendeten KM-Bus-Grammatik, CRC, Klassen-/Slotadressierung und ID-Struktur über drei getrennte Quellen und 16 Jahre. Das ist **keine Bestätigung derselben MCU-Firmware oder des historischen Optolink-ROM-Auslesebefehls**. Außerdem ist das beobachtete lokale WB2A-RX-Telegramm weiterhin Klasse **01**, nicht Klasse **11**; der eigene Teilnehmerindex `0x0A5C` blieb null. Die 2010er CRC-abgeleitete Slot1-Abfrage wurde **nicht** an den Heizungsregler gesendet.

## 4. Was an einer 1:1-Übernahme wirklich scheitern könnte

- **Fehlender service code:** Die WB2A-Firmware kann die damalige spezielle Monitorfunktion schlicht nicht enthalten.
- **Abweichende Optolink-Dispatcher-Semantik:** 200KW2 nutzt KW/VS1; WB2A kann KW/VS1 und P300, aber identisch benannte Operationen müssen nicht dieselbe Controller-Funktion adressieren.
- **Anderer Flash-/Mask-ROM-Schutz und ROM-Start:** Der M30612MC ist eine Mask-ROM-Variante; der genaue eigene MCU-Chip ist nicht identifiziert. Das unterscheidet besonders Bootloader-Funktionsweise und Programm-ROM-Anordnung.
- **Andere Taktung/Watchdog-/Scheduler-Routinen:** Ein früher genutzter Transfermodus kann einen bestimmten Firmwarezustand oder Aufrufkontext verlangen. Bei aktivem Gasbrenner werden keine nicht verifizierten Mode-/DMA-/Interrupt-Schreibzugriffe vorgenommen.

**Kein zusätzlicher Punkt erlaubt derzeit die kategorische Aussage 'nicht anwendbar'.** Das alte Beispiel bleibt ein **hoch priorisierter, technisch plausibler Forschungspfad**, aber nicht eine Copy/Paste-kompatible Programmierprozedur.

## 5. Nächster Forschungsschritt ohne sinnloses Abfragen

1. **Originalsequenz des KarlKoch-/openv.de-Entwicklerforums rekonstruieren.** Die erhaltene Wiki-Git-History (ursprüngliche Okt.-2010-Versionen), 71 alte Wiki-ZIP-Dateien und spätere ViessData/V-Comm-Quellen wurden bereits zuvor tief untersucht; das 128-KB-Binary, die ca. 57.000 Zeilen Disassembly und das Readout-Tool wurden **nicht** gefunden. Nicht wiederholt dieselben Bestände durchsuchen. Priorität hat der fehlende private OpenV-Entwicklerforum-/KarlKoch-Quelltext oder eine archivierte Original-Serialsession.
2. **Konkrete Optolink-Frames offline analysieren**: Richtung/Funktion, 16- vs. 20-Bit-Adresse, Bank/Page oder ROM-Copy, Status-/Unblock-Handshake; sicherstellen, dass ein Kommando tatsächlich bei der WB2A `20C2/0103` vorhanden ist, bevor es am Kessel getestet wird.
3. **Nur bei belegtem Read-only-Controllerpfad minimaler Optolink-Livetest** mit unabhängig aktiviertem 4-min Restore-Timer, originalem Single-Port-Owner und CRC-/Adress-/Len-Gates; ein stabiles kleines ROM-Fenster mit plausibler M16C-Vektor-/Opcode-Semantik ist die Eintrittsbedingung für größeres Segmentdumping.
4. **Erst nach echtem Firmware-Code:** `INTB`/UART1-RX, Klasse11-Dispatcher, `0x1642` und `0x166A/0x166B` aktualisierende Routine sowie `0x0A5C`-Participant-Commit bestimmen. Wenn die Firmware die Route nicht offenlegt, sind Optolink-only RAM-Preseeds ohne Dispatcher-Beleg weiterhin unzureichend.

**Testsicherheitsstatus:** Dieser neue Dreiquellen-Audit nutzt nur bereits bestehende, SHA-gepinnte Offline-Dateien: **0 neue Controller-I/O, 0 Writes, kein Dienst-Neustart**. Die reale Heizung blieb bei `vs1protocol=True` und `VS1_BETRIEB_OK`; zuletzt geprüft am 11.10.2026 um 22:03 CEST. 
