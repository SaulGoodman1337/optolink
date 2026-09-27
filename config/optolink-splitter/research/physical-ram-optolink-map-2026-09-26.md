# Physical_READ RAM / Optolink map — 2026-09-26

Status: read-only hardware characterization on exact local VDensHO1 / 20C2. No write, erase, unlock, guessed selector or private opcode was sent.

## Full internal-RAM snapshot

`tools/physical-ram-snapshot.py` captured two complete Physical_READ passes over `0x0400..0x53FF` in fixed 32-byte blocks. Both passes completed with the 20C2 identity gate and current-alarm/fault-history guards. The range is 20,480 bytes; 841 bytes changed between the two passes and 19,639 remained stable.

The important result is not merely that the range is readable. A byte-exact copy of the request currently being executed was present in the returned RAM image:

```text
RAM 0x196C:
41 05 00 03 19 60 20 A1
```

That is the P300 Physical_READ request for `0x1960 / 0x20`, including checksum. Valid P300 response frames are also present in the same live RAM region. Therefore the Physical_READ address space exposes the controller's actual communication RAM, not just an opaque process-variable namespace.

## P300 communication ring

The live communication storage is centered on a 128-byte ring:

```text
ring base       0x19EE
ring end        0x1A6D
cursor 1        RAM 0x1A6E
cursor 2        RAM 0x1A70
base pointer    RAM 0x1A72 = 0x19EE
```

`tools/physical-comm-ring-probe.py` read only `0x1A60/32` for 24 transactions. In every sample cursor1-cursor2 was exactly 3 bytes. The cursors advanced by `0x2B` bytes per transaction and wrapped modulo `0x80`, while the base stayed `0x19EE`. Recent request/response bytes were visibly rotating through the ring.

## UART/DMA correlation

Fixed read-only SFR probes were added to `tools/vitotest-physical-read-guard.py`.

Observed state:

```text
0x0004..07  = 00 08 0C 20
0x0020..2F  = 1B 16 00 00 AA 03 00 00 08 00 00 00 15 00 00 00
0x0030..3F  = AF 19 00 00 A2 03 00 00 0F 00 00 00 15 00 00 00
0x03A0..AF  = 75 98 75 98 1C 07 BB 01 65 01 65 01 1D 07 C6 01
0x03B0..BF  = 02 98 02 98 02 05 30 01 0F 01 0A 01 EF 69 84 69
```

Using the M16C/62P SFR layout, the strongest correspondence is DMA1:

```text
SAR1   = 0x019AF
DAR1   = 0x003A2  (U0TB)
TCR1   = 0x000F
DM1CON = 0x15
DM1SL  = 0x0A      (UART0 transmit request)
```

UART0 mode byte `U0MR=0x75` is compatible with the observed Optolink 8-bit/even-parity/two-stop-bit framing. DMA1 therefore links the `0x19xx` RAM communication area directly to UART0 transmit. This is the first hardware-level map of the local Optolink transmit path.

DMA0 is distinct:

```text
SAR0   = 0x0161B
DAR0   = 0x003AA  (U1TB)
TCR0   = 0x0008
DM0CON = 0x15
DM0SL  = 0x0F      (UART1 transmit request)
```

This establishes a second serial/DMA path but does not by itself identify its external protocol.

## Communication descriptor foothold

Immediately after the P300 ring metadata, RAM contains a stable control/descriptor structure. Two fields are particularly strong:

```text
RAM 0x1A79:  A2 03        -> literal U0TB address 0x03A2
RAM 0x1A7D:  28 5C 0F 00  -> stable far pointer 0xF5C28
```

The literal U0TB value occurs only there in the captured RAM. The far pointer lies in the M30624 256-KiB program region. The exact semantic role of `0xF5C28` is not yet proven, but its placement next to the UART0 target inside the communication descriptor makes it a high-value handler/function-pointer candidate.

Other stable four-byte-aligned values in the program-address range include:

```text
RAM 0x066C -> 0xE0040
RAM 0x0AB8 -> 0xF0000
RAM 0x0B5C -> 0xF2420
RAM 0x0E98 -> 0xEA864
RAM 0x12D8 -> 0xE9C24
RAM 0x1390 -> 0xEADCB
RAM 0x1580 -> 0xD5805
RAM 0x18F8 -> 0xF5239
RAM 0x1C90 -> 0xCC701
RAM 0x1DCC -> 0xF80EC
RAM 0x1DF0 -> 0xFC0A1
```

These are candidates, not all automatically code pointers.

## Memory-map discriminator

The system-mode read returned `PM0=0x00`, `PM1=0x08`. For the M16C/62P layout this is consistent with single-chip operation and the normal high program-ROM region being enabled. PM10 is clear, so the low Block-A mapping at `0xF000..0xFFFF` is disabled. The previously observed regular Physical_READ patterns at `0xF000/0xFFF0` must therefore not be interpreted as a direct data-flash dump.

The readable Physical_READ RAM boundary `0x0400..0x53FF` also matches the 20-KiB internal-RAM layout of the M30624-class hypothesis. Together with the live P300 frame and SFR/DMA correlations, raw or near-raw MCU address mapping is now strongly established for low memory.

## Workstep-2 consequence

The search target is now much narrower. We no longer need to ask whether a Physical_READ RAM/mailbox exists: it does, and the Optolink ring plus UART0 DMA path are mapped.

The missing element for firmware acquisition is specifically one of:

1. a controller routine that accepts or constructs a 20-bit/far source address;
2. a selector variable that changes the source behind a readable low-memory window;
3. a ROM-to-RAM copy/monitor routine;
4. a private service request that invokes such a routine.

No such invocation has yet been sent or recovered. The next work should use the mapped communication descriptor and stable far-pointer cluster as the static/dynamic foothold rather than broad address or opcode probing.

## Offline stack/task-context clue

The paired RAM snapshots also contain two conspicuous `0x55` fill runs:

```text
0x1D45..0x1D9E  90 bytes
0x1E45..0x1E58  20 bytes
```

Immediately after the first long fill run, the `0x1DA0..0x1DFF` region is unusually dense in stable values that decode as addresses in the program-flash range. A 64-byte sliding classification finds six such values in `0x1DC0..0x1DFF`, the densest window in the complete 20-KiB capture. The following `0x1E01..0x1E3C` region changed substantially between the two passes.

This combination is consistent with a stack/task-context area that was prefilled with `0x55` and now contains return/code addresses, but that interpretation is not yet independently proven. It is useful because the communication-adjacent `0x18F8..0x191B` area independently contains the tight far-pointer cluster `0xF5239`, `0xF5281`, `0xF531E`, `0xF5339`.

The offline analyzer now reports the fill runs, pointer-dense windows, valid in-RAM P300 frames and stable aligned far-pointer candidates automatically.

## Descriptor follow-up: stable far callbacks, dynamic 0x1A79 field

A dedicated fixed-target read-only probe now samples the candidate structures at `0x18F8/32` and `0x1A70/32`. Sixteen consecutive observations completed with unchanged fault history and no active alarm.

Four far-range values were byte-identical in every sample:

```text
RAM 0x18F8 -> 0xF5239
RAM 0x1903 -> 0xF5281
RAM 0x190E -> 0xF531E
RAM 0x1A7D -> 0xF5C28
```

The first three are spaced by exactly 11 bytes, strongly suggesting a repeated RAM descriptor/table layout with a four-byte far value followed by seven bytes of per-entry state. The fourth value, `0xF5C28`, remains the strongest single callback/handler candidate adjacent to the communication ring.

A previous snapshot interpretation of `RAM 0x1A79 = 0x03A2` as a literal U0TB address is withdrawn. In the new run the same field was consistently `0x03B2`, while neighboring state changed. The Renesas M16C/62P SFR table maps `0x03A2` to U0TB but leaves `0x03B2` unassigned/reserved; therefore this RAM word cannot currently be classified as a stable UART-register pointer.

This correction makes the far callback cluster, not the `0x1A79` word, the higher-value static foothold. No selector or write was attempted.

## 2026-09-27 fixed P300 RX/TX parser workspace

Follow-up read-only self-observation resolves a fixed parser workspace immediately before the previously mapped 128-byte communication ring.

RAM 0x196C contains the request currently being executed. This was reproduced with multiple overlapping Physical_READ targets. Whenever the returned block included all eight bytes at 0x196C, the bytes matched the exact current request including checksum, for example target 0x1958 produced 41 05 00 03 19 58 20 99 and target 0x1960 produced 41 05 00 03 19 60 20 A1, 4/4 each.

RAM 0x19AE contains the complete response of the immediately preceding transaction. A Virtual_READ 0x00F8/2 followed by Physical_READ 0x19A0 showed at 0x19AE the exact response 41 07 01 01 00 F8 02 20 C2 E5 in 6/6 rounds. A Physical_READ 0x0400/32 followed by the same 0x19A0 sample showed at 0x19AE the corresponding long function-0x03 response in 6/6 rounds.

This lines up with the earlier DMA1 observation SAR1=0x019AF: with the response frame beginning at 0x19AE, an incrementing DMA source that has already transferred the first 0x41 byte naturally points at the second byte 0x19AF.

The address geometry is exact:

- 0x196C..0x19AB: 64-byte RX/current-request workspace;
- 0x19AC..0x19AD: two intervening bytes, observed as 2C 01 in the paired snapshots;
- 0x19AE..0x19ED: 64-byte TX/response workspace;
- 0x19EE..0x1A6D: the already proven 128-byte communication ring;
- 0x1A6E onward: ring cursors and scheduler/descriptor state.

A previously noticed valid-looking frame around 0x19C3 is not a second fixed response slot: 0x19C0 lies inside the payload range of a long Physical_READ response beginning at 0x19AE, while short Virtual_READ responses leave residual bytes there. This removes that false lead.

This fixed RX/TX/ring layout is now the strongest concrete controller-side parser map. The missing 20-bit bridge, if implemented in the running P300 service, should be sought as state or dispatch logic feeding these buffers rather than as a generic scheduler callback.

A separate function-type correlation test reduced the priority of callback 0xF5C28 as a Physical_READ handler. Its scheduler tick advanced in approximately 1000-tick steps and its linked-list position changed after both Virtual_READ and Physical_READ bursts; no Physical_READ-specific record state was observed. A reduced differential scan likewise found no persistent Virtual-vs-Physical state outside the communication ring in the sampled scheduler/stack blocks. The only strict differences were the two ring cursor words, explained by different frame geometry.

## 2026-09-27 Physical_READ scratch pipeline

Read-only overlap probes identify a parser-local request workspace at 0x192C..0x1933 and a fixed payload scratch at 0x1933..0x1952. The shared byte at 0x1933 is the active request checksum before becoming scratch byte zero.

The Physical_READ handler performs a forward copy from the requested 16-bit source into scratch. Overlapping source tests reproduce exact forward-memcpy alias behavior, and fixed-length tests prove that precisely the requested count is copied. The staged bytes then appear as the Physical_READ response payload beginning at 0x19B5 in the TX frame at 0x19AE.

This completes the low-memory data path: source(low16) -> scratch 0x1933 -> TX payload 0x19B5 -> DMA1/UART0. See physical-read-scratch-map-2026-09-27.md.