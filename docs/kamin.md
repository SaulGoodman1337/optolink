# Kamin: Erdgeschoss-Heizkörper automatisch pausieren

Der Kamin im Wohnzimmer heizt das Erdgeschoss (Wohnzimmer links/rechts, Flur,
Gäste-WC, je nach Tür auch das Büro) stark auf. Das Obergeschoss (Bad,
Kinderzimmer, Schlafzimmer) soll normal weiterheizen. Alles läuft in Home
Assistant, am Splitter ändert sich nichts.

Bausteine:

| Datei | Aufgabe |
| --- | --- |
| `config/optolink-splitter/homeassistant-blueprints/kamin_erkennung.yaml` | Erkennt am Sensor direkt am Kamin, ob er brennt, und schaltet `input_boolean.kaminangeheizt`. |
| `config/optolink-splitter/homeassistant-blueprints/kamin_raum_pause.yaml` | Eine Automation je Raum: Pause, wenn der Kamin brennt **und** der Raum warm genug ist; heizt selbst wieder, wenn der Raum abkühlt. |
| `config/optolink-splitter/homeassistant-room-control-package.yaml` | Raumregelung lässt Sensoren mit Label „Optolink Kamin EG“ weg, solange der Kamin brennt. |
| Dashboard, Ansicht **Raumregelung**, Abschnitt „Kamin“ | Kamin-Status, Pause je Raum, Verlauf, Brennerstarts. |

## Kamin-Erkennung

Gemessen am 18.11.2026: Der Sensor am Kamin stieg von 21,7 °C auf 24,7 °C in
der ersten Stunde und auf 55–58 °C in der zweiten; danach kühlte er langsam
ab (26 °C nach 8 h, 25 °C am nächsten Tag). Ohne Kamin liegt er bei 19–23 °C.

- **An**, sobald der Sensor ≥ 30 °C misst oder um ≥ 3 K über seinem Ruhewert
  liegt. Der Ruhewert (optionaler `input_number`) folgt dem Sensor alle
  15 min: Abkühlen sofort, Erwärmen höchstens 0,5 K je 15 min. Ein Ruhewert
  unter 15 °C oder mehr als 10 K unter dem Sensor gilt als ungültig.
- **Aus**, wenn der Sensor 30 min unter 27 °C liegt und der Kamin mindestens
  2 h an war. Ist der Sensor 1 h nicht erreichbar, geht der Schalter aus.
- Den Schalter kann man jederzeit von Hand einschalten (z. B. beim Anzünden).

## Raum-Pause

Je Raum eine Automation aus `kamin_raum_pause.yaml` und ein eigener
Pause-Schalter (`input_boolean.kamin_pause_<raum>`).

- **Pause**, wenn der Kamin brennt und der Raum ≥ Soll + 0,5 K ist.
- **Wieder heizen**, sobald der Raum < Soll − 0,5 K fällt (auch wenn der Kamin
  noch brennt), wenn der Kamin aus ist oder der Raumsensor keinen Wert
  liefert. Innerhalb der Mindestpausenzeit (15 min) erst 1 K tiefer.
- Das Büro (Tür offen oder zu, kein Türsensor) entscheidet allein über seine
  eigene Raumtemperatur: Bleibt die Tür zu, wird es nicht warm und heizt
  einfach weiter.
- **Frostschutz:** Es wird nie „off“ geschaltet. Schaltet der Blueprint die
  Thermostate selbst, stellt er sie auf 12 °C (einstellbar). Wird ein Raum
  kälter als Soll − 0,5 K, endet die Pause ohnehin.

Zwei Arten, die Thermostate zu schalten (pro Raum genau eine verwenden):

1. **Raum mit Heizplan-Automation** (Advanced Heating Control): Der
   Pause-Schalter des Raums wird dort als *Winter-Modus* (invertiert)
   eingetragen, statt `input_boolean.kaminangeheizt`. Der Heizplan schaltet
   dann selbst und stellt nach der Pause seinen Plan wieder her. Im
   Blueprint bleibt „Thermostate selbst schalten“ leer.
2. **Raum ohne aktive Heizplan-Automation** (derzeit Wohnzimmer): Thermostate
   im Blueprint eintragen. Vor der Pause merkt er sich die Sollwerte
   (`scene.kamin_vorher_<pause-schalter>`) und stellt sie danach zurück.
   Nach einem HA-Neustart während der Pause fehlt die Szene; dann gilt
   „Sollwert nach der Pause“.

Raumsensor: lieber ein eigener Sensor im Raum als das Thermostat. Die
HM-CC-RT-DN messen am Heizkörper und zeigen bei offenem Ventil 1–3 K zu viel
(Flur am 27.11.: Thermostat 23,7 °C, Shelly 20,5 °C). Das Thermostat kann als
„Ersatz-Raumtemperatur“ eingetragen werden, es zählt nur, wenn der Sensor
ausfällt.

Vorschlag für die Instanzen:

| Raum | Raumtemperatur | Ersatz | Pause-Schalter | Soll | Thermostate selbst |
| --- | --- | --- | --- | --- | --- |
| Wohnzimmer | `sensor.temperatursensorwohnzimmer_temperatur` | `climate.wohnzimmer_links`, `climate.wohnzimmer_rechts` | `input_boolean.kamin_pause_wohnzimmer` | 21 | `climate.wohnzimmer_links`, `climate.wohnzimmer_rechts` |
| Flur | `sensor.temperaturflur_temperature` | `climate.flur` | `input_boolean.kamin_pause_flur` | 20 | – (HeizplanFlur) |
| Gäste-WC | `sensor.gaste_wc_temperatur` | – | `input_boolean.kamin_pause_gaste_wc` | 21 | – (HeizplanGästeWC) |
| Büro | `sensor.buro_temperatur` | – | `input_boolean.kamin_pause_buro` | 20 | – (HeizplanBüro) |

## Raumregelung und Obergeschoss

Die Raumregelung (`optolink-room-control`) mittelt alle Sensoren mit dem
Label „Optolink Raumregelung“. Brennt der Kamin, steigt der Mittelwert durch
die EG-Sensoren, die Regelung senkt den Vorlauf für das ganze Haus oder
schaltet nachts auf „Nur WW“, und das Obergeschoss kühlt aus.

Deshalb:

- Den Sensor **direkt am Kamin** nie mit „Optolink Raumregelung“ labeln.
- Label **„Optolink Kamin EG“** (`optolink_kamin_eg`) an die EG-Sensoren
  (z. B. TemperaturFlur) hängen. Solange `input_boolean.kaminangeheizt` an
  ist, schickt die Automation „Optolink: Raumtemperaturen an Raumregelung
  senden“ diese Werte nicht mit. Es zählen dann nur die OG-Sensoren.
- Bleibt dabei kein Sensor übrig, kommt nichts mehr an. Nach 10 min meldet
  die Regelung „Keine Sensordaten“ und gibt den Raumsollwert frei (Therme
  folgt ihrem Zeitprogramm).

## Therme und Taktung

Pausieren die EG-Heizkörper, nimmt die Anlage weniger Wärme ab. Bei niedriger
Last taktet die WB2A eher (siehe Messungen in der Raumregelung/Pumpen-Doku).
Bad und Kinderzimmer bleiben offen und halten den Durchfluss. Die
Brennerstarts stehen im Kamin-Abschnitt im Dashboard; steigen sie bei
brennendem Kamin deutlich, hilft eine etwas niedrigere Heizkurve oder ein
EG-Heizkörper, der nicht pausiert (z. B. Flur aus der Pause nehmen).

## Einrichten in Home Assistant

1. Blueprints importieren (Einstellungen → Automationen → Blueprints →
   Importieren, Raw-URL der beiden Dateien) oder nach
   `<config>/blueprints/automation/optolink/` kopieren.
2. Helfer anlegen: `input_boolean.kamin_pause_wohnzimmer`, `_flur`,
   `_gaste_wc`, `_buro`; optional `input_number.kamin_ruhewert`
   (0–60 °C, Schritt 0,1). `input_boolean.kaminangeheizt` gibt es schon.
3. Automation aus „Kamin-Erkennung“ anlegen (Kamin-Sensor
   `sensor.kamin_temperature`). Die alte Automation „KaminAnheizung“ bleibt
   aus.
4. Je Raum eine Automation aus „Kamin: Raum-Pause“ (Tabelle oben).
5. In HeizplanFlur, HeizplanGästeWC und HeizplanBüro den Winter-Modus von
   `input_boolean.kaminangeheizt` auf den jeweiligen Pause-Schalter
   umstellen (Invertieren bleibt an).
6. Label „Optolink Raumregelung“ vom Gerät „Kamin“ entfernen, Label
   „Optolink Kamin EG“ an TemperaturFlur hängen, Paket bzw. Automation
   „Optolink: Raumtemperaturen an Raumregelung senden“ aktualisieren.
7. Dashboard: Abschnitt „Kamin“ in der Ansicht Raumregelung.
