# WB2A/Vitotrol – schneller persistenter MQTT-Lesepfad und natürliches Master-0x31/00-Ereignis

**Stand 11.10.2026, 21:25 CEST.** Forschung exklusiv über Optolink/P300 an WB2A `20C2/0103`; kein Hardware-KM-Bus, kein zweiter Portbesitzer, keine RAM-/DMA-/SFR-/UART-/Codierwrites. Die alternative Raumtemperaturregelung bleibt zurückgestellt. PR #52 bleibt Draft, `main` und Produktionskonfiguration unverändert.

## 1. Befund der Codeanalyse – Wo die alte Messlatenz entstand

Der unveränderte produktive `/usr/local/bin/optolink-debug` baut für **jeden Einzelread** eine neue Verbindung zu `openv/resp` via MQTT auf, wartet fest `time.sleep(0.4)` nach der Subscription und pollt die Antwort alle 50 ms. Hinzu kommen MQTT-/Prozessstartkosten, die serielle Controller-Kommunikation sowie der `olbreath=0.025`-Schritt im seriellen Hauptprozess. Die MQTT-Lösung nutzt die bestehende `openv/cmnd`-Queue in `/opt/optolink/mqtt_util.py`: **keine zusätzliche serielle Schnittstelle wird geöffnet**.

Neuer nicht produktiv installierter Forschungsclient: `tools/wb2a-vitotrol-persistent-mqtt-readonly.py`. Eine einzige MQTT-Session, bestätigte Subscription, durchgehende Callback-/Queue-Verarbeitung, explizite feste Read-Whitelist, strict Reply-Code/Adresse/Breite sowie timestamped Antworten. Keine allgemein nutzbare rohe Steuer- oder Schreibfunktion. Die Antwort enthält **keine Transaktions-ID**: konkurrierende identische Adressrequests können bei zeitlicher Überschneidung nicht absolut attribuiert werden; dieses Restrisiko wird ausdrücklich markiert.

| Vergleich | Read-Anzahl | gemessener Median je Request | p95 |
| --- | ---: | ---: | ---: |
| Früherer CLI-basierter P300-Splitterpfad | getrennte Vorläufe | ca. **1.700 ms** | nicht als direkt vergleichbarer Wert belegt |
| **Persistentes MQTT in produktivem VS1** | **25/25** | **107,420 ms** | **164,383 ms** |
| **Persistentes MQTT in temporärem P300** | **107/107** | **231,777 ms** | **276,787 ms** |
| Ereignisgesteuertes persistentes P300 | **134/134** | **239,538 ms** | **277,886 ms** |

Die P300-Optimierung von ca. 1.700 ms auf ca. 232 ms ergibt **ungefähr Faktor 7,3**; die alten und neuen Messreihen sind nicht identisch instrumentiert, daher als Größenordnung, nicht als streng kontrollierte A/B-Performanceaussage. P300 bleibt länger als VS1; die Hardwareantwortzeit wird durch den neuen Client nicht per se beschleunigt.

## 2. Erstes schnelles P300-Fenster: 32 Zyklen / 107 gültige FC03-/Status-Reads

Beginn **21:20:34**, automatische Rückstellung **21:21:03**. In jedem Zyklus `FC03 0x164B/32` (letztes RX-CRC-Byte + erstes Metabyte), `FC03 0x164C/32` (beide Metabytes gemeinsam), `FC03 0x161A/32` (ganzer Master-TX-Frame samt CRC). Wechselnde Reihenfolge. Separate Identitäts-, Status- und Teilnehmer-Guards vorher/nachher.

| 32er-P300-Sample | Ergebnis |
| --- | --- |
| RX-Copy `0x164B`-Endbyte / `0x166A` | **32× `C6|06`** |
| Gemeinsames Metapaar `0x166A/0x166B` | **32× `06 00`** |
| Master-TX-Header | 21× `0100B1`, 10× `2000B3`, 1× `010031` |
| Master-TX-Frame-CRC | **32/32 gültig** in jeweils einer FC03-Kopie |
| Teilnehmerindex/Sensor | `00000000` / `03` |

Rohdatei nur im LXC: `/tmp/wb2a-vitotrol-persistent-p300-live-20261011.json`, SHA256 **`d536214e77677c3659510f3bc23e4ee80ba75f81ad3e70985a4d721349c84129`**. Strikter Offline-Auditor `tools/wb2a-vitotrol-persistent-rx-audit.py` prüft alle 107 Antworten einschließlich Replies, Größen, Zeitordnung und Guard-Status. Diese Serie traf **keinen** seltenen Metadatenzustand, demonstriert aber die wesentlich dichtere Beobachtung.

## 3. Natürliches `0x31`-Ereignis unter 96 CRC-validen Master-TX-RAM-Kopien

Neuer ereignisgesteuerter Optolink-only-Client: `tools/wb2a-vitotrol-persistent-event-watch.py`; 96 vollständige Master-TX-Speicherreads (je `FC03 0x161A/32`). Nur bei passendem **CRC-validem** Header `010031`, `2000B3` oder `110033` werden sofort der volle Kandidaten-RX-Frame (`0x1640/32`), Metadaten (`0x164C/32`) und der Master-TX-Puffer nochmals nacheinander ausgelesen. Parallel alle acht Pollversuche eine normale Referenz-RX-/Metaprobe. Bounded maximal 16 Eventfolgeproben. Keine bekannten oder vermuteten Empfangs-IRQ-/DMA-Trigger.

Live **21:23:53 bis 21:24:29**; 96/96 Master-Copies CRC gültig: **95× `0100B1`** und **1× `010031`**. Insgesamt **134/134** bestätigte Read-Requests, 12 normale Referenz-RX-Proben, **ein einziges** automatisch ausgelöstes Event bei Poll **85**.

**Originales Event (alle Hex-Pakete vollständig CRC16/Kermit-gültig):**

| Aufeinanderfolgender FC03-Kopiervorgang | Ergebnis |
| --- | --- |
| Master-TX `0x161A/32` | `01 00 31 09 01 01 00 27 FA` – **Abfrage Register 00** |
| Unmittelbarer RX-Speicher `0x1640/32` | `00 01 B1 0A 01 01 00 00 43 53` – **B1-Antwort zu Register 00** |
| Metadata-Speicher `0x164C/32` | `0x166A=0A`, `0x166B=07`, also **`0A 07`** |
| Master-TX erneut `0x161A/32` | `01 00 B1 0A 01 01 01 05 5C 03` – neuer B1-Pufferinhalt, CRC gültig |

**Reproduzierbare Zeitstempel der vier echten Controllerreads:**

| Kopie | Start relativ zum ersten TX-Read | Ende relativ zum ersten TX-Read | Read-Dauer |
| --- | ---: | ---: | ---: |
| Master 0x31/00 | 0,000 ms | 275,227 ms | 275,227 ms |
| Vollständiges RX-B1/00 | 275,538 ms | 524,382 ms | 248,844 ms |
| `166A/166B` | 524,607 ms | 773,745 ms | 249,138 ms |
| Master danach | 773,988 ms | 1.025,304 ms | 251,316 ms |

Der **Hostabstand** zwischen erstem Master-Readabschluss und RX-Readstart beträgt 0,311 ms. Das macht die eventgesteuerte P300-Readsequenz wesentlich zeitnäher als frühere CLI-Reads, **aber die Controller-Kopien selbst sind zeitversetzt um jeweils ca. 250 ms**. Nicht daraus ableiten, dass der elektrisch übertragene KM-Bus-Request, die Slaveantwort oder der UART1-IRQ innerhalb von 0,311 ms abliefen.

Die 12 ohne Trigger erhobenen Voll-RX-Referenzproben enthielten stets die CRC-gültige normale B1-Variante `00 01 B1 0A 01 01 10 00 D2 C6` mit Metapaar `06 00`. Der Vitotrol-Teilnehmerindex blieb `00000000`, Sensorstatus `03`.

## 4. Wichtigster neuer Negativbefund: Die behauptete +6-Metadateninvariante ist **widerlegt**

Vor diesem Ereignis waren aus 79 alten RAM-Snapshots und acht gemeinsamen Live-Metacopies nur die Paare `06 00` (86×) und `0A 04` (1×) bekannt. Beide ergaben `(0x166A-0x166B)&255=6`. Der nun **innerhalb eines einzigen** `FC03 0x164C/32`-Controllerreads erfasste neue Wert ist **`0A 07`**, Differenz **3**. Daher gilt **keine allgemeine konstante +6-Offset-Regel**; die zuvor diskutierten starren Reader-/Writer-Cursor sind keine gesicherte Erklärung.

Zusätzlich wurde der neue **volle 32-Byte-`0x164C..0x166B`-Metablock** byteweise gegen **historischen FullRAM-Snapshot 64 vom 09.10.2026** (Originalarchiv-SHA und Einzeldateimanifest überprüft) verglichen. **31/32 Bytes sind identisch**, allein **`0x166B`** wechselt von `04` nach `07`; `0x166A` bleibt `0A`. Auch der **vollständige seltene B1/00-Frame** ist in beiden archivierten Speicheransichten **10/10 Bytes identisch**. Das ist eine klare Reproduktion des alten Sonderframe-Kontexts bei **neuem** benachbartem Statusbyte.

Strict forensic audit: `tools/wb2a-vitotrol-master31-register00-event-audit.py`; event-Quell-SHA256 **`26669707fbd572f25a384b865740c730ec9f4b7e1035cde33cbb142ae99d2e27`** und 79er FullRAM-Archiv-SHA256 **`94d5842b6dc5759ecb446a4c617b60b72873b639885d116032f783abdef8431c`**. Vergleich im ROOT-Modus vollständig erfolgreich. Die generierten Ergebnisse bleiben privat bei `/tmp/wb2a-vitotrol-master31-register00-event-audit-20261011.json`.

**Einschränkung:** Master-TX-RAM-Kopie und Slave-RX-RAM-Kopie sind semantisch passende CRC-validierte Telegramme und zeitnah nacheinander sichtbar, aber **keine elektrische KM-Bus-Aufzeichnung** und **kein Beweis einer echten firmwareseitigen RX-ISR-/Vitotrol-Queue-Verarbeitung**. Die beobachtete Klasse `01` ist weiterhin **nicht** die erwartete Klasse `11` der Vitotrol 200/300. Weder durchgehender Program-ROM-Zugriff noch erfolgreicher Vitotrol-Enrollment wurde erreicht.

## 5. Sicherheit, Reproduzierbarkeit und nächste Gate-Prüfung

Jede P300-Livesitzung verwendete vor dem temporären Protokollwechsel einen unabhängigen **4-Minuten-systemd-Restore-Timer**, dazu ein unmittelbares EXIT-Restore und begrenzten 130-Sekunden-Worker. Danach `vs1protocol=True` mit unverändertem SHA256 **`e9a120ef37fe17236a7505ee713c8dd338d98d5093ed75dfb34629d7e8f5c42d`**, `VS1_BETRIEB_OK`, originaler Einzelportbesitzer und aktive Produktivdienste. Alle Tests haben **0 Controllerwrites** durchgeführt. Der bereits nicht mehr vorhandene alte RPM-Passive-Resume-Dienst wird weiterhin als harmlose Restore-Abhängigkeitswarnung protokolliert.

Neue Programme: persistenter MQTT-Diagnoseclient, `persistent-rx-audit.py`, `persistent-event-watch.py`, `master31-register00-event-audit.py` mit eigenen Offline- und Echtdaten-Regressionsmodulen. Alte Quellen werden nicht ersetzt; im älteren Metadatenbericht muss die statische +6-Invariante ausdrücklich durch diesen **neuen Gegenbeweis** korrigiert werden.

**Priorisierter nächster Schritt:** Den natürlichen `0x31/00`-Follow-up in einem weiteren **gezielt begrenzten** Lesefenster um **mehrere rasch aufeinanderfolgende `0x166A/0x166B`-Kopien** und allenfalls den historisch lesbaren Status bei `0x0B6B` erweitern. Ziel: Unterscheiden, ob `0x166B=07` nur transient nach Register-00-Verarbeitung ist oder stabil bis zur nächsten B1-Antwort bleibt. Kein `0x166A`-/`0x166B`-Write und kein fingierter UART1-Interrupt. Nur wenn ein eindeutiger Consumer- oder Dispatcher-Eingang im lesbaren Controllerpfad belegt ist, folgt ein aktiver Vitotrol-Emulationsversuch.

## Nachtrag 11.10.2026, 21:33 CEST: Kurzlebigen Zustand direkt nach natürlichem 0x31/00 gemessen

**Neue unabhängige P300-Session:** Start 21:31:28, Ende mit erfolgreichem Restore 21:32:26 CEST. Optolink-only, derselbe Splitter-Portbesitzer, vorab aktivierter unabhängiger 4-Minuten-Restore-Timer, 130-Sekunden-Timeout, 0 RAM-/Controller-/SFR-/DMA-/UART-/Codierwrites. Programm `tools/wb2a-vitotrol-register00-meta-transition.py`, Sicherheits-/Synthetic-Fixtures `tests/test_wb2a_vitotrol_register00_meta_transition.py`. Strikt auf 256 natürliche TX-Pollversuche begrenzt, bei CRC-validem **genauem** Master-Register-00-Frame sofort Stop-on-Event und acht aufeinanderfolgende Metapair-Reads. Der Controller wurde in keiner Weise zur Aussendung eines 0x31-Kommandos angeregt.

**Messresultat:** Nach **199** TX-Polls tatsächlich der erwartete CRC-gültige Master-Request `01 00 31 09 01 01 00 27 FA` sichtbar, insgesamt **221/221** bestätigte READs, P300-Median **235,365 ms**. Alle TX-Header in 199 Polls: 167× `0100B1`, 30× `2000B3`, 2× `010031`. Der sofort nach dem passenden Register-00-Request separat gelesene volle Klasse01-RX-Frame war erneut **CRC-gültig `00 01 B1 0A 01 01 00 00 43 53`**, also dasselbe spezielle B1/00-Muster wie bei den vorangehenden Ereignissen.

**Acht zeitlich aufeinanderfolgende, jeweils 32 Byte breite `FC03 0x164C/32`-Metadatenkopien ergaben:**

```text
Messung 0: 0x166A/0x166B = 0A 08
Messung 1: 0x166A/0x166B = 06 00
Messung 2: 0x166A/0x166B = 06 00
Messung 3: 0x166A/0x166B = 06 00
Messung 4: 0x166A/0x166B = 06 00
Messung 5: 0x166A/0x166B = 06 00
Messung 6: 0x166A/0x166B = 06 00
Messung 7: 0x166A/0x166B = 06 00
```

Zwischen den **Antwortende-Zeitpunkten** des ersten (`0A08`) und zweiten (`0600`) FC03-Metareads lagen **229,755 ms**. Die exakte controllerinterne Umschaltzeit liegt nur **zwischen den beiden sequenziellen Speicherproben**, nicht bekannt innerhalb dieser 229,755 ms. Der anschließend erneut ausgelesene vollständige RX-Puffer enthielt wieder den CRC-gültigen Normalframe `00 01 B1 0A 01 01 10 00 D2 C6`, der Master-TX-Puffer ein CRC-gültiges B1. SWIndex weiter `00000000`, Raum-Sensorstatus `03`; **keine Vitotrol-Teilnehmeranmeldung**.

Zusammen mit den Originalarchiven sind nun **drei getrennt beobachtete Sonder-Metapaare** belegt: historischer FullRAM-Snapshot 64 → `0A 04`, kurzes natürliches Event 85 → `0A 07`, jetzt Event 198 → **`0A 08`**. Damit ist eine stets konstante Offsetdifferenz `0x166A-0x166B=6` endgültig unhaltbar. Das im neuen Experiment unmittelbar danach beobachtete **`0A08 -> 0600`** stützt die Hypothese eines kurzlebigen KM-Bus-RX-Verarbeitungszustands; **es identifiziert aber weder den UART1-ISR noch einen Firmware-Consumer, der für Klasse11-Vitotrol-Emulation aus Optolink aufrufbar wäre**.

**Forensische Dreiquellenprüfung:** `tools/wb2a-vitotrol-register00-metaprogression-audit.py` mit Einzel- und SHA-Verifikation gegen vorheriges Event und historische FullRAM-Probe. Neue private JSON-Datei `/tmp/wb2a-vitotrol-reg00-metaprogress-live-20261011.json`, SHA256 **`a7194c20d6582b7c71cba1626c867e523b5cd2aec978292ad235cc75281c1b04`**; vorherige Quellen `26669707fbd572f25a384b865740c730ec9f4b7e1035cde33cbb142ae99d2e27` und `94d5842b6dc5759ecb446a4c617b60b72873b639885d116032f783abdef8431c`. Root-Zugriff auf alle drei Originaldateien: kompletter 4/4-Regressionstest erfolgreich. Private Rohdaten bleiben vom Git-PR ausgeschlossen.

**Betrieb nach Restore:** Wieder VS1, Konfigurations-SHA unverändert `e9a120ef37fe17236a7505ee713c8dd338d98d5093ed75dfb34629d7e8f5c42d`; alle produktiven Dienste aktiv, Fehler `00`, Event-Restore-Timer inaktiv. Die bereits vorher fehlende alte RPM-Resume-Unit verursacht lediglich die bekannte Warnung.

**Nächstes tatsächliches Forschungs-Gate:** `0x166A/0x166B` mit dem ursprünglichen M16C-Adress- und Codekontext korrelieren (z.B. über statische RAM-Deskriptoren, bereits vorhandene VitoSoft-/Controller-Quellen), damit aus dem bislang nur lesbaren kurzlebigen Ereignis eine sichere RX-Consumer-Routine wird. Kein UART1-IRQ-/DMA-Write auf Basis der gegenwärtigen Korrelationsmessungen.
