# WB2A: Dispatcher-Seam und feste FC03-Diagnose-Leseblöcke

**Stand:** 2026-10-09; Forschungsbranch `optolink-handover-acceleration`; **nur offline und CI geprüft**. Produktionsdateien unter `/opt/optolink`, Git-Branch `optolink-p300-migration`, Draft-PR #46 sowie laufende Logger wurden nicht verändert. Die hier ergänzte Codepfad-Verifikation öffnet **keinen** seriellen Port und stoppt keine Dienste.

## Was jetzt tatsächlich implementiert ist

1. `dispatcher_bridge.py`: eine gemeinsame Main-Thread-Grenze, in der vorhandene Polling-, MQTT- und TCP-Aufrufe unverändert an `requests_util.response_to_request(...)` delegiert werden. Rückgabeformat und Ausnahmen bleiben gleich; auch `write`, `writeraw`, `raw`, GFA, normale Reads und die bestehenden Readback-Aufträge bleiben im originalen Dispatcher. Das gleiche Portobjekt ist zwingend; andere Handles, reentrante Frames und fremde Threads werden abgewiesen. Ein expliziter `legacy_transaction()`-Kontext kann zusammengehörige Write-/Readback-Aufträge gegen Wartungswechsel sperren.
2. `HandoverCoordinator.borrow_existing_vs1(...)`: übernimmt **dasselbe schon geöffnete** Portobjekt und verifiziert aktuell per bekannten VS1-Reads die Gerätekennung `20C2`, Software `0103`, GFA P80=`20` und gültiges echtes P06, **ohne EOT/Kaltstart und ohne den Port bei `__exit__` zu schließen**. Das ist eine unbestätigte Live-Integrationsannahme: die echten F7/GFA-Antworten bei einer laufenden, bereits synchronisierten VS1-Session wurden nur am Fake-Port getestet. Der bestehende unveränderte `HandoverCoordinator`-Kaltstart bleibt getrennt erhalten.
3. `phase_executor.py`, `scheduler.py` und `coordinator.py`: unter **identitätsgeprüftem** P300 neben FC01/00F8-Identität exakt zwei zuvor am WB2A physisch verifizierte P300-FC03-Snapshots (`0x0F20/32` und `0x1C60/32`); keine freie RAM-Adresse, kein beliebiger Funktionscode, kein GFA-Ersatz und keinerlei Write. Exakter TX-Frame, FC, Adresse, 32-Byte-Länge, Checksummen und ACK werden geprüft. Ein Batch mit zwei FC03-Blöcken und P300-ID benötigt im Offline-Fake-Transport nur eine P300-Einstiegs- und eine VS1-Rückkehr-ENQ. GFA P06 bleibt ein reales VS1-GFA-Sample und wird bei Umschaltung invalidiert.
4. `dispatcher_patch.py`: erzeugt **ausschließlich eine Kopie** eines vorhandenen Hauptloops; er ersetzt genau drei `requests_util.response_to_request()`-Call-Sites durch `handover_legacy_or_shim(...)` und verweigert abweichende Quellen. Die zusätzlich importierte Bridge wird nur bei gesetztem `OPTO_RESEARCH_DISPATCH_SHADOW=1` und eindeutigem VS1-Originalprofil aktiviert; **dort bleibt `allow_maintenance=False`**. Die aktuell aus der Mainloop weitergeleiteten Writes bleiben 100% Altverhalten. `--source` und `--output` dürfen niemals dieselbe Datei sein. In CI wird der alte Upstream `philippoo66/optolink-splitter@c1ee204...` via unveränderter Blob-SHA `1fae36ba...` geprüft, dann ein generierter Source-Copy kompiliert.

## Warum trotzdem noch keine Produktionsfreigabe besteht

Die bestehende Splitter-Hauptschleife, `vs12_adapter` und `optolinkvs1` haben interne VS1-Sync-/Keepalive-Zustände, die erst an einer gemeinsamen Transaktionsgrenze konsistent geführt werden müssen. Ebenso sind externe **mehrere MQTT-Nachrichten umfassende** Schreib-/Readback-Abläufe in der HA-Anwendung bisher nicht an den neuen `legacy_transaction()`-Kontext angebunden. Eine über mehrere MQTT-Aufträge reichende Transaktion darf nicht von einer P300-Diagnosephase unterbrochen werden. Der Produktions-Lifecycle und ein unabhängig wirkender In-Process-Restore müssen noch auf den neuen geliehenen Port getestet werden. Vorher ist das `allow_maintenance=True`-Interface ausschließlich ein Fake-Port-Integrationsnachweis und keine fertige Produktivschaltung.

Der ursprüngliche serielle Hardwaretest (4,610 s Ein-ENQ-Mittel) bleibt ein unabhängiger Beleg. Das Auslassen des **separaten, kalten Zwei-ENQ-Setups** kann die rund 4,3-s-Dienst-Einmalkosten potenziell entfernen, **verkürzt aber nicht die gemessenen rund 4,6 Sekunden eines bereits laufenden VS1↔P300-Rundwechsels**. Mit zwei vollständigen FC03-Snapshots in einem einzigen P300-Fenster spart der Planer nur zusätzliche sonst nötige Rundwechsel. Die 2-s-ENQ-Phasen sind weiterhin im realen Kessel sichtbar; Early-P300 und Early-VS1 innerhalb 350 ms wurden bereits negativ getestet und sind hier nicht wiederholt worden.

## Testplan, Grenzen und nächster Integrationsschritt

Alle Tests per `python -m unittest discover -s tests -p 'test_handover*.py' -q`. FC03-Golden-Wire-Nachweise umfassen die exakten Ausgangstelegramme und gültige bzw. ungültige Antworten; bei CRC/Funktions-/Adressfehlern folgt ein konservativer VS1-Restore, falsche Parameter werden vor TX abgewiesen. Batch-/Bridge-Nachweise umfassen dieselbe Portidentität, Mainthread-Besitz, Write-/Readback-Barrieren, Erhaltung sämtlicher Altantworten, abschließende VS1-Frische sowie Verbote für unbekannte Datenpfade. Für die neue Direktintegration wird in CI außerdem der originale, gegengepinnte Hauptloop **als Kopie** gepatcht und kompiliert.

**Nächste konkrete Entscheidung:** Das Shadow-Seam-Layout mit der produktiv angepassten `/opt/optolink/optolinkvs2_switch.py` vergleichen und sämtliche externen Write-/Readback-Transaktionen katalogisieren; erst anschließend echten P300-Wartungsdispatch freischalten. Der nächste LXC-Test für diesen Schritt darf ausschließlich `dispatcher_patch.py --source /opt/optolink/optolinkvs2_switch.py` im Prüfmodus aufrufen: keine Systemd-Änderungen, keine Ports, keine MQTT-Transaktionen.

## Live-Checkout-Kompatibilität ohne Hardware- oder Dienstzugriff

Die zusätzliche `dispatcher_runtime_audit.py` prüft ausschließlich die drei
Python-Quellen `optolinkvs2_switch.py`, `requests_util.py` und `vs12_adapter.py`
aus dem bestehenden `/opt/optolink`-Verzeichnis. Der Test importiert sie **nicht**
und liest **keine** `settings.*`, Anmeldedaten, Systemd- oder serielle Geräte.
Er gibt nur einen Quellhash, Call-Site-Zähler, GFA-/Write-Fähigkeitsflags und
`shadow_source_copy_supported` als JSON aus. Bei abweichendem Hauptloop ist
das ein dokumentierter Grund, die Patch-Generierung nicht blind auszuführen;
die strukturelle Abweichung wird diagnostiziert, nicht überschrieben.

Read-only Testkommando (nach gepinntem Git-Checkout):

`python tools/handover_acceleration/dispatcher_runtime_audit.py --root /opt/optolink`
