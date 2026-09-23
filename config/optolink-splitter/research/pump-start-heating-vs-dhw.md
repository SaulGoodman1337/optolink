# WB2A pump behavior: heating vs DHW

Status: **read-only investigation active**

Controller under investigation:

- Vitodens 200-W WB2A
- Vitosoft profile: **VDensHO1 / 20C2**
- local developer version: **01.03**
- exact Vitosoft profile range: `VDensHO1` / extension `0100..0103`
- coding plug: **7833971**, revision **2015:0201**

## Research question

During domestic-hot-water preparation the internal boiler pump has been
observed at 100 % around burner operation/startup. During normal space heating,
the same automatic 100 % behavior has not been observed; local captures have
typically shown substantially lower values.

The goal is to determine which controller state and setpoint path selects the
DHW pump value, whether an equivalent path exists for heating, and only then
assess whether a safe controller-side heating-start pump request exists.

No burner/flame safety parameter is to be changed as part of this work.

## Vitosoft evidence for the exact VDensHO1 family

The Vitosoft-derived VDensHO1 device list exposes these pump-related objects:

| Event | Address | Vitosoft meaning | Role in this investigation |
| ---: | --- | --- | --- |
| 245 | `0x7660` | Interne Pumpe / `DigitalAusgang_InternePumpe` | live output/state object |
| 787 | `0x7660` | Interne Pumpe Drehzahl / `InternePumpeDrehzahl` | live pump-speed object |
| 886 | `0x5731` | (31) Solldrehzahl Interne Pumpe | configured internal-pump target |
| 968 | `0x676C` | (6C) Drehzahl Interne Pumpe bei WW-Bereitung | **DHW-specific internal-pump target** |
| 2903 | `0x27E6` | (E6) Maximale Drehzahl geregelte Pumpe A1/M1 | heating-circuit upper limit |
| 2908 | `0x27E7` | (E7) Minimale Drehzahl geregelte Pumpe A1/M1 | heating-circuit lower limit |
| 2913 | `0x27E8` | (E8) Solldrehzahl Pumpe im Nebenbetrieb A1/M1 | reduced/secondary-mode selector |
| 2918 | `0x27E9` | (E9) Reduzierte Drehzahl geregelte Pumpe A1/M1 | reduced-mode pump speed |

The M2 equivalents are at `0x37E6..0x37E9`.

Additional mode/state objects in the VDensHO1 list:

| Address | Meaning |
| --- | --- |
| `0x650A` | Warmwasserbereitung / `WW_Status_NR1` |
| `0x6513` | Speicherladepumpe |
| `0x0A10` | Umschaltventil |
| `0x5730` | (30) Kennung Interne Umwälzpumpe |
| `0x0A54` | software-index block for internal pump |

The exact production Vitosoft join contains 581 VDensHO1 events and **no
KBUS/KMBUS FCRead or FCWrite entries**. Therefore the pump investigation should
not use blind KBUS/KMBUS probes as its primary path. Ordinary VDensHO1 virtual
objects, GFA reads and already hardware-verified raw runtime structures are the
correct first layer.

## 0x7660 interpretation boundary

Vitosoft places both the digital internal-pump output and the internal-pump
speed at base address `0x7660`.

A closely related generated VDensHO1_4 catalog represents the speed as:

- block length 2;
- byte offset 1;
- percent.

That is strong evidence for a two-byte object in which byte 1 carries pump
speed. The local controller is, however, the base VDensHO1 01.03 profile, not
VDensHO1_4. Therefore this project records:

- `0x7660[0]`: raw output/state byte;
- `0x7660[1]`: **pump-speed percent candidate**;

until local hardware correlation shows the expected approximately 50 % and
100 % states.

## Coding-plug evidence

The local coding-plug block is hardware-read as:

```text
0x1070 = 05 1d 14 18 41 32 3c ...
```

Vitosoft mapping gives:

| Field | Meaning | Local raw |
| --- | --- | ---: |
| GWG74 | Kesselsollleistung im Speicherbetrieb | 65 |
| **GWG75** | **Mindestdrehzahl interne Pumpe** | **50** |
| GWG76 | Nachlaufzeit interne Pumpe | 60 |

The value **GWG75 = 50** is especially relevant because the observed heating
pump state has often been around 50 %. It is a credible lower-bound/reference
value for the heating-side pump logic, but it does not by itself prove that
every 50 % runtime value is directly selected by GWG75.

## Current working model

The simplest source-supported model is now:

1. the physical internal pump has a live output/speed object at `0x7660`;
2. normal heating uses the generic/internal-pump and A1 heating-circuit
   configuration path (`31`, E6/E7/E8/E9) with coding-plug constraints such
   as GWG75;
3. DHW has an explicit separate target, **coding 6C at `0x676C`**;
4. the controller selects the appropriate target according to operating mode.

If the local `0x676C` value is 100 and `0x7660[1]` becomes 100 as soon as
DHW mode is selected, no hidden burner-start override is required to explain
the observed behavior.

A separate transient override remains possible until timing proves otherwise.
The critical discriminator is whether the pump transition follows:

- the DHW state / diverter-valve transition, or
- a later GG1/GFA burner-start state such as pre-purge, flame establishment or
  regulation release.

## Read-only comparison logger

Repository helper:

```text
config/optolink-splitter/wb2a-pump-start-logger.py
```

Installed command after `update`:

```text
wb2a-pump-start-logger
```

The logger performs no writes.

At startup it captures a configuration snapshot containing:

```text
0x5730  K30 internal-pump identity
0x5731  K31 internal-pump target
0x5732  external-block influence on pumps
0x5734  external-demand influence on pumps
0x0A54  internal-pump software index
0x27E5..0x27E9  A1 pump identity / E6 / E7 / E8 / E9
0x37E5..0x37E9  M2 equivalents
0x6762  storage-pump overrun
0x6765  diverter-valve type
0x676C  DHW internal-pump target
0x676F  DHW power limit
0x1070  coding-plug GWG70..76 block
```

The runtime loop samples:

```text
0x7660 / 2   internal-pump raw output + speed candidate
0x650A / 1   DHW preparation state
0x6513 / 1   storage charging pump
0x0A10 / 1   diverter valve
0x55D3 / 11  GG1/GFA runtime, flame, 55DC modulation, 55DD
0x55E0 / 17  RKR/restart/OPT runtime structure
0x2544 / 2   A1/M1 flow target
0x0810 / 2   boiler actual temperature
```

It marks transitions for pump speed, DHW state, storage pump, diverter valve,
GG1/GFA state, RKR byte 14 and flame start/stop.

## First comparison protocol

Capture one natural/reproducible space-heating start:

```bash
wb2a-pump-start-logger --mode heating --interval 1.0
```

Then capture one DHW start:

```bash
wb2a-pump-start-logger --mode dhw --interval 1.0
```

Start logging before the mode transition/burner request and keep it running
through flame establishment and at least the first minute of stable firing.
The mode argument is only a label; it does not alter controller state.

For the first analysis compare:

1. local static values of `31`, `6C`, E6/E7/E8/E9 and GWG75;
2. the first transition of `0x7660[1]`;
3. relative timing of `0x650A`, `0x6513` and `0x0A10`;
4. relative timing of GG1/GFA `0x55D3[5:8]` states and flame;
5. whether 100 % starts before burner pre-purge/flame or only during a burner
   state;
6. whether heating ever requests a value above the static heating limits.

## Decision points after the logs

- **6C = 100 and pump reaches 100 at DHW-mode transition:** strongly supports
  a mode-specific DHW setpoint selector.
- **6C != 100 but pump still reaches 100:** search for a genuine transient
  override/state-machine command.
- **Heating pump remains bounded by E6/K31/GWG75-related values:** investigate
  the heating-side selector/parameterization before looking for overrides.
- **Heating briefly reaches 100 only at a GG1/GFA transition:** investigate a
  common startup override whose enable condition differs by operating mode.

No write experiment is justified until the runtime selector and the effective
setpoint source are identified.
## Hardware snapshot — 2026-09-23

Read-only values captured locally during a DHW-related state:

```text
0x5730 = 01   K30 internal pump = speed controlled
0x5731 = 64   K31 internal-pump target = 100
0x676C = 64   K6C DHW internal-pump speed = 100

0x27E5 = 00   E5 A1 pump identification = staged/no separate speed-controlled A1 pump
0x27E6 = 64   E6 A1 maximum = 100 %
0x27E7 = 1e   E7 A1 minimum = 30 %
0x27E8 = 00   E8 reduced/secondary-mode selector = use minimum E7
0x27E9 = 32   E9 reduced speed = 50 %

0x7660 = 01 64
0x650A = 02
0x6513 = 01
0x0A10 = 03
```

The exact generated `VDensHO1` catalog confirms the runtime object layout:

- `0x7660[0]` = internal-pump digital output/state;
- `0x7660[1]` = internal-pump speed in percent;
- `0x7663[0]` = A1/M1 heating-circuit-pump output/state;
- `0x7663[1]` = A1/M1 heating-circuit-pump speed in percent.

Therefore the measured `0x7660 = 01 64` is direct evidence for:

```text
internal pump output = ON
internal pump speed  = 100 %
```

The available enum mapping for the runtime states gives:

- `0x650A = 02`: DHW **overrun / Nachlauf**;
- `0x6513 = 01`: storage charging pump **ON**;
- `0x0A10 = 03`: diverter valve **toward DHW**.

This is an important discriminator: 100 % internal-pump speed is still present
in the DHW overrun state. It is therefore not exclusively tied to flame
presence, ignition or the approximately 12 s flame-stabilization interval.
The evidence now points first to a DHW hydraulic/mode selection that persists
through storage-pump overrun.

At the same time, both K31 and K6C are configured to 100 %. Consequently K6C
alone does not yet uniquely identify the runtime selector. The fact that normal
space heating has nevertheless shown lower pump speed means that the effective
heating request is computed elsewhere or is selected through the A1 pump path.

The next high-value runtime point is therefore `0x7663` (A1/M1 pump speed).
The comparison logger now records it alongside `0x7660`. A heating run can
answer whether normal operation follows a lower A1 request while DHW bypasses
that request and applies the 100 % internal-pump target.
## Second hardware snapshot — A1 path isolated during DHW overrun

A second read-only snapshot was taken while the controller still reported
DHW overrun:

```text
0x7660 = 01 64   internal pump output ON, internal-pump speed 100 %
0x7663 = 00 00   A1/M1 pump output OFF, A1/M1 pump speed 0 %
0x650A = 02      DHW overrun / Nachlauf
0x0A10 = 03      diverter valve toward DHW
```

This is a major architectural discriminator.

The internal pump can run at 100 % while the A1 heating-circuit pump runtime
object is simultaneously completely inactive. Therefore the DHW 100 % state is
**not** produced by a high A1/M1 pump-speed request propagating through
`0x7663`.

The current best-supported runtime model is now:

```text
space heating:
  A1/M1 pump controller -> 0x7663 -> internal-pump arbitration -> 0x7660

DHW / DHW overrun:
  DHW hydraulic/mode controller ---------------------------> 0x7660
  A1/M1 path inactive (0x7663 = 0000)
```

This proves that the controller contains at least one separate mode-dependent
internal-pump request path which bypasses the normal A1/M1 runtime pump object.
It does not yet prove which static parameter supplies the selected 100 % value,
because both coding 31 and coding 6C are currently set to 100 %.

The next decisive comparison is a normal space-heating run. Record
`0x7660/2` and `0x7663/2` before burner start, during startup and after stable
flame. If the two values track in heating mode while DHW keeps `0x7663=0000`,
the operating-mode arbitration boundary will be directly visible.
## Heating startup capture — 2026-09-23 10:44

A complete read-only heating startup was captured with the pump comparison
logger. The burner subsequently shut down into the known restart inhibition /
Taktsperre.

### Pump path

The decisive runtime values were:

```text
pre-start:
  0x7660 = 0000   internal pump OFF / 0 %
  0x7663 = 0000   A1/M1 pump OFF / 0 %

heating request / pre-purge:
  0x7660 = 0132   internal pump ON / 50 %
  0x7663 = 0124   A1/M1 pump ON / 36 %

through ignition, flame establishment, 65-66 % startup plateau,
modulation down-ramp and flame stop:
  0x7660 remained 0132 = 50 %
  0x7663 remained 0124 = 36 %
```

This is strong hardware evidence that the physical internal pump does **not**
simply mirror the A1/M1 runtime pump request in heating mode. The A1 controller
requested 36 %, while the internal pump was clamped to exactly 50 %.

The local coding plug contains:

```text
GWG75 = 50  Mindestdrehzahl interne Pumpe
```

Therefore the best-supported interpretation is now:

```text
A1/M1 calculated request = 36 %
GWG75 internal-pump minimum = 50 %
=> physical internal pump = 50 %
```

This is not yet a universal proof of the complete arbitration formula. A future
passive capture with an A1 request above 50 % should test whether the internal
pump follows it above the GWG75 floor. But the 36 -> 50 result is a direct and
very strong functional correlation with GWG75.

No 100 % heating-start override appeared. The internal pump was already at
50 % when pre-purge began and stayed at 50 % across all GG1/GFA start-state
transitions and flame establishment.

### Heating/DHW architecture after both captures

The two modes now differ clearly:

```text
HEATING
  A1/M1 runtime request 0x7663 = 36 %
             |
             v
  internal-pump arbitration / GWG75 minimum
             |
             v
  physical internal pump 0x7660 = 50 %

DHW OVERRUN
  A1/M1 runtime request 0x7663 = 0 % / OFF
  DHW hydraulic/mode request active
             |
             v
  physical internal pump 0x7660 = 100 %
```

This confirms that the controller has a separate DHW pump-request path which
bypasses the A1 runtime object, while heating is subject to a lower calculated
A1 request plus the internal-pump minimum.

### Burner sequence and thermal shutdown

Key timestamps from the heating run:

```text
10:44:45.000  internal pump 0 -> 50 %, A1 pump 0 -> 36 %, GFA pre-purge
10:44:48.503  diverter valve 03 -> 01 (toward heating)
10:44:55.785  flame start, modulation 66 %, boiler actual 31.0 C
10:45:07.244  +11.46 s: GFA 21/0b/60 -> 21/0b/62, 55E0.b14 01 -> 43
10:45:21.777  +25.99 s: boiler actual 46.3 C, target 38.0 C
10:45:23.855  +28.07 s: 55E0.b14 43 -> 00, boiler actual 48.3 C
10:45:25.990  +30.21 s: flame stop, boiler actual 49.5 C
```

The local coding plug has `GWG61 = 8 K` switch-off difference. With a 38.0 C
boiler/flow target, the observed 46.3 C sample is +8.3 K. The controller then
enters the shutdown/restart-inhibition state at the next sample and the flame
is gone roughly 2.1 s later.

This is strong additional evidence for the already proposed GWG61
interpretation and explains why this test run entered Taktsperre: the 50 %
internal-pump floor did not remove heat quickly enough during the high startup
modulation phase, so the boiler crossed the approximately target + 8 K
switch-off threshold before modulation could settle low enough.

### Immediate read-only follow-up

The highest-value remaining static snapshot from this exact logger run is the
`.probes.txt` file, especially:

```text
0x5732  K32 influence of external blocking on pumps
0x5734  K34 influence of external demand on pumps
0x6762  DHW/storage-pump overrun
0x676F  DHW power limit
0x0A54  internal-pump software index
```

K34 is particularly relevant to the long-term goal because Vitosoft explicitly
labels it **Einfluss Extern Anfordern auf Pumpen**. It should remain read-only
until its current value and exact bit/value semantics are understood.
## Configuration snapshot details — external-demand path and DHW settings

The heating-run probe file captured:

```text
K32 0x5732 = 00  external-block influence on pumps
K34 0x5734 = 00  external-demand influence on pumps
K62 0x6762 = 05  storage-pump overrun = 5 min
K65 0x6765 = 03  diverter-valve type = Grundfos
K6C 0x676C = 64  DHW internal-pump speed = 100 %
K6F 0x676F = 41  DHW power limit = 65 %
```

The WB2A service documentation defines both coding 32:0 and 34:0 as leaving
all connected pumps in their normal regulation function. Therefore the current
configuration contains no special pump action from the external block/request
input.

However, the same WB2A coding-34 table is relevant to the long-term objective:
with an active **Externes Anfordern** signal, coding value **34:16** selects:

```text
internal circulation pump: ON
other listed pumps:         normal regulation
```

Values 16..23 all force the internal circulation pump ON while combinations of
the other pumps may remain in regulation or be switched off.

This is the first controller-documented non-DHW request path found that can
explicitly force the internal pump ON. It is **not yet a proven 100 % speed
request**. The documentation specifies ON/OFF effect only, not resulting pump
speed. Because coding 31 is 100 %, one plausible hypothesis is that a forced
internal-pump ON state could use the K31 boiler-circuit-pump target, but this
must not be assumed without a controlled test.

There is also an important side effect: the WB2A service documentation states
that **Externes Anfordern** also uses coding 9B as a minimum boiler/flow target.
Thus this path is not automatically a pump-only command; it can affect heat
request/burner behavior. It must remain read-only until the external-extension
presence, current 9B value and exact request behavior are established.

The next logger revision therefore also snapshots:

```text
0x572E  coding 2E, external-extension present/absent
0x0A48  external-extension software-index block
0x779B  coding 9B, flow target for external demand
```

The 5-minute value at coding 62 also explains the earlier DHW sample: the
controller reported `0x650A=02` (DHW overrun) with the storage pump still ON,
diverter valve toward DHW and the internal pump at 100 %. The configured
5-minute storage-pump overrun is consistent with that persistent DHW hydraulic
state.
## External-demand path ruled out on this installation

Read-only snapshot:

```text
0x572E = 00         coding 2E: external extension = not present
0x0A48 = 00000000   external-extension software-index block = empty
0x779B = 00         coding 9B external-demand flow target = 0 C/raw 0
```

This means the controller-side **Externes Anfordern** path is not a practical
candidate on the current installation without first adding/configuring an
external extension. The Vitosoft visibility rules for codings 32, 34 and 9B
are consistent with this: those settings are hidden when coding 2E reports no
external extension.

Therefore coding 34 should be deprioritized for the pump-start objective. It is
useful architectural evidence that VDensHO1 can route a non-DHW request to the
internal pump, but it is not an immediately available software-only control
path on this boiler as installed.
## Complete DHW startup capture — 2026-09-23 11:02

A full read-only DHW sequence was captured from normal heating state into DHW,
including two burner phases and transition into DHW overrun.

### Initial transition into DHW

Immediately before the request:

```text
internal pump 0x7660 = 50 %
A1/M1 pump   0x7663 = 35 %
WW status    0x650A = 00 inactive
storage pump 0x6513 = 00 off
diverter     0x0A10 = 01 heating
```

Observed transition:

```text
11:02:59.164
  WW 00 -> 01 (charging)
  storage pump 00 -> 01
  A1 pump 35 -> 0
  internal pump remains 50 %

11:03:01.130   +1.966 s
  internal pump 50 -> 100 %
  GFA enters 01/08/20 pre-purge/start state

11:03:02.129   +2.965 s
  diverter 01 -> 03 (toward DHW)

11:03:11.411   +12.247 s
  flame start
```

Thus the internal pump reaches 100 % roughly ten seconds before flame
establishment and before the diverter-valve end position is observed.
The first sampled 50 -> 100 transition coincides with the GFA pre-purge
transition, so that single instant alone cannot distinguish whether the mode
arbiter or GFA startup caused the edge.

The remainder of the capture resolves that ambiguity.

### 100 % persists independently of burner operation

The first DHW burner phase ends at approximately 11:10:52 while:

```text
WW status = 01 charging
A1 pump = 0 %
internal pump = 100 %
```

The internal pump then remains continuously at 100 % for more than seven
minutes with the burner OFF. At 11:18:01 the burner starts again while the pump
is already at 100 % and no new pump-speed transition occurs.

Therefore the 100 % pump state is not a transient GFA/flame-start override.
It belongs to the DHW hydraulic/operating-mode state and is retained across
burner cycling inside a single storage-charge operation.

### Burner cycling inside one DHW charge

The same capture also separates two different burner stop causes while the pump
remains at 100 %:

- first DHW burner phase: target 68.0 C, boiler actual reaches 77.0 C and the
  burner stops while WW status remains 01. This is consistent with the already
  observed approximately target + GWG61 (8 K) thermal switch-off behavior;
- second DHW burner phase: WW status changes 01 -> 02 at boiler actual 74.0 C,
  then the controller shuts the burner down. This stop is tied to storage-charge
  completion / transition to overrun rather than the thermal +8 K limit.

Thus 100 % pump operation is independent of which burner-stop cause occurs.
It remains selected for the entire DHW hydraulic state.

### Transition to DHW overrun

During the second burner phase:

```text
11:19:30.124  WW 01 -> 02 (DHW overrun), internal pump still 100 %
11:19:32.268  GFA regulation/shutdown transition, 55E0.b14 43 -> 00
11:19:33.892  flame stop, internal pump still 100 %
```

The log ends with the controller still in WW overrun, storage pump ON,
diverter toward DHW, A1 pump OFF and internal pump at 100 %.

This is consistent with coding 62 = 5 min storage-pump overrun and proves that
the 100 % pump command spans both active DHW charging and DHW overrun.

### Status of coding 6C hypothesis

Static configuration:

```text
coding 6C = 100 %  "Drehzahl Interne Pumpe bei WW-Bereitung"
coding 31 = 100 %
```

Heating has already shown that coding 31 = 100 % is not directly applied as
the physical pump speed during normal A1 operation: A1 requested 36 %, the
internal pump ran at the GWG75 floor of 50 %.

In contrast, as soon as DHW takes ownership of the hydraulic path, A1 is shut
off and the internal pump changes to exactly the configured 6C value of 100 %,
then remains there through burner OFF periods and overrun.

Without deliberately perturbing 6C, absolute causal proof is not possible,
but the combination of Vitosoft semantics and hardware timing now provides
**very high confidence that coding 6C is the effective DHW pump-speed source**.
A hidden GFA startup override is no longer required to explain the observed
100 % behavior.

### Additional controller-side pump paths found in VDensHO1

The exact VDensHO1 event set also exposes:

```text
0x572F  coding 2F  Entlüftungs-/Befüllungsprogramm
0x7500  Aktorentest / RelaistestGWG200x
```

For the exact VDensHO1 actuator-test enum, `0x7500 = 0x04` means
**INTERNE PUMPE**. This is a direct controller-side service actuator path and
is independent evidence that the controller can command the internal pump
outside normal A1 and DHW regulation.

It is not yet a candidate for normal automatic heating-start operation and its
resulting speed is not documented by the enum. For now only the current values
of 0x572F and 0x7500 should be read. Any actuator-test write must remain a
later, deliberate service-mode experiment after behavior and side effects are
fully understood.
## Service selectors confirmed inactive

Read-only normal-state snapshot:

```text
0x572F = 00   coding 2F: vent/fill program inactive
0x7500 = 00   actuator test inactive
```

Therefore neither service program nor actuator-test state contributes to the
observed normal heating 50 % / DHW 100 % pump behavior. These paths remain
architectural evidence only and are not part of the live arbitration under
normal operation.
## Internal M2-to-internal-pump request path found

A targeted search for runtime/configuration paths that can request the internal
pump without using DHW or the absent external extension found coding A8:

```text
0x37A8  (A8) Einfluss auf Interne Pumpe
  0 = ohne
  1 = M2 setzt Anforderung an Int.Pumpe
```

This is an important architectural result because it proves that VDensHO1 has
an internal heating-circuit-to-boiler-pump request path in addition to the A1
speed object and the DHW path.

Its practical relevance depends on the configured plant schema:

```text
0x7700  coding 00 / heating-circuit-DHW schema
  1 = A1
  2 = A1 + WW
  3 = M2
  4 = M2 + WW
  5 = A1 + M2
  6 = A1 + M2 + WW
```

Associated M2 runtime objects are:

```text
0x3906 / 1  M2 pump state (0 off, 1 on)
0x7665 / 2  M2 pump output / speed, byte 1 = percent
```

This path is not yet evidence for a 100 % heating-start command. It only shows
that M2 can assert a request to the internal pump when A8=1. Before considering
any write test, first read 0x7700, 0x37A8, 0x3906 and 0x7665 on the local boiler
and determine whether M2 exists and whether this request path is currently in
use.
