# WB2A/20C2: historische GWG-Read-Typen AE und 6E wirklich getestet

**Messfenster:** 12. Oktober 2026, ca. 11:18:24 bis 11:18:42 CEST. **Priorität bleibt die originale WB2A-Firmware über vorhandenen Optolink auszulesen, nicht die GWG-2053-Datenpunkte zu übernehmen.** Ausschließlich historisch dokumentierte **READ**-Frames, unabhängiger Restore, kein Controller-Write, kein produktiver Patch.

## 1. Quellenfester Originalbeleg der tatsächlich gesendeten Bytes

Die unabhängige OpenV-Implementierung `openv/vcontrold` dokumentiert in [xml/kw/vcontrold.xml](https://github.com/openv/vcontrold/blob/master/xml/kw/vcontrold.xml) innerhalb der GWG-Makros: `GETEADDR = SEND 01 AE`, `GETPADDR = SEND 01 6E`, jeweils `SYNC;GET*ADDR $addr $hexlen 04;RECV $len`.

In [xml/kw/vito.xml](https://github.com/openv/vcontrold/blob/master/xml/kw/vito.xml) gibt es für **Gerätekennung 2053, nicht 20C2** die Zuordnungen:

- `getBrennerStunden1`: `device ID="2053" protocmd="geteaddr"`, `addr=17`, `len=2` → **`01 AE 17 02 04`** (EEPROM-Leseart).
- `getVentilStatus`: `device ID="2053" protocmd="getpaddr"`, `addr=01`, `len=1` → **`01 6E 01 01 04`** (Port-Leseart). Die gleichen Bits der Adresse 01 werden dort auch für 2053-Pumpenstatus verwendet.

Diese Geräteprofilzuordnung beweist **nicht**, dass WB2A 20C2 die gleiche RAM-/Port-/EEPROM-Adressierung verwendet. **Es handelt sich explizit um eine generationsübergreifende Kompatibilitätsprobe.**

## 2. Echte WB2A-20C2-Antworten

| Messung | Tatsächlicher Frame | Vollständige RX nach EOT→ENQ | Bewertung |
|---|---|---|---|
| KW-Baseline | `01 F7 00 F8 04` | `20 C2 00 03` | PASS |
| GWG-C7-Baseline | `01 C7 F8 04 04` | `20 C2 00 03` | PASS |
| GWG-EEPROM-AE #1 | **`01 AE 17 02 04`** | *Keine Datenantwort* | 0/1 |
| GWG-Port-6E #1 | **`01 6E 01 01 04`** | **`00`** | 1/1 |
| GWG-Port-6E #2 | **`01 6E 01 01 04`** | **`00`** | 2/2 |
| GWG-EEPROM-AE #2 | **`01 AE 17 02 04`** | *Keine Datenantwort* | 0/2 |
| GWG-C7-Nachkontrolle | `01 C7 F8 04 04` | `20 C2 00 03` | PASS |
| KW-Nachkontrolle | `01 F7 00 F8 04` | `20 C2 00 03` | PASS |

**Alle acht** EOT-ENQ-Synchronisierungen waren erfolgreich. Die 6E-Datenantwort `00` erschien in beiden Fällen exakt einmal nach dem historischen `0x6E`-Read. Dies beweist, dass **der Read-Kanal nicht generell stumm bleibt**. **Ob `00` einen tatsächlichen physischen Portregisterwert, einen Format-spezifischen Erfolgsstatus oder einen anderen Steuerungswert darstellt, ist noch offen.** Keinen bestimmten WB2A-Pumpen-, Ventil- oder Brennerstatus daraus ableiten.

Die beiden `0xAE`-Timeouts sind ausschließlich negative Nachweise für das **konkrete** `AE/0x17/2`-Fenster, nicht für alle EEPROM-Lesearten und vor allem nicht für Programm-ROM.

## 3. Original-Rohdaten, Nachprüfung und Sicherheitsgrenzen

Der am LXC erzeugte, unveränderte Rohmitschnitt liegt unter:

```text
/tmp/wb2a-gwg-legacy-readtypes-live-20261012.json
SHA256 527ae8454ff00d8517075aa7a13f7d238a111b7c5d0e2f8a6db3050356e65afc
Dateigröße 3263 Bytes, Root-only, 8 vollständige Testrecords
```

`tools/wb2a-gwg-legacy-readtypes-original-audit.py` wurde **mit Root-Zugriff gegen das SHA-gepinnte Original** ausgeführt: `audit=PASS`, `reads=8`, `synchronized_frames=8`, `port_6e_01_hex_replies=["00","00"]`, `eeprom_ae_17_responses=0`, `controller_memory_writes=0`, `program_rom_bytes_read=0`, `physical_port_semantics_proven=false`. Zusätzlich gibt es Positiv- und adversariale Negativtests für ein gefälschtes 6E-Ergebnis, einen gefälschten EEPROM-Read, nicht synchronisierte Frames, unbekannte Schreibtelegramme, beschädigten SHA256-Beleg und abweichende Gerätekennungen.

**Live-Sicherheit:** Nur zwei fremdquellbelegte GWG-Read-Codes plus nachgewiesene KW-/C7-Identitätskontrollen; ein einziges exklusives CP2102-Serial-Handle; 4800/8E2; Timer `wb2a-gwg-legacy-readtypes-restore-20261012.timer` vor dem Stoppen des produktiven Owners für 3 Minuten aktiv; maximal 65 Sekunden Live-Client; EXIT-Restore. Keine Codier-, RAM-, EEPROM-, Flash-, Boot-, KMBus- oder Pumpen-Writes.

**Nachzustand mehrfach live verifiziert:** fünf produktive Services `active`; `read;0x00f8;8=20c2000300000103`; `read;0x5738;1=00`; `read;0x0a5c;4=00000000`; ursprüngliche `settings_ini.py` SHA256 `e9a120ef37fe17236a7505ee713c8dd338d98d5093ed75dfb34629d7e8f5c42d`; unabhängiger Restore-Timer abschließend `inactive`. Kein `main`-Merge, kein Produktiv-Patch.

## 4. Für den 20-Bit-ROM-Zugang relevant?

**Bisher nein.** Der erfolgreiche **C7**-Reader ist ein 8-Bit-`Virtual_READ`-Frontend; die mögliche weitere **6E**-Antwort betrifft historisch einen Port-/I/O-Namensraum, nicht ein 20-Bit-Programm-ROM-Fenster. Ein alter **AE**-EEPROM-Read ist ohnehin kein M16C-Programm-ROM und hat an der getesteten Adresse keine Antwort.

Aus dem [historischen OpenV-KM-Bus-Fund](https://github.com/openv/openv/wiki/KM-Bus) ist weiterhin nur KarlKochs Aussage belegt, er habe ~128 KiB Code einer **anderen** V200KW2/M30612MC über Optolink gewonnen; die originale Folge aus Selektor-/ROM-Fenster-Kommandos fehlt. Für einen echten WB2A-Programmdump muss ein 20-Bit-Adressfenster oder ein kontrollierter ROM-zu-RAM-Monitor **explizit und reproduzierbar nachgewiesen** werden. Ohne solchen Beleg keine ungerichtete Opcode-Suche, kein Boot/Reset, kein unbekannter Write am laufenden Heizgerät.

## 5. Reproduktionsskripte

```bash
cd /home/chatgpt-admin/optolink-vitotrol-rpm-20261010
python3 -m unittest discover -s tests -p 'test_wb2a_gwg_legacy_readtypes.py' -v
python3 -m unittest discover -s tests -p 'test_wb2a_gwg_legacy_readtypes_original_audit.py' -v
sudo python3 tools/wb2a-gwg-legacy-readtypes-original-audit.py
python3 -m unittest discover -s tests -q
```

Der Hardware-Runner `tools/wb2a-gwg-legacy-readtypes-session.sh` verweigert den Neustart wegen bereits existierender Originalausgabedatei; bewusst kein automatischer Wiederholungslauf und kein unbeaufsichtigter Mehrtagestest.
