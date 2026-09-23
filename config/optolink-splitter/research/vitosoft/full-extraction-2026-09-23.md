# Vitosoft production extraction — 2026-09-23

Status: **source-verified / local Vitosoft installation**

This note records the first complete join of the production Vitosoft metadata
used by this project.

## Source set

The files were collected from a real Vitosoft 300 SID1 installation after the
application had been launched once.

Production data version:

~~~text
DataPointDefinitionVersion = 0.0.26.4683
~~~

The preserved `configbackup` version is substantially older:

~~~text
DataPointDefinitionVersion = 0.0.2.588
~~~

Important SHA-256 values from the collected production set:

| File | SHA-256 |
| --- | --- |
| DPDefinitions.xml | `efec27568d398021c767771af016143bd51fc196d2d408dbb80faff84d0b19e3` |
| ecnEventType.xml | `2338beb0e8544b6149bc4b2433ecabd9509edcdafc2e8e91f00182eba1aff7ba` |
| ecnDataPointType.xml | `c66a57be8004a64cf3bf686bf2aa51d77f7ee96e794e95b3d09318a78fe8f0a3` |
| ecnEventTypeGroup.xml | `f72caeed1a39c7fa769dbe88e05ddf3f448ba2d18cf064e43e65d24a5456b8b4` |
| ecnVersion.xml | `96db1023b3040e5ac86ffa8daa75e5d0e4a462cf30ad888ebca1b6a4fcf3881f` |
| sysDeviceIdent.xml | `0b64170a14beed3ec1d4a96ef29ce87ffdb10d675a9b3a3384c29285d25d22a1` |
| sysDeviceIdentExt.xml | `aa0cbe9c01c08bc93d67c4b509d2fb5f9beced278fcc770864bf1688e45763dc` |
| Textresource_de.xml | `bd760a53bcf5058560677d4fdd52b557afbc4e2200cede966a944acc9c7ac2dd` |
| Textresource_en.xml | `6effeb79aa155424313025c4757c3b743c650b9e9bc56bc34ca57b649ae89893` |
| ecnViessmann.mdf | `9dc6194ebadc241fd64ffe5f3b6fbe40b4dbd8ffb975bdbccffc218b85c3f727` |
| ecnViessmann.ldf | `3e9ace83069f6f39a430cf304b109ac5f6c077b527e9f6040208c040659f5085` |

The core XML hashes match the previously identified public LFS reference set
except the language resource, which must therefore be treated as a
local-installation source rather than assumed byte-identical to the public copy.

## Exact VDensHO1 selection

`ecnDataPointType.xml` contains:

~~~text
ID                       VDensHO1
Identification           20C2
IdentificationExtension  0100
IdentificationExtensionTill 0103
~~~

and:

~~~text
ID                       VDensHO1_4
Identification           20C2
IdentificationExtension  0104
IdentificationExtensionTill 019F
~~~

The local controller identity ends in developer version `01 03`, therefore
the base `VDensHO1` definition is the correct Vitosoft device profile for the
local WB2A.

In `DPDefinitions.xml`, `VDensHO1` is datapoint type ID **60**.

## Complete VDensHO1 event join

The complete `DPDefinitions.xml -> ecnEventType.xml` join contains:

~~~text
VDensHO1 event links: 581
missing low-level access rows: 0
~~~

FCRead distribution:

| FCRead | Count |
| --- | ---: |
| Virtual_READ | 462 |
| GFA_READ | 94 |
| Remote_Procedure_Call | 22 |
| blank | 2 |
| undefined | 1 |

FCWrite distribution:

| FCWrite | Count |
| --- | ---: |
| undefined | 375 |
| Virtual_WRITE | 182 |
| Remote_Procedure_Call | 22 |
| blank | 2 |

### Major finding: no KBUS/KMBUS access functions in VDensHO1

For the exact local `VDensHO1` profile:

~~~text
FCRead/FCWrite starting with KBUS_  = 0
FCRead/FCWrite starting with KMBUS_ = 0
~~~

This is a major correction to the earlier research direction.

The global Vitosoft database absolutely does contain large numbers of
`KBUS_*` and `KMBUS_*` events, but Vitosoft does **not** use those access
methods for the local VDensHO1 profile.

Consequences:

1. do not treat `KBUS_MEMBERLIST_READ`, `KBUS_GATEWAY_READ` or
   `KBUS_VIRTUAL_READ` as the next natural VDensHO1 read just because their
   function-code names exist;
2. the controller exposes its KM-BUS-related accessory state primarily through
   normal virtual objects;
3. Optolink-only Vitotrol work should first map those virtual objects before
   probing legacy/communication-device KBUS APIs.

## Vitotrol / remote-control objects on VDensHO1

The most important source result is that remote-control identification is an
ordinary writable virtual object.

### Heating circuit A1/M1

~~~text
Event:       1055 / 1056
Address:     0x27A0
FCRead:      Virtual_READ
FCWrite:     Virtual_WRITE
BlockLength: 1
Parameter:   Byte
~~~

Vitosoft enum:

~~~text
0 = nicht vorhanden
1 = Vitotrol 200
2 = Vitotrol 300
~~~

### Heating circuit M2

~~~text
Event:       1053 / 1057
Address:     0x37A0
FCRead:      Virtual_READ
FCWrite:     Virtual_WRITE
BlockLength: 1
Parameter:   Byte
~~~

The same enum applies:

~~~text
0 = nicht vorhanden
1 = Vitotrol 200
2 = Vitotrol 300
~~~

This does **not** prove that writing 1 or 2 emulates a physical Vitotrol. It
does prove that Vitosoft considers the controller-side remote-identification
state a normal virtual configuration object.

No write should be performed until the current value and the related room
sensor state have been captured and rollback is defined.

## Remote software-index objects

~~~text
A1/M1 remote software index
  address      0x0A5C
  FCRead       Virtual_READ
  block length 4
  displayed byte position 3

M2 remote software index
  address      0x0A60
  FCRead       Virtual_READ
  block length 4
  displayed byte position 3
~~~

These are useful presence/discovery indicators.

## Actual room-temperature objects

The measured room value expected from a real room sensor/remote is exposed as a
read-only virtual object:

~~~text
A1/M1 room temperature
  event        5367
  address      0x0896
  FCRead       Virtual_READ
  FCWrite      undefined
  block length 2
  conversion   Div10
  unit         °C

M2 room temperature
  event        5376
  address      0x0898
  FCRead       Virtual_READ
  FCWrite      undefined
  block length 2
  conversion   Div10
  unit         °C
~~~

Sensor status:

~~~text
A1/M1 0x089C
M2    0x089D
~~~

Vitosoft enum:

~~~text
0 = OK
1 = Kurzschluss
2 = Unterbrechung
3 = unbekannt
4 = unbekannt
5 = unbekannt
6 = Nicht vorhanden
~~~

This is the current key boundary for an Optolink-only Vitotrol:

- remote **type/presence configuration** is writable through ordinary
  Virtual_WRITE;
- actual room-temperature data is documented by Vitosoft as read-only;
- therefore merely setting A0 does not establish a room-temperature injection
  path.

## Related room-control configuration

Relevant writable virtual objects include:

~~~text
0x27B0  B0 Raumaufschaltung A1/M1
0x37B0  B0 Raumaufschaltung M2
0x27B2  B2 Raumeinfluss A1/M1
0x37B2  B2 Raumeinfluss M2
0x27E2  E2 Raumgerät Istwertkorrektur A1/M1
0x37E2  E2 Raumgerät Istwertkorrektur M2
~~~

B0 enum for A1/M1:

~~~text
0 = WS - WS
1 = WS - RS
2 = RS - WS
3 = RS - RS
~~~

Setpoint objects such as `0x2306`, `0x2307`, `0x2308` and external
setpoint objects are writable, but they are setpoints, not the measured room
temperature.

The curated event list is stored in
[vdensho1-vitotrol-events.csv](vdensho1-vitotrol-events.csv).

## Global KBus/KM-BUS inventory

Across the complete production `ecnEventType.xml`, Vitosoft contains:

| FCRead | Definitions |
| --- | ---: |
| KMBUS_EEPROM_READ | 91 |
| KBUS_DATAELEMENT_READ | 7 |
| KBUS_DIRECT_READ | 11 |
| KBUS_EEPROM_LT_READ | 500 |
| KBUS_INDIRECT_READ | 97 |
| KBUS_MEMBERLIST_READ | 1 |
| KBUS_TRANSPARENT_READ | 850 |
| KBUS_VIRTUAL_READ | 232 |

This confirms that these access modes are real Vitosoft metadata, not only enum
names.

However, their device usage is concentrated in legacy Dekamatik,
Vitocom/DEKATEL and related communication profiles rather than VDensHO1.

### KBUS_MEMBERLIST_READ is not a VDensHO1 event

The only event definition is:

~~~text
ID          KBUS_V300_Teilnehmer00~0x0000
FCRead      KBUS_MEMBERLIST_READ
FCWrite     KBUS_MEMBERLIST_WRITE
Address     0x0000
Parameter   Array
BlockLength 3
~~~

It is linked to VCOM300/DEKATEL_F profiles, not to VDensHO1.

Therefore `0x5D` should no longer be treated as the highest-priority local
WB2A probe.

## Important KMBUS_EEPROM_READ prefix finding

Of the 91 global `KMBUS_EEPROM_READ` definitions:

~~~text
90 use PrefixRead = 030000000101
1 uses no PrefixRead
~~~

The prefixed events are predominantly `GWG_FA_*` firing-controller objects.

Example:

~~~text
FCRead      KMBUS_EEPROM_READ
Address     0x0078
PrefixRead  030000000101
BlockLength 5
~~~

This materially changes the interpretation of the earlier local experiments:

~~~text
request;0x43;0x00F8;8;;0x00
~~~

Those experiments proved that the local controller accepts and responds to
function byte `0x43`, but they did **not** reproduce the normal Vitosoft
argument shape used by the large majority of real KMBUS_EEPROM_READ events.

The dynamic repeated two-byte result at F8 therefore remains valid wire
evidence, but it must not be used to infer normal KMBUS EEPROM semantics.

### Prefix placement

The Vitosoft-derived VS2 reference message builder constructs:

~~~text
41 LEN PROTID FCT ADDR_H ADDR_L BLOCKLEN [DATA ...] CHECKSUM
~~~

The local Optolink-Splitter generic request uses the same shape and exposes the
optional bytes after block length as its `data` parameter.

That makes the following mapping a strong source-supported hypothesis:

~~~text
Vitosoft PrefixRead -> VS2 DATA bytes after BlockLength
~~~

This mapping has not yet been hardware-verified with a Vitosoft-defined
KMBUS/KBUS event on the local WB2A.

## Revised next read-only tests

Before any write, record the current controller-side Vitotrol state:

~~~text
0x27A0 / 1  A1/M1 remote identification
0x37A0 / 1  M2 remote identification
0x0A5C / 4  A1 remote software-index block
0x0A60 / 4  M2 remote software-index block
0x0896 / 2  A1/M1 measured room temperature
0x0898 / 2  M2 measured room temperature
0x089C / 1  A1 room-sensor status
0x089D / 1  M2 room-sensor status
0x27B0 / 1  A1/M1 room-influence mode
0x27B2 / 1  A1/M1 room influence factor
0x27E2 / 1  A1/M1 room-value correction
~~~

These are all source-derived from the exact VDensHO1 profile.

Only after this baseline should a controlled `0x27A0` write be considered.


## GFA_READ wire-code correction — 2026-09-23

A local test initially used `0x6B` for GFA_READ:

```text
request;0x6B;0x4054;1;;0x00
-> 3;0x4054;05
```

The return code `3` is a VS2 Error Message; the request was not a successful
GFA read.

The protocol sources distinguish two different command encodings:

```text
VS1/KW:
  GFA_Read = 0x6B

VS2/P300:
  GFA_READ = 201 decimal = 0xC9
```

This is consistent with the extended VS2/P300 function values already used
successfully in this project, e.g. `0x41 KMBUS_RAM_READ` and
`0x43 KMBUS_EEPROM_READ`.

Therefore all direct P300 GFA probes for the local WB2A must use `0xC9`,
not `0x6B`.

The exact VDensHO1 metadata for `0x4054` confirms:

```text
token:       VSKO_Scot_CES_P84~0x4054
name:        (P84) GFA Betriebsphase
block:       1 byte
FCRead:      GFA_READ
PrefixRead:  empty
device link: VDensHO1 included
```

Next read-only validation:

```text
request;0xC9;0x4050;1;;0x00
...
request;0xC9;0x4058;1;;0x00
request;0xC9;0x4006;1;;0x00
request;0xC9;0x4009;1;;0x00
request;0xC9;0x400A;1;;0x00
request;0xC9;0x4011;1;;0x00
```
