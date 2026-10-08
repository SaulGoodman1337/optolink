# GFA-Auftrag, Drahtbefehl und VSKO: direkte Quellenpruefung

Stand: 2026-10-08. Geltungsbereich: Hostsoftware Vitosoft und lokale WB2A / VDensHO1 / 20C2 / 01.03. **Keine neue Anfrage an die Heizung durch diese Quellenpruefung.**

## Ergebnis und wichtigste Abgrenzung

Die fruehere Archiv-Zusammenfassung wurde jetzt gegen direkt gelesene, bereits erhaltene dekompilierte Quelltexte und neu bereitgestellte IL-Auszugdaten geprueft:

1. Das globale Host-Enum definiert `GFA_READ = 201 (0xC9)`.
2. Das separate VS1-Draht-Enum definiert `GFA_Read = 0x6B`.
3. `VS1Message.getVS1MessageFromLDAPMessage()` bildet den abstrakten GFA-Leseauftrag auf den VS1-Drahttyp ab und uebernimmt Adresse und Laenge.
4. `VS1Message.toByteArray()` erzeugt fuer diesen Leseauftrag die vier Bytes **6B, Adresse high, Adresse low, Laenge**. Synchronisierung/STX gehoert zum darueberliegenden Verbindungsablauf.
5. `VS1Message.getBytesToRead()` erwartet fuer diesen Auftrag genau die angeforderte Datenlaenge, keine P300-Antworthuelle.
6. In den gelesenen `VSMSDK.SetCommand()`-Kontexten schaltet **VSKOStart explizit nach VS1**. Dabei werden vorherige Interface-, Queue-, Device- und Timerzustaende gesichert. **VSKOStop stellt das vorher gespeicherte Interface wieder her**, nicht pauschal und unabhaengig vom Ausgangszustand P300.

Das ist ein konkreter Hostsoftware-Nachweis fuer den GFA/VS1-Pfad. Ein globaler Enumwert und ein generischer P300-Serializer belegen dagegen keine native GFA-Unterstuetzung der 20C2-Firmware.

**Nicht bewiesen:** dass jedes GFA-Ereignis in allen Vitosoft-Versionen nur diesen Pfad benutzt; dass kein alternativer P300-Gateway oder autonomer RAM-Spiegel existiert; oder dass die gesamten privaten Assemblies jetzt vollstaendig verstanden wurden. Es wurde keine neue native P300-GFA-Implementierung gefunden.

## Direkt gelesene Quellen und Provenienz

Die proprietaeren Quelltexte verbleiben im privaten Quellenarchiv. In diesem oeffentlichen Dokument stehen ausschliesslich Ableitungen, Funktionsnamen, Fundstellen und Hashes, keine vollstaendigen Decompilierungen.

Privates Repository: `SaulGoodman1337/Viessmann-Vitosoft-300-SID1`.
Gelesener Git-Stand: `a94e367fb85909a8970b377f9f7395b55bf7e4f5`.
Bevorzugter Vollsnapshot: `vitosoft-private-archive-20260924-143439.7z`.
Archiv-SHA256: `3d31380d6dfabf8ede9e305b115e847fb0670511e253a4ed4e59feef2f7adfee`.

| Quelle im privaten Git | Git-Blob | Direkt gepruefter Inhalt |
| --- | --- | --- |
| `collector-output/20260925-vs1-process-read-trace/VS1Message.cs` | `f0ad78872394bf139843df51fa79726519218021` | Gesamte erhaltene Klasse, Umwandlung des abstrakten Auftrags, Serialisierung, Antwortlaenge |
| `collector-output/20260925-vs1-process-read-trace/summary.json` | `d5aaaf1aade0ffa08385c115a6e53ce06a79b21a` | Enum sowie dekompilierte SDK-/VSKO-Kontexte; gezielte Bereiche, nicht pauschal die gesamte Datei ausgewertet |
| `.github/workflows/vs1-process-read-trace.yml` | `9dca4afeb8ec93f1ee46a5978b671bbba16cba72` | Herkunft der vorhandenen C#-Ableitung: Extraktion der beiden Interface-DLLs aus dem gehashten v6-Archiv, ILSpy-Ausgabe, anschliessende Auswahl der Kontexte |

Die relevanten SDK-Kontexte stehen in der JSON-Datei etwa in Zeilen 4430-4545. Deren eigene Quellzeilenangaben beziehen sich auf `decompiled/vsmInterfaceCore/vsmInterfaceCore.sdk/VSMSDK.cs`, insbesondere um 577-610. Der Wechsel erfolgt in `SetCommand()`. Aeltere Berichtsnennungen von `IsSDKCommandRunnable` sind deshalb nicht als alleiniger Ausfuehrungsort des Wechsels zu lesen.

## Erneut erzeugter IL-Auszug: Aussagekraft und Grenzen

Ein bestehender **privater, nur lesender Analyseworkflow** wurde erneut ausgefuehrt, weil dessen frueheres Artefakt nicht mehr verfuegbar war. Er veraendert weder Heizungsdaten noch Repositorydateien. Er laedt das bestehende private v6-Release-Asset, prueft dessen SHA256, extrahiert vier Interface-IL-Dateien und erstellt grep-Kontexte.

- Workflow: `GFA read host path trace`.
- Workflow-Quellstand: `8fccc3cd045804bfae975693bc9c2835ffdd18f3`.
- Run-ID: `36175249425` (erneuter Joblauf am 2026-10-08).
- Neu geladenes Artefakt: `11538004477`, `gfa-read-host-trace`.
- Artefakt-ZIP-SHA256: `b340d4a152ee99671b82d760b7a766af1e0a13804fea24a1b66898963d09b325`.
- Bericht: vier Quelldateien; vier GFA-Enumtreffer; 147 Zeilen des zusaetzlichen Dispatch-Kontextreports.

Direkt sichtbare Enumstellen im IL:

| Datei | Quellzeile laut grep | Bedeutung |
| --- | ---: | --- |
| `MobileClient_vsmInterfaceCommon.dll.il` | 6454 | VS1 `GFA_Read = uint8(0x6B)` |
| dieselbe Datei | 6547 | abstrakt `GFA_READ = int32(0x000000C9)` |
| `Webbin_vsmInterfaceCommon.dll.il` | 6484 / 6577 | entsprechende Enumduplikate |

**Wichtig:** Die grep-Suche liefert hier ueberwiegend Enums. Manche Treffer fuer `0x6b` sind nur Kommentarwerte zur Codegroesse, keine Drahtbefehle. Dieses Artefakt allein ist deshalb KEIN vollstaendiger Dispatch-Nachweis. Fuer die obigen Schlussfolgerungen wurden zusaetzlich die vorhandene C#-Klasse und SDK-Kontexte direkt gelesen.

Es wurde in dieser Sitzung keine neue Voll-Decompilierung gestartet und nicht der gesamte 4-GB-Archivinhalt im lokalen Laufzeitsystem neu ausgewertet. Insbesondere bleibt ein etwaiger weiterer VS2-Sonderpfad ausserhalb der gelesenen Kontexte offen.

## Gegenfrage: Physical_RAM einfach nach VS1 bringen?

Die vollstaendig gelesene `VS1Message`-Umwandlung enthaelt sechs passende Faelle: Virtual Read/Write, GFA Read/Write und PROZESS Read/Write. Einen Fall fuer `Physical_READ` oder `Physical_WRITE` enthaelt diese Klasse nicht; ohne passenden Fall entsteht keine VS1Message.

Das grenzt den bekannten Hostpfad ein, beweist aber NICHT, dass die Kesselfirmware keinerlei undokumentierten VS1-Speicherzugriff hat. Historische GWG-OpCodes werden dadurch nicht zu erlaubten VS1-Kommandos. Fuer den aktuellen Versuch werden keine neuen OpCodes abgeleitet.

## Beziehung zum lokalen Livebefund

Bereits bestaetigt, unveraendert:

```text
P300 Virtual_READ 00F8/2 -> 20c2
P300 Virtual_READ 778C/2 -> 0103
P300 C9 / 4050 / 1     -> Error Message 3, Payload 05
```

Der letzte Nutzer-Nachtest nach dem zweiten Rollback liefert:

```text
VS1 gfaread 4050/1 -> 1;0x4050;20
VS1 gfaread 4006/1 -> 1;0x4006;00
```

Damit ist VS1-GFA nach diesem Ruecklauf tatsaechlich wieder lesbar. Fuer diese zwei Folgeabfragen wurde kein genauer Zeitstempel uebermittelt. P06=00 ist ein erfolgreicher Rohwert, aber keine unabhaengige physische Drehzahlmessung durch uns. Die Bedeutung von P300-Fehlerpayload 05 wird nicht erfunden.

## Konsequenz fuer den naechsten Arbeitsschritt

Wir muessen **C9 nicht wiederholen**, um Protokollwechsel sinnvoll zu messen. Ein separater Basistest liest die bereits bestaetigten virtuellen Identitaeten unter P300 und echte GFA-Werte unter VS1. Der bestehende Produktionskandidat mit geschlossenem C9-Gate bleibt unberuehrt; es wird kein fehlender Kanal kaschiert.

Implementierung und erster konkreter Aufruf: [Handover-Basistest](p300-handover-baseline-runbook.md).

Ein spaeterer Hybrid-Fork braucht fuer GFA eine validierte VS1-Phase oder eine neu nachgewiesene gleichwertige Datenquelle. Der jetzt folgende Test klaert zuerst, welche ENQ-/ACK-Wartephasen den bisherigen Zeitbedarf erzeugen. Erst danach wird die quellenbegruendete erste-ENQ-Variante ausgearbeitet. Ein autonom aktualisierter GFA-RAM-Spiegel bleibt ein eigener, noch offener Forschungspfad.

## Oeffentliche Querverweise

- [Vorheriger Quellenaudit](p300-switching-source-audit-2026-10-08.md)
- [Fork-/GFA-Optionen](p300-fork-switching-gfa-options-2026-10-08.md)
- [Negativer C9-Geraetebefund](p300-gfa-c9-hardware-rejection-2026-10-08.md)
- [Erhaltene Archiv-Auswertung](https://github.com/SaulGoodman1337/optolink/blob/79f222c7f3a11b848a6a8ac8ece50e24deede823/config/optolink-splitter/research/vitosoft/private-archive-2026-09-23-analysis.md)
