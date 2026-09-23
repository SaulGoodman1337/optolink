# Vitosoft-derived research data

This directory contains **project-specific derived data**, not a blind mirror of
the complete Vitosoft data set.

The source material currently known to this project comes from the public
`MorrisonHB/Optolink_02` repository at commit
`ec77c6917909ae229b17a6104db4f81f9a31e263`.

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

The same Config directory is also the expected data directory for the Vitosoft
parsers used by this project and is the first place to look for:

~~~text
DPDefinitions.xml
ecnEventTypeGroup.xml
Textresource_de.xml
Textresource_en.xml
sysDeviceIdent.xml
sysDeviceIdentExt.xml
~~~

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

This file is useful as a device-specific inventory, but it does **not** contain
all low-level access metadata from `ecnEventType.xml`.

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

## Missing low-level fields

For KBus/KM-BUS research the next extraction must join the device event list to
`ecnEventType.xml` and retain at least:

- `FCRead`;
- `FCWrite`;
- `Address`;
- `BlockLength`;
- `ByteLength`;
- `BytePosition`;
- `BitLength`;
- `BitPosition`;
- `Parameter`;
- `PrefixRead`;
- `PrefixWrite`;
- conversion/unit metadata.

The original XML files are currently visible through the upstream repository as
Git-LFS pointers, but their full bytes are not materialized by the GitHub tool
available in this environment. Once the LFS objects are available locally, the
project extractor should generate the low-level CSV directly.

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
