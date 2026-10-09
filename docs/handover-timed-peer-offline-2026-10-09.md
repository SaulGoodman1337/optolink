# Offline-Test: Zeitgesteuerte ENQ-/Fast-Switch-Simulation (09.10.2026)

**Status:** `OFFLINE_PASS`; **kein** serieller oder USB-Zugriff. Kein Test an der Viessmann WB2A, keine neue Firmware- oder Hardwaremessung. Ausgeführt in der separaten Sandbox und nur gegen synthetische Gegenstellen. `optolink-p300-migration`, PR #46, `/opt/optolink`, Services und laufende RPM-Logger wurden nicht angesprochen.

## Testziel

Die Einsparung durch **einen statt zweier ENQs auf dem verifizierten P300→VS1-Rückweg** isolieren, ohne den synchronen P300-Einstieg, die GFA-Datenherkunft, Identitätskontrolle, RX-Deadlines oder Recovery zu verändern. Die beiden bereits gemessenen Controller-ENQ-Wartephasen sollen im Replay getrennt ankommen, nicht als gleichzeitiges `RX 060505`.

## Testaufbau und Grenzen

- `timing_simulator.py`: rein virtueller monotonic Clock und `TimedPeer`, dessen Antworten erst nach den festgelegten Delays verfügbar sind. Keine pySerial-, `systemd`-, Netzwerk-, CP2102- oder Geräteinstanz.
- Je drei **historische** ENQ-Zeitpaare aus dem erfolgreich gemessenen EOT/Ein-ENQ-Vergleich und jeweils die separat gemessene zusätzliche ENQ-Wartezeit aus dem alten Zwei-ENQ-Vergleich. Paare unterschiedlicher echter Hardwareversuche werden **nur als Eingabeparameter** einer Simulation kombiniert; das ist keine neue gepaarte Hardwaremessung.
- Gleiche fest definierte Antwortlatenzen für Identität, Software und GFA in beiden simulierten Varianten; nur die zusätzliche ENQ im VS1-Rückweg unterscheidet sich.
- Vor beiden Varianten erfolgt in der Simulation eine konservative **Zwei-ENQ-Kaltinitialisierung außerhalb** des Vergleichsfensters. Der P300-Einstieg verwendet genau eine ENQ; nur der Rückweg benutzt je Variante eine bzw. zwei ENQs.
- Der neue Zustandsautomat prüft beim VS1-Rückweg **zusätzlich Software und P80/P06 direkt während der Rückkehr**, anders als der ursprüngliche Messprober. Daher sind die simulierten absoluten Zeiten nicht mit den gemessenen 4,610 s / 6,863 s gleichzusetzen. Der paarweise Zeitunterschied ist das relevante kontrollierte Ergebnis.

## Paarweiser synthetischer Vergleich

| Archivprofil | 2 ENQ, simuliert | 1 ENQ, simuliert | Simulierter Vorteil | Archivwert zusätzliche ENQ |
|---|---:|---:|---:|---:|
| 1 | 6.921 ms | 4.683 ms | 2.238 ms | 2.237,470 ms |
| 2 | 6.923 ms | 4.686 ms | 2.237 ms | 2.237,667 ms |
| 3 | 6.921 ms | 4.683 ms | 2.238 ms | 2.237,899 ms |

Die 1-ms-Diskretisierung resultiert aus dem virtuellen Polling. Die synthetische Differenz reproduziert damit den entfernten zweiten ENQ-Zyklus (ca. 2,238 s), **nicht** die gesamte reale Einsparung von 2,253 s, in der normale Variationen anderer Phasen enthalten waren.

Der Test sieht pro Übergang eine eigene EOT-Aussendung und getrennte ENQ-Empfangsereignisse. Die Kaltinitialisierung wird nicht als Beschleunigung gezählt. Im simulierten Host ist die längste einzelne Warteanweisung höchstens 25 ms (Gaps); die Sekunden bis ENQ kommen **ausschließlich vom zeitgesteuerten Peer-Modell**.

## Sicherheits- und Negativtests

Die vollständige lokale Suite aus **57 Tests** (51 bereits vorhandene sowie 6 neue zeitgesteuerte Fälle) ist unter Python 3.13 erfolgreich. Die neuen Testfälle überprüfen:

1. Erster und zweiter ENQ haben tatsächlich separate RX-Zeitpunkte (ca. 1,998 s und weitere 2,238 s).
2. Ein ENQ weniger spart ausschließlich die zusätzliche modellierte Wartezeit; es wird nicht heimlich eine weitere Firmwarebeschleunigung behauptet.
3. Keine feste 2-s-Host-Sleep-Anweisung erzeugt die Wartezeit.
4. Eine falsche VS1-Gerätekennung lässt die schnelle Rückkehr scheitern und löst **separaten, konservativen Zwei-ENQ-Restore** aus. Der Fast-Switch wird nicht als Erfolg markiert.
5. Ein ausbleibender P300-ENQ führt zum begrenzten Timeout und danach zum konservativen VS1-Restore.
6. Falsche Identitätsbytes (`05 05`) werden nicht als erfolgreiche VS1-Identität akzeptiert.

Die unveränderten 51 Regressionen decken weitere Fault-Injections (P300-CRC, Softwarekennung, GFA FF/P80, Threads, Portbesitz, PTY, Queue-Fairness, Datenfrische) ab. Ein bereits erfolgreicher CI-Lauf aus Phase 3 bestätigt diese 51 Tests unter Python 3.11/3.12; eine CI-Prüfung **der neuen sechs Tests** ist erst nach Commit und neuem GitHub-Actions-Lauf als erfolgreich zu bezeichnen.

## Bewertung

- **Bewiesen durch frühere echte Hardwareversuche:** Ein-ENQ-Vergleich durchschnittlich 4.610,091 ms statt 6.862,980 ms; Einsparung 2.252,889 ms bzw. 32,827 %; danach echte Identität/GFA und VS1-Restore erfolgreich.
- **Durch diesen Offline-Test belegt:** Der neue Zustandsautomat reproduziert die kontrollierte ca. 2,238-s-Einsparung und meldet Fehler/Recovery korrekt. Eine Virtual-Clock-Simulation kann weder den Firmwaretimer entfernen noch CP2102/Kernel-Verzögerungen messen.
- **Weiterhin offen:** Neue echte Beschleunigung unter 4 s. Die gemessenen beiden ersten ENQ-Phasen dauern zusammen ca. 3.995,460 ms. Selbst ohne jede andere Laufzeit bleibt für unter 4 s praktisch kein Spielraum. Eine zusätzliche Handshakevariante **ohne** neue quellenbelegte Controller-Hypothese wäre kein Erkenntnisfortschritt.
- **Nächster sinnvoller Offline-Arbeitsschritt:** Unabhängigen Recovery-Supervisor nur als Prozess-/PTY-Mock testen und die aktuelle Request-Queue erst nach Integrationsreview mit dem Single-Owner-State-Machine verbinden. Weiterhin keine Hardwareprobe geplant.

## Wiederholen

In einer isolierten Kopie dieses Forschungsbranches:

```sh
PYTHONPATH=tools python3 -m unittest discover -s tests -p 'test_handover*.py' -v
```

Ergebnisdaten: [`evidence/handover-timed-peer-offline-2026-10-09.json`](evidence/handover-timed-peer-offline-2026-10-09.json).

Quellnachweise: [`p300-goals-and-single-enq-result-2026-10-08.md`](https://github.com/SaulGoodman1337/optolink/blob/optolink-p300-migration/docs/p300-goals-and-single-enq-result-2026-10-08.md), [`p300-handover-baseline-result-and-single-enq.md`](https://github.com/SaulGoodman1337/optolink/blob/optolink-p300-migration/docs/p300-handover-baseline-result-and-single-enq.md), [`p300-rpm-trigger-canary-audit-2026-10-09.md`](https://github.com/SaulGoodman1337/optolink/blob/optolink-p300-migration/docs/p300-rpm-trigger-canary-audit-2026-10-09.md).
