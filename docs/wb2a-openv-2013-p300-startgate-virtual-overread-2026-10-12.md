# 2013er OpenV P300-Überlesen auf der echten WB2A nachgewiesen – aber kein 20-Bit-Programm-ROM

**12.10.2026, 08:00–08:21 CEST · Vitodens WB2A, VDensHO1 `20C2/0103`.** Die Originaluntersuchung in [OpenV Issue #142 „Speicher auslesen“ (1. September 2013)](https://github.com/openv/openv/issues/142) berichtet, dass das Protokoll 300 manche direkte Startadressen mit Error-Messagetype 03 ablehnt, aber nach gültiger Startadresse mit längerer Leselänge über nominelle Datenpunktgrenzen hinaus antwortet. Dies haben wir mit **65 unveränderten, genau definierten P300-Virtual_READ-Anfragen in drei vollständig erfolgreichen Fenstern auf der echten WB2A** untersucht. Ein erster zusätzlicher Lauf wurde bei einem unerwarteten P300-Fehlerdiagnosebyte vom Fail-Closed-Parser abgebrochen; die automatische Rückstellung funktionierte auch dort. Alle vier Laufphasen nutzten einen separaten unabhängigen Systemd-Restore-Timer plus EXIT-Restore. Nie unbekannte Befehle, Controller-Writes, MCU-RAM-, UART-/DMA-/SFR-/EEPROM-Manipulationen oder zusätzliche Hardware.

## 1. Wichtigste Ergebnisse mit Bytebeweis

**Die P300-Adressprüfung hängt vom START der Anfrage ab.** Ein gültiger mehrbyteiger virtueller Datenpunkt kann seine **Innenbytes** liefern, auch wenn der Regler eine direkte Einbyte-Anfrage an deren numerisch gleiche Adresse ablehnt. Insbesondere gibt es jetzt einen **Nicht-`FF`-Beleg**:

| Virtueller Start | P300 direkt | Lesen aus gültigem überlappendem Block | Beweisumfang |
| --- | --- | --- | --- |
| **`0x088F/1`** | **Error 03, Diagnostik `01`** | **`0x088E/8`** liefert `20 26 10 12 01 08 20 40` (Wert **`26`** am Offset +1), bei Wiederholung `20 26 10 12 01 08 20 43` und `0x088E/16` ebenfalls Byte **`26`** | **Echte Nicht-`FF`-Datenpunkt-INNENBYTE-Auslesung trotz gesperrter direkter Startadresse** |
| **`0x0897/1`** | **Error 03/01** | **`0x0896/2` = `C8 00`** | Zweites Byte im zweibyteigen Raumtemperatur-Datenpunkt zugänglich, direkt nicht |
| **`0x0899/1`** | **Error 03/01** | **`0x0898/2` = `C8 00`** | Zweites Byte eines zweiten zweibyteigen Datenpunkts |
| **`0x0A5D/1`** | **Error 03/01** | **`0x0A5C/4` = `00 00 00 00`** | Zweites Byte des vierbyteigen Vitotrol-Teilnehmerindexes, direkt nicht |
| `0x0100/4` | Error 03/01, zweimal | `0x00F8/16` = `20C2000300000103FFFFFFFFFFFFFFFF` | Überlappend nur `FF FF FF FF`: **kein verifiziertes verborgenes Nutzdaten-Byte** |
| `0x0A64/4` | Error 03/01 | `0x0A5C/16` = `0000000000000000FFFFFFFFFFFFFFFF` | Überlappend nur `FF`: **kein verifiziertes verborgenes Nutzdaten-Byte** |
| `0x27A1/1` | Error 03/01 | `0x27A0/16` = `00FF02F7000524000105FFFFFFFFFFFF` | Offset +1 `FF`: kein freies Lesen von Speicher |
| `0x089B/1` | Error 03/01 | `0x0896/16` = `C800C800FFFF0303FFFFFFFFFFFFFFFF` | Offset +5 `FF`: kein freies Lesen von Speicher |
| **`0x27A8/1`** | **`01`, zweimal direkt erfolgreich** | `0x27A0/16` liefert an Offset +8 **`01`**, zweimal | **Kein** Überlese-Bypass, obwohl `0x27A8` im VitoSoft-Profil nicht explizit verzeichnet ist |
| `0x00FA/1` | **`00` erfolgreich** | `0x00F8/4` enthält das gleiche Byte | Hersteller-Verzeichnis ist **kein vollständiges Verzeichnis aller direkt lesbaren Startadressen** |

**Fehlerdiagno­stik `01` ist niemals der gelesene Speicherwert `01`:** Status `3;0x088f;01` wurde strikt als Error `03` mit herstellerspezifischer Diagnosenutzlast `01` erfasst, während `1;0x27a8;01` ein echter erfolgreicher Lese-Response ist. Der strikte Parser bricht bei ungültigem Status, nicht numerischer/unerwarteter Adresse, falscher Datenlänge oder nicht freigegebener FC ab.

### VS1-Vorherkontrollen

Bereits über produktiven, einzigen VS1-Splitter vor den P300-Fenstern gemessen:
- `0x088E/8 = 20 26 10 12 01 08 18 13`; `0x088F/1 = FF`;
- `0x0896/2 = C8 00`; `0x0897/1 = FF`; `0x0898/2 = C8 00`; `0x0899/1 = FF`;
- `0x0A5C/4 = 00000000`; `0x0A5D/1 = FF`;
- `0x00FA/1 = 00`, obwohl die VitoSoft-Profilmitgliedschaft keinen separaten Eventtyp für genau diese Adresse nennt.

Das alte VS1-Protokoll verschleiert demnach ebenfalls manche Datenpunkt-Innenadressen bei **direkter** Einzelbyteabfrage, hier mit `FF` statt P300 Error 03. **Die begrenzte Beobachtung gilt nur für diese konkret getesteten Adressen und den aktuellen Firmwarezustand.**

## 2. Datenquellen, Leseanzahl und Beweissicherung

| Quelldatei auf dem privaten LXC | Original-SHA256 | Umfang |
| --- | --- | --- |
| `/tmp/wb2a-vitotrol-p300-overread-vs1-before-20261012.log` | `a866236160c737e47df55c2625e684aad1f0c1bf3f3708c60183ad569caf804d` | Neun produktive VS1-Kontrollen |
| `/tmp/wb2a-vitotrol-p300-overread-live-20261012.json` | `8188cce0fc9f3278cd162a4de8e34c5f2ba4865d90820e53a32dbc5d87102a31` | **21** echte P300 FC01-Reads, davon **3** Error 03/01 |
| `/tmp/wb2a-vitotrol-p300-nonff-vs1-before-20261012.log` | `d16967b41cf6717abb597cdea3e95b53f77d554b115262acc93e53f31799bd36` | Elf VS1-Kontrollen, inkl. Vitotrol-Codierfenster |
| `/tmp/wb2a-vitotrol-p300-nonff-live-20261012.json` | `d6b7e967d72d84d7e1f0e657329a77910ebafae0d1a7a9c47dd23dd40a557c80` | **23** P300 FC01-Reads, **2** Error 03/01 |
| `/tmp/wb2a-vitotrol-p300-internalbyte-vs1-before-20261012.log` | `31fb39a6d5ddb6338af76a72d84dbe3a90902a36940cb3ba8304a5077e8a8b04` | Zehn VS1-Kontrollen, Zeit-, Temperatur- und Teilnehmerindex-Innenbytes |
| `/tmp/wb2a-vitotrol-p300-interior-byte-live-20261012.json` | `fb3e27e8596a498440fe32f9bd73a5d5157956390bf8319c7c8bc4cb2083f772` | **21** P300 FC01-Reads, **4** Error 03/01 |

**Gesamt: 65 durch originale Source-SHAs abgesicherte echte P300-Leseanfragen; 56 erfolgreiche FC01-Antworten, 9 Error-Status 03 mit zusätzlichem Diagnosebyte 01, 0 Controllerwrites.**

Ein erster P300-Probelauf um 08:07:55 wurde absichtlich bei `read;0x0100;4` abgebrochen, weil der Parser zunächst eine nichtleere Error-Diagnosenutzlast als unbekanntes Format ablehnte. **Dieser abgebrochene Lauf gehört nicht zu den 65 vollständig forensisch geprüften Reads; er wurde nicht stillschweigend als Erfolg gezählt.** Der originale VS1-Zustand war danach wiederhergestellt, bevor die korrigierte Software in einem neuen Timer-/Protokollfenster ausgeführt wurde.

Die Offline-Prüfer
- `tools/wb2a-vitotrol-p300-overread-original-audit.py` (erste zwei unabhängige P300- und VS1-Originale)
- `tools/wb2a-vitotrol-p300-interior-original-audit.py` (alle drei P300- und drei VS1-Originale)

prüfen **sämtliche 65 Original-Requests** einschließlich Reihenfolge, Adressen, deklarierter Längen, Status, echter Datenbytes, nicht als Bytes interpretierter Error-Diagnostik, aller unveränderten Source-Hashes, der Identität `20C2/0103` und der realen Positiv-/Negativkontrollen. Ergebnis maschinenlesbar nur lokal `/tmp/wb2a-vitotrol-p300-3session-forensic-20261012.json`.

## 3. Technische Einordnung für den Vitotrol-Firmwarezugriff

**Gesichert:**
1. P300 kann per FC01 einen mehrbyteigen virtuellen Datenpunkt bei **gültigem Start** ganz oder mit zusätzlicher Leselänge zurückgeben, während eine Einbyteanfrage an die zweite Datenpunktadresse Error 03/01 erzeugt.
2. Das ist bei einem **nicht-FF-Wert `26`** nachgewiesen (`0x088E/8` versus `0x088F/1`). Die Reproduktion passt zur alten Originalbeobachtung aus OpenV 2013.
3. **Innerhalb** eines bekannten mehrbyteigen Datenpunkts erreichbare Bytes sind **nicht** gleichbedeutend mit „beliebiger ungeschützter physischer CPU-RAM-Dump“. Die 4 isoliert verweigerten und überlappend getesteten **ungültigen** Einzelstartadressen aus den ersten beiden Testfenstern lieferten überlappend stets `FF`, keinen geheimen Code.
4. `0x27A8` ist selbst direkt `01` lesbar, obwohl die Hersteller-Metadaten nur benachbarte separate Datenpunkte aufführen; fehlende Katalogmitgliedschaft ist folglich **kein** Beweis für eine im Controller gesperrte Adresse.

**Nicht gesichert:**
- beliebige bislang nicht als Datenpunkte abgebildete CPU-RAM-/ROM-Speicherbereiche durch FC01 lesen;
- P300 FC01 mit über 16-Bit-Adressbereich hinausreichender Bank/Page-/20-Bit-Adresse; im aktuell benutzten P300-Host sind genau zwei Byte Zieladresse serialisiert;
- M30612MC-V200KW2-Firmwaremonitor, 128-KiB-KarlKoch-Dump oder eine vergleichbare WB2A-ROM-to-RAM-Copy-Prozedur;
- gültige Klasse11-Vitotrol-Teilnehmeranmeldung/ISR.

Der Befund ist für unsere Entwicklung dennoch wertvoll: künftige Optolink-Read-APIs dürfen **Error 03/01 nicht in `FF` oder `01` umdeuten** und müssen **(gültige Startadresse, angefragte Länge, Art virtueller Datenpunkt)** als Identität des Zugriffs behandeln. Für das Ziel, **originales 20-Bit-Programm-ROM** zu lesen, benötigen wir weiterhin eine belegte Bank-/Monitor-/ROM-Kopie-Semantik und nicht nur ein höheres FC01-Längenfeld.

### Weitere Forschungspriorität

1. Bereits gewonnene Hersteller-/2010er-OpenV-Quelle systematisch gegen den nun nachgewiesenen P300-Datendienst-Startfilter abgleichen; historische **GWG `C7`**-Kompatibilität (`01 C7 F8 04 04` auf eigener WB2A) bleibt korrekt, **impliziert aber keinen 20-Bit-ROM-Read**.
2. Einen **tatsächlich 20C2 zugeordneten** ROM-Bank-/Serviceaufruf oder alte Optolink-Mehrstufensequenz rekonstruieren, nicht ungerichtet über beliebige RAM-/SFR-/Bootloaderadressen probieren. Dass 2010 dieselben Protokolle teilweise direkt kompatibel waren, erhöht diese Suchpriorität.
3. Bei nachgewiesener, nicht-destruktiver 20-Bit-Datenquelle mit minimalem, wiederholtem ROM-Read beginnen; anschließend tatsächlichen M16C-UART1-IRQ-Parser, Klasse11-Teilnehmerliste und Teilnehmer-Commit untersuchen. Kein Eingriff in aktive Gasheizungs-/Brenner-Sicherheit, UART-/DMA-Register oder EEPROM.

## 4. Sicherheitskonzept und Wiederholung

Alle P300-Fenster verwendeten **den vorhandenen einzelnen seriellen Optolink-Splitter als einzigen Besitzer** und dessen etablierte MQTT-Anfrage `read;...`, also ausschließlich **FC01 Virtual_READ** an festen Adressen mit Leselängen von **1–16 Bytes**. Eine eigenständige systemd-Restore-Unit war **vor** jedem Protokollwechsel auf 4 Minuten geschaltet, mit separater EXIT-Restore-Prüfung. Nur die Host-Konfiguration `vs1protocol = False` wurde kurz gesetzt, nie ein Controller-Speicher-/Modusschreibbefehl gesendet. Original-Config nach jedem Fenster SHA256 `e9a120ef37fe17236a7505ee713c8dd338d98d5093ed75dfb34629d7e8f5c42d` und `vs1protocol = True`, Ende `VS1_BETRIEB_OK`, Fehler `0x5738=00`, bisher Vitotrol-Index `0x0A5C=00000000`.

Scripts im Draft-Forschungs-PR #52:
- `tools/wb2a-vitotrol-p300-overread-readonly.py`, `tools/wb2a-vitotrol-p300-overread-session.sh`
- `tools/wb2a-vitotrol-p300-nonff-overread-readonly.py`, `tools/wb2a-vitotrol-p300-nonff-session.sh`
- `tools/wb2a-vitotrol-p300-interior-byte-readonly.py`, `tools/wb2a-vitotrol-p300-interior-session.sh`
- zwei SHA-verifizierende forensische Offline-Auditoren und ihre Testmodule.

**Wiederholung ausschließlich offline, ohne Controller-I/O:**
```sh
cd /home/chatgpt-admin/optolink-vitotrol-rpm-20261010
python3 tools/wb2a-vitotrol-p300-interior-original-audit.py \
    --out /tmp/wb2a-vitotrol-p300-3session-forensic-20261012.json
python3 -m unittest discover -s tests -q
```

Die echten Originalmitschnitte bleiben **nur auf dem LXC**; das Forschungs-PR enthält reproduzierbare Tests, Quellcode und Auswertung, aber keine unverifizierten Firmwarebehauptungen. Beide bereits existierenden, nicht getrackten P300-FC99-Tools bleiben absichtlich unangetastet.
