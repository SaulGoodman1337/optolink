# WB2A/20C2: Reale P300-Nachneustart-SRAM-Differenzen – 3-Byte-Takt, 24-Bit-Pointer-Falsifikation und Originalkontrollen

**12.10.2026 – Fortsetzung nach dem realen, erfolgreich auf VS1 zurückgestellten Fünf-Fenster-Test.** Primärziel bleibt ein **echter WB2A-Hauptprogramm-ROM-Dump nur via Optolink**. Dieser Forschungsabschnitt ist **ausschließlich offline**; er liefert eine neue Analyse der bereits live gelesenen SRAM-Bytes und keine neuen Kommandos an den Heizungscontroller.

## 1. Durchgängig originalbelegte Datenquellen

Das neue Skript `tools/wb2a-postrestart-bitplane-and-triplets-offline.py` kombiniert **fünf unabhängige Originalprüfungen** und lehnt bei einer abweichenden Quelle die Analyse ab:

1. **09.10.**: Original-Tarball mit **79 je per Manifest/SHA geprüften, nicht-atomaren P300-FC03-Voll-SRAM-Bildern** à 20.480 Bytes, SHA256 `94d5842b6dc5759ecb446a4c617b60b72873b639885d116032f783abdef8431c`.
2. **11.10.**: Originale `rom-contrast`-, `dual-readonly`- und `dual-high`-Sitzungen, SHA `f5a31879fedf8c0af780f020c29e50c47cb7727c15e6305c955e6ae8f05935d1`, `e12a10b500cedbc41cc76e8b54ccba78eecc708c9c71f2e14075a25098bf393e`, `c2896229323eba347620b225ac36263a04ac9b59f9e56d94589e68a6a72d7116`. Per ursprünglichem Auditor **vier** echte, voneinander getrennte P300-Leseproben des A-Ziels und seines mutmaßlichen Zeigers, verglichen mit 09.10.
3. **12.10., 21:30 Uhr CEST**: Originalaufzeichnung der realen, fünfmal je Runde geprüften Low-SRAM-Fenster mit **19 echten, ausschließlich lesenden Controller-Anfragen**, SHA256 `ed290530bdd718dd044bd57b07d94c160fb15728a74f3486872cd12fcaa64549`; zwei neue 32-Byte-Leseproben bei `0x3300` und zweimal `0x1DE0`.
4. **12.10.**: **Vier** SHA256-gebundene Originalaufnahmen des kompletten VS1-Fehlerarchivs vor und nach dem P300-Versuch. Baseline `316caaebf012431b7c7089a897b002d1c3976c276c080b4a748a6e00b04ee2b1`; Nachprüfung 0 `3ca5fb5e192d57687179bedb7907ca6871ff8a54836a5b88ec5851b3c4d9012f`; +5 min `6ae0dd86551c5652c15cc1bc429c2d3facd4a2b5f6a2bc0d69b9399bc0602dcf`; +etwa 20 min `c72672e4f1835bb90f011f62a0404fd84849b2039bf053f3cb143f66874234f0`. **Alle vier Originalquellen wurden mit dem früher getesteten Fault-Gate überprüft**, nicht nur ihre SHA-Werte.
5. **VitoSoft-OEM-Katalog**: `DPDefinitions.xml`, `ecnEventType.xml` und tatsächliche `VDensHO1`-Profil/Event-Verknüpfungen aus dem bereits SHA-geprüften, privat archivierten VitoSoft-Installer, **nicht** der WB2A-MCU-Firmware.

Auch der neue Ausgabereport bleibt privat unter `/tmp/wb2a-postrestart-bitplane-and-triplets-audit-with-oem-20261012.json` (SHA256 `2805a109250da626a76c8cabf4036e3c9e0f274ab4eae1a4c9fa2582e45b72f2`). Git erhält **keine Roh-RAM-Dumps** und keine heruntergeladene OEM-Binärdatei.

## 2. Erstes neues Finding: zehn 3-Byte-Wörter statt einer homogenen 29-Byte-Kopie

Die alten **79 Originalimages vom 09.10.** und **vier echten P300-Abfragen vom 11.10.** stimmen für den vollständigen Zielbereich `0x3301..0x331D` überein. Nach dem zwischenzeitlichen Neustart sind die **zwei neuen Antworten vom 12.10.** intern wieder bytegleich, besitzen aber **sieben veränderte Bytes**. Der Blick auf `0x3301..0x331E` (ein **30-Byte-Fenster**, vollständig innerhalb eines einzigen neuen 32-Byte-FC03-Reads) ergibt:

| Adresse | Byte-Offset ab 0x3301 | XOR Alt/Neu | Gekippte Bits | 3-Byte-Feld |
|---|---:|---:|---:|---|
| `0x3305` | 4 | `80` | 1 | Wort 1, Byte 1 |
| `0x3307` | 6 | `10` | 1 | Wort 2, Byte 0 |
| `0x330A` | 9 | `40` | 1 | Wort 3, Byte 0 |
| `0x330D` | 12 | `40` | 1 | Wort 4, Byte 0 |
| `0x3316` | 21 | `80` | 1 | Wort 7, Byte 0 |
| `0x3319` | 24 | `80` | 1 | Wort 8, Byte 0 |
| `0x331C` | 27 | `24` | 2 | Wort 9, Byte 0 |

Damit: **7/30 Bytes ändern sich, aber nur 8/240 einzelne Bits**. Alle anderen 23 Bytes sind zwischen altem und neuem 30-Byte-Block identisch. Noch aussagekräftiger: Unter einer rein **hypothetischen** Gliederung in **zehn Little-Endian-Wörter zu je drei Bytes** ändern sich **sieben Wörter mit je einem geänderten Byte**; **alle zehn dritten Bytes** bleiben identisch. **Sechs von sieben** Änderungen befinden sich in der **ersten Position** dieser 3-Byte-Wörter, die siebte in der zweiten Position eines Wortes.

Die ursprüngliche hypothetische ROM-Kopierlänge des A-Tupels beträgt **29 Bytes**, während das beobachtete lückenlose 3-Byte-Raster **30 Bytes** benötigt. Der 29-Byte-Bereich würde das **letzte 3-Byte-Wort um genau ein Byte abschneiden** (Ende `0x331D` statt `0x331E`). Dies schwächt die einfache Deutung „A-Tupel beschreibt exakt die vollständige 3-Byte-Tabelle“, widerlegt aber keinen anderen möglichen Kopiermechanismus.

Ein **strukturiertes Array von 24-Bit-Feldern** ist damit eine ernsthafte Forschungsinterpretation. Die Tests beweisen **keine** tatsächliche Record-Grenze oder Datentyp-ID. Ein einmaliger Bytevergleich kann weder 24-Bit-Zähler, Bitfelder, Statusdaten, feste Tabellen mit einzelnen Laufzeitänderungen noch RAM-basierte Software-Daten unterscheiden. Der ehemalige „A-Pointer“ `0x1DE5` bleibt seit dem 09.10. unverändert; es wurde **nie** ein Quellbyte aus dem hypothetischen Flash `0xEA2AB` gelesen.

## 3. Drei statistische Gegenproben und die Grenzen ihrer Aussagekraft

| Kontrolle | Tatsächlicher geprüfter Befund | Interpretation |
|---|---|---|
| Exakte Positionswahl bei festem Abstand 3 | Unter sieben ohne Zurücklegen gleichverteilt auf 30 Positionen gewählten Änderungen ist die beobachtete Konzentration **mindestens 6 in derselben 3er-Positionsklasse** in **0,006366** der möglichen Kombinationen enthalten. | **Nur deskriptiv:** 3-Byte-Raster und Zielbereich wurden erst *nach* Einsicht in das Ergebnis betrachtet. |
| **100.000 reproduzierbare** Permutationen mit Seed `20261012` | Der tatsächlich benutzte Test scannt **alle Phasen für Perioden 2 bis 8**, nicht nur das vorteilhaft erscheinende 3-Byte-Raster. **2.593/100.000** zufällige Permutationen sind mindestens so extrem. Mit +1-Korrektur: **0,0259397**. | Mehrfachsuche nach verschiedenen Rastern wurde erfasst. Weiterhin **kein formaler p-Wert**, da bereits die Wahl dieses SRAM-Fensters post hoc erfolgte. |
| Echte historische natürliche SRAM-Änderungen | **78** aufeinanderfolgende alte Imagepaare → **1.595.178** überlappende 30-Byte-Fenster. Davon hatten **10.072** genau sieben geänderte Bytes; **0** davon zeigten mindestens sechs Änderungen in derselben modulo-3-Klasse. | Das Muster ist in dieser historischen **Zeit- und Betriebsbedingung** nicht zu finden. Fenster überlappen und sind hochkorreliert; die 79 Langzeitaufnahmen sind keine unabhängigen RAM-Neustartkontrollen. |

Die drei Belege sprechen konsistent für **nicht-beliebig angeordnete Byteänderungen**. Sie erlauben **keine** Behauptung, eine ROM-Kopierfunktion gefunden zu haben. Insbesondere sind echte natürlichen Flammenwechsel bei der alten Messung enthalten, aber **kein unabhängig isolierter Boot-/ROM-Kopiertrigger**.

## 4. Warum diese 3-Byte-Wörter **keine nachgewiesenen 20-Bit-Firmware-Zeiger** sind

Ein normales M16C-20-Bit-Adressfeld `0x00000..0xFFFFF` passt in drei Little-Endian-Bytes, aber seine **obersten vier Bits müssen Null sein**.

Wenn man die zehn hypothetischen 3-Byte-Wörter schlicht als little-endian unsigned pointer interpretiert, ist **nur eines von zehn** überhaupt ein gültiger 20-Bit-Zahlenwert, und **keines von zehn** verweist in den betrachteten ROM-Bereich `0xC0000..0xFFFFF`. Das gilt für beide neu aufgenommenen Zyklen und den unveränderten historischen Vergleichsbereich. Die einzelnen 24-Bit-Wortwerte werden aus Datenschutz-/Rohdaten-Provenienzgründen nicht in Git gedruckt.

**Grenze des Negativbelegs:** Es könnte sich um kodierte/markierte 20-Bit-Adressen, gemischte Datensätze, Befehlsbits oder gar nicht um Pointer handeln. Aus den konkreten unmaskierten Bytes ergibt sich jedoch **kein direkt nutzbarer ROM-Zeigerarray-Dump**. Der Unterschied eines kopierten *statischen* ROM-Blocks von acht Bits ohne nachgewiesenen Controller-ROM-Update ist mit einer **nachträglichen RAM-Mutation** vereinbar, aber nicht der Beweis eines initialen Boot-Copy.

## 5. OEM-Geräteprofil: Numerische Adressüberschneidung – **nicht** vorschnell Speicherbereiche gleichsetzen

Eine vollständige Hostkatalogprüfung der echten `VDensHO1`-Zuordnungen entdeckte **sieben `Virtual_READ`-Datenpunkte** mit **numerischen Adressen nahe `0x3301`**:

| Echte VS1-/P300-Virtual_READ-Adresse im OEM-Host | Host-Datenpunkt | Blocklänge |
|---|---|---:|
| `0x3302` | `BedienSparbetriebM2` | 1 |
| `0x3303` | `BedienPartybetriebM2` | 1 |
| `0x3306` | `BedienRTSolltemperaturM2` | 1 |
| `0x3307` | `BedienRTSolltemperaturReduziertM2` | 1 |
| `0x3308` | `BedienRTSoll_PartyM2` | 1 |
| `0x3309` | `FerienBeginnM2` | 8 |
| `0x3311` | `FerienEndeM2` | 8 |

**Wichtig:** Das sind **logische Virtual_READ-Adressen aus dem PC-Datenpunktkatalog**, nicht automatisch die **physischen Low-SRAM-Adressen**, die der echte P300-`FC03 Physical_READ` gelesen hat. Der Originalkatalog belegt **keine Gleichheit dieser Adressdomänen**. Die numerische Überschneidung darf **nicht** als Beweis einer heizkreisbezogenen RAM-Struktur gewertet werden; erst ein unabhängig verifizierter Abgleich tatsächlicher VS1-Virtual- und P300-Physical-Antworten könnte diese Hypothese testen. Für den jetzigen Offline-Schritt wurde **kein neuer Heizungsbefehl** gesendet.

Die Identifizierung dieser sieben OEM-Namen ist nützlich, weil sie verhindert, dass wir einen ähnlich benannten Heizungsparameter, einen GFA-Schattenwert oder eine beliebige 24-Bit-Zahl irrtümlich als Firmware-ROM-Adresse deklarieren.

## 6. Sicherheitsabnahme und Fortsetzung

Die vorigen realen Hardware-Lesezugriffe haben laut vollständig verifizierter Original-Fehlerhistorie zu drei Nachkontrollpunkten **keine neu erfasste Störung** verursacht:

| Vollständiges Archiv ab Baseline | Abstand zur Baseline | Original-Fault-Gate |
|---|---:|---|
| Sofort-Nachkontrolle | 334,390 Sekunden | `NO_CHANGE_OBSERVED` |
| +5-Minuten-Nachkontrolle | 602,482 Sekunden | `NO_CHANGE_OBSERVED` |
| Nachkontrolle bei ca. T+20 | 1.443,026 Sekunden | `NO_CHANGE_OBSERVED` |

**Die etwa 75-minütige Langzeitbeobachtung ist zu diesem Zeitpunkt noch offen.** C5 und F9 waren früher real; sie werden dadurch weder rückwirkend als ursächlich für die früheren Versuche noch als ausgeschlossen bewertet. Nach der früheren Session befinden sich das System wieder auf **VS1**, der ursprüngliche Konfigurations-SHA wurde bestätigt und fünf produktive Dienste liefen. Diese Offline-Runde hat **0** zusätzliche Controllerzugriffe und **0** Schreibbefehle verursacht.

**Reproduzierbarkeit:**

```bash
cd /home/chatgpt-admin/optolink-wb2a-research-20261010

# Nur private Originaldateien, keinerlei I/O an der Heizung:
sudo -n python3 tools/wb2a-postrestart-bitplane-and-triplets-offline.py \
  --out /tmp/wb2a-postrestart-bitplane-and-triplets-audit-with-oem-20261012.json

# 27 zusätzliche adversariale Tests inkl. Originaldaten-Prüfung:
sudo -n python3 -m unittest discover -s tests \
  -p 'test_wb2a_postrestart_bitplane_and_triplets_offline.py' -q

# Vollständige Forschungsregression:
python3 -m unittest discover -s tests -q
```

**Nächste priorisierte ROM-Dump-Forschungsaufgaben:** Im originalen P300-/GWG-/VS1-Protokollcode oder einem gesicherten älteren `V200KW2`-ROM-Trace gezielt nach **indirekt indizierbaren ROM-Inhaltsdiensten** suchen. Das strukturierte `0x3301`-RAM-Fenster erst dann erneut als ROM-Kopie betrachten, wenn ein **QuellROM-Byte-Match**, ein **echter Boot-Copy-Trigger** oder ein anwendungsseitig belegter Transfer existiert. Kein weiterer unspezifischer 20-Bit-RAM-Sweep und keine fremden GFA-HO2B-Blocklängen auf der WB2A ausführen.

**Ergebnis: Neues, reproduzierbares 3-Byte-Muster und erfolgreiche Fault-Gates. Echte aus Programm-ROM extrahierte Bytes bleiben 0.**
