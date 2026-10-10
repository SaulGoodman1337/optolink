# WB2A Anlagenschema und Anlagenkonfiguration

Diese Seite dokumentiert die im Home-Assistant-DEV-Dashboard sichtbaren
Topologie- und Anlagenparameter der **Viessmann Vitodens 200 WB2A /
VDensHO1 / Gerätekennung 20C2**.

## Zweck und Sicherheitsgrenze

Die hier beschriebenen Werte sind keine Komfort-Sollwerte, sondern
**Installations- und Topologieparameter**. Sie bestimmen, welche Heizkreise,
Warmwasserfunktionen, Sensoren und Erweiterungen die Regelung erwartet.

Eine falsche Einstellung kann deshalb unter anderem dazu führen, dass:

- ein vorhandener Heizkreis nicht mehr logisch berücksichtigt wird;
- die Regelung einen nicht vorhandenen Sensor erwartet;
- eine reale Pumpe mit der falschen Funktion angesteuert wird;
- Warmwasser- oder Solarfunktionen falsch zugeordnet werden;
- Sensor- oder Kommunikationsfehler entstehen.

Das DEV-Dashboard zeigt die aktuellen Werte normal an. Schreibaktionen sind
hinter **Info / ändern** und einer zusätzlichen Bestätigung versteckt.

Die Optolink-Leseadressen sind im Produktionsprofil etabliert. Die
entsprechenden Codierwerte sind in der WB2A-Serviceanleitung als verstellbar
dokumentiert. Die neu hinzugefügten Remote-Schreibpfade sind quellenbasiert,
aber auf dieser konkreten Anlage **nicht für jeden möglichen Topologiewechsel
live verifiziert**. Nach jeder Änderung muss der Wert an der Vitodens bzw. per
Readback kontrolliert werden.

## Quelle

Primärquelle:

- Viessmann Vitodens 200, Typ WB2A
- Serviceanleitung **5681 573**
- Ausgabe 10/2006
- Kapitel *Erstinbetriebnahme* und *Codierungen / Codierung 1 und 2*

Öffentliche Referenz:

```text
https://www.intec-heizung.de/media/pdf/c2/0c/64/Viessmann-Vitodens-200-WB2A-Serviceanleitung.pdf
```

## Übersicht der Topologieparameter

| Codierung | Optolink | HA-Konfiguration | Bedeutung | Schreibbar im DEV-Dashboard |
|---|---:|---|---|---|
| **00** | `0x7700` | `select.vitodens_200_wb2a_anlagenschema_00_einstellung` | Heizkreis-/Warmwasserschema | ja, mit Bestätigung |
| **52** | `0x7752` | `select.vitodens_200_wb2a_hydraulische_weiche_sensor_52_einstellung` | Vorlaufsensor hydraulische Weiche | ja, mit Bestätigung |
| **53** | `0x7753` | `select.vitodens_200_wb2a_relais_funktion_53_einstellung` | Funktion internes Erweiterungsrelais | ja, mit Bestätigung |
| **54** | `0x7754` | `select.vitodens_200_wb2a_solarregelung_54_einstellung` | Solarregelung | ja, mit Bestätigung |
| **5B** | `0x675B` | `select.vitodens_200_wb2a_warmwasser_speicher_anbindung_5b_einstellung` | Speicher vor/hinter hydraulischer Weiche | ja, mit Bestätigung |
| **65** | `0x6765` | nur Anzeige | Bauart Umschaltventil | **nein** |

Zusätzlich werden die internen Diagnosewerte `0x7701` (Anlagentyp) und
`0x8851` (Bauart Warmwasser) angezeigt. Für diese beiden Werte liegt im
Projekt keine vollständig verifizierte WB2A-Wertetabelle vor. Sie bleiben
daher bewusst read-only und werden nicht semantisch überinterpretiert.

---

## Codieradresse 00 – Anlagenschema

Datenpunkt: **`0x7700`**

Codierung 00 ist die zentrale Topologieeinstellung. Sie beschreibt, welche
Heizkreise vorhanden sind und ob Trinkwassererwärmung zur Anlage gehört.

| Wert | Bedeutung |
|---|---|
| **00:1** | 1 Heizkreis ohne Mischer **A1**, ohne Trinkwassererwärmung |
| **00:2** | 1 Heizkreis ohne Mischer **A1**, mit Trinkwassererwärmung |
| **00:3** | 1 Heizkreis mit Mischer **M2**, ohne Trinkwassererwärmung |
| **00:4** | 1 Heizkreis mit Mischer **M2**, mit Trinkwassererwärmung |
| **00:5** | A1 + M2, ohne Trinkwassererwärmung |
| **00:6** | A1 + M2, mit Trinkwassererwärmung |

Die Serviceanleitung ordnet diese Werte den dokumentierten
Anlagenausführungen zu. Ein Schemawechsel ist **keine automatische
Hydraulikerkennung**; der Wert muss zur realen Anlage passen.

### Abhängigkeiten

- Bei Schemen mit M2 muss ein realer Mischerkreis samt Erweiterung vorhanden
  sein.
- Bei Schemen mit Warmwasser werden die Warmwassercodierungen 56–73 relevant.
- Bei hydraulischer Weiche sind insbesondere Codierung 52 und gegebenenfalls
  5B relevant.
- Codierungen für vorhandene Heizkreise können nach einem Schemawechsel
  zusätzlich sichtbar bzw. wirksam werden.

---

## Codieradresse 52 – Vorlaufsensor hydraulische Weiche

Datenpunkt: **`0x7752`**

| Wert | Bedeutung |
|---|---|
| **52:0** | kein Vorlauftemperatursensor für hydraulische Weiche |
| **52:1** | Vorlauftemperatursensor für hydraulische Weiche vorhanden |

Die Serviceanleitung beschreibt `52:1` als Wert, der bei erkanntem Anschluss
normalerweise **automatisch gesetzt** wird.

Eine manuelle Einstellung auf `52:1`, obwohl kein Sensor angeschlossen ist,
kann zu einem Vorlaufsensorfehler führen. Deshalb nur ändern, wenn die reale
Verdrahtung an X3 und die Hydraulik bekannt sind.

---

## Codieradresse 53 – Funktion des internen Erweiterungsrelais

Datenpunkt: **`0x7753`**

| Wert | Funktion |
|---|---|
| **53:0** | Sammelstörmeldung |
| **53:1** | Zirkulationspumpe |
| **53:2** | externe Heizkreispumpe A1 |
| **53:3** | externe Umwälz-/Speicherladepumpe |

Dieser Wert beschreibt keine abstrakte Softwarefunktion, sondern die Funktion
des real belegten Relaisausgangs der internen Erweiterung. Der Codierwert muss
deshalb zur angeschlossenen Last passen.

---

## Codieradresse 54 – Solarregelung

Datenpunkt: **`0x7754`**

| Wert | Bedeutung |
|---|---|
| **54:0** | ohne Solarregelung |
| **54:1** | Vitosolic 100 |
| **54:2** | Vitosolic 200 |

Auch diese Codierung wird laut Serviceanleitung bei angeschlossener,
unterstützter Solarregelung normalerweise automatisch erkannt. Manuelles
Verstellen ist nur sinnvoll, wenn das tatsächlich vorhandene Gerät bekannt ist.

---

## Codieradresse 5B – Speicher-Wassererwärmer / hydraulische Lage

Datenpunkt: **`0x675B`**

| Wert | Bedeutung |
|---|---|
| **5B:0** | Speicher-Wassererwärmer direkt am Heizkessel |
| **5B:1** | Speicher-Wassererwärmer hinter der hydraulischen Weiche |

Dieser Wert ist nur sinnvoll, wenn die gewählte Anlagenkonfiguration
Trinkwassererwärmung enthält.

---

## Codieradresse 65 – Bauart Umschaltventil

Datenpunkt: **`0x6765`**

| Wert | Bedeutung |
|---|---|
| **65:0** | kein Umschaltventil |
| **65:1** | Viessmann |
| **65:2** | Wilo |
| **65:3** | Grundfos |

Die WB2A-Serviceanleitung kennzeichnet Codierung 65 ausdrücklich als
Anlageninformation **„nicht verstellen“**. Das Dashboard zeigt den Wert daher
nur an und erzeugt absichtlich keine Schreib-Entity.

---

## Interne Diagnosewerte

### Anlagentyp – `0x7701`

Der Wert wird von der Regelung als interner Anlagen-/Topologiewert
bereitgestellt. Für die konkrete WB2A/VDensHO1-Ausführung liegt derzeit keine
vollständig verifizierte Wertetabelle im Projekt vor.

**Konsequenz:** anzeigen, aber nicht raten und nicht schreiben.

### Bauart Warmwasser – `0x8851`

Auch dieser Wert ist als Diagnosewert im Produktionsprofil verifiziert, aber
nicht mit einer belastbaren vollständigen Wertetabelle dokumentiert.

**Konsequenz:** anzeigen, aber nicht raten und nicht schreiben.

---

## Home-Assistant-Schreibpfad

Die neuen Select-Entities verwenden dieselben MQTT-Basistopics wie die
bereits vorhandenen Read-Datenpunkte und ergänzen nur den `/set`-Pfad.

Beispiel Anlagenschema:

```text
Read:    openv/anlagenschema
Write:   openv/anlagenschema/set
Address: 0x7700
Width:   1 byte
Values:  1..6
```

Das Dashboard schreibt keine freien Integerwerte. Es kann ausschließlich die
in dieser Dokumentation aufgeführten Select-Optionen senden.

## Nach einer Änderung prüfen

Nach jeder Topologieänderung:

1. Readback des geänderten Parameters prüfen.
2. Schema/Codierung zusätzlich am Bedienteil kontrollieren.
3. Diagnose auf neue Sensor-, KM-BUS- oder Kommunikationsfehler prüfen.
4. Heizkreis- und Warmwasserfunktionen auf Plausibilität prüfen.
5. Bei Änderungen an 52/54 kontrollieren, ob die erwartete Hardware wirklich
   erkannt wird.
6. Bei Schemaänderungen Heizkennlinien, Pumpen- und Warmwasserparameter nicht
   ungeprüft aus einem anderen Schema übernehmen.

## Nicht automatisch gekoppelte Werte

Das Dashboard verändert **immer nur den ausdrücklich gewählten Parameter**.

Ein Wechsel von Schema 00 führt nicht automatisch zu Änderungen an 52, 53, 54,
5B oder anderen Codierungen. Diese Trennung ist absichtlich, weil die korrekte
Kombination von der realen Hydraulik und den angeschlossenen Erweiterungen
abhängt.
