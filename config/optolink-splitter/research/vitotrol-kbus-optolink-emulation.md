# Vitotrol emulation via Optolink / KBus / KM-BUS

Status: **open research**
Last updated: **2026-09-23**

This note covers the **Vitotrol-specific** application of the KBus/KM-BUS
research through the existing Optolink interface of the Vitodens 200-W WB2A
controller.

The canonical protocol-level research, verified function behavior, frame layout,
safety rules and general KBus/KM-BUS experiment plan are maintained in
[kmbus-optolink-research.md](kmbus-optolink-research.md).

## Production Vitosoft result — remote identity is a normal virtual object

The complete production Vitosoft join for the exact local `VDensHO1 / 20C2`
profile changes the Vitotrol-emulation hypothesis substantially.

For A1/M1:

~~~text
0x27A0
Virtual_READ
Virtual_WRITE
1 byte

0 = not present
1 = Vitotrol 200
2 = Vitotrol 300
~~~

For M2:

~~~text
0x37A0
Virtual_READ
Virtual_WRITE
1 byte

0 = not present
1 = Vitotrol 200
2 = Vitotrol 300
~~~

Therefore Vitosoft does **not** use a `KBUS_MEMBERLIST_WRITE` or
`KBUS_VIRTUAL_WRITE` event to configure the expected remote type on this
controller. It uses ordinary controller virtual objects.

Related discovery/state objects:

~~~text
A1 remote software-index block  0x0A5C / 4 bytes / read-only
M2 remote software-index block  0x0A60 / 4 bytes / read-only

A1 measured room temperature    0x0896 / 2 bytes / Div10 °C / read-only
M2 measured room temperature    0x0898 / 2 bytes / Div10 °C / read-only

A1 room-sensor status           0x089C / 1 byte / read-only
M2 room-sensor status           0x089D / 1 byte / read-only
~~~

The room-sensor status enum is:

~~~text
0 = OK
1 = short circuit
2 = interruption
3..5 = unknown
6 = not present
~~~

This creates a much more precise emulation problem:

1. remote **configuration/presence type** can be manipulated through a
   documented Virtual_WRITE object;
2. the actual measured room-temperature object is documented as read-only;
3. a physical Vitotrol likely causes lower-level bus logic to populate
   0x0896/0x0898 and associated status/software-index state;
4. an Optolink-only solution therefore needs either another internal injection
   path for that state or a way to make the controller consume a substitute
   writable input.

Do not write 0x27A0/0x37A0 yet. First record a complete read-only baseline.

Local read-only baseline:

- [vitosoft/vitotrol-baseline-2026-09-23.md](vitosoft/vitotrol-baseline-2026-09-23.md)

The baseline shows both circuits in the same absent-remote state
(`A0=0`, software-index block all zero, room sensor status 3/unknown, room
value 20.0 °C). The production Vitosoft resources also define
`BC = Fehler Fernbedienung HK1` and `BD = Fehler Fernbedienung HK2` for
VDensHO1, so a manual A0 write must be preceded by an error-history baseline
and an immediate rollback plan.

Detailed source extraction:

- [vitosoft/full-extraction-2026-09-23.md](vitosoft/full-extraction-2026-09-23.md)
- [vitosoft/vdensho1-vitotrol-events.csv](vitosoft/vdensho1-vitotrol-events.csv)


The central question is:

> Can the controller be made to believe that a Vitotrol is present, and can
> Vitotrol values such as room temperature be supplied, without adding a
> physical KM-BUS slave interface?

The answer is not known yet. The important change after the latest research is
that an Optolink-only solution must **not** be dismissed: Viessmann exposes a
substantial KBus/KM-BUS command family in the VS2/P300 protocol, and there is
historical and current evidence that at least part of it is real and used.

## Hardware result — A0 only arms remote expectation

A controlled local experiment wrote the Vitosoft-defined A1/M1 remote
identification from `0` to `1` (Vitotrol 200) and monitored the related state.

Result:

~~~text
0x27A0  00 -> 01
0x0A5C  remained 00000000
0x0896  remained c800 / 20.0 °C fallback
0x089C  remained 03 / unknown
0x5738  remained 00
system alarm -> BC
~~~

`BC` is locally source-confirmed as `Fehler Fernbedienung HK1`.

The script immediately restored `0x27A0 = 00`; the current alarm cleared while
the BC event remained in the fault history.

This disproves the simple hypothesis that setting A0 is sufficient to create a
software-only Vitotrol. A0 is a controller-side expected-device
configuration/detection state, not the remote's runtime data channel.

The next emulation research should focus on:

1. identifying what physical KM-BUS traffic clears the BC condition;
2. determining which runtime values a real Vitotrol causes the controller to
   populate (`0x0A5C`, `0x0896`, `0x089C`, and related state);
3. finding whether those runtime values are reachable through another
   controller-side interface;
4. otherwise returning to physical KM-BUS slave emulation.

## Local controller context

The current test system is documented elsewhere in this directory as:

- Vitodens 200-W WB2A
- controller family: **VDensHO1 / 20C2**
- current production access: Optolink-Splitter
- current research policy: read-only unless a write path is explicitly
  understood and has a recovery procedure

Relevant local documents:

- [kmbus-optolink-research.md](kmbus-optolink-research.md)
- [device-vdensho1-20c2-wb2a.md](device-vdensho1-20c2-wb2a.md)
- [coding-plug-7833971-2015-0201.md](coding-plug-7833971-2015-0201.md)
- [README.md](README.md)

## What has already been ruled out

A normal Optolink virtual write to the suspected room-temperature location did
not work.

The tested path was the normal virtual datapoint write path:

~~~text
Virtual_WRITE (normal Optolink datapoint write)
    -> 0x0896
    -> rejected by the controller
~~~

The observed write error rules out the simple idea that the room temperature
can be injected by treating 0x0896 as a normal writable controller datapoint.

This does **not** rule out any of the dedicated KBus/KM-BUS function codes.
Those use different function codes and therefore a different firmware path.

## VS2/P300 KBus and KM-BUS function-code family

The Viessmann/Vitosoft-derived function-code table contains the following
relevant functions.

| Hex | Decimal | Function |
| ---: | ---: | --- |
| 0x21 | 33 | Virtual_MBUS |
| 0x41 | 65 | KMBUS_RAM_READ |
| 0x43 | 67 | KMBUS_EEPROM_READ |
| 0x51 | 81 | KBUS_DATAELEMENT_READ |
| 0x52 | 82 | KBUS_DATAELEMENT_WRITE |
| 0x53 | 83 | KBUS_DATABLOCK_READ |
| 0x54 | 84 | KBUS_DATABLOCK_WRITE |
| 0x55 | 85 | KBUS_TRANSPARENT_READ |
| 0x56 | 86 | KBUS_TRANSPARENT_WRITE |
| 0x57 | 87 | KBUS_INITIALISATION_READ |
| 0x58 | 88 | KBUS_INITIALISATION_WRITE |
| 0x59 | 89 | KBUS_EEPROM_LT_READ |
| 0x5A | 90 | KBUS_EEPROM_LT_WRITE |
| 0x5B | 91 | KBUS_CONTROL_WRITE |
| 0x5D | 93 | KBUS_MEMBERLIST_READ |
| 0x5E | 94 | KBUS_MEMBERLIST_WRITE |
| 0x5F | 95 | KBUS_VIRTUAL_READ |
| 0x60 | 96 | KBUS_VIRTUAL_WRITE |
| 0x61 | 97 | KBUS_DIRECT_READ |
| 0x62 | 98 | KBUS_DIRECT_WRITE |
| 0x63 | 99 | KBUS_INDIRECT_READ |
| 0x64 | 100 | KBUS_INDIRECT_WRITE |
| 0x65 | 101 | KBUS_GATEWAY_READ |
| 0x66 | 102 | KBUS_GATEWAY_WRITE |

The current upstream Optolink-Splitter source also carries these names in its
function-code dictionary. They are currently commented as symbolic labels there,
but the generic request mechanism can send arbitrary function codes.

Source:

- https://github.com/philippoo66/optolink-splitter/blob/main/optolinkvs2_switch.py

The original Vitosoft reverse-engineering source for the function-code list is:

- https://github.com/sarnau/InsideViessmannVitosoft/blob/main/VitosoftCommunication.md

### Important interpretation

The existence of a symbolic function name by itself does not prove that the
WB2A implements that function.

However, there is additional evidence below showing that at least several of
these paths are not merely unused enum names.

## Strong evidence 1: 0x43 was used as a real KM-BUS access path

Old OpenV/vcontrold configurations explicitly define:

~~~text
GETKMADDR -> SEND 01 43
~~~

and expose a command described as:

~~~text
kmget
Testabfrage, KM-Bus EEProm Adresse eingeben
~~~

Therefore function code **0x43 / KMBUS_EEPROM_READ** was historically used as
an actual KM-BUS-related access method through the Viessmann communication
interface.

Sources:

- https://github.com/openv/vcontrold/blob/master/xml/300/vcontrold.xml
- https://github.com/openv/vcontrold/blob/master/xml/300/vito.xml

This is important because it demonstrates that Optolink-to-KM-BUS access is not
only a theoretical interpretation of names found in Vitosoft.

### Local WB2A validation — 2026-09-22

The generic VS2 request path was first verified against an ordinary
Virtual_READ:

~~~text
request;0x01;0x00F8;2;;0x00
-> 1;0xf8;20c2
~~~

The same address through the normal read path returned the identical controller
ID:

~~~text
r;0x00F8;2;raw;False
-> 1;0xf8;20c2
~~~

This proves that the local Optolink-Splitter generic request transport is
working correctly on this VDensHO1 / 20C2 controller.

A read-only KMBUS_EEPROM_READ probe was then issued:

~~~text
request;0x43;0x00F8;1;;0x00
-> 1;0xf8;54
~~~

This is a **hardware-verified successful response** from the local WB2A to
function code 0x43. The important result is the return code 1: the controller
accepted and executed this function path instead of returning an Optolink error,
NACK or timeout.

The returned byte 0x54 is deliberately **not interpreted yet**. In particular:

- it is not the same address space as ordinary Virtual_READ merely because the
  numeric address field is also 0x00F8;
- it does not by itself prove that a physical KM-BUS accessory is present;
- it does not prove that KBUS_MEMBERLIST, KBUS_VIRTUAL or gateway operations are
  supported;
- it does prove that at least one dedicated KMBUS function is live and readable
  through Optolink on this exact controller.

This substantially strengthens the case for continuing the Optolink-only
KBus/KM-BUS investigation.

### Extended local mapping — 2026-09-22

The complete normal controller identity was recorded as:

~~~text
Virtual_READ 0x00F8 / 8
-> 20 c2 00 03 00 00 01 03

Virtual_READ 0x00F0 / 1
-> error (retcode 3, data 01)
~~~

The same F8..FF addresses were then read one byte at a time with
`0x41 / KMBUS_RAM_READ`:

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

Thus, on this controller, the 0x41 address space exposes the same eight-byte
identity sequence at F8..FF as normal Virtual_READ.

This does **not yet prove** whether 0x41 is a mirror of controller identity,
an internal KM-BUS RAM image, or an aliasing behavior. A block read should be
used to confirm contiguous semantics before assigning a stronger meaning.

The same addresses through `0x43 / KMBUS_EEPROM_READ` returned a clearly
different pattern:

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

All eight requests returned retcode 1.

This confirms that 0x43 is not simply returning the ordinary controller
identity at those numeric addresses. The meaning of the bytes remains unknown;
the numeric address must be treated as belonging to the KMBUS_EEPROM_READ
address space.

Do not currently interpret this as a dump of the Kesselcodierstecker. The
coding plug is exposed elsewhere through structured objects (0x1010 and
0x1030..0x1090), and no evidence yet links those physical plug bytes to the
0x43 address space. The coding-plug-specific investigation is documented in
[coding-plug-7833971-2015-0201.md](coding-plug-7833971-2015-0201.md).

Important protocol-layer caution: do not confuse VS2/P300 function-code values
with the older GWG telegram TYPE values. In current GWG reverse-engineering,
TYPE 0x43 is likewise KMBUS_EEPROM_READ, but GWG KMBUS-RAM is described as
TYPE 0x33. That does **not** make VS2 function code 0x33 a KMBUS RAM read.
For the current VDensHO1/20C2 VS2 path, use the Vitosoft VS2 function-code table
and hardware-verified behavior separately.

### Block-read validation

Two contiguous 8-byte reads were then performed from 0x00F8.

KMBUS_RAM_READ:

~~~text
request;0x41;0x00F8;8;;0x00
-> 1;0xf8;20c2000300000103
~~~

This exactly matches both the earlier one-byte 0x41 reads and the ordinary
Virtual_READ controller identity. Therefore the 0x41 path supports a coherent
contiguous 8-byte read at F8..FF on this controller.

KMBUS_EEPROM_READ:

~~~text
request;0x43;0x00F8;8;;0x00
-> 1;0xf8;5497549754975497
~~~

This result is important because it does **not** match the prior sequence of
individual one-byte reads:

~~~text
individual reads:
F8 54
F9 97
FA 54
FB 98
FC 54
FD 98
FE 54
FF 98

single block read:
F8..FF 54 97 54 97 54 97 54 97
~~~

Consequences:

- 0x43 is definitely active and readable (retcode 1);
- the returned data must **not yet be treated as ordinary linear EEPROM
  contents**;
- at least the odd-position value appears capable of changing between separate
  transactions, or the function has access semantics different from a simple
  byte-addressed memory read;
- the block result is internally regular and looks like four repetitions of
  the two-byte word 0x5497;
- no semantic meaning is assigned to 0x5497 yet.

A useful next diagnostic is to repeat the exact same 0x43 F8/8 block read a few
times at controlled intervals and compare whole snapshots. If the second byte
changes while the repeated-word structure remains, this would strongly indicate
a dynamic register/mailbox-style source rather than static EEPROM bytes.

## Strong evidence 2: Vitosoft data contains KBUS_VIRTUAL events

The current esphome_vitohome project analyses a large Vitosoft XML export.
According to that analysis, Vitosoft datapoints exist with:

~~~text
FCRead  = KBUS_VIRTUAL_READ
FCWrite = KBUS_VIRTUAL_WRITE
~~~

For GWG-family events the analysis reports:

- 34 events using KBUS_VIRTUAL_READ
- 17 writable events using KBUS_VIRTUAL_WRITE

The project author explicitly describes KBUS_VIRTUAL_READ as a **genuine K-bus
tunnel** which cannot be represented by the ordinary GWG access modes.

Sources:

- https://github.com/SoulSolistice/esphome_vitohome/blob/main/scripts/gen_catalog.py
- https://github.com/SoulSolistice/esphome_vitohome/blob/main/components/vitohome/optolink/THIRD_PARTY.md
- https://github.com/SoulSolistice/esphome_vitohome/blob/main/tests/unit/test_gen_catalog_gwg_access.py

This is derived analysis rather than official Viessmann documentation, so the
exact packet semantics still need to be verified.

## Why Vitosoft XML is probably the key to the packet format

The Vitosoft event definitions contain more than only an address and a function
code. Relevant fields include, depending on event:

- FCRead
- FCWrite
- Address
- BlockLength / ByteLength
- PrefixRead
- PrefixWrite
- Parameter

For ordinary Optolink virtual reads the address and length are often sufficient.
For a bus tunnel this may not be true.

A likely interpretation is that target-member, slot, sub-address or bus command
information is stored in the additional prefix/parameter fields.

Therefore arbitrary experiments such as:

~~~text
request;0x5F;<guessed address>;<guessed length>
~~~

are not a good next step.

The next step is to extract real Vitosoft KBUS event definitions and reproduce
their exact parameters.

Vitosoft XML background:

- https://github.com/sarnau/InsideViessmannVitosoft/blob/main/VitosoftXML.md

## Optolink-Splitter can already transport generic function requests

Current upstream Optolink-Splitter has a generic request command in
requests_util.py:

~~~text
request;<function-code>;<address>;<length>;<data>;<protocol-id>
~~~

Aliases:

~~~text
request
req
~~~

The generic request is passed to the lower-level VS1/VS2 request implementation
rather than being forced through normal Virtual_READ or Virtual_WRITE.

Source:

- https://github.com/philippoo66/optolink-splitter/blob/main/requests_util.py

The local helper tools/optolink-debug.py is transport-transparent for its
request subcommand: it publishes the supplied command string to the Splitter
MQTT command topic. Consequently, once exact KBus parameters are known, no new
debug transport is required merely to send them.

This is a useful distinction:

~~~text
/usr/local/bin/optolink-debug request "r;..."
~~~

uses the normal read command if the argument begins with r, whereas a future
KBus probe can pass a complete generic command string beginning with request or
req.

Do not send KBus writes yet.

## Physical KM-BUS behavior relevant to Vitotrol emulation

OpenV reverse-engineering work on issue #387 documents practical Vitotrol
emulation attempts.

Important observations from that work:

1. The boiler/controller is the KM-BUS master.
2. Accessories such as a Vitotrol act as slaves.
3. Slave-to-master signaling uses current modulation.
4. A slave must respond to master discovery/ping traffic with tight timing.
5. Community experiments succeeded far enough that the controller recognized a
   software-emulated remote and continued with ping/status communication.
6. Later work also captured real Vitotrol traffic directly before the M-Bus
   interface, which is valuable because ordinary bus sniffing easily sees the
   master voltage telegrams but not the slave current-modulated response.

Main discussion and captures:

- https://github.com/openv/openv/issues/387

One documented discovery exchange for a Vitotrol-like device is approximately:

~~~text
master discovery:
11 00 33 0A 01 01 F8 04 49 EF

example attempted slave identity reply:
00 11 B3 10 01 01 F8 11 F9 34 FA 00 FB 05 06 64
~~~

These frames are examples from community experiments on other controller
families. They must not be assumed to be byte-for-byte correct for VDensHO1 /
20C2.

The timing evidence is important: replies delayed by roughly 30-40 ms were
reported as probably too slow. A real slave implementation needs immediate
response after the relevant master telegram.

## Gateway access and true slave emulation are different problems

A working KBus tunnel does not automatically mean that a Vitotrol can be
emulated.

### Case A: gateway/tunnel access

~~~text
Optolink client
    |
    v
Vitotronic firmware
    |
    v
KBus / KM-BUS gateway
    |
    v
real accessory
~~~

This means the controller provides an Optolink API for reading/writing something
on its internal/accessory bus.

### Case B: virtual Vitotrol

~~~text
Vitotronic KM-BUS master
    |
    | discovery / ping
    v
virtual Vitotrol state
    |
    | slave response / values
    v
Vitotronic
~~~

For an Optolink-only Vitotrol we need a firmware mechanism that either:

- injects a slave response into the controller's receive path;
- creates/manipulates an internal virtual KBus member;
- exposes a gateway/mailbox whose content the controller treats as a slave;
- or otherwise updates the same internal state that a real Vitotrol would
  populate.

A generic master-to-slave tunnel alone would not be enough.

## Most interesting function codes for an Optolink-only Vitotrol

The following codes currently deserve the highest priority.

### 0x5D / 0x5E — KBUS_MEMBERLIST_READ/WRITE

Hypothesis:

The controller may maintain an internal list of KBus members/accessories. If
this is true, the member list may contain device class, slot/heating-circuit
assignment, presence or identification state.

This is currently a **hypothesis based on the function name**. No packet layout
has been established.

A readable member list would be extremely valuable even if write access is
never used.

### 0x57 / 0x58 — KBUS_INITIALISATION_READ/WRITE

Hypothesis:

These functions may expose bus discovery/initialisation state.

Potential relevance:

- discovery state;
- accessory initialization records;
- address/slot setup;
- controller-side state machine involved in accepting a Vitotrol.

Again, semantics are unknown.

### 0x65 / 0x66 — KBUS_GATEWAY_READ/WRITE

Hypothesis:

This pair may provide a mailbox/gateway abstraction between Optolink/Vitosoft
and the KBus.

If it exposes raw or semi-raw bus messages, it could be the most direct route
to understanding whether slave-like data can be inserted.

### 0x55 / 0x56 — KBUS_TRANSPARENT_READ/WRITE

The name suggests a lower-level transparent tunnel. It may provide raw-ish bus
transport, but this must be proven from real Vitosoft event definitions or
captures.

### 0x5F / 0x60 — KBUS_VIRTUAL_READ/WRITE

These are strongly evidenced as real Vitosoft event access methods.

They are therefore the best-confirmed KBus-specific pair, but the word
"virtual" does not prove that they emulate a bus member. It may simply describe
an address space inside an existing accessory.

## Working architecture hypothesis

The current working hypothesis to investigate is:

~~~text
Optolink VS2/P300
    |
    +-- normal Virtual_READ/WRITE
    |
    +-- KMBUS_RAM/EEPROM
    |
    +-- KBUS_* API
            |
            +-- data element / block
            +-- transparent
            +-- initialisation
            +-- member list
            +-- virtual
            +-- direct / indirect
            +-- gateway
                    |
                    v
              controller KBus driver
                    |
                    v
                 KM-BUS
~~~

If Vitotrol presence and room data are mirrored in an internal member object,
there may be an Optolink-only emulation route.

If the KBUS API is strictly a master-side API that sends telegrams to real
external slaves, then a physical M-Bus/KM-BUS slave interface remains necessary.

## ViessData21 clue

The ViessData21 repository contains:

- KmProtokollTest.zip

At present this archive is known to contain a compiled
KmProtokollTest.exe, not source code. It is evidence that this protocol area was
actively investigated, but no semantics should be inferred from the executable
without further analysis.

Source:

- https://github.com/philippoo66/ViessData21/blob/master/KmProtokollTest.zip

ViessData21 also maps device identifiers and is useful for cross-checking
controller families:

- https://github.com/philippoo66/ViessData21/blob/master/DataPoints.txt

## Safety boundary

Do **not** blindly use any of these writes:

~~~text
0x58 KBUS_INITIALISATION_WRITE
0x5B KBUS_CONTROL_WRITE
0x5E KBUS_MEMBERLIST_WRITE
0x60 KBUS_VIRTUAL_WRITE
0x66 KBUS_GATEWAY_WRITE
~~~

Unknown consequences include:

- corrupt or inconsistent accessory/member state;
- communication faults such as Vitotrol/KM-BUS errors;
- persistent configuration changes;
- loss of communication with other KM-BUS accessories;
- writes to EEPROM-like storage rather than temporary RAM.

Before the first KBus write we need:

1. exact event semantics from Vitosoft or another trustworthy source;
2. read-back of the corresponding current state;
3. knowledge of whether the destination is RAM, EEPROM or bus traffic;
4. a rollback/recovery procedure;
5. preferably a test with a non-critical field before anything related to
   burner, safety or heating control.

## Next-session plan

### Phase 1 — anchor the exact local controller identity

The repository already identifies this unit as VDensHO1 / 20C2. Record the
complete identity bytes as additional evidence:

~~~bash
/usr/local/bin/optolink-debug request "r;0x00F8;8;raw;False"
/usr/local/bin/optolink-debug request "r;0x00F0;1;raw;False"
~~~

Store:

- F8/F9 device identification;
- FA hardware index;
- FB software index;
- FC/FD protocol versions;
- FE/FF developer versions;
- F0 protocol identifier if supported.

### Phase 2 — extract real Vitosoft KBUS events

Obtain/query the Vitosoft XML export and list all events relevant to the
VDensHO1/GWG family whose FCRead or FCWrite contains:

~~~text
KMBUS_
KBUS_
~~~

For each event record at least:

~~~text
event/token name
FCRead
FCWrite
Address
BlockLength
ByteLength
PrefixRead
PrefixWrite
Parameter
conversion/type
device/controller family
~~~

Priority functions:

~~~text
KBUS_MEMBERLIST_READ
KBUS_INITIALISATION_READ
KBUS_GATEWAY_READ
KBUS_TRANSPARENT_READ
KBUS_VIRTUAL_READ
KMBUS_RAM_READ
KMBUS_EEPROM_READ
~~~

### Phase 3 — reproduce only known read requests

Build generic Optolink-Splitter requests from real Vitosoft events.

Generic Splitter syntax:

~~~text
request;<function-code>;<address>;<length>;<data>;<protocol-id>
~~~

Do not guess address, length, prefix or payload. Use parameters from a known
Vitosoft event first.

Log for every probe:

- request parameters;
- complete raw response;
- return code;
- whether the response is stable;
- whether it changes when a KM-BUS accessory is connected/disconnected;
- whether any fault appears in the controller.

### Phase 4 — map member/gateway state

If readable data is returned, look for:

- accessory IDs;
- class/device identifiers;
- heating-circuit/slot identifiers;
- online/presence flags;
- discovery state;
- buffers that change during KM-BUS activity.

If a real Vitotrol can be temporarily connected later, capture before/after
states. That would provide the strongest mapping between internal KBus objects
and real accessory registration.

### Phase 5 — decide whether Optolink-only emulation is feasible

Evidence for feasibility would be one of:

- a writable temporary member structure that creates a recognized Vitotrol;
- a gateway/transparent mailbox that can inject the equivalent of a slave
  response;
- a KBUS_VIRTUAL object whose values map directly to a registered remote;
- a controller-internal Vitotrol data area that can be populated after
  registration is forced safely.

Evidence against the Optolink-only route would be:

- all KBUS functions are only master-side requests to already-existing physical
  slaves;
- member list is read-only/generated exclusively from electrical bus discovery;
- no API can feed the slave-to-master receive path;
- required response timing is handled only by the physical KM-BUS interface.

In that case continue the physical slave path using an M-Bus slave transceiver.

## Physical fallback path

The existing project roadmap already tracks a no-solder hardware route based on
the **MIKROE-4137 M-Bus Slave Click**.

That path remains valid and should be treated as the fallback/parallel route,
not discarded.

If Optolink-only emulation proves impossible, the physical architecture becomes:

~~~text
Home Assistant / host software
    |
    v
MCU / serial host
    |
    v
M-Bus slave transceiver
    |
    v
KM-BUS terminal
    |
    v
Vitotronic master
~~~

The physical route must implement the Vitotrol discovery, ping and response
timing itself.

## Current conclusion

Current confidence levels:

| Statement | Confidence |
| --- | --- |
| normal Virtual_WRITE to 0x0896 is not the solution | high / measured locally |
| KM-BUS-specific Optolink access exists | **hardware-verified on local 20C2 via 0x43** |
| 0x43 KMBUS_EEPROM_READ returns data on local WB2A | **high / measured locally: 0x54 at probe address 0x00F8** |
| Vitosoft contains KBUS_VIRTUAL_READ/WRITE events | high |
| current Splitter can send arbitrary VS2 function requests | high |
| KBUS_* can address useful KBus state on this exact 20C2 | open |
| MEMBERLIST/GATEWAY can create a virtual Vitotrol | hypothesis |
| full Vitotrol emulation can be done via Optolink only | open |

The Optolink-only route is therefore worth a structured read-only investigation
before adding physical KM-BUS hardware.


## WiFiVitotrol source reconstruction of the real KM-BUS runtime path

Public source code from `dumpfheimer/WiFiVitotrol` provides a working
software implementation of a Vitotrol-like KM-BUS slave. This materially
clarifies the hardware result above.

### Device identity

The implementation uses:

~~~text
DEVICE_CLASS = 0x11

Vitotrol 200:
  DEVICE_ID   = 0x34
  DEVICE_SN1  = 0x00
  DEVICE_SN2  = 0x05
  DEVICE_SLOT = 0x01

Vitotrol 300:
  DEVICE_ID   = 0x38
  DEVICE_SN1  = 0x00
  DEVICE_SN2  = 0x11
  DEVICE_SLOT = 0x02
~~~

The slave register map initializes:

~~~text
F8 = DEVICE_CLASS
F9 = DEVICE_ID
FA = DEVICE_SN1
FB = DEVICE_SN2
~~~

Therefore a master read of F8..FB for the default Vitotrol-200 setup produces
the identity bytes:

~~~text
F8 11 F9 34 FA 00 FB 05
~~~

The implementation answers the KM-BUS master command family:

~~~text
0x00  PING
0x31  request one byte
0x33  request N bytes
0x3F  command/unknown
0xB1  sending one byte
0xB3  sending N bytes
0xBF  sending command
0x80  pong
~~~

### Runtime room-temperature path

The software does **not** write the controller's Optolink object `0x0896`.

Instead it defines a runtime datapoint:

~~~text
CurrentRoomTemperature
type          DATA_10_INT
periodic send 30000 ms
~~~

When the KM-BUS master pings the slave and a room-temperature update is due,
the slave prepares a `0xBF / MSG_SENDING_COMMAND` response with command/data
payload:

~~~text
20 <temp-byte xor AA> <high-byte xor AA> <00 xor AA>
~~~

For temperatures <=25.5 °C the high byte is zero before XOR. Higher
temperatures use a two-byte representation according to the implementation.

The complete KM-BUS response wrapper is:

~~~text
00 11 BF 0C SLOT 01
20 <encoded temperature bytes...>
CRC16
~~~

where the source class is `0x11` and the default Vitotrol-200 slot is
`0x01`.

This is strong source evidence that the local controller values

~~~text
0x0896  measured room temperature
0x089C  room-sensor status
0x0A5C  remote software index
~~~

are downstream controller state populated by the internal KM-BUS master/slave
exchange rather than intended Optolink injection registers.

### Why A0=1 produced BC

The hardware experiment is now consistent with the working emulator source:

1. `0x27A0 = 1` tells VDensHO1 to expect a Vitotrol 200 for A1/M1;
2. the internal KM-BUS master expects a class-`0x11`, slot-`0x01` slave;
3. no such slave is currently responding;
4. no identity/software-index/runtime room-temperature state is populated;
5. VDensHO1 raises `BC = Fehler Fernbedienung HK1`.

Thus the BC fault is not evidence that A0 itself is wrong. It is evidence that
the expected KM-BUS slave transaction is missing.

### Revised Optolink-only question

The remaining Optolink-only possibility is now much narrower:

> Can one of the generic KBUS transparent/direct/gateway function codes inject
> or emulate the **slave-side KM-BUS response stream** that the controller's
> internal KM-BUS master expects?

This is distinct from merely setting controller virtual objects.

The relevant generic function names remain:

~~~text
0x55 KBUS_TRANSPARENT_READ
0x56 KBUS_TRANSPARENT_WRITE
0x61 KBUS_DIRECT_READ
0x62 KBUS_DIRECT_WRITE
0x65 KBUS_GATEWAY_READ
0x66 KBUS_GATEWAY_WRITE
~~~

No VDensHO1 Vitosoft event currently documents the required argument semantics
for using those functions as a slave-side injection mechanism. They must not be
blindly written on the live boiler.

The physical KM-BUS slave-emulation path is now source-supported and should be
kept as the reliable fallback/reference implementation.
