# WB2A / VDensHO1 20C2: UART1-P300-Nachtlauf und KM-Bus-TX-Identifikation

**2026-10-09 · Branch `optolink-p300-migration` · abgeschlossene Benutzeraufnahme,
ausschließlich Offline-Auswertung. Kein weiterer Gerätezugriff.**

## 1. Ergebnis und Status

Der Betreiber hat den am 8.10. um 22:54 MESZ gestarteten unbegrenzten
read-only systemd-Nachtlauf am 9.10. gegen 08:03 MESZ mittels
`wb2a-overnight-batch.sh stop` geordnet beendet. Das Archiv wurde
vollständig ausgewertet. **Alle 12.938 Messrunden sowie 51.752
P300-Leseantworten sind mit der gespeicherten TX/RX-Spur konsistent.**

**Neuer, positiv belegter Datenpfad:** Im bereits als UART1-DMA0-TX
klassifizierten Hauptregler-RAM liegt bei **0x161A** eine Sammlung von
**KM-Bus-formatierten Telegrammen**. Drei voneinander verschiedene
Paketformen erfüllen den öffentlich dokumentierten Rahmen und die
CRC16/Kermit-Prüfung. Der lange Broadcast mit `FF 00 B3 16` kodiert
Datum/Uhrzeit; seine Zeitfelder sind über **55 Änderungen**
mit dem Host-Zeitstempel korreliert. Das ist wesentlich mehr als
die vorherige Hypothese „UART1 ist aktiv“, aber **kein**
identifizierter GFA-RX- oder P06-Istdrehzahlkanal.

**Separater Anlagenbefund:** Das bereits lokal im VDensHO1-Profil
dokumentierte Verriegelungsbit `55D3[5] & 0x40` war ungefähr
**23:34:12 bis 07:11:37 MESZ** gesetzt. Eine
erneute, kurzzeitige Anzeige wurde 07:12:33 bis 07:12:38
beobachtet. Erst danach traten die drei natürlichen
Flammenbitfenster auf. Der Benutzer hatte einen gelegentlich
nicht anlaufenden Lüfter und die morgens manuell beseitigte
Störung bereits unabhängig beschrieben. **Daraus folgt weder
eine bewiesene Fehlerursache noch ein Nachweis eines Zusammenhangs
mit dem P300-Test.**

### Aufnahme, Originalintegrität und Wiederherstellung

- Privates Nutzerarchiv:
  `uart1-overnight-run-20261008T205413Z-126713-bundle.tar.gz`;
  SHA256 `fc96b4bbfa60931cd36226bd8bcbd21299c436959164b085ccc47e9662fd5bed`;
  exakt **1.855.082 Bytes**.
- Acht reguläre Archivdateien; die **sieben** SHA256-Dateihashes
  und Größen im internen `bundle-manifest.json` stimmen vollständig.
  Die `samples.jsonl` enthält 12.938 aufeinanderfolgende Indizes.
  Die `trace.jsonl` enthält **155.294** TX/RX-Einträge.
- Für **jede** Runde wurden vier strikte request/response/ACK-Gruppen
  rekonstruiert. Abfragefunktion, Adresse, gemeldete Länge,
  Prüfsumme und sämtliche Nutzdaten stimmen **51.752/51.752**
  mit den entsprechenden gespeicherten Samples überein:
  `FC01 55D3/11`, `FC03 0020/16`,
  `FC03 1600/32`, `FC03 1620/32`.
- Kein fremder TX-Befehl und **kein Write** in der aufgezeichneten
  P300-Beobachtungsphase. Die vier VS1-GFA-Leseantworten vor
  beziehungsweise nach dem Versuch sind separat zuzuordnen.
- `measurement.errors=[]`, `observation_complete=true`,
  `operator_stop=true`. Die Rückkehr zu VS1 sowie alle zuvor
  aktiven sechs Dienste/Timer sind dokumentiert erfolgreich.
  P80 kam anschließend als `20`, P06 gültig als `00`.
  **HA-Entity-Frische wurde nicht separat verifiziert**
  (`ha_entity_freshness_verified=false`).
- Das Originalarchiv und die vollständigen privaten Trace-/RAM-Zeitreihen
  werden **nicht** auf GitHub kopiert.
  [Abgeleitete, datensparsame Prüfevidenz](evidence/p300-uart1-overnight-result-2026-10-09.json).

## 2. Drei vollständige Flammenbitfenster nach Ende der langen Verriegelung

Zeitstempel in MESZ; dies sind **erste/letzte beobachtete
Host-Samples**, keine physikalisch exakten Zünd-/Abschaltzeiten.

| Abschnitt | Erstes Flammensample | Letztes Flammensample | Sample-Abstand |
|---|---|---|---:|
| 1 | 09.10. 07:12:53 | 07:20:05 | **432,37 s** |
| 2 | 09.10. 07:25:56 | 07:28:13 | **137,28 s** |
| 3 | 09.10. 07:52:48 | 07:54:45 | **116,87 s** |

Die erste erkennbare Anlauf-/Statussequenz begann bereits
**08.10. 23:33:21** mit `55D3[7]=20`, ohne Flammenbit.
Ab 23:34:12 zeigte `55D3[5]` die
bekannte Verriegelungsmaske. Das Protokoll liefert
**keinen unabhängigen Drehzahlsensor**, keinen
gesicherten F9-Fehlercode und keine Information darüber,
ob der Nutzer zu einem bestimmten Sample den Resetknopf drückte.
`55D3[7]=80` trat nach dem langen Verriegelungsfenster
20-mal auf; dieser Wert erhält hier **keinen erfundenen
Herstellerzustandsnamen**.

## 3. Warum der zweite UART jetzt als KM-Bus-formatiert einzuordnen ist

Öffentliche [OpenV-KM-Bus-Dokumentation](https://github-wiki-see.page/m/openv/openv/wiki/KM-Bus)
beschreibt die Grammatik:

~~~text
[DK][SK][CMD][LEN][DSL][SSK][...][CRC1][CRC2]
CRC16/Kermit: init=0000, reflected polynomial=8408, CRC low/high
~~~

Die bereits bestätigte physische DMA0-TX-Quelladresse
`0x161B` zeigt **in einen vollständigen RAM-Frame,
der bereits bei `0x161A` beginnt**:

| Typ | Erster vollständiger, aus RAM rekonstruierter Frame | CRC16 des ganzen Frames |
|---|---|---|
| KM-Bus `B1`, 10 Byte | `01 00 B1 0A 01 01 01 06 C7 31` | **0000** |
| KM-Bus `B3`, 12 Byte | `20 00 B3 0C EE 01 10 C2 11 F9 E4 9B` | **0000** |
| KM-Bus `B3`, 22-Byte-Broadcast | `FF 00 B3 16 00 01 01 20 02 26 03 10 04 08 05 22 06 50 07 45 21 12` | **0000** |

Der 12-Byte-Typ mit `20 00 B3 0C EE 01 10 ... 11 ...`
hat sogar dieselbe Ziel-/Slot-/Adresspaarform wie das
öffentliche OpenV-Beispiel für KM-Bus-Datensendungen.

**Vollständiger Puffer-Scan:** 12.573/12.938
RAM-Snapshots enthalten einen anhand `LEN` rekonstruierten,
CRC16/Kermit-gültigen Frame. **365** Pufferansichten
bestehen die CRC nicht. Das ist *kein* Beweis für
tatsächlich fehlerhafte UART1-Wire-Telegramme:
Der RAM wird nicht atomar gelesen, insbesondere
`0x1600/32` und `0x1620/32` stammen aus zwei
aufeinanderfolgenden FC03-Aufträgen. DMA kann
währenddessen einen TX-Puffer verändern.

### 22-Byte-Broadcast: Tag/Wert-Uhrzeit

Der Frame `FF 00 B3 16` trat in **519** RAM-Samples auf,
davon **513** mit gültiger KM-Bus-CRC.
Sein Tag-/Wertmuster ist über den lokalen
Tageswechsel und die nächsten acht Stunden dekodierbar:

| Bytepaar | Beispiel | Durch Uhrzeit bestätigte Zuordnung |
|---|---|---|
| `01 20` | 20 | Jahrtausend/Jahrhundert 20, Interpretation nach BCD |
| `02 26` | 26 | Jahr 2026, zweistellige Jahreszahl |
| `03 10` | 10 | Monat Oktober |
| `04 08` → `04 09` | 08 / 09 | Tag des Monats, wechselt um Mitternacht |
| `05 22` → `05 00` | 22 / 00 | Stunde |
| `06 50` → `06 00` | 50 / 00 | Minute |
| `07 45` → `07 23` | 45 / 23 | Sekunde |

Insgesamt **55** Übergänge der vier dynamischen
Datum-/Zeitfelder; der jeweilige neue Zeitstempel
lag **3,146–6,175 s**, Median **4,574 s**,
vor dem ersten Host-Sample, das ihn anzeigt.
Die registrierten Änderungen erfolgen
typischerweise in Intervallen um **596 s**.
Die erste archivierte Probe enthält eine schon
zuvor gespeicherte Uhrzeit und ist daher
aus der Lag-Statistik ausgenommen.

Damit ist im Speicher **kein bloßes zufälliges
Muster** zu sehen: Der Aufbau stimmt byteweise
mit dem KM-Bus-Frameformat, die CRC stimmt,
und die BCD-Uhrzeit folgt dem echten Datum.
Die physische Gegenstelle und die Empfangsrichtung
sind damit jedoch **nicht** nachgewiesen.

## 4. DMA0-TX-Quellzeiger und Endpositionen

Das DMA0-Ziel blieb bei **0x03AA** in 12.938/12.938 Samples
(UART1-U1TB im historischen M16C-Registermodell).
Der Quellzeiger war 12.745-mal `0x161B`
und 193-mal weitergerückt. Der **Inhalt** des
Speicherbytes an Adresse `0x161B` blieb durchgehend
`00`; Zeigerstand und Speicherinhalt sind
voneinander zu unterscheiden.

`SAR0 + TCR0` nimmt genau vier beobachtete Endwerte an:

| DMA-Endwert | Samples |
|---|---:|
| `0x1622` | 151 |
| `0x1623` | 10.655 |
| `0x1625` | 1.612 |
| `0x162F` | 520 |

Auch während der mehrstündigen Verriegelung
gab es **165** Stichproben mit weitergerücktem
DMA0-Quellzeiger. Das passt zu allgemeinem
Kommunikationsverkehr unabhängig von einer
aktiven Brennerflamme. Die meisten vollständigen
20-Byte-DMA-Resttransfers fallen mit dem
22-Byte-`B3/16`-Zeittelegramm zusammen.
Dieser Satz beschreibt **beobachtete gemeinsame
Puffer-/DMA-Zustände**, keine atomar bestätigte
Busübertragung.

## 5. Konsequenzen für unsere drei Ziele

**Für P300 statt VS1:** Die zweite UART-Schnittstelle
ist im beobachteten **TX-RAM** mit dem bekannten
KM-Bus-Format verknüpft. Es wurden **keine**
unabhängige GFA-Empfangsquelle, kein VS1-GFA-P06-Alias
und kein gleichwertiger P300-GFA-Aufruf gefunden.
Kein Austausch der P06-HA-Entity, keine
volle P300-Produktionsmigration.

**Für Vitotrol-Emulation:** Der Familienbezug zu
KM-Bus-Klassen/Slots ist jetzt durch
Rohtelegramme gestützt und ist ein besonders
guter *Offline*-Ansatzpunkt. Es ist
weiterhin keine Geräteadresse, elektrische
Anbindung oder sichere Emulationsschreibfunktion
freigegeben. Eine echte Busgegenstelle
muss separat nachgewiesen werden.

**Für den Pumpen-100%-Override:** Keine
Freigabe für E7-RAM-Schleifen, andere
RAM-Writes oder Brenner-/Sicherheitseingriffe.

**Zum bekannten Gebläsefehler:** Der lange
Verriegelungszeitraum ist jetzt als
diagnostischer Zeitbeleg dokumentiert;
die Ursache kann diese Optolink-Aufzeichnung
nicht bestimmen. Die Empfehlung bleibt:
Gebläse- und Feuerungsautomatenfehler
fachkundig prüfen, keine Brennerstarts
nur für weitere Tests provozieren.

## 6. Nächster technischer Schritt

Vor **irgendeiner** weiteren Hardwaremessung:
den aus dem Speicher rekonstruierten
KM-Bus-`B1/B3/31/33`-Verkehr mit dem
öffentlichen OpenV-Parser und den vorhandenen
VDensHO1-/Vitosoft-Hardwarequellen vergleichen.
Ziel ist zunächst die
**UART1-Gegenstellen-/KM-Bus-RX-Zuordnung**,
nicht ein neuer Voll-RAM-Scan.

Danach getrennt nach einer **GFA-Istdrehzahl-RX-Quelle**
in der spezifischen WB2A-Architektur suchen.
Aus der bloßen Existenz des UART1-TX-Puffers
darf nicht geschlossen werden, dass das
GFA P06 dort empfangen wird.

Der mehrfach wiederholte P300-Paketmix des Nachtlaufs
hat seine Fragestellung beantwortet.
**Keine erneute identische Nachtmessung erforderlich.**
Original-VS1-Produktion ist wiederhergestellt;
PR #46 bleibt Research/Draft.
