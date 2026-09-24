# WB2A / VDensHO1 read-later address register - 2026-09-24

Status: **source-backed read-only backlog; not a request to probe everything immediately**

Purpose: preserve diagnostically useful VDensHO1 addresses that have not yet been promoted to locally verified project datapoints. The list is intentionally selective. It excludes blind address scans, write experiments and already well-covered runtime objects.

Source basis:
- exact local Vitosoft profile: VDensHO1 / 20C2;
- Collector-v6 snapshot `vitosoft-private-archive-20260924-143439.7z`;
- exact generated VDensHO1 catalog used as an independent field-length/conversion cross-check.

## Priority A - high-value local read-only candidates

| Address | Read | Source meaning | Conversion / values | Why keep it |
| --- | --- | --- | --- | --- |
| `0x0816` | 2 bytes | Abgastemperatur / AGTS | little-endian / 10 °C | explicitly requested dashboard/research value; useful for combustion/heat-exchanger correlation |
| `0x081A` | 2 bytes | gemischte / gemeinsame Vorlauftemperatur VTS | little-endian / 10 °C | may differ from boiler/KTS and helps separate hydraulic temperature points |
| `0x083A` | 1 byte | status outside-temperature sensor ATS | 0 OK, 1 short, 2 open, 3/4 reference error, 6 absent | direct sensor-health diagnostic |
| `0x083B` | 1 byte | status boiler-temperature sensor KTS | same status family | direct sensor-health diagnostic |
| `0x0840` | 1 byte | status flow-temperature sensor VTS | same status family | useful together with `0x081A` |
| `0x0883` | 1 byte | FlowSwitch | 0 OFF, 1 ON | previously overlooked hydraulic binary input; worth checking whether present/used on this WB2A |
| `0x8853` | 1 byte | burner type | 0 single-stage, 1 two-stage, 2 modulating | simple identity consistency check against local modulating GFA behavior |
| `0xA305` | 1 byte | boiler-state modulation value | raw / 2 % | independent modulation view to compare with GFA P09 and existing runtime objects |
| `0x083D` | 1 byte | status sensor STS2 / storage sensor 2 | 0 OK ... 6 absent | useful to document DHW sensor topology |
| `0x089C` | 1 byte | room-temperature sensor HK1 status | 0 OK ... 6 absent | helps document whether a real room sensor is present or only configuration exists |
| `0x5527` | 2 bytes | damped/mixed outside temperature | little-endian / 10 °C | useful for heating-curve behavior and dashboard diagnostics |
| `0x8851` | 1 byte | DHW appliance/construction type | enum | documents storage/combi topology from controller view |

### Suggested first bounded batch

These are ordinary read-only VDensHO1 virtual reads:

```bash
/usr/local/bin/optolink-debug request "r;0x0816;2;raw;False"
/usr/local/bin/optolink-debug request "r;0x081A;2;raw;False"
/usr/local/bin/optolink-debug request "r;0x083A;1;raw;False"
/usr/local/bin/optolink-debug request "r;0x083B;1;raw;False"
/usr/local/bin/optolink-debug request "r;0x0840;1;raw;False"
/usr/local/bin/optolink-debug request "r;0x0883;1;raw;False"
/usr/local/bin/optolink-debug request "r;0x8853;1;raw;False"
/usr/local/bin/optolink-debug request "r;0xA305;1;raw;False"
/usr/local/bin/optolink-debug request "r;0x083D;1;raw;False"
/usr/local/bin/optolink-debug request "r;0x089C;1;raw;False"
/usr/local/bin/optolink-debug request "r;0x5527;2;raw;False"
/usr/local/bin/optolink-debug request "r;0x8851;1;raw;False"
```

Do not automatically add these to the production poll loop. First verify local support, sane values and whether the information is actually useful.

## Priority B - KM-BUS participant identity/error map

These blocks are useful for topology and future firmware/board correlation. They are low-frequency diagnostics, not fast poll candidates.

| Address | Read | Meaning |
| --- | --- | --- |
| `0x0A33` | 1 byte | KM error - separate A1 pump |
| `0x0A34` | 1 byte | KM error - M2 pump |
| `0x0A31` | 1 byte | KM error - mixer |
| `0x0A32` | 1 byte | KM error - external extension |
| `0x0A36` | 1 byte | KM error - Vitocom |
| `0x6550` | 1 byte | KM error - Vitosolic |
| `0x0A4C` | 4 bytes | A1 pump software-index block; byte 3 is SW index |
| `0x0A50` | 4 bytes | M2 pump software-index block; byte 3 is SW index |
| `0x0A44` | 4 bytes | mixer software-index block; byte 3 is SW index |
| `0x0A40` | 4 bytes | solar controller software-index block; byte 3 is SW index |
| `0x0A58` | 4 bytes | Vitocom software-index block; byte 3 is SW index |
| `0x0A5C` | 4 bytes | remote control A1 software-index block; byte 3 is SW index |
| `0x0A60` | 4 bytes | remote control M2 software-index block; byte 3 is SW index |

Expected absence must not be treated as a fault. For example, local `E5=00` already says there is no separate A1 KM-BUS heating-circuit pump. These reads are topology confirmation only.

## Priority C - conditional extension/output diagnostics

Read these only when the related hardware/function is relevant:

| Address | Read | Meaning / caution |
| --- | --- | --- |
| `0x0A80` | 1 byte | external request / operating-mode input |
| `0x0A81` | 1 byte | external block input |
| `0x0A82` | 1 byte | external-extension collective fault |
| `0x0A86` | 2 bytes | external 0-10 V input; catalog renders raw / 10, but engineering semantics should be verified before naming the unit |
| `0x6515` | 1 byte | circulation pump output |
| `0x0842` | 1 byte | internal extension relay K12 |
| `0x089D` | 1 byte | room-temperature sensor HK2 status; low priority because local M2 path is absent |

## Already known; do not duplicate as new discoveries

The following are intentionally excluded from this backlog because local hardware evidence already exists or they are actively documented elsewhere:

`0x0810`, `0x2544`, `0x555A`, `0x55D3`, `0x55DD`, `0x7660`, `0x7663`, `0x0A3A..0x0A3C`, `0x5730`, `0x5731`, `0x0A54`, `0x0A35`, `0x27E5..0x27E9`, `0x676C`, `0x650A`, `0x6513`, `0x0A10`, `0x778C`, `0x778D`, `0x7650`, `0x7656`, GFA P06/P09/P80/P81/P82/P83/P87 and P90/P100-P108.

## Promotion rule

A candidate becomes a normal project datapoint only after:
1. a successful bounded read on the local 20C2 controller;
2. raw value and source conversion are recorded separately;
3. semantics are plausible for the installed hardware;
4. polling frequency is justified;
5. the result is documented in the relevant research file and, if useful, Home Assistant.
