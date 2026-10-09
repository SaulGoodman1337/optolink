# Aufgabe 1: naechster RPM-Wirkvergleich und fallbackfaehige Protokollarchitektur

**Datum 9.10.2026, WB2A 20C2, SW0103, GFA P80=20. Nur Forschungsbranch, PR #46 Draft/unmerged, produktives /opt/optolink bleibt VS1.** Diese Datei ist ein **PLAN**, keine Freigabe, kein gestarteter Hardwarelauf und noch **kein implementierter Logger**.

## Ausgangsbefund und Priorisierung

Der [unabhaengig gepruefte Full-Run](p300-temporal-fullrun-analysis-2026-10-09.md) lieferte 5.224 P300-only-Kernzyklen, 23.028/23.028 valide FC01/FC03-Reads, fuenf komplette natuerliche Brennerzyklen, **29 unterschiedliche Werte an RAM 0x0F20**, 27 an 0x1C76, dynamische Treppe `84→172→...` und wiederholte neun Byte lange FC01-Statuskopien. Daher ist die fruehere Annahme `0F20` sei bloss ein fixes Flammen-EIN/AUS-Flag widerlegt. Eine **echte aktuelle Ist-Drehzahl P06** ist nicht bewiesen. Insbesondere beobachten wir ein fast sofortiges `84→172` **vor** dem Modulationsanstieg – vereinbar mit vorauseilender Geblaeseanforderung. Das vorherige VS1-Referenzfenster P06=**4410 U/min** erbrachte bei zwei kurzen P300-Scans trotzdem Kandidat 84; die Klammern waren danach dynamisch und sind kein atomarer Gegenbeweis, aber ein ernstes Warnsignal.

**Kein weiterer 640-Block-FullRAM-Sweep, kein identischer 2h-P300-only-Logger ohne P06-Gegenmessung.** Falls ueberhaupt ein weiterer Hardwaretest, dann ein neuer **P300-first-triggered / VS1 / P300**-Wirkvergleich, um die Richtung Istwert vs. Sollwert direkt zu pruefen.

## PHASE 0 – jetzt abgeschlossen: Eigentums-/Restore-Integritaet sichern

- Temporal-Archive-SHA256: `f174ee298d60aa2a4a1c31dfc8784a5c0f278475870e823db27bb03d5f06cbda`, Manifest 23/23, Quellhashes 6/6, 23.028/23.028 Frames, keine Writes, alle 5.224 binären Zyklusbezüge stimmen.
- Final: `observation_complete=true`, `data_quality=COMPLETE`, `worker_vs1_restored=true`, systemd success, **sechs zuvor aktive Units wiederhergestellt**; Produktiv-MQTT P80=20, P06=00 (Stillstand, gueltig). `ha_entity_freshness_verified=false` bleibt ausserhalb des gemessenen Gates.
- Keine weiteren Dienstaktionen jetzt noetig. Vor kuenftiger Hardwarearbeit lokale Produktiv-Health und HA-Freshness separat nachvollziehen; sessiongepinnten Code waehrend eines Laufes nie austauschen.

## PHASE 1 – OFFLINE, ohne Kesselkontakt: enge Semantikpruefung

1. Alle `0x0F20`/`0x1C76`-Werte in `core-pairs.bin` mit Quell-Commit sowie den P300-FC01-Rohzeitstempeln verbinden (bereits auditiert). Erklaerbare 9-Byte-Statusspiegel strikt getrennt halten: `0F22..0F2A` und `1C77..1C7F` sind Kopien der ersten neun FC01-`55D3`-Bytes, der davor liegende Wert ist noch nicht erklaert.
2. 84→172-Sprung **vor** Modulationsbyteanstieg und 172→84-Rampe mit Byte0/Byte9 (nur Soll-/Statusindikatoren) und Flammen-/P87-Kanten lagbasiert pruefen; Kausalitaet nicht aus Pearson-Korrelation behaupten. RAM-Kopierverzuege um den gemessenen **0,163s** Kern-Leseversatz herum interpretieren.
3. Fokusarchiv-Captures 4/7/8: echte VS1 P06/P09 mit zeitlicher Distanz und den P300-RAM-Referenzen vergleichen. Kandidat 84 bei PRE-P06=4410 und spaeterer dynamischer POST-P06=3870..4230/4050..4230 ist ein **Testmotiv fuer den kommenden direkten Gegenvergleich**, kein uebertragbarer Ersatz-RPM-Wert.
4. 22 echte VDensHO1-Vitosoft-v6-RPC-Events auf moeglichen konkret belegten GFA-Read untersuchen; abstraktes GFA_READ=201/C9 und VSKO-ChangeInterface(VS1) nicht als native P300-Erfolgsgarantie missverstehen. Keine generischen RPC/C9/09/SFR-/EEPROM-Experimente ohne Host-/Firmwarebeleg.

## PHASE 2 – NUR nach Offline-Code-Review: EIN neuer gezielter read-only Trigger-Logger

**Experimentfrage:** Entspricht der interne Kandidat `x=RAM[0x0F20]` (und `RAM[0x1C76]`) dem realen aktuellen GFA-P06-Rohwert oder eher einem vorauseilenden Geblaese-Soll-/Steuersignal? Zu pruefende numerische Hypothese **nur diagnostisch**: `P06_raw ?= x-1`, entsprechend `x=0x54` → 2490 RPM, `x=0xAC` → *hypothetische* 5130 RPM. Niemals berechnete RPM produktiv publizieren.

### Nur bekannte, strikt begrenzte Telegramme

- P300 FC01 `0x55D3/11`; FC03 `0x0F20/32`, `0x1C60/32` und allenfalls vier bereits freigegebene benachbarte 32-Bloecke; **keine unbekannten SFR-/GFA-/C9-/RPC-/Write-Kommandos**.
- VS1 nur bewiesene GFA-Reads P80=0x4050, P06=0x4006, P09=0x4009, P87=0x4057 (sowie bewiesene 20C2/0103-Identitaet), keine GFA-Writes. P06 FF verwerfen.
- Ein einzelner serieller Besitzer, keine zweite unabhaengige Optolink-Instanz, keine ueberschneidenden systemd-Worker.

### Vorgeschlagene Messabfolge

1. Safety-Preflight: Originalproduktivanlage aktiv/gesund, fuer diesen Versuch genehmigtes exklusives Portfenster, keine aktiven Altlogger, P80=20 / SW=0103, ausreichender freier Speicher, Git-Hash-Pinning, keine Produktionsdatei-Aenderung; sieben Frame-Geometrien und defensiven Restore per deterministischen Offline-/CI-Tests pruefen.
2. Beginne kurz mit echten VS1 P06/P09/P87-Referenzen, wechsel einmal nach P300 und verfolge `0F20`/`1C76` plus native Statusframes. Nur natuerliche Brennerzyklen, **keine erzwungene Waermeanforderung oder Leistungsaenderung**.
3. **Ausloeser:** nach mindestens zwei aufeinanderfolgenden gueltigen und statuskohaerenten P300-Paarreads `0F20≈1C76 >= 0x88` (mindestens 136 dezimal), Flame=true, kein Lockout. Die Schwelle ist bewusst auf den im Full-Run nachgewiesenen **hohen** Wertbereich begrenzt, nicht auf normale 84. Zeitstempel beider echten RAM-Antworten speichern und **sofort** geprueft P300→VS1 wechseln.
4. Unter VS1 sofort fuer ca. 2–4 Sekunden wiederholt echte P06 und P09 lesen (mit absolutem monotonic/UTC-Zeitstempel, z. B. mindestens acht P06-Reads), GFA P80/Identitaet bestaetigen. Beobachte explizit, ob P06 zu dem vorherigen Kandidaten nahe `(x-1)×30 U/min` passt und ob P09 einen ganz anderen Verlauf liefert. **Nicht** eine verlorene/instabile Flamme als RPM-Benchmark verwenden.
5. Nach dem VS1-Lesefenster wieder nach P300 wechseln, ohne Write. Zwei weitere statusgeklammerte P300-Kandidatenpaare lesen. Nur wenn der Kandidat **vor und nach** dem VS1-Fenster stabil im selben hohen Bereich war, ist der dazwischenliegende P06-Wert ein *moeglicher* guter numerischer Wirkvergleich. Ein Kandidatenwechsel waehrend der Luecke → **TRANSITION_OR_UNKNOWN**, kein erzwungener Match.
6. Interpretiere zwei **verschiedene positive Plateaus aus unabhaengigen Brennerzyklen**, plus Kontrollniveau 2490/0. Bei einem stabilen x und stabilen VS1 P06 mit differierender `x-1`-Skalierung Hypothese verwerfen. Bei uebereinstimmenden stabilen Werten erst weitere Timing-/Lag-, P09-Unabhaengigkeits- und Gegenkontrollen verlangen, nicht direkt Produktion umstellen.
7. Logger automatisch begrenzen: **Canary zuerst**, nur falls Transport-/Restore-/Produktiv-GFA-Health bestehen; danach kurze zeitlich begrenzte Session (vorgeschlagen <=2h, ausserhalb normaler HA-Abhaengigkeitszeiten), maximal **vier ausgeloeste** serielle VS1-Gegenpruefungen, mind. **10 Minuten Cooldown** je Trigger, keine automatische Neubestellung von 2h-Laeufen. Erfolgreiche fruehe Evidenz kann Ende ausloesen.
8. Timeout/FF/Identitaetsfehler/SIGTERM/Unplug: **Fail-closed**, laufende TX-Transaktion beenden, P300→VS1-Rueckkehr mit bekanntem Recover-Verfahren, systemd-ExecStopPost stellt alle zuvor aktiven Units wieder her, Hauptsplitter zuerst. Automatischer Health-Check P80=20, P06 nonFF, Produktiv-MQTT und erforderliche HA-Frische. Bei Restore-Fehler **kein** weiterer Test.

### Akzeptanzregeln fuer echte Drehzahl

- Keine zeitgleiche P06 waehrend P300; der Vorher-/Dazwischen-/Nachher-Vergleich bleibt zeitversetzt. Eindeutige **STABLE**-Klassifizierung nur fuer konstanten Kandidaten und wirklich stabiles VS1 P06 ueber die zulassige serielle Luecke; sonst nur dynamisches Indiz.
- Ein positiver Kanal braucht **mindestens zwei verschiedene, deutlich unterschiedliche positive stabile Ist-P06-Level**, korrekte Skalierung (nicht nur mathematischer Fit aus 0/2490), passende zeitliche Reaktionsweise und Unabhaengigkeit von nativen FC01-Status- und P09-Stell-/Sollwerten sowie Optolink-eigenen Puffern.
- `0x54` oder `0xAC` darf niemals vor diesem Nachweis als *aktuelle* RPM an Home Assistant/MQTT ausgegeben werden.
- Wenn die naechste natuerliche High-Phase ausbleibt, Ergebnis **INCONCLUSIVE**, nicht die Temperatur/Brennereinstellung fuer den Versuch veraendern. Vor erneutem Langlauf erst Sinn/Risiko abwaegen.

### Softwarearbeiten vor etwaigem Hardwarestart

- Eigenstaendiger **neuer** Session-Pfad und `systemd`-Unit; bestehende Temporal-/Fokus-Logger **nicht** fuer diese Triggersemantik im Feld patchen.
- Gepinnte Sessionquelle und Hashaudit, exakt sieben freigegebene P300-Rahmen; Output umfasst P06-Einzelzeitstempel, P09-Daten, vollständige P300-Rohframes, Triggerentscheidung, Status/Qualitaet, Signalstopp, 2× echten Wechsel, Recovery/Health und SHA256-Tar-Manifeste.
- Regressionstests fuer `x>=0x88`-Trigger, Cooldown, Abwesenheit natuerlicher Ereignisse, FF-Sperre, P300→VS1-Identitaetstimeout, Phasenwechsel/Teilklammer, Kill/Recover, Serial-Ownership, No-Write und Restore aller vorher aktiven Units. GitHub-CI-PASS und 5-Minuten-Canary **vor** eventueller laengerer Hardware-Session.
- Nutzer muss den spaeteren, separaten Versuch aktiv starten; keine Automatik aus dieser Planungsdatei heraus.

## PHASE 3 – Falls der Kandidat nicht sauber P06 ist: Single-Owner Hybrid fuer Aufgabe 1

**Bevorzugte wartbare Softwarealternative:** **ein** Portbesitzer verwaltet beide Protokolle, mit P300-Batches und periodischen echten VS1-GFA-Lesephasen. Ein Wechsel in der abgeschlossenen Session dauerte **4,329s P300→VS1** plus **2,163s VS1→P300**, zusammen schon **6,492s ohne P06-Scan und Scheduleraufwand**.

Zwei Ausgestaltungen sind vergleichend zu pruefen:

**A. P300-Hauptmodus / VS1-GFA-Phasen:** Alle von P300 nachgewiesen les-/schreibbaren virtuellen Datenpunkte im P300-Modus, eigene *echte* GFA-P06-Abfragephase via VS1. Buendelung aller erforderlichen GFA-Parameter in einer Phase und adaptive Polling-Kadenz. Frische-/Latency-Budget von P06 und sonstigen HA-Entities festlegen, nicht ohne Messung 5s/10s-RPM-Frische versprechen. Keine konkurrierenden Writes waehrend eines Handovers.

**B. VS1-Hauptmodus / kurze optionale P300-Batches:** Bestehende echte P06-/Automations-/MQTT-Funktionalitaet erhalten, P300 nur dann aktivieren, wenn konkrete Mehrwerte belegt sind. Die Migrationsrichtung ist weniger `P300 pur`, dafuer geringeres Risiko und potentiell bessere P06-Datenfrische. Eignet sich als Zwischenstufe, falls A wegen ~6,5s Switchkosten Verfuegbarkeit einbuesst.

**Engineering-Gates fuer beide:** ein FIFO-Serial-Owner, Transaktionsgrenzen und Locking, Fehler-/Watchdog-Zustandsautomat, immer explizite Identitaetsbestaetigung nach jedem Wechsel, unverwechselbare `actual_gfa_p06_rpm`-Provenienz, Zeitstempel/TTL fuer jede Entity, fail-closed auf FF und veraltete Daten, keine Fan-RPM-Schätzung aus P09/55D3, keine aktiven Parallelprozesse. Paritaetsmatrix mit Party-Modus, Zeitprogramm, Clock Sync, Serviceprogrammen, Maintenance API, MQTT/HA-Discovery und Write-Readbacks; echte Prozesswerte und Frische auf Hardware messen. Automatisierte Testtafel inkl. Stromausfall-/Serial-Timeout-/Steckerwechsel- und nicht-funktionierende Verbindungssimulation **offline**, erst dann geschuetzter LXC-Canary. Produktives `/opt/optolink` bleibt bis zum Ende unangetastet.

## PHASE 4 – Weitere Alternativen, abgestufte Plausibilitaet

1. **Hersteller-/Vitosoft-Quellen als Offline-Route:** die 22 echten VDensHO1-RPC-Events mit passenden Handlern/Argumenten und GFA-Referenzen belegen oder ausschliessen; dokumentierter abstrakter GFA_READ=201/0xC9 ist **kein** bewiesener P300-Wire-FC, VSKO-Hostpfad wechselt nach VS1. Niemals `C9/09/07` blind an den Kessel senden. Bereits katalogisierte GFA-Identitaet, Fehlerhistorie, Status `55D3` sind *Teilparitaet*, keine Ist-P06.
2. **Optional externe Drehzahlmessung an HALL**, nur als eigenstaendiges, fachlich freigegebenes, galvanisch korrekt getrenntes Messvorhaben: Viessmann-WB2A-Serviceplan zeigt separaten PWM/HALL/GND-Geblaesepfad. **Nicht** am laufenden Kessel ohne qualifizierte Sicherheits-/EMV-Pruefung abgreifen und keine Anschlussanleitung als Software-Fallback. Das waere eine neue Hardwareloesung, keine P300-Funktion.
3. **KM-Bus** aus anderen Tasks nicht als Geblaese-P06-Ersatz behandeln: nach Herstellerplan separater Bus, master-TX im P300-SRAM belegt, aber **kein** unabhängiger Geblaese-HALL-Tacho-Stream. RX und Vitotrol erst spaeter, Aufgabe 2 nach Aufgabe 1.
4. **Nicht vertretbar:** allein aus P09/Modulationsgrad RPM schätzen und als tatsaechlich ausgeben, beliebige RAM-Adressen/EEPROMs/SFRs live ausprobieren, parallele Adapter um konkurrierend VS1/P300 zu betreiben, Produktionspatch oder PR-Merge bevor alle Paritaets-/Restore-Gates erfuellt sind.

## Stop/Go Entscheidung

| Beobachtung | Folgeschritt |
| --- | --- |
| Zwei verschiedene positive stabile VS1-P06-Plateaus stimmen zeitlich und numerisch reproduzierbar mit `RAM[0F20/1C76]-1` ueberein, P09/Statuscopy sauber ausgeschlossen | Gezielt *zusaetzlichen* Gegenvergleich entwickeln, danach P300-only als moegliche Quelle pruefen; noch keine sofortige Produktionsfreigabe |
| Stabile hohe RAM-Kandidaten, aber echte P06 weicht um mehr als quantisierte Messunsicherheit ab | **P06+1-Hypothese verwerfen**, Hybrid A/B als naechster Schwerpunkt |
| Nur ein dynamischer transienter, nicht stabiler Rampenfall | **Inconclusive**, weder Ist noch Soll mathematisch festsetzen; Kosten weiterer Experimente gegen Hybrid abwaegen |
| Keine High-Events im zeitlich begrenzten Versuch | Nicht automatisch neu starten; ggf. Hybrid priorisieren |
| Serial-/Recovery-/Manifestfehler | Keine weitere Hardwarearbeit bis vollständiger Restore verifiziert |
| Reproduzierbarer P300-GFA-RPC aus Originalhost/Firmware belegt | Vor jeglichem Versuch formale read-only/Profil-/Length-Review, isolierte Tests und ausdrueckliche Freigabe; derzeit kein solcher Beleg |

**Mein empfohlener Pfad:** Phase 1/offline abschliessen, dann genau **einen** sehr kurzen triggergefuehrten P06-Wirkvergleich bauen und Canary-testen, **oder** bei geringem Mehrwert sofort Hybrid A/B evaluieren. Beides braucht eine getrennte Abnahme; kein Endlos-RAM-Logging.
