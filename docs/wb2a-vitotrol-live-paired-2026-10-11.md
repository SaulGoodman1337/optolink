# WB2A/VDensHO1/20C2: gekoppelte Optolink-TX/RX-Fenster und A0:1/B0:3-Hardwareprüfung

**Stand:** 11.10.2026, Europe/Berlin, Live-Messungen 08:38–08:52.
**Arbeitszweig:** `feat/wb2a-vitotrol-rpm-20261010`, PR #52, `main`/Produktivinstallation unverändert.
**Ergebnis:** Feste gepaarte P300-FC03-Lesefunktion funktioniert. Keine emulierte Vitotrol akzeptiert. **Eine** Recovery des Shadow-Dienstes scheiterte nach erfolgreichem P300-Read zunächst an einem `systemctl stop`-Timeout, wurde bewusst als FAIL gewertet und unter genauer PID-/Executable-Kontrolle manuell repariert. Seither keine weiteren Live-Canaries.

## 1. Ziel und reale Ausgangslage

Vorversuche mit allein `B0:3` brachten keine gültige Raumtemperatur. In der historischen WB2A-Research trat bei `A0:1` ohne echte Slave-Antwort bereits BC auf. Direkte `Virtual_WRITE`-Versuche auf `0x0896` werden von der VDensHO1 abgewiesen; `0x089C` wird intern zurückgesetzt. Der reale fehlende Schritt ist deshalb die validierte **Vitotrol-KM-Bus-Receive-/Firmware-State-Commit-Funktion**; das Setzen von A0/B0 ist keine Emulation.

Die heutige Baseline und die Restore-Schwelle waren fest: `A0=0`, `B0=0`, `B5=0`, `SWIndex_FB1 (0x0A5C)=00000000`, `0x0896=C800` (20,0 °C Ersatz), `0x089C=03` (keine gültige Raumquelle), aktueller Fehlercode `00`. RPM-v2-Beobachter war und blieb aktiv. Die kurze Shadow-Umstellung kann Telemetrielücken während der VS1/P300-Umschaltung erzeugen.

## 2. Neue P300-Leseoperation: exact `p300_kmbus_txrx_64`

Ein einziger **manuell** angeforderter, via Kernel-PID/UID verifizierter `SOCK_SEQPACKET`-Auftrag auf dem **ursprünglichen** seriellen Hauptprozess führt genau diese beiden existierenden, bereits einzeln hardwareabgenommenen Transaktionen in einem P300-Fenster aus:

| Reihenfolge | Fixer Read | 8-Byte-P300-Request | Rückgabe |
| --- | --- | --- | --- |
| 1 | FC03 ab 0x161A, 32 Bytes | `41 05 00 03 16 1A 20 58` | Master-TX-RAM-Kandidat |
| 2 | FC03 ab 0x1640, 32 Bytes | `41 05 00 03 16 40 20 7E` | UART1-RX-RAM-Kandidat; möglicher Frame ab 0x1642 |

Beide werden in **64 Bytes**, TX gefolgt von RX, zusammengefügt, **nicht** zeitgleich/synchron abgetastet. Nach dem einzelnen Fenster muss die reguläre VS1-Identität samt echten GFA-P80/P06 bestätigt werden, bevor die Root-only-Schnittstelle die Rohbytes als erfolgreich liefert. Der normale automatische Hybrid-Read-Preset bleibt unverändert und enthält den neuen Auftrag **nicht**. Kein Schreibbefehl, keine Adressparameter und keine zweite serielle Portinstanz.

Der Scheduler verweigert den Auftrag bei zu altem originalem P06: 2175,657 ms veranschlagter Übergang + 280 ms zwei Reads + 2295,102 ms Rückkehr = **4750,759 ms** Mindestplanung. Bei 5300 ms P06-Alter wäre die erlaubte Frischegrenze von 10.000 ms überschritten. Das ließ sich offline reproduzieren. Die Freigabegrenze wurde **nicht** erhöht. Eine erfolgreiche Lesesitzung verwendete zuvor tatsächlich über den bisherigen VS1-Splitter ausgelesenes P80=`20` und P06=`00`.

## 3. Live-Canary A: A0:1 / B0:3, verweigerte P300-Diagnose

- Baseline- und Zeitfensterprüfung, unabhängiger systemd-Restore-Timer zuerst scharfgestellt.
- 08:42:48: `0x27A0=01` und `0x27B0=03` an echter WB2A geschrieben und einzeln zurückgelesen.
- Root-only-Ticket angenommen, aber alle Versuche bis zum Abbruch mit `REAL_GFA_P06_NOT_FRESH`, `PENDING_LEGACY_WORK` oder `DEADLINE_OR_P06_BUDGET_REJECTED` verweigert; **kein P300-FC03-RAM-Paar aus dieser Sitzung vorhanden**.
- Kontrollierter Canary-Abbruch; unabhängig restaurierte Originaldienste und originale VS1-P80/P06. Sofortiges Readback nach Rückstellung `A0=00`, `B0=00`; unabhängiger Timer ebenfalls Erfolg.
- Neuer gespeicherter BC-Eintrag im Fehlerarchiv, zum Beispiel `0x7507=bc2026101107083824` (Rohbytes), aktuelle Störung nach Rollback `00`.

**Bewertung:** Die Fernbedienungskonfiguration fordert weiterhin real eine physisch anwesende Vitotrol. Ohne nachweisbaren Empfangspfad tritt BC auf. Der erste Schattenlauf lieferte absichtlich keine künstliche oder unbestätigte FC03-Antwort.

## 4. Live-Canary B: gekoppeltes TX/RX mit A0:0 / B0:0

Mit fresh VS1-GFA und Root-only-Canary-Sitzung `run-20261011T064553Z-347474`, **genau ein** 64-Byte-Ticket:

```text
08:46:24 P300-FC03 result: verified_vs1=true; elapsed_ms=5394.409
VS1 P80=20, P06=00
TX(0x161A/32):
01 00 B1 0A 01 01 01 06 C7 31 AA F1 04 11 05 08
06 41 07 58 C5 DE 00 00 00 00 00 00 00 00 00 00
RX candidate(0x1640/32):
00 00 00 01 B1 0A 01 01 10 FE 23 D8 FA 01 FB 01
22 D1 00 00 00 00 00 00 00 00 00 00 00 00 00 00
```

Interpretation: CRC/Kermit-gültiges TX `01 00 B1 0A 01 01 01 06 C7 31` (Master an Klasse `01`) und CRC-gültiger RX-Kandidat `00 01 B1 0A 01 01 10 FE 23 D8` (Klasse `01`, **nicht** `11`).

Der Supervisor und die unabhängige systemd-Recovery bestätigten `PASS_ONE_VERIFIED_DEMAND_WINDOW` und `PASS_ORIGINAL_SERVICES_RESTORED`, GFA-P80=`20`, P06=`00`. Keine Vitotrol-Erkennung.

## 5. Live-Canary C: gekoppeltes TX/RX mit A0:1 / B0:3

Vorab erneut A0:0/B0:0 und kein aktueller Fehler; unabhängiger Timer scharf. A0:1/B0:3 wurde gegen den Kessel geschrieben und bestätigt. Manuelles P300-Fenster `run-20261011T064756Z-348150` mit frischem ursprünglichem GFA:

```text
08:48:26 P300-FC03 result: verified_vs1=true; elapsed_ms=5314.338
VS1 P80=20, P06=00
TX(0x161A/32):
01 00 B1 0A 01 01 01 06 C7 31 4D 8E 04 11 05 08
06 41 07 58 C5 DE 00 00 00 00 00 00 00 00 00 00
RX candidate(0x1640/32):
00 00 00 01 B1 0A 01 01 10 FE 23 D8 FA 01 FB 01
22 D1 00 00 00 00 00 00 00 00 00 00 00 00 00 00
```

Der **ausgelieferte On-Demand-P300-Read selbst** ist `completed`, `verified_vs1=true`; beide CRC/Kermit-validen Vordergrundframes in den RAM-Bereichen haben **unverändert Klasse `01`**. Die TX-Puffer-**Nachlaufbytes** unterscheiden sich und dürfen nicht als Bestandteil des 10-Byte-Telegramms gedeutet werden. Wir sehen in diesem einzelnen Snapshot **weder Vitotrol-Discovery-Klasse 11 noch eine Vitotrol-11-Slaveantwort**. Die getrennten FC03-Transaktionen sind nicht atomar; das ist kein vollständiger physischer Busmitschnitt und kein Beweis, dass in der Zeit sonst keine Discovery gesendet wurde.

Die Softwarekennung blieb `0x0A5C=00000000`, Raumtemperatur bei Fallback `20,0 °C`, Sensorstatus `03`; neuer BC-Fehlerhistorieneintrag `0x7507=bc2026101107084656`. Eine Software-Vitotrol wurde **nicht** registriert.

### Wichtiger Recovery-Zwischenfall und tatsächliche Wiederherstellung

**Diese C3-Canary-Sitzung ist NICHT bestanden**, obwohl die P300-Rückkehr innerhalb des Hauptprozesses GFA-verifiziert war. Die unabhängige systemd-Rückstellung meldete:

```text
stop optolink-splitter.service: ... timed out after 15 seconds
restore: rollback could not remove all dropins
result=FAIL_OR_NOT_VERIFIED
```

Der Shadow-Hauptprozess `PID 348352` blieb in `deactivating / stop-sigterm` hängen. Die bekannte Shadow-Executable aus dem Root-Release wurde exakt mit `systemctl MainPID` und Prozessargv verglichen, und es waren keine systemd-Dropin-Dateien mehr vorhanden. **Nur dieser identifizierte Shadow-Prozess** wurde danach mit `systemctl kill --kill-whom=main --signal=SIGKILL` beendet. Anschließend `systemctl daemon-reload`, `reset-failed`, Neustart des **ursprünglichen** Splitter-ExecStart `/opt/optolink/optolinkvs2_switch.py` plus aller üblichen Party-/Schedule-/Service-/Maintenance-/Clock-Sync-Dienste. Erfolgreiche unmittelbare VS1-GFA-/Codier-Readbacks um 08:49:29–08:50. Der unabhängige externe A0/B0-Rückstellauftrag bestätigte am 11.10. **08:52:16** selbständig `A0=00`, `B0=00`, Exit 0.

Abschließende Verifikation: `VS1_BETRIEB_OK`, serieller Originalprozess PID 348772, A0/B0 `00/00`, `0x0A5C=00000000`, `0x0896=C800`, `0x089C=03`, aktueller Fehler `00`, neuer BC nur in Fehlerhistorie. `optolink-wb2a-rpm-passive-20261010-v2.service` aktiv. Unbekannte Controller-RAM-, SFR-, EEPROM- oder KM-Bus-Slave-Writes wurden nicht versucht.

**Keine weiteren Live-Shadow-Canaries im Anschluss an den Timeout.** Alle zuvor gezogenen P300-Rohdaten bleiben als Hardwarebeleg gültig, der Gesamt-Canary ist aber **FAIL**.

## 6. Testbare Recovery-Härtung (Offline, nicht produktiv installiert)

Die Wiederherstellungslogik in `tools/handover_acceleration/shadow_canary.py` wurde um einen optionalen, streng begrenzten Pfad für `systemctl stop MAIN`-Timeout ergänzt:

1. Prüfen, dass der Service noch `deactivating` ist und `systemctl MainPID` existiert.
2. Per `/proc/PID/cmdline` **exakt** Python `-u` und die fest gepinnte Shadow-Executable unter dem attestierten Release vergleichen, einschließlich `optolink`-UID. Unbekannte/originale ausführbare Programme werden **nicht** beendet.
3. Nur die weiterhin verifizierte MainPID bei der ursprünglichen systemd-Unit mit `systemctl kill --kill-whom=main --signal=SIGKILL` stoppen; auf `inactive/failed` warten.
4. Danach exakte SHA-Dropins entfernen, den Original-ExecStart aktivieren, echte VS1-GFA-Werte und ursprüngliche Dienste testen.
5. **Nicht** zu einem grünen Canary umdeklarieren: Auch bei erfolgreichem Restore lautet das Testergebnis `RESTORED_WITH_VERIFIED_FORCE_STOP_NOT_CANARY_PASS` mit Exitcode ungleich 0. Bei nicht bestätigter PID/Executables bleibt Fail-closed und es wird weder ein unbekannter Prozess beendet noch eine scheinbar erfolgreiche Wiederherstellung behauptet.

Bestehende und neue synthetische Regressionen decken Timeout-Pfade, unveränderte Dienste, unbekannte PIDs, nötigen PID-/UID-/Executable-Vergleich, Original-Restore und GFA-Readback ab. Diese Codeänderung ist noch **kein erneuter Live-Hardwarebeleg der reparierten Recovery**.

## 7. Quellen, Reproduzierbarkeit und offene Voraussetzung

- Root-only Hardware-Rohbelege: `/var/lib/optolink-hybrid/canary-sessions/run-20261011T064257Z-346474`, `run-20261011T064553Z-347474`, `run-20261011T064756Z-348150`, Original-Journal `optolink-splitter.service` (Einträge `HYBRID_RUNTIME_VERIFIED_SWITCH` und `HYBRID_RUNTIME_REFUSAL`).
- B0/A0-Rückstell-Skript (nur lokales System): `/tmp/wb2a-vitotrol-a0b0-rollback-20261011-0842.sh`, SHA256 `09576dc6d8fba00e0b1e9e4853be16fce8dd190cf721aacad686036d98b42e0e`.
- Offline-Paardecoder: `tools/wb2a-vitotrol-optolink-pair-audit.py` und `tests/test_wb2a_vitotrol_optolink_pair_audit.py`, aus den beiden echten 64-Byte-Hardwareergebnissen reproduzierbar.
- Separate Ergebnisse: [Live-Einzelreads am Morgen](wb2a-vitotrol-live-optolink-ram-2026-10-11.md), [Firmware-/UART1-Identitätsgrenzen](wb2a-vitotrol-uart1-firmware-attribution-2026-10-11.md), [VitoSoft-Profil](wb2a-vitotrol-vitosoft-profile-audit-2026-10-10.md).

**Entscheidungsgrenze:** Die Live-Tests beweisen P300-RAM-Beobachtung, **nicht** Optolink-Receive-Emulation. Für einen echten Teilnehmer benötigen wir eine belegte, in VDensHO1 erreichbare KM-Bus-Receive-/ISR-/State-Commit-Funktion. Ohne solche Firmware-/Controllerbelege dürfen unbekannte RAM-/SFR-/EEPROM-Writes, `XRAM_WRITE` oder freie `KBUS_TRANSPARENT_WRITE`-Experimente nicht als sicherer Emulatorpfad ausgegeben werden. PR bleibt Draft, originaler VS1-Betrieb bleibt produktiv.

## Nachtrag: echte native P300-Schreibversuche am selben Tag (09:23–09:39)

Die vorherige **read-only**-Evidenz wurde danach entscheidend erweitert:
FC04 `Physical_WRITE` kann **originale Klasse11-Vitotrol-300-Antworten**
nach `0x1642` schreiben; eine physische FC03-RAM-Rücklesung bestätigte
alle vier Originaltelegramme, mehrfach unter `A0:1/B0:3` sowie bei
Type `0x7342=0x74`. Eine echte Vitotrol-Teilnehmerannahme erfolgte
**nicht**; `0x0A5C` blieb 0, Raumtemperatur beim Fallback 20°C,
Sensorstatus `03`. Zustandsbytes `0x166A`/`0x0B6B` wurden mit
früher natürlich beobachteten Varianten aktiv versucht, ohne
Teilnehmerannahme. Weitere aktive Tests im nativen P300-Modus sind
in [wb2a-vitotrol-native-p300-active-2026-10-11.md](wb2a-vitotrol-native-p300-active-2026-10-11.md)
mit Code, Rücklesungen und genauem Abnahmevorbehalt dokumentiert.
Die früheren `VS1/P300`-Canary-Read-only-Gates sollen **nicht** als
grundsätzliche Pflicht für alle P300-basierten Vitotrol-Tests verstanden
werden. Native P300 ist ein eigenständiger real abgenommener Testmodus.
