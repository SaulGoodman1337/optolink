# Vollmessungen: 807 P300-Statusantworten, Flammenbit und verbleibende GFA-Referenzen

Stand: 2026-10-08. Branch `optolink-p300-migration`. Keine Produktionsfreigabe.

## Ergebnis und unmittelbarer naechster Schritt

Die beiden uebergebenen Vollmessungen wurden lokal gelesen und auf Ebene der
Telegrammbytes nachgerechnet. **807 von 807 Statusantworten** bestehen die
Pruefung von Rahmen, Laenge, FC01, Adresse 55D3, Nutzdatenlaenge 11 und Pruefsumme.
Jede Antwort stimmt mit ihrem gespeicherten Sample ueberein. Die JSONL-Samples
sind in beiden Sessions inhaltlich identisch mit `measurement.json`.

Der P300-Statusnachweis wird dadurch staerker. Es wurde aber **keine neue
Ist-Drehzahladresse** entdeckt. Byte 0 und Byte 9 zeigen dynamische Verlaeufe;
sie sind im bestehenden Projekt bereits als Ansteuerdiagnose bzw. Modulation
beschrieben. Eine passende Kurve ist kein Nachweis eines Tachometerwertes.

Der naechste kleine Messschritt ist jetzt implementiert: P06 und P09 jeweils
vor/nach dem vollstaendigen 55D3-Block im **laufenden VS1** lesen. So kann die
bisher fehlende zeitnahe Referenz geliefert und gemessene Drehzahl von einer
Anforderung unterschieden werden. Kein weiteres P300-only-Fenster fuer die
bereits beantwortete Statusfrage, keine Dienstpause, kein RAM-Write.
[Ausfuehrbarer Vergleich und Abbruch](p300-gfa-native-pair-runbook.md).

## Quelle und reproduzierbare Pruefung

Nutzerarchiv: `p87-p300-existing-bYddq6.tar.gz`, 214928 Byte.
SHA256: `262401ecf2b7692f2f26a3a5cceaae2d82e4277fb4b52dec299650e795983cf0`.
Sechs regulaere Dateien: je Session `measurement.json`, `samples.jsonl` und
`recovery.json`. Keine Settings oder Skriptkopien enthalten. Der Offline-Auditor
liest die Mitglieder im Speicher, extrahiert/ausfuehrt nichts aus dem Archiv und
verweigert unerwartete Dateien, Pfade, Links, Mehrfachschluessel und Groessen.

```bash
python3 tools/audit-p87-full-recordings.py \
  /pfad/p87-p300-existing-bYddq6.tar.gz --output /neuer/pfad/audit.json
```

Die [maschinelle Ableitung](evidence/p300-full-status-byte-audit-2026-10-08.json)
enthaelt Hashes aller sechs Mitglieder, Bytebereiche, beobachtete
Flammenbitfenster und Rohspurpruefungen. Originalarchive, volle Zeitreihen und
Trace-Rohdaten werden nicht nochmals in dieses oeffentliche Repo kopiert.
Die frueheren Konsolenberichte bleiben unveraendert als damalige Evidenz erhalten.

## 1. Vollstaendigkeit und Sender-/Empfaengerpruefung

| Merkmal | Session 134132Z-124665 | Session 134745Z-125157 |
| --- | ---: | ---: |
| Gewaehltes Beobachtungsfenster | 300 s | 600 s |
| Samples / passende Drahtantworten | 269 / 269 | 538 / 538 |
| FC01-Statusrequests in der Beobachtungsphase | 269 | 538 |
| Eigene Antwortbestaetigungen 06 | 269 | 538 |
| Andere TX in dieser Phase | 0 | 0 |
| Zusaetzliche Request-ACK-Wiederholungen | 0 | 0 |
| Sampleabstand min / Mittel / max | 1,084 / 1,116 / 1,281 s | 1,084 / 1,115 / 1,288 s |
| Host-Dauer Request-TX bis letztes Antwortbyte, Mittel | 78,685 ms | 78,814 ms |
| Entsprechender beobachteter Maximalwert | 119,777 ms | 119,792 ms |

Die zulassigen TX waren ausschliesslich `41 05 00 01 55 D3 0B 39` und `06`.
Es gab in der protokollierten Beobachtung kein VS1/6B, C9, EOT, Physical_READ oder
Write. Die originalen Mess- und Wiederherstellungsberichte enthalten keine
Fehler, melden Beobachtung und VS1-Link abgeschlossen sowie dieselben sechs
wiederhergestellten Dienste/Timer. `mqtt_freshness_verified=false` im
Recovery-Bericht ist korrekt: die spaeteren separaten MQTT-Abfragen stehen im
bereits uebergebenen Konsolentranskript, nicht in dieser Servicefunktion.

**Grenze:** Das ist eine Verifikation der mitgelieferten Host-Softwaretrace,
kein unabhaengiger Logikanalysator-Mitschnitt. Die ~79 ms sind keine garantierte
Sensoraktualitaet. Ein gecachter, aber intern aktualisierter Wert bleibt moeglich.

## 2. Bedeutung der elf Bytes: Messung und vorhandene Zuordnung trennen

Indizes sind nullbasiert. Die Bereiche sind Dezimalzahlen, keine automatisch
zugewiesenen Prozent-/RPM-Einheiten.

| Index | Unterschiedliche Werte / Bereich | Aussage |
| --- | --- | --- |
| 0 | 27 / 0..71 | Bestehende Leistungs-/Ansteuerdiagnose; dynamisch, auch ohne Flammenbit aktiv. Kein neuer RPM-Nachweis. |
| 1 | 50 / 123..172 | Dynamisch, veraendert sich lange nach Flammenende. Physikalische Bedeutung hier nicht zugeordnet. |
| 2 | 2 / 171..172 | Seltene Wechsel AB/AC; keine begruendete Temperatur-/Drehzahldekodierung. |
| 3, 4, 8 | jeweils nur 0 | In diesen Aufnahmen konstant; kein allgemeiner Nachweis unbenutzter Felder. |
| 5 | 4 / 01,09,21,29 hex | Im bestehenden Zielprofil Bit20=Flamme, Bit40=Verriegelung. |
| 6 | 7 / 0..15 | Status-/Bitfeld; nicht mit Byte7 zu RPM zusammenfassen. |
| 7 | 9 / 00,20,30,40,50,60,62,72,90 hex | Bereits gestuetzter P87-Kandidat, unter P300 dynamisch. |
| 9 | 24 / 0..68 | Vorher mit A305 korrelierter Modulationswert. Kein P09-Sollwertalias bewiesen. |
| 10 | identisch zu Byte5 in 807/807 Samples | Gleiche beobachtete Statusflags in beiden Positionen; kein universeller Gleichheitsbeweis. |

Die Zuordnungen von Byte5 und Byte0 stammen aus dem bestehenden
[Produktionsprofil](../config/optolink-splitter/vdensho1-20c2-wb2a-homeassistant.py),
insbesondere Abschnitte Fire-control diagnostic block und Internal burner/control-chain.
Die Byte9/A305-Korrelation steht in der [gepinnten Geraetedokumentation](https://github.com/SaulGoodman1337/optolink/blob/79f222c7f3a11b848a6a8ac8ece50e24deede823/config/optolink-splitter/research/device-vdensho1-20c2-wb2a.md).
Diese historischen Zuordnungen werden angewendet, nicht in diesem Lauf mit
unabhaengigen Sensoren neu bewiesen.

### Byte0 und Byte9 sind keine zwei neu entdeckten unabhaengigen Messungen

In den 807 Samples gibt es 27 verschiedene beobachtete Paare. Jeder beobachtete
Byte0-Wert hat darin genau einen zugeordneten Byte9-Wert. Beispiele (dezimal):
`69 -> 66`, `61 -> 57`, `38 -> 33`; niedrige Werte `9/10/14/15 -> 30`.
Das ist vereinbar mit einer Transformation oder eng gekoppelten Steuergroessen.
Es beweist weder die Richtung einer Transformation noch ihre allgemeine Gueltigkeit.

Beide Werte sind in **30 Samples trotz ausgeschaltetem Flammenbit ungleich 0**.
Sie duerfen deshalb nicht ungeprueft als tatsaechliche Waermeleistung oder
Flammennachweis verwendet werden. Eine neue Umrechnungsformel wurde nicht gefittet.

## 3. Jetzt ist auch der Flammenbitverlauf sichtbar

Mit der bereits dokumentierten Maske `Byte5 & 0x20` ergeben sich drei Fenster:

| Lauf / Fenster | Erstes Sample mit Bit an | Erstes folgendes Sample mit Bit aus | Beobachteter Abstand | Byte9 zuerst / zuletzt bei Bit an |
| --- | ---: | ---: | ---: | ---: |
| 300 s | 29,048 s | 55,900 s | 26,852 s | 66 / 50 |
| 600 s, erstes | 8,031 s | 35,825 s | 27,794 s | 65 / 48 |
| 600 s, zweites | 363,275 s | 391,155 s | 27,880 s | 66 / 47 |

Das sind Zeitabstaende zwischen Host-Beobachtungen des Telemetrie-Bits. Wegen
Sampleabstand und unbekannter interner Aktualisierungsverzoegerung sind das
**keine exakt gemessenen physischen Flammenlaufzeiten**. Die unter/oberen
Sampleklammern sind getrennt im JSON erhalten, ebenfalls keine physische Latenzgarantie.

Die Nutzerbeobachtung einer Brennerphase wird damit durch das schon verwendete
Flammensignal gestuetzt; im zweiten Lauf sind sogar zwei solche Fenster sichtbar.
In keinem der 807 Samples war das dokumentierte Verriegelungsbit40 gesetzt.
Das schliesst eine normale Wiederanlaufsperre nicht aus und beweist keinen
bestimmten Abschaltgrund. 72 trat in den zweiten Laeufen noch mit Flammenbit
auf, 90 im ersten ohne; beide bleiben ohne gesicherte Zustandsnamen.

Byte9 war beim letzten Sample mit Flammenbit noch bei 50 bzw. 48/47. Die
historisch beschriebene 33-Prozent-Untergrenze wurde damit in diesen beobachteten
Flammenfenstern nicht erreicht. Dies passt zu einem fruehen Abbruch der
Abwaertsrampe, ist **kein Beweis fuer Uebertemperatur, mangelnden Volumenstrom
oder Taktsperre**. Kesseltemperatur, Sollwert, Pumpenvorgabe und RKR-Freigabe
wurden im P300-only-Fenster nicht gleichzeitig erfasst.

## 4. Weshalb die Vollmessungen P06/P09 noch nicht kalibrieren

Vor/nach dem 300-s-Fenster waren P06 und P09 jeweils 00. Vor dem 600-s-Fenster
war P06=00, P09=93, P87=20; danach waren P06/P09/P87 wieder 00. Der 93-Wert ist
eine getrennte Referenz vor dem Wechsel, nicht eine simultane Zuordnung zu
einem spaeteren nativen Bytewert. Eine vollstaendige P06/P09-Zeitreihe innerhalb
der P300-only-Phase kann in diesem Versuch gerade nicht enthalten sein.

Historische GFA-Aufnahmen enthalten P09=93 am Startplateau und P06 um 4410 rpm,
aber an einem anderen Tag. Sie duerfen nicht als fehlende gleichzeitige
Referenz dieser 807 Samples eingesetzt werden. [Historische Evidenz](https://github.com/SaulGoodman1337/optolink/blob/79f222c7f3a11b848a6a8ac8ece50e24deede823/config/optolink-splitter/research/vitosoft/gfa-triggered-startup-2026-09-24-evidence.json).

## 5. Implementierter Anschlussversuch statt erneuter Statusbestaetigung

`tools/wb2a-gfa-native-pair-check.py` liest im unveraenderten laufenden VS1:

`P80 -> P06 vorher -> P09 vorher -> 55D3/11 -> P09 nachher -> P06 nachher`.

Beide Referenzen rahmen denselben nativen Block ein. Je Kanal werden konstante,
wechselnde und zu weit auseinanderliegende Referenzen getrennt markiert. Die
bereits bekannten Byte0/Byte9 werden roh zusammen mit dem ganzen Block erhalten.
Ein Unterschied zwischen stabiler P06- und P09-Referenz ist besonders wichtig,
weil Gleichlauf von Ist und Soll im stationaeren Zustand ihre Identitaet nicht beweist.

Alle bekannten Leseadressen; kein freies Scannen und kein auto-fitted RPM-Alias.
Hoechstens sechs Read-Auftraege pro Runde, mindestens fuenf Sekunden zwischen
Rundenstarts. Zeitgrenzen, beobachtete MQTT-Kollisionen, falsche Identitaet oder
FF beenden die Aufnahme. Der bewiesene VS1-Portbesitzer bleibt aktiv.
Der alte, getestete P87-MQTT-Helfer wird privat und hash-gepinnt wiederverwendet.
[Runbook](p300-gfa-native-pair-runbook.md).

Die 15 neuen Audit-Tests und 23 neuen Paar-Tests pruefen Offline-Code und
simulierte Nachrichten. Keine neue LXC-/MQTT-/Thermenmessung durch die Entwicklung.
P06/P09 bleiben offen, produktives HA und Pumpensteuerung unveraendert.
