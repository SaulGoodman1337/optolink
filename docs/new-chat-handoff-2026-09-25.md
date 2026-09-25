# New-chat handoff - WB2A / Optolink / KMBUS - 2026-09-25

Use the following text as the start prompt in a replacement chat.

---

Wir arbeiten im Projekt **Homeassistant und optolink-splitter** weiter.

Bitte zuerst den aktuellen Stand aus dem Repo berücksichtigen, insbesondere:

- `docs/research-plan-2026-09-24.md`
- `docs/research-checkpoint-2026-09-25.md`
- `config/optolink-splitter/research/kmbus-optolink-research.md`
- `config/optolink-splitter/research/vitosoft/kmbus-read-memory-analysis-2026-09-24.md`
- `config/optolink-splitter/research/vitosoft/physical-vs-kmbus-eeprom-2026-09-25-evidence.json`
- GitHub Issue #30

## Lokale Anlage / Produktion

- Viessmann Vitodens 200-W WB2A
- VDensHO1
- Identifikation 20C2
- Extension / Regelungssoftware-Paar 0103
- permanenter Produktionsbetrieb über **VS1/KW**
- `vs1protocol=True`
- `port_vitoconnect=None`
- Optolink-Port über den stabilen CP2102 by-id-Pfad
- aktuelles `olbreath=0.025 s`
- GFA P80/P06/P09/P87 funktioniert im permanenten VS1-Betrieb
- keine unnötigen Umschaltungen der Produktionskonfiguration

Remote Desktop Commander für den LXC **optolink-splitter** funktioniert.
Der Remote-User ist `chatgpt-admin`; sudo ist absichtlich nur für exakt
freigegebene Kommandos erlaubt. Bitte keine Rechte erweitern, solange es nicht
wirklich nötig ist.

Zuletzt verifiziert aktiv:

- optolink-splitter.service
- optolink-party-emulator.service
- optolink-maintenance-api.service
- optolink-schedule-manager.service

## Sicherheitsregeln

- standardmäßig ausschließlich read-only
- keine breiten Address-Sweeps
- keine KBus/KMBUS-Schreibbefehle
- keine Burner-Safety-Writes
- Erfolg eines Function Codes ist noch kein Semantikbeweis
- `RAM` bedeutet nicht automatisch MCU-RAM
- `EEPROM` bedeutet nicht automatisch Kesselcodierstecker
- GWG-/LGM27-Semantik nicht auf VDensHO1 übertragen, solange das nicht belegt ist
- nach jedem temporären P300-Fenster müssen Splitter, Party, Schedule Manager und permanentes VS1 wiederhergestellt/verifiziert werden

## Gesicherter KM-BUS/P300-Stand

### 0x41 KMBUS_RAM_READ

0x41 ist auf dem lokalen 20C2 echt implementiert.

Frühere kontrollierte Vergleiche von 0x01 Virtual_READ und 0x41 ergaben 7/7
identische Daten, auch bei dynamischen Pumpenwerten.

Wichtiger dynamischer Pumpen-Snapshot:

- `0x7663 = 03 1E` -> A1 Runtime-Anforderung 30 %
- `0x0A3C = 32` -> finaler interner Pumpenbefehl 50 %
- `0x7660 = 03 32` -> interne physische Pumpe 50 %

Damit ist die Transformation 30 % -> 50 % direkt beobachtet. Das passt stark
zur bekannten GWG75-Mindestdrehzahl von 50 %, ist aber ohne same-window
E7+GWG75-Read kein vollständig isolierter Kausalitätsbeweis.

### 0x31 XRAM_READ

Alle sechs aus Vitosoft abgeleiteten GWG-XRAM-Read-Shapes wurden lokal getestet:

- 0x0000/1
- 0x003A/2
- 0x003D/2
- 0x0040/2
- 0x0042/2
- 0x0088/2

Ergebnis: 0/6 erfolgreich. Alle 0x31-Requests lieferten valide Error Messages
mit Payload 05. Die zugehörigen 0x01-Kontrollen lieferten an diesen
Cross-Profile-Adressen Error Message Payload 01.

Daher kein blindes weiteres XRAM-Probing.

### PrefixRead / 0x43

Die Host-Serialisierung wurde statisch in Vitosoft v6 geklärt.

`PrefixRead` wird bei diesem Build nur im RPC-Pfad
`Remote_Procedure_Call / FCRead 0x07` in Request-Daten umgewandelt.

Normale `KMBUS_EEPROM_READ / 0x43`-Reads verwenden PrefixRead **nicht**.

Der normale Request für `0x43 / 0x0001 / len 1` ist:

`41 05 00 43 00 01 01 4A`

ohne die früher experimentell angehängten Bytes
`03 00 00 00 01 01`.

Die früheren Prefix-Experimente bleiben historische Hardwareevidence, sind aber
kein Vendor-Wireformat-Beweis.

### Herkunft der 0x43-Katalogdaten

Im v6-Katalog:

- 91 KMBUS_EEPROM_READ Events gesamt
- 90 mit PrefixRead 030000000101
- diese 90 gehören ausschließlich zu 21 GWG-Profilen
- 1 no-prefix Event gehört zu DEKATEL/VCOM
- **0 Events gehören zu VDensHO1**

Historische GWG-Implementierungen benutzen ebenfalls die Zahl 0x43, aber in
einem anderen 8-Bit-Adress-Protokoll. Die Zahlengleichheit ist kein Beweis für
identische Semantik im P300/VS2-Protokoll.

### 0x43 Response-Seite

Vitosoft erzeugt die merkwürdigen Werte nicht selbst. Nach dem LDAP-Header
werden die Response-Daten roh übernommen.

Damit sind Werte wie

- 5498
- 5497
- d301
- f201
- 81
- 87
- 88

echte Controller-Payloads.

Der Host behandelt die Response-Klassen nach den unteren fünf Command-Bits:

- `0x41 & 0x1F = 0x01`
- `0x43 & 0x1F = 0x03`

Das war die Basis für den letzten Live-Vergleich.

## Letzter Live-Test 2026-09-25 09:57 CEST

Log:

`/root/wb2a-physical-vs-kmbus-eeprom-20260925-095756-217850.log`

Identity Control:

`0x01 / 0x00F8 / 8 -> 20c2000300000103` PASS

### Positive Kontrolle 0x01 vs 0x41 @ 0x00F8/2

- 0x01 -> 20c2
- 0x41 -> 20c2
- 0x41 -> 20c2
- 0x01 -> 20c2

Korrekte Klassifikation: **STABLE_SAME**

### 0x03 Physical_READ vs 0x43 @ 0x00F8/2

- 0x03 -> 5491
- 0x43 -> 5491
- 0x43 -> 5491
- 0x03 -> 5497

Klassifikation: **DYNAMIC_OR_INCONCLUSIVE**

Wichtig: die dynamische Zwei-Byte-Familie tritt auch über normales
Physical_READ 0x03 auf. Sie ist also nicht spezifisch für 0x43.

### 0x03 vs 0x43 @ 0x0001/1

- 0x03 -> 81
- 0x43 -> 81
- 0x43 -> 81
- 0x03 -> 81

Korrekte Klassifikation: **STABLE_SAME**

Aktuelle Schlussfolgerung:

> An den getesteten lokalen Adressen hat 0x43 keinen vom 0x03 Physical_READ
> getrennten Datenraum gezeigt. Eine gemeinsame/aliasierte Physical-/Service-
> View ist derzeit deutlich plausibler als eine dedizierte LGM27-EEPROM-View.
> Universelle 0x03/0x43-Gleichheit ist trotzdem noch nicht bewiesen.

Deshalb **keine weiteren 0x43-Live-Tests**, solange kein neuer
source-backed Discriminator vorliegt.

Evidence-Datei:

`config/optolink-splitter/research/vitosoft/physical-vs-kmbus-eeprom-2026-09-25-evidence.json`

Evidence commit:

`fb5fb0280726a7a61e52d606028ec4377717608c`

## Wichtig: Bugfixes des letzten Helpers

Der Live-Test lief mit Helper v1.0.0.

v1.0.0 hatte nur im Reporter einen Fehler:
der Vergleichsschlüssel enthielt den zurückgespiegelten Function-Code.
Dadurch wurden payload-identische 0x01/0x41- bzw. 0x03/0x43-Paare fälschlich
als STABLE_DISTINCT bezeichnet. Die Rohdaten waren korrekt.

Fix v1.0.1:
`3391e21f9a8179e9773d1760ee408a264d97bc9d`

Danach Self-Test:
`PHYSICAL_VS_KMBUS_EEPROM_PROBE_TESTS=6/6`

Zusätzlich zeigte der Live-Test, dass der Schedule Manager während des
P300-Wartungsfensters aussteigen konnte. Er wurde danach manuell gestartet.

Fix v1.0.2:
`3c1e37e79a628fce4c1ed0ed9683ba01fbf46ad9`

v1.0.2 stoppt/restauriert den Schedule Manager nun explizit.

**Vor jeder erneuten Verwendung dieses Helpers zuerst den normalen `update`
ausführen und danach `--self-test`.**

## Wichtige private Vitosoft-Artefakte

Verifizierter Snapshot:

- `vitosoft-private-archive-20260924-143439.7z`
- SHA256:
  `3d31380d6dfabf8ede9e305b115e847fb0670511e253a4ed4e59feef2f7adfee`

PrefixRead Serializer Deep Dive:

- Workflow commit:
  `d79475d9d955a129bef5d9bbb16755f8988486e7`
- Run: `36107129749`
- Artifact: `10852220322`
- Report commit:
  `f55cf2257d70a46e0bca92fd532b4693fd1c7fab`

GWG99 Native Inspection:

- Workflow commit:
  `4bb3add3b06043d7fb8c3f077684292a14891761`
- Run: `36108141163`
- Artifact: `10851988021`

0x43 Response Analysis:

- Report:
  `collector-output/20260924-143439/kmbus-eeprom-response-analysis-2026-09-25.md`
- Commit:
  `9bdb2b8019a5c4684fb36dc28f896903ab4eeab7`

## Nächste Prioritäten

Bitte nicht automatisch mit weiteren 0x43-Tests weitermachen.

Höchster Nutzen:

1. Coding-Plug-Forschung fortsetzen, sobald der neue EEPROM-Reader verfügbar ist:
   beide 24C04-Seiten eines Ersatzsteckers jeweils dreimal lesen, sauber als
   f01/ST und f02/Microchip labeln, SHA256 vergleichen, **nicht schreiben**.
2. Fotos der tatsächlich eingebauten WB2A-Regelungsplatine aufnehmen und lokale
   PCB-/MCU-/Speicheridentität klären. Die bisher recherchierte 7424735/VBC130-
   Platine ist nur Vergleichsmaterial und darf nicht auf die lokale WB2A
   übertragen werden.
3. Den versteckten Pumpen-Selektor upstream von `0x0A3C` als
   Firmware-/MCU-Frage weiterverfolgen.
4. Extended KBus-Familien nur weiter untersuchen, wenn aus Vitosoft/Code ein
   konkretes neues Request-Shape bzw. ein echter Discriminator abgeleitet wird.
5. Produktion und Home Assistant stabil halten; keine experimentellen
   Schreibpfade einführen.

Bitte neue Erkenntnisse wieder sofort mit Rohdaten, Interpretation,
Unsicherheitsgrenzen und Commit-IDs dokumentieren.
