# Vitotrol software-only emulation deep dive — 2026-09-25

Status: **active research / software-only path not yet proven**

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

## New lead: writable alias at the exact room-temperature address

The deep dive found the strongest new software-only lead so far.

The global production event catalog contains:

~~~text
NRF_Raumtemperatur_M1~0x0896
FCRead  = Virtual_READ
FCWrite = Virtual_WRITE
length  = 2
conversion = Div10

NRF_Raumtemperatur_M2~0x0898
FCRead  = Virtual_READ
FCWrite = Virtual_WRITE
length  = 2
conversion = Div10
~~~

At the **same numeric addresses**, exact VDensHO1 instead links:

~~~text
TiefpassTemperatur_RTS_A1M1~0x0896
FCRead  = Virtual_READ
FCWrite = undefined

TiefpassTemperaturwert_RTS_M2~0x0898
FCRead  = Virtual_READ
FCWrite = undefined
~~~

This distinction matters.

### What this proves

It proves that Viessmann software uses `Virtual_WRITE` to the same
room-temperature address in at least another controller/profile context. Thus
`0x0896` is not globally an intrinsically read-only protocol address.

### What it does not prove

It does **not** prove that the local VDensHO1 firmware accepts a Virtual_WRITE
to `0x0896`.

The earlier local attempt to write the suspected room-temperature object was
rejected. That result remains authoritative for the ordinary VDensHO1 path.

It also does not prove that writing `0x0896` alone would satisfy:

- remote identity/software-index state;
- sensor-valid state;
- remote communication watchdog;
- BC fault supervision.

### Cross-profile differential result — 2026-09-25

A direct Collector-v6 profile comparison on the Optolink-Splitter machine
resolved the writable alias provenance and found a broader, coherent NRF remote
injection surface.

The writable room-temperature aliases are linked to:

~~~text
VBC550S   device 224
VBC550P   device 225
Ecotronic device 432
~~~

For these profiles, the following NRF events form a consistent remote-state
set:

| Address | NRF event | Access | VDensHO1 counterpart |
| --- | --- | --- | --- |
| `0x0896` | `NRF_Raumtemperatur_M1` | Virtual_READ / Virtual_WRITE | same address, read-only `TiefpassTemperatur_RTS_A1M1` |
| `0x089C` | `NRF_TemperaturFehler_RTS_M1` | Virtual_READ / Virtual_WRITE | same address, read-only `HO2B_SensorStatus_RTS_M1` |
| `0x0A40` | `NRF_SWIndex_FB_M1` | Virtual_READ / Virtual_WRITE | VDensHO1 uses read-only `SWIndex_FB1` at `0x0A5C` instead |
| `0x7342` | `NRF_BedienBDETyp_FBM1` | Virtual_READ / Virtual_WRITE | no exact VDensHO1 remote-runtime equivalent recovered |
| `0x75A2` | `NRF_KTInfo_Fernbedienungen` | Virtual_READ only | no exact VDensHO1 event link recovered |
| `0x779C` | `NRF_K9C_KonfiReceiveHeartBeat` | Virtual_READ / Virtual_WRITE | VDensHO1 has the same address as LON participant supervision, not Vitotrol runtime state |

The key architectural observation is that VBC550S/P and Ecotronic contain both
of the following aliases simultaneously at `0x0896`:

~~~text
NRF_Raumtemperatur_M1      Virtual_READ + Virtual_WRITE
TiefpassTemperatur_RTS...  Virtual_READ only
~~~

VBC550S/P similarly contain a writable NRF sensor-status alias at `0x089C`.
This makes a deliberate service/software injection model substantially more
plausible than a coincidental address collision.

It does not make these writes valid on VDensHO1. The local normal
`Virtual_WRITE 0x0896` attempt was already rejected. The next justified local
step is therefore **read-only discovery** of the cross-profile NRF-only
addresses (`0x0A40`, `0x7342`, `0x75A2`) and comparison with the exact
VDensHO1 state. No NRF write should be attempted without a VDensHO1 firmware or
source-backed handler match.

A read-only helper was staged on the Optolink-Splitter host as:

~~~text
/home/chatgpt-admin/vitotrol-nrf-readonly-probe.py
~~~

It uses the existing MQTT/splitter request path and implements no write command.
At the time of staging, `optolink-splitter.service` was independently down due
to the known codierstecker UTF-8 decode crash on an `FF...` response, so the
probe has not yet produced a live controller result.

### Local hardware verification of the NRF/remote-state hypothesis — 2026-09-25

The cross-profile NRF surface was probed on the local WB2A through the existing
VS1 Optolink-Splitter with room influence disabled. All temporary state changes
were bounded and rolled back.

#### Hidden participant/state block is real

Read-only local values:

~~~text
0x7330 /2 = 0100   programming-unit software index
0x7332 /2 = 0000   older-family FB A1/M1 software-index slot
0x7334 /2 = 0000   older-family FB M2 software-index slot
0x7336 /2 = FFFF   older-family FB M3 absent/uninitialised slot

0x7340 /1 = 21     programming-unit type
0x7341 /1 = 00     remote-control type KK absent
0x7342 /1 = 00     remote-control type M1 absent
0x7343 /1 = FF     M2/unused state on this controller
~~~

The exact VDensHO1 Vitosoft profile does not publish 0x7340..0x7344, but these
addresses return a coherent programming-unit/remote-control structure. This is
strong evidence that the firmware retains internal remote-participant state
which is not exposed by the exact Vitosoft profile.

#### 0x7342 is genuinely writable

Vitosoft defines 0x7342 in the VBC550/Ecotronic NRF profiles as
`NRF_BedienBDETyp_FBM1`, with:

~~~text
0x74 = BDETYP_F2M1
0x78 = BDETYP_F3M1
~~~

On the local WB2A:

~~~text
0x7342: 00 -> 74 -> 00
~~~

Both writes were accepted and the changed value was observable by readback until
explicit rollback. No A0, room-temperature, room-sensor, remote-software-index,
current-alarm or fault-history state changed merely from setting 0x7342.

Therefore 0x7342 is a real hidden writable runtime/configuration field, but it
is not by itself remote detection or remote communication.

#### 0x7342 does not satisfy the Vitotrol watchdog

A bounded combination test used:

~~~text
0x7342 = 74
0x27A0 = 01
~~~

with B0 still disabled. The result was:

~~~text
t ~= 0.0 s   A0=01, 7342=74, no current alarm yet
t ~= 0.8 s   current alarm = BC
~~~

During the test:

~~~text
0x0A5C = 00000000
0x0896 = C800
0x089C = 03
~~~

The test stopped on BC and immediately restored:

~~~text
0x27A0 = 00
0x7342 = 00
~~~

The current alarm cleared. The expected BC history entry remains at the newest
fault-history slot. Thus the actual KM-BUS remote communication/alive watchdog
is independent of the hidden 0x7342 type field.

#### Write acceptance is length- and alias-dependent

Several same-value writes were used only to classify handler behaviour:

~~~text
0x0896 /2  C800       -> rejected
0x0896 /1  C8         -> ACK/success
0x089C /1  03         -> ACK/success
0x0A40 /4  00000000   -> rejected
0x0A5C /4  00000000   -> rejected
0x0A5C /1  00         -> ACK/success
0x7332 /2  0000       -> rejected
0x7332 /1  00         -> ACK/success
~~~

This is a critical protocol result: the virtual address space must not be
assumed to be byte-linear. A multi-byte object at address X is not equivalent
to independently addressable bytes X, X+1, ... . Cross-profile aliases can
also make one request length accepted while the canonical local object remains
read-only.

Accordingly, a splitter response of `1;address;value` proves only that the
particular write request shape was accepted. It does **not** prove that the
canonical semantic object changed.

#### One-byte room-temperature ACK does not inject room temperature

With the safe baseline:

~~~text
A0 = 00
B0 = 00
0x0896 = C800 = 20.0 °C fallback
0x089C = 03
~~~

one byte was temporarily written at 0x0896:

~~~text
wraw 0x0896 D7
~~~

If 0x0896 were a byte-linear little-endian room value, this would correspond to
21.5 °C (`D7 00`). The write returned success, but repeated canonical two-byte
reads over roughly two seconds remained:

~~~text
0x0896 /2 = C800
~~~

at every sample. No sensor-status, A0 or current-alarm change occurred. The
original low-byte value was then explicitly written back.

Therefore the one-byte ACK is **not semantic room-temperature injection**. The
full VDensHO1 room-temperature object remains protected/read-only through this
path.

#### 0x089C ACK is also not persistent state injection

A temporary write:

~~~text
0x089C: 03 -> 00
~~~

was acknowledged, but the next canonical read already returned 03 again. This
is consistent with the sensor-status value being recomputed/overwritten by the
controller rather than being a durable externally writable state.

#### Cross-profile aliases eliminated as local Vitotrol hooks

Additional local mapping resolved several apparent NRF candidates as address
collisions:

- `0x0A40` is the VDensHO1 solar-controller software-index location;
- `0x0A44` is the VDensHO1 mixer software-index location;
- `0x75A2` is VDensHO1 burner/BCU fault-history slot FA03, not remote-info;
- `0x779C` is VDensHO1 LON receive-heartbeat configuration; local value is
  `0x14 = 20 min`;
- `0x778E` is a VDensHO1 EEPROM/I2C-related configuration/error location, not
  the NRF remote-control selector.

These addresses must not be repurposed according to VBC550/Ecotronic semantics
on the WB2A.

#### Restored final state

After all bounded tests the controller was verified at:

~~~text
0x27A0 = 00
0x27B0 = 00
0x7342 = 00
0x7332 = 0000
0x0A5C = 00000000
0x0896 = C800
0x089C = 03
current alarm code = 00
~~~

The Optolink-Splitter service was active. The only intentional persistent test
artifact is the new BC entry in the system fault history from the bounded
A0+0x7342 experiment.


#### Additional local discriminators — 2026-09-25 late session

A control pass across the hidden programming-unit block showed that same-value
Virtual_WRITE acceptance is not unique to the M1 remote-type byte:

~~~text
0x7340  21 -> 21   accepted
0x7341  00 -> 00   accepted
0x7342  00 -> 00   accepted
0x7343  FF -> FF   accepted
0x7344  FF -> FF   accepted
~~~

This weakens any interpretation based solely on an ACK at 0x7342. The
significant evidence remains its source-correlated value semantics
(`0x74 = BDETYP_F2M1`, `0x78 = BDETYP_F3M1`) and the fact that a changed
value can be read back.

A separate persistence test held `0x7342 = 0x74` for more than 20 seconds
while `A0 = 0`. It remained `0x74` for the full observation interval, did
not auto-arm `0x27A0`, and caused no current alarm. The value was then
explicitly restored to `0x00`.

A matched A0 control was also run:

~~~text
control:             0x7342=00, A0 00->01 -> BC observed in that run at ~6.48 s
type preloaded:      0x7342=74, A0 00->01 -> BC observed in that run at ~2.56 s
~~~

Both runs left `0x0A5C=00000000`, `0x0896=C800` and `0x089C=03`, and
both were immediately rolled back to `A0=0`; the current alarm then cleared.
The different BC latency must not be interpreted as a causal acceleration:
the controller fault check is asynchronous/cyclic and the trials were not
phase-synchronised. The robust discriminator is binary: **BC occurs in both
cases**.

This strengthens the interpretation that `0x7342` is a writable
type/service-state field, while the actual remote liveness state is owned by a
different firmware path fed by successful KM-BUS traffic.

The generic MQTT maintenance `request;0x41;...` route was also tested and
timed out even for the already known-good `0x00F8` target. This is therefore
a maintenance-API/serializer limitation, not evidence that local
`KMBUS_RAM_READ` stopped working. The isolated guarded P300 helper was run
immediately afterwards and again hardware-verified `0x41` as identical to
Virtual_READ on its whitelisted targets, including `0x27A0`.

Finally, the recovered production FunctionCode table contains
`KMBUS_RAM_READ = 0x41` and then `KMBUS_EEPROM_READ = 0x43`; there is no
defined/source-backed `KMBUS_RAM_WRITE = 0x42`. This is a further reason not
to infer a symmetric write primitive from the working 0x41 path.


#### Updated interpretation

The ordinary Virtual_WRITE route is now strongly constrained:

1. hidden remote-type state exists and can be manipulated at 0x7342;
2. setting that state does not satisfy the real Vitotrol communication
   watchdog;
3. canonical room value and remote software-index objects remain non-writable;
4. ACKs from one-byte alias writes do not alter the canonical multi-byte
   runtime objects;
5. the unresolved state is therefore the KM-BUS RX-derived participant
   alive/watchdog/runtime state, not merely the displayed type or room value.

The next high-value discriminator is a read-only differential of the controller
state while A0 transitions into BC, preferably through the already verified
`0x41 KMBUS_RAM_READ` path under a guarded P300 session, or through firmware
cross-reference once a regulation firmware dump is available.

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
5. **the global writable NRF alias at `0x0896/0x0898` is the strongest new
   software-only lead**;
6. the remaining decisive information is likely in the local regulation
   firmware: room-value handler, remote watchdog and KM-BUS RX state updater.

The recommended research sequence is therefore:

~~~text
NRF writable-alias profile trace
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
