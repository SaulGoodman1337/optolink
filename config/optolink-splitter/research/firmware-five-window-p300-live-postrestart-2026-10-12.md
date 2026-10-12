# WB2A 20C2/0103 – erfolgreicher P300-Lesetest an fünf SRAM-Fenstern nach Controller-Neustart

**12.10.2026, 21:30 Uhr CEST.** Ziel: Das ROM→SRAM-Kopierhypothesenpaar A/B anhand **echter neu aufgenommener** und gegenüber allen 79 historischen P300-FC03-Bildern vom 09.10. bytegleich attestierter SRAM-Fenster abgrenzen. Dies ist ein **erfolgter realer Test am Gerät**, keine Simulation. Keine Controller-Speicherschreibbefehle. **Kein Programm-ROM-Dump.**

## 1. Live-Ablauf, Restore und Provenienz

- Livegerät über vorhandenen VS1-Optolink-Splitter vor Beginn: **`20c2000300000103`**.
- **Fehler-Baseline:** über den Original-Splitter in VS1 komplett gelesen, exakt **alle zehn Systemfehler- und zwanzig GFA-Fehlerarchiv-Slots** sowie aktuelle System-/GFA-Statusbytes `00/00`. Originaldatei `/tmp/wb2a-5win-fault-baseline-20261012.json`, SHA256 `316caaebf012431b7c7089a897b002d1c3976c276c080b4a748a6e00b04ee2b1`, Aufnahme-Ende 19:26:32 UTC.
- Vor Umschaltung gegen originale Fehlergate-Implementierung auf komplette Historien und Alter **229,3 Sekunden** geprüft; **kein aktiver Statusfehler**.
- **21:30:21 CEST:** mit `systemd-run` unabhängigen Rückstelltimer `wb2a-postrestart-5win-restore-20261012.timer` für **drei Minuten** aktiviert und dessen Status geprüft; Restoreziel ist das **bereits vorhandene**, früher verwendete Original-`/root/wb2a-vitotrol-dual-readonly-20261011/restore.sh`. Konfigurations-SHA vorher sowie SHA des originalen Restore-Backups beide `e9a120ef37fe17236a7505ee713c8dd338d98d5093ed75dfb34629d7e8f5c42d`.
- Danach temporär den **bereits vorhandenen** seriellen `optolink-splitter.service` gestoppt, `vs1protocol = False` gesetzt und **denselben seriellen Eigentümer** im nativen P300 wieder gestartet. Keine neue CP2102-Verbindung und keine parallele UART-Anwendung.
- **21:30:29:** Datenaufnahme fertig: eine Gerätekennung, je vier Status-Guards vor und nach, und exakt **zehn** `P300 FC03 Physical_READ`-Anfragen: fünf fest deklarierte Adressen à **32 Bytes**, je zweimal, zweite Runde in umgekehrter Reihenfolge. Summe **19 Controller-Lesetelegramme, null Schreibtelegramme**.
- Exit-Trap rief die gespeicherte VS1-Rückstellung auf, und bestätigte **`VS1_RESTORE_CONFIRMED`**, Service aktiv und originale Datei-SHA. Unabhängigen Timer danach wieder deaktiviert; `ActiveState=inactive`.
- Alle **fünf produktiven Dienste** nach Test `active`, ursprüngliches `vs1protocol = True`, Konfigurations-SHA unverändert.
- Neues privates, hostgebundenes P300-Original: `/tmp/wb2a-postrestart-five-window-live-20261012.json`, SHA256 **`ed290530bdd718dd044bd57b07d94c160fb15728a74f3486872cd12fcaa64549`**. Bytes sind aus tatsächlichen original-owner MQTT-Physical-READ-Antworten, jedoch **nicht** durch unabhängige CPU-Signaturen kryptographisch authentisiert.
- Vergleichsquelle: vollständiges privates Archiv `/root/p300-trial-work/research-bundles/p300-fullram-run-20261009T083607Z-144293-bundle.tar.gz`, SHA256 **`94d5842b6dc5759ecb446a4c617b60b72873b639885d116032f783abdef8431c`**, **79** einzeln im Manifest attestierte nichtatomare 20.480-Byte-FC03-SRAM-Aufnahmen.

## 2. Live-Zyklen und Vergleich zu ALLEN 79 Originalaufnahmen

| Einzig erlaubte P300-FC03-RAM-Adresse | 2 neue Zyklen identisch? | Unterschied zum ersten 09.10.-32-Byte-Fenster pro neuem Zyklus | Über 79 alte Bilder stabile Bytepositionen |
|---|---|---|---:|
| `0x1DE0/32` | **Ja** | 0 / 0 | 30 |
| `0x1E60/32` | **Nein** | 8 / 11 | 11 |
| `0x3300/32` | **Ja** | **7 / 7** | **32** |
| `0x0700/32` | **Ja** | 0 / 0 | 32 |
| `0x2180/32` | **Ja** | 4 / 4 | 30 |

Das echte Original-`0x1E60`-Fenster änderte sich während der lediglich Sekunden auseinanderliegenden Durchläufe an **13 Adressen**: `0x1E60..64`, `0x1E67..68`, `0x1E79` und `0x1E7B..7F`. Der hypothetische 8-Byte-ROM-Quellpointer `0x1E6A..71` selbst blieb jedoch exakt identisch. Die beiden RAM-Aufnahmen sind **nacheinander ausgeführte Leseanfragen**, kein atomarer CPU-Halt.

Die **fünf konkreten Teilbereiche**:

| Ursprüngliche Hypothese | Altwerte in 79/79 Bildern | Beide neue Werte | Ändert sich seit altem Archiv? |
|---|---|---|---|
| **A-8-Byte-Tupel `0x1DE5..1DEC`**, hypothetisch `0xEA2AB → 0x3301/29` | 1 Form | exakt gleiche 8 Bytes | **Nein** |
| **B-8-Byte-Tupel `0x1E6A..1E71`**, hypothetisch `0xFB27D → 0x0705/7` | 1 Form | exakt gleiche 8 Bytes | **Nein** |
| **A-Ziel `0x3301..331D`, 29 Bytes** | alle 79 Aufnahmen gleich | zwei neue Durchläufe exakt gleich | **Ja, 7 von 29** |
| **B-Ziel `0x0705..070B`, 7 Bytes** | alle 79 Aufnahmen gleich, `64`-Füllmuster | exakt unverändert | Nein |
| Kontrollbyte `0x2184` | `C8` | `CD` | **Ja**, 1 von 1 |

**Besonders bedeutsam:** Der 29-Byte-A-Zielbereich `0x3301..331D` war in **79 Bildern vom 09.10.** vollständig statisch und stimmte **auch in vier unabhängigen P300-Messungen am 11.10.** vollständig überein. Nach dem vom Betreiber vorgenommenen zwischenzeitlichen WB2A-Neustart besitzt er nun **7 andere Bytes**, die in beiden neuen Messungen exakt übereinstimmen.

Die differierenden CPU-Adressen mit den tatsächlichen Einzelbytes:

| CPU-Adresse | 09.10. | 12.10. | XOR | Geänderte Bits |
|---|---:|---:|---:|---:|
| `0x3305` | `4D` | `CD` | `80` | 1 |
| `0x3307` | `8E` | `9E` | `10` | 1 |
| `0x330A` | `AB` | `EB` | `40` | 1 |
| `0x330D` | `FF` | `BF` | `40` | 1 |
| `0x3316` | `11` | `91` | `80` | 1 |
| `0x3319` | `A6` | `26` | `80` | 1 |
| `0x331C` | `0E` | `2A` | `24` | 2 |

**Sechs von sieben Unterschieden sind Ein-Bit-Änderungen, der siebte ist eine Zwei-Bit-Änderung.** Das ist *kein* typischer Nachweis einer neuen über ROM geladenen Codepassage. Ebenso könnte es sich um Zustandsbits, strukturierte RAM-Daten oder andere zeitabhängige Controllerinitialisierung handeln. Wiederholbarkeit über zwei P300-Zyklen schließt zufällige einzelne Kommunikationsartefakte teilweise aus, ist aber noch kein Kausalitätsbeweis.

Ein weiteres echtes Kontrollbyte entwickelte sich in unabhängigen Originalmessungen von **`0x2184 = C8`** (09.10.) über **`CB`** (11.10.) zu **`CD`** (12.10.). Damit war der RAM-Inhalt nie vollständig konstant, auch wenn die ursprünglichen Far-Pointer-Tupel stabil geblieben sind.

## 3. Störungsarchiv, Sicherheitsgrenze und Nachbeobachtung

- Die VS1-Fehler-Baseline vom 12.10. vor dem Test wurde nach **334,39 Sekunden** gegen die unmittelbar nach dem Test erneut aufgenommene vollständige VS1-Historie verglichen: Ergebnis **`NO_CHANGE_OBSERVED`**, **0 neu erkannte Fehler- bzw. Archivänderungen**; alle zehn System- und zwanzig GFA-Slots waren geprüft.
- Private erste Nachaufnahme: `/tmp/wb2a-5win-fault-post0-snapshot-20261012.json`, SHA256 `3ca5fb5e192d57687179bedb7907ca6871ff8a54836a5b88ec5851b3c4d9012f`.
- **T+5 Minuten** wurde eine weitere, vollständig lesende VS1-Aufnahme aller zehn System- und zwanzig GFA-Fehlerslots erstellt: `/tmp/wb2a-5win-fault-post5-snapshot-20261012.json`, SHA256 `6ae0dd86551c5652c15cc1bc429c2d3facd4a2b5f6a2bc0d69b9399bc0602dcf`. Der Offlinevergleich des originalen Fault-Gates ergab ebenfalls **`NO_CHANGE_OBSERVED`**, **0 Änderungen / 0 aktive Störungen**, Gesamtabstand von Baseline bis T+5-Nachaufnahme **602,482 Sekunden**. **Ein kurzfristig unverändertes Fehlerarchiv garantiert keine Fehlerfreiheit zu T+15, T+75 oder später.** Nach den zuvor vom Betreiber berichteten Störungen `C5` (KM-Bus-Pumpe) und `F9` (Gebläsedrehzahl) sind weitere experimentelle Controller-Kommandos vor Abschluss der Fehlerbeobachtung nicht gerechtfertigt.
- Hier **0 Controller-Write**, **keine SFR-/DMA-/UART1-/Bootmode-Aktion**, keine unbekannten Opcode-/Adressbankversuche. Die Live-Dateien bleiben lokal privat; **nicht** in Git.

## 4. Reproduzierbarer Forschungs-Code

In dem bereits vorhandenen Branch `optolink-research` werden folgende Quellen mit aufgenommen:

```text
tools/wb2a-postrestart-five-window-readonly.py
tools/wb2a-postrestart-five-window-session.sh
tools/wb2a-postrestart-five-window-offline-audit.py
tests/test_wb2a_postrestart_five_window.py
config/optolink-splitter/research/firmware-five-window-p300-live-postrestart-2026-10-12.md
```

Nur der Supervisor `--execute` startet einen echten Hardwareversuch, wobei das unabhängige Restoreprogramm **vor** dem Protokollwechsel aktiviert werden muss; ein erneuter Aufruf ist **nicht geplant und derzeit nicht nötig**. Der Python-Leser alleine schaltet nie Protokolle und besitzt ausschließlich **fünf explizit bekannte 32-Byte-Low-SRAM-P300-FC03-Anfragen** plus Identitäts-/Statuskommandos. Der Auditor ist selbst rein offline, validiert die exakt zu erwartenden 19 read-only Zeilen und lehnt jede Änderung seiner gepinnten Originaldateien ab.

```bash
cd /home/chatgpt-admin/optolink-wb2a-research-20261010

# Nur offline: 79 Original-RAM-Bilder + echte 12.10.-Hostaufnahme vergleichen
sudo -n python3 tools/wb2a-postrestart-five-window-offline-audit.py \
  --oct9 /root/p300-trial-work/research-bundles/p300-fullram-run-20261009T083607Z-144293-bundle.tar.gz \
  --oct12 /tmp/wb2a-postrestart-five-window-live-20261012.json \
  --output /tmp/wb2a-postrestart-five-window-compare-20261012.json

# Alle synthetischen Mutations- und originalabhängigen Prüftests
python3 -m unittest discover -s tests -p 'test_wb2a_postrestart_five_window.py' -v
python3 -m unittest discover -s tests -q
```

**Kritisches nächstes Entscheidungskriterium:** Eine Änderung des A-Zielblocks **bei unverändertem A-Quellzeiger** liefert einen guten Anlass, im historischen ROM→RAM-Transferkontext weiterzuforschen. Ohne den ausführenden Copy-Code, einen klaren Zustandswechsel/Trigger, oder einen ROM-Quellwert-Match darf das **nicht** zu einer beschreibbaren DMA- oder Task-Scheduler-Injektion hochgestuft werden. Statt blind 20-Bit zu adressieren, ist eine sorgfältige rein offline erstellte Event-/Reset-Provenienz-Matrix am sinnvollsten.

**Nachweislich aus Programm-ROM gewonnene Bytes: 0.**
