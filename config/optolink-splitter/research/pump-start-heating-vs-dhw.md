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
## Local plant schema confirms A1 + DHW only

Read-only local values:

```text
0x7700 = 02      plant schema = A1 + DHW
0x37A8 = 01      M2 would request internal pump if M2 existed
0x3906 = 00      M2 pump state off
0x7665 = 0000    M2 pump output/speed 0 %
0x2906 = 01      A1/M1 pump state on
```

Therefore the A8/M2 path is not active on this installation. Coding A8=1 is
best treated as an inactive/default/stored configuration value because the
selected plant schema contains no M2 circuit. The zero M2 runtime objects
confirm this.

The active heating path is A1. Two additional configuration facts clarify the
meaning of the runtime objects:

```text
0x27E5 = 00  E5 A1 pump identification = staged (not a separate speed-controlled pump)
0x5730 = 01  internal pump = speed controlled
```

This supports the following refined model:

```text
A1 logical pump state 0x2906 = ON
A1 controller calculates speed demand 0x7663 = ~35-36 %
                    |
                    v
speed-controlled internal pump arbitration
                    |
              GWG75 floor = 50 %
                    |
                    v
physical/internal output 0x7660 = 50 %
```

Thus `0x7663` should be interpreted as the A1 control-loop speed demand, not as
evidence for a second physical variable-speed A1 pump on this installation.
The physical controlled actuator is the internal pump identified by coding 30.

The M2/A8 path can be removed from the list of practical candidates for the
heating-start 100 % objective. Future work should focus on the arbitration
between A1 calculated demand, internal-pump minimum/limits and mode-specific
sources such as DHW coding 6C.
## No dedicated heating-start pump boost exposed in VDensHO1

A targeted search across the complete VDensHO1 event set for combinations of
pump with burner start, pre-purge, flame, stabilization, startup and run-up did
not reveal a dedicated heating-start pump parameter or runtime request.

The pump-related control surfaces exposed by Vitosoft are the already known
ones:

```text
0x5731  coding 31, internal-pump target
0x676C  coding 6C, internal-pump speed during DHW
0x27E6..0x27E9  A1 pump max/min/reduced-mode settings
0x37A8  M2 -> internal-pump request (irrelevant locally: no M2)
0x5732 / 0x5734  external block/request effects (extension absent locally)
0x572F  vent/fill service program
0x7500  actuator test
GWG75   coding-plug minimum internal-pump speed
GWG76   coding-plug internal-pump overrun
```

The burner-start-related coding-plug item GWG73 is explicitly an
**Anfahroptimierung modulierender Brenner**, not a pump parameter.

This negative result matters: the normal VDensHO1 configuration model does not
appear to expose a distinct "raise internal pump to 100 % during heating burner
start" switch or setpoint.

The Vitosoft event classes also separate runtime outputs from writable control
surfaces: `0x7660` (internal-pump output/speed) and `0x7663` (A1 speed demand)
are exposed as runtime read objects, whereas codings/service selectors are
separate configuration/control events. Therefore direct writing of the live
pump output is not supported by the normal Vitosoft data model.

Practical implication for the research goal:

1. the normal heating path computes an A1 request and applies internal-pump
   arbitration/minimum limits;
2. the normal DHW path selects the dedicated 6C pump speed;
3. no normal start-specific heating pump source has been found;
4. any automatic 100 % heating-burner-phase solution would therefore have to use a
   different controller-supported request/service path, or modify a general
   pump limit/setpoint, rather than enable a hidden burner-phase-only coding.

General-limit changes such as raising E7 or GWG75 are not equivalent to the
requested behavior because they would raise the pump for the entire heating-pump demand, not specifically as part of a controller operating mode comparable to DHW.
The actuator-test path is also not yet suitable for automation because it is a
service mode and its side effects have not been characterized.
## Writable-pump-object inventory for the corrected objective

Vitosoft metadata distinguishes event types as:

```text
Type 1 = read-only
Type 2 = read/write
Type 3 = write-only
```

Filtering the global event index for writable pump-related objects yields only
configuration/service controls such as:

```text
0x5730  coding 30 internal-pump type
0x5731  coding 31 internal-pump target
0x5732  coding 32 external-block pump effect
0x5734  coding 34 external-demand pump effect
0x6762  coding 62 DHW pump overrun
0x676C  coding 6C DHW internal-pump speed
0x37A8  coding A8 M2 -> internal-pump request
0x27E5..0x27E9  A1 pump configuration
0x37E5..0x37E9  M2 pump configuration
0x7500  actuator test (service command; not a normal operating-mode setpoint)
```

The live objects used by the logger are read-only:

```text
0x7660  internal-pump output/speed
0x7663  A1 calculated pump-speed demand
0x7665  M2 pump output/speed
```

No normal read/write runtime object was found that means "internal pump request"
or "internal pump speed override" and can simply be asserted while the burner
is firing.

This sharpens the available solution classes for the corrected objective
(at least 100 % during the full burner-on phase; controller pre/overrun is OK):

1. use a normal operating topology in which the internal pump is a boiler-circuit
   pump governed by coding 31 (M2 is the current leading candidate);
2. globally change pump limits/minimums (works, but affects all heating-pump
   operation and is not mode-selective);
3. use a service actuator command (diagnostic only until its interaction with
   normal operation is understood);
4. introduce an external/custom control path outside the normal VDensHO1
   operating-mode model.
## Manual actuator-test capture — 2026-09-23 11:45

A manual service-menu test of **Int. Pumpe Ein** was captured with an older
installed revision of the pump logger. That logger did not yet poll 0x7500 or
0xA152 at runtime, so the result must be interpreted cautiously.

Baseline before the apparent test window:

```text
internal pump 0x7660 = 50 %
A1 demand     0x7663 = 33 %
WW inactive
burner off
flow target = 38 C
```

At 11:45:57.476, byte 15 of the 17-byte 0x55E0 structure changed from 0x00 to
0x04 and remained 0x04 until 11:46:26.920. The value 0x04 is notable because
0x7500 enum value 0x04 is exactly **INTERNE PUMPE**, but no source currently
proves that 0x55E0 byte 15 mirrors the actuator-test selector.

During that entire approximately 29 s window:

```text
internal pump remained 50 %
A1 demand remained 33 %
no 100 % pump transition occurred
```

At 11:46:28.471 the internal pump and A1 demand both changed to 0 %. A later
manual read after the test showed:

```text
0x7500 = 00
0x7660 = 0000
```

Therefore this capture does **not** support the idea that the service command
"Int. Pumpe Ein" automatically selects 100 % speed. It is consistent with a
service relay command that only forces the pump output ON while speed remains
set by the existing speed-control path, but this is not yet proven because the
old logger did not capture 0x7500 and relay state concurrently.

The logger has therefore been extended to poll:

```text
0x7500 / 1   actuator-test selector
0xA152 / 2   relay-state block
             byte 0 bit 0x20 = internal-pump relay
             byte 0 bit 0x02 = burner relay
```

A short repeat of the same manual service-menu test with the updated logger can
now determine whether:

1. selecting "Int. Pumpe Ein" really produces 0x7500=04;
2. the internal-pump relay bit is asserted;
3. 0x7660 stays at the prior/A1-derived speed or changes to another target.

## Definitive actuator-test repeat — 2026-09-23 11:56

The actuator test was repeated with runtime logging of 0x7500 and 0xA152.

Observed sequence:

```text
11:56:44  0x7500 00 -> 01   ALLE PASSIV
11:56:46  0x7500 01 -> 02   BRENNER MIN LEISTUNG
           GFA immediately enters 01/08/20
11:56:49  0x7500 02 -> 07
11:56:50  0x7500 07 -> 05
11:56:53  0x7500 05 -> 04   INTERNE PUMPE
11:57:32  0x7500 04 -> 00   test exited
```

Thus the service menu selection is definitely reflected live at 0x7500 and
does not require a second confirmation. The fact that 0x7500=02 immediately
affected the burner state also confirms that the actuator-test framework was
active.

During the full approximately 39 s interval with `0x7500=04`:

```text
0x7660 = 0000   internal-pump runtime output/speed = 0 %
0x7663 = 0000   A1 pump demand = 0 %
0xA152 = 0440   internal-pump relay bit (byte0 bit 0x20) = 0
```

No software-visible internal-pump activation or 100 % speed command occurred.

The WB2A service manual labels this function **"Int. Pumpe Ein"**, but explains
it electrically/logically as **"Int. Ausgang 20"**. The most plausible
interpretation for the local speed-controlled pump is therefore that this
service item acts on the legacy/internal output-20 path and does not establish
the variable-speed command represented by 0x7660.

Strictly, software telemetry cannot prove physical rotor standstill if the
service path bypasses both 0x7660 and the A152 status object. However, for the
automation objective the path is unsuitable either way: it provides no
observable controlled 100 % speed setpoint.

Conclusion: deprioritize 0x7500 as a solution. The normal M2/boiler-circuit
architecture remains more relevant because it has a dedicated documented
speed target, coding 31.
## A1 E7=100 % heating test — 2026-09-23 12:08

A controlled direct-heating test was performed with A1 minimum pump speed
coding E7 raised to 100 % while E6 was already 100 %.

Direct reads confirmed the control chain:

```text
0x27E7 = 0x64    E7 = 100 %
0x7663 = 0x0164  A1 calculated/runtime pump demand = 100 %
0x7660 = 0x0164  internal pump output/speed = 100 %
```

This proves that in the local direct A1 topology E7 can force the A1 request
and the internal speed-controlled pump to 100 % without changing plant schema.

### Burner result at 100 % pump

Key timeline from the capture:

```text
12:10:28.663  pump 0 -> 100 %, A1 demand 0 -> 100 %
12:11:54.256  FLAME_START, modulation 66 %, boiler 33.0 C, target 38.0 C
12:12:03.239  regulation transition, modulation 65 %, boiler 36.5 C
12:12:36.557  modulation reaches 33 % minimum, boiler 43.0 C
12:17:33.545  boiler first reaches 46.0 C while still at 33 % modulation
12:17:54.433  boiler 46.3 C
12:17:56.247  thermal shutdown transition / B14 43 -> 00
12:17:58.499  FLAME_STOP
```

Flame duration was approximately 364 s (6 min 4 s).

This is fundamentally different from the previous 50 % pump heating start,
where the boiler crossed the approximately target + 8 K shutdown threshold
within roughly 26 s and the flame stopped after roughly 30 s, before the burner
could reach minimum modulation.

At 100 % pump the burner successfully survives the startup plateau, reaches the
33 % heating minimum after about 42 s and then remains there for more than five
minutes. Boiler temperature initially peaks around 44.3 C, falls back toward
39.6-40 C as modulation reaches minimum, and only then slowly rises again until
the target + GWG61 threshold is reached.

### Interpretation

This provides strong causal evidence that insufficient heat transport at the
50 % internal-pump speed is the dominant cause of the **premature startup
shutdown / Taktsperre** observed in the earlier heating run.

The later shutdown at 100 % pump is a different operating limit: once the burner
has reached its 33 % minimum output, the connected radiator circuit under the
test conditions still absorbs slightly less heat than the boiler produces over
time. The controller therefore eventually reaches the same thermal upper
threshold. This is normal minimum-load cycling rather than a failed burner
startup.

The test also reconfirms GWG61 ~= 8 K: target remained 38.0 C and shutdown
transition occurred at approximately 46.3 C.

### Pump timing and E7 logging caveat

The logger's one-time configuration snapshot was taken before the E7 change and
therefore still recorded E7=30 %. During the actual heating phase both 0x7663
and 0x7660 were clearly 100 %.

After flame stop the capture later shows A1 demand 100 -> 32 % and internal pump
100 -> 50 %. Because that logger revision did not poll 0x27E7 each cycle, the
capture alone cannot determine whether this transition was caused by E7 being
manually restored or by another controller state change.

The logger has therefore been extended to poll 0x27E7 at runtime and emit E7
change events for future tests.

### Engineering consequence

A real M2 conversion is no longer needed to prove that high boiler-side flow
solves the premature-start problem. The existing A1 topology can already drive
the internal pump to 100 % through the documented E7 path.

The remaining problem is narrower:

> find a durable control strategy that provides the desired high pump speed
> during heating operation without unnecessarily forcing 100 % pump speed for
> all A1 pump-on periods.

Repeatedly rewriting E7 for every burner cycle should not be adopted until the
storage/write semantics of this coding parameter are understood; E7 is exposed
as a configuration/coding value, not as a dedicated volatile runtime request.
## E8/E9 check after E7=100 % test

Vitosoft defines:

```text
E8 = Solldrehzahl Pumpe im Nebenbetrieb A1M1
  0 = minimal nach Cod. E7
  1 = reduziert nach Cod. E9

E9 = Reduzierte Drehzahl geregelte Pumpe A1M1 [%]
```

The associated heating-circuit runtime model separately exposes current
operating mode at 0x2500 byte 1 as Abschaltbetrieb / Reduzierter Betrieb /
Normalbetrieb. This context indicates that E8/E9 belong to normal-vs-reduced
heating operating modes, not to a dedicated burner-on/burner-off pump state.

Therefore E8 is not currently considered a solution for lowering pump speed
specifically when the flame goes out during an otherwise normal daytime A1
heating period.

## E7=100 % burner-off behavior — 2026-09-23 12:27

A follow-up run kept E7 at 100 % for the entire capture and logged E7
continuously.

The capture starts with:

```text
E7 = 100 %
flame = OFF
internal pump = 0 %
A1 demand = 0 %
boiler actual ~47.5 C
heating flow target = 38.0 C
```

When the A1 pump demand becomes active:

```text
12:27:46.588  pump relay 0 -> 1, flame still OFF
12:27:49.326  A1 demand 0 -> 100 %
                 internal pump 0 -> 100 %
                 E7 remains 100 %
                 flame remains OFF
```

The burner does not ignite during the remainder of the approximately 11 min
capture. Nevertheless both A1 demand and the internal pump stay continuously at
100 % while E7 remains 100 %. Boiler temperature falls from the post-cycle heat
level through the 38 C target and down to roughly 36 C, but pump speed does not
reduce.

The final configuration snapshot still confirms:

```text
E7 = 100 %
E8 = 0  -> Nebenbetrieb uses minimum according to E7
E9 = 50 %
```

This definitively answers the earlier open question:

> In the direct A1 topology, E7=100 % is not burner/flame selective. It forces
> the A1 pump request to 100 % whenever the A1 pump is enabled, including long
> burner-off intervals.

Therefore leaving E7 permanently at 100 % does achieve the required 100 % pump
speed during burner operation, but also runs the direct radiator circuit at
100 % during normal pump-only periods. This is not the desired selective
control behavior.

E8=0 reinforces this result: in Nebenbetrieb the controller explicitly uses the
minimum according to E7, so with E7=100 % there is no reduced pump speed there
either.

### Consequence

E7 remains an excellent diagnostic proof and an emergency/simple configuration
option, but not the preferred final policy if unnecessary 100 % pump operation
outside burner operation is to be avoided.

The remaining solution space is now:

1. identify a native operating-state parameter that selects different pump
   speed while the burner is off;
2. determine whether E7 can safely be changed dynamically without excessive
   nonvolatile-memory writes;
3. use another native topology/request path (for example M2) if it provides the
   desired operating-mode semantics;
4. accept E7=100 % permanently if the hydraulic/acoustic/electrical cost is
   acceptable.

### Exact follow-up timing and E8 clarification

In the 12:27 follow-up capture, E7 stayed at 100 % for the entire run. Once A1
enabled its pump request at 12:27:49.326, both A1 demand and the internal pump
remained at 100 % until the capture ended at 12:39:20.334 — about 691 s
(11 min 31 s) — while the flame remained OFF throughout.

The exact WB2A service documentation resolves the ambiguous Vitosoft term
"Nebenbetrieb" for E8/E9:

- E8=1: minimum pump speed during operation with **reduced room temperature**
  according to E9;
- E8=0: speed according to E7;
- E9: pump speed during operation with **reduced room temperature**.

Thus E8/E9 do not represent burner-off or pump-overrun states. They only change
pump speed in reduced-heating mode. They cannot provide the desired
flame-dependent 100 % / lower-speed split during one normal heating period.

## Runtime-write search and coding 51 candidate — 2026-09-23

### No writable runtime pump target in exact VDensHO1

A complete review of the exact VDensHO1 pump-related event set still shows no
normal writable runtime setpoint equivalent to the read-only values:

```text
0x7660  internal-pump runtime output/speed
0x7663  A1 runtime/calculated pump-speed request
0x7665  M2 runtime pump speed
```

The writable controls remain configuration/coding values such as E6/E7/E8/E9,
31, 32/34 and A8. There is therefore no exact-profile object that can simply be
asserted as "A1 pump = 100 %" while flame is present and released afterwards.

### E7 write path and persistence uncertainty

Vitosoft exposes E7 event 2908 as the coding/configuration object
`KE7_KonfiMinDrehzahlA1M1_GWG~0x27E7`.

Historical P300 implementations also explicitly support writing 0x27E7 as
"Pumpenleistung Minimal". Their write path uses the normal P300
`Virtual_WRITE` function code 0x02.

The P300 protocol separately defines `EEPROM_WRITE` as function code 0x06.
This proves that a host write to 0x27E7 is not itself an explicit raw
EEPROM_WRITE transaction. It does **not**, however, prove that the controller
does not persist the virtual coding value internally after processing the
Virtual_WRITE.

Because E7 is a service coding rather than a volatile runtime setpoint, repeated
flame-by-flame rewriting of E7 should not be used as a permanent control policy
until persistence/write-endurance semantics are established.

### Coding 51: conceptually exact, but absent from the local exact profile

Later/other HO1-family profiles expose:

```text
0x7751  coding 51  K51_KonfiHydrWeicheIntPumpe
```

Viessmann documentation for controllers that support it defines the relevant
mode as:

- 51:0: with hydraulic separator, internal circulation pump runs whenever there
  is a heat request;
- 51:1: with hydraulic separator, internal circulation pump runs only while the
  burner is operating, followed by pump overrun;
- some generations additionally use 51:2 for buffer-tank topology with similar
  burner-dependent pump operation.

This is conceptually extremely close to the desired behavior, especially in
combination with coding 31 as the boiler-circuit-pump speed target.

However:

1. coding 51 is **not present** in the exact base VDensHO1 Vitosoft profile used
   by the local WB2A;
2. the exact WB2A service coding table exposes coding 52 (hydraulic-separator
   sensor) but not coding 51;
3. coding 51 is explicitly tied to a boiler-circuit-pump topology with hydraulic
   separator or buffer tank, whereas the local installation is a single direct
   radiator circuit with no separator.

Therefore 0x7751 must not be written on the local boiler based on cross-profile
semantics.

A read-only probe has been added for both:

```text
0x7751  latent K51 candidate
0x7752  exact K52 hydraulic-separator sensor coding
```

The purpose is only to determine whether the address space exists on the local
firmware. Even a readable value at 0x7751 would not establish that coding 51 is
supported or safe in the direct A1 topology.

## Read-only result for latent coding 51 — 2026-09-23

The local WB2A was queried directly:

```text
r;0x7751;1 -> 3;0x7751;01
r;0x7752;1 -> 1;0x7752;00
```

In the optolink-splitter VS2/P300 stack return code 0x01 means success and
0x03 means an **Error Message** response from the controller. The payload byte
`01` in the 0x7751 error response is not decoded here as a specific error
reason.

Thus:

- 0x7752 is a valid readable WB2A virtual datapoint and currently equals 0,
  consistent with coding 52 = no hydraulic-separator sensor;
- 0x7751 does not behave as a valid readable virtual datapoint on this local
  controller. The controller actively returns a protocol error rather than a
  value.

This strongly confirms the exact Vitosoft/service-manual result that coding 51
is not implemented/exposed on this WB2A profile. No write to 0x7751 should be
attempted.

The cross-profile coding-51 idea is therefore closed for the local direct A1
system. The remaining practical paths are static E7=100, a safe dynamic E7
strategy if persistence/endurance can be proven acceptable, or a topology
change that turns the internal pump into a boiler-circuit pump.

## WB2A service display unlock: coding 8A — 2026-09-23

The user recalled a service setting that exposes datapoints/codings which are
normally hidden. This is confirmed as coding **8A**.

The exact generated VDensHO1 catalog contains:

```text
0x778A  K8A_KonfiAnzeigebedingungenAktiv
0xAF    175 = display/configuration conditions active
0xB0    176 = display/configuration conditions inactive
```

Viessmann documentation for this controller family describes:

```text
8A:175  show only codings applicable to the detected plant/accessories
8A:176  show all/otherwise suppressed coding addresses
```

A WB2A-specific service case also documents the procedure
`8A:175 -> 176` to expose suppressed addresses before a coding-plug reread,
then restoring 8A to 175 afterwards.

This distinction is important:

- 8A changes which coding addresses are *shown/eligible in the service UI*;
- it does not necessarily implement firmware functionality that the controller
  does not have.

A second WB2A-specific case demonstrates this limit: after setting 8A:176, a
requested coding address 66 still did not appear on that controller.

Therefore coding 51 must be tested under 8A:176 before being closed completely,
but 8A:176 cannot be assumed to make 0x7751 valid.

### Safe test plan for coding 51

1. Read and record 0x778A.
2. At the local WB2A service menu, change only coding 8A from 175 to 176.
3. Do **not** alter coding 7C; 7C is used for coding-plug reread/master-reset
   procedures and is unrelated to this test.
4. Check whether coding address 51 appears in coding level 2.
5. While 8A=176, read 0x7751 and 0x7752 via Optolink.
6. Restore 8A to 175.
7. Re-read 0x778A to confirm restoration.

No write to 0x7751 is justified even if the address becomes visible/readable;
first establish its exact WB2A semantics.

### Additional read-only service probes

The logger configuration snapshot now also includes:

```text
0x778A  display-condition/service-unlock state
0x778B  K8B "EEPROM Status"
0x778C  software-version MSB
0x778D  software-version LSB
```

The 0x778B object may help characterize configuration persistence/status, but
its exact runtime semantics are not yet established and it should not be used
as a write target.

## XRAM/RAM-shadow search — 2026-09-23

The P300 function-code table confirms distinct access classes:

```text
Virtual_READ   = 0x01
Virtual_WRITE  = 0x02
EEPROM_READ    = 0x05
EEPROM_WRITE   = 0x06
XRAM_READ      = 0x31
XRAM_WRITE     = 0x32
```

A targeted search of the available Vitosoft metadata found no pump-related
event and no E7-equivalent event whose declared access method is XRAM_READ or
XRAM_WRITE. In particular, no metadata link was found between XRAM access and:

- 0x27E7 / A1 E7;
- 0x7663 / A1 runtime pump demand;
- 0x7660 / internal-pump runtime speed;
- K31 / internal boiler-pump target.

Therefore there is currently no documented Vitosoft RAM-shadow setpoint that
could safely replace dynamic E7 coding writes.

This does not prove that the controller firmware has no internal RAM variable;
it only means such a variable is not exposed through the known Vitosoft event
model. Blind XRAM scanning/writing is not justified at this stage.

Priority before lower-level RAM reverse engineering:

1. use the controller-supported coding-8A display-unlock mechanism;
2. determine whether additional WB2A pump codings become visible;
3. only if that fails, consider read-only differential RAM/XRAM mapping with
   known-safe ranges and no writes.

### Coding 8A baseline on local WB2A

Read-only baseline before enabling suppressed-address display:

```text
0x778A = AF  -> 8A:175, display/configuration conditions active
0x778B = 00  -> K8B EEPROM status object = 0
0x778C = 01
0x778D = 03  -> controller software version 01.03
```

This confirms the local controller is currently in the normal filtered coding
display state and independently reconfirms software version 01.03.

Next controlled step: change only coding 8A from 175 to 176 at the boiler
service menu, then check whether coding 51 appears and whether 0x7751 changes
from protocol error to a successful read. Restore 8A to 175 immediately after
the check.

### Coding 8A unlock result: coding 51 remains unavailable

Controlled Optolink test:

```text
baseline:
  0x778A = AF   (8A:175)
  0x7751 -> protocol error 3;0x7751;01

write 8A:176:
  write ACK
  0x778A = B0

while 8A:176:
  0x7750 = 03
  0x7751 -> protocol error 3;0x7751;01
  0x7752 = 00
  0x778B = 00

restore 8A:175:
  write ACK
  0x778A = AF
  0x778B = 00
```

Therefore disabling the coding-display conditions does not make virtual address
0x7751 readable on the local WB2A. 0x7752 remains normally readable in the same
state. Coding 51 is thus not merely hidden by the service UI filter; the local
controller rejects the virtual datapoint even while suppressed-address display
is enabled.

The coding-51 path is closed for this controller. No write to 0x7751 is
justified.

The fact that 0x778B stayed 0 across the 8A writes does not prove that no
nonvolatile write occurred. Any busy/status indication could be shorter than
the one-second post-write sampling delay, and the exact K8B status semantics
remain undocumented.

Vitosoft additionally exposes:

```text
0x778E  K8E_I2C_FehlerEEPROM_GWG
        "I2C Fehlerflag EEPROM GWG"
```

This is a read-only diagnostic flag and can be monitored during further
configuration-write experiments, but it is an error flag rather than a write
counter.

### Local 0x778E baseline: value 0x03

Direct read on the local WB2A returned:

```text
0x778E = 03
```

The exact VDensHO1 metadata names this object
`K8E_I2C_FehlerEEPROM_GWG` ("I2C Fehlerflag EEPROM GWG"), but exposes it as
a raw byte with no enum/bit-value definition.

Therefore 0x03 must **not** be interpreted as "EEPROM fault present" or as a
boolean true value. For persistence experiments, 0x778E is only usable as an
opaque diagnostic byte whose baseline is 0x03; the useful observation is
whether it changes around a configuration write.

The guarded E7 persistence probe has been updated accordingly: it records the
existing 0x778E baseline and compares subsequent values without assuming a
zero/one error semantic.

## Virtual_WILO_* re-evaluation — 2026-09-23

A previously noted hypothesis linked local coding 30 value `0x5730 = 01` to a
Wilo-specific internal-pump interface. That inference was too strong and has
been corrected.

Exact semantics of coding 30 in the VDensHO1 data model are:

```text
0 = stufig
1 = drehzahlgeregelt
2 = drehzahlgeregelt mit Volumenstrom
```

Thus `0x5730 = 01` identifies only a speed-controlled internal pump. It does
**not** identify the pump manufacturer as Wilo.

P300/Vitosoft does define protocol function codes:

```text
Virtual_WILO_READ  = 36 / 0x24
Virtual_WILO_WRITE = 37 / 0x25
```

However, the currently available Vitosoft/event evidence does not bind these
function codes to the WB2A internal-pump datapoints:

```text
0x5730  coding 30 internal-pump type
0x5731  coding 31 internal-pump target speed
0x7660  internal-pump runtime speed/output
0x7663  A1 runtime/calculated pump demand
```

Concrete "Wilo" references found in the extracted Vitosoft material concern
other areas such as Vitocom/Wilo management and Wilo diverter-valve
configuration, not the WB2A internal circulation-pump speed path.

Therefore Virtual_WILO_WRITE must not be used as an assumed direct internal-pump
override. It remains only a protocol-level capability until an exact event or
address/function-code binding for VDensHO1 is found.

Current status:

- interesting protocol primitive: yes;
- proven relevant to local WB2A internal pump: no;
- safe candidate for experimental write: no.

The preferred research direction remains finding an exact volatile/runtime
pump-control object or proving the storage semantics of the normal coding path.


### Virtual-WILO exact-profile result

The complete production `DPDefinitions.xml -> ecnEventType.xml` join for the
exact local `VDensHO1` profile contains **581 events**. Its access-function
distribution contains:

```text
FCRead:
  Virtual_READ
  GFA_READ
  Remote_Procedure_Call
  blank / undefined

FCWrite:
  Virtual_WRITE
  Remote_Procedure_Call
  blank / undefined
```

There are **zero** VDensHO1 events whose access metadata uses:

```text
Virtual_WILO_READ
Virtual_WILO_WRITE
```

This is the strongest current evidence against the idea that the WB2A internal
pump is exposed through the P300 Wilo function codes.

In particular, the known internal-pump objects remain ordinary VDensHO1
virtual objects:

```text
0x5730  coding 30 / internal-pump type
0x5731  coding 31 / internal-pump target
0x7660  internal-pump output + speed
0x0A54  internal-pump software-index block
```

None of these is bound by Vitosoft metadata to `Virtual_WILO_READ` or
`Virtual_WILO_WRITE`.

This means the Wilo FCs must be treated as a separate protocol namespace or
gateway/device mechanism, not as an alternate FC that can simply be substituted
for `Virtual_READ` on the normal WB2A pump addresses.

### What the global Wilo references actually show

The global Vitosoft/reference material contains at least two Wilo-related
families which are distinct from the WB2A internal-pump runtime path:

1. **Vitocom Wilo management**
   - Vitosoft contains a dedicated `Wilo Management` group in the
     `Vitocom300_LAN` profile.
   - The Vitosoft conversion vocabulary also contains
     `Vitocom300SGEinrichtenKanalWILO`, alongside equivalent LON and MBUS
     channel-setup conversions.
   - This strongly suggests a communication/gateway use case for at least part
     of the Wilo protocol support.

2. **Coding-plug Wilo diverter-valve parameters**
   - the global event set contains `GWGB0..GWGBA` parameters labelled
     `Wilo UV ...`;
   - these describe a Wilo **Umschaltventil** actuator calibration/positioning
     family, not the internal circulation-pump speed command.

Therefore a textual match on `Wilo` must not be promoted to an internal-pump
control path without an exact EventType/FC/device binding.

### New metadata extractor support

The repository Vitosoft extractor now has an optional global Wilo inventory:

```bash
python3 tools/extract-vitosoft-project-data.py \
  --data-dir /path/to/vitosoft/XML \
  --device VDensHO1 \
  --out-dir /tmp/vitosoft-wilo \
  --include-global-wilo
```

Additional output:

```text
virtual-wilo-events.csv
```

The CSV records every global event whose low-level metadata uses
`Virtual_WILO_READ` or `Virtual_WILO_WRITE`, including:

- event ID and token;
- numeric address;
- read/write FC;
- prefixes;
- block length and byte/bit positions;
- conversion/type information;
- the Vitosoft device types to which the event is linked.

The extraction summary also reports:

```text
virtual_wilo_event_count
global_virtual_wilo_event_count
global_virtual_wilo_read_count
global_virtual_wilo_write_count
global_virtual_wilo_devices
```

For the exact `VDensHO1` device, `virtual_wilo_event_count` is expected to
remain zero based on the already validated 581-event production join.

### Safe next step

Do **not** send raw function `0x24` probes to guessed addresses yet.

The next read-only step is metadata-first:

1. run the new `--include-global-wilo` extraction against the preserved
   production Vitosoft XML set;
2. inspect `virtual-wilo-events.csv`;
3. identify whether any real `Virtual_WILO_READ` event belongs to a boiler,
   pump or HO1-family device rather than Vitocom/gateway equipment;
4. only if such an event exists, reproduce its exact Vitosoft request shape:
   address, block length and any `PrefixRead`;
5. then consider a single read-only hardware probe of that **known** event.

No `Virtual_WILO_WRITE` hardware experiment is justified at this stage.

### Current conclusion

For the local WB2A / VDensHO1 01.03, the Virtual-WILO route is currently a
**negative result for direct internal-pump control**:

- the protocol function codes exist;
- the exact VDensHO1 profile does not use them;
- the internal-pump objects use the normal virtual access path;
- known Wilo references point to separate Vitocom/gateway and diverter-valve
  contexts.

The Wilo path remains worth cataloguing globally, but it is no longer a leading
candidate for the desired volatile 100 % heating-burner pump override unless
the global event inventory reveals an exact pump-specific event that is also
usable by this controller generation.


## E7 persistence/status probe result — 2026-09-23

A guarded minimal-write probe was executed while the burner flame was off and
DHW was inactive.

Sequence:

```text
baseline:
  E7    = 100 %
  0x778B = 0x00
  0x778E = 0x03

temporary write:
  E7 100 -> 99 %
  write completed at approximately +0.10 s
  first 778B/778E sample at approximately +0.52 s
  20 post-write samples through approximately +7.65 s:
    0x778B remained 0x00
    0x778E remained 0x03
  E7 readback at approximately +7.75 s = 99 %

restore:
  E7 99 -> 100 %
  20 post-restore samples through approximately +15.69 s:
    0x778B remained 0x00
    0x778E remained 0x03

final:
  E7    = 100 %
  0x778B = 0x00
  0x778E = 0x03
```

### What this proves

- the normal `Virtual_WRITE` path changes E7 immediately enough that the new
  value is readable back after the write;
- the original value was restored successfully;
- no persistent change of the observed diagnostic bytes `0x778B` or
  `0x778E` was seen during either observation window.

### What this does not prove

This does **not** establish that E7 is RAM-only or that the write causes no
nonvolatile-memory operation.

The first diagnostic sample was only obtained roughly 0.4 s after the write
completed. Any short EEPROM-busy/status pulse could therefore have occurred
before the first sample. More importantly, the exact semantics of
`K8B EEPROM Status` remain unknown, and `0x778E` is only an opaque I2C
diagnostic byte with local baseline `0x03`.

The test also did not include a controller reboot/power cycle while E7 held the
temporary value, so persistence across restart was not tested.

### Engineering consequence

The result removes one possible warning sign: there is no long-lived 778B/778E
status change associated with a single E7 Virtual_WRITE.

It is still insufficient evidence to justify rewriting E7 on every burner
cycle. Until persistence/endurance is resolved independently, E7 remains a
configuration/coding path rather than a proven volatile runtime setpoint.


## Global Virtual-WILO production inventory — 2026-09-23

The new global Wilo extractor was run against the preserved local production
Vitosoft installation.

The source files exactly match the hashes already recorded in
`research/vitosoft/source-manifest.json`:

```text
DPDefinitions.xml
  size   186559004
  SHA256 efec27568d398021c767771af016143bd51fc196d2d408dbb80faff84d0b19e3

ecnEventType.xml
  size   9935374
  SHA256 2338beb0e8544b6149bc4b2433ecabd9509edcdafc2e8e91f00182eba1aff7ba

Textresource_de.xml
  size   29764414
  SHA256 bd760a53bcf5058560677d4fdd52b557afbc4e2200cede966a944acc9c7ac2dd
```

The exact VDensHO1 result is unchanged:

```text
VDensHO1 events             581
VDensHO1 Virtual_WILO_READ    0
VDensHO1 Virtual_WILO_WRITE   0
```

The global production inventory contains:

```text
Virtual_WILO_READ events    74
Virtual_WILO_WRITE events    9
linked Vitosoft devices      WILO only
```

This is decisive device-binding evidence: every real Vitosoft event using the
Wilo-specific P300 function codes is linked to the separate datapoint/device
profile named `WILO`, not to `VDensHO1`.

### Wilo transport shape

All 74 global Wilo events share the same Vitosoft virtual base address:

```text
0xA0C2
```

The individual Wilo value is selected by `PrefixRead`. Examples:

| Event | Meaning | PrefixRead | BlockLength | Value position |
| ---: | --- | --- | ---: | --- |
| 6070 | Drehzahl | `0007` | 6 | bytes 4..5 |
| 6108 | Pumpentyp | `0011` | 5 | byte 4 |
| 6139 | aktueller Pumpenzustand | `0027` | 6 | bytes 4..5 |
| 6106 | Pumpenbefehl | `0028` | 5 | byte 4 |
| 6114 | Regelungsart der Pumpe | `002A` | 5 | byte 4 |
| 6121 | Sollwert | `0001` | 6 | bytes 4..5 |

The write-capable events are also explicit. For example:

```text
Pumpenbefehl:
  FCWrite     Virtual_WILO_WRITE / 0x25
  PrefixWrite 002801

Regelungsart:
  FCWrite     Virtual_WILO_WRITE / 0x25
  PrefixWrite 002A01

Sollwert:
  FCWrite     Virtual_WILO_WRITE / 0x25
  PrefixWrite 000132
```

These write forms are recorded only as protocol evidence. They must **not** be
sent to the local boiler.

### Independent Wilo-PLR correlation

The open-source WiloPLR protocol implementation independently defines the same
numeric parameter IDs:

```text
measurement SPEED             = 7   -> 0x07
measurement PUMP_TYPE         = 17  -> 0x11
measurement STATE_DIAGNOSTICS = 39  -> 0x27

command PUMP_COMMAND           = 40  -> 0x28
command OPERATION_MODE         = 42  -> 0x2A
command SETPOINT               = 1   -> 0x01
```

These values exactly match the Vitosoft `PrefixRead` selectors above.

This establishes that `Virtual_WILO_READ/WRITE` is not merely a generic
alternate Virtual access class. Vitosoft is tunnelling the actual **Wilo PLR
pump protocol** through the common P300 object at `0xA0C2`.

### Consequence for the WB2A internal pump

The architecture is now best represented as:

```text
VDensHO1 internal-pump model:
  0x5730 / 0x5731 / 0x7660 / 0x0A54
  -> ordinary Virtual_READ / Virtual_WRITE
  -> no Virtual_WILO event binding

separate Vitosoft WILO profile:
  0xA0C2 + PLR selector prefix
  -> Virtual_WILO_READ / Virtual_WILO_WRITE
  -> Wilo PLR pump
```

Therefore there is currently **no metadata basis** for treating
`Virtual_WILO_WRITE` as a volatile override for `0x7660` or E7.

A remaining narrow question is whether the local WB2A firmware nevertheless
implements the Wilo tunnel and routes it to an attached/internal Wilo pump.
That can be tested without writes because the exact Vitosoft read shape is now
known.

### Exact read-only hardware probe

Use the generic splitter request mapping:

```text
request;<function-code>;<address>;<BlockLength>;<PrefixRead>;<protocol-id>
```

Start with pump type because it is a one-byte identification value:

```bash
/usr/local/bin/optolink-debug request \
  "request;0x24;0xA0C2;5;0011;0x00"
```

If that returns a successful Wilo-shaped response, follow with speed and
diagnostic state:

```bash
/usr/local/bin/optolink-debug request \
  "request;0x24;0xA0C2;6;0007;0x00"

/usr/local/bin/optolink-debug request \
  "request;0x24;0xA0C2;6;0027;0x00"
```

These are exact Vitosoft-derived `Virtual_WILO_READ` events. They contain no
write operation.

Interpretation boundary:

- protocol error / no response: supports the conclusion that the local
  VDensHO1 controller does not expose a Wilo PLR endpoint;
- successful response: proves only that the Wilo tunnel is implemented and a
  target responds; it does **not** yet prove that the responding Wilo pump is
  the physical WB2A internal circulation pump;
- correlation of returned speed with `0x7660[1]` across 50 % and 100 % states
  would then be required to establish identity.

No `0x25 Virtual_WILO_WRITE` test is justified before that identity is proven.


## Local Virtual-WILO read probe — successful empty responses

Three exact Vitosoft-derived `Virtual_WILO_READ` requests were executed
read-only on the local WB2A:

```text
request;0x24;0xA0C2;5;0011;0x00  # pump type
-> 1;0xa0c2;none

request;0x24;0xA0C2;6;0007;0x00  # speed
-> 1;0xa0c2;none

request;0x24;0xA0C2;6;0027;0x00  # diagnostic state
-> 1;0xa0c2;none
```

The splitter implementation resolves the meaning of `none` precisely.

For generic `request` commands it calls `do_request()`, then formats the
result as:

```python
val = utils.arr2hexstr(data) if data else "none"
```

and `receive_telegr()` returns retcode `0x01` only after a complete
CRC-valid non-error VS2 response telegram has been received.

Therefore:

```text
1;0xa0c2;none
```

means:

- VS2 ACK/response handling succeeded;
- the response address was `0xA0C2`;
- the response was not an Error Message;
- CRC validation succeeded;
- the decoded response contained zero payload bytes.

It does **not** mean timeout, NACK, protocol error or a failed MQTT parse.

The same successful-empty result for three independent, valid Wilo-PLR
selectors strongly suggests that the WB2A firmware recognizes/accepts the
`Virtual_WILO_READ` service at the P300 layer, but has no Wilo-PLR payload to
return for the local system. This is compatible with the production metadata,
where all real `Virtual_WILO_*` events belong only to the separate `WILO`
device profile and none belong to `VDensHO1`.

This was subsequently confirmed at wire level with the splitter full-raw path;
see the next section.

No `Virtual_WILO_WRITE / 0x25` operation is justified.


### Full-raw confirmation frames

The exact full VS2 requests corresponding to the three generic read-only Wilo
probes are:

```text
pump type:
41 07 00 24 A0 C2 05 00 11 A3

speed:
41 07 00 24 A0 C2 06 00 07 9A

diagnostic state:
41 07 00 24 A0 C2 06 00 27 BA
```

The final byte in each line is the VS2 modulo-256 checksum.

Using the splitter full-raw request path preserves the complete slave response,
including ACK, header, returned BlockLength and CRC:

```bash
/usr/local/bin/optolink-debug request "41070024A0C2050011A3"
/usr/local/bin/optolink-debug request "41070024A0C20600079A"
/usr/local/bin/optolink-debug request "41070024A0C2060027BA"
```

These commands are byte-for-byte equivalent read requests to the already
executed generic requests; they do not perform a write.

### Full-raw hardware result

The local WB2A returned:

```text
request:
41 07 00 24 A0 C2 05 00 11 A3
response:
06 41 05 01 24 A0 C2 05 91

request:
41 07 00 24 A0 C2 06 00 07 9A
response:
06 41 05 01 24 A0 C2 06 92

request:
41 07 00 24 A0 C2 06 00 27 BA
response:
06 41 05 01 24 A0 C2 06 92
```

The returned frames are checksum-valid.

For the first response:

```text
06          VS2 ACK
41          STX
05          payload/package length
01          LDAP + ResponseMessage
24          Virtual_WILO_READ
A0 C2       address
05          requested Wilo block length echoed back
91          checksum
```

The two 6-byte requests have the same shape and echo `06` in the final
header field.

Important detail: the response package length is only `05`, i.e. it contains
exactly the mandatory five VS2 message fields after the length byte and **no
additional data bytes**. The nominal block-length field nevertheless contains
the requested `05` or `06`.

Thus the Wilo response is not shaped like an ordinary successful
`Virtual_READ` carrying BlockLength data bytes. It is best treated as a
Wilo-command-specific acknowledgement/empty response whose header echoes the
request, not as a decoded pump value.

This also explains the splitter result `1;0xa0c2;none`: its parser validates
the packet CRC and message identifier, then extracts bytes after the fixed
header. There are none.

The full-raw receive helper ends after approximately 50 ms of serial silence
once data has arrived. Therefore these captures alone do not mathematically
exclude a later asynchronous Wilo telegram. No source found so far documents
such a second-stage response for this Vitosoft command, however.

### External architecture corroboration

The separate Vitosoft `WILO` profile is identified as device ID `0x0700`
in another Vitosoft-derived device index. That is distinct from the local
`VDensHO1 = 0x20C2`.

External product documentation also matches the global Vitosoft model:

- Wilo describes PLR as a point-to-point pump communications protocol requiring
  a physical interface per pump.
- Viessmann Vitocom 300 documentation describes external Wilo pump integration
  via the Wilo-Digicon converter: PLR on the pump side, RS485 on the Vitocom
  side, with multiple separately connected Wilo pumps.

References:

- https://wilo.com/pl/pl/Narz%C4%99dzia/Cenniki-i-dokumentacja-techniczna/Automatyka-budynku/Protok%C3%B3%C5%82-Wilo-PLR/
- https://www.manualslib.de/manual/104099/Viessmann-Vitocom-300.html?page=9
- https://www.manualslib.de/manual/104099/Viessmann-Vitocom-300.html?page=15

Combined with the exact VDensHO1 metadata containing zero
`Virtual_WILO_*` events, the local empty Wilo responses make this path a very
poor candidate for the WB2A internal circulation pump.

### Virtual-WILO disposition

For the practical research goal, the Wilo path is now considered **closed as a
direct runtime-pump-control candidate**:

- `0x24/0x25` are real Wilo-PLR tunnel functions;
- their production events belong to the separate `WILO` device profile;
- `WILO` is a separate `0x0700` device class, not `VDensHO1 0x20C2`;
- exact local `0x24` reads return only empty acknowledgement-shaped frames;
- none of the VDensHO1 internal-pump events is bound to the Wilo FCs.

Do not test `Virtual_WILO_WRITE / 0x25` on the WB2A.

Further Wilo work would now be protocol archaeology rather than a promising
route to the desired burner-dependent 100 % internal-pump override.


## Next priority after Virtual-WILO: internal pump / KM-BUS identity

The production VDensHO1 metadata exposes the internal pump as a KM-BUS-related
diagnostic participant even though the exact VDensHO1 profile has no direct
`KMBUS_*` event-function bindings:

```text
0x0A54  SWIndex_IntPumpe
        "Interne Pumpe Software-Index"
        Virtual_READ
        BlockLength 4

0x0A35  KM_Error_PumpeIntern
        "KM-Bus-Fehler Interne Pumpe"
        Virtual_READ
        BlockLength 1

0x27E5  KE5_KonfiKennung_D_PumpeA1M1_KM
        "KM-BUS-Heizkreispumpe A1"
        Virtual_READ / Virtual_WRITE
        BlockLength 1

0xA152  nvoRelayState_Interne_Pumpe
        "Relais-Status Interne Pumpe"
        Virtual_READ
        BlockLength 2
        internal-pump flag at bit 2
```

This makes the KM-BUS/internal-pump path a more plausible next research target
than `Virtual_WILO`.

First step remains read-only:

```bash
/usr/local/bin/optolink-debug request "r;0x0A54;4;raw;False"
/usr/local/bin/optolink-debug request "r;0x0A35;1;raw;False"
/usr/local/bin/optolink-debug request "r;0x27E5;1;raw;False"
/usr/local/bin/optolink-debug request "r;0xA152;2;raw;False"
```

Purpose:

- `0x0A54`: determine whether the controller reports a real software index for
  the internal pump participant;
- `0x0A35`: establish the current KM-BUS internal-pump error baseline;
- `0x27E5`: establish the A1 KM-BUS pump identification/coding state;
- `0xA152`: capture the relay/output status block for later correlation with
  burner and pump states.

These reads do not alter any coding or pump command.


## Installed pump identity clarification — 2026-09-23

The physically installed internal pump is:

```text
Viessmann spare part: 7876412
designation:          G-HE KM-Bus
pump family:          Grundfos UPM3
interface:            KM-Bus
```

This is important because the earlier Virtual-WILO investigation must **not**
be read as detection of the installed pump manufacturer.

The `WILO` information came from the **global Vitosoft metadata**, where a
separate device profile named `WILO` uses `Virtual_WILO_READ/WRITE` and
Wilo-PLR selectors. It did not come from a successful Optolink identification
of the local physical pump.

The local `0x24` Optolink probes only established that VDensHO1 returns
checksum-valid empty acknowledgement-shaped responses for those Wilo requests.
They returned no manufacturer, type or speed payload.

Independent corroboration:

- Viessmann community/parts compatibility references identify 7876412 as
  `UPM3 G-HE KM Bus` and as a compatible KM-Bus replacement for WB2A-era
  appliances.
- Grundfos documents UPM3 as an OEM high-efficiency circulator family with
  externally controlled variants including **KMBus**.

Sources:

- https://community.viessmann.de/t5/Gas/Umwaelzpumpe-fuer-Vitodens-200-WB2/td-p/250593
- https://community.viessmann.de/t5/Gas/Pumpentausch-Vitodens-200/m-p/292674
- https://api.grundfos.com/literature/Grundfosliterature-5564187.pdf

### Consequence

Do **not** change the WB2A to the Vitosoft `WILO` device profile or attempt to
enable `Virtual_WILO` because of the installed pump.

The installed 7876412 is controlled through KM-Bus. The fact that the existing
system already reacts correctly to E7 changes and reports an internal
speed-controlled pump means the controller/pump relationship is already active
enough for the current investigation.

Any remaining configuration question should be investigated through the
VDensHO1/KM-Bus pump objects (for example `0x0A54`, `0x0A35`, `0x27E5`,
`0x5730`, `0x7660`) rather than by switching protocol families.
