# GWG, GFA, VS1 und P300 im produktiven Splitter

Diese Beschreibung gilt für die Viessmann Vitodens 200-W WB2A / VDensHO1 /
20C2. Maßgeblich sind die installierte Profilrevision und die unten genannten
Laufzeitmodule. **Der normale Betrieb bleibt VS1.** Ein zweiter
serieller Portbesitzer, automatisches P300-Umschalten und P300-Schreibbefehle
sind nicht Bestandteil der freigegebenen Produktionskonfiguration.

## Begriffe und Datenpfade

| Bereich | Produktives Verhalten | Grenze |
| --- | --- | --- |
| VS1-Splitter | Besitzt allein den Optolink-Port; bearbeitet MQTT-/TCP-Aufträge und den normalen Poll-Zyklus. | Zusatzdienste öffnen den Port nicht selbst. |
| VS1-GFA | Expliziter lesender `GFA_READ`-Aufruf (VS1-Funktion `0x6B`), unter anderem P80 `0x4050` und P06 `0x4006`. | Kein stiller Protokollwechsel; `FF` wird nicht als gültiger Istwert behandelt. |
| GWG-Metadaten | Anlagen-/Codierinformationen aus dem bestehenden Home-Assistant-Profil; `i2c_eeprom_gwg_flag` an `0x778B` wird als Rohwert bereitgestellt. | Ein angezeigter GWG-Wert ist weder eine Freigabe zum EEPROM-Schreiben noch ein Fehlerhistorienrecord. |
| P300 | Nur ein ausdrücklich angefordertes, zeitlich begrenztes Diagnosefenster am **gleichen** seriellen Hauptprozess. | FC01-Gerätekennung `20C2`; FC03-Leseblöcke `0x0F20/32` und `0x1C60/32`; keine freien Adressen und keine Controller-Writes. |

Die im Profil erläuterten GWG30-/GWG32-/GWG34-Felder enthalten
anlagenspezifische Zuordnungen (beispielsweise Begrenzungen der Heiz- und
Warmwasserleistung sowie die Umschaltventilvariante). Das sind
Konfigurationsbeobachtungen; sie dürfen nicht zu zusätzlichen
Schreibbefehlen oder unbestätigten Funktionsbehauptungen führen.
Die technische Quelle ist
`config/optolink-splitter/vdensho1-20c2-wb2a-homeassistant.py`.

## Fehlerbehandlung und Rückkehr

Der GFA-Pfad besitzt eine begrenzte Wiederholung bei einem rohen
`0xFF`-Wert und markiert weiterhin ungültige Antworten als nicht
verwendbar. Bei P300 ist die Vorprüfung strenger: Die
Writer-/Readback-Sperre, die normale MQTT-/TCP-Auftragswarteschlange,
die serielle Besitzeridentität und frische **originale** VS1-GFA-Werte
müssen zusammenpassen. P80 muss `20` liefern; bei P06 ist `00`
ein zulässiger Wert, `FF` nicht. Abbruch, abgelaufene Frist,
fehlende Originalprovenienz oder misslungene Rückkehr ergeben
**keinen** bestätigten Diagnoseerfolg.

Erst nach der unabhängig bestätigten Wiederherstellung der
VS1-Dienste und einer gültigen GFA-Rücklesung darf ein P300-Ergebnis
als vollständig gelten (`verified_vs1=true`). Die P300-Rohdaten
tragen ausdrücklich die Herkunft
`P300_RAW_DIAGNOSTIC_NOT_ACTUAL_RPM`: Sie sind **kein**
verifizierter Gebläsedrehzahl-Istwert.

Der produktive `update`-Pfad installiert die kontrollierte
Hybridbibliothek lediglich. Er aktiviert weder die periodische
P300-Automatik noch den nur während einer ausdrücklich
beaufsichtigten Shadow-Sitzung vorhandenen Root-Diagnosesocket.
Ein Update kann normale Dienste neu starten und ist daher kein
nebenwirkungsfreier Statuscheck.

## Controller-Fehlerzeit versus Host-Zeit

Die WB2A-System-Fehlerhistorie und Optolink-Kommunikationsfehler
sind getrennt auszuwerten. Ein eindeutiger Systemhistorieneintrag
besteht aus **neun Bytes**, einschließlich Fehlercode und BCD-kodierter
Controllerzeit. Der Zeitstempel des späteren `journalctl`-Eintrags
ist lediglich die Lese-/Protokollierungszeit. Wiederholt gelesene
identische Records dürfen nicht als neue Störungen gezählt werden.
GFA-/GWG-Abfragefehler und Kommunikations-Retcodes sind nicht
automatisch WB2A-Systemfehler wie C5 oder F9.

## Quellen und Bedienung

- [Betriebsanleitung für den VS1/P300-Protokollwechsel](hybrid-protokollwechsel.md)
- [Lokale Root-P300-Diagnose](p300-root-lese-api.md)
- [Betrieb und Aktualisierung](operations.md)
- [Systemarchitektur](architecture.md)
- `tools/optolink-apply-vs1-gfa-readonly-patch.py` (VS1-GFA-Integration)
- `tools/handover_acceleration/` (Admission, Writer-Sperren, Lesebatcher, Recovery)
- `tools/optolink-hybrid-modules.txt` (ausschließlich freigegebene Produktionsmodule)

Forschungsprotokolle, Rohmitschnitte, RAM-Korrelationen und
Firmwarehypothesen bleiben im getrennten Zweig `optolink-research`.