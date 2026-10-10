# WB2A / VDensHO1: forensische Auswertung Temporal-Full-Run (9.10.2026)

**Nur Aufgabe 1: echte GFA-P06-Geblaese-Istdrehzahl und vollstaendige P300-Funktionsparitaet.** Geraet `20C2`, SW `0103`, GFA P80 `20`. Forschung in `optolink-p300-migration`; PR #46 bleibt **Draft/unmerged**; `/opt/optolink` nicht aendern. Die Aufnahme ist **abgeschlossen**; alle folgenden Resultate beruhen auf einem unabhängigen **offline** Audit, nicht auf einem weiteren Hardwarezugriff.

## 1. Session, Herkunft, Abschluss

- Privates Nutzerarchiv: `p300-temporal-run-20261009T131357Z-220351-bundle.tar.gz`. **SHA256 `f174ee298d60aa2a4a1c31dfc8784a5c0f278475870e823db27bb03d5f06cbda`** (2.288.000 Byte).
- Session `run-20261009T131357Z-220351`, gepinnter Quellcommit `eb7a9549b812caa95f934950d32ce01b613e7d28`, Python-Version `1.1.0-p300-temporal-candidate`; **6/6 gepinnte Quellhashes stimmen**, 23/23 Manifest-Nutzdateien stimmen in Groesse/SHA256, 24 Tar-Mitglieder mit Manifest.
- Lauf **2026-10-09 13:13:57.388 bis 15:14:09.097 UTC** (15:13:57 bis 17:14:09 MESZ). `observation_complete=true`, `data_quality=COMPLETE`, `errors=[]`, `writes_issued=false`, SIGTERM null. **7.186,156 Sekunden tatsaechlicher P300-only-Stream**.
- **5.224 vollstaendige Kernzyklen**, **23.028 erfolgreiche P300-Paketreads**: 10.448× FC01/55D3/11, 5.224× FC03/0F20/32, 5.224× FC03/1C60/32, je 533× FC03/0F00/0F40/1C40/1C80/32. **533** vollstaendige Kontextgruppen.
- Unabhaengig ueberprueft: **23.028/23.028** TX-Anfragen und Response-Frames (ACK, STX, Laenge, FC, Big-Endian-Adresse, MessageID, Payload, Checksumme), alle 5.224 Zyklusfolgen/Packetordinals, jedes Core-/Kontext-Offset, Payload und SHA256. **0 Paket-/Rekonstruktionsfehler**. **334.336 Bytes** Core-Paare = 5224×64, **68.224 Bytes** Kontext = 533×128.
- TX/RX-Spur **69.306 Ereignisse**, davon **46.168 TX** und **23.138 RX**. Alle P300-Datenreads in genau sieben bekannten FC01/FC03-Formen, zwei bekannte P300-Identitaetsreads `00F8/2` und `778C/2`, daneben nur die dokumentierten VS1-Identitaets-/GFA-Leseframes, EOT/ENQ/ACK; **kein unbekannter Write-/SFR-/C9-/RPC-Zugriff**.
- **2/2 erfolgreiche Protokollwechsel**, VS1→P300 **2,163 s**, P300→VS1 **4,329 s**; `worker_vs1_restored=true`, `systemd_result=success`, **6/6 urspruengliche aktive Systemd-Units wiederhergestellt**, `recovery.errors=[]`. Wiederhergestelltes MQTT P80=`20`, P06=`00` (**0 U/min, gueltig / nicht FF**). `ha_entity_freshness_verified=false`: HA-Frische **nicht** belegt. Keine behauptete tatsaechliche Ist-RPM-Messung waehrend P300.

## 2. Neue substanzielle Resultate: 0F20/1C76 sind NICHT nur zweistufig

| Befund | Ergebnis |
| --- | --- |
| `0x0F20` verschiedene Bytewerte | **29**, von `00` bis `AC` (=172 dez.) |
| `0x1C76` verschiedene Bytewerte | **27**, ebenfalls bis `AC` |
| `0x0F20` exakt `00` | **3.474/5.224** Zyklen |
| `0x0F20` exakt `54` (=84 dez.) | **1.683/5.224** Zyklen |
| `0x0F20` weder `00` noch `54` | **67/5.224** Zyklen |
| Veraenderungen des 0F20-Felds | **60** aufeinanderfolgende Zyklusuebergaenge |
| Dreifach-Mirror-Pruefung aller Kandidatenpaare | **21** Abweichungszyklen |
| Spezifisch `0F20 != 1C76` | **15** Abweichungszyklen |
| Median Antwortversatz der beiden FC03-Reads | **0,1632 s** |
| Status A/B kohärent fuer Flame/P87/Lockout | **5.200/5.224** Zyklen |
| `0F29` stimmt mindestens mit Status A **oder** B Byte7 | **5.224/5.224** Zyklen |

Die **67 dynamischen `0F20`-Zyklen** liegen innerhalb **15:59:23–16:00:54 MESZ**: Kandidat springt von `0x54` auf `0xAC` und veraendert sich dann ueber viele Zwischenschritte (z. B. 170, 165, 157, 144, 130, 120, 106, 91, 88), waehrend die Flamme bereits EIN bleibt. Nachfolgende Rampen etwa `95→148→102→132→84`. FC01-Byte0/9 (Modulation/Status, **nicht** echte P06-RPM) aendern sich dabei mit, aber nicht gleichzeitig: `0F20=172` erschien zuerst bei **FC01-Byte0=38, Byte9=33**, die Modulationsbytes steigen erst in nachfolgenden Samples. Die Pearson-Korrelation `0F20↔FC01-Byte0` **nur** in den 67 Nichtbasis-Samples betraegt `r≈0,7505`, deskriptiv und stark zeitlich autokorreliert; **keine Istwertkausalitaet**.

Eine hypothetische Kodierung `P06_raw = 0F20-1` wuerde `0x54→2490 U/min` und `0xAC→5130 U/min` ergeben. **Die 5.130 U/min sind HYPOTHETISCH, NICHT gemessen und duerfen nicht als Drehzahl ausgegeben werden.** Der vorherige P06-Fokuslauf beobachtete zudem echte VS1-P06=**4410 U/min** unmittelbar vor kurzen P300-Fenstern (Captures 4 und 7), mit POST-P06 **3870..4230** bzw. **4050..4230 U/min** waehrend einer Downrampe, aber `0F20=1C76=0x54` in je zwei RAM-Runden. Das ist ein **Gegenindiz zur einfachen momentanen Istwert-/P06+1-Semantik**. Weil PRE und POST nicht identisch und Protokollphasen nicht gleichzeitig waren, ist es noch kein formal vollstaendiger Ausschluss einer zeitlich anders aktualisierten Representation.

## 3. Noch tiefere Speicherstruktur: interne P300-Statuskopien

- `0x0F21` ist in **5223/5224** Kernzyklen `0x09` (einmal `0x01`, Cycle 2957). Das koennte ein Laengen-/Objektmarker sein, ist **nicht bewiesen**.
- Die direkt folgenden **9 RAM-Bytes `0x0F22..0x0F2A`** sind in **5222/5224** Zyklen genau die ersten neun FC01-`55D3`-Statusbytes von Status A oder Status B. Die Bytes **`0F2B/0F2C` gehoeren NICHT als Statusbyte 9/10 zu dieser Kopie**; genau deshalb ist **9** und nicht 11 die bewiesene Spiegelbreite.
- Die neun Bytes **`0x1C77..0x1C7F`** stimmen **5224/5224** Mal mit Status A oder B (erste neun Bytes) ueberein.
- Die beiden neun Byte langen RAM-Spiegel stimmen untereinander **5108/5224** Mal ueberein, abweichend in 116 Zyklen durch zeitlich nacheinander durchlaufende Statusupdates. Der separate **0F20-/1C76-Variablenwert steht jeweils direkt davor**; seine Semantik ist **offen** (Ist-RPM, Sollwert, Staging, Zustandswert).
- Insbesondere bei Statusaenderungen kann der Erste RAM-Read zum frueheren, der zweite zum spaeteren FC01-Frame passen; die P300 FC03-Reads erfolgen sequenziell. Spiegelinkonsistenz ist daher **kein Fehler**, und nicht gleichbedeutend mit zwei unabhaengigen Messquellen.

Diese starke Strukturkopie beweist, dass die gelesenen Fenster lebendige GFA-nahe Statusobjekte enthalten; das ist ein besserer Ansatz als ein neuer undifferenzierter Voll-RAM-Sweep.

## 4. Fuenf vollstaendig beobachtete natuerliche Flamme-EIN/AUS-Zyklen

Das Roh-FC01-Protokoll enthaelt **5 steigende + 5 fallende Flammenkanten**, keine gesetzte Lockout-Kante. **36** aufeinanderfolgende P87-Byte7-Aenderungen in der vollständigen 10.448-Frame-Reihe (die Fortschrittszahl **15** bezieht sich nur auf einen eng definierten `events.jsonl:NATIVE_CHANGE_BYTE7`-Zaehler). Ferner 274 Aenderungen in Statusbyte0 und 267 in Statusbyte9.

**In allen fünf Brennerstarts** wechselte `0F20` von Null auf Nichtnull **10,704–12,129 Sekunden vor dem nativen Flamme-EIN** (Median **11,528s**). **In allen fünf Abschaltungen** ging `0F20` **2,137–3,134 Sekunden vor nativen Flamme-AUS** auf Null (Median **2,593s**). Das ist mit einer Vor-/Nachlauf-/Ansteuerungssequenz eines Geblaeses *vereinbar*, aber nicht automatisch ein unabhängiger Hall-Tacho. Gerade die fast schlagartige 84→172-Anhebung **vor** dem Modulationsanstieg spricht auch fuer einen vorauseilenden **Soll-/Anforderungswert**.

## 5. Beweislage nach drei Experimenten

| Hypothese | Bewertung |
| --- | --- |
| Ein einfacher exakter `00→53`-P06-RAM-Spiegel | **Nicht nachgewiesen** im frueheren 79×20-KiB-VollRAM-Vergleich |
| `0F20/1C76` sind **nur** konstante EIN/AUS-Flags | **WIDERLEGT** durch 29/27 unterschiedliche Werte im neuen Temporal-Stream |
| `0F20/1C76` sind sicher die **echte aktuelle Ist-RPM** | **NICHT BELEGT**; keine zeitgleiche reale P06 unter P300, bestehender Fokus-Gegenbefund |
| `0F20/1C76` sind GFA-nahe interne Diagnose-/Prozessfelder | **STARK GESTUETZT** durch die direkt folgenden neun nativen 55D3-Statusbytes |
| `0F20/1C76` sind Geblaese-Drehzahl-**Sollwerte** oder Steuer-/Stagingdaten | **OFFEN und plausibel**; sprunghafter Vorlauf der Modulation, keine echten RPM-Klammern fuer 172 |
| Direkte native P300-GFA-C9-Operation | **NEGATIV** fuer konkret getesteten C9/4050/1-Frame; andere Firmwarepfade unbewiesen |
| GFA-P06 von P300 aus periodisch ueber echtes VS1 lesen | **Architekturell moeglicher Fallback**, aber nur ein serieller Besitzer und gemessene ~6,5s Wechselkosten |

## 6. Naechster Schritt – nicht noch ein identischer Stream

**Bevor ein weiterer Hardwarelauf zugelassen wird**, die zweite Dokumentation [Trigger-getriebener VS1-P06-Wirkvergleich und Single-Owner-Fallback](p300-rpm-next-experiment-and-architecture-2026-10-09.md) beachten. Prioritaet: EIN gezieltes kurzes **P300→VS1(P06/P09/P87)→P300**-Experiment **nur bei natuerlich hohem stabilen RAM-Kandidaten**, wenn ein freigegebener und offline getesteter Logger mit Pause/Recovery, Limits und Provenienz bereit steht. Diese Gegenmessung klaert Istwert/Sollwert besser als ein neuer 2h-Stream ohne echtes P06 waehrend P300. Ohne ausreichenden positiven Nachweis dann **Single-Owner-P300+VS1-GFA-Hybrid** statt Endlossuche.

**Privates Roharchiv nicht in Git committen**; nur Hash, aggregierte Fakten und pruefbare Methodik. Keine Task-2-(Vitotrol-/KM-Bus-) oder Task-3-(Pumpenoverride-)Implementierung, keine unbekannten Writes/RPC/SFR, kein Merge.
