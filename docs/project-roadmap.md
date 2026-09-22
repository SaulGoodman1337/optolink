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

### 2. Find the real blower-speed datapoint

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

### 3. Improve A5/A6 dashboard explanation

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

### 4. Continue Vitotrol emulation hardware path

Status: **open**

The separate Vitotrol-emulation work identified the
**MIKROE-4137 M-Bus Slave Click** as a promising no-solder hardware building
block.

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
