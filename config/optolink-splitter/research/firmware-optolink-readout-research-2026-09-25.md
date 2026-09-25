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
