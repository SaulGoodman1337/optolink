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
