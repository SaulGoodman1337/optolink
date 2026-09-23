# GFA live checkpoint - 2026-09-23

**Current status: P80 and P06/P09/P10/P84 have been read successfully on the local WB2A. Burner-off and burner-on snapshots differ as expected; the burner-on P06 value decodes to 4110 rpm.**

This checkpoint supersedes older statements that only P80 has been hardware-tested. It does not establish independent tachometer calibration, a complete phase enum, continuous high-rate sampling or permanent Home Assistant integration.

Primary new evidence: [source-hashed snapshot comparison](../config/optolink-splitter/research/vitosoft/gfa-snapshots-2026-09-23-evidence.json). Static source definitions remain in [the collector evidence](../config/optolink-splitter/research/vitosoft/private-archive-2026-09-23-evidence.json). The collector analysis describes an earlier static-only checkpoint, not these later hardware runs.

## 1. First P80 hardware result

Source: the user's pasted LXC console transcript naming `/root/wb2a-gfa-p80-20260923-223259-168588.log`; the separately stored log file was not fetched.

Tested helper: `wb2a-gfa-p80-probe.py` 1.0.0, commit `ab32e2d2fe2c165390d7098dcffc4bb2e097543d`, SHA256 `6de883c422a09c821b342d12e5bb71dd3d518d8115ec2495bdfb202f5a7f50cb`.

Environment: Python 3.13.5 / pyserial 3.5, configured CP2102 by-id adapter resolving to `/dev/ttyUSB0`, 4800 8E2, `vs1protocol=False`, no Vitoconnect forwarding adapter. The second USB adapter was not selected.

Observed local times (+02:00):

| Time | Observation |
| --- | --- |
| 22:32:59.146 / .172 | Previously running party emulator and splitter stopped. |
| 22:33:01.258 | Baseline P300 Virtual_READ 00F8/2 returned `20 c2`. |
| 22:33:05.495 -> .595 | `01 6b 40 50 01` -> `20`. |
| 22:33:09.880 -> 22:33:10.027 | Independently synchronized repeat -> `20`. |
| 22:33:12.139 | P300 restored and 00F8/2 again returned `20 c2`. |
| 22:33:14.167 / 22:33:16.210 | Splitter and party emulator reported running; PASS. |

Both GFA reads used EOT, interface-detection ENQ, a fresh VS1 ENQ and STX plus the read command. The complete P300 response frame excluding ACK was `41 07 01 01 00 f8 02 20 c2 e5` before and after the test.

This established the local P80 `0x20` GFA variant and the independently synchronized read/recovery path. The original [P80 runbook](gfa-p80-probe.md) retains the implementation and recovery details. Its original helper is unchanged.

## 2. Burner-off and burner-on snapshots

Source: two uploaded console transcripts. Burner off/on is explicitly reported by the user; the snapshot helper does not independently poll flame state. No claim is made that the separate `/root/*.log` files were fetched, or that both states were imposed by the assistant.

Helper: [`wb2a-gfa-snapshot.py`](../config/optolink-splitter/wb2a-gfa-snapshot.py) 1.0.0, commit `8e9b2271c0bbc4bc8691f2778720a444e9f26476`, SHA256 `b8a89bae4a7dbcc4047b115d9c733f596f0e3a9a60d8025db7a86e1c9caf0141`. Both user runs passed the hash check and the 23 base plus 22 snapshot self-tests before actual serial access.

The original snapshot helper remains unchanged. It verifies the pinned P80 helper before loading it, reuses settings/port checks and restoration, and reads each register with independent synchronization. All helpers use the same process lock.

### Measurements

| Register | Burner off: raw -> decoded | Burner on: raw -> decoded | Burner-on SAMPLE timestamp |
| --- | --- | --- | --- |
| P06 / 0x4006 | `00` -> 0 rpm | `89` = 137 -> **4110 rpm** | 22:45:07.923 |
| P09 / 0x4009 | `00` -> 0% | `7b` = 123 -> **48.2406% modulation setpoint** | 22:45:12.268 |
| P10 / 0x400A | `00` -> 0% | `67` = 103 -> **41.2% fan PWM setpoint** | 22:45:16.612 |
| P84 / 0x4054 | `00` | **`06`** | 22:45:20.978 |

The burner-off SAMPLE timestamps are 22:42:17.349, 22:42:21.802, 22:42:26.242 and 22:42:30.667 respectively. The JSON preserves all raw values, exact timestamps, reply latencies and source hashes.

The source definitions for the locally selected GFA variant are events 8175 (P06, x30 rpm), 8259 (P09, x0.3922%), 8179 (P10, x0.4%) and 8208 (P84 raw). P09 is not a blower-RPM setpoint in this variant.

### Communication and recovery

| Check | Burner-off run | Burner-on run |
| --- | --- | --- |
| Transcript-named log | `wb2a-gfa-snapshot-20260923-224201-168882.log` | `wb2a-gfa-snapshot-20260923-224452-168983.log` |
| P80 samples, including closing guard | `20 / 20 / 20` | `20 / 20 / 20` |
| P300 identity before/after | `20c2 / 20c2` | `20c2 / 20c2` |
| Runtime reads | 4/4 | 4/4 |
| P300 restored, splitter restarted | yes / yes | yes / yes |
| Party emulator restored | yes | yes |
| Final result | PASS | PASS |
| Total logged duration | 39.126 s | 38.804 s |
| Splitter stop -> reported running | 37.058 s | 36.735 s |
| P06 -> P84 SAMPLE line span | 13.318 s | 13.055 s |

The user explicitly reported that Home Assistant supplies values again after the first run. The second transcript confirms restoration of both services, but the same message does not separately confirm Home Assistant freshness after that second run. Do not upgrade systemd state alone into an application-level health measurement.

### Interpretation supported by the comparison

The four data addresses are locally readable, not merely entries in a metadata file. They returned zeros in the user-reported idle run and nonzero values in the user-reported firing run. This supports meaningful operating-state dependence and, combined with the exact P06 definition, a usable GFA-reported fan-speed reading.

The RPM calculation is `0x89 = 137; 137 * 30 = 4110`. It is not an independent optical/tachometer measurement or full-range calibration. The obsolete `0x55D3[6:7] = rpm` interpretation remains rejected.

P09 and P10 are different command quantities, and were also sampled at different times. Their 48.2406% versus 41.2% values are not a percentage mismatch that by itself indicates a fault. Modulation is not measured thermal kW. No simultaneous 0x55DC/0xA305 trace was supplied, so direct equality or conversion between them and P09 remains to be tested.

P84=00 was observed in the idle snapshot; P84=06 was observed in the user-reported firing snapshot. Those are behavioral observations, not a recovered vendor enum. Do not label 06 as a proven exclusive steady-state regulation phase or infer the whole state machine from two points. Here the `RX 06` after the VS1 P84 command is processed as the one-byte register reply, not as a P300 ACK from a different protocol context.

The four measurements are sequential and span about 13 seconds. They cannot determine what happened within the approximately 12-second startup plateau, prove a fan/modulation relationship at one common instant, or establish whether the burner was at its heating minimum, heating start, or DHW state. Those contextual details were not captured.

## 3. Next test: bounded same-session access

New helper: [`wb2a-gfa-session-probe.py`](../config/optolink-splitter/wb2a-gfa-session-probe.py) 1.0.0.

Implementation commit: `3b9bb24e035034745b3b3949ad0a86817985597a`.

SHA256:

```text
32351e07cb0d661c00f7bcb7851d8103aca0b9cbc2f339041202e48b760d6da2
```

Git blob `db2ecc6e44261f5dd052747c350511f16afcc016` was read back from that commit and matches the locally compiled/tested file. It depends only on the unchanged, SHA256-pinned `wb2a-gfa-p80-probe.py` beside it; the snapshot script is not a dependency.

**Status: implemented and offline-tested; same-session sequence not yet locally hardware-tested.** A successful independently synchronized snapshot does not establish that commands can be issued back-to-back without another EOT/ENQ/STX cycle. This is the deliberately narrow new question.

### Source basis

The relevant host-code methods were re-read from the supplied private archive without executing Vitosoft:

- `VS1Message::toByteArray`, particularly IL lines 285-322: GFA reads serialize function, high address, low address and length, without a per-message STX.
- `VS1::_timer_processor_Elapsed`, around lines 985-1099: connection setup and message processing are distinct states; normal messages and keepalive use the active connection.
- `VS1::sendVS1Message`, around lines 1283-1510, especially 1331-1341: writes the serialized message and gathers the expected raw reply.
- `VS1::sendKeepVS1Message`, around 1513 onward: a separate keepalive path exists; this helper does not add its commands or use arbitrary keepalives.

Source file: `tool-dumps/ildasm/MobileClient_vsmInterfaceCore.dll.il` in the private archive with SHA256 `50f8215ea74b1d507c78d28294814db1a5fc65683b3308f23057a2fce8bb4daa`. Full proprietary IL is not published. pyserial timeout and buffer behavior was checked against its official API reference, https://pyserial.readthedocs.io/en/latest/pyserial_api.html .

### Fixed sequence and restrictions

1. Verify settings and configured port; pause the previously running party emulator and splitter. Own the port exclusively, as in the successful helpers.
2. Verify P300 identity 20C2 and perform two independently synchronized P80=20 reads.
3. Read P80 once more **in the same VS1 session**, using `6b 40 50 01` without new STX or EOT. Abort before runtime reads if this fails.
4. Perform exactly ten response-paced rounds of P06, P09, P10 and P84, followed each time by a P80=20 guard. No deliberate sleep between rounds, no fixed sampling-rate promise.
5. Finish with independently synchronized P80, verified P300 00F8/2 readback and restoration of previously running services.

The only added transmissions are the four-byte GFA_READ requests for already locally read P80/P06/P09/P10/P84. No new data addresses, long block reads, coding writes, GFA writes, EEPROM writes, process writes, burner-start commands or actuator tests are enabled.

There is a cooperative 20-second budget for the burst itself, excluding entry and recovery. A 300-ms host idle-gap guard prevents blind continuation after a scheduling/logging stall; this is a conservative helper limit, not a measured WB2A firmware timeout. Unexpected queued data, trailing data, mismatched P80, partial writes or reply timeout stop the test without automatic retransmission or same-session resynchronization. P300 recovery remains separately bounded to two attempts.

The five reads per round remain sequential. Raw values, host receive timestamps and measured timing are logged. Samples are initially marked `round_guard=pending`; only the following `ROUND_CONFIRMED` establishes that round's P80 guard passed. A P80 guard improves alignment checking but is not a checksum for every raw VS1 sample. Unknown phase values, including data bytes numerically equal to control characters, remain raw rather than being silently filtered out.

### Offline verification actually performed

Compilation, plan-only invocation and **56 passing offline tests**: the unchanged base's 23 tests plus 33 new tests. The new suite checks exact command sequence, allowlist, wrong identities, first-guard failure before runtime access, per-round guard failure, no retry on timeout, trailing/queued data, host-gap/deadline handling, logging stalls, zero values, control-valued raw bytes, scaling, interrupts, partial writes, open/stop/recovery/close/restart failures and initially inactive services.

All tests simulate serial/systemd and time. They do not establish actual persistent-session timing, kernel/USB behavior on the user's host, full-cycle stability, MQTT health or physical fan calibration.

### Execute in the same LXC as root

Leave the existing `/root/wb2a-gfa-p80-probe.py` unchanged. Do not stop services first, change `vs1protocol`, or use another serial program concurrently. Normal idle or stable firing is acceptable; do not deliberately force a burner start or change parameters to obtain nonzero values. This test concerns transport reuse, not completion of a burner cycle.

```bash
(
  set -euo pipefail
  script=/root/wb2a-gfa-session-probe.py
  tmp=$(mktemp)
  trap 'rm -f "$tmp"' EXIT

  curl --fail --show-error --location --retry 2 --connect-timeout 15 \
    'https://raw.githubusercontent.com/SaulGoodman1337/optolink/3b9bb24e035034745b3b3949ad0a86817985597a/config/optolink-splitter/wb2a-gfa-session-probe.py' \
    -o "$tmp"

  printf '%s  %s\n' \
    '32351e07cb0d661c00f7bcb7851d8103aca0b9cbc2f339041202e48b760d6da2' \
    "$tmp" | sha256sum -c -

  install -m 0700 "$tmp" "$script"
  /opt/optolink/venv/bin/python "$script" --self-test
  /opt/optolink/venv/bin/python -u "$script" --execute
)
```

No `update` is needed and no experiment is run by the normal updater. The new root-only log is `/root/wb2a-gfa-session-<timestamp>-<pid>.log`. Without `--execute`, the helper prints its plan only. Missing/modified dependency bytes are rejected before service or serial changes.

Successful example, not an observed result of this new helper:

```text
SESSION_ROUNDS=10/10
P80_CONFIRMED=0x20 GFA
P300_RESTORED=yes
SPLITTER_RESTARTED=yes
RESULT=PASS
```

On failure retain the complete log and do not repeat blindly. During the test normal MQTT/TCP updates and the active party-emulator service are paused. Ordinary SIGINT/SIGTERM/SIGHUP enter cleanup, but there is no independent watchdog and no guarantee against SIGKILL, power loss, USB failure or unsuccessful systemd recovery. Port-owner inspection is limited to the visible process namespace. After the helper exits, service state and actual Home Assistant updates remain distinct health checks.

## 4. Following work and interpretation boundary

If the same-session test succeeds, develop a bounded full-cycle observation logger using measured timing. Its first goal is to correlate P06/P09/P10/P84 through a natural start, stabilization, modulation and stop, not modify combustion. Determine separately whether/how to obtain synchronized flame/0x55DC/0x55E0 observations while VS1 owns the interface. Existing P300 MQTT loggers cannot run concurrently through a stopped splitter and do not supply contemporaneous data merely because old HA values remain visible.

Only after transport and interpretation validation should permanent Home Assistant acquisition be designed. A second independent serial process competing with the splitter is not an acceptable permanent integration. Integration requires explicit ownership/scheduling of mode switches or another proven acquisition architecture.

GFA firmware identity/coding-plug diagnostics, E7 persistence, internal-pump request selection, full firmware acquisition and M2 remain separate workstreams. These successful fan/status reads do not resolve them by implication. Production profiles, dashboard YAML, heating parameters and installer/updater behavior were not changed in this step.
