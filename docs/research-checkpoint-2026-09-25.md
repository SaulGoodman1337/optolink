# WB2A research checkpoint - 2026-09-25

Purpose: **current handoff checkpoint for the WB2A research**. This file does not replace
`docs/research-plan-2026-09-24.md`; it consolidates the latest verified state,
including the 2026-09-25 KMBUS/Physical_READ discriminator and the safe remote-access
workflow.

## Update through 2026-09-25 10:00 CEST

### Production transport and remote-access baseline

The production Optolink path remains intentionally **permanent VS1/KW**:

- `vs1protocol = True`;
- `port_vitoconnect = None`;
- `port_optolink = /dev/serial/by-id/usb-Silicon_Labs_CP2102_USB_to_UART_Bridge_Controller_0001-if00-port0`;
- serial resolves to `/dev/ttyUSB0`;
- current global `olbreath = 0.025 s`;
- normal datapoints are served through the production splitter while GFA access uses the
  validated permanent-VS1 integration.

Remote Desktop Commander access to the LXC is working. The remote account is
`chatgpt-admin`; root access is deliberately restricted through exact sudo allowlists.
Do not broaden sudo rules merely for convenience. Read-only status checks can be executed
directly; privileged maintenance commands must stay within the existing allowlist.

After the latest test/recovery, the following services were verified active:

- `optolink-splitter.service`;
- `optolink-party-emulator.service`;
- `optolink-maintenance-api.service`;
- `optolink-schedule-manager.service`.

The schedule manager had to be restarted manually after the first revision of the new
P300 helper; this is fixed in helper v1.0.2.

### PrefixRead / 0x43 host serializer - closed

The earlier assumption that Vitosoft serializes
`PrefixRead=030000000101` as trailing request data for ordinary
`KMBUS_EEPROM_READ / 0x43` is rejected for the captured Vitosoft-v6 build.

Recovered `vsmInterfaceCore.dll` behavior:

- `PrefixRead` and `PrefixWrite` are real first-class EventType metadata;
- `RPCConverter.ConvertRpcToDevice_Default()` copies `PrefixRead` into
  `BlockDataToDevice` only for `Remote_Procedure_Call / FCRead 0x07`;
- ordinary non-RPC reads do not execute this conversion;
- the normal `0x43 / 0x0001 / len 1` request is therefore:
  `41 05 00 43 00 01 01 4A`;
- the six-byte prefix must not be manually appended to standard P300 0x43 reads.

The catalog provenance also matters:

- 90/91 KMBUS_EEPROM_READ rows carry `030000000101`;
- all 90 are linked only to GWG-family profiles;
- the single no-prefix KMBUS_EEPROM row belongs to DEKATEL/VCOM;
- **no KMBUS_EEPROM_READ event belongs to VDensHO1**.

Historical GWG implementations use numeric type `0x43` in a different, 8-bit-address
wire protocol. The identical numeric byte does not justify transferring GWG/LGM27
semantics onto local P300/VS2 command 0x43.

Private serializer reports/workflows:

- `collector-output/20260924-143439/prefixread-serializer-deep-dive.md`;
- workflow commit `d79475d9d955a129bef5d9bbb16755f8988486e7`;
- successful run `36107129749`;
- artifact `10852220322`;
- report commit `f55cf2257d70a46e0bca92fd532b4693fd1c7fab`.

### 0x43 response handling - controller bytes, not host artifacts

The Vitosoft response path has also been recovered.

For normal LDAP responses the host strips the five-byte LDAP header, copies the remaining
payload directly into `BlockDataFromDevice/DataFromDevice`, then applies only the normal
event conversion metadata. Therefore repeated/dynamic words such as:

- `5498`;
- `5497`;
- `d301`;
- `f201`;
- low values such as `81`, `87`, `88`;

are raw controller-produced payloads, not synthesized by a host-side KMBUS EEPROM decoder.

The response converter groups command bytes by their low five bits:

~~~text
0x41 & 0x1F = 0x01
0x43 & 0x1F = 0x03
~~~

This does not prove controller-side aliases, but it supplied a precise same-address
hardware discriminator.

Private response report:

`collector-output/20260924-143439/kmbus-eeprom-response-analysis-2026-09-25.md`

commit: `9bdb2b8019a5c4684fb36dc28f896903ab4eeab7`.

### vsmGWG99Native.dll - recognition helper, not a recovered generic KMBUS reader

All archived GWG99 native DLLs were inspected. The x64/x86 builds export only:

- `CheckGWG`;
- `TestCall_GWG99Native`.

They import the expected Windows serial APIs and contain detector/test-style strings such
as `checking gwg...`, `receive ENQ` and `WriteData OK`, but no exported general
GWG/KMBUS datapoint API was recovered.

Workflow:

- `.github/workflows/gwg99-native-inspect.yml`;
- commit `4bb3add3b06043d7fb8c3f077684292a14891761`;
- successful run `36108141163`;
- artifact `10851988021`.

### New bounded live discriminator: 0x03 Physical_READ vs 0x43

A dedicated fixed-allowlist read-only helper was created:

`config/optolink-splitter/wb2a-physical-vs-kmbus-eeprom-probe.py`

Initial helper commit:
`48e77885ce0c9fc0a864cf46465c895828701192`

Updater integration:
`de2d8ab08aa740735366a3eae697822bd5ad5484`

The live run was performed with helper v1.0.0 at:

`/root/wb2a-physical-vs-kmbus-eeprom-20260925-095756-217850.log`

Safety constraints were met:

- read-only;
- fixed address/function allowlist;
- no broad scan;
- no writes;
- fresh P300 session per sample;
- positive 20C2 identity control first;
- splitter and Party restored;
- `VS1/KW protocol initialized` seen after restore.

Identity control:

~~~text
0x01 / 0x00F8 / 8
-> 20 c2 00 03 00 00 01 03
PASS
~~~

#### Positive control: 0x01 vs 0x41 at 0x00F8/2

~~~text
0x01 -> 20c2
0x41 -> 20c2
0x41 -> 20c2
0x01 -> 20c2
~~~

Correct semantic classification: **STABLE_SAME**.

This reconfirms the already proven `0x01 / 0x41` mirrored behavior.

#### 0x03 vs 0x43 at 0x00F8/2

~~~text
0x03 -> 5491
0x43 -> 5491
0x43 -> 5491
0x03 -> 5497
~~~

Classification: **DYNAMIC_OR_INCONCLUSIVE**.

Important consequence: the same dynamic two-byte family previously considered peculiar to
0x43 is also produced by ordinary `Physical_READ 0x03`.

#### 0x03 vs 0x43 at 0x0001/1

~~~text
0x03 -> 81
0x43 -> 81
0x43 -> 81
0x03 -> 81
~~~

Correct semantic classification: **STABLE_SAME**.

At these bounded samples, 0x43 did not expose a distinct local view from 0x03.
The current working hypothesis is therefore a common/aliased local
physical/service view. **Universal equivalence remains unproven.**

Do not interpret this as LGM27 EEPROM access, and do not start a broad 0x43 scan.

Evidence:

`config/optolink-splitter/research/vitosoft/physical-vs-kmbus-eeprom-2026-09-25-evidence.json`

commit:
`fb5fb0280726a7a61e52d606028ec4377717608c`.

### Probe corrections discovered during the run

The raw live data are valid, but helper v1.0.0 had a **reporting bug**:
its equality key included the echoed response command byte. Therefore a
payload-identical `0x01` versus `0x41` or `0x03` versus `0x43` pair was
misreported as `STABLE_DISTINCT`.

v1.0.1 fixes that classifier and adds an explicit regression test.

Commit:
`3391e21f9a8179e9773d1760ee408a264d97bc9d`

Offline self-test after correction:

`PHYSICAL_VS_KMBUS_EEPROM_PROBE_TESTS=6/6`.

A second operational issue was found: the original helper stopped splitter/Party but did
not preserve `optolink-schedule-manager.service`. During the maintenance window the
schedule manager exited and was found inactive afterward. It was manually restarted and
verified listening on 21 guarded schedule topics.

v1.0.2 now explicitly stops/restores the schedule manager with the maintenance window.

Commit:
`3c1e37e79a628fce4c1ed0ed9683ba01fbf46ad9`.

**Important operational note:** the live run itself used v1.0.0. Before this helper is ever
used again on the container, run the normal `update` path so the installed production copy
is refreshed to v1.0.2 or later, then run `--self-test` first.

### Current KM-BUS conclusions

1. `0x41 KMBUS_RAM_READ` is genuinely implemented on local 20C2.
2. At the tested logical addresses, 0x41 mirrors `Virtual_READ 0x01`, including dynamic
   pump objects.
3. The dynamic pump capture directly showed:
   - A1 request `0x7663[1] = 30%`;
   - final/internal command `0x0A3C = 50%`;
   - physical internal pump `0x7660[1] = 50%`.
4. This remains strong evidence for the known GWG75=50% minimum-pump clamp, though a strict
   same-window E7+GWG75 causality capture is optional.
5. Source-derived `XRAM_READ 0x31` shapes were rejected 0/6 on local VDensHO1; do not
   blind-scan XRAM.
6. `PrefixRead` is not a generic non-RPC read serializer in this Vitosoft build.
7. Local P300 `0x43` is implemented, but no dedicated LGM27 EEPROM view has been
   demonstrated.
8. The latest bounded 0x03/0x43 evidence favors a common/aliased local physical/service
   view.
9. No further live 0x43 work is justified without a new source-backed discriminator.

Public documentation commits for this closure:

- KBus read-memory analysis:
  `df4d85a245bf85f14b4c26cac2706a02e7848f8d`;
- canonical KM-BUS research:
  `53c6a552cddd7b8cb8a9593eef55b74ef9be4e66`;
- issue #30 latest discriminator comment id:
  `5829107798`.

### Highest-value next actions

Do **not** continue generic 0x43 experimentation.

Priority order:

1. if coding-plug hardware is available, continue the side-labelled dual-EEPROM capture
   described below;
2. photograph the actual installed WB2A regulation board and identify the local MCU before
   transferring any M16C/VBC130 assumption;
3. continue passive/firmware-side work on the hidden pump selector upstream of
   `0x0A3C`;
4. only return to KM-BUS/P300 extended read families when a new source-derived request
   discriminator exists;
5. keep all bus research read-only and preserve the permanent VS1 production path.


## State at end of 2026-09-24

### LON/HCC/DHWC path - closed locally

The local LON setpoint path is now resolved sufficiently for this appliance:

- `A401/A403/A441/A443 = 20.00 C`;
- Viessmann LON semantics identify 20 C as the HCC nvi fallback/default value;
- `A3C0 = 50.00 C` is not a direct mirror of either local DHW target representation;
- `A400 = FF`, `A440 = FF`, `A3C2 = FF`;
- all three ApplicMode values are `HVAC_NUL`.

Conclusion: HCC1/HCC2/DHWC LON nvi setpoint values are **not authoritative** on the local
controller. Do not expose them in Home Assistant as active local setpoints.

### GFA P84/P87 flame correlation - current state

The permanent-production-VS1 compatibility issue is fixed.

The first real mixed flame-correlation run using v1.0.1:

- verified P300 identity `20C2`;
- verified burner-off precondition `0x55DC=0`;
- verified two independent P80 reads `20/20`;
- captured original `0x2306=21 C`;
- temporarily wrote only `0x2306=37 C`;
- verified the write by readback;
- acquired 32 complete mixed rounds;
- every complete round remained:
  - `P84=00`;
  - `P87=00`;
  - `0x55D3 flame=0`;
  - `0x55DD flame=0`;
  - lockout=0;
  - fine GFA control value=0;
- attempt 33 returned a quarantined raw `FF` at P87;
- exact original setpoint 21 C was restored by readback;
- P300 and services were restored successfully.

This is a **null startup observation**, not a failed heater start. The same 37 C room-setpoint
stimulus had produced a real controller-driven startup earlier in the day, so `0x2306=37`
is now explicitly classified as a **heating-demand stimulus, not a direct burner command**.

v1.0.2 fixes the mixed child so a sporadic GFA `FF`:

1. rejects only the current round;
2. records a quality gap;
3. performs the existing bounded P300/P80 re-identification;
4. clears transition history across the gap;
5. continues only when the inherited safety/time policy permits;
6. reports `STARTUP_ACTIVITY_SEEN=yes|no`.

No trigger/write/restore or burner-safety boundary was loosened.

Evidence:
- `docs/gfa-flame-correlation.md`;
- `config/optolink-splitter/research/vitosoft/gfa-flame-correlation-null-run-2026-09-24-evidence.json`;
- corrected helper: `config/optolink-splitter/wb2a-gfa-flame-correlation-probe.py`.

### Pump/topology state

Current installed topology remains consistent:

- internal KM-BUS pump identity block `0x0A54 = 01 11 01 01`;
- separate A1 pump block `0x0A4C = 00 00 00 00`;
- M2 pump block `0x0A50 = 00 00 00 00`;
- `E5=0`;
- `0x0A3C` is the verified final internal-pump command shadow;
- hidden arbitration upstream of `0x0A3C` remains a controller-firmware/MCU problem.

E9 provenance is closed: the current `E9=100%` was intentionally configured by the user.

## Priority 1 - new EEPROM reader: side-labelled coding-plug capture

The replacement EEPROM reader/programmer is expected on 2026-09-25. Resume physical
coding-plug research only when the new reader is available.

### First capture: both EEPROMs of the SAME spare plug

Explicit physical labels:

- **f01 / SIM1 / ST 24C04W6**;
- **f02 / SIM2 / Microchip 24LC04B**.

Read each side three times without changing the clip between repeat reads.

Recommended filenames:

```text
spare-1-f01-st-read1.bin
spare-1-f01-st-read2.bin
spare-1-f01-st-read3.bin
spare-1-f02-microchip-read1.bin
spare-1-f02-microchip-read2.bin
spare-1-f02-microchip-read3.bin
```

Acceptance before semantic analysis:

- each file must be 512 bytes;
- all three reads of the same EEPROM must hash identically;
- record SHA256 values;
- compare f01 versus f02 of the same physical plug before moving to another plug.

Do not write either EEPROM.

### Then

1. second spare if practical;
2. active plug **last**;
3. boiler unpowered / plug disconnected during active-plug bench read;
4. immediately before or after active-plug capture, snapshot the software-visible coding-plug views:
   - `0x1010`;
   - `0x1020`;
   - `0x1030..0x10C0`;
   - `0x7656`;
   - GFA P90 and P100..P108.

Compare semantic vectors, complement pairs, duplicated records and CRC/integrity patterns rather
than requiring a flat byte-for-byte P300-object match.

## Priority 2 - regulation-board photographs

Photograph the installed WB2A regulation board for firmware/MCU research.

Follow `docs/regulation-board-photo-capture.md`.

Highest-value evidence:

- full board overview;
- PCB part/revision labels;
- both sides where safely accessible;
- main MCU complete marking;
- external EEPROM/flash/SRAM markings;
- oscillator/crystal markings;
- X15;
- X10;
- X3 / 145 KM-BUS area;
- daughterboard;
- burner/GFA-side controller and memory where visible.

Do **not** electrically probe unknown pads yet. First determine the exact local MCU family and
board revision from photographs.

## Priority 3 - flame correlation only when a real burner start is likely

Do not repeatedly write the 37 C stimulus while the controller is clearly thermally satisfied.

First perform a passive readiness snapshot:

```bash
echo "=== Burner-start readiness ==="
/usr/local/bin/optolink-debug request "r;0x55DC;1;raw;False"
/usr/local/bin/optolink-debug request "r;0x2544;2;raw;False"
/usr/local/bin/optolink-debug request "r;0x555A;2;raw;False"
/usr/local/bin/optolink-debug request "r;0x0810;2;raw;False"
/usr/local/bin/optolink-debug request "r;0x7663;2;raw;False"
/usr/local/bin/optolink-debug request "r;0x0A3C;1;raw;False"
```

Useful context:

- `0x55DC`: current burner/modulation state;
- `0x2544`: A1 flow target;
- `0x555A`: effective boiler target;
- `0x0810`: boiler actual temperature;
- `0x7663`: A1 pump/runtime request;
- `0x0A3C`: final internal-pump command.

Only rerun the mixed flame logger when there is a plausible heating demand while the burner is
still off. Use v1.0.2 or later, run its full offline self-test first, and retain both LOG and JSONL.

Target correlation remains:

```text
P84 raw transition
    |
0x55D3 flame
    |
P87 raw / bit transition
    |
0x55DD independent flame signal
```

Do not assign manufacturer names to P84 states or P87 bits solely from temporal proximity.

## KM-BUS update - bounded 0x5F gate completed

On 2026-09-25 10:32 CEST the guarded `KBUS_VIRTUAL_READ / 0x5F`
semantic gate was executed against two source-backed temperature anchors.

Results:

- `0x5F / 0x2508 / 1` (source: outside temperature) -> Error Message `05`, twice;
- `0x5F / 0x2D08 / 1` (source: A1 flow actual) -> Error Message `05`, twice;
- ordinary VDensHO1 controls were stable before/after each pair:
  - `0x5525 = 94 00` -> 14.8 C;
  - `0x0810 = 0d 02` -> 52.5 C;
- identity control `0x00F8/8 = 20c2000300000103` passed;
- classification:
  `NO_LOCAL_KBUS_VIRTUAL_SUCCESS_ON_TESTED_ANCHORS`;
- all four production services were restored active and permanent VS1 was
  confirmed after the run.

This does not prove universal 0x5F rejection. It closes broad 0x5F live
expansion until a new VDensHO1-specific discriminator or stronger source
evidence exists.

Evidence:
`config/optolink-splitter/research/vitosoft/kbus-virtual-read-live-2026-09-25-evidence.json`

Relevant commits:

- helper: `22ab617559cc70dcd21b1f5b1309a2bcbd3f9265`
- updater: `34d5f395c70b52049e01882e1479cf7c56d860c1`
- evidence: `157e7a514d516c227d2f2e1595041d6285da9f29`
- detailed read-memory note: `add661a711089951c76e4d1e5f23e88a99692f2d`
- canonical KM-BUS note: `bd1e3124a4c0f9cd88a92d38bf45c849cb8abf76`

## KM-BUS update - bounded 0x5D member-list gate completed

The only source-defined `KBUS_MEMBERLIST_READ` shape was also tested on
2026-09-25:

- Vitosoft event 2756: `0x5D / 0x0000 / 3`, empty PrefixRead,
  "Teilnehmer 00 am Viessmann-2-Draht-BUS";
- source membership is legacy DEKATEL/VCOM300, not VDensHO1;
- three fresh-session trials all returned the identical Error Message
  `41 06 03 5d 00 00 01 05 6c`;
- classification: `STABLE_ERROR_RESPONSE`;
- pre/post identity controls both returned `20c2000300000103`;
- all four production services and permanent VS1 were restored and verified.

The error payload `05` is now also observed in the bounded 0x31, 0x5F and
0x5D source-shaped failures. Its semantic meaning remains unknown.

Decision: no further 0x5D live expansion unless VDensHO1-specific source
evidence appears.

Evidence:
`config/optolink-splitter/research/vitosoft/kbus-memberlist-read-live-2026-09-25-evidence.json`

Relevant commits:

- live helper: `3df1a6cdfabe5f668e940432d4a1090c74fbb1c6`
- fixture correction: `c0c8e4a5f5ff1c3742d1e056f2718f53ff2aa518`
- updater integration: `2c58ad97c69cb91a362ce891961a8e242dbbcdc6`
- current evidence: `8f350a34cb22207ad13fbf83a211692d8909ca20`
- detailed analysis: `5ced606816eeca051036db35c03b9d3639afb056`
- canonical KM-BUS update: `7ffcfaa3292541ab318e3c41a8193b4f6ef96ea3`

## Priority 4 - remaining firmware/KM-BUS work

After the physical evidence above:

- continue controller-firmware architecture once local board/MCU identity is known;
- keep regulation firmware, GFA firmware and coding-plug EEPROM as separate domains;
- continue the KMBUS read-memory work only from known source-derived request structures;
- no broad blind reads and no KBUS/KMBUS writes.

## Session completion checklist

Before ending the next session:

- [ ] commit hashes and evidence paths recorded;
- [ ] EEPROM side/vendor labels preserved in filenames;
- [ ] SHA256 repeatability recorded;
- [ ] regulation-board photos indexed by visible component/connector;
- [ ] any flame-correlation run classified as STARTUP_ACTIVITY_SEEN yes/no;
- [ ] no unresolved temporary setpoint remains;
- [ ] production splitter/services confirmed running.
