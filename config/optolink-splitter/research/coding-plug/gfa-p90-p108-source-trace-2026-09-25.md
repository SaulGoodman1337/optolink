# GFA coding-plug P90/P100/P107/P108 source trace - 2026-09-25

## Goal

Narrow the still-unresolved physical f02 mapping for GFA parameters P90, P100,
P107 and P108 without guessing from value equality.

This follows the active 7833971 physical capture, where f02 offsets
`0x0E..0x13` are already proven to equal live GFA P101..P106.

## Private-source trace

A first full Python text scan of the verified Vitosoft v6 archive was too slow
for the available GitHub runner and was externally cancelled after about five
minutes.

The workflow was replaced by three bounded fast grep slices:

- SQL exports;
- normalized metadata / all-devices;
- IL dumps.

All three completed successfully. A fourth narrow host-path trace over
`vsmInterfaceCommon`, `vsmInterfaceCore` and communication IL also completed
successfully.

Private workflow commits:

- fast sliced trace: `739088b4bb664c7afd32aa4b2a0acec820d90531`
- GFA host-path trace: `8fccc3cd045804bfae975693bc9c2835ffdd18f3`

## Exact VDensHO1 source semantics

The normalized VDensHO1 metadata confirms:

| Parameter | GFA address | Type | Conversion | Source meaning |
| --- | --- | --- | --- | --- |
| P90 | `0x405A` | Byte | none | coding-card / BCU type `FA42` |
| P100 | `0x4064` | Int | raw x 0.3922 % | minimum output |
| P101 | `0x4065` | String/ByteArray | none | VI coding-card identity 1 |
| P102 | `0x4066` | String/ByteArray | none | VI coding-card identity 2 |
| P103 | `0x4067` | Byte | none | coding-card day |
| P104 | `0x4068` | Byte | none | coding-card month |
| P105 | `0x4069` | Byte | none | coding-card year |
| P106 | `0x406A` | Byte | none | VI coding-card CRC diagnostic |
| P107 | `0x406B` | String/ByteArray | none | coding-card identity `FA40` |
| P108 | `0x406C` | String/ByteArray | none | coding-card identity `FA41` |

All are read-only `GFA_READ` objects in the local VDensHO1 branch.

The source labels therefore make P90/P107/P108 explicitly **FA42/FA40/FA41
identity/type fields**, not generic EEPROM-byte labels.

## Host-path result

Static interface metadata exposes two separate function-code layers:

- abstract Vitosoft `FunctionCodes.GFA_READ = 0xC9`;
- VS1 wire-side `VS1FunctionCode.GFA_Read = 0x6B`;
- corresponding VS1 GFA write code is `0x68`.

The narrow host IL trace did **not** recover a host-side table that maps
P90/P100/P107/P108 to physical 24C04 offsets. This is negative evidence only:
it means no such mapping was found in the traced interface-code contexts, not
that no mapping exists inside GFA firmware.

## Physical-dump implications

### P101..P106

Already proven on active 7833971:

```text
f02 0x0E..0x13 = 15 01 14 0C 04 D6
GFA P101..P106 = 15 01 14 0C 04 D6
```

This remains direct same-plug hardware evidence.

### P107

Known regulation-side / live identity sequence across the three plugs:

```text
7823363: P107 = 02
7833968: P107 = 04
7833971: P107 = 02
```

The two old f02 images are byte-identical throughout `0x000..0x0E1`, despite
their P107 values differing 02 vs 04.

Therefore P107 is **not represented as a simple raw value byte in the main
f02 data region**. The differing tail/control area from `0x0E2` onward also
contains no direct 02/04 field sequence that can be assigned safely.

The source label `FA40` plus this physical differential supports treating
P107 as a GFA identity result that may be derived/decoded rather than a flat
EEPROM byte.

### P108

Active live P108 is `00`, but zero occurs at many physical positions.
No unique physical offset is defensible from one active value.

### P90

Active live P90 / FA42 is `00`. Again, zero is too common in f02 for a unique
physical assignment.

### P100

Active live P100 raw is `0x63`, corresponding to about 38.83%.

The active f02 contains `0x63` at four positions:

```text
0x2B
0x46
0x7D
0x98
```

The repeated-record structure explains the pairing:

- `0x2B` and `0x7D` are 82 bytes apart;
- `0x46` and `0x98` are 82 bytes apart.

All three available f02 images contain the same values at these positions, so
the current physical set provides no differential discriminator between the two
candidate field positions inside each repeated record.

**Do not assign P100 to one of these offsets by value equality alone.**

## Current conclusion

Resolved:

- f01 = main-regulation / GWG coding-plug storage;
- f02 = GFA/fire-control coding-plug storage;
- f02 `0x0E..0x13` = P101..P106;
- P90/P100/P107/P108 source meanings and GFA addresses are exact;
- GFA_READ transport is a dedicated path (`0xC9` abstract, VS1 `0x6B`).

Still unresolved:

- physical f02 offset/encoding of P90 / FA42;
- physical f02 offset/encoding of P100 minimum output;
- physical f02 offset/encoding or derivation of P107 / FA40;
- physical f02 offset/encoding or derivation of P108 / FA41.

## Next discriminator

The safest next step is not another blind EEPROM guess.

Useful evidence would be one of:

1. a physical f02 dump from a coding plug whose P100 or FA40/41/42 live values
   are independently known and differ from 7833971;
2. source/firmware code from the GFA that decodes FA40/41/42 or P100;
3. a small, source-backed set of additional static GFA coding parameters whose
   live values can fingerprint the two repeated f02 records.

Until then, leave P90/P100/P107/P108 physically unresolved.


## Live static discriminator result

A fresh production read-only capture was performed after the source trace.

Two identical rounds returned:

```text
P80=20 P81=02 P82=06 P83=76
P90=00 P100=63
P101=15 P102=01 P103=14 P104=0C P105=04 P106=D6
P107=02 P108=00
```

This provides a new physical discriminator:

- active f02 contains no `20`, no `06`, and no `76` byte anywhere;
- therefore P80 (BCU chip ID), P82 (software revision), and P83 (appliance
  configuration) are not flat f02 EEPROM bytes;
- P81=02 cannot be assigned by value coincidence because the surrounding
  source-defined identity/config fields are demonstrably non-linear with
  respect to f02;
- P101..P106 remain the directly proven coding-plug EEPROM fields;
- P100 remains ambiguous between the two repeated-record field positions;
- P90/P107/P108 remain identity/type results whose physical encoding or
  derivation is unresolved.

This narrows the architecture: GFA_READ exposes both **GFA internal identity /
firmware state** and **coding-plug-derived values**. Do not assume every Pxx
entry maps one-to-one onto the f02 24C04.
