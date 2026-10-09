# WB2A 20C2/0103: Ergebnis des P06-geklammerten 20-KiB-Voll-RAM-Loggers (9.10.2026)

**Nur Aufgabe 1: vollstaendige P300/VS1-Funktionsparitaet und echte GFA-P06-Istdrehzahl.**
**PR #46 bleibt Draft. Kein Merge, keine Produktionsaenderung, keine Vitotrol-/Pumpenarbeiten.**

## Archiv, Lauf und Integritaet

- Private Messdatei: p300-fullram-run-20261009T083607Z-144293-bundle.tar.gz
- SHA256: 94d5842b6dc5759ecb446a4c617b60b72873b639885d116032f783abdef8431c
- Wirksam ausgefuehrter Forschungsstand: 6ae32a9fd458767e753d99f02dfec933af36db0f (aus Session-State und gepinnten Quellhashes).
- Messzeit: 2026-10-09 08:36:08 bis 11:26:09 UTC (knapp 2 h 50 min). **Vorzeitig wegen VS1-Identitaets-Timeout**, nicht wegen fehlgeschlagener FC03-RAM-Blocks.
- In einem unabhaengigen Offline-Audit aller Bytes: **176/176 Manifest-Dateien** in Laenge und SHA256 korrekt; 177 Tar-Mitglieder inklusive Manifest, insgesamt 55.314.932 Bytes dekomprimiert.
- **51.200/51.200** FC03-Leseantworten fuer 640 eindeutige physische RAM-Blockadressen (0x0400..0x53FF / 32), inklusive TX/RX-Frame, ACK, FC, Adresse, Payload, Laenge, Checksumme und Adressreihenfolge validiert.
- **1.600/1.600** FC01 0x55D3/11-Statuscheckpoints korrekt (20 pro Sweep).
- 175.101 TX/RX-Rohtrace-Eintraege; keine unerkannten TX-Kommandos oder Gerätewrites.
- Durchschnitt VS1→P300 **2,165 s**, erfolgreicher P300→VS1 **4,327 s**. Median der 640-Block-Scanzeit **107,679 s** (107,218..109,595 s). Keine atomaren RAM-Momentaufnahmen.

## Snapshot-Qualitaet

| Kategorie | Anzahl |
|---|---:|
| COMPLETE: stabiler P06=0-AUS-Zustand | **48** |
| COMPLETE: stabiler positiver P06-Zustand | **11** |
| COMPLETE: Transition/Unbekannt | **20** |
| PARTIAL: fehlender P06-Nachherbeleg | **1** |
| Gesamt | **80** |

**Snapshot 80 ist kein unvollstaendiger RAM-Lesevorgang:** Alle 640 Blöcke, 20 Statusreadbacks und 20.480 RAM-Bytes sind vorhanden. Der darauf folgende Rueckwechsel nach VS1 schlug fehl und es gibt deshalb keine qualitaetsgepruefte P06-Nachreferenz. Die Datei s00080.partial.bin ist in **absteigender Roh-Scanreihenfolge** gespeichert, nicht in kanonischer Adressfolge. Sie darf nicht als normaler COMPLETE-Dump gelesen werden.

## Physische P06-Referenzen

VS1/GFA lieferte **3.532 P06-Einzelwerte**, davon **3.527 gueltig**, **5-mal FF ungueltig**; unter den gueltigen **2.488 P06=00** und **1.039 P06>00**. In den VS1-Referenzphasen wurden 35 positive Drehzahlniveaus bis **4.440 U/min** gesehen.

**Alle elf stabilen positiven 20-KiB-Snapshots beziehen sich jedoch ausschliesslich auf P06=0x53, also 2.490 U/min.** Betroffene IDs: 7, 21, 22, 35, 36, 49, 50, 51, 64, 65 und 78. Es gibt keinen zweiten stabilen positiven *RAM-geklammerten* RPM-Level. Die hoeheren Werte liegen nur in dynamischen VS1-Phasen.

Die 1.600 nativen FC01-Statusframes enthalten 464 gesetzte Flame-Bits, 11 beobachtete Flame-Bit-Kanten (6 EIN, 5 AUS), fuenf beobachtete vollständige EIN/AUS-Zeitfenster und keine gesetzten Lockout-Bits.

## Vollstaendiger 20-KiB-Abgleich gegen P06

Jede der 20.480 Byteadressen wurde in den 48 stabilen AUS- und elf stabilen EIN-Snapshots verglichen. Auch feste Rohbyte-, Integer-16/32-Bit-Little/Big-Endian-, skalierte und einfache BCD-Darstellungen wurden gescreent:

- **Kein** Byte bleibt durchgehend 00 bei AUS und 53 bei EIN: **0 direkte P06-Rohbyte-Spiegel**.
- **Keine** durchgehend passende 0→2490-U/min-16/32-Bit-Adresse in Little-/Big-Endian.
- **30** physische Byteadressen wechseln durchgehend von Null zu einem jeweils festen, anderen Nichtnullwert; insgesamt **34** dauerhaft korrelierende Zweizustandsbytes. Perfekte Korrelation ist **kein** Tachonachweis.
- Hervorzuheben sind **0x0F20 und 0x1C76**, beide ueber alle stabilen Scans **00 bei AUS / 54 bei EIN**. Der Wert 0x54 ist **nicht** P06=0x53. Eine 0-im-Stillstand/sonst-P06+1-Hypothese waere zwar denkbar, hat aber **keinen** Beweis bei einer zweiten stabilen Drehzahl. Diese Adressen koennen ebenso Betriebszustand oder ein Steuerwert sein.
- **0x0F29** korreliert nicht nur: in allen stabilen Scans entspricht es genau **FC01 0x55D3 Byte 7** (00 / 62). Das ist ein direkter Warnfall einer nur statusbezogenen Spiegelung.
- Die bekannten Optolink-eigenen Kommunikationsbereiche 0x192C..0x1952 und 0x196C..0x1A6D sowie UART1-KM-Bus-TX, GFA P09 und native FC01-Byte0/Byte9 sind **keine** unabhaengig nachgewiesene P06-Sensorquelle.

**Schlussfolgerung:** Ein einfacher direkter echter P06-RAM-Spiegel ist im vollstaendig gelesenen 20-KiB-Bereich **nicht nachgewiesen**. Ob eine indirekte bzw. anders skalierte Sensorquelle existiert, ist durch den fehlenden zweiten stabilen positiven RPM-Level noch nicht entschieden. Keine Freigabe eines Kandidaten als P06.

## Timeout und Recovery – voneinander getrennte Befunde

- Letzte FC03-Antwort 0x0400/32 fuer Snapshot 80 erfolgreich, danach letzter FC01-Status erfolgreich.
- Rueckwechsel P300→VS1 ab **11:25:59.828 UTC**; EOT-TX 04, im Rohtrace RX 060505, darauf VS1-Identitaetsanfrage TX 01f700f802; **keine Identitaetsantwort innerhalb der Frist**.
- Switch-Fehler nach 6,237 s: receive deadline exceeded / identity_verified=false. Nicht als guten P06-Nachherwert klassifiziert.
- Der unmittelbar anschliessende *neue, explizite* Recovery-Handshake erhaelt **20c2 / 0103, GFA P80=20 und P06=53** und bestaetigt VS1. Eine physikalische Ursache fuer den einen Timeout ist nicht gesichert.
- Systemd ExecStopPost: **6/6 vorher aktive Dienste/Timer wiederhergestellt**, keine Recovery-Fehler, Hauptsplitter zuerst. Produktive MQTT-GFA P80=20 und P06=53 nicht-FF geprueft. **HA-Entity-Frische nicht verifiziert.**

## Konkrete naechste Aufgabe-1-Entscheidung

**Nicht erneut einen identischen 640-Block-Logger starten.** Als naechstes gezielte *kurze, read-only* P300-Fokusfenster unter echten VS1-P06-Referenzklammern untersuchen, bewusst waehrend hoehere Drehzahlen als 2.490 U/min beobachtet werden: 0x0F20 und 0x1C76 samt Umfeld, plus FC01-Status und VS1-P09 separat. Fuer einen Istwert sind mindestens zwei positive stabile RPM-Niveaus, richtige Skalierung, Aenderungsdynamik und Unabhaengigkeit von eigenem Optolink-/Statuspuffer erforderlich. Den P300→VS1-Identitaets-Timeout im separaten Safe-Recovery-Test abfangen; keine Writes und keine ungeprueften Adressen.

Falls auch die Fokustests **keinen unabhängigen echten P06-Sensor** belegen, folgt eine **gemeinsame serielle Owner-Architektur: P300 als Hauptprotokoll, periodisch echte VS1-GFA-P06-Lesephasen**. Bereits gemessene ca. 6,49 s Hin-/Rueckwechsel allein sind als Latenz und HA-/MQTT-Frischeverlust im Funktionsparitaetsnachweis zu beruecksichtigen.

**Kein P09-/55D3-Sollwert-Ersatz fuer die tatsaechliche Drehzahl. Keine Produktionsfreigabe.**
