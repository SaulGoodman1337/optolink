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

## B. Newly hardware-verified candidates

The first bounded read-only batch has now been executed successfully.

| Address | Hardware result | Interpretation |
| --- | --- | --- |
| `0x8853` | `02` | source-defined burner type = **modulating**; consistent with the locally observed modulating GFA behavior |
| `0xA403` | `D0 07` = 2000 / 100 = **20.00 °C** | source label `nviHCC1 FlowSetpt`; same-window `0x2544=0.0 °C`, so it is **not** simply a mirror of the internal A1 flow target |
| `0x0A4C` | `00 00 00 00` | A1 pump software-index block empty/zero; consistent with local `E5=0` and no separate A1 KM-BUS pump |
| `0x0A31` | `00` | no KM error code reported for mixer object |
| `0x0A32` | `00` | no KM error code reported for external-extension object |
| `0x0A34` | `00` | no KM error code reported for M2-pump object |
| `0x0A36` | `00` | no KM error code reported for Vitocom object |
| `0x6550` | `00` | no KM error code reported for Vitosolic object |

The zero KM error bytes do **not** prove that optional participants are installed; on this appliance several of those subsystems are known absent.

Same-window thermal context for the A403 comparison:

- `0x2544 = 0000` -> 0.0 °C A1 flow target;
- `0x555A = 3200` -> 5.0 °C effective boiler target;
- `0x0810 = FE01` -> 51.0 °C boiler temperature;
- `0x0816 = 7C01` -> 38.0 °C exhaust temperature.

Machine evidence: [new-readonly-addresses-2026-09-24-evidence.json](../config/optolink-splitter/research/vitosoft/new-readonly-addresses-2026-09-24-evidence.json).

## B1. Remaining genuine read-later candidates

These exact-profile datapoints are still not in the production HA poll definition and remain worth bounded reads.

| Priority | Address | Read | Source meaning | Why it matters |
| --- | --- | --- | --- | --- |
| [x] | `0xA401` | 2 bytes | `nviHCC1 SpaceSetpt` | live `20.00 °C`; differs from configured A1 room target `0x2306=21 °C` |
| [x] | `0xA441` | 2 bytes | `nviHCC2 SpaceSetpt` | live `20.00 °C`; M2 is absent, strong default/inactive control evidence |
| [x] | `0xA443` | 2 bytes | `nviHCC2 FlowSetpt` | live `20.00 °C`; M2 is absent, strong default/inactive control evidence |
| [x] | `0xA3C0` | 2 bytes | `nviDHWC Setpt` | live `50.00 °C`; differs from current/effective `0x6500=5.0 °C`; compare next with configured user target `0x6300` |
| B | `0x0A50` | 4 bytes | M2 pump software-index block | byte 3 is SW index; expected absent/empty in local topology |
| B | `0x0A44` | 4 bytes | mixer software-index block | byte 3 SW index |
| B | `0x0A40` | 4 bytes | solar-controller software-index block | byte 3 SW index |
| B | `0x0A58` | 4 bytes | Vitocom software-index block | byte 3 SW index |
| B | `0x0A5C` | 4 bytes | remote-control A1 software-index block | byte 3 SW index |
| B | `0x0A60` | 4 bytes | remote-control M2 software-index block | byte 3 SW index |

### Viessmann LON protocol resolution

The Viessmann LON handbook now provides the missing protocol semantics:

- `nviHCCxSpaceSet` has a documented 20 C fallback if no fresh network value is received.
- `nviHCCxFlowTSet` likewise uses 20 C as fallback in its applicable LON mode.
- In normal internal/default HCC operation these LON setpoints are not authoritative; internal controller settings apply.
- `nviDHWCSetpt` becomes authoritative only when the DHWC ApplicMode selects the external LON DHW path.

Local hardware follow-up:

```text
0x2306 = 21 C      normal A1 room target
0x2321 =  0 C      explicit external A1 room target
A401   = 20.00 C   nviHCC1 SpaceSetpt

0x6300 = 45 C      configured DHW target
0x6500 =  5.0 C    current/effective DHW target in this idle window
A3C0   = 50.00 C   nviDHWC Setpt
```

Therefore neither A401 nor A3C0 is a direct mirror of the corresponding local controller target.
### Suggested next bounded read-later batch

The direct-mirror questions are now closed. The final LON check is only the current applicability/authority mode:

```bash
echo "=== LON ApplicMode closure ==="
/usr/local/bin/optolink-debug request "r;0xA400;1;raw;False"
/usr/local/bin/optolink-debug request "r;0xA440;1;raw;False"
/usr/local/bin/optolink-debug request "r;0xA3C2;1;raw;False"
```

No writes are involved. The exact catalog exposes these as HCC1, HCC2 and DHWC LON ApplicMode objects. A result representing AUTO/NUL/internal control closes the local LON-setpoint path as inactive. Preserve raw bytes because catalog and handbook terminology differ slightly for 0x00 versus 0xFF, while both non-overriding states leave the corresponding nvi setpoint non-authoritative.

### Live HCC/DHWC classification result

```text
0x2306 = 15       -> 21 °C normal A1 room setpoint
0xA401 = D0 07    -> 20.00 °C nviHCC1 SpaceSetpt

0x2544 = 00 00    -> 0.0 °C current A1 flow target
0xA403 = D0 07    -> 20.00 °C nviHCC1 FlowSetpt

0xA441 = D0 07    -> 20.00 °C nviHCC2 SpaceSetpt
0xA443 = D0 07    -> 20.00 °C nviHCC2 FlowSetpt

0x6500 = 32 00    -> 5.0 °C current/effective DHW target
0xA3C0 = 88 13    -> 50.00 °C nviDHWC Setpt
```

Because the absent M2 HCC objects carry the same 20.00 °C as the A1 HCC objects, the HCC `nvi*` values are strongly consistent with inactive/default LON inputs rather than live internal controller targets.

Follow-up disproved a direct DHW mirror as well: configured `0x6300=45 °C`, current/effective `0x6500=5.0 °C`, while `A3C0=50.00 °C`. Per the Viessmann LON semantics, A3C0 is only authoritative when DHWC ApplicMode explicitly selects the external LON DHW setpoint path.

Machine evidence: [lon-input-classification-2026-09-24-evidence.json](../config/optolink-splitter/research/vitosoft/lon-input-classification-2026-09-24-evidence.json).

### Special note on 0xA403

The exact catalog calls `0xA403` **`nviHCC1 FlowSetpt`**, 2 bytes with `div100` and °C, under `LON Objekte / HCCObjektA1M1`. Hardware now proves it can differ from the internal `0x2544` value: A403 was 20.00 °C while 2544 was 0.0 °C. Treat A403 as a distinct LON/HCC input-side object until a broader correlation proves otherwise.

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
