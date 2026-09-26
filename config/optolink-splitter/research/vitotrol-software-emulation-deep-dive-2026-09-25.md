# Vitotrol software-only emulation deep dive — 2026-09-25

Status: **PAUSED on 2026-09-26 — waiting for regulation-MCU / firmware evidence from Issue #25**


> **Pause checkpoint:** Further live Vitotrol-state probing is intentionally suspended. See [vitotrol-software-emulation-pause-checkpoint-2026-09-26.md](vitotrol-software-emulation-pause-checkpoint-2026-09-26.md) for the verified local restore state, closed hypotheses, firmware reopen criteria and the exact dependency on the MCU/firmware track.

## Objective

Determine whether the local **Vitodens 200-W WB2A / VDensHO1 / 20C2** can be
made to behave as if a Vitotrol 200 is attached **without an additional
physical KM-BUS interface**.

The target is a software service running beside the existing Optolink-Splitter
that supplies a Home Assistant room-temperature value to the controller and
causes the normal VDensHO1 remote-control state to become valid.

This document deliberately distinguishes:

1. **true Vitotrol emulation** — the controller believes a remote participant
   exists and its normal room-sensor state is populated;
2. **functional substitution** — external software changes writable setpoints
   to approximate room influence without creating a Vitotrol participant.

Only (1) is called emulation here.

## Local acceptance criteria

A software-only emulator is considered proven only if all of the following can
be demonstrated on the local controller:

- `0x27A0 = 1` for A1/M1 Vitotrol 200;
- no persistent/current `BC = Fehler Fernbedienung HK1`;
- `0x0A5C` changes from the absent-remote zero state to a meaningful remote
  software/index state, or another source-backed identity state proves the same
  participant;
- `0x089C` changes to a valid room-sensor state;
- `0x0896` follows at least three deliberately injected test temperatures;
- stopping the emulator causes a bounded, understood fallback;
- rollback to `0x27A0 = 0` restores the clean no-remote state.

Room influence `B0` must remain disabled during initial proof. The first goal
is communication/state validity, not closed-loop heating control.

## Verified local baseline

The local absent-remote state is:

~~~text
0x27A0 = 00          no A1/M1 remote configured
0x0A5C = 00000000    no remote software-index state
0x0896 = C800        20.0 °C fallback
0x089C = 03          room-sensor status unknown
~~~

A controlled hardware test changed only:

~~~text
0x27A0: 00 -> 01 -> 00
~~~

The controller accepted/read back `01`, but the software index, room
temperature and sensor status did not become valid. Instead the current alarm
became:

~~~text
BC = Fehler Fernbedienung HK1
~~~

Rollback to `0x27A0 = 00` cleared the current alarm. Therefore A0 is an
**expected-device configuration**, not a software emulation switch.

## What a physical Vitotrol actually does

Two independent community implementations provide a working physical reference:

- `dumpfheimer/WiFiVitotrol`;
- `boblegal31/Heater-remote`.

The current WiFiVitotrol project remains active in 2026. Its source and recent
WB2B test reports confirm the following transport model.

### Physical layer

~~~text
1200 baud
8 data bits
even parity
1 stop bit
KM-BUS / M-Bus electrical layer
controller = master
Vitotrol = current-modulating slave
~~~

### Vitotrol 200 identity used by the working emulator

~~~text
device class = 0x11
device ID    = 0x34
serial bytes = 00 05
slot         = 0x01
~~~

These identity bytes were found experimentally by the WiFiVitotrol author, not
from an official Viessmann protocol specification.

### Discovery

A captured slot-1 request is:

~~~text
11 00 33 0A 01 01 F8 04 49 EF
~~~

A typical Vitotrol-200 response supplies address/value pairs for F8..FB.

Recent public WB2B logs additionally show that after F8..FB discovery the
controller can request register `0x00` with command `0x31`.

### Runtime

The master periodically sends PING:

~~~text
11 00 00 08 01 01 08 88
~~~

The slave normally returns PONG:

~~~text
00 11 80 08 01 01 F9 5C
~~~

When data is pending, the slave uses the PING response opportunity to return a
record instead.

Current-room-temperature for circuit 1 is a `0xBF` record using record
`0x20`. The temperature is tenths of a degree; data bytes are XORed with
`0xAA`.

The current WiFiVitotrol implementation schedules room temperature roughly
every 30 seconds and deliberately stops answering the heater if its upstream
room-temperature source becomes stale. This is a useful safety model for any
software-only implementation.

### Important unresolved physical-protocol detail

Recent 2025/2026 WiFiVitotrol field reports show generally working operation on
a Vitodens WB2B, but intermittent `BC` communication faults can remain. The
project author notes that an original Vitotrol appears to have a small
"rolling-code" or rolling-state detail which may not be fully implemented.

Consequences:

- identity + PING/PONG + room-temperature record is sufficient for substantial
  interoperability, but may not be the complete watchdog/state machine;
- software-only work must not assume that writing a single room-temperature
  value is equivalent to satisfying the controller's remote-participant
  watchdog.

## Vitosoft v6 evidence

Canonical source asset:

~~~text
vitosoft-private-archive-20260924-143439.7z
SHA256 3d31380d6dfabf8ede9e305b115e847fb0670511e253a4ed4e59feef2f7adfee
~~~

A new targeted extraction was executed as workflow run `36176658272`,
artifact `10882772275`, digest
`sha256:32729502c319d26ab260c53dfc4eb3c734c7a02ae25b2845e309beb79cd883e5`.

The extraction searched the exact VDensHO1 event set, the all-device low-level
catalog, managed-member/PE-string indices and relevant IL for room/remote,
RPC, receive/mailbox and KBus/KM-BUS paths.

### Exact VDensHO1 event boundary

The exact local profile has 581 joined events. Relevant normal objects include:

| Object | Address | VDensHO1 access |
| --- | ---: | --- |
| Remote identification A1/M1 | `0x27A0` | Virtual_READ / Virtual_WRITE |
| Remote SW index A1 | `0x0A5C` | Virtual_READ only |
| Room temperature A1/M1 | `0x0896` | Virtual_READ only |
| Room sensor status A1/M1 | `0x089C` | Virtual_READ only |
| Remote identification M2 | `0x37A0` | Virtual_READ / Virtual_WRITE |
| Remote SW index M2 | `0x0A60` | Virtual_READ only |
| Room temperature M2 | `0x0898` | Virtual_READ only |
| Room sensor status M2 | `0x089D` | Virtual_READ only |

The exact VDensHO1 profile contains **no KBUS_* or KMBUS_* event**.

### The 22 exact VDensHO1 RPC events

The targeted extraction confirms that the exact-profile
`Remote_Procedure_Call` events are limited to these semantic groups:

- reset/factory-setting operations;
- fault-history clear;
- **LON** subscriber list at `0xA010`, including subscriber entries 00..15;
- LON subscriber-list clear.

This is an important architectural clue but **not a Vitotrol path**.

Vitosoft demonstrably has a concept of a controller-managed participant list
accessed by RPC, but the recovered exact-profile implementation is the LON
participant list. No corresponding exact VDensHO1 RPC for KM-BUS remote
registration or Vitotrol RX injection was recovered.

### Extended KBus write families do not look like raw Vitotrol injection

Production Vitosoft contains:

~~~text
KBUS_TRANSPARENT_WRITE   853 events, all application BlockLength 1
KBUS_DIRECT_WRITE         11 events, VCOM300/DEKATEL channel records
KBUS_MEMBERLIST_WRITE      2 events, gateway participant management
KBUS_GATEWAY_WRITE         1 event, gateway control
KBUS_VIRTUAL_WRITE       124 events, one-byte datapoint access
KBUS_INDIRECT_WRITE       97 events, indexed participant/channel access
KBUS_CONTROL_WRITE         0 event definitions
~~~

None is linked to VDensHO1.

A complete physical Vitotrol response is 8–16 bytes and contains
class/command/slot/protocol state/CRC. The Vitosoft write shapes above do not
provide source evidence for "inject this raw slave telegram into the local
KM-BUS receive path".

### KMBUS/XRAM symmetry does not provide a write path

Locally useful `0x41 KMBUS_RAM_READ` mirrors known controller values, but the
production catalog provides no source-backed `KMBUS_RAM_WRITE` counterpart.

Likewise, `KMBUS_EEPROM_READ` has no source-backed symmetric write event.

`XRAM_WRITE / 0x32` exists as a function-code enum symbol, but the production
event inventory contains **zero XRAM_WRITE event definitions**. Furthermore all
six source-derived XRAM_READ request shapes were already rejected by the local
VDensHO1 with error payload `05`.

Therefore none of these may currently be treated as a safe software injection
primitive.

## Cross-profile NRF remote-state metadata — corrected interpretation

The global production catalog contains a coherent set of NRF remote-state
events on VBC550S, VBC550P and Ecotronic, including:

~~~text
0x0896 NRF_Raumtemperatur_M1
0x089C NRF_TemperaturFehler_RTS_M1
0x0A40 NRF_SWIndex_FB_M1
0x7341 NRF_BedienBDETyp_FBKK
0x7342 NRF_BedienBDETyp_FBM1
0x7343 NRF_BedienBDETyp_FBM2
~~~

Their access metadata has an important two-layer structure:

~~~text
FCRead     = Virtual_READ
FCWrite    = Virtual_WRITE
AccessMode = Read
~~~

This **corrects the earlier interpretation** that `FCWrite=Virtual_WRITE`
proved a supported software-injection API. It does not.

Across the complete v6 event catalog there are **185** events with
`AccessMode=Read` plus `FCWrite=Virtual_WRITE`, and 229 read-only events with
some defined write function. Therefore a populated `FCWrite` on a read-only
event is a common lower-level metadata pattern and cannot by itself establish
that Vitosoft intentionally writes that datapoint.

An independent 2026 implementation,
`SoulSolistice/esphome_vitohome`, generated from Vitosoft exports reaches the
same practical interpretation: the NRF room value, sensor status, software
index and BDE type are emitted as read-only sensor entities despite the
underlying FCWrite field.

### What the NRF metadata still proves

The NRF controller family exposes a coherent internal representation for
remote-controller state at the addresses above, and the type encoding is highly
specific:

~~~text
0x34 = BDETYP_F2KK
0x38 = BDETYP_F3KK
0x74 = BDETYP_F2M1
0x78 = BDETYP_F3M1
0xB4 = BDETYP_F2M2
0xB8 = BDETYP_F3M2
~~~

The `0x34/0x38` base values match the independently reconstructed physical
Vitotrol-200/300 device-ID families, while `+0x40` and `+0x80` encode M1
and M2 in the NRF representation. This is strong evidence that
`0x7341..0x7343` are genuine remote-type runtime state in that firmware
family.

It does **not** prove that these numeric addresses have the same ownership or
semantics on VDensHO1. Several direct cross-profile collisions have already
been demonstrated:

- `0x0A40`: NRF remote software index, but VDensHO1 solar-controller software
  index;
- `0x75A2`: NRF remote-info block, but VDensHO1 fault-history storage;
- `0x778E`: NRF `KonfiKennungCS_RFB`, but VDensHO1 GWG EEPROM/I2C error flag;
- `0x779C`: receive-heartbeat configuration associated with LON supervision,
  not a fast Vitotrol/KM-BUS watchdog.

The NRF model is therefore a **firmware-family comparison oracle**, not a
write recipe for the WB2A.

### Local discriminator results

On the real VDensHO1/WB2A:

- ordinary `Virtual_WRITE 0x0896` is rejected, including a same-value write;
- ordinary `Virtual_WRITE 0x0A40` is rejected;
- `0x089C` accepts a write response but its effective value is immediately
  regenerated by controller logic;
- `0x7340..0x7344` accept writes, but a one-second
  `0x7342: 00 -> 74 -> 00` experiment followed by 77 seconds of observation
  produced no new BC fault;
- sensor-status control addresses outside the room path also accept same-value
  writes, so `0x089C` write acceptance is not Vitotrol-specific.

The current evidence therefore does **not** support implementing a software
Vitotrol by directly writing the NRF addresses.

### Why this lead remains useful

This alias gives a concrete firmware-research discriminator:

> Find why the NRF profile enables Virtual_WRITE at 0x0896 while VDensHO1
> rejects it.

Potential explanations include:

1. different firmware handler table / access permissions;
2. same storage location with profile-specific write gating;
3. address aliasing to different internal variables;
4. a build/family-specific software-injected room sensor path.

A future regulation-firmware dump can search specifically for the handler for
`0x0896`, its write-access table and cross-reference to the KM-BUS remote
receive routine.

## Candidate software-only paths

### Candidate A — hidden writable room-state path

**Priority: highest**

Goal: find a source-backed method that updates the same internal state as
physical Vitotrol receive processing.

Targets:

- measured room value corresponding to `0x0896`;
- room-sensor-valid state corresponding to `0x089C`;
- remote software/index state corresponding to `0x0A5C`;
- participant/watchdog timestamp or alive state that suppresses BC.

Evidence needed before a live test:

- exact VDensHO1 firmware handler or service function;
- or another exact-profile event/RPC/alias that demonstrably writes the state.

The newly found NRF writable alias is the first concrete cross-profile lead.

### Candidate B — exact VDensHO1 RPC injection

**Priority: currently closed unless new firmware evidence appears**

The 22 exact RPC events have now been enumerated. They do not expose a
Vitotrol/KM-BUS receive mailbox.

The LON `0xA010` participant-list RPC is useful architecture evidence, but
must not be repurposed as KM-BUS.

### Candidate C — legacy KBUS raw/slave injection

**Priority: source-negative**

`0x56/0x62/0x66/0x5E/0x60/0x64` are defined for legacy/gateway datapoint or
channel operations. No recovered request shape maps to a complete Vitotrol
slave telegram on VDensHO1.

Do not blind-probe these writes on the live boiler.

### Candidate D — hidden XRAM/KMBUS write

**Priority: low / firmware dependent**

There is no production event format for `XRAM_WRITE`, no source-backed
KMBUS-RAM write equivalent, and the local XRAM_READ shapes already reject.

Only reopen this path if firmware analysis yields an exact function, address
and argument format.

### Candidate E — firmware-level virtual participant

**Priority: medium after a regulation firmware dump exists**

If no pre-existing Optolink injection primitive exists, the controller firmware
could theoretically be modified to create a virtual remote participant or to
expose a controlled service hook.

Research target:

~~~text
KM-BUS RX ISR/task
  -> frame validation
  -> class/slot/identity dispatch
  -> remote watchdog/alive state
  -> room-temperature decoding
  -> 0x0896 / 0x089C / 0x0A5C state update
~~~

A firmware patch is **not** a production experiment. Any such work belongs on
replacement/sacrificial hardware first.

## Proposed daemon if an injection primitive is found

Working name: `vitotrol-virtuald`.

It should not open the optical serial device independently. It should use the
existing single-owner Optolink-Splitter transport.

### Inputs

- Home Assistant/MQTT current room temperature;
- optional desired room setpoint;
- explicit enable switch;
- source freshness timestamp.

### Internal state

~~~text
DISABLED
  -> PRECHECK
  -> INJECTION_READY
  -> ARM_REMOTE
  -> VERIFY_IDENTITY
  -> ACTIVE
  -> DEGRADED
  -> ROLLBACK
~~~

### PRECHECK

Verify:

- current A0 baseline;
- current BC/BD alarm state;
- `0x0A5C`, `0x0896`, `0x089C`;
- current room-temperature source freshness;
- room influence B0 remains disabled.

### INJECTION_READY

The emulator must prove its injection primitive **before** setting A0. This is
the key difference from the previous A0-only experiment.

### ARM_REMOTE

Only after the injection mechanism is ready:

~~~text
0x27A0 = 1
~~~

### VERIFY_IDENTITY

Require bounded evidence that the controller accepted a remote participant:

- no BC;
- remote identity/SW state changes as expected;
- sensor status becomes valid.

### ACTIVE

Refresh the room-temperature state on a cadence comparable to a physical
Vitotrol. Use the physical emulator as behavioral reference, not necessarily as
the exact internal API.

A conservative design should expire its upstream temperature source and fail
closed rather than replay a stale room value indefinitely.

### ROLLBACK

Immediate rollback triggers include:

- BC current fault;
- failed room-sensor state;
- stale upstream sensor;
- unexpected write/readback;
- loss of splitter ownership/transport;
- internal invariant failure.

Rollback at minimum restores:

~~~text
0x27A0 = 0
~~~

Any additional temporary state must have an exact saved baseline and restore
procedure before testing begins.

## Staged experiment plan

### Stage 0 — offline only

- finish the profile-link trace for `NRF_Raumtemperatur_M1/M2`;
- identify which controller families actually use the writable aliases;
- compare their device/profile architecture with VDensHO1;
- inspect host metadata for any paired valid/status/software-index fields;
- continue internet/source search for those exact NRF tokens.

No boiler writes.

### Stage 1 — firmware correlation

After a local regulation firmware dump exists:

- locate `0x0896` and `0x089C` handlers;
- locate the A0/BC remote watchdog;
- locate KM-BUS RX parsing;
- cross-reference physical Vitotrol records `F8..FB`, register `0x00`,
  PING/PONG and room record `0x20`;
- identify the minimal internal state transition required to mark a remote alive.

### Stage 2 — bounded single-state injection

Only if Stage 0/1 produces an exact source-backed write primitive:

1. keep A0=0;
2. write one harmless bounded test room value through the candidate primitive;
3. read back `0x0896/0x089C/0x0A5C`;
4. restore/expire;
5. do not enable room influence.

This tests the state injection independently of remote watchdog arming.

### Stage 3 — temporary remote arming

Only after Stage 2 succeeds:

1. capture fault baseline;
2. start continuous injection;
3. set A0=1;
4. observe BC, software index, room value and sensor status;
5. rollback automatically on the first violated invariant.

### Stage 4 — persistence and restart behavior

Only after a clean short run:

- controller restart;
- emulator restart;
- temporary loss of upstream temperature;
- temporary loss of Optolink service;
- verify deterministic fail-safe behavior.

### Stage 5 — enable room influence

Room influence is the final step, not part of protocol bring-up.

## Functional-substitution fallback

If true remote emulation proves impossible without physical KM-BUS hardware,
the controller still exposes writable inputs that can approximate some desired
behavior, for example normal/reduced/party room setpoints and external HCC room
setpoints.

This is **not** a Vitotrol emulator:

- `0x0896` remains a fallback/invalid measured room value;
- `0x089C` remains invalid/unknown;
- no remote participant is registered;
- native Vitotrol room-influence semantics are not proven equivalent.

Such a design should be documented as external supervisory control, not remote
emulation.

## Current conclusion

A true software-only Vitotrol on the local WB2A is **not yet implementable from
a documented Vitosoft/Optolink API**.

However the search is no longer generic:

1. raw `KBUS_* WRITE` injection is source-negative;
2. exact VDensHO1 RPCs are exhausted and contain LON participant management but
   no KM-BUS remote hook;
3. `KMBUS_RAM_READ` has no source-backed symmetric write primitive;
4. `XRAM_WRITE` has no production event definitions;
5. the NRF cross-profile state model is useful for naming and locating remote
   state, but its read-only `AccessMode` means it is **not a documented
   injection API**;
6. a legacy `KBUS_Raumtemperatur_M1_IST~0x6F08` write function exists only for
   `HV_V300KW3` and is not linked to VDensHO1;
7. the remaining decisive information is likely in the local regulation
   firmware: room-value handler, remote watchdog and KM-BUS RX state updater.

The recommended research sequence is therefore:

~~~text
NRF state/profile differential + bounded P300 read correlation
        ->
local regulation firmware dump
        ->
0x0896 / 0x089C / 0x0A5C cross-references
        ->
KM-BUS RX / remote watchdog reconstruction
        ->
only then a bounded software-state injection test
~~~

## Evidence and references

Local repository evidence:

- `vitosoft/vitotrol-baseline-2026-09-23.md`
- `vitosoft/vdensho1-vitotrol-events.csv`
- `vitosoft/kbus-write-function-analysis.md`
- `kmbus-optolink-research.md`
- `vitotrol-kmbus-wire-protocol.md`
- `tools/kmbus-frame.py`
- private Collector-v6 workflow run `36176658272`, artifact
  `10882772275`

Public reference implementations:

- `dumpfheimer/WiFiVitotrol`
- `boblegal31/Heater-remote`
- OpenV KM-BUS/Vitotrol reverse-engineering discussion

The public projects are protocol/reference evidence. They do not prove an
Optolink-only injection path on VDensHO1.


## Local hardware follow-up — hidden NRF aliases on VDensHO1

The cross-profile NRF candidates were probed on the real WB2A through the
existing splitter transport.

### Read-only baseline

All of the following Virtual_READ requests were accepted:

~~~text
0x27A0 /1 -> 00
0x0A5C /4 -> 00000000
0x0896 /2 -> c800
0x089C /1 -> 03

0x0A40 /4 -> 00000000
0x7340 /1 -> 21
0x7341 /1 -> 00
0x7342 /1 -> 00
0x7343 /1 -> ff
0x75A2 /8 -> 0020260925052122
0x779C /1 -> 14
~~~

The cross-profile candidates are not all evidence of hidden Vitotrol state.
The all-device metadata resolves several collisions:

- `0x0A40` is already used by VDensHO1 as the read-only solar-control
  software-index object. The NRF profile reuses this address as a remote
  software-index input.
- `0x75A2` is VDensHO1 fault-history slot FA03 / 9-byte structure. The NRF
  profile reuses bytes of this address as a controller-info structure.
- `0x779C` is the normal LON receive-heartbeat configuration on VDensHO1.
  The local value `0x14` is 20 decimal / 20 minutes, matching Viessmann LON
  documentation. It must not be interpreted as a Vitotrol heartbeat.

Therefore those three addresses are cross-profile address reuse, not hidden
Vitotrol proof.

### 0x7340..0x7344 block

Exact VDensHO1 Vitosoft metadata contains no event link for
`0x733F..0x7344`.

Nevertheless the real controller returns stable values:

~~~text
0x7340 = 21
0x7341 = 00
0x7342 = 00
0x7343 = ff
0x7344 = ff
~~~

In VBC550S/P/Ecotronic the corresponding NRF semantics are:

~~~text
0x7340 programming-unit type
0x7341 remote-control ID boiler circuit
0x7342 remote-control ID M1
0x7343 remote-control ID M2
~~~

with `0x7342` values including `0x74 = BDETYP_F2M1`.

All tested addresses `0x7340..0x7344` accepted a same-value Virtual_WRITE.
This proves that the block is writable on local firmware, but not that every
byte has the NRF meaning on VDensHO1.

A bounded `0x7342` test was performed:

~~~text
00 -> 74 -> 00
~~~

Both writes returned success and readback matched. During the immediate
observation window there was no change to:

~~~text
0x27A0
0x0A5C
0x0896
0x089C
current alarm
~~~

A later isolated causality test held `0x7342=0x74` for one second, restored
`00`, and then monitored current alarm and newest fault-history slot for
77 seconds. No new BC entry was generated. Therefore a one-second change of
`0x7342` alone is insufficient to trigger the remote watchdog.

### 0x089C write behavior

A same-value Virtual_WRITE to `0x089C=03` is accepted by the controller:

~~~text
wraw 0x089C 03 -> success
~~~

A temporary attempt to write sensor-status OK:

~~~text
03 -> 00
~~~

also returned success, but the next read already returned `03`. Thus the
value is immediately regenerated/overwritten by internal controller logic.

A later isolated same-value `0x089C=03` write followed by 99 seconds of
monitoring produced no new current alarm and no new fault-history entry.

This proves a write handler exists for `0x089C`, but a normal Virtual_WRITE
does not own the effective sensor-status state.

### Rejected hidden NRF writes

The local controller rejects ordinary Virtual_WRITE to:

~~~text
0x0896  room actual value
0x0A40  candidate cross-profile remote SW index
~~~

including same-value writes. This confirms the previous `0x0896` rejection
and closes the simple NRF-alias injection hypothesis for those two objects.

### BC history observed during the research session

The newest system-fault slots currently contain four BC entries:

~~~text
BC 2026-09-25 21:43:28
BC 2026-09-25 22:04:48
BC 2026-09-25 22:09:04
BC 2026-09-25 22:17:36
~~~

The current alarm is now clear and `0x27A0=00`.

The first BC is consistent with the earlier known A0/Vitotrol-expectation
experiment. The later three occurred during the hidden-state investigation,
but exact one-to-one attribution is not yet proven because the splitter journal
records RX data but not a complete timestamped maintenance-command audit.

Important negative controls performed afterward:

- isolated `0x7342 00 -> 74 -> 00`, 1 s hold + 77 s observation: **no new BC**;
- isolated same-value `0x089C=03` + 99 s observation: **no new BC**.

Therefore neither primitive operation alone reproduces BC under those bounded
conditions. Future active experiments must write a timestamped local experiment
log before transmission so delayed faults can be attributed unambiguously.

### Updated model

Current evidence supports the following distinction:

~~~text
0x7340..0x7344
    writable hidden runtime/config block
    exact VDensHO1 meaning not yet proven

0x089C
    Virtual_WRITE handler exists
    effective value is regenerated by internal logic

0x0896
    effective room value
    ordinary Virtual_WRITE rejected

0x0A5C
    effective VDensHO1 remote software-index
    read-only

0x779C
    LON watchdog configuration
    NOT the Vitotrol watchdog
~~~

The central missing primitive remains the receive-side operation that updates
the effective room value, sensor-valid state and remote-alive/software-index
state together. The hidden writable aliases show that related handlers exist in
shared firmware families, but VDensHO1 applies different ownership/gating.
