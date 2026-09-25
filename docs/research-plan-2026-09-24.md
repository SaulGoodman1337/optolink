# WB2A research plan and TODOs - 2026-09-24

This is the **current execution plan** for the local Vitodens 200-W WB2A / VDensHO1 / 20C2 research. Older runbooks and checkpoints remain historical evidence, but their old "next step" wording does not override this file.

**Next-session handoff:** [WB2A research checkpoint - 2026-09-25](research-checkpoint-2026-09-25.md) consolidates the evening 2026-09-24 state and the exact next actions for the replacement EEPROM reader, regulation-board photos and the corrected mixed flame-correlation run.

## Current verified baseline

- Private Vitosoft Collector v6 snapshot: `vitosoft-private-archive-20260924-143439.7z`, SHA256 `3d31380d6dfabf8ede9e305b115e847fb0670511e253a4ed4e59feef2f7adfee`.
- v6 completed Deep, SQL, All-Devices and Tool-Dumps successfully; all 15,249 manifest files were re-hashed with no missing files or mismatches.
- The complete All-Devices graph contains 399 profiles, 11,582 events and 104,339 Device<->Event links. Its 16 persisted outputs are byte-identical between v5 and v6.
- Permanent VS1 is active on the production splitter. Read-only GFA access for P80/P06/P09/P87 is verified through the single serial owner and exposed to Home Assistant.
- Production timing is intentionally `olbreath=0.025 s`, GFA first attempt `0.025 s`, one raw-FF recovery retry at `0.150 s`, then quarantine/failure on a second FF. No further timing benchmark is planned unless telemetry shows instability.
- P06 / `0x4006` is the canonical controller-reported blower speed for this installation, scaled by 30 rpm/LSB. The old `0x55D3[6:7]` blower interpretation is closed.
- Main regulation software-version bytes are measured as `0x778C=01`, `0x778D=03`, raw pair `0x0103`.
- GFA P80 / `0x4050` is measured as `0x20`, selecting the local GFA branch.
- Pump-role model corrected: direct A1 heating uses the integrated pump as the A1 heating-circuit pump governed by E6/E7 and exposed by 0x7663; DHW uses the same physical pump in the internal/DHW circulation role governed by 6C (local 100%). Internal-pump result surfaces 0x0A3C/0x7660 must not be used as proof of the direct-A1 control algorithm.
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

## P0 - Burner-dependent A1 pump boost / firmware boundary

**Important correction:** the earlier model that treated direct-A1 runtime as
`0x7663 -> hidden clamp -> 0x0A3C -> 0x7660` is superseded.

The integrated physical KM-BUS pump has multiple logical roles:

- **direct A1 heating:** heating-circuit pump A1, governed by E6/E7 and exposed
  by `0x7663 / HKP_A1Drehzahl / Ausgang_HKP_A1`;
- **DHW/storage heating:** internal boiler/DHW circulation role, governed by
  `6C / 0x676C` (local value 100 %);
- **boiler-circuit role:** separate internal-pump configuration such as
  `K31 / 0x5731`, relevant to hydraulic-separation/mixer topologies.

`0x0A3C` and `0x7660` remain genuine internal-pump service/runtime
surfaces, but their correlations are **not** proof of the direct-A1 control
algorithm.

### Actual research target

Find whether local VDensHO1 / 20C2 contains a **volatile burner-dependent A1
pump boost/override** that can raise the direct heating-circuit pump during
burner operation **without repeated E7 coding writes**.

Repeated burner-triggered E7 writes are not a production solution. E7 is a
coding/configuration surface and storage/endurance is not proven suitable for
per-cycle automation.

### Historical Viessmann evidence

The verified Vitosoft-v6 archive proves that Viessmann used burner-dependent
pump concepts in other regulation families:

- `0x571D K1D_KonfiPumpenbeiBrennerein`:
  "Beimischpumpe EIN, wenn Brenner EIN";
- `0x581D SR13_K1D_KonfiPumpenbeiBrennerein`;
- legacy gas coding-card `0x1070` byte 5:
  "Pumpe bei Brennerbetrieb";
- corresponding NRx `0x1080` byte 5;
- later `0x7751 K51_KonfiHydrWeicheIntPumpe`.

None belongs to an exact VDensHO1 EventTypeGroup. Local `0x571D` and
`0x581D` were already invalid. On VDensHO1 the `0x1070` byte-5 slot is
explicitly `GWG75: Mindestdrehzahl Interne Pumpe`, so the older semantic must
not be transferred.

### Natural runtime result - 2026-09-25

A dedicated **read-only** watcher captured two complete natural A1 heating
burner cycles at E7=30.

Machine evidence:

`config/optolink-splitter/research/vitosoft/burner-a1-runtime-2026-09-25-evidence.json`

Raw CSV on appliance:

`/home/chatgpt-admin/wb2a-burner-a1-runtime-20260925-124401.csv`

Key observations:

- A1 pump speed stayed exactly **32 %** through prestart, flame-on, flame-off
  and the inter-cycle wait;
- `0x0A3A` stayed 0;
- source-backed `0xA152` HKP1 and internal-pump relay bits became active
  when heating hydraulics started and stayed unchanged through both burner
  cycles;
- the source-labelled `0xA152` burner-relay bit stayed 0 even with independent
  flame confirmation, so it is not the local GFA burner-request/output path;
- `0xA305 / nvoBoilerState_BLR_value` became nonzero with established flame,
  followed burner modulation closely and returned to 0 at/just before flame
  extinction; it is useful burner-output telemetry but not an independent
  pre-flame pump-boost request;
- no visible burner-dependent A1 speed boost occurred.

Cycle timings:

~~~text
cycle 1:
  GFA/mod start  12:50:58.755
  flame on       12:51:07.750
  flame off      12:51:35.366
  flame duration 27.616 s

cycle 2:
  GFA/mod start  12:55:35.156
  flame on       12:55:44.375
  flame off      12:56:12.223
  flame duration 27.848 s
~~~

Restart/startup timing:

~~~text
cycle1 flame off -> cycle2 GFA start = 239.790 s
cycle1 flame off -> cycle2 flame on  = 249.009 s
GFA start -> flame on                 =   9.219 s
~~~

Local coding-plug values `GWG65=4 min` and `GWG73=240 s` are both
numerically compatible with a ~240 s interval. Do not assign that interval
uniquely to either field yet.

`0x555A / Kesselsoll_eff` reproducibly dropped 38 -> 18 °C immediately
before both starts. The exact 20 K difference matches local `GWG72=20 K`.
Treat this as strong numeric/temporal correlation, not yet firmware-level
causal proof.

### Exposed control-surface closure

Exhaustive exact-VDensHO1 and global Vitosoft searches found:

- no exact VDensHO1 `nvi*` pump-speed command;
- `0x7663`, `0x0A3A`, `0x7660`, `0x0A3C` are read-only runtime/result
  surfaces;
- E6/E7/E8/E9 and K30/K31/K32/K34/6C are coding/configuration writes;
- `0x7500 RelaistestGWG200x` is diagnostic relay test, not a source-backed
  runtime A1 speed controller;
- global KBus write search found only one pump-semantic write event, a legacy
  Dekamatik shunt-pump object at `0x4301`;
- no VDensHO1/HO1 KBus pump-speed write event exists in the recovered catalog.

Therefore the Vitosoft-exposed service, LON and KBus layers are exhausted for
a source-backed volatile direct-A1 pump-speed override.

**TODO / next boundary:**

- [x] Correct the pump-role model; do not conflate direct A1, DHW and
  boiler-circuit pump roles.
- [x] Prove through natural cycles that the active local configuration does
  not visibly boost A1 speed with burner state.
- [x] Exhaust exact VDensHO1 service/LON pump-control surfaces.
- [x] Exhaust global Vitosoft KBus pump-write semantics for a VDensHO1 match.
- [ ] Continue at regulation-firmware / MCU level once the local PCB/MCU is
  identified.
- [ ] Use physical coding-plug EEPROM correlation as the next independent
  evidence path when the reader is available.
- [ ] Only reopen a volatile pump-control path if new vendor/firmware evidence
  produces a concrete local variable or algorithm.
- [ ] Never substitute CFDM production commands, relay-test functions or
  repeated E7 writes for the missing pump-speed function.

**Current conclusion:** the desired burner-dependent A1 boost is a
**firmware/MCU research question**, not an exposed Vitosoft service/LON/KBus
control feature on the recovered VDensHO1 model.

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

## P1 - KM-BUS/KBus read-memory mapping

**Tracking:** GitHub issue **#30** and
[kmbus-read-memory-analysis-2026-09-24.md](../config/optolink-splitter/research/vitosoft/kmbus-read-memory-analysis-2026-09-24.md).

The controller-side read functions have become a concrete reverse-engineering
workstream rather than a generic function-code search.

Current evidence:

- `0x41 KMBUS_RAM_READ` is locally implemented and `0x00F8/8` mirrors the
  normal identity block exactly.
- `0x43 KMBUS_EEPROM_READ` is locally implemented, but the prefix-less F8
  transaction returns a dynamic two-byte result repeated/truncated to requested
  length and is **not** a demonstrated linear EEPROM view.
- Collector v6 contains 91 `KMBUS_EEPROM_READ`, 12 `XRAM_READ`, 850
  `KBUS_TRANSPARENT_READ`, 500 `KBUS_EEPROM_LT_READ`, 232
  `KBUS_VIRTUAL_READ`, 97 `KBUS_INDIRECT_READ`, 11
  `KBUS_DIRECT_READ` and 7 `KBUS_DATAELEMENT_READ` event definitions.
- `KMBUS_RAM_READ` itself has **zero** Vitosoft event definitions even though
  raw 0x41 works on the local controller. Event/profile membership therefore
  remains applicability evidence, not a low-level capability boundary.
- 90/91 `KMBUS_EEPROM_READ` definitions use
  `PrefixRead=030000000101`, but captured Vitosoft host CIL now proves that
  ordinary non-RPC reads such as `0x43` do **not** serialize PrefixRead.
  PrefixRead-to-request-data conversion is confined to the
  `Remote_Procedure_Call / 0x07` path in this build.

**TODO:**

- [x] Extract a small derived KBus-read slice from the already captured v6
  `all-events.csv`; result: 2,055 read-event rows, committed in the private
  source repo under `collector-output/20260924-143439/kmbus-read-slice/`.
- [x] Group exact PrefixRead/parameter/address/length patterns per read family.
- [x] Resolve all 12 XRAM_READ definitions and the exceptional 1/91 KMBUS
  EEPROM prefix row.
- [ ] Continue semantic clustering of the 850 transparent, 500 EEPROM_LT and
  232 virtual KBus reads by participant/device family; structural prefix
  distributions are already extracted.
- [x] Complete the first bounded P300 `Virtual_READ` vs. `0x41`
  correlation matrix in a temporary P300 maintenance window. Result:
  **7/7 IDENTICAL**, including non-zero static values at `0x5730` and
  `0x0A54`; the wire trace confirms a genuine 0x41 response rather than
  client-side rewriting. Permanent VS1/KW + Party were restored successfully.
- [x] Repeat the dynamic pump objects `0x0A3C`, `0x7660`,
  `0x7663` during a non-zero pump state. Result:
  `0x7663=03 1E` (A1 request 30 %), `0x0A3C=32` (final 50 %),
  `0x7660=03 32` (internal pump 50 %); 0x01 and 0x41 were byte-identical
  on all three. Dynamic mirror proven.
- [x] Preserve the historical same-window 0x7663/0x0A3C/0x7660 correlation as raw hardware evidence only. The later pump-role correction supersedes the causal interpretation that direct-A1 control is implemented as an internal-pump GWG75 clamp. Do not use this correlation to infer the A1 algorithm.
- [x] Test all six source-derived `XRAM_READ 0x31` address/length shapes.
  Result: **0/6 successful**; every 0x31 request returned a valid Error Message
  with inner payload `05`. Matching cross-profile Virtual_READ controls
  returned Error Message payload `01`. All source XRAM rows have empty
  PrefixRead, so omitted prefix data does not explain the rejection.
- [x] Execute the historical manually prefixed `0x43` experiment.
  The controller accepted the frame and returned `0x88`, but later
  fresh-session and host-implementation evidence shows that this was **not**
  the captured Vitosoft standard wire shape. Preserve it only as evidence that
  the controller accepts that extended frame.
- [x] Expand to the bounded 13 exact Vitosoft-v6 GWG_BT2 0x43 block shapes:
  **13/13 successful responses**, but most higher-address blocks collapse to a
  repeated two-byte `54 98` pattern. This is not a validated EEPROM dump.
  Low blocks `0x0001=88`, `0x000A=4000000000`,
  `0x000F=1f00000000000000` remain structurally distinct.
- [x] Run same-session P-N-P PrefixRead discriminator. Initial
  `0x0001/1 = 88 -> 87 -> 88` candidate effect observed, while higher blocks
  remained dynamic.
- [x] Re-run `0x0001/1` with a **fresh P300 session per trial** and balanced
  order `PNNPNPPN`. Result: prefixed and no-prefix distributions are exactly
  equal (`81 x3, 87 x1` each). Classification:
  **NO_ISOLATED_PREFIX_EFFECT**. Earlier routing claim withdrawn.
- [x] Recover the Vitosoft host binding from
  `ecnEventType.PrefixRead/PrefixWrite` into request construction. Result:
  `PrefixRead` is converted to `BlockDataToDevice` only on the
  `Remote_Procedure_Call / FCRead 0x07` path. Standard non-RPC reads do not
  consume it.
- [x] Recover the exact ordinary serial VS2 construction:
  `EventType.FCRead -> MRKey.FunctionCode -> LDAPMessage.FunctionCode`,
  with Address/BlockLength mapped directly and optional Data coming only from
  `BlockDataToDevice`. For `0x43 / 0x0001 / len 1` the captured host frame
  is `41 05 00 43 00 01 01 4A`.
- [x] Scan the extracted ServiceTool managed assemblies for an external
  PrefixRead preprocessing path. Result: none found; only import/export setters
  outside `vsmInterfaceCore.dll`.
- [x] Close further live PrefixRead discrimination for 0x43. The no-prefix form
  is the captured host shape; broad address expansion remains unjustified.
- [x] Trace the 0x43 response path. Vitosoft copies the raw payload after the
  five LDAP header bytes and applies normal event conversion only; repeated
  words such as `5498`/`d301` are therefore controller-produced, not a host
  decoding artifact.
- [x] Resolve the catalog provenance: all 90 prefixed KMBUS_EEPROM_READ rows
  are linked only to 21 GWG profiles; the sole no-prefix row belongs to
  DEKATEL/VCOM. No 0x43 event belongs to VDensHO1.
- [x] Inspect archived `vsmGWG99Native.dll`: only `CheckGWG` and
  `TestCall_GWG99Native` are exported; no general GWG/KMBUS datapoint API was
  found. Historical GWG sources independently use TYPE `0x43` in a separate
  8-bit-address wire protocol.
- [x] Run the source-backed bounded discriminator
  `0x03 Physical_READ vs 0x43 KMBUS_EEPROM_READ` with fresh P300 sessions.
  Result: positive `0x01/0x41 @ 0x00F8/2` control is payload-identical
  (`20c2`); `0x03/0x43 @ 0x0001/1` is also stably identical
  (`81` in all four trials); `0x00F8/2` is dynamic but overlapping
  (`0x03=5491,5497`, `0x43=5491,5491`). No distinct local 0x43 data view
  was demonstrated.
- [x] Correct the probe reporter: v1.0.0 included the echoed function byte in
  equality classification and therefore mislabeled identical payload groups as
  `STABLE_DISTINCT`. v1.0.1 compares semantic response outcome/payload only;
  offline self-test is 6/6 PASS.
- [x] Preserve schedule-manager state across future P300 maintenance windows.
  v1.0.0 allowed it to exit while the splitter was paused; it was manually
  restored after this run. v1.0.2 now explicitly stops/restores the service.
- [ ] Require a new source-backed discriminator before any further 0x43 live
  work. Current evidence favors a common/aliased local `0x03/0x43`
  physical/service view over a dedicated LGM27 EEPROM interpretation, but
  universal equivalence is not proven.
- [ ] Keep all work read-only; no broad blind sweep and no KBUS/KMBUS writes.

The exact slice additionally shows that `XRAM_READ` is used on GWG families
for volatile timers/external-state/water-pressure objects; 90 prefixed
`KMBUS_EEPROM_READ` rows describe persistent **LGM27 burner-control**
parameters; and `KBUS_INDIRECT_READ` event names prove the 1-byte prefix is
the participant number. `Virtual_MBUS` is a separate external meter-M-Bus
family, not KM-BUS.

**Firmware boundary:** RAM-like views may expose hidden state, timers,
mailboxes and selector variables and are therefore highly useful for firmware
reverse engineering. They are not yet a program-flash read path. If the local
MCU later confirms as M30624FGPFP, its 256-KiB program flash occupies a 20-bit
address range while the normal VS2 address field is 16 bit; an Optolink
firmware dump would require an additional bank/prefix/RPC mechanism.

## P1 - Platinen-Research / local hardware identity

**Tracking:** GitHub issue **#25** and [regulation-board-7424735-pcb-research.md](../config/optolink-splitter/research/regulation-board-7424735-pcb-research.md).

An online comparison board carrying **7424735** has now been researched in depth. Public evidence correlates it with **7424743 / VBC 130-A03.100 / WB2B**, while the local project baseline remains **WB2A / VDensHO1 / 20C2** and WB2A spare-part evidence points to **GG1 / 7825241**. Therefore the comparison board is useful for topology research but must **not** yet be identified as the installed local board.

Current comparison-board findings:

- likely main MCU: **Renesas/Mitsubishi M16C/62P M30624FGPFP**;
- architecture: 256 KiB program flash, 4 KiB data flash, 20 KiB RAM;
- unpopulated **X15 has three pads**; earlier four-pad wording is superseded;
- X15 is worth passive tracing, but three pads are not a complete E8/E8a interface;
- Renesas flash-ID protection may block readout even when serial programming is physically available;
- X3/`145` remains a useful KM-BUS physical-layer lead;
- X10 and the vertical daughterboard remain unidentified.

**TODO:**

- [ ] Photograph the actual installed WB2A board and all labels before transferring any VBC130-specific claim.
- [ ] Confirm or reject local PCB part number `7424735`.
- [ ] Identify the exact local main MCU and any external memories.
- [ ] Trace X15 and X10 passively on the local board.
- [ ] Map local X3/145 KM-BUS protection/transceiver circuitry.
- [ ] Identify the daughterboard and burner/GFA MCU separately.
- [ ] Build a local annotated board map.
- [ ] Assess a non-destructive firmware-read path only after protection/programmer behavior is understood; never use erase-to-unlock on the production controller.

## P1 - Firmware architecture, not repeated SQL hunting

The current Vitosoft installation contains no authenticated WB2A firmware image and no target-linked update rows.

**TODO:**

- [x] Finish software identity first: P81-P83 read successfully as raw `02/06/76` under P80=`20`.
- [ ] Identify the main-regulation MCU, burner/GFA MCU and external firmware memories. **Planned next hardware evidence:** the user will photograph the regulation board at high resolution, including both sides where safely accessible, IC markings, board/revision labels and service/debug pads. Use [regulation-board-photo-capture.md](regulation-board-photo-capture.md).
- [ ] Keep regulation firmware, GFA firmware and coding-plug EEPROM as separate storage domains.
- [ ] Investigate only concrete service/readout paths backed by a function, method, board interface or known protocol.
- [ ] Archive any future raw firmware privately with hashes; commit only derived maps and reproducible analysis.

**Completion criterion:** either a concrete readout path with identified target memory, or a hardware architecture map that explains what must be accessed next.

## P2 - Flame-start semantics

Current evidence establishes ordering, not vendor meaning: P87 bit 1 becomes set before P09 leaves the high-start plateau.

**TODO:**

- [x] Search existing Vitosoft/private resources and protected-binary derivatives for P84/P85-P88 semantics. Collector-v6 scan: 1,134 text-like files, exact SQL follow-up; P84-P88 all map to generic `Allgemein_Int`, `EnumType=False`, with no recovered phase enum or status-bit table.
- [ ] Continue P84/P87 semantic work only through **independent live correlation or new GFA/firmware documentation**; do not repeat the same Vitosoft static search.
- [x] Prepare a mixed-VS1 flame-correlation helper that brackets P84/P87 against independent `0x55D3` and `0x55DD` flame indicators in the same persistent VS1 session. Offline compile and full pinned test chain pass; see [gfa-flame-correlation.md](gfa-flame-correlation.md).
- [ ] Run flame correlation again only when a real controller-driven burner start is likely. v1.0.1 production run reached hardware and restored 0x2306 correctly, but all 32 complete rounds stayed P84=00/P87=00 with both flame indicators off; attempt 33 hit a known sporadic P87=FF. v1.0.2 now applies the inherited bounded FF re-identification policy and reports `STARTUP_ACTIVITY_SEEN`. The 37 C room-setpoint write is confirmed as a demand stimulus, not a direct burner command.
- [ ] Keep the approximately 12-second post-flame transition separate from the 240-second restart/start-optimization behavior.
- [ ] Correlate pump heat removal and shutdown threshold behavior with startup traces.
- [ ] Do not reduce or disable flame-stabilization/start-safety parameters on the live gas burner.

## P2 - E7 persistence/endurance

The previous E7 100->99->100 test proved mutation/readback/restore, not RAM-only storage or safe write frequency. `0x778B` is not a proven write counter and `0x778E` remains opaque.

**TODO:**

- [ ] Prefer a volatile pump request if one is discovered.
- [ ] Do not implement per-burner-cycle E7 rewriting without independent storage/endurance evidence.
- [ ] If persistence is revisited, design a bounded reboot/power-cycle test with exact baseline/restore and no repeated cycling.

## P2 - LON/HCC input-object classification

**New hardware result:** `0xA403 nviHCC1 FlowSetpt` is readable and returned 20.00 °C while the internal A1 flow target `0x2544` was 0.0 °C in the same observation window. It is therefore a distinct object, not a simple mirror.

**TODO:**

- [x] Read `0xA401/A403` together with local A1 setpoints and `0xA441/A443` as absent-M2 controls. Result: all four HCC `nvi*` objects are `20.00 °C`; A1 local values differ and M2 is absent. Strong evidence for inactive/default external LON inputs.
- [x] Read `0xA3C0 nviDHWC Setpt` with current/effective DHW target `0x6500`. Result: `A3C0=50.00 °C`, `0x6500=5.0 °C`; they are not the same runtime target.
- [x] Read `0x2321 ExternRTSolltemperaturA1M1` vs `A401` and configured DHW target `0x6300` vs `A3C0`. Result: `0x2321=0 °C`, `A401=20.00 °C`; `0x6300=45 °C`, `0x6500=5.0 °C`, `A3C0=50.00 °C`. Direct-mirror hypotheses are rejected.
- [x] Do not add HCC `nvi*` objects to normal HA polling; current evidence supports them as external/default LON input-side variables.
- [x] Do not interpret `0xA403=20.00 °C` as an actual physical flow target without correlation; the same-window mismatch to `0x2544` disproves that shortcut.
- [x] Resolve HCC fallback semantics from the Viessmann LON handbook: HCC `nviHCCxSpaceSet` and `nviHCCxFlowTSet` use 20 °C as the documented fallback when their LON value is unavailable, and are not authoritative in the normal internal-control modes.
- [x] Resolve DHWC authority semantics from the Viessmann LON handbook: `nviDHWCSetpt` is only used when DHWC ApplicMode selects the LON DHW path; otherwise the internal DHW control remains authoritative.
- [x] Final read-only LON closure completed: `0xA400=FF`, `0xA440=FF`, `0xA3C2=FF`; all three ApplicMode objects are `HVAC_NUL`. Combined with the Viessmann LON semantics, the local HCC1/HCC2/DHWC nvi setpoint paths are non-authoritative/inactive.

**Status: LON/HCC/DHWC input classification closed for the local controller.** The observed HCC 20.00 °C values are source-backed fallback inputs; DHWC nvi setpoint is also inactive because its ApplicMode is HVAC_NUL. Do not promote these nvi values to normal Home Assistant control/state entities.

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

## Read-later diagnostic address backlog

A source-backed, read-only backlog is now maintained in [read-later-addresses-2026-09-24.md](read-later-addresses-2026-09-24.md).

Production-profile audit completed:
- `0x0816` exhaust-gas temperature is already polled at NORMAL cadence and can be used in dashboards without additional Optolink traffic.
- `0x5527`, `0xA305`, `0x0883`, primary sensor-status bytes, circulation-pump state, K12 and several KM diagnostics are also already present.
- `0x081A` is intentionally not promoted as a physical temperature because the associated local sensor-status evidence marks that path invalid/open/reference-state.
- first read-later batch completed: `0x8853=02` hardware-confirms a modulating burner; `0xA403=D007` decodes to 20.00 °C while same-window `0x2544=0.0 °C`, proving A403 is not a direct mirror of the internal A1 flow target; `0x0A4C=00000000` is consistent with E5=0/no separate A1 KM-BUS pump; KM error objects `0x0A31/32/34/36` and `0x6550` all returned `00`.

These are **later read-only verification items**. Never add a duplicate poll for an address already present in the production profile.

## P3 - Home Assistant and operator-facing follow-up

- [ ] Keep P06 as the canonical blower RPM entity.
- [ ] Keep P87 raw/unnamed in the UI.
- [ ] Optionally add P81-P83 as low-frequency/ONCE diagnostic entities; raw reads are now captured and labels are source-backed, but human-readable P81/P82 formatting and P83 decoding remain unresolved.
- [ ] If a pump-process dashboard is built, represent direct A1 heating, DHW/internal-pump operation and boiler-circuit operation as separate logical roles. Do not visualize the superseded `0x7663 -> 0x0A3C -> 0x7660` causal chain.
- [ ] Preserve unresolved diagnostic values as diagnostics rather than presenting inferred semantics as facts.

## Evidence discipline

Every new conclusion should name:

1. the source snapshot or live run;
2. exact address/event/function or class/method;
3. evidence level: `metadata`, `host_implementation`, `hardware_observation` or `hypothesis`;
4. raw value(s) and conversion separately;
5. recovery/restore result for any test that changes a controller value.

When a task is completed, update this plan and the specific research document in the same change. Historical runbooks may retain their original state, but the current status at their top must point here when their old "next step" has been superseded.
