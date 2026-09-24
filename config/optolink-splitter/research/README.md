# WB2A / VDensHO1 research notes

## Current checkpoint — 2026-09-23

The current reverse-engineering state is:

- device/controller: **VDensHO1 / 20C2**, Vitodens 200-W WB2A
- GFA chip ID: `2002061501ff`
- coding plug: **7833971**, revision **2015:0201**
- `0x55DC`: hardware-correlated live modulation command/state in percent
- `0xA305`: same live modulation quantity at 0.5 %/LSB
- `0xA38F`: active CFDM power-state value; byte 0 at 0.5 %/LSB follows
  `0x55DC` closely after stable flame
- measured burner start:
  - flame establishment around MOD 65-66 %
  - about **12 s** high-modulation hold after flame establishment
  - then approximately **-1 modulation percentage point/s**
  - final heating modulation around **33 %**
- `0x55D3` bytes 6/7 are **not blower rpm**; they are separate GG1/GFA
  runtime-state bytes
- the **real blower-speed datapoint is still open and is an explicit next
  research task**
- observed GG1/GFA state progression:
  `01/00/00 -> 01/08/20 -> 09/0c/40 -> 09/0f/50 -> 29/0b/60 -> 21/0b/60 -> 21/0b/62`
- byte 7 bit `0x02` appears about 10 s after flame detection, roughly 2.4 s
  before the sustained modulation ramp; it is a strong regulation/run-substate
  candidate, but its exact meaning is not proven
- LGM29-specific `0x0083` and conventional `0x5715/1A/1B/1C` mappings were
  rejected on this WB2A
- coding-plug `GWG73` decodes to **240 s startup optimization**; this is
  distinct from the measured ~12 s post-flame regulation transition
- coding-plug `GWG32 = 29 % max heating power` and
  `GWG71 = 29 % burner minimum power`; together with the burner
  characteristic this explains the observed steady MOD ~33
- `0x55E0 byte14 bit0` is strongly verified as the restart/start release
  state:
  - bit0 remains 0 during the nominal ~240 s post-flame restart inhibition;
  - strong thermal demand does not start the burner while bit0 is 0;
  - bit0 changes to 1 immediately before burner startup is allowed;
  - this behavior was reproduced in two controlled cycles
- `0x55E0[10:12]` is strongly supported as the internal startup-optimized
  boiler target (OPT):
  - at restart release it becomes exactly 20 K lower than the normal RKR
    boiler target;
  - it then ramps back toward the normal target
- `A395.b2` is a separate approximately 60 s post-fire state and is not the
  240 s restart-inhibition timer

## Physical coding-plug dump campaign — 2026-09-24

The external read-only path is now proven on the bench with a CH341A/SOIC8
clip and AsProgrammer in 24C04 mode.

The first capture is **spare-1 / chip1**, not the plug currently installed in
the boiler. Three independent 512-byte reads are identical with SHA256
`3dd583723661ea765f4e57405628def121bf78f1bc7d09dc1dfb51fec362f386`.

The representative image contains a 71-byte exact repeated region at
`0x014..0x05A` and `0x066..0x0AC`. It does not contain the current
installed-plug 7833971/2015:0201 search patterns or exact copies of the known
`0x1030..0x1090` objects. Because spare-1's exact identity is still
unrecorded and only one of the two 24C04 packages has been captured, this is
an observation rather than a storage-format conclusion.

Detailed capture registry and raw-file locations:
[coding-plug-physical-dumps.md](coding-plug-physical-dumps.md).

The physical dump correlation now has a stronger architectural result:

- both spare chip1 images contain the same **82-byte logical record twice**;
- the complete `0x000..0x0E1` 226-byte prefix is identical across both
  spares;
- the repository exposes separate GWG/main-regulation coding-plug objects,
  separate GFA coding-plug diagnostics, and separate GFA/GWG revision fields;
- together with the two physically different f01/SIM1 and f02/SIM2 EEPROMs,
  this supports a dual-domain EEPROM hypothesis, but no side is yet assigned;
- the active `0x1030` coding-plug object is eight value/complement pairs,
  proving that controller-visible P300 blocks need not be literal flat EEPROM
  images.

See the detailed cross-correlation section in
[coding-plug-physical-dumps.md](coding-plug-physical-dumps.md).

Spare-2 adds a second repeatable chip1 image with SHA256
`554d890e5c5158893ca44b10e0503f38f8c6de4f01de0fb2b9e55211a3e48946`.
It is **96.0938 % byte-identical** to spare-1: 492 of 512 bytes match and
`0x000..0x0E1` is identical. Differences are concentrated at
`0x0E2..0x0F0`, the 24C04 `0x100` block boundary region, and `0x1FF`.
Spare-2 contains the deliberate-looking pattern
`00 FF 00 FF 00 FF 00 FF A5 5A A5 5A A5 5A A5 5A` at
`0x100..0x10F`.

## Vitosoft production join — 2026-09-23

The complete production Vitosoft data set for the local controller family is
now available and joined.

Key results:

- exact profile: `VDensHO1 / 20C2 / developer version 01.03`;
- Vitosoft datapoint type ID: **60**;
- complete event count: **581**;
- missing low-level access definitions: **0**;
- VDensHO1 events using `KBUS_*` or `KMBUS_*` FCRead/FCWrite: **0**;
- remote identification is exposed through ordinary `Virtual_READ/WRITE`:
  - A1/M1: `0x27A0`
  - M2: `0x37A0`
- measured room temperature remains read-only in Vitosoft:
  - A1/M1: `0x0896`
  - M2: `0x0898`

The old 385-event VDensHO1 export is a filtered/group-oriented view, not the
complete event inventory.

Detailed source extraction:
[vitosoft/full-extraction-2026-09-23.md](vitosoft/full-extraction-2026-09-23.md).

## Current open research tasks

The central cross-chat backlog is maintained in
[../../../docs/project-roadmap.md](../../../docs/project-roadmap.md).

For WB2A reverse engineering, the main open items are:

1. **Find the real blower-speed datapoint.**
   The old `0x55D3[6:7]` rpm interpretation must not be reused.
2. Resolve the remaining `0x55E0 byte14` bitfield semantics, especially the
   additional bits present in `0x43`.
3. Measure a complete uninterrupted OPT ramp and compare its exact timing with
   the coding-plug 240 s startup-optimization parameter.
4. Continue investigation of the approximately 12 s post-flame transition and
   the related GG1/GFA runtime-state bits.
5. Validate the newly added RKR-derived Home Assistant entities over normal
   operation rather than only controlled test cycles.

## Files

This directory contains hardware-verified and still-open reverse-engineering
notes for the Vitodens 200-W WB2A setup used with Optolink-Splitter.

The notes are intentionally split into two layers:

- [device-vdensho1-20c2-wb2a.md](device-vdensho1-20c2-wb2a.md) —
  controller/device/GFA runtime behavior and live datapoints.
- [coding-plug-7833971-2015-0201.md](coding-plug-7833971-2015-0201.md) —
  Kesselcodierstecker identity, GWG parameters and burner characteristic.
- [pump-start-heating-vs-dhw.md](pump-start-heating-vs-dhw.md) —
  read-only comparison of internal-pump setpoints and runtime state during
  space-heating versus domestic-hot-water burner starts.
- [kmbus-optolink-research.md](kmbus-optolink-research.md) —
  canonical protocol research for controller-side KBus/KM-BUS access through
  Optolink, including verified function codes, frame layout, safety rules and
  reproducible read-only experiments.
- [vitotrol-kbus-optolink-emulation.md](vitotrol-kbus-optolink-emulation.md) —
  Vitotrol-specific application of the KM-BUS/Optolink research. The simple
  A0-only emulation hypothesis is hardware-disproved: A0=1 raises BC unless a
  real/emulated KM-BUS slave responds.
- [vitotrol-kmbus-wire-protocol.md](vitotrol-kmbus-wire-protocol.md) —
  byte-level physical Vitotrol/KM-BUS reference reconstructed from two working
  emulator implementations: discovery, identity, PING/PONG, CRC and room-
  temperature records.
- [vitosoft/README.md](vitosoft/README.md) —
  project-owned structured extracts and provenance for Vitosoft-derived
  metadata. The legacy filtered view contains 385 device events; the validated
  production XML join contains **581 VDensHO1 events**. The Vitosoft research
  directory also contains the global KBus write-function analysis showing no
  source-defined raw Vitotrol telegram injection path for VDensHO1.

Protocol helper:

- `tools/kmbus-frame.py` — offline CRC/frame generator for Vitotrol discovery,
  identity, PONG and room-temperature KM-BUS telegrams. It does not transmit.

Related implementation/reference files currently in the parent directory:

- `vdensho1-20c2-wb2a-service-draft-poll-list.py`
- `vdensho1-20c2-wb2a-homeassistant.py`
- `vcontrol-mapping.md`
- `wb2a-single-session-logger.py`
- `wb2a-rkr-cycle-logger.py`

These files are candidates for the controlled repository reorganization
described in [../../../docs/repository-cleanup-plan.md](../../../docs/repository-cleanup-plan.md).

All current reverse engineering is read-only unless a datapoint is explicitly
documented elsewhere as hardware-verified READ/WRITE.

## Logger installation

Existing Optolink-Splitter LXCs install or refresh the WB2A loggers through:

```bash
update
```

Available helpers:

```text
/usr/local/bin/wb2a-single-session-logger
/usr/local/bin/wb2a-rkr-cycle-logger
```

The RKR logger is the primary helper for restart-inhibition/startup-optimization
work; the single-session logger remains useful for focused GG1/GFA runtime
captures.
- [m2-conversion-pump-assessment.md](m2-conversion-pump-assessment.md) —
  assessment of converting the local A1 + DHW topology to a real M2 mixer
  circuit, including implications for internal-pump speed and burner startup.
