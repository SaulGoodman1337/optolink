# Quellenaudit: Protokollwechsel und GFA unter P300

Stand: 2026-10-08. Ergaenzung zu [Fork-/GFA-Optionen](p300-fork-switching-gfa-options-2026-10-08.md).

## Umfang und Belegklassen

- **LIVE-NUTZER:** Befehlsausgaben und Messwerte aus Nutzertranskripten beziehungsweise vorhandenen Research-Nachweisen. In diesem Arbeitsschritt kein eigener Geraetezugriff.
- **CODE:** Erneute statische Lektuere der genannten Python-Dateien, einschliesslich einer lokalen Kopie des exakt gepinnten Upstreams. Kein Betrieb dieses Codes an der Therme.
- **ARCHIVBERICHT:** Lektuere einer bereits vorhandenen Auswertung von Vitosoft-Originalcode. Private DLL-/IL-Originale in diesem Arbeitsschritt nicht erneut dekompiliert.
- **EXTERNE PRIMAERQUELLE:** OpenV-Protokollrekonstruktionen und veroeffentlichter Autoren-Quellcode, am 2026-10-08 abgerufen. Allgemeine Protokollaussagen nicht automatisch lokal bestaetigt.
- **HYPOTHESE/ENTWURF:** Daraus abgeleitete Moeglichkeiten, fuer die noch ein konkreter Nachweis fehlt.

Research-Stand: `79f222c7f3a11b848a6a8ac8ece50e24deede823`.
P300-Branch vor diesen Dokumentationsaenderungen: `8d1193a2ce7e0449aeeda7ee3f00f68a41956fe4`.
Upstream: `philippoo66/optolink-splitter`, `c1ee204a1421447721603c5f21c6da7337fdac97`.

## A. Konkreter Latenz-Helfer

Quelle: [vs1-p300-handover-latency-probe.py](https://github.com/SaulGoodman1337/optolink/blob/79f222c7f3a11b848a6a8ac8ece50e24deede823/tools/vs1-p300-handover-latency-probe.py).
Git-Blob: `b1a56fdc39b044e4360a158f968a66f395a06fa4`.

Vor `t0`: Stoppen der vorher aktiven Dienste, neuer Port, `sleep(.30)`, Eingangspuffer loeschen. Danach wird P300 ueber EOT/ENQ/Start/ACK aktiviert, eine Identitaetsantwort gelesen, mit EOT beendet und vor dem VS1-Identitaetsread zweimal auf ENQ gewartet.

| Variable | Position | Verwendete Ergebnisdifferenz |
| --- | --- | --- |
| t0 | vor erstem EOT | Start Gesamt und P300-Wechsel |
| t1 | nach erster ENQ, vor Startsequenz | Nicht separat ausgegeben |
| t2 | nach Start-ACK | t2-t0 = P300_SWITCH_MS |
| t3 | nach P300-Identitaetsantwort und deren ACK | t3-t2 = P300_IDENT_MS |
| t4 | nach EOT und erster ENQ auf Rueckweg | Nicht separat ausgegeben |
| t5 | nach ZWEITER ENQ | t5-t3 = VS1_SWITCH_MS |
| t6 | nach VS1-Identitaetsantwort | t6-t5 = VS1_IDENT_MS; t6-t0 = TOTAL_MS |

Zugehoerige dokumentierte Messung: 1680,5 + 51,8 + 4237,0 + 21,0 = 5990,3 ms. Die Messung steht in [pump-min-override.md](https://github.com/SaulGoodman1337/optolink/blob/79f222c7f3a11b848a6a8ac8ece50e24deede823/docs/pump-min-override.md).

**Quellcodegrenzen:**

- Stop/Start von Diensten und Oeffnen/Schliessen des Ports sind nicht Bestandteil von TOTAL_MS.
- Nach dem neuen Portoeffnen wird vor t0 keine aktive warme VS1-Sitzung durch einen neuen Read bestaetigt. Das Label VS1->P300 beweist nicht den Minimalwechsel aus dem kuenftigen laufenden Hybridmanager.
- Der Helfer verwendet blockierende Reads mit 50-ms-Timeout. Bereits vorhandene Bytes koennen frueher zurueckkehren; das ist kein festes sleep pro Byte.
- Der Helfer prueft bei der P300-Antwort ein initiales ACK; die weiteren umfassenden Frame-Pruefungen des neuen Backends sind hier nicht enthalten. Die Identitaeten werden ausgegeben, nicht als umfassendes Test-Gate ausgewertet.
- Der eigene `--self-test` dieses speziellen Helfers besteht nur aus einer PASS-Ausgabe. Er ist nicht mit den substantiellen neueren Fake-Serial-Regressionen zu verwechseln.

**Hypothese:** Ein Teil des Rueckwegs koennte aus der bewusst doppelt abgewarteten Synchronisationsphase kommen. Aus den bisher publizierten Aggregatzeiten kann dessen exakte Groesse nicht bestimmt werden. Neue Instrumentierung sollte zuerst die ohnehin vorhandenen t1-/t4-Zwischenpunkte getrennt ausgeben.

## B. Upstream versus konservativer Vitosoft-P80-Helfer

[optolinkvs1.py](https://github.com/philippoo66/optolink-splitter/blob/c1ee204a1421447721603c5f21c6da7337fdac97/optolinkvs1.py), Blob `cff6b4d8d52ca4ee1f79c310dd9377dba1a18270`:

- `init_protocol()` sendet EOT, wartet einmal auf ENQ und sendet danach STX plus Identitaetsread.
- `wait_for_05()` verwendet 30 Iterationen mit jeweils `sleep(0.1)`. Der Kommentar ueber 300 mal 10 ms stimmt nicht mit dem ausgefuehrten Code ueberein.
- `SYNC_TIMEOUT=0.6` beschreibt lokalen Hostzustand. Keine daraus abgeleitete Firmware-Zeitgarantie.

[optolinkvs2.py](https://github.com/philippoo66/optolink-splitter/blob/c1ee204a1421447721603c5f21c6da7337fdac97/optolinkvs2.py), Blob `7d56f71b10d1bbb74ba2efb443bd16161aff71a8`:

- Auch ENQ- und ACK-Warteschleifen des P300-Einstiegs schlafen 100 ms vor Reads.
- `do_request()` uebernimmt das uebergebene volle Funktionsbyte. Dies ist eine generische Serializer-Faehigkeit und kein Hardwarebeleg fuer beliebige Enumfunktionen.

[vs12_adapter.py](https://github.com/philippoo66/optolink-splitter/blob/c1ee204a1421447721603c5f21c6da7337fdac97/vs12_adapter.py): Protokollauswahl beim Import, bedingtes Dispatching. Ein neuer gemeinsamer Wechselmanager muss mehr verwalten als nur das Flag.

[Historischer P80-Prober](https://github.com/SaulGoodman1337/optolink/blob/79f222c7f3a11b848a6a8ac8ece50e24deede823/config/optolink-splitter/wb2a-gfa-p80-probe.py), Blob `f5c9b1ba0d928b5f477b2d6acdaaed34a8ff91f2`:

- Wartet einmal fuer Interface-Erkennung und einmal fuer frische VS1-Synchronisierung.
- Bezieht diese Zweistufigkeit auf den originalen SDK-Lifecycle.
- Liest P80 erst danach und prueft Variantenkennung und unzulaessige Restdaten.

**Folgerung:** Erste ENQ direkt verwenden ist eine begruendete zu untersuchende Alternative, kein bereits bestaetigter Shortcut. Gegenprobe muss korrekte Nutzantworten nachweisen. Die Upstream-100-ms-Schleifen koennen nicht zur Erklaerung der sechs Sekunden des unabhaengigen Helfers herangezogen werden.

## C. Vitosoft: abstraktes GFA_READ und VSKO-Transport

Quelle: [Private Archive Analysis, Abschnitt 5](https://github.com/SaulGoodman1337/optolink/blob/79f222c7f3a11b848a6a8ac8ece50e24deede823/config/optolink-splitter/research/vitosoft/private-archive-2026-09-23-analysis.md).

Der Bericht beschreibt die Sicherung des Verarbeitungszustands, den Wechsel nach VS1 fuer VSKO, die Umsetzung abstraktes C9 -> VS1/6B, erwartete rohe Antwortlaenge und Wiederherstellung des vorherigen Interface.

Originalquelle laut Archivbericht: `MobileClient/vsmInterfaceCore.dll`, SHA256 `1653fa1346bd37b3e599cdf55fe8eb053d985f8efb8a007c18b94996a575f90d`.

Konkrete Fundstellen in `MobileClient_vsmInterfaceCore.dll.il`:

| Methode/Bereich | Im Bericht genannter Bereich |
| --- | --- |
| VS1Message::getVS1MessageFromLDAPMessage | 429-590 |
| VS1::createVS1Connection | 1139-1281 |
| VS1::sendVS1Message | 1283-1510 |
| VSManager::StartCommunicationVS1 / ChangeInterface | etwa 6629-6800 / 8312-8412 |
| VSMSDK::IsSDKCommandRunnable, VSKO | 18348-18590 |
| RequestCreator::CheckSDKCommandState | 106526-106600 |

Dies ist vorhandene Originalcode-Auswertung. Diese Untersuchung behauptet keine erneute unmittelbare Pruefung der privaten IL-Dateien. Der konkrete naechste statische Auftrag ist die Trennung von abstraktem Auftrag, Interface-Auswahl und tatsaechlichem Senderformat, einschliesslich eventueller eigener VS2-Sonderpfade.

## D. Funktionsbyte und Sequenz: warum C9 nicht vorschnell umbenannt werden darf

[OpenV Protokoll 300](https://github.com/openv/openv/wiki/Protokoll-300), abgerufen 2026-10-08, beschreibt untere fuenf Bits als Funktion und obere drei als Sequenz. Rechnerisch zerfaellt C9 dann in Funktion 09 und Sequenz 6.

[Sarnau VitosoftCommunication.md](https://github.com/sarnau/InsideViessmannVitosoft/blob/main/VitosoftCommunication.md), gelesener Blob `770893a1edac347bc4fcbfdeead9a19df8c7ad92`, nennt sowohl Sequenzbits als auch die breite globale Funktionsliste mit GFA_READ=201.

[Viessmann2MQTT.py](https://github.com/sarnau/InsideViessmannVitosoft/blob/main/Viessmann2MQTT.py), gelesener Blob `9b631b2fee194160c6bd7f1b2646a357a67d7c49`, enthaelt die globale Enum und einen generischen Serializer, der Command.value direkt uebernimmt. Die gelesenen Definitionen sind kein unabhaengiger Live-Nachweis fuer C9 auf dieser WB2A.

Lokale Gegenpruefungen im [KMBUS-Memory-Research](https://github.com/SaulGoodman1337/optolink/blob/79f222c7f3a11b848a6a8ac8ece50e24deede823/config/optolink-splitter/research/vitosoft/kmbus-read-memory-analysis-2026-09-24.md), Blob `fe54133c62c5d586946269044c313f15fc1711db`:

- Sieben gleiche Adressvergleiche von 01 gegen 41 waren payloadidentisch, auch bei nichtnulligen dynamischen Pumpendaten.
- Bei 03 gegen 43 zeigte ein stabiles Fenster denselben Wert; andere Fenster waren dynamisch und deshalb nicht entscheidbar. Keine allgemein nachgewiesene neue EEPROM-Ansicht.
- Der Host gruppiert diese Antworten nach maskiertem Funktionsanteil; das allein beweist noch keine identische Controllerimplementierung.
- Abgelehnte XRAM-Formen lieferten ebenfalls Payload 05, waehrend bestimmte virtuelle Kontrollen Payload 01 lieferten. Der Bericht weist ausdruecklich auf die fehlende Bedeutungszuordnung hin.
- PrefixRead wird beim untersuchten Standard-Non-RPC-VS2-Read nicht einfach angehaengt. Der nachgewiesene Prefix-Serialisierungspfad gehoert RPC/07. Keine geratenen Prefixe an C9 anhaengen.

**Praezise Grenze:** Der physisch gesendete Frame mit Byte C9 ist abgelehnt. Die Schlussfolgerung, jede hypothetische GFA-Funktion unter P300 sei damit widerlegt, geht weiter als die Daten. Ein einfacher Austausch C9->09 waere unter dem Sequenzmodell kein neuer GFA-Pfad. Ein Austausch C9->6B vermischt verschiedene Protokolle. Beides ist kein vorgeschlagener Live-Test.

## E. RAM-Spiegel: positive Grundlage, aber keine gefundene GFA-Adresse

[Physical_RAM / Optolink Map](https://github.com/SaulGoodman1337/optolink/blob/79f222c7f3a11b848a6a8ac8ece50e24deede823/config/optolink-splitter/research/physical-ram-optolink-map-2026-09-26.md), Blob `8c17b6e439d7cfb69c59610fbaa4357414be5ada`, beschreibt echte laufende Optolink-Kommunikationsdaten in Physical_READ-Aufnahmen. Genau deshalb muessen alte Antwortpuffer bei jeder Spiegel-Suche ausgeschlossen werden.

[Archive Analysis](https://github.com/SaulGoodman1337/optolink/blob/79f222c7f3a11b848a6a8ac8ece50e24deede823/config/optolink-splitter/research/vitosoft/private-archive-2026-09-23-analysis.md) grenzt P06-Drehzahl, P09-Modulationssollwert und P10-PWM voneinander ab und verwirft die alte RPM-Deutung von 55D3[6:7]. Das neue Konzept liefert **noch keine Ersatzadresse**. Ein autonom unter P300 fortgeschriebener, validierter RAM-Kandidat waere erst ein Forschungsergebnis.

## F. Weitere gepruefte, aber nicht tragende Spuren

- [V-Comm-DLL-Quellenfund](https://github.com/SaulGoodman1337/optolink/blob/79f222c7f3a11b848a6a8ac8ece50e24deede823/config/optolink-splitter/research/v-comm-dll-source-recovery-2026-09-25.md): explizite VDensHO1-Unterstuetzung, aber in der untersuchten Basis nur normale P300-Reads/Writes. Kein neuer belegter GFA-Gateway aus dieser Quelle.
- [VitoTest-Funktionsklassifikation](https://github.com/SaulGoodman1337/optolink/blob/79f222c7f3a11b848a6a8ac8ece50e24deede823/config/optolink-splitter/research/vitotest-v18-function-classification-2026-09-26.md): historische GWG-Physical-OpCodes und Simulatorantworten sind kein Beleg fuer RAM unter lokalem VS1. Nicht als 16-Bit-VS1-Test uebernehmen.
- [OpenV Protokoll KW](https://github.com/openv/openv/wiki/Protokoll-KW), abgerufen 2026-10-08: beschreibt Folgeanfragen innerhalb einer synchronisierten Sitzung. Begruendet das Buendeln von GFA-Anfragen, aber keinen gleichzeitigen VS1/P300-Betrieb.

Die externe Suche nach P300/GFA/C9 lieferte keine belastbare neue direkte WB2A-Erfolgsimplementierung. Das negative Suchergebnis ist kein Unmoeglichkeitsbeweis. Die naechste Arbeit ist durch die identifizierten Quellcode-/Timingluecken konkretisiert.

## Dokumentations- und Ausfuehrungsgrenze

Alle vorgenannten neuen Optionen sind Entwuerfe. Keine Protokollvariante wurde neu an der Therme ausprobiert. Die bekannten normalen Protokoll-Steuerbytes werden hier beschrieben, nicht als Freigabe fuer beliebige neue Sequenzen ausgegeben. Keine unbekannten Funktionscodes, Prefixe, RPCs, Firmwareaenderungen oder RAM-Writes wurden hinzugefuegt.
