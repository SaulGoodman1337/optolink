# WB2A coding-plug dual-EEPROM analysis - two older plugs - 2026-09-25

## Scope

Four read-only 512-byte EEPROM images from two older physical coding plugs are archived here:

- `7173085-3_HND_SD-20-04-f01.bin`
- `7173085-3_HND_SD-20-04-f02.bin`
- `7173085-3_400_94v_0-f01.bin`
- `7173085-3_400_94v_0-f02.bin`

These are historical single captures per side. The 3x repeat-read criterion from Issue #36 is therefore **not** claimed for these files.

The currently installed/operating coding plug **7833971 / 2015:0201** has now also been physically captured. See `../2026-09-25-active-7833971/`.

## Integrity

| File | Size | SHA256 |
| --- | ---: | --- |
| HND f01 | 512 | `34073f01eec962b709e1be22ed1332fa5bd3ca7bb361d320bb395ddc923dfa6e` |
| HND f02 | 512 | `3dd583723661ea765f4e57405628def121bf78f1bc7d09dc1dfb51fec362f386` |
| 400 f01 | 512 | `86d8703dc40c9eb4db0e1013773507417dd512bb379fad6b17b6ef88da4e6fb2` |
| 400 f02 | 512 | `554d890e5c5158893ca44b10e0503f38f8c6de4f01de0fb2b9e55211a3e48946` |

## Main result: f01 is the main-regulation/GWG coding-plug image

At physical f01 offset `0x10` the two older images contain seven-byte ASCII Viessmann part numbers:

- HND f01: `7823363`
- 400 f01: `7833968`

The current controller exposes its installed coding-plug part number at P300 `0x1010` as ASCII `7833971`.

The mapping continues blockwise. Physical f01 offset `0x20` in **both** old images is exactly:

`00 00 FF FF FF 00 00 00 00 00 00 00 00 00 00 00`

which is byte-identical to the current live P300 `0x1020` block.

The source-decoded blocks at physical offsets `0x30`, `0x40`, `0x50`, `0x60`, `0x70`, `0x80`, `0x90` and `0xC0` have the same layout as P300 `0x1030`, `0x1040`, `0x1050`, `0x1060`, `0x1070`, `0x1080`, `0x1090` and `0x10C0`.

The invariant old/current blocks `0x1020`, `0x1060`, `0x1080`, `0x1090` and `0x10C0` are byte-identical.

**Conclusion:** f01 is the physical main-regulation/GWG coding-plug storage behind the P300 `0x1000 + EEPROM offset` view. The active 7833971 physical dump now provides the same-plug byte-for-byte confirmation.

## Decoded f01 comparison

Current 7833971 values are the existing source-backed live observations from `config/optolink-splitter/vdensho1-20c2-wb2a-service-draft-poll-list.py`.

| Field | 7823363 | 7833968 | active 7833971 | Source meaning |
| --- | ---: | ---: | ---: | --- |
| part number | `7823363` | `7833968` | `7833971` | `0x1010` / physical `0x10` |
| P107/P101 raw | `02 12` | `04 12` | `02 15` | `0x1040` / physical `0x40` |
| GWG30 | 70% | 85% | 65% | DHW power limit |
| GWG32 | 70% | 60% | 29% | heating power limit |
| GWG34 | 3 | 3 | 3 | Grundfos diverter valve |
| GWG5A | 60 C | 63 C | 63 C | DHW setpoint maximum |
| GWG5C | 85% | 85% | 65% | absolute DHW max power |
| GWG5D | 85% | 85% | 65% | absolute heating max power |
| GWG60..67 | identical | identical | identical | boiler regulator constants |
| GWG70 | 5 C | 5 C | 5 C | minimum boiler temperature |
| GWG71 | 29% | 29% | 29% | burner minimum power |
| GWG72 | 20 K | 20 K | 20 K | modulating-burner offset |
| GWG73 | 240 s | 240 s | 240 s | startup optimization |
| **GWG74** | **70%** | **100%** | **65%** | storage-mode boiler target power |
| **GWG75** | **100%** | **50%** | **50%** | minimum internal-pump speed |
| GWG76 | 60 s | 60 s | 60 s | internal-pump overrun |
| GWG80..88 | identical | identical | identical | DHW/DLH regulator |
| GWG91..9A | identical | identical | identical | burner characteristic curve |
| GWGC0..CA | identical | identical | identical | Grundfos diverter motion profile |

The current 7833971 belongs to a different published power class than 7833968, so not every 7833968-vs-7833971 difference should be interpreted as a firmware/revision change. In particular, the power-limit differences are consistent with different appliance output classes.

## 7823363 -> 7833968 replacement delta

The two old f01 images are **499/512 bytes identical**. Only 13 bytes differ:

```text
0x00E 52 -> D4
0x00F E6 -> 6C
0x012 32 -> 33   ASCII part number
0x014 33 -> 39   ASCII part number
0x016 33 -> 38   ASCII part number
0x030 46 -> 55   GWG30 70 -> 85
0x031 B9 -> AA   complement follows GWG30
0x032 46 -> 3C   GWG32 70 -> 60
0x033 B9 -> C3   complement follows GWG32
0x040 02 -> 04   P107/revision byte in the 0x1040 identity block
0x05A 3C -> 3F   GWG5A 60 -> 63 C
0x074 46 -> 64   GWG74 70 -> 100
0x075 64 -> 32   GWG75 100 -> 50
```

The bytes at `0x00E..0x00F` change while `0x000..0x00D` remain identical; they are plausible integrity/check bytes, but no algorithm is claimed yet.

### Pump relevance

The strongest new pump-related physical result is:

```text
7823363 physical f01[0x75] = 0x64 = GWG75 100 %
7833968 physical f01[0x75] = 0x32 = GWG75  50 %
7833971 live P300 0x1075 = 0x32 = GWG75 50 %
```

The public replacement trail independently identifies 7833968 as the WB2A 26 kW replacement for 7823363 and as the coding plug used with the variable-speed/KM-BUS pump retrofit. The physical EEPROM delta therefore matches the source-decoded semantics: the old 7823363 permits no downward internal-pump modulation through GWG75, while 7833968 lowers the internal-pump minimum to 50%.

This is **not** evidence for the sought volatile burner-dependent A1 pump override. It is persistent coding-plug configuration of the internal pump and supports the already established distinction between A1 runtime control and internal-pump coding.

## f02 result

f02 is structurally very different from f01 and does **not** contain the ASCII coding-plug part number or the known P300 `0x10xx` block image.

Key observations:

- the two f02 images are **492/512 bytes identical**;
- their first **226 bytes (`0x000..0x0E1`) are byte-identical** despite the two f01 images representing different coding plugs;
- all f02 differences start at `0x0E2`;
- a long payload region repeats inside each f02: bytes at `0x14..` and `0x66..` have 71 consecutive identical bytes; the record starts are 82 bytes apart;
- the current software vectors `0x7656 = 20 15 02 01`, P100..P108 `63 15 01 14 0C 04 D6 02 00`, current date `14 0C 04`, and current `0x1040 = 02 15` do not occur contiguously in either old f02 image;
- the 20 bytes that differ between the old f02 images are confined to tail/control areas from `0x0E2` onward.

This strongly rejects f02 as a second flat copy of the normal GWG/P300 coding-plug image.

The active 7833971 capture now closes this uncertainty: physical f02 offsets `0x0E..0x13` equal live GFA P101..P106 exactly (`15 01 14 0C 04 D6`). The two old f02 images carry `12 03 08 04 04 FB` at the same offsets. Therefore f02 contains the GFA/fire-control coding-plug dataset; at least P101..P106 are directly mapped.

## Active 7833971 follow-up

The active physical capture is complete and documented in
`../2026-09-25-active-7833971/`.

It confirms:

- f01 same-plug physical/P300 mapping;
- f02 same-plug physical/GFA P101..P106 mapping.

Still unresolved on f02: unique physical offsets for P90, P100, P107 and P108.

## Evidence level

- raw EEPROM bytes: **hardware observation**
- f01 -> P300/GWG mapping: **hardware observation + source metadata**, strongly established
- GWG field names/conversions: **source metadata**, already documented in the repository
- f02 -> GFA assignment: **hardware observation + live GFA_READ**, proven for P101..P106
