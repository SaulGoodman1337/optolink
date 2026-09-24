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
