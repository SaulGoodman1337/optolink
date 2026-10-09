# WB2A: P300-P06-Fokuslogger nach dem 20-KiB-Audit

**9.10.2026 – Nur Aufgabe 1, Forschungsbranch `optolink-p300-migration`, PR #46 bleibt Draft. Kein produktiver P300-Wechsel, keine Vitotrol- oder Pumpenentwicklung.**

## Messziel und Grenzen

Der [Voll-RAM-Bericht](p300-fullram-result-2026-10-09.md) validierte 79 komplette 20-KiB-Snapshots. 48 waren stabil mit P06=0; elf stabil positiv, aber ausnahmslos mit P06=`0x53` = 2.490 U/min. Die Adressen **0x0F20 und 0x1C76** waren in den stabilen Bildern immer `00` bei AUS und `54` bei EIN. Das ist *kein* identischer P06-Wert (`0x53`) und kein Tachobeweis. **0x0F29** spiegelt nachweisbar das native Statusbyte 7 aus `FC01 55D3/11` und ist eine Negativkontrolle.

Der neue Logger erfasst ausschließlich sechs bereits physisch gelesene FC03-Blöcke zu je 32 Byte: `0x0F00`, `0x0F20`, `0x0F40`, `0x1C40`, `0x1C60`, `0x1C80`; zusätzlich den bekannten `FC01 0x55D3/11`-Status. **Keine Writes, kein C9, kein U1RB/SFR, keine unbekannten Adressen, keine erzwungene Brennerfunktion.**

## Methodik

1. Im echten VS1-Verfahren über mindestens drei Sekunden wiederholt GFA `P06` (Rohbyte×30 U/min, `FF` ungültig), `P09` (Modulationsanforderung, **nicht** die Ist-Drehzahl), `P87`, `P80=20` und ergänzend P10/P84 beobachten; P06-Referenzen werden zeitgestempelt gespeichert.
2. Nur bei einer durchgehend identischen, gültigen P06-Klammer zu P300 wechseln. Aus-/2490-U/min-Zustände nur dreimal mit mehrminütiger Sperrfrist erfassen; höhere bzw. andere positive P06-Werte bevorzugen. Die konkrete Ziel-Drehzahl kann nicht erzwungen werden.
3. Zwei kurze sequenzielle RAM-Runden je `6×32=192` Byte lesen, jeweils mit vollständigen Request-/ACK-/Rohantwort-Daten, separat gehashten Binärdateien und drei über den Scan verteilten 11-Byte-Statusframes. Zeitdifferenz zwischen den Runden dokumentieren.
4. Nach P300→VS1 die 20C2/0103-Identität und erneut mindestens drei Sekunden echte P06 prüfen. Klassifizierung `STABLE_OFF`, `STABLE_2490`, `STABLE_OTHER_POSITIVE` oder `TRANSITION_OR_UNKNOWN`, niemals als bestätigten Sensor. Ein fehlgeschlagener Identitäts-Return erzeugt **PARTIAL ohne erfundene Post-P06-Klammer**.
5. Erst wenn **zwei unterschiedliche positive stabile RPM-Stufen** inklusive zeitlichem Verhalten und Unabhängigkeit vom eigenen Optolink-/Statuspuffer nachgewiesen sind, kann eine sensorische Hypothese weiter geprueft werden. `0x54` alleine ist kein Sensorbeleg.

VS1 und P300 sind **nicht simultan**. Hin- und Rückwechsel dauerten vorher durchschnittlich 2,165 s bzw. 4,327 s; eine stabile Vor-/Nachklammer beweist deshalb keine konstante RPM waehrend der gesamten P300-Phase. Alle elf nativen Statusbytes, insbesondere Byte0/7/9, bleiben Diagnostik.

## Freigegebene experimentelle Bedienung (nach GitHub-CI-PASS)

Nur als root in der Optolink-LXC; Original-VS1 unter `/opt/optolink` unverändert und aktiv, exklusiver serieller Port, Forschungscheckout `/root/p300-trial-work/project`. Der Wrapper prüft Branch und Git-Status, aktualisiert nur den Forschungsbranch mit Fast-forward, führt die Offline-Regressionstests aus und startet erst dann die eigene systemd-Unit. **Keine manuelle chmod-Aktion erforderlich.**

```bash
# Kein Hardwarekontakt
bash /root/p300-trial-work/project/tools/wb2a-p300-p06-focus.sh plan

# Einmalige zielgerichtete Messung, Standard 1 Stunde; zulaessig 1..3
bash /root/p300-trial-work/project/tools/wb2a-p300-p06-focus.sh start 1

# Nur Status bzw. geordneter Stopp
bash /root/p300-trial-work/project/tools/wb2a-p300-p06-focus.sh status
bash /root/p300-trial-work/project/tools/wb2a-p300-p06-focus.sh stop
```

Die vorher aktiven Optolink/MQTT/HA-Zusatzdienste werden für den exklusiven Portzugriff temporär pausiert; die Heizungsregelung selbst läuft unabhängig weiter. Ein SIGTERM stoppt **erst an einer Grenze zwischen kompletten seriellen Transaktionen**. Der Worker versucht die geprüfte VS1-Rückverbindung, `systemd ExecStopPost` stellt unabhängig vom Worker alle zuvor aktiven Originaldienste wieder her, **Hauptsplitter zuerst**. Produktives P80=20/P06 gültig-nicht-FF wird über MQTT kontrolliert. Dies ist kein Nachweis über alle HA-Entity-Frischewerte.

## Aufzeichnungen und Ressourcen

- Session: `/root/p300-trial-work/p300-p06-focus-results/run-<UTC>-<PID>/`.
- `vs1.jsonl`: echte VS1-GFA-Referenzen mit Einzelzeitstempeln, `P06 FF` verworfen.
- `ram.jsonl`: alle 12 FC03-Reads pro qualifizierter Aufnahme, ACK/FC/Adresse/Länge/CRC/Raw/Timestamp.
- `status.jsonl`: alle FC01-Statusbytes, Flame/Lockout und Zeitposition.
- `switch.jsonl`, `trace.jsonl`: Wechselzeiten, Fehler und komplette TX-/RX-Spur.
- `captures/cNNNNN-r1.bin` / `r2.bin`: je exakt 192 Datenbytes; `*.partial.bin` für abgebrochene Runden; `captures/cNNNNN.json` mit SHA256, Kandidatenbytes bei 0x0F20/0x0F29/0x1C76, Vor-/Nachreferenzen und Qualitätsmarkern.
- `state.json`, `measurement.json`, `progress.json`, `recovery.json`, `health.json`; gepinnte Quellen `logger.py`, `fullram.py`, `deep.py`, `base.py`, `wb2a-handover-probe.py`.

Standard **eine Stunde**, Maximum **drei Stunden**, maximal 100 Aufnahmen, 384 Byte RAM-Payload pro vollständiger Fokusaufnahme. Vorab >=512 MiB frei, währenddessen >=256 MiB Mindestreserve, Sessionlimit 128 MiB, Streamlimit 64 MiB. Nach jedem kurzen VS1-Fenster wird der Status aktualisiert; alle Rohstreams werden regelmäßig geschrieben. Nicht den alten Vier-Stunden-Voll-RAM-Logger wiederholen.

**Privates einziges Upload-Archiv nach Restore:** `/root/p300-trial-work/research-bundles/p300-p06-focus-run-<UTC>-<PID>-bundle.tar.gz` mit Manifest-SHA256 aller Rohdateien und exakt ausgeführtem Quellstand.

## Entscheidung nach dem Archiv

Rohprotokolle/Manifest erneut unabhängig prüfen, stabile echte **zwei unterschiedliche positive P06-Levels** suchen und die Kandidaten in beiden RAM-Runden vergleichen. Falls `0x0F20`/`0x1C76` weiterhin `54` bei anderer positiver P06-Drehzahl zeigen, die naive `P06+1`-Interpretation verwerfen. **Keinen Proxy als tatsächliche Gebläsedrehzahl ausgeben**. Ohne unabhängigen Sensor folgt als Aufgabe-1-Architektur eine einzelne serielle Besitzerschicht mit **P300 als Hauptprotokoll und gezielten echten VS1-GFA-P06-Lesephasen**, inklusive gemessener Wechselkosten und vollständiger MQTT-/HA-/Wartungs-/Zeitprogramm-/Servicefunktionsparität.

**PR #46 nicht mergen.**
