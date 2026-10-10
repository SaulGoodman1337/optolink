# VS1/P300: Naechste echte Beschleunigungshebel nach dem Hardwaretest

Stand: 2026-10-09. Nur Forschung auf `optolink-handover-acceleration`.
**Kein weiterer serieller Test, keine produktive Integration, keine Aenderung an
`/opt/optolink`, P300-/RPM-Loggern oder Draft-PR #46.**

## 1. Messbare Ausgangslage und Grenzen

Aus dem realen Live-Lauf `run-20261009T190552Z-294681`:

| Getrennte Kategorie | Beobachtete Zeit | Aussagegrenze |
|---|---:|---|
| Ein vollstaendiger VS1 -> P300 -> VS1-Rundweg inklusive vier GFA-Werten | 4666,291 ms | Gemessene einzelne Hardware-Runde |
| ENQ nach EOT Richtung P300 | 2010,961 ms | Host-RX-Zeitpunkt; Ursache nicht isoliert |
| ENQ nach EOT Richtung VS1 | 1998,460 ms | Host-RX-Zeitpunkt; Ursache nicht isoliert |
| Summe ENQ | **4009,421 ms (85,9 %)** | Bei *dieser* Runde ohne Handshake-Aenderung nicht durch Hostcode eliminierbar |
| Alle Nicht-ENQ-Phasen | **656,870 ms** | Umfasst Uebertragung, Controllerantworten und Host; kein frei disponierbares Sleep-Budget |
| Zusaetzlicher VS1-Kaltstart vor der Messung | **4365,844 ms** | Separater Start; NICHT in den 4666 ms enthalten |
| Gemeldete gesamte systemd-Testdienstdauer | **13607 ms** | Vom Benutzer kopiert, inklusive Workerstopp/Restore; keine reine Optolink-Protokollzeit |
| Rest der Testdienstdauer ausser Cold-Start und Roundtrip | **4574,865 ms** | Nicht weiter gemessen/zugeordnet, deshalb KEIN garantierter Einsparbetrag |

Ein unter vier Sekunden liegender vollstaendiger Rundweg kann bei denselben beiden ENQ-Wartephasen selbst mit **null** Zeit fuer alle uebrigen Schritte nicht auftreten: allein 4009,421 ms ENQ-Wartezeit. Das ist eine Untergrenze *dieser Ausfuehrung*, kein Beweis einer unveraenderlichen Firmware-Konstante.

Die historische erfolgreiche n=3-Ein-ENQ-Referenz bleibt 4610,091 ms. Der neue Einzeltest war 56,200 ms langsamer; hieraus folgt kein statistisch abgesicherter Unterschied. Ein-ENQ statt Zwei-ENQ spart bereits real ~2252,889 ms gegenueber 6862,980 ms Baseline. Der Versuch mit natuerlichem ENQ ohne EOT (5628,235 ms) war negativ und ist nicht erneut zu testen.

Ein spaeterer `--health-only`-MQTT-Test bestand mit echten GFA-Antworten P80=20 und P06=00. Die *urspruengliche* Zusammenfassung bleibt korrekt `FAIL_OR_NOT_VERIFIED` wegen des Ausgabeparsers; sie wird nicht umgeschrieben. [Belegdokument](handover-live-result-parser-fix-2026-10-09.md).

## 2. Priorisierte Einsparpotenziale

### A. Ein Prozess, ein schon geoeffneter Port, eine bereits gueltige VS1-Phase

Der neue Standalone-Hardware-Prober musste Originaldienste pausieren,
den Port neu oeffnen und `HandoverCoordinator.__enter__` fuer eine
**zusaetzliche zwei-ENQ-Kaltidentifizierung** ausfuehren: 4365,844 ms.

Der urspruengliche produktive Optolink-Splitter besitzt das Geraet
bereits exklusiv im Hauptloop, und Anfragen von Polling, MQTT und TCP
werden dort seriell ausgefuehrt. Eine *spaetere*, nachweislich korrekte
**In-Process-Integration** koennte deshalb den zweiten Dienstbesitz,
den zusaetzlichen Kaltstart und externe Service-Pausen vermeiden.

**Potenzial:** Der aus der Testausfuehrung separierte Kaltstart ist
~4,366 s; weitere 4,575 s sind bislang nicht auf Funktionen aufgeteilt
und duerfen nicht als garantierte Einsparung verbucht werden.
**Kein Gewinn** fuer die zwei verbleibenden EOT->ENQ-Phasen eines noch
notwendigen einzelnen Protokollwechsels.

**Sicherheitsbedingung:** Nie eine VS1-Sitzung blind uebernehmen. Vor
Uebergabe muss der derzeitige Portbesitzer laufend und eindeutig
VS1-verifiziert sein; Sitzungs-ID, Software 0103, P80=20 und
P06-Provenienz werden nach EOT invalidiert. Bereits laufende
Write+Readback-Sequenzen duerfen nicht unterbrochen werden.

### B. P300-Leseauftraege in einer gueltigen P300-Phase zusammenfassen

Rechnerisch vermeidet jeder tatsaechlich entfallende komplette
Rundwechsel die im letzten Hardwarelauf beobachteten beiden ENQ-Warten
(**4009,421 ms**) und ggf. weitere feste Identifizierungs-/GFA-
Operationen. Beim *identischen* Vier-GFA-Testprofil betraegt der Brutto-
Zeitanteil **4666,291 ms** je ersetzter separater Runde. Diese Zahlen
sind Obergrenzen fuer moegliche Brutto-Ersparnisse gegenueber dem
wiederholten identischen Ablauf, NICHT vorhergesagte neue Hardwarezeiten.

- 3 separate identische Fenster -> 1: 2 Rundwege weniger,
  8,019 s beobachtete ENQ-Anteile bzw. 9,333 s gesamte identische
  feste Rundwege weniger.
- 10 separate identische Fenster -> 1: 9 Rundwege weniger,
  36,085 s ENQ-Anteile bzw. 41,997 s komplette identische Rundwege
  weniger. Die eigentliche Laufzeit zusaetzlicher P300-Leseoperationen
  ist unbekannt und kommt in jedem Fall hinzu.

Unser bisheriger `BoundedReadQueue` benutzt `max_same_mode=4`, was bei
12 unabhaengigen VS1- und 12 P300-ID-Tickets und bevorzugter aktueller
Phase im Modell **drei** P300-Fenster erzeugt. Diese bisherige
Fairnessregel optimiert *Request-Anzahl*, nicht *Wechselkosten*.
Eine neue Policy muss `max_window_ms`, P06-Frischegrenzen,
Deadline/Fairness sowie zusammengehoerige Transaktionen beruecksichtigen,
bevor sie Auftraege neu ordnet. Der neue Offline-Annotator quantifiziert
diese unguenstige Sequenz, nimmt aber **keine** entsprechende
Produktionsaenderung vor.

Wenn echte P06-GFA-Frische **unter 2,1 s** erforderlich ist, laesst sich
nach der gemessenen EOT-Methode **kein** vollstaendiger P300-Ausflug
innerhalb des Budgets unterbringen: schon die ENQ-Warten benoetigten
4,009 s. P09, PWM, RAM oder ein gecachter Wert darf P06 nicht ersetzen.

### C. Die echten EOT/ENQ-Controllerzustaende verkuerzen

**Maximaler Hebel fuer die Latenz einer EINZELNEN realen Runde:**
4009 ms ENQ-Wartezeit im letzten Versuch. Die Host-Latenz einzelner
RX-Bytes wurde im neuen Prober genauer erfasst; daraus folgt aber
noch kein offiziell belegter alternativer Zustandspfad.

Die Originalquellen dokumentieren EOT/ENQ/ACK und `VSManager.ChangeInterface`,
aber keinen bestaetigten `fast-switch`-Befehl fuer diese WB2A. Ein EOT-loser
natuerlicher ENQ-Versuch war bereits langsamer. Ein GFA-C9 unter P300 wurde
bereits abgewiesen. **Keine** erfundenen Sequenzen oder erneuten
Wiederholungsversuche.

### D. Rein softwareseitige Pausen reduzieren

`ReadOnlyWire.gap()` garantiert derzeit 25 ms zwischen Telegrampaketen;
`quiet()` prueft 10 ms auf spaete RX-Bytes; leere Reads nutzen 1-ms-Polling.
Die historischen Vier-GFA-Abfragen dauerten 414,499 ms, im neuen
Test die *restlichen zwei* GFA-Reads 195,532 ms. Diese Werte belegen
kein beliebig kuerzbares Zeitbudget; insbesondere P80-Gate, P06-Rohwert,
Antwortvollstaendigkeit und FF-Retry duerfen nicht geopfert werden.

Selbst das **unrealistische** vollstaendige Entfallen aller 656,870 ms
Nicht-ENQ-Arbeit liesse bei den gemessenen zwei ENQs noch 4009,421 ms.
Damit sind Python-Sleep- und USB-Feinoptimierungen kein Weg zu <4 s
fuer dieselbe vollstaendige Runde.

## 3. Ergebnis: technische Entscheidung und naechster Integrationsschritt

1. **In-Process-Single-Owner ist die Vorzugsarchitektur**, kein zweiter
   serieller Dienst und kein Komplettfork als vermeintliche Beschleunigung.
2. Zunaechst einen **hardwarelosen Integrations-Spike** am originalen
   Dispatcher entwerfen: langlebige explizit verifizierte VS1-Session,
   atomare Anforderung, bounded P300-Window, Status-/Frischeledger,
   Rueckkehr zu echtem VS1-P06 und bewahrte Readback/Writersperren.
3. Eine neue kostenbewusste, GFA-frische- und deadlinekonforme Scheduler-
   Policy mit komplett virtueller Event-Uhr testen. Die bestehende
   `max_same_mode=4`-Policy nicht unbesehen produktiv uebernehmen.
4. Erst wenn aus Quellen ein *neuer*, physikalisch plausibler und sicherer
   Zustandsuebergang folgt, einen **einzelnen** neuen, gesondert
   freizugebenden Hardwareversuch begruenden. Bis dahin keine
   Wiederholung der bestaetigten EOT+Ein-ENQ-Messung.

## 4. Exakt dieselben alten Messdaten auswerten, ohne Hardwarezugriff

Nach Checkout dieses Forschungsbranches:

```sh
python3 tools/handover_acceleration/speed_audit.py \
  --session /root/p300-trial-work/handover-acceleration-live-results/run-20261009T190552Z-294681 \
  --service-runtime-ms 13607 --vs1-reads 12 --p300-reads 12 --max-same-mode 4
```

Das Skript liest nur `measurement.json` und optional `summary.json`,
oeffnet **kein** serielles Geraet, baut kein MQTT und stoppt keine Dienste.
Seine Bruttoeinsparungen sind kontrafaktische, explicit bedingte
**Scheduling-Moeglichkeiten**, keine neu nachgewiesenen Zeitmessungen.

### Belege

- Eigene Host-Messung und Health-Check:
  [Hardware-Audit](handover-live-result-parser-fix-2026-10-09.md)
- [Quell-Audit und vollstaendige historische Zeitzerlegung](handover-acceleration-research-2026-10-09.md)
- [Optolink Hauptloop und in-process Integrationsnaht](handover-dispatcher-integration-audit-2026-10-09.md)
- [OpenV Protokoll 300](https://github.com/openv/openv/wiki/Protokoll-300)
- [Upstream UART und init](https://github.com/philippoo66/optolink-splitter/blob/c1ee204a1421447721603c5f21c6da7337fdac97/optolinkvs2.py)
