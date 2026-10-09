# WB2A/VDensHO1 20C2: P300 Deep Logger, VS1-P06-Referenz gegen nativen RAM

**9.10.2026 | Research-Branch `optolink-p300-migration` | PR #46 bleibt Draft.
Keine Produktivmigration, keine RAM- oder Parameter-Writes.**

## Auftrag und Unterschied zum abgeschlossenen Nachtlauf

**Aufgabe 1:** Das produktive VS1-/GFA-System soll spaeter vollständig
durch eine P300-Architektur abgeloest werden, **ohne Verlust einer
heute vorhandenen Funktion**, insbesondere der **ECHTEN
Geblaese-Istdrehzahl GFA P06**. Die P300-Drehzahlquelle
wurde noch nicht gefunden. Keine Stellvertreterwerte zulassen.

Vitotrol-Emulation ist erst **Aufgabe 2**, nachdem Aufgabe 1
vollstaendig funktioniert und dann in einem **getrennten Branch**.
Der Pumpenoverride ist **Aufgabe 3**. Beide werden mit
diesem Logger **nicht** entwickelt, emuliert oder geschrieben.

Der vom 8./9.10. durchgelaufene P300-Nachtlogger lieferte
12.938 Runden, jedoch **keine einzige zeitgleiche GFA-P06-
Messung** in der P300-Phase. Darum liefert eine unveraenderte
Wiederholung kaum neuen Ist-RPM-Beweis.

**Das neue Messprinzip ist neu und zielgerichtet:**
Die LXC betreibt nach dem einzigen initialen Stoppen der
produktiven Serial-Owner abwechselnd **VS1** und **P300**
ueber *denselben* exklusiv geoefneten Port.
Damit erhalten wir echte GFA-P06-Rohreferenzen, dynamische
P09-Sollwerte und native P300-RAM-Beobachtungen samt
exakten Zeitfenstern **aus einem durchgehenden Versuchsarchiv**.

Kein gleichzeitiger VS1-GFA/P300-Read ist moeglich:
Wechsel- und Abfragezeit erzeugen eine kausale Luecke,
die in der Auswertung niemals verschwiegen werden darf.
Eine Korrelation kann einen P06-RAM-Alias **nicht automatisch
beweisen**. Frische, physikalische Bedeutung und
Unabhaengigkeit vom letzten VS1-GFA-Read muessen getrennt
validiert werden.

## Einmaliges Starten fuer vier oder sechs Stunden

Als `root` in der **Optolink-LXC**, Entwicklercheckout
`/root/p300-trial-work/project`. Der neue Logger ist
nur auf `optolink-p300-migration` versioniert.

**Einmalig nach dem neuen GitHub-Commit:**

```bash
cd /root/p300-trial-work/project &&
git fetch origin optolink-p300-migration &&
git merge --ff-only FETCH_HEAD &&
bash tools/wb2a-p300-deep-logger.sh start 4
```

*Vier Stunden* sind der Default. Alternativ nach exakt
derselben Aktualisierung:

```bash
bash /root/p300-trial-work/project/tools/wb2a-p300-deep-logger.sh start 6
```

Akzeptierter Bereich: **1–8 Stunden**. Der systemd-Dienst
endet auch ohne Eingriff am konfigurierten Zeitlimit und
durchlaeuft dann **dieselbe Wiederherstellung wie bei
manuellem Stopp**. Er stoppt **nicht** nach einem
einzelnen oder einer bestimmten Anzahl Brennerzyklen.
Es werden ausschliesslich **natuerliche** Zyklen
aufgezeichnet, kein Brennerstart wird erzwungen.

**Achtung fuer den Betrieb:** Wie beim vorherigen
Nachtlauf sind die produktiven Optolink-/MQTT-
Zusatzdienste **waehrend des exklusiven Loggerlaufs
absichtlich angehalten**. Die Therme steuert ihre
normale Heizung unabhaengig weiter; allerdings werden
in diesem Zeitfenster bestehende HA-/MQTT-/Service-
Funktionen des Splitters **nicht bereitgestellt**.
Die Anforderung, diese spaeter bei der fertigen
P300-Migration zu erhalten, bleibt unveraendert.
Zusaetzliche Leser duerfen den seriellen Port
nicht gleichzeitig oeffnen.

Nach dem einmaligen Vorab-`git merge` prueft der
Start-Wrapper:
Entwicklungs-Branch, unveraenderten Git-Checkout,
Regressionstests (neuer Logger plus alter
systemd-/VS1-Recovery-Code), bekannte LXC-Port-Identitaet,
keine parallelen Loggerdienste und den zuvor
laufenden Original-Splitter. Erst danach wird
`optolink-p300-deep-logger.service` gestartet.
`--start` arbeitet abgekoppelt von deiner SSH-Sitzung.

## Was genau aufgezeichnet wird

### A. VS1: echte GFA-Daten, dicht im Zeitverlauf

Pro Referenzrunde:

```text
VS1 6B GFA_READ P06 (0x4006)  -> reale Geblaese-Istdrehzahl, raw*30 rpm
VS1 6B GFA_READ P09 (0x4009)  -> Modulationsanforderung, KEIN Ist-RPM
VS1 6B GFA_READ P87 (0x4057)  -> GFA-Statusbyte
VS1 6B GFA_READ P06 (0x4006)  -> Zweitwert zur Drift-/Stabilitaetsklammer
```

Jede **zehnte** Runde ergaenzt:

```text
P10 (0x400A)  -> bisheriges GFA-Quellprofil, Rohbyte
P84 (0x4054)  -> bisheriges GFA-Quellprofil, Rohbyte
P80 (0x4050)  -> GFA-Typkennung zwingend 0x20
```

Zusaetzlich erfolgen gepruefte VS1-Geraete- und
Softwarekennung bei Protokollbeitritt (20C2/0103).
Alle Einzelreads liefern eigenen monotonic- und
UTC-Zeitstempel, Rohhex, Dauer und bei P06
die berechnete Einheit RPM. **0xFF wird NIEMALS
als 7.650 rpm behandelt**, sondern als ungueltige
Probe dokumentiert. Fuer P80 wird genau **ein
bereits in der Altimplementierung belegter
150-ms-Retry** bei 0xFF erlaubt;
eine danach ungueltige Typkennung beendet den Lauf
geordnet mit Original-VS1-Restore.

VS1-Referenzfenster dauern nominal **50 Sekunden**.
Ein P06-Anstieg von 0 auf eine reale Nichtnull-Drehzahl
veranlasst nach ca. sechs Sekunden Referenzbeobachtung
einen fruehen Wechsel zur P300-RAM-Seite.
Die vier Bytewerte innerhalb einer VS1-Klammer
sind ebenfalls **sequentiell**, nicht atomar.

### B. P300: Status und DMA in jedem Durchlauf

Nur bereits lokal erfolgreich benutzte Abfragen;
jede einzelne TX/RX-Nachricht, ihre Bestaetigung,
Response-FC, Adresse, Laenge, Payload und Checksumme
werden als Roh- und strukturierte Daten protokolliert.

| Typ | Adresse / Laenge | Alle P300-Runden | Inhalt |
|---|---|:---:|---|
| FC01 | `0x55D3 / 11` | Ja | Alle 11 nativen Feuerungsautomaten-Statusbytes einschliesslich Flammenbit, Verriegelungsbit und P87-Kandidat |
| FC03 | `0x0020 / 16` | Ja | DMA0 SAR, DAR, TCR und zugehoerige Steuerfelder; historische UART1-TX-Korrelation |
| FC03 | `0x1600 / 32` | Ja | Gesicherter UART1-KM-Bus-TX-RAM |
| FC03 | `0x1620 / 32` | Ja | Direkt angrenzende UART1-TX-Daten und Ring-/Zeitfelder |
| FC03 | `0x15E0 / 32` | Jede 6. Runde | Historisch lesbares benachbartes RAM-Fenster |
| FC03 | `0x1640 / 32` | Jede 6. Runde | Historisch lesbares benachbartes RAM-Fenster |
| FC03 | `0x18F8 / 32` | Jede 6. Runde | Vorher separat vermessene interne RAM-/Zeigerstruktur |
| FC03 | `0x1A70 / 32` | Jede 6. Runde | Vorher separat vermessene Kommunikations-Descriptorstruktur |

Normales P300-Fenster: **75 Sekunden**, zwischen
Runden mindestens 1 Sekunde Startabstand, wenn
die Busausfuehrung das erlaubt. Ein
beobachteter Wechsel des Flammenbits verkürzt
die Phase nach vier weiteren Sekunden
Statusbeobachtung: Wir kehren dann zu VS1 zurueck,
um die echte P06 nach dem P300-Ereignis rasch
wieder zu sehen. Auf dem konservativen
**Zwei-ENQ-Rueckweg** dauert diese Rueckkehr
hardwaregemessen Sekunden; **keine**
Milliseconden-Simultanmessung vortaeuschen.

Bei jeder P300-Runde werden beobachtete
DMA0-Source und Destination, Restzahl,
Statusbyte7, alle elf Statusbytes,
Flamme/Verriegelung, UTC/monotonic, jeweilige
einzelne Lesezeit und der Abstand zur letzten
VS1-GFA-Referenz gespeichert.

**Ausdruecklich NICHT enthalten:**
- Unbekannte C9-/GFA-Reads unter P300: an lokaler WB2A nicht bewiesen.
- `U1RB @ 0x03AE`: moegliche Receive-Flag-Nebenwirkungen.
- Komplettscan aller 20 KiB RAM oder neue frei
  erfundene Adressen/Opcode-Reihen.
- `0x196C..0x1A6D` als Drehzahlkandidat: das ist
  **eigener Optolink-RX/TX-/Ringraum**, nicht ein
  unabhängiger GFA-Sensor. Die bereits historische,
  separat gelesene 0x1A70-Deskriptorregion ist
  davon getrennt und bleibt nur Datenquelle,
  nicht RPM-Alias.
- Keine Parameter-/RAM-Schreibauftraege, kein
  Pumpenoverride und keine Vitotrol-Emulation.

## Datenerhalt und automatischer Rueckweg

Systemd-Transient-Unit:
`optolink-p300-deep-logger.service`.
Die Laufzeit-Pythondateien (Logger, uebernommenes
getestetes UART1-/Recovery-Modul,
exakt gepinnter 20C2-Handshake-Helper)
werden mit SHA256 im privaten Sessionsverzeichnis
gesichert. Spaetere Git-Updates aendern den
laufenden Worker **nicht**.

In der LXC:

```text
/root/p300-trial-work/p300-deep-results/run-<UTC>-<PID>/
  logger.py                 (tatsaechlich gestartete Codekopie)
  base.py                   (geprueftes Supervisormodul)
  wb2a-handover-probe.py    (gepinntes VS1/P300-Transportmodul)
  state.json                (urspruenglicher systemd-Servicezustand)
  progress.json             (fortlaufender Live-Status)
  vs1.jsonl                 (alle echten GFA-Rohreferenzen)
  p300.jsonl                (alle FC01/FC03-Daten)
  switches.jsonl            (alle VS1/P300-Wechsel mit Grund/Dauer)
  trace.jsonl               (alle Host-TX/RX mit Monotonic-Zeit)
  measurement.json          (Abschlusszaehler und Hash-Basis)
  recovery.json             (nach Traeger-Rueckkehr)
  health.json               (neue MQTT P80/P06-Lesepruefung)
```

Logdaten werden fortlaufend geschrieben, nicht
mehrere Stunden vollstaendig im RAM des LXC gesammelt.
Bei weniger als **256 MiB** freiem Speicher bzw.
Logdatei groesser **256 MiB** wird geordnet abgebrochen.
Abweichungen von 20C2/0103, falscher P80,
unerwartete P300-Antwort, unzulaessiger DMA0-
Senderegisterwert, paralleler serieller Besitzer
oder Dienstneustart fuehren ebenfalls zum
sofortigen Fehlpfad.

Bei Ende (Zeitlimit, manuell oder Fehler)
versucht der Worker die bewaehrte
VS1-/GFA-Rueckkehr. Die separate
`ExecStopPost`-Funktion stellt **zuerst den
produktiven Originalsplitter** aus
`/opt/optolink` wieder her und wartet auf
dessen protokollierte Bereitschaft.
Erst danach werden die zuvor aktiven
Serviceprogramme, Schedule-/Party-Emulation,
Wartung, Uhren-Timer wieder aufgenommen.
Die Nachkontrolle fordert P80=20 und
einen formgueltigen P06-Read ueber den
laufenden Originalsplitter an.
Vollstaendige HA-Entity-Aktualitaet ist
darueber hinaus nicht separat nachgewiesen.

**Jeder schwere System-/Strom-/Kernelabbruch
kann die automatische Wiederherstellung trotzdem
verhindern.** Kein Programm garantiert eine
Reparatur bei vollstaendig nicht ausfuehrbarer LXC.

## Status und Stopp

Status ohne neue Optolink-Thermenabfrage:

```bash
bash /root/p300-trial-work/project/tools/wb2a-p300-deep-logger.sh status
```

Manueller geordneter Stopp, **auch vor Ablauf**:

```bash
bash /root/p300-trial-work/project/tools/wb2a-p300-deep-logger.sh stop
```

Erwartete Abschlussfelder:

```text
SERVICE_RESTORE=PASS
VS1_LINK_RESTORE=PASS
VS1_P80_P06_HEALTH=PASS
UPLOAD_ONE_FILE=/root/p300-trial-work/research-bundles/p300-deep-run-...-bundle.tar.gz
```

Den **einen angegebenen tar.gz-Pfad** auf den
Computer kopieren und hier hochladen.
Bei `NOT_VERIFIED` den kompletten Stoppbericht
mitgeben, **keinen neuen Logger starten**.
Auch bei automatischem 4h-Ende gibt `stop`
nur das schon vorhandene Archiv samt Pruefungen
aus; es wird **keine zweite Messung gestartet**.

Unabhaengiger Notstopp, falls der Wrapper
wegen lokaler Probleme nicht aufrufbar ist:

```bash
systemctl stop optolink-p300-deep-logger.service
```

Danach den eigentlichen `stop`-Wrapper zur
Archiv-/Rollback-Ausgabe verwenden.

## Was eine erfolgreiche Folgestudie leisten muss

Nach dem Upload werden alle VS1-Referenzen
und P300-Status-/RAM-Paare
**in getrennten, mit Zeitintervallen verknuepften
Analysefunktionen** ausgewertet.
Ziel: Speicherorte, deren Kandidatenbewegung
bei realem P06=0, P06>0, Anlauf, Rampen,
konstantem Betrieb und Auslauf **mehrfach
und reproduzierbar** zur realen Drehzahl passen.
Eigens erzeugte TX-Befehle, Optolinkpuffer
und P09-Modulationsproxies sind auszuschliessen.

Ein Ergebnis ist erst ein
**produktiver P06-Ersatz**, wenn die
unabhaengige P300-Messquelle
mit identifizierter Semantik,
aktueller Frische, plausibler RPM-Skalierung,
Anlauf-/Nachlaufverhalten und Abweichungs-
toleranz unter verschiedenen Betriebszustanden
nachgewiesen ist. Die zeitlich getrennten
VS1-/P300-Rohfenster allein koennen eine
solche Identitaet nicht beweisen.

Danach erst Migration der vorhandenen
VS1-/MQTT-/Home-Assistant-Funktionen nach P300,
inklusive identischer Payloads, Zeitplaene,
P80-GFA-Typpruefung, P87-Status,
Fehlerbehandlung, sensorischer RPM-Integritaet,
Service-Restore und End-to-End HA-Regression.
**Kein Merge von PR #46 vor Beweis aller Funktionen.**
