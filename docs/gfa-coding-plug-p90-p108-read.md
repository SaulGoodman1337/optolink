# GFA coding-plug P90/P100-P108 read-only correlation - 2026-09-24

## Goal

Correlate the GFA/fire-control coding-plug view with the normal regulation/coding-card view and, later, with side-labelled physical 24C04 EEPROM dumps.

No write is used in this procedure.

## Source-backed targets

For the locally selected GFA branch (P80 = `0x20`):

| Parameter | Address | Meaning | Conversion |
| --- | --- | --- | --- |
| P90 | `0x405A` | coding-plug FA type / FA42 | raw |
| P100 | `0x4064` | minimum-power representation | raw x 0.3922 |
| P101 | `0x4065` | VI coding-plug identity 1 | raw |
| P102 | `0x4066` | VI coding-plug identity 2 | raw |
| P103 | `0x4067` | coding-plug date day | raw |
| P104 | `0x4068` | coding-plug date month | raw |
| P105 | `0x4069` | coding-plug date year | raw |
| P106 | `0x406A` | coding-plug CRC diagnostic | raw |
| P107 | `0x406B` | coding-plug identity FA40 | raw |
| P108 | `0x406C` | coding-plug identity FA41 | raw |

All are one-byte read-only GFA_READ objects in the recovered local branch. P106 is a diagnostic CRC value, not a recovered checksum algorithm.

The normal regulation side is sampled in the same session window:

- `0x1010 / 7`: active coding-plug part-number block, previously measured as ASCII `7833971`;
- `0x7656 / 4`: coding-card summary, previously measured as `20 15 02 01` and documented as revision notation `2015:0201`.

## Bounded read-only sequence

```bash
echo "=== Regulation-side coding plug ==="
/usr/local/bin/optolink-debug request "r;0x1010;7;raw;False"
/usr/local/bin/optolink-debug request "r;0x7656;4;raw;False"

echo
echo "=== P80 opening guard ==="
/usr/local/bin/optolink-debug request "gfaread;0x4050;1;raw;False"

echo
echo "=== GFA coding-plug diagnostics ==="
/usr/local/bin/optolink-debug request "gfaread;0x405A;1;raw;False"   # P90
/usr/local/bin/optolink-debug request "gfaread;0x4064;1;raw;False"   # P100
/usr/local/bin/optolink-debug request "gfaread;0x4065;1;raw;False"   # P101
/usr/local/bin/optolink-debug request "gfaread;0x4066;1;raw;False"   # P102
/usr/local/bin/optolink-debug request "gfaread;0x4067;1;raw;False"   # P103
/usr/local/bin/optolink-debug request "gfaread;0x4068;1;raw;False"   # P104
/usr/local/bin/optolink-debug request "gfaread;0x4069;1;raw;False"   # P105
/usr/local/bin/optolink-debug request "gfaread;0x406A;1;raw;False"   # P106
/usr/local/bin/optolink-debug request "gfaread;0x406B;1;raw;False"   # P107
/usr/local/bin/optolink-debug request "gfaread;0x406C;1;raw;False"   # P108

echo
echo "=== P80 closing guard ==="
/usr/local/bin/optolink-debug request "gfaread;0x4050;1;raw;False"
```

## Live result - PASS 2026-09-24

The bounded production read completed successfully:

```text
0x1010 = 37 38 33 33 39 37 31  -> ASCII 7833971
0x7656 = 20 15 02 01

P80 opening = 20
P90  = 00
P100 = 63
P101 = 15
P102 = 01
P103 = 14
P104 = 0C
P105 = 04
P106 = D6
P107 = 02
P108 = 00
P80 closing = 20
```

Source-backed conversion of P100 gives `99 * 0.3922 = 38.8278 %`.

Three values from the normal `0x7656 = 20 15 02 01` summary reappear directly in the separate GFA identity registers: `P101=15`, `P102=01`, and `P107=02`. This is strong cross-domain correlation, but the current public extraction does not retain the byte positions of the four `0x7656` subfields, so a field-by-field assignment is not yet claimed.

P103/P104/P105 are source-labelled day/month/year. With direct unsigned-byte interpretation they are `20 / 12 / 4`; a BCD reading would be `14 / 12 / 04`. The exact vendor display encoding and year base remain unresolved, so neither calendar date is promoted to fact yet.

P106 is raw `0xD6`. A bounded check against common CRC-8 presets over the obvious adjacent GFA byte sequences produced no match. That is only a negative heuristic result; it does not identify or exclude a proprietary checksum algorithm.

An exact binary scan of both saved spare-chip1 images found no contiguous occurrence of the full live vector `00 63 15 01 14 0C 04 D6 02 00`, the P100-P108 tail, `15 01`, `14 0C 04`, `20 12 04`, or `D6 02 00`. This rejects a simple flat contiguous copy in those two specific captures, not a transformed/mirrored mapping or a mapping to the still-unread second EEPROM.

Evidence: [gfa-coding-plug-p90-p108-live-2026-09-24-evidence.json](../config/optolink-splitter/research/vitosoft/gfa-coding-plug-p90-p108-live-2026-09-24-evidence.json).

## Acceptance criteria

- regulation-side reads return success;
- opening and closing P80 both return raw `20`;
- every P90/P100-P108 response is a successful one-byte value;
- no value is interpreted from a failed/quarantined response;
- no write or coding mutation is performed.

## Interpretation order

1. Preserve all raw bytes exactly.
2. Convert only P100 with its source-backed factor `0.3922`.
3. Check whether P103/P104/P105 form a plausible date, but do not force BCD/decimal notation without matching source evidence.
4. Compare P101/P102/P107/P108 with the `0x7656` summary and active part/revision data.
5. Treat P106 only as a correlation byte until a checksum algorithm is independently recovered.
6. Later compare this semantic vector with both EEPROM sides of the same physical coding plug.

This test is intended to narrow the dual-EEPROM/domain hypothesis; it does not assign f01 or f02 to GWG/GFA by itself.
