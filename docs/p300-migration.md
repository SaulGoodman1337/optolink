# P300-Migration: isolierter Kandidat, noch keine Produktionsfreigabe

Stand: 2026-10-07. Entwicklungsbranch: `optolink-p300-migration`.

## Ausgangspunkt und Ausfuehrungsgrenze

Basis ist `optolink-splitter-ha` bei `7bc69c32788dd19c7a35e787d0b2aa26c9548ce6`.
Upstream bleibt `philippoo66/optolink-splitter` bei
`c1ee204a1421447721603c5f21c6da7337fdac97`.

Bei dieser Entwicklung wurden weder Therme noch serieller Adapter, installierte
Produktionsdienste oder MQTT-Broker angesprochen. Der Ausgangsbranch bleibt
unveraendert. Tests verwenden einen fragmentierend antwortenden Fake-Peer,
kein validiertes Modell der WB2A-Firmware. Die Hardwareparitaet ist weiterhin
eine ausdrueckliche Voraussetzung fuer die spaetere Freigabe.

## Warum ein Umschalten der Einstellung nicht reicht

Der vorhandene Profil-Helper erzwingt VS1. Sein GFA-Adapter liefert unter VS2
absichtlich `0xAF`. Nur `vs1protocol=False` zu setzen wuerde deshalb
P80/P06/P09/P87 verlieren, einschliesslich des kanonischen Geblaesedrehzahlkanals.
Das normale Update kann manuelle Laufzeitaenderungen ausserdem wieder ersetzen.

GFA_READ hat unter P300 laut Vitosoft-Rekonstruktion den Funktionscode `0xC9`
(201), nicht VS1 `0x6B`. Erfolgreiche VS1-GFA- und P300-Virtual_READ-Zugriffe
beweisen nicht die lokale Unterstuetzung von C9. Der Kandidat verweigert den
Start, solange 20C2, Regelungssoftware 01.03 und C9 P80=0x20 nicht gelesen sind.

## Implementierter Umfang

- `tools/optolink_p300.py`: begrenzte P300-Transaktionen auf genau dem Handle,
  das bereits dem Splitter gehoert. Kein zweiter Portbesitzer, kein VS1-Wechsel
  pro Anfrage und kein automatischer Rueckfall auf einen anderen Protokollpfad.
- Pruefung von Pruefsumme, Laenge, Adresse und vollstaendigem Funktionsbyte;
  Antwort-ACK, fragmentierte Reads, feste Fristen, Identitaetspruefung nach
  Verbindungsverlust/Leerlauf. Keine automatische Wiederholung unsicherer Writes.
- Virtual_READ/WRITE mit unveraendertem MQTT-Antwortformat. Die fachliche
  Readback-Pruefung der vorhandenen Zusatzdienste bleibt bestehen.
- C9-GFA-Pfad fuer die vier aktuellen Produktionsziele, P80-Pruefung, genau ein
  FF-Wiederholversuch nach 150 ms, danach Quarantaene. Die Abstaende sind noch
  nicht als produktives P300-Timing an dieser Anlage bestaetigt.
- Optional `ramread;<Adresse>;<Laenge>` ueber denselben Dispatcher: hoechstens
  32 Byte je Anfrage, ausschliesslich 0x0400..0x53FF, standardmaessig gesperrt.
- Bibliotheksfunktion fuer RAM-Compare/Write/Readback mit exakten Adress- und
  Werteregeln. Es gibt KEINE aktive mitgelieferte Schreibregel und KEINEN
  MQTT-RAM-Schreibbefehl. Die Hostsperre ist kein atomarer MCU-Compare-and-Swap;
  die Firmware kann das Feld jederzeit selbst wieder ueberschreiben.
- Opaque Rohtelegramme und nicht freigegebene Funktionsfamilien sind im
  Kandidaten gesperrt. `writeraw/wraw` bleibt normaler Virtual_WRITE und ist
  ausdruecklich kein direkter RAM-Write.
- `tools/optolink-stage-p300.py`: erstellt ein NEUES privates Verzeichnis aus
  unveraendertem, gepinntem Upstream; uebernimmt beide vorhandenen Runtime-Patches,
  die exakten produktiven Discovery-/Set-Readback-Patches und das HA-Profil.
  Vorhandene Zielverzeichnisse und direktes In-place-Staging werden abgelehnt.
- Offline-Regressionstests und eigene CI. Die CI fuehrt keine Heizungsversuche aus.

## Bestand und Funktionsmatrix

Das untersuchte Profil hat **362 deklarierte Eintraege**, davon **222 Poll-
Eintraege**. Das sind nicht 362 unabhaengige Bustransaktionen. Maximale deklarierte
Leselaenge: 29 Byte. Deklarationen nach Domaene: sensor 266, binary_sensor 23,
number 21, switch 7, select 16, text 21, time 8. Diese Zahlen sind kein Inventar
der tatsaechlichen HA-Registry oder separat publizierter Dienst-Entities.

SHA256 des unveraendert uebernommenen Profils:
`f6b48cde6b689d2a3d876783733dc0e283ca03d41fd942f47d5b8fd7d0a1015e`.

| Bisherige Funktion | Behandlung im Kandidaten | Noch erforderlicher Geraetenachweis |
|---|---|---|
| Normale Messwerte, Vorzeichen, Bitfelder | Gleiches Profil und Decoder; P300 FC01 | Werte und Frische aller aktiven Kanaele |
| Vier GFA-Werte | C9 statt 6B; gleiche Namen/Skalierungen | Erst P80, dann P06/P09/P87 in verschiedenen Betriebsphasen |
| Entity-IDs, Topics, Discovery | Bytegleiches Profil; produktiver Publisher-Patch | Keine Neuanlage/Unavailable-Regression |
| HA-Schreibfunktionen | FC02; im Kandidaten ausdruecklich freizugeben | Repraesentative Breiten/Typen und Controller-Readback |
| 21 Zeitprogramm-Tagesbloecke | Unveraenderter Manager und 8-Byte-Format | Gewaehlten Block lesen/schreiben/pruefen/restaurieren |
| Party-Emulation | Unveraenderter Dienst und Restore-State | Aktivierung, Ablauf, Neustart, Restaurierung |
| Uhrensynchronisation | Unveraenderter 8-Byte-BCD-Dienst | FC02-Write und korrekter Zeit-Readback |
| Wartung | Unveraenderter Core, Bestaetigungen und App-Sperre | Bewusst freigegebene Einzelablaeufe |
| Befuellen/Entlueften | Unveraenderte 0/1/2-Abbildung und Manager | Gesonderter Serviceversuch; nie automatischer Paritaetstest |
| Scheduler und Set-Readbacks | Vorhandene Produktivpatches bleiben | P95-Frische und Warteschlangenlatenz unter Last |
| RAM lesen | Neuer optionaler FC03-Pfad | Bekannte begrenzte Fenster und Busbudget |
| RAM schreiben | Nur exakte Bibliotheksregel; keine aktive Betriebspolitik | Feldfunktion, Werte, Lebensdauer, Abbruch und Wiederherstellung |

Identische Discovery-Ausgabe und Fake-Peer-PASS beweisen keine reale
Schreibannahme, Buslaufzeit, Service-Nebenwirkung oder C9-Firmwareunterstuetzung.

## Offline erstellen und testen

Voraussetzung: separater unveraenderter Upstream-Checkout beim genannten Commit.
Diese Befehle installieren oder starten den Kandidaten nicht:

```bash
P300_UPSTREAM_ROOT=/path/to/pristine-upstream \
  python3 tools/test-p300-migration.py --report /tmp/p300-tests.json

python3 tools/optolink-stage-p300.py \
  --upstream /path/to/pristine-upstream \
  --output /tmp/optolink-p300-candidate
```

Ohne Zusatzoption ist kein serieller Port, Broker oder TCP-Listener konfiguriert.
`p300_virtual_write=False` und `p300_ram_read=False`. Das Verzeichnis ist privat,
Settings haben Modus 0600. Optional kopiert `--settings-from` bestehende lokale
Settings nur in den Kandidaten; moegliche Zugangsdaten niemals committen/hochladen.

Der volle Integrationstest benoetigt `pyserial` und `paho-mqtt`; in CI sind sie
Pflicht. Ohne diese lokalen Abhaengigkeiten wird genau ein Integrationstest
explizit uebersprungen. Die Suite startet ausserdem die vorhandenen GFA-,
Scheduler-, Uhr- und Service-Selbsttests. Der Publisher laeuft nur mit `--console`.

## Bewusst noch nicht implementiert

Keine In-place-Aktivierung, Unit-Ersetzung, produktive Updatekanal-Umschaltung,
automatische Zusammenfuehrung, RAM-Reparaturschleife, Firmwareaenderung,
EEPROM-Schreibfunktion, GFA_WRITE, geratene Speicheradresse oder Firmware-Dump.
Das normale Update bleibt der VS1-Produktivpfad. CI allein ist KEINE Begruendung,
diesen Branch als produktiven Updatekanal zu verwenden.

Fehlendes C9-P80 blockiert den Start statt die Geblaesedrehzahl still zu verlieren.
Ein zweiter serieller Master/Vitoconnect wird im Kandidaten nicht unterstuetzt;
das entspricht dem dokumentierten lokalen `port_vitoconnect=None`, aber nicht
allen moeglichen Upstream-Anwendungen. Freie Rohtelegrammdurchleitung ist eine
bewusste Einschraenkung gegenueber dem generischen Debug-Interface.

## Vorteile und verbleibende Kosten

P300 kann normale Datenpunkte und Physical_READ/WRITE in einer Sitzung vereinen.
Damit entfaellt der gemessene VS1/P300-Rundwechsel von etwa sechs Sekunden fuer
jeden RAM-Zugriff. Hinzu kommen strukturierte Antworten und Pruefsummen.

Die Baudrate steigt NICHT: beide Pfade verwenden hier 4800 8E2. Das sind 12 Bit
je UART-Byte beziehungsweise 2,5 ms. Ein synchronisierter VS1-Read von zwei Byte
uebertraegt 4 Anfrage- plus 2 Antwortbytes: 15 ms reine Leitungszeit. P300 benoetigt
8 Anfragebytes, ein ACK, 10 Antwortbytes und ein Abschluss-ACK: 50 ms, jeweils
zuzueglich Verarbeitung und Pausen. Das ist eine Rechnung am Telegrammformat,
keine Durchsatzmessung der Anlage. P300 ist hier nicht pauschal schneller.

Pollgruppen sind Zykluszaehler, keine Zeitgarantien. RAM-Arbeit braucht ein
begrenztes Budget und darf normale Messungen oder ausstehende App-Readbacks
nicht verdraengen. Persistent gespeicherte Virtual_WRITEs bleiben auch unter
P300 persistent; die Protokollumstellung beseitigt keinen E7-Schreibverschleiss.

RAM ist keine komfortable Datenpunkt-API: gleiche Zahlenadressen im virtuellen
und physischen Raum sind nicht austauschbar. Ein erfolgreicher Read beweist
keinen sicheren Write. Der niedrige RAM-Bereich erschliesst nicht automatisch
den hoch adressierten Programm-ROM des Controllers.

## Vorgeschlagene Freigabestufen - nicht ausgefuehrt

1. VS1-Ausgangszustand sichern: Settings/Runtime, Dienstzustaende, Fehlerhistorie,
   Rohreferenzen, Entitybestand und gemessene Frische/Befehlslatenz.
2. Kurze exklusive READ-ONLY-Sitzung mit unabhaengigem Wiederherstellungsplan:
   20C2/0103 identifizieren, C9 P80=20 verlangen, andernfalls abbrechen und VS1
   wiederherstellen. Kein paralleler zweiter serieller Prozess.
3. Alle aktuellen Poll-Eintraege und echte GFA-Werte vergleichen; keine Ersatz-
   oder Fakewerte fuer nicht erreichbare Kanaele verwenden.
4. Normale Writes nur fuer bewusst freigegebene Paritaetsversuche aktivieren.
   Bestehende App-Sperren, Read-before-write und Restore-Zustaende erhalten.
5. Dauerlauf mit natuerlichen Heiz-/WW-Wechseln und Wiederverbindung: P95/maximales
   Messwertalter, Fehler, Restarts, GFA-FF und Befehlslatenz protokollieren.
6. Erst nach Paritaet transaktionalen Installer/Updater/Rollback entwickeln und
   RAM-Experimente separat mit enger Freigabe in denselben Busbesitzer einbauen.

Die Protokollwahl ersetzt keine Kesselfirmware; falsche Anfragen koennen trotzdem
Daten veraendern oder den Betrieb stoeren. Laufender Prozess und retained MQTT-
Wert beweisen keine frischen Messwerte. Hydraulik/M2 bleibt beim ersten P300-Test
unveraendert, damit nicht zwei unabhaengige Aenderungen gleichzeitig getestet werden.

## Quellen

- [Basisarchitektur](architecture.md), [produktives HA-Profil](../config/optolink-splitter/vdensho1-20c2-wb2a-homeassistant.py)
- [Gepinnter Upstream](https://github.com/philippoo66/optolink-splitter/tree/c1ee204a1421447721603c5f21c6da7337fdac97)
- [Vitosoft-Protokollrekonstruktion](https://github.com/sarnau/InsideViessmannVitosoft/blob/main/VitosoftCommunication.md)
- [Lokaler VS1/P300-Lesevergleich](https://github.com/SaulGoodman1337/optolink/blob/optolink-research/docs/vs1-mixed-gfa-integration.md)
- [RAM-E7 und Protokollwechselgrenze](https://github.com/SaulGoodman1337/optolink/blob/optolink-research/docs/pump-min-override.md)
- [Hydraulikmatrix](wb2a-topology-hardware-matrix.md)
