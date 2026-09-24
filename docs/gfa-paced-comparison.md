# GFA pacing comparison: measured baseline and 150-ms result

Checkpoint: **2026-09-24, including the clean 08:46-08:47 60-second paced run**.

**The 150-ms spacing was achieved on hardware. Two FF replies occurred in 1130 measurement-round reads, versus four in 804 in the preceding approximately 51-ms run. This is a descriptive improvement, not proof of a timing cause or a fix.** Both new FFs were P80 replies. All four runtime channels remained zero throughout the supplied data.

The paced run ended with `RESULT=FAIL` after 288.915 seconds because its second FF left less than the required 15-second reserve for another full re-identification. The first re-identification succeeded. P300 and both previously running services were restored. Do not relabel this as a completed uninterrupted 300-second run, a failed reconnect, a three-reconnect-cap failure, or a burner shutdown.

Both the baseline and paced raw-log/JSONL transcripts are already available in full. **Do not request the same files again. Do not raise retry counts, disable P80, or simply increase duration to obtain PASS.**

Current next action: use the **unchanged** pinned paced helper for **one 60-second observation during naturally already-established burner operation**, with an independent observation of the appliance's flame display. This changes the diagnostic question from idle transport repetition to sustained nonzero runtime behavior. It is not a claim that FF has been solved, and not a full-start experiment.

## 0. Follow-up 60-second paced run: transport PASS, runtime still zero

Input: `Eingefügter Text(20260924-065045).txt`, 163260 bytes, 908 lines, SHA256:

```text
09656062d76931b89cb6bcab9eefd65710ec57c38e8acf16ad116dcb324615e7
```

The supplied combined transcript contains `wb2a-gfa-paced-20260924-084613-187025.log` and `wb2a-gfa-paced-20260924-084613-187025.jsonl`. All 52 JSON records were parsed: metadata, observation start, 49 accepted rounds and one summary.

Result:

```text
OBSERVATION_COMPLETE=yes ACCEPTED_ROUNDS=49 REJECTED_ROUNDS=0 RECONNECTIONS=0
P80_CONFIRMED=0x20 GFA
P300_RESTORED=yes
SPLITTER_RESTARTED=yes
RESULT=PASS
```

This is the first supplied paced 60-second run that completes the full requested window with **zero rejected rounds, zero FF replies and zero reconnects**. The 49 accepted rounds contain exactly 245 measurement-round GFA reads:

```text
P06: 49 x 00
P09: 49 x 00
P10: 49 x 00
P84: 49 x 00
P80: 49 x 20
```

The measured reply-to-next-request gap across those 245 reads is 150.094..156.628 ms, mean 150.289 ms. Mean P06-to-P84 span is 733.932 ms. This is useful evidence that a 60-second paced session can be transport-clean on this hardware; it does **not** prove that 150 ms eliminates FF in longer runs.

The intended operating-state question remains unresolved because all runtime values stayed zero from the first to the last accepted round. The transcript itself has no flame channel. More importantly, the active party emulator was stopped at **08:46:13.385**, while observation started at **08:46:24.181** and the first P06 reply arrived at **08:46:24.564**. Thus 10.796 seconds elapsed before the observation window and 11.179 seconds before the first fan-speed sample. The log itself already warns that pausing the party emulator can change externally maintained requests.

Do not infer either of the following without the user's independent appliance observation:

- that the burner was definitely firing while the 49 zero-valued rounds were acquired;
- that persistent-session GFA runtime reads fail during firing.

The deciding external fact is whether the appliance's own flame display stayed active during the actual 60-second observation. If it extinguished before or near sampling start, the zero series is consistent with idle and does not challenge the earlier firing snapshot. If it remained visibly active, this becomes a new discrepancy requiring targeted investigation.

[Machine-readable 60-second evidence](../config/optolink-splitter/research/vitosoft/gfa-paced-60s-2026-09-24-evidence.json) preserves the exact counts, source hash and timing ambiguity.

## 1. New paced capture: provenance and actual checks

Input: `Eingefügter Text(20260924-063900).txt`, 739554 bytes, 3943 lines, SHA256:

```text
11ef98f6aa02cab31e665bafaf6935ec4ecf72f0b1b8f65b663cfcbd0a2202a6
```

The first line is the user's `cat` of:

```text
wb2a-gfa-paced-20260924-083031-186681.log
wb2a-gfa-paced-20260924-083031-186681.jsonl
```

This is a complete supplied combined transcript, not a direct assistant connection to the LXC. No new appliance command was executed while analyzing it. Its metadata identifies the pacing experiment and pinned dependency hashes, but this upload does not include a preceding download/hash-check/self-test preamble. Do not claim those steps are visible in it.

[Machine-readable paced evidence and comparison](../config/optolink-splitter/research/vitosoft/gfa-paced-run-2026-09-24-evidence.json) preserves source hashes, counts, raw histograms, timing, events, recovery and the original summary.

All **231 JSON records** were parsed: metadata, observation-start, 224 accepted rounds, two rejected rounds, one re-identification start, one completion and one summary. Checks covered:

- accepted numbering 1..224 and attempt numbering 1..226 including rejected attempts;
- register sequence, addresses, raw-hex consistency and raw-to-decoded arithmetic;
- per-sample latency and P06-to-P84 span arithmetic;
- all 224 console ROUND records and their associated raw sample values;
- paired raw GFA request/reply order and exact runtime-byte agreement with JSON;
- exactly two raw FF replies matching the two quarantined rounds;
- null decoded values for rejected rounds;
- recorded reply-gap fields versus neighboring monotonic timestamps wherever directly calculable.

The supplied prior approximately 51-ms transcript was re-parsed using the same counting definition. No proprietary collector binaries, credentials, personal machine inventory or full decompilations were published.

## 2. Exact paced-run result

Observation start: **08:30:42.098 +02:00**, 300 seconds requested.

| Attempt | Channel | FF receive time | Recorded reply gap | Reply latency | Action |
| ---: | --- | --- | ---: | ---: | --- |
| 32 | P80 / 0x4050 | 08:31:21.746 | 150.271 ms | approximately 147.0 ms | Quarantine complete round; full re-identification succeeds. |
| 226 | P80 / 0x4050 | 08:35:30.962 | 150.240 ms | 90.329 ms | Quarantine complete round; insufficient window remains for another re-identification. |

Both exact requests were `6b 40 50 01`. P06/P09/P10/P84 returned 00 before each failed P80 in those same attempts. No runtime FF was received in this particular run; this does not invalidate earlier FF observations on P06/P10/P84.

The first re-identification completed at **08:31:32.886**, with:

```text
P300 00F8/2 = 20c2
independent P80 = 20 / 20
same-session P80 = 20
```

Its duration was **11.088428 seconds**; the gap from the previous accepted-round record to re-entry completion was **12.373900 seconds**. Sampling resumed in segment 2. Segment 1 contains 31 accepted rounds and segment 2 contains 193.

At the second rejection the original observation clock was at **288.915275 seconds**, leaving approximately **11.084725 seconds**. The unchanged quality policy requires at least **15 seconds remaining** before starting another full re-identification. Therefore the terminal message was:

```text
08:35:31.013 OBSERVATION FAILED: Too little observation time remains for a new verified segment.
```

Only one reconnection was attempted in this run. The three-reconnection ceiling was not reached; a second attempt was not started. There is no recorded terminal read timeout, unexpected queued/trailing-byte error or long-host-gap exception.

### Restoration

```text
08:35:33.080 P300 identity = 20c2
08:35:35.157 optolink-splitter.service running
08:35:37.230 optolink-party-emulator.service running
08:35:37.232 RESULT=FAIL
```

The P300 reply is an actual checksum-validated identity response, not merely successful transmission of initialization bytes. Splitter stop to reported running was approximately **303.858 seconds**, including entry, re-identification and final restoration. Requested observation duration is not total service downtime.

`P80_CONFIRMED=NOT_CONFIRMED` is consistent with the failed last P80 and absence of the normal closing GFA check. It does not erase the earlier successful identity replies. Renewed HA data freshness was not independently reported for this specific run; immediate systemd running state and a restored P300 link are not a complete MQTT/application health check.

### The saved data remains useful despite FAIL

```text
224 accepted rounds -> 896 accepted runtime values, all 00
226 attempted rounds -> 904 runtime replies, all 00
measurement-round P80 -> 224 x 20, 2 x FF
```

Both rejected rounds have `decoded: null`. They must not be included as accepted measurement sets even though their four runtime replies were zero. The two FFs did not create false RPM, PWM or phase values.

The record contains **no convincing burner-start sequence**, no independent flame measurement and no nonzero runtime values. Zero values are consistent with idle, but do not independently prove the physical burner state or exclude stale/internal unavailable data. The earlier independently synchronized firing snapshot at 4110 rpm remains a separate valid observation within its original limits.

## 3. Fair comparison with the preceding approximately 51-ms run

Baseline source: `Eingefügter Text(20260924-062018).txt`, 489573 bytes, 2901 lines, SHA256:

```text
a976eaac07fa52ea1b1911412e011be51a3cd59705a7d81dd5fe3a25569d431f
```

Its 171 JSON records contain 158 accepted rounds and four rejected attempts, with three successful re-identifications. [Baseline evidence](../config/optolink-splitter/research/vitosoft/gfa-quality-run-2026-09-24-evidence.json) and the historical [quality-helper runbook](gfa-quality-logger.md) preserve the detailed implementation and original result.

### Counting definition

Count actual GFA reads **inside attempted measurement rounds**, including samples already received in a rejected round. Include each round's P80 guard if it was reached. Exclude initial/re-entry/closing identity checks in both runs.

```text
baseline: 158*5 + 4 + 3 + 3 + 4 = 804 replies; 4 FF
paced:    224*5 + 5 + 5         = 1130 replies; 2 FF
```

The baseline is not 162*5 because it stops a round immediately upon runtime FF, before later channels are read. The raw paced log additionally contains four independently synchronized P80 reads and two extra same-session entry/re-entry guards, all successful; including these gives 1136 total GFA reads. Do not mix that total with the 1130 comparison denominator.

| Metric | Previous approximately 51 ms | Paced minimum 150 ms |
| --- | ---: | ---: |
| Observation elapsed before stop | 132.189 s | 288.915 s |
| Accepted rounds | 158 | 224 |
| Attempted measurement-round reads | 804 | 1130 |
| FF replies | 4 | 2 |
| Descriptive FF fraction | **0.4975%** | **0.1770%** |
| Re-identifications attempted/succeeded | 3/3 | 1/1 |
| Mean P06-to-P06 interval within segments | 617.564 ms | 1228.244 ms |
| Mean P06-to-P84 span | 369.690 ms | 737.593 ms |
| Accepted nonzero runtime samples | 0 | 0 |
| Final result | FAIL: fourth rejection hit reconnect cap | FAIL: second rejection left too little time |

Thus the paced run had fewer FF replies **per sampled request**, not just fewer per minute. That is a useful descriptive observation. However, there are only six FF events across two sequential, nonrandomized runs with different stopping/coverage patterns and different affected-register distributions. Do not present this as a proven percentage reduction, proof that excessive request rate caused FF, or an established safe timing requirement.

Pacing has roughly halved the observed per-channel measurement rate: approximately 1.62 rounds/second versus 0.81, using same-segment P06 intervals. Dividing all replies by elapsed time does not give each channel's sampling rate. Channels remain sequential, not simultaneous.

### Measured timing in the paced capture

| Metric | Count | Minimum | Mean | Maximum |
| --- | ---: | ---: | ---: | ---: |
| Annotated preceding-reply to next-request gap | 1130 | 150.099 ms | **150.264 ms** | 155.553 ms |
| Consecutive P06 receives, excluding segment gap | 222 | 1042.376 ms | **1228.244 ms** | 1309.064 ms |
| P06-to-P84 span in accepted round | 224 | 625.833 ms | **737.593 ms** | 802.714 ms |
| Accepted runtime reply latency | 896 | 54.214 ms | **95.377 ms** | 169.077 ms |

The 150-ms minimum is visibly implemented; it was not just a command-line label. These are host-side timestamps and do not establish physical bus edges or the controller's internal sensor acquisition time.

## 4. Retained baseline events and limits

The preceding quality run began at **08:17:31.837** and rejected:

| Attempt | Channel | FF receive time | Elapsed to receive | Action |
| ---: | --- | --- | ---: | --- |
| 12 | P84 | 08:17:39.284 | 7.447 s | First re-identification succeeded. |
| 116 | P10 | 08:18:54.099 | 82.262 s | Second succeeded. |
| 139 | P10 | 08:19:18.975 | 107.138 s | Third succeeded. |
| 162 | P84 | 08:19:43.974 | 132.138 s | No fourth attempt allowed. |

Re-identification durations were 10.886413, 10.950023 and 10.887411 seconds. Accepted counts by segment were 11, 103, 22 and 22. Its final P300 identity was confirmed at 08:19:46.089, then the splitter and party emulator reported running at 08:19:48.172 and 08:19:50.245.

The baseline's early first FF and recurrence after successful re-entry already contradicted a simple five-minute session-lifetime explanation. The FF-to-FF intervals 74.814987, 24.875964 and 24.999339 seconds were retained as a lead, not a proven periodic firmware task. The new paced capture does not resolve that hypothesis.

In the baseline, all eight independent P80 replies and 162 same-session P80 replies in the raw log were 20. In contrast, the new paced capture's only FFs are P80 replies. This changing distribution does not prove that one particular register is faulty. No universal FF sentinel meaning, electrical defect or actual burner fault has been established.

## 5. Unchanged helper and experimental controls

Helper: [`wb2a-gfa-paced-probe.py`](../config/optolink-splitter/wb2a-gfa-paced-probe.py), experiment version **1.0.0**.

Implementation commit: `3a9bfccc2cfcf7562fce50c47715490eea1adfa6`.

SHA256:

```text
053c7806d863c7fe551903a24498f4841c0d2235b661e674f80f07696065e974
```

The retained Git blob is `1091aae156c9c24bea6b6a8240e1405ffc1d225d`. The locally mounted helper bytes were hash-checked again during this analysis. No executable helper was edited or deployed as a new version.

Minimum reply-to-next-request spacing remains 150 ms. This is an experimental comparison setting, not a recovered Viessmann requirement. Its purpose is to avoid inventing further unmeasured timing changes while examining a different actual operating state.

Unchanged constraints:

- Only the already tested P06/P09/P10/P84/P80 one-byte reads and existing identity/protocol-control frames.
- FF quarantines the whole current round; raw bytes retained, no numeric replacement or false phase transition.
- At most three full re-identifications, and at least ten accepted rounds before a subsequent FF can trigger another.
- P300 20C2 plus two independent and one same-session P80=20 checks before sampling resumes.
- Non-FF identity mismatch, timeout, queued/trailing bytes, partial write or excess host gap remain fatal.
- The 300-ms maximum host-gap guard remains active during pacing; no clock manipulation hides stalls.
- Same exclusive port ownership, deliberate service pause and P300/service restoration.
- Observation clock never restarts after a gap; no new segment with less than 15 seconds left.

The wrapper records `experiment=reply_gap_150ms`, `experiment_version=1.0.0`, `minimum_reply_gap_ms=150` and measured `rx_to_next_tx_gap_ms`. Inherited quality version 1.1.0 is a library version, not a conflicting experiment version.

### Dependencies and earlier tests

These four existing files must remain unchanged beside the paced helper:

| File | Required SHA256 |
| --- | --- |
| `wb2a-gfa-quality-logger.py` | `bdd1d829ba2d1387c21ae99e02848755e7ad8045c0b3034ff7430eb555900910` |
| `wb2a-gfa-cycle-logger.py` | `d5d98242e6f9526522a53f3c801d856ba8c1a7fde6349c05b56059fa732a54e3` |
| `wb2a-gfa-session-probe.py` | `32351e07cb0d661c00f7bcb7851d8103aca0b9cbc2f339041202e48b760d6da2` |
| `wb2a-gfa-p80-probe.py` | `6de883c422a09c821b342d12e5bb71dd3d518d8115ec2495bdfb202f5a7f50cb` |

Loading verifies dependency bytes before executing the known helper code; settings are not imported/executed. A mismatch stops before service/serial actions.

The original release was compiled and tested with **125 offline tests**: 109 inherited tests plus 16 pacing tests covering timing, FF handling, allowlist, deadlines, queued bytes during waits, host/logging stalls, interruptions and simulated 300-second completion. Those historical tests are not evidence of physical FF semantics or long-run reliability. During this analysis, the complete new log and comparison consistency checks were executed, and a **60-second plan-only invocation** passed without touching systemd or serial hardware. No new device test or claim of a newly deployed code fix is made.

## 6. Next bounded observation: normal established firing, 60 seconds

The useful unresolved question is now whether the four channels produce plausible sustained **nonzero** values in a persistent session while the burner is actually running. Until now, nonzero firing values came from independently synchronized snapshots; all supplied longer same-session captures are zero-valued apart from quarantined anomalies.

Use the existing helper once during a naturally already-established burner run. Do not deliberately change heating settings, force ignition, use an actuator test or increase limits merely to obtain activity. Record whether the appliance's own flame display remains active and whether it stops during observation. A flame icon before starting alone is not a timestamped flame channel inside the log.

This is a steady-running validity/correlation check, not a full ignition/stabilization trace and not proof that FF has been fixed. If no natural firing opportunity occurs, no immediate heater action is required; offline protocol/sentinel investigation can continue from the retained collector.

Run in the same LXC as root. Do not stop services beforehand, alter `vs1protocol` or run another serial client. Keep all pinned helpers unchanged. Normal HA/MQTT/TCP polling and an active party emulator pause for the observation plus entry/recovery; pausing that emulator may affect externally maintained heat requests. Old HA values are not contemporaneous evidence. Verify application freshness separately after the helper exits.

No new download or full `update` is needed:

```bash
(
  set -euo pipefail

  printf '%s  %s\n' \
    '053c7806d863c7fe551903a24498f4841c0d2235b661e674f80f07696065e974' \
    /root/wb2a-gfa-paced-probe.py | sha256sum -c -

  /opt/optolink/venv/bin/python -u \
    /root/wb2a-gfa-paced-probe.py --execute --seconds 60
)
```

The helper accepts 30..300 seconds; 60 is already supported. It creates new root-only `.log` and `.jsonl` files without overwriting earlier captures. No automatic execution is added to installation or update paths.

Preserve both new files even if the observation ends in FAIL. Already accepted records can still answer the operating-state question, while rejected rounds/gaps remain excluded. A near-end FF can still cause the same reserve-based abort; do not suppress or reclassify it simply to obtain PASS.

Result semantics remain:

- PASS / exit 0: window and closing/recovery conditions met without rejected rounds;
- COMPLETE_WITH_GAPS / exit 2: completed window with explicit rejected rounds and new segments, not uninterrupted success;
- FAIL / exit 1: acquisition, closing identity or restoration criteria were not met; earlier retained records are not automatically erased or physically certified.

Ordinary interruption signals enter cleanup. There is no independent watchdog or unconditional guarantee under SIGKILL, power loss, disconnected USB, kernel stalls or failed service jobs. P300 and service restart status must remain distinct from HA freshness and burner-state observations.

## 7. Research implications

Keep the 150-ms setting as a provisional diagnostic choice, not a production reliability specification. Do not add another wrapper that simply raises retries, increases the observation window or masks FF. The useful next live comparison changes the observed operating state while preserving the same software/guards/pacing.

The underlying FF semantics and source remain unresolved. Source-level invalid-value handling, transport/physical-link checks and reproducible timing comparisons remain distinct research paths. A successful sustained firing trace would not settle all of them. No assumption is made that VS1 blocks combustion; these logs contain no independent contemporaneous flame/heat-request channel.

Permanent Home Assistant acquisition still requires a single coordinated owner of the interface, valid-data policy and bounded recovery, rather than competing serial processes. Flame timestamps, full startup state mapping, actual thermal-kW calibration, firmware acquisition, E7 persistence, selective pump override and coding-plug modification remain separate tasks.

This checkpoint updates documentation and derived evidence only. Production profiles, dashboard YAML, installer/updater behavior, heating settings, safety parameters and every existing diagnostic helper are unchanged.
