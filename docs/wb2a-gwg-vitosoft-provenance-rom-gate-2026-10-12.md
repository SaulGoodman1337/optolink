# WB2A/20C2: GWG-Gerätefamilien, Original-Quellenjoin und 20-Bit-ROM-Beweisgrenze

**Mess-/Analysezeit:** 12. Oktober 2026, Fortsetzung nach den zwei vollständig kontrollierten GWG-Livefenstern. **Ziel: einen echten, adressierten Dump des WB2A-Controller-Programm-ROMs über den vorhandenen Optolink-Port gewinnen; erst danach Vitotrol-200/300-UART1/KM-Bus-Parser disassemblieren.**

**Strikte Trennung:** Quellen-Aussage ≠ tatsächlich auf `20C2` gemessene Fähigkeit ≠ Hypothese. Die neue Etappe selbst ist **ausschließlich Offline-Quellenvergleich und Git-Integrationsplanung**, keine zusätzlichen Optolink-, Brenner-, Pumpen- oder Hardwaretests. Die historischen zwei lesenden Sitzungen bleiben in separaten SHA-gepinnten Originalmitschnitten.

## 1. Neues Gerätedetektions-Gate

Die vorhandenen [InsideViessmannVitosoft-Kommunikationsnotizen](https://github.com/sarnau/InsideViessmannVitosoft/blob/master/VitosoftCommunication.md) (lokal `/home/chatgpt-admin/research/InsideViessmannVitosoft/VitosoftCommunication.md`) beschreiben für die **alte GWG-Geräteerkennung** die Antwortpräfixe `20 53` und `20 54` nach einer `C7/F8/4`-Identitätslesung. **Quellenrang:** öffentliches **Drittanbieter-Reverse-Engineering**, kein authentifizierter Original-Viessmann-Firmwarequelltext und kein vollständiger Beweis, welche Funktionen die 20C2-Controller-Firmware intern implementiert.

Die originale auf dieser WB2A mehrfach gemessene `C7/F8/4`-Antwort lautet dagegen `20 C2 00 03`, also `0x20C2` und **nicht `0x2053` oder `0x2054`**. Daraus folgt ein **klares Negativ** nur für diese konkret dokumentierte *GWG-Geräteerkennungsbedingung*. Es wäre falsch, daraus zu folgern, dass die neuen C7-/6E-Leseantworten „unmöglich“ oder dass alle historischen GWG-Speicherfunktionen implementiert seien.

### Zweite unabhängige Quelle: echter VitoSoft-Host-Datenpunktkatalog

Im lokalen Originalexport `DPDefinitions.xml` (**186.559.004 Bytes, SHA256 `efec27568d398021c767771af016143bd51fc196d2d408dbb80faff84d0b19e3`**) stehen **399 getrennte `ecnDatapointType`-Profile**:

| Katalogprofil | Numerische Host-Typ-ID | Aussage |
|---|---:|---|
| `VDensHO1` (WB2A 20C2) | **60** | Exakte für unsere WB2A früher mit 581 Eventlinks geprüfte Familie |
| `VDensHO1_4` | 208 | Weitere, separat benannte VDensHO1-Variante |
| `GWG_VBEM_00` | **76** | Explizite ältere GWG-VBEM-Familie |
| `HV_GWG` | 148 | Weitere separat benannte GWG-Familie |

Zusätzlich enthält der Katalog **21 mit `GWG_` beginnende Hostprofile**, darunter fünf `GWG_VBEM_*`-Varianten (`00,03,21,35,36`). Ein Gleichsetzen von `GWG_VBEM_00` mit der numerischen historischen `vcontrold`-Gerätekennung `2053` ist **durch diese Tabellen noch nicht bewiesen**. Alle Angaben betreffen **Host-Konfiguration**, nicht direkt ausführbare MCU-Firmware oder ein auslesbares Codeabbild.

Offline-Nachweis: `tools/wb2a-gwg-vitosoft-device-family-offline.py` öffnet die private 186-MB-XML nur read-only per memory-map, prüft vollständige Original-SHA256 und identifiziert alle 399 `ecnDatapointType`-Zeilen. Keine XML-Originaldaten oder Programm-Firmware auf GitHub veröffentlichen.

## 2. Dreistufiger Quellenjoin: OpenV-Frame, 2053-Bindung, 20C2-Liveantwort

| Typ und Adresse | Historische OpenV-Quelle | Reale Antwort **WB2A 20C2** | Was ist gesichert? |
|---|---|---|---|
| `C7/F8/4` | OpenV `VIRTUAL READ`, 8-Bit-Adresse | `20C20003` | **KW/GWG-Dispatcher-Interoperabilität**, aber nicht nativer 2053-GWG-Typ |
| `C7/F8/8` | OpenV gleiches Typbyte mit Länge 8 | `20C2000300000103` | 8-Byte-GWG-Virtual-Read |
| `C7/F9/3` | 8-Bit-Verschiebung des Virtual-Read-Fensters | `C20003` | Adressüberlappung im getesteten Fenster |
| `6E/01/1` | OpenV `PHYSICAL PORT READ`; `vcontrold` `getVentilStatus` für **2053** | Zweimal `00` | **Reproduzierbare Datenantwort**, WB2A-SFR-/Portsemantik **nicht** belegt |
| `AE/17/2` | OpenV `EEPROM READ`; `vcontrold` `getBrennerStunden1` für **2053** | Zweimal **keine Nutzantwort** | Nur genau **dieses** 2053-EEPROM-Fenster an 20C2 negativ |
| `CB/6F/1`, `C5/6F/1` | Historische physische/physische-XRAM-Modi | Frühere Sitzungen ohne Antwort | Adressabhängige Negativproben, keine globale Opcode-Aussage |

Die originale `vcontrold`-Konfiguration ([`xml/kw/vcontrold.xml`](https://github.com/openv/vcontrold/blob/8ca47972c9ac5b0a14a7a36393b0dbfdb165f918/xml/kw/vcontrold.xml)) codiert `GETVADDR=01 C7`, `GETEADDR=01 AE`, `GETPADDR=01 6E`. Ihre originalen [Gerätebindungen](https://github.com/openv/vcontrold/blob/8ca47972c9ac5b0a14a7a36393b0dbfdb165f918/xml/kw/vito.xml) geben `2053/AE/17/2` und `2053/6E/01/1` vor. Damit ist der TX-Vergleich an 20C2 quellgebunden, **ohne** dessen Registersemantik oder die Kompatibilität aller alten Modi zu erfinden.

### Unveränderte Originale (privat auf LXC)

| Rohmitschnitt | SHA256 | Unabhängiges Audit |
|---|---|---|
| `/tmp/wb2a-gwg-c7-dispatcher-live-20261012.json` | `ee38ef08f950c999ed19da9630e789cc69b1f61642b932be5dca3101a163b824` | `7/7` echte Requests, 7 ENQ, 14 TX-Frames, 41 Raw-Events, keine Controller-Writes |
| `/tmp/wb2a-gwg-legacy-readtypes-live-20261012.json` | `527ae8454ff00d8517075aa7a13f7d238a111b7c5d0e2f8a6db3050356e65afc` | `8/8` EOT/ENQ, 6E=00 zweimal, AE-Timeout zweimal, beide KW/C7-Identitätsnachkontrollen erfolgreich |

Der neue quervergleichende `tools/wb2a-gwg-source-and-rom-boundary-audit.py` lädt **beide tatsächlich SHA-verifizierten Root-Captures über die bereits getesteten Original-Auditoren** und die folgenden **vier** genau geprüften Quellen:

| Quelle | SHA256 |
|---|---|
| `openv.wiki/Protokoll-GWG.md` | `6767a5fc30db44ac89ca9e9e4d27d64f5f64091ddd0419b39586a493155af82c` |
| `vcontrold/xml/kw/vito.xml` | `8b30d5060dfbea75e986a3199b986f54b092b6b13e286e6e7ef797608026531e` |
| `vcontrold/xml/kw/vcontrold.xml` | `9a6768dea265f5a88daca67cdcbc727f971e2b1d8786bef3c548edb483c5b139` |
| `InsideViessmannVitosoft/VitosoftCommunication.md` (Community RE) | `19fc2189e1392aa11ba986ee063c2d288e4197637f56083012a702c913881371` |

**Laufresultat:** `audit=PASS`, `observed_controller_id=20c2`, `legacy_gwg_detector_matches_20c2=false`, `gwg_c7_confirmed=true`, `gwg_physical_port_6e_01_response=00`, `gwg_eeprom_ae_17_response_count=0`, `native_gwg_stack_implementation_proven=false`, `program_rom_bytes_read=0`.

## 3. Firmware-Adressraum: Was die Quellen NICHT leisten

- Historisches GWG-Telegramm: `01 TYPE ADDR8 LEN8 04`; **kein 20-Bit-Adressfeld**. Separate Typbytes `C7/AE/6E/9E/...` wählen historische Speicherkategorien, kein dokumentierter höherer Programm-ROM-Bankindex.
- VS1 `F7` sendet **16-Bit-Adresse**; unser P300-Host packt ebenfalls zwei Adressbytes. Frühere Tests zeigten hohe Adressbits beim normalen `FC03(0xF0000)` abgeschnitten, weil auf Draht `0x0000` ankommt.
- Die vorher auf dem Controller gemessenen 20-Bit-DMA-Register beweisen **internes M16C-Adressierungsvermögen** und aktive UART-Zuweisungen, aber keinen für Optolink autorisierten frei steuerbaren **ROM-zu-RAM-Kopierer**.
- Das ältere OpenV-Wiki berichtet, KarlKoch habe ca. **128 KiB M30612MC-Code einer anderen Vitotronic 200 KW2** über Optolink gewonnen. Es liefert **keine Original-Transferbytes, keinen Monitorzugang und kein erhaltenes Firmware-Abbild**. Daraus lässt sich keine sichere WB2A-Requestsequenz ableiten.
- Renesas-M16C-Familienhandbücher zeigen generell Programm-ROM am oberen Ende des 20-Bit-Bereichs und feste Vektoren nahe `0xFFFFF`; z. B. [M16C/28 Hardware Manual](https://www.renesas.cn/zh/document/mah/m16c28-group-m16c28-m16c28b-hardware-manual). **Die M16C-Variante des konkreten WB2A-Reglers ist dadurch nicht identifiziert**; benachbarte M16C-Speicherpläne dürfen nicht blind auf 20C2 angewandt werden.

**Neues Akzeptanzgate:** „ROM-Dump“ darf nur geschrieben werden, wenn ein echter Controllerantwort-Trace die vollen effektiven oberen Adressbits oder einen quellenbelegten expliziten Kopier-/Monitordienst trägt, zwei voneinander unabhängige Leseproben identische Bytes liefern und M16C-Code-/Vektorplausibilität überprüfbar ist. `6E 00`, `C7 20C2` und `AE`-Timeouts erfüllen dieses Gate **nicht**.

## 4. Git: Transfer zum dauerhaften `optolink-research` vorbereiten, noch NICHT vollziehen

Die zwei Branches haben derzeit **keine lineare Übernahmebeziehung**: bei der hier gemessenen Basis `optolink-research = 8e31334`, Forschungs-Feature `e3e92cc`, von ihrer gemeinsamen Basis aus **3 ausschließlich im Research-Branch** und **285 ausschließlich im Feature-Branch** enthaltene Commits. Die Features enthalten auch andere produktionsbezogene Arbeiten und dürfen **nicht komplett** in den research-Branch gemergt werden.

`tools/wb2a-research-branch-transfer-preview.py` ist ein **Git-read-only**-Dry-Run. Er klassifiziert gezielt GWG-/ROM-Dokumentation, Simulatoren, Audits und Tests anhand der Branch-Trees und SHA256-Inhalte als `NEW_IN_RESEARCH`, `IDENTICAL`, `REVIEW_REPLACEMENT` oder `CONFLICT_BOTH_SIDES_CHANGED`. Der erste bereits ausgeführte Stand enthielt **43** GWG-/ROM-Dateien, alle `NEW_IN_RESEARCH` und 0 Dateipfadkonflikte. Die jetzigen neuen Artefakte werden erst nach Commit im folgenden Dry-Run mitgezählt. Diese Einstufung ist **keine Dependency-, Build- oder Merge-Freigabe**.

`docs/README.md` wird absichtlich **nicht blind kopiert**, weil jeder Branch einen eigenen Dokumentationsindex hat. RAW-Hardware-Captures, Host-XML und private Dump-Dateien werden ausdrücklich **nicht** in die Git-Historie übernommen.

Wenn die Forschung inhaltlich abgeschlossen ist: aktuellen Preview gegen `origin/optolink-research` wiederholen, Dateiliste auf abhängige Tests/Module prüfen, nur selektierte Beleg-/Test-/Werkzeugdateien kontrolliert auf **einem neuen temporären Integrationsbranch auf Basis von `optolink-research`** einspielen, dort die passende Offline-Testsuite starten und den Research-Dokumentationsindex gezielt ergänzen. Erst nach dieser Abnahme in `optolink-research` übernehmen. **Kein Merge oder Push nach `optolink-research` in dieser Phase.**

## 5. Reproduzieren

```bash
cd /home/chatgpt-admin/optolink-vitotrol-rpm-20261010

# Nur offline: SHA-gepinnte Hostprofil-Familien
python3 tools/wb2a-gwg-vitosoft-device-family-offline.py \
  --out /tmp/wb2a-gwg-vitosoft-family-contrast-20261012.json

# Unveränderte 20C2-Originalcaptures, vier historische Quellartefakte
sudo python3 tools/wb2a-gwg-source-and-rom-boundary-audit.py \
  --out /tmp/wb2a-gwg-source-rom-boundary-20261012.json

# Neue gezielte Mutationstests (CI ohne private Originale mit synthetischen Fixtures)
python3 -m unittest discover -s tests -p 'test_wb2a_gwg_source_and_rom_boundary_audit.py' -v
python3 -m unittest discover -s tests -p 'test_wb2a_gwg_vitosoft_device_family_offline.py' -v
python3 -m unittest discover -s tests -p 'test_wb2a_research_branch_transfer_preview.py' -v

# Nur Git-Inspektion, kein Merge:
python3 tools/wb2a-research-branch-transfer-preview.py \
  --out /tmp/wb2a-gwg-rom-research-branch-preview-20261012.json

# Vollständige Regression
python3 -m unittest discover -s tests -q
```

**Harter Forschungsstatus:** GWG-Leseinteroperabilität und zwei historische Legacy-Lesetypen punktuell experimentell eingegrenzt. **Keine Original-WB2A-Programm-ROM-Bytes, keine 20-Bit-Optolink-Abfrage, keine neue Vitotrol-Anmeldung und keine produktive Anwendung installiert.** Weitere Hardware-Opcodeversuche erst auf Basis eines **konkreten neuen Originaltraces oder ROM-Monitor-/Bankdienstbelegs**, nicht als Suche mit beliebigen möglichen CPU-Register-Leseadressen.
