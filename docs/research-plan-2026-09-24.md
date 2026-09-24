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

- [x] Treat `0x0A3C` as the verified final command shadow, not a writable target; live correlation with `0x7660[1]` is established.
- [x] Search remaining host-side/protected code for the selector. Focused decompilation of `MobileClient.exe`, `ViessmannCommonObjects.dll`, `vsmControlLibrary.dll`, FlowCalibration and the hydraulic host path found no `0x0A3C`/`0x7660` selector or arbitration method.
- [x] Analyze both protected FlowCalibration states and host integration. Result: the path is hydraulic calibration for VD3XX/Neptun and writes normal E6/E7/E9 configuration; it does not expose a new volatile WB2A pump override.
- [ ] Keep legacy `0x571D` / `0x581D` closed: both returned invalid-address on the local controller.
- [ ] Use natural passive observations only when they answer a specific formula question, e.g. whether an A1 request above the GWG75 50% floor is passed through to the internal command.
- [ ] Keep the documented external-demand/K34 path separate: it can force the internal circulation pump ON but is not proven to request 100% and can affect boiler heat demand via 9B.
- [x] Transfer the hidden-selector algorithm itself to controller-firmware/MCU analysis. The focused host/decompilation layer exposed no `0x0A3C` / `0x7660` arbitration implementation.
- [x] Complete the installed-pump characterization: `K30=01` (speed-controlled), `K31=100`, `K52=00`, `E5=00`, `E6=100`, `E7=30`, `E8=0`, `E9=100`, `0x0A54=01 11 01 01` with software index byte3=`01`; same-window runtime was idle (`A3C=0`, `7660=0000`, `7663=0000`).
- [x] K30 is `01`, not `02`; therefore a mandatory internal-pump volume-flow telemetry search is deprioritized for this installation. The rejected Neptun `0x0C24` path remains unrelated to base VDensHO1.
- [x] K30=`01` confirmed; continue the hidden runtime arbitration as a controller-firmware/MCU problem rather than a flow-sensor discovery problem.
- [x] Characterization completed read-only; no K30/K31 write was performed.

**Status: installed-pump characterization completed 2026-09-24.** The local controller identifies a speed-controlled internal pump (`K30=01`) without the K30=2 volume-flow capability flag, no hydraulic-separator sensor (`K52=0`), and software index `01`. The hidden selector upstream of `0x0A3C` remains a controller-firmware/MCU question.\n\n**Open configuration delta:** current `E9=100%` differs from the earlier documented hardware baseline `E9=50%`. Do not write it; verify provenance/readback before treating 100% as the intended baseline.

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

**Hardware status:** blocked until **2026-09-25** because the replacement EEPROM reader/programmer is still in transit. Do not schedule more bench-dump work before the new reader is available.

**Goal:** map the two physical 24C04-class EEPROMs to the controller-visible GWG and GFA coding-plug domains without writing either EEPROM.

**TODO:**

- [ ] **Resume 2026-09-25 or later when the new EEPROM reader is available.** Label future captures explicitly as PCB side `f01/ST` or `f02/Microchip`.
- [ ] Capture both EEPROMs of one spare three times each and compare repeatability.
- [ ] Capture both EEPROMs of the second spare where practical.
- [ ] Capture the active coding plug last, preserving its identity/revision and keeping the boiler unpowered/disconnected from the plug during bench reads.
- [x] Compare `0x1020[2:5]` with P103-P105. Result: GWG date slots are `FF FF FF`, while GFA remains `14 0C 04`; they are separate datasets. The comparison therefore does not resolve GFA integer-vs-BCD display or year base.
- [ ] Immediately before or after the active-plug bench session, snapshot `0x1010`, `0x1020`, `0x1030..0x10C0`, `0x7656`.
- [x] P90/P100-P108 read-only snapshot completed; see [gfa-coding-plug-p90-p108-read.md](gfa-coding-plug-p90-p108-read.md) and the linked live evidence.
- [ ] Compare semantic field vectors, complement pairs, mirror records and checksums. Initial exact-byte scan is complete: the saved spare-chip1 images do not contain the live GFA vector contiguously; mirrored single-byte candidates are documented separately.
- [x] Establish exact live software-view relations: `0x7656 = P80|P101|P107|P102 = 20 15 02 01` and `0x1040[0:2] = P107|P101 = 02 15`.
- [x] Resolve the `0x7656` field order independently from the exact VDensHO1 catalog: byte0 type=`20`/P80, byte1 identification=`15`/P101, byte2 GWG revision=`02`/P107, byte3 GFA revision=`01`/P102. A private-v6 four-row extract remains optional same-source confirmation, not a blocker.
- [ ] Keep the hypothesis "one EEPROM may serve GWG/regulation and the other GFA/fire-control" explicitly unproven until side-specific evidence supports it. The newly proven separation between GWG `0x1020` date slots and GFA P103-P105 makes the side-labelled second-EEPROM capture more valuable, but does not by itself assign a physical EEPROM to either domain.

**Completion criterion:** side-labelled repeatable dumps plus a documented correlation matrix showing confirmed, rejected and still-unknown mappings.

## P1 - Protected FlowCalibration and embedded resources

**Status: completed for the WB2A pump-control question.** See [FlowCalibration / hydraulic-calibration host analysis](../config/optolink-splitter/research/vitosoft/flowcalibration-hydraulic-2026-09-24.md).

- [x] Identify the two protected binary states: production 4.0.11.1 / SHA256 `bd8b...c017f`, and explicit test 4.0.7.1 / SHA256 `4aa4...7ee3`.
- [x] Perform static analysis without executing vendor binaries. ILSpy exposes metadata/public APIs; the protected numerical algorithm bodies remain obfuscated/stubbed.
- [x] Recover the unprotected host integration from `MobileClient.exe`, `ViessmannIPC.dll` and `vsmCommunicationInterface.dll`.
- [x] Resolve the hydraulic transport: `CustomAppId=1`, start/stop at Neptun `0x7950`, data from `0x7688/0x0C24/0x0C26`.
- [x] Resolve the result writer: KD3/KD4 plus E6/E7/E9, but only for supported VD3XX heater types; `NichtVD3xx` is explicitly rejected for result writes.
- [x] Verify v6 membership: every Neptun/HydraulicCalibration address used by the host path is absent from base VDensHO1; the known E6/E7/E8/E9 GWG objects remain valid VDensHO1 controls.
- [x] Record the negative conclusion: FlowCalibration does **not** expose a newly demonstrated volatile WB2A pump override.

**Completion result:** the host integration and applicability boundary are sufficiently resolved. The protected numerical calibration algorithm itself remains unrecovered, but it is no longer a priority for the current WB2A pump-selector question.

## P1 - Firmware architecture, not repeated SQL hunting

The current Vitosoft installation contains no authenticated WB2A firmware image and no target-linked update rows.

**TODO:**

- [x] Finish software identity first: P81-P83 read successfully as raw `02/06/76` under P80=`20`.
- [ ] Identify the main-regulation MCU, burner/GFA MCU and external firmware memories. GG1 family topology is documented; readable IC markings are still missing.
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
