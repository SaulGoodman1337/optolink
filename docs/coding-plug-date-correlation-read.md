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

## Acceptance and interpretation

- Opening and closing P80 must both be `20`.
- The `0x1020` read must return 16 bytes.
- Compare `0x1020[2]`, `[3]`, `[4]` to P103/P104/P105.
- If they are byte-identical, the two software views are proven to expose the same raw day/month/year triplet.
- Do not convert the year to 2000+raw until that display rule is source-backed.
- Do not reinterpret raw `0x14` as BCD 14 if the normal no-conversion view independently confirms direct numeric 20.

No write or coding reload is part of this test.
