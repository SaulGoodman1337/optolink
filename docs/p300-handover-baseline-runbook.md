# WB2A: instrumentierter VS1/P300-Handover-Basistest

Stand: 2026-10-08. **Die Zwei-ENQ-Basis wurde inzwischen an der echten Anlage erfolgreich ausgefuehrt.** Die fruehere Kennzeichnung als noch ungetestet ist damit ueberholt.

## Historischer, unveraendert erhaltener Teststand

Das vollstaendige urspruengliche Runbook fuer Prober 1.0.0 bleibt unter dem getesteten Commit erhalten:

[Originalrunbook bei d0e16a6](https://github.com/SaulGoodman1337/optolink/blob/d0e16a607b1b473fa1f5e921623b244b3e8b97b5/docs/p300-handover-baseline-runbook.md).

Dort sind der feste Zwei-ENQ-Ablauf, die 32 damaligen Offline-Tests, Supervision, Aufruf, Abbruch und alle Ergebnisfelder dokumentiert. Historische Formulierungen wie "noch nicht ausgefuehrt" beschreiben den Stand VOR dem folgenden Nutzerlauf und sind nicht der aktuelle Status.

## Jetzt vorliegender Hardwarebeleg

- Session `run-20261008T092711Z-124106`, am 8. Oktober 2026.
- Drei vollstaendige warme VS1 -> P300 -> Zwei-ENQ-VS1-Runden mit validierten Identitaeten und GFA-Antworten.
- `RESULT=PASS_READ_ONLY_BASELINE`, Systemd-Exitstatus 0.
- Nach Wiederherstellung erneut echte MQTT-GFA-Abfragen: P80=20, P06=00.
- Mittlere Hin-/Rueckzeit einschliesslich GFA: 6862,980 ms.
- Davon jeweils etwa 1998 ms auf die erste ENQ in jeder Richtung und 2237,679 ms auf die zusaetzliche zweite ENQ.

[Alle drei Konsolen-Datensaetze](evidence/p300-handover-baseline-2026-10-08.json).

## Aktueller naechster Test

[Auswertung und opt-in Ein-ENQ-Vergleich mit Prober 1.1.0](p300-handover-baseline-result-and-single-enq.md).

Die neue Variante wird nur mit `--single-enq` ausgewaehlt. Ohne dieses Flag bleibt die Basissequenz erhalten. Initialer Aufbau und finale Recovery verwenden auch im neuen Vergleich zwei ENQs. Die 32 urspruenglichen Tests bleiben unveraendert; 10 neue Tests ergaenzen den Vergleich. Keine Parameter-/GFA-/RAM-Writes, keine neue Adresse, kein C9 und keine stille Umstellung auf einen anderen Ablauf waehrend einer Messrunde.

Den erfolgreichen Basistest nicht einfach unveraendert wiederholen. Fuer den naechsten Versuch die aktuelle Anleitung und den zugehoerigen geprueften Commit verwenden, nicht den alten CANARY oder Stager.

## Wiederherstellungsgrenze bleibt unveraendert

Der eigenstaendige Worker `optolink-handover-probe.service` pausiert die zuvor aktiven Produktionsdienste und stellt sie ueber `ExecStopPost` selektiv wieder her. Manuelles Abbrechen erfolgt mit `systemctl stop optolink-handover-probe.service`, NICHT mit dem alten P300-CANARY-Rollbackhelfer. RuntimeMaxSec und TimeoutStopSec begrenzen den Worker beziehungsweise seine Stopphase, garantieren aber keine erfolgreiche Wiederherstellung bei Kernel-, Systemd-, USB- oder Stromfehlern.

Nach dem Test echten MQTT-P80/P06-Read und HA-Frische kontrollieren. Die Sessiondateien `measurement.json`, `recovery.json` und `state.json` nicht vor geklaerter Wiederherstellung loeschen. Fehler nicht durch einen unveraenderten neuen Teststart zu reparieren versuchen. Die detaillierten aktuellen Befehle stehen im verlinkten Ein-ENQ-Runbook.
