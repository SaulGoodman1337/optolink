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

1. Complete the deep Vitosoft research bundle.
2. Import the normalized VDensHO1/protocol/symbol results into the repository.
3. Recover the exact request shape for KM-BUS member-list/system-block reads.
4. Continue the read-only runtime work around `0x0A3C`,
   `0x7660`, `0x7663`, `0x0A54` and related pump diagnostics.
5. Identify the WB2A controller and burner-control MCUs from hardware
   photographs/part numbers.
6. Only then decide whether a safe firmware-dump path exists.

## External context

Vitosoft 300 is officially distributed with update service for the Vitosoft
software and device documentation. Public evidence also shows that some
separate Viessmann communication devices (for example Vitogate/Vitocom-class
products) use downloadable firmware/update packages. Those facts must not be
generalised to the older WB2A controller without device-specific evidence.
