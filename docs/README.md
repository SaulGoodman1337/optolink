# Dokumentationsindex

Dieser Ordner trennt produktive Betriebsdokumentation von der Forschung im Branch `optolink-p300-migration`.

## P300: aktueller Stand vom 8. Oktober 2026

**Ziel:** Kontrollierter RAM-Zugriff ohne Verlust bestehender HA-/Optolink-Funktionen, als Grundlage fuer Pumpen- und Vitotrol-Forschung. **Keine Produktionsfreigabe.**

**Vollmessungen jetzt ausgewertet:** Alle sechs uebergebenen Originaldateien sind gelesen. 807/807 FC01-55D3-Antworten stimmen mit JSON- und JSONL-Samples ueberein; waehrend beider Beobachtungsfenster enthaelt die protokollierte TX-Spur nur Statusreads und ACKs. Mit der bereits vorhandenen Flammenbitzuordnung sind drei Flammenbitfenster von jeweils etwa 27 s sichtbar. Kein neues Temperatur-/Taktsperrenmodell wird daraus behauptet.

**Kein vorschneller RPM-Fund:** Byte0/Byte9 sind die bereits bekannten Ansteuer-/Modulationswerte, nicht zwei neue unabhaengige Sensoren. Ihre 27 beobachteten Wertepaarungen sind deterministisch korreliert, P06/P09 aber nicht gleichzeitig erfasst. Ein neuer messender-vs-steuernder Datenweg ist weiter offen.

**Naechster Schritt bereits ausfuehrbar:** Ein separater MQTT-Beobachter liest `P80 -> P06 -> P09 -> 55D3/11 -> P09 -> P06` ueber den laufenden VS1-Splitter. Keine Dienstpause, keine Protokollumschaltung, kein RAM-/Parameterwrite. 23 neue Beobachter- und 15 Offline-Audittests; noch kein echter Lauf des neuen Beobachters. [Ausfuehrung und Abbruch](p300-gfa-native-pair-runbook.md).

### Abgeschlossene Bausteine

- C9/P80 direkt unter P300 abgewiesen; Original-VSKO verwendet VS1/6B. Kein erneuter identischer CANARY.
- Zwei-ENQ 6,863 s, Ein-ENQ 4,610 s, Idle-ENQ 5,628 s. Idle als Beschleunigungsvariante geschlossen; keine Wiederholung.
- 581 exakte Profil-Events / 362 Adressen geprueft. Keine benannte virtuelle P06-Istdrehzahl; 7650 ist Kennung, nicht frischer Kommunikationsnachweis.
- P87-VS1-Vergleich: 59 stabile Matches und ein uneindeutiger Uebergang. P300-only: 300 und 600 s mit spaeten Aenderungen ohne externe GFA-Reads; danach VS1/GFA wieder geprueft.
- Die neue Vollauswertung bestaetigt diese Befunde und nutzt zusaetzlich alle elf Bytes. P06/P09, genaue P87-Latenz und dauerhafter Pumpen-Override bleiben offen.

| Dokument | Bedeutung |
| --- | --- |
| [Vollmessungen und Byteaudit](p300-full-status-byte-audit-2026-10-08.md) | **Aktueller Einstieg:** Telegrammvalidierung, Flammenbitfenster, Byte0/Byte9-Abgrenzung, naechste Referenzmessung |
| [Neue P06/P09-Paarmessung](p300-gfa-native-pair-runbook.md) | **Ausfuehrbarer naechster Test:** laufendes VS1, keine Dienstpause, keine automatischen Aliasfreigaben |
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
