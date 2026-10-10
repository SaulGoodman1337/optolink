# GFA unter P300: vollstaendiger Profilabgleich und konkreter P87-Kandidat

Stand: 2026-10-08. Branch `optolink-p300-migration`. Ausgangsstand `b80f3e14`.
**Keine Produktionsfreigabe. Keine neue Messung an der Therme durch diese Arbeit.**

## Ergebnis

Nach dem abgeschlossenen, nicht beschleunigenden Idle-ENQ-Vergleich wird nicht
weiter dieselbe Umschaltzeit variiert. Stattdessen wurden die bereits vorhandenen
Quellen gezielt auf normale virtuelle GFA-Datenpunkte und RAM-Spiegel untersucht.

Ein konkreter **Statuskandidat** wurde gefunden: das Byte mit Index 7 des
bereits untersuchten normalen Blocks `0x55D3/11` zeigt in einer historischen
Aufnahme dieselbe Folge wie GFA-P87 in einer anderen Aufnahme. Die gemeinsamen
Nichtnullwerte sind `20 -> 40 -> 50 -> 60 -> 62`. Das ist eine gezielte
Vergleichshypothese, noch keine bewiesene Alias-Adresse und kein Drehzahlkanal.

Die gesamte lokale Metadatenzuordnung wurde diesmal neu geprueft: **581 Events
mit 362 nichtleeren Adressen**, statt nur des kleinen UI-Auszuges. Ein benannter
normaler virtueller Geblaese-Istdrehzahlkanal fuer die exakte VDensHO1 wurde darin
nicht gefunden. **P06 bleibt der Engpass fuer vollstaendige Funktionsparitaet.**

## 1. Tatsachlich ausgewertete Quellen und Grenzen

### Oeffentlicher Research-Bestand

Fester Commit `79f222c7f3a11b848a6a8ac8ece50e24deede823` von `optolink-research`.
Der Bestand wurde via read-only GitHub Actions als Quellfixture bereitgestellt,
anschliessend lokal gelesen; keine der experimentellen Geraete-Tools wurde
aufgerufen. Die unmittelbar ausgewerteten Dateien sind SHA256-gepinnt in
`tools/audit-p300-gfa-sources.py`. Dazu gehoeren:

- `config/optolink-splitter/research/device-vdensho1-20c2-wb2a.md`;
- `.../vitosoft/gfa-triggered-startup-2026-09-24-evidence.json`;
- `docs/gfa-live-checkpoint.md`;
- `.../physical-ram-optolink-map-2026-09-26.md`;
- `.../vitosoft/vdensho1-events.csv`.

Die Quelltexte anderer Probeprogramme sind historische Arbeitshilfen, keine
neu ausgefuehrten Experimente. Insbesondere lebt die widerlegte Interpretation
von `55D3[6:7]` als RPM teilweise in alten Programmen weiter und wird hier nicht
als aktuelle Messdefinition uebernommen.

### Privater Vitosoft-v6-Textauszug

Verwendet wurde der bereits verifizierte Snapshot `20260924-143439`, nicht eine
neue Sammlung auf dem Windows-Rechner und nicht ein Firmware-Dump der Therme.
Archiv-SHA256:

`3d31380d6dfabf8ede9e305b115e847fb0670511e253a4ed4e59feef2f7adfee`

Ein separater Analysebranch im privaten Quellenrepo extrahiert ausschliesslich
vorhandene Metadaten/XML-Texte. Erfolgreicher Lauf `37769223322`, Commit
`83d01b15a191220fc3b32eece5551690e2e306f9`, Artefakt `11547222732`.
Der lokal gelesene ZIP-SHA256 ist
`fde104dd1f7c0d6e669f58042eaf452a257c189c0318cc4470da31d6962e2398`.
Alle **21** ausgewaehlten Textdateien wurden gegen den Extraktionsmanifest erneut
gehasht. Die Archivpruefung erfolgte im privaten Workflow; die lokalen Hashes
verifizieren den ausgewaehlten Textbestand, nicht erneut das gesamte 327-MB-Archiv.

Entscheidende Tabellen: `derived/all-devices/all-events.csv` (11.582 Events) und
`all-device-event-links.csv` (vollstaendige Profilverknuepfungen). Die exakte
Mitgliedschaft `VDensHO1`, Profil-ID 60, wurde gegen beide Tabellen geprueft.
Aehnliche Profilnamen werden nicht per Teilstring gleichgesetzt.

Keine proprietaeren Volltabellen, IL-Dumps, Zugangsdaten oder Maschineninventare
wurden in den oeffentlichen Branch kopiert. Der [Evidenzbericht](evidence/p300-gfa-source-audit-2026-10-08.json)
enthaelt nur kleine, bewusst ausgewaehlte Metadatenableitungen, Quellhashes und
eigene Schlussfolgerungen. Es wurde keine archivierte Hersteller-Software ausgefuehrt.

## 2. Vollstaendige lokale Zuordnung statt UI-Teilauszug

Der alte `vdensho1-events.csv`-UI-Auszug hat 385 Zeilen. Zeilen sind nicht
zwangslaeufig verschiedene Events, und der Auszug ist nicht das komplette Profil.
Der vollstaendige Abgleich ergibt:

| FCRead | Anzahl zugeordneter Events |
| --- | ---: |
| Virtual_READ | 462 |
| GFA_READ | 94 |
| Remote_Procedure_Call | 22 |
| undefined | 1 |
| leer / ohne Lowlevel-Funktion | 2 |
| Gesamt | 581 |

Diese Zahlen beschreiben **Metadatenzuordnungen**, keine Liste von 581 lokal
getesteten Funktionen. Auch die 94 GFA-Events enthalten verschiedene
Brennervarianten; nicht alle gelten gleichzeitig fuer den lokalen P80=20-Zweig.

Die dokumentierte Labelsuche nach Geblaese/Blower/Fan/Ventilator zusammen mit
Drehzahl/speed/rpm findet 37 Nicht-GFA-Events im globalen Bestand, aber **keinen
Treffer im exakten VDensHO1-Profil**. Dies ist ein abgegrenztes Suchergebnis,
kein Beweis, dass die Firmware keinen undokumentierten Spiegel besitzt.

Konkrete falsche Freunde:

| Event | Adresse | Bedeutung / Profilgrenze |
| --- | --- | --- |
| 4722 | 0x0B1E | SC100 Geblaese Ist; VBC550S/P, Ecotronic, Ecotronic_100, nicht VDensHO1 |
| 7963 | 0x1A71 | Outdoor-Fan-Istwert; VBC702_S / CU401B_S, nicht VDensHO1 |
| 11284 / 11288 | 0xCAE1 / 0xCAD1 | Fort-/Zuluftventilator, VScotHO1_200_01, nicht lokaler Brenner |
| 8178 / 8233 / 8259 | 0x4009 | Gleiche GFA-Adresse, verschiedene Brennervarianten und Skalierungen |

Die letzte Zeile ist besonders wichtig: Event 8259 beschreibt den lokalen
GFA-Modulationssollwert mit Faktor 0,3922. Die beiden anderen Eintraege bezeichnen
Drehzahlsollwerte mit Faktor 30. Eine Suche nach Adresse allein kann also eine
falsche physikalische Groesse liefern. Die lokal bestaetigte P06-RPM bleibt
gegenueber P09-Sollwert oder PWM getrennt.

## 3. Kandidaten fuer die vier produktiven GFA-Kanaele

| Kanal | Kandidat / Ergebnis | Evidenzstatus |
| --- | --- | --- |
| P80 / Typ | Virtual_READ 0x7650/1, Event 8395, GFA_Kennung | Explizit dem Zielprofil zugeordnet; historisch nativer Rohwert 20. Bedeutung Typ, nicht automatisch frische GFA-Kommunikationspruefung |
| P87 / Status 3 | 0x55D3/11, nullbasiert Byte 7 | Neue konkrete Kreuzkorrelation; dynamischer Same-Session-Vergleich noch offen |
| P06 / Ist-RPM | Kein gleichwertiger virtueller Kanal identifiziert | GFA_READ 0x4006, Faktor 30 bleibt Referenz. Keine Ersatzadresse freigegeben |
| P09 / Modulationssoll | Kein gleichwertiger virtueller Kanal identifiziert | Nicht einfach durch nativen Modulationsgrad oder Ansteuerwert ersetzen |

`0x7650/6` wurde historisch als `20 02 06 15 01 ff` gelesen. Die ersten drei Bytes
passen zur separat gelesenen GFA-Typ-/Softwarefolge `20/02/06`. Die Metadaten
belegen fuer Event 8395 aber nur das erste Byte. Keine vollstaendige Struktur-
oder Live-Gueltigkeitszuordnung wird aus den sechs Bytes konstruiert. Ein
gecachter Typ kann keine lebendige GFA-Kommunikation garantieren.

### P87-Hypothese im Detail

Die native Aufnahme vom 22.09.2026 nennt fuer Byte 7 die Folge:

`00 -> 20 -> 40 -> 50 -> 60 -> 62`.

Die GFA-Aufnahme vom 24.09.2026 nennt fuer P87 die Folge:

`20 -> 40 -> 50 -> 60 -> 62`.

Auch die spaete Aenderung `60 -> 62` liegt in beiden Berichten in der gleichen
Groessenordnung von etwa zehn Sekunden nach der vorangehenden Startphase. Das
stuetzt die Auswahl fuer einen Vergleich, ersetzt ihn aber nicht: **andere
Tage, andere Abfrageablaeufe, keine simultanen Messungen.**

Byte 7 bedeutet das **achte** Byte des Blocks. Rechnerisch liegt es bei 0x55DA;
daraus folgt **kein hier getesteter eigenstaendiger Read auf 0x55DA**. Der neue
Beobachter verwendet unveraendert die bereits untersuchte Blockabfrage 55D3/11.
Das hat nichts mit der widerlegten RPM-Deutung der kombinierten Bytes 6 und 7 zu tun.

Wichtig: Ein Match direkt nach einer GFA-Abfrage koennte theoretisch auch ein
nur durch diese Abfrage aktualisierter Cache sein. Selbst ein fehlerfreier
VS1-Vergleich bestaetigt deshalb noch **keine autonome Aktualisierung unter
P300**. Das bleibt eine spaetere, getrennte Pruefung mit GFA-Abfragen ausgesetzt.

## 4. RAM-Suche: genauer verbleibender Ansatz statt geratener Adresse

Die vorhandenen Berichte belegen echten Physical_READ-RAM, aber die originalen
20-KiB-Dumps und gepaarten dynamischen P06/RAM-Rohaufnahmen liegen nicht in diesem
gepinnten oeffentlichen Research-Bestand. Die vorhandenen `.bin`-Dateien sind
Kodierstecker-Dumps. Daher wurde hier **kein neuer Treffer durch Scannen eines
vollstaendigen RAM-Abbilds** behauptet.

Fuer eine spaetere RAM-Analyse sind die bekannten Eigenverkehrsbereiche zu
kennzeichnen: Anfragepuffer 196C..19AB, Antwortpuffer 19AE..19ED, Ring
19EE..1A6D samt Metadaten. Eine dort gefundene GFA-Zahl kann ein altes eigenes
Telegramm sein. Gleichheit von 00 oder 20 allein ist besonders wertlos.

Der UART1-/DMA0-Pfad mit Quelle 161B ist real dokumentiert. Seine externe
Protokollfunktion ist jedoch noch nicht zugeordnet; daraus wird keine
GFA-RAM-Struktur und keine neue Live-Leseerlaubnis abgeleitet. Datenpunktadresse
und physische RAM-Adresse bleiben getrennte Adressraeume.

## 5. Konkreter neuer Vergleich ohne Protokollwechsel

`tools/wb2a-p87-mirror-check.py` ist ein **separater MQTT-Beobachter** fuer den
laufenden originalen VS1-Splitter. Er stoppt keine Dienste, oeffnet keinen
seriellen Adapter und aendert keine Einstellungen. Default: nur inerter Plan.

Nach Identitaetspruefungen folgt maximal alle fuenf Sekunden:

`P80 pruefen -> P87 vorher -> Virtual_READ 55D3/11 -> P87 nachher`.

Nur kurze Klammern mit gleichem P87 davor/danach werden als stabile Stichproben
gewertet. Wechsel und zu grosse Zeitspannen werden getrennt markiert. Gleiche
Nullwerte oder ein einziger unveraenderter Nichtnullzustand bleiben
`INCONCLUSIVE_STATE_COVERAGE`. Nie automatische HA-Umbenennung oder Aliasfreigabe.

[Aufruf, Abbruch, Grenzen und Ergebnislabel](p300-p87-mirror-runbook.md).
Die MQTT-Schnittstelle hat keine Request-IDs: Retain-Antworten werden ignoriert,
beobachtete konkurrierende Befehle/Doppelantworten fuehren zum Abbruch. Das ist
keine vollstaendige kryptografische/atomare Zuordnung; waehrenddessen keine
anderen Diagnoseclients fuer die gleichen Adressen benutzen. Normales Polling
und vorhandene HA-Funktionen bleiben aktiv. Zusatzverkehr kann ihre Latenz beeinflussen.

## 6. Verifikation und Arbeitsgrenze

11 Quellenaudit-Tests und 33 Beobachtertests pruefen exakte Profilmitgliedschaft,
Adress-/Funktionsunterscheidung, Anfragegrenzen, Retain-/Antwort-/Kollisions-
behandlung, Inertheit, Zeitklammern und die Nichtfreigabe statischer Matches.
Ein simulierter MQTT-Peer prueft subscribe/echo/reply und qos=0/retain=False.
Ein nachgebildeter Gesamtlauf bleibt bei Nullwerten unentschieden; falsche
Geraete-ID stoppt vor GFA-Abfragen. Keine reale MQTT-/LXC-/Thermenpruefung.

Der neue read-only CI-Workflow fuehrt beide Suiten, den inerten Plan und den
gepinnten oeffentlichen Quellenaudit aus. Die privaten Volltabellen gehoeren
nicht in oeffentliche CI; deren separate lokale Pruefung und Provenienz stehen
im Evidenzbericht. Bestehende Handover- und P300-Suiten bleiben unveraendert.

Naechster Erkenntnisschritt ist die dynamische P87-Klammermessung. Sie kann einen
von vier GFA-Kanaelen erklaeren, **nicht allein die funktionsgleiche P300-Migration
oder den Pumpen-Override freigeben**. P06 sowie die autonome Frische bleiben offen.
