# WB2A / VDensHO1 research notes

## Current checkpoint — 2026-09-22

The current reverse-engineering state is:

- device/controller: **VDensHO1 / 20C2**, Vitodens 200-W WB2A
- GFA chip ID: `2002061501ff`
- coding plug: **7833971**, revision **2015:0201**
- `0x55DC`: hardware-correlated live modulation command/state in percent
- `0xA305`: same live modulation quantity at 0.5 %/LSB
- `0xA38F`: active CFDM power-state value; byte 0 at 0.5 %/LSB follows `0x55DC` closely after stable flame
- measured burner start:
  - flame establishment around MOD 65-66 %
  - about **12 s** high-modulation hold after flame establishment
  - then approximately **-1 modulation percentage point/s**
  - final heating modulation around **33 %**
- `0x55D3` bytes 6/7 are **not blower rpm**; they are separate GG1/GFA state bytes
- observed GG1/GFA state progression:
  `01/00/00 -> 01/08/20 -> 09/0c/40 -> 09/0f/50 -> 29/0b/60 -> 21/0b/60 -> 21/0b/62`
- byte 7 bit `0x02` appears about 10 s after flame detection, roughly 2.4 s before the sustained modulation ramp; it is a strong regulation/run-substate candidate, but its exact meaning is not proven
- LGM29-specific `0x0083` and conventional `0x5715/1A/1B/1C` mappings were rejected on this WB2A
- coding-plug `GWG73` decodes to **240 s startup optimization**, so it is not the measured ~12 s regulation delay
- coding-plug `GWG32 = 29 % max heating power` and `GWG71 = 29 % burner minimum power`; together with the burner characteristic this explains the observed steady MOD ~33

### Next experiment

The current single-session logger is intentionally focused on:

```text
0x55D3 / 11   GG1/GFA runtime bytes, 55DC, 55DD
0x0810 / 2    boiler actual temperature
```

Goal: correlate unresolved GFA bytes 1 and 2 against the direct boiler
temperature and reject or confirm a thermal/process-value interpretation.

Run after updating:

```bash
update
wb2a-single-session-logger
```

Capture from before burner start until at least 20-30 s after MOD reaches 33 %.

This directory contains hardware-verified and still-open reverse-engineering notes for the Vitodens 200-W WB2A setup used with Optolink-Splitter.

The notes are intentionally split into two layers:

- [device-vdensho1-20c2-wb2a.md](device-vdensho1-20c2-wb2a.md) — controller/device/GFA runtime behavior and live datapoints.
- [coding-plug-7833971-2015-0201.md](coding-plug-7833971-2015-0201.md) — Kesselcodierstecker identity, GWG parameters and burner characteristic.

Related implementation/reference files in the parent directory:

- `vdensho1-20c2-wb2a-service-draft-poll-list.py`
- `vdensho1-20c2-wb2a-homeassistant.py`
- `vcontrol-mapping.md`
- `wb2a-single-session-logger.py`

All current reverse engineering is read-only unless a datapoint is explicitly documented elsewhere as hardware-verified READ/WRITE.


## Logger installation

Existing Optolink-Splitter LXCs install or refresh the single-session WB2A logger through the normal:

```bash
update
```

The helper is installed as:

```text
/usr/local/bin/wb2a-single-session-logger
```

and can be started simply with:

```bash
wb2a-single-session-logger
```
