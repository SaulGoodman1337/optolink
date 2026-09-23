# WB2A bounded GFA observation logger

Status: **first 300-second attempt stopped on P80=0xFF; P300 and both services restored; raw-log diagnosis pending**.

This advances the successful ten-round session experiment recorded in [GFA live checkpoint](gfa-live-checkpoint.md), but the first longer attempt did not complete. The result below supersedes older statements that the minutes-long test is still unattempted or that continuous operation has been validated. No complete burner cycle has been captured by this attempt.

## First long-run result - 2026-09-23 23:06-23:11 (+02:00)

Source: the user's uploaded `Eingefügter Text(20260923-211214).txt`, SHA256 `c2f84dfd3e70d2204fa03011568b9b58895d0ff094e95948901fab3d830b6642`. It contains the console output and the complete pasted JSONL: metadata, observation start, 463 sequential round records and one failure summary (466 JSON records). It does NOT contain the full TX/RX `.log` file. The file paths printed by the logger are not evidence that the separate remote files were fetched.

[Machine-readable findings](../config/optolink-splitter/research/vitosoft/gfa-cycle-2026-09-23-evidence.json) preserve source identity, raw histograms, anomalous samples, timing, recovery and the original summary. All 463 round records were parsed; numbering, four-register membership, guard values and raw-to-decoded arithmetic were checked offline. No new hardware request was executed while analyzing the upload.

### Exact reason for stopping

```text
23:06:39.617 OBSERVATION_START seconds=300
23:11:25.431 ROUND 463 ... guard=20
23:11:26.069 OBSERVATION FAILED: Session P80 guard is 0xff, expected 0x20.
23:11:28.130 P300 identity = 20c2
23:11:30.205 SERVICE_RESTORED=optolink-splitter.service running
23:11:32.261 SERVICE_RESTORED=optolink-party-emulator.service running
23:11:32.262 RESULT=FAIL
```

The immediate cause is a nonmatching identity/stream-alignment guard, not the configured 300-second deadline, a recorded host idle-gap exception or a recorded read timeout. The session helper raises this particular message after receiving a byte; it does not substitute 0xFF for an empty read. The raw TX/RX line for this failing guard is still needed from the saved `.log`.

The failing attempt is round 464 by the code's sequential control flow; that unconfirmed round is correctly absent from JSONL. The 463 earlier P80 checks do not make every earlier runtime sample physically valid.

Wall-clock difference from observation start to the logged exception is approximately 286.452 seconds. The summary reports `observation_elapsed_s=285.814239` because version 1.0.0 updates `wire.elapsed` only after recording a complete round (and at normal completion). On this failure it is the last completed-round timestamp, not the exact failure time. Future reporting should distinguish both times.

P300 recovery succeeded on the first attempt with an actual 20C2 device reply. Both previously running services reported running afterwards. This is not an independent confirmation of renewed Home Assistant data freshness for this particular long run; the user's earlier HA confirmation referred to an earlier snapshot.

### Two earlier suspicious 0xFF samples

| Item | Observation | Following P80 |
| --- | --- | --- |
| Round 142, P06, 23:08:06.612 | Raw FF; version 1.0.0 multiplies 255 by 30 and prints 7650 rpm | 20 |
| Round 222, P84, 23:08:56.490 | Raw FF; printed as phase 0xFF | 20 |
| Next round after 463, P80 | Exception reports FF instead of expected 20 | Test aborted |

Both saved anomalous samples are isolated between zero-valued samples. P09 and P10 remain zero in all 463 saved rounds. Raw histograms:

```text
P06: 462 x 00, 1 x FF
P09: 463 x 00
P10: 463 x 00
P84: 462 x 00, 1 x FF
saved-round P80: 463 x 20
```

**Do not describe 7650 rpm as a confirmed fan overspeed, or 0xFF as a newly decoded burner phase.** Preserve the raw bytes and flag these isolated samples as suspect/unresolved. A successful following P80 is not a per-sample checksum or a plausibility proof.

Device-side unavailable/error/busy signaling and transport corruption are hypotheses, not established causes. The existing data does not identify an electrical fault, EEPROM problem, burner defect, physical overspeed, changed controller variant or fixed session-duration limit. It also does not prove that 0xFF is universally invalid in every GFA data register.

The summary counters `nonzero_rounds=2` and `phase_changes=2` are explained entirely by these two suspicious samples: P06 FF once, and P84 00->FF->00. They must not be counted as two burner activities or genuine combustion-phase transitions. No convincing burner-start sequence or independently measured flame state is present in this capture.

### Timing of the saved rounds

Computed from individual JSONL receive offsets rather than the later console-print timestamps:

| Metric | Minimum | Mean | Maximum |
| --- | ---: | ---: | ---: |
| P06-to-P06 interval | 564.993 ms | 616.970 ms | 746.024 ms |
| P06-to-P84 span within a round | 318.604 ms | 369.652 ms | 511.339 ms |

The 463 guarded rounds contain 1852 runtime bytes. These counts demonstrate sustained communication before the exception, not an error-free completed 300-second measurement or a burner-cycle validation.

### Current next action - read existing evidence, do not repeat unchanged

Keep all three helper versions and original captures unchanged. Do not remove the P80 guard, silently replace FF with zero/last value, automatically retry indefinitely, or simply increase the duration to get past the failure.

First inspect the existing raw log around the three FF events. This shell block reads a saved file only and does not stop services, open a serial port or contact the boiler:

```bash
log=/root/wb2a-gfa-cycle-20260923-230628-169672.log

grep -n -B 10 -A 8 -E \
  'RX ff|Session P80 guard|OBSERVATION FAILED' \
  "$log"
```

The pasted JSONL has already been received and parsed completely; do not request the user to regenerate it. What is missing is the request/reply context and timing of the failed P80 read in the full raw log.

Follow-up implementation work should preserve raw records, represent suspect samples separately from trusted conversions, keep identity/alignment failures fatal unless a separately reviewed bounded recovery scheme is used, and report last confirmed versus actual failure time. Any changed transport pacing, controlled repeat or resynchronization needs its own explicit limited experiment; it is not justified merely by a longer observation window. The earlier successful P80/snapshot/ten-round results remain valid within their original scope.

## Source and exact implementation

Helper: [`wb2a-gfa-cycle-logger.py`](../config/optolink-splitter/wb2a-gfa-cycle-logger.py), version 1.0.0.

Implementation commit: `008e802ea8d5d0dc5a7a8658896722d37ed922da`.

SHA256:

```text
d5d98242e6f9526522a53f3c801d856ba8c1a7fde6349c05b56059fa732a54e3
```

The remote Git blob `b1d7dcf20970e47928181208b4f137491d0cf5a2` matches the locally compiled/tested script bytes. The script is an original extension of the existing project helpers, not a proprietary Vitosoft decompilation.

Two unchanged helpers must be in the same directory:

| Dependency | Required SHA256 |
| --- | --- |
| `wb2a-gfa-session-probe.py` | `32351e07cb0d661c00f7bcb7851d8103aca0b9cbc2f339041202e48b760d6da2` |
| `wb2a-gfa-p80-probe.py` | `6de883c422a09c821b342d12e5bb71dd3d518d8115ec2495bdfb202f5a7f50cb` |

The logger checks the session helper bytes before loading it; that helper checks the P80 helper. Missing or modified dependencies stop execution before systemd or serial access. The earlier successful installation leaves both dependencies in `/root` already. The snapshot helper is not required.

## Basis for the original logger

The uploaded session transcript from 2026-09-23 22:55:37 +02:00 demonstrates ten complete rounds with 40 runtime values and 11 successful in-session P80 guards, followed by a successful independent closing P80 read and P300 restoration. The response-paced burst took 6.359 seconds.

P06-to-P06 host receive intervals were 597-703 ms (mean 625.889 ms). P06-to-P84 within-round spans were 322.3-417.6 ms (mean 367.35 ms). These are empirical timings from one short all-zero capture, not guarantees for every device state, a fixed sampling rate or simultaneous acquisition. The [source-hashed session evidence](../config/optolink-splitter/research/vitosoft/gfa-session-2026-09-23-evidence.json) retains the values and timing arrays.

The new helper extends observation time, not the protocol vocabulary. Same-session GFA reads and independent entry/exit are inherited unchanged from the pinned, locally tested transport. No new GFA address, arbitrary read length, keepalive, virtual runtime read or write path is introduced.

## Fixed measurement scope

| Register | Recorded meaning |
| --- | --- |
| P06, `0x4006` | GFA-reported fan actual speed, raw x 30 rpm |
| P09, `0x4009` | GFA modulation setpoint, raw x 0.3922 percent, not RPM |
| P10, `0x400A` | Fan PWM setpoint, raw x 0.4 percent |
| P84, `0x4054` | Raw operating phase; no invented manufacturer phase names |
| P80, `0x4050` | Identity/alignment guard; must remain `0x20` |

The helper does not poll flame, temperatures, pump state, `0x55DC`, `0x55E0` or `0xA305`. It cannot assign an exact flame-establishment timestamp solely from these four channels. A phase transition is recorded as a change between two host receive times, not a proven instantaneous internal transition. Modulation/PWM/rotation are distinct quantities and do not establish delivered thermal kW.

## Sequence and time bounds

1. Check literal settings without executing the settings file. Require the splitter to be loaded and running, normal `vs1protocol=False` and no forwarding Vitoconnect adapter.
2. Create root-only capture files and verify they are writable. Acquire the same process lock as the previous helpers.
3. Pause a previously running party emulator, then the splitter. Check serial owners and use the pinned 4800 8E2 exclusive-port implementation.
4. Verify P300 identification `20C2`, then two independently synchronized P80=`20` replies.
5. Confirm same-session P80; continuously read P06/P09/P10/P84 and then P80 for each round. No artificial interval or long idle sleep is inserted.
6. After the requested window, finish the already-started round but do not start another. A six-second hard cooperative grace budget bounds that last round; the existing one-second reply timeout, 300-ms host-gap guard and a 3000-round cap also apply. The maximum user-selectable observation is 600 seconds; the first recommended run was 300 seconds, and its failure is recorded above.
7. Confirm P80 with independent synchronization, restore P300 and verify an actual checksum-valid `00F8/2 = 20C2` reply. Close the serial port, then restart only services paused by the helper and check their immediate running state.

`--seconds` is the observation window, not total service downtime. Entry, final-round completion and recovery add overhead. These bounds are cooperative checks, not an external process watchdog.

## Capture output

Each execution creates new files in `/root`, mode 0600, without overwriting previous captures:

```text
wb2a-gfa-cycle-<timestamp>-<pid>.log
wb2a-gfa-cycle-<timestamp>-<pid>.jsonl
```

The `.log` retains every TX/RX operation, individually timestamped samples, guard decisions and restoration details. Console output is reduced to one line per confirmed round, raw phase changes and lifecycle/status messages.

The `.jsonl` contains metadata, observation start, complete guarded measurement rounds and the final summary. A measurement round is written only after its P80 guard succeeds. If a timeout or invalid guard occurs halfway through a round, its partial bytes remain in the text log but are not published as a valid JSONL round. Earlier confirmed rounds are retained. As the first longer run demonstrates, passing P80 alone does not validate each preceding runtime value.

Each round stores raw bytes, declared conversions, individual host receive times, monotonic offsets from observation start, reply latency, sample span and the identity guard. Change records retain old/new bytes plus both receive times. `NONZERO_ROUNDS` is not a flame-detected count; it only counts rounds with any nonzero value among the four channels.

A successful communication window with no burner activity can legitimately contain all zeros and end with PASS. It does not constitute a burner-start experiment. The summary deliberately leaves `full_burner_cycle_verified=false` and `flame_polled=false`; determining what operating transition was actually captured is subsequent analysis.

## Tests actually performed

Python compilation and plan-only invocation passed before release. `--self-test` passed **89 offline tests**: 23 pinned P80 tests, 33 pinned session tests, and 33 logger tests. The user's first long-run transcript shows these tests passing again before device access.

The new suite checks simulated 300/600-second windows, duration bounds, complete-round-only records, raw/scaled values, chronological sample offsets, raw phase-change brackets, zero states, invalid first/per-round guards, timeout without retry, preserved previous rounds, disk-write failures, logging stalls, constructor/open/stop/close/restart/recovery failures, interruptions, inactive services, source identity gates and root-only non-overwriting output files.

Serial/systemd operations and elapsed observation time in these tests are simulated. The tests did not establish physical FF semantics or flawless long sessions. The live failure is retained as evidence rather than discounted because the tests passed.

The inherited pyserial read/write timeout behavior was checked against its official API documentation: https://pyserial.readthedocs.io/en/latest/pyserial_api.html . No pyserial upgrade or production dependency change is needed.

## Original execution procedure - historical, not the next retry instruction

The block below is preserved for reproducibility of the first run. **Review the FF failure at the top before repeating or extending it.** The next requested action is reading the saved raw log, not another service pause.

Run only in the same splitter LXC as root, with both pinned dependencies unchanged. Do not stop services beforehand, alter `vs1protocol`, run a competing serial process, force a burner start or change heating codings for a capture.

Start before a naturally expected heating cycle if practical, rather than waiting until the flame is already established. The logger does not schedule, trigger or guarantee a start. An idle or already-running capture is still useful for transport/steady-state observation, but is not a complete startup trace.

**Normal MQTT/TCP polling and the previously running party emulator are paused for the observation.** Old HA values are not contemporaneous samples. An externally maintained heat request may be affected by pausing its emulator; prefer a normal autonomous heating demand and record any observed change of operating mode. Do not attempt to maintain heating by issuing guessed commands while the logger owns the interface.

```bash
(
  set -euo pipefail
  script=/root/wb2a-gfa-cycle-logger.py
  tmp=$(mktemp)
  trap 'rm -f "$tmp"' EXIT

  curl --fail --show-error --location --retry 2 --connect-timeout 15 \
    'https://raw.githubusercontent.com/SaulGoodman1337/optolink/008e802ea8d5d0dc5a7a8658896722d37ed922da/config/optolink-splitter/wb2a-gfa-cycle-logger.py' \
    -o "$tmp"

  printf '%s  %s\n' \
    'd5d98242e6f9526522a53f3c801d856ba8c1a7fde6349c05b56059fa732a54e3' \
    "$tmp" | sha256sum -c -

  install -m 0700 "$tmp" "$script"
  /opt/optolink/venv/bin/python "$script" --self-test
  /opt/optolink/venv/bin/python -u "$script" --execute --seconds 300
)
```

No `update` is required. Without `--execute`, only the plan is printed. The helper is not installed or invoked automatically by the production updater.

At the end, retain both files printed as `LOG=` and `JSONL=`. Check `P300_RESTORED`, service restoration and the final result. Verify renewed HA updates separately; systemd active/running alone is not proof of MQTT/application health.

## Recovery and interpretation limits

Ordinary SIGINT/SIGTERM/SIGHUP enter cleanup; repeated such signals are ignored during cleanup. An interrupted observation is reported as failed/incomplete even when communication and services were successfully restored. Prefer to let an explicitly agreed bounded run finish; do not use `kill -9`.

There is no independent watchdog against SIGKILL, power loss, a hung kernel, disconnected USB or failed systemd restoration. Port-owner checks cover only processes visible in the LXC. Services are still restarted after a failed P300 recovery attempt, but the failure remains explicit. A recovery failure must be investigated before retrying.

If the helper has exited and the splitter did not restart, use the recovery instructions in [the P80 runbook](gfa-p80-probe.md); do not start another serial client while the helper still owns the port. Restore the party emulator only when the log shows it was running before this test.

A longer successful GFA log is a prerequisite for startup analysis, not proof of a permanent HA acquisition design. Concurrent normal P300 polling remains a separate integration problem. No dashboard, production poll list, heating parameter, firmware or coding-plug content is changed by this work. No helper code was changed while documenting this first failed longer run.
