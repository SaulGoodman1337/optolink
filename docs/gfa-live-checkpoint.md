# GFA live checkpoint - 2026-09-23

**Current status: short P80/snapshot/same-session tests succeeded, but the first requested 300-second observation failed at a P80=FF mismatch. P300 and both previously running services were restored. Two earlier isolated FF runtime samples expose a measurement-quality gap.**

Read the [long-run FF investigation](gfa-cycle-ff-investigation.md) before executing another logger. The next step is to inspect the existing raw TX/RX log, not repeat the long experiment unchanged. Its complete pasted JSONL has already been analyzed; do not ask for it again.

A firing snapshot previously decoded P06 as 4110 rpm. That result is not revoked, but the later isolated P06=FF conversion to 7650 rpm is not a validated physical event. Continuous acquisition, a complete startup trace and permanent Home Assistant integration remain unverified.

Evidence:

- [First long-run failure and FF samples](../config/optolink-splitter/research/vitosoft/gfa-cycle-ff-2026-09-23-evidence.json).
- [Snapshot comparison](../config/optolink-splitter/research/vitosoft/gfa-snapshots-2026-09-23-evidence.json).
- [Same-session measurements and timing](../config/optolink-splitter/research/vitosoft/gfa-session-2026-09-23-evidence.json).
- [Static variant/scaling definitions](../config/optolink-splitter/research/vitosoft/private-archive-2026-09-23-evidence.json).

This is the current hardware checkpoint. Older collector documents describe static-only work, and older helper/runbook text may describe the state before its first execution. Preserve both the successful short tests and the unsuccessful long observation below.

## 1. First P80 hardware result

Source: the user's pasted console transcript naming `/root/wb2a-gfa-p80-20260923-223259-168588.log`; the separately stored log file was not fetched.

Helper: `wb2a-gfa-p80-probe.py` 1.0.0, commit `ab32e2d2fe2c165390d7098dcffc4bb2e097543d`, SHA256 `6de883c422a09c821b342d12e5bb71dd3d518d8115ec2495bdfb202f5a7f50cb`.

Local environment: Python 3.13.5 / pyserial 3.5, configured CP2102 by-id adapter resolving to `/dev/ttyUSB0`, 4800 8E2, `vs1protocol=False`, no Vitoconnect forwarding adapter. The other USB adapter was not selected.

| Local time (+02:00) | Observation |
| --- | --- |
| 22:32:59.146 / .172 | Running party emulator and splitter stopped. |
| 22:33:01.258 | Baseline P300 Virtual_READ 00F8/2 returned `20 c2`. |
| 22:33:05.495 -> .595 | `01 6b 40 50 01` -> `20`. |
| 22:33:09.880 -> 22:33:10.027 | Independently synchronized repeat -> `20`. |
| 22:33:12.139 | Restored P300 00F8/2 again returned `20 c2`. |
| 22:33:14.167 / 22:33:16.210 | Splitter and party reported running; PASS. |

Both GFA reads used EOT, interface-detection ENQ, a fresh VS1 ENQ, then STX plus GFA_READ. The P300 response frame excluding ACK was `41 07 01 01 00 f8 02 20 c2 e5` before and after the test.

This established P80=`0x20`, the locally selected GFA branch, and independent read/recovery. The [P80 runbook](gfa-p80-probe.md) preserves the procedure and restoration limits. The tested P80 helper is unchanged.

## 2. Burner-off and burner-on snapshots

Source: two uploaded console transcripts. Burner off/on was explicitly reported by the user; the snapshot helper did not poll flame state. The separate device-side `.log` files were not fetched.

Helper: `wb2a-gfa-snapshot.py` 1.0.0, commit `8e9b2271c0bbc4bc8691f2778720a444e9f26476`, SHA256 `b8a89bae4a7dbcc4047b115d9c733f596f0e3a9a60d8025db7a86e1c9caf0141`. Both user runs passed hash checks and 45 offline tests before serial access.

| Register | Burner off | Burner on | Burner-on SAMPLE time |
| --- | --- | --- | --- |
| P06 / 0x4006 | `00` -> 0 rpm | `89` = 137 -> **4110 rpm** | 22:45:07.923 |
| P09 / 0x4009 | `00` -> 0% | `7b` = 123 -> **48.2406% modulation setpoint** | 22:45:12.268 |
| P10 / 0x400A | `00` -> 0% | `67` = 103 -> **41.2% fan PWM setpoint** | 22:45:16.612 |
| P84 / 0x4054 | `00` | **`06`** | 22:45:20.978 |

Idle SAMPLE times were 22:42:17.349, 22:42:21.802, 22:42:26.242 and 22:42:30.667. The source-hashed snapshot JSON preserves exact raw samples/timestamps/latencies.

The GFA-branch source events are 8175 (P06 x30 rpm), 8259 (P09 x0.3922%), 8179 (P10 x0.4%) and 8208 (P84 raw). P09 is not a fan-RPM setpoint for this branch.

| Check | Burner-off run | Burner-on run |
| --- | --- | --- |
| Transcript-named log | `wb2a-gfa-snapshot-20260923-224201-168882.log` | `wb2a-gfa-snapshot-20260923-224452-168983.log` |
| P80 values including closing guard | `20 / 20 / 20` | `20 / 20 / 20` |
| P300 before/after | `20c2 / 20c2` | `20c2 / 20c2` |
| Runtime reads | 4/4 | 4/4 |
| P300 restored / splitter restarted | yes / yes | yes / yes |
| Party restored / final result | yes / PASS | yes / PASS |
| Total logged duration | 39.126 s | 38.804 s |
| Splitter stop -> running | 37.058 s | 36.735 s |
| P06 -> P84 SAMPLE span | 13.318 s | 13.055 s |

Home Assistant value delivery was explicitly reported after the first snapshot. The second transcript proves service restoration but does not independently confirm application freshness.

The off/on contrast supports meaningful runtime values, including a GFA-reported RPM value. It is not independent tachometer calibration. P09 and P10 are distinct command quantities sampled at different instants; their difference is not automatically a fault. No simultaneous 55DC/A305 comparison or thermal-kW calibration was supplied.

P84=00 and P84=06 are observed raw states, not a recovered manufacturer enum. Do not declare 06 exclusively steady regulation or assign every other phase a guessed name. In this VS1 reply context, P84 raw `06` is data, not a P300 acknowledgement.

The independent-synchronization snapshot spans about 13 seconds across its four channels. It cannot resolve the approximately 12-second post-flame interval or prove a relationship at one common instant.

## 3. Same-session access is locally demonstrated for the short test

Helper: `wb2a-gfa-session-probe.py` 1.0.0, commit `3b9bb24e035034745b3b3949ad0a86817985597a`, SHA256 `32351e07cb0d661c00f7bcb7851d8103aca0b9cbc2f339041202e48b760d6da2`. The original tested helper is unchanged.

Source: uploaded `Eingefügter Text(20260923-205625).txt`, SHA256 `cdea0307880b69ecbc22ea6af9a81a4e2068c36f315a1320210e7639bedeb1ab`, naming `/root/wb2a-gfa-session-20260923-225537-169322.log`. All 56 offline tests and the download hash check passed before the actual run.

### Actual sequence

- 22:55:37.764/.787: party emulator and splitter paused.
- 22:55:39.873: baseline P300 identification `20c2` confirmed.
- 22:55:44.175 and 22:55:48.521: two independently synchronized P80 replies `20`.
- 22:55:48.571: first bare `6b 40 50 01` request in the still-active VS1 session, without new EOT/STX; reply `20` at 22:55:48.627.
- Ten response-paced P06/P09/P10/P84 rounds, each followed by P80=`20`, completed without reinitializing the session.
- 22:55:54.930: `ROUND_CONFIRMED=10/10`; burst 6.359 s; 40 runtime samples.
- 22:55:59.316: independent closing P80 reply `20`.
- 22:56:01.428: restored P300 `00F8/2 = 20c2` verified.
- 22:56:03.458 and 22:56:05.508: splitter and party reported running.
- 22:56:05.509: `SESSION_ROUNDS=10/10`, `P80_CONFIRMED=0x20 GFA`, `P300_RESTORED=yes`, `SPLITTER_RESTARTED=yes`, `RESULT=PASS`.

There were 11 successful same-session P80 guards (initial guard plus ten rounds) and three successful independent P80 reads (two entry plus one exit). All 40 runtime replies were `00`. These are actual zero-valued responses, not missing data; P80 consistently returned nonzero `20` in the same transport. The state is consistent with idle, but there was no independent flame measurement or explicit new burner-state report in this upload.

### Timing calculated from the uploaded transcript

| Metric | Minimum | Mean | Maximum |
| --- | ---: | ---: | ---: |
| Consecutive P06 host-receive interval | 597 ms | **625.889 ms** | 703 ms |
| P06-to-P84 span within a round | 322.3 ms | **367.35 ms** | 417.6 ms |
| Individual runtime reply latency | 55.1 ms | 74.06 ms | 151.5 ms |

Approximately 1.60 complete channel sets per second follows from the P06 intervals. Do not divide 40 by 6.359 and call that the sampling rate of each sensor. All channels are sequential, and the device's internal acquisition time is not known from host receive timestamps.

The four-channel spread is substantially shorter than the previous approximately 13-second snapshots. This supported moving to a bounded observation window, but was not proof of minutes-long data validity or a complete burner cycle. No new Home Assistant freshness report was supplied for this specific run.

### Source model and retained constraints

Vitosoft IL methods `VS1Message::toByteArray` (285-322), `VS1::_timer_processor_Elapsed` (985-1099) and `VS1::sendVS1Message` (1283-1510) separate setup/STX from subsequent four-byte reads. The observed short session supports that model locally. `sendKeepVS1Message` exists separately, but no additional keepalive command is introduced.

The pinned session helper enforces the fixed read allowlist, 300-ms host idle-gap guard, no continuation through unexpected queued/trailing data, no automatic retransmission and a 20-second burst budget. Its 56 tests cover framing, identities, per-round guards, timestamps, timeouts, logging stalls and recovery paths. Passing the following P80 guard confirms identity/alignment at that point, NOT per-value integrity or physical plausibility; see the counterexamples in the long run below.

## 4. First long observation failed; recovery worked

The [GFA observation logger](gfa-cycle-logger.md) was executed for a requested 300 seconds. Logger commit: `008e802ea8d5d0dc5a7a8658896722d37ed922da`; SHA256 `d5d98242e6f9526522a53f3c801d856ba8c1a7fde6349c05b56059fa732a54e3`. It requires the unchanged P80 and session helpers. All 89 offline tests passed before the run, but those simulated tests did not establish live response validity.

Source: `Eingefügter Text(20260923-211214).txt`, SHA256 `c2f84dfd3e70d2204fa03011568b9b58895d0ff094e95948901fab3d830b6642`. It includes the complete generated JSONL (466 objects, 463 rounds) as well as the console transcript. Only the separate TX/RX `.log` is still missing.

| Event | Result |
| --- | --- |
| Observation start | 23:06:39.617 +02:00 |
| Retained rounds | 463, all with P80=20; 1852 runtime values |
| All-zero rounds | 461 |
| Round 142, P06 at 23:08:06.612 | Isolated FF, mechanically decoded as 7650 rpm; P09/P10/P84 zero, P80=20 |
| Round 222, P84 at 23:08:56.490 | Isolated FF, surrounding phases zero; P06/P09/P10 zero, P80=20 |
| Next attempted round 464 | P80=FF, guard mismatch; not published as a valid complete JSON round |
| Failure message | 23:11:26.069, RESULT=FAIL |
| P300 restoration | 23:11:28.130, actual 20C2 identity verified on attempt 1 |
| Splitter / party running | 23:11:30.205 / 23:11:32.261 |

P06 and P84 each returned zero immediately before and after their isolated FF values. The two nonzero rounds are not evidence of a burner start. No separate flame state was captured. The earlier firing snapshot does not establish firing during this later observation.

The reported summary duration, 285.814239 seconds, stops at the last completed round in version 1.0.0. The console start-to-failure interval is 286.452 seconds. Do not infer a fixed five-minute session expiry: anomalies already occurred around 87 and 137 seconds, and the failed guard's exact raw context remains unavailable.

Retained-round timings: P06 interval 564.993-746.024 ms, mean 616.970 ms; P06-to-P84 span 318.604-511.339 ms, mean 369.652 ms. These approximately 1.62 rounds/second measurements do not compensate for missing per-value validity. See the linked evidence and [detailed investigation](gfa-cycle-ff-investigation.md) for counts, exact timestamps and code references.

The inspected helper raises a distinct exception on a timeout; it does not synthesize FF. The terminal message means the identity check processed FF instead of 20, not a decoded boiler fault or a successful changed device identity. Its physical origin is not established. Internal GFA response availability, transient/serial behavior and other causes remain hypotheses.

The current logger scales runtime FF without a quality flag when the next P80 passes. Its 7650-rpm output and phase-change counters therefore must not be treated as validated physical events. This is an acquisition-quality limitation, not a reason to discard raw evidence, silently replace FF with zero or disable the guard.

## 5. Immediate next step and production boundary

**Read the existing log before any repeat.** The offline extraction command and precise file path are in [the FF investigation](gfa-cycle-ff-investigation.md). The full JSONL is already available and analyzed; do not request it again. Do not repeat the unchanged 300-second test, extend it to 600 seconds, guess new commands or remove identity validation.

Documented logger follow-up: retain raw/converted/quality fields separately; report suspect FF values without claiming a universal sentinel definition; distinguish identity-guard success from measurement validity; preserve failed-round context and actual failure elapsed time; review any bounded reread/resynchronization policy explicitly after inspecting the raw evidence. No revised live logger was deployed in this analysis.

Normal MQTT/TCP polling and a running party emulator were paused throughout. Service restoration succeeded, but current Home Assistant freshness still requires a separate observation. Old HA states are not contemporaneous samples during a pause. Pausing an emulator can affect externally maintained heating requests; the absence of activity here does not by itself identify why the burner remained idle-like.

Only after response quality is resolved should another natural operating trace be collected and phase/55DC/flame correlation expanded. Permanent Home Assistant acquisition requires deliberate serial ownership and protocol scheduling, not another competing serial process. Do not use the suspect values for fan, burner or pump control.

GFA software identity/coding-plug diagnostics, E7 persistence, internal-pump request selection, full firmware acquisition and M2 remain separate research tasks. No production dashboard, poll list, updater behavior, heating coding or safety parameter was changed by this analysis.
