# KBus / KM-BUS research via Optolink

Status: **active research**
Last updated: **2026-09-24**

This is the canonical research note for all controller-side KBus/KM-BUS access
through the VS2/P300 Optolink interface on the local Vitodens 200-W WB2A.

Vitotrol emulation is one important use case, but not the scope boundary. The
same transport may also be relevant to accessory discovery, controller-internal
bus state, coding-plug questions and other undocumented functions.

Vitotrol-specific interpretation remains in
[vitotrol-kbus-optolink-emulation.md](vitotrol-kbus-optolink-emulation.md).

The current deep analysis of the read-only memory/access families is:
[vitosoft/kmbus-read-memory-analysis-2026-09-24.md](vitosoft/kmbus-read-memory-analysis-2026-09-24.md).
The corresponding execution task is GitHub issue **#30**.

The first bounded live correlation run is prepared in
[../../../docs/kmbus-ram-correlation-probe.md](../../../docs/kmbus-ram-correlation-probe.md),
with a pre-created evidence template at
[vitosoft/kmbus-ram-correlation-2026-09-24-evidence.json](vitosoft/kmbus-ram-correlation-2026-09-24-evidence.json).

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
| 0x56 | KBUS_TRANSPARENT_WRITE | source-analyzed: Vitosoft uses 1-byte participant datapoint writes; **no raw-frame evidence / do not live-probe** |
| 0x57 | KBUS_INITIALISATION_READ | untested |
| 0x58 | KBUS_INITIALISATION_WRITE | **do not test yet** |
| 0x59 | KBUS_EEPROM_LT_READ | untested |
| 0x5A | KBUS_EEPROM_LT_WRITE | **do not test yet** |
| 0x5B | KBUS_CONTROL_WRITE | enum exists but production Vitosoft has **0 event definitions**; argument format unknown / do not live-probe |
| 0x5D | KBUS_MEMBERLIST_READ | global Vitosoft event exists, but **not linked to VDensHO1** |
| 0x5E | KBUS_MEMBERLIST_WRITE | source-analyzed gateway participant-list management; **not VDensHO1 / do not live-probe** |
| 0x5F | KBUS_VIRTUAL_READ | global Vitosoft access method, but **not linked to VDensHO1** |
| 0x60 | KBUS_VIRTUAL_WRITE | source-analyzed 1-byte KBus datapoint writes; **not VDensHO1 / do not live-probe** |
| 0x61 | KBUS_DIRECT_READ | untested |
| 0x62 | KBUS_DIRECT_WRITE | source-analyzed VCOM300/DEKATEL direct-channel records; **not VDensHO1 / no raw-frame evidence** |
| 0x63 | KBUS_INDIRECT_READ | untested |
| 0x64 | KBUS_INDIRECT_WRITE | source-analyzed indexed participant/channel writes; **not VDensHO1 / do not live-probe** |
| 0x65 | KBUS_GATEWAY_READ | no VDensHO1 Vitosoft event; do not prioritize blindly |
| 0x66 | KBUS_GATEWAY_WRITE | one Vitosoft gateway-control event only; **no raw-frame evidence / do not live-probe** |

### 2026-09-24 read-function inventory checkpoint

The verified Collector-v6 All-Devices export materially changes the read
research. Across 11,582 events and 38 protocol-function names it contains the
following read definitions:

~~~text
KMBUS_RAM_READ             0
KMBUS_EEPROM_READ         91
XRAM_READ                 12
Virtual_MBUS             254
KBUS_DATAELEMENT_READ      7
KBUS_TRANSPARENT_READ    850
KBUS_EEPROM_LT_READ      500
KBUS_MEMBERLIST_READ       1
KBUS_VIRTUAL_READ        232
KBUS_DIRECT_READ          11
KBUS_INDIRECT_READ        97
~~~

Functions such as `KBUS_DATABLOCK_READ`, `KBUS_INITIALISATION_READ` and
`KBUS_GATEWAY_READ` are present in the protocol vocabulary but have no event
rows in this captured Vitosoft definition set.

The most important negative/positive pair is `KMBUS_RAM_READ`:

- Vitosoft event definitions using it: **0**;
- local WB2A acceptance of raw function `0x41`: **verified**;
- local `0x41 / 0x00F8 / 8`: `20c2000300000103`, exactly matching the
  ordinary Virtual_READ identity block.

Therefore Vitosoft event/profile membership is not a safe capability boundary
for low-level read functions. Conversely, a successful low-level read does not
prove the name's literal memory semantics.

The targeted v6 slice has now been completed: **2,055 read-event rows** were
extracted reproducibly from `all-events.csv`.

Key semantic results:

- 90/91 `KMBUS_EEPROM_READ` definitions use
  `PrefixRead=030000000101`; the prefixed group consists of persistent
  **LGM27 burner-control** parameters such as identity, parameter set,
  modulation values, temperature limits, minimum burner pause/runtime and
  controller delay.
- the sole no-prefix exception is event 2190 at `0x0310`,
  `Geräteidentifikation Schalterblock`, in DEKATEL/VCOM profiles;
- all 12 `XRAM_READ` events are now resolved and include volatile external
  demand/blocking, several runtime timers and water pressure in GWG profiles;
- all 850 `KBUS_TRANSPARENT_READ` rows carry a 2-byte prefix;
- 227/232 `KBUS_VIRTUAL_READ` rows carry a 2-byte prefix;
- 96/97 `KBUS_INDIRECT_READ` rows carry a 1-byte prefix, and their event
  names prove that this byte is the **participant number**;
- `Virtual_MBUS` is linked to actual external meter profiles and must remain
  separate from KM-BUS.

These catalog results prove that PrefixRead is meaningful metadata, but they do
**not** prove that it is serialized for every function family. Static analysis
of the captured Vitosoft host now shows a sharp boundary: PrefixRead is
converted into request bytes on the `Remote_Procedure_Call / 0x07` path, while
ordinary non-RPC reads such as `KMBUS_EEPROM_READ / 0x43` do not consume it.
The prefix-less 0x43 frame is therefore the standard host-generated shape for
that function in this build.

See the dedicated analysis for the full derived inventory, memory/firmware
boundary and read-only experiment sequence:
[vitosoft/kmbus-read-memory-analysis-2026-09-24.md](vitosoft/kmbus-read-memory-analysis-2026-09-24.md).

### Write-family semantics from the production Vitosoft set

The complete production `ecnEventType.xml` was analyzed specifically to test
the hypothesis that a generic KBus write function might inject a complete
slave-side Vitotrol telegram.

The result is currently **negative**:

~~~text
KBUS_TRANSPARENT_WRITE  853 definitions, every one BlockLength=1
KBUS_DIRECT_WRITE        11 definitions, VCOM300/DEKATEL direct channels
KBUS_GATEWAY_WRITE        1 definition, "delete all fault messages"
KBUS_MEMBERLIST_WRITE     2 definitions, gateway participant management
KBUS_CONTROL_WRITE        0 definitions
~~~

No one of these functions is linked to the exact local VDensHO1 profile.

In particular, `KBUS_TRANSPARENT_WRITE` is shaped as a participant datapoint
operation:

~~~text
PrefixWrite = 2-3 byte KBus target/subselector
BlockLength = 1 application data byte
~~~

That does not resemble the known physical Vitotrol slave frames, which are
12-16 bytes including class/command/slot/CRC.

Therefore there is currently **no source-supported VS2 request** that can be
described as "inject this raw Vitotrol slave telegram into the internal
KM-BUS master".

Detailed evidence:

- [vitosoft/kbus-write-function-analysis.md](vitosoft/kbus-write-function-analysis.md)
- [vitotrol-kmbus-wire-protocol.md](vitotrol-kmbus-wire-protocol.md)

Blind live-boiler probes of 0x56/0x5B/0x5E/0x62/0x66 are not justified by the
current source evidence.

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

The production Vitosoft metadata and recovered host implementation now resolve
the optional-data question more narrowly than the earlier working hypothesis.

The global catalog contains real `PrefixRead`/`PrefixWrite` fields, but the
captured host build does **not** serialize PrefixRead for ordinary non-RPC
reads. PrefixRead is converted into `BlockDataToDevice` only on the
`Remote_Procedure_Call / 0x07` path.

For an ordinary `0x43 / 0x0001 / len 1` request the host-generated serial
shape is therefore:

~~~text
41 05 00 43 00 01 01 4A
~~~

with no PrefixRead bytes.

The 90 catalog rows carrying `030000000101` are all linked only to GWG
profiles. Independent GWG protocol sources map KMBUS EEPROM access to the old
GWG TYPE byte `0x43` with an 8-bit-address frame, not to extra P300 request
data. The same numeric byte appears in two different protocol layers and must
not be used to transfer LGM27/GWG semantics to local VDensHO1 P300 traffic.

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

## Live Phase A started - bounded 0x41 correlation

The first live phase deliberately avoids any broad memory scan. It compares
ordinary `Virtual_READ` and `KMBUS_RAM_READ 0x41` at seven already understood
addresses with source-backed lengths:

~~~text
0x00F8 / 8   controller identity / positive control
0x0A3C / 1   final internal-pump command shadow
0x7660 / 2   internal-pump runtime/output
0x7663 / 2   A1 runtime/calculated pump request
0x5730 / 1   K30 internal-pump identity/capability
0x0A54 / 4   internal-pump software-index block
0x27A0 / 1   A1/M1 remote-control identification
~~~

The objective is to classify each pair as identical, stable-different,
dynamic-different, Virtual-only, KMBUS-only or error.

A match across all addresses would support a broad mirror/alternate-access
interpretation. Differences at runtime addresses would be especially valuable
because they would reveal a partially overlapping hidden state space. If only
`0x00F8` works, it must be treated as a special/common identity structure.

Runbook:
[../../../docs/kmbus-ram-correlation-probe.md](../../../docs/kmbus-ram-correlation-probe.md).

## Transport correction - permanent production transport is VS1/KW

A critical transport-context correction applies to all live KBus/KM-BUS
experiments after the production GFA activation on 2026-09-24.

The local splitter is intentionally running **permanent VS1/KW**:

~~~text
vs1protocol = True
olbreath    = 0.15
~~~

This was activated and verified to support one persistent single-owner VS1
session carrying both:

- `F7 Virtual_READ` for normal controller datapoints;
- `6B GFA_READ` for burner/GFA values including blower speed P06.

Evidence:
[vitosoft/vs1-gfa-production-activation-2026-09-24-evidence.json](vitosoft/vs1-gfa-production-activation-2026-09-24-evidence.json).

The splitter adapter explicitly does **not** support the generic VS2/P300
`request` function while VS1 is selected:

~~~text
request command not supported with VS1/KW, use raw instead
~~~

The 22:08 journal captured this exact warning for both generic function 0x01
and 0x41.

A second correction is equally important: sending a P300 frame through the
splitter's generic `raw` command does not change protocol mode. In the active
VS1 session, raw bytes such as:

~~~text
41 05 00 01 00 F8 08 06
41 05 00 41 00 F8 08 46
~~~

are simply injected into the VS1/KW session and time out. This is expected and
is **not** evidence that P300 or 0x41 stopped working.

Therefore:

1. the earlier successful local `KMBUS_RAM_READ 0x41` remains valid evidence
   from a VS2/P300 context;
2. the 22:01/22:08 timeout runs are transport-context failures only;
3. no further 0x41 semantic test may be executed through the live permanent-VS1
   MQTT request path;
4. future 0x41 work requires a bounded maintenance window that temporarily
   stops the VS1 serial owner, explicitly initializes P300/VS2 on the Optolink
   port, performs read-only requests, closes the direct serial session, and
   restores/validates permanent VS1 + GFA polling.

This correction supersedes the earlier dispatcher/version-mismatch hypothesis.

## Live Phase A result - control failed before semantic comparison

First run window:

~~~text
2026-09-24T22:01:32+02:00
..
2026-09-24T22:02:17+02:00
~~~

All seven ordinary `Virtual_READ` controls succeeded:

~~~text
0x00F8/8 -> 20c2000300000103
0x0A3C/1 -> 00
0x7660/2 -> 0000
0x7663/2 -> 0000
0x5730/1 -> 01
0x0A54/4 -> 01110101
0x27A0/1 -> 00
~~~

Every paired `KMBUS_RAM_READ 0x41` invocation timed out at the debug client,
including the previously locally verified positive control:

~~~text
request;0x41;0x00F8;8;;0x00
-> timeout
~~~

This invalidates the run as a memory-map comparison. It does **not** overturn
the earlier local proof that 0x41 works at 0x00F8. This run is now understood as a **protocol-context error**: the live splitter was already in permanent VS1/KW. The generic VS2/P300 request path is intentionally unavailable there. No RAM-address inference is valid.

Important implementation detail: `optolink-debug` filters MQTT responses by
the requested address. Therefore a printed timeout means that no response with
the expected address was accepted within the timeout. It does **not** prove
that the splitter/controller emitted no response at all; an error or response
using another address could have been discarded by the helper.

Next gate:

1. verify ordinary `r` still works;
2. verify generic `request;0x01;...` works;
3. retry the known-positive `0x41/0x00F8/8` with a longer timeout;
4. capture all MQTT responses, including unmatched-address responses;
5. only after the positive 0x41 control returns, resume the seven-address
   correlation matrix.

Evidence:
[vitosoft/kmbus-ram-correlation-2026-09-24-evidence.json](vitosoft/kmbus-ram-correlation-2026-09-24-evidence.json).

## Live Phase A PASS - 0x41 mirrors 0x01 on all seven sampled addresses

A guarded temporary P300 maintenance window was executed on the exact local
WB2A / VDensHO1 / 20C2 controller while permanent production remained VS1/KW
before and after the test.

Window:

~~~text
2026-09-24T22:23:33.057+02:00
..
2026-09-24T22:23:40.228+02:00
~~~

The probe:

- stopped Party and the permanent VS1 splitter;
- explicitly initialized P300;
- verified the normal 0x01 identity control;
- compared 0x01 Virtual_READ and 0x41 KMBUS_RAM_READ on seven allowlisted
  addresses;
- left the interface in detection state;
- restarted splitter and Party;
- verified `VS1/KW protocol initialized` after restoration.

Result:

| Address | Meaning | 0x01 | 0x41 | Class |
| --- | --- | --- | --- | --- |
| `0x00F8/8` | controller identity | `20c2000300000103` | `20c2000300000103` | IDENTICAL |
| `0x0A3C/1` | final pump command | `00` | `00` | IDENTICAL |
| `0x7660/2` | internal pump runtime | `0000` | `0000` | IDENTICAL |
| `0x7663/2` | A1 pump request | `0000` | `0000` | IDENTICAL |
| `0x5730/1` | internal pump identity | `01` | `01` | IDENTICAL |
| `0x0A54/4` | internal pump SW block | `01110101` | `01110101` | IDENTICAL |
| `0x27A0/1` | A1 remote identity | `00` | `00` | IDENTICAL |

The wire trace proves that 0x41 is genuinely handled as its own function code.
For example:

~~~text
TX 41 05 00 41 00 f8 08 46
RX 06
RX 41 0d
RX 01 41 00 f8 08 20 c2 00 03 00 00 01 03 38
~~~

The response command byte remains `0x41`; the client is not silently rewriting
the request to `0x01`.

### Interpretation

This is now strong local evidence that `KMBUS_RAM_READ 0x41` exposes an
alternate or mirrored **logical address view** for at least these sampled
controller/KM-BUS-related objects.

It is no longer credible to interpret the 0x41 address field as direct raw CPU
RAM for these samples. Static non-zero values (`0x5730=01`,
`0x0A54=01110101`) mirror exactly as well as the identity block.

The remaining caveat is dynamic behavior: during this run
`0x0A3C`, `0x7660` and `0x7663` were all zero. Therefore the next
high-value experiment is to repeat only those three pairs during a naturally
active heating/DHW/pump state and verify whether non-zero transitions remain
byte-identical and temporally aligned.

Evidence:
[vitosoft/kmbus-ram-correlation-2026-09-24-evidence.json](vitosoft/kmbus-ram-correlation-2026-09-24-evidence.json).

## Live Phase B PASS - dynamic 0x41 mirror and 30 -> 50 pump arbitration

A second guarded P300 window caught the pump path in a non-zero runtime state.

Window:

~~~text
2026-09-24T22:26:31.578+02:00
..
2026-09-24T22:26:38.704+02:00
~~~

Again, all seven 0x01/0x41 pairs were byte-identical. The critical dynamic
objects were:

~~~text
0x0A3C / 1
  0x01 -> 32
  0x41 -> 32

0x7660 / 2
  0x01 -> 03 32
  0x41 -> 03 32

0x7663 / 2
  0x01 -> 03 1e
  0x41 -> 03 1e
~~~

Using the already source-validated object layouts:

- `0x7663[1] = 0x1E = 30 %`: A1 calculated/runtime pump request;
- `0x7660[1] = 0x32 = 50 %`: actual internal-pump speed path;
- `0x0A3C = 0x32 = 50 %`: final internal-pump command shadow.

This closes the dynamic-mirror question for the sampled addresses:
`KMBUS_RAM_READ 0x41` tracks changing non-zero state exactly like
`Virtual_READ 0x01`.

It also provides an independent high-value pump-arbitration observation:

~~~text
A1 request           30 %   0x7663[1] = 0x1E
        |
        v
hidden arbitration / clamp
        |
        v
final internal       50 %   0x0A3C    = 0x32
physical internal    50 %   0x7660[1] = 0x32
~~~

The previously established configuration is E7=30 % and coding-plug
GWG75/minimum internal-pump speed=50 %. Therefore the observed 30 -> 50 uplift
is **exactly consistent with a GWG75 minimum clamp**. This run did not re-read
E7/GWG75 in the same window, so record that as the leading explanation rather
than a fully isolated causal proof.

### Decision

Further broad 0x41 probing is now deprioritized. Its sampled behavior is
sufficiently characterized as an alternate/mirrored logical read path.

The next read-only targets should be functions that Vitosoft demonstrably uses
for distinct spaces:

1. `0x31 XRAM_READ` - source-defined volatile timers/state;
2. `0x43 KMBUS_EEPROM_READ` - only after reconstructing a complete prefixed
   Vitosoft request;
3. `0x55/0x5F/0x63` structured KBus reads after prefix/participant decoding.

## XRAM_READ 0x31 local result - no source target succeeded

After closing the dynamic 0x41 mirror question, the next guarded P300 run tested
all six unique XRAM request shapes derived from the verified Vitosoft-v6
metadata.

Result:

~~~text
0x0000/1 -> 0x31 Error Message payload 05
0x003A/2 -> 0x31 Error Message payload 05
0x003D/2 -> 0x31 Error Message payload 05
0x0040/2 -> 0x31 Error Message payload 05
0x0042/2 -> 0x31 Error Message payload 05
0x0088/2 -> 0x31 Error Message payload 05
~~~

The corresponding 0x01 Virtual_READ controls at these addresses also failed,
with inner payload `01`.

All 12 Vitosoft XRAM definitions are GWG-family rows and have empty
`PrefixRead`. Therefore a missing prefix is not a plausible explanation for
this local result.

The helper completed and restored VS1/Party successfully; its historical
`RESULT=PASS` meant **probe execution/restoration passed**, not that XRAM
reads succeeded. The helper has now been corrected to print separate fields:

~~~text
XRAM_SUCCESS_COUNT=...
XRAM_CAPABILITY=...
EXECUTION_RESULT=...
~~~

Decision: the known Vitosoft XRAM shapes are closed as a direct local path.
Do not blind-scan 0x31. The subsequent manually prefixed 0x43 experiment is
retained below as historical evidence, but host analysis later showed that the
captured Vitosoft non-RPC serializer does not emit those PrefixRead bytes.

## Historical manually prefixed KMBUS_EEPROM_READ 0x43 experiment

The exact source-defined Vitosoft request shape from event 578 was executed in
a guarded temporary P300 window:

~~~text
source profile: GWG_BT2
source label:   Kennung (Prog1)
function:       KMBUS_EEPROM_READ / 0x43
address:        0x0001
read length:    1
PrefixRead:     03 00 00 00 01 01
~~~

Wire request:

~~~text
41 0B 00 43 00 01 01 03 00 00 00 01 01 55
~~~

Local response:

~~~text
41 06 01 43 00 01 01 88 D4
~~~

Decoded:

~~~text
message type = normal Response Message
function     = 0x43
address      = 0x0001
length       = 1
data         = 0x88
~~~

The controller accepted this manually extended frame and returned `0x88`.
That fact is preserved, but the interpretation has changed: the fresh-session
P/N test found no isolated effect, and later host CIL analysis proves that the
captured Vitosoft standard non-RPC `0x43` path does **not** append PrefixRead.

Therefore this request must not be called an exact Vitosoft wire shape, and
`0x88` must not be assigned the source GWG_BT2/LGM27 label `Kennung (Prog1)`.
The experiment demonstrates tolerance/handling of extra bytes, not a proven
routed subordinate EEPROM namespace.

Evidence:
[vitosoft/kmbus-eeprom-prefixed-live-2026-09-24-evidence.json](vitosoft/kmbus-eeprom-prefixed-live-2026-09-24-evidence.json).

Historical decision: the bounded 13-shape expansion was completed before the
serializer path was recovered. No further prefixed 0x43 expansion is justified.

## Bounded 0x43 source-map result - 13/13 success, EEPROM semantics not proven

The complete bounded set of exact GWG_BT2 source-defined 0x43 block shapes
sharing `PrefixRead=030000000101` was executed locally. All **13/13**
requests returned normal successful 0x43 responses, and the production
VS1/Party state was restored cleanly. The 0x0001/1 result `88` was repeated
three times identically.

However, the returned bytes expose an important anomaly:

~~~text
0x0001/1   -> 88
0x000A/5   -> 4000000000
0x000F/8   -> 1f00000000000000

0x0064/2   -> 5497
0x006A/6   -> 549854985498
0x0070/7   -> 54985498549854
0x0078/5   -> 5498549854
0x0078/8   -> 5498549854985498
0x0083/4   -> 97549754
0x0091/1   -> 97
0x00A0/10  -> 54985498549854985498
0x00AA/10  -> 54985498549854985498
0x00B4/10  -> 54985498549854985498
~~~

The same-address 0x0078 length variants are especially diagnostic:
`0x0078/5` is exactly the first five bytes of `0x0078/8`, and both are a
repetition/truncation of the two-byte word `54 98`. The three distinct
source fault blocks 0x00A0, 0x00AA and 0x00B4 also returned the exact same
10-byte repeated-word payload.

This reproduces the structural pattern already seen in older prefix-less 0x43
experiments. Therefore:

- a successful 0x43 response is **not sufficient evidence of literal EEPROM
  contents**;
- the low blocks 0x0001/0x000A/0x000F remain interesting because they do not
  follow the repeated-word pattern;
- the source GWG_BT2/LGM27 meanings must not be assigned to the local bytes;
- the earlier wording that PrefixRead was already hardware-proven to alter
  routing was too strong. The local controller accepts the frame carrying the
  six extra bytes, but the next experiment must compare the **same address**
  with and without those bytes.

Evidence:
[vitosoft/kmbus-eeprom-map-live-2026-09-24-evidence.json](vitosoft/kmbus-eeprom-map-live-2026-09-24-evidence.json).

A guarded PrefixRead A/B discriminator is prepared as
`wb2a-kmbus-prefix-ab-probe`. It uses P-N-P ordering (prefixed, no-prefix,
prefixed) on only four fixed source-derived targets:
`0x0001/1`, `0x000A/5`, `0x0078/8`, `0x00A0/10`.

## PrefixRead P-N-P discriminator - one clean effect, two dynamic blocks

A same-address read-only comparison was executed in one P300 session using the
order **prefixed -> no-prefix -> prefixed** with
`PrefixRead=030000000101`.

Results:

~~~text
0x0001/1:
  P1 = 88
  N  = 87
  P2 = 88
  -> PREFIX_EFFECT_OBSERVED

0x000A/5:
  P1 = 4000000000
  N  = 4000000000
  P2 = 4000000000
  -> NO_PREFIX_EFFECT_OBSERVED

0x0078/8:
  P1 = 5497549754975497
  N  = 5497549754975497
  P2 = d301d301d301d301
  -> DYNAMIC_OR_INCONCLUSIVE

0x00A0/10:
  P1 = 54985498549854985498
  N  = f201f201f201f201f201
  P2 = 54975497549754975497
  -> DYNAMIC_OR_INCONCLUSIVE
~~~

The earlier same-session `0x0001/1` result initially suggested that the six extra
request bytes were not universally ignored: within a sub-second P-N-P
sequence the two prefixed reads agreed at `88`, while the otherwise identical
no-prefix read returned `87`.

That still does **not** prove the semantic role is specifically participant
routing. It only proves that the request form can affect the local 0x43 result.

The high-address blocks remain unsuitable for literal EEPROM interpretation.
At `0x0078`, two nominally identical prefixed reads changed from repeated
`5497` to repeated `d301` within the same short sequence. At `0x00A0`,
the two prefixed controls also disagreed. This confirms a fast
transaction/state-dependent mechanism behind the repeated two-byte words.

Next gate: repeat only `0x0001/1` with **one fresh P300 session per trial**
and a balanced P/N order. This removes same-session carry-over and sequence bias
before assigning stronger PrefixRead semantics.

Evidence:
[vitosoft/kmbus-prefix-ab-live-2026-09-24-evidence.json](vitosoft/kmbus-prefix-ab-live-2026-09-24-evidence.json).

## Fresh-session PrefixRead discriminator - NO isolated effect

The apparent same-session PrefixRead effect at `0x0001/1` was retested with a
stronger design: every single 0x43 request used a **freshly initialized P300
session**, and the order was balanced:

~~~text
P N N P N P P N
~~~

where `P` carries `03 00 00 00 01 01` and `N` carries no extra bytes.

Results:

~~~text
P values: 81, 81, 81, 87
N values: 87, 81, 81, 81

P counts: 81 x3, 87 x1
N counts: 81 x3, 87 x1
~~~

Classification:

~~~text
NO_ISOLATED_PREFIX_EFFECT
~~~

This supersedes the earlier one-session `88 -> 87 -> 88` observation as
evidence for PrefixRead semantics. The two request forms have the **same
observed distribution** once session carry-over is removed.

The important correction is therefore:

- local 0x43 accepts frames with extra bytes after BlockLength;
- those bytes are **not hardware-proven to control routing or target
  selection** on the local VDensHO1;
- even `0x0001/1` is dynamic across fresh sessions (`81` / `87`), so it
  is not a demonstrated static EEPROM byte;
- the repeated high-address words and the fresh-session low-byte variation now
  point more strongly to a transaction/status/mailbox-like mechanism than to a
  direct linear EEPROM view.

The Vitosoft host implementation has now been recovered from the verified
private archive. The relevant CIL establishes:

- `RPCConverter.IsFCReadRpc()` returns true only for `FCRead == 0x07`;
- on that RPC path, `ConvertRpcToDevice_Default()` parses PrefixRead hex
  into bytes, stores them in `BlockDataToDevice`, and changes BlockLength to
  the prefix-byte count;
- standard non-RPC reads do not perform that conversion;
- `MultiRequestDictionary.createListOfRequest()` copies FCRead directly to
  the request function code;
- `createMultiRequest()` constructs LDAP data from Address, BlockLength and
  BlockDataToDevice;
- `LDAPMessage.toByteArray()` serializes
  `00 FCT ADDR_H ADDR_L DATA_LENGTH [DATA...]`;
- serial DAP wraps that as
  `41 LEN 00 FCT ADDR_H ADDR_L DATA_LENGTH [DATA...] CRC`;
- the VS1 converter does not support function `0x43`;
- a managed-assembly scan of the extracted ServiceTool tree found no external
  preprocessing path that maps PrefixRead into BlockDataToDevice for ordinary
  reads.

For `0x43 / 0x0001 / len 1`, the captured host-generated serial frame is:

~~~text
41 05 00 43 00 01 01 4A
~~~

with no PrefixRead payload.

Thus the serializer question is closed for this Vitosoft build. The manually
prefixed form used in earlier experiments was not the vendor host shape. The
remaining research question is what the local controller's dynamic no-prefix
0x43 response represents.

Private derived report:
`collector-output/20260924-143439/prefixread-serializer-analysis-2026-09-25.md`
(commit `1bd156be85d947a3af890db426ce4462d71b4099`).

Decision: no more PrefixRead discrimination and no broad 0x43 expansion.

Evidence:
[vitosoft/kmbus-prefix-isolated-live-2026-09-24-evidence.json](vitosoft/kmbus-prefix-isolated-live-2026-09-24-evidence.json).

## 0x43 response-side closure and next discriminator

The Vitosoft response converter has now been traced as well.

For normal LDAP responses it dispatches on the **low five bits** of the command
byte and copies the bytes after the five-byte LDAP header directly into the
event block before applying normal event conversion metadata:

~~~text
0x41 & 0x1F = 0x01
0x43 & 0x1F = 0x03
~~~

Therefore:

- local repeated `0x43` payloads such as `5498`, `5497`, `d301` and
  `f201` are device-produced raw bytes, not a Vitosoft conversion artifact;
- the host processes `0x41` in the same generic read class as `0x01`;
- the host processes `0x43` in the same generic read class as `0x03`.

This masking does **not** prove that the controller aliases the full command
bytes. It does create a precise source-backed hardware discriminator.

The first pair is already locally resolved: `0x01 Virtual_READ` and
`0x41 KMBUS_RAM_READ` were byte-identical across seven same-address samples,
including dynamic non-zero pump values.

The bounded read-only gate has now been executed:

~~~text
positive control 0x00F8/2:
  0x01 = 20c2,20c2
  0x41 = 20c2,20c2
  -> payload STABLE_SAME

0x00F8/2:
  0x03 = 5491,5497
  0x43 = 5491,5491
  -> DYNAMIC_OR_INCONCLUSIVE

0x0001/1:
  0x03 = 81,81
  0x43 = 81,81
  -> payload STABLE_SAME
~~~

Every trial used a fresh P300 session.

Thus `0x43` has **not** demonstrated a distinct local data view from
`Physical_READ 0x03` at the sampled addresses. More importantly, the same
dynamic family previously attributed to strange 0x43 behavior is also visible
through ordinary `0x03`. This strongly shifts the working interpretation
toward a common/aliased legacy physical/service view on VDensHO1 rather than a
dedicated LGM27 EEPROM window.

Universal equivalence remains unproven. Neither result transfers GWG/LGM27
semantics to VDensHO1.

The first helper revision reported payload-identical groups as
`STABLE_DISTINCT` because the classifier included the expected echoed command
byte. Raw frames/data were unaffected. That reporting bug is fixed in v1.0.1;
v1.0.2 also preserves the schedule-manager service across the temporary P300
window.

Evidence:
[vitosoft/physical-vs-kmbus-eeprom-2026-09-25-evidence.json](vitosoft/physical-vs-kmbus-eeprom-2026-09-25-evidence.json).

The archived `vsmGWG99Native.dll` was also inspected. Its only exports are
`CheckGWG` and `TestCall_GWG99Native`; it imports the expected Windows
serial APIs and contains detector-style strings (`checking gwg...`,
`receive ENQ`, `WriteData OK`), but no exported general GWG/KMBUS datapoint
API. This supports treating the current Vitosoft GWG99 component as a
recognition/test helper rather than an alternate managed 0x43 serializer.

Private response analysis:
`collector-output/20260924-143439/kmbus-eeprom-response-analysis-2026-09-25.md`.

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
5. Why does the event catalog retain PrefixRead on non-RPC KBus/KMBUS rows
   even though the captured standard host serializer does not consume it?
6. What does the host-shaped prefix-less dynamic result of 0x43 actually
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
