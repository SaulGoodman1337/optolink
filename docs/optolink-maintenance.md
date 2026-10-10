# Optolink-Wartung über die Kommandozeile

`optolink-maintenance` ist die abgesicherte Wartungsschnittstelle
für die lokal überprüfte **Vitodens 200-W WB2A / VDensHO1 / 20C2 /
SW03**. Sie bietet ausschließlich am realen Regler verifizierte
Wartungsfunktionen. Sie ist **kein allgemeines Werkzeug für
unbeschränkte Optolink-Schreibbefehle**.

## Installation

Der reguläre Produktions-Updater installiert:

```text
/usr/local/bin/optolink-maintenance
/usr/bin/optolink-maintenance -> /usr/local/bin/optolink-maintenance
```

Die Datei besitzt den Modus `0750`. Bedienung als `root`
auf dem Optolink-Splitter-Host:

```bash
update
optolink-maintenance status
```

## Verifizierter Vertrag mit dem Regler

| Adresse | CLI-Zugriff | Verifizierte Bedeutung |
| --- | --- | --- |
| `0x5721` | Lesen/Schreiben | Wartungsschwelle für Brennerbetriebsstunden; Rohwert × 100 Stunden, zulässig 0–10.000 h; beim Wechsel von 0 auf einen Wert größer 0 kann `0x7570` neu referenziert werden |
| `0x5723` | Lesen/Schreiben | Wartungsintervall 0–24 Monate |
| `0x5724` | kontrollierte Schreibfolge | Wartungsstatus; nachgewiesene Rücksetzfolge `1 → 0` |
| `0x756C` | nur Lesen | `LastCheckInterval`, 32-Bit-Referenz; genaue Vitosoft-Zeitumrechnung nicht bestätigt |
| `0x7570` | nur Lesen | `LastBurnerCheck`, gespeicherter Brennerlaufzeit-Referenzwert in Sekunden |
| `0x08A7` | nur Lesen | Brennerlaufzeit gesamt in Sekunden |
| `0x088A` | nur Lesen | Brennerstarts gesamt |

Berechnung der seit der Wartungsreferenz verstrichenen Brennerstunden:

```text
(aktueller Wert 0x08A7 - gespeicherter Wert 0x7570) / 3600
```

Ein Wartungsreset setzt weder `0x08A7` noch `0x088A` zurück.

## Befehle

### Status anzeigen

```bash
optolink-maintenance status
optolink-maintenance --json status
```

Für Einzelanfragen an den Splitter dient `--verbose`. Ausführliche
Protokollausgaben gehen nach `stderr`; `--json` auf `stdout`
bleibt dadurch maschinenlesbar.

### Brennerbetriebsstunden-Wartungsschwelle

Der Bedienwert wird in Stunden angegeben. Zugelassen sind
ausschließlich exakt 100-Stunden-Schritte im verifizierten Bereich.

```bash
optolink-maintenance set-hours 3000 \
  --confirm-reference-reset RESET-BRENNERREFERENZ
```

| Bedienwert | Rohwert |
| --- | --- |
| 0 h | 0 |
| 100 h | 1 |
| 3.000 h | 30 |
| 10.000 h | 100 / `0x64` |

Zunächst wird der bisherige Wert gelesen. Ist er bereits gleich
dem gewünschten Wert, unterbleibt standardmäßig jeder Schreibzugriff.
`--force` erlaubt eine ausdrücklich angeforderte
Gleichwert-Schreiboperation.

Jeder tatsächliche Schreibvorgang muss durch einen neuen
Controller-Readback bestätigt werden. Bei ausbleibender Bestätigung
versucht die CLI die vorherige Konfiguration wiederherzustellen und
erneut zu verifizieren.

**Wichtige Nebenwirkung:** Ein späterer Live-Test zeigte, dass ein
Wechsel von `0x5721 = 0` auf einen Wert größer null den Zähler
`0x7570` auf die aktuelle gesamte Brennerlaufzeit setzen kann.
Deshalb verlangt jeder tatsächliche `set-hours`-Write
das exakte Bestätigungstoken:

```text
--confirm-reference-reset RESET-BRENNERREFERENZ
```

Ein beobachteter Wechsel von 100 h zurück auf 0 h setzte
`0x7570` zwar nicht nochmals um; die Schutzregel gilt
absichtlich für **alle** tatsächlichen Schwellenänderungen.
Die Werte `0x756C`, `0x08A7` und `0x088A` wurden
durch den Test von `0x5721` nicht verändert.

### Zeitintervall der Wartung

```bash
optolink-maintenance set-months 12 \
  --confirm-reference-reset RESET-ZEITREFERENZ
```

Zulässig sind ganzzahlige Werte von 0 bis 24 Monaten.

**Wichtige Nebenwirkung:** Jeder wirkliche Schreibvorgang
auf `0x5723` setzt die 32-Bit-Referenz `0x756C`
(`LastCheckInterval`) neu. Das wurde am realen Regler
sowohl beim vorübergehenden Wechsel auf 24 Monate
als auch bei der Rückkehr zu null beobachtet.
Daher verweigert die CLI jeden solchen Write ohne das
exakte Token `RESET-ZEITREFERENZ`.

Wenn der Wert bereits stimmt, bleibt die vorhandene Zeitreferenz
standardmäßig erhalten. Selbst bei einem bewusst erzwungenen
Gleichwert-Write mit `--force` ist die Bestätigung erforderlich.

### Wartungsstatus zurücksetzen

```bash
optolink-maintenance reset --confirm RESET-WARTUNG
```

Die nachgewiesene Folge lautet:

```text
0x5724 = 1
0x5724 = 0
```

Die CLI versucht unabhängig von einem fehlenden ACK oder einer
fehlgeschlagenen Rücklesung, den Status im Abschluss-/Sicherheitspfad
wieder auf `0` zu bringen.

Im Anschluss prüft sie:

- Rückkehr von `0x5724` in den Grundzustand;
- ob sich `0x756C` verändert hat;
- ob sich `0x7570` verändert hat;
- Plausibilität einer bestehenden Brennerlaufzeitreferenz;
- dass Brennerlaufzeit und Anzahl der Brennerstarts nicht gesunken sind.

Die Referenzänderungen sind **nicht symmetrisch**:
`0x756C` wird beim Reset neu referenziert.
Die Wirkung auf `0x7570` hängt vom Reglerzustand
beziehungsweise von der Konfiguration ab. Ein früherer
Reset initialisierte eine zuvor leere Referenz `0x7570`;
bei einem späteren vollständigen CLI-Test mit
`0x5721 = 0 h` blieb eine vorhandene `0x7570`-Referenz
unverändert. Beide Auswirkungen werden deshalb getrennt ausgegeben.

Die konfigurierten Schwellen `0x5721` und `0x5723`
bleiben erhalten.

## Sicherheitsregeln

- Eine Prozesssperre verhindert parallele Wartungs-CLI-Sitzungen.
- Für `0x756C` und `0x7570` existiert **kein** Schreibbefehl.
- `set-hours` akzeptiert nur 0–10.000 h in 100-h-Schritten.
- Änderungen der Brennerstundenschwelle erfordern die explizite
  Zustimmung zur möglichen Neu-Referenzierung von `0x7570`.
- `set-months` akzeptiert nur 0–24 Monate und verlangt die
  Bestätigung der Zeitreferenzänderung.
- `reset` verlangt das exakte Token `RESET-WARTUNG`.
- Der neue Controller-Readback, nicht das bloße ACK,
  entscheidet über den Erfolg.
- Fehlgeschlagene oder mehrdeutige Schreibvorgänge lösen
  einen Versuch zur Wiederherstellung der bisherigen Konfiguration aus.
- Wartungsrücksetzung und Entriegelung einer Brennerstörung
  bleiben ausdrücklich getrennte Funktionen.
- Ein getestetes Hybrid-P300-Lesefenster begründet
  **keine Berechtigung für P300-Wartungsschreibvorgänge**.

## Gemeinsame MQTT-Wartungs-API

Die Wartungs-CLI und der MQTT-Dienst nutzen denselben abgesicherten Kern:

```text
optolink-maintenance
         \
          --> optolink_maintenance_core.py --> Splitter-MQTT
         /
optolink-maintenance-api
```

Die genaue API mit Befehls- und Antwortformat,
gespeicherten Zuständen, Request-ID-Deduplizierung und
Home-Assistant-Anbindung dokumentiert
[die MQTT-Wartungs-API](optolink-maintenance-api.md).

## Home-Assistant-Integration

Die am realen Gerät geprüfte Wartungsbedienung verwendet
dieselben Regeln wie die CLI:

- Vorgemerkter numerischer Wert für `0x5721` mit deutlicher
  Warnung vor der möglichen Neu-Referenzierung von `0x7570`.
- Vorgemerkter numerischer Wert für `0x5723` mit Warnung
  vor der Änderung von `LastCheckInterval`.
- Geschützter Wartungsreset mit ausdrücklicher Bestätigung.
- Kein direkter Schreibzugriff auf `0x756C` oder `0x7570`.
- Keine Verwendung des Wartungsresets zur Brennerstörungsentriegelung.
- Home Assistant erzeugt niemals rohe `w;0x....`-Schreibbefehle.

## Stand der Hardwareprüfung

Folgende CLI-Pfade wurden am realen Regler erfolgreich nachgewiesen:

- Schreibvermeidung bei `set-hours 0` und `set-months 0`;
- Bereichs- und Bestätigungsprüfungen ohne durchgereichte Writes;
- `set-hours 100` einschließlich Readback und Rückkehr zu null;
- Schutz vor der möglichen `0x7570`-Neu-Referenzierung;
- `set-months 1` einschließlich Readback und Rückkehr zu null;
- Neu-Referenzierung von `0x756C` bei beiden echten
  `0x5723`-Schreibvorgängen, während `0x7570` unverändert blieb.

Auch der abgesicherte `reset`-Pfad wurde vollständig geprüft.
Die tatsächliche Folge war `00 → 01 → 00`:
`0x756C` änderte sich, `0x7570` blieb bei
einer Brennerstundenschwelle von 0 h unverändert.
Die CLI zeigt beide Effekte einzeln an.

### Hinweis zu `LastCheckInterval`

Der rohe Wert von `0x756C` verändert sich in
sekundenähnlichen Schritten und bei Neusetzen der Wartungsreferenz.
Eine früher vermutete direkte Interpretation als
Little-Endian-Unix-Zeitstempel gilt **nicht als verifiziert**.
Die verfügbare Vitosoft-Dokumentation nennt dafür einen
speziellen, noch nicht vollständig rekonstruierten Konverter.
Auch der so berechnete Kalenderwert stimmt nicht
verlässlich mit Host- oder Reglerzeit überein.
Die CLI zeigt daher weiterhin den **rohen Referenzwert**
ohne unbelegte Zeitstempelinterpretation an.
