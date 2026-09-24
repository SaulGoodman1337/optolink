# WB2A / VDensHO1 time-program block format

Status: **read path verified on local hardware; block encoding verified; local write persistence test pending**

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

Public OpenV definitions and Optolink-Splitter itself support eight-byte
CycleTime writes, but this project still requires a write/readback/restore test
on the exact local `VDensHO1 / 20C2 / SW03` appliance before enabling schedule
writes in Home Assistant.

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
8. report PASS only if test persistence and restore both match.

Choose a weekday other than today for the first test.

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

Until the local write gate passes, the dashboard remains read-only.
