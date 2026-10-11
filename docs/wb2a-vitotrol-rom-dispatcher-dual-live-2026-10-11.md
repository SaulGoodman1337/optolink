# WB2A / VDensHO1 / 20C2: aktive Optolink-ROM-Bridge- und Vitotrol-RX-Dispatcher-Forschung

**Datum:** 11.10.2026, 16:26–16:34 CEST. **Ziel:** echte Vitotrol-200/300-Anmeldung ohne separate KM-Bus-Hardware, allein über den originalen Optolink-Splitter. **Ergebnis:** Beide Wege tatsächlich am eigenen Regler mit 123 ausschließlich lesenden nativen P300-Abfragen geprüft, jedoch **weder ein 20-Bit-ROM-Lesezugang noch ein RX-/Teilnehmer-Commit bewiesen**. Das separate Raumregelungsprojekt (0x2321) bleibt ausgesetzt.

## Durchführung und Provenienz

Verwendet wurde ausschließlich der bereits produktive serielle Portbesitzer `optolink-splitter.service`. Für jedes Messfenster wurde mit `systemd-run` zuerst ein **unabhängiger, zeitbegrenzter Restore-Timer** scharfgeschaltet, dann der Originaldienst von VS1 auf natives P300 umgestellt und anschließend die genau begrenzte Read-Whitelist abgefragt. Python-Messsoftware selbst schaltet keine Dienste und hat keinen Schreibbefehl für den Kessel.

- **Messfenster 1:** 16:26:35–16:28:03, 53 Reads, 87,286 s, 3 RX-/UART1-Snapshots.
- **Messfenster 2:** 16:29:48–16:30:43, 34 Reads, 55,482 s, 1 RX-/UART1-Snapshot und zusätzliche FC99-High-Reads.
- **Messfenster 3:** 16:32:25–16:33:23, 36 Reads, 58,163 s, 3 wiederholte High-Address-FC03-/FC99-Vergleichszyklen einschließlich `+2`-Offsets.

**Gesamt:** 123 Controller-Read-Requests, **0 Controllerwrites**, kein UART-/DMA-/IRQ-Schreibzugriff, kein Code-Aufruf und kein zweiter serieller Portbesitzer. Die vollständigen Livequellen verbleiben privat am LXC unter:

```text
/tmp/wb2a-vitotrol-dual-readonly-live-20261011.json
/tmp/wb2a-vitotrol-dual-readonly-high-live-20261011.json
/tmp/wb2a-vitotrol-dual-readonly-aba-live-20261011.json
/tmp/wb2a-vitotrol-dual-readonly-summary-20261011.json
/root/wb2a-vitotrol-dual-readonly-20261011/restore.log
```

## Weg A: 20-Bit-Programm-ROM über P300

Der gewöhnliche P300-Dienst `FC03 Physical_READ` akzeptiert 16-Bit-Serviceadressen; das belegt noch **keine** Übersetzung nach `0xC0000..0xFFFFF`. Im ersten und zweiten Lauf zeigten High-Reads `0xE000/0xF000/0xFFF0` teils `5497` bzw. `5498` als identisches, achtmal wiederholtes 16-Bit-Wort. Andere Samples lieferten `f801`, `0800` oder `4343`, ebenso achtfach wiederholt. Der Inhalt ist **zeitlich veränderlich** und damit nicht als stabiler Program-ROM-Block nachgewiesen.

Der native `FC99 KBUS_INDIRECT_READ` wurde zusätzlich an den belegten RAM-Strukturkandidaten erprobt:

| Adresse | FC99/2 | FC03-RAM/2 an derselben Adresse, zeitversetzt |
| --- | --- | --- |
| `0x0B51` | `3f20` | `3f20` |
| `0x0B74` | `ff23` | `ff23` |
| `0x0B7E` | `f001` | `f001` |
| `0x1A7D` | `285c` | historischer RAM-Anker `285c` |

Bei diesen geprüften RAM-Adressen lieferte FC99 die gespeicherten Pointerbytes, **nicht** nachgewiesene durch den Pointer adressierte Programm-ROM-Bytes. Diese Aussage ist auf die getesteten Parameter begrenzt.

Die neun High-Address-A/B/A-Paare bestätigen, dass FC99 und FC03 teilweise *unterschiedliche*, teilweise gleiche **zeitlich schwankende Servicewerte** liefern:

| High-Adresse | FC03-Zweibytepräfix Zyklen 0/1/2 | FC99/2 Zyklen 0/1/2 |
| --- | --- | --- |
| `0xE000` | `5498 / 4343 / 5498` | `5498 / 5498 / 5497` |
| `0xF000` | `0800 / 5497 / 5498` | `5497 / 5498 / 5498` |
| `0xFFF0` | `5498 / 5498 / 5498` | `5998 / 5498 / 1d90` |

**Nur 3 von 9** zeitversetzten Vergleichspaaren stimmen überein; die `+2`-FC99-Leseproben schwankten ebenfalls (`5498`, `5497`, `1d90`, `5c00`). Das begründet einen **anderen oder zeitabhängigen Dienstpfad**, aber **kein** vollständiges Programm-ROM-Abbild, keine dereferenzierte 20-Bit-Flashadresse und keinen geeigneten sicheren Monitor-Selector. Weder FC03 noch FC99 transportieren in den geprüften Requests eine belegte separate Adressobergrenze/Bank.

Die historisch an `0x1DE0/0x1E60/0x3300` beobachteten Copy-ähnlichen Strukturen sind in der Liveprobe weiterhin lesbar; mangels nachgewiesener ROM-Quelle/Zieländerung ist auch dies **kein ROM-to-RAM-Copy-Dienst**.

## Weg B: vorhandenen RX-Dispatcher/Vitotrol-Teilnehmerzustand nachweisen

Die 4 Live-RX-Snapshots aus Fenstern 1+2 zeigen:

| Anker | Beobachtung |
| --- | --- |
| `0x0B6D..0x0B70` | `42 16 0A FE` in **4/4** RX-Kontexten |
| RAM bei `0x1642` | normales Klasse01-`B1`-Telegramm, keine Klasse11-Slaveantwort |
| TX bei `0x161A` | abwechselnd `01 00 B1 0A` und `20 00 B3 0C` |
| `S1RIC 0x0054` | `41 / 40 / 41 / 41`; IR-Bit nicht beobachtet |
| `U1C1 0x03AD` | `07` in **4/4** (RX-Freigabe an; kein RI-Bit) |
| `SWIndex_FB1 0x0A5C` | `00000000` in **4/4** |
| Raumfühlerstatus `0x089C` | `03` in **4/4** |

Es wurde ausdrücklich **keine Vitotrol-Codierung A0/B0 aktiviert und kein virtueller RX-Frame in RAM geschrieben**. Der Test sucht nach natürlich beobachtbaren RX-/Dispatcher-Anzeichen und belegt lediglich, dass die vorhandenen SRAM-Descriptorbytes auch beim natürlichen Masterverkehr stabil sind. Vorherige bereits dokumentierte aktive Original-B3-RAM-Einspeisungen bei korrektem A0:2/B0:3 führten **ebenfalls nicht** zu gültiger Teilnehmerregistrierung. Die neue Messung fügt **keine** UART-ISR-/Parser-Adresse und **keinen** durch Optolink erreichbaren RX-Dispatch-Aufruf hinzu.

## Recovery und Qualitätskontrolle

Vorher per VS1 geprüft: Gerät `20c2000300000103`, `A0=00`, `B0=00`, Fehler `00`. Die Originaldatei `/opt/optolink/settings_ini.py` und das gesicherte Backup hatten den identischen SHA256 `e9a120ef37fe17236a7505ee713c8dd338d98d5093ed75dfb34629d7e8f5c42d`.

Jede Sitzung führte ihren eigenen manuellen EXIT-Restore zusätzlich zum unabhängigen systemd-Timer durch. **Bei Sitzung 1** musste nach dem Restore der Hauptdienstes die zuvor aktive Servicegruppe (`optolink-party-emulator`, `optolink-schedule-manager`, `optolink-service-programs`) zusätzlich gestartet werden; der zusätzliche Servicezustand wurde sofort erkannt, korrigiert und das Restore-Skript daraufhin verbessert. Bei Sitzungen 2 und 3 waren diese Services anhand eines zuvor gesicherten Zustands automatisch wieder gestartet. Letzte Verifikation nach Fenster 3: `VS1_BETRIEB_OK`, sämtliche ursprünglich aktiven abhängigen Dienste `active`, separater RPM-Recorder `active`, Original-`vs1protocol=True`, Config-Hash exakt, Gerätekennung `20C2/0103`, Fehler `00`, unabhängige Timer danach `inactive`. Die P300-Fenster können temporäre VS1- oder MQTT-Telemetrielücken verursacht haben; der Recorder wurde nicht gelöscht oder neu initialisiert.

## Reproduzierbare Software und Tests

- `tools/wb2a-vitotrol-dual-readonly-probe.py`: streng typisierte feste Whitelist, native-P300-Preflight, FC03/FC99/RX- und High-ABA-Leseprogramme, **kein Controller-Write-API**.
- `tools/wb2a-vitotrol-dual-readonly-session.sh`: root-gated Kurzfenster mit zweitem, im Voraus aktiviertem systemd-Timer.
- `tools/wb2a-vitotrol-dual-readonly-restore.sh`: Host-Config-SHA-Recovery, ursprüngliche Services + RPM, Validierung der Gerätesignatur und des Fehlers.
- `tools/wb2a-vitotrol-dual-readonly-audit.py`: offline JSON-Strukturprüfung, Wiederherstellungsgrenzen, gepaarte FC03-/FC99-Zweibytevergleiche, RX- und Teilnehmer-Negativbelege.
- `tests/test_wb2a_vitotrol_dual_readonly_probe.py` und `tests/test_wb2a_vitotrol_dual_readonly_audit.py` enthalten deterministische positive und negative Fixtures sowie optionale lokale Prüfung der Original-Live-JSONs.

**Gesamte lokale Regression:** **639 Tests erfolgreich, 1 optionaler Test übersprungen**. Auditor inklusive echter Hardware-JSONs: **9/9 Tests erfolgreich**. Keine privaten Live-Rohdaten in GitHub. PR #52 bleibt Draft, `main` und der Code unter `/opt/optolink` bleiben unverändert.

## Konsequenz und nächster echter Gate

**Weg A:** Kein beweisbar über Optolink transportierter 20-Bit-Programm-ROM-Zugriff; weitere High-Adress-Rohlesevarianten liefern ohne dokumentierten Monitor/Selector keine verlässliche Codequelle.

**Weg B:** Kein nachgewiesener `UART1-RX-ISR -> Parser -> Vitotrol-Teilnehmer-Commit`. `0x0B51`, `0x0B55`, `0x0B5C`, `0x0B74`, `0x0B7E` bleiben **Codeadress-ähnliche RAM-Kandidaten, keine sicher aufrufbaren Funktionen**.

Gezielte Fortsetzung: Zuerst einen **authentisch zur 20C2/0103 gehörenden ROM-Read-Monitor/High-Bank-Selector** aus belegten Controller-/Servicequellen finden *oder* ein passendes MCU-Programmabbild gewinnen. Dann ROM-Code und tatsächlichen `INTB` auf den UART1-/Class11-/Liveness-Pfad korrelieren. Erst danach eine getrennt abgesicherte, hardwareverifizierte und rückstellbare Dispatcher-Prüfung erwägen. Blindes Schreiben an SFR/IRQ/Callback/RX-Queue ist **kein sinnvoller Nachweis**, auch bei allgemeiner Experimentierfreigabe nicht.
