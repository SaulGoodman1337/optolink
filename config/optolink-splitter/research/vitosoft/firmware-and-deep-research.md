# VDensHO1 / WB2A deep Vitosoft and firmware research

Status: active research, 2026-09-23

## Goal

Build a durable research corpus for the local Vitodens 200-W WB2A / VDensHO1
(20C2) installation so future investigations do not need to rediscover the
same Vitosoft structures, protocol functions and binary symbols.

The research is deliberately split into two layers:

1. **Vitosoft host-side reverse engineering**
   - datapoint metadata;
   - protocol functions;
   - hidden/global events;
   - KM-BUS/KBUS system blocks;
   - .NET classes/methods;
   - DLL/EXE strings;
   - SQL/database and device-programming clues.

2. **Actual controller firmware reverse engineering**
   - code running inside the WB2A/Vitotronic/burner-control electronics;
   - runtime control algorithms;
   - pump and burner state machines;
   - internal RAM/EEPROM/flash layouts;
   - KM-BUS telegram generation.

The first layer can strongly improve protocol understanding but cannot by
itself reveal all controller algorithms. The second layer would be the
decisive source for hidden logic if an authentic firmware image can be
obtained.

## Deep Vitosoft collector

Use:

```text
tools/collect-vitosoft-deep-research.ps1
```

Companion metadata normalizer:

```text
tools/extract-vitosoft-deep-metadata.py
```

The collector is read-only. It never sends an Optolink command.

### What it collects

- SHA256 and metadata for every file in the Vitosoft installation;
- unlimited research-term hits from XML/config/help/source files;
- every DLL/EXE version record;
- all printable ASCII and UTF-16LE strings from DLL/EXE files by default;
- a filtered PE string set for Optolink/KM-BUS/pump/burner/firmware research;
- .NET type/method/property/field inventories using reflection-only loading
  where the installed runtime supports it;
- research strings from MDF/LDF/ECNDAT/SYS/LIB and firmware-like files;
- firmware/bootloader/programming/update candidates;
- a normalized VDensHO1 metadata bundle.

The normalized metadata bundle includes:

- all exact VDensHO1 linked events;
- all low-level Vitosoft access definitions;
- all global KBUS/KMBUS events;
- global research-interest events;
- events sharing low-level addresses with VDensHO1;
- device mappings for those events;
- protocol function-code inventory;
- raw JSONL preservation of selected metadata rows.

### Repository policy

Raw proprietary Vitosoft DLL/EXE binaries and any future firmware image should
not be committed to the public repository.

Commit instead:

- hashes;
- file/version manifests;
- symbol and string inventories;
- normalized metadata;
- protocol mappings;
- reverse-engineering notes;
- small original scripts written in this repository.

If a firmware image is acquired, retain the original image privately and store
its cryptographic hash plus derived research notes in Git.

## Current firmware-file result

The 2026-09-23 Vitosoft installation inventory contains 7105 files.

No obvious controller firmware image was present under common firmware
extensions such as:

```text
.bin
.hex
.mot
.s19 / .s28 / .s37
.rom
.fw
.dfu
.img
.ugw
```

The installation does contain:

```text
Database/ecnViessmann.mdf
Database/ecnViessmann.ldf
Support/DP/vsmSTSalesOrganisation.ecndat
100 DLL files
2 EXE files
multiple SYS/LIB driver files
```

These are therefore part of the deep scan.

Vitosoft text resources contain firmware/update wording, but much of the
identified device-firmware content is for Vitocom-class communication devices,
not evidence of an embedded WB2A firmware image.

The Vitosoft web application also contains device-programming pages named for
heat pumps, e.g.:

```text
Web/Service/DeviceWpProgrammingCooling.aspx
Web/Service/DeviceWpProgrammingWp.aspx
```

That proves Vitosoft has programming workflows for at least some device
families. It does not prove that VDensHO1/WB2A exposes a flash-programming path.


## 2026-09-23 deep-collector result: controller and GFA software paths

The completed deep collector scanned 7105 files and produced a normalized join
for the exact VDensHO1 / 20C2 profile. The strongest result is that software
identification is available at two separate control layers even though no
firmware-image read path was found.

### Main regulation / controller

The exact VDensHO1 event set contains:

| Address | Vitosoft meaning | Access |
| --- | --- | --- |
| `0x00FB` | Software-Index des Gerätes | `Virtual_READ` |
| `0x778C` | Version der Regelungssoftware - oberes Byte | `Virtual_READ` |
| `0x778D` | Version der Regelungssoftware - unteres Byte | `Virtual_READ` |

The local controller was already observed with:

```text
0x00FB;4 = 03 00 00 01
```

The exact VDensHO1 definition only assigns a one-byte Software-Index event to
`0x00FB`, therefore the first byte `03` is the source-supported software
index. The meaning of the remaining three bytes must remain unresolved for this
controller. Similar four-byte decompositions from other Vitosoft device
families must not be imported into VDensHO1 without hardware evidence.

`0x778C` and `0x778D` are a new, exact-profile route to the regulation
software version and should be read individually before assigning a combined
numeric/version notation.

### Fire-control / GFA layer

The complete production join changes an earlier conclusion based on the legacy
filtered event catalog: exact VDensHO1 membership contains **94 `GFA_READ`
events**.

High-value examples include:

| GFA address | Vitosoft object |
| --- | --- |
| `0x4050` | P80 ID BCU/GFA chip |
| `0x4051` | P81 Softwareversion FA |
| `0x4052` | P82 Softwareversion FA - Revision |
| `0x4053` | P83 appliance/GFA configuration |
| `0x4054` | P84 GFA phase |
| `0x4055..0x4058` | GFA status 1..4 |
| `0x4006` | P06 blower actual speed, raw * 30 rpm |
| `0x4009` | P09 blower speed setpoint, raw * 30 rpm |
| `0x400A` | P10 blower PWM setpoint, raw * 0.4 % |
| `0x4011` | P17 flame formation time, raw / 10 s |
| `0x0008` | C08 offset of gas-flow-ramp start value |
| `0x000B` | C11 qGasStart correction, signed % |
| `0x000D` | C13 correction of pre-purge/ignition/stabilisation power, signed * 2 % |

These definitions are read-only in the exact profile: their write function is
undefined. Exact profile membership establishes that Vitosoft associates these
objects with VDensHO1, but local GG1/GFA support still requires a read-only
hardware test. A failed legacy `Virtual_READ` at address `0x0083` does not
test this separate `GFA_READ` address space.

### Firmware-image / bootloader result

No file in the installation uses a common controller-firmware extension such as
`.bin`, `.hex`, `.mot`, `.s19`, `.rom`, `.fw`, `.dfu`, `.img`
or `.ugw`.

More importantly, the full low-level function inventory contains no
`FLASH_READ`, `ROM_READ`, `BOOTLOADER_READ` or equivalent firmware-dump
function. Firmware/flash wording in low-level metadata resolves to unrelated
device families, notably a LAN-card firmware-version object and Vitocom 300
"Flashdisk schreiben". Neither is linked to VDensHO1.

The heat-pump "Programming" pages in the Vitosoft web application are
parameter/programming workflows for heat-pump profiles, not evidence of a
WB2A firmware flashing interface.

Current conclusion:

- **controller software identification:** source-supported, pending direct reads
  of `0x778C/0x778D`;
- **GFA software identification:** source-supported via `GFA_READ`, pending
  local read-only validation;
- **full WB2A firmware read through known Vitosoft/Optolink metadata:** no
  supporting evidence found;
- **full firmware acquisition:** still a board/MCU identification and hardware
  dump question unless a presently unknown service path is discovered.


## Why actual firmware would matter

A genuine WB2A controller firmware image could potentially reveal:

- the source of the final internal-pump speed command;
- the transformation between A1 demand, coding-plug limits and KM-BUS output;
- burner start and flame-stabilisation timers/state machines;
- previously unknown XRAM/RAM variables;
- hidden service modes and function dispatchers;
- actual use of P300 function codes not linked to the visible VDensHO1
  metadata;
- KM-BUS frame construction and participant handling.

This would be a major step beyond Vitosoft metadata.

## Firmware acquisition questions

Before attempting a hardware dump, establish the electronics architecture.

Required evidence:

1. exact regulation/control-board part numbers;
2. high-resolution photographs of both sides of the relevant boards;
3. readable markings of the main MCU/CPU, external flash, EEPROM and other
   programmable devices;
4. separation of:
   - Vitotronic/main control processor;
   - burner-control processor;
   - coding-plug EEPROM;
   - Optolink/interface electronics;
5. available test/programming headers or service pads;
6. whether the controller firmware is internally protected.

Do not assume the coding plug contains executable controller firmware. Current
project evidence shows the coding plug contains configuration/model data and is
a separate research target.

## Current priority order

1. Read the exact main-controller software version at `0x778C/0x778D`.
2. Validate the VDensHO1 `GFA_READ` identity/version objects
   `0x4050..0x4053` read-only on the local appliance.
3. If supported, validate the high-value GFA runtime objects for blower
   actual/setpoint/PWM and flame-formation time.
4. Keep firmware-image extraction separate: identify the WB2A regulation and
   burner-control MCUs, memories and service/debug headers from hardware.
5. Continue the pump/KM-BUS work as a separate runtime-control workstream.

## External context

Vitosoft 300 is officially distributed with update service for the Vitosoft
software and device documentation. Public evidence also shows that some
separate Viessmann communication devices (for example Vitogate/Vitocom-class
products) use downloadable firmware/update packages. Those facts must not be
generalised to the older WB2A controller without device-specific evidence.


## Open task: read controller software version and firmware image

Status: **open / high-value future research**

Determine whether the installed Vitodens 200-W WB2A / VDensHO1 can expose its
software revision and, separately, whether an executable controller firmware
image can be read out non-destructively.

Treat these as two different questions.

### A. Software/version identification

Find every read-only path that can identify the actual controller software
running in the appliance, including:

- exact controller/application software version;
- firmware build/revision/date if available;
- bootloader/boot-ROM version;
- hardware/board revision;
- burner-control/GFA software revision;
- main-regulation software revision;
- software indices of subordinate KM-BUS participants;
- device identification blocks and service/system-information RPCs.

Research sources:

- exact/global Vitosoft events and hidden diagnostic groups;
- P300 `Virtual_READ`, RPC and system-block functions;
- KM-BUS/KBUS member-list and participant-information functions;
- Vitosoft service/diagnostic code and .NET methods;
- any known service-tool "device information" or "software index" workflow.

First priority is read-only identification. Do not assume that the already
known Vitosoft profile version equals the firmware revision actually running in
the boiler.

### B. Full firmware readout

Determine whether the executable firmware of the relevant WB2A electronics can
be extracted without modifying the appliance.

Investigate, in order:

1. an official/read-only Vitosoft or Optolink service command;
2. P300/KBUS/KMBUS flash/ROM/system-block read functions, if metadata proves
   such a function exists and its request semantics are understood;
3. service/programming headers or debug interfaces on the controller board;
4. direct readout of external flash/EPROM/EEPROM devices;
5. MCU debug/readback interfaces only after the exact MCU and protection state
   are identified.

Keep the main regulation, burner-control electronics and coding plug separate:
they may contain different firmware/configuration images.

### Deliverables

- reproducible command(s) for software/version readout;
- map of which processor/module each reported version belongs to;
- evidence whether a full firmware read is supported through Optolink/Vitosoft;
- if not, board/MCU-specific dump method and readout-protection assessment;
- SHA256 and private archival procedure for any acquired firmware image;
- derived disassembly/decompilation notes in Git, but no raw proprietary
  firmware image in the public repository.


## Local WB2A software / GFA identity readout — 2026-09-23

Direct read-only Virtual_READ probes returned:

```text
0x7650 = 20
0x7656 = 20 15 02 01
0x778C = 01
0x778D = 03
```

The exact VDensHO1 metadata resolves these values as follows.

### 0x7650 — burner-control chip identifier

`GFA_Kennung~0x7650` is labelled:

```text
Kennung Feuerungsautomat-Chip
ID burner control unit chip
description: identifier of the burner-control chip (hex)
```

Therefore the local burner-control chip identifier is:

```text
GFA chip ID = 0x20
```

No vendor meaning for `0x20` has yet been recovered.

### 0x7656 — four-byte coding-card identity block

Vitosoft defines four one-byte fields in the same four-byte block:

```text
byte 0 = Codierkarte Typ
byte 1 = Codierkarte Gerätekennung
byte 2 = Codierkarte Revision GWG
byte 3 = Codierkarte Revision GFA
```

The local value therefore decodes structurally as:

```text
0x7656 = 20 15 02 01

type               = 0x20
device ID          = 0x15
GWG revision       = 0x02
GFA revision       = 0x01
```

This is especially notable because the installed coding-plug / coding-card
revision has already been recorded as `2015:0201`. The raw byte sequence
`20 15 02 01` matches that printed/service revision notation exactly when
written as hexadecimal byte pairs:

```text
20 15 : 02 01
=> 2015:0201
```

This is strong local evidence that the printed/service revision string is the
direct hexadecimal rendering of the four-byte coding-card identity block,
rather than a calendar date.

### 0x778C / 0x778D — control-unit software version bytes

The exact metadata labels:

```text
0x778C  Version der Regelungssoftware - oberes Byte
0x778D  Version der Regelungssoftware - unteres Byte
```

The local values are:

```text
high byte = 0x01
low byte  = 0x03
raw pair  = 0x0103
```

At this stage, `0x0103` is the confirmed raw control-unit software-version
pair. Do not silently format it as `1.03`, `1.3` or decimal 259 until the
Vitosoft presentation/formatting rule is recovered.

These values are distinct from the Vitosoft data-definition/profile version.
