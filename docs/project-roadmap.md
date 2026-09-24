# Optolink project roadmap

Current working backlog for the Optolink / Home Assistant / WB2A project.

Last reviewed: 2026-09-24

The purpose of this file is to keep cross-project work in one place. For WB2A reverse-engineering execution order, completion criteria and research TODOs, use [research-plan-2026-09-24.md](research-plan-2026-09-24.md). Historical roadmap sections below are retained for context and may contain superseded next-step text.

## Home Assistant dashboard checkpoint - 2026-09-24

A detailed implementation checkpoint is available at
[`docs/homeassistant-dashboard-checkpoint-2026-09-24.md`](homeassistant-dashboard-checkpoint-2026-09-24.md).

It records the intermittent Diagnose color/background-rendering issue, the
verified fault-history alias decoding problem, currently unused but already
polled HA values, source-backed maintenance candidates, and the agreed order
for redesigning the remaining dashboard views.

## Priority: next session

### Handoff for the next chat — Home Assistant dashboard

The next chat should return to the Home Assistant dashboard first. The private
Vitosoft collector can continue independently and may later contribute new
diagnostic metadata, but the dashboard work does **not** need to wait for it.

Current dashboard checkpoint:

- the compact popup-driven diagnostics redesign is already present in
  `config/optolink-splitter/homeassistant-dashboard.yaml`;
- Mushroom chips currently summarize flame, modulation, RKR, takt lock,
  restart release, start phase, regulation, OPT and GFA-lock state;
- detailed sensor, RKR/CFDM/GFA, fault-history, device/software and coding-plug
  information is moved into browser_mod popups;
- a dedicated weekly time-program view for heating, DHW and circulation has
  been added;
- the A5/A6 explanation has been revised, but wording and visual clarity still
  need live verification;
- fault-history decoding currently includes the hardware/source-supported
  mappings B7, F9, BC and BD;
- the previous false blower-rpm interpretation from `0x55D3[6:7]` must not
  reappear.

First dashboard actions in the new chat:

1. inspect the current YAML rather than reconstructing the dashboard from
   memory;
2. visually verify the compact diagnostics view and browser_mod popup syntax in
   Home Assistant;
3. verify the dedicated time-program tab and remove any remaining duplicate
   schedule presentation from diagnostics;
4. review labels, explanatory text and grouping for RKR/OPT/restart inhibition,
   burner/GFA state, pumps, faults, software identity and coding plug;
5. verify all entity IDs used by the redesigned cards against the production
   Home Assistant profile before treating them as working;
6. improve the A5/A6 explanation around the actual distinction:
   A5 is the heating-circuit-pump switching boundary, while A6 is the fixed
   summer/winter heating shutdown threshold affecting the whole heating mode;
7. keep unresolved/raw research values visually separated from verified
   operator-facing values.

Collector interaction with the dashboard:

- collector results may later expose exact GFA phase/fan values, firmware
  identity or additional software/update metadata;
- do not add those values to the normal dashboard merely because a string or
  address exists in Vitosoft;
- promote them only after access method, scaling and semantics are supported;
- the already recovered VSKO/GFA access mechanism is a separate read-only
  research path and is not required for the dashboard redesign itself.

### 1. Restructure the Home Assistant diagnostics page

Status: **compact popup-driven redesign implemented / Home Assistant visual verification pending**

The diagnostics page has grown organically and should be reorganized for
day-to-day troubleshooting.

Implementation update (2026-09-23):

- replaced the long always-visible diagnostic lists with a compact live overview;
- added Mushroom status chips for flame, modulation, RKR, takt lock,
  restart release, start phase, regulation, OPT and GFA lock state;
- condensed boiler targets, pump state and current fault state into four
  one-row Mushroom cards;
- moved sensor status, RKR/CFDM/GFA internals, complete fault histories,
  device/software identity and coding-plug details into browser_mod popups;
- uses already-present Mushroom + browser_mod functionality; no new HACS card
  is required for the first compact version.

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

#### Deferred TODO: fault-history presentation

Status: **functional baseline implemented / further visual refinement deferred**

The Diagnose page currently uses a compact chronology for the ten system-fault
history entries and a separate compact two-column GFA archive. Fault-code
decoding for the system-history display aliases is implemented for the
source-backed mappings currently known for this controller.

Keep the current layout for now. Revisit it later with these constraints:

- improve readability/visual hierarchy without returning to 30 separate cards;
- keep historical faults visually different from an active alarm state;
- preserve system-fault and GFA code spaces as separate concepts;
- retain code, known text and timestamp for system history;
- retain raw code and timestamp for GFA history until an exact supported map is
  recovered;
- no frequency/count summary of repeated codes is desired at this time.


### 2. Move time programs to a dedicated Home Assistant tab

Status: **hardware write contract verified / guarded HA editor implemented / live HA-path verification pending**

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


Current schedule reverse-engineering update (2026-09-24):

- one weekday is one complete eight-byte block containing up to four start/end
  pairs;
- time bytes use `(hour << 3) + minute/10`; unused entries are `FF FF`;
- `24:00` is representable as `C0` and should be accepted only as an end
  boundary;
- local readback already confirms `28 A0 FF...` = 05:00-20:00 and
  `2B A8 FF...` = 05:30-21:00;
- upstream Optolink-Splitter supports complete-block `writeraw` and
  `schedvdens` MQTT `/set` conversion;
- the upstream converter is permissive, so production UI writes must use
  project-side strict validation rather than accepting arbitrary strings;
- guarded helper `wb2a-schedule-probe` now provides map/snapshot/decode/
  encode and an explicit write-readback-restore probe;
- exact contract and test procedure:
  `docs/wb2a-schedule-blocks.md`.

Hardware gate completed on 2026-09-24:

- full 21-block read baseline captured;
- 1-, 2- and 4-interval complete-block writes passed;
- populated slots were cleared back to `FF FF` successfully;
- `24:00` end boundary passed;
- fully empty `FFFFFFFFFFFFFFFF` day passed;
- every probe restored the original block byte-for-byte.

Implementation now present:

- guarded `optolink-schedule-manager` service;
- strict validation before every schedule write;
- complete 8-byte writes with byte-exact readback and automatic restore on a
  mismatch;
- 21 non-optimistic MQTT text editor entities;
- schedule reads moved from `ONCE` to `SLOW` for physical-panel resync;
- full weekly dashboard with 24-hour bars, current-day/active indication and
  tap-to-edit rows.

Next gate: deploy with `update`, verify the manager service/discovery, then
perform one live edit through a Home Assistant text entity and confirm the
dashboard write-status/readback behavior.

The old schedule cards should be removed from the diagnostics page once the
dedicated tab is in place.

### 2a. Pumpen dashboard refinement

Status: **current redesign accepted provisionally / revisit later**

The Pumpen page has been converted to the Diagnose-inspired cockpit style and
is usable in live Home Assistant. Keep the current implementation for now.

Deferred redesign TODO:

- revisit the overall visual concept later;
- improve hierarchy, spacing, density and color balance;
- simplify the presentation where possible without losing direct controls;
- keep logical M1 request, A1 output and internal boiler-pump runtime
  semantically separate unless further controller evidence supports a stronger
  relationship;
- use the current page as a baseline, not as the final design reference.

### 2b. Apply the new diagnostic cockpit style to the other Home Assistant dashboards

Status: **TODO / visual direction approved in live dashboard**

The redesigned **Diagnose** tab is now the visual reference for further
Home Assistant work. The current direction was positively evaluated in live
use and should be carried over selectively to the other dashboard views rather
than rebuilding them as plain entity lists.

Reference patterns from the Diagnose tab:

- use `background-graph-entities` where a current value benefits from a short
  history directly behind it;
- use compact `button-card` status tiles for discrete states, faults, modes and
  internal controller values;
- keep every useful entity individually clickable so normal Home Assistant
  `more-info` remains available;
- use semantic state colors for real status/fault meaning, but use restrained
  section accent colors for static/reference data;
- group related technical values into compact multi-value cards instead of
  long `entities` / `multiple-entity-row` lists;
- use process/timeline chains where the controller behavior has a meaningful
  sequence, following the new combustion-sequence presentation;
- preserve responsive behavior: dense desktop cockpit, readable mobile layout,
  no fixed multi-column layout that becomes illegible on phones;
- avoid popup-only navigation for information that is useful during live
  troubleshooting;
- keep raw/research-only values visually distinguishable from confirmed
  operator-facing values.

Candidate views to rework with the same design language:

- **Heizung**: turn the current status/temperature/pump overview into a more
  coherent operating cockpit while keeping controls obvious;
- **Heizkurve**: keep the strong graph-based presentation, but modernize the
  parameter/status sections and consider a compact logic/process presentation
  for A3/A5/A6;
- **Pumpen**: highest-priority follow-up candidate; combine status, commanded
  speed, actual speed and hydraulic result in compact graph/status cards and
  consider a pump-control/process chain similar to the combustion timeline;
- **Nachtabsenkung**: visually separate automation state, active setpoints,
  timing and demand logic while retaining direct controls;
- **Zeitprogramme**: replace the plain weekday entity lists with a compact,
  visually structured weekly overview once the display-only baseline is
  preserved;
- **Graphen**: review whether the existing ApexCharts page can be made more
  consistent with the cockpit styling without duplicating graphs already shown
  contextually elsewhere.

Implementation rule: redesign one view at a time and verify it on both desktop
and mobile before propagating the pattern further. Preserve the working
Diagnose tab as the reference implementation rather than changing all views in
one large pass.

Main reference file:
`config/optolink-splitter/homeassistant-dashboard.yaml`

### 3. Find the real blower-speed datapoint

Status: **open / high interest**

The previous interpretation of `0x55D3[6:7]` as blower rpm was disproved by
live captures and has been removed from the production Home Assistant profile.

The actual blower speed is still wanted.

Current blocker/update (2026-09-23):

- exact VDensHO1 metadata identifies the desired GFA objects
  (`0x4006` actual fan speed, `0x4009` set speed, etc.);
- direct local `GFA_READ` through the normal active P300 request path is
  reproducibly rejected with a VS2 Error Message;
- do not continue guessing wire variants;
- next step is to recover Vitosoft's actual GFA access implementation from the
  private collector's raw assemblies/IL/SQL output.

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

Status: **updated in YAML / wording verification pending**

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

### Maintenance configuration / reset via Home Assistant

Status: **maintenance backend + HA staging + MQTT Discovery live-verified / Wartung view frontend verification pending**

A future Home Assistant dashboard session should add a compact **Service /
Wartung** area that not only displays the verified maintenance diagnostics but,
once the underlying controller operations are proven safe and reversible, can
also configure the maintenance thresholds from Home Assistant.

Desired future controls:

- configure the burner-runtime maintenance threshold at `0x5721`
  (source conversion: raw x 100 h);
- configure the maintenance time interval at `0x5723` in months;
- display the current maintenance state from `0x5724`;
- display elapsed months since the last maintenance by decoding the read-only
  `0x756C` LastCheckInterval reference;
- display burner runtime since the current maintenance reference as
  `(0x08A7 - 0x7570) / 3600`;
- provide a protected maintenance-reset action using the locally verified
  `0x5724: 1 -> 0` sequence.

Splitter verification is now complete for the maintenance control path:

- `0x5721`: local R/W verified, raw x 100 h; a later live CLI test proved
  that changing 0 -> nonzero re-baselines `0x7570`;
- `0x5723`: local R/W verified, 0..24 months, tested at 0 and 24 months;
- `0x5724`: local state transition and maintenance-reset sequence
  `1 -> 0` verified end-to-end through the guarded CLI;
- `0x756C`: read-only LastCheckInterval 32-bit reference; `0x5723` writes
  and the maintenance reset re-baseline it, but the exact Vitosoft wall-clock
  conversion remains unresolved;
- `0x7570`: read-only LastBurnerCheck baseline, verified against the
  current total burner-runtime counter `0x08A7`; changing `0x5721` can
  re-baseline it, while the `0x5724` reset effect is conditional rather than
  guaranteed;
- `0x08A7` and `0x088A` remain unchanged by the maintenance reset.

The Home Assistant implementation remains deliberately deferred to the
dashboard/HA workstream. It should build only on these verified semantics and
keep the maintenance reset separate from burner-fault unlock/reset logic.

Guarded splitter backend now available:

- `optolink-maintenance status`;
- `optolink-maintenance set-hours <0..10000> --confirm-reference-reset RESET-BRENNERREFERENZ`;
- `optolink-maintenance set-months <0..24> --confirm-reference-reset RESET-ZEITREFERENZ`;
- `optolink-maintenance reset --confirm RESET-WARTUNG`;
- `--json` output for a future wrapper/service.

The CLI performs range checks, independent readback, rollback attempts for
ambiguous writes, no-op suppression, a process lock and a safety restore to
`0x5724=0` during reset.

The maintenance backend is now split into one shared
`optolink_maintenance_core.py` plus two frontends:

- root CLI: `optolink-maintenance`;
- unprivileged MQTT service: `optolink-maintenance-api.service`.

The API uses `<mqtt_topic>/maintenance/cmnd`, `result`, retained `state`
and `availability` topics, serializes actions through the same maintenance
lock, deduplicates recent request IDs and ignores retained command messages.
The read-only MQTT API path has now been live-verified on the controller:
the service is active as `optolink`, the shared lock permissions are correct,
`status` traversed the full API/core/splitter path successfully, and the
refactored CLI returned the same controller state.

The non-write API safety suite is now live-verified:

- duplicate request IDs replay cached results with `deduplicated=true`;
- `set_hours 0` and `set_months 0` are no-ops with `changed=false`;
- unconfirmed `set_hours 100`, `set_months 1` and `reset` are rejected;
- baseline and final values for `0x5721`, `0x5723`, `0x5724`,
  `0x756C`, `0x7570`, `0x08A7` and `0x088A` matched.

The shared CLI/API lock is now live-verified. While the common
`/opt/optolink/.maintenance.lock` was held externally, both the root CLI and
the unprivileged MQTT API failed closed with a `busy` result. Normal CLI
access resumed after release.

The final bounded MQTT API write is now live-verified. A guarded
`set_months 0 -> 1 -> 0` sequence completed through the API, both writes were
read back successfully, and only `0x756C` was re-baselined as expected.
`0x7570`, `0x5721`, `0x5724`, `0x08A7` and `0x088A` remained
unchanged.

The maintenance backend is therefore complete for the currently verified
scope. No further raw/backend write experiments are required before Home
Assistant integration.

Home Assistant integration is now implemented in the repository:

- staged burner-hours and month Number entities write only API stage topics;
- changing a staged value cannot write the controller;
- explicit button-card Apply actions send unique JSON requests to the guarded
  `maintenance/cmnd` endpoint;
- a separately confirmed reset action uses the same guarded API;
- the new `Wartung` dashboard page separates current values, staged values,
  API status and destructive/reference-changing actions.

HA staging isolation is now also live-verified: temporary staged values of
`100 h` and `1 month` left the controller at `0 h / 0 months`, after
which the stage values were restored to `0 / 0`.

MQTT Discovery is now live-verified as well: all five new maintenance entities
are published, the two Number entities use only guarded staging topics, stage
state is `0 / 0`, and API availability is `online`.

The first live Wartung render confirmed entity availability but exposed a
presentation issue: the default button-card layout rendered oversized action
icons/cards. A compact maintenance action template and compact safety card are
now committed and YAML-validated.

The remaining task is frontend verification of the corrected Wartung view,
including confirmation dialogs and displayed post-action readbacks.

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

Completed result-object correlation:

- `0x0A3A` and `0x0A3B` are locally readable but remained zero through the tested heating start;
- this rejects the earlier hypothesis that `0x0A3A` is the computed A1 request feeding `0x7663`;
- `0x0A3C` follows the final internal-pump command and matches `0x7660[1]` in a discriminating state where `0x7663[1]` differs;
- therefore the remaining problem is the hidden controller selection **upstream of `0x0A3C`**, not another A3A/A3B validation pass.

Current next work:

- do not repeat the already completed generic heating/DHW startup comparisons;
- search protected FlowCalibration/embedded resources and any remaining host implementation for the selector feeding `0x0A3C`;
- use passive natural runs only for specific formula questions, such as an A1 request above the GWG75 floor;
- keep K34/external-demand semantics separate from a 100% speed claim;
- if host-side analysis yields no selector, continue this question in the controller-firmware/MCU workstream rather than blind address probing.

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

Status: **completed negative result / do not repeat without a new source**

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

Completion update: the private collector has been run through v6. Both priority update tables were exported successfully and contain zero rows. There is no local WB2A update entry to inspect further in these same tables.

Desired outcome:

- clear answer whether the Vitosoft device-software-update subsystem contains
  an entry for `VDensHO1 / 20C2`;
- associated target/source software versions if present;
- evidence for where the actual update package comes from;
- a reproducible read-only SQL query/export procedure for future research.

Detailed firmware context:
`config/optolink-splitter/research/vitosoft/firmware-and-deep-research.md`.

### Private full Vitosoft archival collector

Status: **v6 full run successful, verified and privately archived**

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

Current collector checkpoint (2026-09-23):

- the first private archive was already useful enough to recover the VSKO/GFA
  protocol-switch mechanism and preserve the SQL MDF/LDF files;
- Windows PowerShell 5.1 parser incompatibilities in inline hashtable
  expressions were corrected;
- the SQL connection builder was corrected for Windows PowerShell 5.1;
- missing Build Tools / ILDASM / DUMPBIN prerequisites are now detected and
  can be installed before collection;
- manual validation on the Vitosoft host proved that `dumpbin`, `corflags`,
  `sn.exe` and `ildasm` all work correctly on
  `MobileClient\vsmInterfaceCommon.dll` with exit code 0;
- `MobileClient\FlowCalibration.dll` is explicitly protected from ILDASM and
  returns `Protected module -- cannot disassemble`; this is an assembly-level
  condition, not a broken tool installation;
- early attempts to parallelize the external PE/.NET tools through nested
  `Start-Process` wrappers were unreliable on Windows PowerShell 5.1 and have
  been abandoned;
- current v4 design keeps raw-tree robocopy and independent Deep/SQL stages
  parallel, but executes ILDASM/DUMPBIN/CORFLAGS/SN directly and sequentially
  through the same invocation path that was manually verified;
- every tool group now has a one-file self-test before processing the complete
  file set, preventing another 89/106-task failure cascade;
- ILSpyCmd has been added as a decompiler fallback for managed assemblies that
  ILDASM intentionally refuses;
- interrupted/partial archive directories were deleted by the user, so the
  next execution is a completely fresh full collector run rather than a
  resume.

Current result: Collector v6 `20260924-143439` completed Deep, SQL, All-Devices and Tool-Dumps successfully; 15,249/15,249 manifest files were hash-verified and the private release asset was fresh-download verified. No generic full rerun is planned. Future collection should be targeted only at a newly identified gap.

### Coding-plug read/write and external dumping

Status: **active / read-only physical dump campaign started**

Physical bench update (2026-09-24):

- hardware identified and working: CH341A + SOIC8 clip, CH341PAR, AsProgrammer,
  24C04 selection;
- the photographed coding-plug PCB carries two 24C04 EEPROM packages;
- first sample is **spare-1**, explicitly not the coding plug currently
  installed in the boiler;
- spare-1/chip1 was read three times at 512 bytes; all three captures are
  byte-for-byte identical with SHA256
  `3dd583723661ea765f4e57405628def121bf78f1bc7d09dc1dfb51fec362f386`;
- initial analysis finds a 71-byte exact duplicated region
  `0x014..0x05A -> 0x066..0x0AC`, but no current installed-plug
  `7833971 / 2015:0201` identity pattern and no exact copy of the known
  `0x1030..0x1090` objects;
- spare-1 identity/revision is not yet confirmed, so no cross-plug conclusion
  may be drawn from those absent patterns;
- raw files and the analyzer JSON are now versioned under
  `config/optolink-splitter/research/coding-plug-dumps/spare-1/`;
- second spare/chip1 capture completed: three 512-byte reads are identical,
  SHA256 `554d890e5c5158893ca44b10e0503f38f8c6de4f01de0fb2b9e55211a3e48946`;
- spare-1 and spare-2 chip1 images match at 492/512 bytes (96.0938 %); the
  complete main-looking region through `0x0E1` is identical and differences
  are concentrated near the tail / `0x100` 24C04 block boundary;
- next comparison set: capture chip2 where possible, then the **currently
  active** coding plug last, keeping the whole campaign read-only.
- repository correlation now shows three distinct software views of the coding
  plug: normal GWG `0x10x0` objects, coding-card summary `0x7656`, and
  GFA P90/P100..P108 diagnostics; the two physical EEPROMs may map to separate
  domains, but this is not yet proven;
- both spare chip1 images contain an exact 82-byte logical mirror record and
  share an identical 226-byte prefix, substantially strengthening confidence
  in the saved reads;
- future active-plug correlation should snapshot `0x1010`, `0x1020`,
  `0x1030..0x10C0`, `0x7656`, plus GFA P90/P100..P108 read-only, then
  compare semantic field vectors rather than only literal 16-byte blocks.


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

## Possible upstream contribution: conditional/adaptive polling

Status: **possible TODO / not started**

Investigate moving conditional/adaptive polling out of the local runtime patch
model and into an upstream-capable implementation for
`philippoo66/optolink-splitter`.

Proposed workflow:

- create a fork such as `SaulGoodman1337/optolink-splitter`;
- implement the feature on a dedicated branch as a generic,
  backwards-compatible scheduler capability rather than a WB2A/GFA-specific
  special case;
- allow poll items to switch between an active cadence and a slower idle cadence
  depending on the cached state of another datapoint;
- support an optional hold/debounce period after the dependency becomes
  inactive so short state transitions do not cause poll-mode flapping;
- retain an occasional idle/control poll instead of disabling dependent values
  permanently;
- keep existing poll profiles fully unchanged when no dependency configuration
  is present;
- add tests for dependency lookup, active/idle switching, hold behavior,
  unknown source state and interaction with the existing phased scheduler;
- use the fork in production while the upstream pull request is open, pinned to
  an exact tested commit;
- submit a focused pull request to the original repository containing only the
  generic conditional/adaptive polling capability, not the local WB2A/GFA
  patches;
- if merged upstream, move production back to the original repository and
  remove the corresponding local scheduler patch.

Initial WB2A use case:

- keep the already-required burner/start-state source polled FAST;
- poll GFA P06/P09/P87 FAST only while burner/start activity is present;
- after activity ends, keep them FAST for a short hold window and then reduce
  them to a much slower idle cadence;
- do not use flame-on alone as the activation source because blower/pre-purge
  activity begins before established flame.

Desired outcome:

- reduce unnecessary Optolink traffic while the appliance is idle;
- retain high temporal resolution during burner starts and active operation;
- upstream the generic mechanism so less local patch maintenance is required.

## Repository maintenance

A separate cleanup plan is maintained in
[`repository-cleanup-plan.md`](repository-cleanup-plan.md).

The cleanup should be performed as a controlled refactor. Installer/updater
paths are currently coupled to the existing layout, so files must not simply be
moved without updating and testing all references.