# GFA live checkpoint - 2026-09-23

**Current status: P80, individual P06/P09/P10/P84 reads and a ten-round same-session series have succeeded on the local WB2A. The short same-session burst delivered 40 runtime samples in 6.359 seconds with all P80 guards passing.**

A firing snapshot previously decoded P06 as 4110 rpm. The new repeated series returned all-zero runtime values, consistent with an idle-like state; it did not independently poll flame or capture a burner-start transition. Minutes-long stability, a complete startup trace and permanent Home Assistant integration are still unverified.

Next executable step: [bounded GFA observation logger](gfa-cycle-logger.md), implemented and offline-tested for a first explicit 300-second observation. It reuses the verified transport and does not introduce new addresses or parameter writes.

Evidence:

- [Snapshot comparison](../config/optolink-splitter/research/vitosoft/gfa-snapshots-2026-09-23-evidence.json).
- [Same-session measurements and timing](../config/optolink-splitter/research/vitosoft/gfa-session-2026-09-23-evidence.json).
- [Static variant/scaling definitions](../config/optolink-splitter/research/vitosoft/private-archive-2026-09-23-evidence.json).

This is the current hardware checkpoint. Older collector documents describe static-only work, and older helper/runbook text may describe the state before its first execution. Do not interpret those historical limitations as revoking the successful runs below.

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

## 3. Same-session access is now locally demonstrated

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

The four-channel spread is substantially shorter than the previous approximately 13-second snapshots. This supports moving to a bounded observation window, but a six-second series is not proof of minutes-long stability or a complete burner cycle. No new Home Assistant freshness report was supplied for this specific run.

### Source model and retained constraints

Vitosoft IL methods `VS1Message::toByteArray` (285-322), `VS1::_timer_processor_Elapsed` (985-1099) and `VS1::sendVS1Message` (1283-1510) separate setup/STX from subsequent four-byte reads. The observed session now supports that model locally. `sendKeepVS1Message` exists separately, but no additional keepalive command is introduced.

The pinned session helper enforces the fixed read allowlist, 300-ms host idle-gap guard, no continuation through unexpected queued/trailing data, no automatic retransmission and a 20-second burst budget. Its 56 tests cover framing, identities, per-round guards, timestamps, timeouts, logging stalls and recovery paths. The initial pending `SAMPLE` records become valid only after their round guard passes; a P80 guard is not a checksum on each VS1 data byte.

## 4. Next: bounded observation, not another identical short test

The new [GFA observation logger and execution runbook](gfa-cycle-logger.md) provide a deliberate **300-second first observation** using the same addresses and response-paced transport. No new function code, block length, burner command, GFA write, EEPROM write or process write is enabled.

Logger commit: `008e802ea8d5d0dc5a7a8658896722d37ed922da`; tested SHA256 `d5d98242e6f9526522a53f3c801d856ba8c1a7fde6349c05b56059fa732a54e3`. The remote blob matches the locally tested file. It requires the unchanged P80 and session helpers beside it, with hash verification before loading.

Compilation, plan-only execution and **89 offline tests** passed, including simulated 300/600-second windows and output/recovery failures. Actual minutes-long appliance behavior remains pending.

The logger records raw `.log` data plus guarded `.jsonl` rounds, with per-channel host timestamps, values, timing and raw phase changes. Only complete P80-validated rounds become measurement records. It preserves the earlier frames/recovery logic, catches ordinary interruptions, and restores previously running services. There is no independent watchdog against SIGKILL, power loss, USB failure or systemd failure.

Normal MQTT/TCP polling and a running party emulator are paused throughout. Do not treat old Home Assistant states as contemporaneous measurements. Pausing an emulator can affect externally maintained heating requests; use normal autonomous operation for the first observation. Do not force ignition or alter codings to obtain a trace.

The logger does not read flame, pump or temperature values, so it cannot yet precisely timestamp flame establishment or causally explain every start-phase interval. A full start might not occur in the selected window. All-zero stable data can still validate communication; it is not a successful startup capture.

## 5. Following work and interpretation boundaries

After a real longer capture, correlate P06/P09/P10/P84 through any observed natural changes and check session stability. Keep phase names raw unless evidence supports their meaning. Obtain independent flame/55DC/55E0 observations separately using a source-justified approach before claiming exact post-flame delays. A stopped P300 splitter cannot provide concurrent live MQTT samples.

Permanent Home Assistant acquisition still requires deliberate ownership/scheduling of protocol modes or another demonstrated architecture. A second serial process competing with the splitter is not a permanent integration design.

GFA software identity/coding-plug diagnostics, E7 persistence, internal-pump request selection, full firmware acquisition and M2 remain separate research tasks. These successful fan/status reads do not solve them by implication. No production dashboard, poll list, updater behavior, heating coding or safety parameter has been changed by this work.
