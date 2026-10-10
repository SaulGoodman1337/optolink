# WB2A: drei reale kontinuierliche VS1/P300/VS1-Handover bestanden

**10. Oktober 2026, ca. 11:58 bis 12:02 CEST.**
Forschungszweig: `optolink-handover-acceleration`, Root-Release **premerge-20261010-g**.
System: `optolink-splitter` LXC / Vitodens 200 WB2A / Optolink.
**Keine produktiven Quelldateien unter `/opt/optolink` überschrieben, kein GitHub-Merge.**

## Abnahmeergebnis

Unabhängig von der entwickelnden Sitzung ist der zeitlich begrenzte
`optolink-hybrid-continuous-canary.service` mit **Exitcode 0** und
`HYBRID_CONTINUOUS_RESULT.result=PASS` beendet worden. Dokumentierte,
separat datierte echte Hardwarefenster (aus Original-Hauptdienst-Journal):

| Zeitpunkt (CEST) | Batchdauer (ms) | P300-FC01-ID | P300 FC03 0F20/32 | P300 FC03 1C60/32 | VS1-GFA P80/P06 |
|---|---:|---|---|---|---|
| 11:59:58 | 5515.421 | 20c2 | 32 Bytes gültig | 32 Bytes gültig | 20/00 |
| 12:01:04 | 5497.709 | 20c2 | 32 Bytes gültig | 32 Bytes gültig | 20/00 |
| 12:02:09 | 5437.079 | 20c2 | 32 Bytes gültig | 32 Bytes gültig | 20/00 |

Der Hauptprozess blieb durchgehend der einzige serielle Besitzer und gab den
Port zwischen den P300-Fenstern vollständig für die echten VS1-Polls, MQTT/TCP
und die fünf kooperativ registrierten Writer frei. Ein expliziter read-only
Original-VS1-Identitäts-Read unmittelbar vor jedem P300-Deadline ersetzt den
unter Dauerpolling unterdrückten separaten KW-Keepalive.

Alle fünf unabhängigen Writer (**Party, Schedule, Serviceprogramme,
Maintenance, Clock-Sync**) waren in einem root-eigenen,
SHA256-gebundenen Enrollment-Manifest und durch laufende Systemd-Prozesse
nachgewiesen. Ihr mehrstufiges Write/Readback/Restore wird durch einen
gemeinsamen kernel-`flock` einschließlich persistierter Crash-Marker
atomar gehalten. Verspätete HA-/set-Readbacks und MQTT/TCP-Ingress werden
im Hauptprozess erfasst und während P300-Lesefenstern blockiert oder gepuffert.

## Root-owned Release und Testbelege

- Staging-Quelle: `/home/chatgpt-admin/optolink-hybrid-candidate-20261010-g`.
- Aktivierte, geschützte Quelle: `/var/lib/optolink-hybrid/releases/premerge-20261010-g` (**39** generierte, hashgepinnte Dateien).
- Root-CANARY-Session:
  `/var/lib/optolink-hybrid/canary-sessions/run-20261010T095832Z-308062`.
- `continuous-measurement.json`: `PASS_THREE_VERIFIED_CONTINUOUS_WINDOWS`,
  `event_count=3`, `live_producer_attested=true`, initial und abschließend
  echte VS1-GFA P80/P06 jeweils `20/00`.
- `recovery.json`: `PASS_ORIGINAL_SERVICES_RESTORED`, keine Fehler,
  echte GFA nach Restore `20/00`.
- `/tmp/optolink-continuous-canary-G-real-20261010.log`:
  `HYBRID_CONTINUOUS_RESULT.result=PASS`, `run_rc=0`,
  `Service runtime=3min 50.547s`.
- Letzte Offline-Gesamtsuite vor dem G-Canary: **490/490 PASS**
  auf Debian 13 / Python 3.13.
- Tatsächlicher serial-leasing-Owner `optolink:optolink`, Modus `0600`
  unter `/var/lib/optolink-hybrid/serial.lease`.

### Nachweis des reversiblen Systemd-Rollbacks

Nach CANARY-ENDE:
- `optolink-splitter.service`, Party, Schedule, Maintenance und ServicePrograms
  alle `active`; Clock-Sync-Timer `active`; Pumpenoverride `inactive`.
- Sämtliche sechs hybriden Systemd-Dropins und die zusätzliche
  Auto-CANARY-Einstellung entfernt.
- Root-Enrollment-Manifeste gelöscht.
- Persistenzmarker in `/var/lib/optolink-hybrid/producer-epoch.lock` leer.
- Normale MQTT-GFA P80/P06 auch unabhängig nach der Wiederherstellung lesbar.
- Original `/opt/optolink/optolinkvs2_switch.py` unverändert.

### Behobene Abnahmeblocker

1. Quellenprüfung der Maintenance-API verwendet ihren eigenen Patch-Marker.
2. Bei kontinuierlicher VS1-Pollung ersetzt frische Original-Gerätekennung
   `20c2` den nicht automatisch ausgelösten Keepalive.
3. Der unabhängige Monitor toleriert ein echtes `P300_ACTIVE` maximal
   zwölf Sekunden, nur bei unveränderter Hauptprozess-PID, nicht aber
   `P300_FAILED`.
4. Der Port-Lease-Inode wird VOR dem Hauptprozess als `optolink:optolink 0600`
   provisioniert, nicht im root-verwalteten, für Gruppe schreibgeschützten
   Verzeichnis von einem Unprivilegierten nachträglich angelegt.
5. Sämtliche FAIL-CLOSED-Canarys stellten den echten VS1-Betrieb wieder her,
   bevor sie den P300-Fehlermarker löschten.

## Noch offene Langzeit-/Merge-Freigabeschranken

Drei erfolgreiche Fenster belegen funktionierendes automatisches
Ein-Port-Protokollswitching und einen unabhängigen Wiederherstellungsweg.
Es ist **kein** mehrstündiger unbeaufsichtigter Stabilitätsnachweis und
**kein** realer Boiler-Parameter-Write unter gleichzeitigem Hybrid-Fenster.
Für dauerhaften aktiven Produktivbetrieb sind zusätzlich ein länger laufender
Watchdog-/Soak-Test, Readback-Latenzen unter realer MQTT-/TCP-Schreiblast,
Restart-/SIGKILL-Failure-Injection sowie ein dokumentierter,
administrativ unabhängiger Deaktivierungsbefehl sinnvoll. Es werden weder
freie RAM-Adressen noch produktive Heizungs-Overrides freigeschaltet.

Der GitHub-Draft-PR #48 darf **erst nach ausdrücklicher Betreiberfreigabe**
gemergt werden.
