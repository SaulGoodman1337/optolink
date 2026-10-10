# Hybrid-Protokollwechsel VS1/P300 – Forschungsarchiv Oktober 2026

Dieser Index und die 26 archivierten Daten-/Analyse-Dateien gehören zum Forschungszweig `optolink-research`, **nicht** zum Produktivzweig `optolink-splitter-ha`.

Erfasst sind Messreihen, Versuchsfehlschläge, Timing-/Timing-Simulationsprotokolle, Live-Canary-Nachweise, P300-FC03-Snapshots, Shutdown-/Recovery-Nachweise und sicherheitskritische Beobachtungen vom 9.–10. Oktober 2026.

Die erfolgreiche Hardwareabnahme belegt acht überwachte Read-only-Hybrid-Fenster (ca. 5,3–5,5 Sekunden je Umschaltung), 62/62 parallele MQTT-/TCP-Leseabfragen und den unabhängigen Rückfallpfad nach dem SIGKILL des Canary-Supervisors. **Dies ist keine Freigabe für unbeaufsichtigtes Schreiben, Reboot-Recovery oder dauerhaft aktive P300-Fenster.**

Der Betrieb erfolgt aus dem Produktivzweig über die geprüfte, standardmäßig deaktivierte `optolink-hybrid`-Schnittstelle. Entwicklungs- und Messwerkzeuge in diesem Forschungszweig sind kein Teil der über `update` installierten produktiven Laufzeit.

## Ursprungsreferenzen

- Quelle der archivierten Dateien: GitHub-Branch `optolink-handover-acceleration` am 10.10.2026, Commit `7d58bd6a297c1da797c3b787c4c182539ab68750`.
- Acht-Fenster-/SIGKILL-Bericht: [vs1-p300-eight-window-soak-and-sigkill-2026-10-10.md](vs1-p300-eight-window-soak-and-sigkill-2026-10-10.md).
- Ältere P300-RPM- und KM-Bus-Studien verbleiben ebenfalls in diesem Forschungszweig.

Historische Ergebnisse dienen ausschließlich zur Nachvollziehbarkeit. Keine Controller-Schreibwerte werden durch einen archivierten Versuchsbericht produktiv freigegeben.
