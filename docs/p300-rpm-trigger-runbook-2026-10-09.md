# WB2A P300-RPM-Triggerlogger: sicherer P06-Wirkvergleich, 9.10.2026

**NUR AUFGABE 1.** Vitodens 200-W WB2A / VDensHO1, Controller `20C2`, SW `0103`, GFA P80=`20`. PR #46 bleibt **Draft/unmerged**. Produktives `/opt/optolink` bleibt unveraendert. Dieser neue Logger ist eine **noch nicht live getestete Hardwareforschung**. Die bisherigen guten 2h-Temporal- und Fokus-Ergebnisse sind [hier](p300-temporal-fullrun-analysis-2026-10-09.md) dokumentiert. [Hypothesen-/Sicherheitsplan](p300-rpm-next-experiment-and-architecture-2026-10-09.md).

## Warum genau dieser Versuch?

Die 2h-P300-only-Aufnahme hat **5.224** gueltige Kernzyklen und **23.028** korrekte P300-FC01-/FC03-Pakete geliefert; die zwei GFA-nahen RAM-Werte `0x0F20`/`0x1C76` waren zeitweise dynamisch (bis `0xAC`, 29/27 Werte). Hinter beiden Kandidaten folgen **neun nahezu identische Statusbytes**, die `FC01 0x55D3/11` spiegeln. Eine reine Flammen-EIN/AUS-Kennung sind die zwei Bytes damit **nicht**. Aber die physikalisch echte Drehzahl P06 ist waehrend eines P300-only-Laufs *nicht* erreichbar. Die Formel `(RAM-1)×30` waere nur eine zu pruefende **Hypothese**, nie eine Istwertberechnung.

Beim vorherigen Fokuslauf gab es echte VS1-P06-Vorwerte bis **4410 U/min**, aber einen P300-Kandidaten `0x54` nach dem mehrere Sekunden dauernden Switch. Die nachfolgenden P06-Fenster waren dynamisch. Die neue Versuchsanordnung soll diese Zeitluecke gezielt eingrenzen.

## Erlaubte Telegramme und Exklusivbesitz

Genau drei P300-Wire-Readformate (streng erzwungene Allowlist):

| Operation | Adresse | Laenge | Zweck |
| --- | --- | ---: | --- |
| P300 `FC01` | `0x55D3` | 11 Byte | Flamme, Verriegelung, P87-Indiz, Status-/Modulationsdiagnose |
| P300 `FC03` | `0x0F20` | 32 Byte | erster RAM-Kandidat unmittelbar vor Statuskopie |
| P300 `FC03` | `0x1C60` | 32 Byte | zweiter Kandidat bei `0x1C76` |

VS1 nutzt nur bereits erfolgreich gelesene **GFA-P06/P09/P87/P80/P10/P84** sowie gepruefte 20C2/0103-Geraeteidentitaet. GFA P06 Rohwert × 30 U/min, `FF` ungueltig. **P09 ist Modulation, nicht Tachometer!** Kein neuer Funktionscode, keine SFR-/U1RB-Reads, kein C9/09/RPC, keine Writes, keine Eingriffe in Brenneranforderung, Pumpen oder Zeitprogramme.

Die Unit `optolink-p300-rpm-trigger.service` ist der alleinige serielle Besitzer im Versuch; alle vorher aktiven produktiven Optolink-Splitter-/Zusatzdienste pausieren fuer die Dauer, ohne Produktionsdateien zu aendern. Kein gleichzeitiger zweiter Logger; die Heizung arbeitet lokal weiter, waehrend externe MQTT-/HA-Daten eingeschraenkt sind.

## Messablauf im Full-Run

1. Preflight der urspruenglichen Produktionskonfiguration, des exklusiven Ports, freien Speicherplatzes, alter Temporal-/Fokus-Recovery und der Canary-Freigabe. Gepinnte Kopie **aller sieben Python-Abhaengigkeiten** inklusive SHA256 in eine private Session. Dauer 1 oder 2 Stunden, maximal 4 Trigger.
2. Kurz VS1: echte P06/P09/P87/P80/P10/P84-Referenz, korrekte Identitaet. Gepruefter Wechsel **VS1→P300**.
3. P300: pro Zyklus Status A (`55D3`) → `0F20/32` → `1C60/32` → Status B (`55D3`). Mit rund 1,25 Sekunden angestrebtem Basiszyklus (bei hohen Werten bis 0,60 Sekunden; echte TX/RX-Zeitstempel entscheiden). Jede 64-Byte-Paarantwort und Statusklammer wird vollstaendig mit Hash/Offset protokolliert.
4. **Trigger nur bei natuerlichem Hochzustand**: mindestens **zwei unmittelbar aufeinanderfolgende** P300-Zyklen mit **beiden** Kandidaten `>=0x88` (136 dez.), `|0F20-1C76|<=4`, Flamme in Status A UND B EIN, kein Lockout, keine Flammen-/P87-/Lockout-Aenderung innerhalb des Statuspaars. Keine kuenstliche Brenneranforderung, kein P300-Drehzahl-Poll.
5. Beim Trigger: echte gespeicherte P300-Rohwerte und Zeiten, dann **P300→VS1** mit bestaetigter Identitaet, ca. 2 Sekunden und mindestens sechs Runden echte P06/P09/P87-Reads samt P80-Readback; danach **VS1→P300** und zwei weitere statusgeklammerte RAM-Paare. Jedes P06-Read traegt eigene Zeitstempel; **es gibt weiterhin keine zeitgleiche Messung von RAM und P06**.
6. Ein Trigger ist nur *qualifizierbar*, wenn VS1-P06 durchgehend exakt ein positiver gueltiger Wert war und alle beteiligten P300-Kandidaten vor/nach der seriellen Unterbrechung innerhalb **maximal zwei Rohbyteeinheiten** konstant blieben, bei Flamme EIN und unveraendertem P87-/Lockout-Status in jedem Paar. Sonst `TRANSITION_OR_UNKNOWN`. Eine gute numerische Uebereinstimmung erhaelt **nur** `NUMERICALLY_CONSISTENT_NOT_VERIFIED`, niemals `p300_actual_p06_verified=true`. Ein deutlicher stabiler Missmatch von `(RAM-1)×30` zu echter P06 erhaelt `P06_PLUS_ONE_NUMERIC_MISMATCH`.
7. Maximal **vier** ausgelöste P300→VS1-Gegenmessungen, mindestens **600 Sekunden Cooldown** dazwischen. Nach Erreichen des Limits geordneter Abschluss; bei ausbleibendem natuerlichen Hochzustand Ende nach 1/2 Stunden als **INCONCLUSIVE**, nicht als Nachweis gegen alle RPM-Hypothesen.
8. Am Ende **P300→VS1**, echte P06/P80-Readbacks, Worker-Recovery und zusaetzlich **ExecStopPost** als voneinander getrennte Sicherung. Hauptsplitter zuerst, dann die urspruenglich aktiven sechs Units/Timer. Produktive MQTT-P80/P06-Health wird separat kontrolliert; **HA-Entity-Frische ist damit nicht automatisch nachgewiesen**.

### Zeit-/Fehlergrenzen

- Fuenfminuetiger obligatorischer **Canary ohne aktiven Trigger** vor einem Full-Run, mindestens 30 Kernzyklen und 240 Sekunden P300-Sampling; muss ohne Fehler enden und erfolgreich nach VS1 und in alle aktiven Dienste zurueckkehren.
- Worker `Restart=no`, `TimeoutStopSec=300`, `KillMode=control-group`, `ExecStopPost` fuer separaten Dienstrestore, SIGTERM erst zwischen vollstaendigen seriellen Transaktionen. Serielle Probleme `fail-closed`; kein blinder Retry von Schreib-/Spezialtelegrammen.
- Vorab mindestens 768 MiB frei, waehrend des Laufs mindestens 256 MiB; Sessionlimit 192 MiB und Einzeldatengrenze 96 MiB; max. 12.000 Zyklen. Quelle/Git-SHA + SHA256 gepinnt.
- **Wenn Recovery nicht verifiziert:** keine neue Session starten und zuerst die Produktionsverbindung diagnostizieren.

## Exakte Bedienung (NUR nach gruenem GitHub-CI)

**Nicht direkt das Skript ausfuehrbar machen** – der Wrapper wird mit `bash` aufgerufen. Als `root` im originalen Forschungscheckout, kein Parallel-Logger:

~~~bash
cd /root/p300-trial-work/project

# 0: PLAN ONLY, keine Hardware- oder Dienstaktion
bash tools/wb2a-p300-rpm-trigger.sh plan

# 1: EINMALIG Fuenf-Minuten-Canary, inklusive vollstaendigem Restore
bash tools/wb2a-p300-rpm-trigger.sh canary

# 2: Waehrend Canary: Status lesen
bash tools/wb2a-p300-rpm-trigger.sh status

# 3: Erst wenn Canary UNIT_STATE=inactive, state=RESTORED,
# recovery.services_restored=true, health P80/P06 gueltig und
# ein privates Archiv vorliegen: voller Folgelauf
bash tools/wb2a-p300-rpm-trigger.sh start 2

# 4: Status im Full-Run, beispielsweise alle 30 Sekunden
watch -n 30 'bash tools/wb2a-p300-rpm-trigger.sh status'

# 5: Bei Bedarf geordneter Stop, NICHT kill -9 oder fremden Logger starten:
bash tools/wb2a-p300-rpm-trigger.sh stop
~~~

Der Wrapper aktualisiert **nur** den Forschungsbranch `optolink-p300-migration` per Fast-forward, verlangt sauberen Git-Status und fuehrt vor jeder Hardwareaktion die Trigger-/Temporal-/Fokus-/FullRAM-/Deep-/Overnight-Offline-Regressionssuiten aus. Es wird nichts aus Git mitten in eine aktive Session nachgeladen.

## Output und unabhaengige Auswertung

- Session: `/root/p300-trial-work/p300-rpm-trigger-results/run-YYYYMMDDTHHMMSSZ-PID/`.
- `vs1.jsonl`: echte GFA-P06/P09/P87/P80/P10/P84-Reads mit UTC/monotonic und `FF`-Kennzeichnung.
- `packets.jsonl`: kompletter P300 FC01/FC03-Rohresponse mit Payload, Adresse, ACK, Checksumme und Zeiten.
- `cycles.jsonl`: echte Statusklammer, RAM-Kandidaten/Spiegel, Start/End- und binaere Hash-/Offsetinformationen.
- `triggers.jsonl`: *jede* Triggerentscheidung, Vor-/Nach-Kandidaten, VS1-Referenz, Switch-Erfolg, Klassifizierung; auch `PARTIAL` bei fehlgeschlagenem Handshake.
- `core-pairs.bin`: exakt 64 Byte pro komplettem P300-Zyklus (inkl. Post-Trigger-Kontrollen); `trace.jsonl` und `switch.jsonl`: alle erlaubten TX/RX- und Protokolluebergaenge.
- `state.json`, `measurement.json`, `progress.json`, `recovery.json`, `health.json`, sieben gepinnte Python-Quellen.
- Nach Recover entsteht **eine** private Upload-Datei: `/root/p300-trial-work/research-bundles/p300-rpm-trigger-run-...-bundle.tar.gz`. Alle Manifestdateien mit SHA256 und Laenge. Bitte nur dieses Archiv hochladen, **keine produktiven Settings/MQTT-Credentials**.

### Was waere ein Erfolg?

Nicht das Auftreten einer hohen RAM-Zahl. Ein brauchbarer Tachometerkanal braucht mindestens **zwei getrennte, stabile positive, echte P06-Drehzahlniveaus**, konsistente Skalierung, plausible Dynamik und Unabhaengigkeit von P09/Modulations-Sollwert, FC01-Status und Optolink-eigenen Ringpuffern. Auch bei numerischen Matches bleibt die P300-RPM-Eigenschaft ohne diese Zusatzbelege gesperrt.

### Was passiert, falls es wieder keine sichere P06-Quelle gibt?

Dann **keinen weiteren langen RAM-Logger**. Als Aufgabe-1-Entwicklungsziel: **Single-Owner-Hybrid** (P300 als Hauptmodus mit gebuendelten echten VS1-GFA-P06-Lesefenstern) oder bewusst **VS1 als Hauptmodus** mit kurzen P300-Zusatzdatenfenstern. Beide Varianten muessen gemessene ca. 6,5s Wechselkosten, Queue-/Port-Exklusivitaet, P06-Frische/TTL, MQTT/HA, Service-, Wartungs-, Uhrzeit-, Zeitplan- und Partyfunktionen samt Write-Readback zu voller Funktionsparitaet nachweisen. Keine GFA-P09- oder FC01-Modulationsersatzdrehzahl, keine Vitotrol-/Pumpen-Sidequests und **kein Merge von PR #46**.
