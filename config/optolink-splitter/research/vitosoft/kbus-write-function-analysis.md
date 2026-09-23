# Vitosoft KBus write-function analysis

Status: **source-verified / production Vitosoft 0.0.26.4683**

Purpose: determine whether the generic VS2 KBus write function family looks
capable of injecting raw Vitotrol/KM-BUS slave telegrams into VDensHO1.

Source:

~~~text
ecnEventType.xml
DataPointDefinitionVersion 0.0.26.4683
SHA-256:
2338beb0e8544b6149bc4b2433ecabd9509edcdafc2e8e91f00182eba1aff7ba
~~~

Device-use links were joined through `DPDefinitions.xml`.

## Global write-function inventory

| FCWrite | Definitions | Typical block length | PrefixWrite pattern |
| --- | ---: | --- | --- |
| KBUS_TRANSPARENT_WRITE | 853 | 1 | usually 2-byte KBus address, sometimes 3 bytes |
| KBUS_EEPROM_LT_WRITE | 495 | mainly 4; also 1/15/16 | almost always blank |
| KBUS_VIRTUAL_WRITE | 124 | 1 | usually same 2-byte value as logical KBus address |
| KBUS_INDIRECT_WRITE | 97 | 2; one 3-byte row | usually 1-byte participant/channel selector |
| KBUS_DIRECT_WRITE | 11 | 8; one 2-byte row | blank except one `01` |
| KBUS_MEMBERLIST_WRITE | 2 | 3 and 1 | blank / `00` |
| KBUS_GATEWAY_WRITE | 1 | 1 | blank |
| KBUS_CONTROL_WRITE | 0 | — | — |

There are **zero** `KBUS_*` or `KMBUS_*` FCRead/FCWrite events linked to
the exact local `VDensHO1 / 20C2 / developer 01.03` device profile.

## KBUS_TRANSPARENT_WRITE — 0x56

Function code:

~~~text
0x56 = KBUS_TRANSPARENT_WRITE
~~~

Production Vitosoft contains **853** write definitions.

Every single one has:

~~~text
Parameter   = Byte
BlockLength = 1
~~~

Representative rows:

~~~text
ID:          KBUS_HV_Bedienteil~0x0100
Address:     0x0100
FCRead:      KBUS_TRANSPARENT_READ
FCWrite:     KBUS_TRANSPARENT_WRITE
PrefixRead:  EE08
PrefixWrite: EE08
BlockLength: 1

ID:          KBUS_HV_Bedienteil_2tes~0x0100
Address:     0x0100
FCWrite:     KBUS_TRANSPARENT_WRITE
PrefixWrite: EE0801
BlockLength: 1

ID:          KBUS_HV_Schaltzeit_A1_Dienstag_Ein~0x0100
Address:     0x0100
PrefixWrite: 9008
BlockLength: 1
~~~

The most common prefixes are two-byte logical KBus addresses such as
`CA08`, `D408`, `9808`, `9008`, etc. A smaller set appends a selector
byte, e.g. `EE0800` / `EE0801`.

Device-link analysis shows that these events are used mainly by:

~~~text
Dekamatik_*
HV_V300KW3
VCOM100_DEKM_*
DEKATEL_M*
~~~

and related legacy/gateway profiles.

### Interpretation

The structure is consistent with **transparent datapoint access to a KBus
participant**:

~~~text
outer VS2 address/selector
+ PrefixWrite = target KBus datapoint/subselector
+ exactly one application data byte
~~~

It is **not** shaped like a raw physical KM-BUS telegram injector:

- every Vitosoft write carries only one application byte;
- the raw Vitotrol identity response is 16 bytes total;
- the room-temperature response is 12 bytes total;
- Vitosoft never provides a full `00 11 BF ... CRC` physical telegram as
  PrefixWrite or BlockLength data for this function.

Therefore `0x56` must not currently be treated as "send arbitrary bytes onto
the physical KM-BUS".

## KBUS_DIRECT_WRITE — 0x62

Function code:

~~~text
0x62 = KBUS_DIRECT_WRITE
~~~

Only **11** definitions exist.

They are named:

~~~text
KBUS_V300_T01_DirektKanal_01...
...
KBUS_V300_T11_DirektKanal_01...
~~~

Addresses:

~~~text
0x0001 .. 0x000B
~~~

Lengths:

~~~text
T01: BlockLength 2, PrefixWrite 01
T02..T11: BlockLength 8, PrefixWrite blank
~~~

They are linked exclusively to communication/gateway families such as:

~~~text
VCOM300_*
DEKATEL_F*
~~~

No VDensHO1 link exists.

### Interpretation

This is a stronger low-level primitive than transparent one-byte access, but
there is still no source evidence that it represents arbitrary slave-side
physical telegram injection.

The fixed 8-byte "direct channel" records and communication-device-only
membership instead point to an internal Vitocom/DEKATEL channel abstraction.

A physical Vitotrol room-temperature telegram is 12 bytes total, and its
identity reply is 16 bytes total, so the known Vitosoft record shape does not
map directly to a complete wire frame.

## KBUS_GATEWAY_WRITE — 0x66

Function code:

~~~text
0x66 = KBUS_GATEWAY_WRITE
~~~

There is exactly **one** Vitosoft event:

~~~text
ID:          KBUS_Funktion_LoescheAlleStoermeldungen~0x0001
Address:     0x0001
Parameter:   Byte
BlockLength: 1
PrefixWrite: <blank>
FCRead:      undefined
FCWrite:     KBUS_GATEWAY_WRITE
~~~

It is linked to Vitocom/DEKATEL gateway profiles.

This is clear evidence that `KBUS_GATEWAY_WRITE` is at least used as a
gateway **control operation**. It gives no evidence of raw KM-BUS frame
injection.

## KBUS_MEMBERLIST_WRITE — 0x5E

Two definitions:

~~~text
KBUS_V300_Teilnehmer00~0x0000
  BlockLength 3
  ReadWrite

KBUS_V300GeraetelisteWrite~0x0001
  PrefixWrite 00
  BlockLength 1
  Write
~~~

Again, these are linked to VCOM300/DEKATEL-F profiles rather than VDensHO1.

This supports the earlier conclusion that member-list operations belong to
communication/gateway device management and are not the local WB2A's normal
Vitotrol interface.

## KBUS_VIRTUAL_WRITE — 0x60

There are **124** definitions, all BlockLength 1.

Typical shape:

~~~text
Address:     0x6E04
PrefixWrite: 6E04
BlockLength: 1
~~~

This is conventional KBus datapoint access and not a raw telegram channel.

## KBUS_INDIRECT_WRITE — 0x64

There are **97** definitions.

Most V300 virtual-channel rows use:

~~~text
BlockLength: 2
PrefixWrite: participant/channel byte
~~~

For example:

~~~text
T00 -> PrefixWrite 00
T01 -> PrefixWrite 01
...
~~~

This looks like indexed participant/channel access, not a physical telegram
transport.

## KBUS_EEPROM_LT_WRITE — 0x5A

There are **495** definitions.

Most have no PrefixWrite and are regular fixed-size EEPROM/LT records. This
function is unrelated to the live Vitotrol slave exchange reconstructed from
the physical bus.

## KBUS_CONTROL_WRITE — 0x5B

The function code exists in the enum but the production Vitosoft
`ecnEventType.xml` contains **no event using it as FCWrite**.

There is therefore no source-derived argument format available from this data
set.

## Consequence for the Optolink-only Vitotrol idea

Current evidence does **not** support the previous optimistic interpretation:

~~~text
KBUS_TRANSPARENT_WRITE / DIRECT_WRITE / GATEWAY_WRITE
= raw slave telegram injection
~~~

Instead, the source data supports:

~~~text
KBUS_TRANSPARENT_WRITE = participant datapoint access
KBUS_DIRECT_WRITE      = VCOM300/DEKATEL direct-channel abstraction
KBUS_GATEWAY_WRITE     = gateway control operation
KBUS_MEMBERLIST_WRITE  = gateway participant-list management
~~~

None is linked to VDensHO1.

This does not mathematically prove that the VDensHO1 firmware lacks an
undocumented raw-injection mode. It does mean that **Vitosoft supplies no
documented event or argument shape for one**, and blind write probes on the
live boiler are not justified.

## Current decision

Do not issue blind live-boiler requests using:

~~~text
0x56 KBUS_TRANSPARENT_WRITE
0x62 KBUS_DIRECT_WRITE
0x66 KBUS_GATEWAY_WRITE
0x5E KBUS_MEMBERLIST_WRITE
0x5B KBUS_CONTROL_WRITE
~~~

for Vitotrol emulation.

The physical KM-BUS emulator is now the reference path because its protocol is
source-supported and independently demonstrated.

Further Optolink-only work should be limited to:

1. static analysis of actual VDensHO1 firmware / Vitosoft libraries if such
   code becomes available;
2. passive capture of Vitosoft/Optolink traffic on a system where these KBus
   access functions are legitimately used;
3. testing on sacrificial/gateway hardware rather than the live WB2A.

See also:

- [../vitotrol-kmbus-wire-protocol.md](../vitotrol-kmbus-wire-protocol.md)
- [../vitotrol-kbus-optolink-emulation.md](../vitotrol-kbus-optolink-emulation.md)
