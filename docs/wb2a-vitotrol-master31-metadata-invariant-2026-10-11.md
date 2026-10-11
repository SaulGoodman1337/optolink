# WB2A/20C2 – Master-0x31, RX-Metadateninvariante und Literalsuche

**Stand 11.10.2026, nach 21:00 CEST.** Ziel weiterhin Vitotrol-200/300-Emulation ausschließlich über den vorhandenen Optolink-Pfad. Keine neue KM-Bus-Hardware; alternative Raumregelung pausiert. Entwicklungsbranch `feat/wb2a-vitotrol-rpm-20261010`, Draft-PR #52; `main` und produktive Konfiguration unverändert.

## 1. Authentische Eingangsbeweise

| Originalquelle | SHA256 |
| --- | --- |
| Deep-295, 09.10. | `f0f015032edb94459ff2259a81ef2b84bf23253570d91cc6ba658c8160f5c2af` |
| Voll-RAM-79, 09.10. | `94d5842b6dc5759ecb446a4c617b60b72873b639885d116032f783abdef8431c` |
| Früher Fusionsread 16×, 11.10. | `d22dfbc58cad99798be16aac9bf8b9c55598eeb35f25316b54690bffc5c3a258` |
| Vorheriger RX-Burst, 11.10. | `7d539f98f5861554bf325c981bae33d13263997f96bc7233d42f694b0f5de65f` |
| **Neuer Master31-Metapair-Live-Mitschnitt**, 11.10. | **`d6cc2f4b69d3171944f22f1b5fb015c0bca4fc51dc28b2bb26137932b632db43`** |

Das Deep- und Voll-RAM-TAR werden vor dem Vergleich mit archivweitem SHA256, Einzeldatei-Manifests und CRCs geprüft. Alle privaten Rohdaten bleiben auf dem autorisierten LXC und werden nicht nach GitHub geladen.

## 2. Historische 0x31-Gegenprüfung – **keine** bewiesene Ursache

| Deep-Runde | Master (aus zwei getrennten Reads) | CRC | Natürlicher RX-B1 | TX-Start bis RX |
| --- | --- | --- | --- | ---: |
| 145 | `01 00 31 09 01 01 01 07 4E` | ungültig: `0x8A40` | selten `00 01 B1 0A 01 01 00 00 43 53` | 484,499 ms |
| 1417 | `01 00 31 09 01 01 10 A6 EA` | gültig: `0x0000` | normal `00 01 B1 0A 01 01 10 FE 23 D8` | 491,131 ms |

Die TX-Daten in Runde 145 wurden aus den sequenziellen Reads `0x1600/32` und `0x1620/32` mit 161,117 ms Abstand zusammengesetzt. Das CRC-ungültige Gesamtbild beweist **kein** fehlerhaftes physisches KM-Bus-Telegramm. Das einzige gültige Master-`0x31`-Gesamtbild aus diesen zwei Runden ist das Register-`0x10`-Beispiel **mit normaler B1-Antwort**. Snapshot 64 zeigt als zeitlich nachgelagerten TX-Puffer `01 00 B1`, keinen beweisbaren 0x31-Verursacher.

Offline-CRC-Gegenrechnung für `01 00 31 09 01 01 <Register> <CRC LE>`: `00` → `27 FA`; `01` → `AE EB`; `10` → `A6 EA`; `11` → `2F FB`. Keine dieser synthetischen Registeranfragen wurde in dieser Runde aktiv an den Controller gesendet.

## 3. Neuer ausschließlich lesender P300-Test: Master und beide RX-Metadaten

**Beginn 20:59:01, Rückstellung 21:00:29 CEST.** Alle preflight Guards: Geräte-ID `20C2/0103`, A0/B0/Type/Fehler `00/00/00/00`, originale Config-SHA. Vor Protokollumschaltung wurde ein **unabhängiger systemd-Restore-Timer** aktiviert; dazu EXIT-Handler mit erfolgreichem `RESTORE_VERIFIED`. Nur derselbe serielle Eigentümer `optolink-splitter.service`. Keine Regler-, RAM-, UART-, DMA-, IRQ- oder Codierwrites. Der separate ältere RPM-Resume-Dienst existiert nicht mehr; sein fehlgeschlagener Startversuch im wiederverwendeten Restore wird protokolliert, während der Splitter-Restore erfolgreich war.

**8 Zyklen; 51 erfolgreiche, strikt freigegebene Reads; je Zyklus:**

1. `FC03 0x161A/32` – vollständiger TX-Frame samt CRC, **eine** 32-Byte-Controllerkopie.
2. `FC03 0x164B/32` – RX-CRC-Endbyte `0x164B` und erstes Metadatenbyte `0x166A` in einer Kopie.
3. `FC03 0x164C/32` – beide Metadatenbytes `0x166A/0x166B` in einer Kopie.
4. `FC03 0x164B/32` – RX-/Meta-Fusionsread wiederholen.
5. `FC03 0x161A/32` – Master-TX-Frame erneut.

| Neues Live-Resultat | Wert |
| --- | --- |
| Master-TX-Speicherframes mit gültiger CRC | **16/16** |
| Master-TX-Header | **13× `0100B1`, 2× `2000B3`, 1× `010031`** |
| Echte CRC-gültige Master-`0x31`-RAM-Kopie | `01 00 31 09 01 01 10 A6 EA` (Ende Zyklus 5, **normaler** RX-Status) |
| Fusionsfenster `0x164B`–`0x166A` | **15× `C6|06`, 1× `53|06`** |
| Gemeinsam kopierte Metadaten `0x166A/0x166B` | **8× `06 00`** |
| Seltene Fusionsänderung Zyklus 2 | `53|06` → `C6|06` über zeitversetzte Reads |
| Nachher `SWIndex 0x0A5C`, Sensor `0x089C` | `00000000`, `03`; keine Vitotrol-Anmeldung |

**Bedeutende Korrektur zum vorherigen Fusionsbericht:** Dort ergaben 16 Einzelreads `15× C6|06` und `1× 53|0A`. Jetzt ist **`53|06` innerhalb desselben 32-Byte-FC03-Blocks** bestätigt. Eine starre Regel `CRC-Endbyte 53 => 0x166A=0A` ist **widerlegt**. Da in der letzten Messung nicht gleichzeitig der komplette RX-Frame gelesen wurde, ist `0x164B=53` allein **kein Beweis** eines gerade vollständigen seltenen B1-Frames. Stale/teilaktualisierte RX-Zustände bleiben möglich. Alle Controller-Reads sind sequenziell; kein IRQ-Timing oder echte elektrische KM-Bus-Übertragung wurde gemessen.

## 4. Neue Invariante zweier Metadatenbytes (nicht als Queue-Flag ausgeben)

79 originale RAM-Bilder: `06 00` **78-mal**, `0A 04` **einmal**. Acht neuere, in je **einer** `FC03 0x164C/32`-Kopie erfasste Paare: **8× `06 00`**. Also für **87** bekannte Wertepaarbeobachtungen (jedoch **nur zwei verschiedene Zustände**):

`(RAM[0x166A] - RAM[0x166B]) & 0xFF == 0x06`.

Im seltenen Zustand steigen beide Bytes um vier, während der Differenzwert sechs bleibt. **Mögliche, noch unbewiesene** Bedeutung: zwei zusammenhängende Cursor/Positionen eines RAM-Puffers. Genau so möglich sind unabhängige, funktionsabhängige statische Parameter. Das ist **weder** ein nachgewiesenes Ringbuffer-Protokoll **noch** der UART1-Empfangsinterrupt, eine gültige Schreibadresse oder eine bestätigte Consumer-Routine. Keine RAM-Manipulation aufgrund dieser Invariante.

## 5. Statische unaligned LE16-RAM-Literalsuche, kein MCU-Code-Xref

Über alle 79 SHA/Manifest-bestätigten 20-KiB-Images wurden tatsächliche Little-Endian-Bytefolgen gesucht:

| Gesuchte Adresse | Statische Literalfundstellen 79/79 | Sonstige |
| --- | --- | --- |
| `0x166A` (`6A 16`) | `0x2185`, `0x51A1` | `0x0D16` 1×, `0x0FB9` 1× |
| `0x166B` (`6B 16`) | keine | keine |
| `0x166C` (`6C 16`) | keine | `0x1BCB` 2× |
| `0x1642` (`42 16`) | `0x0B6D`, `0x33A3` | `0x0B5C` 2×, `0x0FB8` 1×, `0x1199` 1× |

Die umgebenden Speicherfelder von `0x2185` und `0x51A1` bleiben beim seltenen Snapshot64 an diesen Literalstellen unverändert; die ganze untersuchte `0x51A1`-Umgebung war statisch und wirkt datenartig. Das sind **zwei stabile Literalstellen**, nicht 158 unabhängige Zeigerbelege. Die tatsächliche Datentypisierung/Code-Referenz des Controllers ist unbekannt.

## 6. Ausführung, Test-Gates und Fortsetzung

Neue Forschungsprogramme: `tools/wb2a-vitotrol-class31-rx-correlation.py`, `tools/wb2a-vitotrol-master31-meta-pair-readonly.py`, `tools/wb2a-vitotrol-master31-meta-session.sh`, `tools/wb2a-vitotrol-master31-meta-pair-audit.py`, `tools/wb2a-vitotrol-rx-metadata-invariant.py`, `tools/wb2a-vitotrol-rx-meta-pointer-xref.py`. Jeweils eigenständige `tests/test_wb2a_vitotrol_*.py` für CRC, Quellhash, falsche Antworten, Address-/Zeit-/Längengates, Bounds und unveränderten Controllerzustand.

**Nächstes echtes Gate**: Zunächst die P300-Zeitauflösung verbessern. Die bisherige CLI-Abrufroutine benötigt pro Read ungefähr 1,6–1,8 s, während die archivierten direkten Deep-Reads etwa 0,14–0,16 s benötigten. Ein persistenter, strikt lesender Request-/Subscribe-Pfad **innerhalb des unveränderten Einzelport-Splitters** könnte kurzlebige ISR-/Cursor-Zustände deutlich besser beobachten. Vor Umsetzung keine zusätzliche serielle Besitzerinstanz, keine Schreibzugriffe. Danach gezielt neue `0x166A/0x166B`-Zustände suchen, anstatt viele identische `06 00`-Abbilder zu sammeln.

**Nicht erreicht**: Kein echter ROM-Dump, keine nachgewiesene Klasse11-UART1-ISR, kein Vitotrol-Consumer-Commit und keine gültige Vitotrol-Anmeldung. Alle Versuche bleiben auf Optolink beschränkt.

## Nachtrag 11.10.2026 21:25 CEST: Die vermeintliche konstante +6-Differenz ist widerlegt

Die bisherige Beobachtung `0x166A/0x166B` = `06 00` (86×) oder `0A 04` (1×), jeweils Differenz 6, gilt **nur für jene 87 Proben**. Ein **neuer**, durch einen CRC-gültigen natürlichen Master-`0x31`-Register-00-Request ausgelöster, strikt lesender `FC03 0x164C/32`-Mitschnitt ergab **`0A 07`**, Differenz **3**. Daher ist die Hypothese einer universell konstanten Offset-Differenz **ausdrücklich verworfen**. Das ist kein Schreib-/ISR-Trigger.

Der vollständige Master-RAM-Request `01 00 31 09 01 01 00 27 FA` und danach der seltene Klasse01-RX-B1-Frame `00 01 B1 0A 01 01 00 00 43 53` wurden als zwei eigene, CRC-gültige Einzelkopien mit 0,311 ms Hostabstand zwischen den Requests beobachtet, aber **nicht atomar** oder elektrisch auf dem KM-Bus verifiziert. Beim Bytevergleich mit historischem FullRAM-Snapshot 64 stimmen 31/32 Bytes der `0x164C`-Fenster überein; nur `0x166B` wechselt `04` → `07`. Siehe neueren Bericht `wb2a-vitotrol-persistent-mqtt-master31-register00-2026-10-11.md`. Frühere Schlussfolgerungen aus der +6-Konstanz haben keine allgemeine Gültigkeit.
