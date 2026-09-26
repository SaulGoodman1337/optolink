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