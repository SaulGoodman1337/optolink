# WB2A research checkpoint - 2026-09-25

Purpose: **start-of-session checkpoint for the next research day**. This file does not replace
`docs/research-plan-2026-09-24.md`; it records the exact state reached on the evening of
2026-09-24 and the highest-value next actions.

## State at end of 2026-09-24

### LON/HCC/DHWC path - closed locally

The local LON setpoint path is now resolved sufficiently for this appliance:

- `A401/A403/A441/A443 = 20.00 C`;
- Viessmann LON semantics identify 20 C as the HCC nvi fallback/default value;
- `A3C0 = 50.00 C` is not a direct mirror of either local DHW target representation;
- `A400 = FF`, `A440 = FF`, `A3C2 = FF`;
- all three ApplicMode values are `HVAC_NUL`.

Conclusion: HCC1/HCC2/DHWC LON nvi setpoint values are **not authoritative** on the local
controller. Do not expose them in Home Assistant as active local setpoints.

### GFA P84/P87 flame correlation - current state

The permanent-production-VS1 compatibility issue is fixed.

The first real mixed flame-correlation run using v1.0.1:

- verified P300 identity `20C2`;
- verified burner-off precondition `0x55DC=0`;
- verified two independent P80 reads `20/20`;
- captured original `0x2306=21 C`;
- temporarily wrote only `0x2306=37 C`;
- verified the write by readback;
- acquired 32 complete mixed rounds;
- every complete round remained:
  - `P84=00`;
  - `P87=00`;
  - `0x55D3 flame=0`;
  - `0x55DD flame=0`;
  - lockout=0;
  - fine GFA control value=0;
- attempt 33 returned a quarantined raw `FF` at P87;
- exact original setpoint 21 C was restored by readback;
- P300 and services were restored successfully.

This is a **null startup observation**, not a failed heater start. The same 37 C room-setpoint
stimulus had produced a real controller-driven startup earlier in the day, so `0x2306=37`
is now explicitly classified as a **heating-demand stimulus, not a direct burner command**.

v1.0.2 fixes the mixed child so a sporadic GFA `FF`:

1. rejects only the current round;
2. records a quality gap;
3. performs the existing bounded P300/P80 re-identification;
4. clears transition history across the gap;
5. continues only when the inherited safety/time policy permits;
6. reports `STARTUP_ACTIVITY_SEEN=yes|no`.

No trigger/write/restore or burner-safety boundary was loosened.

Evidence:
- `docs/gfa-flame-correlation.md`;
- `config/optolink-splitter/research/vitosoft/gfa-flame-correlation-null-run-2026-09-24-evidence.json`;
- corrected helper: `config/optolink-splitter/wb2a-gfa-flame-correlation-probe.py`.

### Pump/topology state

Current installed topology remains consistent:

- internal KM-BUS pump identity block `0x0A54 = 01 11 01 01`;
- separate A1 pump block `0x0A4C = 00 00 00 00`;
- M2 pump block `0x0A50 = 00 00 00 00`;
- `E5=0`;
- `0x0A3C` is the verified final internal-pump command shadow;
- hidden arbitration upstream of `0x0A3C` remains a controller-firmware/MCU problem.

E9 provenance is closed: the current `E9=100%` was intentionally configured by the user.

## Priority 1 - new EEPROM reader: side-labelled coding-plug capture

The replacement EEPROM reader/programmer is expected on 2026-09-25. Resume physical
coding-plug research only when the new reader is available.

### First capture: both EEPROMs of the SAME spare plug

Explicit physical labels:

- **f01 / SIM1 / ST 24C04W6**;
- **f02 / SIM2 / Microchip 24LC04B**.

Read each side three times without changing the clip between repeat reads.

Recommended filenames:

```text
spare-1-f01-st-read1.bin
spare-1-f01-st-read2.bin
spare-1-f01-st-read3.bin
spare-1-f02-microchip-read1.bin
spare-1-f02-microchip-read2.bin
spare-1-f02-microchip-read3.bin
```

Acceptance before semantic analysis:

- each file must be 512 bytes;
- all three reads of the same EEPROM must hash identically;
- record SHA256 values;
- compare f01 versus f02 of the same physical plug before moving to another plug.

Do not write either EEPROM.

### Then

1. second spare if practical;
2. active plug **last**;
3. boiler unpowered / plug disconnected during active-plug bench read;
4. immediately before or after active-plug capture, snapshot the software-visible coding-plug views:
   - `0x1010`;
   - `0x1020`;
   - `0x1030..0x10C0`;
   - `0x7656`;
   - GFA P90 and P100..P108.

Compare semantic vectors, complement pairs, duplicated records and CRC/integrity patterns rather
than requiring a flat byte-for-byte P300-object match.

## Priority 2 - regulation-board photographs

Photograph the installed WB2A regulation board for firmware/MCU research.

Follow `docs/regulation-board-photo-capture.md`.

Highest-value evidence:

- full board overview;
- PCB part/revision labels;
- both sides where safely accessible;
- main MCU complete marking;
- external EEPROM/flash/SRAM markings;
- oscillator/crystal markings;
- X15;
- X10;
- X3 / 145 KM-BUS area;
- daughterboard;
- burner/GFA-side controller and memory where visible.

Do **not** electrically probe unknown pads yet. First determine the exact local MCU family and
board revision from photographs.

## Priority 3 - flame correlation only when a real burner start is likely

Do not repeatedly write the 37 C stimulus while the controller is clearly thermally satisfied.

First perform a passive readiness snapshot:

```bash
echo "=== Burner-start readiness ==="
/usr/local/bin/optolink-debug request "r;0x55DC;1;raw;False"
/usr/local/bin/optolink-debug request "r;0x2544;2;raw;False"
/usr/local/bin/optolink-debug request "r;0x555A;2;raw;False"
/usr/local/bin/optolink-debug request "r;0x0810;2;raw;False"
/usr/local/bin/optolink-debug request "r;0x7663;2;raw;False"
/usr/local/bin/optolink-debug request "r;0x0A3C;1;raw;False"
```

Useful context:

- `0x55DC`: current burner/modulation state;
- `0x2544`: A1 flow target;
- `0x555A`: effective boiler target;
- `0x0810`: boiler actual temperature;
- `0x7663`: A1 pump/runtime request;
- `0x0A3C`: final internal-pump command.

Only rerun the mixed flame logger when there is a plausible heating demand while the burner is
still off. Use v1.0.2 or later, run its full offline self-test first, and retain both LOG and JSONL.

Target correlation remains:

```text
P84 raw transition
    |
0x55D3 flame
    |
P87 raw / bit transition
    |
0x55DD independent flame signal
```

Do not assign manufacturer names to P84 states or P87 bits solely from temporal proximity.

## Priority 4 - remaining firmware/KM-BUS work

After the physical evidence above:

- continue controller-firmware architecture once local board/MCU identity is known;
- keep regulation firmware, GFA firmware and coding-plug EEPROM as separate domains;
- continue the KMBUS read-memory work only from known source-derived request structures;
- no broad blind reads and no KBUS/KMBUS writes.

## Session completion checklist

Before ending the next session:

- [ ] commit hashes and evidence paths recorded;
- [ ] EEPROM side/vendor labels preserved in filenames;
- [ ] SHA256 repeatability recorded;
- [ ] regulation-board photos indexed by visible component/connector;
- [ ] any flame-correlation run classified as STARTUP_ACTIVITY_SEEN yes/no;
- [ ] no unresolved temporary setpoint remains;
- [ ] production splitter/services confirmed running.
