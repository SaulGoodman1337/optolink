# Vitosoft-derived research data

This directory contains **project-specific derived data**, not a blind mirror of
the complete Vitosoft data set.

The project now has two independently traceable Vitosoft sources:

- the public `MorrisonHB/Optolink_02` reference set at commit
  `ec77c6917909ae229b17a6104db4f81f9a31e263`;
- a real Vitosoft 300 SID1 production installation collected on 2026-09-23
  after first launch, with DataPointDefinitionVersion **0.0.26.4683**.

Exact hashes for both source sets are recorded in `source-manifest.json`.

## Where to obtain the original Vitosoft files

The preferred source is a **real Vitosoft 300 SID1 installation after Vitosoft
has been launched at least once**.

Known installation path:

~~~text
C:\Program Files\Viessmann Vitosoft 300 SID1\ServiceTool\MobileClient\Config\
~~~

The Vitosoft reverse-engineering documentation explicitly identifies the
production-generated files in this directory:

~~~text
ecnDataPointType.xml
ecnEventType.xml
ecnVersion.xml
~~~

The actual Vitosoft 300 SID1 installation used for this project was checked on
2026-09-23. The relevant production files are split across several directories.

Verified paths:

~~~text
C:\Program Files\Viessmann Vitosoft 300 SID1\ServiceTool\MobileClient\Config\
    ecnDataPointType.xml
    ecnEventType.xml
    ecnVersion.xml
    ecnEventTypeGroup.xml
    sysDeviceIdent.xml
    sysDeviceIdentExt.xml

C:\Program Files\Viessmann Vitosoft 300 SID1\ServiceTool\Support\DP\
    DPDefinitions.xml

C:\Program Files\Viessmann Vitosoft 300 SID1\ServiceTool\Web\XmlDocuments\
    Textresource_de.xml
    Textresource_en.xml

C:\Program Files\Viessmann Vitosoft 300 SID1\ServiceTool\Database\
    ecnViessmann.mdf
    ecnViessmann.ldf
~~~

A `configbackup` directory is also present below:

~~~text
C:\Program Files\Viessmann Vitosoft 300 SID1\ServiceTool\MobileClient\Config\configbackup
~~~

It may contain older pre-regeneration metadata and should be preserved for
version comparison when practical.

Important: the installer contains older XML files. On first Vitosoft launch,
at least `ecnDataPointType.xml`, `ecnEventType.xml` and `ecnVersion.xml`
are regenerated from the Vitosoft SQL database. Older installer copies may be
moved to a directory named `configbackup`.

If the standard path does not exist, also check the equivalent tree below
`C:\Program Files (x86)\` or search the system for `ecnEventType.xml`.

### Recommended collection set

Highest priority:

~~~text
DPDefinitions.xml
ecnEventType.xml
ecnDataPointType.xml
ecnVersion.xml
~~~

Very useful additional files:

~~~text
ecnEventTypeGroup.xml
Textresource_de.xml
Textresource_en.xml
sysDeviceIdent.xml
sysDeviceIdentExt.xml
~~~

If available, also preserve the Vitosoft SQL database. A current community
reference locates it under:

~~~text
C:\Program Files\Viessmann Vitosoft 300 SID1\ServiceTool\Database\
~~~

Look especially for:

~~~text
ecnViessmann.mdf
ecnViessmann.ldf
~~~

The database is useful because the generated XML metadata originates from it
and community tooling can query it directly when an XML field is missing. It
also contains cached values from a Vitosoft/device synchronization, which can
be useful later for correlating metadata with values actually read from a
controller.

### Windows PowerShell collection

From an installed Vitosoft system:

~~~powershell
$base = "C:\Program Files\Viessmann Vitosoft 300 SID1\ServiceTool\MobileClient\Config"

Get-ChildItem $base -File |
  Where-Object {
    $_.Name -in @(
      "DPDefinitions.xml",
      "ecnEventType.xml",
      "ecnDataPointType.xml",
      "ecnVersion.xml",
      "ecnEventTypeGroup.xml",
      "Textresource_de.xml",
      "Textresource_en.xml",
      "sysDeviceIdent.xml",
      "sysDeviceIdentExt.xml"
    )
  } |
  Select-Object Name, Length, FullName
~~~

If the path is unknown:

~~~powershell
Get-ChildItem "C:\Program Files","C:\Program Files (x86)" -Filter ecnEventType.xml -Recurse -ErrorAction SilentlyContinue |
  Select-Object FullName
~~~

Do not add `DPDefinitions.xml` directly to this repository: the known source
copy is about 186 MB. Keep the original externally, record its hash, and commit
only project-specific derived extracts.

## Why derived data is stored here

The upstream repository exposes the original large Vitosoft XML files through
Git LFS. The files include a roughly 186 MB `DPDefinitions.xml`, a roughly
10 MB `ecnEventType.xml`, language resources and related metadata.

For this project the useful information is the subset that describes the local
controller and the protocol questions under investigation. Keeping a normalized
derived extract has several advantages:

- it is small enough to review and version normally;
- every row can be traced back to a device/event definition;
- research does not depend on an external GUI;
- future discoveries can be reproduced with an extraction script;
- protocol evidence can be kept separate from hypotheses.

The full upstream Vitosoft-derived files should not be copied into this repo
without a specific need and a clear redistribution basis. Their hashes and
paths are recorded in `source-manifest.json` so exact source versions remain
identifiable.

## Current local extracts

### `vdensho1-events.csv`

Structured transform of the upstream
`Documentation/DP_Listen/DP_VDensHO1.txt` device export.

Current row count: **385 events**.

This file is now considered a **legacy filtered/group-oriented view**. The full
production XML join contains **581 VDensHO1 events**. See
[full-extraction-2026-09-23.md](full-extraction-2026-09-23.md).

Columns:

- section;
- group;
- event ID;
- display name;
- technical token;
- numeric address when present;
- displayed data type;
- Vitosoft visibility condition;
- source device.

This file remains useful for human-readable group/visibility context, but it is
not the canonical complete event inventory.

### `vdensho1-kmbus-participants.csv`

The **18 events** from the Vitosoft `Diagnose System -> KM-Bus-Teiln.` group.

Important entries include:

| Meaning | Event | Address |
| --- | ---: | ---: |
| remote control A1/M1 identification | 1055 | 0x27A0 |
| remote control A1 software index | 5290 | 0x0A5C |
| remote control M2 identification | 1053 | 0x37A0 |
| remote control M2 software index | 5291 | 0x0A60 |
| internal pump identification | 885 | 0x5730 |
| internal pump software index | 5292 | 0x0A54 |
| KM-BUS pump A1 identification | 2894 | 0x27E5 |
| KM-BUS pump A1 software index | 5298 | 0x0A4C |
| KM-BUS pump M2 identification | 2897 | 0x37E5 |
| KM-BUS pump M2 software index | 5299 | 0x0A50 |
| mixer extension software index | 5293 | 0x0A44 |
| solar controller software index | 5303 | 0x0A40 |
| Vitocom software index | 5305 | 0x0A58 |
| external extension software index | 5289 | 0x0A48 |

These addresses are **Vitosoft-derived event addresses**. They do not by
themselves establish which VS2 function code is required to access each event.

### `vdensho1-vitotrol-events.csv`

Curated low-level events relevant to Vitotrol/remote-control emulation on the
exact VDensHO1 profile. It includes remote identification, software index,
room-temperature actual/status, room influence and related setpoint objects.

Key source result:

~~~text
0x27A0 A1/M1 remote identification
  Virtual_READ + Virtual_WRITE
  0 = not present
  1 = Vitotrol 200
  2 = Vitotrol 300

0x0896 A1/M1 measured room temperature
  Virtual_READ only
  Div10 °C
~~~

See [full-extraction-2026-09-23.md](full-extraction-2026-09-23.md) for the
complete interpretation boundary.

### `project-interest-events.csv`

A curated global Vitosoft event index for the active project workstreams.

Current row count: **161 events**.

Rows are tagged with one or more categories:

- `km_bus_remote`;
- `coding_plug`;
- `burner_flame_fan`;
- `pump_logic`.

This intentionally includes useful events that are not necessarily part of the
VDensHO1 device tree but are valuable reverse-engineering leads, for example
coding-plug and GFA/SCOT event families.

### `tools/extract-vitosoft-project-data.py`

Repository tool for the point at which the full Vitosoft XML LFS objects are
available locally.

Example:

~~~bash
python3 tools/extract-vitosoft-project-data.py \
  --data-dir /path/to/vitosoft/XML \
  --device VDensHO1 \
  --out-dir config/optolink-splitter/research/vitosoft/generated
~~~

It joins the device membership from `DPDefinitions.xml` against
`ecnEventType.xml` and emits:

- a complete low-level device-event CSV;
- a `KBUS_*` / `KMBUS_*`-only CSV;
- an extraction summary JSON.

For protocol-family research, add `--include-global-wilo`. This performs a
global metadata pass for events whose low-level access uses
`Virtual_WILO_READ` or `Virtual_WILO_WRITE`, maps those events back to the
Vitosoft device types that reference them, and writes
`virtual-wilo-events.csv`. This is intended for metadata-first, read-only
reverse engineering; it does not send any hardware command.

## Full low-level join status

The missing low-level source set was supplied from a real Vitosoft
installation on 2026-09-23. The join of `DPDefinitions.xml` and
`ecnEventType.xml` is now validated.

For VDensHO1:

~~~text
datapoint type ID: 60
event links:       581
missing access:    0
KBUS/KMBUS events: 0
~~~

The validated extractor is `tools/extract-vitosoft-project-data.py`.

The most important protocol result is that the exact VDensHO1 profile uses
ordinary `Virtual_READ/Virtual_WRITE`, `GFA_READ` and RPC accesses, but no
`KBUS_*` or `KMBUS_*` FCRead/FCWrite entries. Global KBus definitions still
exist in Vitosoft and are documented separately.

See [full-extraction-2026-09-23.md](full-extraction-2026-09-23.md).

## Project policy for Vitosoft information

When Vitosoft-derived information materially affects this project:

1. preserve the exact upstream source/ref or local file hash;
2. extract the project-relevant subset into this directory;
3. document interpretation separately from raw/derived facts;
4. prefer machine-readable CSV/JSON plus a short Markdown explanation;
5. do not rely on an external source remaining available;
6. do not silently promote inferred semantics to verified protocol facts.

See also:

- `../kmbus-optolink-research.md`
- `../vitotrol-kbus-optolink-emulation.md`
- `source-manifest.json`


## Virtual-WILO inventory result — 2026-09-23

The global `--include-global-wilo` pass was run against the source-verified
production XML set.

Result:

```text
exact VDensHO1 Virtual_WILO events: 0
global Virtual_WILO_READ events:   74
global Virtual_WILO_WRITE events:   9
linked Vitosoft device profiles:    WILO only
common virtual base address:        0xA0C2
```

The Wilo events use two-byte `PrefixRead` selectors that correlate exactly
with public Wilo PLR parameter IDs, for example `0007` for pump speed,
`0011` for pump type, `0027` for diagnostic state, `0028` for pump
command and `002A` for control mode.

This identifies `Virtual_WILO_READ/WRITE` as a Wilo-PLR tunnelling mechanism
for the separate Vitosoft `WILO` device profile. It is not used by the exact
VDensHO1 event model.

See `../pump-start-heating-vs-dhw.md` for the resulting WB2A interpretation
and the exact read-only probe commands.


## KM-BUS / internal-pump PowerShell collector

For the WB2A internal-pump investigation, use:

```text
tools/collect-vitosoft-kmbus-pump.ps1
```

The collector is intentionally read-only and compact. It:

- inventories the detected Vitosoft installation;
- records hashes of the three core production metadata files when present;
- searches text/XML/configuration files for KM-BUS and internal-pump symbols,
  addresses and manufacturer terms;
- scans EXE/DLL files for matching embedded ASCII/UTF-16 strings without
  copying the binaries;
- produces a ZIP suitable for repository research/import.

Typical direct PowerShell invocation from GitHub:

```powershell
$script = "$env:TEMP\collect-vitosoft-kmbus-pump.ps1"

Invoke-WebRequest `
  -Uri "https://raw.githubusercontent.com/SaulGoodman1337/optolink/main/tools/collect-vitosoft-kmbus-pump.ps1" `
  -OutFile $script

Set-ExecutionPolicy -Scope Process Bypass -Force
& $script
```

If automatic installation discovery fails:

```powershell
& $script -Root "C:\Program Files (x86)\Viessmann Vitosoft 300 SID1\ServiceTool"
```

The ZIP contains only inventories, search hits, hashes and short binary-string
contexts; it does not include Vitosoft EXE/DLL binaries.


### KM-BUS collector production result

The 2026-09-23 local run inventoried 7105 Vitosoft files and produced 8837
stored text-hit rows plus 12 binary-string hits.

The most important new event discovered outside the exact VDensHO1 UI
membership is:

```text
InternePumpeDrehzahl_res~0x0A3C
```

Installed Vitosoft language resources describe it as the **set speed of the
internal pump transferred to the pump**. This makes `0x0A3C` a priority
read-only runtime probe for the WB2A.

The collector now also retains the following terms even after the generic
per-file storage limit has been reached:

```text
InternePumpeDrehzahl_res
0x0A3C
sysblock_KMBus_LonMemberList
KMBusEquipment
KBUS_MEMBERLIST_READ / WRITE
KMBUS_RAM_READ / EEPROM_READ
BusHandlerType
OptolinkHandler
```

It continues scanning to EOF after the generic hit limit and writes a
`hit-summary.csv` report, so a large translation/XML file can no longer hide
later priority matches.


## Deep research collector

For a complete reusable Vitosoft research bundle, use:

```text
tools/collect-vitosoft-deep-research.ps1
```

It supersedes the narrow one-purpose collectors when the goal is to preserve
future research context for VDensHO1/20C2.

Direct PowerShell invocation:

```powershell
$script = "$env:TEMP\collect-vitosoft-deep-research.ps1"

Invoke-WebRequest -Uri "https://raw.githubusercontent.com/SaulGoodman1337/optolink/main/tools/collect-vitosoft-deep-research.ps1" -OutFile $script

Set-ExecutionPolicy -Scope Process Bypass -Force
& $script
```

The collector performs:

- complete file inventory and SHA256 hashing;
- unlimited targeted text scanning;
- DLL/EXE version and managed-assembly identification;
- all printable DLL/EXE ASCII and UTF-16LE string extraction by default;
- .NET type/method/property/field inventory where reflection-only loading is
  available;
- firmware/update/programming candidate discovery;
- binary-string research for MDF/LDF/ECNDAT/SYS/LIB and firmware-like files;
- automatic execution of `extract-vitosoft-deep-metadata.py`.

The resulting `metadata/` directory contains the small Git-suitable,
device-centric corpus. The large raw-derived string bundle is primarily an
analysis input and does not need to be committed wholesale.

See `firmware-and-deep-research.md` for repository policy and the separate
controller-firmware research track.


## Private archival collector

For a deliberately comprehensive **private** capture of the Vitosoft Windows
installation, use:

`tools/collect-vitosoft-private-archive.ps1`

Typical direct invocation from an **elevated (Run as Administrator)**
Windows PowerShell session:

```powershell
$script = "$env:TEMP\collect-vitosoft-private-archive.ps1"

Invoke-WebRequest -Uri "https://raw.githubusercontent.com/SaulGoodman1337/optolink/main/tools/collect-vitosoft-private-archive.ps1" -OutFile $script

Set-ExecutionPolicy -Scope Process Bypass -Force

# Syntax check before execution (especially useful on Windows PowerShell 5.1)
$tokens = $null
$errors = $null
[System.Management.Automation.Language.Parser]::ParseFile(
  $script,
  [ref]$tokens,
  [ref]$errors
) | Out-Null

if ($errors.Count -gt 0) {
  $errors | Format-List *
  throw "Collector script has PowerShell parser errors."
}

& $script -CreateArchive
```

Parallel execution is enabled by default. The collector derives a conservative
worker count from the logical CPU count (roughly half the logical CPUs, capped
at 6) and uses multithreaded robocopy separately.

Override examples:

```powershell
# More aggressive on a fast SSD / many-core machine:
& $script -CreateArchive -Parallelism 8 -CopyThreads 16

# Deterministic/sequential fallback for HDDs or troubleshooting:
& $script -CreateArchive -Sequential
```

Parallelized/overlapped work includes:

- deep-derived collection and SQL read-only collection;
- ILDASM tasks;
- DUMPBIN tasks;
- CORFLAGS tasks;
- strong-name inspection;
- robocopy file transfer via `/MT`;
- 7-Zip multithreaded compression.

The collector records measured phase durations in
`system/phase-timings.csv` and records the chosen CPU/parallelism values in
`private-archive-summary.json`.

The collector now runs a prerequisite preflight before the Vitosoft scan. It
records the before/after tool state and, unless
`-SkipPrerequisiteInstall` is supplied, attempts to install missing research
tools needed for the complete private analysis:

- Visual Studio 2022 Build Tools minimal components for `ildasm.exe`,
  `dumpbin.exe`, MSBuild and related .NET Framework SDK tools;
- 7-Zip via winget when available, for reliable large archive creation.

PowerShell 5.1+, robocopy and reg.exe are treated as core Windows
prerequisites. Optional tools such as dotnet, sqlcmd, sqllocaldb, Git and Git
LFS are inventoried but are not installed merely for collection when the
collector has a native alternative.

The private collector includes the normal deep-derived collector and additionally
attempts to preserve:

- the complete Vitosoft installation parent tree;
- related Viessmann ProgramData/AppData/Documents trees;
- registry keys and Windows service/process/task metadata relevant to
  Viessmann/Vitosoft/SQL;
- Authenticode metadata plus full ILDASM and DUMPBIN output when the tools are
  available after preflight;
- managed assembly identity/MVID/reference/resource graphs even if ILDASM is
  unavailable;
- .NET/Visual-Studio/toolchain inventory, serial/USB inventory, loaded
  Vitosoft/SQL process modules, service executable paths, disk space, Windows
  hotfixes and relevant recent application-event-log entries;
- raw `ecnViessmann.mdf/.ldf` database files;
- SELECT-only SQL schema/table exports through
  `tools/export-vitosoft-sql-readonly.ps1` when an already reachable SQL
  instance can be discovered;
- priority copies of `ecnUpdateDefinition` and
  `ecnDeviceSoftwareUpdate` exports;
- a complete SHA256 manifest, archive statistics, prerequisite report and Git
  LFS template;
- an integrity-tested `.7z` when `-CreateArchive` is used and 7-Zip is
  available.

The collector intentionally does **not** auto-attach an MDF via
`AttachDbFilename`, because attaching a database changes SQL Server state.
If no existing SQL instance is reachable, the MDF/LDF bytes are still
preserved for later isolated analysis.

The resulting private bundle can contain proprietary files, database content,
machine-specific paths and credentials present in application configuration.
Do not upload it wholesale to the public repository. The normal
`collect-vitosoft-deep-research.ps1` remains the preferred public/derived
research collector.
