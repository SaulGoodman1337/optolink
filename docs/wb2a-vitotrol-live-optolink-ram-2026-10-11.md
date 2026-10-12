# VDensHO1 20C2: Live-Vitotrol-Tests ueber Optolink am 11.10.2026

**Geraet:** Viessmann Vitodens 200-W WB2A, VDensHO1/20C2/0103. **Lokale Zeitzone:** Europe/Berlin (CEST).
**Durchgefuehrt:** echte VS1-Virtual_READ-/Virtual_WRITE-Codierung und zwei manuell/fest freigegebene P300-FC03-Diagnosen ueber den *originalen einen* seriellen Hauptprozess. Der RPM-v2-Logger wurde **nicht** gestoppt oder zurueckgesetzt; waehrend der beiden kurzzeitigen VS1/P300-Canaries koennen aber Telemetrieluecken entstanden sein.

## 1. Unveraenderte Live-Ausgangslage (08:18)

| Objekt | Live-VS1-Readback | Bedeutung/Grenze |
| --- | --- | --- |
| `0x27A0/1` | `00` | Keine Vitotrol-Konfiguration HK1 |
| `0x27B0/1` | `00` | B0:0 witterungsgefuehrt |
| `0x27B2/1` | `08` | B2-Raumeinflussfaktor |
| `0x27B5/1` | `00` | B5-Raumpumpenlogik deaktiviert |
| `0x0A5C/4` | `00000000` | Keine bestaetigte Fernbedienungsidentitaet |
| `0x0896/2` | `C800` | 20,0 C, mangels Sensor nur Ersatzwert |
| `0x089C/1` | `03` | Keine gueltig bestaetigte Raumtemperaturquelle |
| `0xA132/29`, Byte 28 | `00` | Kein aktiver Controllerfehler |
| `0x7507/9` | `F92026100905070848` | Neuester Fehlerarchiv-Eintrag (Referenz) |
| `0x0810/2` | `9D01` | Kesseltemperatur 41,3 C |

**Produktionspfad:** `optolink-hybrid status = VS1_BETRIEB_OK`, ein vorhandener serieller Portbesitzer, keine Hybrid-Automatik.

## 2. Live-Versuch A: B0:3 mit unveraenderter Fernbedienung A0:0

- Independent systemd Restore-Timer **vor** dem Write erzeugt und als aktiv bestaetigt.
- `08:19:00` `writeraw;0x27b0;03` -> `1;0x27b0;03`; anschliessendes `read;0x27b0;1` -> `03`.
- Fuenf echte VS1-Messfolgen von `08:19:03` bis `08:19:50`, die alle `A0=00`, `B0=03`, `0x0A5C=00000000`, `0x0896=C800`, `0x089C=03`, aktueller Alarm `00` meldeten.
- Kesseltemperatur in den fuenf Proben 42,0, 42,5, 42,5, 42,5 und 43,0 C.
- `08:20:02` Sofort-Restore auf B0:0 erfolgreich und unabhaengig per Readback bestaetigt.
- `08:20:35` zusaetzlich der **unabhaengige** systemd-Watchdog: `RESTORE_CONFIRMED_B0_00`, Exitstatus 0.

**Ergebnis:** B0:3 wird vom Kessel angenommen, **aber** bei A0=00 wird keine virtuelle Vitotrol erkannt. Das ist kein Beweis fuer die Auswirkungen auf eine tatsaechlich angeschlossene oder emulierte Fernbedienung.

## 3. Live-Versuch B: P300-FC03/32 am RX-Kandidaten `0x1640`

Einmaliger **Root-only** und ausschliesslich lesender On-Demand-Request ueber das verifizierte Shadow-Release `wb2a-rx1640-readonly-20261011`:

```text
08:21:45 queued: p300_ram_1640_32
P300 read at 0x1640 / 32 bytes:
00 00 00 01 B1 0A 01 01 10 FE 23 D8 FA 01 FB 01 22 D1
00 00 00 00 00 00 00 00 00 00 00 00 00 00

elapsed_ms = 5161.056
verified_vs1 = true
vs1_p80 = 20
vs1_p06 = 53
```

Das feste, CRC16/Kermit-gueltige Frame ab `0x1642` lautet
`00 01 B1 0A 01 01 10 FE 23 D8`: Klasse `0x01` (NICHT Vitotrol `0x11`). Es ist dasselbe Class01-B1-Muster wie in den historischen 374 RX-Pufferkandidaten.

**Extern verifizierter Canary:** exakt eine Demand-Operation, `PASS_ONE_VERIFIED_DEMAND_WINDOW`, `PASS_ORIGINAL_SERVICES_RESTORED`, Original-GFA-P80/P06 bestaetigt. Der Shadow-Lauf war vollstaendig rueckgestellt, saemtliche Ursprungsdienste wieder aktiv. Dies ist **RAM-Diagnostik**, weder eine bestaetigte physische UART1-RX-ISR noch ein Schreibzugang.

## 4. Live-Versuch C: `B0:3` mit aktuellem KM-Bus-Master-TX-RAM

Ein zweiter SHA-manifestgepruefter, nur manuell aktivierter Single-Owner-Release wurde geschaffen: `wb2a-tx161a-readonly-20261011`.
Der neue feste Diagnoseauftrag `p300_ram_161a_32` ist **nur** `FC03/0x161A/32`, ohne beliebige Adressen oder Schreibbefehle:

```text
P300 request = 41 05 00 03 16 1A 20 58
```

- `08:25:30` `B0:3` erneut mit verifiziertem Baseline-Readback, aktivem unabhaengigem systemd-Restore-Timer.
- Waehrend `B0:3` aktiv war: Einmaliger P300 Read `0x161A/32`.
- `08:26:08` Root-only-P300-Resultat, `elapsed_ms=5201.552`, `verified_vs1=true`, VS1-P80=`20`, P06=`00`.
- **Echte 32 Bytes**:

```text
20 00 B3 0C EE 01 10 C2 11 00 AA F1
04 11 05 08 06 22 07 04 05 AC
00 00 00 00 00 00 00 00 00 00
```

Die 12 ersten Bytes (`20 00 B3 0C EE 01 10 C2 11 00 AA F1`) besitzen **CRC16/Kermit-Residuum 0** und entsprechen strukturell einem aus der Master-TX-Quelle abgeleiteten Frame mit Quellklasse `00`, Zielklasse `20`, Befehl `B3`. Klasse `20` ist **noch keiner gesichert identifizierten Teilnehmerart** zugeordnet.

**Nicht gesehen in diesem einen Moment:** `11 00 33 ...` fuer Vitotrol-Slot 1/2. Daraus folgt **nicht**, dass solche Master-Discovery-Frames bei B0:3 nie existieren; die archivierten 20C2-TX-Daten belegen schon beide Varianten. Auch ein CRC-gueltiger RAM-Puffer beweist **nicht**, dass der Frame auf dem physikalischen Bus ausgesendet wurde, oder dass B0:3 dessen Inhalt kausal beeinflusste.

Der Canary meldete eine voruebergehende `REAL_GFA_P06_NOT_FRESH`-Abweisung vor dem angenommenen Leseauftrag (Gate blieb aktiv), danach genau ein freigegebenes Diagnosefenster und `PASS_ONE_VERIFIED_DEMAND_WINDOW`, anschliessend `PASS_ORIGINAL_SERVICES_RESTORED`. Die unabhaengige Recovery zeigte keine Fehler.

**Rueckfall:** `08:26:42` Original-VS1 wieder aktiv, B0:0 unmittelbar danach geschrieben und gelesen (`00`). `08:27:51` unabh. Recovery-Timer in `Result=success`, `ExecMainStatus=0` und nochmals `read 0x27B0=00`. Danach `A0=00`, `0x0A5C=00000000`, `0x0896=C800`, `0x089C=03`, aktueller Alarm `00`, Archiv-Eintrag `0x7507` unveraendert.

## 5. KM-Bus-Zugriffsfamilien: warum keine freie Injektion versucht wurde

VitoSoft/P300 enthaelt global Funktionsnamen fuer diverse K-Bus-Operationen. Insbesondere sind `KBUS_TRANSPARENT_WRITE=0x56` und `KBUS_GATEWAY_WRITE=0x66` benannt. Die schon untersuchte lokale Original-VitoSoft-Quelle `research/vitosoft/kbus-write-function-analysis.md` zeigt jedoch:

- `KBUS_TRANSPARENT_WRITE`: **853 globale Eventdefinitionen**, jeweils BlockLength=1, als strukturierte Teilnehmer-Datenpunktwrites, **kein** Rohslavetelegramm-Generator;
- `KBUS_GATEWAY_WRITE`: **1** globales Loesch-/Gateway-Event, kein positiver Vitotrol-Receive-Handler;
- Im exakt verknuepften `VDensHO1`-Profil mit **581** Events: `KBUS_TRANSPARENT_WRITE` und der dokumentierte RX-Inject-Service **nicht** vorhanden (Hostkatalogbefund, keine Aussage ueber alle Firmwarefunktionen);
- `0x41 KMBUS_RAM_READ` wurde historisch fuer `0x00F8/8` verifiziert, lieferte aber die normale Controller-Identitaet und ist **kein** Bus-Sniffer und kein freier RAM-Schreibpfad.

Ohne dokumentierten Controller-RX-Parser/State-Commit oder eine belegte, getrennt abgesicherte P300-Receive-Funktion waeren `Physical_WRITE`, `XRAM_WRITE`, `KBUS_TRANSPARENT_WRITE`, `0x1642`-RAM-Manipulation oder fingierte UART1-IRQ-Telegramme **nicht reproduzierbare Empfangstests**, sondern undefinierte Eingriffe in die laufende Heizungssteuerung. Sie wurden **nicht** ausgefuehrt.

Vergleichsquellen: [InsideViessmannVitosoft](https://github.com/sarnau/InsideViessmannVitosoft), [OpenV-Protokoll-300](https://github.com/openv/openv/wiki/Protokoll-300), lokale Profilanalyse und die im Research-Branch liegende separate detaillierte KBus-Schreibfunktionsanalyse.

## 6. Reproduzierbarkeit und Grenzen

- Original-Captures: private systemd-Journale und Recovery-JSON unter `/var/lib/optolink-hybrid/canary-sessions/run-20261011T062101Z-343582` und `run-20261011T062539Z-344682`; P300-Rohdaten als Root-Socket-Journal in `optolink-splitter.service`.
- Lokaler B0-Logger: `/tmp/wb2a-vitotrol-b0-observation-20261011-0819.log`.
- Code: `tools/handover_acceleration/{coordinator,scheduler,phase_executor,continuous_runtime,continuous_canary}.py`, `tools/wb2a-vitotrol-optolink-tx-audit.py`.
- Tests: `tests/test_handover_fc03_fixed.py`, `tests/test_wb2a_manual_canary.py`, `tests/test_wb2a_local_demand_control.py`, `tests/test_wb2a_on_demand_batcher.py`, `tests/test_wb2a_vitotrol_tx_audit.py`.
- Es wurden **keine** unbekannten Regler-RAM-/SFR-/EEPROM-Adressen geschrieben, keine Fehlersperre umgangen, keine neue serielle Portinstanz erzeugt und keine dauerhafte P300-Automatik aktiviert.
- Der passive RPM-v2-Logger bleibt aktiv. Die beiden autorisierten Shadow-Servicewechsel koennen kurzzeitig Polling- oder MQTT-Luecken erzeugt haben. Der separate RPM-Forschungszweig bleibt ansonsten unveraendert.

**Resultat:** Das Live-Geraet nimmt B0:3 an und laesst sich zu B0:0 zurueckstellen; der fest begrenzte Optolink-P300-Zugang liefert aktuelle CRC-gueltige Master-/RX-RAM-Bilder. **Eine virtuelle Vitotrol wurde nicht registriert, ein sicherer Receive-Inject-Pfad wurde nicht nachgewiesen.** PR #52 bleibt Draft, `main` wird nicht geaendert.
