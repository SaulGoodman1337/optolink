# GFA quality-run result and controlled pacing comparison

Checkpoint: **2026-09-24**.

**Current hardware result: FF quarantine and three full re-identifications worked, but FF recurred and the fourth rejection stopped the run at the configured limit.** This supersedes the pending-live-recovery wording in [the quality-logger runbook](gfa-quality-logger.md). It is not a successful 300-second observation or a resolved FF cause.

The complete log and JSONL for this run have been supplied together and analyzed. Do not request them again or repeat the same long run with a higher reconnection limit. The next explicitly proposed experiment changes only inter-request pacing.

## 1. Evidence and checks performed

Input: `Eingefügter Text(20260924-062018).txt`, 489573 bytes, 2901 lines, SHA256:

```text
a976eaac07fa52ea1b1911412e011be51a3cd59705a7d81dd5fe3a25569d431f
```

The first line is a `cat` of `wb2a-gfa-quality-20260924-081721-186325.log` and the corresponding `.jsonl`. This is user-supplied output, not a new direct device connection by the assistant.

All **171 JSON records** were parsed: one metadata record, one observation-start record, 158 accepted rounds, four rejected rounds, three re-identification starts, three completions and one summary. The accepted sequence is 1..158; including rejected attempts, the attempt sequence is 1..162. The 158 console ROUND lines match the JSON numbering and decoded values. Accepted raw/hex values, register order, guards, conversions and recorded spans were checked.

All 632 accepted runtime values are zero; all their P80 guards are 20. Accepted round counts by segment are 11, 103, 22 and 22. Every rejected round retains its raw samples and has `decoded: null`. No FF-derived RPM or phase transition appears as an accepted measurement.

The upload identifies helper version 1.1.0 and records its dependency hashes. It does not include this run's preceding download/hash-check/self-test transcript; do not claim those steps are visible here.

[Machine-readable evidence](../config/optolink-splitter/research/vitosoft/gfa-quality-run-2026-09-24-evidence.json) preserves source identity, all four events, timing, re-identifications and the original summary. No raw proprietary collector files, credentials or production settings are published.

## 2. What failed, and what worked

Observation started at **08:17:31.837 +02:00** with 300 seconds requested.

| Attempt | Channel | FF receive time | Elapsed to reception | Response latency | Action |
| ---: | --- | --- | ---: | ---: | --- |
| 12 | P84 / 0x4054 | 08:17:39.284 | 7.447 s | 49.316 ms | Reject round; re-identification 1 succeeds. |
| 116 | P10 / 0x400A | 08:18:54.099 | 82.262 s | 95.607 ms | Reject round; re-identification 2 succeeds. |
| 139 | P10 / 0x400A | 08:19:18.975 | 107.138 s | 47.085 ms | Reject round; re-identification 3 succeeds. |
| 162 | P84 / 0x4054 | 08:19:43.974 | 132.138 s | 196.625 ms | Reject round; cap reached, no fourth re-identification attempted. |

The actual failure at 08:19:44.025 is:

```text
Maximum three re-identification attempts reached; stopping.
```

It is not a failed reconnect, a P80 mismatch in this run, a 300-second deadline or a Python crash. The first FF already occurred after about 7.45 seconds, so a simple five-minute session-lifetime explanation is not supported.

Each successful re-identification established P300 00F8/2=20C2, two independently synchronized P80=20 replies and a same-session P80=20 before resuming. Durations were **10.886413, 10.950023 and 10.887411 seconds**. The corresponding gaps from the previous accepted-round recording to re-entry completion were **11.371095, 11.336470 and 11.254067 seconds**. These are measured gaps, not uninterrupted observation.

At final cleanup:

```text
08:19:46.089  P300 identity = 20c2
08:19:48.172  optolink-splitter.service running
08:19:50.245  optolink-party-emulator.service running
```

The splitter was paused for approximately 147.121 seconds including setup, re-entry and final cleanup. The summary reports 132.188506 seconds of the requested observation and `RESULT=FAIL`, with restoration flags true.

`P80_CONFIRMED=NOT_CONFIRMED` is the overall completion/closing-identity result after abort. It must not be read as an observed P80=FF in this run: all eight independent P80 replies and all 162 same-session P80 replies present in this log were 20. The final independent GFA check was not reached; P300 restoration was separately verified.

Renewed Home Assistant freshness was not independently reported for this specific run. A running systemd service and a recovered P300 link are not a complete MQTT/application health measurement.

### Interpretation boundary

The quality policy now demonstrably prevents the known FF values from being published as RPM/PWM/phase measurements, and the full re-entry sequence has worked three times on hardware. It does **not** remove or explain FF. All accepted channels are zero, so this run supplies no convincing burner-start trace and no independent flame timestamp.

The pauses preceding the four FF requests were approximately **51.101, 50.767, 50.339 and 50.799 ms**, measured from the previous reply to the next request. The addresses and lengths are the expected one-byte reads. No terminal timeout, queued-byte, trailing-byte or host-gap exception appears. Internal data unavailability and physical/serial corruption remain hypotheses, not diagnoses.

The FF-to-FF receive intervals are 74.814987, 24.875964 and 24.999339 seconds. Their resemblance to multiples of 25 seconds is worth retaining as a lead, but four events with interrupted coverage do not establish a periodic firmware job or timeout. Neither changing the retry cap nor asserting a timer is a source-backed solution.

## 3. Baseline timing for a pacing comparison

Calculated from accepted JSONL samples, excluding transitions between segments:

| Metric | Minimum | Mean | Maximum | Count |
| --- | ---: | ---: | ---: | ---: |
| P06-to-P06 receive interval | 563.862 ms | 617.564 ms | 720.265 ms | 154 |
| P06-to-P84 within-round span | 318.576 ms | 369.690 ms | 508.348 ms | 158 |
| Accepted runtime reply latency | 53.911 ms | 72.459 ms | 158.264 ms | 632 |

Do not compare errors solely per wall-clock minute: slower pacing changes the number of reads, and re-identification periods also remove observation coverage. Per-request counts, attempted channels, duration, state and gaps must be retained. A later clean run would improve evidence, not prove FF permanently fixed.

## 4. Next helper: minimum 150-ms reply-to-request spacing

Helper: [`wb2a-gfa-paced-probe.py`](../config/optolink-splitter/wb2a-gfa-paced-probe.py), experiment version **1.0.0**.

Implementation commit: `3a9bfccc2cfcf7562fce50c47715490eea1adfa6`.

SHA256:

```text
053c7806d863c7fe551903a24498f4841c0d2235b661e674f80f07696065e974
```

The read-back Git blob `1091aae156c9c24bea6b6a8240e1405ffc1d225d` matches the locally tested script bytes.

**Status: implemented and offline-tested; 150-ms pacing has not yet been tested on this appliance.** The value is a deliberate comparison setting, NOT a recovered Viessmann timing requirement or evidence that excessive request rate caused FF.

The only intentional acquisition change is a minimum **150 ms from receipt of the preceding VS1 reply to transmission of the next same-session read**, instead of the approximately 51 ms visible in the baseline. It is not an extra 150 ms on top of the existing interval, and not a change to pyserial's read timeout. Expected sample rate will be lower, but no fixed rate is promised.

Unchanged:

- the five read addresses and exact frame allowlist;
- full-round FF quarantine, raw retention and no invented replacement values;
- at most three full re-identifications, plus the ten-clean-round condition;
- fatal handling of other identity, timeout, queued/trailing-byte or partial-write errors;
- maximum 300-ms host idle-gap guard, checked during and after pacing;
- exclusive serial ownership, deliberate service pause and P300 restoration.

The wait is broken into short intervals so existing queued-byte/deadline/host-gap checks remain active. It does not consume unexplained data or modify `last_reply` to disguise a scheduling stall. The request timestamp is taken after the wait, so recorded device reply latency does not include intentional pacing.

A new field, `rx_to_next_tx_gap_ms`, retains the actual previous-reply-to-request gap for accepted and rejected samples. Record metadata identifies `experiment=reply_gap_150ms`, `experiment_version=1.0.0` and `minimum_reply_gap_ms=150`. The inherited quality implementation may still report its library version 1.1.0; that is distinct from the experiment version.

No long block reads, new keepalive, parameter write, forced burner start or production HA entity is introduced. This comparison is bounded to **30..300 seconds**, not 600 seconds.

## 5. Dependencies and offline verification

Four existing files must remain unchanged beside the new helper in `/root`:

| File | Required SHA256 |
| --- | --- |
| `wb2a-gfa-quality-logger.py` | `bdd1d829ba2d1387c21ae99e02848755e7ad8045c0b3034ff7430eb555900910` |
| `wb2a-gfa-cycle-logger.py` | `d5d98242e6f9526522a53f3c801d856ba8c1a7fde6349c05b56059fa732a54e3` |
| `wb2a-gfa-session-probe.py` | `32351e07cb0d661c00f7bcb7851d8103aca0b9cbc2f339041202e48b760d6da2` |
| `wb2a-gfa-p80-probe.py` | `6de883c422a09c821b342d12e5bb71dd3d518d8115ec2495bdfb202f5a7f50cb` |

The new wrapper verifies the quality helper before loading it, which verifies its dependencies in turn. A mismatch stops before service/serial operations. Previous scripts, controller settings and production updater paths are not modified.

Compilation, default plan-only execution and invalid-duration rejection passed. The embedded self-test passed **125 offline tests**: 109 inherited tests and 16 new test methods. The new tests cover measured spacing, device latency excluding sleep, FF at each channel, failed/early re-entry inherited behavior, unchanged allowlist, queued bytes arriving during waits, host/console stalls, deadlines, interruptions, inactive party state and simulated 300-second completion.

All serial, service and observation-time behavior in these tests is simulated. They do not demonstrate successful live pacing or resolve FF semantics. pyserial API reference for the distinction between read timeout and received data: https://pyserial.readthedocs.io/en/latest/pyserial_api.html .

## 6. Explicit execution

Run in the same LXC as root. Keep all previous helpers unchanged. Do not stop services beforehand, alter `vs1protocol`, use another serial client concurrently or force a burner start. Normal autonomous operation is appropriate; no flame/activity requirement is imposed for this transport comparison.

Normal HA/MQTT/TCP polling and the active party emulator pause for the observation plus setup/final restoration. Old HA values are not live samples. Pausing an externally maintaining emulator may change its request; it is not operationally invisible just because no parameter write is sent.

```bash
(
  set -euo pipefail
  script=/root/wb2a-gfa-paced-probe.py
  tmp=$(mktemp)
  trap 'rm -f "$tmp"' EXIT

  curl --fail --show-error --location --retry 2 --connect-timeout 15 \
    'https://raw.githubusercontent.com/SaulGoodman1337/optolink/3a9bfccc2cfcf7562fce50c47715490eea1adfa6/config/optolink-splitter/wb2a-gfa-paced-probe.py' \
    -o "$tmp"

  printf '%s  %s\n' \
    '053c7806d863c7fe551903a24498f4841c0d2235b661e674f80f07696065e974' \
    "$tmp" | sha256sum -c -

  install -m 0700 "$tmp" "$script"
  /opt/optolink/venv/bin/python "$script" --self-test
  /opt/optolink/venv/bin/python -u "$script" --execute --seconds 300
)
```

No `update` or collector rerun is needed. Default invocation is plan-only. `--self-test` does not access the boiler. The explicit device execution produces `/root/wb2a-gfa-paced-<timestamp>-<pid>.log` and `.jsonl`, both root-only, without overwriting prior captures.

The result meanings remain PASS/exit 0, COMPLETE_WITH_GAPS/exit 2 and FAIL/exit 1. Gaps are not hidden, and a successfully restored service does not upgrade a failed observation. Ordinary interruptions invoke cleanup; there is still no independent watchdog or unconditional recovery under SIGKILL, power loss, USB/kernel or systemd failure.

Inspect the next actual log for verified gap measurements, FF counts and positions, accepted versus rejected records and final recovery. Do not increase retry limits if FF recurs. Preserve both output files; the entire input for the current analysis has already been received.

## 7. Remaining conclusions

Quality/re-entry success is now hardware-supported, but production reliability, actual flame timing, a complete startup trace and permanent HA integration remain open. The first FF after 7.45 seconds and recurrences after successful re-entry mean that repeatedly resetting the session alone is not a demonstrated cure.

A future improvement with changed pacing would support a timing-related hypothesis; it would not distinguish every device-internal versus physical-link cause. A failure would likewise not prove hardware defective. The suspected timing pattern, physical-link diagnostics and source-level sentinel/validity investigation remain separate possible follow-ups. Firmware acquisition, E7 persistence, pump override and coding-plug modification remain separate tasks, not implied results of this transport work.
