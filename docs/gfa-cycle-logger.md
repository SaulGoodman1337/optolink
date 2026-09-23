# WB2A bounded GFA observation logger

Status: **implemented and offline-tested; first minutes-long local observation pending**.

This advances the successful ten-round session experiment recorded in [GFA live checkpoint](gfa-live-checkpoint.md). It does not imply that a complete burner cycle has already been captured.

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

## Why the logger is now justified

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
6. After the requested window, finish the already-started round but do not start another. A six-second hard cooperative grace budget bounds that last round; the existing one-second reply timeout, 300-ms host-gap guard and a 3000-round cap also apply. The maximum user-selectable observation is 600 seconds; the first recommended run is 300 seconds.
7. Confirm P80 with independent synchronization, restore P300 and verify an actual checksum-valid `00F8/2 = 20C2` reply. Close the serial port, then restart only services paused by the helper and check their immediate running state.

`--seconds` is the observation window, not total service downtime. Entry, final-round completion and recovery add overhead. These bounds are cooperative checks, not an external process watchdog.

## Capture output

Each execution creates new files in `/root`, mode 0600, without overwriting previous captures:

```text
wb2a-gfa-cycle-<timestamp>-<pid>.log
wb2a-gfa-cycle-<timestamp>-<pid>.jsonl
```

The `.log` retains every TX/RX operation, individually timestamped samples, guard decisions and restoration details. Console output is reduced to one line per confirmed round, raw phase changes and lifecycle/status messages.

The `.jsonl` contains metadata, observation start, complete guarded measurement rounds and the final summary. A measurement round is written only after its P80 guard succeeds. If a timeout or invalid guard occurs halfway through a round, its partial bytes remain in the text log but are not published as a valid JSONL round. Earlier confirmed rounds are retained.

Each round stores raw bytes, declared conversions, individual host receive times, monotonic offsets from observation start, reply latency, sample span and the identity guard. Change records retain old/new bytes plus both receive times. `NONZERO_ROUNDS` is not a flame-detected count; it only counts rounds with any nonzero value among the four channels.

A successful communication window with no burner activity can legitimately contain all zeros and end with PASS. It does not constitute a burner-start experiment. The summary deliberately leaves `full_burner_cycle_verified=false` and `flame_polled=false`; determining what operating transition was actually captured is subsequent analysis.

## Tests actually performed

Python compilation and plan-only invocation passed. `--self-test` passed **89 offline tests**: 23 pinned P80 tests, 33 pinned session tests, and 33 logger tests.

The new suite checks simulated 300/600-second windows, duration bounds, complete-round-only records, raw/scaled values, chronological sample offsets, raw phase-change brackets, zero states, invalid first/per-round guards, timeout without retry, preserved previous rounds, disk-write failures, logging stalls, constructor/open/stop/close/restart/recovery failures, interruptions, inactive services, source identity gates and root-only non-overwriting output files.

Serial/systemd operations and elapsed observation time in these tests are simulated. No live appliance command was executed by the assistant while developing this logger. The offline tests do not establish minutes-long physical session stability, actual USB behavior, HA freshness or a burner-start timeline.

The inherited pyserial read/write timeout behavior was checked against its official API documentation: https://pyserial.readthedocs.io/en/latest/pyserial_api.html . No pyserial upgrade or production dependency change is needed.

## Run the first observation

Run in the same splitter LXC as root. Leave both pinned dependencies unchanged. Do not stop services beforehand, alter `vs1protocol`, run a competing serial process, force a burner start or change heating codings for this capture.

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

Ordinary SIGINT/SIGTERM/SIGHUP enter cleanup; repeated such signals are ignored during cleanup. An interrupted observation is reported as failed/incomplete even when communication and services were successfully restored. Prefer to let the bounded run finish; do not use `kill -9`.

There is no independent watchdog against SIGKILL, power loss, a hung kernel, disconnected USB or failed systemd restoration. Port-owner checks cover only processes visible in the LXC. Services are still restarted after a failed P300 recovery attempt, but the failure remains explicit. A recovery failure must be investigated before retrying.

If the helper has exited and the splitter did not restart, use the recovery instructions in [the P80 runbook](gfa-p80-probe.md); do not start another serial client while the helper still owns the port. Restore the party emulator only when the log shows it was running before this test.

A longer successful GFA log is a prerequisite for startup analysis, not proof of a permanent HA acquisition design. Concurrent normal P300 polling remains a separate integration problem. No dashboard, production poll list, heating parameter, firmware or coding-plug content is changed by this work.
