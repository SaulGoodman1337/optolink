# Vitosoft All-Devices cross-profile analysis - 2026-09-24

Status: **offline metadata comparison only; no new appliance writes or live requests performed**.

Source is the private v5 collector snapshot `vitosoft-private-archive-20260924-130004.7z`, SHA256 `ff9eda6738d0cbeaf59b3182acc73ac7d8d2e2ec4b85f5d8878f1f24d7e082ed`. The complete proprietary archive remains private. This file retains only small derived relationships useful to the Optolink research.

The existing [2026-09-23 private archive analysis](private-archive-2026-09-23-analysis.md) remains authoritative for variant-specific GFA semantics, firmware conclusions, pump cautions and source-code interpretation. This supplement adds a complete cross-profile relation graph; it does not supersede later live GFA checkpoints.

## Global graph

The installed Vitosoft definition set contains:

| Item | Count |
| --- | ---: |
| device profiles | 399 |
| event definitions | 11,582 |
| device-event links | 104,339 |
| low-level access definitions | 11,582 |
| unique low-level addresses | 5,356 |
| protocol-function names | 38 |
| globally defined events with no device-profile link | 399 |

All 11,582 event definitions resolve to a low-level access definition. The 38-function inventory has the same definition counts as the earlier archive report; the new information is primarily **which events/functions/addresses are linked to which device profiles**.

## VDensHO1 remains stable

Profile ID 60 / identification `20C2` still has:

- 581 linked events;
- 362 non-empty low-level addresses;
- 462 `Virtual_READ`, 94 `GFA_READ`, 22 `Remote_Procedure_Call` read definitions and one undefined read function;
- 182 `Virtual_WRITE`, 22 `Remote_Procedure_Call` write definitions and 375 undefined write functions.

This matches the earlier exact-profile counts. The new collector did not reveal a new Vitosoft definition version.

## Exact metadata aliases

In the exported event/address relation, these profiles have an identical signature:

- `VDensHO1`
- `VPendHO1`
- `VScotHO1`

Each has the same 581 event IDs and 362 non-empty addresses.

This is a **Vitosoft metadata alias**, not evidence that the physical controllers, firmware images or safe write behaviour are identical.

Nearby profiles provide useful comparison candidates but are not automatically applicable to the WB2A:

| Profile | Common event IDs | Extra | Missing |
| --- | ---: | ---: | ---: |
| VScotHO1_4 | 559 | 2 | 22 |
| VDensHO1_4 | 558 | 2 | 23 |
| VScotHO1_20 | 559 | 7 | 22 |
| VPlusHO1 | 540 | 18 | 41 |

Use those differences to generate hypotheses only. Require exact source semantics and local read-only validation before treating another profile's data point as supported.

## Important correction to profile-membership reasoning: orphan events

There are **399 event definitions with no link to any of the 399 device profiles**.

Examples include:

| Event | Address | Source label | Access |
| ---: | --- | --- | --- |
| 777 | `0x0A3A` | Heating circuit pump A1 set speed | Virtual_READ |
| 779 | `0x0A3B` | Heating circuit pump M2 set speed | Virtual_READ |
| 788 | `0x0A3C` | Internal pump set speed | Virtual_READ |
| 7239 | `0x0B01` | Heating circuit pump M3 set speed | Virtual_READ |

Address `0x0A3C` is already known from local WB2A research despite having no profile link in this graph.

Therefore preserve this rule:

> **No device-profile link does not prove protocol/firmware inaccessibility.**

Profile linkage is useful applicability evidence, but absence is not a safe negative capability test. This also means cross-profile discoveries must not be promoted directly into write probes.

## Virtual WILO

Global definitions contain:

- 74 `Virtual_WILO_READ` definitions;
- 9 `Virtual_WILO_WRITE` definitions.

In the complete Device↔Event link table, those functions are linked only to the profile named `WILO`; there is no VDensHO1 profile link.

This strengthens the existing conclusion that Virtual-WILO is **not a demonstrated control path for the installed WB2A pump**, but it does not turn missing profile linkage into a transport impossibility. The existing WB2A pump workstream must continue to rely on local runtime evidence and controller-specific semantics.

## EEPROM / KBus functions

Cross-profile linkage shows:

| Function | global definitions | linked profiles | linked to VDensHO1 |
| --- | ---: | ---: | --- |
| `KMBUS_EEPROM_READ` | 91 | 40 | no |
| `EEPROM_READ` | 91 | 21 | no |
| `EEPROM_WRITE` | 90 | 21 | no |
| `XRAM_READ` | 12 | 20 | no |

The EEPROM/XRAM links are concentrated in GWG-family definitions; KMBUS EEPROM also appears in DEKATEL/VCOM families.

This is **not** evidence that a WB2A coding plug can be dumped or modified through those generic functions. The physical coding-plug bench-dump track and the separately identified read-only diagnostics remain distinct.

## Firmware result remains negative for this installation

The newer LocalDB export still contains zero rows in both:

- `ecnUpdateDefinition`
- `ecnDeviceSoftwareUpdate`

No new target-linked firmware/flash event emerged from the all-device graph. Firmware-like events seen elsewhere belong to unrelated device families such as Vitocom/LAN-card/service-adapter contexts. Do not reinterpret them as WB2A firmware paths.

## GFA and blower semantics

The all-device graph confirms, but does not newly establish, the already documented GFA branch distinctions:

- `0x4006 / P06`: actual fan speed, factor 30 rpm;
- `0x4009 / P09`: GFA-branch modulation setpoint, factor 0.3922 %, not universally fan RPM;
- `0x400A / P10`: fan PWM setpoint, factor 0.4 %.

The stronger local evidence remains P80 branch selection and the subsequent live VS1/GFA captures. Do not collapse the 94-event GFA union across burner variants.

## Research use

The cross-profile graph is most useful for:

1. finding aliases/near-neighbour profiles around VDensHO1;
2. identifying addresses that exist in related device families but not the base profile;
3. detecting globally defined unlinked events that profile-only searches would miss;
4. separating transport vocabulary such as WILO/EEPROM/KBus from actual profile membership;
5. generating read-only hypotheses without pretending metadata membership is runtime proof.

Machine-readable derived evidence is in [all-devices-2026-09-24-evidence.json](all-devices-2026-09-24-evidence.json).


## v6 reproduction check

The later successful v6 snapshot `vitosoft-private-archive-20260924-143439.7z` (SHA256 `3d31380d6dfabf8ede9e305b115e847fb0670511e253a4ed4e59feef2f7adfee`) completed Deep, SQL and All-Devices successfully. All 16 files in `derived/all-devices/` are byte-identical to the v5 snapshot used for the cross-profile findings above.

Therefore v6 adds stronger provenance and successful collector completion, but **does not change the cross-profile semantic conclusions** in this document.
