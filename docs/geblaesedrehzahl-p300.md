# Gebläsedrehzahl im P300-Betrieb

Stand 26.11.2026. Gilt für die WB2A / VDensHO1 20C2 mit GFA P80 = 0x20.

## Ergebnis der Suche

- Die Gebläsedrehzahl gibt es nur als GFA-Parameter **P06** (`0x4006`,
  × 30 U/min). GFA_READ (`0x6B`) beantwortet die WB2A nur in VS1/KW. Über P300
  wird GFA abgewiesen (Befund 8.10.2026).
- Online-Quellen (openv-Wiki/Issues, vcontrold, Foren, ioBroker) kennen für
  diese Generation keinen anderen Datenpunkt.
- Bester RAM-Kandidat aus der Oktober-Forschung war `0x0F20` (Spiegel
  `0x1C76`). Ein lesender Langzeitlauf am 25.11.2026 mit
  `tools/research/fan-p300-observer.py` (FC03 alle 2,5 s bei Brenner an,
  15 Brennerzyklen in 4 h) zeigte:
  - `0x0F20` = 0 bei Brenner aus, springt einige Sekunden vor der Flamme auf 84 und
    fällt kurz vor Flamme aus auf 0. Das passt zur Vorspülung.
  - Während der Startrampe fällt die Modulation in ~30 s von 66 % auf 40 %.
    `0x0F20` bleibt dabei **konstant 84**. Eine echte Drehzahl müsste fallen.
  - Einzige Bewegung (84 → 116 → 84) beim Warmwasserladen bei konstant 33 %
    Modulation.
  - In den Nachbarblöcken `0x0F00–0x0F5F` und `0x1C40–0x1C9F` folgt kein Byte
    der Last. Die 9 Bytes nach `0x0F21`/`0x1C76` sind eine Kopie von `0x55D3`.
  - Zusammen mit dem Oktober-Befund (P06 = 4.410 U/min bei `0x0F20` = 84):
    `0x0F20` ist **keine Ist-Drehzahl**, eher ein interner Start- oder
    Grenzwert. Er wird nicht als Drehzahl veröffentlicht.

## Lösung: kurze VS1-Fenster (`fan_p06.py`)

Im Dauer-P300-Betrieb läuft in der Splitter-Hauptschleife das Modul
`config/optolink-splitter/fan_p06.py` (eingebunden durch
`tools/optolink-apply-fan-p06-patch.py`, installiert vom normalen `update`).

Ablauf eines Fensters, nur bei brennender Flamme:

1. EOT → ENQ → VS1 (`optolinkvs1.init_protocol`, wie upstream)
2. GFA_READ P80 (muss `0x20` sein), P06, P09, P87, je 1 Byte, FF wird verworfen
3. EOT → ENQ → `16 00 00` → ACK (`optolinkvs2.init_vs2`), dann `0x00F8` als
   Nachweis; bei Fehler ein zweiter Versuch, danach greift der Link-Watchdog
   (60 s)

Zeitplan: erstes Fenster 40 s nach Flammenstart, danach alle *Intervall*
Minuten (Standard 5, 1–30) solange die Flamme brennt. 60 s nach Flamme aus
wird 0 gemeldet (ohne Buszugriff). Den Flammenzustand liefert der
Pumpenwächter (keine zusätzlichen Lesezugriffe).

Während eines Fensters (5–8 s) ruhen Telemetrie und Pumpenwächter. Die Firmware
setzt dann ihre codierte E7 = 100 % ein, also die sichere Richtung. Da Fenster
nur bei brennender Flamme laufen, steht der Pumpenwächter ohnehin auf Boost.

Nach drei Fehlversuchen in Folge pausieren die Fenster 30 min.
Keine Schreibzugriffe, keine anderen Adressen.

### MQTT / Home Assistant

| Topic | Inhalt |
| --- | --- |
| `openv/geblaesedrehzahl_gfa_p06` | P06 × 30 U/min (bisheriger Sensor) |
| `openv/gfa_modulationssollwert_p09` | P09 × 0,3922 % |
| `openv/gfa_p80_typ`, `openv/gfa_status3_p87` | roh, hex |
| `openv/fan_p06/status` | JSON: state, reason, rpm, measured_at, age_s, window_ms, windows, failures |
| `openv/fan_p06/enabled/set` | `ON`/`OFF` (Standard ON) |
| `openv/fan_p06/interval/set` | Minuten 1–30 (Standard 5) |

HA-Entities: `switch.…_geblaesedrehzahl_messung_aktiv`,
`number.…_geblaesedrehzahl_messintervall`,
`sensor.…_geblaesedrehzahl_messung_zustand`, `…_messzeit`,
`…_fensterdauer`. Dashboard: Bereich „Gebläse & GFA – 24 h“.

Abschalten: Schalter „Messung aktiv“ aus oder
`mosquitto_pub -t openv/fan_p06/enabled/set -m OFF -r`.
