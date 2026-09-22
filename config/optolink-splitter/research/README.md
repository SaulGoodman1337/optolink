# WB2A / VDensHO1 research notes

## Current checkpoint — 2026-09-22

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
- [vitotrol-kbus-optolink-emulation.md](vitotrol-kbus-optolink-emulation.md) —
  evidence, protocol-function map, hypotheses and next read-only experiments for
  Vitotrol emulation via Optolink/KBus/KM-BUS.

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
