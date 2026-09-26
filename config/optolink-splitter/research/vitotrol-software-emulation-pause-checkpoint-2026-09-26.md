# Vitotrol software-only emulation pause checkpoint — 2026-09-26

Status: **PAUSED — waiting for regulation-MCU / firmware evidence from Issue #25**

## Decision

The software-only Vitotrol/KM-BUS emulation track is intentionally paused.

No further live Vitotrol-state writes should be performed on the production
WB2A until the regulation-firmware research provides a new, source-backed
discriminator.

The required breakthrough is specifically an **Optolink-reachable firmware or
internal-state path**. The current research goal is not to replace Optolink with
an external programmer. External MCU documentation/programmers may be used as
reference material, but the preferred end state remains:

~~~text
Optolink
  -> documented/understood controller service or memory path
  -> internal Vitotrol/KM-BUS receive state
  -> software-only remote emulation
~~~

Tracking dependency: **GitHub Issue #25 — regulation MCU / firmware access**.

## Why this track is paused now

The exposed Vitosoft/Optolink layer has been searched deeply enough that further
blind probing has a poor evidence/risk ratio.

The current evidence rules out the simple forms of software emulation:

1. setting A0 alone does not emulate a Vitotrol;
2. ordinary Virtual_WRITE cannot set the effective room temperature at
   `0x0896`;
3. exact VDensHO1 RPCs expose no KM-BUS receive/mailbox injection;
4. production `KBUS_*` write families do not expose a source-backed raw
   Vitotrol slave-frame injection path for VDensHO1;
5. `KMBUS_RAM_READ 0x41` has no recovered symmetric write primitive;
6. `XRAM_WRITE 0x32` exists only as a function-code symbol with no production
   event definitions and no recovered local request shape;
7. cross-profile NRF aliases reveal useful internal architecture but do not
   provide a valid VDensHO1 write recipe.

The remaining problem is therefore no longer “which public Optolink datapoint
should be written?” but:

> Which internal firmware state transition is performed after a valid physical
> Vitotrol frame, and is that transition reachable through an undocumented
> Optolink service, monitor, memory or RPC path?

That question requires firmware/MCU evidence.

## Exact local target

Plant/controller:

~~~text
Viessmann Vitodens 200-W WB2A
profile        VDensHO1
identification 20C2
software pair  0103
production     permanent VS1/KW
~~~

The desired software-only result remains:

~~~text
A0 / 0x27A0 = Vitotrol 200 configured
remote participant remains alive
no current/persistent BC communication fault
0x0A5C becomes a meaningful remote software/index state
0x089C becomes valid/OK
0x0896 follows the injected room temperature
~~~

Room influence itself is not part of the initial protocol proof.

## Physical Vitotrol reference model

The physical KM-BUS work remains the behavioral oracle.

Known Vitotrol-200 reference:

~~~text
class      0x11
device ID  0x34
serial     00 05
slot       0x01
serial     1200 8E1
~~~

Relevant runtime traffic includes:

- F8..FB identity discovery;
- follow-up register reads including register `0x00`;
- master PING / slave PONG;
- `0xBF` data records;
- circuit-1 room-temperature record `0x20`;
- a still not fully reconstructed watchdog/rolling-state behavior.

The working public physical emulators prove that a valid Vitotrol is more than
a single room-temperature value. Identity, participant liveness and recurring
communication matter.

## Local A0 proof

Baseline:

~~~text
0x27A0 = 00
0x0A5C = 00000000
0x0896 = C800 = 20.0 °C fallback
0x089C = 03
~~~

Controlled experiment:

~~~text
0x27A0: 00 -> 01
~~~

Result:

- write/readback succeeded;
- `0x0A5C` remained zero;
- `0x0896` remained 20.0 °C;
- `0x089C` remained 03;
- controller generated `BC = Fehler Fernbedienung HK1`.

Rollback:

~~~text
0x27A0: 01 -> 00
~~~

The current alarm cleared.

Conclusion:

> A0 configures the expectation of a physical remote. It is not a software
> emulation switch.

## Exact VDensHO1 Vitosoft boundary

Relevant exact-profile objects:

| Address | Meaning | Access |
| --- | --- | --- |
| `0x27A0` | remote identification A1/M1 | Virtual_READ / Virtual_WRITE |
| `0x0A5C` | remote software index A1 | Virtual_READ |
| `0x0896` | room temperature A1/M1 | Virtual_READ |
| `0x089C` | room sensor status A1/M1 | Virtual_READ |
| `0x37A0` | remote identification M2 | Virtual_READ / Virtual_WRITE |
| `0x0A60` | remote software index M2 | Virtual_READ |
| `0x0898` | room temperature M2 | Virtual_READ |
| `0x089D` | room sensor status M2 | Virtual_READ |

The exact VDensHO1 profile contains no linked `KBUS_*` or `KMBUS_*` event
that represents a Vitotrol slave RX path.

### Exact VDensHO1 RPC result

The 22 exact-profile `Remote_Procedure_Call` events were enumerated.

They cover:

- reset/factory-setting operations;
- fault-history clear;
- LON participant-list read/clear around `0xA010`.

No exact VDensHO1 RPC was recovered for:

- KM-BUS remote registration;
- Vitotrol receive mailbox;
- raw slave-frame injection;
- remote watchdog refresh;
- room-temperature RX injection.

This path is closed unless firmware evidence exposes a hidden call.

## Cross-profile NRF findings

Vitosoft contains a coherent remote-state model on other controller families,
especially VBC550S, VBC550P and Ecotronic.

Relevant aliases include:

~~~text
0x0896 NRF_Raumtemperatur_M1
0x089C NRF_TemperaturFehler_RTS_M1
0x0A40 NRF_SWIndex_FB_M1
0x7341 NRF_BedienBDETyp_FBKK
0x7342 NRF_BedienBDETyp_FBM1
0x7343 NRF_BedienBDETyp_FBM2
~~~

Type encoding:

~~~text
0x34 = BDETYP_F2KK
0x38 = BDETYP_F3KK
0x74 = BDETYP_F2M1
0x78 = BDETYP_F3M1
0xB4 = BDETYP_F2M2
0xB8 = BDETYP_F3M2
~~~

The `0x34/0x38` bases match the independently reconstructed physical
Vitotrol-200/300 ID families. The additional `0x40/0x80` bits encode the
heating-circuit association in the NRF representation.

This is strong architectural evidence for a shared concept of:

~~~text
remote type
remote software/index
room sensor status
room actual value
participant/watchdog state
~~~

It is not proof that VDensHO1 uses the same numeric addresses internally.

## Local hidden-state experiments

### 0x7340..0x7344

The exact VDensHO1 Vitosoft profile has no event links for this block.

The real WB2A nevertheless returns:

~~~text
0x7340 = 21
0x7341 = 00
0x7342 = 00
0x7343 = FF
0x7344 = FF
~~~

All five addresses accepted same-value Virtual_WRITE requests.

A bounded test also proved:

~~~text
0x7342: 00 -> 74 -> 00
~~~

Both writes returned success and readback matched.

Immediate state remained unchanged:

~~~text
0x27A0
0x0A5C
0x0896
0x089C
current alarm
~~~

A later clean causality control held `0x7342=0x74` for one second, restored
`00`, and monitored current alarm plus newest fault-history slot for 77 s.

Result: **no new BC**.

Conclusion:

- the block is genuinely writable on the local firmware;
- `0x7342` is compatible with a remote-type representation;
- a one-second type change alone does not create a valid participant and does
  not reproduce the Vitotrol watchdog fault.

### 0x089C

Same-value write:

~~~text
0x089C = 03 -> accepted
~~~

Temporary sensor-OK write:

~~~text
0x089C: 03 -> 00
~~~

The request returned success, but the next read was again:

~~~text
0x089C = 03
~~~

The effective value is therefore regenerated/owned by internal controller
logic.

A clean isolated same-value write `0x089C=03` followed by 99 s monitoring
produced no new BC.

Conclusion:

> An Optolink Virtual_WRITE handler exists for the address, but ordinary
> Virtual_WRITE does not own the effective room-sensor state.

### 0x0896

Even a same-value write was rejected:

~~~text
Virtual_WRITE 0x0896 C800 -> rejected
~~~

The effective room actual value cannot currently be injected through ordinary
Virtual_WRITE on VDensHO1.

### 0x0A40

Rejected locally.

Cross-profile interpretation is also invalid for VDensHO1 because the same
numeric address is already used there as the solar-controller software-index
object.

### 0x75A2

Cross-profile NRF metadata uses this area for remote information, but on
VDensHO1 it is fault-history storage. It is an address-family collision, not a
hidden Vitotrol structure.

### 0x779C

Local value:

~~~text
0x779C = 0x14
~~~

This is the known LON receive-heartbeat configuration (20 decimal/minutes), not
the fast Vitotrol/KM-BUS communication watchdog.

## BC fault evidence

During the research session the fault history contained four BC entries:

~~~text
BC 2026-09-25 21:43:28
BC 2026-09-25 22:04:48
BC 2026-09-25 22:09:04
BC 2026-09-25 22:17:36
~~~

The first corresponds to the earlier A0 remote-expectation experiment.

The later entries occurred during hidden-state research, but the old splitter
journal did not contain a complete timestamped maintenance-command audit, so
strict one-to-one attribution is not claimed.

Important negative controls performed afterward:

- isolated `0x7342 00 -> 74 -> 00`, 1 s hold + 77 s observation:
  **no new BC**;
- isolated same-value `0x089C=03` + 99 s observation:
  **no new BC**.

As of the 2026-09-26 production verification, no additional BC entry had
appeared after `2026-09-25 22:17:36`.

## Production restore verification — 2026-09-26

Fresh read-only verification:

~~~text
0x27A0 = 00
0x7340 = 21
0x7341 = 00
0x7342 = 00
0x7343 = FF
0x0896 = C800
0x089C = 03
0x0A5C = 00000000
current alarm = clear
~~~

Newest fault-history entries remain the four BC records above.

Services:

~~~text
optolink-splitter.service        active
optolink-maintenance-api.service active
optolink-party-emulator.service  active
~~~

No Vitotrol experimental state remains enabled.

## Current architecture hypothesis

The most useful working model is:

~~~text
physical KM-BUS RX
      |
      v
frame validation / participant dispatch
      |
      +--> remote type / discovery state
      |       candidate class represented by 0x34/0x38 family
      |
      +--> participant alive / watchdog
      |
      +--> remote software/index state
      |
      +--> room-sensor-valid state
      |
      +--> decoded room actual value
              |
              v
         normal controller
         filtering/regulation
~~~

The software-only emulator must reproduce the **receive-side state transition**,
not merely overwrite one final datapoint.

## Firmware/MCU information required to reopen this track

The Vitotrol track should be resumed only when Issue #25 yields at least one of
the following.

### Reopen condition A — firmware image

A readable regulation-firmware image from the local/compatible MCU allows
static cross-reference work for:

~~~text
0x0896
0x089C
0x0A5C
0x27A0
0x7340..0x7344
BC fault path
KM-BUS RX parser
Vitotrol class 0x11
device IDs 0x34 / 0x38
record 0x20
commands 0x00 / 0x31 / 0x33 / 0x80 / 0xB1 / 0xB3 / 0xBF
~~~

The goal is to identify the actual internal handler that marks a remote alive
and commits room data.

### Reopen condition B — Optolink monitor/service path

Firmware or host research reveals an undocumented but exact request shape for
one of:

- MCU monitor read/write;
- bank/page memory access;
- internal service call;
- RX mailbox;
- participant-state injection;
- exact XRAM/working-RAM access;
- remote watchdog refresh.

The request must be sufficiently understood to make a bounded read-only or
reversible test.

### Reopen condition C — exact handler table

Firmware analysis identifies the VDensHO1 write/read dispatch table and explains
why:

~~~text
0x0896 write -> rejected
0x089C write -> accepted but regenerated
0x734x write -> accepted
~~~

That would give a concrete discriminator for the next Optolink experiment.

## What not to repeat while paused

Do not repeat:

- A0=1 alone;
- blind `0x0896` Virtual_WRITE;
- blind NRF cross-profile writes;
- guessed `KBUS_*` write function codes;
- guessed `XRAM_WRITE 0x32` shapes;
- arbitrary `0x56/0x5B/0x5E/0x62/0x66` writes;
- broad address sweeps;
- attempts to treat LON heartbeat `0x779C` as the Vitotrol watchdog.

These paths have either been directly tested, source-negatively bounded or
shown to belong to another subsystem.

## Next action

No additional live Vitotrol work is required now.

The next useful action belongs to the MCU/firmware track:

~~~text
prove regulation-MCU identity
        ->
find non-destructive firmware/monitor/read path
        ->
prefer Optolink-reachable path
        ->
obtain exact firmware/internal handler evidence
        ->
cross-reference Vitotrol receive state
        ->
return to bounded software-emulation experiments
~~~

Until one of the reopen conditions above is met, this document is the
authoritative pause checkpoint for the software-only Vitotrol investigation.

## Related evidence

- `config/optolink-splitter/research/vitotrol-software-emulation-deep-dive-2026-09-25.md`
- `config/optolink-splitter/research/vitotrol-kmbus-wire-protocol.md`
- `config/optolink-splitter/research/vitotrol-kbus-optolink-emulation.md`
- `config/optolink-splitter/research/kmbus-optolink-research.md`
- `config/optolink-splitter/research/vitosoft/kbus-write-function-analysis.md`
- `config/optolink-splitter/research/vitosoft/vitotrol-baseline-2026-09-23.md`
- GitHub Issue #25 — regulation MCU / firmware
- GitHub Issue #30 — KM-BUS read research
