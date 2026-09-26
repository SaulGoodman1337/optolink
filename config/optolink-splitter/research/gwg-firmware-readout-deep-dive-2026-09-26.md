# GWG firmware-readout deep dive — 2026-09-26

## Scope

This note tracks the historical **GWG -> Optolink -> main-regulation MCU firmware**
lead for the WB2A / VDensHO1 research.

The concrete question is whether KarlKoch's 2010 statement that the
**M30612MC software of a V200KW2 could be read through Optolink** can be
reconstructed into a source-backed, non-destructive read path relevant to the
later WB2A generation.

This document deliberately separates:

- directly recovered protocol/source evidence;
- negative evidence that closes false leads;
- still-open hypotheses;
- live-test gates that must be satisfied before sending anything new to the
  production controller.

No production write or blind function-code probing was performed during this
research pass.

## Local research workspace

All archival work in this pass was performed in a separate checkout on the
`optolink-splitter` host:

```text
/home/chatgpt-admin/research/optolink
/home/chatgpt-admin/research/openv.wiki
/home/chatgpt-admin/research/vcontrold
```

The production checkout at `/opt/optolink` was not modified.

The full OpenV wiki history clone currently contains:

```text
7619 commits
11273 reachable objects
```

Ephemeral scan output is kept locally below
`.research-runs/20260926-gwg/` and is intentionally not committed.

## Historical M30612 statement

The key historical evidence remains KarlKoch's OpenV wiki edit from
2010-10-04 (`da56ba2f73ae09d03597d75210d8a76444595503`).

The V200KW2 entry states that the controller uses an **M30612MC**, that its
software can be read "mit etwas Aufwand" through Optolink, and that the code
size is approximately 128 KiB.

The same page mentions an approximately 57,000-line disassembly.

Important detail: the firmware-read link points explicitly to
`Protokoll-GWG`, even though the contemporaneous wiki already had a
separate and correct `Protokoll-KW` page for V200KW2 traffic.

That makes the GWG low-level function family a real archival clue rather than
a generic reference to Optolink.

## Recovered historical GWG wire protocol

The surviving GWG page history starts in 2008.

The documented serial layer is:

```text
4800 baud
8E2
controller periodically emits 0x05
request is sent after 0x05
```

The public request layout is explicitly:

```text
01 <type> <addr> <len> 04
```

Therefore the documented GWG transport has a **one-byte address field**.
The historical function table contains:

| Semantic | GWG type |
| --- | ---: |
| Virtual read | `0xC7` |
| Virtual write | `0xC4` |
| Physical read | `0xCB` |
| Physical write | `0xC8` |
| EEPROM read | `0xAE` |
| EEPROM write | `0xAD` |
| Physical XRAM read | `0xC5` |
| Physical XRAM write | `0xC3` |
| Physical port read | `0x6E` |
| Physical port write | `0x6D` |
| Physical BE read | `0x9E` |
| Physical BE write | `0x9D` |
| Physical KMBUS RAM read | `0x33` |
| Physical KMBUS EEPROM read | `0x43` |

The public example for physical read is:

```text
TX 01 CB 6F 01 04
RX <one byte>
```

## Full GWG page-history result

Every surviving revision of `Protokoll-GWG.md` was diffed from the
first 2008 revision through the later cleanup edits.

Result:

- no removed ROM-read opcode was found;
- no removed page selector was found;
- no removed bank selector was found;
- no removed >8-bit GWG address format was found;
- no removed monitor-entry sequence was found.

The page gained the known low-level function table and examples, but there is
no evidence that a high-address firmware mechanism was once public there and
later deleted.

This is useful negative evidence: KarlKoch's 2010 statement must rely on
knowledge outside the normal public GWG page, or on a multi-stage use of
otherwise documented primitives.

## KW protocol relationship

The historical `Protokoll-KW` page explicitly says that KW resembles
the older GWG protocol but supports **two-byte addresses**.

The normal KW frame is documented as:

```text
01 F7 <addr_hi> <addr_lo> <len>
```

with ordinary virtual write using `F4`.

Later documentation also lists GFA and process families, but the historical
KW page does not document the GWG low-level memory opcodes
`CB/AE/C5/6E/9E/33/43` inside the KW transport.

Therefore one important open question is whether the V200KW2 firmware parser
accepted more of the older GWG function family than the public KW page
documented.

## vcontrold GWG implementation

A historical-compatible GWG definition survives in `openv/vcontrold`.

The GWG protocol macros map directly to the old wire types:

```text
GETADDR   -> 01 CB
GETBADDR  -> 01 9E
GETVADDR  -> 01 C7
GETPADDR  -> 01 6E
GETEADDR  -> 01 AE
GETXADDR  -> 01 C5
GETKMADDR -> 01 43
```

Normal commands append address, length and the `04` terminator.

The configuration also defines interactive test commands for the same
families using the parser's `SEND BYTES` token.
Example shape:

```text
SYNC
GETXADDR
SEND BYTES
SEND 01 04
RECV 1
```

This proves that vcontrold has a **raw-byte forwarding primitive** in its
command bytecode.

The parser implementation recognizes `SEND BYTES` separately from
literal `SEND` data and forwards the supplied buffer without unit
conversion.

However, the stock GWG test commands use device definitions with:

```xml
<len>1</len>
```

and the vcontrold command-input path truncates supplied raw hex data to the
command length.
Therefore the correct evidence boundary is:

- raw-byte forwarding in the vcontrold parser: **proven**;
- stock GWG test commands accepting one raw byte: **proven**;
- stock GWG test commands accepting arbitrary multi-byte selector/address
  payloads: **not proven**;
- a custom XML command using the same parser to send more than one byte:
  technically plausible from the code structure, but not yet recovered as a
  historical firmware-read implementation.

This corrects the earlier provisional interpretation that the stock test
commands themselves proved unrestricted multi-byte injection.

## Historical vcontrold source boundary

The current Git history of `src/parser.c` reaches back to an imported
2013 source state.

Already in that oldest reachable parser revision, `SEND BYTES` exists
and directly transmits the supplied send buffer.

That is useful continuity evidence, but it is still later than KarlKoch's
2010 M30612 statement.

The older wiki attachments
`vcontrold-v0.97.zip` and `vcontrold-v0.98.zip` are therefore
high-value targets: their embedded parser/config sources should be extracted
and compared to establish whether the same raw-byte mechanism existed in the
contemporary 2008-2010 toolchain.

## Historical artifact inventory

A full-path scan of the OpenV wiki Git history identified **121 candidate
binary/source artifacts** relevant enough to preserve for recursive analysis.

High-value examples include:

```text
files/vcontrold-v0.97.zip
files/vcontrold-v0.98.zip
files/vcontrold.zip
files/TerminatorIII.zip
files/OptoLinkLogger_v0.0.1.zip
files/OptoLinkLogger_v0.0.4.zip
files/v-control1_2_5.zip
files/v-control1_3_0M.zip
files/VitoTest_V1.6.zip
files/VitoTest_V1.7.zip
files/VitoTest_V1.8.zip
files/voIdent_v1.0.zip ... v1.5.zip
files/Viess_Data.zip
files/viessdata20x.zip
files/v_comm_dll.zip
```
The next archive pass must inspect **contents**, not filenames only, for:

```text
M30612
M16C
ROM
FLASH
MONITOR
PAGE
BANK
WINDOW
COPY
DUMP
BOOT
MEMORY
CB / C5 / AE / 9E / 33 / 43
```

and for source/dump extensions such as:

```text
.asm .lst .map .bin .rom .hex .mot .s19 .obj .exe
```

The already recovered V-Comm source remains closed as the hidden reader; see
`v-comm-dll-source-recovery-2026-09-25.md`.

## What the GWG evidence does and does not prove

### Proven

1. KarlKoch explicitly associated V200KW2/M30612 firmware readout with
   Optolink and linked GWG protocol material.
2. The old GWG family contains multiple low-level memory/domain reads beyond
   normal virtual datapoints.
3. The public GWG wire format itself is only one-byte addressed.
4. The public GWG page history contains no hidden high-address command.
5. vcontrold includes a raw-byte forwarding primitive and interactive GWG
   low-level test commands.
6. The stock test commands are limited to one raw byte by their command
   length.

### Not proven

1. That a plain `CB/C5/AE/9E/33/43` request can read MCU program ROM.
2. That V200KW2 accepts those GWG opcodes in its KW parser.
3. That any known selector exposes the 20-bit M30612 program address space.
4. That the later WB2A / VDensHO1 implements the same monitor path.

## 2026-09-26 follow-up: contemporary vcontrold binaries and 2098 boundary

A follow-up pass on the `optolink-splitter` host inspected the preserved
`vcontrold-v0.97.zip` and `vcontrold-v0.98.zip` artifacts plus the surviving
OpenV XML configurations.

### Contemporary parser capability confirmed

Both historical archives contain only Windows binaries (`vcontrold.exe` and
`vclient.exe`), not source. Static strings from the 0.97 binary nevertheless
confirm that the parser already supported:

```text
SEND BYTES
Laenge des Hex Strings > Sendelaenge des Befehls, sende nur %d Byte
```

This moves the raw-byte forwarding capability from a post-2013 source
observation into the contemporary 2011 toolchain. It also confirms that the
command-length truncation behavior was already present there.

The surviving GWG XML test commands use shapes such as:

```text
SYNC;GETXADDR;SEND BYTES;SEND 01 04;RECV 1
```

which corresponds to a user-supplied one-byte address inserted between the
GWG function prefix and the fixed `01 04` length/terminator tail.

### Exact device applicability remains limited to GWG / 2053

The surviving `universal_vito.xml` binds the low-level interactive commands
`get`, `vget`, `bget`, `pget`, `eget`, `xget`, and `kmget` to device
`2053`. For example, the EEPROM/XRAM/KM-BUS test commands all carry:

```xml
<device ID="2053">
    <addr>dummy</addr>
    <len>1</len>
</device>
```

No equivalent binding for V200KW2 / device `2098` was found in the preserved
OpenV XML set.

A follow-up search through the reachable `openv/vcontrold` Git history likewise
found `2098` consistently associated with the normal `KW2` protocol, but did
not recover a `2098`-specific use of the GWG low-level test command family.

### Consequence for the firmware-readout hypothesis

This weakens the simple interpretation that KarlKoch merely sent ordinary
`CB/C5/AE/9E/33/43` GWG reads directly to a V200KW2.

The evidence now points more strongly to a missing bridge step:

```text
Optolink/KW2
    -> selector / monitor / service / copy operation
    -> exposed low-address window or alternate parser state
    -> low-level read
```

The missing element is therefore more likely to be a preparatory
selector/monitor/window/copy operation than the raw read primitive itself.

### Live-test decision

No new packet was sent to the local WB2A during this pass.

Reason: the low-level GWG reads are source-backed for `2053`, but there is
still no exact-family evidence that the same opcodes or frame semantics are
valid on `2098`, much less on local `20C2`.

A bounded production test remains gated on recovering either:

1. a `2098`-specific low-level example;
2. a selector/monitor sequence that explicitly precedes such a read; or
3. an exact VDensHO1/20C2 service path with equivalent semantics.

## Current technical interpretation

A direct one-step read of M30612 program ROM using the public GWG frame is
not a good fit because the documented address field is only eight bits.

The strongest remaining architectural models are:

1. **selector/window model** — one command selects a page/bank/domain and a
   subsequent low-level read accesses a small exposed window;
2. **monitor/service mode** — a setup sequence switches the controller into a
   diagnostic parser with different addressing semantics;
3. **copy/mailbox model** — firmware copies a requested program-ROM block into
   an ordinary readable RAM/XRAM/window;
4. **undocumented KW extension** — the KW2 parser accepts a low-level function
   family with two-byte address plus a separately stored high selector.

These are hypotheses, not yet protocol facts.

## Closed or downgraded paths

The following should not be reopened without new source evidence:

- ordinary VS1/KW `Virtual_READ / F7` as direct program-ROM access;
- Viess_Data "Lese Dump" as a special firmware reader;
- OptoLinkLogger dump as a high-ROM reader;
- current V-Comm DLL as a hidden >16-bit VDensHO1 reader;
- `PROZESS_READ / 0x7B` as a banked firmware path;
- `BE_READ / 0x9E` as a standalone firmware-bank solution;
- current Vitosoft VS1 serializer as a carrier for >16-bit target addresses;
- `0x778F` as an exact V200KW2/2098 firmware selector.

See the canonical firmware note for the detailed evidence behind those
closures.

## Next steps

### Priority 1 — recover the missing 2098 bridge

Search the surviving OpenV wiki/object history, former developer-forum mirrors,
attachments, release bundles and external mirrors for combinations of:

```text
2098
V200KW2
M30612
M16C
CB AE C5 6E 9E 33 43
ROM FLASH MONITOR PAGE BANK WINDOW COPY DUMP
```

Highest-value evidence is a sequence showing a setup/selector operation
followed by repeated low-level reads.

### Priority 2 — reverse the contemporary vcontrold binaries narrowly

The 0.97/0.98 binaries are now worth targeted static analysis because they
contain the parser and debug information/string evidence from the relevant era.

Focus on:

- `execByteCode` / `SEND BYTES` handling;
- command-length enforcement;
- protocol macro expansion;
- any unreachable or undocumented parser tokens;
- literal function-code tables beyond the public XML.

The goal is not full reverse engineering of vcontrold, but to prove whether a
hidden command form could carry a selector or additional address bytes.

### Priority 3 — recursively unpack all high-value historical archives

Continue the 121-artifact inventory recursively, including nested installers
and self-extracting archives. Search both filenames and extracted binary
strings for monitor/page/bank/copy vocabulary, M30612/M16C identifiers and
firmware/disassembly artifacts (`.asm`, `.lst`, `.map`, `.bin`, `.rom`,
`.hex`, `.mot`, `.s19`, `.obj`).

### Priority 4 — reconstruct the GWG -> KW compatibility boundary

Establish whether any surviving tool, config, forum example or binary sends
`CB/AE/C5/6E/9E/33/43` to V200KW2 / `2098`.

A single source-backed example would justify a small compatibility test.
Without one, do not transpose the GWG opcodes to KW2 or WB2A.

### Priority 5 — identify selector-state signatures

Search for command sequences with the structure:

```text
set selector/page/bank/window
read small block
increment selector
read next block
```

Also search for copy/mailbox variants where a high ROM address is written into
a request structure and the resulting block is read back from RAM/XRAM.

### Priority 6 — design the first bounded live discriminator

Only after a request shape is source-backed:

- start from a known harmless baseline read;
- change exactly one selector dimension;
- use the smallest possible read length;
- repeat once to establish determinism;
- restore/exit service state exactly as documented;
- stop immediately on reset, alarm, protocol desynchronization or undefined
  response behavior.

No blind write sweep, function-code sweep, erase/unlock or guessed monitor
entry sequence is justified.

## Relevance to the WB2A / Vitotrol work

A regulation-firmware dump is now a shared dependency for two research
questions:

1. locating the historical/hidden Optolink memory-service implementation;
2. tracing the internal Vitotrol receive path that updates remote-alive,
   software/index state, room-sensor validity and room temperature together.

If a WB2A firmware image is acquired, priority cross-references include:

```text
0x27A0
0x0A5C
0x0896
0x089C
0x7340..0x7344
BC remote fault path
KM-BUS receive/parser handlers
```

This is why the MCU firmware workstream remains the highest-value dependency
for the software-only Vitotrol emulator.

## Current conclusion

The GWG lead remains **alive**, but the public one-byte GWG frame itself is
insufficient to explain a ~128 KiB M30612 program-ROM dump.

The new archival work strengthens the interpretation that KarlKoch used a
special developer/diagnostic technique built around the GWG low-level function
family rather than a normal V200KW2 datapoint.

The immediate evidence gap is now narrow and testable:

> recover the missing selector/monitor/copy step, or recover a contemporary
> tool/configuration that demonstrates how the low-level GWG primitives were
> extended beyond their public one-byte address model.

Until that step is recovered, no claim should be made that WB2A firmware is
readable through GWG/Optolink, but the route is not excluded.