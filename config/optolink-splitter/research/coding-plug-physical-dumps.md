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

## Cross-correlation with Optolink/Vitosoft metadata

The physical dumps can now be compared against three distinct coding-plug
views already present in this repository. Keeping those views separate is
important because none of them is proven to be a byte-for-byte view of either
physical EEPROM.

### 1. Main-regulation / GWG view

The Vitosoft-derived event inventory exposes the controller-side
`GWG_Codierstecker_*` family through structured P300 objects:

| Object | Source-defined content |
| --- | --- |
| `0x1010` | coding-plug part number / Sachnummer |
| `0x1020` | commissioning year, month, day |
| `0x1030` | GWG30, GWG32, GWG34 plus additional unlabeled protected slots |
| `0x1040` | coding-plug identifier / Kennziffer |
| `0x1050` | GWG50/51/53/58/59/5A/5B/5C/5D |
| `0x1060` | GWG60..GWG67 |
| `0x1070` | GWG70..GWG76 |
| `0x1080` | GWG80..GWG88 |
| `0x1090` | GWG91..GWG9A burner characteristic |
| `0x10A0` | Viessmann diverter-valve motion profile |
| `0x10B0` | Wilo diverter-valve motion profile |
| `0x10C0` | Grundfos diverter-valve motion profile |

For the currently installed plug, the repository already contains
hardware-verified blocks through `0x1090` and the relevant Grundfos
`0x10C0` block.

A crucial structural result is the active `0x1030` image:

```text
41 BE 1D E2 03 FC 51 AE 64 9B 00 FF 00 FF 00 FF
```

It consists entirely of eight `value / bitwise-complement` pairs. The first
three source-labelled primary values are:

```text
41 / BE -> GWG30 = 65
1D / E2 -> GWG32 = 29
03 / FC -> GWG34 = 3
```

The remaining primary values are not all source-labelled in the retained
VDensHO1 metadata. In particular, the `64 / 9B` pair structurally occupies
the position previously discussed as a possible GWG38-like slot, but its
semantic name is still unproven.

This protected representation is important for physical-dump work: an exact
16-byte P300-object match is **not required** for a real physical mapping.
The controller may synthesize complement/integrity bytes or copy fields into a
different runtime structure.

The active Grundfos diverter-valve block is also now part of the correlation
baseline:

```text
0x10C0 =
5A 32 2D C8 5A 32 02 32 02 32 00 FF FF FF FF FF
```

No exact copy of that block or its distinctive multi-byte profile is present
in either current spare/chip1 image.

### 2. Coding-card summary view

The exact VDensHO1 event set defines four coding-card diagnostics over the same
`0x7656` array:

- coding-card device identification;
- coding-card **GFA revision**;
- coding-card **GWG revision**;
- coding-card type.

The currently installed boiler returns:

```text
0x7656 = 20 15 02 01
```

The public derived event CSV does not retain the original member byte-position
metadata, so it is not yet safe to declare a definitive byte-to-name mapping.
However, the existence of **separate GFA and GWG revision fields** is strong
evidence that the coding card has at least two logical configuration/revision
domains.

The raw value must continue to be described as revision notation
`2015:0201`, not as a calendar date. Vitosoft exposes separate coding-plug
day/month/year diagnostics elsewhere.

### 3. GFA / fire-control view

The recovered VSKO/GFA catalog exposes a second coding-plug namespace:

| GFA address | Parameter | Meaning |
| --- | --- | --- |
| `0x405A` | P90 | coding-plug FA type |
| `0x4064` | P100 | minimum-power representation, factor 0.3922 |
| `0x4065` | P101 | VI coding-plug identity 1 |
| `0x4066` | P102 | VI coding-plug identity 2 |
| `0x4067..0x4069` | P103..P105 | coding-plug day/month/year |
| `0x406A` | P106 | VI coding-plug CRC diagnostic |
| `0x406B..0x406C` | P107..P108 | FA40/FA41 coding-plug identity |

These objects are distinct from the normal `0x10x0` GWG structures. They
provide a high-value future read-only correlation target because one physical
EEPROM may map more directly to the GFA/FA domain than to the normal
controller/GWG domain.

### Dual-EEPROM architecture hypothesis

The photographs show two different 24C04 implementations on separate PCB
faces/contacts:

- f01 / SIM1: ST `24C04W6`;
- f02 / SIM2: Microchip `24LC04B`.

The repository independently shows:

- separate GWG coding-plug structures;
- separate GFA coding-plug diagnostics;
- separate GFA and GWG coding-card revision fields.

Taken together, this supports a **working hypothesis** that the two physical
EEPROMs may serve different coding domains/consumers, for example a
regulation/GWG side and a fire-control/GFA side.

This is **not yet a side assignment**. There is currently no evidence proving
that f01 is GWG or GFA, or that f02 is the other domain. Both EEPROMs must be
captured with their PCB side explicitly recorded before making that claim.

## Stronger mirror structure in both spare dumps

The first analysis described two repeated regions separately. They can in fact
be combined into one exact **82-byte logical mirror record**.

For both spare-1 and spare-2:

```text
logical copy A =
  physical 0x001..0x00B
  +
  physical 0x014..0x05A

logical copy B =
  physical 0x05B..0x0AC

copy A == copy B
length = 82 bytes
SHA256 = 740df5bdd0fcfe2d162616689a1a3b2fab93fef6cf6baf44663077d6e3a5b0c3
```

Between the two pieces of copy A sits an 8-byte area that is not part of the
mirrored logical record:

```text
0x00C..0x013 = 00 FF 12 03 08 04 04 FB
```

That 8-byte area itself contains two obvious complement pairs:

```text
00 / FF
04 / FB
```

Both spare plugs have the same logical mirror record and the same 8-byte
insert. In fact their complete first **226 bytes** are identical:

```text
0x000..0x0E1 identical
SHA256 of common 226-byte prefix:
301bdb0ef23df9602e2e807dd6590549ea8fffd8d4b106f6c86f96d931521997
```

This substantially strengthens the interpretation that the saved data is a
real structured EEPROM image rather than unstable programmer output.

The exact duplicate is consistent with redundancy/integrity storage, but the
purpose is still unproven. It could be a primary/backup parameter record, two
consumer copies, a validation mirror, or another manufacturer-specific
layout.

### Direct mapping result so far

No flat/direct mapping has yet been demonstrated between spare/chip1 and the
currently installed 7833971 / 2015:0201 plug:

- ASCII `7833971` is absent;
- raw `20 15 02 01` is absent;
- common BCD/integer encodings tested for those identities are absent;
- exact active `0x1030..0x1090` blocks are absent;
- exact active Grundfos `0x10C0` is absent.

The lack of an exact match is now less surprising because:

1. the spares have not yet been proven to be the same external part/revision
   as the active 7833971 plug;
2. the captured package has not yet been tied to f01/ST or f02/Microchip;
3. the second EEPROM has not been captured;
4. at least one controller-side object (`0x1030`) demonstrably uses a
   protected value/complement representation rather than a simple flat field
   list;
5. the GFA exposes a second, separate coding-plug view.

Accordingly, the current result is **no direct flat mapping found**, not
"physical EEPROM is unrelated to the Optolink coding plug".

### Best next read-only correlation targets

When bench access is resumed, the highest-value sequence is:

1. explicitly label each read as `f01/ST` or `f02/Microchip`;
2. capture both sides of one spare three times;
3. compare the two sides before reading more plugs;
4. capture the currently installed plug last;
5. snapshot the active controller's complete normal coding-plug view,
   especially `0x1010`, `0x1020`, `0x1030..0x10C0` and `0x7656`;
6. through the already recovered read-only GFA path, snapshot P90 and
   P100..P108;
7. compare **semantic field vectors** and complement/integrity patterns rather
   than requiring a whole 16-byte P300 object to occur literally in EEPROM.

A machine-readable summary of this correlation is stored as
`coding-plug-dumps/repo-correlation-2026-09-24.json`.

## Live GFA coding-plug vector correlation - 2026-09-24

The installed `7833971 / 2015:0201` plug now has a same-window read-only software correlation across the normal regulation and GFA domains:

```text
0x1010 = ASCII 7833971
0x7656 = 20 15 02 01

P90..P108 raw vector:
00 63 15 01 14 0C 04 D6 02 00
```

Detailed field values:

- P90 = `00` (FA type / FA42);
- P100 = `63` = 99 raw = **38.8278 %** using the source-defined factor 0.3922;
- P101 = `15`;
- P102 = `01`;
- P103/P104/P105 = `14 / 0C / 04`, source-labelled day/month/year but calendar encoding still unresolved;
- P106 = `D6` CRC diagnostic;
- P107/P108 = `02 / 00`.

The values `15`, `01` and `02` also occur in the four-byte regulation-side summary `20 15 02 01`. This is the first direct live evidence that the regulation/coding-card summary and GFA coding-plug namespace share identity/revision material. Exact subfield correspondence remains open because the retained public extraction does not prove the byte positions of the four `0x7656` source fields.

Both existing spare-chip1 binaries were scanned byte-for-byte for the full GFA vector and for the distinctive multi-byte fragments `63 15 01 14 0C 04 D6 02 00`, `15 01`, `14 0C 04`, `20 12 04`, and `D6 02 00`. There were **no exact contiguous hits** in either image.

Therefore a simple flat copy of the active GFA diagnostic block is not present in the two current spare-chip1 captures. This strengthens the need to read both physical EEPROM sides with explicit f01/f02 labels before assigning domains.

A second-pass single-byte scan found a more specific pattern inside the exact duplicated 82-byte logical record. The following active GFA raw values occur at corresponding offsets in **both** mirror copies and in both spare-chip1 images:

```text
P107 raw 02 : 0x003 <-> 0x05D
P102 raw 01 : 0x01B <-> 0x06D
P104 raw 0C : 0x01D <-> 0x06F
P100 raw 63 : 0x02B <-> 0x07D
               0x046 <-> 0x098
```

By contrast, active `P101=15`, `P103=14` and `P106=D6` do not occur anywhere in either spare-chip1 image. The mirrored matches are **candidate correlations only**: a shared byte value is not enough to assign a field. However, the pattern is compatible with a physical record that contains shared model parameters while identity/date/CRC material is plug-specific, transformed, or stored on the other EEPROM.

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
