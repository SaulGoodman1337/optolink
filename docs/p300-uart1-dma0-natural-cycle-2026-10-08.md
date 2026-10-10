# UART1 TX vs. RX auf WB2A/VDensHO1: Quellenbefund und gebuendelter P300-Lesetest

**2026-10-08 | Nur optolink-p300-migration / Draft-PR 46**
**Noch keine UART1-GFA-Zuordnung, keine P06-RPM-Quelle und keine Pumpen-RAM-Freigabe.**

## 1. Datenweg: statisch belegte Register und altes Laufzeitverhalten

[Eigenes M16C/62P-SFR-Snapshot-Protokoll, 26.09.2026](https://github.com/SaulGoodman1337/optolink/blob/optolink-research/config/optolink-splitter/research/physical-ram-optolink-map-2026-09-26.md#uartdma-correlation):

```text
RAM/SFR physical 0x0020..0x002F:
  1B 16 00 00 AA 03 00 00 08 00 00 00 15 00 00 00
  DMA0 source 0x0161B / dest 0x003AA (UART1 transmit U1TB)
  DMA0 TCR 8 / DM0CON 0x15
SFR physical 0x03A0..0x03AF:
  75 98 75 98 1C 07 BB 01 65 01 65 01 1D 07 C6 01
  UART1 mode U1MR @0x03A8 = 0x65
  UART1 control U1C1 @0x03AD = 0x07
```

Das 8-Bit-Controlregister `U1C1=0x07` dekodiert nach dem
[M16C/62P/vergleichbaren M16C UART-Registermodell](https://www.renesas.com/en/document/mah/m16c28-group-m16c28-m16c28b-hardware-manual)
wie folgt: **TE=1** (Sender eingeschaltet),
**TI=1** (Sende-TB leer zum Abfragezeitpunkt),
**RE=1** (Empfaenger eingeschaltet),
**RI=0** (kein ungelesenes Empfangsbyte in diesem Moment).
Das ist **eine einmalige Beobachtung, nicht der Beweis**, dass der
Empfaenger Pakete des Feuerungsautomaten empfaengt.
Die Hardwareangabe bedeutet auch nicht, dass wir bereits
den im RAM gespeicherten UART1-RX-Handler oder P06 gefunden haetten.

Ein [historischer, read-only DMA-Pointer-Watch mit
**154 SFR-Samples**](https://github.com/SaulGoodman1337/optolink/blob/optolink-research/config/optolink-splitter/research/gwg-firmware-readout-deep-dive-2026-09-26.md)
berichtete **sieben UART1-DMA0-TX-Staende**, Quellzeiger
in `0x161B..0x1622`, Ziel stets `0x03AA`, `DM0SL=0x0F`.
Die damalige Auswertung war ursprünglich gegen einen
ROM-ueber-DMA-Read gerichtet; sie ist aber ebenso
ein **eigener Laufzeitbeleg fuer eine aktive UART1-Sendeleitung**.
Sie beweist noch keine Verbindung zum GFA.

## 2. Neue Offline-Analyse der hochgeladenen 25x64 Byte

Datei:
`uart1-run-20261008T194615Z-126382-bundle.tar.gz`
(SHA256 `a0e2809c5eeb1477ac7ff3bd012cbd30c247ddebe4c8d5b63ed5e2c283e5f3c2`).
25 komplette 11-Byte-Status- und 64-Byte-RAM-Messungen,
77/77 gueltige P300-Rohantworten, VS1-Restore PASS
(siehe [vorherige vollstaendige Quellpruefung](p300-uart1-live-result-and-batch-2026-10-08.md)).

Die **fuenf** veraenderten 64-Byte-RAM-Snapshots zeigen
**sechs verschiedene Zustaende**. Blick auf das vom
alten DMA-Watch physikalisch belegte UART1-**TX**-Fenster
`0x161B..0x1622` (je acht Byte, Originalfolge, HEX):

| Probe / Zeit | UART1-TX-Quellfenster 161B..1622 | Native 55D3 Byte2 | Flammenbit |
| --- | --- | --- | --- |
| 1 / 0,522 s | `00 B1 0A 01 01 01 06 C7` | `B1` | 0 |
| 7 / 15,400 s | `00 B1 0A 01 01 01 06 C7` | `B1` | 0 |
| 8 / 17,809 s | `00 B1 0A 01 01 01 06 C7` | `B1` | 0 |
| 16 / 37,574 s | `00 B3 0C EE 01 10 C2 11` | `B1` | 0 |
| 19 / 44,867 s | `00 31 09 01 01 01 07 4E` | `B2` | 0 |
| 20 / 47,323 s | `00 B1 0A 01 01 01 06 C7` | `B2` | 0 |

Der komplette native Statusblock wechselte erstmals in
**Probe 17 bei 39,986 s** nur in Byte2 von `B1` auf `B2`.
Die volatile UART1-RAM-TX-Gruppe hatte sich zuvor ab
Probe 16 geaendert. Eine kausale oder zeitliche
Verbindung waere bei diesen sequentiell gelesen
Samples **nicht** bewiesen.

Der alte *DMA-Quellzeigerstand* `0x161B` und das neue
*RAM-Byte an Adresse* `0x161B` sind unterschiedliche
Sachverhalte. Das RAM-Byte selbst war bei allen
25 Proben `00`; der Zeiger wurde in dieser
Aufnahme **nicht erneut abgefragt**.

**Das gesuchte RX-Gegenstueck liegt NICHT automatisch
an den gleichen RAM-Adressen.** Das UART1-RXDatenregister
`U1RB @0x03AE..0x03AF` ist aus Sicherheitsgruenden
nicht Teil des folgenden Experiments. Read-Side-
Effects sind auf der M16C-UART-Familie
architektonisch relevant; es wird daher weder ein
neuer UART1-RX-Read noch ein SFR-Scan vorgenommen.

## 3. EIN weiterer kontrollierter P300-Durchlauf (nur bei natuerlichem Heizbetrieb)

[Neues Werkzeug](../tools/wb2a-uart1-dma0-cycle.py)
hat eine exakte FC01-/FC03-Abfrage-Whitelist:

| Anfrage pro Runde | Frame HEX | Erwartete Bytes |
| --- | --- | ---: |
| P300 FC01 Virtual_READ `0x55D3/11` | `41 05 00 01 55 D3 0B 39` | 11 |
| P300 FC03 Physical_READ **DMA0/SFR 0x0020/16**, historisch 154x zuvor read-only geprueft | `41 05 00 03 00 20 10 38` | 16 |
| P300 FC03 Physical_READ `0x1600/32` | `41 05 00 03 16 00 20 3E` | 32 |
| P300 FC03 Physical_READ `0x1620/32` | `41 05 00 03 16 20 20 5E` | 32 |

Achtung: Das SFR-Fenster enthaelt **nur**
DMA0-Register; UART1-RX-Datenregister wird nie gelesen.
Eine Runde besteht ausschliesslich aus den vier festen
Anfragen und deren ACKs. Der gewuenschte
Unterschied zum letzten 60-s-Test: diesmal sehen wir
**DMA-Source/TCR-Registerstand und RAM-Bytes innerhalb
einer durchgehenden P300-Sitzung**, zusaetzlich
zu den nativen Status- und Flammenbits.

- **Ein** serieller Besitzer, ein supervisierter
  VS1→P300→VS1-Wechsel, kein einzelner extra
  SFR-/GFA-Aufruf waehrend P300.
- Am Anfang und Ende werden VS1/GFA-P80/P06/P09/P87
  als Referenz/Recovery gelesen; **nicht** waehrend P300.
- Laufzeit **max. 600 Sekunden**; automatische
  Verkuerzung nach mindestens drei aufeinander
  folgenden Flammenbit-Proben, Flammenende
  und mindestens 15 s Nachlauf.
  Wenn es keinen natuerlichen Flammenzyklus gibt,
  erhaelt der Lauf nur `INCONCLUSIVE...` und
  darf nicht selbsttaetig wiederholt werden.
  Ein Brennerstart wird **nie erzwungen**.
- Timing: die vier Reads sind sequentiell,
  keine atomare Busaufnahme. Quellzeiger und
  RAM-Bytefelder duerfen nicht ohne Zeitklammer
  als gleichzeitig angenommen werden.
- Original-VS1-Rueckkehr und Rueckstart der vorher
  aktiven Dienste via denselben konservativen
  `ExecStopPost`-Pfad wie bisher.
  Fail-closed Nachkontrolle: Original-Hauptdienst
  aktiv mit WorkingDirectory `/opt/optolink`,
  neues MQTT-P80=`20`, gueltige MQTT-P06-Antwort.
  Die zusaetzlichen Aufrufe erfolgen **erst nach**
  der Rueckkehr in den Originalbetrieb.
  HA-Entity-Freshness ist dadurch nicht
  vollstaendig pruefbar.
- Ergebnisse werden **auch im Fehlerfall**
  automatisch in einem privaten `tar.gz` archiviert;
  keine komplette Konsolenabschrift mehr.
- **Keine FC C9, keine Parameter-/RAM-Writes,
  kein Pumpen-Override, kein UART1-RX-Registerread,
  kein aktiv erzwungener Heiztakt und kein
  Produktionscheckout-Aendern.**

### Der eine Befehl fuer den Nutzer

Als root in der Optolink-LXC mit vorhandenem
Experiment-Checkout:

```bash
bash /root/p300-trial-work/project/tools/wb2a-research-batch.sh execute-dma0-cycle
```

Der schon vorhandene Wrapper kontrolliert den
Entwicklungsbranch und lokale Aenderungen, fuehrt
nur ein Fast-Forward aus, laesst die bisherigen
Offline-Regressionen plus die neuen
[DMA0-Probetests](../tests/test_uart1_dma0_cycle.py)
und [Archiv-/Restore-Tests](../tests/test_uart1_dma0_cycle_archive.py)
durchlaufen und startet **nur danach** den einzelnen
supervisierten Hardwarelauf.
Er erzeugt abschliessend
`UPLOAD_ONE_FILE=/root/p300-trial-work/research-bundles/uart1-dma0-...tar.gz`.

**Der Aufruf unterbricht die normale HA-/MQTT-Telemetrie
waehrend der gesamten P300-Beobachtung.**
Er sollte daher nur gestartet werden, wenn das
betriebliche Zeitfenster eine solche Unterbrechung
erlaubt. Ein Zwischenstand zeigt den beobachteten
Brennerstatus und DMA0-Zeiger.

**Expliziter Abbruch aus zweiter root-LXC-Konsole:**

```bash
systemctl stop optolink-uart1-dma0-cycle.service
```

`ExecStopPost` versucht die Wiederherstellung der
Originaldienste auch bei vorzeitigem Workerende.
Schwerer systemd-/Strom-/Serialausfall bleibt ein
Restrisiko. Bei abgebrochener/unvollstaendiger
Wiederherstellung **nicht blind neu starten,
sondern den automatisch erzeugten Bericht
pruefen und VS1 gezielt wiederherstellen**.

## 4. Was ein Erfolg und was KEIN Erfolg bedeutet

- **DMA0 SAR0=0x161B..1622 und DAR0=0x03AA
  bewegen sich bei einem natuerlichen
  Flammenzyklus:** Neue dynamische Korrelation
  des UART1-**Sendepfades**, noch **kein** Beweis,
  dass das GFA an UART1 haengt.
- **UART1 TX-RAM-Daten korrelieren mit
  55D3-Flamme:** Interessanter Bus-/Status-Hinweis,
  aber noch **keine** isolierte RX-Datenquelle
  und kein P06-Istdrehzahlkanal.
- **Zeiger/Status bleiben konstant:** Keine
  Aussage ueber ungesampelte Flanken und
  kein "UART1 ist nicht GFA"-Beweis.
- P06/P09 als reale externe GFA-Drehzahl und
  Modulationssollwert bleiben produktiv bei
  VS1. Unter P300 bleibt P06 ungelöst.
- Kein Production-Merge und keine Aenderung
  an `optolink-splitter-ha`.
