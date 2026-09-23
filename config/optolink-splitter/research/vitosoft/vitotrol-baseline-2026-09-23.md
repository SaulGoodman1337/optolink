# Vitotrol baseline on local VDensHO1 — 2026-09-23

Status: **LOCAL-VERIFIED / read-only**

This baseline was recorded on the local Vitodens 200-W WB2A / VDensHO1 before
any Vitotrol-emulation write was attempted.

## A1/M1

~~~text
0x27A0 / 1 -> 00
0x0A5C / 4 -> 00000000
0x0896 / 2 -> c800
0x089C / 1 -> 03
0x27B0 / 1 -> 00
0x27B2 / 1 -> 08
0x27E2 / 1 -> 32
~~~

Decoded with the production Vitosoft metadata:

| Address | Meaning | Raw | Decoded |
| --- | --- | --- | --- |
| 0x27A0 | remote identification A1/M1 | 00 | no Vitotrol configured/detected |
| 0x0A5C | remote software-index block | 00000000 | no software-index data present |
| 0x0896 | measured room temperature A1/M1 | c800 | little-endian 0x00C8 = 200 -> 20.0 °C |
| 0x089C | room-sensor status A1/M1 | 03 | Vitosoft enum: unknown |
| 0x27B0 | room influence operating-mode selection | 00 | WS/WS: weather-compensated normal + reduced |
| 0x27B2 | room influence factor | 08 | factor 8; allowed 0..31; Vitosoft ALZ/default 8 |
| 0x27E2 | room-temperature correction | 32 | decimal 50 = 0.0 K correction |

## M2

~~~text
0x37A0 / 1 -> 00
0x0A60 / 4 -> 00000000
0x0898 / 2 -> c800
0x089D / 1 -> 03
0x37B0 / 1 -> 00
0x37B2 / 1 -> 08
0x37E2 / 1 -> 32
~~~

The M2 values are byte-for-byte equivalent to the A1/M1 baseline:

| Address | Meaning | Raw | Decoded |
| --- | --- | --- | --- |
| 0x37A0 | remote identification M2 | 00 | no Vitotrol configured/detected |
| 0x0A60 | remote software-index block | 00000000 | no software-index data present |
| 0x0898 | measured room temperature M2 | c800 | 20.0 °C |
| 0x089D | room-sensor status M2 | 03 | Vitosoft enum: unknown |
| 0x37B0 | room influence operating-mode selection | 00 | WS/WS |
| 0x37B2 | room influence factor | 08 | factor 8 / Vitosoft default |
| 0x37E2 | room-temperature correction | 32 | decimal 50 = 0.0 K correction |

## Interpretation

The two heating circuits show the same absent-remote signature:

~~~text
remote identification = 0
software index        = 00000000
room value            = 20.0 °C
room sensor status    = 3 / unknown
~~~

Because both remote-identification objects are 0, both software-index blocks are
all zero and both independent room-temperature channels report the exact same
20.0 °C while their sensor status is not OK, the 20.0 °C value must **not** be
treated as a measured room temperature. The strongest current interpretation is
that it is a controller fallback/default value while no valid room sensor is
available.

This is an inference from the correlated local state, not an explicit Vitosoft
description of 20.0 °C as a sentinel.

## Relevant Vitosoft configuration semantics

Remote identification:

~~~text
A1/M1 0x27A0
M2    0x37A0

0 = no Vitotrol
1 = Vitotrol 200
2 = Vitotrol 300
~~~

The Vitosoft description states that an attached remote is detected
automatically. For the A1/M1 configuration event it additionally states that
the value is automatically set after detection and is reset only manually.

Room influence factor B2:

~~~text
0      = no room influence
1..31  = increasing room-sensor influence
default/ALZ = 8
~~~

Room-temperature correction E2:

~~~text
0..49  = negative correction in 0.1 K steps
50     = no correction
51..99 = positive correction in 0.1 K steps
default/ALZ = 50
~~~

Therefore the measured values B2=8 and E2=50 are exactly the Vitosoft defaults.

## Fault risk before a manual A0 write

The same production Vitosoft text resources define for the exact profile:

~~~text
VDensHO1 error BC = Fehler Fernbedienung HK1
VDensHO1 error BD = Fehler Fernbedienung HK2
~~~

This is strong source evidence that configuring/expecting a remote while no
physical KM-BUS remote responds can create a real controller fault.

Therefore a manual `0x27A0 = 1` or `2` test must not be treated as a harmless
boolean toggle. Before any such write:

1. capture the current controller/system fault state and relevant fault-history
   entries;
2. preserve the exact A0/B0/B2/E2 baseline above;
3. prepare the immediate rollback `0x27A0 = 0`;
4. monitor remote software-index, room-sensor status and error state during the
   test;
5. do not enable room influence (B0) at the same time.

## Error-history baseline for the next step

The production Vitosoft access metadata also contains the generic system fault
archive:

~~~text
ID          ecnsysEventType~Error
Address     0x7507
FCRead      Virtual_READ
BlockLength 90
BlockFactor 10
~~~

This represents ten 9-byte system-fault slots. Current community
reverse-engineering identifies each slot as:

~~~text
byte 0   fault code
bytes 1..8   BCD timestamp
~~~

and distinguishes this system archive from the burner/GFA-specific fault
history at 0x7590 and following addresses.

For the upcoming controlled Vitotrol experiment it is sufficient to capture at
least the first/newest 9-byte slot before and after the test:

~~~text
0x7507 / 9
~~~

The exact VDensHO1 text resources define:

~~~text
0xBC = Fehler Fernbedienung HK1
0xBD = Fehler Fernbedienung HK2
~~~

so those two codes are the primary fault signatures to watch for.

## Measured system-fault baseline

Read-only measurements:

~~~text
0x7507 / 9
-> b72026092202025912

0x7507 / 90
-> b72026092202025912
   f92026092101173144
   b72026091906025704
   b72026090506025704
   b72026082805025704
   b72026081405025704
   b7
~~~

The 90-byte request returned only **55 data bytes** while still reporting
success. That is six complete 9-byte slots plus the first byte of slot 7.
Therefore the full archive must not be assumed to be returned in one request on
this controller. For controlled experiments, read slots individually in
9-byte units.

The BCD timestamp layout is consistent with:

~~~text
code CC YY MM DD weekday hh mm ss
~~~

Decoded complete slots:

| Slot | Code | Timestamp | Local Vitosoft meaning |
| ---: | ---: | --- | --- |
| 1 | B7 | 2026-09-22 02:59:12 | Kesselcodierkarte falsch/fehlerhaft |
| 2 | F9 | 2026-09-21 17:31:44 | Fehler Gebläse - Drehzahl nicht erreicht |
| 3 | B7 | 2026-09-19 02:57:04 | Kesselcodierkarte falsch/fehlerhaft |
| 4 | B7 | 2026-09-05 02:57:04 | Kesselcodierkarte falsch/fehlerhaft |
| 5 | B7 | 2026-08-28 02:57:04 | Kesselcodierkarte falsch/fehlerhaft |
| 6 | B7 | 2026-08-14 02:57:04 | Kesselcodierkarte falsch/fehlerhaft |

Slot 7 is incomplete in the long read and begins with B7 only.

The exact local `Textresource_de.xml` entries for VDensHO1 also define:

~~~text
B7 = Kesselcodierkarte falsch/fehlerhaft
F9 = Fehler Gebläse - Drehzahl nicht erreicht
BC = Fehler Fernbedienung HK1
BD = Fehler Fernbedienung HK2
~~~

No BC or BD entry is present in the six complete baseline slots. That gives a
clean fault-history reference for the planned remote-identification experiment.

## Current-alarm baseline immediately before a possible A0 write

Measured read-only:

~~~text
0xA132 / 29
-> 00000000000000000000000019173101ea070917091719000000000000

0x5738 / 1
-> 00
~~~

For the 29-byte `0xA132` alarm block, the Vitosoft-derived fields of interest
are at byte positions 27 and 28 (zero-based):

~~~text
byte 27 = 00   participant number associated with current alarm
byte 28 = 00   current alarm fault code
~~~

Thus, immediately before any Vitotrol identification write:

~~~text
current alarm participant = 0
current alarm code        = 0
current GFA error         = 0
~~~

This is the clean pre-write reference. If a later controlled `0x27A0 = 1`
test creates the expected missing-remote condition, the primary signatures to
watch are:

~~~text
A132 byte 28 -> BC
0x7507 newest system fault -> BC
~~~

where local Vitosoft maps `BC` to `Fehler Fernbedienung HK1`.

## Current conclusion

The local absent-Vitotrol state is now well characterized.

The next experiment should still be read-only: establish an error/fault baseline
suitable for a controlled before/after comparison. Only then should a temporary
A0 identification write be considered.
