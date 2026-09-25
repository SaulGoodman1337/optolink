# M30624 / M16C-62P non-destructive readout plan

Status: **planning only — local MCU identity not yet proven**

This document applies **only if the main QFP on the local WB2A / GG1 / board
7187393 is physically confirmed as an M30624…FP device**. Until the top marking
is readable, M30624 is a working hypothesis, not a board fact.

## Why this path is plausible

Renesas classifies `M30624FGPFP` as an M16C/62P device with:

- 100-pin QFP `PLQP0100KB-A / 100P6Q-A`;
- 256 KiB program flash;
- 20 KiB RAM;
- 4 KiB data flash;
- 24 MHz maximum clock.

The 256 KiB user-flash window is:

~~~text
0xC0000 .. 0xFFFFF
~~~

Two independent open-source readers support the M16C/62P family:

- `truhy/m16c-flasher` — asynchronous serial bootloader reader/flasher,
  explicitly tested by its author on an M30624 device;
- `beroset/pico-puller` — Raspberry-Pi-Pico synchronous-serial M16C reader.

The production WB2A must never be used for erase/unlock experiments.

## Official M30624…FP pin map

For the **100-pin FP package** Renesas Table 1.13/1.14 gives:

| Signal | MCU function | FP pin |
| --- | --- | ---: |
| CNVSS | mode select | 9 |
| RESET | reset | 12 |
| VSS | ground | 14 |
| VCC1 | logic supply | 16 |
| TXD1 | P6_7 / TXD1 | 31 |
| RXD1 | P6_6 / RXD1 | 32 |
| SCLK | P6_5 / CLK1 | 33 |
| BUSY | P6_4 / RTS1 | 34 |
| EPM | P5_5 in serial-programming mode | 41 |
| CE | P5_0 in serial-programming mode | 46 |
| VCC2 | second supply domain | 62 |
| VSS | ground | 64 |

These pin numbers are specific to the `FP` column. Renesas also publishes a
different `GP` numbering; do not mix them.

## Standard serial I/O boot-mode state

Renesas' standard serial-I/O application circuit shows:

~~~text
CNVSS = VCC1
EPM   = VSS
CE    = VCC2
RESET = transition VSS -> VCC1
~~~

and uses UART1 / serial channel 1:

~~~text
P6_7 / TXD1
P6_6 / RXD1
P6_5 / CLK1   (mode 1)
P6_4 / RTS1   BUSY / monitor
~~~

For standard serial I/O mode 2, Renesas documents RXD1/TXD1 and the same
control/mode pins. The M16C monitor-debugger documentation also identifies
P6_6/RXD1 and P6_7/TXD1 as the M16C/62P programming/debug communication port.

## Local-board correlation procedure

This section is deliberately passive first.

### Gate 1 — prove the MCU

Required evidence:

- original-resolution close-up of the complete top marking;
- package dimensions / pin count;
- pin-1 orientation.

Do **not** proceed from the current visual resemblance alone.

### Gate 2 — unpowered continuity map

With appliance power removed and the board treated according to normal service
safety procedure, map candidate service pads / headers to the exact MCU pins.

Highest-value nets:

~~~text
pin  9  CNVSS
pin 12  RESET
pin 14  VSS
pin 16  VCC1
pin 31  TXD1
pin 32  RXD1
pin 33  CLK1
pin 34  RTS1/BUSY
pin 41  EPM
pin 46  CE
pin 62  VCC2
pin 64  VSS
~~~

For each J1/X10/test pad record:

- direct continuity yes/no;
- series resistor / zero-ohm link;
- pull-up / pull-down;
- nearby transistor/buffer/level-shifter;
- visible via route if available.

A good service/programming connector should account for several of these nets,
not merely one UART pair.

### Gate 3 — voltage-domain confirmation

Before attaching a programmer:

- determine actual VCC1 and VCC2 levels on the local board;
- establish a common reference at a proven VSS point;
- confirm no service pad is connected to mains-referenced circuitry;
- confirm whether the board inserts buffers or protection between service pads
  and MCU pins.

Do not assume 3.3 V TTL. Renesas specifies the flash read operation for this
device family in the VCC1 4.0–5.5 V region.

### Gate 4 — bootloader existence proof only

The first active test is limited to the standard bootloader's **version/status**
commands.

With `truhy/m16c-flasher` these correspond to:

~~~text
m16cflasher ver    ...
m16cflasher status ...
~~~

These commands do not require the seven-byte flash ID and do not request an
erase/program operation.

Acceptance criterion:

- repeatable valid bootloader version/status;
- no write, erase, lock-bit or RAM-download command used;
- board returns to normal operation after removing the programming fixture.

If this gate fails, stop and re-check MCU identity, mode pins and electrical
mapping.

## ID-code gate

Normal user-flash read requires the correct seven-byte M16C ID.

Renesas places the bytes at:

~~~text
0xFFFDF
0xFFFE3
0xFFFEB
0xFFFEF
0xFFFF3
0xFFFF7
0xFFFFB
~~~

Open-source tools commonly demonstrate all-zero IDs, while Renesas tooling
documents the all-FF case as undefined/open.

Only the two source-justified default candidates are reasonable on production
hardware:

~~~text
00 00 00 00 00 00 00
FF FF FF FF FF FF FF
~~~

If neither authenticates, **stop**.

Do not use:

- all-chip erase;
- erase-to-unlock;
- lock-bit clearing;
- boot-ROM rewriting;
- speculative ID brute force;
- voltage/clock glitching on the production controller.

## Readout if the ID authenticates

For an M30624 256 KiB image the read target is:

~~~text
0xC0000 .. 0xFFFFF
size = 0x40000 = 262144 bytes
~~~

The `m16c-flasher` repository includes an example for exactly this address
range.

Acquisition procedure:

1. read the range once;
2. read it a second time without power-cycle if practical;
3. compare SHA-256 hashes;
4. power-cycle / re-enter boot mode;
5. read a third time;
6. require byte-identical results before treating the image as canonical;
7. archive raw dump privately;
8. publish only hashes and derived analysis.

## Immediate post-dump analysis

Repository helper:

~~~text
tools/m16c-fw-inspect.py
~~~

Initial workflow:

~~~text
python3 tools/m16c-fw-inspect.py firmware.bin
python3 tools/m16c-fw-inspect.py firmware.bin --json > firmware-first-pass.json
~~~

Then load at:

~~~text
processor: M16C
image base: 0xC0000
size:       0x40000
~~~

in Ghidra/IDA and apply M16C/62P SFR definitions.

## Vitotrol-specific firmware targets

The goal is not a generic disassembly. Search for the receive-side state
transition which physical KM-BUS traffic triggers.

Known external/controller state:

~~~text
0x27A0  remote configuration A1/M1
0x0A5C  remote software/index state
0x0896  room actual value A1/M1
0x089C  room-sensor status A1/M1
BC      remote-control communication fault
~~~

Known physical protocol anchors:

~~~text
device class  0x11
Vitotrol 200  0x34
Vitotrol 300  0x38

discovery:
11 00 33 0A 01 01 F8 04 ...

PING/PONG:
11 00 00 08 01 01 ...
00 11 80 08 01 01 ...

room record HK1:
00 11 BF 0C 01 01 20 ...
~~~

Known cross-family runtime type encodings from the VBC550/NRF metadata:

~~~text
0x34 F2 / Vitotrol-200 family
0x38 F3 / Vitotrol-300 family
0x74 F2 on M1
0x78 F3 on M1
0xB4 F2 on M2
0xB8 F3 on M2
~~~

These are search/correlation anchors, not proof that the numeric NRF datapoint
addresses map directly to MCU RAM on VDensHO1.

The desired call chain is conceptually:

~~~text
KM-BUS RX
  -> CRC/frame validation
  -> class / slot / device-ID handling
  -> participant alive/watchdog refresh
  -> remote software/index state
  -> room-sensor validity
  -> room-temperature decode/update
~~~

Once that code path is located, check for:

- callable service function already reachable from Optolink;
- shared mailbox/queue;
- writable internal state with an existing guarded host handler;
- watchdog timestamp/counter;
- address translation between Optolink datapoints and actual MCU storage.

Only after that should any new live Optolink write hypothesis be generated.

## Sources

Primary:

- Renesas, *M16C/62P Group Hardware Manual*, Rev. 2.41.
- Renesas product page for `M30624FGPFP`.
- Renesas M32C/M16C UART monitor-debugger documentation.

Implementation references:

- `truhy/m16c-flasher`
- `beroset/pico-puller`
- `BitBangingBytes/m16c-62p` Ghidra support/SFR definitions.

Local project evidence:

- GitHub issue #25.
- `docs/regulation-board-photo-capture.md`.
- `config/optolink-splitter/research/vitotrol-software-emulation-deep-dive-2026-09-25.md`.
- `tools/m16c-fw-inspect.py`.
