# WB2A / VDensHO1: Vitotrol-Discovery auf dem KM-Bus-Master-TX

**9.10.2026 – reine Offline-Analyse des beendeten P300-Nachtlaufs.**
**Keine neue Live-Abfrage, keine produktive Konfiguration, keine Writes.**

## Wichtigstes Ergebnis

Die 12.938 vorhandenen Messrunden enthalten im bereits belegten
UART1-DMA0-Sendepuffer bei **0x161A** zwei exakt decodierbare,
CRC16/Kermit-gueltige KM-Bus-Master-Telegramme fuer die Vitotrol-Klasse `0x11`.
Diese Telegramme entsprechen dem historischen
[OpenV-KM-Bus-Referenzprotokoll](https://github.com/openv/openv/wiki/KM-Bus)
zur Abfrage der vier Geraetekenndaten `F8..FB`:

| Master-Anfrage | Vollstaendiger Frame (HEX) | CRC-gueltige RAM-Samples | Nichtbenachbarte Beobachtungsfenster |
|---|---|---:|---:|
| Vitotrol `0x11`, Slot 1, Register `F8`/4 lesen | `11 00 33 0A 01 01 F8 04 49 EF` | **27** von 33 | **19** |
| Vitotrol `0x11`, Slot 2, Register `F8`/4 lesen | `11 00 33 0A 02 01 F8 04 84 CA` | **27** von 31 | **20** |

**Das Slot-1-Telegramm ist bytegenau im OpenV-Artikel enthalten.**
Dessen historische Hardwarequelle ist **V200KW2**, nicht unsere WB2A.
Der konkrete Byteabgleich am lokalen 20C2 ist der neue Befund.

Dekodierung nach Quelle: `destination=11`, `source=00` (Master),
`command=33` (mehrere Register anfordern), `length=0A`,
`target slot=01/02`, `source subclass=01`, `start address=F8`,
`count=04`, CRC16/Kermit in den letzten zwei Bytes.

**Beweisgrenze:** Wir sehen den **gesampelten Master-Sendepuffer**.
Daraus folgt weder, dass eine Fernbedienung angeschlossen ist, noch,
dass sie antwortet. Die Antwort `00 11 B3 10 ... F8 ... FB ...`
wuerde aus dem **UART1-Empfangspfad** stammen, den der
Nachtlauf absichtlich nicht ausgelesen hat.
Es wurden keine physischen KM-Bus-Signale mitgeschnitten.

Das vorherige [lokale Vitotrol-Baseline-Protokoll](https://github.com/SaulGoodman1337/optolink/blob/optolink-research/config/optolink-splitter/research/vitosoft/vitotrol-baseline-2026-09-23.md)
meldet historisch `0x27A0=0` und eine ausgeloeste
BC-Fernbedienungsstoerung bei `0x27A0=1` ohne Slaveantwort.
**Nicht erneut eine Fernbedienung konfigurieren, nur um die
Discovery zu erzwingen.**

## Alle 12.938 TX-Pufferansichten nach KM-Bus-Header geprueft

Die vier Optolink-P300-Lesetransaktionen je Runde sind
bereits **51.752/51.752** mit dem originalen TX/RX-Trace
abgeglichen; P300->VS1-Rueckkehr und GFA P80/P06 waren erfolgreich
([Nachtlaufbericht](p300-uart1-overnight-result-2026-10-09.md)).

Der neue rein lokale Klassifikator hat alle 64-Byte-RAM-Felder
nach Zielklasse, Quellklasse, KM-Bus-Befehl, Laenge, Slot und
CRC16/Kermit geordnet:
**12.573 gueltige Pufferansichten**, **365** CRC-inkonsistente.
Die Letzteren sind nicht automatisch defekte Drahttelegramme,
da RAM und DMA bei zwei aufeinanderfolgenden FC03-Leseauftraegen
weiterarbeiten koennen.

| Typ / Beispiel | CRC-gueltige Samples | Quellenbezogene Bedeutung |
|---|---:|---|
| `01 00 B1 0A 01 01 01 06 C7 31` | 10.282 fuer den B1/01-Header; dieser Einzelwert 10.253 | Klasse `01`, Slot 1, Master-Datensendung Register `01=06`; Geraetenamen unbekannt |
| `20 00 B3 0C EE 01 10 C2 11 F9 E4 9B` | 1.564 fuer B3/EE | Klasse `20`, Slot `EE`, Master schreibt Register `10/11` |
| `FF 00 B3 16 ...` | 513 | Bereits BCD-/CRC-validierter Datum-/Zeit-Broadcast |
| `04 00 33 0A 01 01 F8 04 50 23` | 25 | Kennungsabfrage Klasse `04`, Slot 1; Quellendefinition aus V200KW2 legt eine Erweiterung nahe |
| `11 00 33 0A 01/02 01 F8 04 CRC` | 54 | Vitotrol-Klasse, Kennung ab `F8` lesen |

**Zweiter exakter Quellenabgleich:** Der OpenV-Artikel dokumentiert
fuer die aeltere V200KW2 auch genau die Kombination
`20 00 B3 0C EE 01 10 xx 11 yy CRC`.
Dort wird Slot `20/EE` als moeglicherweise *intern angebunden*
beschrieben; das konkrete Geraet und die Semantik
der Register `10/11` bleiben im OpenV-Text offen.
Aus der Bytegleichheit am 20C2 folgt **keine**
unabhaengige Geblaese-Istdrehzahl.

### Beobachtungseinheiten und Brennerverriegelung

**45 von 54** CRC-gueltigen Vitotrol-ID-Anfrage-Samples
wurden bei gesetztem, vorher zugeordnetem
Verriegelungsbit `0x55D3[5] & 0x40` gespeichert.
Zwei weitere waehrend gesetztem Flammenbit.
Der KM-Bus-Master-Datenpfad arbeitet damit erkennbar
auch in einer Phase ohne regulare Flamme.
Die Ursache der bekannten Geblaese-Anlaufstoerung
ist daraus nicht ableitbar.

**54 sind Speicher-Sampleansichten, nicht 54 sicher
gesendete Telegramme!** Die 39 getrennten validierten
Beobachtungsfenster sind ebenfalls keine
On-Wire-Telegrammzaehlung. Die Aufzeichnung tastete
ungefaehr alle 2,5 s ab; kurze Busnachrichten
zwischen den Messpunkten bleiben unbeobachtet.

## Reproduzierbar ohne neue Geraetezugriffe

Der neue [Offline-Klassifikator](../tools/audit-kmbus-master-tx.py)
verwendet zunaechst den bereits vorhandenen
[Bundle-/TX/RX-Auditor](../tools/audit-uart1-overnight-bundle.py)
fuer Quelldatei-Hashes und framegenaue Optolink-Kontrolle.
Anschliessend klassifiziert er ausschliesslich
die archivierten RAM-Puffer. Mit einem
vorhandenen `tar.gz`-Archiv:

```bash
python3 tools/audit-kmbus-master-tx.py \
  /pfad/uart1-overnight-run-20261008T205413Z-126713-bundle.tar.gz \
  --output /neuer/pfad/kmbus-master-tx.json
```

Ohne Archivpfad druckt der Code nur `PLAN ONLY`.
[12 Offline-Tests](../tests/test_kmbus_master_tx.py)
decken F8/04, CRC, fremde Klassen, Probenlatenz, Statusbits und
die fehlende Schreib-/Aliasfreigabe ab.

Verifizierte Quelle: privates Userarchiv
`uart1-overnight-run-20261008T205413Z-126713-bundle.tar.gz`,
SHA256 `fc96b4bbfa60931cd36226bd8bcbd21299c436959164b085ccc47e9662fd5bed`.
Die Rohdatei wird nicht nach GitHub gestellt.
[Abgeleitete Quelle und Negativfreigaben](evidence/p300-kmbus-vitotrol-master-tx-2026-10-09.json).

## Der folgende technisch notwendige Schritt

**Gesucht ist nicht mehr, ob die WB2A an Vitotrol-Slots
gerichtete KM-Bus-Anfragen erstellt: Das ist beobachtet.**
Gesucht ist stattdessen eine **begruendete UART1-RX-
Puffer-/ISR-Zuordnung** im Hauptregler, um
echte Antwortdaten von eigenen TX-Puffern zu unterscheiden.

- Firmware-/Interrupt-Service- oder vorhandene
  RAM-Strukturbelege fuer UART1-RX suchen,
  bevor eine konkrete Adresse empfohlen wird.
- Das M16C-Empfangsdatenregister `U1RB @ 0x03AE`
  **nicht probeweise lesen**: Zugriffe koennen den RX-Zustand
  und Flags beeinflussen.
- Keine Optolink-RAM-Writes, keine Fake-Vitotrol-Identitaet
  und keine Konfiguration `0x27A0=1` ohne validierten
  physischen oder sicheren virtuellen Slavepfad.
- Wenn eine RX-Quelle spaeter belegbar wird,
  erst die echte Antwortsignatur `00 11 B3`
  sowie Frische, Rolle und Device-Gates pruefen.
- Dieser Fortschritt beweist **keinen GFA-P06-RPM-Alias**;
  GFA-Kommunikation und KM-Bus muessen getrennt bleiben.

**Status:** Vitotrol-Masterdiscovery unter P300 aus RAM
nachgewiesen, RX/physische Slaveantwort offen,
VS1-Produktion unveraendert, P300-PR weiter Draft.
