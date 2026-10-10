# P300-GFA / VDensHO1: tiefer Quellen- und Internetabgleich (09.10.2026)

**Geltung: nur Aufgabe 1 (20C2, SW 0103, P80=20, echte P06-Istdrehzahl). PR #46 bleibt Draft, nicht mergen. Produktion /opt/optolink und laufender Fokuslogger unveraendert.** Saemtliche Arbeiten in diesem Bericht sind Quellenanalyse, keine neuen Hardwaretelegramme.

## Ergebnis

Es wurde weiterhin **kein unabhaengig belegter, auf dieser WB2A funktionierender nativer P300-Lesezugriff fuer GFA P06/0x4006** gefunden. Allerdings sind unter P300 **autonom aktualisierte GFA-nahe Statusdaten** vorhanden und mehrere noch nicht vollstaendig geklaerte virtuelle Diagnose-/Host-RPC-Quellen erkennbar. Ein fehlender Treffer ist kein allgemeiner Unmoeglichkeitsbeweis, zumal keine authentifizierte WB2A-Firmware/ROM-Dispatchanalyse vorhanden ist.

## 1. Ein zentraler Kodierkonflikt: Vitosoft-GFA_READ=201 vs. echtes P300-Funktionsbyte

**Tatsaechlich verifizierte Quellen:**

1. Das globale Vitosoft-v6-Enum nennt **GFA_READ=201=0xC9**. Ein **anderes Enum** fuer VS1-Wire nennt **GFA_Read=0x6B**.
2. Das archivierte **VS1Message.cs** dekodiert einen abstrakten GFA-Auftrag explizit in die VS1-Nachricht mit **0x6B + Adresse + Laenge** um; GetBytesToRead erwartet rohe Datenbytes. Dateiblob f0ad78872394bf139843df51fa79726519218021.
3. In **VSMSDK.SetCommand** wird bei **VSKOStart** zunaechst die bestehende Interface-/Queue-/Timer-/Device-Konfiguration gesichert und ausdruecklich **ChangeInterface(VS1)** aufgerufen. VSKOStop setzt die zuvor genutzte Schnittstelle zurueck. So ist der genutzte Vitosoft-v6-GFA-Sonderpfad technisch erklaert. Dies belegt keine globale Unmoeglichkeit anderer Protokollwege.
4. Die OpenV-Spezifikation **Protokoll 300** definiert im Funktionsbyte die unteren **fuenf Bits als Funktionsnummer** und die oberen **drei Bits als Sequenznummer**. Rechnerisch ist 0xC9 & 0x1F = 0x09 und 0xC9 >> 5 = 6. Bei diesem Frame-Modell ist 0xC9 kein belegter eigenstaendiger 201er-GFA-Befehl. Eigene Software und andere Drittprojekte, die das globale Enum einfach in den generischen P300-Serializer uebernehmen, haben damit noch keinen echten GFA-Wire-Pfad bewiesen. Herstellererweiterungen bleiben prinzipiell moeglich.
5. **Realer 20C2-Versuch**: P300-Rahmen mit 0xC9 / 0x4050 / 1 erzeugt **Controller-Fehlernachricht Identifier=3, Payload=05**. Das ist ein echter hardwareseitiger Reject **dieses Frames**, nicht der Beweis fuer alle moeglichen GFA-Gateways. Payload 05 ist nicht herstellerspezifisch dekodiert; weder nicht implementiert noch falscher Befehl darf als gesicherte Bedeutung angegeben werden.
6. Der Konflikt stand bereits in den Research-Dokumenten vom **08.10.2026**; diese Nachpruefung **bestaetigt und vertieft**, statt einen neuen testbaren GFA-FC zu behaupten. Insbesondere **kein C9->09 oder C9->6B und kein willkuerlicher Prefix-/Sequenztest**.

Original-/Archivquellen:
- https://github.com/openv/openv/wiki/Protokoll-300
- https://github.com/sarnau/InsideViessmannVitosoft/blob/main/VitosoftCommunication.md
- https://github.com/sarnau/InsideViessmannVitosoft/blob/main/Viessmann2MQTT.py
- https://github.com/f18m/viessmann-optolink2mqtt/blob/main/src/optolink2mqtt/optolinkvs2_protocol.py
- https://github.com/SaulGoodman1337/Viessmann-Vitosoft-300-SID1/blob/a94e367fb85909a8970b377f9f7395b55bf7e4f5/collector-output/20260925-vs1-process-read-trace/VS1Message.cs
- https://github.com/SaulGoodman1337/Viessmann-Vitosoft-300-SID1/blob/a94e367fb85909a8970b377f9f7395b55bf7e4f5/collector-output/20260925-vs1-process-read-trace/summary.json
- [Bisheriger Quellenabgleich](p300-switching-source-audit-2026-10-08.md)

## 2. Das vorhandene VDensHO1-Profil liefert GFA-Diagnoseobjekte, aber keinen aktuellen P06-Istwert als normalen Virtual_READ

Der bestehende Vitosoft-v6-**Profil-ID-60**-Join enthaelt **581 Events** und **362 befuellte Adressen**, davon **462 Virtual_READ**, **94 GFA_READ**, **22 Remote_Procedure_Call** sowie drei andere/leere. Die 94 GFA-Ereignisse betreffen **mehrere Brennervarianten** und sind nicht alle am lokalen P80=20 anwendbar.

| Datenquelle | Genannte Semantik | Bewertung fuer diese WB2A |
| --- | --- | --- |
| **FC01 0x55D3/11** | Feuerungszustand, Flags, Modulationsdiagnose; Byteindex 7 korreliert mit P87 | **Hardware bestaetigt**, P300-only autonom dynamisch ohne externe VS1-GFA-Abfragen; **kein P06-Istwert** |
| **Virtual 0x7650/1** | Event 8395 GFA_Kennung | Katalogspezifisch. Historisch 0x7650/6 = 20 02 06 15 01 FF, aber P300-Typread fuer dieses Geraet noch nicht eigenstaendig verifiziert; Typcache ersetzt keinen laufenden GFA-Read |
| **Virtual 0x7656** | GFA-Codierkartenrevision | Identitaets-/Revisionsdiagnose. Bytebreite muss aus Event belegt werden |
| **Virtual 0x5738** | K38 KonfiFehlerByteGFA | Konfigurationsfehler, kein aktueller Fan-Istwert |
| **Virtual 0x7590 und Folgeslots** | FehlerHisFA01..20 | Historisierte Brennerfehler, keine Tachoquelle; eine 0x7590/9-Abfrage wurde fuer *andere* P300-Geraete gezeigt, nicht fuer dieses 20C2 als lokale Slotgeometrie bewiesen |
| **Virtual 0x55DD** | GWG_Flamme1 | liegt bereits im erfolgreich gelesenen 0x55D3/11-Bereich |
| **Virtual 0xA305** | Modulationsgrad | Nicht P06, auch P09-Setpoint nicht automatisch identisch |

**Positiver Ausnahmebefund gegen zu weite Negativaussagen:** In zwei frueheren P300-only-Sessions veraenderte sich 55D3-Byte7 eigenstaendig, sogar nach 353 Sekunden ohne externe GFA-Reads. Ein vorheriger P87-Klammervergleich brachte 59 stabile Matches, aber auch einen unaufgeloesten Uebergang. Also **gewisse GFA-nahe Diagnose ist sehr wohl P300-zugaenglich**; ein Echtzeit-RAW-P06-Tacho jedoch nicht nachgewiesen.

Hinweise zur Quellenqualitaet:
- Der ESPHome VitoHome-VDensHO1-Katalog **filtert GFA_READ/RPC/KBUS** absichtlich aus. Das Fehlen von P06 dort ist deshalb kein selbstaendiger Nichtvorhandensbeweis. Andere Kataloge entstammen demselben Vitosoft-Export.
- ViessData21 nennt **20C2/SW 0100-0103 genau VDensHO1**, ab 0104 VDensHO1_4, und warnt, dass sogar aus Hersteller-XML abgeleitete Listen in anderen Familien unvollstaendig sein koennen.
- Die fremden Fan-Ist-Adressen **0x0B1E** (VBC550S) und **0x1A53** (V200WO1C) sind fuer die lokale Familie **keine** freigegebenen Lesepunkte.
- Keine unbestimmte 9-Byte-Laenge aus einem Fremdgeraet fuer GFA-Fehlerhistorie uebernehmen.

Quellen:
- [Bestehender 581-Event-Profiljoin](p300-gfa-source-candidates-2026-10-08.md)
- [Autonome P87-Dynamik](p300-p87-p300-only-result-2026-10-08.md)
- [807 volle P300-Statusreads](p300-full-status-byte-audit-2026-10-08.md)
- https://github.com/SoulSolistice/esphome_vitohome/blob/main/example/catalogs/vdensho1.yaml
- https://github.com/philippoo66/ViessData21/blob/master/DataPoints.txt
- https://github.com/philippoo66/ViessData21/blob/master/README.md

## 3. Die ungeklaerten abstrakten RPC- und Extended-Code-Wege

Vitosoft nennt neben GFA_READ auch **Remote_Procedure_Call=7, KMBUS_RAM_READ=65, KMBUS_EEPROM_READ=67, KBUS_GATEWAY_READ=101, PROZESS_READ=123, BE_READ=53** usw. Dies sind **globale Host-/Datenbank-Funktionsnamen**, **kein Nachweis**, dass die konkrete WB2A diese Bytes als autonome P300-Funktionscodes akzeptiert.

**Bereits abgeschlossene Fehlervermeidung:** Die private Vitosoft-v6-Serializerrekonstruktion zeigt, dass PrefixRead nur fuer bestimmte **RPC**-Kontexte in Nutzdaten gelangt, nicht automatisch bei normalem Non-RPC Virtual/KMBUS_READ. Ein geratenes Praefix oder ein generischer RPC an 0x4006 ist daher **kein** sinnvoller Hardwareversuch.

**Noch nicht ausgeschlossener reiner Offline-Pruefpunkt:** Die **22 tatsaechlich VDensHO1-zugeordneten RPC-Events** auf GFA-Bezug, konkrete Parameter, Anwendbarkeitsfilter, Read-only-Semantik und Host-Dispatch bewerten. Ein GFA-RPC-Gateway wurde bislang nicht nachgewiesen; die globale Existenz eines RPC-Enums genuegt nicht, um einen einzigen unbekannten Live-Aufruf zu legitimieren.

Quelle: https://github.com/SaulGoodman1337/Viessmann-Vitosoft-300-SID1/blob/main/collector-output/20260924-143439/prefixread-serializer-analysis-2026-09-25.md

## 4. Zusaetzlicher, aber nachrangiger externer Quellenvergleich: Vitosoft v8

Ein Communitybeitrag nennt **Vitosoft 300 SID1 8.0.6.4, Releasedatum 21.07.2025**. Unser privater Host-Archivnachweis stammt aus **v6**. Es gibt **keinen** belastbaren Hinweis, dass v8 eine native WB2A-GFA/P300-Funktion hinzugefuegt hat; Changelog-Eintraege nennen ueberwiegend Stammdaten-/WLAN-/Sicherheits-/Updatearbeiten.

Ein **rein offline** beschaffter legitimer neuerer Hoststand koennte bei Bedarf folgende Bereiche vergleichbar machen: VSMSDK.SetCommand, VSManager.ChangeInterface, VS1Message, LDAPMessage, RequestCreator, Sonderbehandlung von GFA_READ und VDensHO1-Profil 60. Keine Drittinstallateure auf der LXC ausfuehren und nicht waehrend des laufenden Loggers eine neue Vitosoft-Optolink-Verbindung starten.
Quelle: https://community.viessmann.de/t5/Sonstige-Produkte/Vitosoft-300-fuer-Vitocal-200S/m-p/395622

## 5. Priorisierte Evidenz-Gates nach Abschluss des laufenden Fokusloggers

1. **Fokuslogger abwarten**: Zwei reale unterschiedliche stabile positive P06-RPM-Niveaus und Unabhaengigkeit von P09/55D3/Optolink-Eigenpuffer pruefen. Kein Eingriff in aktive gepinnte Session.
2. **Ohne Hardware neue Profilextraktion:** Die 22 RPC-Events des **exakten** VDensHO1 v6-Zweigs gegen GFA und echte Hostserialisierung/Read-only-Parameter screenen. Kein ungezielter RPC-/Prefix-/C9-Test.
3. **Erhaltene Belege der GFA-nahen virtuellen Adressen** fuer 7650, 7656, 5738, 7590 ff. sichten. Sind echte P300-Rohantworten und sichere Laengen bisher nicht belegt, nur bei begruendetem Nutzen ein separates kurzes read-only Experiment **nach** dem Fokuslogger definieren. Eine Typkennung oder Fehlerhistorie kann die P06-Drehzahl nicht ersetzen.
4. **Bei negativem Istwert-Fokustest** die schon bewaehrten echten VS1-GFA-P06-Reads in eine **Single-Owner-Hybridarchitektur** fuer P300-Hauptbetrieb einordnen. Wechselkosten, P95/Maximum/Fehler, P06-Frische, MQTT, HA, Wartung, Schedules, Party, Serviceprogramme und Readbacks vor einer Produktionsfreigabe pruefen.
5. Vitosoft-v8-Codevergleich und physische HALL-/KM-Bus-Hypothesen bleiben optionale spaetere *Quellen*arbeitsrichtungen, nicht begruendete Soforttests. Aufgaben 2/3 weiterhin gesperrt.

**Keine Produktionsaenderung, kein Merge, keine neue Firmware-/SFR-/RAM-Write-, C9-, 09-, 6B- oder RPC-Liveprobe.**
