# P300-CANARY: Installation, Abnahmetests und Rueckkehr zu VS1

Status: **nur zeitlich begrenzter READ-ONLY-Test**, nicht freigegebene Produktionsmigration.
Basis: optolink-splitter-ha inklusive Commit 555528c, in optolink-p300-migration
per Merge-Commit 42b1208 uebernommen. Die folgenden Schritte aendern keine
Kessel-Codierung, keine Hydraulik und keinen persistenten produktiven Splitter.

## Wesentliche Sicherheitsgrenzen

- **Nicht** einfach den Produktiv-Updatekanal auf optolink-p300-migration
  umstellen; tools/optolink-splitter-update.sh aktiviert weiterhin VS1.
- Der Kandidat wird nach /opt/optolink-p300-candidate neben die bestehende
  Installation gebaut. /opt/optolink wird nicht ueberschrieben.
- Ein kurzzeitiger systemd-Drop-in liegt **nur in /run**. Reboot beseitigt ihn.
- Vor der Umstellung wird ein systemd-Timer gestartet, der den alten VS1-Dienst
  spaetestens nach der gewaehlten Testzeit wieder aktiviert.
- Schreibende Zusatzdienste und der Clock-Timer werden waehrend des Tests
  angehalten; ihre vorherigen Aktivzustaende werden gesichert.
- Virtual_WRITE und RAM_WRITE bleiben im Kandidaten gesperrt.
  Auch RAM_READ ist in diesem ersten Test standardmaessig gesperrt.
- MQTT-Retain und laufender systemd-Dienst beweisen keine aktuellen Sensordaten.
- Ein funktionierender P300-Identity-Read beweist keine C9-GFA-Unterstuetzung.
  Der Kandidat verlangt beim Start explizit 20C2, 0103 und GFA P80=20.
- Kein M2-Schemawechsel und keine Pumpen-RAM-Experimente beim ersten Test.

## A. Vorbereitung in der Optolink-LXC (als root)

Voraussetzungen: Aktive, funktionierende Produktionsinstallation unter
/opt/optolink mit optolink-Splitterdienst, SSH/Konsolenzugriff und funktionierendem
MQTT. Der Benutzer optolink und die bestehende Python-venv muessen vorhanden sein.

Zuerst Sicherung und Ausgangszustand aufnehmen:

~~~bash
sudo -i
install -d -m 0700 /root/p300-trial-work
systemctl status optolink-splitter.service --no-pager
systemctl list-units 'optolink-*.service' 'optolink-*.timer' --no-pager
cp -a /opt/optolink/settings_ini.py /root/p300-trial-work/settings_ini.py.vs1.backup
optolink-debug request 'r;0x00F8;2;raw;False' --timeout 8
optolink-debug request 'r;0x778C;2;raw;False' --timeout 8
optolink-debug request 'gfaread;0x4050;1;raw;False' --timeout 8
~~~

Erwartete Identitaet: 00F8=20c2, 778C=0103, GFA P80=20.
Auch wichtige Home-Assistant-Sensorwerte und deren Zeitstempel notieren.

Den Entwicklungsbranch und den exakt gepinnten Upstream holen:

~~~bash
git clone --depth 1 --branch optolink-p300-migration --single-branch \
  https://github.com/SaulGoodman1337/optolink.git \
  /root/p300-trial-work/project
git clone https://github.com/philippoo66/optolink-splitter.git \
  /root/p300-trial-work/upstream
git -C /root/p300-trial-work/upstream checkout --detach \
  c1ee204a1421447721603c5f21c6da7337fdac97
git -C /root/p300-trial-work/project rev-parse HEAD
~~~

Der letzte Befehl zeigt den genauen Kandidaten-Commit. Bei erneutem Test nie
blind einen weiterentwickelten Branch einsetzen; zuerst die Diff/CI pruefen.

Offline-Tests ausfuehren, bevor der serielle Port angesprochen wird:

~~~bash
P300_UPSTREAM_ROOT=/root/p300-trial-work/upstream \
  /opt/optolink/venv/bin/python \
  /root/p300-trial-work/project/tools/test-p300-migration.py \
  --report /root/p300-trial-work/offline-test-report.json
bash -n /root/p300-trial-work/project/tools/optolink-p300-trial.sh
~~~

Dann ein neues, isoliertes Verzeichnis erstellen. Kein vorhandenes Verzeichnis
wird dabei ueberschrieben:

~~~bash
python3 /root/p300-trial-work/project/tools/optolink-stage-p300.py \
  --upstream /root/p300-trial-work/upstream \
  --output /opt/optolink-p300-candidate \
  --settings-from /opt/optolink/settings_ini.py
chown -R optolink:optolink /opt/optolink-p300-candidate
chmod 0700 /opt/optolink-p300-candidate
chmod 0600 /opt/optolink-p300-candidate/settings_ini.py
~~~

Die kopierten Settings enthalten moeglicherweise MQTT-Zugangsdaten:
keine Logs/Konfigurationskopien in oeffentliche Issues hochladen.

## B. Zeitbegrenzten P300-Test starten

Der Test dauert maximal 600 Sekunden und wechselt danach automatisch zurueck
auf VS1. Die zugrunde liegende Therme wird weiterhin ganz normal durch ihre
interne Sicherheitsregelung gesteuert; waehrend des Tests sind Optolink-Writes
und die gestoppten Automationsdienste nicht verfuegbar.

~~~bash
bash /root/p300-trial-work/project/tools/optolink-p300-trial.sh activate 600
/usr/local/sbin/optolink-p300-trial status
journalctl -u optolink-splitter.service -n 80 --no-pager
~~~

Der Service wird nicht doppelt gestartet: der bestehende Systemd-Dienst benutzt
uebergangsweise den Kandidaten als WorkingDirectory/ExecStart. Das alte
Produktionsverzeichnis und die alte Servicedatei bleiben unveraendert.

Ein laufender Service allein ist KEIN PASS. Wenn Init/C9/P80 scheitert:
sofort manuell zurueckstellen oder den Timer abwarten.

## C. Lese- und GFA-Tests im laufenden Testfenster

Ueber den bestehenden MQTT-basierten Debugclient (kein zweiter serieller
Besitzer) einzeln die folgenden Anfragen absetzen:

~~~bash
optolink-debug request 'r;0x00F8;2;raw;False' --timeout 8
optolink-debug request 'r;0x778C;2;raw;False' --timeout 8
optolink-debug request 'r;0x00FB;1;raw;False' --timeout 8
optolink-debug request 'r;0x0810;2;raw;False' --timeout 8
optolink-debug request 'r;0x7660;2;raw;False' --timeout 8

optolink-debug request 'gfaread;0x4050;1;raw;False' --timeout 8
optolink-debug request 'gfaread;0x4006;1;raw;False' --timeout 8
optolink-debug request 'gfaread;0x4009;1;raw;False' --timeout 8
optolink-debug request 'gfaread;0x4057;1;raw;False' --timeout 8
~~~

Dazu in Home Assistant pruefen, ob normal gepollte Temperatur- und
Pumpensensoren *neue* Werte samt plausiblen Zeitstempeln liefern. Die GFA-Werte
muessen realistisch sein; ein P06=FF ist nicht als Drehzahl zu interpretieren.
Fuer die erste Abnahme keine Betriebsart oder Solltemperatur umschreiben.

Negativkontrolle: der neue RAM-Read ist im ersten Test absichtlich gesperrt.

~~~bash
optolink-debug request 'ramread;0x20A5;1' --timeout 8
~~~

Ein kontrolliertes DENIED (Returncode 175/0xAF) ist hier das erwartete Ergebnis,
kein fehlgeschlagener P300-Migrationsnachweis.

## D. Sofortiger manueller Rollback und Kontrolle

~~~bash
/usr/local/sbin/optolink-p300-trial rollback
/usr/local/sbin/optolink-p300-trial status
systemctl status optolink-splitter.service --no-pager
journalctl -u optolink-splitter.service -n 60 --no-pager
optolink-debug request 'r;0x00F8;2;raw;False' --timeout 8
optolink-debug request 'gfaread;0x4050;1;raw;False' --timeout 8
systemctl list-units 'optolink-*.service' 'optolink-*.timer' --no-pager
~~~

Der Rollback entfernt den Drop-in, fuehrt systemctl daemon-reload aus,
startet den originalen VS1-Splitter und stellt die zuvor aktiven Writer-Dienste
wieder her. Die Stop/Start-Aktionen verwenden kein enable/disable. Das normale
update bleibt auf dem Produktionsbranch.

Zusatz-Fallback bei komplett nicht erreichbarem Testskript:

~~~bash
rm -f /run/systemd/system/optolink-splitter.service.d/95-p300-canary.conf
systemctl daemon-reload
systemctl restart optolink-splitter.service
~~~

Danach die zuvor aktiven Zusatzdienste anhand der unter
/run/optolink-p300-trial/services gesicherten Liste starten.
Wenn der originale VS1-Dienst nicht hochkommt, Logs pruefen. Keine gleichzeitige
zweite Instanz der seriellen Kommunikation starten.

Auch ein Reboot entfernt den ausschliesslich temporaeren Drop-in unter /run;
er ersetzt aber keine nachfolgende Kontrolle von MQTT-Frische, Dienststatus
und eventuell aktiven Party-/Zeitprogrammzuständen.

## E. Was diese Freigabestufe ausdruecklich nicht beweist

Der erste CANARY prueft P300-Handshake, virtuelle READs, C9-GFA,
MQTT-Dispatch/HA-Frische und Rueckkehr zum echten VS1.

Er beweist nicht Virtual_WRITE-Paritaet, Party-/Zeitplan-Writes, Clock-Writes,
Wartungsaktionen, langfristige GFA-FF-Rate, Dauerlast, latenzarme Poll-Zyklen
oder die Verwendbarkeit von RAM fuer Vitotrol-/Pumpeninjektion.

Fuer Schritt 2 werden nach positivem CANARY gezielt Virtual_WRITE,
Readback/Restore, Zusatzdienste und Poll-Metriken getestet; dazu braucht der
Kandidat einen gesondert freigegebenen Write-Testplan. Der CANARY verhindert
absichtlich, dass jemand Virtual_WRITE einfach fuer den ersten Smoke-Test
einschaltet.

RAM_READ/WRITE werden erst danach als separates Forschungsfeature vorbereitet.
Physical_READ ist keine Garantie fuer sicheres Physical_WRITE; ein erfolgreicher
RAM-Write aendert weder die physische M2-Hydraulik noch beweist er einen
gueltigen Vitotrol-Teilnehmerzustand.

**KEINE PRODUKTIONSFREIGABE** durch gruenes CI oder einen kurzen Smoke-Test.
Fuer Produktivbetrieb sind langer Dauerlauf, vollstaendige Funktionsparitaet,
transaktionaler Installer und ein vorab nachgewiesener Restore erforderlich.

Siehe auch: p300-migration.md und wb2a-topology-hardware-matrix.md.
