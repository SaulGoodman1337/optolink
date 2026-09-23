# Device / controller / GFA: VDensHO1 20C2 on Vitodens 200-W WB2A

## Identity

Measured read-only over Optolink:

| Address | Raw | Interpretation |
| --- | --- | --- |
| `0x00F8` | `20c2` (first two bytes) | VDensHO1 device ID |
| `0x00F9` | `c2` | controller identification byte |
| `0x00FB` | `03000001` | software-index area; field encoding still unresolved |
| `0x7650` | `2002061501ff` | GFA / combustion-controller chip identification |
| `0x8853` | `02` | modulating burner |

The exact sub-field encoding of `0x7650 = 20 02 06 15 01 ff` is not yet known.

## 0x55D3 runtime block

A read of eleven bytes from `0x55D3` exposes several useful live values in one Optolink transaction:

```bash
/usr/local/bin/optolink-debug request "r;0x55D3;11;raw;False"
```

Hardware-verified on this appliance:

- byte 5, mask `0x20`: flame present
- byte 5, mask `0x40`: GFA lockout

Observed runtime-state bytes:

- bytes 6 and 7 must be treated as **separate state/bitfield bytes**, not as one
  big-endian 16-bit numeric value. The earlier blower-rpm interpretation is
  rejected.
- byte 10 / address `0x55DD`: status patterns observed as `01`, `09`,
  `29`, `21`; individual bits are only partly decoded.

A high-resolution 2026-09-22 start captured this byte-5/6/7 state sequence:

```text
b5 b6 b7   observed phase
01 00 00   idle
01 08 20   pre-purge / startup preparation
09 0c 40   ignition sequence
09 0f 50   ignition sequence, later sub-step
29 0b 60   flame detected / establishment
21 0b 60   stable flame
21 0b 62   stable firing, later sub-state
```

This staged progression explains why interpreting `0x0B60` and `0x0B62`
as 2912/2914 rpm was misleading: the two bytes encode state transitions and
remain nearly unchanged while actual modulation falls from 66 % to 33 %.

### 0x55DC modulation

Byte 9 / address `0x55DC` is now hardware-correlated with Vitosoft's
`0xA305` Modulationsgrad:

- `55DC=66` corresponds to `A305 raw=132 -> 66.0 %`
- `55DC=60` corresponds to `A305 raw=120 -> 60.0 %`
- `55DC=50` corresponds to `A305 raw=100 -> 50.0 %`
- `55DC=33` corresponds to `A305 raw=66 -> 33.0 %`

Across the 2026-09-22 single-session run, the two values track essentially
1:1. Small transient differences of one or two percentage points occur because
the two Optolink reads are sequential and typically about 0.12-0.30 s apart.

Conclusion: `0x55DC` is a directly usable live modulation percentage on this
controller. `0xA305` carries the same quantity with raw scale `0.5 %/LSB`.

## 0xA305 modulation datapoint

Vitosoft identifies `0xA305` as `nvoBoilerState_BLR_value / Modulationsgrad`.

The scale factor is hardware-verified as:

```text
percentage = raw_byte * 0.5
```

The 2026-09-22 single-session measurement proved that this percentage tracks
`0x55DC` almost exactly throughout the full startup ramp. This resolves the
previous uncertainty about whether `0x55DC` and `0xA305` represented
different control layers: for this controller they expose the same live
modulation quantity in different encodings.

The `0x55DC <-> 0xA305` equivalence was established with the
single-session logger. The logger has since moved on to the next experiment
and now samples `0x55D3` together with `0x0810` boiler temperature.

## Measured burner-start behavior

Representative single-session high-resolution start on 2026-09-22:

```text
before flame: 55DD 01 -> 09
T= 0.00 s  55DC=66  A305= 0 %  55DD=29
T= 0.55 s  55DC=66  A305=66 %  55DD=29
T= 1.02 s  55DC=66  A305=66 %  55DD=21
...
T=12.56 s  55DC=66  A305=66 %
T=13.12 s  55DC=65  A305=65 %   <- sustained ramp begins
...
T=25.63 s  55DC=50  A305=50 %
...
T=44.70 s  55DC=33  A305=34 %
T=45.17 s  55DC=33  A305=33 %
```

Observed phases:

1. `0x55DD` changes `01 -> 09 -> 29 -> 21` around ignition/flame establishment.
2. From first normal `0x21` state at about T=1.02 s, modulation remains at
   66 % until the sustained fall begins at T=13.12 s: about **12.1 s**.
3. `A305` then falls from 65 % at T=13.12 s to 33 % at T=45.17 s:
   32 percentage points in 32.05 s, essentially **1 percentage point/s**.
4. Modulation then remains at 33 % if the hydraulic system can absorb the heat.

The roughly 12 s regulation delay and approximately 1 %/s ramp-rate limit are
not yet mapped to a specific controller/GFA parameter.

## Flame-stabilization / high-start-power problem

This is a distinct project problem and should not be conflated with the
240-second RKR startup optimization.

Measured locally:

~~~text
flame establishment:
  modulation command about 65-66 %

hold:
  about 12 s at about 65-66 %

down-ramp:
  about 1 modulation percentage point/s

steady heating floor:
  about 33 %
~~~

External Viessmann statements for comparable Vitodens generations describe a
roughly 60-70 % burner start level as being fixed by the Kesselcodierstecker
for **Startsicherheit / Flammenstabilisierung**, and state that limiting maximum
heating power does not lower this startup level.

This matches the local WB2A behavior closely enough to make the coding-plug/GFA
parameter layer a primary research target, but it does not prove the exact
storage field on 20C2.

Current model of the problem:

~~~text
burner start
    |
    v
high fixed startup modulation (~65-66 %)
    |
    | about 12 s hold
    v
controlled downward ramp (~1 %/s)
    |
    v
normal minimum/required modulation (~33 %)
~~~

If the hydraulic system cannot absorb the startup heat before the controller
reaches the lower modulation range, boiler temperature rises rapidly and the
burner can stop/takt during the startup phase.

### What we want to identify

Read-only research should distinguish at least three separate quantities:

1. **startup modulation/start power** -- likely associated with flame
   stabilization;
2. **regulation delay after flame establishment** -- locally about 12 s;
3. **downward modulation slew/ramp limit** -- locally about 1 percentage
   point/s.

They may be three separate parameters or partly fixed GFA firmware behavior.

Known coding-plug values do not yet resolve them:

- GWG73 = 24 * 10 s = 240 s is the RKR/startup-optimization duration and is
  **not** the 12 s flame-stabilization hold;
- GWG32/GWG71 explain the 29 % heating-power ceiling/minimum-power convergence,
  not the 65-66 % startup level;
- GWG91..GWG9A explain the burner characteristic and the 33 % modulation floor,
  not the startup hold duration.

### Could the new KMBUS access help?

Potentially, yes, for **finding and observing** the responsible parameter/state.

The newly verified 0x41/0x43 read paths prove that dedicated KMBUS address
spaces are reachable through Optolink. Together with the still-unexplored
KBUS_* read functions and Vitosoft event metadata, this may expose:

- a GFA/KM-BUS parameter corresponding to startup power;
- a regulation-delay value;
- a startup-state register;
- a mirrored coding-plug field not present in the ordinary 0x10x0 objects.

However, KMBUS_EEPROM_READ has not been shown to address the physical
Kesselcodierstecker, and no write path for these safety-relevant values is
currently established.

### Project boundary: understand, do not bypass combustion safety

The high start level is documented by Viessmann as serving flame stability /
start safety on comparable Vitodens units. Therefore the project goal is to
**identify and understand** the responsible field and to find safe ways to
prevent startup heat from causing cycling.

Do not experimentally reduce, disable or bypass flame-stabilization/start-safety
parameters on a live gas burner.

The practical low-risk mitigation path remains hydraulic/controller-side:

- maximize useful heat removal during the startup plateau;
- verify internal-pump behavior during the first 15-45 s;
- avoid valve/bypass states that immediately return hot supply water;
- compare starts at different known flow conditions.

This is directly supported by the local observation that a higher internal-pump
condition allowed the burner to reach the 33 % modulation floor, whereas the
lower-pump condition correlated with an early stop.

## Pump / hydraulic correlation

Observed internal-pump raw values include:

```text
0132 -> second byte 0x32 = 50
0164 -> second byte 0x64 = 100
```

In captured starts, the lower pump condition correlated with a burner stop before reaching the low-modulation region, while the higher pump condition allowed the burner to reach the floor and continue running.

This is a strong correlation, not proof of causality.

### Open question: DHW forces 100 %, heating mode does not

An additional operational difference needs to be revisited:

- in **DHW preparation**, the internal pump is observed to go automatically to
  100 % while the burner is running;
- in normal **space-heating mode**, the pump does not show the same automatic
  100 % behavior.

This may be highly relevant to the startup/flame-stabilization problem because
the 100 % pump condition improves heat transport exactly during the period in
which burner modulation is initially held near 65-66 %.

The newly verified generic VS2/P300 request path and KMBUS/KBUS read functions
create a new way to investigate this. The next comparison should search for a
mode-dependent internal pump request rather than only watching the final pump
speed.

Candidate classes of state to look for:

~~~text
DHW active / heating active
burner-start state
internal-pump target
internal-pump actual state
pump override / forced speed
minimum/maximum pump limit
boiler-pump demand
hydraulic operating mode
KBus/KM-BUS pump command or data element
~~~

The key experiment is a synchronized comparison of one heating start and one
DHW start, aligned at burner ignition/flame establishment. Any field that
changes only in DHW shortly before the pump reaches 100 % becomes a strong
candidate for the automatic override mechanism.

Do not assume that the already observed 50/100 raw pump value is itself the
controlling request; it may be only the downstream result of another internal
command.

## Open device/GFA questions

1. Decode the fields in `0x7650 = 2002061501ff`.
2. Decode the exact semantics of the separate `0x55D3` bytes 6 and 7
   state/bitfield bytes; the earlier 16-bit blower-rpm interpretation is rejected.
3. Determine whether byte 7 bit `0x02`, which appears about 10 s after flame
   detection, represents a regulation/run sub-state.
4. Identify the source of the approximately 12 s post-flame regulation delay.
5. Identify the internal parameter that generates the approximately
   1 percentage-point/s downward modulation-command ramp.
6. Correlate unresolved GFA bytes 1 and 2 with direct boiler temperature
   `0x0810`.
7. Decode all relevant `0x55DD` status bits.
8. Find an independently documented/verified blower-speed datapoint for this
   exact VDensHO1/20C2 generation.


## Historical hypothesis: candidate origin of the 12 s delay and 1 %/s ramp

> **Superseded:** this section records the earlier search path. Later measurements
> rejected the 100 s actuator explanation, decoded GWG73 as 240 s, and rejected
> the LGM29 `0x0083` map for this WB2A/GG1. See the later sections for the
> current conclusions.

### Regulation delay after burner start

Vitosoft contains a dedicated fire-control/timing parameter named:

```text
Reglerverzögerung nach Brennerstart
GWG_FA_Takt_ReglerverzoegerungStart
```

In the LGM29/GWG datapoint families it is part of the `Taktschutz` group and
is associated with the `0x0083` parameter structure. Some LGM29 variants also
use that same structure for burner-minimum-run-time data, so `0x0083` must
not yet be treated as a proven direct byte mapping on this VDensHO1.

Independent Viessmann service documentation for other controller generations
uses parameter `1B` for:

```text
Zeit vom Zünden des Brenners bis zum Beginn der Regelung
```

with the value expressed in seconds and factory setting dependent on the
coding plug.

This semantic definition matches the measured WB2A behavior extremely well:

```text
first normal 0x21 flame state: about T=1.02 s
sustained modulation decrease: about T=13.12 s
difference: about 12.1 s
```

**Current assessment:** the measured ~12.1 s is very likely a deliberate
regulation-delay parameter or equivalent firmware constant. Its exact storage
location on VDensHO1/20C2 is not yet proven.

### Downward modulation ramp

Viessmann controllers with conventional modulating-burner configuration expose
a parameter named:

```text
Laufzeit Stellantrieb Brenner
```

(commonly coding parameter `15`), expressed as the time for actuator travel
and factory-defined according to the coding plug.

The WB2A measurement gives:

```text
65 % -> 33 %
32 percentage points in 32.05 s
=> 0.998 percentage points/s
```

A full 0..100 % actuator travel time of 100 s would mathematically produce:

```text
100 percentage points / 100 s = 1 percentage point/s
```

which matches the observed ramp almost exactly.

The coding-plug raw block also contains an unresolved byte value `0x64 = 100`
at offset `0x1038`:

```text
0x1030 = 41 be 1d e2 03 fc 51 ae 64 9b 00 ff 00 ff 00 ff
                                      ^^
                                     100
```

Vitosoft currently provides no `GWG38` or other semantic label tying this
specific byte to actuator travel time. Therefore this is an **interesting
correlation, not a proven mapping**.

### Candidate read-only locations to test

Two parameter families deserve read-only probing:

- controller-side conventional coding block around `0x5715..`:
  `15` actuator run time, `1A` startup optimization,
  `1B` regulation delay, `1C` burner start delay in other Viessmann
  controller generations;
- LGM29/GWG fire-control timing structure around `0x0083`, where Vitosoft
  lists `Reglerverzögerung nach Brennerstart` for GWG/LGM29 families.

The VDensHO1-specific datapoint list does **not** expose those names directly,
so any result from these addresses must be treated as an experimental
read-only probe rather than an established VDensHO1 mapping.


## Read-only candidate probe result (2026-09-22 20:10)

The single-session logger probed several addresses whose semantics are known
from other Viessmann controller/GFA families:

```text
0x5715 -> 3;0x5715;01
0x571A -> 3;0x571a;01
0x571B -> 3;0x571b;01
0x571C -> 3;0x571c;01
0x0083 -> 3;0x83;01
0x1038 -> 3;0x1038;01
```

On this VDensHO1/20C2 all of these direct reads are rejected by P300
(retcode 3, payload 01).

Consequences:

1. The conventional-controller addresses `0x5715/1A/1B/1C` cannot be reused
   directly on this controller generation.
2. The LGM29/GWG-family `0x0083` timing structure is likewise not exposed at
   that direct address here.
3. Most importantly, `0x1038` is rejected even though byte offset 8 of a
   valid `read;0x1030;16` block is `0x64`. This proves that the coding-plug
   blocks must not be treated as a flat independently addressable byte range.
   A valid base object can return an internal structure whose member bytes are
   not individually readable as P300 addresses.
4. Therefore earlier notation such as "0x1073 = GWG73" should be understood as
   **byte offset 3 inside the 0x1070 coding-plug object**, unless an independent
   direct-address read proves otherwise.

The measured ~12.1 s delay and ~1 %/s ramp correlations remain valid, but their
storage locations are still unknown.


## RKR power path: 0x555C and 0x55E0

Read-only probing on 2026-09-22 confirmed that two datapoints known from other
Viessmann RKR families are directly readable on this VDensHO1/20C2:

```text
read;0x555C;1 -> success
read;0x55E0;1 -> success
```

Vitosoft names these datapoints:

```text
0x555C  RKR_12PSolleff_Kessel   Kesselsollleistung (effektiv)
0x55E0  RKR_04PIst_Kessel      Brennerleistung
```

The same values can be captured without extra transactions by extending two
already useful structures:

```text
read;0x555A;4
  bytes 0..1 = 0x555A Kesselsolltemperatur (effektiv), little-endian / 10
  byte 2     = 0x555C Kesselsollleistung (effektiv)
  byte 3     = 0x555D unresolved

read;0x55D3;14
  byte 9     = 0x55DC live Modulationsgrad
  byte 10    = 0x55DD status
  byte 13    = 0x55E0 Brennerleistung
```

Example while the burner was off:

```text
0x555C = 00
0x55E0 = 01
0x555A;4 = 3d010000
```

`0x013d = 317` confirms the already-used 0.1 C scale for the effective boiler
temperature setpoint, giving 31.7 C in this sample.

The unit/scaling and off-state behavior of `0x55E0` still need dynamic
correlation. The value `01` while off means it should not yet be assumed to
be a literal percentage.

### Why this matters

The next full startup log will distinguish two architectures:

1. `0x555C` drops quickly to a low target while `0x55E0/0x55DC` ramp down
   slowly -> the approximately 1 %/s limitation is downstream in the
   burner/GFA/actuator path.

2. `0x555C` itself ramps down at approximately 1 %/s and the burner follows
   it -> the ramp is already generated by the boiler controller/RKR.

The single-session logger was updated to use exactly two fast block reads
(`0x55D3;14` and `0x555A;4`) so this comparison does not reduce sampling
resolution relative to the previous two-read logger.


## Correction: 0x555C / 0x55E0 are not usable as power values on VDensHO1/20C2

A full high-resolution burner start on 2026-09-22 showed:

```text
0x555C raw = 0 for the entire run
0x55E0 raw = 1 for the entire run
```

while verified live modulation at `0x55DC` changed from about 66 % down to
33 %. Therefore the Vitosoft labels known from other controller families:

```text
0x555C  RKR_12PSolleff_Kessel  Kesselsollleistung (effektiv)
0x55E0  RKR_04PIst_Kessel     Brennerleistung
```

must **not** be transferred to this VDensHO1/20C2 as working power datapoints
just because the addresses are readable.

The VDensHO1-specific Vitosoft datapoint list itself contains `0x555A`
(Kesselsolltemperatur) but does not list either `0x555C` or `0x55E0`.
This device-specific list takes precedence over cross-family address matches.

Conclusion:

- `0x555C`: readable raw byte, semantics unresolved on 20C2
- `0x55E0`: readable raw byte, semantics unresolved on 20C2
- neither value should currently be labelled set power / burner power for this device

The search for the source of the ~1 %/s ramp therefore moves to the CFDM
objects (`0xA380` / `0xA38F`), which have already shown dynamic behavior in
earlier WB2A logs.


## 2026-09-22 high-resolution run: pre-ignition and ramp details

The 20:19 run added several useful observations:

- `0x55DC` starts changing **before flame is present**:
  roughly 30 -> 34 -> 57 -> 67/68 -> 65 while `FL=0`.
- At flame start, `0x55DC` is already about 65 %.
- After flame start it holds about 66 % for roughly 12 s.
- The sustained downward ramp then reaches 33 % after about 44-45 s from
  flame start, again consistent with approximately 1 percentage point/s.
- After flame loss, `0x55DC` remains nonzero briefly (33 -> 30 -> 0),
  confirming that it is a controller modulation command/state value rather
  than a direct proof of instantaneous combustion output.

This makes it even more important to distinguish the controller modulation
command from a downstream actual-power signal.

## CFDM next-step hypothesis

Cross-family Vitosoft metadata identifies:

```text
0xA380  nviProdCmd_CFDM_state/value   Anlagen-/ Kessel-Sollleistung
0xA38F  nvoPWRState_CFDM_state/value Anlagen-Istleistung
```

These names are not present in the VDensHO1-specific datapoint list, so they
remain cross-family hints rather than verified 20C2 semantics.

Earlier hardware logs nevertheless show dynamic `A38F` data. One notable
sample had:

```text
A305 raw = 0x84 -> 66.0 %
A38F raw = 82 01
```

If `A38F` byte 0 uses the same 0.5 %/LSB scaling, `0x82 = 130 -> 65.0 %`,
which is a strong numerical correlation. Byte 1 may be a state/status field,
but that layout is not yet proven.

The single-session logger now records raw `0xA380;2` and `0xA38F;2`
alongside verified `0x55DC` modulation. The goal is to determine whether the
CFDM command changes abruptly while CFDM actual power follows the 1 %/s ramp,
or whether the CFDM command itself is already ramp-limited.


## 2026-09-22 CFDM correlation: 0x55DC command vs 0xA38F active power state

A full single-session start log with simultaneous raw reads of `0x55D3`,
`0xA380` and `0xA38F` resolves an important architectural question.

### Pre-ignition behavior

Before flame is present, `0x55DC` already moves through the startup sequence:

```text
55DC: 30 -> 33 -> 58 -> 67 -> 68 -> 67 -> 66 -> 65 %
FL:   0
A38F: 0000
```

This proves that `0x55DC` is not a direct measurement of current combustion
output. It is better interpreted as the live burner modulation command/state
used by the controller.

At flame establishment:

```text
T=0.00 s  55DC=65  A38F=0000  55DD=29
T=0.74 s  55DC=66  A38F=0000  55DD=21
T=1.48 s  55DC=66  A38F=8201  55DD=21
```

Thus the CFDM power-state object becomes active only after stable flame.

### 0xA38F raw layout

The observed raw form is strongly consistent with:

```text
byte 0 = power/modulation value with 0.5 % per LSB
byte 1 = state/valid flag
```

Examples:

```text
A38F=8201 -> byte0 0x82 = 130 -> 65.0 %
A38F=7c01 -> 124 -> 62.0 %
A38F=6401 -> 100 -> 50.0 %
A38F=5401 ->  84 -> 42.0 %
A38F=4201 ->  66 -> 33.0 %
A38F=0000 -> inactive/off
```

This byte order/scaling is empirically very strong, although the Vitosoft
metadata only names the object as `nvoPWRState_CFDM_state/value` and does
not document the raw member layout.

The second byte changes from 0 to 1 when the active power state becomes valid
after flame establishment and remains 1 during firing.

### Ramp correlation

Across the falling-ramp interval, comparing:

```text
x = 0x55DC modulation command
y = A38F byte0 * 0.5
```

gives approximately:

```text
y = 1.002 * x - 0.04
correlation r ~= 0.996
```

The remaining differences are consistent with:

- sequential sampling delay between the two Optolink reads, and
- coarser update/quantization of the A38F power-state value.

Therefore the approximately 1 percentage-point/s downward ramp is already
present in `0x55DC` before the downstream active-power state follows it.

**Conclusion:** the measured ramp is not explained by a slow physical burner
actuator that receives an immediate lower target. It is generated in the
controller/GFA modulation-command path itself.

This substantially weakens the earlier hypothesis that a generic
"100 s actuator travel time" parameter is the direct cause of the observed
1 %/s ramp.

### 0xA380 result

`0xA380` remained exactly:

```text
00ff
```

for the complete off/start/ramp/steady interval.

The cross-family Vitosoft name is
`nviProdCmd_CFDM_state/value / Anlagen-/Kessel-Sollleistung`, but this object
is evidently not carrying a changing power command in this VDensHO1 heating
mode. A plausible interpretation is that no direct CFDM power command is
active and the boiler instead operates from a temperature demand/local burner
controller. The exact meaning of `00ff` is not yet decoded.

For high-resolution follow-up logging, `0xA380` no longer needs to be sampled
continuously unless a different operating mode is being investigated.


## Regulator-delay interpretation after CFDM correlation

The CFDM correlation changes the interpretation of the startup sequence:

- `0x55DC` already contains the approximately 1 %/s downward ramp.
- `0xA38F` becomes valid only after stable flame and then follows `0x55DC`
  very closely.
- Therefore the ramp is generated upstream in the controller/GFA modulation
  command path; it is not primarily caused by a slow downstream actuator.

This is consistent with the generic combustion-controller concept called
`Reglerverzögerung nach Brennerstart`: after positive flame detection the
controller holds a defined startup power for a fixed time before normal
modulation is released.

The measured WB2A plateau is approximately 12 seconds after flame
establishment.

Important correction: `GWG73 / Anfahroptimierung modulierender Brenner` is
not this 12-second delay. A VDensHO1-specific catalog decodes GWG73 as
`raw * 10 s`; with raw 24 this coding plug therefore contains 240 s (4 min)
of startup optimization. Viessmann documentation for other controller
families also treats startup optimization and regulation delay as separate
parameters.

### GFA 0x0083 object probe

In the LGM29/GWG Vitosoft family both:

- `Brennermindestlaufzeit`
- `Reglerverzögerung nach Brennerstart`

are associated with the same base `0x0083` object.

A one-byte read on this WB2A returned retcode 3, but this does not yet prove
that the object is absent: the object may require a larger structure length.
The logger therefore probes `0x0083` read-only with lengths 1, 2, 4, 8 and
16 on startup. If all lengths fail, the LGM29 map can be rejected more
confidently for this GFA generation.


## 2026-09-22 RKR structure discovery: 0x5556 mirrored at 0x55E0

A direct four-byte read from `0x5556` produced:

```text
0x5556;4 = 01 3e 01 00
```

At the same time the 17-byte block at `0x55E0` was:

```text
0x55E0;17 = 01 3e 01 00 00 00 00 00 05 51 3e 01 00 00 00 00 00
             ^^^^^^^^^^^
             exact mirror of 0x5556;4
```

This is a structural match, not merely a similar value. The first four bytes
of the `0x55E0` block are identical to the direct `0x5556;4` object.

The currently best-supported interpretation is:

```text
0x5556 +0     01       RKR enable/release candidate
0x5556 +1..2 3e 01    RKR boiler setpoint candidate = 31.8 C (LE / 10)
0x5556 +3     00       unresolved, cross-family hint: RKR power setpoint/status
```

The temperature field is strongly supported by simultaneous values:

```text
0x2544 = 3e01 -> 31.8 C
0x5556[1:3]   -> 31.8 C
0x55E0[10:12] -> 31.8 C
0xA307 = 6c0c -> 31.8 C when decoded /100
```

The same snapshot showed:

```text
0xA305 = 00
0x55D3 = 00 9a a2 00 00 01 00 00 00 ...
flame = off
0x5556[0] = 01
```

Therefore `0x5556[0] = 01` is definitively **not equivalent to burner
running/flame present**. It is more plausibly an upstream RKR demand/release
state that may remain active while the burner is off due to temperature
limits, minimum off-time or other burner-control logic.

The semantic names of byte 0 and byte 3 are not yet proven on VDensHO1/20C2.
They must be verified dynamically across a full sequence:

```text
burner on -> flame off -> boiler pause -> next release/ignition
```

For that purpose the repository now contains:

```text
config/optolink-splitter/wb2a-rkr-cycle-logger.py
```

It logs `0x5556`, `0x55E0`, `0xA395`, `0xA305`, `0x55D3`,
`0x2544`, `0x0810` and `0xA307` in one persistent TCP session and
marks flame, RKR-byte-0 and A395-byte-2 transitions.


## 2026-09-22: 0x0083/LGM29 path rejected

The GFA timing candidate `0x0083` was probed read-only with several object
lengths:

```text
read;0x0083;1  -> retcode 3 / payload 01
read;0x0083;2  -> retcode 3 / payload 01
read;0x0083;4  -> retcode 3 / payload 01
read;0x0083;8  -> retcode 3 / payload 01
read;0x0083;16 -> retcode 3 / payload 01
```

This rules out the earlier theory that only the requested object length was
wrong. The LGM29/GWG P300 timing map is not directly exposed on this WB2A.

Public WB2A documentation and Viessmann community material identify the WB2A
generation as using a **GG1 control**, and explicitly distinguish it from the
older WB2/LGM29 generation. Therefore LGM29-specific addresses such as
`GWG_FA_Takt_ReglerverzoegerungStart~0x0083` must not be treated as WB2A
addresses.

The device-specific VDensHO1 Vitosoft list exposes only these named
fire-control datapoints:

- `0x55D3` burner / lockout runtime data
- `0x55DD` flame signal
- `0x7650` GFA chip identification

No named VDensHO1 datapoint for the approximately 12-second regulator delay is
present in that list.

Current conclusion: the ~12 s plateau is strongly consistent with a burner
control "Reglerverzögerung nach Brennerstart" function, but its storage
location is not exposed by the known VDensHO1 P300 map and may be an internal
GG1/GFA firmware parameter.


## 2026-09-22 20:50 GG1 runtime-byte analysis

A focused start log sampled `0x55D3;11` and `0xA38F;2` with roughly
0.24-0.60 s resolution.

### Confirmed identity snapshot

The run reconfirmed:

```text
GFA chip ID            2002061501ff
coding-card revision   20150201
coding-plug part no.   7833971
0x1070 block           051d141841323c000000000000000000
```

### Byte 5 / 6 / 7 state machine

The burner-start sequence is now visible directly in the `0x55D3` block:

```text
idle                    b5/b6/b7 = 01/00/00
pre-purge               b5/b6/b7 = 01/08/20
ignition step 1         b5/b6/b7 = 09/0c/40
ignition step 2         b5/b6/b7 = 09/0f/50
flame establishment     b5/b6/b7 = 29/0b/60
stable flame            b5/b6/b7 = 21/0b/60
later stable sub-state  b5/b6/b7 = 21/0b/62
```

Known bits in byte 5 remain consistent:

- `0x20` = flame present
- `0x40` = lockout
- `0x08` is present during the ignition phase (`09`, `29`) and clears
  once the stable `21` state is reached. Its exact Viessmann name is not yet
  proven.

Byte 7 bit `0x02` is especially interesting:

```text
flame start              T = 0.00 s, b7 = 0x60
stable 0x21 state        T = 0.99 s, b7 = 0x60
b7 changes 0x60 -> 0x62 T = 9.99 s
first sustained MOD drop T = 12.35 s
```

The `0x02` transition therefore occurs about 10 s after flame detection and
roughly 2.4 s before the modulation command starts its sustained downward
ramp. It is a strong **candidate for a GG1 run/regulation sub-state**, but the
exact bit meaning remains unverified.

### Byte 0 follows the modulation path but is not MOD itself

During the controlled downward ramp, GFA byte 0 changes monotonically with
`0x55DC`:

```text
MOD 66 % -> b0 0x45 = 69
MOD 64 % -> b0 0x43 = 67
MOD 60 % -> b0 0x3f = 63
MOD 50 % -> b0 0x37 = 55
MOD 40 % -> b0 0x2f = 47
MOD 33 % -> b0 0x26 = 38
```

Across the falling-ramp interval the correlation is approximately
`r = 0.995`. Byte 0 itself falls at roughly one raw unit per second.

It is therefore clearly burner-control-related, but it is **not the same
quantity or scale as the verified 0x55DC modulation percentage**. A
fan/air/gas actuator-related quantity remains plausible, but no semantic label
is assigned without independent evidence.

### Bytes 1 and 2 are continuous internal variables

Byte 1 does not behave like a state flag:

```text
near flame start  ~0xA5 = 165
minimum           ~0x87 = 135 at about T=23.5 s
later steady      ~0x97 = 151 by about T=62 s
```

Byte 2 changes much more slowly and stepwise:

```text
0xA4 -> 0xA5 -> 0xA6 -> 0xA7
```

Neither byte shows a discrete transition exactly at the approximately
12-second modulation-release point. They therefore look more like internal
continuous process/control quantities than a simple regulation-enable flag.

Bytes 3, 4 and 8 remained zero throughout this captured start.

### A38F activation timing

`A38F` remains `0000` through pre-purge, ignition and initial flame
establishment. In this run:

```text
T=0.00 s  flame detected, 55DD=29, A38F=0000
T=0.99 s  stable 55DD=21,      A38F=7f01 (63.5 % candidate value)
T=1.90 s  stable firing,       A38F=8201 (65.0 %)
```

This further supports the interpretation that `A38F` is an active
combustion/power-state value that becomes valid only after the GFA reaches its
stable firing state.

### Next targeted correlation

The next useful read-only correlation is `0x0810` (boiler temperature)
against GFA bytes 1 and 2. Their raw trajectories could be thermal, but no
temperature scaling should be assigned until a simultaneous direct
temperature measurement proves it.


## 2026-09-22: 0x55E0 byte 14 changes at the 240 s post-flame boundary

A deliberately induced heating cycle (D4/heating-curve level changed only to
produce a reproducible demand change) captured a long burner-off interval.

Relevant events:

```text
20:58:11.412  FLAME_STOP detected
20:59:09.777  A395 byte 2: 0x50 -> 0x00   (+58.4 s from detected stop)
21:02:09.536  0x55E0 byte 14: 0x00 -> 0x01
21:11:59.343  next FLAME_START            (off=827.9 s)
```

The previous flame-positive sample was approximately 20:58:09.523. Therefore
the real flame-loss instant lies between the last positive sample and the
20:58:11.412 detection. The first observed byte-14 transition at 21:02:09.536
is consequently compatible with a timer expiring essentially exactly 240 s
after the actual flame loss:

```text
21:02:09.536 - 20:58:09.523 ~= 240.013 s
```

The sampling cadence is about 1-2 s, so the transition cannot be assigned
millisecond precision. Nevertheless, the correlation with the 240 s boundary
is very strong.

During this transition the burner remains off and no restart sequence begins:

```text
0x55E0 before: 01 72 01 00 00 00 00 00 05 51 72 01 00 00 00 04 00
0x55E0 after:  01 72 01 00 00 00 00 00 05 51 72 01 00 00 01 04 00
                                                        ^^
                                                   byte 14
A395.b2 = 0x00
flame   = 0
55DC    = 0
55DD    = 0x01
boiler actual ~= 34.6 C
boiler target ~= 37.0 C
```

The next burner start occurs much later because the boiler cools only slowly
to the thermal restart threshold. Therefore the approximately 828 s total
off-time is not itself a burner lockout duration.

Current interpretation:

- `A395.b2 = 0x50` is **not** the 240 s boiler-pause state; it clears after
  only about 58 s in this run.
- `0x55E0 byte 14` is the strongest current candidate for a
  **240 s post-burner-stop timer/release state**.
- It should not yet be assigned a final Viessmann semantic name until the
  same 0->1 transition is reproduced in another independent burner cycle.
- A stronger functional proof would be a cycle where the thermal restart
  condition is already satisfied before 240 s and ignition waits until this
  byte changes.

The RKR cycle logger now records this byte separately as `55e0_b14` and emits
events such as:

```text
55E0_B14_00->01
```

The 16-bit field at `0x55E0[10:12]` is no longer labelled as a temperature
in the logger. Its dynamic behavior during startup shows that the earlier
`GWG=... C` presentation was not justified; it is retained only as an
unresolved raw little-endian word.


## 2026-09-22: functional proof of the ~240 s restart inhibition and startup-optimization target

A second deliberately induced cycle produced a much stronger test because a
large heat demand was created while the burner was still off.

### Restart inhibition under unambiguous demand

Relevant sequence:

```text
21:39:16.126  0x55E0 byte14: 0x43 -> 0x00, A305 already 0, flame still sampled as 1
21:39:18.106  FLAME_STOP detected
21:39:38.931  flow/BLR target raised to 65.0 C
21:39:57.271  flow/BLR target raised further to 67.1 C
21:40:16.257  A395.b2: 0x50 -> 0x00
...
21:43:13.282  0x55E0 byte14: 0x00 -> 0x01
21:43:17.104  55DC begins startup sequence (33 %)
21:43:25.196  FLAME_START, logged off interval 247.1 s
```

For more than three minutes the boiler therefore had an unambiguous demand
(`67.1 C` target while actual temperature was roughly `56 -> 51 C`), yet
`55DC` remained zero and no burner start occurred while byte14 remained
`0x00`.

The first startup activity appears only after byte14 changes to `0x01`.
Measured from the controller's burner-off transition around
21:39:16 to the first nonzero 55DC at 21:43:17, the interval is about
241 s. Because the reads are sequential and the cycle time is roughly
1-2 s, this is consistent with a nominal 240 s restart inhibition.

This is functional evidence, not merely a time correlation:

```text
strong thermal demand + byte14=0 -> no start
byte14 0->1                  -> startup becomes possible
~4 s later                  -> 55DC startup sequence
~12 s later                 -> flame present
```

The full byte is clearly a bitfield, not a Boolean:

```text
off / restart inhibited         0x00
released / pre-start            0x01
stable firing/regulation state  0x43
```

Bit 0 is therefore the strongest current candidate for a restart/start-release
state. Bits represented by `0x42` are associated with the firing/regulation
phase but remain semantically unresolved.

### 0x55E0[10:12] is a temperature-like startup-optimization target

The same run also resolves the earlier uncertainty around the word at
`0x55E0[10:12]`. It behaves consistently as a little-endian value in
0.1 C units, but it is not a simple duplicate of the external boiler target.

With the main target at 50.0 C:

```text
main RKR / BLR target       50.0 C
0x55E0[10:12] initially    0x012c = 300 -> 30.0 C
difference                         = -20.0 K
```

During the firing period this internal target then ramps upward and reaches:

```text
0x01f4 = 500 -> 50.0 C
```

roughly four minutes after burner start.

Later, while the burner is off and the main target is raised to 67.1 C,
the internal word follows it directly as `0x029f = 671 -> 67.1 C`.
At the restart-release transition it changes simultaneously to:

```text
0x01d7 = 471 -> 47.1 C
```

which is again exactly 20.0 K below the 67.1 C main target.

This strongly supports the interpretation that `0x55E0[10:12]` is an
**internal startup-optimized boiler target**. It is reduced by 20 K at burner
startup and subsequently ramps back toward the normal target over roughly the
known 240 s startup-optimization interval.

This behavior is an excellent match for the coding-plug parameter
`GWG73 / Anfahroptimierung modulierender Brenner = 24 * 10 s = 240 s`.

Important distinction: the approximately 240 s startup-optimization ramp and
the approximately 240 s post-stop restart inhibition are two separate observed
behaviors. They must not be treated as one timer merely because their nominal
durations are similar.


## 2026-09-22: second independent restart-inhibition reproduction

A further controlled cycle reproduced the restart inhibition with a cleaner
time base and with the thermal demand becoming true very early in the off
period.

Relevant sequence:

```text
21:48:27.999  FLAME_START
21:48:38.006  0x55E0 byte14: 0x01 -> 0x43
21:49:03.690  FLAME_STOP + byte14 0x43 -> 0x00
21:49:39.817  boiler actual 67.0 C < target 67.1 C
21:49:41.633  boiler actual 66.0 C, target still 67.1 C
21:50:02.868  A395.b2 0x50 -> 0x00
...
21:53:01.950  byte14 0x00 -> 0x01 and OPT 67.1 -> 47.1 C
21:53:03.554  55DC startup command becomes nonzero (30 %)
21:53:12.579  FLAME_START, logged off interval 248.9 s
21:53:24.481  byte14 0x01 -> 0x43
```

The important functional observation is that the boiler is already below the
67.1 C target by about 36-38 s after flame stop and later falls far below the
target, yet no burner-start activity appears while byte14 bit0 remains zero.
The first nonzero 55DC command appears at 21:53:03.554, 239.864 s after the
logged FLAME_STOP at 21:49:03.690. This is an especially strong reproduction
of a nominal 240 s restart inhibition.

Because the logger reads values sequentially, the byte14 transition itself is
observed slightly earlier (OFF=238 s), while the start command lands almost
exactly at 240 s. The previous flame-positive sample was at 21:49:02.444, so
the byte14 0->1 observation at 21:53:01.950 is also 239.506 s after the last
known flame-positive sample.

This second cycle therefore strongly supports:

- `0x55E0 byte14 bit0 = 0`: restart/start release not yet granted.
- `0x55E0 byte14 bit0 = 1`: restart/start release granted.
- the nominal post-stop inhibition interval is approximately 240 s.
- `A395.b2` is a separate approximately 60 s post-fire state and is not the
  restart-inhibition timer.

The same cycle independently confirms the startup-optimization target:
when byte14 bit0 becomes 1, `OPT` changes immediately from 67.1 C to
47.1 C, exactly 20 K below the normal target. The burner startup command
follows about 1.6 s later.

Finally, byte14 transitions from `0x01` to `0x43` about 11.9 s after
FLAME_START in this cycle, again suggesting that the additional `0x42` bits
belong to the established firing/regulation phase rather than to the basic
restart release.


## Next session: restructure Home Assistant diagnostics page

The Home Assistant diagnostics page should be reviewed and reorganized in the
next working session. The current page has accumulated many experimentally
discovered and service-level entities and is technically useful, but no longer
optimally structured for day-to-day diagnosis.

Planned goals:

- separate **operational burner state** from low-level/raw diagnostics;
- group the newly verified RKR states together:
  - restart inhibition / `brenner_taktsperre_aktiv`;
  - restart released / `brenner_wiederanlauf_freigegeben`;
  - burner start phase;
  - startup optimization active;
  - established regulation state;
  - normal RKR boiler target vs internal optimized target (OPT);
  - raw `0x55E0 byte14` only as a secondary diagnostic value;
- group burner/flame/modulation values separately from CFDM and other internal
  controller-chain values;
- move coding-plug parameters into a clearly separated configuration/reference
  section;
- keep unresolved/raw research fields clearly marked as such instead of mixing
  them with hardware-verified operational states;
- remove obsolete or disproved interpretations from the UI;
- improve explanatory text so the page communicates **what a value means in
  operation**, not only its internal address/name;
- reduce visual clutter and make the most useful live states visible first,
  with deep diagnostics lower on the page;
- review whether 24 h history charts for burner, modulation, restart inhibition,
  OPT and boiler temperature would improve diagnosis.

The existing dashboard file to restructure is:

`config/optolink-splitter/homeassistant-dashboard.yaml`

Do not discard the current diagnostic entities during the redesign; reorganize
them and preserve useful low-level access where appropriate.

## Local system fault F9 — blower speed not reached

The general system fault archive at `0x7507` contains a complete historical
entry:

~~~text
F9 20 26 09 21 01 17 31 44
~~~

Decoded timestamp:

~~~text
2026-09-21 17:31:44
~~~

The exact local Vitosoft mapping for VDensHO1 is:

~~~text
F9 = Fehler Gebläse - Drehzahl nicht erreicht
~~~

This is useful corroborating evidence for the open blower-speed research task:
the controller itself monitors whether blower speed reaches a target, so a
blower-speed command/actual-state path necessarily exists internally even
though the previously assumed `0x55D3[6:7]` RPM interpretation was disproved.

The F9 history entry does **not** identify the hidden live RPM datapoint by
itself. It should be used as a clue when searching GFA/GG1/diagnostic objects
for target/actual speed and speed-deviation states.
