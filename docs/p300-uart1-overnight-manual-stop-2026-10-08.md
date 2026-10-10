# WB2A / VDensHO1 20C2: operator-gesteuerter P300-Nachtlauf

**Historisches Runbook fuer den bereits abgeschlossenen Nachtlauf vom 8./9.10.2026 – nicht erneut starten.**
Der systemd-Operator-Stopp wurde am 9.10. ausgefuehrt. Original-VS1 und
die GFA-P80/P06-Lesekommunikation wurden erfolgreich wiederhergestellt.
Die vollstaendige Auswertung von 12.938 Runden zeigt jetzt
CRC-gueltige KM-Bus-TX-RAM-Telegramme, eine mehrstuendige
GFA-Verriegelungsanzeige und drei danach beobachtete Flammenfenster.
**Kein P06-Drehzahl-Alias und kein weiterer identischer Live-Test freigegeben.**
Aktueller [Nachtlaufbericht](p300-uart1-overnight-result-2026-10-09.md).

**Stand 8.10.2026 – ausschließlich Research-Branch `optolink-p300-migration`.**
Der Betreiber wünscht einen einzigen, von ihm selbst beendeten Nachtlauf mit
beliebig vielen **natürlichen** Brennerzyklen, ohne wiederholtes Copy/Paste.

## Grundregel: Keine zeitliche Höchstdauer

- **Kein `RuntimeMaxSec`, keine `--seconds`-Option und kein Stoppen nach
  dem ersten Brennerzyklus.** Der Operator beendet die Messung morgens.
- Der Prober läuft als **abgekoppelte systemd-Transient-Unit**;
  ein geschlossenes SSH-Fenster beendet den Lauf nicht.
- **Nur technische Sicherheitsabbrüche** bleiben: unerwartete
  Protokoll-/Prüfsummen-/Identitätsantwort, konkurrierender Besitzer,
  Dienstneustart, zu wenig freier Speicherplatz (**128 MiB** Reserve)
  oder Protokolldatei größer/gleich **384 MiB**.
  Diese Grenzen schützen die LXC und das produktive VS1 vor
  dauerhaft verwaisten Ressourcen. Sie sind **keine Uhrzeitbegrenzung**.
- Bei Ende durch Benutzer oder Fehler versucht der Worker immer die
  konservative Zwei-ENQ-VS1-Rückkehr und die GFA-P80-Nachkontrolle.
  `systemd ExecStopPost` stellt **zuerst den Originalsplitter**,
  erst nach dessen Bereitschaft die zuvor aktiven Zusatzdienste wieder her.
  Danach werden P80/P06 über das normale VS1/MQTT gelesen.
  Schwere Host-, Strom- oder systemd-Ausfälle können eine
  Wiederherstellung trotzdem vereiteln.

## Einmaliger Start

Auf der Optolink-LXC als root, nicht in `/opt/optolink`:

```bash
cd /root/p300-trial-work/project && git pull --ff-only origin optolink-p300-migration && bash tools/wb2a-overnight-batch.sh start
```

Der Wrapper:
1. prüft, dass das **separate Entwicklercheckout** auf dem erwarteten
   Experiment-Branch steht und keine versionierten Änderungen enthält;
2. zieht via `fetch` + `merge --ff-only` nur diesen Branch;
3. führt alle **offline**-Tests für den neuen Nacht-Worker
   sowie die vorherigen DMA0/P87/Handover-Regressionsprüfungen aus;
4. aktiviert **einmal** die beaufsichtigte, abgekoppelte
   `optolink-uart1-overnight.service`;
5. gibt `SESSION=...` und `OVERNIGHT_START_ACCEPTED=...` zurück.

Falls ein Preflight-Test fehlschlägt, startet **kein** Hardwarelauf.
Der Start-Aufruf selbst bleibt **nicht** bis morgens in der SSH-Sitzung.

## Während der Nacht

Die normale Home-Assistant-/MQTT-Telemetrie des Splitters ist
absichtlich pausiert. Der Benutzer hat diesen Verzicht für den
Versuchszeitraum ausdrücklich akzeptiert. Die Therme regelt sich
selbst weiter; keine Parameter-, Hydraulik- oder Pumpensteuerung
wird geschrieben.

Alle rund zwei Sekunden jeweils genau:

| Zweck | Erlaubte Anfrage |
|---|---|
| Nativer Flammen-/Statusblock | P300 `FC01 55D3/11` |
| Bereits bekannter DMA0-Zeiger/TCR/SFR-Block | P300 `FC03 0020/16` |
| Belegtes UART1-TX-Quell-RAM | P300 `FC03 1600/32` |
| Anschlussbereich des TX-Quell-RAM | P300 `FC03 1620/32` |

Die vier Reads sind **sequentiell** und liefern keinen atomaren
UART-Busmitschnitt. Das zuvor als Empfangsregister belegte
`U1RB @0x03AE` wird **niemals** gelesen.
**Keine GFA-Abfragen während P300**, kein C9, keine RAM- oder
Parameterwrites, kein erzwungener Brennerstart.

Folgende Rohdaten werden **fortlaufend** geschrieben, nicht
stundenlang unbeschränkt im Python-RAM gesammelt:

- `samples.jsonl`: alle kompletten Status-, DMA0- und 64-Byte-RAM-Runden;
- `trace.jsonl`: TX- und RX-Frames samt monotonic Timestamps;
  unmittelbar nacheinander empfangene RX-Bytes werden zu
  zusammenhängenden Empfangsabschnitten gebündelt;
- `progress.json`: etwa alle 30 Runden Fortschritt, aktuelles
  Flammenbit und Anzahl vollständig beobachteter natürlicher Zyklen;
- `measurement.json`: am Ende Prüfergebnis,
  Referenzen und abschließende, speicherschonend rekonstruierte Statistik;
- `recovery.json` und `health.json`: VS1-Dienst-Rollback und
  neue P80/P06-MQTT-Readbacks.

Die öffentlichen Quellcodes werden bei Start zusammen mit dem gepinnten
Handshake-Helper **privat in das Sitzungsverzeichnis kopiert**,
damit ein späterer Git-Stand den laufenden Worker nicht verändert.
Ein parallel gestarteter serieller Optolink-Client ist nicht erlaubt.

### Optionaler Status (nur Dateien/systemd, keine Zusatzreads)

```bash
bash /root/p300-trial-work/project/tools/wb2a-overnight-batch.sh status
```

Oder:

```bash
systemctl status optolink-uart1-overnight.service --no-pager
```

## Morgens: ein Stopp, eine Datei

```bash
bash /root/p300-trial-work/project/tools/wb2a-overnight-batch.sh stop
```

**Dieser Stopp ist unabhängig von GitHub und hat keine Testvorprüfung.**
Er sendet einen **geordneten systemd-Stopp**, lässt Worker und
`ExecStopPost` VS1/Dienste restaurieren und gibt die Status-/
Gesundheitsprüfung und **genau einen Uploadpfad** aus:

```text
UPLOAD_ONE_FILE=/root/p300-trial-work/research-bundles/uart1-overnight-run-...-bundle.tar.gz
```

Das private `tar.gz` enthält vollständige Rohdaten,
fortlaufende Empfangs-/Sendespuren, Vergleichsstatistik,
Hash-Manifest und die Restore-/GFA-Nachkontrolle.
**Nur diese eine Datei hochladen.**
Ein zweiter Stopp sollte das vorhandene Archiv wiederverwenden,
statt einen neuen Gerätetest oder neue Telemetrie zu starten.

**Unabhängiger Notabbruch**, falls der Batch-Runner nicht verfügbar ist:

```bash
systemctl stop optolink-uart1-overnight.service
```

Das löst ebenfalls `ExecStopPost` aus. Danach über
`.../tools/wb2a-overnight-batch.sh stop` die Restore- und
Archivausgabe einholen. Bei Recoveryfehlern weder blind neu
starten noch unter `/opt/optolink` Dateien austauschen.

## Was dieser Nachtlauf leisten kann – und was nicht

Mehrere natürliche Brennerzyklen plus DMA0-Zeigerbewegungen erlauben
wesentlich bessere Vergleiche von **UART1-TX-Aktivität,
RAM-TX-Quellpuffer und Flammen-/Modulationsstatus**.
**Aber:** Weil während P300 absichtlich keine VS1-GFA-Abfragen
erfolgen, fehlt nach wie vor eine *zeitgleiche unabhängige
P06-Istdrehzahl-Referenz*. Selbst ein langer Nachtlauf kann
daher **nicht garantieren**, den unbekannten
GFA-RX-Pfad oder einen echten P06-RPM-RAM-Spiegel zu identifizieren.

Die vollständige Analyse erfolgt erst auf Grundlage
des morgendlichen Archivs. Eine Drehzahladresse,
Pumpen-Override-Funktion oder eine Produktionsumstellung
wird durch diesen Datensammler **nicht** freigegeben.

## Regressionen und Review

- [Neuer Worker](../tools/wb2a-uart1-overnight.py)
- [Start/Status/Stopp als einheitlicher Wrapper](../tools/wb2a-overnight-batch.sh)
- [Offline-Simulations-/Failsafe-Tests](../tests/test_uart1_overnight.py)
- [GitHub-CI](../.github/workflows/validate-uart1-overnight.yml)
- [Alte 600s-Probe](p300-uart1-dma0-natural-cycle-2026-10-08.md)
  bleibt als **historische, nicht auszuführende** Variante erhalten.

Noch keine P300-Migration in Produktion, keine Änderung
an `/opt/optolink` oder `optolink-splitter-ha`.
