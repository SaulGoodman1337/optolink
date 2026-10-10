# WB2A: lokaler, root-authentifizierter On-Demand-P300-Lesekanal

**Status 10.10.2026:** Offline-Regressionen bestanden, echter manueller
Operator-Request am WB2A verifiziert, unabhängiger Systemd-Rollback bestanden.
Diese Funktion bleibt **explizit opt-in**, schreibgeschützt und ist **kein**
MQTT-, TCP-, HA- oder Web-Endpunkt. Der normale VS1-Betrieb startet **ohne**
Demand-Socket, ohne P300-Scheduleraktivierung und ohne zusätzliche serielle
Verbindungen.

Siehe auch [Implementierungsdesign](wb2a-on-demand-p300-design-2026-10-10.md)
und [Hardwareabnahme einschließlich C1–C3](wb2a-on-demand-canary-2026-10-10.md).

## Sicherheits- und Prozessgrenze

- Der bereits laufende **originale serielle Hauptthread** bedient alle
  Socket-RPCs nichtblockierend, höchstens vier pro VS1-Loop. Weder Client
  noch Unix-Socket-Klasse dürfen eine zweite serielle Verbindung öffnen.
- Ausschließlich `AF_UNIX/SOCK_SEQPACKET` über
  `/run/optolink-hybrid/p300-demand.sock`, **kein TCP-Listener**.
  Die Socket-Datei hat Modus `0600`; das von systemd für den ursprünglichen
  `optolink`-Service angelegte `RuntimeDirectory=optolink-hybrid` hat `0700`.
- Der Server prüft Linux-`SO_PEERCRED`: **Client-UID muss 0 (root)** sein,
  unabhängig von Daten in der Nachricht. Der CLI-Client prüft seinerseits
  Kernel-PID, UID und GID des Socket-Servers und vergleicht die PID mit
  `systemctl show optolink-splitter.service -p MainPID`. Eine andere,
  auch unter Benutzer `optolink` laufende Prozess-ID wird abgewiesen.
- Der Socket wird nur bei gepinntem Shadow-Modus `fenced-ondemand`,
  nach nachgewiesener Anmeldung aller Producer, mit dem **exakten**
  systemd-konfigurierten Socket-Pfad aktiviert. Kein Socket wird von
  `fenced-readonly`, normalem VS1 oder `update` automatisch eingeschaltet.
  Symbolische Links, bereits existierende Sockets oder unsichere Verzeichnisse
  verursachen ein Fail-closed-Startverbot.
- Auftragsanmeldung ist keine physische Freigabe. Die bestehende
  `RuntimeAdmissionGate` entscheidet erst innerhalb von
  `IngressEpoch.freeze()`, Writer-`p300_window()`-Lease und Serienlease,
  mit originalen GFA-P80/P06-Zeitstempeln, HA-Write-Readbacks und
  VS1-Identität.
- Bei Transport-/Protokollfehler darf kein Ergebnis als erfolgreich gelten.
  Die bestehende persistente Fehlermarkierung sowie die unabhängige
  `ExecStopPost`-Recovery bleiben maßgeblich.

### Berechtigungsgrenze

Root ist **derzeit die einzige** berechtigte lokale Rolle. Home Assistant
oder ein MQTT-Client erhält damit ausdrücklich noch keine Berechtigung.
Eine spätere HA-Anbindung braucht einen separat geprüften, minimal
privilegierten Broker mit ausdrücklicher Auftragsallowlist und Authentisierung.
Da andere Prozessprogramme auf demselben LXC teilweise ebenfalls als
`optolink` laufen, ist der Co-UID-Angreifer nicht als unabhängige
Sicherheitsdomäne modelliert. Der beidseitige PID-/UID-Abgleich verhindert
das Akzeptieren eines nachgebildeten Ergebnisservers; eine kompromittierte
`optolink`-Instanz könnte dagegen lokale Verfügbarkeit sabotieren.


## Protokoll Version 1 und Ergebniszustände

Jede Nachricht ist **ein** JSON-Objekt mit maximal 512 UTF-8-Bytes in einem
`SOCK_SEQPACKET`-Frame. Doppelte JSON-Schlüssel, zusätzliche Felder,
fremde Versionen, non-finite Zahlen, freie Controlleradressen, Schreib- oder
Raw-Frame-Operationen werden verworfen. Nur folgende feste Arten:

| Art | Transport | Bedeutung |
| --- | --- | --- |
| `p300_identity` | Freigegebene FC01 | Geräte-ID; nicht Gebläsedrehzahl |
| `p300_ram_0f20_32` | Freigegebene FC03 | 32 diagnostische Rohbytes |
| `p300_ram_1c60_32` | Freigegebene FC03 | 32 diagnostische Rohbytes |
| `p300_ram_1640_32` | Historisch belegte FC03 (nur Draft-Entwicklungsbranch) | 32 Rohbytes ab 0x1640, einschließlich UART1-RX-Pufferkandidat 0x1642; **kein** RX-/Write-Nachweis |

Request/Response-Beispiel (IDs illustrativ):

```json
{"v":1,"op":"submit","request_id":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","kind":"p300_ram_0f20_32","ttl_s":90}
{"v":1,"ok":true,"session":"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb","request_id":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","state":"queued","kind":"p300_ram_0f20_32"}
{"v":1,"op":"status","session":"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb","request_id":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}
{"v":1,"op":"cancel","session":"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb","request_id":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}
```

`request_id` ist eine vom Client erzeugte 32-stellige kleingeschriebene
Hex-Idempotenzkennung, `session` eine vom ursprünglichen Hauptprozess
erzeugte 32-stellige zufällige Sitzungskennung. Eine Wiederholung **innerhalb
derselben laufenden Sitzung** mit identischem `request_id`, Leseart und TTL
liefert den vorhandenen Auftrag statt eines zweiten Controllerreads, solange
der Datensatz gehalten wird. Gleiches `request_id` mit anderer Leseart oder TTL
führt zu `IDEMPOTENCY_CONFLICT`. Nach Ende der Aufbewahrungsfrist ist die
Auftragskennung für die laufende Sitzung dauerhaft gesperrt
(`REQUEST_ID_RETIRED`), um spätere Doppelreads auszuschließen.
Nach Prozessneustart wird eine alte Sitzung strikt `STALE_SESSION`; es darf
kein altes Ergebnis als neu ausgegeben werden.

Statusübergänge: `queued` → `running` → `completed`, oder
`expired`, `cancelled`, `failed`. `cancel` ist nur vor der Reservierung
zugelassen. Ein `completed`-Ergebnis enthält `raw_hex`, `origin`,
`verified_vs1=true`, `vs1_p80`, `vs1_p06` und `elapsed_ms`.
Vor der verifizierten VS1-Rückkehr sind **keine Rohdaten abrufbar**.

Kapazität: höchstens 16 wartende Lesetickets, 128 gleichzeitig lokal
verfolgte Auftragskennungen und 1024 eindeutige Kennungen pro Prozessgeneration
(bei Erreichen: `SESSION_REQUEST_LIMIT` statt ID-Wiederverwendung).
TTL 5–120 Sekunden; terminale Datensätze werden nach 180 Sekunden seit
Einreihung bereinigt. Die eigentliche
P300-Ausführung unterliegt zusätzlich der vorhandenen Admission-Prüfung
und einem minimalen 60-Sekunden-Cooldown. Der Socket sendet **kein**
serielles Byte und speichert nichts über einen Neustart hinweg.

## Operator-Bedienung im bewusst überwachten Shadow-Test

Im produktiven VS1-Normalbetrieb ist `anfordern` grundsätzlich
**nicht erreichbar**, denn der Socket existiert nicht. Das unveränderliche
geprüfte Shadow-Release muss zuerst über den gesonderten, root-eigenen
`demand-manual`-Canary mit explizit bestätigter Telemetriepause gestartet
werden. Diese Session erlaubt **exakt ein** echtes P300-Fenster, besitzt
`RuntimeMaxSec=240` und garantiert den unabhängigen Rückfall.

```bash
# In einem separaten Terminal: beaufsichtigter Shadow-Lauf
sudo env PYTHONPATH=/pfad/zum/checkout/tools \
  /opt/optolink/venv/bin/python -m handover_acceleration.continuous_canary \
  --launch /var/lib/optolink-hybrid/releases/GEPRUEFTES-RELEASE \
  --accept-telemetry-pause --demand-manual

# Erst wenn der explizit angelegte lokale Socket existiert:
sudo /opt/optolink/venv/bin/python tools/optolink-hybrid.py \
  anfordern p300_ram_0f20_32 --ttl 90 --lesefenster-bestaetigt

# request_id und session aus der JSON-Antwort einsetzen:
sudo /opt/optolink/venv/bin/python tools/optolink-hybrid.py \
  ergebnis REQ_ID --sitzung SESSION_ID

# Nur solange noch wartend:
sudo /opt/optolink/venv/bin/python tools/optolink-hybrid.py \
  abbrechen REQ_ID --sitzung SESSION_ID

# Danach (automatischer Systemd-Rollback) normalen Zustand prüfen:
optolink-hybrid status
```

Während des laufenden Canarys ist das Socketverzeichnis nur für Root und
den originalen `optolink`-Hauptprozess zugänglich. Der CLI-Befehl
`anfordern` verlangt eine gesonderte Lesefensterbestätigung. Für den
Fallback genügt keine reine P300-Antwort: der unabhängige Supervisor
verlangt gültiges originales VS1-GFA-P80/P06 plus Wiederherstellung der
ursprünglichen Dienste.

Das sind **keine** Anweisungen für das Aktivieren einer unbeaufsichtigten
Dauerautomatik, keinen MQTT-/HA-Broker und keine P300-Schreibfreigabe.


## Technische Abnahme C3 am 10.10.2026

Release: `wb2a-manual-rpc-c3-20261010`, echte Session:
`run-20261010T192559Z-327016`. Die Shadow-Unit wurde ohne internen
Startup-Selbsttest gestartet. Auftrag:
`eee42b270dac733e49a1811bdce929be`; lokale Gateway-Session:
`a9cefcf93a25e4cec24660736eda0e3f`.

Der Root-CLI-Aufruf erhielt zuerst `state=queued`, danach über
`ergebnis` vollständig `state=completed` mit:

```json
{
  "kind": "p300_ram_0f20_32",
  "result": {
    "elapsed_ms": 5180.292,
    "origin": "P300_RAW_DIAGNOSTIC_NOT_ACTUAL_RPM",
    "raw_hex": "000900aeab00000100000064648d05f50e18006408020000440ac2016b0d6b0d",
    "verified_vs1": true,
    "vs1_p80": "20",
    "vs1_p06": "00"
  },
  "state": "completed"
}
```

Derselbe RAW-Wert wurde unter dieser Canary-Session im **originalen
Hauptprozessjournal** protokolliert. Der unabhängige Systemd-Wächter
prüfte exakt ein Fenster und meldete
`PASS_ONE_VERIFIED_DEMAND_WINDOW`. Anschließend:
`PASS_ORIGINAL_SERVICES_RESTORED` mit `errors=[]`, originaler
VS1-GFA-P80=`20`, P06=`00`, danach
`VS1_BETRIEB_OK`. Alle sechs zuvor aktiven Produktivdienste/Timer
sind wieder aktiv; Pumpenoverride und Canary inaktiv,
Producer-Lease frei, keine unbekannten Drop-ins. Das Socketverzeichnis
`/run/optolink-hybrid` wurde von systemd entfernt.

Das 32-Byte-Feld wurde **nicht** als Ist-Drehzahl interpretiert.
Auch ein erfolgreicher FC03-Lesevorgang begründet keinerlei Erlaubnis
für Controller-Schreibbefehle.

## Offline-Regression und verbleibende Einschränkungen

Die Regressionen prüfen originalen Dispatcher-Shim, Fake-CP2102-Readback,
den tatsächlichen Linux-Sockettransport, unprivilegierte Peer-Ablehnung,
Client/MainPID-Pinning, privates Laufzeitverzeichnis, Symlinks,
ungültige JSON-Frames, TTL, Idempotenz, P06-GFA-Alter, HA-Readback-Gates,
Deadline, Prüfsummenfehler, Sessionwechsel, Ergebnisprovenienz und
Rollback. Neben dem eigentlichen C3-Test waren alle Simulationen
vollständig ohne Zugriff auf den physischen Controller.

Offen für eine spätere HA-Integration: ein dedizierter, bewusst
berechtigter Broker, zusätzliche automatisierte Authentisierungstests
dieser separaten Brokergrenze sowie die HA-Entity-Validierung. Weder
eine solche HA-Freigabe noch eine unbeaufsichtigte Protokollwechsel-
Automatik wird durch die vorliegende Root-CLI-Abnahme beansprucht.

## 10.10.2026: zusaetzlicher Optolink-only RX-Diagnoseentwurf (Draft)

Der Entwicklungsbranch kennt nun den zusaetzlichen **festen**
Root-On-Demand-Read `p300_ram_1640_32`, Request
`41 05 00 03 16 40 20 7E`. Die Adresse stammt aus
**295 erfolgreich archivierten P300-Physical_READs** und
wird fuer die Untersuchung des bei `0x1642` gefundenen
CRC-gueltigen, empfangsgerichteten KM-Bus-RAM-Frames genutzt.

Alle bestehenden Authentisierungs-, Admission-, Writer-, Recovery-
und VS1-Readback-Gates bleiben erhalten. Die neue Leseart ist
**nicht** in den periodischen/automatischen Canarys und **nicht**
im derzeit installierten Main-Release enthalten. Ihre eigene
Hardwareabnahme ist noch offen; kein Lauf waehrend des passiven
RPM-v2-Dienstes. Sie ist niemals eine Erlaubnis fuer einen
RAM-Write, KM-Bus-Injektionsversuch oder direkter UART1-U1RB-Zugriff.

Siehe [vollstaendiger Quellen-/Offline-Audit](wb2a-vitotrol-optolink-rx-2026-10-10.md).
