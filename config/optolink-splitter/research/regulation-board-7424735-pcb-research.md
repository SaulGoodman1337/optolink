# PCB research: Viessmann 7424735 / VBC 130 comparison board

Status: **active preliminary PCB research; local-board identity not yet confirmed**

Last updated: **2026-09-24**

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

### Working rule

Until the actual installed board is photographed:

- use 7424735 only as a **comparison platform**;
- do not label the local controller as VBC 130-A03.100;
- do not transfer X15 pinout, MCU type, firmware map or replacement compatibility to the local WB2A;
- prioritize local label/MCU capture before any electrical probing.

This identity check is now the first gate of the PCB workstream.

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
- [ ] Photograph the actual local WB2A regulation board and labels.
- [ ] Confirm or reject 7424735 as the local PCB number.
- [ ] Confirm exact local main MCU.
- [ ] Trace local X15 pads to MCU/passives.
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
| Local MCU is M30624FGPFP | **unknown** | depends on local-board identity |
| Local firmware can be read without ID | **unknown** | flash ID may be set |
| Vertical daughterboard is burner/GFA electronics | low / unproven | no IC/trace evidence |

## Research discipline

For this workstream:

- preserve **board identity**, **MCU identity**, **protocol identity** and **firmware-readability** as separate claims;
- distinguish seller correlations from vendor documentation;
- do not infer local hardware from a visually similar online board;
- do not issue burner-safety writes as part of PCB research;
- prefer spare-board bench work for any future programmer experiment;
- never publish acquired proprietary firmware binaries in this public repository.
