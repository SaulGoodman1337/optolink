# WB2A Vitotrol: Offline-Abnahmepruefer

Stand: 10.10.2026. **Entwicklung nur ueber Optolink/P300**, PR #52 bleibt Draft. Der produktive VS1-Dienst, die `update`-Kette von `main` und der passive RPM-v2-Logger werden nicht veraendert.

## Implementiert und getestet

Der neue rein synthetische Abnahmepruefer `tools/wb2a-vitotrol-acceptance-offline.py` wertet **keine echten Controllerdaten** aus. Er nimmt ausschliesslich explizite `synthetic_offline`-JSON-Fixtures fuer `VDensHO1 / 20C2 / 0103 / HK1` entgegen. Kein Zugriff auf serielle Geraete, GPIO, Optolink, MQTT, systemd oder Controller-RAM; keine Codierungs- oder Heizungsaktionen.

Der Test prueft in zeitlicher Reihenfolge:

1. **Baseline**: `0x27A0=00`, `0x0A5C=00000000`, keine aktuelle BC-Stoerung, frische Readbacks.
2. **Armed**: unveraenderte Register und weiter intakte VS1-Verifikation.
3. **Active** (nur simuliert): mindestens vier zeitlich getrennte Abfragen, mindestens zwei unterschiedliche nichtfallback Raumtemperaturziele jeweils doppelt bestaetigt, stabiler Nichtnull-Fernbedienungsindex und veraenderter Sensorstatus.
4. **Restored**: Originalwerte von `0x27A0`, `0x0A5C`, `0x0896`, `0x089C` wiedergefunden.
5. **Postcheck**: mindestens zwei Messungen; letzte mindestens 30 Sekunden nach Restored; weiterhin Originalwerte.

Strikte Abbrueche: BC irgendwann aktiv, geaenderter BC-Fehlerhistorienzaehler/Fingerprint, andere Controllerstoerung, ungueltiges VS1-Readback, aktivierte Raumaufschaltung, erzwungene Pumpen-/Brenneraktionen, veraltete oder fehlende Werte, unvollstaendiger Rollback, instabile Fernbedienungskennung, zu wenige Temperaturwechsel oder fehlerhafte Testdaten.

Zeitgrenzen gelten **nur fuer das kuenstliche Testszenario**: 180 Sekunden gesamt, 90 Sekunden angenommene aktive Phase, 5 Sekunden maximales Readback-Alter. Dies sind keine nachgewiesenen UART1-/KM-Bus-Timing-Anforderungen.

## Reproduzierbare Tests

```bash
cd /home/chatgpt-admin/optolink-vitotrol-rpm-20261010
python3 tools/wb2a-vitotrol-acceptance-offline.py tests/fixtures/wb2a-vitotrol-acceptance-synthetic-pass.json
python3 tools/wb2a-vitotrol-acceptance-offline.py tests/fixtures/wb2a-vitotrol-acceptance-synthetic-bc-fail.json
python3 -m unittest discover -s tests -p 'test_wb2a_vitotrol_acceptance_offline.py' -q
python3 -m unittest discover -s tests -p 'test_*.py' -q
```

Positives **synthetisches** Szenario: `OFFLINE_SCENARIO_PASS`, CLI-Exit 0. Negatives synthetisches Szenario mit kurzzeitigem BC: `OFFLINE_SCENARIO_FAIL`, `CURRENT_BC_FAULT_OBSERVED`, CLI-Exit 2. Beide melden zwingend `live_hardware_authorized=false` und `tested_controller=false`. Ein bestandenes Offline-Szenario ist **niemals** eine reale Hardwarefreigabe.

Die Beispielwerte `0x0A5C=01000000` und `0x089C=00` waehrend einer simulierten Aktivierung sind hypothetisch, keine real verifizierte Vitotrol-Akzeptanz. Historisch wurde `0x0896` per Virtual_WRITE abgewiesen und `0x089C` durch die Reglerlogik ueberschrieben. Eine BC-freie Codierung allein beweist keine funktionsfaehige Vitotrol.

## Technische Gates vor jedem spaeteren Live-Versuch

Weiterhin nicht nachgewiesen: der **exakte 20C2-UART1-RX-Parser und State-Commit**, ein kontrollierter **Optolink-interner RX-Injektionsservice**, Atomizitaet und Recovery der internen Puffer, **unabhaengige Rueckstellung der Heizungs-Codierung**, unabhaengige BC- und Fault-History-Beobachtung sowie ein betreutes Zeitfenster ohne Beeintraechtigung der laufenden RPM-Forschung.

Das bestehende VS1/P300-Systemd-Recovery stellt die serielle Originalkommunikation wieder her. Es garantiert **keinen** Rollback einer experimentellen Controller-Codierung. Fuer einen spaeteren Test muss ein solches unabhängiges und verifiziertes Codierungs-Recovery **zusaetzlich** existieren.

**Nicht ausgefuehrt:** Aktivierung von `0x27A0=01`, RAM-/SFR-Writes, KM-Bus-Telegramminjektion oder Raumaufschaltung. Ohne belegten Empfangspfad wuerde eine solche Wiederholung lediglich den historischen BC-Fehler riskieren.

## Research-Bezuege

- [Original-Vitotrol-300-Antworten](wb2a-vitotrol-optolink-emulator-profile-2026-10-10.md)
- [P300-RX-Kandidat 0x1642](wb2a-vitotrol-optolink-rx-2026-10-10.md)
- [Zeit-/CRC-/RAM-Xref-Beweisgrenzen](wb2a-vitotrol-optolink-rx-context-2026-10-10.md)
- [Bestehendes verifiziertes Read-only-Demand-Recovery](wb2a-root-on-demand-api-2026-10-10.md)

## Nachtrag: VitoSoft-Hostkatalog als unabhängiges Recherche-Gate

Der [VitoSoft-Profilaudit](wb2a-vitotrol-vitosoft-profile-audit-2026-10-10.md)
belegt fuer das Profil VDensHO1 **581** Eventdefinitionen und **22**
RPCs, aber **keinen** genau zugeordneten KM-Bus-RX-Injektions- oder
XRAM_WRITE-Aufruf. Die Herkunft aus dem globalen Dropdown-Katalog
reicht dafuer nicht aus. Der vollstaendige Live-Abnahme-Blocker
bleibt deshalb bestehen: ohne belegten Optolink-RX-/State-Commit
und unabhaengigen Codierungs-Rollback kein Hardware-Schreibversuch.
