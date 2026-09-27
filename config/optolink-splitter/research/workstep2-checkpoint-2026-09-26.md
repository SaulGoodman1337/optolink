# Arbeitsschritt 2 checkpoint — 2026-09-26

Status: consolidated checkpoint of the firmware-readout / Physical_READ workstream on the exact local VDensHO1 / 20C2 controller. This file separates hardware-proven observations, source-backed architecture, hypotheses and closed leads.

## Safety / execution boundary

All new live work in this phase was read-only. No unknown write opcode, erase, unlock, bootloader entry, guessed selector, private service invocation or arbitrary function sweep was sent to the production controller.

Every bounded P300 maintenance-window test used:
- positive 20C2 identity control;
- exclusive serial ownership;
- fixed request allowlists;
- current GFA/alarm checks;
- byte-for-byte system fault-history guards;
- restoration of splitter, party-emulator and schedule-manager services.

The production controller remained operational after the documented runs.

## Historical target and problem statement

OpenV/KarlKoch documentation establishes that a V200KW2 / identification 2098 used an M30612MC and that its approximately 128 KiB program software had been read through Optolink with additional effort. The surviving public material does not preserve the exact selector/monitor/copy sequence.

The fundamental architecture problem is address width: M16C program ROM occupies the high 20-bit address space, while normal Optolink/Vitosoft event addressing is 16 bit.
## Normal Vitosoft path: closed as >16-bit carrier

Recovered Vitosoft core types and serializers make the normal event-address boundary explicit:

~~~text
EventType.Address      ushort
MRKey Min/MaxAddress   ushort
MultiRequest pAddress  ushort
BaseDataService        Convert.ToUInt16(address, 16)
~~~

No recovered serializer takes byte 2/3 from EventType.Address or shifts an address by 16/24 bits. Earlier broad hits on bytes[2]/bytes[3] were 32-bit data values, not wider addresses.

The VitosorpAccessController is useful architectural precedent: it rewrites a request to fixed endpoints 0xA400/0xA401 and places a secondary address in the payload. However that secondary address is still only 16 bit.

Exact V200KW2/2098 exceptional reads are limited to reset RPCs at 0xA051, RPCWink at 0xA000 and one undefined/write-only reset object. None exposes ROM/page/bank/window/copy semantics.

Conclusion: the missing bridge is outside the ordinary Vitosoft EventType address field.

## VitoTest / historical GWG status

VitoTest 1.6, 1.7 and 1.8 were statically compared. The built-in simulator dispatcher already contains the same old physical/GWG canned cases in 1.6 and 1.7; 1.8 adds explicit GWG identity selection but no hidden ROM/page/bank/monitor path.

Known simulator cases include physical-style reads at BD, 2F, 3F and 9B plus one write-shaped C8 example. They are simulator behavior, not proof of a firmware service.

The native vsmGWG99Native helper was also closed: CheckGWG constructs ordinary C7 F8 04 identification and accepts 2053/2054-family replies. No selector or memory-monitor path is present there.
## Physical_READ on exact local 20C2: major positive result

P300 Physical_READ function 0x03 is hardware-verified on the exact local controller and is demonstrably distinct from Virtual_READ.

Source-backed and architecture-discriminator addresses succeeded, including:
- old VitoTest/GWG physical addresses;
- 0x0400/16;
- 0x53F0/16;
- 0xF000/16;
- 0xFFF0/16.

At 0x0400 and 0x53F0, corresponding Virtual_READ requests are rejected while Physical_READ succeeds. Therefore Physical_READ is not merely another encoding of the normal datapoint namespace.

A full two-pass read-only capture of 0x0400..0x53FF returned 20,480 bytes per pass. 841 bytes changed and 19,639 remained stable.

Most importantly, the returned image contains the exact P300 request then being executed:

~~~text
RAM 0x196C:
41 05 00 03 19 60 20 A1
~~~

Valid P300 response frames are present in the same RAM area. This proves that Physical_READ exposes actual live controller communication RAM or a near-raw MCU mapping.

The readable 0x0400..0x53FF span also matches a 20 KiB internal-RAM layout expected for the M30624-class working hypothesis.
## Optolink communication ring

The P300 communication storage has been resolved as a 128-byte circular buffer:

~~~text
ring base       0x19EE
ring end        0x1A6D
cursor 1        0x1A6E
cursor 2        0x1A70
base pointer    0x1A72 = 0x19EE
~~~

A 24-transaction read-only probe showed both cursors advancing and wrapping modulo 0x80 with a constant three-byte separation. Recent request/response bytes visibly rotate through this ring.

This removes the earlier uncertainty about whether a controller-side mailbox exists: a live Optolink communication mailbox/ring is now hardware-proven.

## SFR / DMA transport correlation

Read-only SFR observations map the Optolink path into M16C-style UART/DMA state.

Observed DMA1 state:

~~~text
SAR1   0x019AF
DAR1   0x003A2
TCR1   0x000F
DM1CON 0x15
DM1SL  0x0A
~~~

Together with UART0 mode byte U0MR=0x75, this is compatible with the observed Optolink serial path and links the 0x19xx RAM communication region to UART0 transmission.

DMA0 separately points from RAM 0x0161B toward 0x03AA, establishing a second serial/DMA path whose external role is not yet proven.
## Important correction: 0x1A79 is not a proven UART pointer

An earlier snapshot happened to contain A2 03 at RAM 0x1A79, which numerically equals M16C U0TB address 0x03A2. That was initially classified as a possible literal UART target pointer.

The dedicated descriptor follow-up disproved the stability of that interpretation. The same field repeatedly returned B2 03 = 0x03B2 in the later run.

Renesas documents 0x03A2 as U0TB, while 0x03B2 is unassigned/reserved in the relevant M16C/62P SFR map. Therefore RAM 0x1A79 must currently be treated as dynamic state, not a stable UART-register pointer.

The documentation has been corrected accordingly.

## Stable far-pointer / callback cluster

The strongest current static foothold is a set of stable 20-bit program-range values embedded in structured RAM.

A dedicated 16-sample fixed-target probe found these values byte-identical on every transaction:

~~~text
RAM 0x18F8 -> 0xF5239
RAM 0x1903 -> 0xF5281
RAM 0x190E -> 0xF531E
RAM 0x1A7D -> 0xF5C28
~~~

The first three RAM locations are exactly 0x0B bytes apart. This strongly suggests a repeated 11-byte descriptor/table record containing a far value plus per-entry state.

A fourth nearby F5xxx value also exists in the original snapshot:

~~~text
RAM 0x1919 -> 0xF5339
~~~

The 0xF5C28 value is adjacent to the communication-ring descriptor area and remains the highest-value single handler/callback candidate.
Other stable far-range values exist elsewhere in RAM, including clusters around 0x1DA1..0x1DDD. These are candidates only; not every aligned value in the program range is automatically a function pointer.

## Task/stack-like region

The paired RAM snapshots contain long 0x55 fill runs near 0x1D45..0x1D9E and 0x1E45..0x1E58. The first is followed by a far-pointer-dense stable window around 0x1DC0..0x1DFF, while adjacent memory changes between passes.

This is consistent with a prefilled task/stack region containing saved program addresses, but no hardware stack pointer or task identity has yet been proven.

## High-address Physical_READ caveat

Physical_READ succeeds at high 16-bit addresses such as 0xF000 and 0xFFF0, but the returned regular patterns are not evidence of direct program/data flash.

System-mode bytes were observed as PM0=0x00 and PM1=0x08. Under the M16C/62P working map, the low Block-A mapping is not enabled. Therefore the F000/FFF0 data must not be interpreted as a direct flash dump.

Physical_READ is now strongly established as raw/near-raw low-memory access, but its numeric 16-bit address must not automatically be equated to the complete 20-bit MCU bus.

## Current architecture model

The evidence now supports this model:

~~~text
Optolink P300
    |
Physical_READ 0x03
    |
    +--> low MCU RAM / SFR-like state
    |       |
    |       +--> P300 ring 0x19EE..0x1A6D
    |       +--> descriptor tables / callback values
    |
    +--> missing private bridge
            |
            +--> far source selector / pointer
            +--> ROM-to-RAM copy or monitor routine
            +--> readable low-memory response/window
                    |
                    v
              20-bit program ROM
~~~
## What is now considered proven

Hardware-proven on exact local VDensHO1/20C2:
- P300 Physical_READ 0x03 works;
- Physical_READ differs from Virtual_READ;
- 0x0400..0x53FF can be captured read-only;
- the capture contains current Optolink request/response bytes;
- a 128-byte communication ring exists at 0x19EE..0x1A6D;
- several stable far-range values exist in structured RAM;
- the F5239/F5281/F531E sequence is laid out at 11-byte RAM intervals;
- 0xF5C28 is stable adjacent to the communication descriptor area;
- all documented bounded tests completed without new controller fault history.

Source-backed/static:
- ordinary Vitosoft event addresses are structurally 16 bit;
- fixed-endpoint secondary-address RPC architecture exists elsewhere;
- no exact 2098 Vitosoft event provides the missing high-address bridge;
- surviving public GWG/VitoTest material does not expose a ROM/page/bank command.

## What remains unproven

Still unproven:
- exact MCU marking of the installed production board;
- that every stable far value is executable code;
- the semantic identity of F5239/F5281/F531E/F5339/F5C28;
- a 20-bit source-selector variable;
- a ROM-to-RAM copy routine;
- a private monitor/service opcode or RPC;
- a complete Optolink firmware dump path on 20C2;
- equivalence of the local 20C2 mechanism to KarlKoch's historical 2098/M30612 method.

## Closed or downgraded leads

Do not spend live-test budget on these without new evidence:
- wider normal EventType.Address;
- RPCWink as firmware selector;
- Vitosorp A400/A401 as a >16-bit bridge;
- BE_READ as a bank selector;
- PROCESS_READ as a firmware path;
- arbitrary PrefixRead as a high-address byte;
- the native GWG99 CheckGWG path;
- treating F000/FFF0 Physical_READ output as direct flash;
- assuming RAM 0x1A79 is a stable U0TB pointer.
## Current next step

The highest-value next work is no longer broad event/opcode discovery.

Priority is:
1. fully characterize the repeated 11-byte structure around 0x18F8/0x1903/0x190E/0x1919;
2. correlate those records and 0x1A7D/F5C28 against controlled read-only Optolink activity;
3. identify which fields are counters, buffer pointers, SFR targets or callback pointers;
4. search historical/static sources specifically for the resulting far addresses or structure signature;
5. only after a source-backed selector/copy semantic appears, design a new bounded live discriminator.

No guessed selector/write should be introduced merely because far pointers are now visible.

## Current tooling

Relevant committed helpers:
- tools/vitotest-readonly.py
- tools/vitotest-physical-read-guard.py
- tools/physical-read-correlation-logger.py
- tools/physical-ram-snapshot.py
- tools/analyze-physical-ram-snapshot.py
- tools/physical-comm-ring-probe.py
- tools/physical-descriptor-probe.py

Primary detailed notes:
- gwg-firmware-readout-deep-dive-2026-09-26.md
- firmware-20bit-bridge-static-2026-09-26.md
- high-address-bridge-static-audit-2026-09-26.md
- physical-ram-optolink-map-2026-09-26.md
- vitotest-version-diff-2026-09-26.md

This checkpoint is intended to be the concise handoff point for continuing Arbeitsschritt 2 without reopening already closed branches.

## Update: scheduler structure resolved

The far-pointer cluster around 0x18F6 is now structurally classified as an 11-byte linked scheduler/timer record format:

~~~text
next16 | callback32 | tick16 | period16 | flag8
~~~

The four contiguous nodes begin at 0x18F6, 0x1901, 0x190C and 0x1917. Their callbacks are F5239/F5281/F531E/F5339 and their period-like values are 2000/250/2000/1100.

A host-time correlation measured approximately 1005 controller ticks per second in the changing tick fields, strongly supporting a nominal 1 kHz time base. Additional nodes with the same layout exist at 0x1139, 0x1144, 0x12D6, 0x12E1, 0x138E, 0x160F, 0x1A7B and 0x1D25.

The +0 link words move among these RAM nodes while callback and period fields remain stable. This reclassifies the cluster from possible selector/mailbox records to scheduler/control-flow records.

Consequently, F5C28 remains useful as a communication-adjacent callback/function candidate, but the scheduler table itself is no longer the leading candidate for the missing 20-bit selector. The next search should target separate copy/monitor/service state and use these callbacks as control-flow anchors.

## Update: two far-source / low-RAM copy-shaped candidates

After the scheduler cluster was reclassified, the paired full RAM snapshots were scanned for stable 8-byte 3+3+2 tuples carrying one 20-bit program-range pointer, one low-RAM pointer and a small count.

Exactly two strict candidates were found:

~~~text
RAM 0x1DE5: src=0xEA2AB dst=0x3301 count=29
RAM 0x1E6A: src=0xFB27D dst=0x0705 count=7
~~~

Both candidate tuples are stable across the paired snapshots. Candidate A remained byte-identical for 16 live rounds. Candidate B was stable for a later 24-round run; one earlier sample briefly showed a different destination/count while the source stayed fixed, but its surrounding region is highly dynamic and the observation may be non-atomic.

The destination blocks at 0x3301/29 and 0x0705/7 are stable across both full snapshots. The 0x3301 payload is unique in captured RAM; the 0x0705 payload is a non-unique 0x64 fill run.

A controlled read-only test using four different Physical_READ targets (0x0400, 0x0700, 0x3300, 0x53E0) did not change either tuple, so they are not merely the current Physical_READ request parameters.

Classification: high-value ROM-to-RAM-shaped candidates or saved copy-call frames, not yet proven copy descriptors.

## Update: idle correlation does not move copy candidates

A 60-second fixed read-only correlation run sampled both copy-shaped tuples, their low-RAM destination blocks, and burner/runtime anchors. All 66 samples remained in burner-idle state (flame=0, rpm=0, modulation=0, CFDM off, boiler 48.0 C).

Across the complete run:
- EA2AB -> 3301 / 29 remained unchanged;
- FB27D -> 0705 / 7 remained unchanged;
- both destination payloads remained byte-identical;
- no runtime transition occurred;
- fault-history guard passed.

This excludes fast idle-time churn as the explanation for these structures, but does not yet distinguish static configuration/call-frame state from a copy descriptor that only updates on a natural operating transition.

## Update: active-burner attempt missed the active window

A user-triggered attempt was launched immediately after a reported burner-on state. The exclusive probe itself found the burner already off for the whole 60-second acquisition (flame/rpm/modulation all zero) while boiler temperature cooled from about 48.3 C to 33.0 C. Both copy candidates and destination blocks remained unchanged.

A following five-minute normal-splitter watcher on 0x55D3/11 saw no nonzero modulation, flame or fan rpm before timeout. Therefore no active-state conclusion should be drawn from this attempt.

## Update: real burner startup captured with reduced-setpoint trigger

A bounded source-backed trigger on the hardware-verified reduced room setpoint 0x2307 changed 21 -> 37 C only for the acquisition window and restored 37 -> 21 C afterward with exact readback.

The resulting 60-second exclusive P300 capture successfully covered a genuine burner startup: fan rpm became nonzero after about 2.4 s, modulation rose into the high 60s, flame became active at about 13.3 s, and boiler temperature climbed from 26.5 C to about 51 C.

Neither copy candidate changed in any of 77 samples, and neither destination block changed. Thus EA2AB -> 3301 / 29 and FB27D -> 0705 / 7 are not supported as burner-transition-driven copy descriptors. Keep them classified as static copy-shaped/call-frame candidates and move the search toward other 20-bit bridge/mailbox mechanisms.

Cleanup and safety checks passed: original 0x2307=21 C restored, 20C2 identity confirmed, current GFA/alarm clear, fault history unchanged, and all previously active services restored.

## Update: strict 32-bit descriptor pass

A stricter offline pass searched the paired 0x0400..0x53FF snapshots for non-overlapping contiguous far32/RAM/count layouts, matching the confirmed 32-bit representation of scheduler callbacks. The broad heuristic candidate population collapsed to four exact hits.

Two hits belong to the known communication area. The apparent 0x113B candidate was resolved as another 11-byte scheduler chain (callbacks 0xE97F1 and 0xE9815). The strongest remaining exact shape is 0x1C90 = 0xCC701 | 0x0D58 | 32.

Live probing showed the 0x1C90 descriptor byte-identical for 32/32 samples while the 32-byte block at 0x0D58 changed on every sample. Therefore it is not supported as a simple immutable-ROM-to-RAM copy descriptor; callback/context/size or task-state semantics fit better.

A separate preceding-Physical_READ-target test found target history only in the mapped rotating communication ring. No sampled fixed field outside the ring reproducibly shadowed the preceding target. No selector/write/private opcode was attempted.

## Update: fixed P300 parser workspace mapped

Read-only self-observation has now resolved the fixed controller-side P300 work buffers immediately before the known ring.

0x196C is the start of the current RX/request buffer. Multiple overlapping Physical_READs reproduced the exact currently executing request at that fixed address, including function, target, length and checksum.

0x19AE is the start of the TX/response buffer. After a Virtual_READ 0x00F8/2, sampling 0x19A0 exposed the exact previous response 41 07 01 01 00 F8 02 20 C2 E5 at 0x19AE. After Physical_READ 0x0400/32, the same location contained the corresponding long function-0x03 response. Both behaviors reproduced 6/6.

The resulting layout is exact: RX 0x196C..0x19AB (64 B), two bytes at 0x19AC..0x19AD, TX 0x19AE..0x19ED (64 B), ring 0x19EE..0x1A6D (128 B), then cursors/metadata from 0x1A6E. Earlier DMA1 SAR1=0x019AF is consistent with an auto-incrementing DMA already one byte into a frame starting at 0x19AE.

This supersedes the looser idea that the communication evidence is only a rotating ring: there are now proven fixed RX and TX parser workspaces as well.

Callback 0xF5C28 was also tested after alternating Virtual_READ and Physical_READ bursts. Its 1000-period scheduler record behaved like ordinary time-based linked-list state under both function types, with no Physical_READ-specific state. Its priority as the missing read-handler anchor is therefore reduced.

## Update: passive DMA bridge discriminator

A bounded 60-second read-only watch sampled the already mapped M16C DMA0/DMA1 SFR blocks and DMA request-select state. Across 154 samples, DMA1 remained the known Optolink UART0 TX path (0x019AF -> 0x03A2, DM1SL 0x0A). DMA0 remained an independent UART1 TX path with source confined to 0x0161B..0x01622 and destination 0x03AA, DM0SL 0x0F.

No DMA source pointer entered 0xE0000..0xFFFFF. Thus there is no evidence for a naturally active ROM-to-low-memory DMA reader in the observed state. A DMA bridge remains architecture-possible only if some still-missing private service first reconfigures the channel; no such trigger was attempted.

## Update: Physical_READ scratch/copy primitive resolved

Read-only self-observation now resolves the controller-side Physical_READ copy path. A parser-local copy of the active request occupies 0x192C..0x1933. The checksum byte at 0x1933 overlaps the first byte of a fixed Physical_READ payload scratch buffer at 0x1933..0x1952.

Controlled overlapping reads prove forward-copy semantics from the requested low16 source into that scratch. 0x1932/32 propagates the 0x20 length byte through all 32 returned bytes; 0x1934/32 shifts the prior payload left by one; 0x1940/32 returns exactly prior payload[13:32]; and 0x1950/32 returns prior payload[29:32].

A fixed 0x3300 source tested at lengths 1,2,7,16,29,32 copied exactly the requested number of bytes, leaving primed scratch bytes beyond the requested count unchanged. The response builder then places the scratch payload at TX 0x19B5 inside the fixed TX frame beginning at 0x19AE; this was verified for lengths 1,7,16,29,32.

The resulting hardware-proven flow is: RX 0x196C -> parser-local request 0x192C -> low16 forward copy to scratch 0x1933 -> response payload 0x19B5 -> TX 0x19AE -> DMA1/UART0.

The invariant 0x1920..0x192B block does not track source address, and literal RAM pointer 0x1933 is absent from both full snapshots. This weakens a persistent RAM selector/page-byte model for ordinary Physical_READ. The historical >16-bit firmware reader more likely requires a separate far-copy/private service or a transient register-held far pointer.

Reproducer: tools/physical-read-scratch-probe.py. No write/private opcode was used.

## 2026-09-27 dispatch-afterglow probe prepared; live run gated by active fault

A new fixed-target read-only helper, `tools/physical-dispatch-afterglow-probe.py`, was added to alternate a known Virtual_READ stimulus (0x00F8/2) with a known Physical_READ stimulus (0x0400/32), immediately sampling the same fixed parser/ring/task windows after each request. It reports strict class-separated bytes and far program-range pointers.

The offline self-test passes. The first live execution stopped before any measurement because the baseline fault guard was nonzero. Production-path verification immediately afterwards returned:

- 0x5738 = 0x98 (current GFA raw fault code)
- A132 byte 28 = 0xF9 (current alarm code)
- splitter, party emulator and schedule manager all active after automatic restoration

The existing source-backed candidate interpretation associates GFA 0x98 / display F9 with fan target speed not reached at burner start. No attempt was made to bypass the guard or collect dispatcher data during this abnormal controller state.

Next gate: repeat the unchanged read-only probe only after both current-fault anchors have returned to zero.

## 2026-09-27 dispatch-afterglow differential result

After the active F9/GFA 0x98 condition was cleared, both fault anchors returned to zero and the fixed read-only differential capture completed during DHW preparation.

Two complementary captures were run:

1. 24 alternating Virtual_READ 0x00F8/2 vs Physical_READ 0x0400/32 stimuli followed by a fixed sequence of parser/ring/task windows.
2. A second earliest-observable pass where each candidate window was read as the first post-stimulus sample, averaging about 129 ms after the stimulus transaction.

Findings:
- The first broad pass found strict class-separated bytes only at 0x1A6E/0x1A70, the already mapped communication-ring cursors. These differences are explained by frame geometry.
- No reproducible Physical_READ-only far program pointer appeared.
- Stable far-pointer-dense regions 0x1D80..0x1DE0 were byte-identical between classes even when sampled first at ~129 ms.
- 0x1E00 was identical in all 10 Virtual samples and 8/10 Physical samples; the two Physical deviations were confined to the last three bytes and did not repeat or form a far pointer.
- 0x1E60 remained highly volatile for both classes. Each apparent class-only far pointer occurred once only, with unrelated one-off values in both directions; no repeatable dispatch signature exists there.
- Final current-fault and fault-history guards passed; all services were restored.

Conclusion: no persistent or >=129 ms post-dispatch class-specific handler pointer, selector, or mailbox state was found in the sampled parser/ring/task windows. The previously proposed RAM-afterglow approach is therefore substantially weakened. Any true function-dispatch pointer/state is either shorter-lived than one P300 round-trip, stored outside these windows, or not materialized as a readable RAM pointer at all.

## 2026-09-27 Physical_READ scratch capacity and 0xffff boundary

Further read-only overlap probes extend the mapped Physical_READ copy primitive.

The payload scratch beginning at 0x1933 is not 32 bytes; it accepts up to exactly 55 response bytes. Requests for lengths 49..55 return the requested count. A request for length 56 still returns SUCCESS but is silently capped to 55 bytes, producing the same 55-byte payload/frame size as length 55.

Direct observation through 0x1960 proves the staged source tail byte-for-byte. For a 55-byte read from 0x3300, scratch offsets 45..54 appear at 0x1960..0x1969 exactly. Thus the fixed geometry is:

- scratch payload: 0x1933..0x1969 = 55 bytes maximum;
- 0x196A..0x196B = two-byte gap;
- fixed RX/current-request workspace starts at 0x196C.

This matches the fixed 64-byte TX workspace: a maximum 55-byte payload plus P300 response framing fits the bounded TX structure.

A second discriminator tested Physical_READs that cross the 0xffff boundary. 0xffff/2 returned 98 00 while 0x0000/1 returned ff, proving the second byte is not low address 0x0000. Detailed 0xfffc..0xffff/8 tests showed that bytes after the boundary align with low-memory bytes beginning at 0x0001 (with expected live variation at the dynamic 0x0002/0x0004 values), not with a distinct stable 0x10000 region.

Therefore ordinary Physical_READ does not provide a useful 20-bit carry into upper MCU address space. The boundary behavior is best classified as a wrap/loop special case that resumes from low memory offset 1. It does not expose program ROM above 0xffff.

Reproducers:
- tools/physical-read-scratch-boundary-probe.py
- tools/physical-read-maxlen-probe.py
- tools/physical-read-wrap-probe.py
- tools/physical-read-wrap-detail-probe.py

All tests were read-only; current fault and fault-history guards passed and services were restored.

## 2026-09-27 Physical_READ scratch capacity and 0xffff boundary

Further read-only overlap probes extend the mapped Physical_READ copy primitive.

The payload scratch beginning at 0x1933 accepts up to exactly 55 response bytes. Requests for lengths 49..55 return the requested count. A request for length 56 still returns SUCCESS but is silently capped to 55 bytes.

Direct observation through 0x1960 proves the staged source tail byte-for-byte. For a 55-byte read from 0x3300, scratch offsets 45..54 appear at 0x1960..0x1969 exactly. Thus scratch payload is 0x1933..0x1969, followed by a two-byte gap at 0x196A..0x196B, with the fixed RX/current-request workspace starting at 0x196C.

## Update: minimal-latency byte discriminator

A fixed read-only bytewise discriminator compared Virtual_READ 0x00F8/2 with Physical_READ 0x0400/32 and then sampled one byte immediately from 0x1E00..0x1E1F or 0x1E60..0x1E7F. Direct byte-read latency was about 50.5..50.8 ms, substantially below the earlier ~129 ms first-window capture.

Across six paired samples for every byte, no address produced disjoint Virtual-vs-Physical value sets (`DISJOINT_COUNT=0`). The 0x1E00 area was almost entirely identical. The 0x1E60 area remained highly dynamic but with overlapping V/P distributions, consistent with transient task/stack state rather than a stable Physical_READ marker.

The only screening anomaly, 0x1E1D, was retested for 48 pairs: Virtual = 0x4E in 46/48 samples plus two singleton outliers; Physical = 0x4E in 46/48 plus two different singleton outliers. There was still no disjoint distribution. Both runs passed the active-fault/history guard and restored all services.

Conclusion: no reproducible Physical_READ-specific afterglow was found in these two candidate RAM windows even with ~50 ms direct byte sampling. Future work should prioritize state closer to the parser/SFR path or a different trigger observable rather than repeating broad stack-window scans.

## 2026-09-27 update: SFR path closed, EEPROM_READ mapped to coding plug

A complete paired read-only SFR discriminator over 0x0000..0x03FF initially found DMA1 TCR and timer differences. Equal-length control requests resolved the DMA1 effect as TX frame length: Virtual_READ 0x00F8/2 and Physical_READ 0x0400/2 both left TCR1=8. DMA0, DMA1, UART0/1 and DMA-select state then had no disjoint function-specific values. Residual differences were confined to free-running timer registers. No stable Physical_READ dispatch/handler afterglow was recovered from SFR state.

P300 EEPROM_READ function 0x05 is nevertheless implemented locally and exposes a space distinct from Physical_READ. A two-pass 0x0000..0x00FF snapshot was byte-identical. The high request byte is significant, but sparse high addresses form a segmented alias/service map rather than a linear memory space.

Most importantly, every successful high segment had the 16-byte fingerprint `801310910510004013051000401317d2`, identical to the start of the independently acquired active coding-plug image. A bounded verifier then read EEPROM_READ 0x1000..0x11FF in <=55-byte chunks and matched the existing active coding-plug f01 image for all **512/512 bytes**.

Classification: P300 EEPROM_READ 0x1000..0x11FF is a hardware-proven active coding-plug window on this exact controller, not the missing MCU program-ROM bridge. See `p300-eeprom-read-map-2026-09-27.md`.

## 2026-09-27 update: private-monitor archive search narrowed further

The remaining source-backed read families were audited without opcode fuzzing. The full Vitosoft event catalogue contains 20 `BE_READ` rows, all one byte and without PrefixRead. Three representative fixed shapes (`0x0008`, `0x0057`, `0x00F5`) were tested through P300 function `0x35`; all returned controller error payload `05` in 3/3 repetitions. Thus BE_READ is not locally exposed on the 20C2 through these source-backed shapes.

The second active coding-plug image (`f02`) was checked only through fixed neighboring EEPROM_READ windows. `0x1200`, `0x1600`, `0x1800`, `0x1A00`, `0x1C00` and `0x1E00` rejected the sample with `31 01`; `0x1400` repeated the already proven f01 signature. No second linear EEPROM bank or ROM-like neighbor window was found.

The global RPC catalogue was structurally re-audited: exactly 30 RPC reads carry PrefixRead payloads of two or more bytes, all are exactly three bytes, and all 30 target `0xA095` M-Bus data-header service. There is no second 3-/4-byte address-bearing RPC endpoint in the recovered catalogue.

Archive archaeology also closed several remaining public-source possibilities. All 14 unique historical OpenV XML blobs were scanned: none contains an `<addr>` value wider than 16 bits. Historical SEND templates contain the known GWG/KW/P300 families and normal fixed write/RPC templates, but no preserved monitor/page/far-address request.

All Viess-Data archives through 2.06 were re-extracted. Early releases implement the dump only through ordinary KW/F7 16-bit reads; from the 2.01-era source onward the dump UI/path is removed and P300 request construction uses only normal function `0x01` read / `0x02` write. `files/TerminatorIII.zip` contains only the normal and extended V200KW2 datapoint XML catalogues and no executable reader.

KarlKoch's complete public wiki author history around October 2010 contains KM-Bus pages and interface images only. The only new archives/tools added to the wiki between October 2010 and March 2011 were `vito_VScotHO1.zip`, `voIdent_v1.3.zip`, `TerminatorIII.zip`, and `OptoLinkLogger_v0.0.4.zip`; all relevant paths have now been classified and none preserves the M30612 firmware-read sequence.

Consequence: the public artefact trail is now close to exhausted. The missing historical bridge is increasingly likely to have existed only in a private developer-forum post, local one-off script/tool, or controller-specific monitor sequence that never entered the surviving public XML/tool archives.

## 2026-09-27 update: remaining indirect/catalog paths closed

`KBUS_INDIRECT_READ` was inspected across all 97 recovered Vitosoft definitions. 96/97 use exactly one prefix byte and form the regular `KBUS_V300_T00..T11_VirtKanal_01..08` matrix; addresses advance by 0x08 and the prefix selects K-Bus participant/channel groups. This is a subordinate K-Bus virtual-channel mechanism, not a wider MCU-memory pointer.

The full historical OpenV Git XML corpus contains 14 unique XML blobs. None contains an `<addr>` wider than four hex digits. The parser could technically expand longer addresses, but no surviving configuration uses that capability. Historical SEND templates likewise contain only the known GWG/KW/P300 families and ordinary fixed write/RPC forms; no preserved monitor/page/far-address transaction was found.

The exact local GG1/7187393 MCU marking remains unproven. Public exact-board photos show a ~100-pin QFP and J1/X10 service/test footprints, but no readable part number or defensible mapping of those headers to M16C programming pins. Therefore the next high-confidence acquisition gate is passive local hardware identification/continuity mapping rather than further speculative Optolink requests.