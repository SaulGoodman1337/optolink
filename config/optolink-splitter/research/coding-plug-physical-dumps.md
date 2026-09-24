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

## Sample registry

| Sample | Physical role | IC | Reads | Result | SHA256 |
| --- | --- | --- | ---: | --- | --- |
| spare-1 | spare; **not installed in the boiler** | chip1 / 24C04 | 3 | byte-for-byte identical | `3dd583723661ea765f4e57405628def121bf78f1bc7d09dc1dfb51fec362f386` |
| spare-2 | second spare | pending | pending | pending | pending |
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

## Repository files

Raw captures are stored unchanged under:

`config/optolink-splitter/research/coding-plug-dumps/spare-1/`

Files:

- `chip1-read1.bin`
- `chip1-read2.bin`
- `chip1-read3.bin`
- `coding-plug-dump-analysis.json`

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
