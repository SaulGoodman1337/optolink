# WB2A 20C2: Zusatzanalyse RX-naher 24-Bit-Muster (11.10.2026)

## Versuchsart
Reine Offline-Analyse bestehender P300-Physical_READ-SRAM-Snapshots auf optolink-splitter. Keine seriellen Befehle, keine Codier-, RAM-, SFR- oder Firmware-Schreibzugriffe. Die produktive Installation bleibt unveraendert.

## Herkunft und Selektion
Verzeichnis: /root/p300-trial-work/p300-fullram-results/run-20261009T083607Z-144293/snapshots
79 vollstaendige Images s00001.bin bis s00079.bin von jeweils 20480 Byte, zuvor als Archiv SHA256 94d5842b6dc5759ecb446a4c617b60b72873b639885d116032f783abdef8431c verifiziert.
Beim Verzeichnis-Glob s*.bin wird zusaetzlich s00080.partial.bin (20480 Byte auf Datentraegerebene, aber inhaltlich unvollstaendig) erfasst. Diese Datei muss explizit ausgeschlossen werden; der bestehende SHA-/Manifest-gepruefte Archiveinleser tut das bereits.

## Gemessene LE24-Werte bei festen RAM-Adressen
| RAM-Adresse | LE24-Wert | Haeufigkeit in 79 vollstaendigen Images |
| --- | --- | --- |
| 0x0B51 | 0xF203F | 75/79 |
| 0x0B55 | 0xFCBB6 | 75/79 |
| 0x0B5C | 0xF2420 | 75/79 |
| 0x0B74 | 0xF23FF | 79/79 |
| 0x0B7E | 0xE01F0 | 79/79 |

Die Werte 0xF203F und 0xFCBB6 sind NEUE Kandidaten gegenueber dem bisherigen fixen Auswertungssatz. Unregelmaessige RAM-Inhalte an 0x0B40-0x0B5F zeigen, dass hier Speicherzustand und/oder dynamische Strukturen vorliegen, nicht automatisch eine ISR-Tabelle. Das LE24-Interpretationsfenster kann selbst ein misaligniertes Feld treffen. Es wurde kein Program-ROM gelesen, kein INTB gesichert und kein UART1-RX-Handler oder Parser/State-Commit identifiziert.

## Naechster belastbarer Test
Die neuen Kandidaten zuerst an den 79 manifestverifizierten RAM-Images und unabhaengigen zeitlichen Sequenzen mit Adress-Ausrichtung, relativer Lage zu 0x0B6D und Nebenfeldern vergleichen. Programmcode-Disassemblierung erst nach einer echten, geprueften 20C2-ROM-Quelle. Eine direkte Aenderung oder Ausfuehrung dieser Werte ist nicht gerechtfertigt.

Vitotrol ist weiterhin NICHT am Regler registriert. Die Raumtemperaturregelung 0x2321 bleibt absichtlich pausiert.

## Zweite reproduzierbare Auswertung: synchronisierte Zustandsaenderung

Der gepinnte Originalarchiv-Auditor `tools/wb2a-vitotrol-near-rx-rom-candidates.py` wurde um
`0x0B51` und `0x0B55` sowie eine gemeinsame Anomalieanalyse von
`0x0B51/0x0B55/0x0B5C` erweitert.

Alle drei Feldinterpretationen weichen **in exakt denselben vier Aufnahmen**
vom jeweiligen Modalwert ab: **1, 41, 60, 62** (keine partiellen
Abweichungen). Die statusaehnliche Einzelbyteposition `0x0B6B` lautete:

| Beobachtungsgruppe | 0x0B6B=01 | 0x0B6B=0A | 0x0B6B=0B |
| --- | ---: | ---: | ---: |
| Drei benachbarte LE24-Werte gleichzeitig vom Modalwert verschieden | 1 | 3 | 0 |
| Keine gemeinsame Abweichung | 71 | 0 | 4 |

Die Klassenbytes des Master-TX-Snapshots `0x161A` waren bei allen drei
`0x0B6B=0A`-Ereignissen `01 00 B1 0A`, nicht eine Vitotrol-Discovery.
Die Archive sind nicht atomar aufgenommen; weder der exakte Zeitpunkt eines
UART-Empfangs noch eine physisch gesendete KM-Bus-Antwort ist belegt.

### Folgerung

`0x0B51`, `0x0B55` und `0x0B5C` sind **keine drei unabhaengigen,
unveraenderlichen ROM-Einsprungpunkte**: Sie liegen in einem
gemeinsam veraenderlichen Speicherbereich. Das erhoeht den Erkenntniswert
von `0x0B6B` als *Zustandskorrelationskandidat*, qualifiziert ihn aber
ausdruecklich **nicht** als schreibbares Receive-Ready-Flag.

Die unabhaengig in allen 79 Images stabilen `0x0B74=0xF23FF` und
`0x0B7E=0xE01F0` bleiben priorisierte *statische ROM-aehnliche Datenfelder*.
Ohne realen Controller-ROM-Inhalt und ohne INTB-Fund ist weder ihre Typisierung
noch eine Code-/ISR-Zuordnung moeglich. Das M16C-Handbuch definiert die
relokierbare Vektortabelle relativ zum CPU-Register `INTB`; dessen
aktueller Inhalt wird aus den P300-RAM-Snapshots nicht gewonnen.
Primarquelle: https://www.renesas.com/en/document/mah/m16c62p-group-m16c62pt-hardware-manual

## Neue Testevidenz

- SHA256-verifiziertes Originalarchiv: 79 vollstaendige Images erneut analysiert.
- Private Ausgabe: `/tmp/wb2a-vitotrol-neighbor-correlations-20261011.json`
- 8/8 spezielle Tests **mit** dem Root-only-Originalarchiv bestanden.
- Gesamtsuite: 619 Tests erfolgreich, 1 optionaler Test ohne Privatzugriff uebersprungen.
- Keine Controllerbefehle fuer die Analyse, kein Protokollwechsel und
  keine aktiven Schreibzugriffe an den Heizungskessel.

Naechster technischer Schritt: echte ROM-Quelle oder pruefbarer
Optolink-Dispatcher-Zugang. Eine reine FC04-RAM-Einspeisung an `0x1642`
hat die Vitotrol bisher **nicht** angemeldet.