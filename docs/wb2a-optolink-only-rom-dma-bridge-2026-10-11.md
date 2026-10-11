# WB2A 20C2 / Optolink-only ROM-Readout: 20-Bit-DMAC als möglicher ROM-zu-RAM-/UART-Transport

**11.10.2026, 17:00 CEST.** Benutzerentscheidung: **ausschliesslich Optolink**, keine Platinen-, Löt-, Programmer-, separaten KM-Bus- oder Reset-/Boot-Pin-Versuche. Die alternative Raumtemperaturregelung über `0x2321` bleibt pausiert. Forschungsbranch und PR #52 bleiben getrennt von `main` und dem produktiven optolink-splitter.

## 1. Wesentliche neue technische Erkenntnis

Die Renesas-M16C/62P-Dokumentation spezifiziert für die zwei DMA-Kanäle:

- `SAR0` an `0x0020..0x0022` und `SAR1` an `0x0030..0x0032` als **20-Bit-Quellzeiger**, mit Adressbereich `0x00000..0xFFFFF`.
- `DAR0` `0x0024..0x0026`, `DAR1` `0x0034..0x0036` als 20-Bit-Zielzeiger; `DM0CON` `0x002C`, `DM1CON` `0x003C`; `DM0SL` `0x03B8`, `DM1SL` `0x03BA`.
- DMAC darf über denselben Datenbus wie die CPU unter anderem auf **internes ROM** zugreifen. Eine DMA-Quelle über 64 KiB ist daher auf Architektur-Ebene plausibel, ohne dass ein zwei Byte breites P300-Adressfeld die ROM-Adresse selbst direkt übermitteln müsste.
- Für die DMA-Adressfortschaltung darf **nicht gleichzeitig** Quell- und Zieladresse vorwärts laufen (`DSD=1 && DAD=1` nicht erlaubt). Ein linearer ROM→linearer RAM-Blockdump ist folglich nicht trivial nur durch Einstellen beider Auto-Inkrementbits möglich. Denkbar sind einzelne 8-/16-Bit-Transfers in einen festen RAM-Puffer oder ein ROM→UART-Stream mit festem UART-TX-Ziel. Für einen echten Dump wären zusätzliche Steuerung, Wiederholung und eine sichere Host-Übertragungsstrecke nötig.
- Die CPU kann mittels Software-Request nur bei passend gesetzter DMA-Request-Auswahl und Registersteuerung DMA auslösen. Das ist **kein** beweisbarer, schon vorhandener P300-ROM-Auslesedienst.

Primärquelle: Renesas M16C/62P Hardware Manual, Rev. 2.41, Kapitel 14 DMAC, Register/SAR-/DAR-Dokumentation, besonders Seiten 128–134: https://www.renesas.com/en/document/mah/m16c62p-group-m16c62p-m16c62pt-hardware-manual

**Harte Grenze:** Die exakte MCU-Bestellnummer unserer GG1 ist weiterhin nicht physisch bestätigt. Die starken Live-SFR-/DMA-/UART-Korrelationen machen M16C/62P plausibel, nicht endgültig bewiesen. Program-ROM `0xC0000..0xFFFFF` und Flash gegen Mask-ROM bleiben Arbeitshypothesen.

## 2. Neuer ausschließlich lesender Optolink-Hardwareversuch

Am **11.10.2026 von 16:58:51 bis 16:59:38 CEST** wurden über den bereits vorhandenen Optolink-Splitter temporär im **nativen P300-Modus** in einer gesicherten Sitzung **29 erfolgreiche Leseanforderungen**, davon fünf DMA-Snapshots, durchgeführt. Vor der Umschaltung: genau verifizierte Gerätekennung `20C2000300000103`, `A0=00`, `B0=00`, `0x7342=00` und kein aktueller Fehler `0x5738=00`. Zusätzlicher unabhängiger 4-Minuten-`systemd-run`-Rollback war **vor der Umschaltung aktiv**.

Feste explizite Read-Whitelist der neuen Funktion `--dma-only`:

```text
P300 Virtual_READ   0x00F8/8              (Gerätekennung)
P300 Virtual_READ   0x27A0/1 0x27B0/1     (Codierung)
P300 Virtual_READ   0x7342/1 0x5738/1     (Status/Fehler)
P300 Physical_READ  0x0020/32             (beide DMAC-Kanäle)
P300 Physical_READ  0x03B8/4              (DM0SL/DM1SL)
P300 Virtual_READ   0x0A5C/4 0x089C/1     (Vitotrol-/Sensorstatus)
```

Keine `Physical_WRITE`-, UART-SFR-, DMA-/Software-Request-, ROM-, EEPROM- oder Heizungs-Codierwrites.

### 2.1 DMA-Registerbefund (fünf Snapshots)

| Eigenschaft | DMA0 / KM-Bus-UART1 | DMA1 / Optolink-UART0 |
| --- | --- | --- |
| 20-Bit-SAR (beobachtet) | `0x0161B` und `0x01621` | `0x019AF` |
| DAR | `0x003AA` (U1TB) | `0x003A2` (U0TB) |
| `DMiSL` Request-Selector | `0x0F` (UART1 TX) | `0x0A` (UART0 TX) |
| `DMiCON` | `0x15` in 4/5, `0x19` in 1/5 | `0x15` in 5/5 |
| DMAE-Bit **Bit 3** | 1/5 eingeschaltet | 0/5 eingeschaltet |
| DMAS-Bit **Bit 2** | bei `0x15` gesetzt | bei `0x15` gesetzt |
| Transferzähler (in 5 Stichproben) | `8,8,4,10,20` | `8,8,15,10,8` |
| ROM-Quelladresse beobachtet? | **0/5** | **0/5** |

**Neue Korrektur:** `DMiCON=0x15` bedeutet nach Renesas-Bitbelegung **DMAE=0 im Moment der Messung**, nicht "DMA läuft ständig". `0x19` entspricht DMAE=1, DMAS=0, DSD=1. Die dynamischen Zähler und DMA0-Quellpositionen sowie die UART-TX-Selektoren zeigen dennoch, dass beide Kanäle von der normalen Reglerkommunikation **verwendet/konfiguriert** sind. Die DMA-Register und Selector-Register stammen aus getrennten, nicht atomaren P300-Reads.

Weitere Prüfung: `0x0A5C=00000000` und `0x089C=03` in **5/5**; keine Vitotrol-Registrierung beobachtet. Gerätesignatur/Codierung/Fehlerstatus vor und nach der Messreihe unverändert.

### 2.2 Restore-Vollständigkeit

Beim Ende des Zeitfensters funktionierte der manuelle EXIT-Restore; der unabhängige systemd-Failsafe wurde erst nach dessen bestätigtem Abschluss gestoppt. Original-`/opt/optolink/settings_ini.py` und Snapshot SHA256 identisch `e9a120ef37fe17236a7505ee713c8dd338d98d5093ed75dfb34629d7e8f5c42d`. `optolink-hybrid status` meldete wieder **`VS1_BETRIEB_OK`**, und die ursprünglich aktiven Splitter-, Party-, Schedule-, Service-, Maintenance- und RPM-Logger-Units waren aktiv; `0x5738=00`. Kein neuer serieller Besitzer und kein produktiver Deploy.

Privater Rohdatensatz: `/tmp/wb2a-vitotrol-dma-rom-occupancy-live-20261011.json`; unabhängige Offline-Zusammenfassung: `/tmp/wb2a-vitotrol-dma-rom-audit-20261011.json`; Rückstellungslog: `/root/wb2a-vitotrol-dual-readonly-20261011/restore.log`. Keines dieser Geräte-Rohdatenarchive wird nach GitHub veröffentlicht.

## 3. Warum noch kein DMA-ROM-Dump

**Die 20-Bit-ROM-Quelladresse ist hardwarearchitektonisch möglich, aber ein optolinkseitiger Transfer ist damit nicht automatisch sicher oder funktionsfähig.**

1. **DMA0** ist für den realen KM-Bus/UART1-Transmit-Pfad konfiguriert; Schreibzugriffe auf SAR/DAR/TCR/DM0CON/DM0SL könnten die Mastertelegramme stören und fehlende Empfangsantworten/Faults provozieren.
2. **DMA1** ist für das Optolink/UART0-Senden konfiguriert. Ein ROM→UART0-Stream würde genau den Diagnosepfad sabotieren, über den wir die Originalregister wiederherstellen müssten. Die bestehende Host-/systemd-Rückstellung allein kann **Controller-SFRs bei verlorener Optolink-Kommunikation** nicht garantieren.
3. Beide Kanäle sind intermittierend statt konstant DMAE=1. Das macht sie **nicht frei**; Host-P300-Anfragen dauern wesentlich länger als Mikrocontroller-DMA-Takte. Ein kurzer Wert `DMAE=0` reicht nicht als atomare Reservierung.
4. Ein direkter ROM→RAM-DMA-Blocktransfer kann wegen des Quell-/Ziel-Fortschaltlimits nicht allein durch beide Autoinkremente realisiert werden. Ein hypothetischer Einzelworttransfer müsste einen dauerhaft ungefährlichen Zielbereich, einen verifizierten atomaren Servicepfad und einen verlässlichen Rücktransport besitzen.

**Entscheidung:** Keine blinden DMA-/UART-/Interrupt-SFR-Schreibtests auf der produktiven WB2A. Diese Erkenntnisse eröffnen eine technisch reale **Optolink-only**-Architektur, aber kein live-sicheres, jetzt ausführbares Flash-Dump-Verfahren. Für einen praktischen Versuch ist eine **existierende Anwendungs-/Monitorfunktion** zum Synchronisieren des DMAC oder zum kontrollierten ROM-Kopieren weiterhin der beste nächste Gate.

## 4. Softwareabnahme

Erweitert:
- `tools/wb2a-vitotrol-dual-readonly-probe.py`: neue DMA-SFR-Lese-Whitelist und `--dma-only`-Modus.
- `tools/wb2a-vitotrol-dma-rom-occupancy-session.sh`: eigenes, unabhängiges rückstellbares Host-P300-Zeitfenster.
- `tools/wb2a-vitotrol-dma-rom-audit.py`: Offline-Dekodierung der 20-Bit-DMA-Register, Bitbelegung, realer Quellen-/Zieladressen, dynamischer Kanalnutzung und zwingender ROM-Negativbelege.
- `tests/test_wb2a_vitotrol_dual_readonly_probe.py` und `tests/test_wb2a_vitotrol_dma_rom_audit.py`: positive und negative Fixturetests sowie optionale private Rohdatenauswertung.

**Validierung: 649 Tests erfolgreich, 1 optionaler übersprungen**. In `main` und `/opt/optolink` wurde kein neuer Forschungs-Code installiert.

## 5. Konkrete nächste rein softwarebasierte Forschungsarbeiten

A. **VM/Monitor- oder ROM→RAM-Copy-Primitive finden:** Frühere 20C2 RAM-Deskriptoren `0x1DE0/0x1E60/0x3300`, historische KarlKoch-M30612-Optolink-Auslesung, verlorene OpenV-Entwicklertraces und VitoSoft-LDAP-Multi-Request-/RPC-Aufrufe mit sekundärem Payload. Es gibt bislang **keinen verifizierten Kandidaten**, der einen 20-Bit-Quellpointer aktiv verarbeitet.

B. **DMA sicher erkennbar abtrennen?** Nur wenn ein belegter, atomarer Controller-Service einen kommunikationsfreien DMA-Kanal mit bestätigter Controller-seitiger Wiederherstellung bereitstellt; kein 1-Sekunden-P300-Write-Sweep.

C. **Keine falschen ROM-Beweise:** FC03/FC99-High-Adressantworten `5497/5498/0800/4343/1d90` sind historisch schwankend und keine Program-ROM-Bytes. Das aktuell beobachtete `0x5380..0x53FF`-RAM ist 79/79 stabil, enthält aber hochentropische Daten, die **nicht** automatisch freier Scratch-RAM oder ausführbarer Code sind. Kein ungeprüfter Schreibtest dorthin.

**Ziel bleibt:** ausschliesslich über Optolink reproduzierbar echte 20-Bit-Programm-ROM-Bytes auslesen, dann UART1-RX-/Vitotrol-Klasse-`0x11`-Verarbeitung und den Commit nach `0x0A5C` analysieren. Kein Hardware-Plan-B als Voraussetzung.
