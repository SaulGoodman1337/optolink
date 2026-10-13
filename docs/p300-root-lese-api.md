# Lokale Root-P300-Lesediagnose

Dieser Vertrag beschreibt die bereits implementierte, **standardmäßig
deaktivierte** lokale Diagnose am vorhandenen seriellen
VS1-Splitter. Sie ist weder eine Home-Assistant-Funktion noch eine
allgemeine MQTT-, TCP- oder Webschnittstelle.

## Aktivierung und Berechtigung

Der Dienst wird ausschließlich in einer zuvor geprüften,
root-eigenen und zeitbegrenzten Shadow-Sitzung mit dem Profil
`fenced-ondemand` bereitgestellt. **Normaler VS1-Betrieb und `update`
legen keinen Diagnosesocket an.** Das vorbereitete Release muss
einen unveränderten Hash, die vollständige Anmeldung der
Schreibdienste und die Writer-/Port-Sperren nachweisen. Es ist
eine ausdrücklich bestätigte Telemetriepause erforderlich.
Im manuell beaufsichtigten Modus ist höchstens ein P300-Fenster
zulässig; `RuntimeMaxSec=240` begrenzt die Sitzung.

Der Eingang nutzt ausschließlich
`/run/optolink-hybrid/p300-demand.sock`
(`AF_UNIX/SOCK_SEQPACKET`, Modus `0600`; Laufzeitverzeichnis `0700`).
Der Server erlaubt per `SO_PEERCRED` nur UID 0. Der CLI-Client
prüft die Kernel-Identität des Servers und dessen PID gegen
`optolink-splitter.service/MainPID`. Ein nachgebildeter Socket,
unsichere Symlinks oder falsche Berechtigungen führen zur
Verweigerung. Das Annehmen eines Auftrags erzeugt noch kein
P300-Telegramm; zuerst müssen VS1-GFA-Provenienz, Portbesitz,
Eingangs- und Writer-Epochen und ausstehende HA-Rücklesungen
innerhalb der Admission-Sperre geprüft werden.

## Zulässige Diagnoseaufträge

| Leseart | Erlaubte physische Operation |
| --- | --- |
| `p300_identity` | FC01, Gerätekennung `20C2` |
| `p300_ram_0f20_32` | FC03, exakt 32 Rohbytes ab `0x0F20` |
| `p300_ram_1c60_32` | FC03, exakt 32 Rohbytes ab `0x1C60` |

Keine frei gewählten Adressen, RAM-Schreibbefehle,
Coding-Änderungen oder Gebläsedrehzahl-Ableitung.
Die JSON-Schnittstelle (Version 1) nutzt maximal 512
UTF-8-Bytes pro Frame, lehnt unbekannte Felder oder doppelte
Schlüssel ab und hat die Operationen `submit`, `status` und
`cancel`. `request_id` ist eine 32-stellige, kleingeschriebene
Hex-Kennung; die `session`-Kennung wird vom laufenden
Hauptprozess erzeugt.

Die TTL liegt zwischen **5 und 120 Sekunden**; höchstens
16 wartende Tickets sind erlaubt. Wiederholte identische Aufträge
sind idempotent. Konflikte, abgelaufene Kennungen, fremde Sitzungen,
überfüllte Warteschlangen sowie fehlende GFA-Frische werden abgelehnt.
`cancel` wirkt nur, solange ein Auftrag noch nicht reserviert ist.
Nach einem Prozessneustart gelten alte Sitzungen nicht mehr.

Eine abgeschlossene Antwort darf Rohdaten erst **nach**
erfolgreicher Rückkehr zu VS1 und echter GFA-P80/P06-Bestätigung
enthalten. Ein erfolgreiches Ergebnis umfasst unter anderem
`raw_hex`, `origin`, `verified_vs1=true`, `vs1_p80`,
`vs1_p06` und `elapsed_ms`. `P300_RAW_DIAGNOSTIC_NOT_ACTUAL_RPM`
verbietet die Interpretation als gemessene Gebläsedrehzahl.

## Befehlsübersicht

```bash
# Diese Befehle setzen eine gesondert aktivierte, geprüfte
# und beaufsichtigte fenced-ondemand-Shadow-Sitzung voraus.
sudo optolink-hybrid anfordern p300_ram_0f20_32 \
  --ttl 90 --lesefenster-bestaetigt
sudo optolink-hybrid ergebnis REQUEST_ID --sitzung SESSION_ID
sudo optolink-hybrid abbrechen REQUEST_ID --sitzung SESSION_ID

# Ohne Controller-Leseauftrag den normalen Zustand betrachten:
optolink-hybrid status
```

`REQUEST_ID` und `SESSION_ID` werden aus der Antwort des
ersten Befehls übernommen. Im Normalbetrieb werden die
Auftragsbefehle mangels Socket verweigert. Die Aktivierung
des Shadow-Canarys ist **keine** Aufgabe von `update`
und nicht als allgemeiner Bedienvorgang vorgesehen.
Die unabhängige `ExecStopPost`-Recovery stellt die
VS1-Dienste wieder her. Ein bloßer erfolgreicher
FC03-Rohread ist noch **kein** erfolgreicher Recovery-Nachweis.

## Fehler und Sicherheitsgrenzen

Bei Schreibauftrag, unsicherem Socket, fehlendem
Original-GFA-Readback, Timeout, Protokollfehler oder
fehlender VS1-Rückkehr gilt der Auftrag als gescheitert.
Eine persistierende P300-Sperre darf nicht manuell
entfernt werden, um einen neuen Versuch zu erzwingen.
Für kontrollierte Freigabe, genaue Prüfschritte und
Rollback siehe [Hybrid-Betriebsanleitung](hybrid-protokollwechsel.md).
Die dauerhafte Produktionsarchitektur ist in
[GWG-/VS1-/P300-Lesebetrieb](lesebetrieb-gwg-vs1-p300.md) dokumentiert.