# WB2A/20C2: echte C5-/F9-Störung am 12.10.2026 – Ursachenoffenheit, Forensik, neue Hardware-Testschranke

**Stand 12.10.2026, ca. 12:45 CEST.** Bericht zur vom Anlagenbetreiber tatsächlich gesehenen Folge **C5 (Pumpen-KM-Bus-Kommunikation) → F9 (Gebläsedrehzahl beim Start)**. Betreiber hat die Anlage anschließend selbst neu gestartet; der Heizbetrieb funktioniert laut Betreiber wieder. **Dies ist ein Vorfall am Gas-Heizgerät, kein rein informatischer Protokollfehler.**

**Wichtige Trennung:** Im historischen Optolink-/GWG-Protokoll ist **`0xC5` auch der Opcode `PHYSICAL_XRAM_READ`**. Das ist **nicht** der identisch geschriebene **Störungscode C5**. Die beiden Zahlen nicht in der Dokumentation vermischen.

## 1. Gesicherte Controller-Störungen mit Original-9-Byte-Ereignisdaten

Das vorhandene, alleinige produktive VS1-Optolink-System liest bereits die **10 System-Störungshistorienplätze** `0x7507 + 9*n` und **20 separate GFA-Ereignisplätze** `0x7590 + 9*n`. System-Record: **erstes Byte Störungscode**, acht weitere Bytes BCD `YYYY MM DD weekday HH MM SS`. Das Linux-Journal hält die original empfangenen `rx`-Bytes samt Host-Abfragezeit fest. Letztere **ist nicht die tatsächliche Fehlerentstehungszeit**.

| Controller-Zeit CEST | Systemcode | Originaler 9-Byte-Eintrag | Host liest erstmalig im gesicherten Ausschnitt | Kommentar |
|---|---|---|---|---|
| **12.10. 02:42:08** | **F9** | `f92026101201024208` | 10:51:59 | Bereits **vor** beiden heutigen 11-Uhr-GWG-Fenstern vorhanden; bei der 11:18-Nachkontrolle noch im Archiv |
| **12.10. 11:22:40** | **C5** | `c52026101201112240` | 11:43:15 | 3 Minuten 58 Sekunden **nach** dem 11:18:42 endenden `AE/6E`-Versuch |
| **12.10. 12:22:24** | **F9** | `f92026101201122224` | 12:30:22 | 63 Minuten 42 Sekunden nach dem `AE/6E`-Versuch, also knapp eine Stunde nach C5 |

**Nachweis des positiven/negativen Verhältnisses:** An diesem Tag wurde `01 C7 F8 04 04` über den Staging-Originaldispatcher gegen die echte `20C2` gelesen (11:08 Uhr); der zweite Live-Lauf um 11:18 enthielt ausschließlich die historisch dokumentierten **Lese-Frames `01 AE 17 02 04`** und **`01 6E 01 01 04`** zwischen sicheren KW-/C7-Identitätsreads. Die **GWG-`C5`-XRAM-Opcode-Probe war in einem früheren Fenster gegen 07:17 Uhr**, nicht im 11:18-Fenster. Die Geräte-Störung `C5` ist also **nicht** als Beweis zu lesen, dass gerade ein GWG-`C5`-Telegramm gesendet wurde.

**Kausalitätsstatus: UNGEKLÄRT.** Der zeitliche Abstand zwischen letztem GWG-Read und C5 macht einen firmwareinternen Neben-/Kommunikationseffekt **plausibel als Untersuchungshypothese**. Er ist **kein Beweis**. Die F9-Vorbelastung um 02:42 liegt vor den aktuellen GWG-Tests und kann auf unabhängige Gebläse-/Signal-/Regelungsprobleme oder auf frühere andere Testeinflüsse hindeuten; auch das lässt sich mit den vorliegenden Logs nicht entscheiden. Die Tatsache, dass sich der Lüfter akustisch dreht, widerlegt eine nicht erreichte **Soll-Drehzahl** oder eine fehlerhafte **Drehzahlrückmeldung** nicht.

Bei Viessmann hat **C5** die Bedeutung `Kommunikationsfehler drehzahlgeregelte Pumpe`; die Fehlerübersicht nennt **Regelbetrieb mit maximaler Pumpendrehzahl** und Prüfung des Pumpen-KM-Bus. [Viessmann Fehlercodes](https://www.viessmann.de/de/wissen/wartung-und-reparatur/fehlercodes.html). Zur **WB2A F9** beschreibt die [Viessmann-Community mit genauem WB2A-Bezug](https://community.viessmann.de/t5/Gas/Vitodens-200-Wb2A-faehler-F9/td-p/148798) die **zu niedrige Gebläsedrehzahl beim Brennerstart**, mögliche Gebläseverkabelung bzw. -ansteuerung. **F9 beweist nicht automatisch einen allgemeinen KM-Bus-Ausfall der gesamten Anlage.** C5 und F9 können gemeinsame Versorgungs-/Controllerbedingungen haben, müssen es aber nicht.

## 2. Retrospektive Hostbelege und Logs

Das bewusst auf relevante `rx C5/F9`, GFA-Retrywarnungen und Optolink-Timeouts begrenzte **Original-Journal-Extrakt** liegt **nur lokal**, nicht in Git:

```text
/tmp/wb2a-c5-f9-incident-journal-20261012.txt
SHA256 88e8987a53e850dd91c36a4b16c3089b64d37220b6a8084ae66831b99250fb79
81 Zeilen / 11129 Bytes, Quelle: journalctl -u optolink-splitter.service
Zeitfenster 12.10.2026 10:50-12:39:59 CEST
```

Der neue unabhängige Offline-Auditor `tools/wb2a-c5-f9-incident-audit-offline.py` prüft den **unveränderten SHA256**, alle drei BCD-Zeitfelder, getrennte Controller-/Host-Zeit, Originalreihenfolge, erste Auftretenszeiten, C5-Abstand **238 s** und neuen F9-Abstand **3822 s** seit Ende des 11:18-Liveversuchs. **Original-Audit PASS**, `cause_established=false`, 31 GFA-Fast-Retry-Warnungen und drei Optolink-Timeout-Einträge im gefilterten Journal. Warnungen treten **bereits vor dem neuen C5 auf**. Dass einzelne GFA-Reads nach `FF` erfolgreich wiederholt wurden, belegt nur das Retry-Verhalten, nicht die Ursache der Pumpen-/Gebläsestörung.

**12:33:33–12:33:38**: Im Splitter-Log Optolink-Telegramm-/ENQ-Timeouts, zeitlich **vereinbar** mit dem vom Betreiber beschriebenen Neustart. Es gibt keinen separat verifizierten physischen Resetzeitstempel; diese Timeoutfolge deshalb nicht als sicheren Resetnachweis deklarieren.

## 3. Kontrollmessung nach dem vom Betreiber ausgeführten Neustart

Alle folgenden Bytes wurden **ausschließlich lesend** über den bestehenden einzigen VS1-Serial-Owner und seine MQTT-Schnittstelle abgefragt, ohne Neustart-, Schreib- oder Protokollwechsel:

| Datenpunkt | Rohantwort nach Neustart | Deutung |
|---|---|---|
| `Virtual_READ 0x00F8/8` | `20c2000300000103` | Eindeutige Gerätekennung |
| `Virtual_READ 0x5738/1` | `00` | Kein **aktuell gemeldeter GFA-Fehler** |
| `Virtual_READ 0x0A82/1` | `00` | Keine aktuelle Sammelstörung |
| `Virtual_READ 0x7507/9` | `b71970010104000000` | Historischer B7-Eintrag, kein Status-Nullbeweis |
| `Virtual_READ 0x7510/9` | `f92026101201122224` | Aktueller F9 bleibt im Störungsarchiv |
| `Virtual_READ 0x7519/9` | `c52026101201112240` | C5 bleibt im Störungsarchiv |
| `Virtual_READ 0x7522/9` | `f92026101201024208` | Frühere F9 um 02:42 bleibt erhalten |
| `Virtual_READ 0x7590/9` | `002026101201112640` | **GFA-Archivereignis**, Code `00` darf hier NICHT mit „keine Störung“ gleichgesetzt werden |

Beide abgeschlossenen vollständigen **10-Slot-System-Archive**-Samples nach dem Neustart (ca. 12:43:45–12:44:23 CEST, 19,9 Sekunden Abstand) wurden durch das neue Gate erstellt und verglichen. Ergebnis **`NO_CHANGE_OBSERVED`**, neue/aktive Ereignisse `[]`, `checked_all_system_slots=true`, aber `checked_all_gfa_slots=false` (bewusst `--system-only` für die minimale Live-Diagnose nach dem Vorfall):

```text
/tmp/wb2a-c5-f9-after-restart-fault-gate-baseline-20261012.json
SHA256 1121b2f58ee82115b2356070130752b97acb79bca4a8e8ba9a84e74f8f428042

/tmp/wb2a-c5-f9-after-restart-fault-gate-post-20261012.json
SHA256 ff3778031513de122c35767027b8f668ecec139b3bfc2f82ee3120e934fd9c12
```

Eine **20-Sekunden-Stichprobe** ist keine Langzeitaussage, und ein **grünes `0x5738` sagt NICHTS** darüber, ob C5 in der Systemhistorie neu dazugekommen ist.

**Abschließender Hostzustand:** fünf produktive Services aktiv, `/opt/optolink/settings_ini.py` SHA256 `e9a120ef37fe17236a7505ee713c8dd338d98d5093ed75dfb34629d7e8f5c42d`, keine zusätzlichen Port-Owner oder Controller-Writes durch diese Vorfallanalyse. Die Heizungsfunktion nach Neustart bestätigt nur der Betreiber; der Optolink-Mitschnitt weist allein auf momentan normale Kommunikations- und Fehlerstatus-Rückmeldungen hin.

## 4. Neue verbindliche Schranke für sämtliche künftigen echten Hardwaretests

**Lücke bisher:** Historische GWG-Sessions prüften nach Rückstellung `0x5738=00`, ID und `systemctl is-active`. Das deckt weder neue System-Archivmeldungen noch aufgetretene und bereits quittierte Störungen ab. Genau deshalb wurde **C5 um 11:22 nicht direkt gemeldet**, obwohl der letzte Controller-Leseversuch um 11:18 endete. Diese ältere Prüfmethodik wird nicht rückwirkend als vollständig dargestellt.

Die Forschungswerkzeuge liefern jetzt:

- **`tools/wb2a-experiment-fault-gate.py`**: Nur-lesender VS1/MQTT-Snapshot aller **10 System-Fehlerhistorien** und **20 GFA-Archivplätze** plus Identität `0x00F8`, aktuelle GFA-Störung `0x5738` und Sammelstörung `0x0A82`. Prüft jede zurückgelieferte Adresse, Status=1, exakte Länge, Hexbytezahl und Gerätekennung. Ungültige/fehlende Antwort = `ALERT_UNVERIFIED`, niemals PASS. Vergleicht komplette Rohbytes statt nur erste Code-Bytes. `GFA-Archivcode 00` gilt nicht als frei. Optional `--system-only` begrenzt das GFA-Archiv explizit, ohne fälschlich Vollständigkeit vorzutäuschen.
- **`tools/wb2a-experiment-with-fault-gate.sh`**: akzeptiert nur explizit freigegebene, vorhandene **Read-only-Hardware-Sessionrunner**, verweigert jede andere Programmdatei; prüft vor Beginn das Archiv, startet den bereits unabhängig rückstellgesicherten Runner, prüft **sofort nach dessen Ende sowie bei T+5, T+15 und T+75 Minuten** erneut, protokolliert Unterbrechungen/Fehler als Alarm in Journal und privaten Dateien. Keine automatische Heizungs-Reset-/Fehlerlöschfunktion, kein geheimer Dauer-Service, kein zusätzlicher Serial-Owner. Der Wrapper ist **implementiert und offline getestet, nicht als produktiver Hintergrundwächter installiert und noch nicht mit einem neuen realen Hardwareexperiment abgenommen**.
- **`tests/test_wb2a_experiment_fault_gate.py`**: synthetische Negativtests zeigen ausdrücklich, dass `C5` und `F9` **auch bei `0x5738=00` und `0x0A82=00`** als neue Historieneinträge ALARM ergeben. Geänderte GFA-Records mit Code `00` sind ebenfalls ALARM. Einschließlich Stale-/Diff-/Adress-/Status-/Unvollständigkeits-/SHA-Gates und Private-0600-Ausgabe.
- **`tests/test_wb2a_experiment_fault_wrapper_offline.py`**: Shell-Syntax, explizite Session-Whitelist, Traversal-Sperre, T+0/+5/+15/+75-Minuten-Zeitplanung, EXIT-Kontrolle und alarmierende Exitcodes.

**Ergänzende Benachrichtigung:** Eine ChatGPT-Störungswache wurde am 12.10.2026 eingerichtet (stündlicher Check, Europe/Berlin). Sie prüft über den bereits verbundenen Desktop-Commander ausschließlich vorhandene Host-Journale und passive Telemetrie, markiert bekannte C5-/F9-Ereignisse als bereits berichtet und meldet nur **neue** Codes/Zeitstempel oder deutliche neue Optolink-Abbrüche. Sie öffnet keine serielle Schnittstelle und führt keine Anlage-Reads oder Writes aus. Eine Benachrichtigung ist **nicht instantan**: RARE-Pollverzögerung, stündliche Aufgabe und eventuelle Nichtverfügbarkeit der Remote-Verbindung begrenzen die Erkennung. Die stündliche Aufgabe ersetzt **nicht** den unmittelbaren Vollarchiv-Vorher-/Nachher-Vergleich des Experimentwrappers.

**Pflicht für weitere echte Forschung:** Sämtliche Optolink-/P300-/GWG-Eingriffe nur über diese Schranke und die **jeweilige separate systemd-/EXIT-Rückstellung**. Kein automatischer Neustart der Heizungssteuerung; kein Weiterprobieren bei neuem Systemcode, Archivierdelta, GFA-Statusabweichung oder unvollständiger Nachbeobachtung. Jede konkrete Änderung wird gegenüber dem Benutzer mit Zeitstempel und Rohbeleg gemeldet. Die 75-Minuten-Überwachung reicht nur bis zu diesem Fenster und ist keine Garantie gegen spätere Fehler.

**Forschungspriorität:** Original-WB2A-Firmwareauslesung über Optolink bleibt das höchste technische Ziel. Bis zur Klärung des Vorfalls nur **Offline-Quellen-/Protokollforschung** ohne zusätzliche direkte GWG-/P300-/ROM-Funktionstests. Einen F9-Ausfall am Gasgebläse nicht als bloß akzeptables Testartefakt behandeln. Bei Wiederholung trotz Neustart sollte der zuständige Viessmann-Fachbetrieb Pumpe/KM-Bus sowie Gebläse-, Stecker- und Drehzahlsignale prüfen; keine Brenner- oder Sicherheitseinrichtungen überbrücken.

## 5. Offline-/Live-Reproduktion

```bash
cd /home/chatgpt-admin/optolink-vitotrol-rpm-20261010

python3 tools/wb2a-c5-f9-incident-audit-offline.py \
  --output /tmp/wb2a-c5-f9-incident-audit-20261012.json

python3 -m unittest discover -s tests -p 'test_wb2a_c5_f9_incident_audit_offline.py' -v
python3 -m unittest discover -s tests -p 'test_wb2a_experiment_fault_gate.py' -v
python3 -m unittest discover -s tests -p 'test_wb2a_experiment_fault_wrapper_offline.py' -v

# Nur Whitelist anzeigen: keinerlei Hardware
python3 tools/wb2a-experiment-fault-gate.py plan

# Nur bei einer später separat vorbereiteten und überprüften Hardware-Session:
# bash tools/wb2a-experiment-with-fault-gate.sh --execute tools/REVIEWED-LIVE-SESSION.sh

# Gesamtregression ohne zusätzliche Hardwaretest-Session:
python3 -m unittest discover -s tests -q
```

**Git-Policy:** Forschungscommit ausschließlich auf `feat/wb2a-vitotrol-rpm-20261010` / Draft-PR #52; später selektiv mit Quellen- und Abhängigkeitsprüfung nach `optolink-research`. Keine Änderung von `main`, keine Produktionspatches, keine Veröffentlichung der privaten Original-Controllerlogs.
