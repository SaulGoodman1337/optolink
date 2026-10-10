# WB2A / VDensHO1 20C2: P300-GFA C9 durch Regelung abgewiesen (Livebefund)

Stand: **2026-10-08, 10:08 CEST**. Status: **GERAETEPRUEFUNG NEGATIV FUER GFA-C9**. Der P300-Branch bleibt ein isolierter Entwicklungskandidat, keine Produktionsfreigabe.

## Aussage auf einen Blick

- Unter P300 funktionieren auf der konkreten WB2A die zur Initialisierung benoetigten virtuellen Lesezugriffe auf **0x00F8/2 = 20C2** und **0x778C/2 = 0103**, denn die Init-Routine erreichte nach beiden Vergleichen die dritte Stufe.
- Die dritte Stufe, **P300 GFA_READ Funktionscode 0xC9, Adresse 0x4050, ein Byte (P80)**, wird mit einer **Controller-Fehlerantwort (Message Identifier 3, Payload 05)** beantwortet.
- Die gepatchte Fehlerausgabe vom Geraet lautet wortgetreu:
  ```text
  Oct 08 10:08:54 P300_INIT_STAGE_FAILED stage=gfa_p80 fc=C9 addr=4050 code=03 payload=05
  Oct 08 10:08:54 P300_INIT_FAILED: controller rejected request
  Oct 08 10:08:54 Exception: init_protocol VS2/300 failed
  ```
- **GFA-Code C9 ist fuer diesen P80-Aufruf in dieser P300-Sitzung nicht nutzbar**. Dies widerlegt nicht die ganze P300-Schnittstelle, nicht die P300-RAM-Lesefunktion und nicht prinzipiell alle GFA-Adressen oder alternative GFA-Kommandos.
- Der eingebaute GFA-Gate hat **korrekt verhindert**, dass alle HA-GFA-Entities im Betrieb ohne gueltige Daten zurueckgelassen werden. GFA-P80/P06/P09/P87 sind Bestandteile des produktiven Profils; P06 bleibt der belegte Geblaesedrehzahlkanal.
- Das neue Canary-Skript erkennt den Init-Reject und stellt **automatisch und sofort** die bewiesene VS1-Konfiguration wieder her.

## Hardwaretranskript / Timeline

Der Nutzer hat ausschliesslich folgende Teilabfolge gemeldet; dies ist kein Zugriff durch den Autor auf die LXC.

### 09:42 Uhr – erster CANARY

- Produktives VS1 vorher erfolgreich: `r;0x00F8;2;raw;False -> 1;0xf8;20c2`.
- Erster P300-CANARY: `ActiveState=active`, aber `P300_INIT_FAILED: controller rejected request` um **09:42:13** und erneut **09:42:24**.
- Problem der frueheren Canary-Version: Sie akzeptierte `systemctl ActiveState=active`, obwohl der Upstream-Prozess nach 10 s intern erneut die P300-Initialisierung probierte; der Dienst hatte `enter main loop` **nicht** erreicht.

### Rueckkehr VS1 bestaetigt

- Explizit `/usr/local/sbin/optolink-p300-trial rollback` ausgefuehrt.
- `No P300 drop-in`, `WorkingDirectory=/opt/optolink`, `ActiveState=active`.
- `r;0x00F8;2;raw;False -> 1;0xf8;20c2`.
- `gfaread;0x4050;1;raw;False -> 1;0x4050;20`.
- Damit ist auch **echte GFA-Lesbarkeit unter VS1**, nicht nur ein gestarteter Prozess, nach dem Rollback belegt.

### 10:08 Uhr – zweiter, diagnostisch verbesserter CANARY

- Checkout des Dev-Commits `5cfd6ba376feca63a751336ccd4e277dd5114ec5` durch `git pull --ff-only`.
- Nur `tools/optolink_p300.py` wurde in den isolierten Kandidaten kopiert; der Stager wurde nicht erneut ausgefuehrt.
- `activate 120` -> `P300_CANDIDATE_PREFLIGHT=PASS`.
- `P300 rejected an initialization request; immediate VS1 rollback`.
- Um **10:08:54** dokumentiert der Kandidat die **konkrete** Ablehnung `fc=C9 addr=4050 code=03 payload=05`.
- Um **10:08:56**: `enter main loop` von PID `123974` aus **/opt/optolink**. Status `No P300 drop-in`, Original-Service `active`.
- **Grenze**: Der Nutzer hat nach diesem zweiten Rollback nicht nochmals P80 abgefragt; der unmittelbare vorherige VS1-Rollback inklusive P80 war jedoch bereits erfolgreich. Darueber hinaus ist keine kuenftige Verfuegbarkeit behauptet.

## Fehlersemantik / Abgrenzung

- Das P300-Backend akzeptiert nur Telegramme mit validierter Groesse, Funktionsnummer, Antwortadresse und Pruefsumme. `code=03` kommt aus einer strukturellen **Geraete-Fehlernachricht**, nicht aus einem seriellen Timeout, einer falschen Pruefsumme oder einem fehlenden ACK.
- `payload=05` ist ein **uninterpretierter Rohfehlerwert**. Eine belastbare herstellerspezifische Bedeutungszuordnung fuer dieses Byte wurde nicht gefunden. **Nicht** ohne Beleg als `not implemented`, `unknown command` oder als Brenner-/Anlagenstoerung deklarieren.
- Das auf GitHub dokumentierte Vitosoft-VS2-Protokoll *definiert* `GFA_READ=201 (0xC9)`; es beweist **nicht**, dass die konkrete WB2A-Firmware diesen Befehl in P300 bereitstellt.
- Der Produktionspfad benutzt dagegen erfolgreich **VS1-Kommando 0x6B** und bleibt vollstaendig bestehen.
- Es gab **keinen Schreibzugriff**, keinen Anlagenschemawechsel, keinen RAM-Write und keinen neuen permanenten Dienst.

## Architektur-Folgen / Entscheidungsvarianten

| Alternative | Alle jetzigen GFA-Entities | P300 Physical_RAM in laufender Telemetrie | Status / Bewertung |
|---|---|---|---|
| **A. Produktives VS1 beibehalten** | **Ja, live bestaetigt** | Nur getrennte Wartungssitzung, nicht simultan | **Aktueller sicherer Stand** |
| B. Permanente P300-Sitzung mit dem vorhandenen C9-GFA-Gate | **Nein** – Start wird korrekterweise verweigert | Konzeptuell ja | **Auf konkreter WB2A blockiert** |
| C. C9-Gate entfernen und unter P300 ohne GFA fahren | **Nein**; P06/P09/P87 fehlen | Moeglich, aber nicht funktionsgleich | **Nicht akzeptabel** |
| D. Innerhalb des einzelnen Optolink-Besitzers zeitgesteuert VS1/P300 umschalten | Nur mit Unterbrechungen / ggf. alternden Werten | Momentane P300-Fenster ja | Bereits gemessener VS1->P300->VS1-Rundweg **ca. 5990 ms**, bei E7-RAM-Reload **ca. 2,1 s** nicht als Regelung geeignet |
| E. P300 zusaetzlich ueber bestaetigte alternative GFA-Lesequelle / Firmware-Gateway | Noch keine verifizierte Quelle | Konzeptuell ja | **Offene Forschung**, nicht implementiert |
| F. Zweiter physischer GFA-Bus-/Interface-Adapter mit eigenem legalem Zugriff | Vielleicht | Konzeptuell ja | **Neue Hardware und Protokollanalyse**; nicht erforderlich fuer VS1-Produktivbetrieb, bisher keine verifizierte Ausfuehrung |

Begriffe: Ein `0xC9` im P300-Funktionsfeld laesst sich nicht durch simples Einsetzen des VS1-Codes `0x6B` ersetzen. Die beiden Rahmenprotokolle und erwarteten Antworten sind verschieden. Ebenso belegt die Existenz eines dokumentierten alternativen Funktionscodes seine Unterstuetzung auf dieser Firmware nicht.

## Naechste sichere Schritte

1. **Keine weiteren identischen C9/P80-Live-Versuche** auf dem bisherigen Code: Ablehnung wurde reproduzierbar festgestellt.
2. Nur offline pruefen, ob Vitosoft/VDensHO1-Tabellen oder Firmware-Rekonstruktionen einen **P300-lesbaren Spiegel** der GFA-P80/P06/P09/P87-Werte oder einen dokumentierten anderen Gateway-Befehl nennen. Provenienz (Softwaremodell, Funktionscode, Adresse, Breite) separat belegen, keine Vermutung als Produktion ausgeben.
3. Falls sich ein belegt lesbarer alternativer Pfad findet, zuerst isolierte **read-only** Hardwarepruefung mit voller VS1-Wiederherstellung. Nur dann GFA-Gate/Produktionsprofil anpassen.
4. Bis dahin VS1 produktiv beibehalten; P300 fuer dedizierte, exklusive, seltene Wartungsabfragen statt fuer Dauerbetrieb nutzen. Keine automatischen, hochfrequenten RAM-Overrides aufgrund der gemessenen Protokollwechselzeit.
5. Falls Nutzer die gewohnte HA-Funktionsparitaet priorisiert, den ersten produktiven P300-Wechsel explizit als **BLOCKED_GFA_C9_REJECTED** markieren.

## Quellen im Repo

- [VS1-GFA-Kompatibilitaet, live hardwarebewiesen](https://github.com/SaulGoodman1337/optolink/blob/optolink-research/docs/vs1-mixed-gfa-integration.md)
- [Permanenter VS1/GFA-Produktionsnachweis](https://github.com/SaulGoodman1337/optolink/blob/optolink-research/docs/gfa-live-checkpoint.md)
- [VS1/P300-Wechsel und Pumpen-RAM-Limit](https://github.com/SaulGoodman1337/optolink/blob/optolink-research/docs/pump-min-override.md)
- [Vitosoft-Protokollrekonstruktion](https://github.com/sarnau/InsideViessmannVitosoft/blob/main/VitosoftCommunication.md)
- [P300-Implementierung](../tools/optolink_p300.py), [Tests](../tools/test-p300-migration.py), [CANARY-Runbook](p300-trial-install-rollback.md)
