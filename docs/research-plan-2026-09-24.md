# WB2A research plan and TODOs - 2026-09-24

This is the **current execution plan** for the local Vitodens 200-W WB2A / VDensHO1 / 20C2 research. Older runbooks and checkpoints remain historical evidence, but their old "next step" wording does not override this file.

## Current verified baseline

- Private Vitosoft Collector v6 snapshot: `vitosoft-private-archive-20260924-143439.7z`, SHA256 `3d31380d6dfabf8ede9e305b115e847fb0670511e253a4ed4e59feef2f7adfee`.
- v6 completed Deep, SQL, All-Devices and Tool-Dumps successfully; all 15,249 manifest files were re-hashed with no missing files or mismatches.
- The complete All-Devices graph contains 399 profiles, 11,582 events and 104,339 Device<->Event links. Its 16 persisted outputs are byte-identical between v5 and v6.
- Permanent VS1 is active on the production splitter. Read-only GFA access for P80/P06/P09/P87 is verified through the single serial owner and exposed to Home Assistant.
- Production timing is intentionally `olbreath=0.025 s`, GFA first attempt `0.025 s`, one raw-FF recovery retry at `0.150 s`, then quarantine/failure on a second FF. No further timing benchmark is planned unless telemetry shows instability.
- P06 / `0x4006` is the canonical controller-reported blower speed for this installation, scaled by 30 rpm/LSB. The old `0x55D3[6:7]` blower interpretation is closed.
- Main regulation software-version bytes are measured as `0x778C=01`, `0x778D=03`, raw pair `0x0103`.
- GFA P80 / `0x4050` is measured as `0x20`, selecting the local GFA branch.
- Pump captures distinguish the normal heating path from the DHW path: heating showed A1 runtime 36% with the internal pump clamped to the 50% GWG75 floor; DHW/DHW overrun showed the internal pump at 100% while A1 runtime was 0%.
- Two spare coding plugs have repeatable 512-byte chip1 dumps. Both use a two-EEPROM 24C04-class board architecture; the two chip1 images share an identical 226-byte prefix and an exact duplicated 82-byte logical record.

## Closed or deprioritized searches

Do not reopen these as generic tasks without new evidence:

- another full Collector run merely to repeat the same Vitosoft installation;
- another query of `ecnUpdateDefinition` or `ecnDeviceSoftwareUpdate`: both are exported and contain zero rows;
- `0x55D3[6:7]` as blower rpm;
- Virtual-WILO as the primary WB2A internal-pump control path;
- treating generic `EEPROM_*`, `KMBUS_EEPROM_READ` or `XRAM_READ` metadata as proof of a WB2A coding-plug programming route;
- treating missing VDensHO1 profile membership as proof that an address is inaccessible. `0x0A3C` is the counterexample;
- treating P87 bit 1 as a named "flame stabilized" signal; only its measured timing relation is established;
- blind GFA, burner-safety, EEPROM or coding-plug writes.

## P0 - Internal-pump arbitration map

**Goal:** determine where the normal A1 request becomes the final internal-pump request and whether a safe, documented heating-mode request path exists.

**Read-only channels:**

- `0x0A3A / 1` - heating-circuit pump A1 set speed;
- `0x0A3B / 1` - heating-circuit pump M2 set speed;
- `0x0A3C / 1` - internal pump set speed;
- `0x7663 / 2` - A1/M1 runtime/output;
- `0x7660 / 2` - internal-pump runtime/output.

**TODO:**

- [ ] Capture all five values in pump-off, heating request/pre-purge, flame-on stable heating and post-flame/restart-inhibition states.
- [ ] Preserve exact timestamps and burner/GFA context with each transition.
- [ ] Observe, if it occurs naturally, a heating state with A1 demand above the 50% GWG75 floor.
- [ ] Determine whether `0x0A3A` follows calculated A1 demand while `0x0A3C` follows the later internal-pump arbitration result.
- [ ] Compare the same channels during DHW/DHW overrun to keep the bypass path explicit.
- [ ] Do not introduce pump-control writes until the read-only arbitration map is internally consistent.

**Completion criterion:** a reproducible state table explains which object changes first and how `0x0A3A`, `0x0A3C`, `0x7663` and `0x7660` relate in heating and DHW.

## P0 - Complete GFA software identity

The read transport is already production-verified. The missing identity fields are therefore a small, bounded read-only task.

**TODO:**

- [ ] Read P81 / `0x4051` - FA software version.
- [ ] Read P82 / `0x4052` - FA software revision.
- [ ] Read P83 / `0x4053` - appliance/GFA configuration.
- [ ] Record raw bytes before assigning human-readable version notation.
- [ ] Correlate P81-P83 with P80=`0x20`, main-regulation `0x0103`, device software index `0x00FB=03` and coding-card identity `0x7656`.

**Completion criterion:** one provenance-preserving evidence record with raw P80-P83 values and no inferred release name unless a source provides the mapping.

## P1 - Coding-plug physical/software correlation

**Goal:** map the two physical 24C04-class EEPROMs to the controller-visible GWG and GFA coding-plug domains without writing either EEPROM.

**TODO:**

- [ ] Label future captures explicitly as PCB side `f01/ST` or `f02/Microchip`.
- [ ] Capture both EEPROMs of one spare three times each and compare repeatability.
- [ ] Capture both EEPROMs of the second spare where practical.
- [ ] Capture the active coding plug last, preserving its identity/revision and keeping the boiler unpowered/disconnected from the plug during bench reads.
- [ ] Immediately before or after the active-plug bench session, snapshot `0x1010`, `0x1020`, `0x1030..0x10C0`, `0x7656`.
- [ ] Through read-only GFA access, snapshot P90 and P100-P108.
- [ ] Compare semantic field vectors, complement pairs, mirror records and checksums; do not require controller-visible blocks to appear as literal flat byte sequences in EEPROM.
- [ ] Keep the hypothesis "one EEPROM may serve GWG/regulation and the other GFA/fire-control" explicitly unproven until side-specific evidence supports it.

**Completion criterion:** side-labelled repeatable dumps plus a documented correlation matrix showing confirmed, rejected and still-unknown mappings.

## P1 - Protected FlowCalibration and embedded resources

v6 confirms four protected ILDASM outputs representing two distinct FlowCalibration binary states. A new Collector run is not required.

**TODO:**

- [ ] Hash and identify the two distinct protected FlowCalibration binaries from the private snapshot.
- [ ] Perform offline static inspection with tools that do not execute the assemblies.
- [ ] Inspect embedded resources/proprietary containers for pump, calibration, firmware and coding-plug structures.
- [ ] Record negative findings as negative findings; a failed decompiler is not proof that the functionality is absent.

**Completion criterion:** a small derived report names each binary hash, tool/result and any source-supported constants or call paths.

## P1 - Firmware architecture, not repeated SQL hunting

The current Vitosoft installation contains no authenticated WB2A firmware image and no target-linked update rows.

**TODO:**

- [ ] Finish software identity first: P81-P83.
- [ ] Identify the main-regulation MCU, burner/GFA MCU, external flash/EEPROM devices and accessible service/debug headers from board evidence.
- [ ] Keep regulation firmware, GFA firmware and coding-plug EEPROM as separate storage domains.
- [ ] Investigate only concrete service/readout paths backed by a function, method, board interface or known protocol.
- [ ] Archive any future raw firmware privately with hashes; commit only derived maps and reproducible analysis.

**Completion criterion:** either a concrete readout path with identified target memory, or a hardware architecture map that explains what must be accessed next.

## P2 - Flame-start semantics

Current evidence establishes ordering, not vendor meaning: P87 bit 1 becomes set before P09 leaves the high-start plateau.

**TODO:**

- [ ] Search existing Vitosoft/private resources and protected-binary derivatives for P84/P85-P88 bit/phase semantics.
- [ ] Keep the approximately 12-second post-flame transition separate from the 240-second restart/start-optimization behavior.
- [ ] Correlate pump heat removal and shutdown threshold behavior with startup traces.
- [ ] Do not reduce or disable flame-stabilization/start-safety parameters on the live gas burner.

## P2 - E7 persistence/endurance

The previous E7 100->99->100 test proved mutation/readback/restore, not RAM-only storage or safe write frequency. `0x778B` is not a proven write counter and `0x778E` remains opaque.

**TODO:**

- [ ] Prefer a volatile pump request if one is discovered.
- [ ] Do not implement per-burner-cycle E7 rewriting without independent storage/endurance evidence.
- [ ] If persistence is revisited, design a bounded reboot/power-cycle test with exact baseline/restore and no repeated cycling.

## P2 - KM-BUS / Vitotrol

**TODO:**

- [ ] Keep physical KM-BUS slave emulation as the reference path.
- [ ] Use the reconstructed Vitotrol class/ID/slot and frame/CRC behavior for a physical emulator.
- [ ] Treat `0x41`/`0x43` address spaces as their own protocol spaces until a deterministic mapping is demonstrated.
- [ ] Do not treat A0=1 as emulation; the local BC fault already disproves that shortcut.
- [ ] Revisit Optolink-only emulation only if a concrete receive-side/member/mailbox mechanism is found.

## P3 - Home Assistant and operator-facing follow-up

- [ ] Keep P06 as the canonical blower RPM entity.
- [ ] Keep P87 raw/unnamed in the UI.
- [ ] Add new P81-P83 identity fields only after their raw reads are captured and labels are source-backed.
- [ ] Build the planned pump-process visualization once the `0x0A3A/0x0A3C/0x7663/0x7660` arbitration map is verified.
- [ ] Preserve unresolved diagnostic values as diagnostics rather than presenting inferred semantics as facts.

## Evidence discipline

Every new conclusion should name:

1. the source snapshot or live run;
2. exact address/event/function or class/method;
3. evidence level: `metadata`, `host_implementation`, `hardware_observation` or `hypothesis`;
4. raw value(s) and conversion separately;
5. recovery/restore result for any test that changes a controller value.

When a task is completed, update this plan and the specific research document in the same change. Historical runbooks may retain their original state, but the current status at their top must point here when their old "next step" has been superseded.
