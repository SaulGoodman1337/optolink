# Physical_READ scratch/copy map — 2026-09-27

Status: hardware-proven on local VDensHO1 / 20C2 using bounded read-only P300 requests only. No write function, guessed selector, private opcode, monitor entry or bootloader action was used.

## Fixed parser and transport geometry

Earlier probes established:

- fixed current RX/request workspace: `0x196C..0x19AB` (64 bytes);
- fixed previous TX/response workspace: `0x19AE..0x19ED` (64 bytes);
- communication ring: `0x19EE..0x1A6D`;
- DMA1 transmits the TX workspace through UART0.

The new self-observation probes resolve a second, parser-local workspace before those buffers.

## Local request workspace

A non-overlapping read of `0x1913/32` always exposes the request currently being processed at:

```text
0x192C..0x1933
```

For example a sample request for `Physical_READ 0x1913/32` appears as:

```text
41 05 00 03 19 13 20 <checksum>
```

The first seven bytes are directly visible at `0x192C..0x1932`. The final checksum byte occupies `0x1933`.

Thus there are two request representations:

```text
fixed RX/current request @ 0x196C
parser-local request     @ 0x192C
```

## Physical_READ payload scratch

`0x1933` is simultaneously the first byte of a Physical_READ payload scratch buffer.

The hardware behavior is consistent with:

```text
requested low16 source
        |
        | forward byte copy, requested length
        v
scratch 0x1933...
```

For the normal 32-byte probe size the scratch extent is:

```text
0x1933..0x1952
```

The overlap at `0x1933` explains why a scratch self-read replaces byte zero with the checksum of the current sample request while retaining bytes 1..31 from the previously staged payload.

For `Physical_READ 0x1933/32`, the current request checksum is `0x74`:

```text
41 05 00 03 19 33 20 74
```

After a prior source read, the scratch self-read therefore returns:

```text
74 | previous_payload[1:32]
```

## Forward-copy overlap proof

The strongest evidence is the behavior when the requested source overlaps the scratch destination.

With a known 32-byte source payload:

- `Physical_READ 0x1932/32` returns 32 copies of `0x20`. Source begins one byte before destination; the current request length byte `0x20` propagates through a forward byte copy.
- `Physical_READ 0x1933/32` returns current checksum in byte 0 and the prior staged payload in bytes 1..31.
- `Physical_READ 0x1934/32` returns prior payload bytes 1..31 shifted left by one byte, followed by zero.
- `Physical_READ 0x1940/32` returns exactly prior payload bytes 13..31 at sample offsets 0..18.
- `Physical_READ 0x1950/32` returns exactly prior payload bytes 29..31 at sample offsets 0..2.

For a distinctive source at `0x3300/32`:

```text
source:
38 36 1e cc b4 4d df 9e f8 ef ab b7 87 df fe 7d
87 08 88 48 23 32 91 83 b9 e6 d4 11 8e 3e 57 cf
```

`0x1940/32` reproducibly returned:

```text
df fe 7d 87 08 88 48 23 32 91 83 b9 e6 d4 11 8e 3e 57 cf
00 00 00 00 00 00 00 00 00 00 00 00 00
```

which is exactly `source[13:32]`.

The same geometry reproduced with unrelated payloads at `0x0400`, `0x0700`, and `0x53E0`.

## Length-controlled copy proof

The scratch was primed with the known stable `0x0700/32 = 64...` payload. A fixed source `0x3300` was then read using allowlisted lengths:

```text
1, 2, 7, 16, 29, 32
```

For every length, three repetitions produced exactly:

```text
scratch[1:N]  = source_payload[1:N]
scratch[N:32] = unchanged 0x64 prime bytes
```

Byte zero is the `0x74` checksum side effect of the subsequent `0x1933/32` self-read.

This proves that the Physical_READ path copies exactly the requested count into the fixed scratch rather than filling a fixed-size response block unconditionally.

## Scratch to TX response

The previous TX frame begins at `0x19AE`.

For Physical_READ responses the payload begins seven bytes later:

```text
TX frame    0x19AE
payload     0x19B5
```

For source `0x3300` and lengths `1, 7, 16, 29, 32`, the visible payload bytes in a subsequent `0x19A0/32` sample matched the just-read source byte-for-byte in every repetition.

The reconstructed pipeline is therefore:

```text
P300 RX frame @ 0x196C
        |
        v
parser-local request @ 0x192C..0x1933
        |
        | low16 source + requested length
        v
forward copy to scratch @ 0x1933
        |
        v
response payload @ 0x19B5
        |
        v
TX frame @ 0x19AE
        |
        v
DMA1 -> UART0
```

## Metadata immediately before the scratch

`0x1920..0x192B` is stable:

```text
04 00 01 02 00 00 00 00 08 00 04 00
```

Varying the current Physical_READ source across `0x190C..0x1913` did not change this 12-byte block. It is therefore not a RAM-resident source/destination/count descriptor for the copy.

A literal little-endian pointer to scratch address `0x1933` (`33 19`) does not occur anywhere in either complete `0x0400..0x53FF` snapshot. The scratch destination is therefore not represented as an obvious persistent RAM pointer.

## Implication for the missing 20-bit firmware bridge

This materially changes the model.

The ordinary Physical_READ implementation is now demonstrated to be a direct low-address copy primitive:

```text
16-bit request source -> fixed low-RAM scratch -> P300 response
```

There is no evidence in the mapped RAM state for a persistent high-address selector attached to this primitive.

For M16C program ROM above 64 KiB, the missing historical mechanism therefore most likely needs one of:

1. a separate far-copy routine that accepts a 20-bit source;
2. a private service/monitor that prepares a far source and copies into this or another low-RAM scratch;
3. a transient CPU-register-held far pointer not mirrored in ordinary RAM.

The result weakens models where the existing Physical_READ handler merely has an undiscovered static RAM bank/page byte beside its current low16 source.

## Tool

```text
tools/physical-read-scratch-probe.py
```

The tool has no arbitrary address input and permits only the fixed read-only addresses and lengths used to reproduce the scratch and TX geometry.