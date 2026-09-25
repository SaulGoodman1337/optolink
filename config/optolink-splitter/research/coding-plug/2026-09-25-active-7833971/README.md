# Active 7833971 coding-plug dual-EEPROM correlation - 2026-09-25

## Scope

These are the physical f01/f02 EEPROM dumps from the coding plug currently
installed/operating in the local WB2A / VDensHO1 / 20C2 appliance.

Raw files:

- `7173085-3_CHL-G_3F1_94V-0_f01.bin`
- `7173085-3_CHL-G_3F1_94V-0_f02.bin`

Each file is exactly 512 bytes. These are single supplied captures; a 3x
repeat-read stability claim is not made unless repeat files are captured later.

## SHA256

- f01: `6b60b5b9de3dc90cbbe2bba2f7878ef4db36e117577f3402970170746e5cf63f`
- f02: `e20316f2053b5002fc52b213b7f6bd7f8b63944a3202bf4b865c999091113e9a`

## f01: direct physical P300/GWG image - now same-plug proven

Physical f01 offset `0x10` contains:

`37 38 33 33 39 37 31` -> ASCII **7833971**

The supplied physical f01 image matches every already captured live P300
coding-plug block that has a source-backed decode:

| physical f01 | P300 | current physical bytes | live comparison |
| --- | --- | --- | --- |
| 0x10 | 0x1010 | ASCII 7833971 | exact |
| 0x20 | 0x1020 | 00 00 FF FF FF 00... | exact |
| 0x30 | 0x1030 | 41 BE 1D E2 03 FC 51 AE 64 9B 00 FF 00 FF 00 FF | exact |
| 0x40 | 0x1040 | 02 15 | exact |
| 0x50 | 0x1050 | 00 00 00 02 00 00 00 00 4A 14 3F 0A 41 41 00 00 | exact |
| 0x60 | 0x1060 | 04 08 1E 04 05 04 1E 14 00... | exact |
| 0x70 | 0x1070 | 05 1D 14 18 41 32 3C 00... | exact |
| 0x80 | 0x1080 | 04 08 1E 28 37 00 03 08 00... | exact |
| 0x90 | 0x1090 | 00 21 21 21 2F 37 3F 48 51 5A 64 00... | exact |
| 0xC0 | 0x10C0 | 5A 32 2D C8 5A 32 02 32 02 32 00 FF... | exact |

This closes the mapping for the active plug:

`P300 address = 0x1000 + physical f01 EEPROM offset`

for the verified coding-plug range.

The physical active image therefore independently confirms the previously
decoded source fields including:

- GWG71 burner minimum = 29%;
- GWG72 modulating-burner offset = 20 K;
- GWG73 startup optimization = 240 s;
- GWG74 storage-mode boiler target power = 65%;
- **GWG75 internal-pump minimum = 50%**;
- GWG76 internal-pump overrun = 60 s.

## f02: direct GFA coding-plug evidence

The active physical f02 image gives the previously missing same-plug hardware
correlation.

Physical offsets `0x0E..0x13` are:

```text
15 01 14 0C 04 D6
```

The live GFA_READ values already captured from this exact operating plug are:

```text
P101 = 15
P102 = 01
P103 = 14
P104 = 0C
P105 = 04
P106 = D6
```

Therefore:

| physical f02 offset | live GFA field | active value |
| ---: | --- | ---: |
| 0x0E | P101 coding-plug identity 1 | 0x15 |
| 0x0F | P102 coding-plug identity 2 | 0x01 |
| 0x10 | P103 date day raw | 0x14 |
| 0x11 | P104 date month raw | 0x0C |
| 0x12 | P105 date year raw | 0x04 |
| 0x13 | P106 CRC diagnostic raw | 0xD6 |

This is direct physical <-> live GFA correlation on the same coding plug.

The two older f02 images have at the exact same offsets:

```text
12 03 08 04 04 FB
```

Both older f01 images independently contain P101=0x12 in their physical
0x1040-equivalent block, while the active f01 contains P101=0x15. Thus f01
and f02 also cross-correlate P101 across all three physical plugs.

**Conclusion:** f02 contains the GFA/fire-control coding-plug dataset. At
minimum P101..P106 have a proven direct physical mapping at offsets
0x0E..0x13. The earlier f02->GFA assignment is no longer merely a hypothesis.

## What is not yet mapped on f02

Current live GFA values also include:

- P90 = 00
- P100 = 63
- P107 = 02
- P108 = 00

The active f02 contains multiple candidate bytes with those values:

- 0x63 occurs at 0x2B, 0x46, 0x7D and 0x98;
- 0x02 and 0x00 occur at multiple positions.

No unique physical offset is assigned to P90/P100/P107/P108 yet.

The f02 record structure remains notable:

- a 71-byte sequence beginning at 0x14 repeats at 0x66;
- the two starts are 82 bytes apart;
- the current f02 differs from the old HND f02 at only 12/512 positions;
- six of those positions are exactly the P101..P106 area (five changed
  values plus unchanged P105 within the mapped six-byte field);
- the remaining changes are in the tail/control region around 0xE2..0xEF
  and 0x1FF.

Do not assign the repeated 0x63 candidates to P100 without another independent
discriminator.

## Date interpretation remains bounded

P103/P104/P105 are source-labelled day/month/year.

Active raw:

`14 0C 04`

Old raw:

`08 04 04`

The old day value 0x08 does not distinguish binary from BCD encoding. Therefore
the active raw 0x14 must still not be promoted to either decimal day 20 or BCD
day 14 without source/display evidence.

## Pump-research significance

The active f01 physically confirms GWG75=50%.

Together with the old-plug result:

- 7823363: GWG75 = 100%
- 7833968: GWG75 = 50%
- active 7833971: GWG75 = 50%

this strengthens the link between the coding-plug revision/replacement path
and variable-speed internal KM-BUS pump capability.

It does **not** establish a volatile burner-dependent A1 pump boost. GWG75 is
persistent coding-plug configuration for the internal-pump role.

## Evidence level

- f01 bytes / f02 bytes: hardware observation
- f01 <-> P300 mapping: same-plug hardware observation + source metadata
- f02 P101..P106 <-> GFA mapping: same-plug hardware observation + live GFA_READ
- P90/P100/P107/P108 physical offsets: unresolved
- date display encoding: unresolved


## Fresh static GFA fingerprint - live read-only correlation

A fresh bounded read-only run used the production VS1 `gfaread` path and read
the static identity/configuration fields twice. P80 was used as the branch gate.

Both rounds were identical:

```text
P80  0x4050 = 20
P81  0x4051 = 02
P82  0x4052 = 06
P83  0x4053 = 76
P90  0x405A = 00
P100 0x4064 = 63
P101 0x4065 = 15
P102 0x4066 = 01
P103 0x4067 = 14
P104 0x4068 = 0C
P105 0x4069 = 04
P106 0x406A = D6
P107 0x406B = 02
P108 0x406C = 00
```

Source semantics:

- P80 = ID BCU/FA chip
- P81 = BCU software version
- P82 = BCU software revision
- P83 = appliance configuration
- P90 = coding-card/BCU type FA42
- P100 = minimum output
- P107 = coding-card identity FA40
- P108 = coding-card identity FA41

### Important physical negative evidence

The active f02 EEPROM contains:

- no byte `0x20` anywhere;
- no byte `0x06` anywhere;
- no byte `0x76` anywhere.

Therefore P80, P82 and P83 **cannot** be flat raw bytes stored in the f02 image.

P81 happens to have raw value `0x02`, and `0x02` occurs in f02, but the
P80/P82/P83 result shows that the P80-P83 identity/configuration block belongs
to GFA chip/firmware/device state rather than a direct linear coding-plug
EEPROM mapping. A coincidental `0x02` match must not be promoted to a P81
offset.

This cleanly separates:

- f02 coding-plug bytes proven by P101..P106;
- GFA chip/software/appliance identity represented by P80..P83.

### P100 remains ambiguous

Active P100 raw = `0x63`.

The active f02 contains `0x63` at:

```text
0x02B
0x046
0x07D
0x098
```

The two pairs are separated by the known 82-byte repeated-record distance:

- `0x02B -> 0x07D`
- `0x046 -> 0x098`

All three available f02 images carry `0x63` at all four positions, so this
live read still cannot select the physical P100 field by differential evidence.

### Safety / runtime state

- only explicit `GFA_READ` operations were used;
- no write command was issued;
- no service was stopped or restarted for this capture;
- all four production services remained active after the run.
