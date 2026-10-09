# WB2A / VDensHO1: Full-RAM-Logger mit echter VS1-P06-Klammer

**9. Oktober 2026 | Forschungsbranch `optolink-p300-migration` | PR #46 | keine Produktionsfreigabe**

## Ziel und Abgrenzung

Aufgabe 1 bleibt die vollstaendige P300-Migration mit funktionaler VS1-Paritaet, vor allem **echter Geblaese-Istdrehzahl GFA P06**. Die vorherige acht-Block-Messung fand keinen belegten P300-P06-Kanal. Dieser **neue Logger** liest jetzt in jedem Sweep physisch **0x0400..0x53FF inkl. (640 x 32 = 20.480 Byte)** und misst echte VS1-P06 vor und nach jedem Durchgang. Keine Vitotrol-Emulation, kein Pumpenoverride, keine Parameter-/RAM-Schreibbefehle. **P09 ist Modulationsanforderung, keine gemessene Drehzahl; 55D3 Byte0/7/9 sind Diagnostik, kein P06-Alias.**

Die Daten stammen nie zeitgleich aus VS1 und P300. Eine ueber ca. 90 s verteilte RAM-Aufnahme ist **nicht atomar**. `STABLE_BRACKET_OFF/RUNNING` bedeutet nur: mindestens sechs Sekunden und sechs gueltige VS1-Referenzrunden vor **und** nach dem Sweep mit identischem P06-Rohbyte, ohne beobachteten Flame-Bit-Wechsel. Das ist keine Garantie fuer Stabilitaet innerhalb der RAM-Aufnahme. Jeder andere Fall wird `TRANSITION_OR_UNKNOWN`.

## Betrieb nur in separater Optolink-LXC-Forschungsinstallation

Vor dem Start: LXC als root, Produktivinstallation unveraendert unter `/opt/optolink`, separater sauberer Checkout unter `/root/p300-trial-work/project`, Original-VS1-Splitter aktiv. Verwende nur folgenden neuen Wrapper nach dem CI-PASS. Nicht den bisherigen Deep-Logger erneut ausfuehren.

Start (vier Stunden, optional `start 1` bis `start 8`):

```bash
bash /root/p300-trial-work/project/tools/wb2a-p300-fullram-logger.sh start 4
```

Status:

```bash
bash /root/p300-trial-work/project/tools/wb2a-p300-fullram-logger.sh status
```

Geordneter Stopp, jederzeit:

```bash
bash /root/p300-trial-work/project/tools/wb2a-p300-fullram-logger.sh stop
```

Ohne Hardwarezugriff kann vorab `bash /root/p300-trial-work/project/tools/wb2a-p300-fullram-logger.sh plan` aufgerufen werden. Der Startwrapper synchronisiert nur diesen Forschungsbranch per Fast-forward, prueft dessen Offline-Tests und startet eine temporaere, separat beaufsichtigte systemd-Unit `optolink-p300-fullram-logger.service`. **Nicht vor Gruenstatus der GitHub-CI starten.**

Waerend der Messung sind alle zuvor aktiven produktiven Optolink-MQTT-/HA-Dienste fuer exklusiven seriellen Zugriff voruebergehend angehalten; die Heizungsregelung selbst laeuft normal. Die Dienste werden in urspruenglicher Aktivkonstellation restauriert, Hauptsplitter zuerst. Bei Fehlern nach einer nicht abgeschlossenen seriellen Transaktion wird nicht einfach eine neue unbekannte Abfrage losgeschickt. Der alte Stop-Fix wartet bei SIGTERM das aktuelle Telegramm ab. Fuer Crash/SIGKILL ist die systemd-`ExecStopPost`-Wiederherstellung hinterlegt. **Ein dauerhaft gelungener Recovery-Pfad kann erst live nachgewiesen werden.**

## Datenformat und Integritaet

Je Session `/root/p300-trial-work/p300-fullram-results/run-<UTC>-<PID>/`:

| Datei | Inhalt |
|---|---|
| `snapshots/sNNNNN.bin` | bei `COMPLETE` exakt 20.480 Bytes, kanonisch ab Adresse 0x0400 |
| `snapshots/sNNNNN.partial.bin` | bei `PARTIAL` alle bisher erfassten Bytes, auch bei Stopp/Fehler |
| `snapshots/sNNNNN.json` | Scanrichtung, Zeitfenster, SHA256, Dauer, Blockzahl, Fehler, Klassifikation, P06-Klammern |
| `blocks.jsonl` | jeder Block: UTC/monotonic TX/RX, Frame/Rohantwort, ACK, FC/Adresse/Laenge, Checksumme, Antwortdauer und Fehler |
| `vs1.jsonl` | echte GFA-P06/P09/P87/P80/P10/P84 mit Rohhex, Einzeltimestamps, Status |
| `status.jsonl` | alle 32 Bloecke FC01 0x55D3/11, Flame/Lockout und unveraenderter 11-Byte-Rohstatus |
| `switch.jsonl` | Wechselzeit, Grund, Ergebnis und Identitaetspruefung |
| `trace.jsonl` | alle TX/RX-Rohdaten aus dem gepinnten seriellen Delegate |
| `state.json`, `progress.json`, `measurement.json`, `recovery.json`, `health.json` | Quellversion, Fortschritt, Messung, Restore und Original-VS1-MQTT/P80/P06-Gesundheit |
| `logger.py`, `deep.py`, `base.py`, `wb2a-handover-probe.py` | im Archiv gespeicherte und mit SHA256 verankerte Ausfuehrungsquellen |

Das eine Upload-Archiv liegt nach Abschluss unter:

```text
/root/p300-trial-work/research-bundles/p300-fullram-run-<UTC>-<PID>-bundle.tar.gz
```

Darin `bundle-manifest.json` mit SHA256/Laenge aller aufgenommenen Dateien. Kein stilles Nullenauffuellen, keine unkontrollierten Retries: fehlerhafter Block markiert den Sweep als `PARTIAL` und beendet die Aufnahme geordnet. Rueckwaerts erfasste volle Dumps werden bei Abschluss in die kanonische Adressreihenfolge gedreht. Auch partielle Dateien bleiben erhalten, mit expliziter Scanrichtung.

## Ressourcen und Grenzen

Vier Stunden mit theoretischen 90 s pro Sweep ergeben grob **160 Snapshots**, also nur ca. **3,13 MiB reine RAM-Binardaten**, jedoch vielfach mehr fuer Rohframes, VS1-Klammern, JSON und Trace. Die Kapazitaetsplanung nimmt vorsichtig **1 MiB pro Snapshot = ca. 160 MiB unkomprimierte Daten** an. Dies ist eine Schaetzung, keine obere Schranke je Sweep. Hardcap: 256 MiB Session, 128 MiB pro Logstream, zusaetzlich mindestens 384 MiB freier Datentraeger, Start nur mit mindestens 896 MiB frei. Bei Grenzwertverletzung geordneter Fehler und Restore. Fortschritt nach spaetestens etwa 20 s bzw. jedem 32-Block-Checkpoint, fsync pro Checkpoint. Maximale Loggerlaufzeit 4 h Standard, 1..8 h konfigurierbar. Einzelne serielle Reads haben eine dreisekuendige Antwortfrist; eine laufende Transaktion wird nicht wegen der Zeitgrenze unterbrochen.

## Qualitaetspruefung nach dem Upload

1. Manifest, SHA256, Dateigroessen und die 640 verschiedenen FC03/32-Adressen je vollem Snapshot unabhaengig nachrechnen; Response-ACK, FC, Adresse, Laenge, Checksumme und RX-Rohbytes gegen Blocklog pruefen.
2. Echte VS1-P06=00- und Nichtnull-Phasen anhand einzelner Rohbytes und Zeitstempel analysieren; P06=FF ausklammern. P09/Status getrennt behandeln.
3. Byte-, 16-/32-bit Little-/Big-Endian-, skalierte RPM-, BCD- und Bitfeldkandidaten vergleichen; RAM-Kommunikationspuffer 0x192C..0x1952 / 0x196C..0x1A6D und KM-Bus-UART1-TX als moegliche Artefakte ausschliessen.
4. Kandidaten nur bei mindestens zwei positiven Drehzahlstufen, Null-/Nichtnull-Trennung, Aktualitaet, Uebergangsverhalten und Unabhaengigkeit von vorherigen Optolink-P06-Abfragen weiterverfolgen.
5. Falls kein unabhaengiger Sensorzugriff belastbar nachweisbar: **gemeinsamer serieller Besitzer mit P300-Hauptbetrieb und gezielten VS1-GFA-Lesephasen** als Architekturvariante untersuchen, einschliesslich mehrsekundiger Wechselzeiten und kompletter Funktionsparitaet. Kein Freigeben geschaetzter RPM.

## Sperre

**PR #46 nicht mergen; Produktivcode, Updatekanal, Pumpen und Vitotrol unveraendert lassen.** CI-Test ist kein Hardwarebeweis; nur lokale echte Messung plus erfolgreicher Restore koennen die praktische Nutzbarkeit bestaetigen.
