# WB2A 20C2/0103 – Nächster Optolink-only-Schritt: ROM-Monitor-Eingang finden

**11.10.2026**. Nutzerauflage: **nur Optolink**, keine Boardarbeit, keine Programmer/Boot-Pins, keine weitere Hardware. Hauptziel bleibt echte Vitotrol-200/300-Anmeldung über P300. Die Raumtemperatur-Alternative `0x2321` ist pausiert. Bestehender produktiver Splitter, MQTT-Dienste und RPM-Logger sollen nicht verändert werden.

## 1. Belegte Datenkette statt weiterer Adress-Sweeps

Die frühere, am echten `20C2/0103` nachgewiesene P300-`Physical_READ FC03`-Verarbeitung ist präzise eingegrenzt:

```text
Hostanfrage / P300 FC03
     |
     +--> 16-Bit-Anforderung in Kommunikations-RAM um 0x196C
                   |
                   v
            FC03-Kopierroutine
                   |
     Quelladresse (low 16) -> Scratch-Puffer 0x1933..0x1952
                                        |
                                  TX-Nutzdaten 0x19B5
                                        |
                                  DMA1/UART0/Optolink
```

Überlappende Quelle/Scratch-Messungen bestätigten **vorwärts kopierende memcpy-ähnliche Semantik**; die Länge der Antwort entspricht exakt der angeforderten Low-Memory-Menge. Das ist ein **nachgewiesener Controller-seitiger Speichertransport**, aber die Eingabe enthält nur 16 Bit und kopiert keine belegte Programm-ROM-Adresse über `0xFFFF`. Quelle: `physical-ram-optolink-map-2026-09-26.md` / `physical-read-scratch-map-2026-09-27.md`.

Das fehlende Primitive ist daher klar formuliert: Ein belegter Monitor-/RPC-/Copy-Service muss eine **20-Bit-Quelladresse** entgegennehmen oder aus separatem Zustand zusammensetzen und das Ergebnis in diesen RX/TX-Datenpfad beziehungsweise in gewöhnlich lesbares RAM schreiben.

## 2. Originaldaten: Die zwei 3+3+2-Far-Source/Low-Destination-Tupel

Alle **79** historischen `20C2/0103`-P300-RAM-Abbilder `0x0400..0x53FF` wurden über das SHA256-gepinnte TAR-Archiv **sowie das Dateimanifest und die Image-Metadaten** erneut geprüft. Quelle SHA256:
`94d5842b6dc5759ecb446a4c617b60b72873b639885d116032f783abdef8431c`.

| Feld | A | B |
| --- | --- | --- |
| Feldbeginn | `0x1DE5` | `0x1E6A` |
| Rohdaten | `AB A2 0E 01 33 00 1D 00` | `05 07 00 7D B2 0F 07 00` |
| Mutmaßliche 20-Bit-ROM-Quelle | `0xEA2AB` | `0xFB27D` |
| Mutmaßliches Low-RAM-Ziel | `0x3301` | `0x0705` |
| Mutmaßliche Länge | 29 | 7 |
| Unveränderte Feldtupel | **79/79** | **79/79** |
| Unterschiedliche Zielblockinhalte | **1** | **1** |
| Zielbytes mit 0x64-Füllmuster | 0/79 | **79/79** |
| Verschiedene 24-Byte-Nachbarschaften | 1 | **75** |

Der B-Tupeltyp ist `lowRAM24 | farROM24 | len16`, bei A `farROM24 | lowRAM24 | len16`. Das ist **keine** identische Struktur und schützt vor einem falschen gemeinsamen Parser.

**Neue Einstufung:** Weder A noch B zeigt in diesem historischen Fenster die Datenbewegung eines lebenden ROM-Readers. A enthält einen unveränderten, hochentropieähnlichen 29-Byte-Datenblock; B zeigt über alle 79 Aufnahmen siebenmal das Füllbyte `0x64`. Beide wären weiterhin mit einer einmalig initialisierten Tabelle/Stack-Zwischenspeicherung kompatibel; weder anfangs noch jetzt gibt es einen belegten Aktivierungsaufruf. Ihre Nachbarschaft macht B eher task-/stackähnlich, nicht automatisch zum lesbaren ROM-Mailbox-Service. Nicht als schreibbare Sprungadressen interpretieren.

## 3. Neuer DMA-Befund und harte Sicherheitsgrenze

Die M16C/62P-DMA-Quellregister haben **20-Bit-Adressen**, auch für internes ROM möglich. Unsere 29 realen Optolink-Leseabfragen mit fünf DMA-Zeitpunkten bestätigen aber:

- DMA0 gehört `UART1/KM-Bus`, Quelle `0x0161B/0x01621`, Ziel `0x003AA`, Selector `0x0F`.
- DMA1 gehört `UART0/Optolink`, Quelle `0x019AF`, Ziel `0x003A2`, Selector `0x0A`.
- Transfer-Zähler variieren; DMA0 war bei einer Stichprobe aktiv. Beide Kanäle sind **nicht frei**, auch wenn die DMAE-Bits während kurzer Pausen auf null stehen.

Der vorhandene Host-`systemd`-Restore kann UART/Optolink-Verbindung nur wiederherstellen, wenn der Controller weiterhin auf dem seriellen Pfad antwortet. **Keine direkte DMA-SFR-/Softwaretrigger-Manipulation**, weil sonst selbst der Rückkanal verloren gehen kann. Ein 20-Bit-DMA-Hardwarevermögen beweist keinen optolinkseitig erreichbar gesicherten DMA-Service.

## 4. Geordnete nächste Forschung (weiterhin nur Optolink)

1. **Controller-Input-/Request-Provenienz rekonstruieren:** In den vorhandenen VitoSoft-V6-/VitoTest-/OpenV-Binärdateien alle explizit aufgebauten P300-/GWG-Frames mit anwendungsspezifischem Prefix/Adress-Proxy erfassen. Vorhandene negative Ergebnisse beachten: Host-`EventType.Address` ist `ushort`; normale RPC-Kataloge haben keinen belegt geeigneten ROM-Service. Interessant bleiben *undokumentierte*, direkt serialisierte Requests mit zusätzlichen Adressbytes oder zustandsbehafteten zwei Schritten.
2. **Historisches KarlKoch-Artefakt gezielt suchen:** M30612MC-Mask-ROM ist laut OpenV-Historie mit Aufwand über Optolink lesbar gewesen, aber die Originalsequenz ist nicht bekannt. Nur Quelltext, originale Traces oder wiederauffindbare private Werkzeugbytes qualifizieren einen Live-Test. Keine Übertragung von `V200KW2/2098` auf `WB2A/20C2` ohne Nachweis.
3. **P300-Service-Eingabeseite gegen den echten Low-Memory-Datenpfad korrelieren:** `0x192C`, `0x1933`, `0x196C`, `0x19AE`, `0x19B5`. Sobald ein **belegter** Adress-/Prefix-Selector auftaucht, zunächst ein exakt begrenzter *rein lesender* Request mit verifizierter `20C2/0103`-Identität, `0x5738=00` sowie vor/nachher Status, unabhängigem Host-Restore. Ein zufälliger Schreib-Prefix ist kein geeigneter Test.
4. **Akzeptanzkriterium für echten ROM-Fund:** dieselbe an `0xC0000..0xFFFFF` verortete 8-/16-Byte-Quelle muss in zwei unabhängigen, stabilen Optolink-Reads übereinstimmen, darf nicht identisch mit den bekannten periodischen `54xx`-Buswerten sein und muss plausiblen M16C-Maschinencode oder plausible feste Vektoren enthalten. Erst dann einen segmentierten, prüfsummenvalidierten größeren Dump implementieren.
5. **Für Vitotrol weiter:** nach erfolgreichem echten ROM-Lesefund UART1-Interruptvector / `INTB`, Parser für Klasse `0x11` und Teilnehmer-Commit `0x0A5C/0x089C/0x0896` rückverfolgen.

## 5. Prüfbar gesichert

Neue Offline-Analyse `tools/wb2a-vitotrol-rom-copy-candidates-offline.py` und `tests/test_wb2a_vitotrol_rom_copy_candidates_offline.py`, inklusive synthetischer Gegenbeispiele, strikter SHA-/Manifestprüfung und **7/7 privater Archivtests bestanden**. Gesamtsuite: **656 Testfälle, davon 654 bestanden und 2 optionale übersprungen** beim regulären User. Keine Controller-, UART-, DMA- oder Codierwrites dieser Arbeitsphase, kein zusätzlicher serieller Eigentümer. GitHub-Forschungs-PR bleibt Draft, produktiver Splitter unverändert.
