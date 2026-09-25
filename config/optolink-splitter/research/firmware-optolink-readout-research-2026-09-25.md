# WB2A firmware readout via Optolink — research checkpoint 2026-09-25

Status: **active / read-only research**

## Objective

Determine whether the executable firmware of the local Viessmann Vitodens 200-W
WB2A / VDensHO1 / device ID `20C2` can be acquired non-destructively through
Optolink, without using erase/program/unlock operations on the production
controller.

The research question is deliberately narrower than generic MCU programming:

> Does the running Viessmann controller firmware expose a service, memory
> window, bank selector, RPC, monitor or other read mechanism that can return
> program-flash contents through Optolink?

A physical MCU programming interface remains the fallback path, but is not the
preferred first path.

## Local target and identity boundary

Locally verified software identity:

```text
device/profile       VDensHO1 / 20C2
regulation SW bytes  0x778C=01, 0x778D=03
raw SW pair          0x0103
device SW index      0x00FB=03
```

Board-family evidence currently points strongly at the GG1-era PCB
`7187393`. The owner reports from memory that the local board matches the
7187393 photo variant with the screw terminals, unlike the comparison board
without those terminals. This raises confidence but is **not formal local
photo/label confirmation**.

The current MCU working hypothesis is:

```text
Renesas/Mitsubishi M16C/62P
M30624FGPFP
```

This is intentionally a working assumption, not a proven local marking.

If this assumption is correct, the relevant architecture is approximately:

```text
program flash  256 KiB
data flash       4 KiB
RAM             20 KiB
program area    0xC0000..0xFFFFF
```

The 20-bit program-flash address range matters because ordinary P300/VS2
requests expose a 16-bit address field. A direct one-to-one program-flash dump
therefore cannot be implemented by an ordinary prefix-less VS2 read alone.

## Vitosoft / P300 boundary already established

The verified Collector-v6 Vitosoft snapshot contains no authenticated WB2A
controller firmware image and no source-backed exact VDensHO1 function named
`FLASH_READ`, `ROM_READ`, `BOOTLOADER_READ` or equivalent.

Locally tested extended read families also do not establish a program-flash
view:

- `0x41 KMBUS_RAM_READ` is implemented but mirrors ordinary virtual objects
  at the tested addresses, including dynamic pump data.
- `0x31 XRAM_READ` rejected all six source-derived legacy shapes with error
  payload `05`.
- `0x43 KMBUS_EEPROM_READ` has not demonstrated a distinct local view from
  ordinary `Physical_READ / 0x03` at the bounded tested addresses.
- `0x5F KBUS_VIRTUAL_READ` rejected the tested semantic anchors.
- `0x5D KBUS_MEMBERLIST_READ` rejected the sole source-derived shape.
- `0x55 KBUS_TRANSPARENT_READ` is not a justified live target because the
  current Vitosoft-v6 non-RPC serializer does not serialize the catalog
  `PrefixRead` selector required to distinguish the 850 definitions.

Therefore there is currently no source-backed P300 function that can simply be
renamed "firmware read".

## Important historical OpenV evidence

A stronger historical lead exists in the OpenV wiki.

Current OpenV KM-BUS documentation states for the Vitotronic 200 KW2:

```text
CPU: M30612MC
software: readable via Optolink with some effort
code size: about 128 KiB
```

The same page states that analysis was based on a disassembly of approximately
57,000 lines.

This is not a later inference. Git history shows that the MCU/readout statement
was introduced by **KarlKoch** in:

```text
commit: da56ba2f73ae09d03597d75210d8a76444595503
author: KarlKoch
date:   2010-10-04T15:50:12+02:00
page:   KM-Bus.md
```

The commit changes the generic device list into a table and adds, in the same
edit, all of the following:

- Vitotronic 200KW2;
- CPU `M30612MC`;
- firmware/code size of about 128 KiB;
- explicit statement that the software can be read through Optolink;
- the approximately 57,000-line disassembly statement.

That provenance makes the historical claim materially stronger than an
anonymous forum recollection.

Source:

- https://github.com/openv/openv/wiki/KM-Bus
- OpenV wiki Git commit
  `da56ba2f73ae09d03597d75210d8a76444595503`

### What this proves

It proves that at least one older M16C-based Viessmann Vitotronic family had a
practical firmware/software acquisition path associated by the original
researcher with Optolink.

### What it does not prove

It does **not** yet prove:

- which exact Optolink function or telegram was used;
- that the M30612 boot ROM itself was reached through the optical interface;
- that the readout was performed through normal application-mode virtual reads;
- that the mechanism exists unchanged on WB2A/VDensHO1;
- that the local MCU is M30624FGPFP;
- that the full 20-bit flash address was supplied directly in one request.

The exact historical mechanism remains the highest-value acquisition question.

## Historical OpenV tool audit

The OpenV wiki Git repository still contains several old utilities and binary
archives. A first audit focused on tools contemporary with the 2010 research.

### OptoLinkLogger v0.0.4

Files:

```text
files/OptoLinkLogger_v0.0.4.zip
SHA256 0884eaa6fef433adecd477f7848abb1f1e8d75b7b3637db249e9809f34952ce1

OptoLinkLogger.exe
SHA256 9f01cb85bb9e4c6982ac405cee2bc7e67a534e9bc95d3e7a637882c3768976ff
```

The README records that v0.0.3 added:

```text
Daten Dump mit konfigurierbaren Parametern (Start-Adr., Länge)
```

The executable also contains UI text equivalent to "dump the complete memory
(binary representation)". This initially looked like a possible match for the
historical firmware statement.

### IL recovery result

The .NET executable was disassembled offline. The relevant implementation is
`MainForm::TS_DumpAll`.

The static read-request template is:

```text
F7 00 18 30
```

and the helper functions modify it as follows:

```text
SetReadAddr(addr):
    request[1] = (addr >> 8) & 0xFF
    request[2] = addr & 0xFF

SetReadLen(len):
    request[3] = len & 0xFF
```

Thus the actual request shape is:

```text
F7 <address-high> <address-low> <length>
```

This is the normal VS1/KW **virtual read** request. The method explicitly
rejects protocols other than VS1:

```text
"Dump supports protocol VS1 only."
```

The dump loop uses blocks of at most 254 bytes. Default settings embedded in
the assembly are:

```text
DumpStartAddr = 2048  = 0x0800
DumpLength    = 4096  = 0x1000
```

Although the UI stores the start address as a 32-bit value, `SetReadAddr`
serializes only the low 16 address bits.

### Conclusion for OptoLinkLogger

**Closed as a firmware-dump mechanism.**

OptoLinkLogger's "memory dump" is a bulk dump of the 16-bit VS1 virtual address
space. It cannot directly address an M30624 program-flash range such as
`0xC0000..0xFFFFF`.

This is useful negative evidence: historical OpenV terminology such as
"Speicher dump" must not automatically be interpreted as executable MCU flash.

Other audited archive hashes:

```text
files/VitoTest_V1.8.zip
SHA256 e82bf183edb85e2c43938ab626401650b9a6bdff21eacedd5712325432ac9b9c

files/v-control1_3_0M.zip
SHA256 39abe11d671a2de7b798fdf066873a6357dfe82b918b3507db334a06c5760c22
```

The ongoing audit should focus on raw/physical/XRAM/monitor functionality
rather than normal virtual-read logging.

## Separate but relevant KM-BUS internal-memory service

A different historical mechanism exists on the **physical KM-BUS**.

OpenV's reconstructed `0x3F / 0xBF` table protocol describes command records
used between Vitotronic and Vitotrol. Later working emulator research in OpenV
issue #387 resolved a practical controller-data query:

```text
Vitotrol-like slave -> controller:
  0xBF record 0x15  <memory selector XOR 0xAA> ...

controller -> slave:
  0xBF record 0x11  <selector> <data...>
```

For slot/circuit 2 and 3 the associated request records are 0x16/0x17.

The 2018 prototype initially scanned selectors across `0x00..0xFF`. The
refined 2020 script tracks blocks such as:

```text
00 08 10 18 20 28 30 38 40 48 50 58 60 68 70 78
```

and interprets controller replies containing, depending on block:

- burner runtime and starts;
- temperature setpoints;
- current targets;
- system time;
- weekly heating/DHW/circulation schedules;
- additional controller state.

Record `0x19` is treated as a changed-block bitmap so the remote can request
only data that changed.

Sources:

- https://github.com/openv/openv/issues/387
- issue comment `426756977` by `timob0`
- later attached `kmBusAgent.py` revisions
- OpenV wiki `KM-Bus-Command-0xBF`

### Interpretation boundary

This is a real controller-internal structured data service, but it is **not
evidence of program-flash readout**. The returned structures behave like
application data blocks and schedule/state records.

It nevertheless matters architecturally because it demonstrates that Viessmann
firmware can expose internal controller structures through a communication
service that is richer than ordinary one-address/one-value datapoints.

The physical KM-BUS service should therefore be kept as an architectural clue,
not mislabelled as the firmware path.

## M16C serial-boot fallback

Independent open-source tooling confirms a second, hardware-level acquisition
route for the assumed MCU family.

`truhy/m16c-flasher` implements the M16C/62P built-in serial-I/O bootloader
and was tested by its author on `M30624FGPGP`. It implements read, ID check,
bootloader-version/status and flash-page access.

For the M30624 family this is important because it demonstrates that a
read-only dump is technically feasible if the relevant MCU boot/UART signals
are physically reachable and the ID protection state is understood.

This fallback must remain separate from the Optolink hypothesis:

```text
Optolink application service
    !=
M16C ROM bootloader serial I/O
```

A three-pad J1 alone is unlikely to be a complete programming interface. X10
is more interesting, but no local pin mapping is proven.

No external voltage should be applied to J1/X10 until passive continuity has
identified ground, supply/reference and exact MCU pins.

## Current acquisition model

The remaining plausible paths are now:

### A. Historical Viessmann/OpenV Optolink firmware service — highest priority

Recover the exact mechanism behind the 2010 M30612MC statement.

Evidence sought:

- original source or utility;
- raw Optolink command sequence;
- page/bank selector;
- monitor/loader command;
- service-mode transition;
- dump file or disassembly metadata that reveals original address layout.

### B. Hidden controller-side bank/window/RPC service

If WB2A can expose program flash through normal running firmware, a mechanism
must bridge the VS2 16-bit address field to the M16C 20-bit program area.

Candidate architectures include:

```text
bank selector + 16-bit window
RPC copies flash page -> low-address communication buffer
service command with high-address bytes in request data
monitor routine with page number + offset
controller-side table/export routine
```

None is demonstrated yet.

### C. Physical M16C serial-boot readout

Fallback after exact local MCU confirmation and passive J1/X10 tracing.

Requirements:

- exact MCU marking;
- pin-1 orientation;
- continuity to RXD/TXD/RESET/CNVSS or other documented boot pins;
- voltage-domain confirmation;
- read-only connection plan;
- ID-protection behavior understood before attempting flash reads.

No erase/unlock operation belongs in the production-board workflow.

### D. External memory readout

If local photos reveal an external program ROM/flash, direct readout may be
simpler than MCU boot mode. No external executable-memory device is currently
confirmed on the local board.

### E. KM-BUS internal data service

Useful for state/model discovery and possibly for finding firmware-side
structures, but currently not a program-flash acquisition path.

## Why the historical M30612 lead is especially valuable

The target families are not identical, but there is a meaningful structural
analogy:

```text
historical Vitotronic 200 KW2:
    M30612MC
    ~128 KiB code
    documented by OpenV as readable via Optolink

current WB2A working hypothesis:
    M30624FGPFP
    M16C/62P
    256 KiB program flash
    Optolink / P300 service layer
```

If the older readout was implemented in Viessmann application firmware rather
than only in an MCU-specific boot configuration, the same design concept may
have survived across controller generations even if the exact function code
changed.

That is now a concrete research hypothesis rather than a reason to blind-scan
function codes.

## Next research actions

### Offline / Internet

1. Continue OpenV wiki Git-history audit around 2008–2011.
2. Search old tool archives for:
   - raw `SEND` sequences outside normal virtual read/write;
   - `Physical_READ`, XRAM, EEPROM and port functions;
   - bank/page/monitor/boot/ROM terminology;
   - large sequential binary output paths.
3. Search historical HaustechnikDialog/OpenV posts by the original researchers,
   especially KarlKoch and contemporaries.
4. Search Wayback/archive copies of old OpenV download pages and the former
   private/developer material where publicly archived.
5. Inspect historical binaries only offline; do not execute unknown Windows
   tools on the production host.
6. Compare documented M30612 and M30624 memory/programming architecture to
   determine which mechanisms could plausibly be shared.

### Local hardware

1. Photograph the actual WB2A controller before active probing.
2. Confirm board number/revision and main MCU marking.
3. Establish QFP pin-1 orientation.
4. With the board unpowered, trace J1 and X10 through passives/vias.
5. Test continuity against the M30624 working-hypothesis pins only after the
   package orientation is certain.
6. Do not inject power or logic levels into unknown pads.

### Live Optolink

No new live firmware-read probe is justified yet.

The next live command should only be sent after an offline source provides a
specific request shape and a reason to expect read-only behavior on VDensHO1.

## Research decision

The firmware-over-Optolink hypothesis remains **open and materially
strengthened by historical evidence**, but the obvious old "Dump Data" utility
has now been proven to be only a 16-bit VS1 virtual-memory dump.

The correct next step is therefore not a broad P300 scan. It is recovery of the
specific M30612-era readout mechanism, followed by a protocol/architecture
comparison against the WB2A/M30624 working model.


## BE_READ / 0x9E discriminator — closed as firmware-bank lead

During the historical GWG review, `BE_READ` / GWG wire type `0x9E` was
briefly considered as a possible "Bereich"/bank-extension mechanism because its
name was otherwise unexplained and a banked service would solve the 16-bit
Optolink vs. 20-bit M16C program-address mismatch.

The verified Collector-v6 source material now closes that hypothesis.

A dedicated extraction from the hash-verified private Vitosoft snapshot found:

```text
20 unique BE_READ event IDs
18 unique low addresses
range represented by the events: 0x0008..0x00F6
PrefixRead: none
FCWrite counterpart: BE_WRITE
AccessMode: ReadWrite
```

Representative exact event tokens are:

```text
GWG_Raumtemperatur_SollwertNormalBEM~0x0008
GWG_Trinkwasser_SolltemperaturBEM~0x0011
GWG_Niveau_HKA_BEM~0x0018
GWG_Neigung_HKA_BEM~0x0020
GWG_BetriebsprogrammBEM~0x0057
GWG_Uhrzeit_Wochentag_BEM~0x00F4
GWG_Uhrzeit_Stunden_BEM~0x00F5
GWG_Uhrzeit_Minute_BEM~0x00F6
```

The translated catalog text explicitly identifies the `0x0057` object as
the operating program of the **menügeführte Bedieneinheit**. Device membership
is confined to legacy `GWG_V*` profiles; no BE event is linked to
`VDensHO1`.

Therefore `BE_READ` is best interpreted as a Bedieneinheit-domain access
family in this catalog. It provides no evidence for a program-ROM bank
selector or extended M16C address mechanism.

Private reproducible evidence:

```text
collector-output/20260925-m16c-be-read-trace/
  be-summary.json
  be-events.json
  be-membership.csv
  raw-be-hits.txt
```

Workflow:

`.github/workflows/m16c-be-read-trace.yml`

Decision: **remove BE_READ / 0x9E from the active firmware-readout candidate
list unless independent firmware-level evidence assigns it another meaning on
a different controller family.**


## Historical M30612 memory type — mask ROM, not flash

The historical OpenV controller is now materially better constrained.

Renesas/Mitsubishi documentation places the `M30612MC` family in the
M16C/61 group. The contemporaneous M16C/61 device table and type-number scheme
show:

```text
M = mask ROM version
C = 128 KiB ROM capacity
M30612MCA = 128 KiB mask-ROM device
internal ROM: 0xE0000..0xFFFFF
internal RAM end: 0x017FF
```

The `A` suffix belongs to the documented M16C/61 device revision; the older
Renesas technical note also explicitly lists `M30612MC-XXXFP/GP` as an
M16C/61 device.

Primary/period documentation used for the architecture check:

- Renesas technical note `M16C-07-9701`, which explicitly lists
  `M30612MC-XXXFP/GP`;
- Mitsubishi M16C/61 group datasheet, which classifies `M30612MCA` as
  128-KiB mask ROM and maps its internal ROM to `0xE0000..0xFFFFF`.

### Consequence for the OpenV Optolink claim

This sharply reduces the probability that the historical statement

```text
"SW lässt sich mit etwas Aufwand über Optolink auslesen"
```

referred to an ordinary flash-programming bootloader:

- mask ROM is not a user-reprogrammable flash array;
- the M30612 application image occupies the high 20-bit ROM region;
- the documented GWG Optolink requests expose only short logical/physical
  address fields.

The historical readout therefore more plausibly involved one of:

1. a **monitor/read service implemented in the running Viessmann firmware**;
2. a pointer/page setup followed by an application-side memory-copy/read
   operation;
3. a service/debug mode entered through Optolink;
4. a still-undocumented GWG request type carrying an extended address or page.

This remains an inference from the documented memory type plus the explicit
OpenV readout statement. The exact command sequence has not yet been recovered.

### Comparison to current WB2A working hypothesis

```text
historical Vitotronic 200 KW2
  M30612MC(A), M16C/61
  128 KiB mask ROM
  ROM 0xE0000..0xFFFFF
  OpenV says software was read via Optolink

current WB2A hypothesis
  M30624FGPFP, M16C/62P
  256 KiB flash
  program flash 0xC0000..0xFFFFF
  normal VS2 address = 16 bit
```

Both therefore present the same central acquisition problem: executable code
lives above `0xFFFF`, so a useful Optolink firmware service must do more than
a plain 16-bit virtual/physical read.


## 2026-09-25 follow-up: historical ROM-checksum objects in TerminatorIII material

The OpenV wiki repository contains the historical archive:

```text
files/TerminatorIII.zip
import commit: fcd37fc
import date:   2011-01-21
archive files:
  vito_V200KW2.xml
  vito_V200KW2_extended.xml
```

Both XML files declare device `2098 / V200KW2 / protocol KW` in their header.
The extended file contains two unusually relevant objects:

```text
ChecksummeROMBerechnet
  address     0x08F0
  length      2
  description ChecksummeROM

NRF_ChecksummeROMLinker
  address     0x08F4
  length      2
  description Gespeicherte Checksumme ROM
```

These names are significant because they distinguish a checksum calculated by
the running software from a ROM checksum stored by the linker. They are
consistent with firmware which can traverse or otherwise validate its own
program ROM and expose the result through the normal 16-bit application data
space.

### Applicability boundary

The two ROM-checksum objects occur only in `vito_V200KW2_extended.xml`, not
in the smaller base `vito_V200KW2.xml`.

The difference is substantial:

```text
vito_V200KW2.xml           578 datapoints
vito_V200KW2_extended.xml 1796 datapoints
```

The extended file also contains clearly unrelated families such as many
`WPR_*` heat-pump and `SC100_*` objects. It therefore behaves as an
extended/unfiltered candidate universe rather than a trustworthy statement
that every contained object exists on physical V200KW2 hardware.

Decision:

- retain `0x08F0` and `0x08F4` as **historical ROM-service candidates**;
- do not call them confirmed V200KW2 objects without independent membership or
  live evidence;
- do not infer that they expose raw ROM bytes;
- use the naming as architectural evidence that Viessmann firmware had an
  internal concept of runtime ROM checksum versus linker-stored ROM checksum.

This strengthens the application-firmware monitor/service hypothesis slightly,
but it does not by itself solve firmware acquisition.

## 2026-09-25 follow-up: PROZESS_READ / VS1 0x7B closed as firmware-read route

The verified Vitosoft-v6 host implementation exposes another VS1 read command
that initially deserved scrutiny:

```text
FunctionCodes.PROZESS_READ = 123 = 0x7B
VS1FunctionCode.PROZESS_READ = 0x7B
```

Static host recovery shows that VS1 serializes it exactly like Virtual_READ:

```text
7B <addr_hi> <addr_lo> <length>
```

There is no high-address byte, bank selector or request-data extension in the
VS1 message object. The response converter likewise treats
`PROZESS_READ` as an ordinary returned byte block.

The verified event inventory contains:

```text
111 PROZESS_READ event definitions
177 device/event memberships
```

The recovered memberships are concentrated in the `VSorp` process-control
family. Representative events are process tuning/configuration values in the
`0x2000..` range, for example burner shutdown delta-T, pump limits and
process timers. No VDensHO1 program-ROM or firmware-dump semantic was recovered.

Private reproducible source report:

```text
collector-output/20260925-vs1-process-read-trace/summary.json
```

Decision: **PROZESS_READ / 0x7B is removed from the active WB2A firmware
acquisition candidate list unless new controller-specific evidence gives it a
different meaning.**

## Updated acquisition ranking

After the additional historical and Vitosoft work, the active ranking is:

1. **Recover the exact M30612-era Optolink readout mechanism.**
   The original OpenV statement remains the strongest direct lead.
2. **Search for an application-side ROM monitor/page service**, not merely
   another ordinary 16-bit read opcode.
3. **Use ROM checksum objects as semantic anchors** when historical firmware
   material or disassembly becomes available.
4. Keep M30624 serial boot/J1/X10 as a fallback after local hardware identity
   is confirmed.
5. Do not resume blind function-code or address sweeps on the production
   WB2A.

The two strongest negative closures now are:

- old OptoLinkLogger bulk dump = ordinary 16-bit VS1 Virtual_READ;
- Vitosoft PROZESS_READ = ordinary 16-bit VS1 process-data read.

Neither can directly address the assumed M30624 program range
`0xC0000..0xFFFFF`.


## 2026-09-25 follow-up: Viess_Data "Lese Dump" is another plain VS1 virtual dump

A second historical OpenV tool with an explicitly named dump function has now
been recovered from the wiki Git history:

```text
files/Viess_Data.zip
wiki import commit: 22510b0
import date:        2011-12-24
author:             TerminatorIII
archive timestamp:  2011-12-23
```

Unlike the native OptoLinkLogger binary, this archive contains the C# source.
The relevant implementation is
`Viess_Data/Viess_Data/Form_Main.cs`.

The GUI button is literally named `Lese Dump` and creates a file named:

```text
HH_mm_ss KW200.Dump
```

The implementation is nevertheless unambiguous. The initial request after the
normal `0x05` synchronization is:

```text
01 F7 <addr_hi> <addr_lo> 10
```

and subsequent requests use:

```text
F7 <addr_hi> <addr_lo> 10
```

The program:

1. reads 16 returned bytes;
2. appends them to the dump file;
3. increments the 16-bit `Read_Adress` by 16;
4. repeats until the user-selected end address.

Therefore the Viess_Data `Lese Dump` feature is another **sequential
16-bit VS1 Virtual_READ dump**, not an M16C program-ROM extractor.

This independently confirms the earlier OptoLinkLogger closure. Historical UI
labels containing the word "Dump" are not evidence for the special M30612
firmware-read mechanism.

Decision: close Viess_Data bulk dump as a direct program-ROM path.

## 2026-09-25 follow-up: provenance gap points to the former OpenV developer forum

The public historical trail now explains why the exact M30612 readout sequence
may be absent from the surviving wiki repository.

Contemporaneous HaustechnikDialog posts document that OpenV maintained a
separate developer forum on `openv.de`:

- in January 2010 MarcusT explicitly stated that an
  `Entwickler-Forum` existed and was not publicly accessible, with access
  managed by pshome;
- posts from the same period describe the developer material as containing the
  raw KW1/2 protocol work and reverse-engineering history;
- by June 2010 participants reported that the internal forum had been closed;
- in August/September 2010 `openv.de` itself disappeared, after which
  Vitoopen/BrainHunter restored important public downloads into the wiki/SVN.

This chronology matters because KarlKoch's explicit
`M30612MC ... SW lässt sich ... über Optolink auslesen` statement entered the
public KM-BUS documentation in October 2010. The detailed command sequence may
therefore have remained in the former developer forum or another off-repository
artifact even though the derived conclusion survived in the wiki.

A full scan of the surviving OpenV wiki Git object history was also performed:

```text
~11,273 Git objects
~1,649 blobs
```

Search terms included M30612/M16C, firmware, ROM, flash, bootloader,
disassembly, monitor and readout terminology across normal and UTF-16 strings.

Result:

- no M30612 firmware image;
- no 57,000-line disassembly;
- no dedicated firmware-read utility;
- no recovered special Optolink read sequence beyond the already known
  ordinary tools.

This negative result materially increases the value of archive recovery of the
former `openv.de` developer material rather than repeating searches over the
same surviving wiki files.

## 2026-09-25 follow-up: Vitosoft programming-position and ROM-checksum trace

A dedicated trace was executed against the verified Vitosoft-v6 archive.

Private workflow:

```text
.github/workflows/programming-mode-trace.yml
workflow commit:
fa1658d106582a5c307f2864b07a30c0193cb940

result commit:
586a03a0443c3cd93a3ebc874241c9a93d22d4bc

collector-output/20260925-programming-mode-trace/
  README.md
  summary.json
```

Result summary:

```text
matching event rows:            17
direct DataPointType memberships: 32
direct VDensHO1 memberships:     0
```

### ROM checksum objects are VBC550S/P, not VDensHO1

The exact Vitosoft config-backup memberships resolve the earlier
TerminatorIII ambiguity:

```text
ChecksummeROMBerechnet
  address:  0x08F0
  read:     Virtual_READ
  length:   2
  text:
    "Aktuell ermittelte Checksumme über die vom Programm
     belegten ROM-Bereiche. Muß mit der Checksumme des
     Linkers uebereinstimmen."

NRF_ChecksummeROMLinker
  address:  0x08F4
  read:     Virtual_READ
  write fn: Virtual_WRITE
  length:   2
  text:
    "vom Linker gebildete, im ROM gespeicherte Checksumme."
```

Recovered direct memberships:

```text
VBC550S  identification 2032
VBC550P  identification 2033
```

No direct VDensHO1 membership exists.

This is stronger than the earlier historical XML interpretation:
`0x08F0/0x08F4` are genuine Vitosoft ROM-checksum concepts, but current
evidence assigns them to VBC550S/P, not to the WB2A/VDensHO1 main regulation.

### SC100 programming-position objects are also VBC550S/P

Recovered events:

```text
SC100_ProgrammierstellungEin
  address: 0x0C04
  FCRead:  Virtual_READ
  FCWrite: Virtual_WRITE
  text:
    "Für Diagnosezwecke: Umsetzung Lesen/Schreiben
     Virtuell auf RPC von/zur SC100"

SC100_ProgrammierstellungAus
  address: 0x0C05
  FCRead:  Virtual_READ
  FCWrite: Virtual_WRITE
  same diagnostic/proxy description
```

Direct memberships are again only:

```text
VBC550S / 2032
VBC550P / 2033
```

This is useful architecture evidence for a controller-side virtual-to-RPC proxy
toward an SC100 subordinate controller. It is **not evidence that VDensHO1
exposes the same path**, and it must not be transferred to the local boiler
without a controller-specific source.

### Legacy GWG has an explicit fire-control programming-state flag

Another exact event is closer to the older gas-wall-device line:

```text
GWG_Auftragsflag_Programmieren
  address: 0x003D
  FCRead:  Physical_READ
  length:  1
  text:
    "zeigt an, ob der Feuerungsautomat in Programmierstellung steht"
```

Its recovered memberships are legacy `GWG_V*` profiles with identification
`2053`, including `GWG_VBEM`, `GWG_VBES`, `GWG_VBT2` and `GWG_VWMS`
variants.

This proves that Viessmann service metadata explicitly models a
**Feuerungsautomat programming state** on legacy GWG devices.

It does **not** prove:

- a programming state of the main regulation MCU;
- a program-ROM read operation;
- a VDensHO1 equivalent;
- that the state is entered by an Optolink command represented in this event.

### Interpretation for the WB2A firmware-acquisition problem

The programming-position search separates three previously conflated concepts:

```text
main regulation program ROM
    !=
SC100 subordinate-controller programming proxy
    !=
legacy GWG Feuerungsautomat programming state
```

The Vitosoft evidence therefore closes "Programmierstellung" as a direct
shortcut to the local M30624 main-regulation firmware.

It remains useful as architectural evidence that Viessmann controllers can
proxy service/programming operations to subordinate combustion controllers.

## Updated hard boundary

After the new trace, none of these currently provides a source-backed
VDensHO1 program-ROM read:

- VS1 Virtual_READ / `0xF7`;
- Viess_Data `Lese Dump`;
- OptoLinkLogger `Dump Data`;
- PROZESS_READ / `0x7B`;
- BE_READ / legacy `0x9E`;
- KMBUS_RAM_READ / P300 `0x41`;
- XRAM_READ / P300 `0x31`;
- SC100 programming-position events;
- legacy GWG fire-control programming-state flag.

The strongest still-open evidence remains the historical statement that the
M30612MC-based V200KW2 software itself was readable over Optolink.

The active question is therefore narrower:

> Which application-side monitor/page/copy mechanism was used to bridge the
> 16-bit Optolink request space to the M30612 high program-ROM region?

That mechanism, rather than another ordinary datapoint read function, is the
next acquisition target.


## 2026-09-25 follow-up: v_comm_dll source provenance and VScotHO1 branch

The old V-Comm source trail is now better constrained.

### The VB6 source definitely existed outside the surviving installer archive

A January 2010 HaustechnikDialog discussion contains a developer working
directly from the `v_comm_dll` source and quoting a concrete source line in
the receive/error path involving `V_DataRX` and comparison against `0x15`.
This is direct evidence that the VB6 source was circulating at the time, even
though the surviving OpenV archive currently exposes only:

```text
files/v_comm_dll.zip
  setup_vcomm.exe
  MANUAL.txt
  AUTHORS.txt
  COPYING.txt
```

The manual identifies V-Comm as a VB6 ActiveX component by Peter Schulze,
first public release May 2007.

The embedded installer is a Wise installer. This task is now **closed**:
the installer was statically extracted and contains the original VB6 source,
compiled DLL, Visual Basic sample project and Excel sample.

Detailed reproducible analysis:
[v-comm-dll-source-recovery-2026-09-25.md](v-comm-dll-source-recovery-2026-09-25.md).

The recovered `v_comm.cls` explicitly supports `VDensHO1 = 0x20C2`, but
its transport is limited to normal P300 `Virtual_READ / 0x01` and
`Virtual_WRITE / 0x02` with a two-byte address. An exhaustive audit of
`SerialPort.Output` found no raw/service/monitor/high-address path.

### Walter/wkiffe maintained a VScotHO1 modification

Public forum chronology:

- 2010-11-20: Walter/wkiffe states that he modified `v_comm_dll` for
  `VScotHO1` and could read all values from his system.
- 2013-12-10: the same user states that he wants to publish the source of his
  VB6 program / modified `v_comm_dll`.
- 2013-12-14: he is told to upload it to the OpenV Wikispaces site.

This branch is relevant because VScotHO1 is architecturally closer to the
later 20C2/VDensHO1 generation than the old KW2/GWG examples.

A Git-history audit around December 2013 / January 2014 found **no committed
Walter/wkiffe VB6 archive** and no newly introduced `.bas`, `.frm`,
`.cls` or `.vbp` source. A complete scan of all surviving OpenV ZIP
archives likewise found no VB6 source tree; only the Wise installer and a
`vito_VScotHO1.xml` archive are present.

Therefore Walter's source was either never uploaded to the surviving wiki,
uploaded outside the imported Git history, or later lost.

This is now a specific archival acquisition target.

## 2026-09-25 follow-up: later Viess_Data source is plain P300 Virtual_READ

The 2014-era `viessdata201.zip` archive contains full C# source and supports
the VS2/P300 framing used by later controllers.

Its read path constructs only:

```text
41 05 00 01 <addr_hi> <addr_lo> <len> <checksum>
```

where function code `0x01` is Virtual_READ.

The code identifies the controller via `0x00F8` and then performs ordinary
16-bit datapoint reads. No alternate function code, page selector, program-ROM
read, flash monitor or >16-bit address mechanism was found in the
communication implementation.

Decision: the later Viess_Data source is useful as an independent P300 framing
reference but does not contain the missing firmware-read mechanism.

## Refined archival priorities

The firmware-acquisition research now has two concrete lost-source targets:

1. **KarlKoch / old OpenV developer-forum M30612 material**
   - likely source of the 128-KiB Optolink software-read claim and the
     ~57,000-line disassembly.
2. **Walter/wkiffe VScotHO1-modified v_comm_dll VB6 source**
   - closer-generation Optolink implementation;
   - may preserve service/raw-command handling lost from the public installer.

Until either source is recovered, ordinary public dump/logging tools continue
to converge on the same 16-bit Virtual_READ behavior and add no new path into
main program ROM.


## 2026-09-25 follow-up: VitosorpAccessController proves an Optolink RPC address-proxy architecture

A targeted static trace was executed against the verified Collector-v6 archive
to answer a narrower question:

> Does any recovered Vitosoft RPC serializer move a target address into request
> data and route the request through a fixed Optolink endpoint?

This matters because such a proxy/window architecture is one of the plausible
ways a 16-bit Optolink request space could reach another address domain.

Private reproducible evidence:

```text
workflow:
  .github/workflows/optolink-high-address-rpc-trace.yml

workflow source commit:
  df21ed4f2fb95fd4c21ebbfd598383177b016e3b

result commit:
  9649093181eb148bf54dfada416c253e7489253f

collector-output/20260925-optolink-high-address-rpc-trace/
  README.md
  summary.json
  exact-methods.json
  exact-methods.txt
  serializer-candidates.json
  event-candidates.json
```

### Exact read serializer recovered

`RPCConverter.ConvertRpcToDevice_VitosorpAccessController()` implements a
real address proxy.

For a read request, Vitosoft takes the original event address and block length,
then rewrites the request as:

```text
original target:
  EventType.Address = <16-bit target address>
  EventType.BlockLength = <requested length>

RPC proxy:
  endpoint = 0xA400
  payload  = <target_addr_hi> <target_addr_lo> <requested_length>
```

The recovered code is equivalent to:

```text
target = BitConverter.GetBytes(EventType.Address)

EventType.Address = 0xA400
BlockDataToDevice = [
    target[1],
    target[0],
    requested_length
]
BlockLength = 3
```

For writes the same concept uses fixed endpoint `0xA401`:

```text
payload =
  <target_addr_hi>
  <target_addr_lo>
  <data_length>
  <data...>
```

The response path then copies the returned RPC payload back into the original
event representation and applies the normal event conversion.

### Why this is important

This is the first recovered Vitosoft implementation in this workstream that
demonstrates the **exact architectural pattern** previously hypothesized for a
hidden firmware-access mechanism:

```text
ordinary Optolink RPC
        |
        v
fixed service endpoint
        |
        v
target address carried inside request data
        |
        v
controller-side proxy accesses another object/address
```

Therefore it is no longer merely hypothetical that Viessmann uses
controller-side address-proxy services behind Optolink.

### Why handler 71 does not solve the M30624 firmware dump

The same static recovery also closes this specific handler as a direct
high-address program-ROM path.

The serializer uses only:

```text
target[1]
target[0]
```

from `BitConverter.GetBytes(EventType.Address)`.

It does **not** use:

```text
target[2]
target[3]
>> 16
>> 24
PrefixRead
PrefixWrite
bank/page bytes
```

Thus the proxy target remains strictly 16 bit.

The fixed proxy endpoints are:

```text
0xA400  read
0xA401  write
```

and the recovered event scan found **zero catalog rows explicitly using
RPC handler 71 / VitosorpAccessController** in the captured event definitions.
The implementation exists in the host code as a generic/specialized capability,
but there is no current source-backed VDensHO1 event which activates it.

### High-address serializer scan

The same trace inspected request serializers for address-style use of:

- third/fourth bytes from `BitConverter.GetBytes(Address)`;
- `>> 16` / `>> 24`;
- page/bank/address-extension fields;
- PrefixRead/PrefixWrite used as an address extension;
- request-data construction around an event address.

No recovered serializer in the traced Vitosoft core uses a third or fourth
byte of `EventType.Address` to construct a target address.

Four-byte `BitConverter` payloads do occur elsewhere, for example for
32-bit **values** such as impulse counters / LON parameters. They are not
address extensions.

### Research decision

`VitosorpAccessController` is therefore:

- **positive architectural evidence** that fixed-endpoint RPC address proxies
  exist in Viessmann/Vitosoft;
- **negative evidence** for this particular handler as the missing M16C
  20-bit program-ROM path.

Do not live-probe `0xA400/0xA401` on VDensHO1 merely because the serializer
has been recovered. No VDensHO1 applicability or high-ROM semantic is proven.

The next static target is now more precise:

> enumerate every recovered fixed RPC/service endpoint which builds request
> payloads from addresses, offsets, selectors or opaque byte arrays, and look
> specifically for a service carrying more than 16 target-address bits or a
> page/bank selector.

This is a substantially narrower search than scanning arbitrary P300 function
codes.


## 2026-09-25 follow-up: original V-Comm source recovered from Wise installer

The historical `files/v_comm_dll.zip` archive has now been fully resolved.

Static Wise extraction recovered:

```text
MAINDIR/Source/v_comm.cls
MAINDIR/Source/V_comm_dll.vbp
MAINDIR/V_comm_dll.dll
MAINDIR/Samples/VisualBasic/...
MAINDIR/Samples/Excel/v-comm.xls
```

The key source hash is:

```text
v_comm.cls
SHA256 12b7d426f2410c7e237fc0459d44cf4b192f96103b7fa798004a34a35091610d
```

The source explicitly contains:

```text
VDensHO1 = 0x20C2
```

and a dedicated VDensHO1 address map matching the local P300 model.

The transport audit is conclusive:

```text
protocol start: 16 00 00
protocol stop:  04

reads:
  41 05 00 01 <addr_hi> <addr_lo> <len> <checksum>

writes:
  function 0x02 with the same two-byte address model
```

Every `SerialPort.Output` site in the class was enumerated. There is no
additional raw function-code sender, ROM/flash monitor, page selector, bank
selector or address byte beyond the normal 16-bit target.

Decision:

**The surviving public V-Comm implementation is closed as the hidden
VDensHO1/20C2 firmware reader.**

This is especially useful because it is not a cross-family inference: the
source itself names the exact local device ID `20C2`.

The historical KarlKoch M30612MC readout claim therefore remains a genuinely
different mechanism that has not yet been recovered.

Detailed note:
[v-comm-dll-source-recovery-2026-09-25.md](v-comm-dll-source-recovery-2026-09-25.md).

Public evidence commit:
`e9d1d66c5c214a7dcb8fb7a88c931c273ec7f326`.
