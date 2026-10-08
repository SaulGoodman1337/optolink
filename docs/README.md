# Dokumentationsindex

Dieser Ordner enthält die vom produktiven Branch `optolink-splitter-ha` übernommene Betriebs- und Entwicklerdokumentation sowie die getrennte Arbeit des Entwicklungsbranches `optolink-p300-migration`.

## P300: Ziel und aktueller Stand vom 8. Oktober 2026

**Ziel:** Kontrollierter RAM-Zugriff ohne Verlust bestehender Optolink-/HA-Funktionen, als Grundlage für Pumpen- und Vitotrol-Forschung. P300, ein Fork und Protokollwechsel sind Mittel zum Zweck. **Keine Produktionsfreigabe.**

**Abgeschlossene Kommunikationstests:** Zwei-ENQ-Basis 6,863 s, Ein-ENQ-Vergleich 4,610 s, Idle-ENQ 5,628 s im Mittel einschließlich GFA. Alle drei Abläufe funktionierten in den gemeldeten Runden; anschließend wurde VS1/GFA jeweils geprüft. Die Idle-Variante ist als Beschleunigungsansatz geschlossen. Kein erneuter identischer Test. Direkter C9/P80 wurde abgewiesen; die Quellen bestätigen den VSKO-Weg über VS1/6B.

**Quellenarbeit:** Alle 581 exakten Profil-Events mit 362 Adressen wurden gegen vollständige Metadaten geprüft. Keine benannte virtuelle P06-Istdrehzahl gefunden. Normale `0x7650/1` ist als GFA-Kennung belegt, aber kein automatischer Ersatz für frische P80-Kommunikation.

**Neuer Livebefund – P87-Vergleich durchgeführt:** Session `run-20261008T121446Z-124582`, Beobachter 1.0.0 / Commit `fbbebc26`. Im laufenden VS1 wurden 60 Klammermessungen ausgeführt: **59 stabile Matches** von P87 mit dem achten Byte (Index 7) aus `0x55D3/11`, ein uneindeutiger Übergang, keine stabile Abweichung. Matching-Zustände `00`, `20`, `60`, `62`; davon 54 der 59 Matches im Zustand `62`. Die Klammern dauerten 0,328–0,544 s. Das stützt den Kandidaten in den beobachteten stabilen Zuständen, nicht alle denkbaren Übergänge.

**Übergang nicht überspielen:** In Runde 4 kam P87=`30`, der native Block noch mit `20`, danach P87=`50`. Unterschiedliche Aktualisierungszeiten oder ein verzögerter Spiegel bleiben möglich; die genaue Latenz ist nicht bestimmt. `CANDIDATE_SUPPORTED_ON_SAMPLED_STATES` ist **keine Aliasfreigabe**.

**Nachkontrolle:** Normale MQTT-Reads P80=`20` und P06=`53` erfolgreich. P06 entspricht mit der dokumentierten Skalierung 2.490 U/min, ohne unabhängige Drehzahl-/Flammenmessung. Kein Dienst-/Protokoll-/Parameterwechsel durch den Beobachter und kein Rollback erforderlich. Allgemeine HA-Frische wurde im Transkript nicht vollständig geprüft.

**Noch offen:** Aktualisierung des Kandidaten während einer ausschließlich P300-lesenden Phase ohne externe GFA-Abfragen; P06- und P09-Ersatz. Die laufende VS1-Produktion pollte beim Vergleich weiterhin GFA, deshalb ist autonome P300-Frische ausdrücklich nicht belegt. Der Ergebniscommit dokumentiert die nächste Fragestellung, enthält aber **keine neue Testvariante**. Alten CANARY nicht reaktivieren, erfolgreiche Vergleiche nicht unverändert wiederholen.

| Dokument | Bedeutung |
| --- | --- |
| [P87: Ergebnis des dynamischen VS1-Vergleichs](p300-p87-vs1-result-2026-10-08.md) | **Aktueller Einstieg:** 59 Matches, Übergangsanalyse, P06-Nachkontrolle, P300-Frische weiterhin offen |
| [P87-Konsolendaten und Statistik](evidence/p300-p87-vs1-result-2026-10-08.json) | Alle 60 Messzeilen, Originalhash, abgeleitete Statistik getrennt; keine originalen pairs.jsonl/summary.json importiert |
| [GFA-Quellenabgleich und Kandidaten](p300-gfa-source-candidates-2026-10-08.md) | Quellenanalyse vor dem jetzt ausgeführten Test: Profilzuordnung, ursprüngliche P87-Hypothese, P06-/RAM-Grenzen |
| [Getesteter P87-MQTT-Vergleich](https://github.com/SaulGoodman1337/optolink/blob/fbbebc267dbc5b09cb4c86eb28661c815102915e/docs/p300-p87-mirror-runbook.md) | Erhaltene Anleitung und vorab festgelegte Kriterien; Vergleich inzwischen durchgeführt, kein neuer Testauftrag |
| [Quellenevidenz](evidence/p300-gfa-source-audit-2026-10-08.json) | Hashes, kleine Metadatenauswahl und getrennte Hypothesen; keine privaten Volltabellen |
| [Idle-ENQ-Ergebnis](p300-idle-enq-result-2026-10-08.md) | Erfolgreiche Kommunikation, aber langsamer: dieser Optimierungszweig abgeschlossen |
| [Idle-Messwerte](evidence/p300-idle-enq-result-2026-10-08.json) | Nutzertranskript und abgeleitete Vergleichswerte |
| [Historischer Idle-Test](p300-idle-enq-comparison.md) | Verweis auf getestete Fassung; kein neuer Testauftrag |
| [Ziele und Ein-ENQ-Ergebnis](p300-goals-and-single-enq-result-2026-10-08.md) | Anwendungsziele und erfolgreicher Ein-ENQ-Lauf |
| [Zwei-ENQ-Basis und Ein-ENQ-Vorbereitung](p300-handover-baseline-result-and-single-enq.md) | Historische Vorbereitung des inzwischen ausgeführten Vergleichs |
| [Zwei-ENQ-Messwerte](evidence/p300-handover-baseline-2026-10-08.json) | Erhaltene Nutzer-Konsolenmessungen |
| [Historischer Basistest](p300-handover-baseline-runbook.md) | Unverändertes Original über getesteten Commit |
| [Direkte GFA-/VSKO-Quellenprüfung](p300-gfa-host-trace-2026-10-08.md) | Befehlsabbildung, C#-/IL-Provenienz |
| [Fork-/GFA-Optionen](p300-fork-switching-gfa-options-2026-10-08.md) | Forschungsentwurf; offene Alternativen |
| [Umschalt-Quellenaudit](p300-switching-source-audit-2026-10-08.md) | Ursprüngliche Wartephasen und Messgrenzen |
| [C9-Hardwarebefund](p300-gfa-c9-hardware-rejection-2026-10-08.md) | Konkreter negativer Befund, kein globales P300-Unmöglichkeitsurteil |
| [Migrationsplan](p300-migration.md) | Historischer Kandidat und weiterhin geschlossene Freigabestufen |
| [Historischer CANARY](p300-trial-install-rollback.md) | **Nicht erneut unverändert ausführen** |
| [Hydraulikmatrix](wb2a-topology-hardware-matrix.md) | Reale Anlagenhardware, getrennt von Kommunikation |

Privates Rohmaterial bleibt im privaten Quellenrepo. Neue veröffentlichbare Ableitungen und eigene Werkzeuge liegen hier. Der neue Livebefund stammt vom Nutzer; seine Auswertung änderte nur Dokumentation und Evidenz. Bestehende Produktion, Beobachtercode, Installer, HA-Profil und Updatekanal bleiben unverändert. P06 und P09 sind nicht durch einen P87-Statuskandidaten ersetzt; der Pumpen-Override bleibt unfertig.

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
