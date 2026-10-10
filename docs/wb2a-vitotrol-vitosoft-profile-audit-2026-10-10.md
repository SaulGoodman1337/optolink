# WB2A / 20C2: SHA-geprüfter VitoSoft-Profilaudit für Vitotrol

**Stand 10.10.2026. Offline-only, Optolink-only, kein Hardware-Eingriff.**

## Quellen und Zuordnung

Der statische Auditor `tools/wb2a-vitotrol-vitosoft-static.py` untersucht die lokal vorhandenen Original-Exporte und folgt der realen Geräteverknüpfung statt nur Zeichenketten zu zählen.

| Quelle | SHA256 |
| --- | --- |
| `DPDefinitions.xml` (186.559.004 Bytes) | `efec27568d398021c767771af016143bd51fc196d2d408dbb80faff84d0b19e3` |
| `ecnEventType.xml` | `2338beb0e8544b6149bc4b2433ecabd9509edcdafc2e8e91f00182eba1aff7ba` |

Der Join lautet: `ecnDatapointType(Id=60, Address=VDensHO1)` -> `ecnDataPointTypeEventTypeLink(DataPointTypeId=60)` -> numerische `ecnEventType/Id` -> voller Eventalias -> exakter `EventType/ID` in `ecnEventType.xml`. Fehlende oder mehrdeutige Treffer führen zum Testfehler.

## Resultat für genau VDensHO1

| Ereignistyp | Anzahl |
| --- | ---: |
| Exakt verknüpfte Eventdefinitionen | **581** |
| `Virtual_READ` | 462 |
| `GFA_READ` | 94 |
| `Remote_Procedure_Call` (lesen) | 22 |
| Leseaktion `undefined` | 3 |
| `Virtual_WRITE` | 182 |
| `Remote_Procedure_Call` (schreiben) | 22 |
| Schreibaktion `undefined` | 377 |
| Exakt profilierte `XRAM_WRITE`, `KBUS_TRANSPARENT_WRITE`, `KBUS_DIRECT_WRITE` | **0** |
| Profilalias `KMBUS_RECEIVE`, `UART1_RX`, `Vitotrol_Inject` | **0** |

Die Summen sind Eventdeskriptoren des Hostkatalogs, **keine** bewiesenen oder ausgeschlossenen MCU-Funktionen.

### Relevante Fernbedienungsobjekte

| Adresse | Exakter Profilalias | Lesen | Schreiben im Host-Katalog |
| --- | --- | --- | --- |
| `0x27A0` | `KA0_KennungFernbedienungA1M1`, `KA0_KonfiKennungFernbedienungA1M1` | `Virtual_READ` | `Virtual_WRITE` |
| `0x0A5C` | `SWIndex_FB1` | `Virtual_READ` | `undefined` |
| `0x0896` | `TiefpassTemperatur_RTS_A1M1` | `Virtual_READ` | `undefined` |
| `0x089C` | `HO2B_SensorStatus_RTS_M1` | `Virtual_READ` | `undefined` |
| `0x1642` | Kein VDensHO1-Profilereignis | – | – |

Die Bytefolge `0x1642` tritt zwar auch im *globalen* DP-Katalog im Namen `WPR_Heizwaerme03~0x1642` auf. Das ist **kein UART1-RX-Nachweis und keine gesicherte Verbindung** zum gleichnamigen physikalischen RAM-Kandidaten.

`XRAM_WRITE` steht nur als Option im globalen Dropdown-Katalog, **nicht** als exakt auf VDensHO1 verknüpfter Aufruf. Auch die 22 vorhandenen RPC-Ereignisse liefern keinen beschriebenen KM-Bus-Empfangs-/Vitotrol-Inject-Service. Fehlende Host-Eventdefinitionen schließen technisch eine undokumentierte ROM-Routine aber **nicht** aus.

## Reproduzierbare Offline-Tests

```bash
cd /home/chatgpt-admin/optolink-vitotrol-rpm-20261010
python3 tools/wb2a-vitotrol-vitosoft-static.py \
  /home/chatgpt-admin/research/vitosoft-lfs/DPDefinitions.xml \
  /home/chatgpt-admin/research/vitosoft-lfs/ecnEventType.xml
python3 -m unittest discover -s tests -p 'test_wb2a_vitotrol_vitosoft_static.py' -q
python3 -m unittest discover -s tests -p 'test_*.py' -q
```

Der Test prüft auf dem Forschungs-LXC die kompletten SHA-gepinnten Originaldaten. CI ohne die privaten großen VitoSoft-Dateien benutzt kleine synthetische Verknüpfungen und testet ausdrücklich, dass `XRAM_WRITE` oder `KBUS_*` aus einem anderen Geräteprofil nicht fälschlich als VDensHO1-Funktion erscheinen. Die originalen Exporte werden nicht in GitHub hochgeladen.

## Offenes technisches Gate

Benötigt werden weiterhin ein **20C2-spezifischer UART1-RX-ISR/Parser-/State-Commit-Nachweis** und ein **sicherer Optolink-intern erreichbarer Einspeisedienst**. Nur dann lässt sich aus den bereits bytegenau rekonstruierten Original-V300-Slaveantworten eine echte WB2A-Vitotrol-Emulation bauen. `0x1642` als physischer RX-Puffer, ein eventueller Deskriptor bei `0x0B6D` und sonstige Offsets bleiben Hypothesen.

**Während dieses Audits:** Keine Controllerwrites, keine Raumführung, keine neuen P300-Fenster, keine Veränderung des produktiven VS1 oder des passiven RPM-v2-Loggers. Bestehender PR #52 bleibt Draft.
