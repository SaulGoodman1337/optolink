# Optolink project roadmap

Current working backlog for the Optolink / Home Assistant / WB2A project.

Last reviewed: 2026-09-23

The purpose of this file is to keep open work from the different project chats
in one place. Detailed experimental evidence remains in the device/coding-plug
research documents; this file contains tasks and next actions.

## Priority: next session

### 1. Restructure the Home Assistant diagnostics page

Status: **planned**

The diagnostics page has grown organically and should be reorganized for
day-to-day troubleshooting.

Goals:

- put operational burner/RKR state first;
- group restart inhibition, restart release, start phase, startup optimization
  and regulation state together;
- show normal RKR boiler target and internal startup-optimized target (OPT)
  next to each other;
- separate burner/flame/modulation from CFDM internals;
- separate coding-plug/reference values from live runtime diagnostics;
- move unresolved/raw research values into a lower-level section;
- remove obsolete or disproved interpretations;
- improve explanatory text and reduce visual clutter;
- review useful 24 h history charts.

Main file:
`config/optolink-splitter/homeassistant-dashboard.yaml`

### 2. Move time programs to a dedicated Home Assistant tab

Status: **planned**

The weekly time programs currently live at the bottom of the diagnostics page
and should be moved out of diagnostics into a dedicated, visually polished
Home Assistant tab.

Existing schedule groups already present in the dashboard:

- heating circuit M1: Monday through Sunday;
- domestic hot water: Monday through Sunday;
- DHW circulation: Monday through Sunday.

Current entities use the corresponding
`*_zeitprogramm_<weekday>_anzeige` sensors.

Design goals for the new tab:

- one clear tab/view dedicated to schedules rather than diagnostics;
- visually separate **Heating**, **Domestic hot water** and **Circulation**;
- make the complete week readable at a glance;
- avoid a long plain 21-row entity list if a clearer weekly layout is
  achievable with the installed Home Assistant cards;
- use consistent weekday ordering and compact labels;
- show multiple switching periods per day cleanly where the underlying entity
  provides them;
- preserve the existing entities first; improve presentation before changing
  data acquisition;
- investigate whether the schedules can later be made safely editable from
  Home Assistant, but keep display-only behavior unless write semantics have
  been verified on this controller.

Main file:
`config/optolink-splitter/homeassistant-dashboard.yaml`

The old schedule cards should be removed from the diagnostics page once the
dedicated tab is in place.

### 3. Find the real blower-speed datapoint

Status: **open / high interest**

The previous interpretation of `0x55D3[6:7]` as blower rpm was disproved by
live captures and has been removed from the production Home Assistant profile.

The actual blower speed is still wanted.

Next work:

- search VDensHO1 / GG1 / GFA datapoints for a plausible live speed value;
- compare candidates against the complete burner sequence:
  pre-purge -> ignition -> flame establishment -> modulation ramp -> steady
  firing -> shutdown;
- reject state/counter words that merely correlate with burner operation;
- when possible, compare the candidate with a second observable quantity
  (service display, acoustic/tach behavior, known fan command or another
  controller datapoint);
- expose a Home Assistant entity only after the scaling/unit is supported by
  measurements.

Do not restore the old `0x55D3[6:7] = rpm` interpretation.

### 4. Improve A5/A6 dashboard explanation

Status: **planned**

The "Heizkurve & Vorlauf" page needs a clearer explanation of the relationship
between:

- A5 Heizkreispumpenlogik;
- A6 Sommersparabschaltung.

The current explanation is not yet sufficiently clear about which condition
acts on the heating-circuit pump, which condition also suppresses burner heat
demand, and how the two functions interact.

Goal: rewrite the explanatory cards around actual controller behavior and
avoid historical/editorial comments that do not help operation.

### 5. Map KBus / KM-BUS access over Optolink

Status: **active / high interest**

The complete production Vitosoft metadata for the exact local
`VDensHO1 / 20C2 / developer 01.03` profile is now available.

Major correction to the earlier direction:

- the full profile contains **581 events**;
- none of those events use `KBUS_*` or `KMBUS_*` as FCRead/FCWrite;
- remote/Vitotrol identification is exposed as ordinary virtual controller
  state:
  - `0x27A0` A1/M1 remote identification, read/write;
  - `0x37A0` M2 remote identification, read/write;
- actual room-temperature state remains read-only:
  - `0x0896` A1/M1 room temperature;
  - `0x0898` M2 room temperature;
- remote software-index and room-sensor-status objects provide additional
  discovery/presence evidence.

The next local work is therefore **not** a blind KBUS function-code sweep.
First establish the complete read-only baseline for those ordinary virtual
objects and determine what controller state changes when a Vitotrol is
configured/present.

Current next steps:

1. read and record `0x27A0`, `0x37A0`, `0x0A5C`, `0x0A60`,
   `0x0896`, `0x0898`, `0x089C`, `0x089D`;
2. record related room-influence configuration `0x27B0/0x27B2/0x27E2`
   and M2 equivalents;
3. establish whether absent-remotes produce deterministic software-index and
   sensor-status signatures;
4. controlled `0x27A0: 0 -> 1 -> 0` experiment completed: the controller
   accepted the value, then raised `BC = Fehler Fernbedienung HK1`; A0 alone
   is therefore not sufficient for emulation;
5. **completed source reconstruction:** a working Vitotrol slave is class
   `0x11`, V200 ID `0x34`, slot `0x01`; it answers F8..FB discovery and
   PINGs, and sends HK1 room temperature as a `0xBF` record `0x20`;
6. **completed Vitosoft write-family analysis:** `KBUS_TRANSPARENT_WRITE`,
   `KBUS_DIRECT_WRITE`, `KBUS_GATEWAY_WRITE` and related operations are
   shaped as participant datapoint/gateway-channel operations, with no
   source-defined raw Vitotrol telegram injection path and no VDensHO1 links;
7. keep Optolink-only emulation as an undocumented/static-analysis question;
   do not issue blind live writes using 0x56/0x5B/0x5E/0x62/0x66;
8. separately hardware-verify the Vitosoft `PrefixRead` mapping if a suitable
   source-defined KBus event/path becomes available.

The earlier prefix-less `0x43 / KMBUS_EEPROM_READ` experiments remain valid
wire-level evidence, but production Vitosoft data shows that 90 of 91 real
KMBUS_EEPROM_READ definitions use a six-byte `PrefixRead`, so those F8 tests
must not be interpreted as normal Vitosoft EEPROM reads.

Detailed evidence:

- `config/optolink-splitter/research/kmbus-optolink-research.md`;
- `config/optolink-splitter/research/vitotrol-kmbus-wire-protocol.md`;
- `config/optolink-splitter/research/vitosoft/kbus-write-function-analysis.md`;
- `config/optolink-splitter/research/vitosoft/full-extraction-2026-09-23.md`.

### 6. Continue Vitotrol emulation hardware path

Status: **open / now source-supported reference path**

The controlled A0 experiment proved that controller-side configuration alone
is insufficient: `0x27A0=1` is accepted but quickly raises
`BC = Fehler Fernbedienung HK1` when no KM-BUS slave responds.

Source review of `dumpfheimer/WiFiVitotrol` now provides a concrete working
reference implementation:

- Vitotrol class `0x11`;
- default Vitotrol-200 ID `0x34`, slot `0x01`;
- identity registers `F8..FB`;
- master commands `0x00/0x31/0x33`;
- slave responses `0x80/0xB1/0xB3/0xBF`;
- room temperature sent as KM-BUS command `0x20` in a `0xBF` response,
  periodically every 30 s when valid data is available.

The separate Vitotrol-emulation work identified the
**MIKROE-4137 M-Bus Slave Click** as a promising no-solder hardware building
block.

Keep this as the fallback/parallel route while the Optolink KBus path is being
investigated.

The byte-level reference is now documented in
`research/vitotrol-kmbus-wire-protocol.md`. Known minimum behavior includes:

~~~text
1200 8E1
class 0x11
Vitotrol 200 ID 0x34
slot 0x01
F8..FB identity response
PING -> PONG/data response
HK1 room temperature -> 0xBF record 0x20
~~~

An offline helper is available as `tools/kmbus-frame.py`; it reproduces known
CRC vectors and builds discovery, identity, PONG and room-temperature frames
without accessing any hardware.

Next work:

- define the complete hardware chain around the M-Bus Slave Click or another
  proven TTL<->M-Bus slave interface;
- choose a practical host/interface board and power arrangement;
- first implement only discovery/identity + PONG and verify that `BC` no
  longer appears with `0x27A0=1`;
- then send a deliberately distinctive test room temperature and verify that
  `0x0896` follows it and `0x089C` becomes valid;
- capture the physical bus during the experiment and compare every frame with
  the reconstructed reference;
- only after the minimal link is stable, add setpoint/mode commands and the
  Home Assistant bridge;
- prefer a solution assembled from finished modules without soldering where
  practical.

Do not treat the M-Bus Slave Click choice as a completed implementation yet.

## WB2A reverse engineering: open items

### RKR / restart state

Status: **major behavior verified, bitfield details open**

Verified in two controlled cycles:

- `0x55E0 byte14 bit0 = 0` during the nominal ~240 s post-flame restart
  inhibition;
- strong thermal demand does not start the burner while bit0 remains 0;
- bit0 becomes 1 immediately before a new burner startup can begin;
- the first new 55DC startup activity was measured essentially at the 240 s
  boundary;
- `A395.b2` clears after roughly 60 s and is a different state.

Open:

- determine the meaning of byte14 bits represented by `0x02` and `0x40`;
- reproduce/characterize other byte14 values if they occur in DHW or other
  operating modes;
- verify Home Assistant derived-state transitions during ordinary operation.

### Startup optimization / OPT

Status: **strongly supported**

`0x55E0[10:12]` behaves as an internal startup-optimized boiler target:

- at restart release it drops exactly 20 K below the normal RKR target;
- it then ramps back toward the normal target;
- behavior is consistent with the coding-plug startup-optimization setting.

Open:

- measure the complete OPT ramp in a clean uninterrupted burner run;
- determine exact ramp start/end timing and whether the ramp is linear;
- compare the measured duration against the coding-plug 240 s parameter.

### ~12 s post-flame regulation transition

Status: **observed, exact internal cause still open**

Repeated observations show an approximately 12 s interval after flame
establishment before the established regulation state/down-ramp.

Relevant clues:

- `0x55E0 byte14` changes `0x01 -> 0x43` about 12 s after FLAME_START;
- `0x55D3` runtime byte7 bit `0x02` appears shortly before the sustained
  modulation ramp;
- direct LGM29-style flat-address candidates were rejected;
- `0x1030/16` is a structured coding/control block, not a directly addressable
  flat map at each byte.

Open: determine whether the ~12 s interval is a fixed GG1/GFA state-machine
phase, a coding-plug parameter, or another internal control condition.

### Flame stabilization / high startup modulation

Status: **open / high interest**

The WB2A starts combustion around 65-66 % modulation, holds that level for
about 12 s, and then ramps down at about 1 percentage point/s toward the
approximately 33 % modulation floor.

Comparable Vitodens documentation/community statements from Viessmann describe
the high startup level as a coding-plug-defined flame-stabilization/start-safety
behavior. The local exact parameter on VDensHO1/20C2 is still unknown.

Next work:

- search the full VDensHO1/Vitosoft event set for startup-power,
  regulator-delay, GFA timing and KBus/KM-BUS fields;
- use the newly verified KMBUS read capability only for read-only parameter
  correlation until semantics are known;
- separate three effects: startup power, about-12-s regulation hold and
  about-1-%/s down-ramp;
- correlate internal pump/flow state with successful vs prematurely aborted
  burner starts;
- prefer hydraulic/startup heat-removal mitigation over changes to burner
  start-safety behavior;
- do not experimentally disable or reduce flame-stabilization/start-safety
  parameters on the live gas burner.

Detailed evidence:
`config/optolink-splitter/research/device-vdensho1-20c2-wb2a.md`.

### Internal pump: automatic 100 % during burner operation in heating mode

Status: **active / read-only comparison logger added**

Observed behavior to explain:

- during **domestic-hot-water preparation**, the internal boiler pump can
  automatically run at 100 % when the burner is active;
- during **space-heating operation**, the same automatic 100 % pump behavior
  has not been observed;
- local startup captures have shown pump states corresponding to roughly
  50 % and 100 %, and the higher-flow condition correlated with the burner
  surviving the high-start-power phase and reaching low modulation.

Source-supported pump paths are now identified in the exact VDensHO1 family:

- `0x7660`: internal-pump output / pump-speed runtime object;
- `0x5731`: coding 31, internal-pump target;
- `0x676C`: coding 6C, **internal-pump speed during DHW preparation**;
- `0x27E6..0x27E9`: A1/M1 E6/E7/E8/E9 pump max/min/reduced-mode settings;
- coding-plug GWG75: minimum internal-pump speed, locally measured raw **50**;
- `0x650A`, `0x6513`, `0x0A10`: DHW preparation, storage charging pump
  and diverter-valve runtime states.

The complete 581-event production join for the exact local VDensHO1 profile
contains **no KBUS/KMBUS FCRead or FCWrite events**. The earlier plan to search
for special-access KBUS/KMBUS pump events is therefore obsolete for this
controller profile.

Next hardware task after returning to the appliance:

- validate the newly discovered read-only result objects `0x0A3A` and
  `0x0A3B` together with `0x0A3C`, `0x7660` and `0x7663`;
- first take a stable-state snapshot with:
  ```text
  0x0A3A / 1   HKP_A1_res
  0x0A3B / 1   HKP_M2_res
  0x0A3C / 1   InternePumpeDrehzahl_res
  0x7660 / 2   internal-pump runtime/output
  0x7663 / 2   A1 pump runtime/output
  ```
- compare at least pump-off, heating/pre-ignition, flame-on and flame-off
  takt-lock states;
- determine whether `0x0A3A` tracks the computed A1 pump setpoint while
  `0x0A3C` represents the later/final internal-pump selection;
- keep this experiment strictly read-only;
- the enhanced `wb2a-pump-divergence-watch.py` already includes
  `0x0A3A` and `0x0A3B`.

Next work:

- use `wb2a-pump-start-logger --mode heating` for a complete heating start;
- use `wb2a-pump-start-logger --mode dhw` for a complete DHW start;
- compare the local static values of 31, 6C, E6/E7/E8/E9 and GWG75;
- verify the exact `0x7660` byte layout against the known approximately
  50 % and 100 % pump states;
- identify whether the 100 % transition follows DHW mode / diverter-valve
  selection or a later GG1/GFA burner-start transition;
- only if `6C` does not explain the 100 % runtime value, search for a
  separate transient override/state-machine command;
- remain read-only until the responsible field and write semantics are known.

Potential relevance:

If a safe controller-side heating-mode pump request exists, it could improve
heat removal during the 65-66 % flame-stabilization/startup plateau without
altering burner start-safety parameters.

Detailed evidence:
`config/optolink-splitter/research/pump-start-heating-vs-dhw.md`.

### WB2A software version / firmware readout

Status: **open / high-value future research**

Determine whether the installed Vitodens 200-W WB2A can expose the actual
software/firmware revision running in the appliance and whether the executable
firmware image itself can be read non-destructively.

Keep two goals separate:

**Software/version identification**

- find read-only Optolink/Vitosoft diagnostics for controller application
  version, build/revision/date and hardware revision;
- identify software versions of main regulation, burner-control/GFA and
  subordinate KM-BUS participants separately;
- inspect hidden/global Vitosoft events, RPC/system-block functions and
  KM-BUS/KBUS participant information;
- do not confuse the Vitosoft profile/data-definition version with the
  firmware revision actually running in the boiler.

**Full firmware extraction**

Investigate in this order:

1. supported Vitosoft/Optolink readout;
2. documented/recovered P300, KBUS or KMBUS flash/ROM/system-block read
   functions;
3. service/programming/debug headers on the controller electronics;
4. external flash/EPROM/EEPROM devices;
5. MCU debug readout after exact MCU identification and protection analysis.

Any acquired raw firmware should be archived privately with hashes; commit
derived maps, disassembly/decompilation findings and reproducible procedures to
the repository, not proprietary firmware binaries.

Detailed plan:
`config/optolink-splitter/research/vitosoft/firmware-and-deep-research.md`.

### Vitosoft SQL: device software-update tables

Status: **open / high priority**

The deep Vitosoft collector exposed a separate device-software-update data
model in addition to Vitosoft's own PC application updater. Before any further
firmware-update conclusions are drawn, inspect the production Vitosoft SQL
database read-only and determine whether the local WB2A / VDensHO1 / 20C2
family is represented in that update infrastructure.

Primary database:

`C:\Program Files\Viessmann Vitosoft 300 SID1\ServiceTool\Database\ecnViessmann.mdf`

Primary tables/objects to inspect:

- `dbo.ecnUpdateDefinition`
- `dbo.ecnDeviceSoftwareUpdate`

Fields of particular interest from the recovered .NET data model:

- `DeviceTypeId`
- `UsingIdentification`
- `Name`
- `Description`
- `MajorSoftwareVersion`
- `MinorSoftwareVersion`
- `ConnectionString`
- `CreateTime`
- `ReleaseTime`
- `Released`
- `UpdateName`
- `UpdateStatus`
- `UpdateUsingIdentification`
- `UpdateTime`
- `UpdateReadTime`

Research goals:

1. enumerate both tables read-only and preserve schema plus row counts;
2. resolve `DeviceTypeId` against the Vitosoft device-type table and search
   explicitly for `VDensHO1`, identification `20C2`, and related WB2A
   device identifiers;
3. determine whether `UsingIdentification` / `UpdateUsingIdentification`
   contain or select a device-identification value relevant to `20C2`;
4. identify any update definition carrying controller software versions that
   could match the local regulation or GFA software;
5. inspect `ConnectionString` and related fields only as metadata first to
   determine whether the actual update payload is local, database-backed,
   network-fetched or generated by another Vitosoft component;
6. correlate any matching rows with the recovered
   `ecnMobileClient.vsmconnector.softwareupdate` workflow and its
   `ReadyForUpdate`, `BeginUpdate` and `EndUpdate` methods;
7. export only the relevant schema/rows and conclusions to Git; do not commit
   the proprietary MDF/LDF database itself to the public repository.

The first pass must be **strictly read-only SQL**. Do not trigger
`BeginUpdate`, alter database rows, or initiate a device programming session.

Collector support is now prepared:

- `tools/export-vitosoft-sql-readonly.ps1` preserves MDF/LDF files, discovers
  reachable existing SQL instances, exports schema plus all user tables using
  SELECT-only queries, and copies `ecnUpdateDefinition` /
  `ecnDeviceSoftwareUpdate` into a priority export;
- `tools/collect-vitosoft-private-archive.ps1` invokes that SQL stage as part
  of a much broader private Vitosoft archive;
- automatic `AttachDbFilename` / MDF attach is intentionally not performed,
  because attaching a database changes SQL Server state.

Next execution task: run the private collector on the Vitosoft Windows system,
store the resulting raw/private bundle outside the public repository, then
inspect the SQL priority exports for VDensHO1 / 20C2.

Desired outcome:

- clear answer whether the Vitosoft device-software-update subsystem contains
  an entry for `VDensHO1 / 20C2`;
- associated target/source software versions if present;
- evidence for where the actual update package comes from;
- a reproducible read-only SQL query/export procedure for future research.

Detailed firmware context:
`config/optolink-splitter/research/vitosoft/firmware-and-deep-research.md`.

### Private full Vitosoft archival collector

Status: **collector ready / execution pending**

A second, intentionally comprehensive collector now exists for material that
should later live in a **private** research repository:

`tools/collect-vitosoft-private-archive.ps1`

It is deliberately broader than the public/derived deep collector. By default
it collects:

- the complete Vitosoft installation parent tree;
- related Viessmann directories in ProgramData/AppData/Documents when present;
- the normal deep-derived metadata/string/member corpus;
- raw MDF/LDF plus SELECT-only SQL schema/table exports where an existing SQL
  instance is reachable;
- Viessmann/SQL-related registry keys;
- related Windows services/processes/scheduled tasks and installed-software
  inventory;
- Authenticode signature metadata;
- optional ILDASM and DUMPBIN output if those tools are installed;
- a complete SHA256 manifest;
- a Git LFS `.gitattributes` template for later private-repository import.

The generated bundle may contain proprietary binaries, database contents,
machine-specific paths and credentials stored in application configuration.
It must therefore remain private and must not be committed wholesale to this
public repository.

Execution task:

1. run the collector on the Vitosoft Windows installation;
2. retain the original output and SHA256 manifest unchanged;
3. create/use a private Git repository with Git LFS for raw binaries/databases;
4. import only derived conclusions/hashes/scripts back into the public repo.

### Coding-plug read/write and external dumping

Status: **open / research only**

Determine whether the Kesselcodierstecker can be read or modified beyond the
currently verified read-only structured Optolink objects.

Investigate two independent paths:

**A. Via Optolink / controller protocol**

- identify whether the structured `0x10x0` coding-plug objects have supported
  write operations, service commands, commit/apply commands or checksums;
- distinguish normal coding-address writes from actual coding-plug/GWG writes;
- determine whether values are stored in the controller, copied from the plug,
  or written back to the physical plug;
- inspect Vitosoft/service-protocol behavior for any coding-plug programming or
  replacement workflow;
- determine whether the hardware-verified `0x41 KMBUS_RAM_READ` and
  `0x43 KMBUS_EEPROM_READ` address spaces have any deterministic mapping to
  known coding-plug/GWG fields; do not assume `0x43` is the coding plug merely
  because it contains "EEPROM" in its function name;
- do not issue experimental writes to burner-safety/limit fields until the
  write semantics, validation and recovery path are understood.

**B. Directly from the physical coding plug**

Available hardware for the next session:

- two additional/spare coding plugs are available for non-destructive bench
  investigation;
- an EPROM/EEPROM reader/programmer is probably also available and should be
  identified before use.

Next task:

- photograph/document both spare coding plugs, including labels, PCB and all
  semiconductor markings;
- record part numbers/revisions and determine whether either spare matches
  **7833971 / revision 2015:0201** exactly;
- identify the available EPROM/EEPROM reader/programmer model and supported
  devices/voltages;
- identify the memory/device technology and pinout used by coding plug
  **7833971 / revision 2015:0201**;
- determine whether it contains a standard EEPROM/EPROM/serial memory device
  that can be read with a common programmer;
- document voltage levels, package, bus/protocol and any in-circuit loading
  considerations before attaching a programmer;
- make at least two independent read-only dumps first and compare hashes;
- perform the first bench work strictly **read-only**; do not erase, program,
  modify protection bits or write configuration/fuse data until the memory
  technology, voltage, pinout and recovery path are known;
- store the resulting raw dumps, hashes, programmer settings and photos in the
  repository so they can be compared with Optolink data later;
- decode whether the observed `0x10x0` Optolink objects can be mapped to
  offsets in the physical dump;
- identify checksums, duplicated blocks, version fields and plausibility data;
- only after a verified backup/recovery procedure exists, investigate whether a
  modified image can be written and accepted by the controller.

Desired outcome:

- a reproducible **read-only dump procedure**;
- a map from physical coding-plug bytes to known GWG fields where possible;
- a clear answer whether modifications are possible by Optolink, external
  programmer, both, or neither;
- a rollback/recovery procedure before any write experiment.

Detailed coding-plug evidence remains in
`config/optolink-splitter/research/coding-plug-7833971-2015-0201.md`.

## Home Assistant follow-up

Status: **implementation added; live validation pending**

New RKR entities have been added for:

- restart inhibition;
- restart release;
- burner start phase;
- startup optimization;
- regulation state;
- normal RKR target;
- internal optimized RKR target;
- raw byte14 diagnostic.

Next work:

- verify entity creation after `update`;
- verify transitions over a natural burner cycle;
- check retained discovery cleanup for the removed false blower-rpm entity;
- revise naming/text during the diagnostics-page redesign if necessary.

## Repository maintenance

A separate cleanup plan is maintained in
[`repository-cleanup-plan.md`](repository-cleanup-plan.md).

The cleanup should be performed as a controlled refactor. Installer/updater
paths are currently coupled to the existing layout, so files must not simply be
moved without updating and testing all references.