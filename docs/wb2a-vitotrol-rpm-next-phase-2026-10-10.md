# WB2A: Vitotrol und mehrtägige RPM-Forschung – 10.10.2026

**Basis:** PR #51 ist in `main` integriert (Merge `6664c5e`).
Der echte LXC-Befehl `update` wurde danach mit Exit-Code 0
gegen `COMMUNITY_SCRIPTS_REF=main` ausgeführt. 362 MQTT-Discovery-
Entitäten veröffentlicht, `VS1_BETRIEB_OK`, alle ursprünglichen Dienste
aktiv, Pumpenoverride und Protokollautomatik deaktiviert.

**Neuer Entwicklungsbranch:** `feat/wb2a-vitotrol-rpm-20261010`
ab diesem Main-Commit. Controller-RAM, Firmware, Kodierung und
die produktive VS1-Hauptschleife bleiben während dieser Forschung
unverändert.

## 1. Vitotrol: bekannte TX-Anfragen und fehlender RX-Kanal

Aus dem historischen UART1-P300-Archiv wurden 54 CRC16/Kermit-
gültige **RAM-Snapshotansichten** der beiden KM-Bus-Masterabfragen
für Klasse `0x11` nachgewiesen. Nicht mit 54 physischen
Busübertragungen verwechseln.

| Slot | Historischer Masterrequest F8..FB |
| --- | --- |
| 1 | `11 00 33 0A 01 01 F8 04 49 EF` |
| 2 | `11 00 33 0A 02 01 F8 04 84 CA` |

`tools/wb2a-vitotrol-offline.py` ist ein eigenständiger,
transportloser Decoder/Modellsimulator. Er bietet:
- Validierung des gerahmten KM-Bus-Protokolls mit CRC16/Kermit;
- F8..FB-Antwort für die bekannte Vitotrol-200-Identitätsfamilie
  `00 11 B3 10 01 01 F8 11 F9 34 FA 00 FB 05 06 64`;
- bekannten PONG `00 11 80 08 01 01 F9 5C`;
- 0xBF-/Record-0x20-Raumtemperaturbeispiel für 21,5 °C
  `00 11 BF 0C 01 01 20 7D AA AA 6F 33`;
- den vollständig offline simulierten Ablauf Discovery → PING →
  PONG beziehungsweise Raumtemperaturdatensatz, inklusive Verweigerung
  bei veralteter Temperaturquelle.

**Beweisgrenze:** Es gibt bisher nur UART1-TX-Mastersamples im
Regler-RAM, keinen gesicherten realen RX-Puffer und keine
Optolink-Schnittstelle zur Einspeisung von Vitotrol-Slaveantworten.
Der Versuch `0x27A0=1` ohne reale Gegenstelle löste historisch
`BC = Fernbedienungsfehler HK1` aus; danach wurde `0x27A0=0`
wiederhergestellt. Keine Wiederholung ohne belastbaren RX-/Rollback-Pfad.
Das historische Firmware-/Regler-MCU-Research in Issue #25 bleibt
die entscheidende Abhängigkeit für **software-only** Emulation.
Ein **externes physisches KM-Bus-Slave-Interface** wäre eine andere
Architektur und nicht automatisch durch P300 ersetzt.

Forschungsgrundlagen im Branch `optolink-research`:
- `config/optolink-splitter/research/vitotrol-kmbus-wire-protocol.md`
- `config/optolink-splitter/research/vitotrol-software-emulation-deep-dive-2026-09-25.md`
- `docs/p300-kmbus-vitotrol-master-tx-2026-10-09.md`
- [OpenV KM-Bus](https://github-wiki-see.page/m/openv/openv/wiki/KM-Bus)

## 2. Vier Tage passiv VS1-P06 mitschneiden

**Läuft seit 10.10.2026, 21:52 Uhr CEST.** Der erste, nur P06
erfassende Dienst `optolink-wb2a-rpm-passive-20261010.service`
wurde um 21:59 Uhr ausschließlich als Beobachter sicher beendet
(`SIGNAL_STOPPED`; 64 vorhandene P06-Samples bleiben im Archiv).
Mit unverändertem absolutem Endtermin wurde der erweiterte Dienst
`optolink-wb2a-rpm-passive-20261010-v2.service` gestartet.
Er erfasst jetzt **P06, P09 und Brennerflamme**; die exakten
Produktions-MQTT-Topics wurden gegen `homeassistant_poll_list.py`
geprüft. Gemeinsame Auswertung verwendet beide Recorder-Generationen.
Gesamtlaufzeit 96 Stunden bis 14.10.2026, ca. 21:53 Uhr CEST;
separate Systemd-Maximallaufzeit rund eine Minute länger.

`tools/wb2a-rpm-passive-observer.py` liest via bestehendem MQTT-Broker
nur aktuelle (nicht Retained-) VS1-Werte; kein zweiter serieller Port,
keine MQTT-Veröffentlichungen, keine Controller-Kommandos.
Erfasst `geblaesedrehzahl_gfa_p06`,
`gfa_modulationssollwert_p09`, `brenner_flamme` und
`brenner_flamme_gfa`, jeweils höchstens alle fünf Sekunden
pro Messart. P09/Flamme sind Kontext und ausdrücklich **keine RPM**.
Ausgabefelder markieren die Provenienz unmissverständlich:
`VS1_MQTT_PUBLISHED_NOT_P300_RPM`.

Limits: 400.000 Zeilen, höchstens 60 MiB, privates
Root-Verzeichnis `0700` / Dateimodus `0600`, maximal
100 MiB Arbeitsspeicher, keine automatische Neustartschleife.
Beobachter ist nicht Teil des normalen `update`- oder VS1-Dienstes.

Private Messdaten:
```text
/var/lib/optolink-research/rpm-passive-20261010/
    progress.json
    vs1-YYYY-MM-DD.jsonl
```

Read-only Status:
```bash
systemctl status optolink-wb2a-rpm-passive-20261010.service --no-pager
sudo cat /var/lib/optolink-research/rpm-passive-20261010/progress.json
sudo python3 tools/wb2a-rpm-passive-summary.py \
  --dir /var/lib/optolink-research/rpm-passive-20261010
optolink-hybrid status
```

Die Offline-Zusammenfassung meldet echte positive P06-Anzeigeepisoden,
Zeitbereiche und Spitzenwerte, aber **niemals eine P300-Istdrehzahl**.
**Erste positive Referenz:** Bereits am 10.10.2026 von
21:56:30 bis 21:57:01 Uhr CEST wurde eine positive P06-Episode
mit **6 Messpunkten und 4410 U/min Spitzenanzeige** protokolliert.
Dieses Fenster liegt vor der v2-Kontexterweiterung und besitzt daher
noch keine flankierenden neuen P09-/Flammen-Samples.
Es beweist **keine P300-Gebläse-Istdrehzahl**.

Eine für vier Vormittage (11.–14.10.2026, Europe/Berlin)
eingerichtete, rein lesende Aufgabenautomatik kontrolliert beide
Recorder-Generationen im gemeinsamen Archiv und meldet Auffälligkeiten;
keine Hardwarewechsel.

### Warum kein unbeaufsichtigter P300-Dauerwechsel?

Auch ein kurzer physischer P300-Zugriff beansprucht denselben Port
und pausiert vorübergehend produktive Dienste. Die früheren
C2/C3-Hardware-Canaries dauern ca. 5,2 Sekunden je Wechsel
**plus** Vorprüfung und Recovery. Daraus folgt noch keine
Freigabe für unbeaufsichtigte periodische Unterbrechungen über Tage.

Für den eigentlichen P300-Gebläsedrehzahlnachweis brauchen wir
nach einer identifizierten **stabilen positiven VS1-P06-Phase**
einen gesondert abgesicherten und zeitlich eng geklammerten
kurzen P300-Gegentest. Zahlenähnlichkeit von `0x0F20` oder
`0x1C76` zur P06-Probe beweist noch keine Tachometerquelle.
Der vorhandene unabhängige Offline-Audit liegt unter
`optolink-research/docs/wb2a-rpm-offline-audit-2026-10-10.md`.

## 3. Tests und nächste Freigaben

```bash
python3 -m unittest discover -s tests -p 'test_wb2a_*.py' -q
python3 -m unittest discover -s tests -p 'test_*.py' -q
```

**398/398 vollständige lokale Python-Regressionstests bestanden**
(362 Tests der integrierten Main-Basis plus 36 zusätzliche Offline-Tests).

Die neuen Tests schützen CRC, KM-Bus-Header, Slot, Identitätsantwort,
PING/PONG, Raumtemperatur-XOR-Record, Stale-Source, MQTT-Retained,
Berechtigung der Outputdateien, P06-Messreihe und
Nichtverwechslung von VS1- und P300-RPM.

**Keine** reale Vitotrol wurde durch diese Arbeiten emuliert.
Keine RAM-Writes und kein blinder SFR-/UART1-RX-Leseversuch.
Der produktive `main` bleibt gegenüber diesem Research-Branch unverändert.
