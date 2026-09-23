# Collector research checkpoint - 2026-09-23

**Read this checkpoint before older collector-related tasks in the project roadmap.** It records the results from `vitosoft-private-archive-20260923-205048.7z` and supersedes older intermediate interpretations where they conflict. It does not supersede later independent dashboard work or erase historical hardware measurements.

The full derived analysis, source hashes, SQL join details and IL method references are in [Private archive analysis](../config/optolink-splitter/research/vitosoft/private-archive-2026-09-23-analysis.md). The [machine-readable evidence](../config/optolink-splitter/research/vitosoft/private-archive-2026-09-23-evidence.json) includes the expected GFA branch's 36 events.

## Executive checkpoint

The fresh collector produced usable SQL exports and substantive IL dumps. All 15,350 manifest entries passed SHA256 verification. All 144 SQL-table CSVs were parsed and matched the reported counts, totaling 608,740 rows. Four protected ILDASM outputs represent two FlowCalibration binaries, not a system-wide collection failure. A new full collector run is not the next priority merely because these protected assemblies lack IL output.

The most important changes are:

1. **The update tables are empty.** `ecnUpdateDefinition` and `ecnDeviceSoftwareUpdate` each contain zero rows in the captured database. Earlier update-looking method names resolve to PC installation, UI refresh or data-cache readiness, not a demonstrated WB2A flasher.
2. **GFA events require burner-variant selection.** The 94 GFA_READ events in the VDensHO1 union span CES, GFA, SCOT and DOVER branches. The expected local GFA branch has 36 entries and must be selected after reading P80.
3. **P09 is not universally fan RPM.** In the GFA branch, 0x4009 is a modulation setpoint with factor 0.3922; P06 at 0x4006 remains the actual-fan-speed candidate with factor 30 rpm.
4. **The VS1/VSKO access implementation is now supported by full method bodies.** Local hardware validation is still outstanding.
5. **Pump-address properties resolve to Neptun calibration.** They do not establish a base-VDensHO1 volatile pump override.
6. **The KM-BUS/LON block name is misleading without implementation context.** The inspected block contains 16 LON RPC A010 participant entries, not a demonstrated physical KM-BUS enumeration/injection channel.

No appliance command, production profile change or dashboard change was performed in this analysis. Proprietary binaries, raw SQL content, full IL and machine-specific exports were not committed.

## Workstream status and next action

| Workstream | Result from this archive | Next action / dependency |
| --- | --- | --- |
| Collector integrity and source inventory | Completed for supplied archive; raw-source hashes match the earlier production XML set. SQL succeeds despite misleading wrapper exit-code messages. | Retain original archive privately. Improve future wrapper reporting separately; do not repeat the entire run unnecessarily. |
| Real blower RPM | Exact expected GFA branch retains P06 0x4006, raw x 30 rpm. P09 interpretation corrected. | Build/review an exclusive-port read-only VSKO probe, confirm P80, then correlate P06 over a natural start/run/stop. |
| GFA transport | Vitosoft switches to VS1, maps abstract GFA_READ 0xC9 to 0x6B, and restores prior processing/interface state. | Validate the protocol lifecycle on the appliance with a strict read allowlist and guaranteed restoration. No parallel splitter polling during VS1. |
| Flame stabilization / startup plateau | Variant selection removes unsupported assumptions about P17/C08/C11/C13. Those previously discussed entries are not in the expected GFA branch. | Observe valid P84/status/P06/P09/P10 data before attributing the approximately 12-second interval to a parameter. No start-safety writes. |
| Internal pump selection / 100-percent heating operation | Neptun properties resolved, but linked to later/different devices; no new verified WB2A volatile request. Existing A1/final-pump distinction remains. | Focus on a supported runtime request or actual firmware evidence. Keep commands distinct from measured rotor feedback. |
| E7 persistence / endurance | 0x778B description is periodically set/reset-only, not a defined write counter; 0x778E remains opaque. Prior minimal-write test does not prove RAM-only semantics. | Do not adopt per-burner-cycle E7 rewriting until storage behavior/endurance or a volatile alternative is established. |
| KM-BUS through Optolink | sysblock_KMBus_LonMemberList resolves to LON RPC entries. The name does not bind it to physical KM-BUS or function 0x5D. | Keep participant virtual diagnostics, physical KM-BUS, LON RPC and legacy gateway functions separate. Require exact request semantics before further probes. |
| Vitotrol emulation | No new proven Optolink-only raw slave-injection route. Earlier A0-only failure remains valid. | Continue the source-supported physical emulator route separately; static software investigation remains open, without blind writes. |
| Regulation/GFA/software identities | SQL resolves profile-selection bounds; VSKO enabled for VDensHO1. Main regulation raw 0x0103 is not an official release-name mapping. | Read GFA P80-P83 if access works. Keep controller, burner, panel, pump, profile and coding-card identities distinct. |
| Firmware update definitions | Completed negative result for this SQL snapshot: both relevant tables empty. PC updater/UI names are not a heater flash workflow. | Seek a specific new source or package only when evidence identifies one. Do not rerun the same SQL query as an uncompleted task. |
| Full firmware acquisition | No authenticated WB2A image or complete readout route recovered. Filename scan is not proof against all embedded containers. | Identify board/MCU/memory/debug architecture or a genuine source-defined service read path. Keep any resulting raw image private. |
| Coding plug | Expected GFA branch exposes extra identity/date/CRC diagnostics. No physical dump/checksum algorithm/write recovery established. | First validate read-only GFA identity fields. Separately identify spare-plug chips and programmer, then make repeatable read-only bench dumps. |
| RKR / restart / OPT / modulation | Existing measured restart, OPT and startup observations not replaced by new vendor bit semantics. Thermal-kW mapping remains unverified. | Capture the full OPT ramp; correlate source-valid GFA states with 0x55E0 and 0x55D3. Keep 240-second restart, OPT timing and approximately 12-second transition separate. |
| Home Assistant diagnostics and fault display | Better branch/scaling/identity distinctions; no newly hardware-verified entity. No complete new phase/bit enum table found. | Continue UI work independently. Promote sensors only after access/semantics validation; do not restore false blower RPM or relabel raw state as vendor-defined state. |
| A5/A6/A9 explanations | A5 relative pump threshold and A6 damped-temperature circuit shutdown are source-described. A6 is not a global DHW inhibit. A9 remains the normal-to-reduced transition pump standstill, not generic overrun. | Use precise operator-facing wording. Do not claim the archive settles every frost-protection/priority interaction or A5's exact outdoor-temperature filter. |
| Weekly time programs | Source-backed 56-byte week, four periods/day, 5+3 time format, FF unused, C0 24:00. Strict offline round-trip test passed. | Build an offline editor/validator first. Verify day/slot ordering and backups before any explicit live write/readback test. Current production behavior unchanged. |
| M2/hydraulic alternative | No new local M2 test or reason to reinterpret the Neptun path as a coding-only M2 conversion. Earlier E7 test already proved high pump speed on A1. | Keep as an optional real hydraulic redesign, not the default software workaround. |
| Repository structure / research maintenance | Full analysis and this cross-topic checkpoint added; original raw archive is not imported publicly. | Controlled path refactor remains separate. Preserve installer/updater compatibility and ensure new findings are indexed before moving files. |

## Corrections that future work must preserve

### Exact-profile union is not sufficient applicability

A data point may be linked to VDensHO1 but belong to another burner variant behind a conditional UI group. Future extractions should preserve event-to-group links and exclusion-condition logic. Event 8258/P80 is the branch selector. A successful Virtual_READ chip identity at 0x7650 is useful prior evidence, but not a substitute for confirming GFA_READ 0x4050.

Conversely, absence from a visible device group does not prove absence in firmware: 0x0A3C was previously validated locally despite missing that visible membership. These two rules are compatible: metadata generates hypotheses, variant constraints prevent false generalization, and live read-only measurements establish local support.

### Firmware vocabulary must be traced to its caller

The presence of a software-update table, method named BeginUpdate or apparent version range is not a firmware-flashing proof. In this capture, the tables are empty, BeginUpdate/EndUpdate call sites belong to ComboBox rendering, ReadyForUpdate belongs to data-read readiness, and 0100..0103 / 0104..019F are profile-selection ranges.

### Command feedback is not independent measurement

0x0A3C and correlated 0x7660 pump values represent the selected/transmitted command/runtime state. Their consistency is valuable but does not prove actual hydraulic flow or mechanical RPM. Similarly, P09 modulation is not measured boiler thermal output.

## Closed or deprioritized local hypotheses

These earlier results remain in force unless genuinely new, controller-specific evidence changes them:

- 0x55D3 bytes 6/7 are not fan RPM.
- Virtual-WILO is not a demonstrated control path for the installed internal Grundfos KM-BUS pump.
- Coding 51 was rejected locally even after the coding-display filter was disabled.
- Historical 0x571D/0x581D burner-pump codings were rejected locally.
- 0x0A3A did not track the local A1 calculated demand during the captured heating start.
- The tested internal-pump actuator service command did not establish the required controlled 100-percent speed path.
- E8/E9 concern reduced-heating mode, not flame-off periods within normal heating.
- Declaring a Vitotrol with A0 alone does not replace a responding physical/emulated participant.

## Immediate execution sequence

### Step A - exclusive read-only GFA identity probe

Produce an original minimal helper with a read-only register allowlist. Validate its frame construction offline, pause the normal splitter deliberately, obtain exclusive serial ownership, enter VS1 using the source-derived sequence, read only P80, and restore the previous protocol/service state even after timeouts. Do not run this automatically as part of a normal update.

### Step B - variant-aware observations

Only after P80 confirms the branch, collect actual RPM at P06, modulation command at P09, PWM at P10, operating phase P84 and selected raw status bytes. Keep raw capture, timestamps and interpretation separate. Correlate with an ordinary burner cycle before exposing operational Home Assistant entities.

### Step C - remaining offline tracks

The preserved archive can support further focused analysis of protected FlowCalibration metadata/bodies and overlooked embedded resources. Such work must not silently promote later-controller Neptun operations into WB2A support. Keep firmware extraction, E7 endurance and physical coding-plug dumping explicit unresolved tasks.

Time-program serialization can be developed and tested entirely offline until the user deliberately requests a controlled live test. Dashboard layout work does not depend on waiting for these hardware research steps.

## Completion boundary

This is a broad cross-workstream static analysis with complete archive-hash verification and complete SQL table-count verification. It is not a claim that every proprietary method has been understood, that a GFA read already succeeded on the boiler, or that the pump/firmware questions are fully solved. Every further hardware result should be added with its raw capture and conditions rather than inferred from these source-only findings.
