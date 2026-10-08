# P06/P09 gegen native Steuerwerte: naechster begrenzter VS1-MQTT-Vergleich

Stand 2026-10-08, Werkzeug `wb2a-gfa-native-pair-check.py` 1.0.0.
**Implementiert und offline getestet. Hardware-Ergebnis noch ausstehend.**

## Fragestellung

Die vollstaendige Auswertung von 807 P300-Antworten zeigt dynamische Byte0/Byte9-
Verlaeufe, aber keine zeitgleich erhobene GFA-P06/P09-Zeitreihe. Diese Werte sind
nicht neu als Drehzahl entdeckt: Byte0 ist bereits eine Ansteuerdiagnose, Byte9
ein Modulationskanal. Der neue Vergleich sammelt eine nachvollziehbare
Same-Session-Referenz. Er erzwingt keine Drehzahl-/Prozentinterpretation und
ersetzt keinen bestehenden HA-Sensor.

## Vorbedingungen und Vorbereitung

Als root in der Optolink-LXC. Originales VS1 laeuft. Alte CANARY-, Handover-,
P87-MQTT- und P300-only-Versuche beendet. Kein Wartungs-/Serviceprogramm und
keine gleichzeitigen Updates oder Diagnoseclients fuer diese Adressen.
Normale Produktion und HA bleiben aktiv. Kein Stager, kein produktives update,
keine Kopie nach `/opt/optolink` oder in den alten Kandidaten.

Den im zugehoerigen Abschlusskommentar genannten Commit per Fast-forward holen,
lokale Aenderungen nicht ueberschreiben. Danach:

```bash
cd /root/p300-trial-work/project
/opt/optolink/venv/bin/python -m unittest discover -s tests -p test_gfa_native_pair_check.py -v
/opt/optolink/venv/bin/python tools/wb2a-gfa-native-pair-check.py
```

Erwartet: 23 erfolgreiche Tests und
`PLAN ONLY: P80 -> P06 -> P09 -> 55D3/11 -> P09 -> P06.`
Ohne execute keine MQTT-Verbindung, Diensteabfrage oder Ergebnisdatei.
Helperhash: `2d50024f9418f4ba72170c28e3aa08a23e7a4929654e8e9b7196296cef6ea914`.

## Ein Beobachtungsfenster

Am aussagekraeftigsten sind natuerliche Anlauf-, Regel- und Auslaufphasen.
**Keine Sollwert-/Betriebsartaenderung zum Erzwingen eines Starts.**

```bash
/opt/optolink/venv/bin/python -u \
  /root/p300-trial-work/project/tools/wb2a-gfa-native-pair-check.py \
  --execute --seconds 600
```

Dauerargument 30..900 s, Standard 600. Verbindung, offene Reads und Abschluss
kommen hinzu. Ein Read hat die bestehende achtsekundige Antwortfrist. Kein
Retry/Reconnect im Beobachter; die vorhandene Produktions-GFA-Behandlung bleibt.
Rundenstartabstand mindestens fuenf Sekunden, kein Nachhol-Burst.

Der Client sendet auf dem bestehenden MQTT-Kanal nur folgende sechs
Kommandotypen: virtuelle Reads 00F8/2, 778C/2 und 55D3/11; GFA-Reads P80, P06,
P09 mit je einem Byte. Pro Runde P80 und fuenf eingerahmte Reads. Es gibt kein
C9, kein RAM, keine Schreibkommandos, keinen seriellen Zugriff und keinen
Dienststopp. Das normale Polling bleibt aktiv; der Zusatzverkehr kann seine
Aktualitaet/Latenzen beeinflussen. Bei Stoerung den Beobachter stoppen.

Der geteilte MQTT-Antwortkanal hat keine Request-ID. Retain wird ignoriert;
Echo, Adresse, Laenge, Status und beobachtete Kollisionen werden kontrolliert.
Gleichzeitige andere Diagnoseclients auf denselben Adressen bleiben verboten;
keine vollstaendige Zuordnungsgarantie in jedem denkbaren Rennen.

## Bedeutung der Ausgaben

P06/P09 `before`/`after` sind Hexstrings. Native b0/b9 sind **Dezimal-Rohwerte**.
Nicht direkt als gleiche Prozent-/RPM-Einheiten vergleichen.

- `STABLE_REFERENCE`: gleicher GFA-Wert vor/nach dem nativen Block, Abstand
  der empfangenen Referenzen hoechstens zwei Sekunden.
- `REFERENCE_CHANGED`: vor/nach verschieden, dynamischer Verlauf; keine
  feste Paarzuordnung fuer diesen Kanal behaupten.
- `BRACKET_TOO_WIDE`: gleicher Wert, aber zu grosse Zeitklammer.

`PAIRS_RECORDED_NEEDS_ANALYSIS` heisst nur: Fuer beide Kanaele liegt wenigstens
ein stabiler Nichtnullbezug vor. Es bedeutet **weder ausreichende Zustandsvielfalt
noch eine gefundene Alias-/Umrechnungsfunktion**. Alles statisch null ergibt
`INCONCLUSIVE_REFERENCE_COVERAGE`. Fehler/Abbruch ergeben `INCOMPLETE_OR_FAILED`.
Gleiche Endwerte schliessen versteckte A->B->A-Bewegungen nicht aus.

Der Bericht zaehlt auch stabile Paare, in denen P06-Rohwert und P09-Rohwert
verschieden sind. Dies beweist keine gemeinsame Einheit beider Codes; es
kennzeichnet nur Vergleichssituationen, die zur Trennung von Ist und Soll
interessant sind. Keine Produktionsfreigabe, kein neuer Skalierungsfaktor.

## Ende und Dateien

Strg+C beendet nur diesen MQTT-Beobachter. **Kein Rollback noetig**, da weder
Protokoll, Dienste noch Parameter veraendert werden. Nicht die alten
Systemd-Abbruchbefehle verwenden. Angefangene Daten bleiben gespeichert.

`SESSION` liegt unter `/root/p300-trial-work/gfa-native-pairs/run-...`.
`pairs.jsonl` und `summary.json` enthalten rohe Referenzen, die ganzen 11 Bytes,
Hostzeitstempel, Fehler und Analysegrenzen. Dateien privat, keine MQTT-Zugangsdaten.
Bitte beide Dateien fuer die naechste Auswertung bereitstellen; kurze
Konsolenzeilen ersetzen hier gerade nicht die vollstaendigen Referenzdaten.

Nach dem Ende, nicht parallel:

```bash
optolink-debug request 'gfaread;0x4050;1;raw;False' --timeout 8
optolink-debug request 'gfaread;0x4006;1;raw;False' --timeout 8
```

P80=20/Status1, gueltige P06-Antwort und frische normale HA-Werte pruefen.
Bei Fehlern nicht unveraendert wiederholen; Bericht behalten.

## Verifikation und Quellen

23 neue Offline-Tests: Rohwerttrennung, Referenzklammern, FF-Abbruch, feste
sechs Kommandos, exakte Rundenreihenfolge, Kollision, Retain, No-op-Plan,
Helperhash, Grenzen und ein simulierter Gesamtlauf. Der vorhandene Helper
bleibt bytegleich; seine eigenen 33 Tests bleiben erhalten.
[Quelle und Vollmessung](p300-full-status-byte-audit-2026-10-08.md),
[Implementierung](../tools/wb2a-gfa-native-pair-check.py),
[Tests](../tests/test_gfa_native_pair_check.py).
