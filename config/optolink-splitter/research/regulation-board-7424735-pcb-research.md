# PCB research: Viessmann 7424735 / VBC 130 comparison board

Status: **active preliminary PCB research; local-board identity not yet confirmed**

Last updated: **2026-09-25**

This document records the board-level research triggered by two third-party online-reference photos supplied by the user on 2026-09-24. The photographed board looks similar to the user's installed regulation electronics, but **the supplied photos are not photos of the installed local boiler board**. No conclusion below may therefore be transferred to the local WB2A until its labels and IC markings have been photographed directly.

The current local appliance baseline elsewhere in this repository remains **Vitodens 200-W WB2A / VDensHO1 / identification 20C2**. That distinction is important because public Viessmann evidence points to a GG1 control for WB2A, while the online comparison board 7424735 is associated with the later VBC 130-A03.100 / 7424743 family.

## Executive findings

1. Two independent online board samples carry the PCB/assembly number **7424735** and are visually the same board layout.
2. A current eBay listing explicitly sells **7424735** as the PCB from control **7424743**. Independent WB2B field documentation identifies **7424743** as **VBC 130-A03.100**.
3. The user-supplied online photo set appears to show the main MCU marking **M16C / M30624FGPFP**. This is a Renesas/Mitsubishi **M16C/62P** 16-bit flash MCU in a 100-pin QFP.
4. Renesas specifies this MCU with **256 KiB program flash, 4 KiB data flash and 20 KiB RAM**. The main executable firmware can therefore plausibly reside inside the MCU; a separate external program ROM is not required by the architecture.
5. The unpopulated footprint **X15 has three pads**, not four. It is close to the MCU and is worth tracing, but a three-pad X15 cannot by itself be the complete Renesas E8/E8a interface, which uses substantially more MCU control/signalling pins.
6. M16C/62P supports in-system serial flash programming. Renesas documents both synchronous UART1-based programming/debug signalling and a flash-ID-code mechanism that can prevent unauthorized readout.
7. The local appliance identity creates a critical compatibility warning: Viessmann sources for WB2A equipment identify **GG1, spare part 7825241** as the appropriate regulation. Therefore **7424735/VBC130 must be treated only as a comparison-board hypothesis until the actual local board is photographed**.
8. The online 7424735 images are still highly valuable: they expose PCB routing, the reverse side, connector labels, service/test footprints and a likely MCU family before the local board is opened.

## Evidence classes used here

- **hardware_observation**: directly visible in a supplied or public high-resolution board photograph.
- **vendor_documentation**: Renesas or Viessmann documentation / Viessmann staff response.
- **marketplace_correlation**: seller listing or spare-parts catalogue; useful for part-number linkage, not sufficient alone for electrical equivalence.
- **hypothesis**: technically plausible interpretation that still requires continuity measurement, a sharper local photo or another independent source.

## Online-reference board set A: user-supplied photos

Source: third-party online images supplied in the project chat on 2026-09-24. They are retained only as conversation evidence and are **not mirrored into this public repository**, because copyright/provenance is not established.

Visible identifiers:

- sticker: **40597 / 7424735**
- barcode string: **7424735926155101**
- PCB manufacturer marking: **VIESSMANN**
- main screw terminal: **X3**
- X3 silk groups visible as **[1] [2] [145]**
- separate small connector marking **[145]**
- edge/test connectors **X10** and **X15**
- X15: **three unpopulated through-hole pads** plus pin-1 triangle
- large main QFP MCU marking appears to read:
  - **M16C**
  - **M30624FGPFP**
  - remaining lot/date lines are not yet needed for identification
- relays in the power section are visibly from the Schrack V23061 family; exact suffix should be transcribed again from a local macro photo before it is used as a design fact.

Evidence level: **hardware_observation**.

### Correction to the first visual assessment

An earlier conversational assessment described X15 as four pads. The enhanced crop clearly shows **three**. This document supersedes that earlier count.

## Online-reference board set B: independently found 7424735 listing

Current public listing:

- https://www.ebay.de/itm/127843796384
- title: `1x Viessmann 7424735, Platine, Vitodens 200, Leiterplatte Steuerplatine 7424743`
- seller-stated MPN/model: **7424735**
- 16 photos include useful front, edge and reverse-side views.

Visible in the listing photos:

- board sticker: **40494 / 7424735**
- board barcode: **7424735910112103**
- same overall component placement as reference set A
- same X3/X4/X10 region
- X3 silk visibly groups **[1] [2] [145]**
- separate **145** connector is present
- PCB text near X10 includes **HND 43/09**
- a full reverse-side photo is available and should later be used for trace/continuity planning
- the vertical daughterboard is also shown from the rear; a visible barcode includes **84346912**, but its function has not been identified.

The repeated 7424735 number on boards with different serial/barcode strings is consistent with **7424735 being a board/assembly part identifier rather than an individual serial number**.

Evidence level: **hardware_observation + marketplace_correlation**.

Do not over-interpret `HND 43/09`. It looks compatible with a production/revision/date-style code, but no source has yet established its exact semantics.

## Part-number and control-family correlation

### 7424735 -> 7424743

The eBay listing above explicitly describes PCB **7424735** as the board from control **7424743**.

A separate marketplace listing names:

- **7424743**
- **VBC 130-A03.100**

https://www.ebay.de/itm/277505858079

More importantly, a Viessmann Community case for a real Vitodens 200-W WB2B records:

- appliance: **WB2B 7194474**
- regulation: **VBC 130-A03.100 7424743**

https://origin-viessmann.lithium.com/t5/Gas/Neue-Umwaelzpumpe-fuer-WB2B-Stromstecker-passt-nicht/td-p/256386

Evidence level:
- 7424735 -> 7424743: **marketplace_correlation**
- 7424743 -> VBC 130-A03.100 on WB2B: **vendor-hosted field documentation / user equipment identification**

### VBC 130 replacement lineage

Viessmann replacement documentation for **7834245 / VBC 130-A04.100** states that it replaces VBC 130-A03 variants including A03.100/.200/.300/.400. This places the A03 family in a known VBC-130 hardware lineage, but it does **not** prove that every A03 board uses exactly the same PCB or MCU.

Reference:
https://community.viessmann.de/viessmann/attachments/viessmann/customers-gas/132264/1/5712942VMA00004_1%20%281%29.pdf

Evidence level: **vendor_documentation**.

## Critical WB2A boundary: do not identify the local board from appearance alone

The current project baseline identifies the local appliance as **WB2A**. Multiple independent sources point to **GG1 / 7825241** for WB2A rather than VBC 130-A03.100:

- Viessmann Community, WB2A 7176543: Viessmann staff states that control **7825241** must be used:
  https://community.viessmann.de/t5/Gas/Vismann-Vitodens-200-WB2A-Sporadisch-Luefter-laeuft-hoch-und/td-p/145871
- Current spare-parts catalogue: **7825241 GG1** is listed for WB2A/WB3A/WS3A and as successor to earlier GG1 part numbers:
  https://www.loebbeshop.de/7825241-viessmann-regelung-gg1-fuer-wb2a-wb3a-ws3a/
- Independent current parts catalogue also lists WB2A device numbers such as 7176540/41/43 and 7186846 for 7825241:
  https://www.uttscheid.de/Viessmann-Regelung-GG1-fuer-Vitodens-200-WB2A-300-WB3A-333-WS3A-7825241/VI7825241

A GG1 7825241 board image is visually related in general architecture but is **not identical enough to assume that the 7424735 VBC130 board is the installed WB2A board**.

### Stronger GG1 comparison anchor: 7184367 / 405334100

A Viessmann Community case for a **GG1** regulation gives a concrete PCB marking from the installed board:

- regulation family discussed: **GG1**
- older regulation part: **7823830**
- PCB marking reported directly from the board: **7184367 405334100**
- Viessmann staff confirms **7823830** is usable for that application and separately states that **7825241** is the successor model; in the same thread, Viessmann states that no software changes were made in the successor.

Primary public evidence:

- https://community.viessmann.de/t5/Gas/Regelung-GG1-unterschiedliche-Bestellnummern/m-p/13079
- https://community.viessmann.de/t5/Gas/Regelung-GG1-unterschiedliche-Bestellnummern/m-p/12157

An active marketplace listing also identifies a complete **GG1 / 7184367** regulation:

- https://www.ebay.de/itm/156269696802

This is a materially better comparison anchor for the local **WB2A / VDensHO1 / 20C2** than the 7424735/VBC130 board, because it belongs to the GG1 lineage that is independently linked to WB2A.

However, it is still **not a local-board identity proof**:

- the reported 7184367 board came from another appliance/control;
- successor compatibility does not prove unchanged PCB layout or MCU;
- the exact local board number and MCU still require direct local photographs.

### Working rule

Until the actual installed board is photographed:

- use 7424735 only as a **comparison platform**;
- do not label the local controller as VBC 130-A03.100;
- do not transfer X15 pinout, MCU type, firmware map or replacement compatibility to the local WB2A;
- prioritize local label/MCU capture before any electrical probing.

This identity check is now the first gate of the PCB workstream.

## Exact WB2A/GG1 board trail: 7187393 and 84346904

Online evidence now gives a much stronger board trail for the actual WB2A/GG1 generation than the earlier VBC130 comparison board.

### Direct WB2A -> GG1 -> 7187393 correlation

A Viessmann Community case identifies one appliance explicitly as:

- **Vitodens 200 WB2A**
- appliance production family: **7176543**
- Kesselkreisregelung: **GG1 7187362**
- main PCB: **7187393**

Source:
https://community.viessmann.de/t5/Gas/Vitodens-200-WB2A-Startet-nicht-mehr/m-p/214246

This is currently the strongest public direct correlation between an actual WB2A and a specific GG1 PCB number.

A separate Viessmann Community case identifies a 2004 WB2A with appliance number `7176543...` and a GG1 production number `7185329 405099105`. This supports the important distinction that the visible 718xxxx/719xxxx labels on complete controls are production/component numbers and need not equal the PCB number.

Source:
https://community.viessmann.de/t5/Gas/Vitodens-200-WB2A-Ersatz-Platine-lieferbar/td-p/209270

Viessmann staff explicitly states in another GG1 compatibility thread that numbers such as `7187362` and `7196527` are **Produktionsnummern einzelner Komponenten** and identifies `7825241` as the required GG1 order/material number for WB2A `7186846`.

Source:
https://origin-viessmann.lithium.com/t5/Gas/GG1-Kompatibilitaet/td-p/154525

Therefore keep these identifier classes separate:

- `7176543`, `7186846`, etc.: appliance production families;
- `7187362`, `7185329`, `7196527`, etc.: regulation/component production numbers;
- `7187393`: observed PCB/board number;
- `7825241`: replacement/order material number for the GG1 regulation family.

### 7187393 is shared within the GG1-era family

A separate Viessmann Community case on a **Vitodens 300 WB3A 7176537** explicitly reports:

`Leiterplatte: 7187393 522521106`

Source:
https://community.viessmann.de/t5/Gas/Vitodens-300-WB3A-71-76-537-Fehler-F4/td-p/247256

Thus `7187393` is not a WB2A-exclusive application board. It appears in at least WB2A and WB3A GG1-era equipment. This makes the board number useful for PCB research but insufficient by itself to identify appliance-specific firmware/coding.

### Vertical daughterboard 84346904

A second WB2A repair case reports replacing `PCB 84346904` and explicitly describes it as `das stehende PCB auf der Hauptplatine`.

Source:
https://community.viessmann.de/t5/Gas/Vitodens-200-WB2A-Stoerung-F0-Zuendtrafo-liegt-ununterbrochen-an/td-p/219269

Multiple independent marketplace listings pair **7187393** with **84346904**, including complete controls with 10-15 photographs:

- https://www.ebay.de/itm/127115328332
- https://www.ebay.de/itm/127843820272
- https://www.ebay.de/itm/127843820279

This makes the physical pairing **7187393 main PCB + 84346904 vertical PCB** high-confidence at the marketplace/photo level.

### Service-manual architecture creates a new identification target

The WB2A service manual `5681 543` does not expose board part numbers, but it separates the control electronics functionally into:

- `A1` = **Grundleiterplatte**
- `A2` = **Schaltnetzteil**
- `A3` = **Optolink**
- `A4` = **Feuerungsautomat**
- `A5` = **Bedienteil**
- `A6` = **Codierstecker**
- `A7` = **Anschlussadapter**
- `A8` = **Kommunikationsmodul LON**

It also labels connector/function `145` as **KM-BUS** and the internal pump separately.

Primary WB2A service manual:
https://community.viessmann.de/viessmann/attachments/viessmann/customers-gas/126396/1/vitodens_200_serviceanleitung.pdf

This separation is important for the firmware workstream. The currently observed `84346904` vertical PCB **must not yet be equated with A4/Feuerungsautomat**, but A4 is now an explicit physical-identification target when the local board is photographed.

Required local evidence:

1. determine whether `7187393` is printed/stickered on the local A1/main PCB;
2. check whether the vertical board is `84346904`;
3. trace/identify which physical assembly corresponds to service-manual `A4 Feuerungsautomat`;
4. identify the MCU and memory on A1 and A4 separately;
5. keep the coding-plug A6 EEPROM domain separate from both.

### C105 as a board-location landmark

The same direct WB2A/7187393 repair thread reports successful replacement of `C105`, where the failed part measured about 38 nF and the expected replacement was 220 nF X2/305 VAC. This is useful mainly as a **visual board landmark** for matching online photos to the 7187393 layout, not as a firmware clue.

Do not generalize C105 repair advice to other control generations.

### Current evidence boundary

Despite the stronger PCB identity trail, no reliable public source found so far identifies:

- the exact MCU on `7187393`;
- the exact MCU on `84346904`;
- a schematic for either PCB;
- a debug/programming connector or pinout;
- firmware dump files;
- a proven relation between `84346904` and service-manual `A4 Feuerungsautomat`.

Those remain photographic/component-identification tasks rather than facts.

## Exact 7187393 high-resolution photo evidence - 2026-09-25

Public source material now includes two independent photo sets of **exact PCB 7187393**, not just visually similar controls.

### Michl product set

Product page:
https://www.michlsonlineshop.at/produkt/viessmann-7187393-leiterplatte/

The page exposes static high-resolution front/detail/rear images. Relevant source files include:

- `20240515_142244-scaled.jpg` - full component side;
- `20240515_142302-scaled.jpg` - power/board-number detail;
- `20240515_142306-scaled.jpg` - X3 / 145 / barcode detail;
- `20240515_142325-scaled.jpg` - solder side / trace view.

Direct visual observations from that exact board:

- Viessmann sticker: **7187393**;
- barcode/serial visible on the photographed sample: **7187393513594102**;
- X3 silk grouping: **[1] [2] [145]**;
- a separate adjacent connector is also silk-labelled **[145]**;
- **X10** is a small black service/test header near the lower-right edge;
- an unpopulated **J1** footprint immediately beside the main logic section has **three through-hole pads** and a pin-1 triangle;
- the main logic device is a large rectangular QFP with approximately **100 leads**;
- a vertical daughterboard is fitted along the upper edge;
- the exposed daughterboard face carries at least two smaller QFP/TQFP-class ICs plus discrete support circuitry;
- a full solder-side photograph is available and preserves enough routing detail for later passive continuity planning.

The main MCU laser marking is **not legible** in this image set. Multiple crops and contrast transformations were checked; the source pixels do not support a reliable part-number transcription. No MCU identity is promoted from these photos.

### Independent Kleinanzeigen 7187393 set

Archived/deleted listing:
https://www.kleinanzeigen.de/s-anzeige/viessman-steuerung-platine-7187393/3388584017-84-16390

The archived page still exposes four CDN images. The largest tested CDN rendering is 1200 x 1600 (`rule=$_57.JPG`).

Direct visual observations:

- Viessmann board sticker again reads **7187393**;
- second photographed board barcode/serial: **7187393513812107**;
- the same X3 `[1] [2] [145]`, separate `[145]`, X10, J1, large QFP and vertical-daughterboard topology is visible;
- this provides an independent second physical sample of the same layout;
- even in the 1600-pixel version the main-QFP marking remains below reliable transcription quality.

CDN image identifiers retained as source references only; third-party images are not copied into this repository:

- `1ee1bfed-256b-4229-97c7-f4a3acceb146`
- `385fcc69-292b-42d7-8a6e-276a7c0eaf19`
- `a4a18677-b897-4865-ab4e-3fd80add6ff7`
- `e8f3c5fb-5159-4b46-bc65-2038ed39af55`

### J1 is now the highest-value exact-board passive trace target

The earlier 7424735/VBC130 comparison board had a three-pad X15 candidate. Exact 7187393 evidence instead exposes a **three-pad J1** next to the main MCU.

This is an important correction of scope:

- do **not** transfer the VBC130 `X15` label or presumed routing to GG1/7187393;
- on the actual GG1 candidate, trace **J1 -> passives -> MCU pins / ground / supply** first;
- a three-pad footprint is compatible with a UART/test interface hypothesis, but the photos alone do not establish signal function;
- no voltage should be applied to J1 before local continuity and rail mapping.

### Related GG1-family comparison: PCB 7186950

A high-resolution public photograph of **7186950** (GG1-era board) is available here:
https://www.mig-welding.co.uk/forum/attachments/dscf2936-jpg.330026/

Visual comparison with exact 7187393 shows a strongly shared architecture:

- same large ~100-pin main-QFP position and surrounding routing pattern;
- same three-pad **J1** position;
- same X3 `[1] [2] [145]` and separate `[145]` region;
- same X10 location;
- same vertical-daughterboard concept;
- closely matching power/relay layout.

However, the assemblies are not identical. One visible discriminator is the silkscreened/circled Viessmann board variant marker: the photographed 7187393 sample shows **circled 1**, while the 7186950 comparison photograph shows **circled 4**. Therefore 7186950 is useful for family-level routing/component comparison only.

The 7186950 main-QFP marking is also too faint for a defensible transcription. Image enhancement suggests there is laser text, but it is not readable enough to identify a device.

### Follow-up image sweep: assembly variants, 7142213-4 and PCB-material marking

A second deep image/search pass on 2026-09-25 reloaded the original Michl full-resolution files and compared additional GG1/GG1E-family boards.

#### Additional independent 7187393 assembly evidence

A further sold eBay sample is explicitly labelled:

- main PCB/reference: `7187393`;
- full visible listing identifier: `7187393622882206`;
- 8-image listing: https://www.ebay.com/itm/296194458383

This is a third independent 7187393 production sample in addition to the Michl `7187393513594102` and Kleinanzeigen `7187393513812107` boards.

A current marketplace listing also pairs:

- complete regulation/fabrication number: **GG1E 7187364**;
- PCB/manufacturer number: **7187393**.

Source:
https://www.ebay.de/itm/167709425528

This must be interpreted carefully. Direct WB2A field evidence elsewhere in this document pairs **GG1 7187362** with the same `7187393` PCB number, while Viessmann itself states that `7187364` and `7187362` are *Fertigungsnummern* and that the queried GG1E/GG1 controls are not directly interchangeable.

Viessmann source:
https://community.viessmann.de/t5/Gas/Kompatibilitaet-Steuerung-7187364-GG1E-und-7187362-GG1/td-p/35751

Therefore `7187393` is increasingly likely to represent a reused main-PCB hardware platform across more than one complete-control configuration. **This does not imply control interchangeability.** Coding plug, daughterboard, component population and/or firmware/configuration can still distinguish the complete regulation.

#### 7186950 / 7142213-4 reference and the circled variant marker

Multiple independent listings explicitly pair the closely related `7186950` board with **`7142213-4`**, including:

- https://www.ebay.de/itm/117121874610
- https://www.ebay.de/itm/157843170299
- https://climatizacioniberica.es/recambio/placa-electronica-viessmann-vitodens-300-7186950/

The Spanish spare-parts source describes `7186950` as replacing/reference-equivalent to `7142213-4`.

The high-resolution 7186950 photograph independently shows the already recorded **circled `4`** Viessmann variant marker, whereas exact 7187393 shows **circled `1`**.

This creates a useful but still unproven hypothesis:

- the circled `1` / `4` marks may encode a hardware/layout/assembly variant related to the `7142213-x` numbering;
- public searches did **not** find a defensible `7142213-1 = 7187393` source;
- therefore do not promote `7142213-1` as an identifier; instead photograph any comparable local silk/variant marking directly.

#### Correction: `E200175(2) WM328ML ... 94V-0` is not a Viessmann board identity

Both exact 7187393 and the related 7186950 board carry a lower-edge PCB-material marking of the form:

`E200175(2) WM328ML ... 94V-0`

A wider search resolves this marking class:

- independent safety/certification documentation names **World Mastery Technology Ltd.** as PCB-material manufacturer;
- `WM328DS-2` is listed as an FR-4 PCB-material/type designation;
- UL file **E200175** belongs to that PCB-material manufacturer;
- unrelated industrial PCBs also carry `E200175` / `WM328DS` or `WM328ML` markings.

References:

- https://products.electrovoice.com/download/977444
- https://axxacnc.com/pcb-e200175-2-wm328ds-94v-0-new/
- https://www.lektronix.de/equipment/cse-e2001752/162348

Consequences:

- **do not use `E200175` as a Viessmann board number**;
- **do not use `WM328ML` as a firmware/controller-family identifier**;
- it is useful only as evidence about PCB fabrication/material provenance.

#### Additional visual family comparator: Viessmann 7189106

A current Spanish parts listing exposes a direct image of another Viessmann boiler PCB stickered `7189106`:

https://www.openclima.com/products/13264/placa-electronica-caldera-viessmann-7189106

Direct image:
https://openclima-static.s3.eu-west-1.amazonaws.com/images/2025/products/13264/placa-electronica-caldera-viessmann-7189106-principal.webp

Visual comparison shows the same broad GG1-era architecture: vertical daughterboard, large main QFP, J1/X10-like service/test footprint placement, X3/[145] region, right-edge connector bank and very similar mains/relay topology. Its exact appliance/control-family mapping has not been established, so it is retained only as a **visual family comparator**, not as local-board evidence.

The main QFP marking in this image is also not readable enough to identify the MCU.

#### Revalidated Kleinanzeigen pixel evidence and coding-plug clue

The archived exact-7187393 Kleinanzeigen page was fetched again on 2026-09-25 and all four still-accessible CDN images were inspected directly at the largest available `$_57.JPG` rendering rather than relying on search thumbnails.

Directly revalidated observations:

- full-board image shows exact main PCB sticker **7187393**, the vertical daughterboard, the large main QFP, three-pad **J1**, black **2 x 3 X10**, X3/[145] and the separate [145] connector in one frame;
- X3 close-up sharply confirms `X3 [1] [2] [145]`, the separate `[145]` connector and barcode **7187393513812107**;
- the close-up around the 7187393 sticker/C105/C106 region shows multiple optocoupler-class 4-pin packages; two top markings are visually consistent with the **SFH618A-1 family**, but the suffix/date lines are not promoted as exact part identification from this photograph;
- the full-board photograph also contains a removed coding plug next to the PCB carrying visible side/sticker number **7177432**;
- the fourth image is an appliance/HMI photograph and adds no PCB-level component evidence.

CDN sources:

- `https://img.kleinanzeigen.de/api/v1/prod-ads/images/a4/a4a18677-b897-4865-ab4e-3fd80add6ff7?rule=$_57.JPG`
- `https://img.kleinanzeigen.de/api/v1/prod-ads/images/e8/e8f3c5fb-5159-4b46-bc65-2038ed39af55?rule=$_57.JPG`
- `https://img.kleinanzeigen.de/api/v1/prod-ads/images/38/385fcc69-292b-42d7-8a6e-276a7c0eaf19?rule=$_57.JPG`
- `https://img.kleinanzeigen.de/api/v1/prod-ads/images/1e/1ee1bfed-256b-4229-97c7-f4a3acceb146?rule=$_57.JPG`

#### Important coding-plug numbering implication

Public WB2A evidence shows that **7177432 is not sufficient to identify the programmed coding-plug data set**.

In a WB2A exchange case, two plugs both carry `7177432` but have different further/article identifiers and different appliance semantics:

- `7177432 / 7824047`: reported for a WB2A with storage cylinder/Vitocell 100;
- `7177432 / 7823552`: reported from another WB2A configuration with plate heat exchanger.

Source:
https://community.viessmann.de/t5/Gas/ich-habe-eine-Viessmann-vitodens-200-wb2a-fehler-b7-neuer/td-p/89744

A second direct WB2A case identifies appliance `7186846`, GG1 `7187362`, and coding plug **7824047**, strengthening the relevance of that programmed identifier for this WB2A branch:

https://community.viessmann.de/t5/Gas/Vitodens-200-WB2A-Stoerung-F0-Zuendtrafo-liegt-ununterbrochen-an/td-p/219269

Other Viessmann generations likewise show `7177432` beside different programmed/article numbers, so treat `7177432` as a carrier/base-part marking unless a device-specific article number and/or EEPROM contents establish the data set.

Research consequence for the planned physical dumps:

- photograph **all labels on every coding plug, including side labels only visible when removed**;
- retain plug identity together with `f01/ST` and `f02/Microchip` side identity and every dump hash;
- do not group two plugs as equivalent merely because both say `7177432`;
- use the binary content plus known software anchors (`20 15 02 01`, etc.) for correlation.

### Updated image-search boundary

After the expanded search, no public image yet supports a defensible MCU part-number transcription for exact `7187393`, `84346904`, `7186950` or the additional `7189106` comparator. The MCU question remains gated on a perpendicular local macro photograph.

### Optical routing assessment: J1 and X10

The exact `7187393` rear-side photograph from the Michl source was horizontally mirrored only for front/rear registration and compared against the component-side image.

#### J1

- exact board footprint: **3 through-hole pads**, silk `J1`, directly beside the main logic region;
- component side shows a small local SMD network immediately adjacent to J1;
- rear-side routing is visible only partially and crosses vias/layer changes;
- the photographs do **not** prove that any J1 pad connects directly to a main-MCU pin;
- therefore `J1 = UART/debug/programmer` remains a hypothesis, not a finding.

#### X10

- exact board connector: black **2 x 3 through-hole header**, silk `X10`;
- solder-side image shows a nearby parallel multi-trace bundle running toward the logic region;
- because of vias, layer changes and overlapping routing, the photographs do **not** support a defensible per-pin destination map;
- X10 is therefore a high-value passive trace/debug candidate, but no programming/debug protocol is assigned to it yet.

#### Safe local continuity sequence

With the board fully de-energized and isolated:

1. identify which J1/X10 pins have continuity to a known logic ground;
2. identify likely supply/reference pins only by passive continuity/resistance to known decoupling/rail points; **do not inject voltage**;
3. trace remaining pins to nearby passives and then to exact main-QFP pins;
4. photograph/record every measured endpoint and resistance/continuity result;
5. only after the main MCU is identified, compare those QFP pins with the vendor datasheet's UART/boot/reset/debug functions;
6. do not attach a programmer/debugger until voltage domains, reset/mode behavior and readout-protection behavior are known.

Current conclusion: **J1 and X10 are both worth mapping. X10 may be at least as interesting as J1, but online imagery alone cannot rank them as a debug/programming port.**

### MCU inference boundary

The package and pin count on exact 7187393 are visually compatible with 100-QFP microcontrollers such as the Renesas/Mitsubishi M16C parts seen on other Viessmann boards, including the previously researched M30624FGPFP comparison board. Renesas specifies M30624FGPFP as a 100-QFP, 20 x 14 mm device.

That is **package compatibility only**. Current evidence does not prove that 7187393 uses M30624FGPFP, another M16C variant, or another 100-pin MCU family.

A separate Viessmann Community report on a different A1 regulation board explicitly mentions an `M16C..` microcontroller, which shows that M16C use exists in the broader Viessmann regulation ecosystem, but it is not an identification source for 7187393.

### WB2A / LGM29 boundary

A Viessmann Community response for appliance **7176543** explicitly corrects a common confusion:

> the appliance is not WB2 with LGM29; it is **WB2A with GG1 regulation**, with a 230-V ignition-transformer output.

Source:
https://community.viessmann.de/t5/Gas/Vitodens-200-7176543/td-p/250327

Therefore:

- do not import LGM29 PCB/firmware architecture from older WB2 into the local WB2A research;
- `LGM29.22B2000` marketplace/repair results are legacy-WB evidence, not local WB2A/GG1 evidence;
- keep the exact WB2A/GG1 main-regulation path (`7187393` candidate) separate from older LGM29 and from the later VBC130 comparison family.

### Current outcome

The online-photo work has now resolved the physical research target substantially:

1. **7187393 is a real, directly photographed GG1-era main PCB and is directly correlated with WB2A elsewhere in this document.**
2. **J1**, not VBC130 X15, is the exact-board three-pad trace target beside the main MCU.
3. **X3 / [145] / separate [145] / X10** can be located unambiguously before opening the local appliance.
4. The exact main MCU remains **unknown** because no found 7187393 photo resolves its laser marking.
5. The next decisive evidence is a local perpendicular macro photo of the 7187393 main QFP and both faces of the vertical daughterboard, followed by unpowered continuity mapping.

## Additional 7187393 photo sources and current MCU-search result

Targeted web/image research on 2026-09-25 found several exact 7187393/84346904 sale sets with multiple photographs:

- eBay item `127115328332`: `Viessmann Vitodens Regelung 7187393 Kesselkreisregelung Platine 84346904`, 10 images.
- eBay item `127843820272`: `Viessmann 7187393 Kesselkreisregelung Regelung 84346904 Platine 7187393775791202`, 10 images.
- eBay item `127843820279`: `7297094 Viessmann Regelung 7187393 Kesselkreisregelung 84346904`, 15 images; seller metadata lists `7297094 / 7297094900583117`.
- Kleinanzeigen ad `3388584017-84-16390`: standalone `Viessman Steuerung Platine 7187393`, 4 images.
- Michl's Onlineshop: standalone `Viessmann 7187393 Leiterplatte` product page.

These sources strengthen the existence of multiple physical 7187393 assemblies and provide future photo-comparison material. The number `7297094` is currently only seller/listing metadata and must **not** yet be treated as a Viessmann board-family identifier.

### Negative result: no public readable MCU marking yet

Targeted searches for combinations of:

- `7187393` + MCU / processor / microcontroller / Renesas / M306
- `84346904` + MCU / processor / microcontroller
- exact listing/barcode strings such as `7187393775791202` and `7297094900583117`

did **not** produce a reliable source that names or clearly exposes the MCU/ASIC marking on either PCB.

Current boundary:

- exact 7187393 main-board MCU: **unknown**;
- exact 84346904 vertical-board MCU/ASIC: **unknown**;
- M30624FGPFP remains proven only for the 7424735/VBC130 comparison board and must not be carried over to GG1.

### Useful physical clues from the repair thread

The WB2A repair report involving vertical PCB `84346904` also mentions:

- optocoupler reference `U5` in the ignition-transformer switching path;
- three nearby relays complicating trace-following;
- persistent 230-V behaviour at the ignition transformer under fault conditions.

Source:
https://community.viessmann.de/t5/Gas/Vitodens-200-WB2A-Stoerung-F0-Zuendtrafo-liegt-ununterbrochen-an/td-p/219269

This is user repair evidence, not a schematic. It does, however, make `U5` and the adjacent relay cluster useful landmarks when comparing high-resolution photographs of 84346904/7187393 assemblies.

### Photo-analysis priority

For any newly found or locally captured 7187393/84346904 image, inspect in this order:

1. all QFP/TQFP/PLCC devices and exact top markings;
2. all 8-pin and 14/16-pin ICs near the MCU and vertical-board connector;
3. crystals/resonators and their frequency markings;
4. EEPROM candidates (`24Cxx`, `93Cxx`, `25xx`, etc.);
5. optocouplers, especially the board-designator `U5` region;
6. X10/X15/test pads and continuity-relevant nearby passives;
7. connector pins between 7187393 and 84346904;
8. KM-BUS/145 physical-layer components.

At present, **local macro photos remain the shortest path to a trustworthy MCU identification**.

## Main MCU: likely Renesas M30624FGPFP

The enhanced crop of reference set A shows a 100-pin QFP with markings strongly consistent with:

`M16C`
`M30624FGPFP`

Renesas product page:
https://www.renesas.com/en/products/m16c-62p/part-details/m30624fgpfp-u3c

Renesas reports for M30624FGPFP:

- family: **M16C/62P**
- CPU: **M16C/60**, 16 bit
- package: **100-pin QFP**
- maximum operating frequency: **24 MHz**
- program memory: **256 KiB**
- data flash: **4 KiB**
- RAM: **20 KiB**

Primary M16C/62P hardware manual:
https://www.renesas.com/en/document/mah/m16c62p-group-m16c62p-m16c62pt-hardware-manual

Primary group datasheet:
https://www.renesas.com/en/document/dst/m16c62p-group-m16c62p-m16c62pt-datasheet?r=1053231

Evidence level:
- MCU marking on the online photo: **hardware_observation, high confidence**
- memory/peripheral architecture: **vendor_documentation**
- equivalence to the local WB2A MCU: **unproven**

### Firmware-storage implication

Because M30624FGPFP already contains 256 KiB user program flash, the working hypothesis is that the primary regulation firmware can be entirely internal to the MCU. No external firmware ROM is required.

That is **not** proof that the board has no external EEPROM/flash. Small ICs around the MCU still need exact markings and trace analysis; they may hold parameters, calibration, communication-state data or other persistent information.

Evidence level: **architecture-backed hypothesis**.

## Programming/debug architecture and X15

### X15 observation

X15 is a **3-pad unpopulated footprint** directly in the logic/MCU area with a pin-1 triangle.

This makes it a legitimate target for passive trace analysis. It does **not** establish its protocol.

Possible roles include:

- production test UART;
- service/monitor serial port;
- a subset of the M16C serial programming interface;
- generic manufacturing test points;
- another proprietary interface.

Evidence level: **hardware_observation + hypothesis**.

### Why X15 is not a complete E8/E8a connector

Renesas' E8a connection document for M16C/62P specifies a 14-pin user connector and uses at least these MCU signals:

- P65 / SCLK
- P67 / TxD
- P66 / RxD
- P64 / BUSY
- P55 / EPM
- P50 / CE
- CNVss
- RESET
- Vcc
- multiple Vss/GND pins

Reference:
https://www.renesas.com/en/document/mat/e8a-emulator-additional-document-users-manual-notes-connecting-m16c62p-m16c6n4-m16c6n5-m16c6nk

Therefore a three-pad X15 **cannot alone expose the full E8/E8a interface**.

A three-wire TxD/RxD/GND-style manufacturing UART remains plausible because the M16C/62P can use asynchronous serial programming with UART1 when the required boot/mode conditions are established elsewhere. It is only a hypothesis until continuity to MCU pins is measured.

### Serial flash support

Renesas M16C/62P documentation defines standard serial I/O programming for the on-chip flash. Third-party production-programmer device lists specifically include **M30624FGPFP** and identify it as a serial-programmable M16C/62P target.

A practical programmer manual identifies the M30624FGP user-ROM region as **0xC0000..0xFFFFF**, exactly 256 KiB.

References:

- Renesas M16C/62P hardware manual:
  https://www.renesas.com/en/document/mah/m16c62p-group-m16c62p-m16c62pt-hardware-manual
- SUISEI EFP-LC example:
  https://www.suisei.co.jp/product/pdf/English/Mainbody/EFP-LC_2412_E.pdf

Evidence level: **vendor_documentation / programmer_documentation**.

## Readout protection: important before any firmware-dump experiment

Renesas documents a seven-byte **flash memory ID code** for M16C/62P. If an ID is set, it must match before the E8a debugger can access the device; an all-FF ID is treated as undefined/automatically authenticated.

Documented ID-byte addresses:

| Byte | Address |
| --- | --- |
| 1 | `0xFFFDF` |
| 2 | `0xFFFE3` |
| 3 | `0xFFFEB` |
| 4 | `0xFFFEF` |
| 5 | `0xFFFF3` |
| 6 | `0xFFFF7` |
| 7 | `0xFFFFB` |

Primary reference:
https://www.renesas.com/en/document/mat/e8a-emulator-additional-document-users-manual-notes-connecting-m16c62p-m16c6n4-m16c6n5-m16c6nk

The M16C Flash Starter manual additionally documents the same ID layout:
https://www.renesas.com/en/document/mat/m16c-flash-starter-m3a-0806-users-manual

### Consequence for our work

A non-destructive firmware read cannot be assumed merely because the MCU has a serial bootloader. We first need:

1. exact local MCU identity;
2. exact connection/pin map;
3. confirmation of programming mode and board power domain;
4. a read-only tool path known not to erase on authentication failure;
5. knowledge of the ID/protection state where possible.

**Do not use an erase-to-unlock workflow on the production boiler controller.**

## X3 / 145 / KM-BUS relevance

The 7424735 photos visibly associate the right-side connector area with **145**, and X3 shows a group labelled **[145]**.

Viessmann documentation across this regulation generation consistently uses **145** for KM-BUS. Viessmann-hosted installation diagrams show KM-BUS 145 on **X3.6/X3.7** for relevant gas-wall-device controls. A WB2B/VBC130 field case also specifically instructs connection at X3.6/X3.7.

Examples:

- VBC130/WB2B field case:
  https://origin-viessmann.lithium.com/t5/Gas/Neue-Umwaelzpumpe-fuer-WB2B-Stromstecker-passt-nicht/td-p/256386
- Viessmann-hosted schematic example showing `145` and `X3.6/X3.7`:
  https://community.viessmann.de/viessmann/attachments/viessmann/customers-solar/3801/1/Anlagenbeispiele%20SM1.pdf

This makes the X3/145 area useful for our ongoing internal-pump/KM-BUS work, but **the exact 7424735 trace path and transceiver IC are not yet mapped**.

Next board-level questions:

- Do the separate 145 connector and X3.6/X3.7 join directly?
- Which protection/filter components sit between 145 and the logic-side bus transceiver?
- Which IC is the physical KM-BUS transceiver?
- Does that transceiver connect directly to the M30624 UART/port pins or through another controller?

## Possible KM-BUS <-> MCU serial-path convergence

The software research now gives the PCB work a specific trace target.

The local WB2A already accepts VS2/P300 function `0x41 KMBUS_RAM_READ` and
`0x43 KMBUS_EEPROM_READ`. Separately, the comparison-board M30624FGPFP
provides multiple serial channels, while its Renesas serial programming/debug
path uses UART1-related signals.

This creates a testable **hardware hypothesis**, not a conclusion:

~~~text
145 KM-BUS
    |
    v
bus protection / transceiver
    |
    v
MCU UART or GPIO
~~~

If the local board eventually confirms the same M16C family, the important
continuity question is whether the 145 transceiver terminates on the UART1 pins
used by the M16C serial programming architecture, another UART, or unrelated
GPIO.

Possible outcomes:

1. **145 -> UART1:** normal KM-BUS and the MCU boot/programming serial channel
   would share MCU serial resources. Boot-mode control would still require
   separate reset/mode signals; 145 alone would not automatically become a
   firmware-dump port.
2. **145 -> another UART:** KM-BUS and the M16C boot/programming path are
   electrically separate. X15/X10 then become stronger debug/programming
   candidates.
3. **145 -> another controller/ASIC:** the main MCU may see KM-BUS only through
   an intermediate device, changing the firmware/readout model completely.

The Optolink read-function research also limits a simple "firmware over KM-BUS"
interpretation. Standard VS2 carries only a 16-bit address field, whereas a
256-KiB M30624FGPFP program image occupies the 20-bit range
`0xC0000..0xFFFFF`. Direct program-flash access through Optolink would
therefore require an additional bank/prefix/RPC/gateway mechanism. No such
local path is currently demonstrated.

The existing 0x41 read remains highly useful even without flash access because
RAM-like or mirrored runtime structures can expose state machines, timers,
mailboxes and hidden pump-selection state.

Cross-reference:
[vitosoft/kmbus-read-memory-analysis-2026-09-24.md](vitosoft/kmbus-read-memory-analysis-2026-09-24.md)
and GitHub issue **#30**.

## X10

X10 is a small black unpopulated/populated header near the PCB edge on the online board.

Current status: **function unknown**.

Do not infer debug/programming function from the connector name alone. The next useful evidence is reverse-side trace mapping from X10 to nearby logic ICs and MCU pins.

## Vertical daughterboard

The 7424735 board carries a vertical daughterboard along one edge. The public listing includes front/rear views.

Observed identifier from one public photo:

- barcode includes **84346912**

No reliable part-number/function correlation was found for that number. Search results for the isolated number are noisy and unrelated.

Open questions:

- HMI/interface expansion vs. communication board vs. another regulation subassembly;
- MCU/ASIC/EEPROM identity;
- whether any GFA/burner-control function is present there.

**Do not call this the GFA board without direct evidence.** The project must continue to keep main regulation, burner/GFA and coding-plug storage domains separate.

## C105 / supply section

C105 is visibly present in the supply/power area of boards of this broader regulation era. Viessmann Community repair discussions around WB2A/GG1 and other controls repeatedly mention degraded C105 and a replacement specification around:

- 220 nF
- 305 V AC
- X2 safety class

Example WB2A thread:
https://community.viessmann.de/t5/Gas/Vitodens-200-WB2A-Startet-nicht-mehr/m-p/214246

This is **community repair evidence**, not an official universal diagnosis and not proof that the 7424735 C105 has the same electrical role/value. Any repair work must use the exact fitted component specification and applicable safety class.

## Online image inventory worth preserving as references

### 7424735 exact-layout listing

https://www.ebay.de/itm/127843796384

The 16-image set is unusually useful because it contains:

- full component-side overview;
- angled overview;
- close-up of board labels and C105 area;
- close-up of X3/X4/X10 and 145 markings;
- reverse side of the main PCB;
- reverse side of the vertical daughterboard;
- daughterboard barcode close-up.

These are references only; third-party images should not be copied into the public repository without permission.

### Additional complete-control listing

https://www.ebay.de/itm/277505858079

Useful for the external label correlation **7424743 = VBC 130-A03.100**.

### WB2A/GG1 comparison images

Search/reference part: **7825241 / GG1**. Current WB2A-compatible product pages and marketplace images show a related but separately identified regulation generation.

Useful current reference:
https://www.loebbeshop.de/7825241-viessmann-regelung-gg1-fuer-wb2a-wb3a-ws3a/

This is the more important comparison set once the installed WB2A board is photographed.

## Local hardware capture: required next evidence

Use the dedicated capture checklist:
[regulation-board-photo-capture.md](../../../docs/regulation-board-photo-capture.md)

Minimum photos needed before this research can be promoted from comparison-board analysis to local-board analysis:

1. local control label / complete manufacturing number;
2. local board part-number sticker;
3. complete PCB component side;
4. complete PCB rear side if safely accessible without invasive disassembly;
5. macro of main MCU marking;
6. macro of every 8/14/16-pin logic or memory IC around the MCU;
7. X15 from both sides;
8. X10 from both sides;
9. X3/145 area from both sides;
10. vertical daughterboard front/back and every IC marking if present;
11. coding-plug connector/nearby circuitry;
12. oscillator/crystal markings next to each MCU.

## Safe electrical follow-up after photography

Only after the local board is identified:

- work with the appliance de-energized and isolated;
- continuity/ohms measurements only for the first mapping pass;
- establish PCB ground before interpreting any test pad;
- trace X15 pads to MCU pins and nearby passives;
- specifically test continuity toward M16C UART1/E8 candidate pins only if the local MCU is confirmed as M30624FGPFP;
- trace X10 independently;
- map 145 through protection/filter/transceiver circuitry;
- identify Vcc rails without applying external voltage;
- do not attach an E8/E8a/programmer until the local connection map and board supply topology are known.

No live probing of the mains/power section is part of this workstream.

## Firmware acquisition decision tree

If the local controller really contains M30624FGPFP or a close M16C/62P variant:

1. **Photographic identification**
   - exact MCU suffix;
   - package;
   - oscillator;
   - test headers.

2. **Passive continuity map**
   - X15/X10 -> MCU pins;
   - RESET, CNVss, P50, P55, P64..P67;
   - GND/Vcc only with board unpowered.

3. **Protection-risk review**
   - determine programmer behavior on unknown ID;
   - reject any method that auto-erases on connection/authentication failure.

4. **Read-only bench plan**
   - isolated spare board strongly preferred over production controller;
   - exact voltage and reset/mode sequencing;
   - no erase/program command.

5. **Acquisition**
   - dump program/data flash only if authentication permits;
   - hash immediately;
   - retain raw firmware only in the private research archive;
   - public repo receives hashes, memory map, strings/symbol analysis and reproducible notes.

If the local board is instead GG1 with another MCU, restart the decision tree from the exact local MCU datasheet rather than carrying over M16C assumptions.

## PCB-research task list

- [x] Find an independent high-resolution 7424735 board set with front and rear views.
- [x] Correlate 7424735 with complete control 7424743 at marketplace level.
- [x] Correlate 7424743 with VBC 130-A03.100 in an independent WB2B source.
- [x] Identify the comparison-board main MCU at high confidence as M16C/62P M30624FGPFP.
- [x] Record Renesas memory architecture and E8/E8a interface requirements.
- [x] Record M16C/62P flash-ID readout-protection mechanism.
- [x] Correct X15 footprint count to three pads.
- [x] Establish the WB2A identity conflict: local project baseline points to GG1/7825241, so 7424735 cannot yet be treated as the installed board.
- [x] Establish 7187393 as a strong exact WB2A/GG1 PCB candidate from direct public evidence.\n- [x] Establish 84346904 as the recurring vertical daughterboard paired with 7187393.\n- [ ] Photograph the actual local WB2A regulation board and labels.
- [ ] Confirm or reject 7424735 as the local PCB number.
- [ ] Confirm exact local main MCU.
- [ ] Trace local **J1** three-pad footprint to MCU/passives on GG1/7187393; do not transfer VBC130 X15 naming.
- [ ] Trace local X10.
- [ ] Identify local external memories.
- [ ] Identify local KM-BUS 145 physical-layer circuitry.
- [ ] Identify the daughterboard role and all ICs.
- [ ] Identify burner/GFA MCU separately.
- [ ] Build a local annotated component/connector map.
- [ ] Define a non-destructive firmware-read path only if protection and programmer behavior are understood.

## Confidence matrix

| Finding | Confidence | Evidence |
| --- | --- | --- |
| Online PCB part number is 7424735 | high | two independent photo sets |
| Public 7424735 layout matches the supplied online photos | high | direct visual comparison |
| 7424735 is sold as PCB of 7424743 | medium-high | independent marketplace listing |
| 7424743 = VBC 130-A03.100 for WB2B | high | Viessmann-hosted field record + marketplace label |
| Main MCU in supplied online photo is M30624FGPFP | high, pending sharper macro | readable package marking |
| MCU has 256 KiB program flash + 4 KiB data flash + 20 KiB RAM | high | Renesas product documentation |
| X15 has 3 pads | high | image observation |
| X15 is a serial/debug/programming interface | low-medium | location/topology only; no continuity yet |
| X15 is a full E8/E8a header | rejected | 3 pads vs. Renesas multi-signal interface |
| Local WB2A uses the same 7424735 PCB | **unknown** | no local-board photo yet; WB2A spare data points to GG1/7825241 |
| Local / 7187393 MCU is M30624FGPFP | **unknown** | exact 7187393 photos show a ~100-pin QFP but marking is unreadable; package compatibility is not identity |
| Local firmware can be read without ID | **unknown** | flash ID may be set |
| 7187393 occurs on WB2A/GG1 hardware | high | direct WB2A community identification + independent WB3A occurrence |\n| 84346904 is a vertical PCB paired with 7187393 | medium-high | direct WB2A repair report + multiple marketplace photo sets |\n| Vertical 84346904 equals service-manual A4/Feuerungsautomat | **unknown** | manual separates A4 functionally, but no public part-number mapping found |

## Research discipline

For this workstream:

- preserve **board identity**, **MCU identity**, **protocol identity** and **firmware-readability** as separate claims;
- distinguish seller correlations from vendor documentation;
- do not infer local hardware from a visually similar online board;
- do not issue burner-safety writes as part of PCB research;
- prefer spare-board bench work for any future programmer experiment;
- never publish acquired proprietary firmware binaries in this public repository.
