# WB2A 20C2/0103 – Firmware-Dump ohne eigenen 20-Bit-Optolink-Adressbefehl

**Datum:** 12.10.2026. **Priorität 1:** Echte M16C-Programm-ROM-Bytes der laufenden WB2A allein über den bestehenden Optolink-UART0-Pfad extrahieren. **Keine Voraussetzung**, dass ein 20-Bit-Adressoffset direkt auf dem Kabel übertragen wird. Bestehendes Repository `SaulGoodman1337/optolink`, dauerhafter Branch `optolink-research`. Ohne Einfluss auf `main`/laufende Heizung/experimentellen Draft-PR #52.

## 1. Strategieänderung: Content-Orakel statt direktem ROM-Reader

Der bisherige 8-/16-Bit-Adressaudit hat wichtige Negativbelege gebracht, ist aber **keine Vollständigkeitsprüfung aller Möglichkeiten zur Codegewinnung**. Eine vorhandene Controllerfunktion könnte ROM lesen, indizieren, vergleichen, einen CRC bilden oder interne Inhalte in einen erreichbaren Diagnosepuffer kopieren. Dafür muss **der Host die CPU-Adresse nicht explizit übermitteln**. Gesucht wird daher die Bedingung, unter der die Ausgabe der Funktion *invertierbare Informationen über einzelne ROM-Bytes* liefert.

Fünf getrennte Kandidaten, ohne einen davon bereits als Controllerfähigkeit zu behaupten:

1. **Variabel langer ROM-Checksum-/CRC-Orakel (neu modelliert):** Ein Dienst liefert nachweislich CRC16 über `ROM[START:START+N]`; `START` bleibt gleich, `N` ist in **Einzelschritten** steuerbar. Aus `CRC(N)` und `CRC(N+1)` kann unter bekanntem CRC-Algorithmus das angehängte Byte bestimmt werden, indem 256 mögliche Werte offline geprüft werden. Dies benötigt **kein** 20-Bit-Adressfeld im Transport. Ein **einmalig gemeldeter unveränderlicher Gesamt-ROM-CRC** reicht dagegen absolut nicht.
2. **ROM→RAM-Initialisierung oder Tabellen-Caching:** Viele Embedded-C-Runtimes initialisieren SRAM-Daten aus ROM und kopieren Tabellen bedarfsabhängig nach RAM. Ein read-only P300-`Physical_READ` könnte solche natürlich entstehenden Kopien als **Teilbytes** sichtbar machen. Ohne zugeordnete ROM-Quelle und reproduzierte Datenbewegung wären sie jedoch nicht als Firmwarebytes zu etikettieren.
3. **ROM-Tabellensuche als Byte-Orakel:** Eine legitime Diagnosefunktion könnte nach einem wählbaren Tabellenindex ein Byte, eine Kennlinie oder einen Deskriptor aus ROM zurückgeben. Den gültigen Indexbereich und die echte Datenherkunft müsste zuerst eine passive Reaktionsmessung oder die Host-Sequenz belegen; ein Host-XML-Datenpunkt allein reicht nicht.
4. **Bestehende Kommunikations-/Pufferkopie:** Der real nachgewiesene P300-`FC03`-Pfad kopiert Low-RAM in seinen `0x1933`-Scratch und danach `0x19B5`/UART0-TX. Eine unbekannte vorgelagerte *Anwendungsfunktion* könnte ROM-Daten hineinstellen, ohne dass `FC03` selbst hohe ROM-Adressen kennt. Dazu müssen *Quelle, Kopier-Auslöser und Ziel* im selben Funktionszusammenhang beobachtet werden.
5. **Stufiger Wartungs-/Update-/Debug-Pfad:** Statt eines statischen `ROM_READ`-Namens könnte eine alte, mehrstufige Service-/Loader-Sequenz eine ROM-Tabelle oder Memory-Self-Test-Ausgabe nutzen. 2010 wurde M30612MC/200KW2-ROM-Auslesen über Optolink als tatsächliches Ergebnis berichtet. Dessen originaler Transfermechanismus ist verloren und darf **nicht** als belegter WB2A-Request angenommen werden. Der Renesas-Hardware-Flashboot über UART1 nach Boot-Pin-Reset ist **keine** normale Optolink-UART0-Sequenz.

## 2. Durchgeführte Prüfungen an den vorhandenen Quellen

### A. Echter Offline-Mathematiktest: CRC kann Bytes preisgeben

Neues vollständig offline lauffähiges `tools/wb2a-rom-indirect-oracles.py` mit strikt hypothetischem **CRC16/CCITT-FALSE** und `tests/test_wb2a_rom_indirect_oracles.py`. Aus der echten CRC16-Vorschrift mit bekanntem Startzustand ergibt sich für jedes `N` eine eindeutig invertierbare 1-Byte-Fortschreibung:

```text
checksum_after(N+1) = CRC16_Update(checksum_after(N), secret_byte[N])
                                  |
                      256 Werte ausprobieren
                                  |
                         genau ein Byte
```

Die Tests haben **512 rein synthetische unbekannte Bytes** aus 512 zusammenhängenden Präfix-Checksummen zurückgerechnet; zusätzlich Positiv-/Negativtests für CRC-Polynom, Länge, ausgelassene Abfragen, manipulierte Prüfsumme, falsche Gerätekennung und unbelegte Live-Freigabe. Die demonstrierte Eigenschaft ist mathematisch gültig; dies **beweist nicht**, dass ein 20C2-ROM-CRC-Orakel existiert.

**Gerätegebundenes Negativ-Gate:** Die beiden echten VitoSoft-`Virtual_READ`-Namen `ChecksummeROMBerechnet~0x08F0` (2 B) und `NRF_ChecksummeROMLinker~0x08F4` (2 B) sind **anderen Reglerfamilien** zugeordnet, nicht den 581 original verlinkten `VDensHO1/20C2`-Hostevents. Der erneut SHA-attestierte Join am 12.10. enthält **null** passenden `20C2`-ROM-/CRC-/Prüfsummen-Datenpunkt mit variabler Präfixlänge. Nicht `0x08F0` am Kessel blind abfragen und aus einer konstanten Prüfsumme keine Codebytes behaupten. Ein alternatives undokumentiertes Orakel ist dadurch nicht ausgeschlossen.

### B. Echter Full-RAM-Befund – nicht als Firmware missverstehen

Der jetzt erneut komplett archiv- und manifestgeprüfte Satz von **79 × 20.480** Low-RAM-Bytes vom 09.10., SHA256 des Gesamtarchivs `94d5842b6dc5759ecb446a4c617b60b72873b639885d116032f783abdef8431c`, enthält über alle 79 Bilder **18.955 stabile Bytes (92,55%)**. Der längste stabile Block `0x2182..0x53FF`, **12.926 Bytes**, hat Entropie ca. **7,87 Bit/Byte**. Das war **bereits am 11.10.** durch `wb2a-vitotrol-class11-sram-firmware-ownership-gate-2026-10-11.md` belegt; keine Neuentdeckung behaupten. In einer unabhängigen späteren P300-Messung wechselte bei `0x2184` ein Byte `C8→CB`, während `0x3300/32` gleich blieb.

**Konsequenz:** Reines stabil/hoch-entropisch ist kein Herkunftsnachweis. Das RAM könnte initialisiert, ungenutzt, tabellengestützt, stackartig oder codehaltig sein. `0x1DE5` mit `0xEA2AB -> 0x3301 /29` und `0x1E6A` mit `0xFB27D -> 0x0705 /7` sind auffällige weit adressierte Deskriptor-Lookalikes; die bereits mehrfach geprüften Zielbytes sind aber unverändert, und ein natürlicher ROM→RAM-Transfer wurde **nicht** beobachtet. Keine Schreibversuche und keine Testbytes in diese Bereiche einbringen.

### C. Ein existierendes echtes Lesefenster, das wir anders behandeln müssen

Die WB2A hat bei P300 `Virtual_READ` innerhalb eines **gültigen** mehrbyteigen Datenpunktes Bytes geliefert, die als ungültige einzelne Startadresse `Error 03/01` zurückgaben: z. B. Start `0x088E/8` enthält an `0x088F` das echte Byte `26`, obwohl `0x088F/1` nicht direkt verfügbar ist. Der Befund wurde mit 65 echten P300-Reads am 12.10. dokumentiert: `wb2a-openv-2013-p300-startgate-virtual-overread-2026-10-12.md`. **Dies ist eine reale Filter-/Objektgrenzen-Asymmetrie**, kein bewiesener CPU-ROM-Leser. Daraus folgt eine neue Suchstrategie nach **gültigen, ROM-intern tabellierenden Ausgangsobjekten**, nicht nach bloß ungültigen hohen Startadressen oder ungebundenen Überlängen.

## 3. Entscheidungsorientierte Reihenfolge ohne Wiederholung

| Spur | Neuer oder vorhandener überprüfbarer Anker | Erkenntnis, die den nächsten Schritt erlaubt |
|---|---|---|
| **1. ROM-Inhalt als auslesbare Funktion** | VitoSoft-/Originaltraces auf variable Prüfsummen, Tabellenindices, Diagnoseblöcke und Lookup-Trigger auswerten; eigener CRC-Oracle-Test nun vorhanden | Ein realer rein lesender WB2A-Request muss mindestens zwei zusammenhängende, unterschiedlich parametrisierte ROM-abhängige Ausgaben liefern |
| **2. Natürliches RAM-Mirroring** | Die bereits archivierten 09.–12.10.-P300-Messungen inkl. nach Restart gemessener unabhängiger Fenster vergleichen | Eindeutige ROM→RAM-Provenienz mit Quellzuordnung, nicht bloß stabiler Inhalt |
| **3. vorhandener FC01-Überlesepfad** | Nur bereits gültige Startobjekte und tatsächlich bestätigte Response-Typen untersuchen | Eine Datenfunktion mit ROM-abhängigem, indizierbarem Inhalt, reproduzierbar ohne P300-Adressalias |
| **4. Programminterner Kopier-/Lookuppfad** | Far-Descriptor- und P300-Scratch-Zustand *passiv* bei natürlich eintretenden Ereignissen korrelieren | Eindeutiger Consumer/Trigger und reversibler, ungefährlicher rein lesender Aufruf |
| **5. Historische Werkzeug-/Update-Rekonstruktion** | Bewiesene Originalbefehlsbytes oder vollständiger Ablauf statt nur GWG-Funktionsname | An `20C2` eindeutig zuordenbarer Wartungslesedienst, bevor überhaupt live getestet wird |

**Stopp-Gate:** Keine neuen DMA0/DMA1-, UART1-, IRQ-, SFR-, Scheduler-Funktionszeiger- oder Bootmodus-Schreibtests an der aktiven Gasregelung. Diese könnten gerade den Optolink-Rückkanal zerstören und trotz Systemd-Host-Timer **nicht** selbständig rücksetzbar sein. C5/F9 traten historisch bereits auf und sind keine harmlosen Erfolgssignale. Nur nach echter nachweisbarer Leseprimitive und eigener Safety-/Recovery-Gegenprobe ein minimales Live-Abnahmefenster einplanen.

## 4. Reproduktion

```bash
cd /home/chatgpt-admin/optolink-wb2a-research-20261010
python3 tools/wb2a-rom-indirect-oracles.py --self-test \
  --out /tmp/wb2a-indirect-oracle-20261012.json
python3 -m unittest discover -s tests -p 'test_wb2a_rom_indirect_oracles.py' -v
python3 -m unittest discover -s tests -q
```

**Abgrenzung:** Der vom PC gelieferte synthetische CRC-Demo-Dump ist **keine WB2A-Firmware**. Reale WB2A-Programm-ROM-Bytes: **0**. Keine neuen Controller-Reads/Writes. Ein Erfolg wird erst nach zwei unabhängigen und quellenklaren aufeinanderfolgenden ROM-inhaltlichen Bytebeweisen, sinnvoller ROM-Verortung und anschließend vollständigem Hash-validiertem Dump anerkannt.
