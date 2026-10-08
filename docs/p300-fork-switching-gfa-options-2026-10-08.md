# P300 / VS1: eigener Fork, schnellere Wechsel und GFA-Alternativen

Stand: **2026-10-08**. Lokale Anlage: **WB2A / VDensHO1 / 20C2 / 01.03**.
Status: **Quellenpruefung und Entwicklungsentwurf; keine neuen Heizungsversuche**.

## Ergebnis

**Beide Vorschlaege sind sinnvoll und nicht gegenseitig ausschliessend.** Ein eigener Splitter-Fork kann Protokollwechsel sauber integrieren und vermeidbare Host-Wartezeiten reduzieren. Er kann keine feste Wartezeit der Kesselfirmware wegprogrammieren. Zugleich wurde nur der konkrete C9-Aufruf negativ getestet, nicht jede denkbare GFA-Lesequelle unter P300.

Die Produktionsfreigabe bleibt geschlossen. Keine GFA-Entities entfernen, keine veralteten Ersatzwerte als aktuelle Messung ausgeben, kein C9-Gate einfach uebergehen. Der unveraenderte CANARY muss nicht erneut ausgefuehrt werden.

**Korrektur der bisherigen Begruendung:** Die gemessenen sechs Sekunden sind keine bewiesene technische Untergrenze. Ebenso ist eine abstrakte Enum-Konstante `GFA_READ=201` kein ausreichender Nachweis eines nativen P300-GFA-Befehls. Die vorhandene Vitosoft-Analyse beschreibt bereits die Uebersetzung C9 -> VS1/6B. Diese Unterscheidung haette bei der Begruendung unseres ersten Kandidaten staerker beruecksichtigt werden muessen.

Quellen, genaue Messgrenzen und Serialisierungsbefunde stehen im [Quellenaudit](p300-switching-source-audit-2026-10-08.md).

## 1. Neue Bestaetigung des VS1-Rollbacks

Der Nutzer liefert nach dem zweiten CANARY:

```text
gfaread;0x4050;1;raw;False -> 1;0x4050;20
gfaread;0x4006;1;raw;False -> 1;0x4006;00
```

Damit ist auch nach diesem Ruecklauf echte VS1-GFA-Kommunikation belegt, nicht nur ein laufender Prozess. P80 ist korrekt; P06 antwortet mit einem gueltigen Rohwert 00 statt FF. Fuer diese beiden Folgeabfragen wurde kein genauer Zeitstempel mitgeliefert. Ein separater physischer Drehzahl-/Flammenzustand wurde dabei nicht erfasst.

Der vorherige Befund bleibt bestehen:

```text
2026-10-08 10:08:54 CEST
P300_INIT_STAGE_FAILED stage=gfa_p80 fc=C9 addr=4050 code=03 payload=05
```

Die vorausgehenden FC01-Identitaetsvergleiche wurden passiert. Die Bedeutung des Fehlerpayloads 05 bleibt unzugeordnet. Es ist kein belegter Anlagen-/Brennerstoercode. Siehe [Hardwareprotokoll](p300-gfa-c9-hardware-rejection-2026-10-08.md).

## 2. Fork: ja, aber nicht als alleinige Geschwindigkeitsloesung

Gemeint ist ein Fork der **Hostsoftware**, keine Veraenderung der Kesselfirmware. Fuer den ersten Machbarkeitsnachweis reicht ein versionierter Patch gegen den gepinnten Upstream. Ein gepflegter eigener Fork ist sinnvoll, wenn der gemeinsame Sitzungsmanager dauerhaft gebraucht wird: weniger fragile Textpatches, explizite Tests und reproduzierbare Updates.

Der bisherige Adapter waehlt VS1/VS2 im Wesentlichen beim Import. Ein dynamischer Betrieb muss ausser dem Protokollflag auch Empfangspuffer, Synchronisationszeit, Decoder, Fehlerbehandlung und Warteschlange verwalten.

### Zielarchitektur, noch nicht implementiert

```text
Bestehende HA-Entities und MQTT-/Zusatzdienst-API
                       |
               gemeinsamer Dispatcher
                       |
         EIN serieller Besitzer/Sitzungsmanager
            VS1 <-> SWITCHING <-> P300
                       |
           begrenzte Recovery nach VS1
```

Die Software waehlt pro Auftrag die benoetigte Faehigkeit: GFA ueber bestaetigtes VS1, physischer RAM ueber bestaetigtes P300, normale virtuelle Datenpunkte ueber den geeigneten aktiven Pfad. Funktionale Gleichwertigkeit nach aussen ist moeglich; die zeitliche Gleichwertigkeit muss gemessen werden.

Anforderungen an einen solchen Fork:

- Keine Protokollwechsel mitten im Telegramm oder zwischen zusammengehoerendem Read/Write/Readback. Vorhandene Anwendungssperren an die zentrale Queue anbinden.
- Keine konkurrierenden Portbesitzer. MQTT-/TCP-Requests waehrend des Wechsels kontrolliert einreihen, nicht auf den Draht durchlassen.
- Faehigkeiten getrennt modellieren: P300-Transport, Physical_READ, GFA-Provider, vollstaendige Produktionsparitaet. Ein C9-Reject ist nicht gleichbedeutend mit defektem P300.
- Keine automatische Write-Wiederholung bei unklarem Ausgang; Adressraeume strikt trennen.
- RAM-Arbeit budgetieren. GFA, normale Telemetrie und anstehende Readbacks duerfen nicht dauerhaft verdraengt werden.
- Frische und letzten erfolgreichen Messzeitpunkt ausweisen; MQTT-Retain nicht als neue Messung behandeln.
- Upstream-/Fork-Commit und Profil pinnen, Installer und Rueckweg ausdruecklich anpassen. Der heutige Updater benutzt einen neu erstellten Fork nicht automatisch.

Der aktuelle Vollmigrations-Kandidat behaelt seine Sperre. Ein spaeterer Hybridmanager darf einen getrennten P300-Maintenancepfad besitzen und GFA ueber VS1 erhalten; das ist nicht dasselbe wie das ersatzlose Entfernen des GFA-Gates.

## 3. Der konkrete Ansatz fuer schnellere Wechsel

### Was der alte Messhelfer wirklich misst

Im Helfer `vs1-p300-handover-latency-probe.py` liegen Dienststopps, Portoeffnung und eine 300-ms-Pause **vor** dem Startzeitpunkt. Die sechs Sekunden enthalten diese Arbeiten nicht.

Innerhalb der Messung:

| Abschnitt | Ablauf | Gemessen |
| --- | --- | ---: |
| Einstieg P300 | EOT -> ENQ -> 16 00 00 -> ACK | 1680,5 ms |
| P300-Identitaet | Virtual_READ 00F8/2 | 51,8 ms |
| Rueckweg VS1 | EOT -> ENQ1 -> ENQ2 | 4237,0 ms |
| VS1-Identitaet | STX + F7 00F8/2 | 21,0 ms |
| Gesamt | Messfenster | 5990,3 ms |

**Wichtiger Fund:** Fuer den Rueckweg werden zwei aufeinanderfolgende ENQs abgewartet. Die Zeitstempel fuer ENQ1 und ENQ2 existieren im Skript, werden aber nicht getrennt ausgegeben. Wir wissen deshalb nicht, welcher Anteil auf welche Wartephase entfaellt.

Der historische P80-Helfer tut dies absichtlich: einmal Interface-Erkennung, dann frische VS1-Synchronisierung. Der gepinnte Upstream verwendet nach EOT dagegen nur **eine** ENQ und sendet dann STX mit Identitaetsread. Das ist eine konkrete, quellenmotivierte Alternative, aber noch kein erfolgreicher schneller Wechsel auf der lokalen WB2A.

**Hypothese:** Die zweite ENQ ist in einem sauber verwalteten warmen Wechsel moeglicherweise entbehrlich. Sie darf nicht einfach gestrichen werden, ohne danach exakte Identitaet und GFA-Antworten statt beliebiger Bytes zu pruefen.

Falls eine etwa zweisekuendige Warteperiode entfaellt, blieben vom bisherigen Wert rechnerisch immer noch etwa vier Sekunden. Das ist nur eine Orientierung, keine Prognose und noch keine Loesung fuer das 2,1-s-Reloadproblem.

### Welche Host-Optimierung zusaetzlich sinnvoll ist

Die Upstream-Warteschleifen lesen ENQ/ACK nach jeweils `sleep(0.1)`. Ereignisgesteuertes Lesen oder ein eng begrenzter kurzer Poll kann diese zusaetzliche Reaktionsverzoegerung reduzieren. Ein bereits angekommenes ENQ wird dann schneller beantwortet. Ein noch nicht gesendetes ENQ wird dadurch nicht frueher erzeugt.

Der alte separate Messhelfer verwendet diese Upstream-Schleifen gar nicht. Seine sechs Sekunden duerfen deshalb nicht den 100-ms-Sleeps zugerechnet werden. Auch `serial.timeout=.05` in diesem Helfer ist keine feste 50-ms-Pause fuer jedes vorhandene Byte.

### Weitere Ideen und Grenzen

- Alle vier GFA-Abfragen in **einer** VS1-Phase buendeln, nicht viermal hin- und herschalten.
- Fuer haeufige RAM-Arbeit kann P300 der Grundmodus und VS1 ein kurzes GFA-Zeitfenster sein. Fuer seltene RAM-Diagnose ist VS1-Grundbetrieb plausibler.
- Ein Warmwechsel ohne vollstaendigen EOT-Neustart oder eine ausgenutzte ENQ-Phase bleibt unbelegt. Erst passende Sender-/Parserlogik untersuchen, nicht beliebige Steuerbytes ausprobieren.
- Kuerzere Timeouts beschleunigen nur den Fehlerabbruch, nicht die Antwort des Geraets. Zu kurze Fristen koennen durch Retries sogar verschlechtern.
- Hoehere Baudrate oder gleichzeitig sendende zweite Optolink-Master sind kein belegter Weg.

## 4. Warum GFA unter P300 trotzdem weiter untersucht werden sollte

### 4.1 Abstract C9 ist nicht automatisch Wire-C9

Die vorhandene Archive-Auswertung beschreibt explizit: Vitosoft pausiert Verarbeitung fuer VSKO, wechselt nach VS1, bildet den abstrakten GFA_READ-Code C9 auf `6B` ab und stellt danach das alte Interface wieder her. Das ist ein wichtigerer Familienbezug als die blosse globale Enum-Liste.

In dieser Runde wurde dieser archivierte Analysebericht erneut gelesen. Die privaten DLL-/IL-Dateien wurden **nicht neu dekompiliert**. Fuer eine erneute Originalcodepruefung sind die bereits identifizierten Methoden `VS1Message::getVS1MessageFromLDAPMessage`, `VSManager::ChangeInterface` und `VSMSDK::IsSDKCommandRunnable` die konkreten Anlaufstellen.

Die Frage ist also nicht nur: Gibt es eine andere Adresse? Zuerst muss geklaert sein, ob der abstrakte Auftrag auf der konkreten Familie ueberhaupt einen nativen P300-Wire-Befehl besitzt.

### 4.2 Sequenzbits: zusaetzliche Unsicherheit im bisherigen Frame-Modell

Die oeffentliche P300-Beschreibung teilt das Funktionsbyte in fuenf Funktionsbits und drei Sequenzbits. Unter diesem Modell gilt:

```text
C9 & 1F = 09
C9 >> 5 = 6
```

Ein gesendetes C9 koennte daher Funktion 09 mit Sequenz 6 darstellen, nicht eine eigenstaendige Funktion 201. Diese Interpretation ist fuer die konkrete Firmware noch nicht vollstaendig bewiesen. Lokale Vergleiche 01/41 sowie 03/43 liefern aber bereits Hinweise auf gemeinsame/aliasierte Ansichten trotz verschiedenem oberen Byteanteil.

**Nicht daraus ableiten:** C9 einfach durch 09 oder 6B ersetzen. Im beschriebenen Modell waere 09 nur derselbe Funktionsanteil mit anderer Sequenz. VS1/6B ist ein anderer Rahmen. Auch das Echo von C9 in einer Antwort beweist keine semantische GFA-Annahme. Unsere Fake-Peer-Tests pruefen das implementierte Modell, nicht dessen externe Geraetekonformitaet.

### 4.3 Alternative Datenquellen

| Ansatz | Relevanz | Fehlender Nachweis |
| --- | --- | --- |
| Originaler VS2-/LDAP-/VSKO-Serializer | Hoechste Prioritaet zur Korrektur des Befehlsmodells | Tatsachlich verwendeter nativer P300-GFA-Aufruf, falls vorhanden |
| Existierender virtueller GFA-Spiegel | FC01 koennte ohne Wechsel genuegen | Adresse, exakte Bedeutung, Breite, Skalierung, Aktualitaet fuer alle benoetigten Kanaele |
| Autonom aktualisierte GFA-Daten im Regelungs-RAM | FC03 ist auf dieser Anlage real nutzbar | Struktur und Aktualisierung ohne laufende VS1-GFA-Anfragen |
| Dokumentierter indirekter Leseaufruf/Gateway | Koennte Originaldaten liefern | Familienpassender read-only Argumentaufbau; generische KBus-Namen reichen nicht |
| Hybrider Ein-Prozess-Splitter | Verwendet die schon bekannten Pfade | Ausreichende maximale Frische und hinreichend kurze RAM-Serviceunterbrechung |
| Umgekehrte Suche: Physical_RAM unter VS1 | Wuerde eine Vollmigration vermeiden | Keine hier belegte lokale Abbildung von Physical_READ/WRITE; alte GWG-CB/C8-Codes nicht uebertragen |

Es wurde kein unabhaengig belegter nativer P300-GFA-Erfolgsfall fuer **genau 20C2/01.03** gefunden. Die neuen Ansatzpunkte stammen vor allem aus dem erneuten Abgleich des vorhandenen Research mit den Protokollquellen, nicht aus einem fertig nutzbaren Fremdprojekt.

### 4.4 RAM-Spiegel: besonders auf Aktualitaet achten

Der vorhandene Physical_READ-Nachweis erschliesst echten Kommunikations-RAM. Darin koennen aber auch **alte GFA-Antworten** liegen. Ein Byte, das nach einem VS1-Read unter P300 wiedergefunden wird, beweist noch keine kontinuierliche Datenquelle. P06=00 und P80=20 sind als einzelne Bytewerte besonders unspezifisch.

Nachweisplan, noch nicht ausgefuehrt:

1. Vorhandene RAM-Snapshots offline mit mehreren markanten Werten und Verlaeufen vergleichen, nicht nur einzelne Nullbytes suchen.
2. Optolink-RX/TX-Puffer, alte Antworten und zufaellige Gleichheit als Erklaerung ausschliessen.
3. In einem separat freigegebenen read-only Zeitfenster pruefen, ob sich der Kandidat bei natuerlichen Betriebswechseln weiter aktualisiert, **ohne dass VS1-GFA-Reads ihn auffrischen**.
4. P06/P09/P87 jeweils unabhaengig semantisch validieren und Aktualitaet/Gueltigkeit beobachten. Bei nichtatomaren Snapshots Konsistenz der Struktur beachten.
5. Keine Zeiger-, DMA- oder Mailbox-Schreibzugriffe, um eine Aktualisierung zu erzwingen.

Die alte Deutung `0x55D3[6:7] = Geblaesedrehzahl` ist bereits widerlegt. P09 ist in dieser GFA-Variante ein **Modulationssollwert**, nicht die gemessene Drehzahl. Ein anderer Modulationskanal oder ein eingefrorener letzter Wert ersetzt die benoetigte GFA-Funktion nicht.

## 5. Die 2,1 Sekunden sind nicht das einzige Erfolgskriterium

Fuer einen P300-Grundbetrieb mit VS1-GFA-Fenstern waere zu messen:

```text
T_unbeobachtet = Wechsel nach VS1 + GFA-Block
              + Wechsel nach P300 + Queue-/Reaktionszeit
```

Der RAM-Reload ist asynchron. Selbst ein Schreibintervall unter 2,1 s garantiert daher keine durchgehende Pumpenvorgabe: Die Firmware kann kurz nach dem letzten Repair zurueckschreiben. Relevant sind maximale Abweichungsdauer, Phase, Jitter und die reale Pumpenreaktion. Die beobachteten 2,1 s sind zudem kein zugesichertes Echtzeitlimit.

Ein endlicher Benchmark liefert keine absolute Worst-Case-Garantie. Er muss wenigstens Median, P95, Maximum, Fehler/Recoveries, Datenalter je GFA-Kanal und laengste Unterbrechung des RAM-Service erfassen. Ein schneller Durchschnitt allein reicht nicht.

Bleibt der Rundwechsel mehrere Sekunden lang, ist ein Fork als Wartungswerkzeug trotzdem nuetzlich. **Den dauerhaften E7-Override wuerde das nicht freigeben.** Dafuer waere ein autonom frischer GFA-Spiegel unter P300 oder ein anderer verstandener, weniger timingkritischer Pumpenpfad attraktiver. Wiederholtes persistentes E7-Schreiben bleibt kein Ersatz.

## 6. Priorisierter naechster Arbeitsplan

**A. Offline-Befehlsmodell:** Enum, Transportwahl und echte Serialisierung in den schon benannten Vitosoft-Methoden trennen. Keine erfundenen Prefixe, Teilnehmernummern oder RPCs an die Therme senden.

**B. Neuer read-only Timingnachweis:** Erst den bekannten Ablauf in Teilzeiten erfassen, dann hoechstens eine begruendete Variante aendern. Eine offene Verbindung, monotone Zeitstempel, exakte Identitaetspruefung und GFA-Read statt bloss `active` oder beliebiger Antwortbytes. Keine aktiven Schreibtransaktionen; begrenzte Versuche und unabhaengiger Rollbackplan. Host-Zeitstempel nicht mit exakten Leitungszeitstempeln verwechseln.

**C. Fork-Entscheidung nach Messung:** Bei brauchbarem Wechsel kleine zentrale Zustandsmaschine entwickeln. Bei weiterhin zu langen Pausen Hybrid nur fuer Wartung, paralleler Schwerpunkt auf frischer P300-GFA-Quelle. Bei gefundenem nativen P300-Aufruf zuerst isolierte Lesebestaetigung und Vergleich mit VS1.

**D. Erst danach RAM-Anwendung:** Vollstaendige Kommunikations-/Frischeparitaet, Update und Recovery vor Pumpen-/Vitotrol-Schreibexperimenten. Ein vorhandener RAM-Zugang beweist weder die Feldsemantik noch eine sichere Emulation.

## 7. Was hier geaendert wurde und was nicht

Dieser Arbeitsschritt dokumentiert Recherche, Korrekturen, Optionen und den neuen VS1-Rollbacknachweis im P300-Branch. **Keine Runtime-Aenderung, kein neuer Fork, kein Deployment und keine neue Liveprobe.** Der aktuelle CANARY und die produktive VS1-Konfiguration wurden nicht veraendert. Die bestehenden C9-Aktivierungsanweisungen sind historische Reproduktion und kein Auftrag zu einem erneuten identischen Versuch.

Fazit: **Ja zu einem eigenen, wartbaren Splitter mit dynamischer Protokollwahl. Ja zur weiteren GFA-P300-Suche. Zuerst die zwei konkreten Unklarheiten klaeren: ENQ-Wartefolge und abstrakte C9-Abbildung.**

Siehe [Quellenaudit und Fundstellen](p300-switching-source-audit-2026-10-08.md), [Migrationsstatus](p300-migration.md) und [C9-Hardwarebefund](p300-gfa-c9-hardware-rejection-2026-10-08.md).
