# WB2A/20C2: GWG-C7-Dispatcher erstmals real über den bestehenden Serial-Owner bestätigt

**Datum:** 12. Oktober 2026, 11:08:28–11:08:43 Europe/Berlin. Forschungsbranch `feat/wb2a-vitotrol-rpm-20261010`, Draft-PR #52. **Keine Änderung an `main` und keine Änderung des produktiven `/opt/optolink`-Python-Codes.**

## 1. Ergebnis und exakte Beweisgrenze

**Echter Hardware-Nachweis:** Die über `tools/optolink-apply-gwg-readonly-patch.py` in eine **separate Kopie** der installierten Runtime eingebundenen Module `optolinkgwg.py`, `vs12_adapter.py` und `requests_util.py` haben über genau **ein exklusives** CP2102-Handle sieben lesende KW/GWG-Requests an eine reale WB2A VDensHO1 20C2/0103 übertragen und deren Identitätsantworten erhalten. Der eigentliche Aufruf erfolgte jeweils durch `requests_util.response_to_request(..., shared_serial)`, nicht durch ein isoliertes Testprogramm mit parallel geöffnetem Port.

Belegt ist die Folge **KW → GWG → KW → GWG/8 → KW/8 → GWG/F9 → KW** unter wiederholter `EOT 04 → ENQ 05`-Synchronisierung. Das GWG-C7-Lesetelegramm verwendet nur **ein 8-Bit-Adressfeld**. **Kein CPU-Programm-ROM gelesen, kein 20-Bit-Adressierungs-/Monitorweg bewiesen, keine Vitotrol-Anmeldung.**

## 2. Originäre, kontrollierte Messung

| Schritt | Von `response_to_request` übergebener Request | Gesendeter Datenframe | Echte Antwort (RX) | Ergebnis |
|---|---|---|---|---|
| 1 | `read;0x00f8;4` | `01 F7 00 F8 04` | `20 C2 00 03` | PASS |
| 2 | `gwgread;0xF8;4` | `01 C7 F8 04 04` | `20 C2 00 03` | PASS |
| 3 | `read;0x00f8;4` | `01 F7 00 F8 04` | `20 C2 00 03` | PASS |
| 4 | `gwgread;0xF8;8` | `01 C7 F8 08 04` | `20 C2 00 03 00 00 01 03` | PASS |
| 5 | `read;0x00f8;8` | `01 F7 00 F8 08` | `20 C2 00 03 00 00 01 03` | PASS |
| 6 | `gwgread;0xF9;3` | `01 C7 F9 03 04` | `C2 00 03` | PASS |
| 7 | `read;0x00f8;4` | `01 F7 00 F8 04` | `20 C2 00 03` | PASS |

Alle Frames waren von einem `04`-EOT-Synchronisierungsbyte und einer echten `05`-ENQ-Antwort begleitet. **14 TX-Frames, 7 ENQ-Paare, 41 rohe TX/RX-Ereignisse**, Gesamtdauer 14,497 Sekunden. Es gab **0 Controller-Speicherwrites**. Die 7 Abfragen waren identitätsgebunden; bei einem falschen Byte, unerwartetem Frame, Sync-Timeout oder nicht erreichtem Restaurationsgate wäre der Versuch abgebrochen worden.

**Unverändertes Original-JSON auf dem LXC:**

```text
/tmp/wb2a-gwg-c7-dispatcher-live-20261012.json
SHA256 ee38ef08f950c999ed19da9630e789cc69b1f61642b932be5dca3101a163b824
```

`tools/wb2a-gwg-c7-dispatcher-original-audit.py` prüft das SHA-gepinnte Original, die exakten sieben Befehle, den TX-Whitelist-/EOT-/ENQ-Paarverlauf, sämtliche tatsächlich empfangenen Bytes und die Controller-Read-only-Schranke. Ergebnis: `audit=PASS, reads=7, sync_pairs=7, tx_frames=14, raw_events=41, controller_writes=0`. Das Roh-JSON bleibt privat; nur Prüfer, Tests und diese Ergebniszusammenfassung kommen nach GitHub.

## 3. Sicherheitsfenster und produktiver Nachzustand

- Vor dem Test: Alle fünf produktiven Optolink-Dienste `active`; VS1-ID `20c2000300000103`; aktueller Fehler `0x5738=00`; Vitotrol-Index `0x0A5C=00000000`; Konfiguration-SHA256 `e9a120ef37fe17236a7505ee713c8dd338d98d5093ed75dfb34629d7e8f5c42d`.
- Nur eine private `/tmp/wb2a-gwg-c7-stage-20261012.*`-Runtime-Kopie wurde gepatcht, nicht `/opt/optolink`. Ein einzelner `serial.Serial(..., exclusive=True, 4800,8E2)` transportierte die Frames.
- Vor Stoppen des produktiven Owners: unabhängiger systemd-Wiederherstellungstimer `wb2a-gwg-c7-dispatcher-restore-20261012.timer` **aktiv** (3 Minuten).
- Nur die sechs festen zulässigen TX-Telegramme `04`, `01F700F804`, `01F700F808`, `01C7F80404`, `01C7F80804`, `01C7F90304`. Keine beliebigen Opcodes, kein P300/Bootloader und keine Heizungs-Codierungsänderung.
- Nach exakt 7 Antworten: Exitcode 0; EXIT-Trap ruft unverändertes unabhängiges `/root/wb2a-vitotrol-dual-readonly-20261011/restore.sh` auf; danach Timer deaktiviert.
- Unabhängige Nachkontrolle: **5/5 produktive Dienste active**, `read;0x00f8;8 = 20c2000300000103`, `read;0x5738;1=00`, `read;0x0a5c;4=00000000`, Original-SHA256 identisch, Restore-Timer `inactive`.
- Der gesonderte passive RPM-Recorder `optolink-wb2a-rpm-passive-resume-20261011.service` war **schon vor diesem Test nicht geladen/inaktiv**. Er wurde hier nicht installiert, gestartet oder geändert.

## 4. Staging, Code und Tests

- `tools/optolinkgwg.py`: C7-Virtual-Read, 8-Bit-Adresse, 1–8 Bytes, EOT/ENQ, Timeouts, optional ein Retry, Trace-Hook; kein Write, keine Portöffnung.
- `tools/optolink-apply-gwg-readonly-patch.py`: ausschließlich gegen eine private Stage, Produktionshotpatch ausdrücklich gesperrt.
- `tests/test_gwg_dispatcher_runtime_e2e.py`: E2E im **unveränderten echten Python-Dispatcher und Adapter** (kopierte installierte Runtime-Dateien), per simuliertem Serial-Owner; KW→GWG→KW etc. und ungültige Parameter verursachen keine unbekannten TX.
- `tools/wb2a-gwg-c7-dispatcher-live.py`: strikt gebundener Hardware-Abnahmetreiber mit ext. restore timer, UART-Whitelist und originalem Dispatcherpfad.
- `tools/wb2a-gwg-c7-dispatcher-session.sh`: source-SHA-/Root-/Service-Gates, 3-Minuten-Restore, 75-Sekunden-Live-Timeout, EXIT-Restore, kein Deploy.
- `tools/wb2a-gwg-c7-dispatcher-original-audit.py`: belegtreues vollständiges Rohcapture-Audit.
- `tests/test_wb2a_gwg_c7_dispatcher_original_audit.py`: Positiv- und adversariale Negativfälle; Originalcapture optionaler Test bei Zugriff, SHA-gebundene Rootprüfung ist separat real ausgeführt.

Reproduzierbarkeit:

```bash
cd /home/chatgpt-admin/optolink-vitotrol-rpm-20261010
python3 -m unittest discover -s tests -p 'test_gwg_dispatcher_runtime_e2e.py' -v
python3 -m unittest discover -s tests -p 'test_wb2a_gwg_c7_dispatcher_original_audit.py' -v
sudo python3 tools/wb2a-gwg-c7-dispatcher-original-audit.py
python3 -m unittest discover -s tests -q
```

`sudo bash tools/wb2a-gwg-c7-dispatcher-session.sh --execute` ist **nicht** unbegrenzt wiederholbar: Die erste originale Ausgabedatei existiert bereits, und der Runner verweigert einen zweiten Lauf ohne eine gesonderte, nachvollziehbare Testdefinition.

## 5. Quellengebundene GWG-Opcode-Inventur und ROM-Forschungsentscheidung

Die alten GWG-Zugriffsarten werden in [OpenV Protokoll-GWG](https://github.com/openv/openv/wiki/Protokoll-GWG) beschrieben und durch reale quelltextbasierte Implementierungen zusätzlich bestätigt: [dannerph/esphome_vitoconnect README_GWG](https://github.com/dannerph/esphome_vitoconnect/blob/master/README_GWG.md), [GWG-Treiber](https://github.com/dannerph/esphome_vitoconnect/blob/master/components/vitoconnect/vitoconnect_optolinkGWG.cpp) sowie [SoulSolistice/esphome_vitohome, constants.h](https://github.com/SoulSolistice/esphome_vitohome/blob/main/components/vitohome/optolink/constants.h). Die beiden zuletzt genannten neueren Implementierungen bestätigen **Telegrammformen**, aber sind keine WB2A-ROM-Protokollcapturen.

| Historischer READ-Opcode | Alte Bedeutung | WB2A 20C2 | Relevanz für Programm-ROM |
|---|---|---|---|
| **C7** | Virtual Read | **Live bestätigt**: F8/4, F8/8, F9/3 | 8-Bit virtuelles Fenster, **kein ROM-Gate** |
| **CB** | Physical Read | 6F/1 und F8/1 je 2x **keine Antwort** | Anderer Adressbereich/Zustand möglich, bisher kein ROM |
| **C5** | Physical XRAM Read | 6F/1 und F8/1 je 2x **keine Antwort** | XRAM ≠ Programm-ROM |
| **AE** | EEPROM Read | Noch **kein WB2A-Test** | EEPROM ≠ CPU-Programm-ROM |
| **6E** | Physical Port Read | Noch **kein WB2A-Test** | Portregister, kein belegtes ROM |
| **9E** | Physical BE Read | Noch **kein WB2A-Test** | Bedienteil-Bereich in alten Konfigurationen; kein ROM-Beleg |
| **33** | KM-Bus RAM Read | Noch **kein WB2A-Test** | Eventuell KM-Bus-Forschung, kein ROM-Nachweis |
| **43** | KM-Bus EEPROM Read | Noch **kein WB2A-Test** | EEPROM, nicht Programm-ROM |

Das alte `vcontrold` kennt bei Gerät 2053 z. B. `AE`/EEPROM-Adresse `0x17` und `6E`/Portadresse `0x01`; das beweist keine Nutzbarkeit bei VDensHO1 20C2. `0x33` ist historisch tabelliert, aber es fehlt eine passende Original-2053-vcontrold-Leseanwendung. Daher **keine ungestützten RO-Opcode-Sweeps am laufenden Gaskessel**. Ein Programmspeicherzugang mit effektiver 20-Bit-Adresse `0xE0000..0xFFFFF` braucht eine separate dokumentierte Bank-/Page-, Kopier-/Monitor- oder andere Optolink-Dienstfunktion.

Der historische [OpenV KM-Bus-Bericht](https://github.com/openv/openv/wiki/KM-Bus) von KarlKoch zu 128 KiB M30612MC-Code der V200KW2 macht die Forschung plausibel; seine **Befehlsfolge ist nicht überliefert**. [OpenV #10](https://github.com/openv/openv/issues/10) enthält zwar originalen GWG-C7-Gerätecode, aber keinen erfolgreichen Programm-ROM-Dump. Dieses neue Livefenster erbringt daher die **GWG-Integrationsfähigkeit**, nicht die Original-Firmware.

### Konkreter nächster belastbarer Durchbruch

Ein Originalcapture mit ROM-Bankwahl, tatsächlich ausführbarer Monitor-/RPC-Leseprozedur oder wiederholbar kodierten 20-Bit-Adressen. Erst danach einen kleinen echten Programm-ROM-Abschnitt **zweimal identisch** lesen und M16C-Code-/Vektoren prüfen. Bis dahin zusätzliche historische Quellen und lokale Binary-/VitoSoft-Kommandofunde offline korrelieren. Kein unbekanntes `WRITE`-/Boot-/Flash-/Controller-Reset-Telegramm und kein physischer Eingriff an der laufenden Heizung.
