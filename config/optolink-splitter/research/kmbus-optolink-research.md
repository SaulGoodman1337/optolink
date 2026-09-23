# KBus / KM-BUS research via Optolink

Status: **active research**
Last updated: **2026-09-23**

This is the canonical research note for all controller-side KBus/KM-BUS access
through the VS2/P300 Optolink interface on the local Vitodens 200-W WB2A.

Vitotrol emulation is one important use case, but not the scope boundary. The
same transport may also be relevant to accessory discovery, controller-internal
bus state, coding-plug questions and other undocumented functions.

Vitotrol-specific interpretation remains in
[vitotrol-kbus-optolink-emulation.md](vitotrol-kbus-optolink-emulation.md).

## Local system

- boiler: Vitodens 200-W WB2A
- controller family: **VDensHO1**
- device identification: **0x20C2**
- Optolink protocol: VS2/P300
- production transport: Optolink-Splitter
- debug helper: `/usr/local/bin/optolink-debug`
- research policy: **read-only by default**

Known normal controller identity:

~~~text
Virtual_READ 0x00F8 / 8
-> 20 c2 00 03 00 00 01 03
~~~

## Terminology and protocol layers

The following layers must be kept separate:

~~~text
Optolink optical link
    |
    v
VS2/P300 telegram
    |
    +-- Virtual_READ / Virtual_WRITE
    |
    +-- KMBUS_RAM_READ / KMBUS_EEPROM_READ
    |
    +-- KBUS_* function family
            |
            v
      controller KBus/KM-BUS implementation
            |
            v
      physical KM-BUS accessories
~~~

Important consequences:

1. A VS2 function-code name does not prove that the local WB2A implements it.
2. A successful VS2 response does not by itself identify the returned data.
3. The same numeric address can refer to different data in different function
   spaces.
4. VS2/P300 function codes must not be mixed with older GWG telegram TYPE
   values even when names or numbers happen to overlap.
5. Controller-side KBus access is not automatically equivalent to physical
   KM-BUS slave emulation.

## Evidence levels used in this document

| Level | Meaning |
| --- | --- |
| **LOCAL-VERIFIED** | executed successfully on the local VDensHO1 / 20C2 |
| **SOURCE-CONFIRMED** | function/transport exists in current source or Vitosoft-derived data |
| **HISTORICAL** | documented working use on other Viessmann/OpenV setups |
| **HYPOTHESIS** | plausible interpretation, not yet demonstrated |

Only **LOCAL-VERIFIED** results may be treated as facts about this controller.

## VS2/P300 KBus and KM-BUS function family

The Vitosoft-derived function table contains:

| Hex | Function | Local status |
| ---: | --- | --- |
| 0x21 | Virtual_MBUS | untested |
| 0x41 | KMBUS_RAM_READ | **LOCAL-VERIFIED** |
| 0x43 | KMBUS_EEPROM_READ | **LOCAL-VERIFIED** |
| 0x51 | KBUS_DATAELEMENT_READ | untested |
| 0x52 | KBUS_DATAELEMENT_WRITE | **do not test yet** |
| 0x53 | KBUS_DATABLOCK_READ | untested |
| 0x54 | KBUS_DATABLOCK_WRITE | **do not test yet** |
| 0x55 | KBUS_TRANSPARENT_READ | untested |
| 0x56 | KBUS_TRANSPARENT_WRITE | **do not test yet** |
| 0x57 | KBUS_INITIALISATION_READ | untested |
| 0x58 | KBUS_INITIALISATION_WRITE | **do not test yet** |
| 0x59 | KBUS_EEPROM_LT_READ | untested |
| 0x5A | KBUS_EEPROM_LT_WRITE | **do not test yet** |
| 0x5B | KBUS_CONTROL_WRITE | **do not test yet** |
| 0x5D | KBUS_MEMBERLIST_READ | global Vitosoft event exists, but **not linked to VDensHO1** |
| 0x5E | KBUS_MEMBERLIST_WRITE | **do not test yet** |
| 0x5F | KBUS_VIRTUAL_READ | global Vitosoft access method, but **not linked to VDensHO1** |
| 0x60 | KBUS_VIRTUAL_WRITE | **do not test yet** |
| 0x61 | KBUS_DIRECT_READ | untested |
| 0x62 | KBUS_DIRECT_WRITE | **do not test yet** |
| 0x63 | KBUS_INDIRECT_READ | untested |
| 0x64 | KBUS_INDIRECT_WRITE | **do not test yet** |
| 0x65 | KBUS_GATEWAY_READ | no VDensHO1 Vitosoft event; do not prioritize blindly |
| 0x66 | KBUS_GATEWAY_WRITE | **do not test yet** |

Primary source for the names:

- https://github.com/sarnau/InsideViessmannVitosoft/blob/main/Viessmann2MQTT.py

The current upstream Optolink-Splitter also carries the KBus function names:

- https://github.com/philippoo66/optolink-splitter/blob/main/optolinkvs2_switch.py

## What the current Optolink-Splitter can actually send

The upstream generic command is:

~~~text
request;<function-code>;<address>;<length>;<data>;<protocol-id>
~~~

Aliases:

~~~text
request
req
~~~

The relevant source path is:

- https://github.com/philippoo66/optolink-splitter/blob/main/requests_util.py
- https://github.com/philippoo66/optolink-splitter/blob/main/optolinkvs2.py

The current `do_request()` implementation builds the VS2 telegram as:

~~~text
41 LEN PROTID FCT ADDR_H ADDR_L RLEN [DATA ...] CRC
~~~

Therefore the current debug path directly controls:

- function code;
- 16-bit address;
- requested/data length;
- optional payload bytes;
- protocol/message byte.

This is stronger than merely knowing that arbitrary function codes can be sent:
the request-frame layout used by the splitter is known.

The production Vitosoft metadata now resolves much of the earlier uncertainty
around the additional event fields.

The global `ecnEventType.xml` contains real KBus/KM-BUS rows with
`PrefixRead`/`PrefixWrite`. For example, 90 of 91
`KMBUS_EEPROM_READ` definitions use:

~~~text
PrefixRead = 030000000101
~~~

The Vitosoft-derived VS2 message builder and the Optolink-Splitter generic
request use the same structural location for optional bytes:

~~~text
41 LEN PROTID FCT ADDR_H ADDR_L BLOCKLEN [DATA ...] CHECKSUM
~~~

Therefore the strongest current mapping is:

~~~text
Vitosoft PrefixRead -> request DATA bytes after BlockLength
~~~

This mapping is **source-supported but not yet hardware-verified** with a real
Vitosoft-defined KBus event on the local WB2A. The earlier prefix-less 0x43/F8
experiments remain valid wire evidence, but they must not be treated as normal
Vitosoft KMBUS_EEPROM_READ semantics.

## Production Vitosoft join for the exact local profile

A complete production Vitosoft 300 SID1 data set was supplied on 2026-09-23
after first launch.

~~~text
DataPointDefinitionVersion = 0.0.26.4683
VDensHO1 datapoint type ID = 60
VDensHO1 event links        = 581
missing access definitions  = 0
~~~

The exact device selector in `ecnDataPointType.xml` is:

~~~text
VDensHO1
Identification              20C2
IdentificationExtension     0100
IdentificationExtensionTill 0103
~~~

The local controller reports developer version `01 03`, so this is the exact
Vitosoft profile for the local WB2A.

### Major result: VDensHO1 itself uses no KBUS/KMBUS FCRead/FCWrite

The complete 581-event join has:

~~~text
Virtual_READ           462
GFA_READ                94
Remote_Procedure_Call   22
blank                     2
undefined                 1

KBUS_* / KMBUS_*         0
~~~

This changes the priority of the project.

The global Vitosoft database contains 1797 KBus/KM-BUS access definitions, but
none are linked to the exact VDensHO1 profile. Their main users are legacy
Dekamatik and Vitocom/DEKATEL communication profiles.

In particular:

- the single `KBUS_MEMBERLIST_READ` event is linked to VCOM300/DEKATEL_F
  profiles, not VDensHO1;
- `KBUS_VIRTUAL_READ` exists globally (232 definitions), but is not a
  VDensHO1 access method;
- `KMBUS_EEPROM_READ` exists globally (91 definitions), but is not part of
  the VDensHO1 event tree.

Therefore the next local step is **not** a blind 0x5D/0x5F/0x65 sweep.

### KM-BUS accessory state is exposed through ordinary virtual objects

For VDensHO1, Vitosoft exposes remote-control presence/configuration through
normal virtual addresses.

A1/M1 remote:

~~~text
0x27A0
Virtual_READ + Virtual_WRITE
0 = not present
1 = Vitotrol 200
2 = Vitotrol 300
~~~

M2 remote:

~~~text
0x37A0
Virtual_READ + Virtual_WRITE
0 = not present
1 = Vitotrol 200
2 = Vitotrol 300
~~~

Remote software-index blocks:

~~~text
A1/M1 0x0A5C / 4 bytes
M2    0x0A60 / 4 bytes
~~~

Actual room values are separate and read-only according to Vitosoft:

~~~text
A1/M1 0x0896 / 2 bytes / Div10 °C / Virtual_READ only
M2    0x0898 / 2 bytes / Div10 °C / Virtual_READ only

sensor status:
A1/M1 0x089C
M2    0x089D
~~~

This makes an Optolink-only Vitotrol path more concrete but also defines the
remaining obstacle: the controller-side **remote type** can be configured via
Virtual_WRITE, while the measured room-temperature object has no documented
Virtual_WRITE path.

Full extraction details:

- [vitosoft/full-extraction-2026-09-23.md](vitosoft/full-extraction-2026-09-23.md)
- [vitosoft/vdensho1-vitotrol-events.csv](vitosoft/vdensho1-vitotrol-events.csv)

## Local hardware-verified results

### Generic transport control

~~~text
request;0x01;0x00F8;2;;0x00
-> 1;0xf8;20c2

r;0x00F8;2;raw;False
-> 1;0xf8;20c2
~~~

The generic request path therefore reaches the local controller correctly.

### 0x41 / KMBUS_RAM_READ

Single-byte reads of F8..FF returned:

~~~text
F8 20
F9 c2
FA 00
FB 03
FC 00
FD 00
FE 01
FF 03
~~~

A single 8-byte block read returned:

~~~text
request;0x41;0x00F8;8;;0x00
-> 1;0xf8;20c2000300000103
~~~

This exactly matches the normal eight-byte controller identity.

**Established:** 0x41 is implemented and supports coherent contiguous reads at
this location.

**Not established:** whether this is an actual KM-BUS RAM image, a mirrored
controller structure, an alias or some other controller-internal view.

### 0x43 / KMBUS_EEPROM_READ

A one-byte probe succeeded:

~~~text
request;0x43;0x00F8;1;;0x00
-> 1;0xf8;54
~~~

Individual one-byte reads of F8..FF produced:

~~~text
F8 54
F9 97
FA 54
FB 98
FC 54
FD 98
FE 54
FF 98
~~~

A single 8-byte block read produced:

~~~text
request;0x43;0x00F8;8;;0x00
-> 1;0xf8;5497549754975497
~~~

This proves that 0x43 is implemented and readable on the local controller.

It also proves that its semantics are **not yet safe to describe as a normal
linear EEPROM dump**: the block result does not reproduce the earlier sequence
of separate byte transactions and instead contains repeated 0x5497 words.

No relationship to the Kesselcodierstecker has been demonstrated.

### Repeated 0x43 F8/8 test — 2026-09-23

Ten identical read-only requests were executed over approximately 23 seconds:

~~~text
request;0x43;0x00F8;8;;0x00
~~~

All ten returned retcode 1, but the eight-byte payload changed between
transactions:

| Run | Raw payload | 2-byte unit |
| ---: | --- | --- |
| 1 | 1d801d801d801d80 | 1d80 |
| 2 | 4800480048004800 | 4800 |
| 3 | 5497549754975497 | 5497 |
| 4 | 5498549854985498 | 5498 |
| 5 | 411d411d411d411d | 411d |
| 6 | 1d801d801d801d80 | 1d80 |
| 7 | 5497549754975497 | 5497 |
| 8 | 5498549854985498 | 5498 |
| 9 | 5497549754975497 | 5497 |
| 10 | 3500350035003500 | 3500 |

The simultaneous 0x41 control series was completely stable in five runs:

~~~text
request;0x41;0x00F8;8;;0x00
-> 1;0xf8;20c2000300000103
~~~

#### Established from this experiment

- 0x43 at address 0x00F8 is **dynamic or transaction-dependent**.
- Every observed 8-byte response consists of one two-byte word repeated four
  times: `XY XY XY XY`.
- The changing values are not caused by general Optolink transport instability,
  because the 0x41 control remained bit-for-bit stable.
- The observed F8/8 result therefore must **not** be documented as eight
  sequential EEPROM bytes.

#### Current interpretation boundary

The strongest current hypothesis is that the P300 0x43 request is exposing a
two-byte register/result/mailbox-like quantity whose value is replicated to
fill the requested response length, or that our generic request is missing an
argument that changes the intended addressing semantics.

This is still a **HYPOTHESIS**, not a decoded protocol rule. In particular, the
two-byte words must not yet be interpreted as temperatures, addresses, status
words, raw KM-BUS telegram bytes or EEPROM contents.

The next experiment must characterize response-length behavior before trying
new addresses or other KBUS function families.

## Source evidence outside the local controller

### Historical KMBUS EEPROM access — GWG, not P300

Old vcontrold/OpenV configurations contain a `GETKMADDR` macro that sends
`01 43` and a test command described as "KM-Bus EEProm Adresse eingeben".

Important correction: this macro belongs to the **GWG protocol block** in
`xml/300/vcontrold.xml`, not to its P300 protocol block. It is therefore
historical evidence for a GWG KM-BUS EEPROM access mode, but it must **not** be
used as proof of the packet semantics of P300/VS2 function code 0x43.

The local P300/VS2 evidence for 0x43 stands independently because the WB2A
actually accepts and answers our generic VS2 function-code request.

Source:

- https://github.com/openv/vcontrold/blob/master/xml/300/vcontrold.xml
- https://github.com/openv/vcontrold/blob/master/xml/300/vito.xml

### Vitosoft-derived KBUS_VIRTUAL events

Current Vitosoft-derived tooling reports real `KBUS_VIRTUAL_READ` and
`KBUS_VIRTUAL_WRITE` events in the data set. In the GWG family analysis, these
events are explicitly treated as a K-bus tunnel that cannot be represented by
the ordinary GWG access modes.

Source:

- https://github.com/SoulSolistice/esphome_vitohome/blob/main/scripts/gen_catalog.py

This is useful evidence that `KBUS_VIRTUAL_*` is a real access method. It is
not evidence that the local 20C2 accepts arbitrary 0x5F/0x60 requests.

### Public VDensHO1 Vitosoft-derived catalog

The same project identifies a `VDensHO1` device token with identification
`0x20C2`.

Its normal generated P300 catalog intentionally filters access methods other
than ordinary Virtual_READ. Therefore that generated YAML is useful for device
identity and normal datapoints, but it cannot be used to infer the hidden KBus
event definitions that we need.

The next useful source artifact is the underlying Vitosoft event data, not the
already-filtered generated catalog.

## Current capability matrix

| Capability | Status | Meaning |
| --- | --- | --- |
| send arbitrary VS2 function code | **verified** | generic splitter request works |
| control VS2 address/length/payload/protid | **source-confirmed** | exact frame builder inspected |
| read 0x41 KMBUS RAM space | **verified at F8..FF** | coherent 8-byte response |
| read 0x43 function at F8 | **verified** | accepted repeatedly; payload is dynamic |
| characterize 0x43 F8 response shape | **LOCAL-VERIFIED** | dynamic 2-byte word is repeated/truncated to requested length; confirmed in raw VS2 frames |
| prove 0x43 is static/linear EEPROM | **disproved for current F8/8 interpretation** | repeated test is transaction-dependent |
| enumerate KBus members | **not a VDensHO1 Vitosoft path** | 0x5D exists globally only for VCOM300/DEKATEL_F profiles |
| inspect KBus initialisation | **unknown** | 0x57 not yet tested |
| transparent KBus read | **unknown** | 0x55 not yet tested |
| KBUS virtual read | **global source-confirmed, not VDensHO1-linked** | 232 definitions elsewhere in Vitosoft |
| gateway/mailbox access | **global function only / local relevance unknown** | no VDensHO1 Vitosoft event |
| inject accessory/slave state | **unknown** | no write experiment justified yet |
| emulate Vitotrol over Optolink only | **unknown** | depends on previous rows |
| access coding-plug EEPROM through 0x43 | **not proven** | no physical/semantic link established |

## Research questions

The project should answer these in order:

1. What is the current local state of the VDensHO1 remote-identification
   objects at 0x27A0/0x37A0 and their software-index/sensor-status objects?
2. What changes internally when a real or configured Vitotrol is present?
3. Is there any documented or experimentally safe controller-side path that
   populates the read-only room-temperature objects at 0x0896/0x0898?
4. Does a controlled A0 remote-identification write only configure the expected
   accessory type, or can it create enough internal state for operation without
   a physical slave?
5. Can Vitosoft `PrefixRead` be hardware-verified as the optional VS2 DATA
   bytes using a source-defined event on a suitable device/path?
6. What does the prefix-less dynamic two-byte result of 0x43 at F8 actually
   represent?
7. Are any global KBUS APIs useful on VDensHO1 despite not being present in its
   Vitosoft event tree?
8. Is there any evidence connecting the KMBUS EEPROM space to the physical
   Kesselcodierstecker?

## Experimental rules

Until the argument semantics are known:

- do not issue any `KBUS_*_WRITE` request;
- do not perform broad 0x0000..0xFFFF address sweeps;
- do not infer memory semantics from function names alone;
- record exact command, return code, response address and raw bytes;
- repeat every interesting read under identical conditions;
- compare block reads with equivalent single-byte reads;
- record controller operating state when a response appears dynamic;
- prefer source-derived addresses and lengths over guessed values.

A successful return code means only that the controller accepted the request.
It does not prove that the chosen address or interpretation is correct.

## Reproducible observation format

Every experiment should be recorded with at least:

~~~text
timestamp:
controller state:
function:
address:
length:
payload:
protocol-id:
command:
return code:
response address:
raw response:
repeat number:
notes:
~~~

For dynamic comparisons also record relevant boiler state such as idle/heating,
burner state, DHW activity and connected KM-BUS accessories.

## Immediate read-only experiment sequence

### A. Determine whether 0x43 F8/8 is stable — **completed 2026-09-23**

Result: dynamic/transaction-dependent. Every 8-byte response was a changing
two-byte word repeated four times. See the hardware-verified section above.

### B. Check length dependence at one address — **completed 2026-09-23**

Three passes were run for lengths 1 through 8.

Observed payloads:

~~~text
PASS 1
len1  54
len2  5491
len3  549754
len4  54985498
len5  5498549854
len6  460046004600
len7  54985498549854
len8  5497549754975497

PASS 2
len1  54
len2  5497
len3  749874
len4  54985498
len5  5498549854
len6  549854985498
len7  54975497549754
len8  73ff73ff73ff73ff

PASS 3
len1  54
len2  400f
len3  549754
len4  54985498
len5  5491549154
len6  549854985498
len7  54985498549854
len8  5498549854985498
~~~

For every response with length >= 2, the payload is exactly the requested-length
prefix of a transaction-specific two-byte word repeated indefinitely.

Examples:

~~~text
word 5498:
len4 -> 54 98 54 98
len5 -> 54 98 54 98 54
len6 -> 54 98 54 98 54 98
len7 -> 54 98 54 98 54 98 54
len8 -> 54 98 54 98 54 98 54 98

word 7498:
len3 -> 74 98 74

word 4600:
len6 -> 46 00 46 00 46 00

word 73ff:
len8 -> 73 ff 73 ff 73 ff 73 ff
~~~

This establishes a strong structural rule for the current F8 experiment:
`RLEN` controls the number of returned bytes, while the controller fills those
bytes by repeating one two-byte transaction result and truncating it when the
requested length is odd.

The two-byte result itself remains dynamic. The first byte is often 0x54 but is
not fixed; observed alternatives include 0x74, 0x46, 0x73 and 0x40.

Length 1 returned 0x54 in all three passes. That is interesting but not enough
to conclude that 0x54 is a fixed first byte, because longer transactions prove
that the first byte of the two-byte result can change.

#### Parser verification

The upstream Optolink-Splitter `receive_telegr()` implementation does not
construct or repeat response data. After validating frame length and checksum it
returns the received payload slice directly:

~~~text
retdata = inbuff[7:pllen+2]
~~~

Therefore the repeated two-byte structure is not produced by the MQTT/debug
formatting path.

The reference `InsideViessmannVitosoft/Viessmann2MQTT.py` implementation also
encodes the complete extended command value directly in the VS2 command byte,
including `KMBUS_EEPROM_READ = 67 / 0x43`. This supports the generic request
builder's use of a literal 0x43 command byte.

The splitter receiver currently derives a diagnostic `fctcd` value with
`inbuff[3] & 0x1F`. That masked diagnostic value is not used to build the
request and does not modify `retdata`; it should not be used to identify
extended function codes such as 0x43.

### C. Capture the unparsed VS2 response — **partially completed 2026-09-23**

The length-2 request was sent as a full raw VS2 frame:

~~~text
TX:
41 05 00 43 00 F8 02 42

RX:
06 41 07 01 43 00 F8 02 54 97 30
~~~

Decoded response:

| Byte(s) | Meaning |
| --- | --- |
| `06` | VS2 ACK |
| `41` | VS2 standard telegram start |
| `07` | payload length |
| `01` | LDAP + ResponseMessage |
| `43` | command echoed as KMBUS_EEPROM_READ |
| `00 F8` | response address |
| `02` | returned block length |
| `54 97` | returned data |
| `30` | modulo-256 VS2 checksum |

The checksum is valid.

This raw capture directly confirms all of the following without relying on the
normal response parser:

- the controller acknowledges the request;
- the response message identifier is a normal response;
- the returned command byte is still exactly `0x43`;
- the returned address is `0x00F8`;
- the controller reports block length `0x02`;
- the actual wire payload is `54 97`.

Therefore the earlier parsed `5497` result is genuine controller response data.

#### Length-8 raw attempt and debug-helper race

The first length-8 full-raw attempt produced:

~~~text
1;0x2303;0
~~~

This is not a valid raw response to the 0x43 request and is clearly an unrelated
normal MQTT response.

Root cause: for a single-field full-raw command, `tools/optolink-debug.py`
could not derive an expected datapoint address and therefore accepted the first
message arriving on the shared MQTT response topic. Normal address-based
requests already had filtering; the full-raw path did not.

The helper was fixed on 2026-09-23 so that an all-hex single-field command only
accepts an all-hex single-field response. Semicolon-delimited normal MQTT
responses are ignored while waiting for the raw frame.

Fix commit:

~~~text
9778719071e57bf988201a45d9b805ceb9017802
~~~

After deploying the updated helper, the length-8 raw capture was repeated:

~~~text
TX:
41 05 00 43 00 F8 08 48

RX:
06 41 0D 01 43 00 F8 08 54 98 54 98 54 98 54 98 01
~~~

Decoded response:

| Byte(s) | Meaning |
| --- | --- |
| `06` | VS2 ACK |
| `41` | VS2 standard telegram start |
| `0D` | payload length |
| `01` | LDAP + ResponseMessage |
| `43` | command echoed as KMBUS_EEPROM_READ |
| `00 F8` | response address |
| `08` | returned block length |
| `54 98 54 98 54 98 54 98` | returned data |
| `01` | modulo-256 VS2 checksum |

The checksum is valid:

~~~text
(0D + 01 + 43 + 00 + F8 + 08 + 54 + 98 + 54 + 98 + 54 + 98 + 54 + 98) mod 256
= 01
~~~

This closes the raw-frame verification. The controller itself returns a normal
VS2 response with command 0x43, address 0x00F8, block length 8 and the repeated
two-byte data pattern. The repetition is neither created by the MQTT helper nor
by the normal VS2 response parser.

For the current F8 experiment the structure is therefore **LOCAL-VERIFIED**:

~~~text
0x43 / address F8 / requested length N
-> normal VS2 response
-> response block length N
-> one transaction-specific 2-byte word repeated/truncated to N bytes
~~~

The semantic meaning of that 2-byte word remains unknown.

### D. Establish a stable 0x41 control series

Repeat the known identity read in the same session:

~~~bash
for i in $(seq 1 5); do
  /usr/local/bin/optolink-debug request "request;0x41;0x00F8;8;;0x00"
  sleep 1
done
~~~

This is the control path. If it changes unexpectedly, the experiment session
itself is not stable enough for interpretation.

### E. Extract real KBus events from Vitosoft data — **partially resolved**

A Vitosoft-derived VDensHO1 device export is now preserved in normalized form
under [vitosoft/](vitosoft/README.md).

Current local derived files:

- `vitosoft/vdensho1-events.csv`: 385 VDensHO1 events;
- `vitosoft/vdensho1-kmbus-participants.csv`: 18 events from
  `Diagnose System -> KM-Bus-Teiln.`;
- `vitosoft/source-manifest.json`: exact upstream paths, source commit and
  Git-LFS SHA-256 identities for the original XML files;
- `tools/extract-vitosoft-project-data.py`: extractor for the full XML set.

The KM-BUS participant group is source-confirmed for this device and includes,
among others:

| Meaning | Event | Address |
| --- | ---: | ---: |
| remote control A1/M1 identification | 1055 | 0x27A0 |
| remote control A1 software index | 5290 | 0x0A5C |
| remote control M2 identification | 1053 | 0x37A0 |
| remote control M2 software index | 5291 | 0x0A60 |
| internal pump identification | 885 | 0x5730 |
| internal pump software index | 5292 | 0x0A54 |
| KM-BUS pump A1 identification | 2894 | 0x27E5 |
| KM-BUS pump A1 software index | 5298 | 0x0A4C |

These are Vitosoft event addresses, not yet proof of the required VS2 function
code for each event.

The remaining low-level extraction target is every VDensHO1/20C2 event whose
`FCRead` or `FCWrite` contains:

~~~text
KMBUS_
KBUS_
~~~

Preserve all available fields, especially:

~~~text
event ID/name
FCRead
FCWrite
Address
BlockLength
ByteLength
Parameter
PrefixRead
PrefixWrite
Type/access
conversion metadata
~~~

Do not collapse duplicate numeric addresses across different function codes.

The original XML sources have now been identified in
`MorrisonHB/Optolink_02` as Git-LFS objects, including
`DPDefinitions.xml`, `ecnEventType.xml`, `ecnDataPointType.xml`,
`Textresource_de.xml` and `ecnEventTypeGroup.xml`. Exact SHA-256 values and
sizes are preserved in `vitosoft/source-manifest.json`.

The current GitHub tool can see the LFS pointers but cannot materialize the
large LFS object bytes. Consequently the device membership and addresses are
already preserved locally, while the exact `FCRead`/`FCWrite`,
`PrefixRead`/`PrefixWrite` and block-length join still requires the LFS XML
objects to be made available to the extractor.

Until that join is complete, do not invent argument semantics for
0x5D/0x57/0x65.

### F. Only then test additional read functions

Priorities:

1. `KBUS_MEMBERLIST_READ` / 0x5D
2. `KBUS_INITIALISATION_READ` / 0x57
3. `KBUS_GATEWAY_READ` / 0x65
4. `KBUS_TRANSPARENT_READ` / 0x55
5. `KBUS_VIRTUAL_READ` / 0x5F
6. `KBUS_DATAELEMENT_READ` / 0x51
7. `KBUS_DATABLOCK_READ` / 0x53
8. `KBUS_DIRECT_READ` / 0x61
9. `KBUS_INDIRECT_READ` / 0x63
10. `KBUS_EEPROM_LT_READ` / 0x59

Use source-derived parameters whenever possible. Do not blindly substitute
`0x00F8` into every function just because it works for 0x41/0x43.

## Decision points

### Optolink-only Vitotrol remains plausible if

- member/discovery state can be read and manipulated safely;
- a virtual/gateway/mailbox state exists inside the controller;
- room-temperature/accessory data can be injected into that internal state
  without physical slave timing.

### Physical KM-BUS hardware remains necessary if

- all KBUS APIs are strictly controller-master-to-real-slave operations;
- no controller-side virtual member state is exposed;
- writes merely send bus telegrams to an already-present accessory;
- correct slave current modulation and response timing remain mandatory.

## Related documents

- [vitotrol-kbus-optolink-emulation.md](vitotrol-kbus-optolink-emulation.md)
- [coding-plug-7833971-2015-0201.md](coding-plug-7833971-2015-0201.md)
- [device-vdensho1-20c2-wb2a.md](device-vdensho1-20c2-wb2a.md)
- [README.md](README.md)
- [../../../docs/project-roadmap.md](../../../docs/project-roadmap.md)
