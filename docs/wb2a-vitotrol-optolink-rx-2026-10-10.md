# WB2A / VDensHO1: Optolink-only Vitotrol RX-Puffer-Kandidat 0x1642

**Stand: 10.10.2026, nur offline + neu typisierter, nicht aktivierter FC03-Read.**
**Verbindliche Architektur: ausschließlich Optolink/P300 im vorhandenen
seriellen Hauptprozess; kein externer KM-Bus-Mikrocontroller.**
Dieses Dokument enthält keine Controller-Write-Freigabe.

## 1. Neue Bestandsaufnahme aus bereits abgeschlossenen Aufzeichnungen

Der bekannte UART1-KM-Bus-Master-TX-Puffer beginnt bei `0x161A`
(DMA0-Quelle oft `0x161B`, Ziel U1TB `0x03AA`). Bisher wurden
vor allem `0x1600/32` und `0x1620/32` untersucht. Dabei endete
unser naheliegender Blickbereich bei `0x163F`.

**40 Bytes nach dem TX-Pufferbeginn** liegt an **`0x1642`** ein
RAM-Inhalt mit dem *umgekehrten* KM-Bus-Telegrammheader `00 01 B1`.
Dieser Bereich wurde bereits im historischen Deep-Logger mit
`FC03 0x1640 / 32` gelesen. Ein erneutes Live-Experiment war
für die folgende Analyse daher unnötig.

### Zwei unabhängige historische Roharchive

| Archiv | Archiv-SHA256 | geprüfte `0x1640/32`-Samples | CRC-gültige Antworten |
| --- | --- | ---: | ---: |
| `p300-fullram-run-20261009T083607Z-144293-bundle.tar.gz` | `94d5842b6dc5759ecb446a4c617b60b72873b639885d116032f783abdef8431c` | 79 `COMPLETE` | **79** |
| `p300-deep-run-20261009T070505Z-130246-bundle.tar.gz` | `f0f015032edb94459ff2259a81ef2b84bf23253570d91cc6ba658c8160f5c2af` | 295 echte FC03 | **295** |
| **Gesamt** | | **374** | **374** |

- Voll-RAM-Archiv: **40 aufsteigend und 39 absteigend** ausgeführte
  Scans mit kanonischer RAM-Adressablage. Der **80. partielle,
  absteigend roh gespeicherte** Snapshot wurde ausgeschlossen.
  Jedes verwendete `.bin` und `.json` ist gegen das Archivmanifest
  gehasht, Snapshot-Metadaten mit 20C2 / 0103, 0x0400..0x53FF,
  20.480 Bytes und `COMPLETE` verglichen.
- Deep-Logger: 295 explizite `FC03/0x1640/32` mit archivierter
  Request-Adresse/Funktion/Länge und gültigem Archivmanifest.
  Alle **295** RAM-Blöcke sind jeweils in *einer* FC03-Antwort
  vorhanden, im Gegensatz zum gesplitteten Master-TX-Nachtlauf.
- Beide Roharchive bleiben privat; der GitHub-Commit enthält **nur
  aggregierte Ergebnisse, Quellhashes und synthetische Fixtures**.
- Keine dieser 374 Proben stammt aus der laufenden RPM-v2-Aufnahme.
  Es wurden **keine** neuen seriellen Transaktionen ausgeführt.

### Bytegenaue Beobachtungen

Die aktuell beobachteten gültigen Slave-seitigen Telegramme sind:

```text
RX-Kandidat 0x1642 (78 Voll-RAM + 294 Deep):
00 01 B1 0A 01 01 10 FE 23 D8

RX-Kandidat 0x1642 ( 1 Voll-RAM +   1 Deep):
00 01 B1 0A 01 01 00 00 43 53
```

Beide erfüllen die originale KM-Bus-CRC16/Kermit-Prüfung
(`crc16_kermit(frame)==0`). `00` bedeutet Ziel Master,
`01` bedeutet *Quellklasse 0x01*. **Das ist keine Vitotrol
(Klasse `0x11`)**, sondern ein bisher nicht genau zugeordneter
anderer KM-Bus-Teilnehmer. Auch die Class-01-Semantik und
Objektwerte `10=FE`, `00=00` sind nicht bewiesen.

Historische Voll-RAM-Probe Nr. 64 und Deep-Probe Nr. 145
zeigen die seltene alternative Antwort. Dass sich der
RAM-Pufferinhalt bei ansonsten konstantem Header änderte, ist
**ein Indiz gegen eine bloße statische Signatur**. Die
Aufzeichnung beweist jedoch nicht den exakten Zeitpunkt des
UART1-Hardwareempfangs oder die damit verknüpfte Masterfrage.

### Altdaten hinter dem vollständigen B1-Frame

In allen 374 beobachteten RAM-Blöcken stehen bei `0x164C..0x1651`
noch sechs Bytes hinter dem 10-Byte-Frame:

```text
FA 01 FB 01 22 D1
```

Unter der **ausdrücklichen Annahme**, dass dort Reste eines
überschriebenen `B3/16`-Kennungsrecords mit `F8,F9,FA,FB`
liegen, lässt sich ein zuvor verlorenes Byte durch 256 Offline-
CRC-Varianten rekonstruieren. **Exakt eine** Variante passt:

```text
HYPOTHETISCH vorheriger Inhalt, NICHT gemessen:
00 01 B3 10 01 01 F8 01 F9 11 FA 01 FB 01 22 D1
                         ^^ CRC-eindeutige F9-Ergänzung
```

Das unterstützt das Modell eines wiederverwendeten
UART1-Receive-Buffers, ist aber **keine beobachtete vollständige
Identitätsantwort**, kein Gerätebeweis und kein Beleg für
ISR-/DMA-Puffer-Eigentümerschaft. Die sechs Bytes können auch
anderweitige persistierte Reste sein.

### Stand der RX-Hypothese

```text
             WB2A-Regler / Haupt-MCU (Hypothese)
                    UART1-Master / KM-Bus
                          |
              TX-SRAM ab 0x161A   [belegt]
                          |
                  physische Gegenstelle
                          |
              RX-SRAM ab 0x1642   [starker Kandidat]
                          |
       unbekannte ISR / Frame-Parser / Teilnehmerstatus
                          |
        Vitotrol-State / Raumtemperatur / Watchdog
                          |
                    Optolink-Objekte
```

**Unverändert offen:** tatsächlicher UART1-RX-Interrupt und
Vektor/INTB, Source/Owner von `0x1642`, Parser-/Commit-Routine,
Kessel-Statusobjekte, Watchdog, Writeability und sichere
Einspeisung. Wir haben in **dieser Anlage keine Vitotrol-Klasse
0x11 als RX** beobachtet. Der physische WB2A-Empfang einer
Virtuellen Vitotrol ist damit **nicht** bewiesen.

## 2. Neu implementierte Offline-Analyse

`tools/wb2a-vitotrol-optolink-rx-audit.py`:

- verarbeitet die beiden **unveränderten** Archive mit gepinnten
  SHA256-Quellhashes; Manifest-, Metadaten-, Geräteprofil- und
  Zeitrichtungs-/Snapshotgrenzen werden kontrolliert;
- verwendet ausschließlich die bereits archivierten lesenden
  FC03-Daten, **keinen** Live-Optolink-/UART1-SFR-/MQTT-/Socketzugriff;
- extrahiert den potentiellen Slave-RX-Frame mit Start `0x1642`
  aus dem 32-Byte-RAM-Feld `0x1640` (`+2`);
- prüft Header, Paketlänge, Subklasse, CRC, erkennt beide
  verschiedenen Antwortframes und kennzeichnet eine
  CRC-Rekonstruktion aus Restbytes **als hypothetisch**;
- verweigert defekte Rohdaten, CRC und Header, falsche Manifest-
  Hashes, unbekannte oder partielle Voll-RAM-Snapshots;
- meldet die Beweisgrenzen `physical_uart1_rx_verified=false`
  und `controller_write_authorized=false` ausdrücklich im JSON.

**Reproduzierbar ohne sudo-Ausführung des Auditors:**

```bash
cd /home/chatgpt-admin/optolink-vitotrol-rpm-20261010

sudo cat /root/p300-trial-work/research-bundles/p300-fullram-run-20261009T083607Z-144293-bundle.tar.gz \
  | python3 tools/wb2a-vitotrol-optolink-rx-audit.py --fullram

sudo cat /root/p300-trial-work/research-bundles/p300-deep-run-20261009T070505Z-130246-bundle.tar.gz \
  | python3 tools/wb2a-vitotrol-optolink-rx-audit.py --deep

python3 -m unittest discover -s tests -p 'test_wb2a_vitotrol_optolink_rx_audit.py' -q
python3 -m unittest discover -s tests -p 'test_*.py' -q
```

## 3. Neue **Optolink-only** Read-only-Diagnose (nicht aktiviert)

Auf dem Draft-Branch wurde die vorhandene Root-only-On-Demand-
Infrastruktur **genau um einen konstanten, historisch belegten**
FC03-Leseauftrag erweitert:

| Eigenschaft | Fester Wert |
| --- | --- |
| Root-only-Request-Art | `p300_ram_1640_32` |
| Optolink/P300-Funktion | `FC03` / Physical_READ |
| Gerätedatenbereich | `0x1640 / 32` |
| Exakte P300-TX-Nachricht | `41 05 00 03 16 40 20 7E` |
| Erwartete P300-Datenlänge | 32 Bytes |
| Einzige neue Zweckbindung | Offline-/manuelle RX-Puffer-Diagnose; niemals Vitotrol-Injection |

Sicherheitsmodell der vorhandenen Infrastruktur wird **nicht
abgeschwächt**: dieselbe serielle Original-Owner-Instanz, Root-
Peer/PID-Gate, Shadow-Opt-in, Writer- und Ingress-Admission,
VS1-ID/Original-GFA-P80/P06, Crash-Fence und Recovery,
Einzelanfrage-TTL/Idempotenz und veröffentlichte Rohbytes
**erst nach verifizierter Rückkehr zu VS1**.

**Wichtig:** Die neu typisierte Leseart wird weder der automatischen
`READONLY_PRESET`-Dreierliste (Identität + 0F20 + 1C60)
noch dem Boot-/Continuous-Canary-Ablauf hinzugefügt.
Die normale Produktivinstallation `/opt/optolink`, `main`,
die laufenden Systemd-Dienste und der passive RPM-Logger
bleiben unverändert. Es erfolgte **keine** Hardwareabnahme
dieser neuen Leseart über den Shadow-Pfad; die 295 alten
FC03/1640-Proben belegen nur die ursprüngliche Lesbarkeit.

Wenn später ein eigenes, beaufsichtigtes und ausdrücklich
freigegebenes On-Demand-Fenster mit Telemetriepause vorliegt,
läßt sich die optolink-only Diagnose ohne neue Port-Owner
als **genau ein** Root-Request innerhalb des bestehenden
manuellen Canarys vorsehen. Während der laufenden RPM-Forschung
wird dieser Schritt **nicht** ausgeführt.

Für reine Offline-Dekodierung eines vorhandenen, bereits
abgerufenen 32-Byte-Rohfelds genügt:

```bash
python3 tools/wb2a-vitotrol-optolink-rx-audit.py --sample-1640 \
  00000001b10a010110fe23d8fa01fb0122d10000000000000000000000000000
```

**Weder das Vorhandensein eines RX-Puffers noch sein Lesen
berechtigt zu `Physical_WRITE`, `Virtual_WRITE`, direktem
`U1RB`-Zugriff oder künstlichem RX-Interrupt.** Solche
Schreiboperationen werden nicht implementiert.

## 4. Ab hier: Optolink-only Forschungsentscheidung

Wir verfolgen **keinen externen KM-Bus-Emulator**. Die
Original-Vitotrol-300-TX-Frames aus dem anderen OpenV-Archiv sind
lediglich ein *Byte-/Verhaltensorakel* für den künftigen
controllerinternen Vitotrol-RX-Parser.

Der nächste Engpass ist damit wesentlich konkreter:

1. `0x1642` gegen einen verfügbaren UART1-ISR-/Parser-
   Firmwarebeleg und dessen SRAM-Puffer-Ownership prüfen.
2. Den **kontrollierten Übergang vom RX-SRAM zum Vitotrol-State**
   statisch nachweisen: CRC, Klassen-/Slotzuordnung, Alive/BC,
   Raumtemperatur und sensorseitige Statusänderung.
3. Einen belegten, kontrollierbaren Optolink-Service für genau
   diesen Zustandsübergang finden. Ein vorhandener
   `Physical_READ` beweist **keine** Schreib-/Inject-Funktion.
4. Erst dann ein gesondertes, fail-closed Offline-/Integration-
   Harness für einen *nachgewiesenen* Controller-Service bauen.

**Produktivstatus:** VS1 bleibt aktiv, Hybrid-Shadow deaktiviert;
RPM-v2-Aufzeichnung im anderen Chat bleibt unangetastet.
PR #52 bleibt Draft.

### Quellverweise

- Private abgeschlossene Roharchive wie oben, SHA-verifiziert.
- [UART1-/Master-TX-Auswertung vom 09.10.2026](https://github.com/SaulGoodman1337/optolink/blob/optolink-p300-migration/docs/p300-kmbus-vitotrol-master-tx-2026-10-09.md)
- Historisch bereits gelesenes `0x1640/32`:
  `/root/p300-trial-work/project/docs/p300-deep-result-2026-10-09.md`.
- Vorheriger Voll-RAM-Bericht:
  `/root/p300-trial-work/project/docs/p300-fullram-result-2026-10-09.md`.
- [Originale externe Vitotrol-300-Belege](wb2a-vitotrol-original-reference-2026-10-10.md).
- [Quellgebundene Optolink-/Firmwaregrenzen](wb2a-vitotrol-rpm-next-phase-2026-10-10.md).
