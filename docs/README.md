# Dokumentationsindex

Dieser Ordner enthält die vom produktiven Branch `optolink-splitter-ha` übernommene Betriebs- und Entwicklerdokumentation sowie die getrennte Arbeit des Entwicklungsbranches `optolink-p300-migration`.

## P300: Ziel und aktueller Stand vom 8. Oktober 2026

**Ziel:** Kontrollierter RAM-Zugriff ohne Verlust bestehender Optolink-/HA-Funktionen, als Grundlage für Pumpen- und Vitotrol-Forschung. P300, ein Fork und Protokollwechsel sind Mittel zum Zweck. **Keine Produktionsfreigabe.**

**Neuer Hardwarebefund: beide P300-only-Läufe positiv.** Mit Prober 1.0.0 / Commit `e667c408` wurden 300 und 600 Sekunden ausschließlich FC01-Statusreads auf `0x55D3/11` beobachtet, während die bekannten externen GFA-Lesequellen pausierten. Beide Ausgaben melden `CHANGES_OBSERVED_WITHOUT_EXTERNAL_GFA`: 269 und 538 Samples, 7 und 10 späte Wechsel, davon 4 und 6 über mehrere Samples bestätigt. Im zweiten Lauf beginnt nach **353,333 Sekunden** eine weitere Statusfolge. Damit ist Aktualisierung während P300 ohne weitere externe GFA-Reads für diese Beobachtungen belegt, nicht nur Lesbarkeit eines alten Einstiegswerts.

**Beide Wiederherstellungen geprüft:** `LINK_AND_SERVICE_RESTORE=PASS`, anschließend Originaldienst `/opt/optolink`, active/running, echte MQTT-Antworten P80=20 und P06=00. Der Nutzer berichtet eine Brennerphase und vermutet eine Taktsperre; letztere ist aus den Statusbytes allein nicht diagnostiziert und entwertet den Frischenachweis nicht. Die Rohwerte 72/90 werden hier keinem gesicherten Abschaltgrund zugeordnet.

**Nächster Schritt ohne weiteren Heizungsversuch:** Die bereits lokal gespeicherten Vollmessungen beider Sessions sichern und offline auswerten. Die Konsole enthält nur Zusammenfassungen von Byte 7, nicht die 807 vollständigen 11-Byte-Blöcke oder TX/RX-Spuren. Der [aktuelle Bericht](p300-p87-p300-only-result-2026-10-08.md) enthält den unmittelbaren Archivierungsbefehl. Kein Update und kein erneutes gleichartiges P300-only-Fenster nötig.

**Weiterhin offen:** Vollständige P87-Aliasgleichheit und Latenz bei Übergängen sowie Ersatz für P06-Istdrehzahl und P09-Sollwert. Ein Statusspiegel ersetzt keine Drehzahl. Die normale FC01-Aktualisierung macht den zuvor abgewiesenen direkten C9/P80-Aufruf nicht funktionsfähig. Kein produktiver P300-Wechsel oder Pumpen-RAM-Override wird daraus freigegeben.

### Bereits abgeschlossene Bausteine

- Zwei-ENQ-Handover 6,863 s, Ein-ENQ 4,610 s, Idle-ENQ 5,628 s im Mittel einschließlich GFA. Alle drei Abläufe funktionierten in den gemeldeten Runden; Idle-ENQ ist als Beschleunigungsansatz geschlossen. Kein erneuter identischer Test. Die Quellen bestätigen den originalen VSKO-Weg über VS1/6B.
- Vollständige Quellenzuordnung: 581 exakte Profil-Events mit 362 Adressen. Keine benannte virtuelle P06-Istdrehzahl gefunden. `0x7650/1` ist als GFA-Kennung belegt, aber kein automatischer Ersatz für einen aktuellen GFA-Kommunikationsnachweis.
- Dynamischer VS1-Vergleich: 60 Klammern, 59 stabile Matches von P87 mit dem achten Byte von 55D3/11, Zustände 00/20/60/62, davon 54 Matches bei 62. Ein Übergang P87=30, Block=20, P87=50 bleibt Hinweis auf mögliche unterschiedliche Aktualisierung. Kein universeller verzögerungsfreier Aliasnachweis.
- Die neue P300-only-Beobachtung beantwortet die danach offene Aktualisierungsfrage positiv. Sie ergänzt den VS1-Vergleich, ohne dessen Übergangs- und Latenzgrenzen zu löschen.

| Dokument | Bedeutung |
| --- | --- |
| [P300-only: Ergebnis beider Läufe und nächster Schritt](p300-p87-p300-only-result-2026-10-08.md) | **Aktueller Einstieg:** 300/600 s, späte Änderungen, Taktsperren-Abgrenzung und Export bereits vorhandener Vollmessungen |
| [P300-only-Konsolenevidenz](evidence/p300-p87-p300-only-result-2026-10-08.json) | Beide ausgegebenen Ergebnisobjekte, Quellhash, Nachkontrollen und getrennte Berechnungen; keine erfundene Vollzeitreihe |
| [Getesteter P300-only-Ablauf](https://github.com/SaulGoodman1337/optolink/blob/e667c4084d3392e64be30ecd89a9c4425b3e464b/docs/p300-p87-p300-only-runbook.md) | Erhaltene Versuchsanleitung und ursprüngliche Abnahmekriterien; inzwischen in zwei Läufen durchgeführt, kein neuer Testauftrag |
| [P87: Ergebnis des dynamischen VS1-Vergleichs](p300-p87-vs1-result-2026-10-08.md) | 59 Matches, Übergangsanalyse und damalige P06-Nachkontrolle; separat von der jetzt positiven P300-Frische |
| [P87-Konsolendaten und Statistik](evidence/p300-p87-vs1-result-2026-10-08.json) | Alle 60 früheren Messzeilen und abgeleitete Statistik |
| [GFA-Quellenabgleich und Kandidaten](p300-gfa-source-candidates-2026-10-08.md) | Historische Kandidatenauswahl, vollständige Profilzuordnung, verbleibende P06-/RAM-Grenzen |
| [Getesteter P87-MQTT-Vergleich](https://github.com/SaulGoodman1337/optolink/blob/fbbebc267dbc5b09cb4c86eb28661c815102915e/docs/p300-p87-mirror-runbook.md) | Vorab definierte Kriterien; Vergleich durchgeführt, kein neuer Testauftrag |
| [Quellenevidenz](evidence/p300-gfa-source-audit-2026-10-08.json) | Hashes und Metadatenableitungen; keine privaten Volltabellen |
| [Idle-ENQ-Ergebnis](p300-idle-enq-result-2026-10-08.md) | Erfolgreiche Kommunikation, aber langsamer: Optimierungszweig abgeschlossen |
| [Idle-Messwerte](evidence/p300-idle-enq-result-2026-10-08.json) | Nutzertranskript und abgeleitete Vergleichswerte |
| [Historischer Idle-Test](p300-idle-enq-comparison.md) | Verweis auf getestete Fassung; kein neuer Testauftrag |
| [Ziele und Ein-ENQ-Ergebnis](p300-goals-and-single-enq-result-2026-10-08.md) | Anwendungsziele und erfolgreicher Ein-ENQ-Lauf |
| [Zwei-ENQ-Basis und Ein-ENQ-Vorbereitung](p300-handover-baseline-result-and-single-enq.md) | Historische Vorbereitung des abgeschlossenen Vergleichs |
| [Zwei-ENQ-Messwerte](evidence/p300-handover-baseline-2026-10-08.json) | Erhaltene Nutzer-Konsolenmessungen |
| [Historischer Basistest](p300-handover-baseline-runbook.md) | Unverändertes Original über getesteten Commit |
| [Direkte GFA-/VSKO-Quellenprüfung](p300-gfa-host-trace-2026-10-08.md) | Befehlsabbildung, C#-/IL-Provenienz |
| [Fork-/GFA-Optionen](p300-fork-switching-gfa-options-2026-10-08.md) | Forschungsentwurf; offene Alternativen |
| [Umschalt-Quellenaudit](p300-switching-source-audit-2026-10-08.md) | Ursprüngliche Wartephasen und Messgrenzen |
| [C9-Hardwarebefund](p300-gfa-c9-hardware-rejection-2026-10-08.md) | Konkreter negativer Befund, kein globales P300-Unmöglichkeitsurteil |
| [Migrationsplan](p300-migration.md) | Historischer Kandidat und weiterhin geschlossene Freigabestufen |
| [Historischer CANARY](p300-trial-install-rollback.md) | **Nicht erneut unverändert ausführen** |
| [Hydraulikmatrix](wb2a-topology-hardware-matrix.md) | Reale Anlagenhardware, getrennt von Kommunikation |

Die neuen Hardwareergebnisse stammen aus dem Nutzertranskript. Die aktuelle Auswertung ändert nur Dokumentation und Evidenz. Produktionsruntime, alle Prober, Tests, Installer, HA-Profil und Updatekanal bleiben unverändert. Privates Rohmaterial bleibt im privaten Quellenrepo; öffentlich werden nur erlaubte Ableitungen und eigene Werkzeuge dokumentiert.

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
