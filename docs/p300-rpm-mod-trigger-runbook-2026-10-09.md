# WB2A: echter VS1-P06-Vergleich bei zwei natuerlichen Modulationsniveaus (09.10.2026)

**NEUER EIGENSTAENDIGER Forschungstest.** Geraet 20C2, SW 0103, GFA P80 20. Nur Aufgabe 1. Produktives /opt/optolink bleibt unveraendert, PR #46 bleibt Draft. Dieser Test ist offline in GitHub-CI geprueft, aber **noch nicht an realer Hardware als Canary ausgefuehrt**.

## 1. Wissenschaftliche Frage

Die beiden RAM-Kandidaten 0x0F20 und 0x1C76 sind eng mit dem Brenner verbunden. Die zweistuendige P300-Temporal-Aufnahme zeigte zeitweilig 29/27 unterschiedliche Rohwerte (bis AC). Der letzte natuerliche Nachtlauf mit 2185 validierten Zyklen hatte dagegen konstant RAM=54 bei Flamme EIN und schwankende native Modulations-/Statusbytes; sein altes HIGH-RAM-Triggerkriterium RAM>=88 konnte nicht ausloesen. **Es gab bislang keine echte P06-Gegenmessung bei nativer hoher Modulation**.

Neuer Ansatz: P300 beobachtet nur bekannte Status-/RAM-Daten. Vier hintereinander gueltige natuerliche Statuszyklen mit hoher Modulation loesen EINEN echten VS1-GFA-P06-Vergleich aus. Vier gueltige Statuszyklen mit niedriger Modulation bei derselben beobachteten Flamme loesen spaeter einen ZWEITEN echten P06-Vergleich aus. Wenn dieselben RAM-Bytes 54 bleiben und echte P06 deutlich unterschiedliche stabile positive U/min liefert, ist die simple Istwert-Kodierung P06_raw=RAM-1 widerlegt. **Modulationsbytes sind nur Triggerindikatoren, nie reale Geblaese-Istwerte.**

## 2. Bereits offline an privaten Originalarchiven geprueft

- 9.10.2026 RPM-Trigger-Kurzlauf: **2185** P300-Zyklen, **16 aufeinanderfolgende HIGH-qualifizierte**, gefolgt von **256 LOW-qualifizierten** Zyklen im EINEN natuerlichen Brennerlauf. Die hypothetischen HIGH- und LOW-Ausloeser waeren bei diesem echten Datenverlauf beide erreichbar gewesen.
- 9.10.2026 Temporal-Fullrun: **5224** P300-Zyklen mit insgesamt **173 HIGH-** und **1276 LOW-qualifizierten** Zyklen in mehreren Brennerfenstern.
- Das Replay erfolgte mit den nachstehenden tatsaechlichen Status-/RAM-Qualitaetsregeln (nicht nur anhand von Durchschnittswerten). Es ist **keine Garantie fuer kuenftige Heizlast oder P06-Stabilitaet**.
- Diese Originalarchive bleiben privat, nur aggregierte Zahlenergebnisse kommen nach Git.

## 3. Exakte erlaubte Hardware-Telegramme

Ausschliesslich die bewaehrten P300-Leser:
- FC01 Adresse 0x55D3 Laenge 11 (Status A UND B um jedes Paar)
- FC03 Adresse 0x0F20 Laenge 32
- FC03 Adresse 0x1C60 Laenge 32 (enthaelt 0x1C76)

VS1: korrekte Geräte-ID 20C2, SW 0103 und bereits bewiesene **echte GFA-Lesebefehle** P80, P06, P09, P87, P10, P84; kein GFA-/Regelungswrite. Echte P06-Rohwerte werden mit Faktor 30 in U/min umgerechnet, FF ist ungueltig.

KEINE unbekannten FCs 201/C9/09/RPC, keine willkuerlichen virtuellen Datenpunkte, keine SFR-/UART1-U1RB-RX-Reads, keine EEPROM- oder RAM-Writes, keine kuenstliche Brenneranforderung.

## 4. Triggerbedingungen

Fuer **jeden von vier unmittelbar aufeinanderfolgenden** P300-Zyklen:
- Status A UND B: Flame EIN, Lockout AUS, keine Flame/P87/Lockout-Aenderung *innerhalb* des Zyklus.
- Beide Kandidaten-Rohbytes **0x0F20=0x54 UND 0x1C76=0x54**.
- Zuerst **HIGH**: FC01 Byte0 >=60 UND Byte9 >=55, an beiden Statusendpunkten.
- Erst nach erfolgreichem HIGH-VS1→P300-Ruecklauf **LOW**: FC01 Byte0 <=42 UND Byte9 <=40, an beiden Endpunkten.
- LOW mindestens **15s nach HIGH**, hoechstens **600s danach**; bei einem beobachteten Flammen-AUS wird die LOW-Armierung verworfen. Ein sehr kurzer unbeobachteter Flammenwechsel im VS1-Messloch ist theoretisch nicht auszuschliessen.
- Maximal **2** Trigger (HIGH und LOW), danach automatischer geordneter Abschluss.
- HIGH-/LOW-Rohwerte 54 bleiben **nicht** automatisch als P06 freigegeben; die alte hypothetische Formel (54-1)*30 = 2490 U/min wird nur als falsifizierbare Hypothese protokolliert.
- VS1 misst mindestens sechs Runden, je zwei echte P06 plus P09 und P87, P80 vorher/nachher, mit Einzelzeitstempel. Danach zwei statusgeklammerte P300-Nachmessungen. Ergebnislabel COMPLETE beschreibt nur den Protokollablauf, NICHT einen bewiesenen P06-Alias.

## 5. Laufzeit, Stopp und Safety

**Eigener systemd-Dienst:** optolink-p300-rpm-mod.service. **Eigene Session:** /root/p300-trial-work/p300-rpm-mod-results/run-UTC-PID. Start- und Stopskript: tools/wb2a-p300-rpm-mod-trigger.sh.

Der Port bleibt exklusiv beim Worker, produktive Optolink-Telemetriedienste werden fuer die Forschung temporaer pausiert. Steuerung am Geraet bleibt unangetastet; fuer MQTT/HA ist mit Datenluecken zu rechnen.

- **Pflichtcanary:** 300s Budget, mindestens 240s P300-Stream und 30 komplette Zyklen, **keine ausgeloesten Zwischen-VS1-Trigger**, gueltiger Rückwechsel/Restore und eigene hashgebundene Canary-Session (alter HIGH-RAM-Canary gilt nicht).
- Full 1h Standard, optional 2h; **maximal 2** gegliederte echte VS1-P06-Zwischenmessungen.
- Keine zweite Optolink-Instanz gleichzeitig; versiegelte Kopien aller sieben Python-Quellmodule und SHA256; Root/Branch/Exklusiv-Port/sauberer Git-Checkout/alte Recovery geprueft. Min. 768MiB vor Start, 256MiB während Lauf, 192MiB private Session-Obergrenze und 96MiB Einzeldateigrenze.
- SIGTERM nur zwischen ganzen Frames, Worker-Rueckkehr nach VS1, zweite systemd ExecStopPost-Recovery startet produktiven Hauptsplitter ZUERST und danach vorher aktive Zusatzdienste/Timer. Produktion-GFA-P80=20, P06 nonFF pruefen. HA-Entity-Frische braucht extra Nachweis.
- Bei fehlendem Restore, Portkonflikt oder unbekanntem Telegramm nicht erneut starten. Nicht kill -9 benutzen.

## 6. Konkrete LXC-Befehle – nur nach gruener CI

~~~bash
cd /root/p300-trial-work/project
git status --short
git branch --show-current
git fetch origin optolink-p300-migration
git merge --ff-only FETCH_HEAD

# Kein Hardwarekontakt
bash tools/wb2a-p300-rpm-mod-trigger.sh plan

# Einmaliger 5-Minuten-Canary, keine Zwischen-GFA-Trigger
bash tools/wb2a-p300-rpm-mod-trigger.sh canary

# Nur Status; nicht gleichzeitig andere Logger starten
watch -n 15 'bash /root/p300-trial-work/project/tools/wb2a-p300-rpm-mod-trigger.sh status'
~~~

Canary-Full-Gate: UNIT_STATE=inactive; progress.state=RESTORED; measurement.observation_complete=true; measurement.errors=[]; Worker-VS1-Restore=true; recovery.services_restored=true; Health P80=20 und P06 gueltig/nonFF; mindestens 240s/30 Zyklen; privates SHA256-Tararchiv vorhanden. **Canary komplett pruefen, bevor Full gestartet wird.**

~~~bash
# Nur bei erfolgreichem Canary, ideal waehrend der naechsten
# sowieso geplanten natuerlichen Heizphase – nicht nachts kuenstlich heizen:
bash tools/wb2a-p300-rpm-mod-trigger.sh start 1

watch -n 15 'bash /root/p300-trial-work/project/tools/wb2a-p300-rpm-mod-trigger.sh status'

# Ggf. geordneter Stopp
bash tools/wb2a-p300-rpm-mod-trigger.sh stop
~~~

Monitoring: natural_high_modulation_cycles, natural_low_modulation_cycles, trigger_crosschecks (0/1/2), high_plateau_completed, low_plateau_completed, last_crosscheck, numerically_consistent_not_verified, p06_plus_one_mismatches. Nach 2 erfolgreichen GFA-Gegenproben beendet sich die Session selbststaendig. Wenn ein Ereignis fehlt, nur INCONCLUSIVE; kein Heizungs-Write/erzwungener Heizstart.

Archivausgabe: UPLOAD_ONE_FILE=/root/p300-trial-work/research-bundles/p300-rpm-trigger-run-YYYYMMDDTHHMMSSZ-PID-bundle.tar.gz. **Bitte nur dieses eine Archiv hochladen.**

## 7. Danach: alternative P300-Datenpunkte, sinnvoll begrenzt

Die Vitosoft-v6-Profildaten enthalten beim exakten VDensHO1-Zweig **581 Eventzuordnungen**: 462 Virtual_READ, 94 GFA_READ, 22 RPC. Es ist kein bereits dokumentierter normaler P300 Virtual_READ auf den wahren P06-Tacho gefunden. Ein GFA_READ=201 abstrahiert in Vitosoft eine Sonderkommunikation, und VSKO wechselt nach VS1. Das ist kein Firmware-Unmoeglichkeitsbeweis.

Weiter verfolgungswuerdige **GFA-nahe Diagnosen**, als separate Aufgabe-1-Teilparitaet und NICHT RPM:
- FC01 0x7650/1 GFA-Chipkennung (Event 8395, im Zielprofil, exakte Laenge 1 belegt).
- 0x7656 GFA-Codierkartenkennung/Revision; Bytebreite/Profilkontext zuerst pruefen.
- 0x5738 GFA-Konfigurationsfehler; Bytebreite/Anwendbarkeit zuerst pruefen.
- 0x7590 ff. GFA-Fehlerhistorie; nur mit zielprofilbezogenem Beleg.
- FC01 0x55D3/11 P87-naher Feuerungsstatus **schon verifiziert**.
- 0xA305 Modulationsgrad nur bei passender Katalog-Brennertypbedingung, NICHT P06.

Unbekannte RPC-Events zuerst aus dem originalen v6-Profil und dem konkreten Host-Handler **offline** dekodieren. Keine blinden C9/09/07-, FC01-Sweep- oder GFA-Schreibproben an der Therme.

Wenn nach diesen exakt getrennten Wegen kein P300-eigener P06-Istwert eindeutig nachweisbar ist: **Single-Owner Hybrid P300+VS1-GFA** mit nachvollziehbaren Freshness-TTLs, der bereits erforschten Switchzeit, MQTT-/HA-/Service-/Zeitplan-/Party-/Write-Readback-Paritaet. Ein numerischer RAM-Rohwert darf nie als gemessene RPM ausgegeben werden.
