# WB2A P300: UART1-Hardwareergebnis und Ein-Befehl-Forschungsbatch

**2026-10-08 | Nur Branch optolink-p300-migration | keine Produktionsfreigabe**

## 1. Original-UART1-Fokuslauf bereits abgeschlossen; nicht wiederholen

Das vom Betreiber hochgeladene LXC-Transkript enthielt den gesamten
Sitzungsbericht und die TX/RX-Spur fuer den ersten UART1-DMA0-Fokuslauf
`run-20261008T194615Z-126382`. Die Auswertung wurde aus dem
kompletten 25-Runden-`measurement.json`-Teil direkt aus dem Transkript
reproduziert, nicht nur aus dem ausgegebenen JSON-Summary.

| Feld | Beobachtung |
|---|---|
| Entwicklungscode | Commit `2c80a058cdc3ee80c74af17466110a585bb0018f` |
| Testregressionen in LXC | 29/29 erfolgreich |
| systemd Ergebnis | `success`, gemeldete Laufzeit 75,826 s |
| P300-Beobachtungsphase | 60 s |
| Status+RAM-Paare | 25, alle mit 55D3/11 und je FC03 0x1600/32, 0x1620/32 |
| Alternative 64-Byte-RAM-Zustaende | **6** |
| Echte Adressaenderungen | **15** RAM-Adressen |
| Aktivitaetsereignisse | **5** bei etwa 15,40 / 17,81 / 37,57 / 44,87 / 47,32 s |
| Gepruefte Ankeradresse `0x161B` | **0** Aenderungen |
| Status `55D3[7]` | `00` in allen 25 Samples |
| GFA-P06/P09/P87 davor und danach | Je `00`; P80 jeweils `20` |
| Telegrammausgang | 25x FC01 Status, 25x FC03 1600, 25x FC03 1620, nur bekannte Steuersignale und VS1-Lesebefehle |
| Beobachtungsfehler | Keine |
| Rueckkehr | `observation_complete=true`, `vs1_link_restored=true`, `services_restored=true`, `GFA_AFTER P80=20` |

Exakte kleine, nicht-private Datenableitung mit SHA256 der Quelle:
[Evidenz JSON](evidence/p300-uart1-focus-result-2026-10-08.json).

**Evidenzgrenze:** Der Brenner war in diesem 60-s-Fenster in
den beobachteten Status-/P06-Zustaenden nicht aktiv. Die
5 RAM-Aktivitaetsereignisse sind **nicht** mit Drehzahl,
einer UART1-GFA-Verbindung oder einem Empfangspuffer
gleichzusetzen. Die historischen UART1-TX-Quelle `SAR0=0x161B`
hat **in diesem Fenster nicht gewechselt**. Das beweist
weder UART1-noch-GFA noch seine Inaktivitaet in anderen
Betriebsphasen. Ein neuer gleicher Messlauf ist derzeit
nicht begruendet.


### Vollstaendiges privates Originalarchiv verifiziert

Das nachgereichte Archiv
`uart1-run-20261008T194615Z-126382-bundle.tar.gz` wurde
unabhaengig vom bisherigen Konsolentranskript geprueft:
**SHA256**
`a0e2809c5eeb1477ac7ff3bd012cbd30c247ddebe4c8d5b63ed5e2c283e5f3c2`.
Die SHA256-Werte seiner Originaldateien stehen in der
[abgeleiteten Evidenz](evidence/p300-uart1-focus-result-2026-10-08.json).
Das Archiv mit privaten Rohdaten wird **nicht** auf GitHub hochgeladen.

- **77/77 erneut rekonstruierte P300-Antworten**:
  1x Geraetekennung, 1x Firmware, 25x `FC01 55D3/11`,
  25x `FC03 0x1600/32`, 25x `FC03 0x1620/32`.
  Alle ueberprueften ACK/STX, Funktionscodes, Adressen,
  Laengen, Daten und Checksummen stimmen mit den
  gespeicherten Samples ueberein. Keine Fehler.
- Volltrace: **2763** Eintraege, **170 TX und 2593 RX**,
  monotone Zeitstempel, nur freigegebene Sendeauftraege.
  **143 Offline-Regressionstests** im Originalarchiv:
  29 UART1-Fokus, 17 UART1-RAM, 37 P87, 60 Handover.
- Der Batch-Gesundheitscheck nach der Wiederherstellung
  meldet originalen VS1-Splitter `active/running` im
  Verzeichnis `/opt/optolink` und erfolgreiche
  MQTT-Leseantworten P80=`20` und P06=`00`.
  **Die Frische aller HA-Entitaeten wurde nicht separat geprueft.**
- Die 15 aktiven RAM-Byteadressen bilden wiederholte
  Aenderungsgruppen `0x160F/10` (je 5 Aenderungen),
  `0x1615/16` (je 4), `0x161C/1D` (je 3),
  `0x1620..1623` (2-3). `0x160B/C` wechselten
  je einmal und blieben danach stabil.
  Die historisch beobachtete UART1-DMA-TX-Quelladresse
  `0x161B` enthaelt hier durchgaengig `00` und
  wurde nicht veraendert.
- Im **kompletten** Statusblock `55D3/11` wechselte
  nur Byteindex 2 von `B1` auf `B2`,
  erstmals bei Probe 17 (`39,986 s`).
  Das P87-Statusbyte, Index 7, blieb `00`.
  Daraus folgt **keine** kausale Verbindung
  zur GFA-Istdrehzahl oder zum UART1-RX.

**Interpretation:** Der 60-s-Leselauf samt Restore
ist bestaetigt, aber er enthaelt nur eine Brenner-Aus-
Phase. Deshalb keine P06-RPM-Adresse freigeben,
den gleichen Test nicht nochmals wiederholen;
zuerst die UART1-/GFA-Empfangsseite
aus statischen Firmware-/Kommunikationsquellen eingrenzen.


## 2. Das neue Ein-Befehl-Werkzeug

Der Betreiber benoetigt weniger gestueckelte Copy/Paste-Bloecke.
Daher wurde ein Research-Orchestrator in den P300-Branch aufgenommen:

- [`tools/wb2a-research-batch.sh`](../tools/wb2a-research-batch.sh):
  nur im festen Entwicklungscheckout
  `/root/p300-trial-work/project`, verifiziert
  Branchname `optolink-p300-migration` und fehlende
  versionierte Aenderungen, fuehrt `git fetch` und
  `git merge --ff-only` aus; greift den Produktionscheckout
  `/opt/optolink` nicht an.
- [`tools/wb2a-research-batch.py`](../tools/wb2a-research-batch.py):
  `collect` prueft vor Ort vorhandene Testdaten, fuehrt
  offline 4 relevante Regressionstestgruppen aus,
  validiert die zuletzt gespeicherte UART1-Session gegen
  `samples.jsonl`, alle 64 RAM-Bytes, GFA-P80,
  die gesendete P300-Frame-Allowlist und jetzt auch die
  **Rohantworten inklusive Checksumme und Payload je Sample**
  und prueft die laufende VS1-`systemd`-Instanz.
- Anschliessend werden ueber `optolink-debug request`
  ausschliesslich die bekannten **lesenden** VS1-GFA-P80
  und P06 abgefragt und die Auftragsantworten mit Status
  in den lokalen `health.json`-Bericht aufgenommen. Der
  Orchestrator meldet **keine verifizierte HA-Freshness**,
  weil bloesse MQTT-Antworten kein HA-Sensoraktualitaetsbeleg sind.
- Ein **privates** `.tar.gz` unter
  `/root/p300-trial-work/research-bundles/` nimmt
  `measurement.json`, `samples.jsonl`, `recovery.json`,
  `state.json`, `batch-analysis.json`, `batch-health.json`
  und ein `offline-tests.txt` auf. Ueber GitHub
  wird **kein** privater RAM-Rohmitschnitt hochgeladen.
- Bei gleichem Session-Namen und gleichen Rohdateien
  verwendet `collect` dasselbe bereits gepruefte Archiv;
  kein erneutes Multi-KiB-Cat, keine Endlosschleife.
- Ein eigener `execute-uart1`-Modus kann grundsaetzlich
  einen bereits geprüften, supervisierten Hardwaretest
  mit Offline-Gate anstossen. **Hier verweigert er aber
  eine Wiederholung**, sobald eine erfolgreich dokumentierte
  UART1-Sitzung gefunden wird (`UART1_PROFILE_ALREADY_COMPLETED`).
  Neue Adresslisten/Profile erfordern ihren **eigenen,
  vorher geprueften Review**, nicht einen universellen
  Blind-Sweeper.

### Einmalig nach diesem Commit aktualisieren und sammeln

```bash
cd /root/p300-trial-work/project &&
git pull --ff-only origin optolink-p300-migration &&
bash tools/wb2a-research-batch.sh collect
```

Bei spaeteren Arbeitsbloecken nur noch **eine** Zeile:

```bash
bash /root/p300-trial-work/project/tools/wb2a-research-batch.sh collect
```

Erwartet: `OFFLINE_TEST ... PASS`, ein
`RESULT=VALIDATED_EXISTING_DATA, NOT_A_NEW_DEVICE_READ`,
`MAIN_SERVICE=PASS` (bei verifiziertem laufendem Splitter)
und `UPLOAD_ONE_FILE=/root/p300-trial-work/research-bundles/...tar.gz`.

Das erneute Sammeln **ist optional**: Der aktuelle UART1-Befund
ist bereits vollstaendig aus dem hochgeladenen Konsolentext
ausgewertet; kein weiterer Copy/Paste-Schritt ist fuer das
vorliegende Ergebnis erforderlich.

### Sicherheitsregeln auch beim Batch

1. **Voraussetzung für neue, nichttriviale RAM-Zugriffe**
   bleibt ein fest begruendeter Adressbereich mit eigener
   P300-Frame-Allowlist, Offline-Tests und Stop-/Restore-Pfad.
2. **Maximal ein serieller Besitzer zur Zeit**.
   Eine zusammengefasste Messung darf mehrere **vorher
   belegte reine Leseauftraege** innerhalb einer
   P300-Sitzung ausfuehren; keine unkontrollierten
   sequentiellen Dienststopps.
3. **Dauer und Anzahl** begrenzen; bei Fehler
   **sofort** abbrechen und original VS1 restaurieren.
4. Status, vorhandene GFA-Daten, RAM-Bytes,
   Kommando-Trace, Nachkontrolle und die
   Ergebnisdateien werden fuer die gemeinsam
   festgelegte Fragestellung in einem Durchgang
   gespeichert.
5. **Kein automatisches Nachversuchen** von
   fehlerhaften Schreib-/Verbindungsoperationen.
   Ueber UART1/GFA, E7 oder Pumpen-RAM wird
   nichts freigegeben.
6. Kein Merge in den produktiven
   `optolink-splitter-ha`-Branch, keine neuen
   HA-P06-Drehzahl-Aliase.

**Die weiteren Untersuchungen sollen erst auf den jetzt
gesicherten UART1-Datenaenderungen und der historischen
Firmware-Analyse aufbauen**, nicht mit einem weiteren
identischen 60-s-Fenster beginnen.
