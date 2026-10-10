# Aufgabe 1: P300-Migration mit 100 % VS1-Funktionsparitaet – konsolidierte Evidenz

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


**WB2A / VDensHO1 / 20C2 / Software 01.03 / GFA P80=20**
**Stand 9.10.2026 | nur `optolink-p300-migration` | PR #46 ungemergt**

## Verbindliche Prioritaeten und Stop-Kriterien

1. **Aufgabe 1 – jetzt:** Den produktiven VS1-Optolink-Splitter vollstaendig
   auf P300 migrieren, dabei **ALLE heute funktionierenden Messwerte,
   Geblaese-Istdrehzahl P06, Topics, Entities, HA-Writes,
   Readbacks, Schedules, Party-Emulation, Uhrensynchronisation,
   Wartung und Serviceprogramme erhalten.**
   P09-Steuersignal oder native Modulation NICHT als P06 ausgeben.
2. **Aufgabe 2 – erst wenn 1 komplett nachgewiesen und lauffaehig:**
   Vitotrol-Emulation, **in einem getrennten neuen Entwicklungsbranch**.
   Bisherige KM-Bus-Quellenfunde sind in diesem Research-Branch nur Historie;
   keine neue Vitotrol-Entwicklung waehrend Aufgabe 1.
3. **Aufgabe 3 – danach:** Pumpenoverride. Keine Pumpen-RAM-Writes
   oder produktiven Regeln im aktuellen Logger.

Diese Reihenfolge ersetzt alle aelteren, konkurrierenden
\"naechster Schritt\"-Hinweise zu Vitotrol/ISR/Overrides
in historischen Forschungsnotizen.

## 1. Was bei genau diesem Geraet erwiesen ist

**Neuer P06-Hardwaredatensatz vom 9.10.:**
[Der VS1/P300-Deep-Logger ist beendet und ausgewertet](p300-deep-result-2026-10-09.md).
5.360 echte VS1-GFA-P06-Werte (1.836 gueltig mit RPM>0
bis zu 4.590 U/min), **2** vollstaendige Flammenbitfenster,
**8.256/8.256** P300-Frames gegen die Rohspur validiert.
**108 von 2.593** stabilen P06-Klammern zeigen andere
P09-Rohwerte: somit keine RPM-Ersetzung durch Soll-Modulation.
15 P06=0- und sieben P06~=0x53-geklammerte
P300-Phasen erlauben erstmals einen gezielten Vergleich.
In den acht existierenden Status-/SFR-/RAM-Bloecken wurde
**kein direkter 8-bit-P06- oder 16-bit-RPM-Spiegel** gefunden.
Die Branch-Software hat inzwischen einen beim
manuellen Stop aufgetretenen SIGTERM/P10-Race behoben;
**32 neue Logger-Tests PASS**, keine produktiven Aenderungen.
Der einstige 4h-Startplan ist abgeschlossen,
**nicht unveraendert erneut starten**.
Neuer P06-Quellenansatz: vollstaendig 20KiB
physikalisches RAM **zustandsgepaart** gegen VS1-P06
lesen und vergleichen (historisch bereits lesbarer
0x0400..0x53FF-Raum), kein SFR-U1RB und keine Writes.

| Schicht | Stand und harte Grenze | Primärbeleg |
|---|---|---|
| Grundgeraet | `00F8=20C2`, Firmware `778C=0103`; GFA-Typ `P80=20` | [Identitaet und Handover](p300-goals-and-single-enq-result-2026-10-08.md) |
| Reale Geblaese-Istdrehzahl | **VS1 `GFA_READ 0x4006` / P06**: `raw*30 U/min`. `0xFF` ist ein ungueltiger/unklarer Rueckgabewert, kein tatsaechlicher RPM-Wert | [180 echte Paare](p300-gfa-native-pair-result-2026-10-08.md) |
| Modulationsanforderung | GFA `P09 0x4009`; fuer GFA-Typ `20` als Sollwert zu lesen, **nicht** P06 | [Same-session-Referenzen](p300-fan-actual-source-screen-2026-10-08.md) |
| GFA-Zustand | VS1-GFA `P87 0x4057`, native `FC01 0x55D3` Byte7 als korrelierter P87-Kandidat; Zeitdifferenzen existieren | [P87-Forschung](p300-p87-vs1-result-2026-10-08.md) |
| Native P300-Diagnose | `FC01 55D3/11` liefert 11 Bytes, Byte5 Flammen-/Verriegelungsbits, Byte0/9 dynamische Steuerwerte | [807 volle Statusframes](p300-full-status-byte-audit-2026-10-08.md) |
| Direkter P300-GFA-Kanal | Auf WB2A **FC C9 / 0x4050 P80 abgelehnt** mit Fehlerpayload `05`; Vitosoft-VSKO schaltet dafuer explizit nach VS1/6B | [Negativer lokaler C9-Test](p300-gfa-c9-hardware-rejection-2026-10-08.md) |
| Andere Drehzahladressen | `0x0B1E` / `0x0B1C` liefern beim lokalen SW03 P300-Fehler; `0x1A53` gehoert zu anderer Geraetefamilie; `0x7660` ist Pumpe | [Quellenaudit](p300-fan-actual-source-screen-2026-10-08.md), [HA-Profil](../config/optolink-splitter/vdensho1-20c2-wb2a-homeassistant.py) |
| Dynamische P06-Abweichung | Bei 180 GFA/P300-Statusklammern waren 171 P06-Klammern stabil, neun zeigten Transition. Bei Auslauf trennen sich P06 und P09/55D3 deutlich. Byte0/Byte9 sind kein Sensorersatz | [Messbericht](p300-gfa-native-pair-result-2026-10-08.md) |
| Protokollwechsel | VS1/P300-Rundwechsel mit einem ENQ rund **4,61 s** (drei gueltige Runden), mit zwei ENQ laenger; ein spontaner 2,1-s-Laufzeitmechanismus ist dadurch nicht geloest | [Handover-Messung](p300-goals-and-single-enq-result-2026-10-08.md) |
| Physischer Hauptregler-RAM | P300 FC03 `0x0400..0x53FF`, ehemals zwei komplette 20-KiB-Dumps mit 841 geaenderten Bytes. RAM-Bedeutung muss von eigener Optolink-IO unterschieden werden | [RAM-Karte](https://github.com/SaulGoodman1337/optolink/blob/optolink-research/config/optolink-splitter/research/physical-ram-optolink-map-2026-09-26.md) |
| Optolink-IO | `0x192C..0x1952` Parser/Scratch, `0x196C..0x19AB` RX, `0x19AC..0x19AD` Luecke, `0x19AE..0x19ED` TX, `0x19EE..0x1A6D` Ring. Kein unabhaengiger P06-RPM-Beweis aus eigenem RX/TX-Echo | [UART1-/RAM-Datenfluss](p300-uart1-gfa-dataflow-offline-2026-10-08.md) |
| Zweiter UART1 | DMA0: TX-Quelle um `0x161B`, Ziel `0x03AA` (UART1-U1TB); physischer **TX**, nicht RX | [Nachtlauf](p300-uart1-overnight-result-2026-10-09.md) |
| Protokoll im UART1-TX | KM-Bus-kompatible Frames ab `0x161A`, CRC16/Kermit validiert; Uhrzeit-Broadcast und Master-Discovery an Teilnehmerklasse `11` in alten Daten. UART1-Gegenstelle/RX und GFA-P06 bleiben **unbewiesen** | [KM-Bus-Telegrammauswertung](p300-kmbus-vitotrol-master-tx-2026-10-09.md) |
| Letzter P300-Nachtlauf | 12.938 Runden, 51.752/51.752 rekonstruierte P300-Read-Antworten, drei komplette natuerliche Flammenfenster; nach Stopp VS1 und GFA-P80/P06 wiederhergestellt. Aber keine GFA-Messwerte **waehrend P300** | [Nachtlauf-Integritaet](p300-uart1-overnight-result-2026-10-09.md) |

Die umfangreichen Vitosoft-Kataloge fuer exakt VDensHO1
(581 Profilevents / 362 Adressen; 94 GFA_READ-Definitionen)
liefern **keinen** benannten unabhaengigen FC01-P06-Tachokanal.
Dies schliesst einen bislang unbekannten physikalischen
Hauptregler-RAM-Spiegel **nicht** aus.

## 2. Die Funktionsparitaet ist eine pruefbare Abnahmematrix

Das produktive
[20C2-HA-Profil](../config/optolink-splitter/vdensho1-20c2-wb2a-homeassistant.py)
hat laut [Migrationserstentwurf](p300-migration.md)
362 deklarierte Eintraege, davon 222 Poll-Eintraege;
das sind keine 362 unabhängigen Drahttransaktionen.
Es bleibt die unveraenderte Referenz fuer Topics, Decoder
und freigegebene Schreibvorgaenge.

| Funktion | Produktionsquelle | P300-Freigabestatus | Abnahmebedingung |
|---|---|---|---|
| Alle Poll-Messwerte und Binaerflags | Original Profil / VS1 | **OFFEN** | Identische Werte, Dekodierung, Frische und Fehlerbehandlung |
| Reale Geblaese-Drehzahl P06 | VS1/6B GFA `0x4006` | **BLOCKIERT** | Verifizierter P300-Datenweg fuer tatsaechliche, frische RPM |
| GFA P09/P80/P87 | VS1/6B | **BLOCKIERT** als komplettes Paket | P80=20, statusgenaue P87-/Sollwertsemantik ohne Phantom-Aliase |
| MQTT Topic-/HA Entity-IDs | Original-Splitter + Publisher-Patch | **OFFEN** | Unveraenderte IDs und Antwortformate, keine stale Retains |
| Normale HA-Write- und Readbacks | freigegebene Virtual Writes | **OFFEN** | Zulassung/Readback von repräsentativen echten Funktionen unter P300 |
| 21 Tages-Zeitplanbloecke | schedule-manager + 8-Byte-Write | **OFFEN** | Zeitpläne bytegleich lesen/schreiben/restaurieren |
| Party-Funktion | party-emulator + `0x2306`, `0x2323` | **OFFEN** | Set/Restore, Ende, Neustart, UI-Status |
| Uhrensynchronisation | clock-sync Timer/Service | **OFFEN** | BCD-Uhrzeit-Write mit Readback, kein Drift |
| Serviceprogramme | service-programs `0x572F`, Wartungs-Core | **OFFEN** | Nur bewusst freigegebene 0/1/2-Testablaeufe und Restore |
| MQTT-Wartung & Housekeeping | maintenance-api, schedule-manager, timer | **OFFEN** | Dienstzustand, Warteschlangen, HA-Status auf Ende-zu-Ende-Ebene |
| RAM-Reads (P300-Forschung) | P300 FC03 | **LESEWEG BELEGT** | Limitierung und Lastbudget fuer Betrieb |
| Laufzeit-RAM-Overrides | zukuenftige Aufgabe 3 | **NICHT Teil Aufgabe 1-Logger** | Erst spaeter gesondert pruefen |

**Keine** dieser noch offenen Zeilen wird durch einen
erfolgreichen read-only Logger zum Produktiv-PASS.

## 3. Der bewusst neue Logger fuer Aufgabe 1

[Start-/Stopp-Runbook](p300-deep-logger-runbook-2026-10-09.md) und
[detached Logger](../tools/wb2a-p300-deep-logger.py).

Bisher fehlte in der Nachtmessung die dynamische
GFA-P06-Referenz. Der neue Lauf wechselt deshalb
innerhalb eines einzigen beaufsichtigten Prozesses:

**VS1-Phase, nominal 50 s:** GFA-Read
P06 -> P09 -> P87 -> P06 als driftbewusste Klammer;
jede zehnte Runde zusaetzlich P10, P84 und P80.
Aus P06 wird RPM berechnet; P09 bleibt separate
Modulationsanforderung. Einzel-TX/RX-Zeitstempel,
zwei P06-Werte je Klammer und 0xFF-Qualitaet.

**P300-Phase, nominal 75 s:** jedes Mal
FC01 `55D3/11`, FC03 `0020/16`,
FC03 `1600/32`, FC03 `1620/32`;
jede sechste Runde vier weitere **zuvor
historisch gelesene** 32-Byte-RAM-Ziele:
`15E0`, `1640`, `18F8`, `1A70`.

**Event-Trigger:** Bei realem VS1-P06-Anstieg
nach sechs Sekunden Referenzdaten frueher zu P300;
bei nativem P300-Flammenbitwechsel nach vier
Sekunden Statusklammer frueher zu VS1.
Ziel ist eine hoehere Chance auf
Anlauf/Rampe/Auslauf beider Datenfamilien,
ohne Brennerstarts zu erzwingen.

**Probezeit 1–8 h (Default 4 h)**,
systemd detached, ein serieller Portbesitzer.
Die zeitaufwendigen 2-ENQ-VS1-Rueckwechsel
werden explizit als Luecke gestempelt;
einfache P06/KM-Bus-Payload-Interpolation ist
kein Beweis eines GFA-Sensor-Spiegels.

Alle Roh-Bytes, UTC- und monotonic-Zeiten,
Schnell-/Slow-RAM, GFA-Flags,
Wechselgründe/-dauern sowie Originalsystem-
Restore/MQTT-P80/P06-Health werden in
einem privaten tar.gz-Archiv gesichert.
Original produktive `settings_ini.py`,
Produktionscheckout `/opt/optolink` und
bestehendes HA-Profil werden nicht veraendert.

**Waehrend des Loggers** pausieren aus
Single-Owner-Gruenden die produktiven
MQTT/HA-Optolink-Dienste, **wie im alten Nachtlauf**.
Sie werden nach dem Ende in ihrem urspruenglichen
Aktivzustand restauriert. Somit ist der Logger
kein bereits funktionsparitaerer P300-Betrieb.

Die explizite P300-Anfragenliste enthalten
ausschliesslich Read-Funktionen `0x01/0x03`
und acht statisch bekannte Adress-/Laengenpaare.
Kein Durchlauf von UART1 `U1RB @ 0x03AE`,
kein erfundener C9, keine RAM-Schreibbefehle.

## 4. Direkter Folgeschritt NACH dem naechsten Upload (ohne erneutes Nachfragen)

1. Archivmanifest und SHA256 jeder Datei, alle
   VS1-/P300-Rohantworten, Adress-/Längen-/
   Checksummentreue und Systemd-Restore verifizieren.
2. Mehrere echte P06=0-/Nichtnull-/Anlauf-/
   Auslauf-Intervalle anhand der VS1-Rohdaten
   klassifizieren. Ein instabiles FF nicht zu RPM
   konvertieren. P09/P87 und Statusbytes separat.
3. Reale zeitliche Protokollluecken fuer
   jeden VS1->P300->VS1-Uebergang berechnen.
   GFA-P06 nur innerhalb dokumentierter
   Vor-/Nach-Fenster in eine Kandidatensuche
   einbeziehen; nicht behaupten, dazwischen
   simultan gemessen zu haben.
4. Die acht P300-Datengruppen **byteweise**
   vergleichen. UART1-KM-Bus **TX-Payloads**,
   Optolink-eigene Sendeantworten und
   Modulations-/Status-Proxies ausschliessen.
5. Nur falls unabhaengige, plausible P06-
   Sensor-Update-Kandidaten wiederholt auftauchen:
   Speichersemanik, Updateursprung,
   Freshness und anderen Betriebszustand
   mit einem **gezielten** neuen Vergleich
   validieren. Kein blindes Freigeben per Regression.
6. Im negativen Fall die Hardwarearchitektur
   fuer direkte GFA-Signalaufnahme bzw.
   VS1/P300-Hybrid-Single-Owner erneut
   gegen das volle Funktionsparitaetsbudget
   bewerten; keine Teilmigration, die P06 verliert.

**Erst wenn Aufgabe 1 produktiv und End-to-End
nachgewiesen ist**, wird Vitotrol im neuen Branch
als Aufgabe 2 begonnen. Die Pumpenoverride-
Forschung wartet als Aufgabe 3.

**Naechster technischer Beweisschritt (nach erfolgter Auswertung):**
Nicht denselben acht-Block-Logger nochmals starten. Stattdessen
P06-geklammerte, vollstaendige 20-KiB-Physical-RAM-Reads in mehreren
stabilen echten P06=0- und P06>0-Zustaenden entwerfen und
quellen-/risikobewusst freigeben. Die Messmethode muss die
~89 Sekunden Buszeit pro 20KiB-Snapshot aus den realen
FC03-Latenzen beruecksichtigen, mit vor-/nachher P06 pruefen
und die eigenen Optolink-UART-Puffer als falsche Kandidaten
ausschliessen. Produktionsmigration bis echtem RPM-Sensorbeleg
gesperrt; Full-Parity-Abnahmematrix oben bleibt verbindlich.
