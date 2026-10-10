# WB2A: Vitotrol und mehrtägige RPM-Forschung – 10.10.2026

**Basis:** PR #51 ist in `main` integriert (Merge `6664c5e`).
Der echte LXC-Befehl `update` wurde danach mit Exit-Code 0
gegen `COMMUNITY_SCRIPTS_REF=main` ausgeführt. 362 MQTT-Discovery-
Entitäten veröffentlicht, `VS1_BETRIEB_OK`, alle ursprünglichen Dienste
aktiv, Pumpenoverride und Protokollautomatik deaktiviert.

**Neuer Entwicklungsbranch:** `feat/wb2a-vitotrol-rpm-20261010`
ab diesem Main-Commit. Controller-RAM, Firmware, Kodierung und
die produktive VS1-Hauptschleife bleiben während dieser Forschung
unverändert.

## 1. Vitotrol: bekannte TX-Anfragen und fehlender RX-Kanal

Aus dem historischen UART1-P300-Archiv wurden 54 CRC16/Kermit-
gültige **RAM-Snapshotansichten** der beiden KM-Bus-Masterabfragen
für Klasse `0x11` nachgewiesen. Nicht mit 54 physischen
Busübertragungen verwechseln.

| Slot | Historischer Masterrequest F8..FB |
| --- | --- |
| 1 | `11 00 33 0A 01 01 F8 04 49 EF` |
| 2 | `11 00 33 0A 02 01 F8 04 84 CA` |

`tools/wb2a-vitotrol-offline.py` ist ein eigenständiger,
transportloser Decoder/Modellsimulator. Er bietet:
- Validierung des gerahmten KM-Bus-Protokolls mit CRC16/Kermit;
- F8..FB-Antwort für die bekannte Vitotrol-200-Identitätsfamilie
  `00 11 B3 10 01 01 F8 11 F9 34 FA 00 FB 05 06 64`;
- bekannten PONG `00 11 80 08 01 01 F9 5C`;
- 0xBF-/Record-0x20-Raumtemperaturbeispiel für 21,5 °C
  `00 11 BF 0C 01 01 20 7D AA AA 6F 33`;
- den vollständig offline simulierten Ablauf Discovery → PING →
  PONG beziehungsweise Raumtemperaturdatensatz, inklusive Verweigerung
  bei veralteter Temperaturquelle.

**Beweisgrenze:** Es gibt bisher nur UART1-TX-Mastersamples im
Regler-RAM, keinen gesicherten realen RX-Puffer und keine
Optolink-Schnittstelle zur Einspeisung von Vitotrol-Slaveantworten.
Der Versuch `0x27A0=1` ohne reale Gegenstelle löste historisch
`BC = Fernbedienungsfehler HK1` aus; danach wurde `0x27A0=0`
wiederhergestellt. Keine Wiederholung ohne belastbaren RX-/Rollback-Pfad.
Das historische Firmware-/Regler-MCU-Research in Issue #25 bleibt
die entscheidende Abhängigkeit für **software-only** Emulation.
Ein **externes physisches KM-Bus-Slave-Interface** wäre eine andere
Architektur und nicht automatisch durch P300 ersetzt.

Forschungsgrundlagen im Branch `optolink-research`:
- `config/optolink-splitter/research/vitotrol-kmbus-wire-protocol.md`
- `config/optolink-splitter/research/vitotrol-software-emulation-deep-dive-2026-09-25.md`
- `docs/p300-kmbus-vitotrol-master-tx-2026-10-09.md`
- [OpenV KM-Bus](https://github-wiki-see.page/m/openv/openv/wiki/KM-Bus)

## 2. Vier Tage passiv VS1-P06 mitschneiden

**Läuft seit 10.10.2026, 21:52 Uhr CEST.** Der erste, nur P06
erfassende Dienst `optolink-wb2a-rpm-passive-20261010.service`
wurde um 21:59 Uhr ausschließlich als Beobachter sicher beendet
(`SIGNAL_STOPPED`; 64 vorhandene P06-Samples bleiben im Archiv).
Mit unverändertem absolutem Endtermin wurde der erweiterte Dienst
`optolink-wb2a-rpm-passive-20261010-v2.service` gestartet.
Er erfasst jetzt **P06, P09 und Brennerflamme**; die exakten
Produktions-MQTT-Topics wurden gegen `homeassistant_poll_list.py`
geprüft. Gemeinsame Auswertung verwendet beide Recorder-Generationen.
Gesamtlaufzeit 96 Stunden bis 14.10.2026, ca. 21:53 Uhr CEST;
separate Systemd-Maximallaufzeit rund eine Minute länger.

`tools/wb2a-rpm-passive-observer.py` liest via bestehendem MQTT-Broker
nur aktuelle (nicht Retained-) VS1-Werte; kein zweiter serieller Port,
keine MQTT-Veröffentlichungen, keine Controller-Kommandos.
Erfasst `geblaesedrehzahl_gfa_p06`,
`gfa_modulationssollwert_p09`, `brenner_flamme` und
`brenner_flamme_gfa`, jeweils höchstens alle fünf Sekunden
pro Messart. P09/Flamme sind Kontext und ausdrücklich **keine RPM**.
Ausgabefelder markieren die Provenienz unmissverständlich:
`VS1_MQTT_PUBLISHED_NOT_P300_RPM`.

Limits: 400.000 Zeilen, höchstens 60 MiB, privates
Root-Verzeichnis `0700` / Dateimodus `0600`, maximal
100 MiB Arbeitsspeicher, keine automatische Neustartschleife.
Beobachter ist nicht Teil des normalen `update`- oder VS1-Dienstes.

Private Messdaten:
```text
/var/lib/optolink-research/rpm-passive-20261010/
    progress.json
    vs1-YYYY-MM-DD.jsonl
```

Read-only Status:
```bash
systemctl status optolink-wb2a-rpm-passive-20261010.service --no-pager
sudo cat /var/lib/optolink-research/rpm-passive-20261010/progress.json
sudo python3 tools/wb2a-rpm-passive-summary.py \
  --dir /var/lib/optolink-research/rpm-passive-20261010
optolink-hybrid status
```

Die Offline-Zusammenfassung meldet echte positive P06-Anzeigeepisoden,
Zeitbereiche und Spitzenwerte, aber **niemals eine P300-Istdrehzahl**.
**Erste positive Referenz:** Bereits am 10.10.2026 von
21:56:30 bis 21:57:01 Uhr CEST wurde eine positive P06-Episode
mit **6 Messpunkten und 4410 U/min Spitzenanzeige** protokolliert.
Dieses Fenster liegt vor der v2-Kontexterweiterung und besitzt daher
noch keine flankierenden neuen P09-/Flammen-Samples.
Es beweist **keine P300-Gebläse-Istdrehzahl**.

Eine für vier Vormittage (11.–14.10.2026, Europe/Berlin)
eingerichtete, rein lesende Aufgabenautomatik kontrolliert beide
Recorder-Generationen im gemeinsamen Archiv und meldet Auffälligkeiten;
keine Hardwarewechsel.

### Warum kein unbeaufsichtigter P300-Dauerwechsel?

Auch ein kurzer physischer P300-Zugriff beansprucht denselben Port
und pausiert vorübergehend produktive Dienste. Die früheren
C2/C3-Hardware-Canaries dauern ca. 5,2 Sekunden je Wechsel
**plus** Vorprüfung und Recovery. Daraus folgt noch keine
Freigabe für unbeaufsichtigte periodische Unterbrechungen über Tage.

Für den eigentlichen P300-Gebläsedrehzahlnachweis brauchen wir
nach einer identifizierten **stabilen positiven VS1-P06-Phase**
einen gesondert abgesicherten und zeitlich eng geklammerten
kurzen P300-Gegentest. Zahlenähnlichkeit von `0x0F20` oder
`0x1C76` zur P06-Probe beweist noch keine Tachometerquelle.
Der vorhandene unabhängige Offline-Audit liegt unter
`optolink-research/docs/wb2a-rpm-offline-audit-2026-10-10.md`.

## 3. Tests und nächste Freigaben

```bash
python3 -m unittest discover -s tests -p 'test_wb2a_*.py' -q
python3 -m unittest discover -s tests -p 'test_*.py' -q
```

**398/398 vollständige lokale Python-Regressionstests bestanden**
(362 Tests der integrierten Main-Basis plus 36 zusätzliche Offline-Tests).

Die neuen Tests schützen CRC, KM-Bus-Header, Slot, Identitätsantwort,
PING/PONG, Raumtemperatur-XOR-Record, Stale-Source, MQTT-Retained,
Berechtigung der Outputdateien, P06-Messreihe und
Nichtverwechslung von VS1- und P300-RPM.

**Keine** reale Vitotrol wurde durch diese Arbeiten emuliert.
Keine RAM-Writes und kein blinder SFR-/UART1-RX-Leseversuch.
Der produktive `main` bleibt gegenüber diesem Research-Branch unverändert.

## 4. Vertiefung am 10.10.2026: RX-ISR-Firmwaregate und Offline-Statusrecords

**Tatsaechlich erneut geprueft:** die beiden historischen P300-UART1-Auswertungen
unter `/root/p300-trial-work/project/docs/`,
`config/optolink-splitter/research/vitotrol-kmbus-wire-protocol.md`,
`vitotrol-software-emulation-deep-dive-2026-09-25.md`,
`vitotrol-software-emulation-pause-checkpoint-2026-09-26.md`,
`firmware-20bit-bridge-static-2026-09-26.md`,
`vitosoft/kbus-write-function-analysis.md` und GitHub-Issue #25.

### Belegt versus offen

- **Lokaler Nachweis:** UART1-DMA0-TX an `U1TB=0x03AA` und 54
  CRC-gueltige TX-Pufferansichten fuer Vitotrol-Discovery Slot 1/2 aus
  12.938 Archivmessrunden. Diese 54 sind RAM-Samples, keine 54
  unabhaengig belegten physikalischen Telegramme.
- **MCU-Familienhypothese:** M16C/62P, `S1RIC=0x0054`, UART1 RX
  `U1RB=0x03AE..0x03AF`, RX-Vektor 20, Vektortabellen-Offset `INTB+0x50`.
  Weder lokale MCU-Kennzeichnung, `INTB`, RX-ISR-Adresse noch RX-Puffer
  sind verifiziert. Kein Zugriff auf U1RB oder andere SFRs erfolgt.
- **Artefakt-Luecke:** In den gezielt durchsuchten Firmware-Dateipfaden
  unter `/root/p300-trial-work` und dem lokalen Research-Checkout wurde
  kein geeignetes Regler-ROM-/ELF-/SREC-Firmwareimage gefunden. Die
  historische VitoSoft-Analyse enthaelt nur Host-/RPC-Metadaten, keinen
  Controller-ISR-Dump. Diese negative Dateisuche ist keine Behauptung
  ueber saemtliche jemals existierenden Archive.
- **Optolink-Grenze:** `0x41 KMBUS_RAM_READ` spiegelt nach lokalen
  Vergleichstests virtuelle Objekte; fuer `0x32 XRAM_WRITE` ist kein
  gueltiges profilspezifisches Format bekannt, die 22 VDensHO1-RPCs
  enthalten keinen RX-Inject-Handler. Aus der reinen Existenz eines
  generischen Write-Function-Codes folgt keine Freigabe.

### Konkrete zu testende RX-Hypothese

Auf dem angenommenen M16C/62P verarbeitet eine UART1-RX-ISR an Vektor 20
Byteeingaben, uebergibt sie an einen KM-Bus-Frameparser und dieser
aktualisiert nach erfolgreicher CRC-/Slot-/Klassenpruefung die
Vitotrol-Teilnehmer-/Sensorzustaende. Der unbekannte SRAM-Ringpuffer,
ISR-Einsprung und Parser sind **nicht belegt**. Geraetegenau zugeordneter
Firmwaredump oder gesicherter vorhandener Vektortabellensnapshot ist
zwingende Voraussetzung fuer die naechste statische Zuordnung.

Empfohlene Offline-Kette nach Beschaffung eines echten Images:
MCU/Memory-Map verifizieren -> tatsaechliches INTB und Vektor 20
lokalisieren -> ISR-U1RB-Zugriffe und RAM-Buffer-XREF identifizieren
-> Parser-CRC/Slot verknuepfen -> Status/Room-Commit nachverfolgen
-> Read-only-Fixturetests. Insbesondere darf `INTB+0x50` **nicht** als
fixe physische Adresse benutzt werden.

### Neu abgesicherte Protokollteile

Der Offline-Simulator erkennt nun masterseitige `0xBF`-Statusrecord-
**Rahmen** `0x1C..0x1F` nach Slot-/Header-/Laengen-/CRC-Pruefung.
Die Nutzdaten bleiben absichtlich opak und `decoded_status_verified=false`:
Die historischen lokalen UART1-Belege umfassen keine bestaetigte
Vitotrol-RX-Gegenstellenantwort und keine WB2A-Status-Record-Nutzlast.
Weitere Offline-Tests pruefen unbekannte Recordnummern, CRC-Fehler
und rueckwaerts laufende Uhr-/Sensortimestamps. Es wurde **kein**
physischer Antwortpfad aktiviert.

### Variantenentscheidung (Stand dieses Commits)

1. **Physischer KM-Bus-Slave am geprueften Businterface:**
   beste praktische Realisierungsaussicht, weil 1200 8E1,
   Master-Discovery, CRC, Antworten und elektrische M-Bus/KM-Bus-
   Gegenstelle in externen Emulatoren belegt sind. Vor einem
   Anschluss benoetigt die lokale WB2A eine elektrische und
   galvanische Interfacepruefung sowie eine passive Busabnahme.
2. **Optolink-only/P300:** wartungsfreundliches Wunschziel, jedoch
   blockiert, bis eine exakte RX-/Monitor-Service-Funktion nachgewiesen
   wird. Bestehende Hybrid-P300-Fenster erlauben nur freigegebene
   Read-only-Diagnosen.
3. **Direkter RAM-/Puffer-Write:** derzeit nicht vertretbar, da
   Empfangspuffer, ISR-Ownership, Atomizitaet und Rollback unklar sind.

**Freigabeentscheidung:** Draft-PR behalten; keine Controllercodierung,
keinen RAM-Write, keinen KM-Bus-Busanschluss, keinen Produktivmerge.
Die mehrtaegige passive P06/P09/Flammen-Aufzeichnung bleibt unberuehrt.

## 5. Originale Vitotrol-300-TX-Aufzeichnung (10.10.2026)

Ein von `boblegal31` direkt an einer originalen Vitotrol 300
abgegriffenes 3.858-Byte-UART-TX-Archiv ist jetzt quellverifiziert
und offline ausgelesen: **448 CRC-gueltige Komplettframes**, darunter
416 PONG, 28 `BF/15`, 2 `BF/20` (20,0 und 20,6 Grad C), 1
`B3/F8..FB` (Identitaet `11 38 01 0A`) und 1 `B1/reg00=12`;
vier abgeschnittene EOF-Bytes. Die Daten stammen *nicht* von unserer
WB2A. Die simulatorischen B1-/BF-Decoder und die kompletten
Audit-/Quellbelege stehen im
[Original-Vitotrol-Referenzbericht](wb2a-vitotrol-original-reference-2026-10-10.md).

Die UART1-RX-/P300-Injektionssperre bleibt bestehen.

## 6. Optolink-only-Entscheidung und neuer RX-Fund (10.10.2026)

**Ausdrueckliche Architekturvorgabe:** Nur Optolink/P300; kein externer
KM-Bus-Adapter oder physischer Emulator. Die fruehere Variantenbewertung
ist durch diese Prioritaetsentscheidung ueberholt.

Zwei historische private Archive enthalten im Hauptregler-RAM bei
`0x1642` insgesamt **374/374** CRC-gueltige Frames der Richtung
`00 01 B1` (andere Teilnehmerklasse als Vitotrol).
Der Bereich liegt **40 Bytes hinter dem bekannten UART1-TX-Puffer**
bei `0x161A`; beide beobachteten RX-Inhalte sind unterschiedlich.
Ein Restbyte-Muster erlaubt eine eindeutige, jedoch **nicht beobachtete**
CRC-Rekonstruktion eines laengeren B3-Kennungsframes. Es handelt sich
um einen starken RX-Puffer-Kandidaten, **noch nicht** um verifizierten
UART1-Hardware-RX oder einen freigegebenen RAM-Schreibpfad.

Der bestehenden Root-only-On-Demand-API wurde ausschließlich die
neu typisierte, bereits historisch 295-mal benutzte Read-only-Abfrage
`p300_ram_1640_32` hinzugefuegt. Sie wird **nicht automatisch
ausgefuehrt**, nicht in den Continuous-/Boot-Canary-Plan aufgenommen
und nicht produktiv deployed. Der neue forensische Offline-Auditor
und alle Beweise/Grenzen stehen unter
[WB2A Optolink RX-Forschung](wb2a-vitotrol-optolink-rx-2026-10-10.md).

## 7. Optolink-only RX-Kontext-Audit: zwei gesicherte Archive

Der erweiterte, ausschließlich offline arbeitende
[RX-Timing-/Status-Auditor](wb2a-vitotrol-optolink-rx-context-2026-10-10.md)
verifiziert 79 vollständige RAM- und 295 Deep-Proben sowie die
640 Blockread-Zeitstempel von Snapshot 64. **0/79** Voll-RAM-Images
enthalten einen gültigen Klasse-11-Slaveframe; `0x0B6D` könnte ein
Zeiger auf den RX-Kandidaten `0x1642` sein, bleibt aber unbewiesen.
Die bisherige Master-Anfragezuordnung in Deep-Runde 145 wurde
**herabgestuft**: der über zwei Zeitpunkte zusammengesetzte
Master-TX-Frame enthält einen CRC-Fehler, der nicht mit einem
fehlerhaften Drahtframe gleichgesetzt werden darf.

**Fehlendes Gate:** lokal belegter INTB/Vektor20, UART1-RX-Handler
und Übergang zum Vitotrol-State. Bis dahin keine physische Emulation,
keine neue Optolink-/RAM-/Register-Schreibfunktion.

## 8. Original-V300-Profil + stärkere RAM-Xref-Forschungsbasis

Eigenständige [Emulatorprofil-Fortsetzung](wb2a-vitotrol-optolink-emulator-profile-2026-10-10.md):
Eine originale Vitotrol 300 wird jetzt mit `11 38 01 0A`
(anstatt des älteren Samplewerts `11 38 00 11`) und
explizitem Register-00-Wert `12` in einer Slot-1-Offline-
State-Machine modelliert. **420/448** echte Original-Slave-TX-
Frames sind damit bytegenau darstellbar; 416 sind gleiche PONG.
`BF/15` bleibt trotz 28/28 valider, unterschiedlicher Records
semantisch und bezüglich Rolling-State unbewiesen.

Die erweiterte Xref-Suche belegt `0x1642` als 16-Bit-
Bytefolge bei `0x0B6D` und **auch** `0x33A3` in 79/79
RAM-Snapshots. Daraus folgt kein eindeutiger UART1-RX-Pointer,
kein ISR-Gate und kein Recht zu RAM-Writes.
