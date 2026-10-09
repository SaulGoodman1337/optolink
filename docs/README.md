# Dokumentationsindex

- [Naechster P300-Temporal-Logger: natuerliche Brennerzyklen, RAM-Spiegel, gestufte 1,5s/0,5s-Abtastrate und sichere VS1-Wiederherstellung (9.10.2026)](p300-temporal-runbook-2026-10-09.md) – erst NACH Fokus-Logger-Recovery+Privatarchiv, kein automatischer Start, keine P06-Sensorfreigabe.

- [GFA unter P300: tiefe Vitosoft-, Protokoll-, Katalog- und Internetnachpruefung (9.10.2026)](p300-gfa-p300-quellennachpruefung-2026-10-09.md) – C9/Sequenz-Konflikt, VS1/VSKO-Sonderrouting, autonomer Status und verbliebene read-only RPC-/Virtual-Diagnose-Hypothesen; keine Produktionsfreigabe.

- [P06 vs. P300, RAM-Muster und HALL/KM-Bus-Hypothesen (9.10.2026)](p300-p06-hall-kmbus-hypothesen-2026-10-09.md) – echte GFA-P06-Quelle, redundante Statusspeicher, separater HALL/PWM-Geblaesepfad und spaetere KM-Bus-RX-Denkoption (keine Produktionsfreigabe).

### Naechste Stufe vorbereitet: kurzer P06-Fokuslogger (noch KEIN Live-Test)

Nach dem [validierten Voll-RAM-Ergebnis](p300-fullram-result-2026-10-09.md) wurde im Forschungsbranch der [gezielte P06-Fokuslogger](../tools/wb2a-p300-p06-focus.py) mit [separatem deutschen Runbook](p300-p06-focus-runbook-2026-10-09.md) implementiert. Er erfasst nur sechs historisch erfolgreiche FC03/32-Bloecke um **0x0F20 und 0x1C76** samt Status-Negativkontrolle 0x0F29/55D3-Byte7. Jede Aufnahme hat echte VS1-P06/P09/P80/P87-Referenzen vor und nach einem kurzen P300-Fenster, zwei Roh-RAM-Runden und gepinnten Read-only-Systemd-Lifecycle mit Original-VS1-Restore. Ein fehlgeschlagener Return-Handshake wie bei Snapshot 80 erzeugt **PARTIAL**, nie einen fingierten RPM-Wert.

**Kein P06-Sensorbeweis und keine Produktionsfreigabe.** Das naechste Datenziel sind mindestens **zwei verschiedene stabile positive echte P06-RPM-Niveaus**. Die Messung startet nicht automatisch; der Anwender fuehrt nach CI-PASS den separaten Startwrapper in der Optolink-LXC aus. Falls die Kandidaten bei geaenderten echten P06-Drehzahlen unveraendert bleiben, ist die direkte RPM-Alias-Hypothese zu verwerfen und die **Single-Owner P300+VS1-GFA-Hybridarchitektur** weiter zu untersuchen. Aufgabe 2/3 bleiben gesperrt; PR #46 nicht mergen.


## Aktualisierung 9.10.2026 – Voll-RAM-Experiment BEGRENZT ABGESCHLOSSEN

**Der 20-KiB-P06-geklammerte Logger wurde bereits real ausgefuehrt; den gleichen Vier-Stunden-Lauf NICHT erneut starten.**
[Abschlussbericht und Integritaetsanalyse](p300-fullram-result-2026-10-09.md) ·
[maschinenlesbare Evidenz](evidence/p300-fullram-p06-vs1-result-2026-10-09.json).

- **79 COMPLETE, 1 PARTIAL** (Nr. 80 mit allen 640 RAM-Reads, jedoch ohne gueltige nachfolgende P06-Klammer), **51.200/51.200** FC03- und **1.600/1.600** FC01-Frames gueltig; alle 176 Manifestdateien korrekt. 48 stabile OFF-, elf stabile ON-Snapshots. Alle elf ON-Snapshots lagen jedoch nur bei **P06=0x53 / 2.490 U/min**.
- Kein direkter 00→53-P06-Rohwert- oder 0→2490-U/min-16/32-Bit-Spiegel im 20-KiB-RAM. **0x0F20 und 0x1C76** zeigen 00→54, sind aber **nicht** als echte Drehzahl bewiesen. 0x0F29 spiegelt FC01-Statusbyte 7.
- Ein Timeout beim **P300→VS1-Identitaetswechsel nach dem vollstaendigen RAM-Scan 80** beendete die Messung. Recovery stellte alle sechs zuvor aktiven Units und gueltige MQTT-GFA P80/P06 her. **HA-Entity-Frische nicht nachgewiesen.**
- **Naechster Aufgabe-1-Schritt:** gezielte kurze P06-geklammerte, read-only RAM-Fokusmessungen bei nachgewiesenen **verschiedenen positiven RPM-Niveaus**. Bei weiterhin fehlendem unabhaengigem Sensor: gemeinsame serielle P300/VS1-Owner-Architektur mit echten VS1-GFA-P06-Abfragephasen und nachgewiesener Gesamtfunktionsparitaet.
- PR #46 bleibt **Draft und ungemergt**, produktiver VS1-Betrieb unveraendert. Keine Vitotrol-/Pumpen-Nebenprojekte.


Dieser Ordner trennt produktive Betriebsdokumentation von der Forschung im Branch `optolink-p300-migration`.

## P300: aktueller Stand vom 9. Oktober 2026

**NEU - abgeschlossener Deep-Logger vom 9.10., Messdaten und Stop-Fix:**
55 min 34 s innerhalb einer Sitzung, **2 komplette Flammenbitfenster**,
2.680 echte VS1-Referenzrunden (5.360 P06-Reads; 1.836 gueltig
mit RPM>0 bis 4.590 U/min), 1.769 P300-Runden, 52 Wechsel
und **8.256 von 8.256 bytegenau gepruefte P300-Leseantworten**.
In 2.593 P06-stabilen VS1-Klammern differierten P09
und P06 **108-mal**; P09 bleibt kein Istwert.
In 15 P06=0- und sieben P06~=83-geklammerten P300-Phasen
**kein direkter Rohbyte-/16-Bit-RPM-Alias** in den acht
abgefragten Bloecken. Die letzte Stop-Meldung
`VS1_LINK_RESTORE=NOT_VERIFIED` wurde auf **SIGTERM
waehrend laufender P10-Antwort** zurueckgefuehrt;
`ExecStopPost` stellte alle sechs produktiven Units
wieder her und verifizierte per MQTT P80=20/P06=00.
Kein Produktivausfall daraus nachgewiesen;
HA-Entity-Frische nicht separat kontrolliert.
Der Signalhandler ist im **neuen Branch-Code** nun
auf Runden-Grenzen verschoben; Vermeidung von
neuer EOT-Synchronisierung bei bereits aktiver
VS1-Sitzung; **32 Offline-Tests PASS**.
**Alten identischen Logger nicht wiederholen.**
[Kompletter Ergebnisbericht](p300-deep-result-2026-10-09.md),
[abgeleitete Provenienz](evidence/p300-deep-vs1-p06-ram-result-2026-10-09.json).
Naechster P06-Quellentest: nur P06-vor-/nach-geklammerte
20-KiB-Physical-RAM-Dumps ueber den zuvor schon
gelesenen Bereich 0x0400..0x53FF, danach
unabhaengige RPM-Frische/Quellbeweispruefung.
Vitotrol (Aufgabe 2) und Pumpenoverride (Aufgabe 3)
bleiben nachgelagert.

**VERBINDLICHER ARBEITSAUFTRAG (9.10.2026): P300-Aufgabe 1 zuerst.**
Vollstaendige Migration aller heute produktiven VS1-/MQTT-/HA-Funktionen
einschliesslich der ECHTEN GFA-P06-Istdrehzahl; kein P09- oder
55D3-Steuerfeld als Drehzahlersatz. **Vitotrol ist erst Aufgabe 2
nach erfolgreicher P300-Migration und dann ein getrennter Branch;
Pumpenoverride folgt als Aufgabe 3.** Bereits vorhandene Vitotrol-
Quellenanalysen bleiben Archivbelege, sind kein aktueller Arbeitsauftrag.

**NAECHSTER KONKRETER SCHRITT – neuer 4h/6h Deep Logger:**
[Ein-Befehl-Runbook](p300-deep-logger-runbook-2026-10-09.md).
Er misst erstmalig innerhalb EINER betreuten Sitzung wiederholte
echte VS1/GFA-P06-Referenzen (P06/P09/P87/P10/P84/P80)
**und** abwechselnd P300-Nativstatus, UART1-DMA und acht
historisch belegte read-only Status-/RAM-Bloecke,
mit praezisen Zeitstempeln und eventgesteuerten
Phasenwechseln. Automatisches Ende nach 1-8h
(Default 4h), originaler VS1-Service-Restore,
MQTT-P80/P06-Gesundheitscheck und genau ein tar.gz.
**Waehrend des Laufes ist die produktive
HA-/MQTT-Optolink-Telemetrie wie beim Nachtlauf pausiert.**
Der Logger selbst ist kein produktives P300-Profil;
ein P06-Alias bleibt ohne Nachweis gesperrt.

[**Komplettstand Aufgabe 1 samt Funktions-/Freigabematrix**](p300-task1-evidence-and-parity-2026-10-09.md).
Keine neue Vitotrol-/Pumpenforschung vor Abschluss Aufgabe 1.
Kein Merge von Draft-PR #46.

**NEU - Vitotrol-Suchtelegramme in der abgeschlossenen Nachtmessung:**
Bei 0x161A im UART1-Master-TX-RAM wurden fuer **KM-Bus-Klasse 0x11**
an Slots 1 und 2 jeweils die exakt OpenV-kompatiblen
**0x33/F8/04-Identitaetsabfragen** nachgewiesen:
27+27 CRC-gueltige Pufferansichten, verteilt ueber
19+20 nichtbenachbarte Samplefenster.
Klasse 0x20/Slot 0xEE zeigt ebenfalls die im
historischen OpenV-Referenzsystem dokumentierte B3-Form.
**Nur Master-TX, keine Slaveantwort, keine angeschlossene
Vitotrol, kein P06-Alias und kein neues Live-RAM-Gate
bestaetigt.**
[Quellengestuetzter Slotvergleich](p300-kmbus-vitotrol-master-tx-2026-10-09.md),
[abgeleitete Evidenz](evidence/p300-kmbus-vitotrol-master-tx-2026-10-09.json),
[Offline-Decoder](../tools/audit-kmbus-master-tx.py) und 12 Tests.
Der naechste offene Beweisschritt ist die **UART1-RX-Pufferzuordnung
aus statischer Firmware-/ISR-Evidenz**, nicht ein erneuter Nachtlauf.

**NEU - abgeschlossener UART1-P300-Nachtlauf mit KM-Bus-TX-Nachweis:**
Der Betreiber hat die detached systemd-Aufnahme geordnet beendet;
Original-VS1, P80 und P06 wurden erfolgreich zurueckgeprueft.
Das private Archiv enthaelt 12.938 Runden mit **51.752/51.752**
bytegenau validierten P300-Leseantworten und 155.294 TX/RX-Spureintraegen.
Bei 0x161A liegen KM-Bus-formatierte UART1-TX-Frames mit
**12.573/12.938 gueltigen CRC16/Kermit-Pufferansichten**;
ein 22-Byte-Broadcast enthaelt per BCD kodiertes Datum/Uhrzeit
(55 natuerliche Zeitupdates). Der Drehzahl-Istwert P06 und
der UART1-RX-/GFA-Datenweg sind damit **nicht** nachgewiesen.
Separat war das bekannte Verriegelungsbit rund 7 h 37 min gesetzt,
bevor drei natuerliche Flammenbitfenster beobachtet wurden.
Keine dokumentierte Stoerungsursache und keine Verbindung zum
historisch bekannten Geblaeseanlaufproblem nachgewiesen.
**Nicht den gleichen Nachtlauf wiederholen.**
[Komplette technische Nachtauswertung](p300-uart1-overnight-result-2026-10-09.md),
[reduzierte Evidenz](evidence/p300-uart1-overnight-result-2026-10-09.json),
[rein lokaler Bundle-Auditor](../tools/audit-uart1-overnight-bundle.py)
und neue Offline-CI. Keine HA-/RPM-Aliasfreigabe oder RAM-Writes.

**Historisch: Vorbereitung des inzwischen abgeschlossenen DMA0-Sammeltests:**
Der alte, bereits dokumentierte 154-Messpunkt-DMA0-Watch weist den
UART1-TX-Quellzeiger **dynamisch** im Bereich `0x161B..0x1622` nach;
die damalige SFR-Aufnahme enthaelt `U1C1=0x07`
(**UART1 TX- und RX-Hardware eingeschaltet**, noch nicht GFA zugeordnet).
Das hochgeladene 25x64-Byte-Archiv zeigt TX-RAM-Muster mit 6 Zustaenden,
aber keinen Flammenzyklus. Ein neuer gebuendelter, **explizit auszufuehrender**
P300-Read-Only-Test erfasst Status, **DMA0-Quellzeiger/TCR** und denselben
64-Byte-RAM-Bereich **in einer** betreuten Sitzung bis max. 600 s,
mit automatischem Ende nach natuerlichem Flammenzyklus plus Nachlauf.
Er liest **NICHT** das moeglicherweise zugriffssensitive UART1-RX-Datenregister.
Ein-Befehl-Wrapper, Offline-CI, Protokoll-Allowlist, Original-VS1-Restore,
MQTT-P80/P06-Nachkontrolle und automatischer Export eines einzigen
privaten Archives sind vorbereitet: [Runbook und Datenflussnachweis](p300-uart1-dma0-natural-cycle-2026-10-08.md).
**P06-Ist-Drehzahl und UART1/GFA-Kopplung weiterhin UNBEWIESEN.**


**AKTUELL: UART1-Fokuslauf erfolgreich abgeschlossen.** Der Betreiber
hat den 60-s-P300-FC03-Lauf mit 25 Status-/RAM-Runden
bereits erfolgreich ausgefuehrt. 15 RAM-Bytes wechselten
in fuenf Ereignissen zwischen sechs erfassten Speicherzustaenden;
die historische UART1-DMA0-Ankeradresse `0x161B`
selbst wechselte nicht. Status `55D3[7]`, P06
und P09 blieben in diesem Fenster `00`.
VS1 und alle aktiven Dienste wurden laut Mess-/
Restore-Protokoll erfolgreich wiederhergestellt.
Das **vollstaendige nachgereichte Originalarchiv** ist jetzt unabhaengig
verifiziert: **77/77 P300-Antworten** mit gueltiger Adresse, Laenge,
Pruefsumme und Sample-Payload, **143/143 archivierte Tests**,
post-Restore MQTT-GFA-P80=20/P06=00 erfolgreich.
Der RAM-Befund wird **nicht** mit GFA-P06 gleichgesetzt; vollstaendiger
Status Byte2 wechselte B1->B2, P87-Byte7 blieb 00.
**Keine UART1/GFA-Anbindung und kein P06-RPM-Alias nachgewiesen.**
[Hardwareauswertung und vereinheitlichter Batchablauf](p300-uart1-live-result-and-batch-2026-10-08.md)
sowie [abgeleitete Evidenz](evidence/p300-uart1-focus-result-2026-10-08.json).

**Weniger Copy/Paste:** Fuer den naechsten Datenbatch
gibt es jetzt `tools/wb2a-research-batch.sh`, das den
ausschliesslich experimentellen Branch ohne lokale Aenderungen
per Fast-Forward aktualisiert, die Offline-Tests laeuft,
die vorhandene UART1-Messung validiert,
den laufenden Original-VS1-Dienst kontrolliert und
**ein einziges privates tar.gz-Ergebnisarchiv** erzeugt.
Der bereits erfolgreiche identische UART1-Hardwaretest
wird **nicht** automatisch wiederholt. Kein RAM-Write,
kein Produktivmerge.

**NEU - P06-Istdrehzahl unter P300 (Source-First-Abschluss):**
Ein weiterer modellgebundener Vergleich oeffentlicher VDensHO1-Kataloge
und alle elf Bytes der bereits hochgeladenen 180 P06/P09-VS1-Paarmessungen
liefern **keinen validierten, unabhaengigen P06-Istwert**. `0x0B1E`
gehoert zu VBC550S/SC100, `0x1A53` zum V200WO1C-Modell, `0x7660`
zur Umwaelzpumpe. Im Statusblock sind Byte0/Byte9 Ansteuer-/Modulationswerte;
Byte1/Byte2 bleiben sogar in allen 154 stabilen P06=00-Runden ungleich null.
**Keine neue Leseadresse und kein RPM-Alias freigegeben.**
[Quellenvergleich und naechstes RAM-Evidenz-Gate](p300-fan-actual-source-screen-2026-10-08.md)
mit [abgeleiteten Kennzahlen](evidence/p300-fan-actual-source-screen-2026-10-08.json)
und Offline-Testwerkzeug. Kein neuer Thermenzugriff, kein Aendern der Produktion.

**Ziel:** Kontrollierter RAM-Zugriff ohne Verlust bestehender HA-/Optolink-Funktionen, als Grundlage fuer Pumpen- und Vitotrol-Forschung. **Keine Produktionsfreigabe.**

**Aktueller Hardwarebefund:** Die erste direkte Same-Session-Messung von GFA-P06/P09 gegen den nativen 55D3-Block ist abgeschlossen: **180 von 180 Runden** stimmen in `pairs.jsonl` und `summary.json` ueberein. P06 war in 171 Runden stabil, aenderte sich aber in neun Klammern; P09 war in allen 180 Klammern stabil. Die Aufnahme enthaelt 24 Flammenbit-Samples und eine natuerliche Brennerphase mit Anlauf, Abwaertsrampe, Modulationsboden und Abschalten. **Der entscheidende Gegenbeleg fuer einen einfachen P06-RPM-Alias:** Nach dem Flammenbit-Ende ist P09=00 und P06 sinkt innerhalb einer Klammer von 0x52 auf 0x1D, waehrend Byte9 im Statusblock noch 33 zeigt.

**Einordnung:** Status-Byte7 ist zuvor als dynamischer P87-Kandidat unter P300 belegt. Byte0/Byte9 sind Ansteuer-/Modulationswerte, **keine bewiesene Ist-Geblaesedrehzahl**. Auch P09 ist nicht als vollwertiger 1:1-Alias freigegeben. Eine beschraenkte quellenbasierte Suche nach einem unabhaengigen P06-Istwert hat deshalb Vorrang vor weiteren identischen 600-/900-Sekunden-Paarmessungen oder RAM-Schreibexperimenten.

**Dokumentation und Reproduktion:** [180-Runden-Geraeteauswertung](p300-gfa-native-pair-result-2026-10-08.md), [abgeleitete Evidenz](evidence/p300-gfa-native-pair-result-2026-10-08.json), `tools/audit-gfa-native-pairs.py` (nur offline), 11 Regressionstests. Private Rohzeitreihen sind **nicht** im oeffentlichen Repository. VS1 bleibt produktiv, **keine P300-Migration oder Pumpen-RAM-Freigabe**.

### Abgeschlossene Bausteine

- C9/P80 direkt unter P300 abgewiesen; Original-VSKO verwendet VS1/6B. Kein erneuter identischer CANARY.
- Zwei-ENQ 6,863 s, Ein-ENQ 4,610 s, Idle-ENQ 5,628 s. Idle als Beschleunigungsvariante geschlossen; keine Wiederholung.
- 581 exakte Profil-Events / 362 Adressen geprueft. Keine benannte virtuelle P06-Istdrehzahl; 7650 ist Kennung, nicht frischer Kommunikationsnachweis.
- P87-VS1-Vergleich: 59 stabile Matches und ein uneindeutiger Uebergang. P300-only: 300 und 600 s mit spaeten Aenderungen ohne externe GFA-Reads; danach VS1/GFA wieder geprueft.
- Die neue Vollauswertung bestaetigt diese Befunde und nutzt zusaetzlich alle elf Bytes. P06/P09, genaue P87-Latenz und dauerhafter Pumpen-Override bleiben offen.

| Dokument | Bedeutung |
| --- | --- |
| [Deep-Logger 9.10.: 5.360 GFA-P06 und 8.256 P300-Reads](p300-deep-result-2026-10-09.md) | **Aktuelles Ergebnis:** zwei Brennerzyklen, P06/P09 unterschieden, kein direkter RPM-Alias; Worker-Stop-Race gefunden und gefixt |
| [Abgeleitete Deep-Logger-Evidenz](evidence/p300-deep-vs1-p06-ram-result-2026-10-09.json) | Quelle SHA, Trace/Checksums, echte P06-Baende, zeitliche Zustandsklammern, Restore-Evidenz |
| [Aufgabe 1: gesicherte Fakten und 100-Prozent-VS1-Paritaetsmatrix](p300-task1-evidence-and-parity-2026-10-09.md) | **Aktueller Masterstand** fuer alle bisherigen Produktionsfunktionen, offenen P06-Beweis und Reihenfolge 1/2/3 |
| [Ausfuehrbarer 4h/6h Deep Logger mit Real-P06](p300-deep-logger-runbook-2026-10-09.md) | **Jetzt starten:** VS1/GFA-P06-P09-P87 mit P300-FC01-/FC03-RAM-Fenstern, geordneter systemd-Stopp und Ein-Archiv-Upload |
| [Vitotrol KM-Bus Klasse 0x11 Master-ID-Abfragen](p300-kmbus-vitotrol-master-tx-2026-10-09.md) | **Neuster Fortschritt:** CRC-validierte Slot-1-/Slot-2-Anfragen, exakt OpenV, UART1-Empfang und Slaveantwort weiterhin offen |
| [Vitotrol-TX-Quellenaudit](evidence/p300-kmbus-vitotrol-master-tx-2026-10-09.json) | Privatarchiv-SHA, 54 CRC-gueltige Samples, 39 Beobachtungsfenster, klare Nichtfreigaben |
| [Abgeschlossener 9-h-P300-Nachtlauf: KM-Bus TX und GFA-Verriegelung](p300-uart1-overnight-result-2026-10-09.md) | **Aktueller Befund:** 12.938 Samples, 51.752 Rohantworten, CRC-KM-Bus und BCD-Zeit, 3 Flammenfenster nach Verriegelung |
| [Abgeleitete Nachtlauf-Evidenz](evidence/p300-uart1-overnight-result-2026-10-09.json) | Archiv-SHA, TX/RX-Integritaet, Lockout-, UART1- und KM-Bus-Kennzahlen, **kein P06-Alias** |
| [UART1 DMA0/RAM/native Status: Natuerlicher Zyklus in einem Batch](p300-uart1-dma0-natural-cycle-2026-10-08.md) | **Historischer, bereits abgeschlossener read-only-Lesetest:** dynamischer DMA0-TX-SAR0/TCR, 64 RAM-Bytes, natuerliche Flammenbit-Sequenz, VS1-Rueckkehr und ein Archiv |
| [UART1: Hardwareergebnis und Ein-Befehl-Batch](p300-uart1-live-result-and-batch-2026-10-08.md) | **Aktuell:** 25 verifizierte Runden, 15 geaenderte RAM-Bytes, keine RPM-Freigabe, einheitlicher Datenexport |
| [UART1: abgeleitete physische Lesemessung](evidence/p300-uart1-focus-result-2026-10-08.json) | Beobachtungsdauer, Trace-Allowlist, Werte-/Adressdelta und Restore-Befund; kein privater Volldump |
| [Abgeschlossener UART1-P300-RAM-Fokus](p300-uart1-p300-focus-runbook.md) | Historischer einmaliger 60-s-Geraeteversuch vom 8. Oktober; nicht unveraendert wiederholen |
| [UART1/Optolink Datenfluss aus alten Forschungsergebnissen](p300-uart1-gfa-dataflow-offline-2026-10-08.md) | DMA0-Quellpointer ist kein P06-Istwert; Offline-Auditor fuer vorhandene Dumps |
| [P06-Istdrehzahl: modellgebundener Quellenaudit](p300-fan-actual-source-screen-2026-10-08.md) | **Aktueller Stand:** 11 Statusbytes, auszusondernde fremde Leseadressen, naechstes RAM-Evidenz-Gate |
| [Fan-Quellenaudit-Evidenz](evidence/p300-fan-actual-source-screen-2026-10-08.json) | SHA256-gepinnte private Quelle, Modellgrenzen, Bytekennzahlen, keine RPM-Freigabe |
| [P06/P09 gegen 55D3: 180-Runden-Ergebnis](p300-gfa-native-pair-result-2026-10-08.md) | **Aktueller Einstieg:** kein nativer P06-Istalias, voneinander getrennte Soll-/Istwerte, beobachtete Brennerphase |
| [Abgeleitete P06/P09-Evidenz](evidence/p300-gfa-native-pair-result-2026-10-08.json) | Datei-Hashes, Paarzaehlung, Statusfenster, zehn ausgesuchte Gegenproben |
| [Vollmessungen und Byteaudit](p300-full-status-byte-audit-2026-10-08.md) | Historisch: 807 P300-Statusantworten, drei kurze Flammenbitfenster und Quelle der Anschlussmessung |
| [Durchgefuehrter P06/P09-MQTT-Vergleich](p300-gfa-native-pair-runbook.md) | Historischer, bereits abgeschlossener lesender VS1-Ablauf; nicht ohne neue Fragestellung wiederholen |
| [Maschinelle Vollauswertung](evidence/p300-full-status-byte-audit-2026-10-08.json) | Hashes, Antwortpruefungen, Bytebereiche und beobachtete Bitfenster |
| [P300-only-Konsolenbefund](p300-p87-p300-only-result-2026-10-08.md) | Historischer Bericht vor Uebergabe der nun ausgewerteten Originaldateien; kein erneuter Exportauftrag |
| [P300-only-Konsolenevidenz](evidence/p300-p87-p300-only-result-2026-10-08.json) | Beide damaligen Konsolensummen und Nachkontrollen |
| [Getesteter P300-only-Ablauf](p300-p87-p300-only-runbook.md) | Durchgefuehrter Statusversuch; nicht fuer die bereits beantwortete Frage wiederholen |
| [Dynamischer P87-VS1-Vergleich](p300-p87-vs1-result-2026-10-08.md) | 59 Matches, Uebergangsgrenze und GFA-Nachkontrolle |
| [P87-VS1-Konsolenevidenz](evidence/p300-p87-vs1-result-2026-10-08.json) | 60 fruehere Vergleichszeilen |
| [GFA-Quellenabgleich](p300-gfa-source-candidates-2026-10-08.md) | Profilzuordnung und Herkunft der Kandidaten |
| [Quellenevidenz](evidence/p300-gfa-source-audit-2026-10-08.json) | Hashes und kleine Metadatenableitungen, keine privaten Volltabellen |
| [Historischer P87-MQTT-Test](p300-p87-mirror-runbook.md) | Bereits ausgefuehrter P87-Vergleich |
| [Idle-ENQ-Ergebnis](p300-idle-enq-result-2026-10-08.md) | Kein Geschwindigkeitsgewinn, Zweig geschlossen |
| [Idle-Messwerte](evidence/p300-idle-enq-result-2026-10-08.json) | Nutzertranskript und Berechnungen |
| [Historischer Idle-Test](p300-idle-enq-comparison.md) | Verweis auf getestete Fassung |
| [Ziel und Ein-ENQ-Ergebnis](p300-goals-and-single-enq-result-2026-10-08.md) | Anwendungsziele und Zeitgewinn |
| [Zwei-ENQ-Basis](p300-handover-baseline-result-and-single-enq.md) | Historische Vorbereitung und Auswertung |
| [Zwei-ENQ-Messwerte](evidence/p300-handover-baseline-2026-10-08.json) | Basisdatensaetze |
| [Historischer Basistest](p300-handover-baseline-runbook.md) | Unveraendertes Original ueber Commit |
| [Direkte VSKO-Quellenpruefung](p300-gfa-host-trace-2026-10-08.md) | C#-/IL-Befehlsabbildung |
| [Fork-/GFA-Optionen](p300-fork-switching-gfa-options-2026-10-08.md) | Forschungsentwurf, offene Alternativen |
| [Umschalt-Quellenaudit](p300-switching-source-audit-2026-10-08.md) | Zeitablauf, Quellen- und Messgrenzen |
| [C9-Hardwarebefund](p300-gfa-c9-hardware-rejection-2026-10-08.md) | Konkreter negativer Befund |
| [Migrationsplan](p300-migration.md) | Historischer Kandidat, Freigaben geschlossen |
| [Historischer CANARY](p300-trial-install-rollback.md) | Nicht unveraendert wiederholen |
| [Hydraulikmatrix](wb2a-topology-hardware-matrix.md) | Reale Anlage, getrennt von Protokollforschung |

Originalarchive und private Quellen bleiben ausserhalb dieses oeffentlichen Dokumentationsbestands; publiziert sind abgeleitete technische Ergebnisse und eigene Werkzeuge. Bestehende Produktion, bisherige Prober, Installer, HA-Profil und Updatekanal bleiben unveraendert.

## Einstieg in die übernommene Produktionsdokumentation

| Dokument | Wann lesen? |
| --- | --- |
| [architecture.md](architecture.md) | Als Erstes: Komponenten, Datenfluss, Dienste und Sicherheitsgrenzen |
| [operations.md](operations.md) | Beim Betrieb: Update, Status, Logs, Clock-Sync, Fehlerdiagnose |
| [home-assistant.md](home-assistant.md) | Bei HA-/MQTT-/Dashboard-Änderungen |
| [anlagenschema.md](anlagenschema.md) | WB2A-Anlagenschema, Hydrauliktopologie und dokumentierte Schreibwerte 00/52/53/54/5B |
| [development.md](development.md) | Vor Änderungen an Reads, Writes, Services oder Deployment |
| [optolink-maintenance.md](optolink-maintenance.md) | Wartungswerte und CLI |
| [optolink-maintenance-api.md](optolink-maintenance-api.md) | MQTT-Wartungs-API und HA-Integration |
| [wb2a-schedule-blocks.md](wb2a-schedule-blocks.md) | Zeitprogrammformat und verifizierte WB2A-Blöcke |
| [service-programs.md](service-programs.md) | Befüllungs-/Entlüftungsprogramm, Codieradresse 2F / 0x572F |
| [manuals/README.md](manuals/README.md) | Servicehandbuch-Quelle und lokaler Download-Helfer |

Zusätzliche technische Referenz:

- [../config/optolink-splitter/vcontrol-mapping.md](../config/optolink-splitter/vcontrol-mapping.md) — Legacy-vcontrold-Migrationsmapping; nicht die aktuelle 20C2-Quelle der Wahrheit.

## Quellen der Wahrheit

Für unterschiedliche Fragestellungen gelten bewusst unterschiedliche Dateien als maßgeblich:

| Frage | Quelle |
| --- | --- |
| Welche Entities/Datenpunkte pollt Produktion? | `config/optolink-splitter/vdensho1-20c2-wb2a-homeassistant.py` |
| Wie sind Anlagenschema/Topologie und deren zulässige Schreibwerte dokumentiert? | `docs/anlagenschema.md` |
| Welche Werte darf Wartung schreiben? | `config/optolink-splitter/optolink_maintenance_core.py` |
| Welche Zeitprogrammblöcke sind erlaubt? | `tools/optolink-schedule-manager.py` |
| Wie wird Party technisch umgesetzt? | `tools/optolink-party-emulator.py` |
| Wie wird die Gerätezeit synchronisiert? | `tools/optolink-clock-sync.py` |
| Wie werden Befüllung/Entlüftung gesteuert? | `tools/optolink-service-programs.py` |
| Wie wird ein bestehendes System aktualisiert? | `tools/optolink-splitter-update.sh` |
| Wie wird das Profil sicher aktiviert? | `tools/optolink-apply-vdensho1-ha-profile.sh` |
| Wie wird eine neue LXC-Installation aufgebaut? | `install/optolink-splitter-install.sh` |
| Wie sieht die HA-Oberfläche aus? | `config/optolink-splitter/homeassistant-dashboard.yaml` |

## Dokumentationsregel

Die übernommene Betriebsdokumentation beschreibt den **produktiven Zustand**. Allgemeines Reverse Engineering bleibt im Research-Archiv. Auf ausdrücklichen Nutzerwunsch wird die aktuelle P300-Migrationsforschung in diesem Entwicklungsbranch dokumentiert, getrennt von produktiven Freigaben und mit erkennbaren Hypothesen-/Beleggrenzen.

Wenn Codeverhalten geändert wird, sollten im selben Änderungssatz mindestens die direkt betroffene Dokumentation und — bei einer wichtigen Invariante — der CI-Guard angepasst werden.

## Architekturdiagramme

- [Systemübersicht](images/optolink-system-overview.svg)
- [Dienstekommunikation und Sicherheitsmodell](images/service-communication-security.svg)

Die Root-README rendert beide Diagramme direkt.
