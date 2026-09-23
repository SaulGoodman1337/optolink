# Optolink project roadmap

Current working backlog for the Optolink / Home Assistant / WB2A project.

Last reviewed: 2026-09-22

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
5. determine which actual KM-BUS runtime exchange is required to avoid BC and
   populate software-index / room-sensor state, and whether any internal
   writable path can reproduce that state;
6. retain the global KBUS/KMBUS function family as a secondary reverse-
   engineering path rather than assuming it is the VDensHO1 Vitotrol API;
7. separately hardware-verify the Vitosoft `PrefixRead` mapping if a suitable
   source-defined KBus event/path becomes available.

The earlier prefix-less `0x43 / KMBUS_EEPROM_READ` experiments remain valid
wire-level evidence, but production Vitosoft data shows that 90 of 91 real
KMBUS_EEPROM_READ definitions use a six-byte `PrefixRead`, so those F8 tests
must not be interpreted as normal Vitosoft EEPROM reads.

Detailed evidence:
`config/optolink-splitter/research/kmbus-optolink-research.md` and
`config/optolink-splitter/research/vitosoft/full-extraction-2026-09-23.md`.

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

Next work:

- define the complete hardware chain around the M-Bus Slave Click;
- choose a practical host/interface board and power arrangement;
- verify electrical/M-Bus compatibility with the intended Vitotrol emulation;
- define the software protocol bridge to Home Assistant/Optolink;
- prefer a solution that can be assembled from finished modules without
  soldering where practical.

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

### Internal pump: automatic 100 % at burner start in heating mode

Status: **open / revisit with KMBUS/KBUS access**

Observed behavior to explain:

- during **domestic-hot-water preparation**, the internal boiler pump can
  automatically run at 100 % when the burner is active;
- during **space-heating operation**, the same automatic 100 % pump behavior
  has not been observed;
- local startup captures have shown pump states corresponding to roughly
  50 % and 100 %, and the higher-flow condition correlated with the burner
  surviving the high-start-power phase and reaching low modulation.

Research goal:

Determine whether VDensHO1/20C2 has an internal mode, request, limit, override
or state-machine parameter that can cause the internal pump to go to 100 %
automatically during a burner start in **heating mode**, analogous to the
behavior already observed in DHW mode.

Re-open this question using the newly verified generic VS2/P300 and KMBUS/KBUS
read capability.

Next work:

- capture identical startup windows in **heating** and **DHW** mode and compare
  all known pump, burner, RKR, GFA and mode-state datapoints;
- search the complete VDensHO1/Vitosoft event set for pump command, pump target,
  internal-pump override, boiler-pump demand, DHW pump logic and KBus/KM-BUS
  fields;
- specifically inspect special-access events whose FCRead uses KMBUS_ or KBUS_
  and which may previously have been unreachable through normal Virtual_READ;
- determine whether the observed 100 % value is a pump setpoint, a temporary
  override, a mode-specific minimum, or a downstream actuator state;
- identify the state transition that activates the 100 % command in DHW and
  check whether the same state/command exists but is disabled or parameterized
  differently in heating mode;
- remain read-only until the responsible field and write semantics are known.

Potential relevance:

If a safe controller-side heating-mode pump override exists, it could improve
heat removal during the 65-66 % flame-stabilization/startup plateau without
altering burner start-safety parameters.

Detailed evidence belongs in:
`config/optolink-splitter/research/device-vdensho1-20c2-wb2a.md`.

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
