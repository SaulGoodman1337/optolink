# Home Assistant dashboard checkpoint - 2026-09-24

Status: **analysis/documentation complete; implementation changes from this checkpoint are still pending unless explicitly marked otherwise**

This checkpoint records the current state of the Home Assistant dashboard after
reviewing the live profile and the current dashboard YAML. It is intended to be
the handoff/source of truth for the next dashboard implementation session.

Relevant files:

- `config/optolink-splitter/homeassistant-dashboard.yaml`
- `config/optolink-splitter/vdensho1-20c2-wb2a-homeassistant.py`
- `docs/project-roadmap.md`
- `docs/research-plan-2026-09-24.md`

## 1. Intermittently missing colors / background graphs

### Observed symptom

On the **Diagnose** view, some colored visual markings can be missing after the
initial dashboard render. Switching to another dashboard view and back, or
reloading the frontend, makes the missing visualization appear again.

The current Diagnose view uses three
`custom:background-graph-entities` cards:

- **Brenner / Regelung**
- **Temperaturen / Hydraulik**
- **Pumpen / Aktoren**

It also uses state-colored `custom:button-card` templates for discrete states.

### Current implementation detail

The background-graph cards define graph bounds, opacity, width, history window
and related display settings, but do **not** currently define explicit graph
colors for the affected series. Their initial visual appearance therefore
depends partly on frontend/custom-card initialization and theme resolution.

The `button-card` templates also use CSS variables such as
`var(--success-color)`, `var(--warning-color)`,
`var(--error-color)` and `var(--state-inactive-color)`, but those cards are
otherwise state-driven and are not currently proven to be the primary source
of the intermittent symptom.

### Assessment

The exact root cause is **not yet proven**. The behavior is consistent with an
initial-render/custom-card lifecycle problem because a view switch or reload
causes the missing visualization to reappear.

Do not document this as a confirmed bug in Home Assistant or in
`background-graph-entities` until reproduced more narrowly.

### Planned fix sequence

1. Give the short-history graph series explicit, stable colors rather than
   depending entirely on initial theme/custom-card color resolution.
2. Verify the Diagnose view from a cold browser/dashboard load.
3. Verify desktop and mobile.
4. If the issue still occurs, replace only the affected
   `background-graph-entities` cards with an already installed and more
   deterministic graph implementation, preferably ApexCharts.
5. Do **not** redesign the rest of Diagnose merely to solve this rendering
   issue.

Completion criterion: repeated cold loads render the same state colors and
short-history markings without requiring a view switch or browser reload.

## 2. Fault-history text issue

### Verified data path

The production profile reads the ten normal/system fault-history slots from
`0x7507` onward. Each slot is nine bytes:

- byte 0: system fault code;
- bytes 1..8: BCD date/time.

The normal source entities already contain a Jinja translation layer. The
currently source-backed/local mappings in the production profile are:

| Code | Text |
| --- | --- |
| `B7` | Kesselcodierkarte falsch/fehlerhaft |
| `F9` | Fehler Gebläse - Drehzahl nicht erreicht |
| `BC` | Fehler Fernbedienung HK1 |
| `BD` | Fehler Fernbedienung HK2 |

Unknown codes deliberately remain visible as raw hex instead of being guessed.

### Verified dashboard alias problem

The dashboard does not use the original fault-history entities directly. It
uses:

- `sensor.vitodens_200_wb2a_fehlerhistorie_01_anzeige`
- ...
- `sensor.vitodens_200_wb2a_fehlerhistorie_10_anzeige`

These aliases were intentionally added because Home Assistant can preserve an
old entity-registry disabled state even after MQTT discovery settings change.

However, the aliases currently subscribe directly to the raw
`{mqtt_base}/fehlerhistorie_XX` topics **without their own
`value_template`**. Therefore the source entity's fault-code translation is
not inherited by the alias. This explains why the Diagnose table can show a
code/raw slot without the expected human-readable error text.

### Required implementation change

Keep the dashboard aliases, because they solve the entity-registry problem, but
give the aliases the same verified system-fault decoding/template semantics as
the source entities.

Do not solve this by deleting the aliases and relying on Home Assistant to
re-enable historical registry entries.

### UI implementation and deferred refinement

The fault-history section has now been converted from the original wide raw
table to a compact chronology layout:

- **Systemfehler** and **GFA-Archiv** are separated visually;
- system entries show slot number, code, verified text where known and
  timestamp;
- the GFA archive remains a compact two-column raw-code/timestamp view;
- a small status row above the history shows current GFA state, the newest
  system-history code and the newest GFA-history code;
- repeated historical entries are intentionally **not** summarized or counted
  by code.

The current chronology is functional and accepted as the working baseline for
now, but its visual presentation is **not considered final**.

Deferred TODO:

- revisit spacing, typography, column proportions and visual hierarchy after
  the higher-priority dashboard/data work is complete;
- evaluate whether the system chronology should use a more purpose-built
  timeline/list presentation while remaining compact;
- keep historical entries visually distinct from currently active faults so a
  stored old fault is never presented as a live alarm;
- preserve the separate GFA code space and do not add guessed GFA descriptions;
- do **not** add a repeated-code/frequency summary unless explicitly revisited
  later.

### GFA fault history remains a separate code space

The 20 GFA history slots at `0x7590..` are a separate archive. Their byte 0
must **not** be decoded using the normal Vitotronic/system fault-code map.

Current policy remains:

- display the GFA code as raw hex;
- display its timestamp where present;
- do not assign a fault description until an exact GFA code map for this
  controller branch is recovered and supported.

A broad error-code list from another Viessmann controller family can be useful
for research correlation, but must not silently become the authoritative
VDensHO1/GFA map.

## 3. Existing production values not currently shown on the dashboard

The following values are already polled/published by the current production HA
profile but are not referenced by the current dashboard YAML. Adding them to a
dashboard therefore requires **no additional Optolink read**.

| Entity suffix | Address | Suggested use |
| --- | --- | --- |
| `aussentemperatur_tiefpass` | `0x5525` | heating/weather logic; compare raw/filtered/attenuated outside temperature |
| `kessel_solltemperatur_effektiv` | `0x555A` | high-value regulation diagnostic; compare with RKR/OPT/CFDM/BLR targets |
| `abgastemperatur` | `0x0816` | heating and combustion overview |
| `warmwasser_solltemperatur_aktuell` | `0x6500` | current DHW operating target |
| `heizkreis_m1_raumsolltemperatur_aktuell` | `0x2500` block | currently effective room target |
| `gfa_p80_typ` | `0x4050` | technical GFA identity; local value verified as `0x20` |
| `brenner_betriebsstunden_stufe1` | `0x0886` | service/counter context |
| `heizkreis_m1_pumpe_logisch` | `0x2906` | logical pump request/status; useful beside `0x7663` and pump speed |
| `warmwasser_flowswitch` | `0x0883` | DHW draw/flow state |
| `heizkreis_m1_sparbetrieb` | `0x2302` | operating-state indication; read-only use in dashboard |
| `relais_k12_status` | `0x0842` | actuator/relay diagnostics |
| `heizkreis_m1_frostgefahr` | `0x2500` block | operating-state indication |
| `heizkreis_m1_ferienbetrieb` | `0x2535` | operating-state indication |
| `brenner_flamme_gfa` | `0x55DD` | cross-check GFA flame bit against normal burner flame entity |
| `rkr_statusblock_55e0_raw` | `0x55E0` | research-only raw source; keep hidden/lower-level |
| `hydraulische_weiche_vorhanden` | `0x7752` | topology/identity only; installation is known not to have one |
| `solar_typ` | `0x7754` | topology/identity only; installation is known not to have solar |

### Highest-value additions

#### Effective boiler-target chain

`kessel_solltemperatur_effektiv` at `0x555A` should be added to Diagnose.
It can make the internal target path much clearer when placed beside:

- RKR normal target;
- RKR startup-optimized target (OPT);
- CFDM effective target;
- BLR effective target;
- modulation/GFA demand.

This is more useful than adding another isolated temperature tile.

#### Pump request/output chain

`heizkreis_m1_pumpe_logisch` should be visualized together with:

- heating-circuit demand/logical state;
- A1 output at `0x7663`;
- internal pump command/runtime at `0x7660`;
- pump speed;
- final internal-pump command shadow `0x0A3C` once the intended operator
  presentation is settled.

The desired visual pattern is a compact process chain similar to the existing
combustion sequence, while preserving the current research distinction between
A1 heating-circuit runtime and the internal physical-pump command.

#### Useful operating-state chips

Good compact additions to the normal/operator-facing part of the dashboard:

- DHW flow switch;
- economy state;
- frost-danger state;
- holiday state;
- exhaust-gas temperature.

GFA P80, raw RKR status and redundant flame bits belong in the technical
diagnostic/research area rather than the top-level daily view.

## 4. Potential new values from the exact VDensHO1 Vitosoft metadata

The exact local VDensHO1 event metadata contains additional diagnostic/service
objects that are not yet part of the production HA profile.

The most promising next group is **maintenance/service status**:

| Vitosoft name | Address |
| --- | --- |
| (23) Eingestelltes Zeitintervall | `0x5723` |
| (24) Wartung | `0x5724` |
| (21) Grenzwert Betriebsstunden Brenner | `0x5721` |
| Betriebsstunden Brenner seit letzter Wartung | `0x7570` |
| vergangene Zeit seit letzter Wartung | `0x756C` |

These addresses/names are source-backed for the exact VDensHO1 profile.

### Maintenance live validation completed

Read-only validation on the local **VDensHO1 / 20C2 / SW03** appliance on
2026-09-24 returned:

| Address | Raw | Verified interpretation |
| --- | --- | --- |
| `0x5721` | `00` | configured burner-runtime maintenance threshold = 0 h; source conversion is raw x 100 h |
| `0x5723` | `00` | configured maintenance interval = 0 months |
| `0x5724` | `00` | maintenance status = `Grundzustand` |
| `0x756C` | `00000000` | initial raw value only; later write testing proved custom `LastCheckInterval` reference semantics |
| `0x7570` | `00000000` | initial raw value only; source uses custom `LastBurnerCheck` conversion |

All five reads succeeded with their source-backed block lengths.

Follow-up splitter testing then verified `0x5723` as read/write. Setting it
temporarily to 24 months produced raw `0x18` and restoring it to zero produced
raw `0x00`. Both writes caused `0x756C` to be replaced with a new
32-bit reference value; the two captured values were exactly ten counts apart
over a ten-second test interval. Therefore `0x756C` is **not** a plain
elapsed-month counter. The source conversion is `LastCheckInterval`, whose
exact wall-clock conversion remains unresolved.

The original Vitosoft event inventory confirms that `0x756C` and
`0x7570` are read-only Type-1 events.

Follow-up splitter tests completed the missing semantics:

- `0x5721` is locally verified R/W; a later live CLI test showed that
  changing it from 0 h to a nonzero threshold re-baselines `0x7570` to the
  current burner-runtime counter; the observed nonzero -> 0 restore did not
  re-baseline it again;
- `0x5723` is locally verified R/W for 0..24 months;
- maintenance reset is locally verified end-to-end as `0x5724 = 1`
  followed by `0x5724 = 0`;
- that reset re-baselines the `0x756C` LastCheckInterval reference;
- the `0x7570` effect is conditional: an early reset initialized a zero
  burner reference, while a later guarded CLI reset with `0x5721 = 0 h`
  left the existing burner reference unchanged;
- burner runtime since the current burner maintenance reference is therefore
  `(current 0x08A7 - stored 0x7570) / 3600`;
- total burner runtime `0x08A7` and burner starts `0x088A` remained
  unchanged during the maintenance reset.

The splitter-side maintenance read/write/reset behavior is therefore verified.

The zero configuration at `0x5721` / `0x5723` should be described
conservatively as **no nonzero maintenance threshold/interval currently
configured**. It must not be presented as evidence for when the appliance was
last serviced.

The five values are now exposed in the production HA profile as slow-changing
`RARE` read-only diagnostic entities:

- `wartung_brennerstunden_grenzwert`;
- `wartung_zeitintervall`;
- `wartung_status`;
- technical raw reference sensors `wartung_intervall_referenz_raw` and
  `wartung_brenner_referenz_raw` for the two custom-conversion registers.

No command/reset entity is exposed even though Vitosoft contains maintenance
write/reset paths.

### Deferred HA task: editable maintenance configuration

In a later Home Assistant dashboard session, build a compact **Service /
Wartung** section around these entities. The intended end state is to allow the
maintenance interval and burner-runtime threshold to be configured from Home
Assistant, with a separately protected maintenance-reset action.

The splitter workstream has now verified the real controller write/reset paths
and the guarded CLI. Home Assistant implementation remains intentionally
deferred to a dedicated dashboard session.

The HA implementation must preserve these verified constraints:

- `0x5721` writes can re-baseline `0x7570` and require explicit warning;
- `0x5723` writes re-baseline `0x756C` and require explicit warning;
- `0x5724: 1 -> 0` is the protected maintenance-reset sequence;
- the reset reliably re-baselines `0x756C`, but its effect on `0x7570` is
  conditional and must be reported rather than assumed;
- `0x756C` and `0x7570` remain read-only;
- lifetime counters `0x08A7` and `0x088A` must never be reset by this UI.

Other metadata candidates include controller identity, remote/KM-BUS software
indices and communication topology. These are lower priority for normal
operation and should be kept in a technical/system-information area.

### Explicit exclusions

Do not add a datapoint merely because it exists in the Vitosoft profile.

The production profile intentionally excludes measurements for absent or
invalid local hardware, including:

- M2 as an active local heating circuit;
- solar measurements;
- hydraulic-separator temperature measurements;
- default-looking values from invalid/open sensor inputs.

Topology/presence values may still be shown as identity information when they
are useful, but they must not be presented as live physical measurements.

## 5. Diagnose view completion plan

Before propagating the visual design to other pages, finish Diagnose in this
order:

1. fix/verify intermittent color/background rendering;
2. fix fault-history alias decoding; **implemented**;
3. keep the current compact fault chronology as the accepted baseline and
   revisit its visual/UX design later;
4. add the effective boiler target `0x555A`;
5. add selected already-polled status values where they improve diagnosis;
6. add a pump request/output process presentation only if labels remain
   faithful to the verified command-path distinctions;
7. verify desktop and mobile;
8. preserve unresolved values as clearly marked technical/research data.

Diagnose then becomes the stable reference implementation for all later views.

## 5b. Pumpen view modern cockpit test

Status: **implemented and live-tested / accepted as provisional baseline**

The **Pumpen** view has been rebuilt as the first follow-up view using the
Diagnose cockpit language. The current live result is usable and will be kept
for now, but the visual design is **not considered final** and should be
revisited in a later dashboard-design pass.

Current structure:

- top-level pump/hydraulic status badges and chips;
- separate live sections for **Heizkreis M1** and the **internal boiler pump**;
- short-history background graphs for pump speed/hydraulic context;
- compact status tiles for logical M1 request, A1 output, pump status, speed
  and diverter-valve state;
- editable E6/E7/E8/E9/A9 and coding 31 controls retained;
- long parameter explanations moved from separate info buttons to hold-action
  browser_mod popups to reduce visual clutter;
- DHW charging/circulation states and controls consolidated into a modern
  subsection;
- KM-BUS pump diagnostics and hardware identity grouped at the bottom.

Semantics are intentionally conservative:

- `0x2906` logical M1 request and `0x7663` A1 output are shown together;
- `0x7660` internal-pump runtime is shown as a separate boiler-pump path;
- the dashboard does **not** imply that A1 output directly drives the internal
  physical pump;
- the unresolved upstream selector feeding the final internal-pump command
  remains a research topic rather than an operator-facing claim.

All Vitodens entities referenced by the redesigned Pumpen view were checked
against the current production Home Assistant profile before committing.

Deferred TODO:

- revisit the Pumpen page later with a stronger visual concept;
- refine spacing, density, colors, hierarchy and control grouping;
- reconsider whether the request/output/runtime relationships can be presented
  more intuitively without implying an unverified direct control path;
- keep the current implementation as the working baseline until that redesign.

## 6. Order for redesigning the remaining dashboard views

The agreed visual direction is to reuse the Diagnose cockpit language rather
than rebuild pages as plain entity lists.

Recommended implementation order:

1. **Pumpen**
   - highest-value next page;
   - request -> A1 output -> internal command -> speed -> hydraulic result;
   - short history backgrounds plus discrete process/status cards.
2. **Heizung**
   - coherent operating cockpit;
   - burner, temperatures, DHW, pump state and controls clearly separated.
3. **Heizkurve**
   - retain graph strength;
   - modernize D3/D4, A3/A5/A6, minimum/maximum limits and active logic.
4. **Nachtabsenkung**
   - separate automation state, timing, demand logic and currently effective
     setpoints.
5. **Zeitprogramme**
   - complete daily 8-byte block semantics are hardware-verified;
   - guarded schedule-manager write/readback/restore path is implemented;
   - 21 non-optimistic HA text editors are exposed through MQTT discovery;
   - the dashboard is now a three-lane weekly cockpit with 24 h bars,
     active-now indication and tap-to-edit weekday rows;
   - first live Home Assistant editor write after deployment is still pending.
6. **Graphen**
   - make the existing ApexCharts page visually consistent;
   - remove graphs that merely duplicate contextual graphs elsewhere.

Implementation rule remains: **one view at a time**, with desktop/mobile visual
verification before using the pattern on the next view.

## 7. Next implementation-session checklist

- [ ] Apply deterministic color handling to the three Diagnose short-history cards.
- [ ] Cold-load test Diagnose without switching views.
- [x] Copy verified system-fault decoding into the `*_anzeige` aliases.
- [x] Replace the original raw fault-history table with the compact chronology baseline.
- [ ] Revisit fault-history visual/UX design later; current chronology is accepted for now and no repeated-code summary is wanted.
- [ ] Add `kessel_solltemperatur_effektiv`.
- [ ] Decide which of exhaust temperature, DHW flow, economy, frost and holiday
      state belong in the top-level Diagnose view.
- [ ] Design the logical-pump -> A1 output -> internal-pump chain.
- [x] Read-only verify maintenance/service candidates and add read-only diagnostic entities.
- [ ] Add editable Service / Wartung controls in HA using the verified splitter semantics.
- [x] Run `wb2a-schedule-probe snapshot` and preserve the 21 raw day blocks.
- [x] Verify 0/1/2/4 interval writes, slot clearing, 24:00 and byte-exact restore.
- [x] Implement guarded schedule-manager writes and the full Zeitprogramme editor.
- [ ] Live-test one Home Assistant weekday edit and verify status/readback presentation.
- [ ] Verify all changed cards on desktop and mobile.
- [ ] Only after Diagnose is stable, start the **Pumpen** page redesign.
