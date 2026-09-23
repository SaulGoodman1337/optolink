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
test would be required for direct confirmation. Crucially, an M2 heat request can
outlast the burner-on phase, so M2 may keep the internal boiler pump at coding 31
speed during burner-off intervals too. That would not exactly match the target
behavior.

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

For the corrected goal "100 % internal pump during the complete heating burner-on phase, then return to normal pump regulation":

- no dedicated VDensHO1 burner-on pump override has been found;
- actuator test is diagnostic/service-only;
- raising GWG75/E7 would be global, not start-only;
- a real M2 conversion is the first normal controller-supported architecture
  found that plausibly makes coding 31 (currently 100 %) the boiler-pump speed.

M2 is therefore technically plausible if the hydraulic benefits justify the
hardware conversion, but it should not be undertaken solely as a software
workaround. Before converting, confirm the actual heating-system hydraulics,
emitter type, design flow and whether a mixer is thermally appropriate.