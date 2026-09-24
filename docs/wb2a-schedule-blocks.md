# WB2A / VDensHO1 time-program block format

Status: **daily block semantics hardware-verified; guarded Home Assistant write path live-verified**

Scope:

- Viessmann Vitodens 200-W WB2A
- controller profile `VDensHO1 / 20C2 / SW03`
- heating circuit M1 schedules
- domestic-hot-water schedules
- circulation schedules

This document exists so the Home Assistant schedule editor can be built only
after the controller-side block contract is understood and locally verified.

## Address map

Each weekday is one independent eight-byte block. Weekdays are spaced by
`0x08`.

| Program | Monday | Tuesday | Wednesday | Thursday | Friday | Saturday | Sunday |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Heating M1 | `0x2000` | `0x2008` | `0x2010` | `0x2018` | `0x2020` | `0x2028` | `0x2030` |
| DHW | `0x2100` | `0x2108` | `0x2110` | `0x2118` | `0x2120` | `0x2128` | `0x2130` |
| Circulation | `0x2200` | `0x2208` | `0x2210` | `0x2218` | `0x2220` | `0x2228` | `0x2230` |

The same address families are present in the historical OpenV/vcontrold
CycleTime definitions for read and write. The production WB2A profile already
uses these addresses for read-only Home Assistant sensors.

## Eight-byte day layout

A complete day is:

~~~text
byte 0  start interval 1
byte 1  end   interval 1
byte 2  start interval 2
byte 3  end   interval 2
byte 4  start interval 3
byte 5  end   interval 3
byte 6  start interval 4
byte 7  end   interval 4
~~~

Therefore one day supports at most four on/off intervals.

Unused pairs are encoded as:

~~~text
FF FF
~~~

Production UI code should normalize unused slots to the end of the block and
write the full eight bytes rather than trying to patch an individual slot.

## Time-byte encoding

For ordinary times:

~~~text
encoded_byte = (hour << 3) + (minute / 10)
~~~

Minutes therefore have ten-minute resolution.

Examples:

| Time | Byte |
| --- | ---: |
| 00:00 | `00` |
| 05:00 | `28` |
| 05:30 | `2B` |
| 08:30 | `43` |
| 13:00 | `68` |
| 20:00 | `A0` |
| 21:00 | `A8` |
| 23:50 | `BD` |
| 24:00 | `C0` |

`24:00` is meaningful as a day-end boundary. It should be allowed only as an
interval end in the guarded UI. Values that decode to 24:10 or later, hours
above 24, or minute fields 60/70 are not valid schedule times.

## Locally observed blocks

### Full 21-block snapshot — 2026-09-24

A complete live snapshot of all schedule blocks was read successfully through
the running splitter.

| Program | Mon | Tue | Wed | Thu | Fri | Sat | Sun |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Heating M1 | 05:00-20:00 | 05:00-20:00 | 05:00-20:00 | 05:00-20:00 | 05:00-20:00 | 05:00-20:00 | 05:00-20:00 |
| DHW | 05:30-21:00 | 05:30-21:00 | 05:30-21:00 | 05:30-21:00 | 05:30-21:00 | 05:30-21:00 | 05:30-21:00 |
| Circulation | 05:30-21:00 | 05:30-21:00 | 05:30-21:00 | 05:30-21:00 | 05:30-21:00 | 05:30-21:00 | 05:30-21:00 |

Raw baseline:

~~~text
Heating M1  0x2000..0x2030  28 A0 FF FF FF FF FF FF
DHW         0x2100..0x2130  2B A8 FF FF FF FF FF FF
Circulation 0x2200..0x2230  2B A8 FF FF FF FF FF FF
~~~

All 21 reads returned splitter success code `1` and the expected eight-byte
payload. The appliance currently uses only interval slot 1 in all three weekly
programs; slots 2..4 are unused `FF FF` pairs.

Read-only hardware work on the local WB2A already produced:

~~~text
Heating M1:
28 A0 FF FF FF FF FF FF
= 05:00-20:00

DHW:
2B A8 FF FF FF FF FF FF
= 05:30-21:00

Circulation:
2B A8 FF FF FF FF FF FF
= 05:30-21:00
~~~

These values independently confirm the byte formula used by
Optolink-Splitter's `schedvdens` codec.

## Optolink-Splitter read path

The production poll item has:

~~~text
(address, length=8, type='schedvdens')
~~~

The splitter reads all eight bytes and `schedvdens2str()` renders them as
four start/end pairs, for example:

~~~text
05:00-20:00,na-na,na-na,na-na
~~~

`0xFF` is rendered as `na`.

## Optolink-Splitter write path

The current upstream splitter has two supported paths relevant here.

### Raw command

A complete block can be written directly:

~~~text
wraw;0x2000;4368FFFFFFFFFFFF
~~~

This represents Monday heating `08:30-13:00`.

The splitter derives the write length from the hex payload, so this is an
eight-byte Virtual_WRITE.

### MQTT datapoint /set

When the schedule datapoint exists in the poll list with type
`schedvdens`, the splitter also accepts a human-readable payload on:

~~~text
<mqtt-base>/<datapoint-name>/set
~~~

For example:

~~~text
08:30-13:00,16:00-22:00
~~~

The splitter converts this to raw schedule bytes, pads the remaining slots with
`FF`, and issues `writeraw`.

A delayed forced refresh is scheduled after a `/set` write.

## Important validation gap in the upstream codec

The upstream `schedvdens2bytes()` converter is intentionally permissive. It
rounds the minute component instead of requiring an exact ten-minute value and
does not enforce all controller-level invariants.

The Home Assistant editor for this project must therefore validate before any
write:

1. maximum four intervals;
2. exact ten-minute resolution;
3. start time 00:00..23:50;
4. end time 00:10..24:00;
5. start strictly before end;
6. intervals sorted chronologically;
7. no overlaps;
8. unused slots represented as complete `FF FF` pairs;
9. always write/read back the complete eight-byte day block.

Do not pass arbitrary user strings directly to the permissive upstream
converter.

## Local write-verification gate

### First full-block write test — PASS

A guarded write/readback/restore test was completed on Heating M1 Sunday
(`0x2030`).

Original:

~~~text
28 A0 FF FF FF FF FF FF
05:00-20:00
~~~

Temporary test:

~~~text
28 9D FF FF FF FF FF FF
05:00-19:50
~~~

Observed result:

- test block persisted exactly: `289DFFFFFFFFFFFF`;
- original block was restored exactly: `28A0FFFFFFFFFFFF`;
- both post-write reads returned normal read success code `1`;
- therefore complete eight-byte schedule writes are confirmed to persist on
  the exact local `VDensHO1 / 20C2 / SW03` appliance.

The write command itself returned splitter response `255;0x2030;00` for both
the test and restore. This is not a failed controller write in this case.
Upstream VS1/KW `write_datapoint_ext()` waits for `wrlen` response bytes;
for an eight-byte write this controller returned only a short `00` response,
so the splitter eventually reports `0xFF = timeout` even though subsequent
byte-exact reads prove that the write was applied. For guarded schedule writes,
the post-write byte-exact readback is therefore the authoritative persistence
criterion.

### Second-interval write test — PASS

A second guarded probe on Heating M1 Sunday verified that bytes 2/3 are the
second independent start/end pair.

Temporary test:

~~~text
28 40 80 9D FF FF FF FF
05:00-08:00, 16:00-19:50
~~~

Observed result:

- exact test readback: `2840809DFFFFFFFF`;
- exact restore readback: `28A0FFFFFFFFFFFF`;
- therefore slot 2 is hardware-confirmed as byte 2=start / byte 3=end;
- the same VS1/KW short-response timeout behavior occurred and remains
  diagnostic only; byte-exact readback confirmed persistence and restoration.

### Four-interval / full eight-byte write test — PASS

A third guarded probe on Heating M1 Sunday populated all four interval pairs:

~~~text
28 40 50 60 70 80 90 9D
05:00-08:00, 10:00-12:00, 14:00-16:00, 18:00-19:50
~~~

Observed result:

- exact test readback: `284050607080909D`;
- all eight bytes were accepted as active schedule time values;
- exact restore readback: `28A0FFFFFFFFFFFF`;
- the restore therefore also proves that populated slots 2..4 can be cleared
  back to `FF FF` by writing the complete day block;
- the same VS1/KW short-response timeout behavior occurred, while byte-exact
  readback confirmed both persistence and restoration.

The core day-block structure is therefore hardware-confirmed end-to-end:
four ordered start/end pairs in eight bytes, with unused pairs represented by
`FF FF`.

### 24:00 day-end write test — PASS

A guarded probe on Heating M1 Sunday verified the special day-end boundary:

~~~text
28 C0 FF FF FF FF FF FF
05:00-24:00
~~~

Observed result:

- exact test readback: `28C0FFFFFFFFFFFF`;
- exact restore readback: `28A0FFFFFFFFFFFF`;
- therefore `0xC0` is hardware-confirmed as a valid `24:00` interval end
  on this exact controller;
- production validation should permit `24:00` only as an interval end, never
  as a start time.

### Empty-day write test — PASS

A final guarded probe on Heating M1 Sunday wrote an entirely empty day:

~~~text
FF FF FF FF FF FF FF FF
(no active intervals)
~~~

Observed result:

- exact test readback: `FFFFFFFFFFFFFFFF`;
- exact restore readback: `28A0FFFFFFFFFFFF`;
- therefore zero active intervals is hardware-confirmed and can be represented
  safely by the Home Assistant editor;
- the same VS1/KW short-response timeout occurred and remains diagnostic only.

### Hardware schedule contract — COMPLETE

The local `VDensHO1 / 20C2 / SW03` controller has now verified:

- zero, one, two and four active intervals;
- all four start/end slot pairs;
- complete eight-byte writes;
- addition and removal of interval slots;
- unused pairs as `FF FF`;
- ten-minute time encoding;
- `24:00 / 0xC0` as a valid interval end;
- byte-exact post-write readback;
- byte-exact restoration of the original day block.

The remaining gate is no longer controller block semantics. It is the
production Home Assistant/MQTT integration: strict validation, serialized
write/readback, visible status and non-optimistic UI behavior.


A guarded helper is included:

~~~text
wb2a-schedule-probe
~~~

It is restricted to the 21 known schedule blocks.

Useful commands:

~~~bash
wb2a-schedule-probe map
wb2a-schedule-probe snapshot
wb2a-schedule-probe decode 28A0FFFFFFFFFFFF
wb2a-schedule-probe encode '05:00-20:00'
~~~

The live probe:

~~~bash
wb2a-schedule-probe probe heating sonntag '05:00-19:50' \
  --confirm WRITE_AND_RESTORE
~~~

Behavior:

1. read and preserve the original eight-byte block;
2. refuse the current weekday unless explicitly overridden;
3. strictly validate and encode the requested test schedule;
4. write the complete eight-byte block;
5. read it back byte-for-byte;
6. restore the exact original bytes in a `finally` path;
7. read the restored block back byte-for-byte;
8. report PASS if test persistence and restore both match byte-for-byte; the
   VS1/KW write transport return code is shown diagnostically but is not treated
   as authoritative for an eight-byte schedule block.

Choose a weekday other than today for the first test.

## Current local schedule state after live HA testing

The first live Home Assistant edit was successfully written through the guarded
schedule manager and independently read back from the controller.

Current intentional local state relevant to follow-up work:

- Heating M1 Sunday is still at the test value `05:50-20:00` unless changed
  back by the user.
- The circulation schedule is intentionally cleared to
  `FFFFFFFFFFFFFFFF` for all seven weekdays because the local installation
  does not have a circulation pump.
- The circulation lane remains visible in the dashboard by user request and
  should not be removed or hidden yet.

The cleared circulation week is therefore **intentional configuration**, not a
write-path incident.

## Guarded Home Assistant write path

The production implementation now uses a dedicated
`optolink-schedule-manager` service instead of exposing raw schedule writes
from Home Assistant.

Write flow:

~~~text
MQTT text entity
  -> openv/schedule/set/<program>/<weekday>
  -> strict project-side validation
  -> read original 8-byte block
  -> complete writeraw block write
  -> byte-exact readback
  -> publish verified state
~~~

If the target readback does not match, the manager writes the previously read
original block back and verifies that restore byte-for-byte before reporting
the error.

Accepted editor values are intentionally narrow:

~~~text
05:00-20:00
05:00-08:00,16:00-22:00
05:00-08:00,10:00-12:00,14:00-16:00,18:00-24:00
none
~~~

The 21 normal schedule datapoints remain the source of truth. They are now
refreshed at the `SLOW` poll cadence instead of only at splitter startup so a
change made at the physical boiler control eventually reaches Home Assistant.
A successful schedule-manager write additionally republishes the verified
schedule state immediately.

Home Assistant discovery exposes:

- 21 non-optimistic MQTT `text` editor entities;
- one diagnostic `zeitprogramm_schreibstatus` sensor with JSON attributes
  describing the last operation.

The dashboard uses each text entity as both the displayed verified state and
the edit target. Tapping a weekday opens the native Home Assistant more-info
editor for that day.

Current integration status: **live-verified end-to-end through Home Assistant,
MQTT, the guarded schedule manager and independent controller readback.**

## Home Assistant implications after PASS

Once the local probe passes:

- change schedules from a start-only read strategy to an appropriate low-rate
  refresh group so physical-panel changes eventually appear in HA;
- expose guarded writable schedule entities/API rather than raw unvalidated
  strings;
- keep the raw eight-byte state/readback available for diagnostics;
- build the final dashboard from the validated structure:
  - three program lanes: heating, DHW, circulation;
  - seven weekdays;
  - up to four intervals/day;
  - active-now indication;
  - compact 24-hour timeline;
  - per-day editor;
  - copy day / copy weekdays / copy whole week actions;
  - explicit save/apply state;
  - readback confirmation and visible error state;
  - no optimistic UI for controller writes.

The controller block gate and first live Home Assistant write/readback are complete. Further work is now dashboard UX, multi-day convenience operations and visual verification.

## Detailed handoff

The complete schedule/Home Assistant handoff for this session is recorded in
`docs/zeitprogramme-ha-handoff-2026-09-24.md`.
