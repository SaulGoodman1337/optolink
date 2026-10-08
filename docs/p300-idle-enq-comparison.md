# Historischer Idle-ENQ-Vergleich: ausgeführt und ausgewertet

Stand: 2026-10-08. Prober 1.2.0, getesteter Commit `099e3c1528de4f1d9f8aa101384586fbea473bbb`.

**Aktueller Befund: funktional bestanden, aber langsamer. Dieser Optimierungszweig ist abgeschlossen; kein erneuter unveränderter Testauftrag.**

Der Nutzer hat `--execute --idle-enq` in Session `run-20261008T100802Z-124372` ausgeführt. Drei gültige Messrunden, `PASS_READ_ONLY_IDLE_ENQ`, anschließend Originaldienst `/opt/optolink` active/running und echte MQTT-Antworten P80=20/P06=00.

Der gemessene Gesamtweg einschließlich GFA dauerte im Mittel **5,628 s** statt **4,610 s** beim vorigen EOT-/Ein-ENQ-Lauf. Die natürliche ENQ kam nach **2,971 s** ab passivem Einstieg, nicht früher als die bisherige EOT-basierte ENQ nach etwa **1,998 s**. Damit fehlt die angestrebte Beschleunigung.

## Aktuelle Dokumente

- [Vollständige Auswertung, Messvergleich und nächste Arbeitspriorität](p300-idle-enq-result-2026-10-08.md).
- [Originale Messobjekte aus der Nutzerkonsole und getrennte Berechnungen](evidence/p300-idle-enq-result-2026-10-08.json).
- [Funktionale Ziele und vorheriger Ein-ENQ-Befund](p300-goals-and-single-enq-result-2026-10-08.md).

## Unveränderte historische Anleitung

Die vollständige damals getestete Anleitung mit Hypothese, Quellen, festen Lesegrenzen, Vorbereitung, Abbruchweg und Wiederherstellung bleibt [im getesteten Commit erhalten](https://github.com/SaulGoodman1337/optolink/blob/099e3c1528de4f1d9f8aa101384586fbea473bbb/docs/p300-idle-enq-comparison.md).

Der Code wurde mit dieser Ergebnisdokumentation nicht verändert. Das Werkzeug bleibt als reproduzierbare Forschungsversion vorhanden, wird aber nicht als schnellerer Produktionspfad empfohlen. Es gibt keine neue Freigabe für C9, RAM- oder Parameterwrites.

Die normale VS1-Kommunikation ist nach dem gemeldeten Lauf wiederhergestellt. Für diesen erfolgreichen Lauf sind kein weiterer Rollback und keine erneute Anforderung der bereits hinreichenden Erfolgsprotokolle nötig. Fehler bei einem anderen späteren Lauf wären gesondert anhand dessen eigener Session zu bewerten.
