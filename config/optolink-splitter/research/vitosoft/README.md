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

### Private extractor: `extract-vitosoft-project-data.py`

The extractor source has moved to the private Vitosoft source repository:

`SaulGoodman1337/Viessmann-Vitosoft-300-SID1/collector/tools/extract-vitosoft-project-data.py`

It joins device membership from `DPDefinitions.xml` against
`ecnEventType.xml` and emits the complete low-level device-event CSV,
the KBUS/KMBUS-only CSV, and an extraction summary. The
`--include-global-wilo` mode remains a metadata-only global pass and sends no
hardware command. Collector/extractor implementation is intentionally no longer
stored in this operational Optolink repository.

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

The validated extractor is maintained privately at `collector/tools/extract-vitosoft-project-data.py` in `SaulGoodman1337/Viessmann-Vitosoft-300-SID1`.

The most important protocol result is that the exact VDensHO1 profile uses
ordinary `Virtual_READ/Virtual_WRITE`, `GFA_READ` and RPC accesses, but no
`KBUS_*` or `KMBUS_*` FCRead/FCWrite entries. Global KBus definitions still
exist in Vitosoft and are documented separately.

See [full-extraction-2026-09-23.md](full-extraction-2026-09-23.md).

## Private-archive static-analysis checkpoint — 2026-09-23

The first private archival capture was incomplete in some tooling stages, but
it already produced one major protocol result that is now considered the
current working implementation model for GFA access.

### VSKO / GFA access mechanism

Static analysis of the installed Vitosoft assemblies shows:

- Vitosoft has an explicit `SDKCommandState.VSKO`;
- normal command state does not expose `GFA_READ/GFA_WRITE`;
- VSKO state allows `GFA_READ`, `GFA_WRITE`,
  `PROZESS_READ` and `PROZESS_WRITE`;
- entering VSKO calls `VSManager.ChangeInterface(VS1)`;
- Vitosoft's VS2-side GFA abstraction `GFA_READ = 0xC9` is translated to
  VS1 `GFA_Read = 0x6B`.

The reconstructed protocol transition is therefore:

~~~text
normal VS2 / P300
  -> send 0x04 (EOT)
  -> controller 0x05 (ENQ)
  -> VS1 synchronization / next 0x05
  -> PC sends 0x01 (STX)
  -> VS1 active
  -> GFA_READ: 0x6B <addr_hi> <addr_lo> <len>
  -> raw response bytes
~~~

Example target:

~~~text
GFA_READ 0x4054 length 1
wire request in VS1:
6B 40 54 01
~~~

Vitosoft returns to VS2/P300 with:

~~~text
16 00 00
~~~

This explains the earlier failures when `0xC9` or `0x6B` was sent while
the normal P300/VS2 session was still active. The function code was not the
only missing piece; the protocol interface had to be changed first.

Read-only GFA targets already supported by exact VDensHO1 metadata include:

| Address | Meaning | Scaling |
| --- | --- | --- |
| `0x4006` | P06 actual blower speed | raw × 30 rpm |
| `0x4009` | P09 blower speed setpoint | raw × 30 rpm |
| `0x400A` | P10 blower PWM setpoint | raw × 0.4 % |
| `0x4011` | P17 flame formation time | raw / 10 s |
| `0x4050..0x4053` | GFA identity/version/configuration | raw/metadata-specific |
| `0x4054` | P84 GFA phase | raw enum/state |
| `0x4055..0x4058` | GFA status objects | raw state |

A future live prober must remain read-only, take exclusive ownership of the
serial port, stop the normal splitter service before switching to VS1, restore
VS2/P300 in a `finally` path, then restart the service. Do not issue
`GFA_WRITE` while investigating blower speed or burner state.

### Collector toolchain location

The Collector implementation and its historical generations were moved on
2026-09-24 to the private source repository
`SaulGoodman1337/Viessmann-Vitosoft-300-SID1`, under `collector/tools/`.

The current hardened archival generation is
`collector/tools/collect-vitosoft-private-archive-v4.ps1`. SQL export,
deep-metadata extraction, KM-BUS/pump collection and the older collector
generations are preserved there as well. The verified
`collector-20260923-205048` Release in that repository is the canonical raw
snapshot for the analysis documented here.

This repository keeps the derived protocol findings and hardware-facing work,
not the Windows collection implementation.

### Firmware/update interpretation boundary

The first raw MDF scan confirmed the presence of the strings:

~~~text
VDensHO1
20C2
ecnUpdateDefinition
ecnDeviceSoftwareUpdate
~~~

Binary adjacency also exposed apparent version-like pairs such as
`0100 / 0103` and `0104 / 019F`. These values are **not yet interpreted as
firmware ranges** because their SQL table/row context has not been proven.
The next successful SQL export/decompilation pass must establish that context
before any firmware-update conclusion is made.

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


## KM-BUS / internal-pump collector source

The source of the read-only KM-BUS/internal-pump collector moved to the private
Vitosoft repository:

`collector/tools/collect-vitosoft-kmbus-pump.ps1`

The production result below remains in Optolink because it is a project finding
used by the WB2A pump investigation.

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

The reusable deep-research collector and its metadata extractor are maintained
in the private Vitosoft source repository:

- `collector/tools/collect-vitosoft-deep-research.ps1`
- `collector/tools/extract-vitosoft-deep-metadata.py`

See that repository's `collector/README.md` for invocation and provenance.

## Private archival collector

The complete private archival Collector toolchain now lives in
`SaulGoodman1337/Viessmann-Vitosoft-300-SID1`.

Current hardened entry point:

`collector/tools/collect-vitosoft-private-archive-v4.ps1`

The supporting read-only SQL exporter, historical Collector generations and
offline extractors are preserved beside it. The full verified archive is stored
as private Release asset `collector-20260923-205048`; this public Optolink
repository intentionally retains only small derived research artifacts and
device-facing tooling.
