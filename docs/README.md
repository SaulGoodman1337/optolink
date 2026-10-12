# Dokumentationsindex

Dieser Ordner enthält die Betriebs- und Entwicklerdokumentation für den produktiven Branch `optolink-splitter-ha`.

## Einstieg

| Dokument | Wann lesen? |
| --- | --- |
| [architecture.md](architecture.md) | Als Erstes: Komponenten, Datenfluss, Dienste und Sicherheitsgrenzen |
| [hybrid-protokollwechsel.md](hybrid-protokollwechsel.md) | Optionaler VS1/P300-Lesetest, Verifikation, Rückfallroutine und Sperrmechanismen |
| [wb2a-root-on-demand-api-2026-10-10.md](wb2a-root-on-demand-api-2026-10-10.md) | Nur Root: authentifizierter lokaler On-Demand-P300-Request, Rückgabe, TTL, Berechtigungsgrenze und C3-Hardwarecanary |
| [wb2a-vitotrol-rpm-next-phase-2026-10-10.md](wb2a-vitotrol-rpm-next-phase-2026-10-10.md) | Separater Entwicklungsbranch: Vitotrol-KM-Bus-Offline-Simulator, passive Vier-Tage-VS1-RPM-Messung und Beweisgrenzen |
| [wb2a-vitotrol-original-reference-2026-10-10.md](wb2a-vitotrol-original-reference-2026-10-10.md) | Research: 448 CRC-gueltige Original-Vitotrol-300-TX-Frames, Quellvergleich und Offline-Audit |
| [wb2a-vitotrol-native-p300-variant-matrix-2026-10-11.md](wb2a-vitotrol-native-p300-variant-matrix-2026-10-11.md) | Echte Vitotrol-200/300-Vergleichsmessungen: A0:1 vs. A0:2, typkorrekte Original-Identitäten, zwei echte Discovery-Follower, Regler-Readbacks und vollständige Rückstellung |
| [wb2a-vitotrol-p300-gateway-differential-2026-10-11.md](wb2a-vitotrol-p300-gateway-differential-2026-10-11.md) | Direktes A0:0→A0:2/B0:3→A0:0 P300-Experiment mit KBUS-Gateway-FC0x65, indirektem FC0x63, RX-Deskriptor-/TX-RAM-Differenz und unabhängiger Originalwiederherstellung |
| [wb2a-vitotrol-optolink-room-feedback-live-2026-10-11.md](wb2a-vitotrol-optolink-room-feedback-live-2026-10-11.md) | Drei echte 20C2-Hardware-A/B/A-Versuche mit externem Raumsollwert 0x2321: Vorlauf-Soll +1,9/-0,5 Grad C und nachweisliche Rueckstellung; neuer experimenteller MQTT-Raumregler, weiterhin keine Vitotrol-Anmeldung |
| [wb2a-vitotrol-native-p300-active-2026-10-11.md](wb2a-vitotrol-native-p300-active-2026-10-11.md) | Echter nativer P300-SRAM-Schreibtest: originale V300-B3/B1/BF/PONG-Frames in WB2A-RAM, A0/B0-Liveversuche, 0B6B-Ereignisflags, Gateway-Opcode-Matrix, automatisierter Bridge-Treiber und weiterhin fehlende Vitotrol-Anmeldung |
| [wb2a-vitotrol-public-pcap-firmware-gate-2026-10-11.md](wb2a-vitotrol-public-pcap-firmware-gate-2026-10-11.md) | Zwei SHA-gepinnte öffentliche PCAPNG-Captures (5269 + 701 CRC-gültige Nachrichten), Vitotrol-Master-Replay, 79-SRAM-RX-Deskriptor-Indizien und VitoSoft-Profil-Negativbelege |
| [wb2a-vitotrol-optolink-rx-2026-10-10.md](wb2a-vitotrol-optolink-rx-2026-10-10.md) | Optolink-only RX-Forschung: 0x1642-Kandidatenpuffer aus 374 historischen P300-RAM-Samples, sicherer fester Read-only-Diagnosepfad |
| [wb2a-vitotrol-optolink-rx-context-2026-10-10.md](wb2a-vitotrol-optolink-rx-context-2026-10-10.md) | Byte- und Zeitkontext des 0x1642-RX-Kandidaten, 79 Voll-RAM- und 295 Deep-Proben, nichtatomare Grenzen und 0 Klasse-11-Treffer |
| [wb2a-vitotrol-ram-window-diff-2026-10-11.md](wb2a-vitotrol-ram-window-diff-2026-10-11.md) | Neue 79-Snapshot-Nachbarschaftsanalyse von 0x0B6D, 0x33A3 und DMA0-TX 0x161A; mit Offline-Runner, Sicherheitsgrenzen und synthetischen Regressionstests |
| [wb2a-vitotrol-uart1-p300-sfr-live-2026-10-11.md](wb2a-vitotrol-uart1-p300-sfr-live-2026-10-11.md) | Echte native-P300-Messung von M16C-S1RIC/U1C1/DMA0: RE und IRQ-Priorität wechseln zeitabhängig, 11 FC03-Register-Snapshots, 79 SHA-gepinnte SRAM-Bilder und zwei neue ROM-adressähnliche RX-Nachbarn |
| [wb2a-vitotrol-uart1-firmware-attribution-2026-10-11.md](wb2a-vitotrol-uart1-firmware-attribution-2026-10-11.md) | Wichtiges Beweisgate: 20C2-Profil ist keine MCU-Identifikation; M16C-UART1-Vektor 20 ist auf der lokalen WB2A nicht nachgewiesen, keine ISR-/State-Commit- oder Injektionsfreigabe |
| [wb2a-vitotrol-optolink-emulator-profile-2026-10-10.md](wb2a-vitotrol-optolink-emulator-profile-2026-10-10.md) | Optolink-only Original-V300-Emulatorprofil: 420/448 Original-TX-Frames offline rekonstruierbar, 28 BF15 opaque und RAM-Xref-Audit |
| [wb2a-vitotrol-acceptance-offline-2026-10-10.md](wb2a-vitotrol-acceptance-offline-2026-10-10.md) | Optolink-only Vitotrol-Hardwareabnahme: synthetische BC-/Rollback- und Temperatur-Regressionen, keine Freigabe fuer Live-Controller |
| [wb2a-vitotrol-live-optolink-ram-2026-10-11.md](wb2a-vitotrol-live-optolink-ram-2026-10-11.md) | Reale WB2A-B0:3-/P300-RAM-Tests am 11.10.: festes TX-161A- und RX-1640-Lesefenster mit VS1-Recovery und Grenzen |
| [wb2a-vitotrol-live-paired-2026-10-11.md](wb2a-vitotrol-live-paired-2026-10-11.md) | Kombinierter TX/RX-RAM-Liveleser bei A0:0/B0:0 vs. A0:1/B0:3, BC-Störung und unter Timeout fehlgeschlagener Shadow-Restore mit nachweislich erfolgreicher manueller Wiederherstellung |
| [wb2a-vitotrol-b0-real-canary-2026-10-10.md](wb2a-vitotrol-b0-real-canary-2026-10-10.md) | Echter, begrenzter Optolink-B0:3-Hardwarecanary mit zwei unabhängig bestätigten Rückfallwegen und unveränderter Fernbedienungskennung |
| [wb2a-vitotrol-vitosoft-profile-audit-2026-10-10.md](wb2a-vitotrol-vitosoft-profile-audit-2026-10-10.md) | SHA-gepruefte statische VitoSoft-Auswertung: 581 exakte VDensHO1-Events, 22 RPCs, kein katalogisierter KM-Bus-RX-Inject-Dienst |
| [wb2a-vitotrol-persistent-mqtt-master31-register00-2026-10-11.md](wb2a-vitotrol-persistent-mqtt-master31-register00-2026-10-11.md) | Neuer persistenter Optolink-MQTT-P300-Lesepfad (ca. 232ms/Read), echte CRC-validierte 0x31/00- und B1/00-Folge sowie Metadaten-Transienten 0A04, 0A07, 0A08, ohne Vitotrol-Commit |
| [wb2a-vitotrol-class11-sram-firmware-ownership-gate-2026-10-11.md](wb2a-vitotrol-class11-sram-firmware-ownership-gate-2026-10-11.md) | **Neu:** Alle 79 Voll-RAM-Aufnahmen lueckenlos auf Klasse11-CRC-Telegramme geprueft: 0 Treffer, 79 RX-Klasse01-Positivkontrollen bei 0x1642; 12.926 stabil-hochentropische SRAM-Bytes, aber kein belegter ROM-Code; VDensHO1-RPC- und RX-Consumer-Gate |
| [wb2a-vitotrol-vs1-p300-rom-contrast-live-2026-10-11.md](wb2a-vitotrol-vs1-p300-rom-contrast-live-2026-10-11.md) | Geraete-Livevergleich: 13 VS1- und 20 P300-Reads, getrennte Adressraeume und neue RAM-Byteabweichung |
| [wb2a-vitotrol-200kw2-crossgeneration-compatibility-2026-10-11.md](wb2a-vitotrol-200kw2-crossgeneration-compatibility-2026-10-11.md) | Original KarlKoch 2010 gegen Original-Vitotrol 2018 und WB2A 2026: CRC-/KM-Bus-Kompatibilitaet, aber unbekannter Optolink-ROM-Auslesebefehl |
| [wb2a-vitotrol-200kw2-gwg-issue10-rom-gate-2026-10-12.md](wb2a-vitotrol-200kw2-gwg-issue10-rom-gate-2026-10-12.md) | OpenV-Originalbelege GWG-C7 an 200KW2 (2010), Adressscan ueber 0x8000 leer (2011), wiedergefundenes privates Entwicklerforumzitat, gegen Original-VitoSoft falsifizierte KW2-ROM-Programmierflags |
| [wb2a-v200kw2-legacy-gwg-live-compatibility-2026-10-12.md](wb2a-v200kw2-legacy-gwg-live-compatibility-2026-10-12.md) | **Echte WB2A-Hardwarevalidierung 12.10.:** unveraendertes 200KW2-GWG-C7 liest 20C2-ID, 8-Byte- und verschobenes Adressfenster erfolgreich, CB/C5 an 6F und F8 ohne Antwort, 16/16 read-only-Anfragen mit unabhaengiger Rueckstellung |
| [wb2a-openv-2013-p300-startgate-virtual-overread-2026-10-12.md](wb2a-openv-2013-p300-startgate-virtual-overread-2026-10-12.md) | **P300-Livetest des OpenV-Hinweises von 2013:** 65 SHA-gepinnte FC01-Reads, 9 Error03/01, 20C2-Datenpunkt-Innenbyte 0x088F=26 blockweise lesbar trotz direkter Sperre; kein Programm-ROM-Dump |
| [wb2a-optolink-rom-fc-low5-alias-rx-flag-gates-2026-10-12.md](wb2a-optolink-rom-fc-low5-alias-rx-flag-gates-2026-10-12.md) | **Echte WB2A-Hardwaremessung:** 30 sichere FC03/99- und FC05/101-A/B/B/A-Lesekontrollen, alle fuenf Paare identisch; offline 79 RAM-Abbilder: 0x0B6B kein verlaessliches RX-Ready, 0x166A/B nur ein RX-korrelierter Fall; kein 20-Bit-ROM-Dump |
| [wb2a-gg1-bootloader-gwg-20bit-labor-readiness-2026-10-12.md](wb2a-gg1-bootloader-gwg-20bit-labor-readiness-2026-10-12.md) | GWG-2010-Mask-ROM-Spur und Renesas-Flashboot getrennt: Boot-UART1 vs Optolink-UART0, vollstaendiger Fake-PTY-Bootloader mit zwei korrekten 20-Bit-ROM-Seiten, sichere Nur-Ersatzplatine-Laborgates |
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
| Wo sind die zulässigen Hybridfenster und deren Sperren implementiert? | `tools/optolink-hybrid.py`, `tools/handover_acceleration/` |
| Wie wird einmalig auf den Update-Zweig `main` umgestellt? | `tools/optolink-update-main-umstellen.sh` |
| Wie wird eine neue LXC-Installation aufgebaut? | `install/optolink-splitter-install.sh` |
| Wie sieht die HA-Oberfläche aus? | `config/optolink-splitter/homeassistant-dashboard.yaml` |

## Dokumentationsregel

Dokumentation soll den **aktuellen produktiven Zustand** beschreiben. Hypothesen, nicht verifizierte Register und Reverse-Engineering-Zwischenstände gehören nach `optolink-research`.

Wenn Codeverhalten geändert wird, sollten im selben Änderungssatz mindestens die direkt betroffene Dokumentation und — bei einer wichtigen Invariante — der CI-Guard angepasst werden.


## Architekturdiagramme

- [Systemübersicht](images/optolink-system-overview.svg)
- [Dienstekommunikation und Sicherheitsmodell](images/service-communication-security.svg)
- [Überwachter VS1/P300-Protokollwechsel](images/vs1-p300-wechsel.svg)

Die Root-README rendert beide Diagramme direkt.
