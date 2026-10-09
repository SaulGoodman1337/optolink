# Aufgabe 1: echte GFA-P06-Drehzahl, P300-RAM-Strukturen und KM-Bus-/HALL-Denkszenario

**Stand 9.10.2026; Forschungsbranch; PR #46 bleibt Draft.** Hypothesen strikt von Live-Nachweisen trennen. Dies ist Dokumentation, keine Hardwarefreigabe. Aufgabe 2 Vitotrol und Aufgabe 3 Pumpenoverride bleiben nachgelagert.

## 1. Warum der VS1-GFA-Leseweg echte P06-Daten liefert

- Lokal verifizierte Identitaet `20C2`, SW `0103`, GFA P80 `0x20`. VS1-GFA-Leseparameter P06: TX `6B 40 06 01` (GFA_READ, Adresse 0x4006, 1 Byte); Empfaenger meldet einen Rohwert, z. B. `0x53` = 83 und damit `83 × 30 = 2490 U/min`; `FF` ist ungueltig. Weitere getrennte GFA-Parameter sind P09=0x4009 (Modulations-/Ansteuerungssollwert), P87=0x4057 (Diagnostik), P80=0x4050 (Variante).
- VS1 und P300 laufen ueber denselben Optolink-Zugang, aber mit unterschiedlichen Rahmen und GFA-Routingoptionen. Unter P300 funktionieren `FC01 0x55D3/11` (Status) und `FC03` (physischer 32-Byte-RAM-Read). P300 `FC=C9 addr=4050 len=1` erhielt am echten WB2A-Controller die strukturierte Fehlerantwort `code=03 payload=05`. Diese konkrete Anforderung funktioniert nicht; die Bedeutung von `05` ist **nicht herstellerspezifisch belegt**. Es ist kein Beweis, dass *jede* alternative P300-GFA-Operation unmoeglich waere.
- Bei mehreren echten VS1-Referenzmessungen waren P06 und P09 verschieden; P09 ist kein Istdrehzahlersatz. Genauso ist `55D3` ein Status-/Modulationsdiagnoseblock, kein bereits nachgewiesener Tacho.

## 2. Unabhaengige Hersteller-Evidenz: Geblaese ist PWM/HALL, nicht KM-Bus

Die Viessmann-Serviceanleitung fuer **Vitodens 200, WB2A 8,8–26 kW, Ausgabe 10/2006, Dokument 5681 573** belegt auf **Druckseite 105, PDF-Seite 105 (0-basiert 104)** im internen Schaltplan: Bauteil 100 Geblaesemotor, 100A Ansteuerung Geblaesemotor, Leitung zur A1-Grundleiterplatte mit **X8.15 PWM**, **X8.13 HALL**, **X8.12 GND**. Separat auf **Druckseite 107 (0-basiert 106)** fuehrt der externe Schaltplan **KM-Bus 145** an X3.6/X3.7 bzw. weiterem Verbindungspfad. Das ist kein dargestellter Anschluss der Geblaese-Rueckmeldung.

Quelle: https://www.intec-heizung.de/media/pdf/c2/0c/64/Viessmann-Vitodens-200-WB2A-Serviceanleitung.pdf (Seiten 105 und 107). Der konkrete Geraeterevisionsstand ist fuer Arbeiten am Kessel trotzdem gesondert zu verifizieren. Die logische Verarbeitung der HALL-Pulse zum P06-Wert erfolgt in der Brenner-/Regelungselektronik; eine vollstaendige interne Firmware-Datenflusskette ist noch **nicht** rekonstruiert.

**Physik und Protokoll trennen:** PWM ist typischerweise Stellgroesse fuer den Motortreiber, das HALL-Signal typischerweise Drehzahlfeedback (Impulse); das Istdrehzahl-/P06-Uebersetzungsverhaeltnis zu HALL-Impulsen ist fuer diese Platine nicht gemessen. Ein regelungsunabhaengiger, galvanisch isolierter, vom Hersteller/zustaendigen Fachbetrieb sicherheitsgerecht gepruefter *passiver* Hall-Pulszaehler waere ein theoretischer dritter Weg. **Keine Anschluss-/Abgriffanleitung**: heiztechnische Sicherheitsfunktion, Isolations-/EMV-Risiko, keine passive Messung am laufenden Geraet ohne Freigabe.

## 3. Was der 80-Sweep-Datensatz wirklich belegt

Privates Archiv `p300-fullram-run-20261009T083607Z-144293-bundle.tar.gz`, SHA256 `94d5842b6dc5759ecb446a4c617b60b72873b639885d116032f783abdef8431c`. Details/Manifest: [p300-fullram-result-2026-10-09.md](p300-fullram-result-2026-10-09.md).

- Vollstaendig validiert: **51.200/51.200** FC03-Paketreads, 640 feste 32-Byte-Blockadressen von `0x0400` bis `0x53FF`; 1.600/1.600 native FC01/11-Statusframes. **79 qualifizierte COMPLETE-Snapshots** von je 20.480 Bytes (48 OFF, 11 ON, 20 TRANSITION/UNKNOWN). Letzter Sweep #80 enthielt noch alle 640 RAM-Blocks, aber VS1-Reentry-Timeout und daher keine P06-Nachklammer: **PARTIAL**, nicht als stabiles Vergleichsbild zugelassen. Originaldienst/6 Units wurden danach wiederhergestellt.
- 3.532 echte VS1-P06-Reads in Referenzfenstern, 3.527 gueltig (5 × FF); 2.488 Null, 1.039 positiv, 35 verschiedene positive RPM-Niveaus bis 4.440 U/min. **Aber alle 11 stabil positiv geklammerten kompletten RAM-Snapshots haben nur den einen Level `0x53` = 2490 U/min.** Zeitliches Vorher/Nachher garantiert keine konstante Motordrehzahl waehrend der 107,679 s Median-Sweepzeit.
- Byte-Variabilitaet ueber die 79 vollstaendigen kanonischen Dumps: **18.955 von 20.480 Adressen waren konstant, 1.525 variabel**; 478 hatten genau zwei Werte, 1.047 mindestens drei. Stark veraenderlich sind etwa die 256-Byte-Seiten `0x0900–0x09FF` (119), `0x0A00–0x0AFF` (127), `0x0B00–0x0BFF` (105), `0x0C00–0x0CFF` (132), `0x1A00–0x1AFF` (106). Ab `0x2400` bis `0x53FF` keine Aenderung zwischen den 79 Snapshots. Konstant heisst **nicht** unbelegt, ROM oder geräteunwichtig.
- In allen 48 OFF-/11 ON-Klammern: **0 Byteadressen mit direkt 00→53**; keine direkten 0→2490-U/min-16/32-Bit-Le-/Be-Speicherrepräsentationen. Aber 30 Adressen mit stabilem 00→einem konstanten Nichtnullwert und insgesamt 34 verschiedene exakt stabile Zweizustandswerte; dies sind primaere *Zustands-/Staging-Korrelationen*, **keine** direkten Drehzahlnachweise.

### Doppelter Status-/Prozessspeicher

| Speicher | OFF-Wert (48/48) | ON bei P06=53 (11/11) | Beobachtung |
|---|---|---|---|
| `0x0F20` | `00` | `54` | Exakt identisch mit `0x1C76` in **79/79** Dumps; nicht P06=53 |
| `0x1C76` | `00` | `54` | Zweite Kopie/gleichlaufende Zustandsstruktur wahrscheinlich, Semantik offen |
| `0x0F22` | `00` | `26` | In enger Nachbarschaft zu weiterem statusaehnlichen Byteblock |
| `0x0F27` | `01` | `21` | Spiegelt bei stabilen Zustaenden natives FC01-Statusbyte 5 (Flame-Flag-Bereich) |
| `0x0F28` | `00` | `0B` | Spiegelt `0x1C7D` in **79/79** Dumps |
| `0x0F29` | `00` | `62` | Spiegelt `0x1C7E` in **79/79** Dumps und natives FC01-Statusbyte 7; bei allen 79 Snapshots wenigstens ein Statuscheckpoint passend |

Weitere gleichlaufende Felder befinden sich bei `0x1B67/0x1B7A/0x1B8D/0x1BA0/0x1BB8`; die wiederkehrenden Abstaende/Statuswerte legen eine wiederholte interne Datenstruktur nahe, ihre Laenge und Funktion sind aber **nicht** belegt. Auch bekannte Optolink-TX/RX-Ringpuffer koennen scheinbar passende GFA-Antworten enthalten, ohne einen vom Optolink-Abfrageweg unabhaengigen GFA-Sensor nachzuweisen.

**Neue strukturelle Einordnung:** Dass `0x0F20` und `0x1C76` sogar in saemtlichen 20 transienten Vollsweeps exakt gleich sind und umgebende Bytes statusartig kopiert erscheinen, spricht eher fuer doppelte Diagnose-/Zustandsstroeme oder Header als fuer zwei eigenstaendige Tachowerte. Die Alternativhypothese `0x54 = P06+1` kann ohne zweiten stabil positiven P06-Wert nicht hinreichend widerlegt/unterstuetzt werden. Eine numerische Korrelation alleine genuegt **nicht**.

## 4. KM-Bus als spaetere Option – genau abgrenzen

Der KM-Bus haengt nach WB2A-Schaltplan **separat** am externen Anschluss **145**; die Geblaese-HALL-Leitung geht ueber X8.13 in die A1-Grundleiterplatte. Daher **keine Direktannahme**, dass P06 als KM-Bus-Telegramm verkehrt. Eine prinzipielle interne Uebertragung von GFA-Status via KM-Bus waere erst nach physischer/protokollarischer Evidenz relevant.

Es gibt aber bereits **positiven P300-Mitschnitt-Indizienbeweis fuer KM-Bus-Master-TX-Softwarepuffer**: Historische read-only FC03-Samples bei SRAM `0x161A/0x161B` zeigen gueltige CRC16/Kermit-Telegramme der Klassen `0x11` (Vitotrol-Discovery/F8..FB), `0x04`, `0x20` und FF-Broadcast. Sie werden ueber DMA0 → UART1 `U1TB @ 0x03AA` gesendet, dokumentiert in [Master-TX-KM-Bus-Audit](p300-kmbus-vitotrol-master-tx-2026-10-09.md). Es sind **gesampelte Controller-Sendepuffer**, *keine* drahtseitig mitgeschnittenen kompletten KM-Bus-Verkehrsstroeme.

**Noch nicht belegt:** UART1-Empfangs-Ringpuffer, KM-Bus-Slaveantworten, angeschlossene Fernbedienung, KM-Bus-Leserechte fuer beliebige Datenpunkte, echte P06-Verfuegbarkeit. Das UART1-RX-Datenregister `U1RB @ 0x03AE` ist ein peripheres Register, das beim Lesen RX-Flags/Empfangszustand beeinflussen kann: **nicht live probeweise lesen**, kein blindes SFR-/ISR-/Speicher-Scanning. Statische Firmware/INTB/Vektor-20-/RX-Buffer-Nachweise zuerst, danach eng begrenzte passiv read-only Pruefung.

Eine **physische** KM-Bus-Aufzeichnung waere konzeptionell separat: freigegebenes galvanisch sicheres, hochohmiges Sniffing an geeignetem Bus-Zugang, mit Analyse beider Richtungen, Adress-/CRC16-/Timing-Parsen und ohne Businteraktion. Keine Anschlussanleitung, bevor Hardwarestand, Spannungspegel, Schutzkonzept und Fachfreigabe geklaert sind.

### Hypothesen-Gates und Aufgabenprioritaet

| Hypothese | Erwarteter Beweis | Aktueller Status |
|---|---|---|
| H1: P300-RAM enthaelt P06 (anders kodiert) | mindestens 2 verschiedene stabile positive VS1-P06-Klammern plus skalierte, frische, vom P09/FC01/Optolink abgrenzbare RAM-Payload | **OFFEN**, neuer kurzer P06-Fokuslogger laeuft / kein Ergebnis der Liveaufnahme hier behauptet |
| H2: KM-Bus liefert eigenstaendige Geblaese-HALL-/RPM-Telegramme | physisches Fan-Bus-Protokoll oder gelaesene GFA-Antwort mit eigenstaendig validierter RPM-Semantik | **KEIN BELEG, indirekter Weg unwahrscheinlich**: Herstellerbild zeigt PWM/HALL separat |
| H3: P300 ermoeglicht passives KM-Bus-TX-Tracking | zeitgestempelte gueltige Master-Telegramme in Controller-TX-RAM | **POSITIV fuer Master-TX-Sampling**, kein RX/On-Wire-Livestream |
| H4: P300-Software kann UART1-RX-Antworten passiv aus belegtem Haupt-RAM lesen | offline rekonstruierter UART1-RX-ISR-/Pufferpfad und validierte echte Slaveantwort | **OFFEN**; kein U1RB-SFR-Liveread |
| H5: Alternative Hall-Pulsmessung ausserhalb Optolink | fachgepruefte, galvanisch sichere passive Messung mit plausibler Pulse/Umdrehung-Kalibrierung, keine Stoerung der sicherheitsrelevanten Geblaeseregelung | **REINE ARCHITEKTURIDEE**, keinerlei Anschluss-/Hardwarefreigabe |

**Priorisierung:** Aufgabe 1 vollstaendig mit echtem P06 und allen MQTT/HA/Service-/Schreibfunktionen fertigstellen. Wenn kein unabhaengiger P300-P06-Pfad nachgewiesen wird, die Single-Owner-Hybridarchitektur P300 plus gezielte echte VS1-GFA-Lesefenster gegen den Frische-/Latenzhaushalt pruefen. **KM-Bus-RX/Vitotrol-Hypothesen als spaeteres Denkszenario fuer Aufgabe 2 dokumentiert, aber noch keine Task-2-Implementierung starten.** Aufgabe 3 Pumpenoverride erst danach. Produktives `/opt/optolink` unveraendert lassen.
