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
| 0x5D | KBUS_MEMBERLIST_READ | untested / high interest |
| 0x5E | KBUS_MEMBERLIST_WRITE | **do not test yet** |
| 0x5F | KBUS_VIRTUAL_READ | source-confirmed / local untested |
| 0x60 | KBUS_VIRTUAL_WRITE | **do not test yet** |
| 0x61 | KBUS_DIRECT_READ | untested |
| 0x62 | KBUS_DIRECT_WRITE | **do not test yet** |
| 0x63 | KBUS_INDIRECT_READ | untested |
| 0x64 | KBUS_INDIRECT_WRITE | **do not test yet** |
| 0x65 | KBUS_GATEWAY_READ | untested / high interest |
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

What is **not** yet known is how Vitosoft-specific event metadata such as
`Parameter`, `PrefixRead` and `PrefixWrite` maps onto these VS2 fields for
the KBus function family. Those values may be encoded in address or payload
bytes, may be consumed only by higher-level Vitosoft logic, or may vary by
function. This mapping must be established from real event definitions or
captures rather than guessed.

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
| characterize 0x43 F8/8 shape | **verified** | one changing 2-byte word repeated four times |
| prove 0x43 is static/linear EEPROM | **disproved for current F8/8 interpretation** | repeated test is transaction-dependent |
| enumerate KBus members | **unknown** | 0x5D not yet tested |
| inspect KBus initialisation | **unknown** | 0x57 not yet tested |
| transparent KBus read | **unknown** | 0x55 not yet tested |
| KBUS virtual read | **source-confirmed, local unknown** | 0x5F event type exists elsewhere |
| gateway/mailbox access | **unknown** | 0x65 not yet tested |
| inject accessory/slave state | **unknown** | no write experiment justified yet |
| emulate Vitotrol over Optolink only | **unknown** | depends on previous rows |
| access coding-plug EEPROM through 0x43 | **not proven** | no physical/semantic link established |

## Research questions

The project should answer these in order:

1. What does the dynamic two-byte result of 0x43 at F8 actually represent,
   and why is it repeated to the requested length?
2. Which KBus read function codes are implemented on VDensHO1 / 20C2?
3. What exact argument layout do those functions require?
4. How do Vitosoft `Parameter` / `PrefixRead` values map to the VS2 request
   fields?
5. Can the controller expose its KBus member/discovery state through 0x5D,
   0x57 or 0x65?
6. Can accessory data be read through 0x5F/0x55/0x61/0x63/0x65?
7. Is any controller-side state writable in RAM without persistent EEPROM
   effects?
8. Is there a controller-side path that can create or update a virtual Vitotrol
   member?
9. Is there any evidence connecting the KMBUS EEPROM space to the physical
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

### B. Check length dependence at one address — **next**

Test every length from 1 through 8, with three complete passes:

~~~bash
for pass in 1 2 3; do
  echo
  echo "=== PASS $pass ==="
  for len in 1 2 3 4 5 6 7 8; do
    echo "--- len=$len ---"
    /usr/local/bin/optolink-debug request       "request;0x43;0x00F8;$len;;0x00"
  done
done
~~~

The value itself may change between requests. The important property is the
**shape** for each length:

- does length 1 return only the first byte of a two-byte result?
- does length 2 return exactly one two-byte result?
- do lengths 3/5/7 truncate a repeating two-byte pattern?
- do lengths 4/6/8 contain exact repetitions?
- does changing length alter the underlying two-byte result semantics?

This test is deliberately limited to the already verified function/address and
does not introduce a new address space.

### C. Establish a stable 0x41 control series

Repeat the known identity read in the same session:

~~~bash
for i in $(seq 1 5); do
  /usr/local/bin/optolink-debug request "request;0x41;0x00F8;8;;0x00"
  sleep 1
done
~~~

This is the control path. If it changes unexpectedly, the experiment session
itself is not stable enough for interpretation.

### D. Extract real KBus events from Vitosoft data

For the VDensHO1/20C2 family collect every event whose `FCRead` or `FCWrite`
contains:

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

### E. Only then test additional read functions

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
