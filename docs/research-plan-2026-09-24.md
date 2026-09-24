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

## P0 - Internal-pump hidden selection logic

**Completed hardware result:** the adjacent global result objects have already been tested on the local WB2A.

- `0x0A3A` is readable but remained `0` through the tested local heating start even while A1 runtime was active.
- `0x0A3B` is readable but remained `0`; no separate M2 pump path is active.
- `0x0A3C` tracks the final internal-pump command and matches `0x7660[1]` even when it diverges from `0x7663[1]`.
- `0x7663` represents the A1 heating-circuit runtime command; `0x7660` represents the internal physical-pump runtime command.
- Therefore the earlier hypothesis `0x0A3A = computed A1 request feeding 0x7663` is **rejected**. Do not schedule another generic A3A/A3B discriminator run.

Current best architecture:

```text
A1 demand + operating mode + E6/E7/E8/E9 + K31 + 6C + GWG75/76 + other overrides
                                  |
                                  v
                      hidden controller selection
                                  |
                                  v
                    0x0A3C ~= 0x7660[1]
                                  |
                                  v
                         internal KM-BUS pump
```

**TODO:**

- [ ] Treat `0x0A3C` as the verified final command shadow, not a writable target.
- [ ] Search remaining host-side/protected code specifically for the selector between exposed configuration inputs and `0x0A3C`.
- [ ] Prioritize the two protected FlowCalibration binary states and embedded resources; the normal deep string/member corpus did not expose a WB2A burner-dependent pump override.
- [ ] Keep legacy `0x571D` / `0x581D` closed: both returned invalid-address on the local controller.
- [ ] Use natural passive observations only when they answer a specific formula question, e.g. whether an A1 request above the GWG75 50% floor is passed through to the internal command.
- [ ] Keep the documented external-demand/K34 path separate: it can force the internal circulation pump ON but is not proven to request 100% and can affect boiler heat demand via 9B.
- [ ] If protected host code yields no selector, move this question to actual controller-firmware/MCU analysis rather than probing unrelated virtual addresses.

**Completion criterion:** a source-backed selector/override path is found, or the workstream is explicitly transferred to controller-firmware analysis with the exposed datapoint layer considered exhausted.

## P0 - Complete GFA software identity

The read transport is already production-verified. The missing identity fields are therefore a small, bounded read-only task.

**TODO:**

- [x] Read P81 / `0x4051` - FA software version: raw `0x02`.
- [x] Read P82 / `0x4052` - FA software revision: raw `0x06`.
- [x] Read P83 / `0x4053` - appliance/GFA configuration: raw `0x76`.
- [x] Record raw bytes before assigning human-readable version notation. No source-backed formatting rule for `02/06` has been recovered yet.
- [x] Correlate P81-P83 with P80=`0x20`, main-regulation `0x0103` and device software index `0x00FB=03`; coding-card/GFA correlation continues with P90/P100-P108.

**Status: completed 2026-09-24.** Hardware evidence: `P80=20`, `P81=02`, `P82=06`, `P83=76`, closing `P80=20`. Preserve P81/P82 as separate raw version/revision bytes until an official display mapping is found.

## P1 - Coding-plug physical/software correlation

**Goal:** map the two physical 24C04-class EEPROMs to the controller-visible GWG and GFA coding-plug domains without writing either EEPROM.

**TODO:**

- [ ] Label future captures explicitly as PCB side `f01/ST` or `f02/Microchip`.
- [ ] Capture both EEPROMs of one spare three times each and compare repeatability.
- [ ] Capture both EEPROMs of the second spare where practical.
- [ ] Capture the active coding plug last, preserving its identity/revision and keeping the boiler unpowered/disconnected from the plug during bench reads.
- [ ] Immediately before or after the active-plug bench session, snapshot `0x1010`, `0x1020`, `0x1030..0x10C0`, `0x7656`.
- [x] P90/P100-P108 read-only snapshot completed; see [gfa-coding-plug-p90-p108-read.md](gfa-coding-plug-p90-p108-read.md) and the linked live evidence.
- [ ] Compare semantic field vectors, complement pairs, mirror records and checksums. Initial exact-byte scan is complete: the saved spare-chip1 images do not contain the live GFA vector contiguously; mirrored single-byte candidates are documented separately.
- [x] Establish exact live software-view relations: `0x7656 = P80|P101|P107|P102 = 20 15 02 01` and `0x1040[0:2] = P107|P101 = 02 15`.
- [ ] Recover the low-level byte positions for the four `0x7656` source fields from the preserved Vitosoft metadata/SQL so the semantic order (Kennung / GFA revision / GWG revision / type) can be source-position-proven rather than inferred from the exact byte match.
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

- [x] Finish software identity first: P81-P83 read successfully as raw `02/06/76` under P80=`20`.
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

## Home Assistant dashboard implementation checkpoint

The current dashboard implementation findings and UI backlog are documented in
[`homeassistant-dashboard-checkpoint-2026-09-24.md`](homeassistant-dashboard-checkpoint-2026-09-24.md).

Key points carried into the execution plan:

- the intermittent Diagnose color/background issue is observed but its exact
  frontend root cause is not yet proven;
- the `fehlerhistorie_*_anzeige` aliases currently bypass the verified system
  fault-code translation because they subscribe to raw MQTT topics without
  their own `value_template`;
- `0x555A` effective boiler target and several other already-polled values can
  be added to the UI without increasing Optolink traffic;
- maintenance/service candidates from the exact VDensHO1 metadata remain
  read-only verification tasks before HA exposure;
- finish and verify Diagnose before redesigning Pumpen, Heizung, Heizkurve,
  Nachtabsenkung, Zeitprogramme and Graphen.

## P3 - Home Assistant and operator-facing follow-up

- [ ] Keep P06 as the canonical blower RPM entity.
- [ ] Keep P87 raw/unnamed in the UI.
- [ ] Optionally add P81-P83 as low-frequency/ONCE diagnostic entities; raw reads are now captured and labels are source-backed, but human-readable P81/P82 formatting and P83 decoding remain unresolved.
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
