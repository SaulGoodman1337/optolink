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

## 2026-09-26 workstream 1: partial 2098 bridge recovered

The search for a V200KW2 / `2098` bridge produced a concrete but limited
result from the imported OpenV Wikispaces discussion archive.

### GWG framing is source-backed on V200KW2 / 2098 for device identification

OpenV issue #10 preserves a 2010 V200KW2 trace from TerminatorIII. The request:

```text
01 C7 F8 04 04
```

returned:

```text
20 98 00 02
```

on an actual V200KW2. This is the GWG `Virtual_READ / C7` family rather than
the normal two-byte-address KW `F7` request.

In the same thread, Hanspeter (`vitoopen`) explicitly states that a general
client can use the GWG protocol to identify controllers and switch to a
"higher" protocol such as KW or 300 afterwards.

Source:
https://github.com/openv/openv/issues/10

This changes the evidence boundary:

- GWG framing/opcode compatibility on `2098`: **proven for C7 identification**;
- general acceptance of all GWG low-level opcodes on `2098`: **not proven**;
- `CB/C5/AE/9E/33/43` on `2098`: **still not recovered**.

The missing bridge has therefore narrowed from "does KW2 accept any GWG
traffic?" to "does KW2 expose the low-level GWG memory families, and if so
under what selector/monitor state?"

### Ordinary 16-bit dump attempt produced a useful negative boundary

The same imported discussion later records TerminatorIII's attempt to build a
binary dump by reading the ordinary 16-bit address space. In January 2011 he
reported that this worked as a general address dumper, but that there were no
data above `0x8000`.

This is not evidence that physical MCU ROM ends at `0x8000`. It is evidence
that an ordinary address walk did not expose the ~128 KiB M30612 program ROM.

That result independently supports the existing conclusion that KarlKoch's
firmware readout required an additional mechanism rather than a plain
sequential virtual-address read.

### KarlKoch's firmware possession is independently corroborated

The full 2010 history of `KM-Bus.md` shows that KarlKoch created the page and
documented internal V200KW2 firmware structures before adding the explicit
M30612 readout note.

On 2010-10-05 he documented, among other details:

- eleven internal V200KW2 participant tables;
- internal slot mappings;
- command dispatch groupings;
- specific firmware behavior around KM-Bus participant state.

This level of internal implementation detail is consistent with the same
author's statement that he had an approximately 57,000-line V200KW2
disassembly. No firmware binary or disassembly file is present in the surviving
wiki Git history.

### Lost private developer forum becomes a primary archival target

HaustechnikDialog preserves multiple contemporary references to a non-public
OpenV developer forum:

- a 2007 pshome statement says the private forum contained the "raw"
  information for the KW1/KW2 protocol and the history of how it was
  discovered;
- in January 2010 marcusT confirms that the developer forum was not public and
  that pshome managed access;
- by August 2010 users report that `openv.de` was unreachable and old source
  links were already disappearing.

Sources:

- https://www.haustechnikdialog.de/Forum/t/59578/Vitotronic-vom-PC-steuern-ueberwachen?page=15
- https://www.haustechnikdialog.de/Forum/p/1294186
- https://www.haustechnikdialog.de/Forum/p/1392876

This makes the former developer forum / SVN / `openv.de` archive a stronger
candidate for the missing KarlKoch readout method than the public wiki page
history.

### Related historical simulator lead

A 2009 HaustechnikDialog post references a pshome V200KW2 simulator file:

```text
http://openv.de/svn/xml/sim-2098.ini
```

and shows ordinary KW examples such as:

```text
01 F7 08 00 02 = 3C 00
```

The simulator artifact is therefore another concrete historical filename to
recover from mirrors/backups. The surviving reference currently demonstrates
normal KW traffic only, not a firmware-read extension.

Source:
https://www.haustechnikdialog.de/Forum/t/59578/Vitotronic-vom-PC-steuern-ueberwachen?PostSort=1&page=20

### SourceForge/vcontrold archaeology closes two false positives

The recovered `openv/vcontrold` history contains the historical
`sim-2098.ini`. It first appears in the reachable Git history in commit
`91e7d84b2becaab5f14a6417dd097395ce8c8490` and later moved to
`doc/examples/sim-2098.ini`.

The recovered simulator contains ordinary KW reads only, for example:

```text
01 F7 08 00 02 = 3C 00
01 F7 08 A7 04 = 87 03 1A 00
```

No `CB/C5/AE/9E/33/43`, page, bank, monitor or copy sequence was found in
this recovered simulator. The historical `sim-2098.ini` lead is therefore
closed as a hidden firmware-reader configuration in its surviving form.

A second apparent lead was an old `vcontrold.xml` blob containing both:

```xml
<device ID="2098"/>
```

and the GWG macro:

```text
GETADDR -> SEND 01 CB
```

Object-to-path mapping identifies this blob as
`doc/examples/vcontrold.xml`. That file contains multiple protocol
definitions in one global configuration; coexistence of the selected device
ID and the GWG macro does **not** establish that `2098` uses `CB`.

The matching `vito.xml` history remains decisive: `2098` is bound to
`KW2`, while low-level overrides such as `geteaddr`, `getpaddr`, and
`getxaddr` are attached specifically to device `2053`.

This also explains historical startup/debug output that appears to compile
`CB` command bytecode in a `2098` setup: vcontrold compiles protocol
definitions globally. Such output is not evidence that the frame was
transmitted to or accepted by a V200KW2.

### External exact-frame search result

A targeted search for successful V200KW2 traces containing
`01 CB`, `01 C5`, `01 AE`, or `getxaddr` did not recover an
exact-family success case.

Public mirrors of the vcontrold XML continue to show the same model:
`2098 -> KW2`, `2053 -> GWG`, with the physical/EEPROM/XRAM overrides
belonging to the GWG device-specific path.

This is negative evidence rather than proof of absence, but it removes the
strongest configuration-based false positives found so far.

### Updated workstream-1 gate

Workstream 1 is now **partially satisfied**:

1. a GWG command on `2098` is source-backed (`C7` identification);
2. a plain 16-bit address dump was historically attempted and did not expose
   the high firmware image;
3. the exact low-level memory-family bridge is still missing.

The next archival discriminator is therefore specifically:

> recover a `2098` example using `CB/C5/AE/9E/33/43`, or recover the
> selector/monitor/copy setup sequence that makes such a read meaningful.

No live `CB/C5/AE/9E/33/43` packet is justified on the local WB2A from the
current evidence alone.

## Hourly checkpoint: expanded external 2098 search

An expanded public-web search was run for combinations of:

```text
openv.de
M30612 / M30612MC
V200KW2 / 2098
01 CB / 01 C5 / 01 AE / 01 9E
monitor / page / bank / selector / copy
```

The search re-confirmed the known HaustechnikDialog references to the private
OpenV developer forum and to `openv.de/svn/xml/sim-2098.ini`, but did not
recover a preserved developer-forum post, SVN artifact, or successful
V200KW2 low-level-memory trace beyond the already documented `C7`
identification path.

The surviving public OpenV/vcontrold material still consistently models:

```text
2098 -> KW2
2053 -> GWG low-level memory overrides
```

No source-backed selector/monitor/copy request shape was recovered in this
checkpoint. Therefore the evidence threshold for beginning a bounded live
`CB/C5/AE/9E/33/43` discriminator on the production WB2A is still not met.

**Workstream-2 gate:** not yet open. The concrete missing prerequisite remains
one of:

1. a successful `2098` trace using a low-level GWG memory opcode;
2. a contemporary selector/monitor/copy sequence tied to V200KW2/M30612; or
3. an exact VDensHO1/20C2 equivalent service path.

## Active continuation: legacy v-control binary pass

The preserved public `v-control` archives were unpacked and scanned directly:

```text
v-control1_2_5.exe
v-control1_3_0M.exe
```

These are VB6 applications from the same historical ecosystem and therefore
plausible places for a hidden developer/debug readout path.

Static string analysis did **not** recover any of the expected firmware-read
markers:

```text
M30612
M16C
firmware
ROM / FLASH
MONITOR
PAGE / BANK / WINDOW
COPY / DUMP
```

The only apparent `C5` hit is ordinary UI text
(`C5 Minimalbegrenzung Vorlauf`), not opcode evidence.

This makes the preserved public `v-control 1.2.5/1.3.0M` binaries a weak
candidate for KarlKoch's firmware-dump mechanism. They should not be treated
as evidence for a hidden M30612 readout path without deeper code-level
evidence.

The archival priority remains the lost private developer-forum/SVN material
and exact `2098` low-level traces.

## Active workstream checkpoint: TerminatorIII extended XML closed as monitor lead

The historical `files/TerminatorIII.zip` archive was re-extracted and compared
at file level. It contains only:

```text
vito_V200KW2.xml
vito_V200KW2_extended.xml
```

The archive entered the wiki history on 2011-01-21 in commit
`fcd37fc74e15ddeb93c8402f8fed409aed1b6787`.

The potentially interesting symbols:

```text
ChecksummeROMBerechnet       -> 0x08F0
NRF_ChecksummeROMLinker     -> 0x08F4
SC100_ProgrammierstellungEin -> 0x0C04
SC100_ProgrammierstellungAus -> 0x0C05
```

occur **only** in `vito_V200KW2_extended.xml`, not in the normal
`vito_V200KW2.xml`.

The same extended file also contains a large foreign-family payload including
many `SC100_*` and `WPR_*` datapoints. This is consistent with the earlier
Vitosoft provenance work that mapped the ROM-checksum and SC100 programming
positions to other controller families rather than to V200KW2 / 2098.

Therefore the extended TerminatorIII XML must not be treated as evidence that
V200KW2 exposes:

- a ROM checksum service at `0x08F0/0x08F4`;
- a firmware programming mode at `0x0C04/0x0C05`;
- a selector/monitor/copy bridge through those addresses.

No hidden parser command, page selector, bank selector or ROM-copy operation
was found in the TerminatorIII archive. It is a datapoint catalogue, not a
firmware-read implementation.

This closes the strongest remaining interpretation of the TerminatorIII
extended file as a direct path to the missing 2098 firmware-reader mechanism.

## Active workstream checkpoint: voIdent / VitoTest binary string pass

A targeted static string pass was run over the preserved `voIdent` releases
(v1.0, v1.1, v1.3, v1.5) and `VitoTest` releases (v1.6, v1.7, v1.8).

Results:

- `voIdent` embeds the expected V200KW2 / `2098` device metadata and protocol
  selection strings;
- no `M30612`, `M16C`, ROM/flash monitor, page/bank/window/copy, or low-level
  `CB/C5/AE/9E` firmware-read strings were recovered;
- `VitoTest` produced no protocol-specific firmware-read vocabulary in the
  static string pass; apparent "monitor" hits are Windows API/UI symbols only.

This does not prove that the binaries contain no relevant code, but it removes
another easy archival route: neither tool exposes a self-describing firmware
reader or selector/monitor command set in its preserved public binary.

## Active continuation: vcontrold parser/framer boundary

The original SourceForge SVN source closes an important implementation
question that remained open after the binary/string pass.

In `parser.c`, `expand()` substitutes `$addr` by walking the complete
address string in two-hex-character chunks and emitting one space-separated
byte token for each pair. There is no one-byte or two-byte address limit in
that expansion loop. The resulting command string is then compiled by
`buildByteCode()` / `parseLine()`, where every ordinary `SEND` token is
converted to one byte and appended to the command buffer.

Relevant source path:

```text
trunk/vcontrold/parser.c
$Id: parser.c 34 2008-04-06 19:39:29Z marcust $
```

This means that vcontrold itself is capable of representing an `addr` value
longer than the one- or two-byte forms used by the surviving public
configuration. A historical command could therefore have encoded additional
selector/page/high-address bytes entirely in XML data without requiring an
undocumented parser token or a special compiled binary.

The framer boundary reinforces this result. In `framer.c`,
`framer_send()` only constructs a special frame when the active protocol ID
is the P300 lead-in (`0x41`). For non-P300 protocols it passes the already
compiled byte buffer directly to `my_send()`. Therefore the KW/GWG path does
not impose a separate fixed address width in the framer.

What this proves:

- the vcontrold parser is **not** the architectural reason the public GWG
  command appears limited to an 8-bit address;
- a multi-byte selector/address sequence was technically expressible in the
  historical XML command layer;
- the highest-value archival target shifts from hidden parser syntax to lost
  `vito.xml` / protocol-command variants, developer configurations, traces,
  and attachments containing unusually long `<addr>` values or explicit
  selector bytes.

What this does **not** prove:

- that V200KW2 / device `2098` accepts a multi-byte `CB/C5/AE/9E/33/43`
  request;
- that the M30612 firmware space is directly addressable this way;
- the byte order or semantics of any missing selector/page/high-address field.

This narrows Priority 2 substantially: a hidden vcontrold bytecode opcode is
no longer required to explain a >16-bit historical readout. The next search
should concentrate on historical XML/configuration artifacts and transmitted
frames.

The `legacy` branch of `openv/vcontrold` carries the same address-expansion
loop in `vcontrold/parser.c`, so this capability is not merely a later
refactor. Its preserved `vcontrold/vcontrold.xml` is much simpler and defines
the GWG read primitive as `SEND 01 CB`; the selected example device is
`2098`. This coexistence is configuration-level only and still does not prove
that a CB frame was accepted by 2098.

A full inventory of numeric `<addr>` values in the surviving public
`xml/kw/vito.xml` found only 2- and 4-hex-character values (one or two
bytes), despite the parser being able to expand longer strings. The visible
low-level `getxaddr`, `getpaddr`, and `geteaddr` uses remain associated
with device `2053`, not `2098`. Therefore the missing bridge is absent from
the current public XML rather than being prevented by the parser.

There is also a second archival implication. The GWG test commands use
`SEND BYTES`, and `execByteCode()` appends caller-supplied bytes to the
preceding SEND buffer before calling `framer_send()`. A developer could thus
have exercised an extended/custom request interactively without ever storing
the full byte sequence as a long `<addr>` value. Historical simulator INIs,
debug logs, shell/client examples and forum traces are therefore now as
important as XML files for recovering the missing request shape.

Source:

- https://sourceforge.net/p/vcontrold/code/HEAD/tree/trunk/vcontrold/parser.c
- https://sourceforge.net/p/vcontrold/code/HEAD/tree/trunk/vcontrold/framer.c

## Active continuation: OptoLinkLogger dump path fully decompiled

A high-value historical lead was recovered from
`files/OptoLinkLogger_v0.0.4.zip`.

The included README dates the configurable data-dump feature to version 0.0.3
on 2010-12-29:

```text
Daten Dump mit konfigurierbaren Parametern (Start-Adr., Länge)
```

This is temporally close to the 2010 V200KW2/M30612 work and the binary embeds
explicit support metadata for V200KW2 / device `2098`.

The .NET assembly was decompiled to IL using an isolated `monodis` runtime
extracted under `/tmp`; no packages were installed on the splitter host.

### Exact dump request shape

The static request buffer is initialized as:

```text
F7 00 18 30
```

The dump state machine sends the VS1 lead-in byte `01` after the normal
`05` synchronization byte and then sends that four-byte request buffer.
Therefore the effective wire request is:

```text
01 F7 <addr_hi> <addr_lo> <len>
```

The private implementation data in the assembly independently contains
examples such as:

```text
01 F7 08 00 FE
01 F7 00 18 30
F7 00 F8 04
```

### The configurable uint32 address is truncated to 16 bits

The UI/settings expose `DumpStartAddr` and `DumpLength` as `uint32`, but
`SetReadAddr(uint32 nAddr)` writes only:

```text
s_ReadRequest[1] = (nAddr >> 8) & 0xff
s_ReadRequest[2] = nAddr & 0xff
```

No bits above bit 15 are encoded anywhere in the request.

`SetReadLen()` writes one byte to `s_ReadRequest[3]`.

`TS_DumpAll()`:

1. explicitly aborts unless the selected protocol is `VS1`;
2. reads `DumpStartAddr` / `DumpLength`;
3. splits the dump into blocks of at most `0xFE` bytes;
4. calls `SetReadAddr()` for each block;
5. increments the software-side `uint32` address;
6. sends the normal VS1 `F7` request.

If the configured address crosses `0xFFFF`, the high software-side bits are
discarded on the next call to `SetReadAddr()`. The transmitted address
therefore wraps in the 16-bit VS1 address space.

### Consequence

The historical OptoLinkLogger "Dump Data" function is conclusively **not** the
missing M30612 program-ROM readout mechanism.

It is a sequential normal-VS1 virtual-address dump. This strongly explains why
a contemporary user could create a binary dump yet observe no useful data in
the high part of the ordinary address space.

The result also strengthens the distinction between two historical meanings of
"dump":

- public/user tool dump: sequential `F7` reads in the ordinary 16-bit VS1
  space;
- KarlKoch M30612 firmware readout: a different, still-lost mechanism required
  to reach the ~128 KiB MCU program ROM.

The OptoLinkLogger lead is therefore closed as a selector/page/high-address
implementation.

## Active continuation: original SourceForge SVN history audited

The original SourceForge repository is still reachable directly at:

```text
https://svn.code.sf.net/p/vcontrold/code/
```

An isolated Subversion client was extracted under `/tmp` on the splitter
host; no system package was installed. The complete repository history
(`r1..r107`) was enumerated with changed paths.

### Initial public import predates the KarlKoch firmware work

Revision 1, committed by `brainhunter` on 2010-12-13 as
`upload des orginal`, imported the old public layout:

```text
/vcontrold/
/xml-32/xml/sim-2098.ini
/xml-32/xml/vcontrold.xml
/xml-32/xml/vito.xml
```

The imported XML working-copy timestamps are 2010-08-31. That snapshot
therefore predates KarlKoch's October 2010 M30612/V200KW2 firmware notes.

This materially lowers the probability that the initial SourceForge import
ever contained the later/private firmware-readout mechanism.

### Deleted r2 svn-commit.tmp recovered

Revision 2 temporarily added `/svn-commit.tmp`; revision 3 deleted it.
Using an SVN peg revision (`svn-commit.tmp@2`) recovered the file.

Its complete meaningful content is only the original commit message plus the
list of files staged in the first import:

```text
upload des orginal
...
A xml-32/xml/vito.xml
A xml-32/xml/sim-2098.ini
A xml-32/xml/vcontrold.xml
A vcontrold/parser.c
...
```

It contains no hidden command, trace, attachment name, monitor sequence or
firmware-read reference.

### r2 already contains the known public low-level GWG machinery

The r2 public XML already defines:

```text
GETADDR   -> 01 CB
GETBADDR  -> 01 9E
GETPADDR  -> 01 6E
GETEADDR  -> 01 AE
GETXADDR  -> 01 C5
GETKMADDR -> 01 43
```

and the interactive `SEND BYTES` test forms.

At the same revision:

```xml
<device ID="2098" name="V200KW2" protocol="KW2"/>
```

is present in `vito.xml`, while the low-level EEPROM/port/XRAM overrides are
attached specifically to device `2053`.

This confirms that the separation between `2098/KW2` and the low-level
`2053/GWG` path is not a later cleanup; it was already present in the
restored public source snapshot.

### r7 "additional XML commands" contains no firmware bridge

Revision 7 (2010-12-14) is described as:

```text
Zusatzliche Befehle ins XML eingefugt
V200KW1 ID 2094 hinzugefugt
```

A byte-level r2 -> r7 diff shows ordinary datapoint additions, error markers,
setpoint/write commands and the `2094` device identifier. It introduces no:

- `2098` low-level protocol override;
- M30612/M16C reference;
- page/bank/window selector;
- monitor/service entry;
- ROM-copy request;
- extended address form.

### Full SVN deletion history

Across r1..r107 the only meaningful deleted standalone file from the original
root is the recovered `svn-commit.tmp`. Other deletions are build/readme
files or whole directories removed during the 2013 trunk/branches/tags
restructure.

No deleted firmware reader, private XML, trace or simulator variant appears in
the SourceForge SVN path history.

### Consequence

The original SourceForge SVN can now be treated as a **restored public subset**,
not as an archive of KarlKoch's missing private firmware-readout work.

The most important temporal clue is that its core XML snapshot predates the
October 2010 M30612 investigation. The missing mechanism is therefore more
likely to have lived in:

1. the private OpenV developer forum;
2. an uncommitted/private XML or command file;
3. a local developer tool/script;
4. an attachment or archive never imported into SourceForge.

The SourceForge SVN history itself is no longer a high-priority place to search
for the selector/monitor/copy bridge.

## Active continuation: exact VDensHO1 exceptional read surface fully classified

The verified private Vitosoft v6 snapshot
`vitosoft-private-archive-20260924-143439`
(SHA256 `3d31380d6dfabf8ede9e305b115e847fb0670511e253a4ed4e59feef2f7adfee`)
was revisited using only targeted derived metadata.

To avoid re-expanding the 4.2 GiB installation, an isolated 7-Zip binary was
extracted under `/tmp` and only
`derived/metadata/vdensho1-all-events.csv` was read from the verified archive.
No Vitosoft executable was run.

The exact `VDensHO1 / 20C2` profile contains 581 events. Its exceptional
read-function surface consists of exactly:

```text
22 x Remote_Procedure_Call
 1 x undefined
```

All 23 entries have now been classified.

### The 22 exact-profile RPC definitions

They collapse to five concrete RPC endpoint families:

| Endpoint | Events | Metadata meaning | Effective role |
| --- | ---: | --- | --- |
| `0xA010` | 17 | `Teilnehmerliste_LON_0` plus entries `00..15` | LON participant-list readout |
| `0xA051` | 2 | `Bedienparameter...FunktionReset` | operating-parameter reset for A1/M1 or M2; AccessMode is Write |
| `0xA050` | 1 | `Konfi_FunktionReset_GWG` | coding/configuration reset; AccessMode is Write |
| `0xA029` | 1 | `valmRPCClearErrorHistoryTable` | clear error-history table; AccessMode ReadWrite, RPCHandler 22 |
| `0xA009` | 1 | `vlogRPCClearMemberList` | clear participant list; AccessMode is Write |

The `0xA010` entries use one-byte prefixes `00..0F`, six-byte RPC blocks and
extract the participant identifier from those blocks. Existing host-IL analysis
already resolves this endpoint through `OptolinkHandler::rpcA010` as the LON
participant-list system block.

The three reset/clear families are explicitly named and typed as reset/list
maintenance operations. None exposes:

- arbitrary source addresses;
- page/bank/high-address fields;
- a program-ROM selector;
- a memory-copy buffer;
- firmware image bytes;
- a generic monitor request.

Three of the 22 rows have `FCRead=Remote_Procedure_Call` even though their
`AccessMode` is Write. They must not be counted as demonstrated read services
merely because both low-level FC columns are populated.

### The sole undefined exact-profile read is host metadata

The one exact-profile row with `FCRead=undefined` is:

```text
event 12646
DatabaseVersionForExport
description: "DatabaseVersion For Export. Used to show the current database version"
address: <empty>
block length: 5
FCRead / FCWrite: undefined / undefined
```

It has no controller address and is not an undocumented Optolink transaction.

### Consequence for the preferred firmware path

This closes the complete **Vitosoft-catalogued exceptional read surface** for
the exact local `VDensHO1 / 20C2` profile.

There is no remaining exact-profile RPC/undefined event that can plausibly be
reinterpreted as a firmware/ROM/monitor/page/bank/copy service.

This does **not** prove that the running controller firmware contains no hidden
service outside the Vitosoft event catalogue. It does prove that such a service
is not hiding among the 23 non-`Virtual_READ`/non-`GFA_READ` read
definitions previously left only as aggregate counts.

Combined with the already closed local paths:

- `KMBUS_RAM_READ 0x41` -> mirrored logical objects;
- `XRAM_READ 0x31` -> all six source-derived local shapes rejected;
- `KMBUS_EEPROM_READ 0x43` -> not a demonstrated linear EEPROM/ROM space;
- exact VDensHO1 RPC surface -> LON/reset/list/error-history semantics only;

the preferred Optolink firmware path now depends even more strongly on either:

1. a historical/private application monitor not represented in Vitosoft
   metadata; or
2. a controller service entered through a sequence not modelled as a normal
   Vitosoft event.

No new live probe follows from this result.

## Active continuation: replaced Wiki blobs and global RPC sanity check

Two remaining archival false-positive classes were audited after the exact
VDensHO1 service-surface classification.

### Historical archive blobs no longer present in the current Wiki tree

The complete reachable OpenV Wiki Git history contains:

```text
76 archive blobs (.zip/.rar/.7z)
6 archive blobs whose content differs from the file currently stored at the
  same path
```

The six superseded archive versions are historical revisions of:

```text
Viess-ion_1_2_0_4.zip
Vies-sion_V1.2.zip
xml_ohneVS.zip
13102012_vito.zip
vito.zip
vito_VScotHO1.zip
```

They were materialized directly from Git blob objects and recursively unpacked.
The historical-only extraction produced 76 files.

No historical-only file or binary string recovered:

- `M30612` / `M16C`;
- a ROM/flash monitor;
- page/bank/window selector semantics;
- a firmware dump implementation;
- a persisted multi-byte `CB/C5/AE/9E/43/6E` selector sequence;
- a >16-bit protocol address definition.

The older `vito.xml` / `vcontrold.xml` variants still show the familiar
public GWG low-level macros and `2098 -> KW` identification, not a
V200KW2-specific low-level bridge.

### Vies-sion readPages / rdPage is not a memory-page mechanism

The superseded `Vies-sion_V1.2.zip` initially looked interesting because its
.NET binary contains symbols:

```text
readSystemValues(string readPages, ...)
updController(string rdPage)
```

and the archive contains `SystemAdresses.txt`.

The binary was decompiled to IL with the already isolated `monodis` tooling.

The result is unambiguous:

- `readPages` is compared against `Parameter.Category`, `"All"` and
  `"Bedien"`; it selects UI/data categories, not MCU memory pages;
- the `rdPage` argument in `updController()` is not used at all;
- the configured read header is `41050001`, the normal P300
  `Virtual_READ` request prefix;
- each read message is constructed as
  `msghdrrd + AddrString + LenString`;
- `Parameter::get_AddrString()` formats the address with `"X4"`;
- `Parameter::get_LenString()` formats length with `"X2"`.

So the effective request is limited to a normal four-hex-digit / 16-bit
address plus one-byte length.

The accompanying `SystemAdresses.txt` contains 886 ordinary
`<4-hex-address><2-hex-length>` entries. It is an address catalogue, not a
page/bank map.

This closes `Vies-sion` as a hidden page/high-address firmware-reader lead.

### Global Vitosoft RPC sanity check

The global low-level Vitosoft catalogue contains 1,034 rows that use
`Remote_Procedure_Call` for read and/or write, spanning 113 unique RPC
addresses.

A metadata/name scan across that entire RPC population found no endpoint named
or described as:

- firmware/ROM/flash read;
- bootloader;
- monitor;
- program-memory page/bank/window;
- memory-copy/readback;
- software-image download/upload.

The superficially service-like hits are configuration reset, service-PIN,
LON/MBus configuration/trending, error/list maintenance and similar application
services. They do not expose a generic memory address field.

This global check is weaker than the exact VDensHO1 classification because an
unnamed private service could still exist outside the event database. It does,
however, remove the hypothesis that an obvious generic firmware RPC is present
elsewhere in the same Vitosoft event catalogue and merely absent from the
local profile.

### Resulting archival priority

The remaining preferred-path evidence gap is now concentrated even further on
material that was **never represented by the surviving public/configuration
catalogues**:

1. a private OpenV developer-forum post or attachment;
2. a local KarlKoch tool/script/configuration;
3. an undocumented controller monitor/service entry sequence;
4. a trace captured while such a service was active.

No live test is justified by these negative findings.

## Active continuation: private OpenV forum fragment recovered through public issue comments

A new archival route was confirmed in the imported OpenV Wikispaces discussion
history: later public posts can contain fragments quoted from the former
private OpenV forum.

OpenV issue #245 contains a 2015 reply by Hanspeter (`vitoopen`) explicitly
quoting a private-forum post dated 2009-01-17 22:31. The quoted material
contains protocol implementation detail that is absent from the surviving
public wiki page itself.

Source:
https://github.com/openv/openv/issues/245#issuecomment-339633725

### Archival consequence

The former private forum is therefore not completely opaque. At least some
private material survived indirectly as quotations in later Wikispaces
discussions that were subsequently imported into GitHub issues/comments.

A targeted search of other issue-comment hits for phrases such as "alten
Forum", "Forum vom" and similar quotation markers did not recover another
comparable private protocol fragment in this pass. Issue #245 is currently the
strongest demonstrated example.

Imported comment bodies and quoted historical fragments should therefore be
treated as a first-class archival source alongside wiki revisions, attachments
and SourceForge history.

### 2098 relevance

The recovered 2009 fragment does not name V200KW2, device `2098`,
M30612/M16C, a page/bank selector, monitor entry or a program-ROM copy
operation.

No `2098` trace using the low-level GWG memory families was recovered in the
accompanying GitHub issue/comment searches. The live-test gate remains closed.

## Active continuation: private OpenV developer-site provenance narrowed

The historical ownership and timeline of the lost private development
environment can now be stated more precisely.

### pshome is Peter Schulze

The recovered original V-Comm distribution contains:

```text
AUTHORS.txt:
Peter Schulze <v-control@mailsnake.com>

COPYING.txt / MANUAL.txt:
Copyright 2007 Peter Schulze
```

This matches the contemporary HaustechnikDialog history where Marcus later
refers to `pshome` as "Peter" while discussing the Windows V-Control
development.

This identity is useful here only as project provenance: it ties the recovered
V-Comm source, `pshome`, the `v-control@mailsnake.com` contact and the lost
OpenV developer infrastructure to the same maintainer.

### Development platform chronology

The public HaustechnikDialog thread preserves a useful sequence:

- **2007-04-12:** pshome states that he will provide the development platform
  and asks productive contributors to contact him by email.
- **2007-06-24:** a later contemporary quotation of pshome's post says that a
  login to "our forum" gives access to the raw KW1/KW2 protocol information
  and the history of how it was reverse engineered.
- **2007-12-29:** pshome explicitly offers a login to the
  `Entwicklerforum` for KM-Bus/Optolink protocol details.
- **2009-02/03:** users still ask for access; Kathrin reports that pshome is
  less active but still forwards V-Control requests to people continuing the
  development.
- **2009-10-26:** Marcus reports that Peter/pshome plans no further Windows
  V-Control development but has released the communication libraries.
- **2010-01-05:** Marcus explicitly confirms that the developer forum still
  exists but is not public and that pshome manages the accounts.
- **2010-08-23:** Walter can no longer find the PSHOME forum through search.
- **2010-08-27:** TerminatorIII reports that the public V-Comm source link is
  dead.
- **2010-09-04:** hgy/Vitoopen describes `openv.de` as the
  **"nicht mehr existierende Entwicklerseite"** and says BrainHunter restored
  the important downloads to the Wiki and recreated the vcontrold SVN on
  SourceForge.
- **2010-10-04:** KarlKoch begins adding the detailed V200KW2/M30612 firmware
  analysis to the OpenV Wiki.

Relevant surviving public thread pages:

```text
https://www.haustechnikdialog.de/Forum/t/59578/Vitotronic-vom-PC-steuern-ueberwachen?page=4
https://www.haustechnikdialog.de/Forum/t/59578/Vitotronic-vom-PC-steuern-ueberwachen?page=9
https://www.haustechnikdialog.de/Forum/t/59578/Vitotronic-vom-PC-steuern-ueberwachen?PostSort=1&page=20
https://www.haustechnikdialog.de/Forum/t/59578/Vitotronic-vom-PC-steuern-ueberwachen?PostSort=0&page=23
```

### Implication for the missing M30612 method

The chronology matters:

1. the private developer environment held protocol material that was
   intentionally not public;
2. the public `openv.de` developer site and source links were already lost by
   August/September 2010;
3. the reconstructed SourceForge import contains an August-2010 public XML
   snapshot and only the important recovered downloads;
4. KarlKoch's detailed M30612/disassembly documentation appears one month
   later.

Therefore absence of the firmware-readout method from SourceForge/Wikispaces
does not imply that it never existed in the OpenV development environment.
The surviving sources explicitly say that the restored public repositories
were a recovery of the important downloads, not a complete preservation of the
private developer site/forum.

### Archive-index checks

Targeted Wayback-availability checks for known paths such as:

```text
openv.de/forum/
openv.de/svn/
openv.de/svn/xml/sim-2098.ini
```

did not yield a useful 2010-era developer-forum snapshot.

The historical Common Crawl indexes `CC-MAIN-2008-2009` and
`CC-MAIN-2009-2010` were also queried for `openv.de` / `www.openv.de`.
No usable captured URL set was recovered. Some wildcard index requests return
gateway errors, so this is **not proof that no crawl ever existed**; it only
means those archive indexes currently do not provide a recoverable path.

### Current archival conclusion

The private OpenV developer forum/site is now the strongest known provenance
for information that is missing from all surviving public repositories.

However, no forum URL, attachment, trace or selector/monitor request has yet
been recovered. Workstream 1 therefore remains open, but its unresolved
surface is now much smaller:

- search for mirrors/backups of the former private OpenV developer site;
- search surviving participants' public technical archives for old exported
  logs/configs;
- search for a KarlKoch-local readout tool or trace rather than further copies
  of the known public vcontrold XML.

No production-controller live test follows from this archival conclusion.

## Active continuation: six omitted V200KW2 FCRead rows resolved from public LFS data

The previously identified public Git-LFS source in
`MorrisonHB/Optolink_02` was successfully materialized on the
`optolink-splitter` host via GitHub's media endpoint.

All downloaded objects matched the LFS pointer hashes exactly:

```text
ecnDataPointType.xml
c66a57be8004a64cf3bf686bf2aa51d77f7ee96e794e95b3d09318a78fe8f0a3

ecnEventType.xml
2338beb0e8544b6149bc4b2433ecabd9509edcdafc2e8e91f00182eba1aff7ba

DPDefinitions.xml
efec27568d398021c767771af016143bd51fc196d2d408dbb80faff84d0b19e3
```

The public dataset identifies `V200KW2` as datapoint type ID `26`.
Joining:

```text
ecnDatapointType ID 26
  -> ecnDataPointTypeEventTypeLink
  -> ecnEventType numeric row
  -> ecnEventType.xml symbolic ID
```

resolves 415 V200KW2 event links with no missing join keys.

The read-function distribution is:

```text
Virtual_READ            407
Remote_Procedure_Call     4
undefined                 2
blank                     2
```

The **six non-blank, non-Virtual_READ rows** that were omitted by the generated
catalogue are now resolved exactly:

| Event | Address | FCRead | Access | Prefix / handler | Meaning |
| --- | --- | --- | --- | --- | --- |
| `BedienparameterA1M1FunktionReset` | `0xA051` | `Remote_Procedure_Call` | Write | prefix `00` | A1/M1 operating-parameter reset |
| `BedienparameterM2FunktionReset` | `0xA051` | `Remote_Procedure_Call` | Write | prefix `01` | M2 operating-parameter reset |
| `BedienparameterM3FunktionReset` | `0xA051` | `Remote_Procedure_Call` | Write | prefix `02` | M3 operating-parameter reset |
| `Oelverbrauch_Reset` | `0x7574` | `undefined` | Write | FCWrite `Virtual_WRITE` | oil-consumption reset |
| `RPCWink` | `0xA000` | `Remote_Procedure_Call` | ReadWrite | RPCHandler `22`, block length `0` | generic RPC wink service |
| `DatabaseVersionForExport` | no controller address | `undefined` | Read | block length `5` | host/export metadata |

Two further V200KW2 rows have blank `FCRead` values:

```text
ecnStatusEventType
ecnsysEventType~ErrorNotification
```

They do not define an Optolink memory-read transaction.

### RPCWink cross-check

`RPCWink @ 0xA000` is not V200KW2-specific. The same event is linked to 22
datapoint types spanning multiple Vitotronic generations, Vitocom LAN devices,
Ecotronic, VBC550 and other controller families.

Its public event definition carries:

```text
FCRead       Remote_Procedure_Call
FCWrite      Remote_Procedure_Call
AccessMode   ReadWrite
Parameter    Byte
BlockLength  0
ByteLength   0
RPCHandler   22
```

It provides no source-address field, high-address selector, page/bank value,
copy-buffer descriptor or firmware block length.

This independently reproduces the earlier private exact-2098 trace in
`firmware-optolink-readout-research-2026-09-25.md`, which had already
identified the same three `A051` reset RPCs and `RPCWink @ A000`.

The public and private datasets differ in total V200KW2 membership counts
(415 public LFS links versus 465 unique exact events in the private trace), but
their exceptional RPC surface agrees on the relevant service candidates.

### Consequence

The six omitted generated-catalogue rows do **not** reveal the missing M30612
firmware reader.

This closes the public-LFS exceptional-`FCRead` lead as a direct path to
workstream 2. The remaining firmware mechanism must still be outside ordinary
V200KW2 datapoint metadata, most plausibly a historical/private monitor,
selector/window setup, raw developer command sequence, or ROM-to-RAM/mailbox
operation.

### Workstream-2 gate impact

Still closed. No new live request is justified by these six rows.

## Active continuation: original openv.de SVN snapshot and non-ZIP archive audit

The previous historical-archive scanner recursively inspected ZIP files, but
only recognized containers whose filenames ended in `.zip`. A second pass was
therefore run over every reachable OpenV Wiki Git blob using archive magic
bytes rather than filename extensions.

The audit covered 1,649 blobs and found no PE/self-extracting ZIP archive.
It did identify historical containers that the ZIP-only pass had skipped,
including:

```text
svn20100707-rev35.tgz
trace.log.gz
trace_r97.txt.gz
trace_r97_2.txt.gz
vitalk.tgz
patch.gz
vMon.jar
```

### Original openv.de SVN working copy recovered

The most important artifact is `svn20100707-rev35.tgz`, imported into the
Wiki on 2010-08-23 and described by the historical Wiki page as a snapshot of
the SVN archive from 2010-07-07.

Unlike the later SourceForge history, this archive contains an SVN 1.6 working
copy with its original `.svn` metadata intact.

The exact original repository identities are:

```text
vcontrold:
  URL/root: http://openv.de/svn/vcontrold
  working-copy revision: 35
  repository UUID: 641cf739-d045-0410-8dd4-adb8ee2ff659

xml:
  URL/root: http://openv.de/svn/xml
  working-copy revision: 32
  repository UUID: ec234c39-d045-0410-ada0-f70c8351f8e9
```

The metadata also shows that the relevant files themselves substantially
predate KarlKoch's October 2010 M30612 investigation:

```text
vcontrold/parser.c     r34, 2008-04-06, marcust
vcontrold/Makefile     r35, 2008-05-05, marcust
xml/vito.xml           r32, 2008-05-04
xml/sim-2098.ini       r18, 2008-03-21
```

### No hidden local modifications in the archived working copy

Every working file was compared with its pristine
`.svn/text-base/*.svn-base` version.

The XML files relevant to the 2098 bridge are byte-identical to their pristine
SVN bases:

```text
vito.xml
vcontrold.xml
sim-2098.ini
```

The apparent differences in C/H/Makefile files are entirely explained by SVN
keyword expansion, for example:

```text
/* $Id$ */
->
/* $Id: parser.c 34 2008-04-06 19:39:29Z marcust $ */
```

No uncommitted experimental parser, custom 2098 XML, selector command or
developer-only request survived in this working-copy archive.

### Original 2010 public 2098/GWG boundary

The original openv.de XML snapshot already declares:

```xml
<device ID="2098" name="V200KW2" protocol="KW2"/>
<device ID="2053" name="GWG_VBEM" protocol="GWG"/>
```

The low-level GWG-specific overrides remain attached to device `2053`.

The preserved `sim-2098.ini` contains 68 request rows. All 68 use ordinary
KW `F7`; no `CB/C5/AE/9E/33/43/6E` request occurs.

This independently proves that the public openv.de SVN snapshot already kept
`2098/KW2` separate from the low-level `2053/GWG` path before KarlKoch's
October 2010 firmware work.

### Historical compressed trace files

The three previously unscanned gzip traces were materialized and reconstructed
frame-by-frame using the actual serial sequence:

```text
write 04 -> receive 05 -> request bytes -> response read
```

Results:

```text
trace.log        639 requests
trace_r97.txt    524 requests
trace_r97_2.txt 1046 requests
total           2209 requests
```

All 2,209 reconstructed requests are exactly five bytes long and use
function code `F7`. There is no low-level GWG memory-family request and no
long selector/service frame.

Their Wiki discussion provenance also identifies them as 2013 vcontrold
serial/timeout diagnostics (r95/r97), not firmware-dump experiments.

### Other missed containers

- `vitalk.tgz`: 2013 P300/Vitodens B3HA software; no 2098 firmware path.
- `patch.gz`: build/portability patch for the old vcontrold source snapshot.
- `vMon.jar`: 2015 network/OpenHAB client for a vcontrold endpoint; no MCU
  monitor, M30612 or GWG low-level firmware semantics.
- no PE/self-extracting ZIP artifact was found in the reachable Wiki blob set.

### Consequence

This closes two remaining archival ambiguities:

1. the July 2010 public `openv.de` SVN snapshot itself contains no hidden
   2098 firmware reader or uncommitted selector/monitor code;
2. the significant non-ZIP attachments missed by the first archive pass do not
   contain the missing M30612 readout sequence.

The exact original SVN URLs and repository UUIDs are nevertheless valuable
archive keys for searching external SVN caches, old mirrors and Wayback/CDX
records.

The timing is also important: the public snapshot's relevant source/XML
content substantially predates KarlKoch's October 2010 M30612 investigation.
That further strengthens the hypothesis that the missing mechanism lived in a
private developer artifact, forum post, local script/tool or post-snapshot
command sequence rather than in the public openv.de SVN tree.

### Workstream-2 gate impact

Still closed. No new live request is justified by this archive recovery.

## Active continuation: TerminatorIII dump lineage resolved through Viess-Data source

The historical TerminatorIII thread can now be tied directly to preserved
source code rather than inferred only from forum descriptions.

In `openv/openv#10`, TerminatorIII wrote on 2011-01-17 that he was developing
his own tool to read all addresses into a binary file and had observed that
ordinary reads returned no useful data above `0x8000`.

By late 2011 his Windows tool had evolved into **Viess-Data**. A 2012 public
discussion about adding a vcontrold socket transport explicitly distinguishes
Viess-Data's existing **"Dump-Funktion"** from individually addressed
datapoints.

The earliest preserved `Viess_Data.zip` contains the C# implementation of
that dump path. The request constructed after normal `0x05` synchronization
is exactly:

```text
01 F7 <addr_hi> <addr_lo> 10
```

The state machine:

1. initializes `Read_Adress` from the user-selected start address;
2. requests 16 bytes with ordinary KW/VS1 `F7`;
3. writes the returned bytes directly to `KW200.Dump`;
4. increments `Read_Adress` by `0x10`;
5. repeats until the selected end address.

The implementation stores the address as a 16-bit-compatible value and emits
only the two address bytes shown above. There is no:

- GWG `CB/C5/AE/9E/33/43/6E` memory opcode;
- selector/page/bank byte;
- monitor-entry command;
- ROM-to-RAM copy request;
- >16-bit target address.

This establishes a direct provenance chain:

```text
2011 TerminatorIII "all addresses -> binary file" experiment
        ->
later Viess-Data "Lese Dump"
        ->
ordinary sequential 16-bit F7 reads
```

Therefore TerminatorIII's public dump/tool lineage is conclusively **not**
KarlKoch's separate M30612 firmware-readout mechanism.

The two historical observations are compatible rather than contradictory:
the public/user-level F7 dump could stop yielding meaningful data around the
ordinary virtual-address boundary while KarlKoch's private/developer technique
used an additional still-missing service/selector mechanism.

### Workstream-2 gate impact

Still closed. This removes another possible source of ambiguity but yields no
new live request.

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