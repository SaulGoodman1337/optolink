# KM-BUS / KBus read-memory analysis - 2026-09-24

Status: **active, read-only research**

This note deepens the controller-side KM-BUS/KBus read-function work for the local
Vitodens 200-W **WB2A / VDensHO1 / 20C2**. It complements the canonical
[KBus / KM-BUS research via Optolink](../kmbus-optolink-research.md).

The main question is no longer merely whether the extended function codes
exist. Two of them are already accepted by the local controller. The useful
question is now **which memory or participant view each read function exposes,
which selector/prefix bytes Vitosoft supplies, and whether those views can
reveal controller state that ordinary Virtual_READ does not expose**.

No write function is part of this workstream.

## Executive result

The read families are worth pursuing. In particular:

1. **0x41 KMBUS_RAM_READ is already locally verified** and can return a stable,
   coherent block. At `0x00F8/8` it returns exactly the normal eight-byte
   controller identity `20 c2 00 03 00 00 01 03`.
2. That result makes 0x41 potentially very valuable for state discovery, but it
   does **not** prove that 0x41 is raw CPU RAM. It may be a mirrored controller
   structure, a KM-BUS participant RAM view, an alias of the virtual data store,
   or another internal memory window.
3. **0x43 KMBUS_EEPROM_READ is also locally accepted**, but the prefix-less
   `0x00F8` experiment is not a linear EEPROM read. It returns a changing
   two-byte transaction result repeated/truncated to the requested length.
4. **90 of 91 KMBUS_EEPROM_READ definitions carry
   `PrefixRead=030000000101`**, but host-implementation recovery now shows
   that the captured Vitosoft standard non-RPC VS2 read path does **not**
   serialize `PrefixRead`. Only the `Remote_Procedure_Call / 0x07` path
   converts PrefixRead hex into request data. For `0x43`, the normal host
   frame is therefore prefix-less.
5. The verified v6 All-Devices export contains a large amount of KBus read
   metadata even though the exact VDensHO1 profile uses none of those functions
   in its event tree. This is useful cross-profile protocol evidence.
6. **KMBUS_RAM_READ is the interesting exception:** the function exists in the
   protocol enum and works on the local controller, but the v6 event inventory
   contains **zero event definitions using it**. It appears to be a lower-level
   capability that Vitosoft's datapoint catalog does not normally expose.
7. RAM-like reads are much more likely to help us recover hidden runtime state
   and state-machine variables than to return executable firmware directly.
   Firmware extraction remains a separate MCU/flash problem unless a dedicated
   flash/window/bank mechanism is found.

## What "RAM read" can realistically buy us

A RAM or RAM-like memory view can be extremely useful even if it never contains
the executable program.

Potential targets include:

- intermediate pump arbitration state upstream of `0x0A3C`;
- the distinction between A1 request `0x7663` and final internal-pump command
  `0x7660`;
- timers, mode flags and state-machine steps;
- KM-BUS participant descriptors and presence state;
- copies of current sensor/command values before or after conversion;
- communication mailboxes;
- buffers for KM-BUS frames;
- tables or pointers that lead to otherwise undocumented objects;
- firmware/software identity structures.

The most informative experiment is therefore **correlation**, not a blind
memory dump: read a small set of already understood dynamic objects through
ordinary Virtual_READ and through the candidate memory function in the same
time window. If multiple values line up, we learn how the memory view is mapped.
If they do not, that is also useful because it demonstrates that the function
reaches a distinct address space.

## Important distinction: P300 functions vs. old GWG access modes

Several names occur in both old GWG documentation and the VS2/P300 function
vocabulary. The packet formats are not interchangeable.

For the local WB2A we are using VS2/P300:

| VS2 code | Name |
| ---: | --- |
| `0x21` | Virtual_MBUS |
| `0x31` | XRAM_READ |
| `0x41` | KMBUS_RAM_READ |
| `0x43` | KMBUS_EEPROM_READ |
| `0x51` | KBUS_DATAELEMENT_READ |
| `0x53` | KBUS_DATABLOCK_READ |
| `0x55` | KBUS_TRANSPARENT_READ |
| `0x57` | KBUS_INITIALISATION_READ |
| `0x59` | KBUS_EEPROM_LT_READ |
| `0x5D` | KBUS_MEMBERLIST_READ |
| `0x5F` | KBUS_VIRTUAL_READ |
| `0x61` | KBUS_DIRECT_READ |
| `0x63` | KBUS_INDIRECT_READ |
| `0x65` | KBUS_GATEWAY_READ |

Old GWG has its own TYPE-byte access modes. For example, public GWG research
maps `XRAM_READ` to TYPE `0xC5`, KMBUS EEPROM to TYPE `0x43` and KMBUS RAM
to TYPE `0x33`. Those values describe a different wire protocol. The identical
`0x43` value is not sufficient to equate the request semantics.

## What the verified Vitosoft v6 export says

Preferred private source snapshot:

- snapshot: `vitosoft-private-archive-20260924-143439`
- SHA256: `3d31380d6dfabf8ede9e305b115e847fb0670511e253a4ed4e59feef2f7adfee`
- 399 datapoint profiles
- 11,582 events
- 104,339 device-event links
- 5,356 unique low-level addresses
- 38 protocol-function names
- 1,797 globally selected KBus/KM-BUS events in the deep metadata report

The global protocol-function inventory contains:

| Read function | Definitions |
| --- | ---: |
| `KMBUS_RAM_READ` | **0** |
| `KMBUS_EEPROM_READ` | **91** |
| `XRAM_READ` | **12** |
| `Virtual_MBUS` | **254** |
| `KBUS_DATAELEMENT_READ` | **7** |
| `KBUS_DATABLOCK_READ` | **0 in inventory** |
| `KBUS_TRANSPARENT_READ` | **850** |
| `KBUS_INITIALISATION_READ` | **0 in inventory** |
| `KBUS_EEPROM_LT_READ` | **500** |
| `KBUS_MEMBERLIST_READ` | **1** |
| `KBUS_VIRTUAL_READ` | **232** |
| `KBUS_DIRECT_READ` | **11** |
| `KBUS_INDIRECT_READ` | **97** |
| `KBUS_GATEWAY_READ` | **0 in inventory** |

"0 in inventory" means that the function name exists in the protocol enum but
no event row in this Vitosoft definition set uses it. It does **not** mean the
controller firmware cannot implement the function. Local 0x41 is the direct
counterexample: Vitosoft has no KMBUS_RAM_READ event definitions, yet the local
20C2 accepts 0x41 and returns valid data.

### Exact VDensHO1 profile

For the exact local profile the complete 581-event join contains:

```text
Virtual_READ           462
GFA_READ                94
Remote_Procedure_Call   22
blank                     2
undefined                 1
KBUS_* / KMBUS_*          0
```

Therefore Vitosoft does not present these extended KBus functions as normal
WB2A service datapoints. That is a metadata/applicability result, not a firmware
capability boundary.

### Profile linkage already derived

The public small evidence extract records:

- `KMBUS_EEPROM_READ`: 91 definitions, linked to 40 profiles, not VDensHO1;
- `XRAM_READ`: 12 definitions, linked to 20 profiles, not VDensHO1;
- EEPROM/XRAM use is concentrated in GWG-family definitions;
- KMBUS EEPROM also occurs in DEKATEL/VCOM-related families.

This cross-profile material is valuable because it carries the argument shapes
that the low-level functions expect.

## The export contains more than function names

The v6 All-Devices extractor preserves, for every event:

- event ID and translated name/description;
- device/profile membership;
- address;
- `FCRead` / `FCWrite`;
- `Parameter`;
- `PrefixRead` / `PrefixWrite`;
- block length;
- byte position and byte length;
- bit position and bit length;
- data type / SDK data type;
- conversion, factor and offset;
- access mode;
- value and option lists;
- mapping type.

A targeted extractor has now been run against the verified v6 release asset.
The derived slice contains **2,055 read-event rows** and is committed in the
private source repository under:

```text
collector-output/20260924-143439/kmbus-read-slice/
  kmbus-read-events.csv
  kmbus-read-summary.json
  kmbus-read-summary.md
```

The extraction is reproducible through
`collector/tools/extract-kmbus-read-slice.py` and the dedicated GitHub Actions
workflow `.github/workflows/kmbus-read-slice.yml`. No new Vitosoft collection
was required.

### Exact prefix and profile structure from the targeted slice

| Function | Events | Prefix shape | Main semantic clue |
| --- | ---: | --- | --- |
| `KMBUS_RAM_READ` | 0 | none in metadata | low-level function exists and works locally despite zero catalog rows |
| `KMBUS_EEPROM_READ` | 91 | 90x 6-byte `030000000101`, 1x empty | persistent parameters / identity in subordinate legacy control units |
| `XRAM_READ` | 12 | empty | volatile runtime objects: external demand/lockout, timers, water pressure |
| `Virtual_MBUS` | 254 | mostly 2 bytes; some 3/4 bytes | actual external M-Bus meter integrations, not Viessmann KM-BUS |
| `KBUS_DATAELEMENT_READ` | 7 | empty | compact legacy data-element access |
| `KBUS_TRANSPARENT_READ` | 850 | **2 bytes on all 850** | strongly structured participant/channel selector space |
| `KBUS_EEPROM_LT_READ` | 500 | empty | legacy KBus EEPROM/logical-table address space |
| `KBUS_MEMBERLIST_READ` | 1 | empty | legacy participant-list operation |
| `KBUS_VIRTUAL_READ` | 232 | 227x 2 bytes, 5x empty | participant virtual-data tunnel |
| `KBUS_DIRECT_READ` | 11 | 10x empty, 1x 1 byte | direct legacy channel access |
| `KBUS_INDIRECT_READ` | 97 | 96x 1 byte, 1x empty | prefix is explicitly the participant number in the Vitosoft event names |

The prefix distributions remain useful **catalog metadata**, but host static
analysis changes their wire interpretation materially.

The recovered Vitosoft-v6 core consumes `PrefixRead` as request bytes only on
the `Remote_Procedure_Call / 0x07` conversion path. Ordinary non-RPC reads,
including `KMBUS_EEPROM_READ / 0x43`, do not copy PrefixRead into
`BlockDataToDevice`.

This also resolves the profile provenance of the 0x43 rows:

- all **90** rows carrying `PrefixRead=030000000101` are linked only to
  **21 GWG profiles**;
- their LGM27 names therefore describe the legacy GWG-family access model, not
  the local VDensHO1;
- the sole no-prefix KMBUS EEPROM event is event 2190 at `0x0310/4`,
  `Geräteidentifikation Schalterblock`, in 19 DEKATEL/VCOM profiles;
- no KMBUS_EEPROM_READ event is linked to VDensHO1.

Independent GWG implementations and vcontrold map KMBUS EEPROM access to the
old GWG TYPE byte `0x43`, using a one-byte address frame of the form
`01 43 <addr> <len> 04`. That is a different wire protocol from P300/VS2.
The shared numeric byte must not be used to transfer the GWG LGM27 semantics
onto a local P300 `0x43` response.

The 1-byte PrefixRead values on `KBUS_INDIRECT_READ` still clearly encode
participant numbers at the **metadata** level. What is no longer justified is
the generic assumption that every catalog PrefixRead is serialized as trailing
VS2 request data by this host build.

### XRAM_READ really is used for volatile runtime state

All 12 XRAM definitions belong to GWG-family profiles. They include:

| Address | Meaning |
| --- | --- |
| `0x0000` | external operating-mode change/request |
| `0x0000` | external blocking |
| `0x003A` | run-on timer + raw value |
| `0x003D` | 1-minute timer + raw value |
| `0x0040` | 7-minute timer + raw value |
| `0x0042` | 13-minute timer + raw value |
| `0x0088` | water pressure + raw value |

This is important conceptually: Vitosoft really does use a dedicated RAM-like
access space for **live transient state and timers** on some controller
families. That strongly supports pursuing analogous read-only memory views for
hidden WB2A runtime logic, while still not proving that local function 0x41 is
literal CPU RAM.

### Virtual_MBUS is a separate M-Bus workstream

The 254 `Virtual_MBUS` rows are overwhelmingly linked to real meter profiles
such as Calec, Engelmann/Senso, Techem, Viterra, ABB, Siemens and Kamstrup.
Therefore `Virtual_MBUS` should be treated as **external metering M-Bus**, not
as another spelling of Viessmann KM-BUS. It is not currently a promising route
to the WB2A regulation firmware.

### Transparent / virtual / indirect KBus reads expose a structured gateway model

The targeted slice shows:

- all **850** `KBUS_TRANSPARENT_READ` rows have exactly a **2-byte prefix**;
- **227/232** `KBUS_VIRTUAL_READ` rows have a **2-byte prefix**;
- **96/97** `KBUS_INDIRECT_READ` rows have a **1-byte prefix**, with event
  names proving that byte to be the participant number;
- the indirect address grid advances in regular 8-byte steps for participant
  datapoint slots.

The combined evidence supports a model in which the main regulation/gateway
routes requests using explicit target/channel selectors. It does **not** yet
show that `KBUS_TRANSPARENT_READ` transports arbitrary raw physical frames.

## 0x41 KMBUS_RAM_READ: local evidence and interpretation

Verified local request:

```text
request;0x41;0x00F8;8;;0x00
-> 1;0xf8;20c2000300000103
```

Equivalent normal virtual value:

```text
Virtual_READ 0x00F8/8
-> 20c2000300000103
```

Single-byte 0x41 reads from F8 through FF also reproduce the same eight bytes.

### What this proves

- function 0x41 is implemented by the local controller;
- at least the F8 window supports stable contiguous reading;
- its data can alias an ordinary virtual controller structure.

### What it does not prove

It does not prove:

- raw M16C CPU RAM;
- physical KM-BUS wire bytes;
- RAM of the internal pump;
- a specific participant;
- an unrestricted 64-KiB memory window.

The identity alias gives us a useful discriminator. If 0x41 also reproduces
several known volatile Virtual_READ objects, it is probably a broad
controller-side mirror/alternate access mode. If it diverges at those objects,
then F8 may be a special/common structure and other regions may expose a more
specific KM-BUS memory domain.

### Conditional M16C memory-map discriminator

If the **local** board later confirms the same M30624FGP/M16C/62P family as the
online comparison board, Renesas' documented 256-KiB memory map becomes a
strong discriminator:

```text
0x00000..0x003FF  SFR / peripheral registers
0x00400..0x053FF  20-KiB internal RAM
0x0F000..0x0FFFF  4-KiB data flash
0xC0000..0xFFFFF  256-KiB program flash
```

The already verified `0x41 / 0x00F8` result lies in what would be the M16C
**SFR region**, not its internal RAM, yet it returns the Viessmann controller
identity. Therefore, **if the local CPU is really this M16C variant, a simple
1:1 interpretation of the 0x41 address as raw CPU RAM is very unlikely**.
`KMBUS_RAM_READ` would then be better understood as a logical
controller/KM-BUS RAM address space, mirror or gateway view.

Primary memory-map source: Renesas M16C/62P Group datasheet, section 3
(Memory).

## 0x43 KMBUS_EEPROM_READ: response path and current interpretation

The local controller accepts the P300/VS2 command byte `0x43`, but its
prefix-less behavior is not a normal linear EEPROM read.

Examples from local hardware include changing two-byte words that are
repeated/truncated to the requested length:

~~~text
54 98 54 98 ...
54 97 54 97 ...
d3 01 d3 01 ...
f2 01 f2 01 ...
~~~

The recovered Vitosoft response converter proves that these patterns are **not
created by host-side conversion**. `convertLDAPDataFromDevice()` strips the
five-byte LDAP header, copies the remaining response bytes directly into
`BlockDataFromDevice` / `DataFromDevice`, and then applies only the normal
event conversion metadata.

A second useful source clue is the LDAP command-byte handling:

~~~text
0x41 & 0x1F = 0x01
0x43 & 0x1F = 0x03
~~~

Vitosoft places `0x41` responses in the same generic read-conversion class as
`0x01`, and `0x43` responses in the same class as `0x03`. This does not
prove that the controller itself aliases those command bytes, because the
controller may interpret the full byte. It does provide a precise local
discriminator.

The `0x01 vs 0x41` pair is already locally closed: seven same-address
comparisons, including non-zero dynamic pump objects, were byte-identical.

The next justified read-only test is therefore a very small
`0x03 Physical_READ vs 0x43` same-address comparison. Matching values would
support an alias/common-view hypothesis; different values or different error
behavior would prove that 0x43 reaches a distinct local service/view.

Do **not** call the local P300 0x43 payload LGM27 EEPROM data. The LGM27 catalog
rows belong to legacy GWG profiles, and the local VDensHO1 profile contains no
KMBUS_EEPROM_READ event.

## Why this probably will not directly dump M16C program flash

If the comparison-board M30624FGPFP hypothesis eventually also proves true for
the local WB2A, the MCU has a **20-bit / 1-MiB address space**. The 256-KiB
program area occupies `0xC0000..0xFFFFF`, while its 20-KiB internal RAM is
within the low address region.

A standard VS2 request exposes only a **16-bit address field** plus optional
prefix/data bytes. Therefore a simple prefix-less 0x41 sweep cannot map
one-to-one onto the M16C program-flash range. Direct firmware access through
Optolink would require one of:

- an explicit bank/high-address selector;
- a prefix that extends the address;
- a gateway/RPC abstraction;
- a controller-side copy/read service.

None of those has yet been demonstrated for the local WB2A.

This does **not** reduce the value of RAM analysis. Runtime state can reveal the
algorithm and data structures we currently cannot see in Vitosoft, and can
later provide anchors for a firmware disassembly if an MCU dump becomes
possible.

## Read-family research value

### 1. 0x41 KMBUS_RAM_READ - highest immediate value

Reason: already locally accepted and stable.

Next objective: establish whether it is an alias/mirror or a distinct memory
space by correlating a small set of known dynamic objects.

Good discriminators include:

- `0x0A3C` final internal-pump command shadow;
- `0x7660` internal physical-pump runtime command;
- `0x7663` A1 heating-circuit runtime request;
- `0x5730` internal pump identification;
- `0x0A54` internal-pump identity/software block;
- `0x27A0` A1/M1 remote-identification object.

These addresses are candidates for a **bounded comparison**, not permission for
a blind sweep.

### 2. 0x43 KMBUS_EEPROM_READ - implemented locally, semantics still unresolved

Potentially useful for:

- KM-BUS participant identity/configuration;
- persistent participant parameters;
- correlating physical accessories with software views.

Do not equate it with the boiler coding-plug EEPROM. No such link is proven.

## Historical manual prefixed 0x43 experiment - superseded

A manual KMBUS EEPROM frame was built by placing the catalog PrefixRead bytes
after the standard read length and tested locally:

~~~text
event 578
KMBUS_EEPROM_READ / 0x43
address 0x0001
block length 1
PrefixRead 030000000101
~~~

Wire result:

~~~text
TX 41 0B 00 43 00 01 01 03 00 00 00 01 01 55
RX 06
RX 41 06
RX 01 43 00 01 01 88 D4
~~~

So the local 20C2 accepted that frame and returned raw data `88`.
This **does not** prove that the six bytes are the Vitosoft PrefixRead wire
encoding. The later fresh-session discriminator found no isolated prefix effect,
and the recovered Vitosoft host implementation now proves that ordinary
non-RPC `0x43` reads do not serialize PrefixRead at all.

Do not interpret `88` as the GWG_BT2/LGM27 `Kennung (Prog1)`. The manually
appended request form is retained only as historical hardware evidence.

The v6 slice contains a bounded family of additional exact 0x43 block shapes
using the same prefix, including `0x000A/5`, `0x000F/8`, `0x0064/2`,
`0x006A/6`, `0x0070/7`, `0x0078/5|8`, `0x0083/4`, `0x0091/1`,
and the fault-history blocks `0x00A0/10`, `0x00AA/10`, `0x00B4/10`.
Those are the justified next read-only targets; do not infer a contiguous
EEPROM map beyond them.

## 0x43 source-map follow-up: success does not equal EEPROM semantics

The bounded follow-up tested all 13 exact GWG_BT2 address/length shapes using
the six-byte source PrefixRead. Every request returned a normal 0x43 response,
but most higher-address blocks collapse to the same repeated two-byte pattern:

~~~text
0x0078/5  = 54 98 54 98 54
0x0078/8  = 54 98 54 98 54 98 54 98

0x00A0/10 = 54 98 54 98 54 98 54 98 54 98
0x00AA/10 = 54 98 54 98 54 98 54 98 54 98
0x00B4/10 = 54 98 54 98 54 98 54 98 54 98
~~~

This is structurally the same phenomenon as the earlier prefix-less F8 test.
It makes a literal EEPROM interpretation implausible for those returned blocks.

Three low blocks remain structurally different:

~~~text
0x0001/1 = 88        (3 immediate repeats stable)
0x000A/5 = 40 00 00 00 00
0x000F/8 = 1F 00 00 00 00 00 00 00
~~~

The critical next protocol question is therefore not "what do the bytes mean?"
but first: **does PrefixRead change the transaction at all on the local 20C2?**

The acceptance of a frame containing six extra bytes is not enough to prove
that those bytes are consumed as a selector. A same-address P-N-P comparison is
required. The prepared helper compares prefixed -> no-prefix -> prefixed at
0x0001, 0x000A, 0x0078 and 0x00A0.

## Local PrefixRead discriminator result

The same-address P-N-P experiment materially narrows the 0x43 interpretation.

At `0x0001/1`:

~~~text
prefixed   -> 88
no-prefix  -> 87
prefixed   -> 88
~~~

This is direct local evidence that the six extra source bytes can alter an
0x43 result; they are not always ignored by the controller.

At `0x000A/5`, however, the result was unchanged
(`4000000000` for P/N/P). At the repeated-word addresses
`0x0078/8` and `0x00A0/10`, the two prefixed controls themselves changed
within the same short run, so those blocks remain transaction/state-dependent
and cannot isolate PrefixRead semantics.

The strongest current statement is therefore:

> `PrefixRead=030000000101` has a reproducible candidate effect at
> `0x0001/1`, but the exact semantics as routing, target selection or another
> request parameter are not yet proven.

The next experiment must reset P300 between every `0x0001/1` sample and use
a balanced deterministic P/N order.

## Fresh-session correction: PrefixRead effect not reproduced

The stronger isolated-session experiment tested only `0x0001/1`, opening a
new P300 session before every request. Balanced order:

~~~text
P N N P N P P N
~~~

Observed:

~~~text
P: 81, 81, 81, 87
N: 87, 81, 81, 81
~~~

The distributions are exactly identical. Therefore the prior same-session
`88 -> 87 -> 88` sequence was a confounded dynamic/session-state observation,
not a reproducible PrefixRead effect.

This changes the protocol conclusion materially:

- do **not** claim that `PrefixRead=030000000101` is locally proven routing;
- do **not** treat `0x0001` as a static EEPROM identity byte;
- do **not** expand the address map while the vendor field serialization is
  unresolved.

Host-implementation recovery is now complete for the captured Vitosoft build.

Static CIL analysis of `vsmInterfaceCore.dll` establishes the complete standard
read chain:

~~~text
EventType.FCRead
  -> MRKey.FunctionCode
  -> LDAPMessage.FunctionCode

EventType.Address
  -> LDAPMessage address

EventType.BlockLength
  -> LDAPMessage DataLength

EventType.BlockDataToDevice
  -> LDAPMessage Data
~~~

`LDAPMessage.toByteArray()` serializes:

~~~text
00 FCT ADDR_H ADDR_L DATA_LENGTH [DATA...]
~~~

and the serial DAP wrapper produces:

~~~text
41 LEN 00 FCT ADDR_H ADDR_L DATA_LENGTH [DATA...] CRC
~~~

For `0x43 / 0x0001 / len 1`, the captured host therefore generates:

~~~text
41 05 00 43 00 01 01 4A
~~~

with **no PrefixRead bytes**.

The reason is explicit in the code:

- `RPCConverter.IsFCReadRpc()` is true only for `FCRead == 0x07`;
- on that RPC path, `ConvertRpcToDevice_Default()` converts PrefixRead hex
  with `Util.getBytes()`, stores the bytes in `BlockDataToDevice`, and
  changes `BlockLength` to the prefix byte count;
- ordinary non-RPC reads such as `KMBUS_EEPROM_READ = 0x43` do not execute
  that conversion;
- exhaustive field/call-site analysis found no direct hidden read serializer
  for the PrefixRead backing field;
- a scan of the extracted ServiceTool managed assemblies found no external
  preprocessing path that maps PrefixRead into `BlockDataToDevice`;
- the VS1 converter does not support function `0x43` at all.

Thus the no-prefix form used in the fresh-session control is the actual standard
Vitosoft host shape for `0x43`. The six-byte `030000000101` catalog value
must not be manually appended to ordinary 0x43 frames.

Private derived report:
`collector-output/20260924-143439/prefixread-serializer-analysis-2026-09-25.md`
(commit `1bd156be85d947a3af890db426ce4462d71b4099`).

The open question is no longer PrefixRead placement. It is the semantics of the
controller's dynamic `0x43` response itself. Further prefix discrimination is
closed; no broad 0x43 address expansion is justified.

### 3. 0x31 XRAM_READ - high conceptual value, local applicability unknown

The 12 definitions are now fully enumerated. They expose volatile objects such
as run-on/1-minute/7-minute/13-minute timers, external demand/blocking and water
pressure in GWG-family devices. This strongly confirms the usefulness of
RAM-like spaces for hidden runtime state.

They are **not linked to VDensHO1**, so do not send 0x31 blindly on the WB2A.
Use the source semantics as architectural evidence and prioritize the already
verified local 0x41 path first.

### 3a. Local XRAM_READ 0x31 result - source-derived GWG shapes rejected

A guarded P300 run tested **all six unique address/length request shapes** from
the 12 Vitosoft-v6 XRAM definitions:

~~~text
0x0000 / 1
0x003A / 2
0x003D / 2
0x0040 / 2
0x0042 / 2
0x0088 / 2
~~~

The normal P300 identity control passed first:

~~~text
0x01 / 0x00F8 / 8 -> 20c2000300000103
~~~

Every 0x31 request then returned a valid VS2 **Error Message** rather than data.
The response command remained `0x31`, and the one-byte inner error payload was
consistently `05`.

Examples:

~~~text
TX 41 05 00 31 00 3a 02 72
RX 03 31 00 3a 01 05 7a

TX 41 05 00 31 00 88 02 c0
RX 03 31 00 88 01 05 c8
~~~

The matching Virtual_READ 0x01 controls at these cross-profile addresses also
returned Error Messages, but consistently with inner payload `01`.

Important boundaries:

- all 12 source XRAM events are GWG-family definitions, not VDensHO1;
- all 12 use **empty PrefixRead**, so the local 0x31 rejection is not explained
  by a missing source-defined prefix;
- no source-backed mapping for the inner error payload values `01` or `05`
  has been recovered, so do not assign semantic names to them;
- the result proves that the six known Vitosoft XRAM request shapes are not
  directly usable on local VDensHO1/20C2;
- it does **not** mathematically prove that every possible 0x31 address is
  unsupported, but there is now no source-derived local success target.

Decision: deprioritize blind XRAM probing and move to the next source-shaped
read path, prefixed `0x43 KMBUS_EEPROM_READ`.

Evidence:
[xram-read-live-2026-09-24-evidence.json](xram-read-live-2026-09-24-evidence.json).

### 4. 0x55 KBUS_TRANSPARENT_READ - very high protocol value

There are **850 definitions**, by far the richest KBus read family in the
current export. This likely offers the best dataset for reconstructing:

- target/participant selector structure;
- prefix length and byte roles;
- datapoint/channel addressing;
- return length conventions.

"Transparent" must not be interpreted as arbitrary raw KM-BUS frames until the
prefix and event semantics demonstrate that.

### 5. 0x59 KBUS_EEPROM_LT_READ - high value

There are **500 definitions**. Grouping them by device family, prefix and
address should reveal how legacy KBus participant EEPROM is addressed.

### 6. 0x5F KBUS_VIRTUAL_READ - useful tunnel candidate

There are **232 definitions**. Public independent analysis of the same Vitosoft
data treats these as a genuine KBus tunnel rather than a normal GWG access
mode. They are not linked to VDensHO1, but their parameter patterns can teach us
how KBus participant virtual data is selected.

### 7. Direct / indirect / data-element reads

- `KBUS_DIRECT_READ`: 11 definitions
- `KBUS_INDIRECT_READ`: 97 definitions
- `KBUS_DATAELEMENT_READ`: 7 definitions

The small, structured sets are valuable for understanding the difference
between direct channel access, indexed access and data-element access.

## Completed targeted extraction from the v6 archive

The derived, non-proprietary slice now contains the following functions:

```text
KMBUS_EEPROM_READ
XRAM_READ
Virtual_MBUS
KBUS_DATAELEMENT_READ
KBUS_DATABLOCK_READ
KBUS_TRANSPARENT_READ
KBUS_INITIALISATION_READ
KBUS_EEPROM_LT_READ
KBUS_MEMBERLIST_READ
KBUS_VIRTUAL_READ
KBUS_DIRECT_READ
KBUS_INDIRECT_READ
KBUS_GATEWAY_READ
```

For every row preserve:

```text
event_id
name_de / name_en
device/profile
address
fc_read
parameter
prefix_read
block_length
byte_length
conversion
access_mode
description
```

Completed aggregates include:

1. unique `PrefixRead` values and counts per function;
2. prefix-length distribution;
3. device/profile distribution;
4. address inventories;
5. the complete 12-row XRAM set;
6. the single exceptional no-prefix KMBUS EEPROM row.

Further semantic clustering of the 850 transparent, 500 EEPROM_LT and 232
virtual rows remains useful, but the first extraction gate is complete. No new
full Collector run is needed.

## Proposed local read-only sequence after the source slice is complete

Do not begin with a 64-KiB scan.

### Phase A - 0x41 mapping

For a handful of already-known safe addresses:

1. read with ordinary Virtual_READ;
2. immediately read same address/length with 0x41;
3. repeat while the relevant state changes naturally;
4. classify each address as identical, stable-different, dynamic-different,
   invalid or error.

This builds a memory-view correlation matrix.

### Phase B - source-defined 0x43 event

Choose one Vitosoft `KMBUS_EEPROM_READ` event whose semantic role and profile
make the request shape clear. Reconstruct its exact address, length and prefix.
Only then assess whether an equivalent read is appropriate on the local WB2A.

### Phase C - other read families

Test only functions for which the v6 slice supplies a concrete request shape.
Start with identity/version/configuration semantics rather than actuator or
burner-safety data.

## Stop conditions

- no write functions;
- no address-space sweep while target semantics are unknown;
- no interpretation based only on a successful return code;
- no assumption that `RAM` means main-MCU RAM;
- no assumption that `EEPROM` means the Kesselcodierstecker;
- no cross-profile write experiment;
- stop if a read changes controller state, causes a fault, disrupts Optolink or
  changes KM-BUS participant state.

## Relation to the PCB / M16C research

The protocol and PCB workstreams should converge later:

```text
Optolink read-function map
        |
        +--> 0x41 / RAM-like view
        +--> 0x43 / EEPROM-like participant view
        +--> KBUS transparent/virtual/direct/indirect
        |
        v
software-visible structures
        |
        +------------------------------+
                                       |
local PCB photos                      |
        |                              |
        v                              v
MCU + KM-BUS transceiver ------> correlate memory/bus architecture
```

If the local board ultimately confirms M30624FGPFP, its documented memory map
provides an additional discriminator for any real CPU-RAM hypothesis. Until
then, 0x41 should be called a **KMBUS_RAM_READ view**, not "the M16C RAM".
