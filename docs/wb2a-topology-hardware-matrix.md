# WB2A: Anlagenschema und tatsaechlich erforderliche Hardware

Stand: 2026-10-07. Quellenpruefung, kein Umbau und kein Liveversuch.
Geltungsbereich: lokale WB2A / VDensHO1 / 20C2, dokumentierter direkter
Heizkoerperkreis, eine integrierte Pumpe, Warmwasser, keine externe Heizkreispumpe,
kein Mischer und keine hydraulische Weiche. Historische Werte sind keine aktuelle
Messung der Anlage.

## Codierung und Zeichnungsnummer sind unterschiedliche Dinge

`00:1..6` waehlt aktive A1-/M2-/Warmwasserfunktionen. Die nummerierten
**Anlagenausfuehrungen 1..4** der Anleitung beschreiben hydraulische Beispiele.
Insbesondere ist `00:4` KEINE Anweisung, alle Komponenten aus Zeichnung 4 zu kaufen.

| Code | Aktive Funktionen | Unterschied zur dokumentierten vorhandenen Anlage |
|---|---|---|
| 00:1 | Direkter A1, kein WW | Vorhandenes direktes Heizkonzept ohne geregelte WW-Funktion; kein Pumpenboost |
| 00:2 | Direkter A1 + WW | Dokumentierter Ausgangszustand; kein zusaetzlicher Mischerkreis |
| 00:3 | Gemischter M2, kein WW | Reale Heizkoerperhydraulik als Mischerkreis umbauen; lokaler A1 inaktiv, WW nicht geregelt |
| 00:4 | Gemischter M2 + WW | Gleicher echter M2-Umbau mit geeigneter WW-Anbindung; A1 darf fehlen |
| 00:5 | A1 + M2, kein WW | Tatsaechlich direkten Kreis behalten UND zweiten gemischten Kreis anschliessen |
| 00:6 | A1 + M2 + WW | Beide realen Heizkreise plus WW; deutlich mehr Hardware als vorhanden |

Zu M2 gehoeren eine passende versorgte KM-BUS-Mischererweiterung, motorischer
Mischer, echter korrekt montierter Vorlauffuehler und externe M2-Pumpe sowie
passende Rohrfuehrung. Die Temperaturbegrenzung der gezeichneten Fussboden-
heizungsbeispiele macht aus den vorhandenen Heizkoerpern keine Fussbodenheizung.
Bauteilauswahl und Dimensionierung brauchen Herstellnummer und Hydraulikplanung.

Die Therme erkennt keine Rohrfuehrung automatisch: elektrische Teilnehmer- und
Sensorerkennung, konfigurierte Funktionen und tatsaechliche Wasserwege sind drei
verschiedene Ebenen. Ein vorhandenes Modul beweist nicht, dass ein unbeschalteter
Mischerausgang oder eine fehlende externe Pumpe die Befehle wirklich umsetzt.

## Abgleich mit Herstellerzeichnungen

Primaerquelle: Viessmann **5681 573, 10/2006**, WB2A 8,8..26 kW.
Gedruckte Seiten 25, 26 und 27 wurden visuell geprueft, nicht nur als Text gelesen.

- Seite 25: direkter A1, optional Warmwasser.
- Seite 26: A1 plus M2. Die Codiertabelle derselben Seite nennt ausdruecklich
  00:4/00:3 auch fuer eine Anlage mit NUR einem Mischerkreis, mit/ohne Speicher.
  Eine zweite Regelung, ein Puffer oder eine Weiche folgt also nicht pauschal
  allein aus der Auswahl M2. Die dortige 30-Prozent-Volumenstrombedingung gehoert
  zum gezeichneten kombinierten A1/M2-Aufbau und ist nicht universell uebertragbar.
- Seite 27: weiteres Beispiel mit Waermetauscher zur Systemtrennung. Kein Beleg
  fuer eine generelle Tauscherpflicht bei M2. Die folgende Ueberschrift beschreibt
  einen lokalen M2-Erweiterungssatz, einen weiteren Mischerkreis unter Vitotronic
  050 und eine hydraulische Weiche. Der zusaetzliche Kreis folgt nicht aus 00:4.

System-/Medientrennung durch Waermetauscher, hydraulische Entkopplung durch
Weiche und thermische Speicherung durch Puffer erfuellen verschiedene Aufgaben.
Keiner dieser Begriffe ist mit dem Code M2 gleichzusetzen.

## Unabhaengig konfigurierte Hardwarefunktionen

Die quellenbasierten Wertetabellen stehen in [anlagenschema.md](anlagenschema.md).

| Codierung | Reale Abhaengigkeit |
|---|---|
| 52 | Tatsaechlicher Vorlauf-/Weichenfuehler, kein Softwareersatz fuer eine Weiche |
| 53 | Tatsaechliche Last am internen Erweiterungsrelais: eine gewaehlte Ausgangsrolle; keine neu entstehende Pumpe |
| 5B | Hydraulische Lage des Warmwasserspeichers relativ zur Weiche |
| 54 | Wirklich vorhandene kompatible Solarregelung, unabhaengig von A1/M2 |
| 65 | Eingebaute Umschaltventilbauart; Information, kein Migrations-Tuningparameter |

Ein Schemawechsel macht diese Hardwareentscheidungen nicht automatisch richtig.
Die Bestaetigung im DEV-Dashboard ist keine Hydraulik-Plausibilitaetspruefung.

## Bedeutung fuer das Pumpenziel

Im direkten Kreis stehen A1-Anforderung und interne Pumpentelemetrie fuer
logische Rollen des eingebauten Aktors. Ein echter M2 ergaenzt eine eigene Pumpe.
K31 betrifft dann die INTERNE Kesselkreispumpe, nicht die externe M2-Pumpe.
A8:1 erlaubt eine interne Pumpenanforderung aus M2. K31=100 ist damit in einer
passenden Topologie plausibel, aber keine lokal bewiesene Folge von bloss 00:4.

Eine M2-Anforderung kann bei erloschener Flamme fortbestehen. A8 ist kein
brennerexklusiver Drehzahlschalter. 9F veraendert Temperaturreserve, nicht
Pumpendrehzahl. Ein Mischer garantiert keine unabhaengigen Volumenstroeme;
100 Prozent Sollvorgabe beweist weder gemessenen Durchfluss noch entsprechende
Waermeabnahme durch Heizkoerper. Die Mindestbrennerleistung bleibt unveraendert.

E7=100-Versuche belegen schon heute hohe interne Pumpenvorgabe im A1-Kreis,
aber keine dauerhafte brennerselektive Steuerung. Die Versuche vom 23. September
(364 s und 8m52s) und 25. September (mindestens 391,1 s, manuell beendet,
Heizkoerper zusaetzlich geoeffnet) bleiben getrennte Beobachtungen.

## Technische Empfehlung, keine Installationsanweisung

Keinen Schein-M2 neben A1 anlegen, nur um eine Pumpenanforderung zu erzeugen.
Akzeptierte Codierung und plausible Sensoranzeige beweisen keinen sicheren
Brennerbetrieb. Ein abgestufter Referenzversuch kann zunaechst die elektrische
Erkennung und interne Pumpenauswahl ohne Brenner pruefen. Fachkundige Personen
muessen reale Sperrung/Wiederherstellung und einen offenen, gefuellten Wasserweg
sicherstellen. Das beantwortet eine elektrische Frage, zertifiziert aber keinen
unvollstaendigen M2-Aufbau. Ein Heizversuch benoetigt passende Hardware und
hydraulische Inbetriebnahme statt lediglich einer geaenderten Zahl.

Die P300-Protokollmigration braucht KEINEN dieser hydraulischen Umbauten.
Sie ist ein separates Kommunikationsprojekt. Schema/Pumpenumbau beim ersten
P300-Paritaetstest unveraendert lassen, damit die Ursachen zuordenbar bleiben.

## Quellen

- [Viessmann WB2A-Serviceanleitung 5681 573](https://www.intec-heizung.de/media/pdf/c2/0c/64/Viessmann-Vitodens-200-WB2A-Serviceanleitung.pdf), gedruckte S.25-28 und Codierung 00 auf S.37.
- [Vorhandene Schemadokumentation](anlagenschema.md), Basis 7bc69c32788dd19c7a35e787d0b2aa26c9548ce6.
- [Lokale M2-Bewertung](https://github.com/SaulGoodman1337/optolink/blob/optolink-research/config/optolink-splitter/research/m2-conversion-pump-assessment.md).
- [Pumpen-Messhistorie](https://github.com/SaulGoodman1337/optolink/blob/optolink-research/config/optolink-splitter/research/pump-start-heating-vs-dhw.md).
- [P300-Migration und Freigabestufen](p300-migration.md).
