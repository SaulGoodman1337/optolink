# P300 EEPROM_READ map — 2026-09-27

Status: hardware-proven, read-only characterization on the local VDensHO1 / 20C2 controller. No EEPROM write, erase, unlock or private opcode was used.

## Capability result

P300 function `0x05 = EEPROM_READ` is implemented on the local controller. A source-backed historical read at `0x0017/2` returned stable `FC 3A` in 3/3 repetitions. The corresponding source-backed `PORT_READ 0x33` test at `0x0001/1` was rejected with controller error payload `05` in 3/3 repetitions.

EEPROM_READ is distinct from Physical_READ. At the same addresses:

- `EEPROM_READ 0x0005/1 -> 47`, while `Physical_READ -> 08`;
- `EEPROM_READ 0x0017/2 -> FC 3A`, while `Physical_READ -> 97/98 00`.

All tests passed current-fault and fault-history guards.

## Stable low EEPROM/service page

A complete two-pass read of `EEPROM_READ 0x0000..0x00FF` in 16-byte blocks succeeded without errors. The two 256-byte passes were byte-identical (`0/256` changed bytes), proving a persistent, structured address space rather than volatile RAM.

## Address-width and segmentation

The P300 request's high address byte is significant: `0x0005`, `0x0105` and `0x1005` returned different stable values, while `0xFF05` returned controller error `31 01`.

A sparse `x005` scan showed a segmented validity pattern. Successful high segments included `0x1000`, `0x2000`, `0x5000`, `0x6000`, `0x9000`, `0xA000`, `0xD000` and `0xE000`; intervening groups such as `0x3000/0x4000`, `0x7000/0x8000`, `0xB000/0xC000` and `0xF000` rejected the sample with `31 01`.

All successful high segment bases returned the same 16-byte fingerprint:

```text
80 13 10 91 05 10 00 40 13 05 10 00 40 13 17 D2
```

This is therefore a segmented service/alias map, not a linear 64-KiB EEPROM or ROM view.

## Active coding-plug window

The high-segment fingerprint is byte-identical to offset `0x0000` of the independently acquired active coding-plug image `7173085-3_CHL-G_3F1_94V-0_f01.bin`.

A dedicated bounded verifier then read the complete 512-byte interval `0x1000..0x11FF` in chunks of at most 55 bytes. Every returned byte matched the existing active coding-plug dump: **512/512 bytes identical**.

Thus, on this exact controller:

```text
P300 EEPROM_READ 0x1000..0x11FF
        -> active coding-plug image f01[0x000..0x1ff]
```

This classifies the high EEPROM_READ window as coding-plug access, not program-ROM firmware access.

## SFR discriminator result

A separate paired Virtual_READ/Physical_READ scan covered the complete `0x0000..0x03FF` SFR range. With unequal response lengths, DMA1 TCR recorded the expected TX frame-length difference (`8` vs `38`), and free-running timer registers around `0x0380/0x0390` produced timing-dependent differences.

When the Physical_READ stimulus was reduced to the same two-byte payload length as the Virtual_READ control, the DMA1 difference disappeared completely. DMA0, DMA1, UART0/1 and DMA-select state showed no disjoint function-specific values. The remaining differences were confined to running timer registers and were non-constant.

Therefore no persistent Physical_READ-specific handler/dispatch state was found in the sampled SFR space after controlling for frame length and timing.

## Consequence for firmware readout

Two candidate directions are now closed or reclassified:

1. post-request SFR state does not expose a stable Physical_READ-specific handler pointer/selector;
2. P300 `EEPROM_READ 0x05` does expose a useful separate persistent space, but its high service window is the active coding plug rather than MCU program ROM.

The missing historical >16-bit firmware bridge remains most consistent with a separate/private monitor or far-copy service rather than an ordinary catalogued read function.

## Follow-up: BE_READ and second coding-plug image

The complete Vitosoft event catalogue contains 20 `BE_READ` definitions, all fixed one-byte reads without PrefixRead. A bounded local capability test used three representative source-defined addresses (`0x0008`, `0x0057`, `0x00F5`). P300 `BE_READ / 0x35` returned error payload `05` for every request (3/3 per address), with unchanged fault history. This read family is therefore not locally exposed through those documented shapes.

The active coding-plug `f02` image begins `FF 72 00 02 00 00 00 FF ...`, distinct from f01. Fixed EEPROM_READ checks at neighboring 512-byte-style bases did not expose it: `0x1200`, `0x1600`, `0x1800`, `0x1A00`, `0x1C00`, `0x1E00` returned `31 01`, while `0x1400` repeated the f01 alias signature. No adjacent second-chip linear window was found.

## Full 16-bit aligned map — 2026-09-27

A guarded read-only sweep covered the complete 16-bit request address space with
aligned 16-byte requests:

```text
0x0000/16
0x0010/16
...
0xFFF0/16
```

That is 4096 request starts and, for successful blocks, byte coverage of the
corresponding 16-byte interval. The run completed with unchanged current-fault
and fault-history guards and restored all production services.

Result:

```text
tested blocks:      4096
successful blocks:   640
successful bytes:  10240
```

Successful aligned ranges:

```text
0000-07FF

1000-11FF
1400-15FF

2000-21FF
2400-25FF

5000-51FF
5400-55FF

6000-61FF
6400-65FF

9000-91FF
9400-95FF

A000-A1FF
A400-A5FF

D000-D1FF
D400-D5FF

E000-E1FF
E400-E5FF
```

Important boundary: an aligned 16-byte rejection does not prove that every
shorter or unaligned request touching that interval is rejected. This map is a
complete aligned /16 characterization, not proof of universal inaccessibility
for every other request shape.

### Exact f01 alias windows

Every 512-byte high window listed below is byte-for-byte identical to the
independently captured active f01 image
`7173085-3_CHL-G_3F1_94V-0_f01.bin`:

```text
1000-11FF   1400-15FF
2000-21FF   2400-25FF
5000-51FF   5400-55FF
6000-61FF   6400-65FF
9000-91FF   9400-95FF
A000-A1FF   A400-A5FF
D000-D1FF   D400-D5FF
E000-E1FF   E400-E5FF
```

Reference SHA256:

```text
6b60b5b9de3dc90cbbe2bba2f7878ef4db36e117577f3402970170746e5cf63f
```

All 16 windows reproduce all 512 bytes exactly. The high address field is
therefore acting as a decoded/aliased service selector around the coding-plug
resource, not as a linear physical EEPROM address.

### f02 result after full map

The independently captured active f02 image has SHA256:

```text
e20316f2053b5002fc52b213b7f6bd7f8b63944a3202bf4b865c999091113e9a
```

No successful aligned 512-byte window in the full 16-bit scan matches f02.
This rules out an obvious linear f02 mirror under the tested EEPROM_READ /16
request shape. It does not rule out shorter/unaligned addressing, a separate
function code, a private monitor path or a controller-side transformed view.

## Low 2-KiB EEPROM/service table

The full scan showed that `0x0000..0x07FF` is continuously readable with
16-byte requests. A dedicated two-pass verifier then reread all 2048 bytes.
The two passes were identical:

```text
changed bytes: 0 / 2048
SHA256:
5308cae96adb984c7cdf0cf24819f3fff28df808e44e5cfaa3ed152b38ecf177
```

This proves the low region is stable persistent/service data for the measured
state.

### Protected value/complement representation

A stronger structure appears in the low map. Every two-byte pair from raw
address `0x0000` through `0x0597` satisfies:

```text
byte0 XOR byte1 == FF
```

That is 716 complete value/complement pairs with no exception in that range.
The remaining `0x0598..0x07FF` bytes are all `FF`.

Collapsing each pair to its primary byte therefore yields a 716-byte logical
table. One exact cross-view identity appears at collapsed offset `0x0028`:

```text
raw 0x0050..0x0057:
20 DF 15 EA 02 FD 01 FE

primary bytes:
20 15 02 01

P300 0x7656:
20 15 02 01
```

Thus the low EEPROM_READ table contains an exact protected copy of the
controller coding-card summary `0x7656`.

A second correlation appears at raw `0x04D0..0x04D3`:

```text
02 FD 15 EA
 -> primary bytes 02 15
```

That equals the known two-byte identity tuple at the start of `0x1040`
(`P107 | P101`). This is a useful correlation, but its semantic field
assignment inside the low table is not yet independently source-proven.

### What is not present in the low map

Neither the raw 2048-byte image nor the collapsed logical table contains an
exact copy of:

- ASCII `7833971`;
- the complete active f01 blocks `0x1010`, `0x1020`, `0x1030`,
  `0x1040`, `0x1050`, `0x1060`, `0x1070`, `0x1080`, `0x1090`
  or `0x10C0`;
- the direct f02/GFA P101..P106 vector `15 01 14 0C 04 D6`;
- the P100..P108 vector `63 15 01 14 0C 04 D6 02 00`;
- the P90/P100..P108 vector `00 63 15 01 14 0C 04 D6 02 00`.

The low area is therefore not a flat f01 or f02 image. It is best classified
for now as a protected controller service/configuration table that includes at
least selected coding-card identity material.

Machine-readable evidence:
[p300-eeprom-full-map-2026-09-27-evidence.json](p300-eeprom-full-map-2026-09-27-evidence.json).
