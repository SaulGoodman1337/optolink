# WB2A assessment: convert A1 heating circuit to M2 mixer circuit

Status: research / no conversion performed

Local controller state:

- Vitodens 200-W WB2A / VDensHO1 / 20C2
- plant schema 00 = 2: A1 + DHW
- no M2 runtime activity
- internal pump coding 30 = 1: speed controlled
- coding 31 = 100 %
- DHW coding 6C = 100 %
- coding-plug GWG75 internal-pump minimum = 50 %
- measured normal heating: A1 demand ~35-36 %, internal pump 50 %
- measured DHW: A1 demand 0 %, internal pump 100 %

## Is M2 + DHW supported?

Yes. The WB2A service documentation explicitly supports:

- 00:3 = one heating circuit with mixer M2, without DHW
- 00:4 = one heating circuit with mixer M2, with DHW
- 00:5 / 00:6 = A1 + M2 without/with DHW

A real M2 circuit is not a coding-only conversion. The documented topology
requires at least:

- mixer circuit / mixing valve with actuator;
- Viessmann mixer extension on KM-BUS;
- M2 flow-temperature sensor;
- separate M2 heating-circuit pump;
- corresponding hydraulic pipework;
- where required for floor heating, a maximum-temperature limiter.

The current 00:2 A1 circuit uses the internal boiler pump as the heating-circuit
actuator. With a real M2 circuit, the external M2 pump circulates the heating
circuit while the internal pump works on the boiler/primary side.

## Why M2 is highly relevant to the pump-start problem

Viessmann's WB2A-compatible high-efficiency-pump conversion instructions define
coding 31 as:

"Set speed of the internal circulation pump when operated as boiler circuit
pump", adjustable from 50 to 100 %.

The local value is already:

    31 = 100 %

VDensHO1 also defines coding A8 for M2:

    A8 = 1  M2 sets a request to the internal pump
    A8 = 0  M2 does not set a request to the internal pump

The local stored M2 value is already A8 = 1, although M2 is not currently part
of plant schema 00:2.

Therefore the strongest current hypothesis for a true M2 conversion is:

    M2 heat request
      -> M2 pump + mixer regulate circuit flow/temperature
      -> A8:1 requests internal boiler pump
      -> internal pump runs as boiler-circuit pump
      -> coding 31 becomes the relevant speed target
      -> local 31 = 100 %, therefore likely internal pump = 100 %

This is strongly supported by the documented coding semantics but is not yet
hardware-proven on this exact boiler. A real M2 setup or a safe representative
test would be required for direct confirmation. An M2 heat request can outlast the burner-on phase, so M2 may keep the internal
boiler pump at coding 31 speed during burner-off intervals too. Under the
corrected objective this is not inherently a disadvantage; it is analogous to
the observed DHW mode, where 100 % pump operation also persists through burner
off periods and overrun.

## Additional effect: differential temperature 9F

For mixer circuits WB2A exposes coding 9F, differential temperature, factory
value typically 8 K. This raises the boiler target above the mixer-circuit flow
target.

For the current startup problem this can add thermal headroom. Example:

    M2 flow target = 38 C
    9F = 8 K
    boiler target ~ 46 C

If the already observed GWG61 switch-off difference of roughly +8 K remains the
upper boiler threshold, the effective thermal shutdown point can move upward as
well. This could help the boiler survive the high startup modulation long
enough to reach low modulation.

However, higher boiler temperatures also reduce condensing benefit and increase
distribution/standby losses. 9F should therefore be kept only as high as
hydraulically necessary.

## Expected benefits of a real M2 conversion

1. Boiler-side flow becomes independent of heating-circuit flow.
   The internal pump can maintain high heat-exchanger flow while the M2 pump
   serves the actual circuit.

2. Coding 31 becomes relevant to the internal pump as boiler-circuit pump.
   With the current value 100 %, this is a strong candidate for eliminating the
   50 % boiler-side flow limitation while the burner is firing.

3. The mixer directly controls actual heating-circuit flow temperature using a
   dedicated M2 flow sensor.

4. Low-temperature emitters, especially floor heating, can be protected from
   excessive boiler temperature by the mixer and an optional/required maximum
   temperature limiter.

5. The M2 loop can continue to receive the requested low supply temperature
   even if the boiler must run several kelvin hotter for stable burner
   operation.

6. The arrangement gives a clean separation between:
   - combustion/boiler-side hydraulic requirements;
   - heating-circuit temperature/flow requirements.

## Expected disadvantages

1. Significant hardware conversion.
   This is not a software-only change: mixer, actuator/extension, M2 pump,
   sensor, KM-BUS wiring and pipework are required.

2. Additional pump electricity and another moving pump/actuator to maintain.

3. The internal boiler pump may run at coding 31 for the whole M2 heat request,
   not only during burner startup. With local 31 = 100 %, that could mean 100 %
   boiler-pump speed whenever M2 requests heat.

4. Higher boiler target from 9F can reduce condensing efficiency and increase
   heat loss if configured unnecessarily high.

5. More control parameters and failure modes:
   A5/A6/A7/A8/A9, C5/C6, D3/D4, 9F, mixer actuator, flow sensor and M2 pump.

6. Incorrect hydraulic sizing can create poor mixer authority, unwanted bypass
   flow, noise or excess return temperature.

7. A mixer does not reduce the WB2A minimum burner power. It can help absorb
   startup heat and decouple flows, but cannot eliminate cycling when building
   heat demand is genuinely below minimum burner output.

## Assessment of actuator test 0x7500

VDensHO1 exposes service actuator test 0x7500 with:

    00 inactive
    04 internal pump

The WB2A service procedure also documents an "Int. Pumpe Ein" relay test.
This is a controller-native direct pump command, but the documentation only
specifies ON/OFF and does not define the resulting speed.

It is therefore useful as a diagnostic experiment but not currently acceptable
as an automatic burner-on control path:

- relay/actuator test is a service mode;
- it may take normal actuator arbitration away from the controller;
- interaction with burner sequencing has not been characterized;
- no guarantee exists that selecting the test during a burner start preserves
  normal safety/state-machine operation.

Recommended diagnostic only:

- burner OFF;
- DHW inactive;
- run pump logger;
- activate "Int. Pumpe Ein" through the local service relay-test menu;
- observe 0x7660 speed and 0xA152 relay state;
- exit relay test through the documented service-menu procedure;
- verify 0x7500 returns to 00.

Do not automate 0x7500 during burner operation unless the service-mode side
effects are completely understood.

## Current conclusion

For the corrected goal "100 % internal pump for at least the complete heating burner-on phase, analogous to DHW; controller-managed pre-run/overrun is acceptable":

- no dedicated VDensHO1 burner-on pump override has been found;
- actuator test is diagnostic/service-only;
- raising GWG75/E7 would be global, not start-only;
- a real M2 conversion is the first normal controller-supported architecture
  found that plausibly makes coding 31 (currently 100 %) the boiler-pump speed.

M2 is therefore technically plausible if the hydraulic benefits justify the
hardware conversion, but it should not be undertaken solely as a software
workaround. Before converting, confirm the actual heating-system hydraulics,
emitter type, design flow and whether a mixer is thermally appropriate.

## Update: actuator test does not supply a speed command

A repeat test with runtime logging confirmed that selecting service actuator
`0x7500=04` (INTERNE PUMPE) does not produce a 100 % speed command on this
installation. During roughly 39 s at selector value 04, both the internal-pump
runtime speed object `0x7660` and A1 speed demand `0x7663` remained at 0 %;
the normal internal-pump relay-state bit in `0xA152` also remained clear.

This weakens the service-actuator path substantially. The service manual calls
the function "Int. Pumpe Ein" but describes it as "Int. Ausgang 20", which is
consistent with an enable/legacy-output test rather than a variable-speed
setpoint.

This strengthens the distinction to a real M2 topology: M2 has both a normal
controller request path (A8) and a dedicated internal-boiler-pump speed target
(coding 31). The local coding 31 is already 100 %, so M2 remains the leading
controller-native architecture for maintaining high boiler-side pump speed
through heating burner operation.
## Concrete WB2A M2 hardware path

External documentation confirms that the WB2A supports a real M2 mixer circuit
through a KM-BUS mixer extension. Historical Viessmann installation
instructions list mixer-extension kits 7301063 (mixer-mounted) and 7301062
(wall-mounted) as compatible with Vitodens 200-W type WB2A. A more recent
Viessmann community answer for a WB2A retrofit identifies extension module
7639039 as suitable and states that its KM-BUS connects at X3.6/X3.7 after
removing plug 145.

For one mixed heating circuit plus DHW the WB2A service documentation specifies
plant schema:

```text
00:4 = M2 + DHW
```

The M2 extension provides/controls:

- M2 heating-circuit pump;
- mixer actuator;
- M2 flow-temperature sensor;
- KM-BUS communication to the boiler controller.

The mixer extension uses rotary-selector position 2 for M2 in the installation
manual.

### Why coding 31 matters more under M2

Viessmann documentation defines coding 31 as the speed setpoint of the internal
circulation pump **when operated as boiler-circuit pump**. Viessmann technical
support also distinguishes the direct A1 topology: when the internal pump acts
as the heating-circuit pump, E6/E7 govern it and coding 31 has no effect.

That distinction matches the local measurements exactly:

```text
current schema 00:2 A1 + DHW
A1 calculated demand ~33-36 %
internal pump = 50 % due internal minimum
coding 31 = 100 % but has no visible effect in A1 mode
```

A real M2 topology is therefore the first normal operating topology found where
the role of the internal pump changes in precisely the way needed to make
coding 31 relevant.

With A8:1, the WB2A service documentation states that M2 asserts a request to
the internal circulation pump. The resulting working hypothesis is:

```text
M2 heat request
  -> A8:1 internal-pump request
  -> internal pump operates as boiler-circuit pump
  -> coding 31 supplies boiler-pump speed target
  -> local coding 31 = 100 %
```

This remains a hypothesis until measured on a real M2 configuration, but every
known controller-side semantic is consistent with it.

### M2 differential temperature

Coding 9F becomes relevant with a mixer circuit. Viessmann defines it as the
minimum amount by which the common/boiler flow target should exceed the highest
currently required mixed-circuit flow target. The typical factory value is
8 K and the range is 0..40 K.

This can provide additional thermal headroom during burner operation, but it
also raises boiler temperature and should not be treated as free efficiency.
For the pump objective, the main benefit of M2 is the hydraulic role change of
the internal pump; 9F is a separate secondary tuning parameter.
## Local hydraulic topology: simple radiator circuit

The local installation has now been clarified as:

```text
WB2A
  -> internal pump
  -> single direct radiator circuit

no hydraulic separator
no external heating-circuit pump
no underfloor-heating circuit
no existing mixer circuit
```

This materially changes the practical M2 assessment.

For a single radiator circuit there is no independent low-temperature circuit
that inherently requires a mixer. Converting to M2 would therefore add a mixer,
M2 pump, flow sensor, KM-BUS extension and hydraulic re-piping primarily to
change the role of the internal pump from direct heating-circuit pump to
boiler-circuit pump.

Viessmann documentation/support distinguishes the two roles:

- without mixer/hydraulic separator, the internal pump acts as the heating-
  circuit pump and E6/E7 are the relevant normal-heating speed limits;
- with mixer/hydraulic separator, the internal pump becomes the boiler-circuit
  pump and coding 31 becomes the relevant speed target.

This matches the local observations: schema 00:2, coding 31 = 100 %, but normal
heating still runs the internal pump at 50 % from an A1 request around 33-36 %.

### Preferred diagnostic before any M2 conversion

The local values are already:

```text
E6 = 100 %
E7 = 30 %
31 = 100 %
GWG75 = 50 %
```

Before adding M2 hardware, perform a short controlled heating test with the
standard A1 minimum pump-speed coding E7 temporarily set to 100 % (E6 is already
100 %), then restore E7 to 30 % after the test.

Expected result if E7 is the active direct-circuit speed limiter on this WB2A:

```text
A1 pump demand 0x7663 -> 100 %
internal pump  0x7660 -> 100 %
```

The comparison should record whether the burner survives the high-start-power
phase without crossing the target + GWG61 switch-off threshold. This is a much
lower-complexity diagnostic than an M2 retrofit and directly tests whether
100 % boiler-side flow solves the observed cycling mechanism.

If successful, the remaining engineering question is not whether 100 % pump
helps, but how to obtain it only for the desired heating operating periods.
Leaving E7 at 100 % permanently would make the pump run at 100 % whenever the
A1 pump is enabled, potentially for long burner-off periods as well.

### Revised M2 assessment for this installation

M2 remains technically valid and could make coding 31 = 100 % the boiler-pump
setpoint, while a separate M2 pump controls radiator-circuit flow. For this
simple radiator-only system, however, M2 is a large hardware solution to a
control problem that may be demonstrable with the existing direct circuit.

Potential reasons to choose M2 anyway would be:

- deliberate hydraulic separation of boiler-side and radiator-side flow;
- desire to run high boiler-pump flow without exposing radiators/TRVs to the
  same differential pressure;
- desire for independent mixed-circuit temperature control.

Without those needs, first validate E7=100 % behavior on A1.
