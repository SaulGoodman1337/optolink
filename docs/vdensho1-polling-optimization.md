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


## Live 150 ms cadence baseline

A passive 180-second MQTT observation was recorded with
`mqtt_no_redundant=False`, `poll_interval=0` and `olbreath=0.15`.

Measured FAST cadence:

| Datapoint | Median | P95 | Max |
|---|---:|---:|---:|
| Kesseltemperatur | 4.763 s | 4.974 s | 5.045 s |
| Brenner Modulationsgrad | 4.745 s | 4.975 s | 5.031 s |
| GFA P06 blower RPM | 4.722 s | 4.958 s | 5.094 s |
| GFA P09 modulation setpoint | 4.732 s | 4.945 s | 5.101 s |
| GFA P87 raw status | 4.713 s | 4.945 s | 4.967 s |

Measured NORMAL cadence:

| Datapoint | Median | P95 | Max |
|---|---:|---:|---:|
| Außentemperatur | 23.949 s | 24.354 s | 24.461 s |
| GFA P80 identity | 23.972 s | 24.401 s | 24.515 s |

This validates the phased scheduler design: FAST values no longer show the
previous 15-20 second latency spikes, and NORMAL cadence is approximately five
FAST cycles as configured.

The next controlled experiment is `olbreath=0.10` with the identical passive
observer and journal-error check. The 150 ms run is the comparison baseline.


## Live 100 ms cadence test

A second passive 180-second observation was recorded after changing only
`olbreath` from 0.15 s to 0.10 s. The phased scheduler and poll profile were
unchanged.

Measured FAST cadence:

| Datapoint | Median | P95 | Max |
|---|---:|---:|---:|
| Kesseltemperatur | 3.541 s | 3.768 s | 3.830 s |
| Brenner Modulationsgrad | 3.542 s | 3.744 s | 3.832 s |
| GFA P06 blower RPM | 3.508 s | 3.720 s | 3.800 s |
| GFA P09 modulation setpoint | 3.514 s | 3.721 s | 3.807 s |
| GFA P87 raw status | 3.496 s | 3.725 s | 3.816 s |

Measured NORMAL cadence:

| Datapoint | Median | P95 | Max |
|---|---:|---:|---:|
| Außentemperatur | 17.517 s | 18.191 s | 18.244 s |
| GFA P80 identity | 17.598 s | 18.226 s | 18.355 s |

No `FF` quarantine, `OL Error`, restart or traceback was observed since the
restart used for this test.

Relative to the 150 ms baseline, median cadence improved by about 26 percent
for P06 and Kesseltemperatur and about 27 percent for Außentemperatur.

Result: **PASS**.

The next controlled step is 50 ms. If that also passes the short gate, perform
a longer soak including at least one burner start before changing the profile
helper's permanent timing from the conservative 150 ms setting.


## Live 50 ms cadence test

A third passive 180-second observation was recorded after changing only
`olbreath` from 0.10 s to 0.05 s.

Measured FAST cadence improved substantially:

| Datapoint | Median | P95 | Max |
|---|---:|---:|---:|
| Kesseltemperatur | 2.134 s | 2.341 s | 2.428 s |
| Brenner Modulationsgrad | 2.152 s | 2.303 s | 2.390 s |
| GFA P06 blower RPM | 2.128 s | 2.334 s | 2.404 s |
| GFA P09 modulation setpoint | 2.137 s | 2.323 s | 4.151 s |
| GFA P87 raw status | 2.129 s | 2.307 s | 2.439 s |

Measured NORMAL cadence was about 10.6 s.

However, the journal recorded one GFA P09 transport failure during the test:

```text
GFA_READ 0x4009 returned FF; quarantined
OL Error do_poll_item 16, Addr 4009, RetCode 255, Data ?
```

The P09 maximum interval of 4.151 s is consistent with one missed FAST poll.

The test gate therefore failed and the test script automatically restored
`olbreath=0.10`.

Result: **FAIL for production use at 50 ms**.

This single event does not prove that 50 ms is the sole physical cause, but it
is sufficient to reject 50 ms as the current production setting. The fastest
clean tested value remains 100 ms. A longer 100 ms soak including a burner
cycle should be completed before optionally exploring an intermediate 75 ms
setting.


## 30 minute 100 ms soak

A 30-minute passive soak was run at `olbreath=0.10`.

Measured FAST cadence remained fast and tightly grouped:

| Datapoint | Median | P95 | Max |
|---|---:|---:|---:|
| Kesseltemperatur | 3.399 s | 3.577 s | 6.774 s |
| Brenner Modulationsgrad | 3.393 s | 3.603 s | 6.821 s |
| GFA P06 blower RPM | 3.413 s | 3.584 s | 6.769 s |
| GFA P09 modulation setpoint | 3.414 s | 3.576 s | 6.769 s |
| GFA P87 raw status | 3.419 s | 3.599 s | 6.775 s |

NORMAL cadence was about 17.0-17.1 s median.

However, at 14:55:38 the journal recorded:

```text
GFA_READ 0x4057 returned FF; quarantined
OL Error do_poll_item 17, Addr 4057, RetCode 255, Data ?
```

This is a different GFA address from the earlier 50 ms failure
(`P09 / 0x4009`) and shows the same transport symptom. The roughly 6.77 s
maximum FAST interval is consistent with one missed approximately 3.4 s cycle.

Result: **FAIL for production use at 100 ms**.

The 100 ms short test was therefore not long enough to establish stability.
The repeated FF pattern at shorter reply-to-next-request spacing strengthens
the timing-margin hypothesis, but it does not yet prove that `olbreath` is
the sole cause. A long 150 ms baseline is required before drawing that stronger
conclusion.

Current conservative production target remains 150 ms. If a long 150 ms soak
is clean, 125 ms may be tested as an optional intermediate value.


## GFA-specific pacing and FF retry experiment

The 50 ms and 100 ms failures observed so far were both isolated direct
`GFA_READ 0x6B` acquisitions:

- 50 ms: P09 / 0x4009 returned raw FF;
- 100 ms long soak: P87 / 0x4057 returned raw FF.

No equivalent F7/F4 error was observed in those timing gates. This motivates
decoupling the ordinary VS1 timing from the direct GFA timing instead of
slowing the entire poll loop.

GFA patch helper v1.0.4 therefore adds:

```text
global olbreath:                 independent
GFA_MIN_GAP_SECONDS:             0.15
raw GFA FF:                      one retry
second FF / failed retry:        quarantine and return failure
```

The GFA minimum gap is measured from the VS1 module's `last_comm` timestamp,
which is updated by successful VS1 responses. Therefore a global 50 ms
`olbreath` only incurs the extra delay required to reach the 150 ms GFA
minimum; ordinary F7/F4 traffic remains at the global timing.

The existing FF quarantine remains intact. A raw FF is never converted into a
physical value. A successful retry is returned normally; a second FF remains
quarantined.

Implementation commit:
`06a963948ddbfcca13164ea9c00e8c1a4d2de053`.

This is an experimental timing optimization and still requires live validation
with global `olbreath=0.05`.


## Mixed 50 ms global / 150 ms GFA short gate

The GFA-specific pacing patch v1.0.4 was applied and tested with:

```text
global olbreath = 0.05 s
GFA_MIN_GAP_SECONDS = 0.15 s
raw GFA FF retry count = 1
```

Only `optolinkvs1.py` changed during the upgrade; the adapter and
`requests_util.py` were already current.

The 180-second passive cadence gate produced:

| Datapoint | Median | P95 | Max |
|---|---:|---:|---:|
| Kesseltemperatur | 2.480 s | 2.750 s | 2.839 s |
| Brenner Modulationsgrad | 2.493 s | 2.761 s | 2.883 s |
| GFA P06 blower RPM | 2.483 s | 2.692 s | 2.756 s |
| GFA P09 modulation setpoint | 2.480 s | 2.706 s | 2.769 s |
| GFA P87 raw status | 2.470 s | 2.709 s | 2.767 s |
| Außentemperatur | 12.416 s | 12.992 s | 13.016 s |
| GFA P80 identity | 12.491 s | 12.943 s | 13.155 s |

Retry telemetry:

```text
GFA_FIRST_FF=0
GFA_RETRY_RECOVERED=0
HARD_ERRORS=none
P80_OK=1
SERVICE_OK=1
RESULT=PASS_CLEAN
```

This is the first clean gate combining the upstream 50 ms timing for ordinary
VS1 traffic with a separate 150 ms minimum gap for direct GFA_READ 0x6B.

The result strongly supports the hypothesis that the shorter-timing failures
are specific to the GFA_READ path rather than VS1/F7/F4 generally. It is not
yet sufficient for permanent deployment because the retry path was not
exercised and the short gate lasted only three minutes.

Next gate: 30-60 minute soak including normal burner activity, while counting
first-attempt FF events, successful retry recoveries, second FF/failures and
splitter restarts separately.


## Fast-first 25 ms GFA short gate

The experimental GFA patch v1.0.5 was tested with:

```text
global olbreath = 0.025 s
GFA first-attempt gap = 0.025 s
GFA retry gap = 0.150 s
raw GFA FF retry count = 1
```

The 180-second passive cadence gate produced:

| Datapoint | Median | P95 | Max |
|---|---:|---:|---:|
| Kesseltemperatur | 1.477 s | 1.625 s | 1.691 s |
| Brenner Modulationsgrad | 1.485 s | 1.617 s | 1.681 s |
| GFA P06 blower RPM | 1.482 s | 1.620 s | 1.751 s |
| GFA P09 modulation setpoint | 1.488 s | 1.655 s | 1.747 s |
| GFA P87 raw status | 1.492 s | 1.592 s | 1.706 s |
| Außentemperatur | 7.424 s | 7.602 s | 7.709 s |
| GFA P80 identity | 7.393 s | 7.699 s | 7.781 s |

Retry/error telemetry:

```text
GFA_FAST_FIRST_FF=0
GFA_RETRY_RECOVERED=0
P80_OK=1
SERVICE_OK=1
HARD_ERRORS=none
RESULT=PASS_CLEAN
```

This is about 69 percent faster in FAST median cadence than the original
approximately 4.72 s 150 ms global baseline. It is also materially faster than
the approximately 1.88 s median measured with global 25 ms but a 150 ms GFA
first-attempt gap.

No FF occurred in this short gate, so the conservative 150 ms retry path was
not exercised during this run. A 30-60 minute soak including burner activity
is required before making this configuration permanent.
