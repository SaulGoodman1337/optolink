# Naechster Handover-Test: natuerliche VS1-ENQ statt zusaetzlichem EOT

Stand: 2026-10-08. Prober 1.2.0, Branch `optolink-p300-migration`.
**Implementiert und offline getestet, noch kein Hardwareergebnis dieser Variante.**

## Ziel und eng begrenzte Hypothese

Das Anwendungsziel bleibt RAM-Zugriff ohne Verlust bestehender HA-/GFA-Funktionen,
als Grundlage fuer Pumpen- und Vitotrol-Forschung. Dieser Versuch ist nur ein
Kommunikationsvergleich: **Ist der VS1-Ausgang ohne ein neues EOT schneller als
der bisher gemessene EOT->ENQ-Ablauf?** Er implementiert keinen Pumpen-Override.

Der Nutzer hat den Ein-ENQ-Rueckweg bereits erfolgreich getestet: Session
`run-20261008T094009Z-124230`, Prober 1.1.0 / Commit `ff5504d`. Drei Runden,
`PASS_READ_ONLY_SINGLE_ENQ`, danach Originaldienst active/running und echte
MQTT-Abfragen P80=20/P06=00. Die Daten stehen unveraendert im
[Ergebnisbericht](p300-goals-and-single-enq-result-2026-10-08.md).
Die beiden ersten ENQ-Wartephasen dauerten weiterhin jeweils etwa 1,998 s,
der Gesamtweg einschliesslich GFA im Mittel 4,610 s. Diesen Ablauf nicht
unveraendert wiederholen.

**Arbeitshypothese, kein Quellenfakt:** Das Senden von EOT aus einer laufenden
VS1-Sitzung koennte einen anderen Timeout/Erkennungsablauf ausloesen als das
blosse Auslaufenlassen der bereits geprueften Sitzung. Das wird unterschieden,
nicht vorausgesetzt. Das Weglassen von EOT darf weder die natuerliche ENQ noch
die nachfolgende P300-Identitaetspruefung ersetzen.

## Quellen und ihre Grenzen

1. OpenV [Protokoll KW](https://github.com/openv/openv/wiki/Protokoll-KW),
   Abschnitt Kommunikation, abgerufen 2026-10-08: periodisches 05 und die Wahl,
   entweder eine weitere ENQ abzuwarten oder ohne neues 01 Folgeanfragen zu senden.
   Das begruendet passives Warten nach einer vollstaendig beantworteten Anfrage.
2. OpenV [Protokoll 300](https://github.com/openv/openv/wiki/Protokoll-300),
   Initialisierung und Beenden, abgerufen 2026-10-08: 05 bedeutet nicht initialisiert;
   danach Start 16 00 00 und ACK 06. EOT wird fuer einen definierten Ausgangszustand
   empfohlen; das Wiki nennt fuer periodische ENQs etwa zwei Sekunden.
3. [VitosoftCommunication.md](https://github.com/sarnau/InsideViessmannVitosoft/blob/main/VitosoftCommunication.md),
   VS1/VS2, abgerufen 2026-10-08: VS1-Keepalive alle 500 ms ist beschrieben.
   **Das ist kein Nachweis eines 500-ms-Idle-Timeouts dieser WB2A.** Der beschriebene
   Standard-P300-Neustart verwendet EOT. Ein schneller Warmwechsel ohne EOT ist
   damit nicht als fertige Funktion dokumentiert.
4. [Direkte GFA-Quellenpruefung](p300-gfa-host-trace-2026-10-08.md): fuer GFA bleibt
   der belegte VS1/6B-Pfad. Kein erneutes direktes C9, kein C9->09/6B-Raten.

Diese Quellen begruenden einen eng begrenzten Unterschiedstest. Sie garantieren
weder, dass eine natuerliche ENQ frueher kommt, noch dass P300 nach ihr ohne EOT
auf genau dieser Regelung angenommen wird. Die Quellen wurden nicht als
WB2A-Firmwaredokumentation ausgegeben.

## Was Prober 1.2.0 genau aendert

Neue Option: `--idle-enq` (nicht mit `--single-enq` kombinieren).

- Aufbau bleibt EOT -> zwei ENQs -> VS1; Controller 20C2, Software 0103 und
  GFA-P80=20 werden geprueft. Genau dieselben GFA-Adressen wie vorher.
- Vor jeder der drei Messrunden wird F7/00F8/2 vollstaendig beantwortet und
  auf 20c2 geprueft. Nur diese frische Antwort kann den neuen Einstieg freigeben.
  Zwischenzeitlicher TX oder ein veralteter Nachweis sperrt ihn.
- **Nur beim gemessenen VS1->P300-Einstieg:** kein EOT, kein Keepalive, kein
  Pufferloeschen; hoechstens sechs Sekunden empfangen, ohne vorher etwas zu senden.
  Erst eine wirklich empfangene 05 erlaubt das unveraenderte 16 00 00.
- Ein unerwartetes Byte (auch ACK/NACK) oder Timeout beendet die Messfolge.
  Es wird nicht still doch EOT gesendet und ein Ergebnis des alten Pfades ausgegeben.
- Start-ACK sowie beide P300-Identitaetsantworten mit Laenge/Adresse/Pruefsumme
  muessen unveraendert bestehen.
- Rueckweg P300->VS1 bleibt EOT -> eine ENQ -> Identitaet, dann P80/P06/P09/P87.
- Finale Link-Wiederherstellung bleibt der bewaehrte Zwei-ENQ-Pfad. Systemd-
  ExecStopPost stellt wie bisher die zuvor aktiven Dienste selektiv wieder her.

Die **TX-Allowlist ist bytegleich** mit Prober 1.1.0. Keine neue Adresse, kein
C9, keine RAM-/EEPROM-Abfrage, kein GFA_WRITE, keine Codierung und kein Prozess-
Write. EOT wird nicht global entfernt, nur an der genannten Messstelle.
`--idle-enq` allein zeigt nur einen inerten Plan. Erst `--execute` greift auf
das Geraet zu. Der Produktionssplitter und sein Updatekanal bleiben unveraendert.

## Vorbereitung in der Optolink-LXC

Als root, bei funktionierendem VS1, nicht waehrend einer Party-/Wartungs-/Service-
programmoperation. Keine parallelen Updates, Schreibtests oder seriellen Clients.
Die bekannte HA-/MQTT-Telemetrie wird waehrend der Messung pausiert. Der Prober
ersetzt keine Schutzfunktion der Heizung. Die gestoppten und wieder gestarteten
Produktionsdienste behalten ihre normalen Lebenszyklen.

Den im zugehoerigen PR-Kommentar genannten, geprueften Commit per Fast-forward
holen; keine lokalen Aenderungen resetten oder ueberschreiben. Kein erneuter
Stager und keine Kopie ins P300-Kandidatenverzeichnis. Danach:

```bash
cd /root/p300-trial-work/project
/opt/optolink/venv/bin/python -m unittest discover -s tests -p 'test_handover*.py' -v
/opt/optolink/venv/bin/python tools/wb2a-handover-probe.py --idle-enq
```

Erwartet: **60 Handover-Tests** erfolgreich (42 bestehende + 18 neue) und
`PLAN ONLY` / `IDLE ENQ: no EOT or TX before natural VS1 ENQ`.

Nur bei Erfolg einmal ausfuehren:

```bash
/opt/optolink/venv/bin/python -u \
  /root/p300-trial-work/project/tools/wb2a-handover-probe.py --execute --idle-enq
```

Erwartete Variantenanzeige: `VARIANT=idle-enq-comparison`.
Erfolgslabel nur bei gueltigen Messrunden und Wiederherstellung:
`RESULT=PASS_READ_ONLY_IDLE_ENQ`. Es garantiert **keine Beschleunigung**.

Abbruch aus zweiter LXC-Konsole:

```bash
systemctl stop optolink-handover-probe.service
```

Der alte CANARY-Rollbackhelfer ist nicht fuer diesen Worker zustaendig.
RuntimeMaxSec=90 und TimeoutStopSec=90 bleiben bestehen; sie garantieren keine
Wiederherstellung oder gesamte Ausfalldauer bei Systemd-/Kernel-/USB-/Stromfehlern.
Wiederherstellung erfolgt auch nach negativem Messergebnis. Bei Fehler nicht
unveraendert wiederholen; `measurement.json` und `recovery.json` im ausgegebenen
SESSION-Verzeichnis auswerten. Ein fehlendes PASS ist kein Auftrag, Writes
freizuschalten oder Guards zu umgehen.

## Kontrolle nach Ende und Notweg

```bash
systemctl show optolink-splitter.service -p WorkingDirectory -p ActiveState -p SubState
optolink-debug request 'gfaread;0x4050;1;raw;False' --timeout 8
optolink-debug request 'gfaread;0x4006;1;raw;False' --timeout 8
```

Originaldienst muss wieder `/opt/optolink`, active/running zeigen. P80=20 mit
Status 1; P06 zustandsabhaengig und nicht FF. Auch aktuelle HA-Werte und zuvor
aktive Zusatzdienste kontrollieren. Wird der Originaldienst nicht hergestellt,
erst sicherstellen, dass der Probe-Worker beendet und der Port frei ist, dann
`systemctl start optolink-splitter.service` und Journal pruefen. Zusaetzliche
Dienste nur anhand `state.json`/`recovery.json` wiederherstellen, nicht pauschal
alle einschalten. Reports erhalten.

## Welche Werte entscheiden?

| Feld | Bedeutung |
| --- | --- |
| `p300.entry_mode` | Muss `natural-enq-no-eot` sein |
| `p300.eot_sent` | False: beschreibt den ausgefuehrten Pfad, kein alleiniger Erfolgsnachweis |
| `p300.enq_ms` | Wartezeit ab Start des passiven Einstiegs, statt ab EOT |
| `p300.last_vs1_rx_to_enq_ms` | Ab letztem empfangenen Byte der vorgeschalteten VS1-Identitaet, einschliesslich der 10-ms-Restdatenpruefung |
| `p300.start_ack_ms` | Unveraenderte Start-/ACK-Phase nach empfangener ENQ |
| `vs1.first_enq_ms` | Unveraenderter EOT-basierter Rueckweg, zuletzt etwa 1998 ms |
| `roundtrip_with_gfa_ms` | Ganzer gemessener Hin-/Rueckweg einschliesslich GFA |

Die Wartezeit wird nicht vor der Messung versteckt; es gibt kein vorab
abgearbeitetes Idle-Sleep. Host-, USB- und Schedulinganteile bleiben enthalten.
Rund 500 ms waeren kein zugesagter Sollwert. Drei Messrunden liefern keine
Worst-Case-Garantie und pruefen ohne beobachteten Brennerwechsel keine Dynamik.

**Entscheidung nach dieser Variante:**

- Gueltig und deutlich schneller: moeglicher Baustein fuer Hybridkommunikation;
  die andere etwa zweisekuendige Richtung bleibt separat offen. Noch kein
  Pumpen-Override und noch keine vollstaendige Funktionsparitaet.
- Gueltig, aber etwa gleich langsam oder langsamer: diesen Optimierungszweig
  schliessen; nicht die gleichen Timeouts weiter verkuerzen. Danach bevorzugt
  GFA-Spiegel/alternativen belegten Zugriff oder gezielte Quellenanalyse der
  Rueckrichtung untersuchen.
- Keine ENQ oder keine gueltige P300-Antwort: negative Aussage nur zu dieser
  Sequenz. Recovery pruefen und keine Wiederholung ohne neue Begruendung.

## Verifikation dieser Entwicklung

18 neue Tests behandeln unter anderem natuerliche ENQ, ausbleibende/unerwartete
Bytes, unveraenderte TX-Allowlist, fehlenden/veralteten Warmnachweis, keine
Pufferloeschung, keine versteckten Fallbacks, alle bisherigen P300-Pruefungen,
partielle Ergebnisse, persistierte Variantenwahl und konservative Recovery.
Die 42 vorherigen Handover-Tests bleiben unveraendert. Alle 60 bestehen lokal.
Die bestehende P300-Suite besteht lokal mit einem wegen fehlender Laufzeit-
Abhaengigkeit uebersprungenen Adaptertest; dieser ist in CI verpflichtend.
Die zugehoerigen CI-Ergebnisse werden im Commit-bezogenen PR-Kommentar belegt.
**Keine neue Live-Messung durch die Entwicklung, kein Zugriff auf die LXC.**
