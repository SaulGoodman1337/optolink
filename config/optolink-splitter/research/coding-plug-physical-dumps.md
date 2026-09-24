# Physical coding-plug EEPROM dump campaign

## Scope

This document tracks read-only external EEPROM captures from the physical
Kesselcodierstecker boards. It deliberately keeps spare-plug evidence separate
from the coding plug currently installed in the boiler until the physical
labels/revisions have been recorded and matched.

No erase, program, write-protect or other write operation is part of this
campaign.

## Hardware and read method

First successful capture: **2026-09-24**.

Bench setup:

- CH341A MiniProgrammer;
- SOIC8 test clip;
- Windows CH341PAR driver;
- AsProgrammer with device family **24C04** selected;
- coding plug fully removed from the boiler during the capture;
- three independent read operations with the clip left in place;
- raw output saved as 512-byte binary files.

The photographed coding-plug PCB is populated on both sides and carries two
24C04 serial EEPROM packages. The first batch below is explicitly named
**chip1** because only that physical package was captured in this batch.

Important limitation: an in-circuit clip can power more of the PCB than the
clipped package alone. The three identical reads prove repeatability of this
capture setup, but they do not yet prove electrical isolation of chip1 from the
second 24C04. Reading chip2 separately is therefore an important control.

## Physical IC identification from the existing photos

A closer review of the already available photographs corrects the earlier
over-simplified description of the two packages. They are **not identical
parts**, although both belong to the same 4-Kbit I2C EEPROM class:

- **f01 / SIM1 side:** STMicroelectronics `24C04W6` (M24C04-W family);
- **f02 / SIM2 side:** Microchip `24LC04B` (marking consistent with
  `24LC04B/SN`).

Both devices provide 4 Kbit = **512 bytes**, use a two-wire I2C-compatible
interface, have a 16-byte page-write organization and operate at 2.5..5.5 V
for these variants. They are therefore broadly programmer-compatible as a
24C04-class device, but they are not identical silicon.

There is one relevant implementation difference:

- Microchip 24LC04B documents A0/A1/A2 as not internally connected;
- ST M24C04-W uses E1/E2 as chip-enable/address inputs, with the upper address
  bit A8 carried in the device-select code.

The board photographs show a very similar passive network on both faces
(decoupling capacitor plus `1003` = 100 kOhm resistor) and five external
contact pads per face. This strongly suggests two separate EEPROM channels or
interfaces, one per board face, rather than two identical packages simply
paralleled on one I2C bus. That topology is still a **photographic inference**,
not an electrically verified schematic.

The existing saved files are named `chip1`, but the photographs do not prove
whether that label corresponds to **f01/ST** or **f02/Microchip**. Until a new
capture explicitly records the board face, the raw files must remain
vendor-neutral `chip1` samples.

## Sample registry

| Sample | Physical role | IC | Reads | Result | SHA256 |
| --- | --- | --- | ---: | --- | --- |
| spare-1 | spare; **not installed in the boiler** | chip1 / 24C04 | 3 | byte-for-byte identical | `3dd583723661ea765f4e57405628def121bf78f1bc7d09dc1dfb51fec362f386` |
| spare-2 | second spare; **not installed in the boiler** | chip1 / 24C04 | 3 | byte-for-byte identical | `554d890e5c5158893ca44b10e0503f38f8c6de4f01de0fb2b9e55211a3e48946` |
| active | currently installed coding plug | pending | pending | pending | pending |

The exact external part number/revision of **spare-1** has not yet been
recorded in this capture set. It must therefore not be assumed to be
7833971 / 2015:0201 merely because that is the identity of the currently
installed plug.

## Spare-1 / chip1 analysis

All three files are exactly **512 bytes** and have the same SHA256:

```text
3dd583723661ea765f4e57405628def121bf78f1bc7d09dc1dfb51fec362f386
```

Pairwise comparison:

```text
read1 == read2
read1 == read3
read2 == read3
differing bytes: 0
stable offsets: 512 / 512
```

Basic structure of the representative image:

- Shannon byte entropy: approximately **2.658 bits/byte**;
- **48** distinct byte values;
- longest `FF` run: **255 bytes**, offsets `0x100..0x1FE`;
- byte `0x1FF = 0x01`;
- longest `00` run: **52 bytes**, offsets `0x0AE..0x0E1`;
- a **71-byte region** at `0x014..0x05A` is repeated exactly at
  `0x066..0x0AC`;
- printable ASCII `M22,` occurs at offsets `0x021` and `0x073`,
  consistent with that repeated region.

The large repeated region is the first strong indication of internal
redundancy or duplicated parameter data. Its semantics are not yet known.

### Comparison with the currently installed coding-plug evidence

The physical spare-1/chip1 image does **not** contain any of the patterns
currently searched by the repository analyzer:

- raw identity sequence `20 15 02 01` for revision 2015:0201;
- ASCII `7833971`;
- BCD-like candidates `78 33 97 1F` or `07 83 39 71`.

It also contains no exact 16-byte match for the currently measured Optolink
objects `0x1030`, `0x1050`, `0x1060`, `0x1070`, `0x1080` or
`0x1090`, and no exact match for the 8-byte `0x1040` object.

This is **not** evidence that the dump is wrong. Several explanations remain
open:

1. spare-1 may be a different coding-plug part/revision;
2. the physical EEPROM layout may encode or transform the controller-visible
   `0x10x0` objects rather than storing them verbatim;
3. the two EEPROMs may divide data/functions between them;
4. in-circuit electrical participation of both EEPROMs still needs to be
   excluded by reading chip2 independently.

No semantic byte mapping should be claimed until the remaining plug/chip
captures are available.


## Spare-2 / chip1 analysis

Despite the temporary CH341A/clip connection trouble during setup, the three
saved reads are internally consistent:

```text
size:   512 bytes each
SHA256: 554d890e5c5158893ca44b10e0503f38f8c6de4f01de0fb2b9e55211a3e48946

read1 == read2
read1 == read3
read2 == read3
differing bytes: 0
stable offsets: 512 / 512
```

This makes random read noise or an unstable I2C capture unlikely for the three
files that were actually saved.

Basic structure:

- Shannon byte entropy: approximately **2.763 bits/byte**;
- **49** distinct byte values;
- longest `FF` run: **240 bytes**;
- longest `00` run: **52 bytes**;
- the same **71-byte duplicated region** is present:
  `0x014..0x05A == 0x066..0x0AC`;
- printable ASCII `M22,` again occurs at `0x021` and `0x073`;
- the known currently-installed-plug search patterns
  `20 15 02 01`, ASCII `7833971` and the tested BCD variants are absent.

### Spare-1 versus spare-2

This comparison is particularly useful because the two spare captures are
**not identical**, but they are extremely close:

```text
identical bytes: 492 / 512 = 96.0938 %
first difference: 0x0E2
bytes 0x000..0x0E1: identical
```

All differences are confined to a small tail/service-looking area:

| Offset | spare-1 | spare-2 |
| ---: | ---: | ---: |
| 0x0E2 | 5C | BE |
| 0x0E5 | 06 | 10 |
| 0x0E8 | 2B | AE |
| 0x0EB | 02 | 00 |
| 0x0EE | 02 | 0C |
| 0x0EF | 70 | E6 |
| 0x0F0 | 00 | 01 |
| 0x100 | FF | 00 |
| 0x102 | FF | 00 |
| 0x104 | FF | 00 |
| 0x106 | FF | 00 |
| 0x108..0x10F | FF FF FF FF FF FF FF FF | A5 5A A5 5A A5 5A A5 5A |
| 0x1FF | 01 | FF |

The `A5 5A` repetition and the exact repeatability of all three reads make
this look like deliberate stored content rather than transient bus corruption.
The change exactly at the `0x100` boundary is also notable because a 24C04
crosses its 256-byte block boundary there.

The strongest current interpretation is therefore:

- both spare plugs share the same main data image/family to a very high degree;
- the duplicated 71-byte main-looking region is identical between them;
- only a small tail/upper-block area differs and may contain manufacturing,
  test, calibration, state, copy-selection or other per-device metadata;
- this remains a hypothesis until the plug labels, chip2 captures and active
  coding-plug dump are available.

The 96 % identity is also useful evidence against the temporary programmer
connection problem having produced arbitrary garbage: an accidental bad read
would be very unlikely to reproduce the same coherent image three times and
match the first spare at 492 of 512 byte positions.

### Additional binary-structure observations

A closer binary comparison reveals more structure than the initial summary:

- `0x01..0x0B` is repeated exactly at `0x5B..0x65`;
- `0x14..0x5A` is repeated exactly at `0x66..0xAC` (71 bytes);
- the first copy has an additional unique 8-byte area at `0x0C..0x13`;
- `0xAE..0xE1` is a 52-byte zero-filled area in both spare captures;
- the differing lower-block tail at `0xE2..0xF0` naturally groups into five
  consecutive 3-byte fields.

If interpreted only structurally as unsigned little-endian 24-bit values
(without assigning semantics), those five fields are:

| Field offset | spare-1 | spare-2 |
| ---: | ---: | ---: |
| 0x0E2 | 92 | 190 |
| 0x0E5 | 6 | 16 |
| 0x0E8 | 43 | 174 |
| 0x0EB | 2 | 0 |
| 0x0EE | 28674 | 124428 |

This 3-byte alignment makes the tail differences look deliberately formatted,
but it does **not** establish whether the fields are counters, identifiers,
calibration values, checksums or something else.

### Special caution around 0x100

Both EEPROM families are 512-byte devices organized around a 256-byte address
boundary; the high address bit is part of the device-select/addressing
mechanism. The conspicuous spare-2 pattern beginning exactly at `0x100`
therefore deserves extra caution, especially because connection problems were
observed later during the bench session.

The saved reads are internally repeatable, so they remain useful evidence.
However, until the same side is re-read with the face/vendor explicitly
recorded (or with an independent reader), the `0x100..0x1FF` region should
not be given semantic meaning solely from the `A5 5A` pattern.

The lower-block differences at `0x0E2..0x0F0` are not affected by that
256-byte boundary and are therefore the stronger cross-sample evidence.

## Repository files

Raw captures are stored unchanged under:

`config/optolink-splitter/research/coding-plug-dumps/spare-1/` and
`config/optolink-splitter/research/coding-plug-dumps/spare-2/`

Files:

- `chip1-read1.bin`
- `chip1-read2.bin`
- `chip1-read3.bin`
- `coding-plug-dump-analysis.json`

The spare-2 directory contains the corresponding three `chip1-read*.bin`
files and analyzer report. The campaign directory additionally contains
`spare-1-vs-spare-2-chip1.json` with the exact cross-sample byte differences.

The JSON report follows the output structure of
`tools/analyze-wb2a-coding-plug-dumps.py`.

## Next capture sequence

For every physical coding plug:

1. record the plug label/part number/revision before correlating its data;
2. identify which PCB side/package is called chip1 and chip2;
3. read **each 24C04 three times** without moving the clip between the three
   reads;
4. require identical sizes and SHA256 hashes before using a capture for
   reverse engineering;
5. compare chip1 versus chip2 on the same plug;
6. then compare spare-1, spare-2 and the currently installed plug;
7. only after those comparisons, search for checksums, copy-selection markers,
   Optolink/GWG correlations and candidate identity fields.

The active boiler plug should remain the final capture. The entire campaign
remains read-only.
