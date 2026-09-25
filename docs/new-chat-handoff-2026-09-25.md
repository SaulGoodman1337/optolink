# New-chat handoff - WB2A / Optolink / burner-dependent A1 pump research - 2026-09-25

Use the following state as the authoritative starting point in a replacement
chat. Newer evidence in this file and in
`docs/research-checkpoint-2026-09-25.md` supersedes older intermediate pump
interpretations.

## Project / local plant

We continue the project **Homeassistant und optolink-splitter**.

Local appliance:

- Viessmann Vitodens 200-W WB2A
- controller profile: VDensHO1
- identification: 20C2
- regulation software pair: 0103
- production protocol: permanent VS1/KW
- `vs1protocol=True`
- `port_vitoconnect=None`
- stable CP2102 by-id Optolink device
- production `olbreath=0.025 s`

GFA P80/P06/P09/P87 access works in permanent VS1.

Remote access to the LXC `optolink-splitter` works through Remote Desktop
Commander. Remote user: `chatgpt-admin`. sudo is intentionally restricted;
do not broaden privileges unless truly required.

At the final verification on 2026-09-25 13:27 CEST:

- E7 = 30 % (`0x27E7=0x1E`)
- A1 runtime = 30 % (`0x7663=01 1E`)
- flame off
- no experimental helper process running
- all production services active:
  - `optolink-splitter.service`
  - `optolink-party-emulator.service`
  - `optolink-maintenance-api.service`
  - `optolink-schedule-manager.service`

## Mandatory safety boundaries

- default read-only
- no broad address sweeps
- no KBus/KMBUS writes
- no burner-safety writes
- a successful function code is not semantic proof
- RAM does not automatically mean MCU RAM
- EEPROM does not automatically mean physical coding-plug EEPROM
- do not transfer GWG/LGM27/legacy regulator semantics to VDensHO1 without proof
- after any P300 maintenance window, restore and verify Splitter, Party,
  Schedule Manager and permanent VS1
- do not implement burner-triggered E7 writes as a production solution
- do not repurpose CFDM production commands or relay-test functions as a
  pump-speed solution

## Critical pump-role correction

Earlier work temporarily over-coupled direct-A1 heating with the generic
internal-pump result surfaces. That causal model is superseded.

The integrated physical KM-BUS pump has multiple logical roles.

### Direct A1 heating

In the local direct heating circuit without mixer, the integrated pump acts as
the **A1 heating-circuit pump**.

Source-backed controls:

- E6 / `0x27E6`: maximum regulated A1/M1 pump speed
- E7 / `0x27E7`: minimum regulated A1/M1 pump speed
- `0x7663`: direct A1 heating-circuit pump runtime/output

### DHW/storage heating

During DHW the A1 heating-circuit path is withdrawn and the same physical pump
is used in the boiler/DHW circulation role.

Source-backed control:

- 6C / `0x676C`: internal-pump speed during DHW

Local 6C = 100 %. This explains why the physical integrated pump runs at
100 % during DHW while the A1 runtime surface is 0.

### Boiler-circuit role

K31 / `0x5731` belongs to the internal-pump/boiler-circuit role such as
hydraulic-separation/mixer topologies. It must not be treated as the normal
direct-A1 speed setting.

### 0x0A3C / 0x7660

`0x0A3C` is a genuine VDensHO1 service result named
`InternePumpeDrehzahl_res`; raw metadata places it in the VDensHO1
Information/Diagnose boiler groups.

`0x7660` is an internal-pump runtime surface.

Their measured correlations remain valid observations, but they are **not**
proof that direct-A1 control is implemented as
`0x7663 -> clamp -> 0x0A3C -> 0x7660`.

## Actual current research target

Find whether VDensHO1/20C2 contains a **volatile burner-dependent A1 pump
boost/override** that raises the direct A1 heating-circuit pump during burner
operation without persistent E7 rewrites.

This is the desired function class:

~~~text
normal A1 heating:
E7-derived A1 pump speed, e.g. ~30 %

burner starts:
internal volatile override -> A1 pump higher / possibly 100 %

burner stops:
return to normal A1 regulation
~~~

Repeated Home Assistant writes of E7 on every burner start/stop are rejected
as the production design. E7 is a coding/configuration surface; storage
endurance for per-cycle writes is not established.

## Historical Viessmann evidence: function class exists

The verified Vitosoft-v6 archive contains explicit burner-dependent pump
concepts in other regulator families:

- `0x571D K1D_KonfiPumpenbeiBrennerein`:
  "Beimischpumpe EIN, wenn Brenner EIN"
- `0x581D SR13_K1D_KonfiPumpenbeiBrennerein`
- legacy gas coding-card `0x1070`, byte 5:
  "Pumpe bei Brennerbetrieb"
- corresponding NRx `0x1080`, byte 5
- later `0x7751 K51_KonfiHydrWeicheIntPumpe`

None belongs to an exact VDensHO1 EventTypeGroup.

Local `0x571D` and `0x581D` were already invalid-address.

Important semantic boundary: on VDensHO1 the same `0x1070` byte-5 position is
explicitly **GWG75 = Mindestdrehzahl Interne Pumpe**. Do not transfer the
legacy "Pumpe bei Brennerbetrieb" meaning to WB2A.

Private archive traces:

- burner/pump semantic trace:
  - workflow commit `5a38c5bc7655426d112a5dc7ae967c41b0eadfff`
  - run `36123710024`
  - artifact `10859205686`
- exact VDensHO1 burner-pump candidates:
  - workflow commit `ace35d303018604e1ac5e696614398d5a2c9c86c`
  - run `36124347409`
  - artifact `10859586607`

## Natural burner/A1 runtime experiment - decisive read-only result

Evidence:

`config/optolink-splitter/research/vitosoft/burner-a1-runtime-2026-09-25-evidence.json`

Raw CSV on appliance:

`/home/chatgpt-admin/wb2a-burner-a1-runtime-20260925-124401.csv`

Watcher:

`config/optolink-splitter/wb2a-burner-a1-runtime-watch.py`

Self-test:

`BURNER_A1_RUNTIME_WATCH_TESTS=5/5`

The run captured two complete natural direct-A1 burner cycles with **no
writes**, E7=30.

### Heating activation

DHW-only idle:

~~~text
12:44:03
A152=0400
HKP1=0
internal-pump relay=0
UV heating=0
UV DHW=1
A1=0 %
flame=0
~~~

After switching to heating + DHW:

~~~text
12:46:10
A1 becomes active at 32 %

12:46:12
A152=b020
HKP1=1
internal-pump relay=1
UV heating=1
UV DHW=0
A1=32 %
flame=0
~~~

The heating pump/hydraulic state therefore becomes active several minutes
before burner startup.

### Cycle 1

~~~text
GFA/mod start  12:50:58.755
flame on       12:51:07.750
flame off      12:51:35.366
flame duration 27.616 s
~~~

### Cycle 2

~~~text
GFA/mod start  12:55:35.156
flame on       12:55:44.375
flame off      12:56:12.223
flame duration 27.848 s
~~~

### Key invariant

Across prestart, flame-on, flame-off and the inter-cycle wait:

~~~text
A1 speed = 32 %
0x0A3A = 0
A1 mode = 0x02
HKP1 relay = 1
internal-pump relay = 1
UV heating = 1
UV DHW = 0
~~~

There is **no visible burner-dependent A1 speed boost** in the active local
configuration.

This is strong negative runtime evidence, but it does not prove that no
dormant firmware path exists.

## VDensHO1 runtime-state surfaces decoded

### 0xA152 nvoRelayState

Raw Vitosoft EventType metadata uses MSB-first bit numbering.

Relevant bits:

- bit 2: internal pump
- bit 3: diverter/heating
- bit 5: diverter/DHW
- bit 6: burner
- bit 10: HKP1

Metadata trace:

- workflow commit `53beef8abdddcccd2548af55341985d7a90e982c`
- run `36125220363`
- artifact `10859906815`

Local finding:

- HKP1/internal-pump/heating-diverter bits track the heating hydraulic state
- the source-labelled burner bit remains **0** even while independent flame
  signals are 1

Therefore that LON relay bit is not the local GFA burner-request/output path on
this installation.

### 0xA305 nvoBoilerState_BLR_value

Vitosoft source name: `Modulationsgrad`.

Local behavior:

- stays 0 during pre-flame GFA/modulation startup
- becomes nonzero with established flame
- follows burner modulation closely
- returns to 0 at or just before flame extinction

It is useful burner-output telemetry, not an independent pre-flame
burner-demand flag.

## Startup / takt timing correlations

Measured:

~~~text
cycle1 flame off -> cycle2 GFA start = 239.790 s
cycle1 flame off -> cycle2 flame on  = 249.009 s
GFA start -> flame on                 =   9.219 s
~~~

Local coding-plug fields:

- GWG65 = `Brennermindestpausenzeit` = 4 min
- GWG73 = `Anfahroptimierung modulierender Brenner` = 240 s

Both are numerically compatible with a ~240 s interval. Do **not** assign the
measured interval uniquely to GWG65 or GWG73 yet.

`0x555A / Kesselsoll_eff` reproducibly changed:

~~~text
38 °C -> 18 °C
~~~

immediately before both burner starts.

The exact 20 K difference matches local:

- GWG72 = `Offset modulierender Brenner` = 20 K

This is strong numeric/temporal correlation, not yet causal firmware proof.

## Controlled E7=100 experiment - what it did and did not prove

A user-authorized bounded test temporarily changed only:

~~~text
E7 30 -> 100 -> 30
~~~

with safe readback/restore.

Immediate observation:

- A1 runtime moved to 100 %
- high-flow heating allowed a much longer burner run

However several radiators were opened at the same time, so the longer burner
runtime cannot be attributed to E7 alone.

The experiment is useful only as proof that E7 controls the direct-A1 pump
path and as a high-flow reference state.

E7 was safely restored to 30 %. Do not use per-burner E7 rewriting in
production.

Evidence:

`config/optolink-splitter/research/vitosoft/e7-100-heating-cycle-2026-09-25-evidence.json`

## Exhausted exposed control surfaces

### Exact VDensHO1 LON nvi trace

12 exact `nvi*` inputs were recovered, belonging to CFDM, HCC1/HCC2 and
DHWC.

Noteworthy CFDM objects:

- `0xA380 nviCFDMProdCmd`
- `0xA382 nviCFDMApplicMode`
- `0xA383 nviCFDMSetpoint`

CFDM is a heat-production demand interface, **not** a source-backed A1
pump-speed interface.

No exact VDensHO1 `nvi*` pump-speed command exists.

Run `36127098381`, workflow commit
`024cbaafb26ca9eaadf69dfc4d4f39f3ca01322f`.

### Exact VDensHO1 pump write surfaces

Recovered result:

- `0x7663` A1 runtime: read-only
- `0x0A3A` A1 result: read-only
- `0x7660`, `0x0A3C`: read-only
- E6/E7/E8/E9: coding/configuration Virtual_WRITE
- K30/K31/K32/K34/6C: coding/configuration
- `0x7500 RelaistestGWG200x`: diagnostic actuator/test surface, not a normal
  A1 speed regulation command
- no dedicated volatile A1 speed command exists in exact VDensHO1 metadata

Run `36127320074`, workflow commit
`85e4603854cb12902c81a5bd4ef2171cf8719149`.

### Global KBus pump-write scan

Global KBus write function counts:

- DIRECT_WRITE: 11
- EEPROM_LT_WRITE: 495
- GATEWAY_WRITE: 1
- INDIRECT_WRITE: 97
- MEMBERLIST_WRITE: 2
- TRANSPARENT_WRITE: 853
- VIRTUAL_WRITE: 124

Only one pump-semantic KBus write event exists:

~~~text
0x4301
KBUS_Kessel_Beimischpumpe_nach_KTS_RTS
KBUS_VIRTUAL_WRITE
Dekamatik_E/M1/M2/M2_3 only
~~~

No VDensHO1/HO1 KBus pump-speed write event exists.

Run `36127576729`, workflow commit
`ffc9070c8ff2b10dd8027364497751d7fd43d2a6`.

### Current conclusion

The recovered Vitosoft-exposed:

1. service/runtime layer,
2. LON input layer,
3. KBus/KMBUS write layer

contain **no source-backed volatile direct-A1 pump-speed override for
VDensHO1**.

The research boundary is now regulation firmware / MCU, plus the independent
physical coding-plug EEPROM path.

## KM-BUS / P300 current state

### 0x41 KMBUS_RAM_READ

Locally implemented. On seven tested known addresses it matched ordinary
Virtual_READ, including dynamic values.

Use only for bounded known-address correlations. Do not call it MCU RAM without
MCU proof.

### 0x31 XRAM_READ

All six source-derived GWG shapes failed locally with valid Error Message
payload `05`. Closed unless new source evidence appears.

### 0x43 KMBUS_EEPROM_READ

PrefixRead is not part of ordinary 0x43 host serialization in Vitosoft v6.
Bounded 0x03-vs-0x43 comparison found no distinct local data view on tested
addresses.

No further 0x43 live work without a new source-backed discriminator.

### 0x5F KBUS_VIRTUAL_READ

Two strong source-backed semantic anchors were tested and rejected with stable
Error Message payload `05`. Closed.

### 0x5D KBUS_MEMBERLIST_READ

The sole source-defined shape `0x5D/0x0000/3` was tested three times and
returned stable Error Message payload `05`. Closed.

### 0x55 KBUS_TRANSPARENT_READ

Do not live-probe. The 850 catalog rows require PrefixRead for semantic
selection, but the current v6 standard non-RPC host serializer does not put
PrefixRead on the wire. The 850 rows collapse to only 11 standard request
shapes without it.

### Other extended KBus families

`0x59/0x63/0x61/0x51` are legacy-only and lack a VDensHO1 discriminator.
`0x53/0x57/0x65` have no source read-event rows.

There is currently no justified next live Extended-KBus probe.

Canonical KBus docs:

- `config/optolink-splitter/research/kmbus-optolink-research.md`
- `config/optolink-splitter/research/vitosoft/kmbus-read-memory-analysis-2026-09-24.md`
- GitHub Issue #30

## Coding-plug physical/software correlation

This is the next independent evidence path when the EEPROM reader is available.

Known physical state:

- two spare coding plugs
- two 24C04-class EEPROM sides per board
- previous repeatable 512-byte chip1 dumps
- two spare chip1 images share identical 226-byte prefix and an exact duplicated
  82-byte logical record

Known controller-visible identity:

- `0x7656 = P80|P101|P107|P102 = 20 15 02 01`
- `0x1040[0:2] = P107|P101 = 02 15`
- exact VDensHO1 catalog order:
  - byte0 P80 type = 20
  - byte1 P101 identification = 15
  - byte2 P107 GWG revision = 02
  - byte3 P102 GFA revision = 01
- GWG date slots in `0x1020[2:5]` are FF FF FF
- GFA P103-P105 = 14 0C 04; treat as separate data

When the reader is available:

1. label sides explicitly `f01/ST` and `f02/Microchip`
2. read both EEPROMs of one spare 3x each
3. compare repeatability and SHA256
4. repeat second spare where practical
5. active coding plug last, boiler unpowered and plug disconnected
6. **never write**

The hypothesis "one EEPROM GWG/regulation, other GFA/fire-control" remains
unproven until side-specific physical evidence exists.

## PCB / firmware boundary

GitHub Issue #25 tracks the regulation-board / MCU work.

Important identity boundary:

- researched 7424735 / VBC130 board is comparison material only
- public evidence associates that board with WB2B/VBC130
- local plant is WB2A/VDensHO1/20C2
- do not transfer MCU/board identity until local hardware photos prove it

Next hardware work:

- photograph actual installed WB2A regulation PCB at high resolution
- identify local board number/revision
- identify regulation MCU
- identify external memories
- document X15, X10 and X3/145/KM-BUS areas
- identify daughterboard and burner/GFA MCU separately
- only then assess a non-destructive firmware read path
- never erase/unlock production hardware

## Current priority order

1. **Tonight / when available:** read both coding-plug EEPROM sides
   repeatedly, hash, label, compare; no writes.
2. **Local PCB photos:** prove regulation-board/MCU/memory identity.
3. **Firmware research:** continue the burner-dependent A1 pump-boost search
   inside the regulation firmware after MCU/board identity is known.
4. Treat `0x555A` 38->18 °C, GWG72=20 K and the ~240 s
   GWG65/GWG73 timing as firmware-correlation leads, not yet causal facts.
5. Do not repeat already exhausted Vitosoft service/LON/KBus pump-command
   searches unless new source material creates a concrete discriminator.
6. Keep production and Home Assistant stable; no experimental write path.

## Important files to read first in the next chat

- `docs/research-plan-2026-09-24.md`
- `docs/research-checkpoint-2026-09-25.md`
- `docs/new-chat-handoff-2026-09-25.md`
- `config/optolink-splitter/research/pump-start-heating-vs-dhw.md`
- `config/optolink-splitter/research/vitosoft/burner-a1-runtime-2026-09-25-evidence.json`
- `config/optolink-splitter/research/vitosoft/e7-100-heating-cycle-2026-09-25-evidence.json`
- `config/optolink-splitter/research/kmbus-optolink-research.md`
- `config/optolink-splitter/research/vitosoft/kmbus-read-memory-analysis-2026-09-24.md`
- GitHub Issue #25
- GitHub Issue #30

## Working discipline for the replacement chat

Before proposing a new live request, first classify it as:

- source-backed read-only;
- bounded controlled write with explicit restore;
- or unsupported speculation.

Prefer offline/private Vitosoft analysis before live probing.

For every new finding document:

1. raw evidence;
2. exact address/event/function;
3. evidence type: metadata / host implementation / hardware observation /
   hypothesis;
4. interpretation and uncertainty boundary;
5. service/controller restore status if anything was changed;
6. commit IDs and evidence paths.

Do not reopen superseded pump interpretations from older notes.
