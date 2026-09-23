# GFA live checkpoint - 2026-09-23

**Current status: the first recorded local VS1 GFA P80 read succeeded twice.**

This checkpoint supersedes the older "first hardware execution pending" wording in the collector analysis and P80 runbook for **P80 only**. Runtime P06/P09/P10/P84 access, rapid logging and permanent Home Assistant integration are not yet hardware-validated.

## 1. Evidence from the actual appliance

Source: the user's pasted console transcript from the Optolink-Splitter LXC, not a simulated self-test. The transcript names `/root/wb2a-gfa-p80-20260923-223259-168588.log`; the separately stored log file was not fetched in this step.

Tested helper: `wb2a-gfa-p80-probe.py` version 1.0.0, commit `ab32e2d2fe2c165390d7098dcffc4bb2e097543d`, SHA256 `6de883c422a09c821b342d12e5bb71dd3d518d8115ec2495bdfb202f5a7f50cb`.

The user's download passed its hash check and all 23 embedded offline tests before the live run.

Local environment: Python 3.13.5 / pyserial 3.5, configured CP2102 by-id adapter resolving to `/dev/ttyUSB0`, 4800 8E2, `vs1protocol=False`, no Vitoconnect forwarding adapter. A different USB adapter was not used.

### Key observed events, Europe/Berlin (+02:00)

| Time | Actual observation |
| --- | --- |
| 22:32:59.146 | Running party emulator stopped. |
| 22:32:59.172 | Running splitter stopped. |
| 22:33:01.258 | P300 Virtual_READ 00F8/2 returned `20 c2`. |
| 22:33:05.495 | First synchronized VS1 request: `01 6b 40 50 01`. |
| 22:33:05.595 | First raw GFA reply: `20`. |
| 22:33:09.880 | Second independently synchronized request: `01 6b 40 50 01`. |
| 22:33:10.027 | Second raw GFA reply: `20`. |
| 22:33:12.139 | P300 restored; actual Virtual_READ 00F8/2 again returned `20 c2`. |
| 22:33:14.167 | Splitter reported running after restart. |
| 22:33:16.210 | Party emulator reported running after restart; final result PASS. |

The complete P300 response frame, excluding its leading acknowledgement, was the same before and after GFA access:

```text
41 07 01 01 00 f8 02 20 c2 e5
```

Both GFA reads used EOT `04`, an interface-detection ENQ `05`, a fresh VS1 ENQ `05`, then the STX-prefixed read. This independently synchronized sequence is now locally demonstrated, rather than only reconstructed from Vitosoft IL.

The final live status was:

```text
P80_RESULT=0x20 GFA
P300_RESTORED=yes
SPLITTER_RESTARTED=yes
RESULT=PASS
```

### What is established

- The local `VDensHO1 / 20C2` accepts this VS1 `GFA_READ` P80 request.
- P80 returned the same `0x20` byte in two separate synchronized sessions.
- This matches the GFA branch selected by Vitosoft's P80 display conditions, not the CES, SCOT or DOVER branches.
- Returning to P300 worked in this run and was verified with a real, checksum-validated device reply.
- Both previously running services were restored to systemd active/running state.

### What is NOT established yet

- Readability or physical plausibility of any other GFA register.
- Actual fan RPM, GFA phase names or a complete status-bit dictionary.
- A persistent VS1 session that can sample several registers rapidly without fresh synchronization.
- MQTT/Home Assistant data freshness after restart; systemd running alone is not an application-level health check.
- An unconditional recovery guarantee after power loss, SIGKILL, USB loss or systemd failure.
- A firmware flashing/readout path or a new pump override.

No parameter, setpoint, GFA control value, EEPROM or process write was involved.

## 2. Next helper: bounded four-register snapshot

Implementation: [`wb2a-gfa-snapshot.py`](../config/optolink-splitter/wb2a-gfa-snapshot.py).

Commit: `8e9b2271c0bbc4bc8691f2778720a444e9f26476`.

SHA256:

```text
b8a89bae4a7dbcc4047b115d9c733f596f0e3a9a60d8025db7a86e1c9caf0141
```

The committed blob `62213a111dc12e5f02575c111c94114edc675011` matches the compiled/tested local file.

The successful original P80 helper is deliberately unchanged. The new helper requires it beside the snapshot script, verifies its complete SHA256 before loading it, and reuses its settings parsing, port ownership checks, serial settings, logging and P300 parser. It does not import the production splitter or execute the settings file. Both helpers share the same process lock, preventing concurrent local probe runs.

### Fixed scope

| Register | GFA-branch interpretation from the collector | Output field |
| --- | --- | --- |
| P06, 0x4006 | Actual fan speed, raw x 30 rpm | `fan_actual_rpm` |
| P09, 0x4009 | Modulation setpoint, raw x 0.3922 percent; NOT RPM | `modulation_setpoint_pct` |
| P10, 0x400A | Fan PWM setpoint, raw x 0.4 percent | `fan_pwm_setpoint_pct` |
| P84, 0x4054 | Operating phase; no validated name table | `phase_raw` |

These are source-derived interpretations, not newly observed measurements. The source entries are recorded in [the collector evidence](../config/optolink-splitter/research/vitosoft/private-archive-2026-09-23-evidence.json), events 8175, 8259, 8179 and 8208.

The helper performs: P300 baseline; two P80=0x20 checks; one read each of P06/P09/P10/P84; closing P80=0x20 check; P300 verification and restoration of previously running services. It aborts before runtime reads for any other variant.

Every GFA read uses exactly the independent synchronization strategy that succeeded above. There is no arbitrary address or length option, no loop duration, no automatic burner start and no write function. Runtime timeouts or unexpected trailing data stop the sequence rather than trying additional addresses.

**The four samples are taken sequentially with fresh synchronization, not simultaneously.** This is an access/plausibility check, not a one-second-resolution burner-start logger. Do not infer the timing or causal relationship of fast phase changes from this snapshot.

Raw bytes, decoded values, timestamps and reply latencies are retained in the log. Values are not silently clamped: for example, declared factors can produce 100.0110 percent or 102.0 percent at raw 255. Such an output requires interpretation and is not automatically a physical setpoint above the nominal limit. Unknown phase values remain raw. A raw VS1 byte has no P300-style checksum; a one-byte response alone does not independently prove measurement semantics. Its future correlation across operating states remains necessary.

### Tests actually performed

Python compilation passed. `--self-test` ran **45 passing offline tests**: 23 from the unchanged P80 helper plus 22 for snapshot framing, decoding, allowlist rejection, variant guards, zero values, unclamped values, trailing data, timeouts, interrupts, serial/service failures and restoration. Default invocation prints a plan and performs no serial or systemd operation.

Tests use fake ports/services and a simulated clock. They do not replace actual hardware validation of these four registers. No live appliance command was run by the assistant while preparing this helper.

pyserial's read/write timeout semantics were checked against its official API documentation: https://pyserial.readthedocs.io/en/latest/pyserial_api.html

## 3. First snapshot execution

Run in the same LXC as root. The existing `/root/wb2a-gfa-p80-probe.py` from the successful test is required; leave it unchanged. The helper refuses a missing or different-hash dependency before changing any service.

Do not stop the splitter beforehand, change `vs1protocol`, or run another serial program at the same time. Prefer a naturally occurring stable burner state for meaningful runtime values; an idle snapshot is also useful as a baseline. Do not force a start, change codings or use an actuator test just to obtain nonzero values.

During the test, the splitter and an active party emulator are paused, so their normal polling/control service is temporarily unavailable. Leave the helper's cleanup to complete. Ordinary SIGINT/SIGTERM/SIGHUP enter cleanup, but there is no separate watchdog against SIGKILL, host failure or disconnected hardware.

```bash
(
  set -euo pipefail
  script=/root/wb2a-gfa-snapshot.py
  tmp=$(mktemp)
  trap 'rm -f "$tmp"' EXIT

  curl --fail --show-error --location --retry 2 --connect-timeout 15 \
    'https://raw.githubusercontent.com/SaulGoodman1337/optolink/8e9b2271c0bbc4bc8691f2778720a444e9f26476/config/optolink-splitter/wb2a-gfa-snapshot.py' \
    -o "$tmp"

  printf '%s  %s\n' \
    'b8a89bae4a7dbcc4047b115d9c733f596f0e3a9a60d8025db7a86e1c9caf0141' \
    "$tmp" | sha256sum -c -

  install -m 0700 "$tmp" "$script"
  /opt/optolink/venv/bin/python "$script" --self-test
  /opt/optolink/venv/bin/python -u "$script" --execute
)
```

No `update` is needed. The new log is `/root/wb2a-gfa-snapshot-<timestamp>-<pid>.log`, created with mode 0600. Inspect all four `SAMPLE` lines, the closing identity, `P300_RESTORED`, service restoration and the final `RESULT`.

`RESULT=PASS` means the bounded request sequence and cleanup succeeded, not that all scaling/phase semantics are physically validated. On failure, preserve the full log and do not repeat blindly. Once the helper exits, confirm Home Assistant resumes normal updates separately from the systemd status.

## 4. Following work

After real snapshot results: validate nonzero P06 against ordinary burner operation and compare P09/P10 with known modulation behavior. Only then review a persistent-session logger for finer timing. Such a logger must preserve exclusive ownership and recovery; it cannot be added to normal MQTT polling as though GFA_READ were an ordinary P300 virtual read.

Keep GFA firmware identity/coding-plug diagnostics, E7 persistence, pump request selection and firmware acquisition as separate subsequent tasks. This successful P80 experiment does not resolve them by implication.
