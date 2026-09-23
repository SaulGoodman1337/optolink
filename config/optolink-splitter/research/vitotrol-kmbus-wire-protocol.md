# Vitotrol KM-BUS wire protocol — reconstructed reference

Status: **source-reconstructed / partially hardware-correlated**

Purpose: provide the byte-level physical KM-BUS reference for Vitotrol
emulation against the local VDensHO1/WB2A.

This document is based primarily on two independently developed working
emulators:

- `dumpfheimer/WiFiVitotrol` at
  `abf6de604ff3843aab1f6aa0730511b65ac61757`;
- `boblegal31/Heater-remote` at
  `db1290705c1495d2f00f63aea844dda06914d3f4`.

It is also consistent with the local hardware experiment in which
`0x27A0 = 1` caused `BC = Fehler Fernbedienung HK1` because no physical
KM-BUS Vitotrol slave was answering.

## Physical serial layer

Both working emulator codebases configure:

~~~text
1200 baud
8 data bits
even parity
1 stop bit
~~~

or, compactly:

~~~text
1200 8E1
~~~

The electrical layer is M-Bus/KM-BUS rather than TTL UART directly. The
boiler/controller is the bus master; a Vitotrol behaves as an M-Bus slave and
returns data by current modulation.

## Common telegram header

Observed/reconstructed frame layout:

~~~text
byte 0  destination class
byte 1  source class
byte 2  command
byte 3  total telegram length
byte 4  internal slot / heating-circuit slot
byte 5  source subclass
byte 6..n payload
last 2 bytes CRC16
~~~

Relevant device classes:

~~~text
0x00  Vitotronic / controller
0x11  Vitotrol
0xFF  broadcast
~~~

Relevant commands:

| Command | Meaning |
| ---: | --- |
| 0x00 | PING |
| 0x31 | request one register byte |
| 0x33 | request N register bytes |
| 0x3F | command/request-record style exchange |
| 0x80 | PONG |
| 0xB1 | send one register byte |
| 0xB3 | send N register bytes / data record |
| 0xBF | send command/data record |

## CRC

The physical KM-BUS telegram uses reflected CRC-16 with polynomial `0x1021`,
initial value `0x0000`, no final XOR. In reflected form this is equivalent
to the usual Kermit bit processing with polynomial `0x8408`.

The CRC is transmitted low byte first.

Known validation example from Heater-remote:

~~~text
00 11 80 08 02 01 91 76
                  ^^^^^ CRC
~~~

## Vitotrol identity

### Vitotrol 200 reference

Current WiFiVitotrol defaults:

~~~text
DEVICE_CLASS = 0x11
DEVICE_ID    = 0x34
DEVICE_SN1   = 0x00
DEVICE_SN2   = 0x05
DEVICE_SLOT  = 0x01
~~~

Registers:

~~~text
F8 = 11
F9 = 34
FA = 00
FB = 05
~~~

### Vitotrol 300 reference

Heater-remote and WiFiVitotrol both use the known Vitotrol-300 identity family:

~~~text
DEVICE_CLASS = 0x11
DEVICE_ID    = 0x38
SN bytes     = 00 11   (one known implementation)
~~~

Heater-remote used slot 2 because a real Vitotrol was already present as the
first remote.

## Discovery sequence

OpenV captures show the boiler walking expected devices and requesting
`F8..FB`.

A source-captured slot-1 discovery request is:

~~~text
11 00 33 0A 01 01 F8 04 49 EF
~~~

Decode:

~~~text
11       destination class: Vitotrol
00       source class: controller
33       request N registers
0A       total telegram length = 10
01       internal slot 1
01       source subclass
F8       first register
04       number of registers
49 EF    CRC
~~~

A Vitotrol-200 identity response generated from the current WiFiVitotrol
identity and the same CRC algorithm is:

~~~text
00 11 B3 10 01 01
F8 11 F9 34 FA 00 FB 05
06 64
~~~

The response payload is address/value pairs rather than just four values.

The emulator must answer quickly after the master request. Community hardware
work reports roughly a 60 ms reply window as the practical order of magnitude;
implementation should respond immediately rather than deliberately waiting.

## Register 0x00 caveat

Several emulator generations answer a one-byte read of register `0x00`, but
the value is not stable across implementations:

~~~text
older Heater-remote, slot 2: 0x02
WiFiVitotrol before 2025:    0x01
WiFiVitotrol current:        0x12
~~~

The current WiFiVitotrol change to `0x12` was introduced in commit
`67196f757928706eeac73ebcb6cf3f5e68c9c2e9`.

Therefore register `0x00` must not yet be treated as a fully decoded protocol
constant. The robust identity evidence is F8..FB.

## Ping / runtime behavior

After successful discovery the controller starts addressing the configured
Vitotrol slot with PING telegrams.

The slave does **not** transmit asynchronously. It uses the master's PING
opportunity to return one of:

- PONG;
- a pending command/data record;
- a periodic room-temperature record.

This behavior is implemented independently by both Heater-remote and
WiFiVitotrol.

A slot-1 PONG constructed from the documented frame layout is:

~~~text
00 11 80 08 01 01 F9 5C
~~~

The older slot-2 Heater-remote source contains the independently known frame:

~~~text
00 11 80 08 02 01 91 76
~~~

## Room-temperature injection on the physical KM-BUS

This is the most important runtime path for the project.

The physical Vitotrol emulator does **not** write Optolink object `0x0896`.
It sends a slave-to-master `0xBF` record.

Circuit/record numbers:

~~~text
0x20  heating circuit 1 room temperature
0x21  heating circuit 2 room temperature
0x22  heating circuit 3 room temperature
~~~

This resolves an apparent discrepancy in older examples: a frame using
`0x22` was reporting circuit 3, while WiFiVitotrol's default `0x20` is
circuit 1.

### Encoding

The room temperature is represented in tenths of a degree as a little-endian
integer. Data bytes after the record number are XORed with `0xAA`.

For 21.5 °C:

~~~text
21.5 °C
-> 215 decimal
-> 0x00D7
-> low byte D7 xor AA = 7D
-> high byte 00 xor AA = AA
~~~

A known physical frame for record `0x22` is:

~~~text
00 11 BF 0C 01 01 22 7D AA AA 19 0A
~~~

The CRC validates exactly.

The equivalent circuit-1/record-`0x20` frame is:

~~~text
00 11 BF 0C 01 01 20 7D AA AA 6F 33
~~~

For the controller's current 20.0 °C fallback value:

~~~text
20.0 °C = 200 = 0x00C8

00 11 BF 0C 01 01 20 62 AA AA 3D FC
~~~

### Send cadence

The cadence is not a strict protocol constant:

- current WiFiVitotrol schedules the value every 30 s;
- Heater-remote schedules it about every 60 s;
- both actually transmit it as the response to a suitable master PING.

Therefore the important requirement is not exactly 30 vs 60 seconds. It is
that a valid room-temperature response is periodically returned during the
controller's poll/ping cycle.

## Master-to-slave status records

After discovery the controller also sends records such as:

~~~text
record 0x1C  master/general status
record 0x1D  heating circuit 1 status
record 0x1E  heating circuit 2 status
record 0x1F  heating circuit 3 status
~~~

These are `0xBF` records from controller to Vitotrol. Their payload bytes
after the record number use XOR `0xAA` encoding.

Known contents include boiler temperature, DHW temperature, outside
temperature, flow temperature, operating mode and burner/pump status.

A complete room-temperature-only emulator does not need to decode every field
before proving registration, but it should accept these records without
breaking the link.

## Minimal emulator state machine for local WB2A

The minimum source-supported sequence is now:

~~~text
1. Configure A1/M1 for Vitotrol 200
   controller virtual object 0x27A0 = 1

2. Controller searches slot 1:
   11 00 33 ... 01 01 F8 04 ...

3. Slave responds with F8..FB identity:
   class 11 / ID 34 / serial bytes

4. Handle any follow-up one-byte register reads
   especially register 0x00, value still implementation-dependent

5. Controller enters normal runtime:
   PINGs addressed to class 0x11 / slot 1
   status records sent to slave

6. Slave responds to PING:
   normally PONG
   periodically 0xBF record 0x20 with room temperature

7. Observe controller-side state:
   0x0A5C remote software-index block
   0x0896 measured room temperature
   0x089C room-sensor status
   0xA132 current alarm
   0x7507 fault history
~~~

Success criterion:

~~~text
0x27A0 = 1
AND no persistent/current BC fault
AND 0x0896 follows the transmitted test temperature
AND 0x089C transitions to a valid/OK state
~~~

## Relation to Optolink-only emulation

The physical wire protocol is now sufficiently concrete to serve as the
reference target.

An Optolink-only solution would have to reproduce the *effect* of this slave
exchange inside the controller. Merely writing `0x27A0` is already proven
insufficient.

The current Vitosoft analysis of `KBUS_TRANSPARENT_WRITE`,
`KBUS_DIRECT_WRITE` and `KBUS_GATEWAY_WRITE` does not show a raw physical
frame-injection API. See
[vitosoft/kbus-write-function-analysis.md](vitosoft/kbus-write-function-analysis.md).

Until a source-defined raw-slave-injection path is found, physical KM-BUS slave
emulation is the reference implementation and the lower-risk engineering path.
