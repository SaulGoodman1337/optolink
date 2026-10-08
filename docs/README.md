# Dokumentationsindex

Dieser Ordner enthält die vom produktiven Branch `optolink-splitter-ha` übernommene Betriebs- und Entwicklerdokumentation sowie die unten getrennt aufgeführte Arbeit des Entwicklungsbranches `optolink-p300-migration`.

## P300-Entwicklung: aktueller Stand vom 8. Oktober 2026

**Keine Produktionsfreigabe.** Der konkret gesendete C9/P80-Aufruf wurde von der lokalen WB2A zurückgewiesen. VS1 funktioniert nach dem Rollback erneut mit P80=20 und P06=00. Das widerlegt nicht jeden denkbaren GFA-Zugriff unter P300.

Die sechs Sekunden des bisherigen Wechselhelfers sind ein Messwert dieses Ablaufs, keine bewiesene Untergrenze. Der Rückweg wartet auf zwei ENQs; Dienststopps und Portöffnung liegen außerhalb des Messfensters. Die erneute Quellenprüfung unterscheidet außerdem abstraktes GFA_READ=C9 von dessen belegter VSKO-Übersetzung nach VS1/6B.

| Dokument | Bedeutung |
| --- | --- |
| [Fork, schnellere Wechsel und GFA-Alternativen](p300-fork-switching-gfa-options-2026-10-08.md) | Aktuelle Bewertung beider Entwicklungswege, RAM-Spiegel, Prioritäten und Testgrenzen |
| [Quellenaudit und genaue Fundstellen](p300-switching-source-audit-2026-10-08.md) | Zeitmessung, ENQ-Folge, Upstream-Wartezeiten, C9/Sequenzbits und archivierte Vitosoft-Analyse |
| [C9-Hardwarebefund](p300-gfa-c9-hardware-rejection-2026-10-08.md) | Negativer Gerätebefund; der ergänzende GFA-Rollbacknachweis steht im aktuellen Optionsbericht |
| [P300-Migrationsplan](p300-migration.md) | Bestehender Kandidat und weiterhin geschlossene Freigabestufen |
| [Historischer CANARY und Rollback](p300-trial-install-rollback.md) | Reproduktion des bisherigen Tests und Wiederherstellung; **kein Auftrag zu einem erneuten unveränderten C9-Versuch** |
| [Hydraulik-/Hardwarematrix](wb2a-topology-hardware-matrix.md) | Anlagenschema und realer Umbau, getrennt von der Protokollmigration |

Die aktuelle Ergänzung ist Dokumentation und Entwurf. Kein neuer Fork, Runtime-Umbau oder Live-Test wurde damit ausgeführt. Die vorhandenen Aktivierungsanleitungen sind ohne neue, begründete Testvariante nicht erneut anzuwenden.

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
