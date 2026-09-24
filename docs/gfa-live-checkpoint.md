# GFA live checkpoint - 2026-09-23

**Current status: the self-triggered 37 C run succeeded end-to-end. It captured 50/50 clean P84/P87/P06/P09 rounds, verified exact 37 C readback and restore to 21 C, and strongly correlates P87 bit 1 (60->62) with release of the 57.6534% high-start modulation plateau. P84/P87 manufacturer semantics and the earliest ~4.8 s after the trigger remain unresolved.**

Read the [paced comparison and startup trace](gfa-paced-comparison.md) for the latest live result. The next bounded experiment is the [GFA status/startup probe](gfa-status-probe.md): P84/P12 every round, alternating P85/P86 and P87/P88, with P80 guarding every round. It records raw bits only; no flame/status semantics are assigned. The earlier [long-run FF investigation](gfa-cycle-ff-investigation.md) remains relevant to acquisition quality.

A firing snapshot previously decoded P06 as 4110 rpm. The new continuous trace now independently supports the channel with a coherent 0->660->2490->4500 rpm startup and subsequent ramp down to 2790 rpm. The older isolated P06=FF conversion to 7650 rpm remains invalid as a physical event. Permanent Home Assistant integration remains unverified.

Evidence:

- [Continuous startup trace](../config/optolink-splitter/research/vitosoft/gfa-startup-run-2026-09-24-evidence.json).
- [Status-target selection](../config/optolink-splitter/research/vitosoft/gfa-status-targets-2026-09-24-evidence.json).
- [First long-run failure and FF samples](../config/optolink-splitter/research/vitosoft/gfa-cycle-ff-2026-09-23-evidence.json).
- [Snapshot comparison](../config/optolink-splitter/research/vitosoft/gfa-snapshots-2026-09-23-evidence.json).
- [Same-session measurements and timing](../config/optolink-splitter/research/vitosoft/gfa-session-2026-09-23-evidence.json).
- [Static variant/scaling definitions](../config/optolink-splitter/research/vitosoft/private-archive-2026-09-23-evidence.json).

This is the current hardware checkpoint. Older collector documents describe static-only work, and older helper/runbook text may describe the state before its first execution. Preserve both the successful short tests and the unsuccessful long observation below.

## 0. Successful self-triggered startup correlation - 2026-09-24

Trigger helper v1.0.1 read the original A1 normal setpoint as 21 C and `0x55DC=0`, wrote only `0x2306=37`, verified 37 by Virtual_READ, and then captured 50 clean GFA rounds. Cleanup restored and read back 21 C; P300 20C2 and both services were restored. Result PASS, zero rejected rounds/reconnects/FF.

The capture begins 4.793 s after the 37 C trigger at P84=02. It observes P87 `20->40->50->60->62`, P84 `02->05->06`, fan rise through 2490->3900->4500->4590 rpm and the subsequent high-start hold.

The key new correlation is P87 `60->62`: bit 1 is first observed set at 10:42:26.805. P09 is first observed below its raw-93 / 57.6534% plateau at 10:42:27.302. Their true transition windows overlap within the same sequential acquisition round, so causal order is not proven, but bit 1 is now a strong candidate marker for the release/end of the high-start plateau. It must not yet be named "flame stabilized" or "regulation enabled".

First P84=06 to first P87=62: 10.148 s. First P87=60 to first P87=62: 9.866 s. This reproduces the previously observed short startup hold.

At restore, `0x2306=21` was read back successfully, but immediate `0x55DC=0x21` showed the burner still active. A restored room setpoint therefore does not imply immediate burner shutdown.

Evidence: [successful triggered startup](../config/optolink-splitter/research/vitosoft/gfa-triggered-startup-2026-09-24-evidence.json). Detailed analysis: [GFA status/startup probe](gfa-status-probe.md).

## 0a. Triggered-status attempt - write ACK parser corrected, 2026-09-24

The first self-triggered helper read `0x2306=21` and `0x55DC=0`, confirmed P80=20 twice, then sent the bounded temporary write `0x2306=37`. The WB2A returned `41 05 01 02 23 06 01 32`. Version 1.0.0 misparsed the final payload byte as a data-length field and aborted before the required readback or any GFA observation.

Cleanup sent the original 21 C value three times; all three writes received the same successful one-byte Virtual_WRITE acknowledgement. Because the parser aborted before readback, that run did not independently verify the final setpoint value. P300 20C2 was restored and both services restarted.

Version 1.0.1 corrects this specific response grammar while retaining exact Virtual_READ verification of the requested value. Commit `8259cd5f3c07c4d46939e17e7bc87dc47378717f`, SHA256 `6d5810e1595ba6e464452dcd927259e9bade8f550a92b492fd40c2a27972604b`; 168/168 offline tests pass, including the exact live ACK frame.

Evidence: [failed triggered-status run](../config/optolink-splitter/research/vitosoft/gfa-triggered-status-failed-run-2026-09-24-evidence.json).

## 0. Latest live result - continuous startup trace, 2026-09-24

The unchanged paced helper ran for 60 seconds with 150-ms minimum reply spacing. The appliance transitioned from idle-like zero GFA values into a complete startup-like sequence during the observation. All 49 rounds were accepted; no FF reply or reconnect occurred. Closing P80 remained 20, P300 20C2 was restored, and both previously running services reported running.

Observed P84 raw sequence: **00 -> 02 -> 04 -> 05 -> 06**. No manufacturer phase names have been recovered, so these remain raw states.

Key timing:

- P84 02 at 08:56:37.119.
- P09 raw 93 / 57.6534% at 08:56:37.895.
- P10 raw 58 / 35.2% at 08:56:38.104.
- P06 first nonzero at 08:56:38.882: 660 rpm.
- P06 first reaches 4500 rpm at 08:56:41.339.
- P84 04 at 08:56:45.655, 05 at 08:56:46.766, 06 at 08:56:47.934.
- P09 first leaves its 57.6534% plateau 9.368 s after the first observed 06.
- P06 first drops below 4410 rpm 10.362 s after the first observed 06.
- Last round: 2790 rpm, P09 34.9058%, P10 33.2%, P84 06.

This is the strongest timing lead for the short startup-hold/flame-stabilization investigation. It does not prove that P84=06 is flame recognition because the logger did not poll an independent flame signal. See [paced comparison](gfa-paced-comparison.md) and the machine-readable startup evidence for details.

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
