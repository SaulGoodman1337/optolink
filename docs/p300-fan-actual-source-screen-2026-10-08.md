# VDensHO1 / WB2A: P06-Istdrehzahl unter P300 - gezielter Quellenaudit

**2026-10-08 · Branch optolink-p300-migration · Negatives, modellgebundenes Suchergebnis.**

## Ergebnis

Auf dem lokalen `20C2 / 01.03` ist `GFA_READ P06 (VS1/6B, Adresse 0x4006, raw * 30 U/min)` die belegte Ist-Geblaesedrehzahl. `P09` ist fuer die P80=20-Variante **Modulationssollwert**, nicht identisch mit dem gemessenen Motorwert. Ein **unter P300 sicher lesbarer, unabhaengiger P06-RPM-Alias** wurde weder im exakten Geraeteprofil noch in den neu gesichteten Katalogen oder in den elf Bytes von `0x55D3` gefunden.

Das bedeutet **nicht**, dass der Wert niemals im Hauptregler-RAM zwischengespeichert wird. Es ist eine klare Grenze des untersuchten Quellen- und Aufnahmebestands, **keine** allgemeine Firmware-Unmoeglichkeitsaussage.

## 1. Zusaetzliche oeffentliche Quelldaten, nach Geraetefamilie getrennt

| Treffer | Quelle / Modellgrenze | Schluss |
|---|---|---|
| `0x0B1E`, `SC100_DrehzahlIst` | [VBC550S-Katalog](https://github.com/SoulSolistice/esphome_vitohome/blob/main/example/catalogs/vbc550s.yaml), Blob `be75d86e6a766bee29a3dd3beb389e266c8a1e9a` | **Andere Brenner-/Reglerfamilie; keine 20C2-Adresse.** |
| `0x1A53`, `Status_Fanspeed` | [SmartHomeNG-Katalog](https://github.com/smarthomeNG/plugins/blob/0176a8684934aab9a52f905cdea80f8410200c2f/viessmann/commands.py), `V200WO1C`-Block ab Zeile 3040, Treffer Zeile 3086 | **Anderes Modell; keine 20C2-Adresse.** |
| `0x7660`, `0x7663` | [VDensHO1-Datenpunktliste](https://github.com/MorrisonHB/Optolink_02/blob/master/Optolink_02/Documentation/DP_Listen/DP_VDensHO1.txt), Blob `d0d2a6941c7d68fa5cc7b5ea431c20e0b827746f` | Interne bzw. A1-Heizkreispumpe, nicht Feuerungsautomat-Geblaese. |
| `0x55D3`, `0x7650` | Gleicher VDensHO1-Datensatz, außerdem [ESPHome VitoHome VDensHO1](https://github.com/SoulSolistice/esphome_vitohome/blob/main/example/catalogs/vdensho1.yaml), Blob `0171ea32f90d317fb801ae0938fa59a39bb0c869` | Feuerungsautomat-Status und Typkennung; kein benannter P06-Tacho. |

**Provenienzgrenze:** VitoHome ist selbst ein aus Vitosoft-XML generierter Katalog. Er schreibt, dass **117** Events mit GFA_READ/RPC/KBUS/anderen nicht direkt erreichbaren Zugriffsmethoden aus dem Standardkatalog entfernt wurden. Die fehlende P06-Zeile ist daher kein unabhängiger Hardwarebeweis. Mehrere Listen können denselben XML-Ursprung haben; wir zählen sie **nicht** als unabhängige Echtgerätemessungen.

Der bereits ausgeführte **vollständige Profiljoin** aus Vitosoft ist hier stärker: für **exakt VDensHO1** 581 Events, 362 Adressen, davon 94 GFA_READ-Events über verschiedene GFA-Varianten, aber kein dem lokalen P06 entsprechender *benannter virtueller Ist-RPM-Kanal*. [Vorheriger Profilaudit](p300-gfa-source-candidates-2026-10-08.md). Die fremden Adressen wurden **nicht** an der WB2A probeweise gelesen.

## 2. Erstmals alle elf Statusbytes gegen echte P06-Klammern verglichen

Zwei hochgeladene, private Quelldateien:
- `pairs.jsonl`, SHA256 `5323deef1cc01c67918e31d9d3bc22e2c3df3f4429f52ff80f3dda6724cf1411`
- `summary.json`, SHA256 `41a4c1dcaef875ff805e18b9912b28b80e7adca3d86eb56ea2e7e8858a4ec987`

**180** sequenzielle `P06 -> P09 -> Virtual_READ 55D3/11 -> P09 -> P06`-Runden, Fehlerliste leer, kein Protokollwechsel, kein Write. **171** P06-Klammern stabil (154 mit `00`, 17 mit Nichtnull); **neun** veraendert. P09: 180 stabile Klammern. 24 Samples mit dokumentiertem Flammenbit.

Nullbasierter Byteindex; Rohbereiche **dezimal**. Nichtnull bei gleichzeitig stabiler P06=00 bedeutet keine *direkt gleiche*, unskalierte RPM-Kopie; es widerlegt nicht jede denkbare interne Codierung.

| Byte | Unterschiedliche Werte | Rohbereich | Nichtnull bei P06=00 | Einordnung |
|---:|---:|---:|---:|---|
| 0 | 10 | 0..71 | 0/154 | Vorher belegte Ansteuer-/Control-Diagnose, **kein** unabhaengiger Tachometer. |
| 1 | 20 | 88..116 | 154/154 | Unbenannt, dynamisch trotz P06=00; keine RPM-Semantik. |
| 2 | 7 | 151..157 | 154/154 | Wie Byte1, nicht 1:1 P06. |
| 3,4,8 | jeweils 1 | 0 | 0/154 | In dieser Aufnahme konstant. |
| 5 | 3 | 1..41 | 154/154 | Bereits zugeordnete Flammen-/Statusflags. |
| 6 | 3 | 0..11 | 1/154 | Status-Hilfsfeld; kein RPM-Nachweis. |
| 7 | 4 | 0..98 | 1/154 | Unter P300 dynamisch nachgewiesener P87-Statuskandidat, kein RPM. |
| 9 | 10 | 0..68 | 0/154 | Modulations-/Ansteuerwert, kein Ist-Tach. |
| 10 | 3 | 1..41 | 154/154 | Flagspiegel (bereits im frueheren 807-Frame-Satz mit Byte5 identisch). |

### Direkt beobachtete Unterschiede

- **R110:** P06 stabil `00`, P09 `93`, native Byte0/Byte9 noch `0`.
- **R114:** P06 stabil `93`, P09 `91`, Byte0=69 und Byte9=66.
- **R116:** P06 stabil `81`, P09 `7D`, Byte0=61, Byte9=56.
- **R122:** P06 stabil `53` = 83 * 30 = 2490 U/min nach *P06*-Skalierung; P09 `53` mit **anderer physikalischer Bedeutung**, Byte9=33. Eine einzelne Plateaukorrelation ist keine RPM-Umrechnung.
- **R136:** Flammenbit aus, P09 `00`, Byte9 noch 33; P06 aendert sich *innerhalb seiner Vor-/Nach-Klammer* von `52` zu `1D`. Die Abfragen sind nicht gleichzeitig; keine unbewiesene exakte Abfalllatenz behaupten.

Byte0/Byte9 duerfen deshalb nicht durch eine erzwungene Regressionsformel in einen scheinbar gemessenen P06-Drehzahlsensor verwandelt werden. Von Byte1/2 fehlen ebenfalls Quelle, Einheit und dynamischer Tach-Nachweis.

## 3. Reproduzierbarkeit und Sicherheitsgrenze

Neuer rein lokaler [Auditor](../tools/audit-vdensho1-fan-source.py) samt [16 Negativ-/Positivtests](../tests/test_vdensho1_fan_source_audit.py). Er kontrolliert alle Bytes, Identitaet `20C2/0103`, GFA-P80, Zeitklammern, Rohwerte und Zaehler und verweigert unbewiesene Aliasfreigaben. Keine Netzwerk-/Serial-/Geraeteimports.

```bash
python3 tools/audit-vdensho1-fan-source.py \
  /pfad/pairs.jsonl /pfad/summary.json \
  --output /neuer/pfad/fan-audit.json
```

Die [oeffentliche Ableitung](evidence/p300-fan-actual-source-screen-2026-10-08.json) enthaelt nur Hashes, per-Byte-Kennzahlen und exemplarische Vergleiche; **nicht** die kompletten privaten Rohzeitreihen.

## 4. Naechste technische Arbeit: eine **wirklich neue** Datenquelle

Ein weiterer gleicher VS1-MQTT-Vergleich loest nichts. Von P300 ist **Physical_READ aus Hauptregler-RAM 0x0400..0x53FF bereits lokal nachgewiesen**, aber der GFA-Istdrehzahlwert muss keineswegs dort abgelegt werden. Der Feuerungsautomat ist eine separate Funktionseinheit.

Die frueher ermittelten **eigenen Kommunikationspuffer** `0x196C..0x19AB` (Anfrage), `0x19AE..0x19ED` (Antwort) und `0x19EE..0x1A6D` (Ring) sind **keine Kandidaten**: P06-Zahlen koennten dort einfach von eigenen letzten Telegrammen stammen.

**Evidenz-Gate fuer die naechste Forschung:** erst per statischer Firmware-/Datenpfad-Analyse oder gepaarter vorhandener RAM-Dumps einen **konkreten, begruendeten Speicherbereich** finden, dann nur diesen mit expliziter read-only-Allowlist, festem Zeitbudget, einem einzigen seriellen Besitzer, vorab getesteter VS1-Rueckkehr und mehreren natuerlich unterschiedlichen P06-Referenzzustaenden validieren. Voraussetzung fuer einen Erfolg ist Frische auch **ohne** externe VS1-GFA-Reads. Keine blind breit ausgefuehrten RAM-Sweeps, keine RAM-Writes oder Heizungs-Codierungsaenderungen.

Die alternative Hybridsoftware bleibt moeglich fuer **seltene Diagnosereads**, behebt mit dem besten gemessenen VS1/P300-Rundweg (`4,61 s) aber das asynchrone `2,1-s-E7-RAM-Reload nicht. **VS1 bleibt Produktion; PR #46 bleibt Draft.**

*Urteil:* Der untersuchte Statusblock enthaelt keinen als unabhaengiges P06-Istsignal freigegebenen Kanal. Die RAM-Frage bleibt offen, ist aber jetzt auf echte Quellen- und Datenflussforschung eingegrenzt.
