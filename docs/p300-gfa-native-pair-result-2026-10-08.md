# GFA P06/P09 gegen nativen Statusblock: 180-Runden-Auswertung (WB2A 20C2)

Stand: **2026-10-08**. Branch: `optolink-p300-migration`. **Kein Produktions- oder RAM-Write-Freigabenachweis.**

## Kurzfazit

Der getrennte MQTT-/VS1-Referenzvergleich wurde vom Nutzer auf der echten WB2A ausgefuehrt. Alle **180** Runden aus `pairs.jsonl` stimmen mit der eingebetteten Liste in `summary.json` ueberein. `errors=[]`, `device_writes=false`, `protocol_switched=false`, `services_stopped=false`. Die komplette Aufnahme enthaelt **eine** natuerliche Brennerphase mit 24 aufeinanderfolgenden Samples mit gesetztem bereits dokumentiertem Flammenbit. Die offene P300-Voraussetzung ist dadurch **nicht** geloest: Byte0/Byte9 sind **kein validierter Ersatz fuer GFA P06-Istdrehzahl** und P09 ist noch kein produktionsfaehiger Alias.

**Wichtigster neuer Sachbefund:** P06 und P09 laufen in stationaeren Abschnitten oft mit demselben Rohzaehler, **trennen sich aber beim Anlauf, bei der Abwaertsrampe und bei Brennerende**. Der native Modulationswert Byte9 folgt wieder einer anderen Skala und bleibt beim Abschalten kurz auf 33, obwohl der P09-Referenzwert bereits 00 ist und P06 binnen derselben Klammer von 0x52 auf 0x1D faellt. Reine Korrelation oder ein passender Plateauwert waeren daher irrefuehrend.

## Datenintegritaet und Herkunft

| Gegenstand | Ergebnis |
| --- | --- |
| Aufgenommene Runden | 180, Indizes 1..180 |
| JSONL verglichen mit den 180 eingebetteten `summary.json`-Runden | 1:1 identisch |
| Messfenster (UTC) | 2026-10-08 14:49:15 bis 15:04:14 |
| Kontrollerkennung / GFA P80 vor dem Lauf | 20C2 / 0103 / 20 |
| GFA P80 nach dem Lauf | 20 |
| Protokollwechsel, Service-Stopp, Geraetewrites | Nein / Nein / Nein |
| Beobachterfehler | 0 |
| Stable GFA P06 / Aenderung waehrend Klammer | 171 / 9 |
| Stable GFA P09 / Aenderung waehrend Klammer | 180 / 0 |
| P06-stabil-nichtnull | 17 Runden, Werte 53, 81, 93 hex |
| P09-stabil-nichtnull | 26 Runden, neun verschiedene Hexwerte |
| Gleichzeitige stabile, aber unterschiedliche P06/P09-Rohwerte | 3 Runden (110, 114, 116) |
| Flammenbit / Verriegelungsbit | 24 Samples gesetzt / 0 Samples gesetzt |

SHA256 `pairs.jsonl`: `5323deef1cc01c67918e31d9d3bc22e2c3df3f4429f52ff80f3dda6724cf1411`

SHA256 `summary.json`: `41a4c1dcaef875ff805e18b9912b28b80e7adca3d86eb56ea2e7e8858a4ec987`

Die privaten Rohdateien werden **nicht** ins oeffentliche Repository kopiert. `docs/evidence/p300-gfa-native-pair-result-2026-10-08.json` enthaelt Hashes und ausgewaehlte abgeleitete Vergleichspunkte, keine komplette Rohzeitreihe. Reproduzierbar mit `python3 tools/audit-gfa-native-pairs.py pairs.jsonl summary.json --output neuer-bericht.json` (Ziel darf noch nicht existieren). Das Skript ist ausschliesslich offline, liest keine Therme und sendet nichts an MQTT.

## Ein natuerlicher Brennerzyklus statt weiterer Nullvergleiche

Die Runden 1..109 und 137..180 sind hinsichtlich P06/P09 und Byte0/Byte9 null. Relevant sind Runden 110..136. Der **erste gesetzte Flammenbit-Sample** ist Runde 112 (t=557,864 s relativ zum ersten nativen Read), der letzte Runde 135 (ca. 673,3 s), der erste folgende **ohne** Flammenbit Runde 136 (ca. 678,3 s). Somit liegt der beobachtete Abstand zwischen erster und letzter Flammen-Sample bei ca. 115 s; zum naechsten Aus-Sample ca. 120 s. Aufgrund des Abtastintervalls und unbekannter interner Meldeverzoegerung ist dies **keine exakt gemessene physische Flammenlaufzeit**.

| Runde | Flammenbit | P06 vorher -> nachher (hex) | P09 (hex) | Native Byte0 / Byte9 (dez) | Beobachtung |
| ---: | :---: | --- | --- | --- | --- |
| 110 | 0 | 00 -> 00 | 93 | 0 / 0 | GFA-Sollwert bereits ungleich 0, native Steuerfelder noch 0 |
| 111 | 0 | 97 -> 99 | 93 | 71 / 68 | Geblaese laeuft vor erster Flammenbit-Sichtung, P06 4530 -> 4590 rpm |
| 112 | 1 | 93 -> 93 | 93 | 69 / 66 | Start-/Plateauphase; P06 4410 rpm |
| 114 | 1 | 93 -> 93 | 91 | 69 / 66 | P09 veraendert, P06 und Byte9 noch gleich |
| 116 | 1 | 81 -> 81 | 7d | 61 / 56 | P06 3870 rpm, P09-Rohwert 125 (also nicht gleich) |
| 120 | 1 | 59 -> 57 | 55 | 41 / 35 | P06 faellt innerhalb der Klammer weiter |
| 122–135 | 1 | meist 53 -> 53 | 53 | 38 / 33 | Ca. 65 s ueber mehrere Stichproben auf dem unteren Betriebsplateau |
| 136 | 0 | **52 -> 1d** | **00** | **38 / 33** | P06 2460 -> 870 rpm waehrend Status-Byte9 noch 33 ist |
| 137 | 0 | 00 -> 00 | 00 | 0 / 0 | Steuerstatus ebenfalls 0 |

P06 verwendet in diesem Projekt die bereits lokal dokumentierte Umrechnung **Rohwert ×30 rpm**; Byte0 und Byte9 sind davon unabhaengige native Rohzahlen. P09 besitzt einen anderen Skalierungsweg. Beispiele: Bei P09=0x93 betraegt die dokumentierte Darstellung `147 × 0.3922 = 57,65 %`, waehrend Byte9 in der Flammenphase bei 66 liegt. Bei P09=0x53 entspricht die Darstellung 32,55 %, waehrend Byte9 33 ist. **Aehnliche Werte am unteren Ende erlauben keine durchgehend identische Skalierung.**

In den dynamischen P06-Klammern steigt oder faellt der gemessene Fan-Rohwert, waehrend P09 in jeder einzelnen Klammer stabil bleibt. Das passt zu einer zeitlich nachlaufenden Istdrehzahl gegenueber einer Anforderung, beweist aber wegen **aufeinanderfolgender statt gleichzeitiger Reads** weder eine definierte Regelabweichung noch eine millisekundengenaue Reaktionszeit. Bei Runde 136 liegt sogar ein Abschalt-/Nachlaufeffekt vor, der keine Umrechnung von `Byte9=33` zu exakt einem P06-Wert zulaesst.

## Konsequenzen fuer den P300-Plan

1. **P87**: getrennt in frueheren Tests im Statusblock Byte7 unter P300 dynamisch bestaetigt, aber exakte Uebergangslatenz nicht vollstaendig geklaert.
2. **P09**: Byte9/Byte0 koennen den Modulationsverlauf sichtbar machen; eine universelle, 1:1-aequivalente P09-Ersatzfunktion mit gleicher Bedeutung, Skalierung, Transienten- und Aktualisierungsguete ist **noch nicht nachgewiesen**. Runde 110 und 136 sind direkte Gegenbeispiele fuer die naive Sofortgleichheit.
3. **P06**: Die P06-Istdrehzahl ist explizit nicht aus den vorhandenen Status-/Ansteuerbytes als exakter Tachometerwert ableitbar. Besonders wichtig ist die Trennung von Ist (P06) und Soll (P09) in Start-/Ramp-/Nachlaufphasen.
4. **P80**: GFA-Typkennung und lokale Identitaetspruefung bleiben bei Produktauswahl gesondert zu beachten.
5. **Gesamt**: Kein Abschalten von GFA-P06 in HA, keine Umbenennung nativer Werte zu `geblaesedrehzahl_gfa_p06`, kein dauerhafter Produktivwechsel zu P300, kein RAM-Write und keine automatische Pumpenregelung aus diesem Nachweis.

## Naechste begruendete Forschungsarbeit

**Nicht** denselben 600-/900-Sekunden-VS1-Vergleich wiederholen: Diese Aufnahme enthaelt die bis dahin fehlende natuerliche Anlauf-, Rampen-, Plateau- und Abschaltphase. Naechste Prioritaet ist eine **quellenbasierte Suche nach einem unabhaengigen, fuer VDensHO1 20C2 nachweisbaren FAN-IST-Wert**, der unter P300 Virtual_READ oder eingeschraenktem, ausschliesslich lesendem Physical_READ verifiziert werden kann. Dabei **Adresse, Bytebreite, Aktualisierungsmodell und Herkunft vor einem Geraeteversuch belegen**, keine pauschalen RAM-Bereiche scannen oder aus Statusbits eine Drehzahl fitten.

Erst fuer einen konkret belegten Kandidaten einen kurzen, abgesicherten P300-only-Read-Versuch mit VS1-Wiederherstellung aufbauen. Ohne einen solchen Kandidaten bleibt **VS1 Produktivstandard**, waehrend P300-RAM-Zugriff auf isolierte Forschungssitzungen beschraenkt ist.

Die beobachtete natuerliche Flammenphase (etwa zwei Minuten im Telemetriefenster) ist laenger als die vorherigen ca. 27-Sekunden-Fenster. Der Datensatz enthaelt aber **keine zeitgleichen Pumpen-/Kesseltemperaturen** und erlaubt daher keine Ursache-Wirkung-Aussage zur Pumpe oder Taktsperre.

**Quellen:** [vorheriger 807-Frame-Audit](p300-full-status-byte-audit-2026-10-08.md), [VS1-Paar-Prober und originales Runbook](p300-gfa-native-pair-runbook.md), [P87 P300-only](p300-p87-p300-only-result-2026-10-08.md), [Geraeteprofil](../config/optolink-splitter/vdensho1-20c2-wb2a-homeassistant.py).