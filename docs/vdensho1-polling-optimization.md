# VDensHO1 polling optimization

Status: LIVE PASS on the validated WB2A / VDensHO1 / 20C2 installation.

## Why this is needed

The old polling profile used cycle groups like this:

- FAST = every cycle
- NORMAL = every 15 cycles
- SLOW = every 150 cycles
- RARE = every 900 cycles
- ONCE = cycle 0

The upstream scheduler evaluated every member of a due group in the same cycle.
That produced bursty latency:

- ordinary FAST cycles were comparatively short;
- every NORMAL/SLOW/RARE boundary added many extra serial requests to one cycle;
- a FAST datapoint could therefore occasionally take much longer to reappear
  even though it remained assigned to FAST.

Live observation matched this behavior: outdoor temperature normally arrived
about every 7 seconds but one interval reached about 17 seconds.

The previous GFA identity guard also had a separate latency corner case: a
transient P80 read failure could suppress P06/P09/P87 until the next P80 read.
That guard behavior is fixed independently in the GFA patch helper v1.0.3.

## Poll-load audit

Before rebalancing, the active profile contained approximately:

| Group | Logical poll items | Approx. serial transactions |
|---|---:|---:|
| FAST | 33 | 32 |
| NORMAL | 22 | 21 |
| SLOW | 37 | 36 |
| RARE | 55 | 55 |
| ONCE | 68 | 22 |

The lower ONCE transaction count is because many coding-plug bit filters reuse
one shared block read.

## New profile

The optimized profile uses:

```text
poll_interval = 0
ONCE  = 0
FAST  = 1
NORMAL = 5
DIAG  = 15
SLOW  = 150
RARE  = 900
```

With the reclassified datapoints:

| Group | Logical items | Approx. serial transactions |
|---|---:|---:|
| FAST | 21 | 20 |
| NORMAL | 19 | 19 |
| DIAG | 10 | 9 |
| SLOW | 12 | 12 |
| RARE | 34 | 34 |
| ONCE | 119 | 74 |

Important policy changes:

- process values needed for burner/pump/GFA visualization stay FAST;
- outdoor temperature is NORMAL rather than FAST;
- user setpoints and operating selections are NORMAL because a write already
  gets an explicit forced readback;
- internal BLR/CFDM diagnostics move to DIAG;
- sensor/EEPROM health values move to SLOW;
- service/coding configuration moves to ONCE because it is effectively static
  and writable controls already get forced readback;
- read-only weekly schedules move to ONCE;
- counters and error histories remain RARE.

## Phased scheduler

The local scheduler patch changes recurring group execution from burst to
phased operation.

For a period N, different physical transactions of that group get different
cycle phases. Example: 19 NORMAL transactions with NORMAL=5 are spread roughly
four per cycle rather than all 19 running together every fifth cycle.

Startup remains intentionally different: the first process-start cycle reads a
complete initial snapshot so Home Assistant is populated after restart.

## True ONCE semantics

ONCE is now process-start-only:

- it runs during the initial process-start snapshot;
- after that first completed cycle the ONCE group is disabled in memory;
- `forcepoll` refreshes all recurring groups but not completed ONCE items;
- `reloadpoll` preserves the completed-ONCE state;
- a full systemd/process restart runs ONCE again;
- explicit forced readback of a particular datapoint after a write remains
  possible.

This specifically prevents expensive coding-plug/startup values from being
re-read by routine refresh commands.

## Expected cadence before lowering olbreath

Keep `olbreath=0.15` initially.

With roughly 20 FAST transport requests plus a few phased background requests,
the target is a stable FAST cadence of approximately 4-6 seconds rather than
7 seconds with occasional 15-20 second spikes.

NORMAL should land roughly around 20-30 seconds. Exact times remain transport
dependent, so live MQTT timestamps are authoritative.

Only after this scheduler/profile optimization is stable should olbreath be
reduced experimentally, e.g. 0.15 -> 0.10 and then possibly 0.05, while
measuring FF quarantine events, Optolink errors, restarts and actual P06/F7
latency.

## Implementation

- phased scheduler patch:
  `tools/optolink-apply-phased-poll-scheduler-patch.py`
- optimized profile:
  `config/optolink-splitter/vdensho1-20c2-wb2a-homeassistant.py`
- updater-safe activation:
  `tools/optolink-apply-vdensho1-ha-profile.sh`

Prepared commits:

- phased scheduler patch: `3856d5afa1c652ee8383f72214ae0c49dfea3574`
- polling profile rebalance: `ee783069077ffd690c6411b0f12de3e0cffc2b72`
- profile helper integration: `38ee1a07a00978ebb20219c095f9a0f4b5496dc4`


## Live activation result

The corrected deployment completed successfully on 2026-09-24.

Observed:

```text
VS1_GFA_READONLY_PATCH_TESTS=9/9
PHASED_POLL_SCHEDULER_TESTS=4/4
Patcher preflight OK.
PATCHED_FILES=c_polllist.py,optolinkvs2_switch.py
RESULT=PASS
Discovery dry-run OK.
Party emulation service is active.
294 entities published successfully.
MQTT state refresh triggered.
```

The phased scheduler is therefore active in production while `olbreath`
remains at the conservative 0.15 s baseline. The next step is observation of
actual FAST/NORMAL cadence and communication error rate before any timing
reduction.
