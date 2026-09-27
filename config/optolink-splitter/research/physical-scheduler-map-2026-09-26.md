# Physical_READ scheduler/callback map — 2026-09-26

Status: read-only characterization on exact local VDensHO1 / 20C2. No write, selector, private opcode, erase, unlock or bootloader action was used.

## Core finding

The previously identified far-pointer cluster is now structurally resolved as an 11-byte linked scheduler/timer record format.

The record layout supported by the live data is:

~~~text
offset  size  interpretation
+0      2     next/link pointer in low RAM
+2      4     far callback/function address
+6      2     16-bit time/tick field
+8      2     interval/period-like value
+10     1     status/enable-like byte
~~~

This layout is independently visible at multiple non-contiguous RAM nodes and in a four-record contiguous table beginning at 0x18F6.
## Four contiguous records

The four records around 0x18F6 are:

| Node | Next/link | Callback | Period-like | Flag |
| --- | --- | --- | ---: | ---: |
| 0x18F6 | dynamic RAM link | 0xF5239 | 2000 | 1 |
| 0x1901 | dynamic RAM link | 0xF5281 | 250 | 0 |
| 0x190C | dynamic RAM link | 0xF531E | 2000 | 0 |
| 0x1917 | dynamic RAM link | 0xF5339 | 1100 | 0 |

The node starts are exactly 11 bytes apart. The earlier far-pointer-only view at 0x18F8/0x1903/0x190E/0x1919 was therefore observing the callback field at offset +2 inside these records.

## Tick-rate proof

A dedicated bounded read-only timing run sampled these records against host monotonic time.

For the actively changing tick fields, measured rates were:

~~~text
record 0 mean 1004.822 ticks/s
record 1 mean 1005.328 ticks/s
record 3 mean 1005.165 ticks/s
~~~

The small measurement spread is compatible with a nominal 1 kHz controller time base plus non-atomic sequential read overhead.

The phase differences between records remained nearly constant:
- record0 - record1 approximately 0x0642 ticks;
- record3 - record1 approximately 0x02D4 ticks.

This makes a timer/scheduler interpretation substantially stronger than a generic selector/mailbox interpretation for this table.
## Additional linked records

The same 11-byte structure is present at multiple RAM locations found independently in both full snapshots:

| Node | Callback | Period-like | Flag |
| --- | --- | ---: | ---: |
| 0x1139 | 0xE97F1 | 125 | 1 |
| 0x1144 | 0xE9815 | 115 | 0 |
| 0x12D6 | 0xE9C24 | 1000 | 1 |
| 0x12E1 | 0xE9CA6 | 10000 | 1 |
| 0x138E | 0xEADCB | 100 | 1 |
| 0x160F | 0xF157F | 800 | 0 |
| 0x18F6 | 0xF5239 | 2000 | 1 |
| 0x1901 | 0xF5281 | 250 | 0 |
| 0x190C | 0xF531E | 2000 | 0 |
| 0x1917 | 0xF5339 | 1100 | 0 |
| 0x1A7B | 0xF5C28 | 1000 | 1 |
| 0x1D25 | 0xFA711 | 2500 | 1 |

Some broad offline pattern matches elsewhere are intentionally excluded from this table because they lack the same dynamic/link behavior and may be accidental byte patterns.

## Live linked-list behavior

A second fixed-address read-only run sampled known nodes and the four table links.

The +0 word changed between other known node addresses while each node's callback and period-like field remained stable. Examples observed include links among:

~~~text
0x1139
0x1144
0x12D6
0x12E1
0x138E
0x18F6
0x1A7B
0x1D25
~~~

This is direct evidence of a dynamically maintained low-RAM linked structure rather than four unrelated static pointers.
For example, node 0x1A7B remained structurally:

~~~text
next/link     dynamic
callback      0xF5C28
tick          0x0000 in the sampled run
period-like   1000
flag          1
~~~

while its next/link word moved among other known nodes.

## Consequence for Arbeitsschritt 2

The callback cluster is no longer a good candidate for the missing 20-bit selector itself.

Instead it is now valuable as a firmware-control-flow map:
- the 0xFxxxx values are strongly consistent with scheduler callback/function addresses;
- 0xF5C28 remains communication-adjacent and therefore a high-value callback to identify if a firmware image becomes available;
- the low-RAM next/link pointers expose scheduler/list activity but do not themselves provide a ROM page/bank selector.

This narrows the missing firmware-read mechanism further: search should move away from treating 0x18F6..0x1917 as selector records and toward finding a separate memory-copy/monitor/service state whose callback may be reachable from this scheduler/control-flow infrastructure.

## Reproducible tooling

Committed tools:
- tools/physical-scheduler-probe.py — fixed live read-only timing/table probe;
- tools/analyze-physical-scheduler.py — offline scanner/classifier for raw RAM snapshots.

All live runs completed with the existing 20C2 identity, active-fault and fault-history guards.