# VDensHO1: GFA-Istdrehzahl, zweiter UART und begrenzte RAM-Quellenanalyse

**2026-10-08 | Branch `optolink-p300-migration` | Source-first-Fortsetzung | nicht produktiv.**

## Ergebnis und technische Tragweite

Die gezielte P06-Istwertsuche fand bisher keinen von der GFA-Kommunikation
unabhaengigen FC01/Virtual_READ-Datenpunkt (siehe
[elf Bytes und Profile](p300-fan-actual-source-screen-2026-10-08.md)).
Ein neues **hardwareverankertes Indiz** ergibt sich aus der bereits erstellten
[WB2A-RAM-Speicherkarte](https://github.com/SaulGoodman1337/optolink/blob/optolink-research/config/optolink-splitter/research/physical-ram-optolink-map-2026-09-26.md):
der Hauptregler besitzt neben **UART0 = Optolink**
einen **UART1-DMA0-Sendepfad**.

In der alten, read-only abgefragten DMA-Registeraufnahme lautete die
Zuordnung:

| Register | Beobachteter Wert | Interpretation, sofern M16C/62P SFR-Modell zutrifft |
|---|---|---|
| DMA1 source (SAR1) | 0x19AF | Bereits bewiesener Optolink-TX-Puffer bei 0x19AE |
| DMA1 destination (DAR1) | 0x03A2 | UART0 TX (U0TB) |
| DMA1 selector (DM1SL) | 0x0A | UART0-TX-DMA |
| **DMA0 source (SAR0)** | **0x161B** | **Aktueller Quellepointer eines zweiten Sendepfades** |
| **DMA0 destination (DAR0)** | **0x03AA** | **UART1 TX (U1TB)** |
| DMA0 count (TCR0) | 0x0008 | Einmalig beobachteter Restzaehler, keine feste Paketlaenge |
| DMA0 selector (DM0SL) | 0x0F | UART1-TX-DMA |

Dies **beweist NICHT**, dass UART1 am GFA haengt.
Weder das externe Gegenstueck noch die gesendeten/empfangenen
Bedeutungen oder ein GFA-Istwert-RAM-Feld sind daraus ermittelt.

**Noch wichtiger:** `SAR0` ist ein **TX-Quellzeiger**.
Selbst wenn UART1 mit dem Feuerungsautomaten sprechen wuerde,
koennte die echte Geblaesedrehzahl im **separaten RX/Antwortpfad**
liegen. Das heutige Indiz identifiziert keinen solchen RX-Puffer
und schon gar keinen P06-Speicherort.

## 1. Was die vorhandene RAM-Sammlung bereits hergibt

Im Research-Branch wurden am 26.09.2026 ueber **P300 Physical_READ**
zwei komplette RAM-Paesse im festen Bereich `0x0400..0x53FF`
(je 20.480 Bytes) gespeichert; zwischen diesen Paessen aenderten
sich 841 Bytes. Die historischen Ausgabedateien des Helpers heissen:

```text
/tmp/physical-ram-<DATUM>-pass1.bin
/tmp/physical-ram-<DATUM>-pass2.bin
/tmp/physical-ram-<DATUM>-report.json
```

Die Dumps wurden **nicht** ins oeffentliche Repository gestellt
und sind moeglicherweise inzwischen von `/tmp` entfernt worden.
Daher wurde in diesem Arbeitsschritt **kein echter DMA0-Byteverlauf
der archivierten Passdateien neu ausgewertet**; ob sich der Bereich
um `0x161B` im Altbestand aenderte, bleibt offen.

Der alte Bericht haelt **eine einzelne** DMA0-Registerbelegung
fest. Dies darf nicht als stabiler UART1-TX-Pufferanfang oder
als regelmaessiges Motor-Istsignal interpretiert werden.

## 2. Sicherer Offline-Auditor fuer die alten Dumps

[`tools/audit-uart1-gfa-ram.py`](../tools/audit-uart1-gfa-ram.py)
arbeitet ausschliesslich auf **bereits gespeicherten lokalen Dateien**:

- Verifiziert die feste RAM-Geometrie 0x0400..0x53FF, 32-Byte-Blöcke,
  zwei unterschiedliche regelmaessige 20.480-Byte-Dateien, alle
  optional im Originalbericht gespeicherten Aenderungszaehler.
- Verweigert SymLinks, ueberschriebene Berichte und ungueltige
  Quelldateien.
- Gibt SHA256 der Eingabedateien und Veraenderungszahlen zur
  spaeteren Provenienzpruefung aus, nicht den gesamten RAM.
- Fokusbereich: **0x15E0..0x165F (128 Bytes)** um den beobachteten
  DMA0-Quellzeiger `0x161B`. Die Rohbytes **0x1600..0x163F**
  (64 Bytes) beider alten Paesse werden fuer lokale Offline-Auswertung
  aufgenommen. **Das ist ein Untersuchungsbereich und keine
  erlaubte live P06-Read-Adresse.**
- Ausgeschlossen von der allgemeinen Aktivitaetsrangliste sind
  die bekannten eigenen **Optolink**-Strukturen:
  `0x192C..0x1952` Parser/Scratch,
  `0x196C..0x19AB` RX,
  `0x19AC..0x19AD` ungekl. RX/TX-Zwischenbytes,
  `0x19AE..0x19ED` TX,
  `0x19EE..0x1A6D` Ring.
- Listet ausserhalb dieser Bereiche bis zu zwoelf sonstige
  veraenderliche 32-Byte-Fenster auf, **ohne daraus Drehzahlen
  oder UART1-RX-Adressen zu behaupten**.
- Im JSON sind die Freigabefelder `candidate_gfa_ram_address_verified`,
  `production_alias_approved`, `physical_ram_write_approved`,
  `live_read_approved_from_this_offline_result` alle **false**.

Der Default ohne CLI-Argumente ist ein reiner **Plan**, keine
Datei- oder Geraetemessung. Mit `--report` werden ausschliesslich
lokal gespeicherte alte Binärdateien gelesen. **Kein USB, Optolink,
MQTT, Netzwerk, Service-Stopp, Protokollwechsel oder RAM-Write.**

## 3. Genau dieser naechste Offline-Schritt auf der LXC

Als `root` in der Optolink-LXC; aktueller Dev-Checkout liegt wie
bisher unter `/root/p300-trial-work/project`.

1. Den P300-Entwicklungsbranch holen. Die aktuelle Commit-SHA aus
   der PR beziehungsweise dieser Session verwenden, keine anderen
   Branches mergen.
2. Die reine Regression ausfuehren:

```bash
/opt/optolink/venv/bin/python -m unittest discover \
  -s /root/p300-trial-work/project/tests \
  -p test_uart1_gfa_ram_audit.py -v

/opt/optolink/venv/bin/python \
  /root/p300-trial-work/project/tools/audit-uart1-gfa-ram.py
```

3. Falls noch ein historischer `physical-ram-*-report.json` samt
   beiden Binärdateien existiert, den **neuesten** gefundenen Bericht
   an den Auditor uebergeben und die neue JSON-Auswertung
   unter `/root/p300-trial-work/` speichern.
   Die fertigen Befehle stehen in der Assistentenantwort zu diesem Commit;
   es sind ausschliesslich lokale Dateioperationen.

Wenn die alten RAM-Snapshots nicht mehr vorhanden sind:
**keinen neuen 20-KiB-Speicher-Gesamtscan als Ersatz starten.**
Die Offline-Stufe meldet dann "keine alten RAM-Berichte"; das ist
ein begrenzter Informationsstand, kein Hardwarefehler.

## 4. Evidenz-Gates vor der naechsten echten RAM-Messung

**Gate A: Ist UART1 ueberhaupt der GFA-Datenpfad?** Nicht aus SAR0
allein ableitbar. Gesucht sind plausible Zuordnungen von UART1
und dessen RX-Ereignissen ueber existierende Quellen/Hardwarezeichnung
oder datenabhaengige, eng begrenzte Beobachtungen. Keine
Firmwaredefinition der Herstellerkommunikation wird vermutet.

**Gate B: Gibt es einen RX-/Zustandsspeicher ausserhalb des
Optolink-RX/TX/Ring-Puffers?** Sichtbarer TX-Verkehr kann nur
Anforderungen senden; das gesuchte P06-Istsignal muesste semantisch
mit mehreren unterscheidbaren P06-Werten oder einer geeigneten
unabhaengigen Quelle verglichen werden koennen. Keine Gleichsetzung
eines Sendebytes mit der Motordrehzahl.

**Gate C: Ist eine gezielte, NICHT schreibende Live-Leseliste
nachvollziehbar?** Erst nach Gate A/B: einzelne begruendete
RAM-Fenster, genau dokumentierte Grenzen, keine Peripherie-/SFR-
Zufaellauftraege, nur ein serieller Besitzer, fester Ablauf,
korrekte GFA/VS1-Rueckkehr und vorherige Erfolgs-/Fehlerpruefungen.
Das bestehende P87-only-Referenzexperiment bleibt
denormalisierte historische Evidenz, nicht automatisch eine
Freigabe fuer einen neuen RAM-Scan.

**Gate D: autonom und korrekt?** Frische ohne externe
VS1-GFA-Abfragen, multiple unterschiedliche P06-Drehzahlwerte
und erkennbare Verzoegerung. Ein Treffer im RAM bei konstant 00
oder 53 ist nicht ausreichend. Ein unter P300 lesbarer Zustand
ist nicht automatisch ein P06-Drehzahlsensor.

## 5. Architekturentscheidung bis dahin

- Produktiv bleibt **VS1** mit **P06/P09/P87/P80**.
- P300 Virtual_READ fuer normale Datenpunkte und physischer
  Low-RAM-Read sind separat nachgewiesene Entwicklungsfaehigkeiten.
- Hybridwechsel ist in der bestaetigten schnellen Variante mit
  rund **4,61 s** Gesamtunterbrechung inkl. GFA noch **zu langsam**
  fuer einen lueckenarmen `2,1-s-E7-RAM-Override.
- **Keine E7-/RAM-Writes und keine Umcodierung des Hydraulikschemas.**
- P300-Branch/PR bleiben Entwurf bis GFA-Paritaet und sichere
  End-to-End-Wiederherstellung bewaehrt sind.

Quellen: [historische RAM-/DMA-Karte](https://github.com/SaulGoodman1337/optolink/blob/optolink-research/config/optolink-splitter/research/physical-ram-optolink-map-2026-09-26.md), [Physical_READ-Scratch-Nachweis](https://github.com/SaulGoodman1337/optolink/blob/optolink-research/config/optolink-splitter/research/physical-read-scratch-map-2026-09-27.md), [P06/P09-Vergleich](p300-gfa-native-pair-result-2026-10-08.md), [P06-Fan-Quellenaudit](p300-fan-actual-source-screen-2026-10-08.md).
