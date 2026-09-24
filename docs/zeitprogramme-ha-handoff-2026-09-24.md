# Zeitprogramme / Schedule editor handoff - 2026-09-24

Status: **controller block semantics fully verified; guarded Home Assistant write path live-verified; dashboard visual refinement in progress**

This document is the current handoff/source of truth for the WB2A schedule
workstream. It records the verified controller contract, the production
Home Assistant write path, the live test result, the current local schedule
state and the next dashboard tasks.

## Scope

Exact local appliance/profile:

- Viessmann Vitodens 200-W WB2A
- VDensHO1
- device id 0x20C2
- software index 0x03

Programs:

- Heating circuit M1
- DHW
- circulation

Each weekday is one independent eight-byte block.

## Verified day-block contract

Address families:

| Program | Monday | Tuesday | Wednesday | Thursday | Friday | Saturday | Sunday |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Heating M1 | 0x2000 | 0x2008 | 0x2010 | 0x2018 | 0x2020 | 0x2028 | 0x2030 |
| DHW | 0x2100 | 0x2108 | 0x2110 | 0x2118 | 0x2120 | 0x2128 | 0x2130 |
| Circulation | 0x2200 | 0x2208 | 0x2210 | 0x2218 | 0x2220 | 0x2228 | 0x2230 |

Byte layout:

~~~text
byte0 start1
byte1 end1
byte2 start2
byte3 end2
byte4 start3
byte5 end3
byte6 start4
byte7 end4
~~~

Unused pairs are exactly:

~~~text
FF FF
~~~

Time encoding:

~~~text
encoded = (hour << 3) + minute/10
~~~

The local hardware tests verified:

- zero active intervals: `FFFFFFFFFFFFFFFF`;
- one interval;
- two intervals;
- all four intervals / all eight bytes as time values;
- slot removal back to `FF FF`;
- exact ten-minute resolution;
- `24:00 = 0xC0` as a valid interval end;
- byte-exact post-write readback;
- byte-exact restoration of the original block.

The VS1/KW low-level write response can still return
`255;0xADDR;00` for these eight-byte writes because the upstream receiver
waits for eight response bytes while this controller returns only a short
response. Byte-exact post-write readback is therefore the authoritative
persistence criterion on this path.

## Production guarded write path

Home Assistant does not write schedule blocks directly to `openv/cmnd`.

The dedicated service is:

~~~text
optolink-schedule-manager.service
/usr/local/bin/optolink-schedule-manager
~~~

Data path:

~~~text
Home Assistant MQTT text entity
  -> openv/schedule/set/<program>/<weekday>
  -> strict schedule validation
  -> read original complete 8-byte block
  -> complete writeraw block write
  -> byte-exact readback
  -> publish verified state
~~~

On a mismatch, the manager restores the previously read original block and
verifies the restore byte-for-byte before reporting an error.

Accepted editor values are intentionally narrow:

~~~text
05:00-20:00
05:00-08:00,16:00-22:00
05:00-08:00,10:00-12:00,14:00-16:00,18:00-24:00
none
~~~

Validation includes:

- maximum four intervals;
- exact ten-minute minute values;
- start 00:00..23:50;
- end up to 24:00;
- start strictly before end;
- ordered/non-overlapping intervals;
- complete eight-byte block writes.

Safety hardening after the first live UI session:

- blank payloads are rejected;
- only explicit `none` may clear a day;
- retained MQTT schedule commands are ignored;
- retained values on the guarded command topics are cleared before subscribe;
- HA text editor entities have a minimum length of four characters;
- incoming guarded command payloads are logged.

The manager was redeployed after this hardening and was confirmed active:

~~~text
2026-09-24 22:03:06
listening on 21 guarded schedule topics; Optolink commands=openv/cmnd
~~~

## Live Home Assistant end-to-end verification

The first production HA edit used Heating M1 Sunday.

Original:

~~~text
28A0FFFFFFFFFFFF
05:00-20:00
~~~

HA edit:

~~~text
2DA0FFFFFFFFFFFF
05:50-20:00
~~~

The schedule manager transmitted the complete block and an independent
`wb2a-schedule-probe read heating sonntag` later returned:

~~~text
RAW      2DA0FFFFFFFFFFFF
DECODED  05:50-20:00
~~~

This verifies the complete path:

~~~text
HA -> MQTT -> guarded schedule manager -> controller -> independent readback
~~~

## Current intentional local schedule state

At the end of this session:

### Heating M1

Monday through Saturday remain:

~~~text
05:00-20:00
28A0FFFFFFFFFFFF
~~~

Sunday remains at the live-test value unless manually changed later:

~~~text
05:50-20:00
2DA0FFFFFFFFFFFF
~~~

### DHW

All seven weekdays remain:

~~~text
05:30-21:00
2BA8FFFFFFFFFFFF
~~~

### Circulation

All seven weekdays are intentionally configured as empty:

~~~text
none
FFFFFFFFFFFFFFFF
~~~

This was done deliberately by the user because no circulation pump is
installed. It is **not** a write-path fault.

The circulation lane remains visible in the dashboard by explicit user
request. Do not remove or hide it yet.

## Production polling/discovery

The 21 schedule state datapoints were changed from startup-only `ONCE` reads
to the `SLOW` poll group so changes made at the physical controller
eventually resynchronize to Home Assistant.

Home Assistant discovery now exposes:

- 21 non-optimistic MQTT `text` editor entities;
- one diagnostic `zeitprogramm_schreibstatus` sensor with JSON attributes;
- the original schedule state topics remain the source of truth.

## Dashboard state

Dashboard source:

~~~text
config/optolink-splitter/homeassistant-dashboard.yaml
~~~

Current Zeitprogramme view:

- three program lanes: Heizung, Warmwasser, Zirkulation;
- seven weekday rows per lane;
- up to four interval pills per day;
- compact 24-hour timeline;
- current weekday highlight;
- active-now detection;
- tap a weekday row to open the native HA text editor;
- top summary cards for today's three programs;
- guarded write-status card.

Latest visual refinement added:

- a real 00 / 06 / 12 / 18 / 24 axis instead of the broken concatenated
  `0006121824` display;
- compact weekday cards;
- stronger current-day highlighting;
- a live "now" marker on today's timeline;
- active interval glow/emphasis;
- explicit `HEUTE`, `AKTIV · bis HH:MM` and `HEUTE · AUS` states;
- `none` rendered as `Keine Schaltzeit`;
- shorter top-card copy to reduce truncation.

Latest dashboard refinement commit:

~~~text
2ca471b8b88129a13cebac68db4faec3d342abc2
feat(dashboard): refine schedule timeline cockpit
~~~

Relevant backend/safety commits from this workstream include:

~~~text
e2dfa0dc  guarded schedule manager
e034609a  schedule-manager systemd service
e02f032b  guarded HA schedule editors
e6238c86  editable weekly schedule cockpit
4c435eb1  reject empty and retained destructive commands
0f83f611  prevent blank HA schedule submissions
5741d486  log guarded command payloads
60631ade  document intentional cleared circulation week
2ca471b8  refine schedule timeline cockpit
~~~

## Next session

Immediate next task:

1. reload/render the updated Zeitprogramme dashboard;
2. visually verify the new axis, current-day tint, now marker and compact card
   sizing;
3. fix any remaining desktop spacing/truncation issues;
4. check mobile layout before changing the interaction model.

After the visual baseline is accepted, extend the editor with higher-level
operations while leaving the verified schedule manager underneath unchanged:

- copy one day to another day;
- apply one day to Monday-Friday;
- apply one day to Saturday-Sunday;
- apply one day to the whole week;
- explicit preview/apply workflow for multi-day operations;
- visible readback confirmation/error state;
- later replace raw schedule text editing with a structured four-slot editor
  if that improves usability.

Do not remove the circulation lane during this next pass.

## Deferred/non-blocking items

- Decide later whether the circulation lane should stay operator-facing when no
  circulation pump is installed.
- Decide later whether Heating Sunday should be returned from the test value
  05:50-20:00 to 05:00-20:00.
- Continue to treat byte-exact readback, not the eight-byte VS1 write transport
  return code, as the persistence criterion.
