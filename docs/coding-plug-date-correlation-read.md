# Coding-plug date correlation: 0x1020 vs GFA P103-P105 - 2026-09-24

## Goal

Determine the raw encoding of the GFA coding-plug date fields P103/P104/P105 by comparing them with the normal GWG/main-regulation coding-plug date block.

This test is read-only.

## Exact VDensHO1 field layout

The exact VDensHO1 catalog defines the normal coding-plug date fields inside the 16-byte object at `0x1020`:

| Field | Object | Byte position | Conversion |
| --- | --- | ---: | --- |
| coding-plug day | `0x1020` | 2 | no conversion |
| coding-plug month | `0x1020` | 3 | no conversion |
| coding-plug year | `0x1020` | 4 | no conversion |

The already measured GFA values are:

```text
P103 day   = 0x14
P104 month = 0x0C
P105 year  = 0x04
```

The remaining question is whether the GFA and GWG views expose the same raw bytes and, if so, whether Vitosoft displays those numeric values directly.

## Bounded read-only sequence

Run on the production Optolink splitter:

```bash
echo "=== GWG/main-regulation coding-plug date block ==="
/usr/local/bin/optolink-debug request "r;0x1020;16;raw;False"

echo
echo "=== GFA date confirmation ==="
/usr/local/bin/optolink-debug request "gfaread;0x4050;1;raw;False"
/usr/local/bin/optolink-debug request "gfaread;0x4067;1;raw;False"
/usr/local/bin/optolink-debug request "gfaread;0x4068;1;raw;False"
/usr/local/bin/optolink-debug request "gfaread;0x4069;1;raw;False"
/usr/local/bin/optolink-debug request "gfaread;0x4050;1;raw;False"
```

## Live result - PASS / negative correlation 2026-09-24

The bounded read completed successfully:

```text
0x1020 = 00 00 FF FF FF 00 00 00 00 00 00 00 00 00 00 00

P80 opening = 20
P103 = 14
P104 = 0C
P105 = 04
P80 closing = 20
```

The source-defined GWG date positions are therefore:

```text
0x1020[2] day   = FF
0x1020[3] month = FF
0x1020[4] year  = FF
```

They do **not** match the GFA triplet `14 0C 04`. Because `FF` is not a valid calendar day or month, the normal GWG date slots are not populated with a usable date on this active plug. The exact vendor sentinel meaning of `FF` is not asserted.

This rejects the earlier hypothesis that `0x1020[2:5]` and P103-P105 are two views of the same raw date. On this appliance the GWG/main-regulation and GFA/fire-control date fields are separate datasets.

As a consequence, `0x1020` cannot decide whether GFA `P103=14` is displayed as decimal 20 or BCD 14. P103-P105 remain source-labelled day/month/year with raw `14 0C 04`; their final calendar rendering and year base need independent source/display evidence.

Evidence: [coding-plug-date-separation-2026-09-24-evidence.json](../config/optolink-splitter/research/vitosoft/coding-plug-date-separation-2026-09-24-evidence.json).

## Acceptance and interpretation

- Opening and closing P80 must both be `20`.
- The `0x1020` read must return 16 bytes.
- Compare `0x1020[2]`, `[3]`, `[4]` to P103/P104/P105.
- If they are byte-identical, the two software views are proven to expose the same raw day/month/year triplet.
- Do not convert the year to 2000+raw until that display rule is source-backed.
- Do not reinterpret raw `0x14` as BCD 14 if the normal no-conversion view independently confirms direct numeric 20.

No write or coding reload is part of this test.
