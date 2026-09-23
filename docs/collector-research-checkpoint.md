# Collector research checkpoint - 2026-09-23

**Read this checkpoint before older collector-related tasks in the project roadmap.** It records the results from `vitosoft-private-archive-20260923-205048.7z` and subsequent explicit hardware tests. It supersedes older intermediate interpretations where they conflict, without erasing historical measurements or superseding unrelated dashboard work.

## Latest hardware update - 22:33 Europe/Berlin

**Step A is completed:** the user ran `wb2a-gfa-p80-probe.py` 1.0.0 on the local WB2A. Two independently synchronized VS1 reads of `0x4050` returned `0x20` (GFA). Actual P300 identity reads returned `20C2` before and after the test, both previously running services were restored, and the live result was PASS.

The transcript and scope are documented in [GFA live checkpoint](gfa-live-checkpoint.md). That document also describes the next helper, `wb2a-gfa-snapshot.py`, which is implemented and passes 45 offline tests but **has not yet been run on the appliance**. The next test reads only P06/P09/P10/P84 once each with fresh synchronization, guarded by P80=0x20 before and after. It is not a high-rate or simultaneous logger.

Do not repeat the initial P80-only experiment merely because older static-analysis files say hardware validation is pending. The new evidence proves P80 access and successful recovery in this run, not all GFA registers, permanent integration, firmware access or a pump override.

The full derived archive analysis, source hashes, SQL joins and IL references are in [Private archive analysis](../config/optolink-splitter/research/vitosoft/private-archive-2026-09-23-analysis.md). The [machine-readable archive evidence](../config/optolink-splitter/research/vitosoft/private-archive-2026-09-23-evidence.json) remains a record of the static-analysis pass and includes the GFA branch's 36 events.

## Archive findings

The fresh collector produced usable SQL exports and substantive IL dumps. All 15,350 manifest entries passed SHA256 verification. All 144 SQL-table CSVs matched the reported counts, totaling 608,740 rows. Four protected ILDASM outputs represent two FlowCalibration binaries, not a system-wide collection failure. A new full collector run is not required merely because these assemblies lack IL output.

The important results are:

1. **The update tables are empty.** `ecnUpdateDefinition` and `ecnDeviceSoftwareUpdate` each contain zero rows in the captured database. Earlier update-looking method names resolve to PC installation, UI refresh or cache readiness, not a demonstrated WB2A flasher.
2. **GFA events require burner-variant selection.** The 94 GFA_READ events in the VDensHO1 union span CES, GFA, SCOT and DOVER branches. The local P80 result now selects the GFA branch, with 36 metadata entries; individual runtime values still need validation.
3. **P09 is not universally fan RPM.** In the GFA branch, 0x4009 is a modulation setpoint with factor 0.3922. P06 at 0x4006 is the actual-fan-speed target with factor 30 rpm.
4. **The VS1/VSKO access implementation is supported by method bodies and now by the successful local P80 test.** Rapid successive reads in a persistent session have not been tested.
5. **Pump-address properties resolve to Neptun calibration**, not a proven base-VDensHO1 volatile pump override.
6. **The KM-BUS/LON block name needs implementation context.** The inspected block contains 16 LON RPC A010 participant entries, not a demonstrated physical KM-BUS enumeration/injection channel.

The archive analysis itself issued no appliance commands. The subsequent P80 test was explicitly executed by the user and transmitted only reads and communication-control bytes. Production profiles, dashboard, settings and controller parameters were not changed by these helpers. Raw proprietary binaries, SQL content, full IL and machine-specific exports were not committed.

## Workstream status and next action

| Workstream | Current result | Next action / dependency |
| --- | --- | --- |
| Collector integrity and source inventory | Completed for supplied archive. SQL succeeds despite misleading wrapper exit-code messages. | Retain original privately; improve reporting separately rather than recollecting. |
| Real blower RPM | P80 confirms GFA branch. P06 0x4006 is raw x30 rpm; P09 interpretation corrected. | Run the bounded four-register snapshot, then correlate P06 with natural operation. |
| GFA transport | Independently synchronized P80 read succeeded twice; P300 reply and running services restored. | Validate other allowlisted reads. A persistent-session logger is a separate later step, without parallel splitter polling. |
| Flame stabilization / startup plateau | P17/C08/C11/C13 do not belong to the now-confirmed GFA branch. | Validate P84/P06/P09/P10 before attributing the approximately 12-second interval to a parameter. No start-safety writes. |
| Internal pump selection / high-speed heating | No new verified WB2A volatile request. Neptun remains other-device calibration. | Seek supported runtime request or actual firmware evidence. Keep commands distinct from rotor feedback. |
| E7 persistence / endurance | 0x778B is periodically set/reset-only, not a defined write counter; 0x778E remains opaque. Prior minimal-write test does not establish RAM-only behavior. | No per-burner-cycle E7 policy until storage/endurance or a volatile alternative is established. |
| KM-BUS through Optolink | Named member-list block resolves to LON RPCs, not physical KM-BUS or function 0x5D. | Keep virtual diagnostics, physical KM-BUS, LON and legacy gateways separate; require exact request semantics. |
| Vitotrol emulation | No new Optolink-only raw slave-injection route. A0-only failure remains valid. | Continue physical emulator reference separately; static software investigation without blind writes. |
| Software identities | P80=0x20 now measured. Main regulation raw 0x0103 still lacks official release-name mapping. | Later read GFA P81-P83; keep controller, burner, panel, pump, profile and coding-card identities distinct. |
| Firmware update definitions | Completed negative result for this SQL snapshot: both tables empty. | Seek a specific new source/package when evidence identifies one; do not repeat the same query as an uncompleted task. |
| Full firmware acquisition | No authenticated WB2A image or complete readout route recovered; filename scan does not exclude all containers. | Identify board/MCU/memory/debug architecture or a genuine service read path; raw images private. |
| Coding plug | GFA branch includes identity/date/CRC diagnostics; no physical memory map, checksum algorithm or write recovery. | Later validate those read-only fields; identify spare-plug chips/programmer and make repeatable bench dumps. |
| RKR / restart / OPT / modulation | No new complete vendor bit semantics or thermal-kW mapping. | Capture full OPT ramp; correlate validated GFA data with 55E0/55D3. Keep restart, OPT and approximately 12-second timings separate. |
| Home Assistant diagnostics / faults | GFA identity is measured, but no new runtime entity or complete phase/bit table. | UI work independent; promote runtime sensors only after access/semantics and communication integration are validated. |
| A5/A6/A9 explanations | A5 relative pump threshold; A6 damped-temperature circuit shutdown, not global DHW inhibition; A9 normal-to-reduced transition standstill, not generic overrun. | Preserve operator-facing distinctions; no claim to have resolved every frost/priority interaction or A5 filter detail. |
| Weekly time programs | 56-byte week, four periods/day, 5+3 format, FF unused, C0 24:00; offline round-trip passed. | Offline editor/validator first, then explicit backup/order/write/readback checks. Production remains unchanged. |
| M2/hydraulic alternative | No new M2 test; earlier E7 test already demonstrated high speed on A1. | Optional real hydraulic redesign, not default software workaround. |
| Repository structure / maintenance | Analysis and live checkpoints indexed; no raw archive import. | Controlled refactor remains separate; preserve installer/updater compatibility. |

## Corrections future work must preserve

### Exact-profile union is not sufficient applicability

A data point can be linked to VDensHO1 while belonging to another burner variant behind a conditional UI group. Preserve event/group links and exclusion-condition logic. Event 8258/P80 selects the branch. The earlier Virtual_READ 0x7650=0x20 was supporting evidence; the new actual GFA_READ 0x4050=0x20 now confirms that selection.

Conversely, absence from a visible group does not prove absence in firmware: 0x0A3C was previously validated despite missing that membership. Metadata generates hypotheses, variant constraints prevent false generalization, and local read-only measurements establish support.

### Firmware vocabulary must be traced to its caller

A software-update table, BeginUpdate method or apparent version range is not a flashing proof. Here the tables are empty, BeginUpdate/EndUpdate call sites are ComboBox rendering, ReadyForUpdate is data-read readiness, and 0100..0103 / 0104..019F are profile-selection ranges.

### Command feedback is not independent measurement

0x0A3C and correlated 0x7660 values represent pump command/runtime state, not independent hydraulic flow or mechanical RPM. P09 modulation is not measured thermal output. A nonzero P06 result still needs plausible operating-state correlation before production presentation as a verified sensor.

## Closed or deprioritized local hypotheses

Unless new controller-specific evidence changes them:

- 0x55D3 bytes 6/7 are not fan RPM.
- Virtual-WILO is not a demonstrated control path for the installed Grundfos KM-BUS pump.
- Coding 51 was rejected even with the coding-display filter disabled.
- Historical 0x571D/0x581D burner-pump codings were rejected.
- 0x0A3A did not track local A1 calculated demand during the captured heating start.
- The tested internal-pump service command did not supply the required controlled 100-percent speed path.
- E8/E9 concern reduced heating, not flame-off periods during normal heating.
- A0 alone does not replace a responding physical/emulated Vitotrol participant.

## Immediate execution sequence

### Step A - completed: P80 identity

User's live run at 22:33 on 2026-09-23: two P80=0x20 replies, valid P300 baseline and recovery, both services restored. The original helper remains unchanged as a reproducible reference. [P80 runbook](gfa-p80-probe.md).

### Step B - prepared, live execution pending: bounded snapshot

Use [the snapshot instructions](gfa-live-checkpoint.md) for P06/P09/P10/P84. All reads have fresh synchronization; the sample timestamps differ. Preserve raw replies and report idle versus naturally running burner state. Do not force a start. No parameter writes, automatic updater execution or permanent VS1 configuration change.

The helper tries to restore communication and services after ordinary errors/signals. It is not an unconditional guarantee against SIGKILL, power failure or disconnected USB hardware. Verify Home Assistant freshness separately after the helper finishes.

### Step C - later: faster observation and independent offline work

Once runtime access is confirmed, review a persistent-session logger for finer timing. Do not mistake this first sequential snapshot for a startup trace. Only after read timing, semantics and normal-operation integration are validated should GFA values become production HA sensors.

Protected FlowCalibration analysis, embedded-resource investigation, E7 endurance, physical coding-plug dumping and actual firmware acquisition remain independent tasks. Time-program serialization can be developed offline; dashboard work does not wait for these hardware research steps.

## Completion boundary

The archive received complete manifest/table-count checks but not exhaustive understanding of every proprietary method. Subsequent P80 access is now hardware-confirmed from the user's transcript; other GFA access and pump/firmware solutions are not. Preserve each new hardware result with raw evidence, conditions and recovery status rather than inferring it from static metadata or this successful identity read.
