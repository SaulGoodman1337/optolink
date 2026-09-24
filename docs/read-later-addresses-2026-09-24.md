# WB2A / VDensHO1 read-later address register - 2026-09-24

Status: **audited against the current production Home Assistant profile**

Purpose: distinguish three different things that had previously been mixed together:

1. useful values that are **already polled** and therefore can be used in Home Assistant without additional Optolink traffic;
2. source-backed addresses that are **genuinely not integrated yet** and are worth a later bounded read;
3. source-defined values that should stay deprioritized because the related hardware is absent or its sensor status is invalid.

Source basis:
- exact Vitosoft profile VDensHO1 / 20C2;
- Collector-v6 snapshot `vitosoft-private-archive-20260924-143439.7z`;
- exact generated VDensHO1 catalog for length/conversion cross-check;
- current `vdensho1-20c2-wb2a-homeassistant.py` production poll definition.

## A. Already polled - no additional bus traffic required

These were initially rediscovered from the exact catalog, but the production profile audit shows that they are already active.

| Address | Current poll | Meaning | Conversion / role |
| --- | --- | --- | --- |
| `0x0816` | NORMAL | **Abgastemperatur** | 2 bytes, /10 °C |
| `0x5527` | SLOW | gedämpfte Aussentemperatur | 2 bytes, /10 °C |
| `0xA305` | FAST | boiler-state modulation value | 1 byte, /2 % |
| `0x0883` | FAST | Warmwasser FlowSwitch | binary |
| `0x083A` | SLOW | ATS sensor status | diagnostic enum |
| `0x083B` | SLOW | KTS sensor status | diagnostic enum |
| `0x083D` | SLOW | STS2 sensor status | diagnostic enum |
| `0x0840` | SLOW | VTS/VLTS sensor status | diagnostic enum |
| `0x089C` | SLOW | room sensor HK1 status | diagnostic enum |
| `0x6515` | NORMAL | circulation pump output | binary |
| `0x0842` | NORMAL | internal extension relay K12 | binary |
| `0x8851` | ONCE | DHW appliance/construction type | enum |
| `0x0A33` | NORMAL | KM error - separate A1 pump | diagnostic |
| `0x0A35` | NORMAL | KM error - internal pump | diagnostic |

**Consequence:** especially `0x0816` Abgastemperatur does not need a new poll item. Dashboard work should reuse the existing HA entity.

## B. Genuine high-value read-later candidates

These exact-profile datapoints are not currently in the production HA poll definition and are worth a bounded read.

| Priority | Address | Read | Source meaning | Why it matters |
| --- | --- | --- | --- | --- |
| A | `0x8853` | 1 byte | burner type | 0 single-stage, 1 two-stage, 2 modulating; useful identity consistency check |
| A | `0xA403` | 2 bytes | `nviHCC1 FlowSetpt` | /100 °C; separate A1/HCC flow-setpoint view worth comparing with verified `0x2544` |
| A | `0x0A4C` | 4 bytes | A1 pump software-index block | byte 3 is SW index; topology check against E5=0 |
| B | `0x0A50` | 4 bytes | M2 pump software-index block | byte 3 is SW index; expected absent/empty in local topology |
| B | `0x0A31` | 1 byte | KM error - mixer | participant/topology diagnostic |
| B | `0x0A32` | 1 byte | KM error - external extension | participant/topology diagnostic |
| B | `0x0A34` | 1 byte | KM error - M2 pump | participant/topology diagnostic |
| B | `0x0A36` | 1 byte | KM error - Vitocom | participant/topology diagnostic |
| B | `0x6550` | 1 byte | KM error - Vitosolic | participant/topology diagnostic |
| B | `0x0A44` | 4 bytes | mixer software-index block | byte 3 SW index |
| B | `0x0A40` | 4 bytes | solar-controller software-index block | byte 3 SW index |
| B | `0x0A58` | 4 bytes | Vitocom software-index block | byte 3 SW index |
| B | `0x0A5C` | 4 bytes | remote-control A1 software-index block | byte 3 SW index |
| B | `0x0A60` | 4 bytes | remote-control M2 software-index block | byte 3 SW index |

### Suggested first bounded read-later batch

```bash
/usr/local/bin/optolink-debug request "r;0x8853;1;raw;False"
/usr/local/bin/optolink-debug request "r;0xA403;2;raw;False"
/usr/local/bin/optolink-debug request "r;0x0A4C;4;raw;False"
/usr/local/bin/optolink-debug request "r;0x0A31;1;raw;False"
/usr/local/bin/optolink-debug request "r;0x0A32;1;raw;False"
/usr/local/bin/optolink-debug request "r;0x0A34;1;raw;False"
/usr/local/bin/optolink-debug request "r;0x0A36;1;raw;False"
```

This is read-only. Do not promote the addresses to normal polling until local support and usefulness are established.

### Special note on 0xA403

The exact catalog calls `0xA403` **`nviHCC1 FlowSetpt`**, 2 bytes with `div100` and °C. This is not automatically the same semantic object as the already verified A1 flow target `0x2544`. The useful experiment is a same-window read of both values across different heating states.

## C. Coding-plug blocks to preserve for tomorrow's EEPROM correlation

These are already part of the coding-plug research plan but are explicitly kept in the read-later register because the physical EEPROM work is deferred until the new reader arrives:

- `0x10A0 / 16` - GWGA block;
- `0x10B0 / 16` - GWGB block;
- `0x10C0 / 16` - GWGC block;
- together with the already planned `0x1010`, `0x1020`, `0x1030..0x1090`, and `0x7656`.

Capture these immediately before or after the active-plug bench session so the controller-visible state and physical EEPROM images refer to the same plug state.

## D. Conditional / absent-hardware candidates

These remain source-backed but should only be read when their related subsystem matters:

| Address | Meaning | Local reason to deprioritize |
| --- | --- | --- |
| `0x080C` | hydraulic-separator temperature | K52=0, no hydraulic separator |
| `0x3900`, `0x3544`, `0xA443` | M2 temperatures/setpoint | local M2 path absent |
| `0x6564`, `0x6566`, `0x6552` | solar temperatures/pump | solar path absent |
| `0x089D` | room sensor HK2 status | M2 absent |
| `0x0A80` | external request/mode input | external extension absent |
| `0x0A81` | external block input | external extension absent |
| `0x0A82` | extension collective fault | external extension absent |
| `0x0A86` | external 0-10 V input | extension absent; unit/rendering should be verified before exposure |

## E. Do not promote known invalid/default sensor values

The production profile intentionally does **not** poll `0x081A` VTS/VLTS as a real temperature because the corresponding local sensor-status evidence is invalid/open/reference-state. The previously seen 20.0 °C style values are defaults, not a proven physical measurement.

The same evidence rule applies to optional M2/solar/hydraulic-separator temperatures: a plausible number alone does not establish that the sensor exists.

## Already known; do not duplicate as new discoveries

Well-covered local datapoints remain outside this queue:

`0x0810`, `0x2544`, `0x555A`, `0x55D3`, `0x55DD`, `0x7660`, `0x7663`, `0x0A3A..0x0A3C`, `0x5730`, `0x5731`, `0x0A54`, `0x27E5..0x27E9`, `0x676C`, `0x650A`, `0x6513`, `0x0A10`, `0x778C`, `0x778D`, `0x7650`, `0x7656`, GFA P06/P09/P80/P81/P82/P83/P87 and P90/P100-P108.

## Promotion rule

A genuinely new candidate becomes a normal project datapoint only after:
1. a successful bounded read on the local 20C2 controller;
2. raw value and source conversion are recorded separately;
3. semantics are plausible for the installed hardware;
4. polling frequency is justified;
5. the result is documented in the relevant research file and, if useful, Home Assistant.

For already-polled items, do not add a duplicate poll; expose or visualize the existing entity instead.
