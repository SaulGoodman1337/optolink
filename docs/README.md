# Dokumentationsindex

Dieser Ordner trennt produktive Betriebsdokumentation von der Forschung im Branch `optolink-p300-migration`.

## P300: aktueller Stand vom 8. Oktober 2026

**AKTUELL: UART1-Fokuslauf erfolgreich abgeschlossen.** Der Betreiber
hat den 60-s-P300-FC03-Lauf mit 25 Status-/RAM-Runden
bereits erfolgreich ausgefuehrt. 15 RAM-Bytes wechselten
in fuenf Ereignissen zwischen sechs erfassten Speicherzustaenden;
die historische UART1-DMA0-Ankeradresse `0x161B`
selbst wechselte nicht. Status `55D3[7]`, P06
und P09 blieben in diesem Fenster `00`.
VS1 und alle aktiven Dienste wurden laut Mess-/
Restore-Protokoll erfolgreich wiederhergestellt.
Das **vollstaendige nachgereichte Originalarchiv** ist jetzt unabhaengig
verifiziert: **77/77 P300-Antworten** mit gueltiger Adresse, Laenge,
Pruefsumme und Sample-Payload, **143/143 archivierte Tests**,
post-Restore MQTT-GFA-P80=20/P06=00 erfolgreich.
Der RAM-Befund wird **nicht** mit GFA-P06 gleichgesetzt; vollstaendiger
Status Byte2 wechselte B1->B2, P87-Byte7 blieb 00.
**Keine UART1/GFA-Anbindung und kein P06-RPM-Alias nachgewiesen.**
[Hardwareauswertung und vereinheitlichter Batchablauf](p300-uart1-live-result-and-batch-2026-10-08.md)
sowie [abgeleitete Evidenz](evidence/p300-uart1-focus-result-2026-10-08.json).

**Weniger Copy/Paste:** Fuer den naechsten Datenbatch
gibt es jetzt `tools/wb2a-research-batch.sh`, das den
ausschliesslich experimentellen Branch ohne lokale Aenderungen
per Fast-Forward aktualisiert, die Offline-Tests laeuft,
die vorhandene UART1-Messung validiert,
den laufenden Original-VS1-Dienst kontrolliert und
**ein einziges privates tar.gz-Ergebnisarchiv** erzeugt.
Der bereits erfolgreiche identische UART1-Hardwaretest
wird **nicht** automatisch wiederholt. Kein RAM-Write,
kein Produktivmerge.

**NEU - P06-Istdrehzahl unter P300 (Source-First-Abschluss):**
Ein weiterer modellgebundener Vergleich oeffentlicher VDensHO1-Kataloge
und alle elf Bytes der bereits hochgeladenen 180 P06/P09-VS1-Paarmessungen
liefern **keinen validierten, unabhaengigen P06-Istwert**. `0x0B1E`
gehoert zu VBC550S/SC100, `0x1A53` zum V200WO1C-Modell, `0x7660`
zur Umwaelzpumpe. Im Statusblock sind Byte0/Byte9 Ansteuer-/Modulationswerte;
Byte1/Byte2 bleiben sogar in allen 154 stabilen P06=00-Runden ungleich null.
**Keine neue Leseadresse und kein RPM-Alias freigegeben.**
[Quellenvergleich und naechstes RAM-Evidenz-Gate](p300-fan-actual-source-screen-2026-10-08.md)
mit [abgeleiteten Kennzahlen](evidence/p300-fan-actual-source-screen-2026-10-08.json)
und Offline-Testwerkzeug. Kein neuer Thermenzugriff, kein Aendern der Produktion.

**Ziel:** Kontrollierter RAM-Zugriff ohne Verlust bestehender HA-/Optolink-Funktionen, als Grundlage fuer Pumpen- und Vitotrol-Forschung. **Keine Produktionsfreigabe.**

**Aktueller Hardwarebefund:** Die erste direkte Same-Session-Messung von GFA-P06/P09 gegen den nativen 55D3-Block ist abgeschlossen: **180 von 180 Runden** stimmen in `pairs.jsonl` und `summary.json` ueberein. P06 war in 171 Runden stabil, aenderte sich aber in neun Klammern; P09 war in allen 180 Klammern stabil. Die Aufnahme enthaelt 24 Flammenbit-Samples und eine natuerliche Brennerphase mit Anlauf, Abwaertsrampe, Modulationsboden und Abschalten. **Der entscheidende Gegenbeleg fuer einen einfachen P06-RPM-Alias:** Nach dem Flammenbit-Ende ist P09=00 und P06 sinkt innerhalb einer Klammer von 0x52 auf 0x1D, waehrend Byte9 im Statusblock noch 33 zeigt.

**Einordnung:** Status-Byte7 ist zuvor als dynamischer P87-Kandidat unter P300 belegt. Byte0/Byte9 sind Ansteuer-/Modulationswerte, **keine bewiesene Ist-Geblaesedrehzahl**. Auch P09 ist nicht als vollwertiger 1:1-Alias freigegeben. Eine beschraenkte quellenbasierte Suche nach einem unabhaengigen P06-Istwert hat deshalb Vorrang vor weiteren identischen 600-/900-Sekunden-Paarmessungen oder RAM-Schreibexperimenten.

**Dokumentation und Reproduktion:** [180-Runden-Geraeteauswertung](p300-gfa-native-pair-result-2026-10-08.md), [abgeleitete Evidenz](evidence/p300-gfa-native-pair-result-2026-10-08.json), `tools/audit-gfa-native-pairs.py` (nur offline), 11 Regressionstests. Private Rohzeitreihen sind **nicht** im oeffentlichen Repository. VS1 bleibt produktiv, **keine P300-Migration oder Pumpen-RAM-Freigabe**.

### Abgeschlossene Bausteine

- C9/P80 direkt unter P300 abgewiesen; Original-VSKO verwendet VS1/6B. Kein erneuter identischer CANARY.
- Zwei-ENQ 6,863 s, Ein-ENQ 4,610 s, Idle-ENQ 5,628 s. Idle als Beschleunigungsvariante geschlossen; keine Wiederholung.
- 581 exakte Profil-Events / 362 Adressen geprueft. Keine benannte virtuelle P06-Istdrehzahl; 7650 ist Kennung, nicht frischer Kommunikationsnachweis.
- P87-VS1-Vergleich: 59 stabile Matches und ein uneindeutiger Uebergang. P300-only: 300 und 600 s mit spaeten Aenderungen ohne externe GFA-Reads; danach VS1/GFA wieder geprueft.
- Die neue Vollauswertung bestaetigt diese Befunde und nutzt zusaetzlich alle elf Bytes. P06/P09, genaue P87-Latenz und dauerhafter Pumpen-Override bleiben offen.

| Dokument | Bedeutung |
| --- | --- |
| [UART1: Hardwareergebnis und Ein-Befehl-Batch](p300-uart1-live-result-and-batch-2026-10-08.md) | **Aktuell:** 25 verifizierte Runden, 15 geaenderte RAM-Bytes, keine RPM-Freigabe, einheitlicher Datenexport |
| [UART1: abgeleitete physische Lesemessung](evidence/p300-uart1-focus-result-2026-10-08.json) | Beobachtungsdauer, Trace-Allowlist, Werte-/Adressdelta und Restore-Befund; kein privater Volldump |
| [Abgeschlossener UART1-P300-RAM-Fokus](p300-uart1-p300-focus-runbook.md) | Historischer einmaliger 60-s-Geraeteversuch vom 8. Oktober; nicht unveraendert wiederholen |
| [UART1/Optolink Datenfluss aus alten Forschungsergebnissen](p300-uart1-gfa-dataflow-offline-2026-10-08.md) | DMA0-Quellpointer ist kein P06-Istwert; Offline-Auditor fuer vorhandene Dumps |
| [P06-Istdrehzahl: modellgebundener Quellenaudit](p300-fan-actual-source-screen-2026-10-08.md) | **Aktueller Stand:** 11 Statusbytes, auszusondernde fremde Leseadressen, naechstes RAM-Evidenz-Gate |
| [Fan-Quellenaudit-Evidenz](evidence/p300-fan-actual-source-screen-2026-10-08.json) | SHA256-gepinnte private Quelle, Modellgrenzen, Bytekennzahlen, keine RPM-Freigabe |
| [P06/P09 gegen 55D3: 180-Runden-Ergebnis](p300-gfa-native-pair-result-2026-10-08.md) | **Aktueller Einstieg:** kein nativer P06-Istalias, voneinander getrennte Soll-/Istwerte, beobachtete Brennerphase |
| [Abgeleitete P06/P09-Evidenz](evidence/p300-gfa-native-pair-result-2026-10-08.json) | Datei-Hashes, Paarzaehlung, Statusfenster, zehn ausgesuchte Gegenproben |
| [Vollmessungen und Byteaudit](p300-full-status-byte-audit-2026-10-08.md) | Historisch: 807 P300-Statusantworten, drei kurze Flammenbitfenster und Quelle der Anschlussmessung |
| [Durchgefuehrter P06/P09-MQTT-Vergleich](p300-gfa-native-pair-runbook.md) | Historischer, bereits abgeschlossener lesender VS1-Ablauf; nicht ohne neue Fragestellung wiederholen |
| [Maschinelle Vollauswertung](evidence/p300-full-status-byte-audit-2026-10-08.json) | Hashes, Antwortpruefungen, Bytebereiche und beobachtete Bitfenster |
| [P300-only-Konsolenbefund](p300-p87-p300-only-result-2026-10-08.md) | Historischer Bericht vor Uebergabe der nun ausgewerteten Originaldateien; kein erneuter Exportauftrag |
| [P300-only-Konsolenevidenz](evidence/p300-p87-p300-only-result-2026-10-08.json) | Beide damaligen Konsolensummen und Nachkontrollen |
| [Getesteter P300-only-Ablauf](p300-p87-p300-only-runbook.md) | Durchgefuehrter Statusversuch; nicht fuer die bereits beantwortete Frage wiederholen |
| [Dynamischer P87-VS1-Vergleich](p300-p87-vs1-result-2026-10-08.md) | 59 Matches, Uebergangsgrenze und GFA-Nachkontrolle |
| [P87-VS1-Konsolenevidenz](evidence/p300-p87-vs1-result-2026-10-08.json) | 60 fruehere Vergleichszeilen |
| [GFA-Quellenabgleich](p300-gfa-source-candidates-2026-10-08.md) | Profilzuordnung und Herkunft der Kandidaten |
| [Quellenevidenz](evidence/p300-gfa-source-audit-2026-10-08.json) | Hashes und kleine Metadatenableitungen, keine privaten Volltabellen |
| [Historischer P87-MQTT-Test](p300-p87-mirror-runbook.md) | Bereits ausgefuehrter P87-Vergleich |
| [Idle-ENQ-Ergebnis](p300-idle-enq-result-2026-10-08.md) | Kein Geschwindigkeitsgewinn, Zweig geschlossen |
| [Idle-Messwerte](evidence/p300-idle-enq-result-2026-10-08.json) | Nutzertranskript und Berechnungen |
| [Historischer Idle-Test](p300-idle-enq-comparison.md) | Verweis auf getestete Fassung |
| [Ziel und Ein-ENQ-Ergebnis](p300-goals-and-single-enq-result-2026-10-08.md) | Anwendungsziele und Zeitgewinn |
| [Zwei-ENQ-Basis](p300-handover-baseline-result-and-single-enq.md) | Historische Vorbereitung und Auswertung |
| [Zwei-ENQ-Messwerte](evidence/p300-handover-baseline-2026-10-08.json) | Basisdatensaetze |
| [Historischer Basistest](p300-handover-baseline-runbook.md) | Unveraendertes Original ueber Commit |
| [Direkte VSKO-Quellenpruefung](p300-gfa-host-trace-2026-10-08.md) | C#-/IL-Befehlsabbildung |
| [Fork-/GFA-Optionen](p300-fork-switching-gfa-options-2026-10-08.md) | Forschungsentwurf, offene Alternativen |
| [Umschalt-Quellenaudit](p300-switching-source-audit-2026-10-08.md) | Zeitablauf, Quellen- und Messgrenzen |
| [C9-Hardwarebefund](p300-gfa-c9-hardware-rejection-2026-10-08.md) | Konkreter negativer Befund |
| [Migrationsplan](p300-migration.md) | Historischer Kandidat, Freigaben geschlossen |
| [Historischer CANARY](p300-trial-install-rollback.md) | Nicht unveraendert wiederholen |
| [Hydraulikmatrix](wb2a-topology-hardware-matrix.md) | Reale Anlage, getrennt von Protokollforschung |

Originalarchive und private Quellen bleiben ausserhalb dieses oeffentlichen Dokumentationsbestands; publiziert sind abgeleitete technische Ergebnisse und eigene Werkzeuge. Bestehende Produktion, bisherige Prober, Installer, HA-Profil und Updatekanal bleiben unveraendert.

## Einstieg in die übernommene Produktionsdokumentation

| Dokument | Wann lesen? |
| --- | --- |
| [architecture.md](architecture.md) | Als Erstes: Komponenten, Datenfluss, Dienste und Sicherheitsgrenzen |
| [operations.md](operations.md) | Beim Betrieb: Update, Status, Logs, Clock-Sync, Fehlerdiagnose |
| [home-assistant.md](home-assistant.md) | Bei HA-/MQTT-/Dashboard-Änderungen |
| [anlagenschema.md](anlagenschema.md) | WB2A-Anlagenschema, Hydrauliktopologie und dokumentierte Schreibwerte 00/52/53/54/5B |
| [development.md](development.md) | Vor Änderungen an Reads, Writes, Services oder Deployment |
| [optolink-maintenance.md](optolink-maintenance.md) | Wartungswerte und CLI |
| [optolink-maintenance-api.md](optolink-maintenance-api.md) | MQTT-Wartungs-API und HA-Integration |
| [wb2a-schedule-blocks.md](wb2a-schedule-blocks.md) | Zeitprogrammformat und verifizierte WB2A-Blöcke |
| [service-programs.md](service-programs.md) | Befüllungs-/Entlüftungsprogramm, Codieradresse 2F / 0x572F |
| [manuals/README.md](manuals/README.md) | Servicehandbuch-Quelle und lokaler Download-Helfer |

Zusätzliche technische Referenz:

- [../config/optolink-splitter/vcontrol-mapping.md](../config/optolink-splitter/vcontrol-mapping.md) — Legacy-vcontrold-Migrationsmapping; nicht die aktuelle 20C2-Quelle der Wahrheit.

## Quellen der Wahrheit

Für unterschiedliche Fragestellungen gelten bewusst unterschiedliche Dateien als maßgeblich:

| Frage | Quelle |
| --- | --- |
| Welche Entities/Datenpunkte pollt Produktion? | `config/optolink-splitter/vdensho1-20c2-wb2a-homeassistant.py` |
| Wie sind Anlagenschema/Topologie und deren zulässige Schreibwerte dokumentiert? | `docs/anlagenschema.md` |
| Welche Werte darf Wartung schreiben? | `config/optolink-splitter/optolink_maintenance_core.py` |
| Welche Zeitprogrammblöcke sind erlaubt? | `tools/optolink-schedule-manager.py` |
| Wie wird Party technisch umgesetzt? | `tools/optolink-party-emulator.py` |
| Wie wird die Gerätezeit synchronisiert? | `tools/optolink-clock-sync.py` |
| Wie werden Befüllung/Entlüftung gesteuert? | `tools/optolink-service-programs.py` |
| Wie wird ein bestehendes System aktualisiert? | `tools/optolink-splitter-update.sh` |
| Wie wird das Profil sicher aktiviert? | `tools/optolink-apply-vdensho1-ha-profile.sh` |
| Wie wird eine neue LXC-Installation aufgebaut? | `install/optolink-splitter-install.sh` |
| Wie sieht die HA-Oberfläche aus? | `config/optolink-splitter/homeassistant-dashboard.yaml` |

## Dokumentationsregel

Die übernommene Betriebsdokumentation beschreibt den **produktiven Zustand**. Allgemeines Reverse Engineering bleibt im Research-Archiv. Auf ausdrücklichen Nutzerwunsch wird die aktuelle P300-Migrationsforschung in diesem Entwicklungsbranch dokumentiert, getrennt von produktiven Freigaben und mit erkennbaren Hypothesen-/Beleggrenzen.

Wenn Codeverhalten geändert wird, sollten im selben Änderungssatz mindestens die direkt betroffene Dokumentation und — bei einer wichtigen Invariante — der CI-Guard angepasst werden.

## Architekturdiagramme

- [Systemübersicht](images/optolink-system-overview.svg)
- [Dienstekommunikation und Sicherheitsmodell](images/service-communication-security.svg)

Die Root-README rendert beide Diagramme direkt.
