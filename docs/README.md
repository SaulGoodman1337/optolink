# Dokumentationsindex

Dieser Ordner enthält die vom produktiven Branch `optolink-splitter-ha` übernommene Betriebs- und Entwicklerdokumentation sowie die getrennt aufgeführte Arbeit des Entwicklungsbranches `optolink-p300-migration`.

## P300-Entwicklung: Ziel und aktueller Stand vom 8. Oktober 2026

**Ziel:** Kontrollierter zusätzlicher RAM-Zugriff ohne Verlust bestehender Optolink-/HA-Funktionen. Er soll die Forschung an einer temporären Pumpensteuerung und an einer möglichen Vitotrol-Raumtemperaturaufschaltung ermöglichen. P300, schnelle Protokollwechsel und ein Fork sind Mittel zum Zweck, keine eigenen Abnahmekriterien. RAM-Zugriff allein beweist weder eine funktionierende Pumpenregelung noch eine Vitotrol-Emulation.

**Keine Produktionsfreigabe.** Der direkt gesendete C9/P80-Aufruf wurde von der lokalen WB2A zurückgewiesen. Die Quellenprüfung bestätigt den originalen VSKO-Weg über VS1/6B. Ein neuer nativer P300-GFA-Pfad ist nicht nachgewiesen.

**Beide Handover-Vergleiche jetzt an echter Hardware bestanden:**

- Zwei-ENQ-Basis: Session `run-20261008T092711Z-124106`, Prober 1.0.0, drei gültige Runden, `PASS_READ_ONLY_BASELINE`, anschließend MQTT P80=20/P06=00. Gesamter Weg inklusive GFA im Mittel 6,863 s.
- Ein-ENQ-Vergleich: Session `run-20261008T094009Z-124230`, Prober 1.1.0 / Commit `ff5504d`, drei gültige Runden, `PASS_READ_ONLY_SINGLE_ENQ`, anschließend Originaldienst active/running und MQTT P80=20/P06=00. Gesamter Weg inklusive GFA im Mittel **4,610 s**, Bereich 4,569–4,637 s. Aufbau und Recovery blieben beim Zwei-ENQ-Pfad.

Die zusätzliche zweite ENQ konnte in diesen drei gemessenen Rückwegen entfallen. Die beiden EOT-basierten ersten ENQ-Wartezeiten bleiben jeweils etwa 1,998 s. Die knapp 33 Prozent kürzere Gesamtdauer ist ein Fortschritt des Messablaufs, **keine Pumpen-RAM- oder Dauerbetriebsfreigabe**. Die E7-Arbeitskopie wird in der bisherigen Forschung etwa alle 2,1 s asynchron nachgeladen; ein lückenarmer Override ist mit dem aktuellen Wechselablauf nicht nachgewiesen.

**Neuer gezielter Vergleich vorbereitet:** Prober 1.2.0 bietet `--idle-enq`. Der gemessene VS1->P300-Einstieg wartet nach frischem Identitaetsread auf eine natuerliche ENQ, ohne vorher EOT zu senden. Der bestaetigte Ein-ENQ-Rueckweg sowie konservativer Aufbau/Recovery bleiben erhalten. Keine neue Adresse, kein C9 und kein RAM-/Parameterwrite. **Noch nicht an der Therme ausgefuehrt.** Kein identischer Wiederholungstest und kein dauerhaft aktivierter Hybridbetrieb; Details und Abnahmekriterien im neuen Runbook.

| Dokument | Bedeutung |
| --- | --- |
| [Natuerliche VS1-ENQ statt EOT](p300-idle-enq-comparison.md) | **Naechster vorbereiteter Test:** passive ENQ abwarten, dann unveraenderter P300-Handshake; 60 Offline-Tests, noch kein Geraeteergebnis |
| [Ziel und erfolgreiches Ein-ENQ-Ergebnis](p300-goals-and-single-enq-result-2026-10-08.md) | **Aktueller Einstieg:** Anwendungsziele, neue Messwerte, Abnahmekriterien und Grenzen |
| [Basisergebnis und damaliger Ein-ENQ-Testplan](p300-handover-baseline-result-and-single-enq.md) | Historische Auswertung und Vorbereitung des inzwischen ausgeführten Vergleichs; kein neuer Testauftrag |
| [Erhaltene Zwei-ENQ-Konsolenmesswerte](evidence/p300-handover-baseline-2026-10-08.json) | Drei echte Basisdatensätze; Ein-ENQ-Datensätze stehen im aktuellen Ergebnisbericht |
| [Historischer Handover-Basistest](p300-handover-baseline-runbook.md) | Verweis auf die erfolgreich ausgeführte Zwei-ENQ-Version und ihr unverändertes Original |
| [GFA-/VSKO-Auftrag: direkte Quellenprüfung](p300-gfa-host-trace-2026-10-08.md) | Direkt gelesene C#-Klasse, SDK-Kontexte und IL-Enumstellen; Quellen- und Aussagegrenzen |
| [Fork, schnellere Wechsel und GFA-Alternativen](p300-fork-switching-gfa-options-2026-10-08.md) | Früher Forschungsentwurf; RAM-Spiegel und Alternativen bleiben offen |
| [Quellenaudit und genaue Fundstellen](p300-switching-source-audit-2026-10-08.md) | Historischer Zeitablauf, ENQ-Folge, Upstream und Befehlsabbildung |
| [C9-Hardwarebefund](p300-gfa-c9-hardware-rejection-2026-10-08.md) | Negativer C9-Gerätebefund; kein pauschales P300-Unmöglichkeitsurteil |
| [P300-Migrationsplan](p300-migration.md) | Bestehender Kandidat und weiterhin geschlossene Freigabestufen |
| [Historischer CANARY und Rollback](p300-trial-install-rollback.md) | **Kein erneuter unveränderter C9-Versuch** |
| [Hydraulik-/Hardwarematrix](wb2a-topology-hardware-matrix.md) | Anlagenschema und realer Umbau, getrennt von der Protokollmigration |

Die bisherigen Live-Berichte beruhen auf Nutzer-Konsolentranskripten, nicht auf zusaetzlich importierten Originaldateien. Die neue Idle-ENQ-Variante aendert nur den isolierten Prober, seine Tests und Dokumentation. Produktionsruntime, Installer, HA-Profil und Updatekanal bleiben unveraendert.

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
