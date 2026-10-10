# UART1-DMA0: begrenzter P300-RAM-Lesetest nach fehlenden Alt-Snapshots

**2026-10-08. Optolink-P300-Entwicklungsbranch; read-only Experiment, keine Produktionsfreigabe.**

## Anlass und Motivation

Der bisherige reine Offline-Auditor `tools/audit-uart1-gfa-ram.py` bestand
die **17 Offline-Regressionstests**, fand aber beim Nutzer
`NO_HISTORICAL_RAM_REPORT`: die am 26.09.2026 unter `/tmp` angelegten
20-KiB-RAM-Aufnahmen sind dort nicht mehr vorhanden. Es fand somit
**keine neue Analyse eines alten RAM-Binärbilds** statt. Eine alternative
lokale Aufbewahrung unter anderen Verzeichnissen ist unbekannt.

Ein begrenzter **neuer** Geräte-Read ist jetzt vorbereitet, der **nicht**
den alten Vollspeicherscan wiederholt. Aus der früheren
[20-KiB-RAM/SFR/DMA-Hardwarekarte](https://github.com/SaulGoodman1337/optolink/blob/optolink-research/config/optolink-splitter/research/physical-ram-optolink-map-2026-09-26.md)
stammt die physische Einzelbeobachtung
`DMA0 SAR0 = 0x161B`, `DMA0 DAR0 = 0x03AA (UART1 TX)`. 
Die zweite UART ist ein **Quellensuchansatz**, kein bewiesener
GFA-Anschluss. Ein TX-Quellzeiger ist **kein** P06-Istwert.

## Phase A: zuerst lokal nach alten Dateien suchen

Ausschließlich Dateisystem, **keine** Optolink-/MQTT-Abfrage:

```bash
find /root /var/tmp /opt -type f \
  \( -name 'physical-ram-*-report.json' \
  -o -name 'physical-ram-*-pass1.bin' \
  -o -name 'physical-ram-*-pass2.bin' \) -print 2>/dev/null
```

Falls **ein kompletter alter Bericht plus beide Binärdateien** gefunden
werden, erst `tools/audit-uart1-gfa-ram.py --report PATH` offline
ausführen und **nicht** zusätzlich den Live-Test starten. Das reduziert
unnötige Ausfallzeit der HA-Telemetrie.

Ist der Altbestand weg, darf der folgende explizit ausgewählte
read-only Test **einmal** durchgeführt werden, nachdem die
Offline-Tests auf dem neuen P300-Branch erfolgreich sind.

## Phase B: neuer, begrenzter Live-Test

Tool:
[`tools/wb2a-uart1-p300-focus.py`](../tools/wb2a-uart1-p300-focus.py).

### Exakte P300-Sendeallowlist

Während der Beobachtungsphase sind nur diese Telegramme plus ein
standardmäßiges `ACK=06` erlaubt:

| Zweck | P300-Protokoll | Gesendete Datenbytes |
|---|---|---|
| bekannter nativer Feuerungsautomaten-Status | FC01 Virtual_READ `0x55D3/11` | `41 05 00 01 55 D3 0B 39` |
| **UART1-DMA0-Quellumfeld, erste Hälfte** | FC03 Physical_READ `0x1600/32` | `41 05 00 03 16 00 20 3E` |
| **UART1-DMA0-Quellumfeld, zweite Hälfte** | FC03 Physical_READ `0x1620/32` | `41 05 00 03 16 20 20 5E` |

Die beiden physischen Reads sind **zusammen genau 64 Bytes** pro
Runde, Bereich `0x1600..0x163F`. Sie umfassen den früheren
DMA0-Quellzeiger `0x161B`; kein anderer RAM-Block und keine SFR-Adresse
werden abgefragt. FC03/RAM ist zuvor auf der eigenen 20C2 verifiziert.
**Kein FC C9, kein 0x41 KMBUS, kein RAM-Write, kein Parameter-Write
und kein künstlicher Brennertrigger.** Der Start-/Identitätswechsel
benutzt den seit Oktober geprüften Handshake-Helper mit festem SHA256.

### Ablauf und Grenzen

1. Mit dem bisher **laufenden** produktiven VS1-Splitter starten,
   nur root in Optolink-LXC und mit Original-WorkingDirectory
   `/opt/optolink`. Alte Beobachter/Update/Wartung beenden.
2. Prober checkt aktuelle Gerät- und Softwareidentität
   `20C2/0103`, VS1-P80=`20` und die GFA-Kanäle.
3. Der supervisierte `systemd-run`-Worker stoppt **temporär**
   die vorher aktiven Optolink-Dienste inklusive Telemetrie,
   kontrolliert alleinige serielle Portbelegung und wechselt
   auf P300.
4. **Default 60 Sekunden**, wiederholte Reihenfolge
   `55D3/11 -> 1600/32 -> 1620/32` mit
   **mindestens zwei Sekunden Pause nach jeder Runde**. 
   Grenzwerte der Laufzeit `30..180` Sekunden; nicht automatisch
   erweitern oder immer wieder starten.
5. Noch im Worker wird die **konservative Zwei-ENQ-VS1-Rückkehr**
   und die GFA-Nachkontrolle ausgeführt. `ExecStopPost` hat eine
   zweite, vom Worker-Erfolg unabhängige Zuständigkeit:
   ursprünglichen Splitter zuerst starten und seine
   Hauptschleife prüfen; erst danach zuvor aktive Zusatzdienste
   wiederherstellen. Bei Versagen **keine** automatische
   Freigabe der Zusatzschreiber.
6. Nach beendeter Unit die tatsächlichen Live-Werte von
   Originaldienst, P80, P06 und HA gesondert kontrollieren.
   Der Worker-Report kann **keine** vollständige
   HA-Aktualitätsprüfung ersetzen.

Die Probe fragt den Brennerzustand über den nativen Statusblock
ab. **Ein Brennerstart und -stopp sind NICHT erforderlich**,
um zu sehen, ob das UART1-RAM-Umfeld überhaupt Aktivität zeigt.
Wenn alle Bytes unverändert bleiben, heißt das nur
`NO_CHANGES_IN_UART1_FOCUS` und ist **kein** Beweis, dass UART1
inaktiv oder nicht mit dem GFA verbunden ist.

Unabhängig von Änderungen bleibt
`UART1_GFA_LINK=NOT_PROVEN; P06_RPM_ALIAS=NOT_PROVEN`.
Der RAM-Lesetest deckt keine RX-Pufferstruktur, keine
P06-Wertsemantik und keine Temperatur- oder Drehzahlumrechnung
automatisch auf. Physische RAM-Werte sind nicht notwendigerweise
ein zeitgleich konsistenter Busmitschnitt.

### Befehle (nur nach Offline-CI-Gate)

```bash
cd /root/p300-trial-work/project
/opt/optolink/venv/bin/python -m unittest discover \
  -s tests -p test_uart1_p300_focus.py -v

/opt/optolink/venv/bin/python tools/wb2a-uart1-p300-focus.py
```

Erwartet: vollständiges `OK` und `PLAN ONLY`.
Der zweite Befehl führt **keinen** Geräte- oder Dienstzugriff aus.

Erst danach den einmaligen, bewusst telemetrieunterbrechenden
Hardwarelauf durchführen:

```bash
/opt/optolink/venv/bin/python -u \
  /root/p300-trial-work/project/tools/wb2a-uart1-p300-focus.py \
  --execute --seconds 60
```

### Abbruch

**Aus einer zweiten root-LXC-Konsole**:

```bash
systemctl stop optolink-uart1-p300-focus.service
```

Bei erfasstem Signal versucht der Worker die
VS1-Rückkehr; `ExecStopPost` startet die zuvor aktiven
Dienste neu. Auch das ist keine Garantie bei schwerem
Strom-, Hardware- oder systemd-Ausfall. Versuche niemals,
parallel einen zweiten seriellen Optolink-Client zu starten.

### Kontrolle und Ausgaben

Nach beendetem und vollständig restauriertem Experiment:

```bash
systemctl show optolink-splitter.service \
  -p WorkingDirectory -p ActiveState -p SubState
optolink-debug request 'gfaread;0x4050;1;raw;False' --timeout 8
optolink-debug request 'gfaread;0x4006;1;raw;False' --timeout 8
```

Erwartet: Arbeitsverzeichnis `/opt/optolink`, `active/running`,
P80 `20`, gültige zustandsabhängige P06-Antwort, und
anschließend neue HA-Telemetriewerte.

Der Worker schreibt unter
`/root/p300-trial-work/uart1-p300-results/run-*/`:
`measurement.json` (komplette Messreihe inkl. Telegrammtrace),
`samples.jsonl` (Status und 64 RAM-Bytes pro Runde),
`recovery.json` (Dienstewiederherstellung) und `state.json`.
Rohdaten enthalten technische Betriebs-/Pfadinformationen,
sie gehören nicht in das öffentliche Repository.
Bei einem Fehler **nicht** unverändert wiederholen, sondern
Fehler- und Wiederherstellungsberichte prüfen.

Das Gesamtergebnis `CHANGES_SEEN_SOURCE_UNKNOWN` bedeutet
**nur**, dass sich im fraglichen Speicherfenster Bytes
verändert haben. P300-GFA-Gleichwertigkeit, P06-Ist-RPM,
die Quelle der Bytes, ihre Frische und ihre
Brennerphasenabhängigkeit bleiben offen.

## Offline-Validierung

Neuer Test `tests/test_uart1_p300_focus.py` enthält mindestens
24 draht-/ablaufspezifische Regressionen: erlaubte/abgelehnte
P300-Frames, richtige Checksummen, Response-Länge bis 37,
Fehler- und Negativquittungen, 0xFF als legitimes RAM-Byte,
ausbleibende Antwort, defekte Prüfsumme, gestörte
Zwischenphase, strikte Phase-Allowlist,
recovery after CRC fault und supervisierte
Dienstwiederherstellung.

Die CI-Workflowdatei
`.github/workflows/validate-uart1-p300-focus.yml` führt
diese simulierten Tests und die erprobten
P87-/Handover-Regressionsprüfungen aus.
**Bis zu einem tatsächlichen Geräteversuch bleibt
Hardwarefunktion und P06-Fund weiterhin offen.**

Siehe auch:
[historischer Offline-Report](p300-uart1-gfa-dataflow-offline-2026-10-08.md) und
[exakter P06-Profilvergleich](p300-fan-actual-source-screen-2026-10-08.md).
