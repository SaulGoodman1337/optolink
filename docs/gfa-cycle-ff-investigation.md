# GFA long observation: isolated FF values and guard failure

Status: **first 300-second observation failed before completion; P300 and both services were restored**.

Date: 2026-09-23, local times Europe/Berlin (+02:00).

This result supersedes the pending-first-observation status in the earlier [logger runbook](gfa-cycle-logger.md). It does not revoke the successful short P80, snapshot or same-session tests. However, continuous acquisition is not yet suitable for production Home Assistant entities or control decisions.

Machine-readable evidence: [gfa-cycle-ff-2026-09-23-evidence.json](../config/optolink-splitter/research/vitosoft/gfa-cycle-ff-2026-09-23-evidence.json).

## Source and actual analysis coverage

Input: uploaded `Eingefügter Text(20260923-211214).txt`, 631294 bytes, 1095 lines, SHA256:

```text
c2f84dfd3e70d2204fa03011568b9b58895d0ff094e95948901fab3d830b6642
```

This is a console transcript followed by `cat` of the generated JSONL. All 466 JSON objects were parsed: metadata, observation-start, 463 consecutive rounds and a final summary. All 463 console round values were compared with their JSON records. Raw/scaled values, raw-hex consistency, ordering, sample spans and latency arithmetic were checked. This is an offline analysis, not another hardware test.

The JSONL is already present in full; do not ask the user to supply it again. The separate raw TX/RX file `wb2a-gfa-cycle-20260923-230628-169672.log` has NOT been uploaded or fetched. In particular, the failing partial round is not in the JSONL by design.

Tested logger: version 1.0.0 at commit `008e802ea8d5d0dc5a7a8658896722d37ed922da`, SHA256 `d5d98242e6f9526522a53f3c801d856ba8c1a7fde6349c05b56059fa732a54e3`. The supplied transcript shows the hash check and 89 passing offline tests before the live run.

## Acquisition failed, restoration succeeded

| Time | Observation |
| --- | --- |
| 23:06:28.858 | Splitter stopped after the active party emulator. |
| 23:06:30.926 | Initial P300 identification 20C2 confirmed. |
| 23:06:35.270 / 23:06:39.616 | Independent P80 reads returned 20. |
| 23:06:39.617 | Observation started, 300 seconds requested. |
| 23:11:25.380 | Last retained round's P80 reply was 20. |
| 23:11:26.069 | Next round aborted: P80 guard was FF, expected 20. |
| 23:11:28.130 | P300 identification 20C2 verified after restoration, attempt 1. |
| 23:11:30.205 | Splitter reported active/running. |
| 23:11:32.261 | Party emulator reported active/running. |
| 23:11:32.262 | Final result FAIL; restoration flags yes. |

There are 463 complete, identity-guard-passing records, with 1852 retained runtime readings. The failing attempted round is 464 and was correctly not published as a complete JSON measurement. Passing the identity guard does not make every preceding payload physically trustworthy.

The first-to-failure console timestamps differ by 286.452 seconds. The JSON summary says `observation_elapsed_s=285.814239`, because version 1.0.0 updates `Wire.elapsed` after completed rounds, not after a failed partial round. This is a reporting limitation; neither number is evidence for a fixed firmware session lifetime. The splitter was paused for 301.347 seconds including setup/recovery. Home Assistant freshness after this particular run was not separately confirmed.

`P80_CONFIRMED=NOT_CONFIRMED` describes the failed overall/closing identity condition; it does not erase the two successful initial P80 reads and the 463 retained passing guards.

## The two earlier isolated FF events matter more than the final FAIL alone

| Round | Parameter | Exact receive time | Raw byte | Other runtime values | Next P80 guard |
| ---: | --- | --- | --- | --- | --- |
| 142 | P06 fan speed | 23:08:06.612 | FF | P09/P10/P84 all 00 | 20 |
| 222 | P84 phase | 23:08:56.490 | FF | P06/P09/P10 all 00 | 20 |
| 464, not retained | P80 identity | exact RX time missing; failure message 23:11:26.069 | FF reported | failed round's raw log not supplied | mismatch |

P06 and P84 were 00 immediately before and after their isolated FF samples. The P06 reply latency was 127.274 ms, P84 71.424 ms. Both are inside the observed runtime response range; these are not JSON substitutions for absent replies.

All other retained runtime bytes were zero:

```text
P06: 462 x 00, 1 x FF
P09: 463 x 00
P10: 463 x 00
P84: 462 x 00, 1 x FF
461 rounds: all four runtime bytes zero
2 rounds: one isolated FF
```

The logger mechanically converted P06 FF to `255 * 30 = 7650 rpm`. This calculation is correct, but this isolated reading is NOT validated as a physical rotor-speed event. Likewise, the recorded `00 -> FF -> 00` phase changes do not establish a manufacturer-defined phase 255 or two real burner transitions.

`nonzero_rounds=2` and `phase_changes=2` count the raw anomalies. They are not proof of ignition, flame activity or a captured startup. There was no separate flame, pump, temperature or 55DC channel in this logger.

## Code-level diagnosis and limits

The supplied SHA256-pinned `wb2a-gfa-session-probe.py` was inspected, and its relevant code was read back from GitHub at commit `3b9bb24e035034745b3b3949ad0a86817985597a`:

- `Wire.exact`, lines 90-103, raises `RX timeout: expected ...` when insufficient bytes arrive; it does NOT return synthetic FF for a timeout.
- `Wire.read_session`, lines 139-173, takes the received byte from `exact(1)`. For P80, any value other than 20 raises the observed guard error.
- Runtime values are retained and scaled even when FF, provided the following P80 guard passes. That is the current data-quality gap.
- `Wire.observe` in the cycle logger, lines 148-205, records a round only after its guard passes, but has no independent per-value plausibility or FF-quality status.

The current evidence establishes an identity mismatch and two suspect raw-byte outliers. It does not distinguish an internal GFA-forwarding/unavailable response from a physical/serial reception problem, another transient state or other transport behavior. No universal rule that FF always means unavailable, a particular error, a reset or a firmware timeout is established here.

The recurrence in different registers makes an acquisition/data-validity problem a useful hypothesis. A passing P80 guard is demonstrably NOT a checksum or value-validity guarantee for the other four samples. It is also insufficient evidence to declare all 461 zero rounds correct or all prior measurements wrong.

No timeout, host-idle-gap, trailing-byte or queued-byte exception was reported as the terminal reason. The actual failure is the value mismatch. Earlier suspect values appeared about 87 and 137 seconds after observation start, so describing this solely as a five-minute session timeout would ignore the earlier evidence.

## Timing of the retained records

| Metric | Minimum | Mean | Maximum |
| --- | ---: | ---: | ---: |
| P06-to-P06 interval | 564.993 ms | 616.970 ms | 746.024 ms |
| P06-to-P84 span | 318.604 ms | 369.652 ms | 511.339 ms |
| Runtime reply latency | 52.467 ms | 72.626 ms | 160.139 ms |
| Visible receive-to-next-transmit host gap | 50.313 ms | 50.715 ms | 54.455 ms |

These are computed from the complete retained JSONL records, approximately 1.62 rounds/second. They do not include the failing P80's missing raw timing and do not make the readings simultaneous. Speed alone is no longer the main blocker; data validity is.

## Immediate next action: read existing log, no additional heater experiment

Do not repeat the 300-second logger unchanged, switch to a 600-second run, remove the P80 guard or blindly retry FF replies. First inspect the three known contexts in the existing raw log:

```bash
log=/root/wb2a-gfa-cycle-20260923-230628-169672.log

echo '=== FF replies and their immediate context ==='
grep -n -B 10 -A 14 -E \
  'RX ff|Session P80 guard is 0xff|OBSERVATION FAILED' "$log"

echo
echo '=== Final raw log and restoration ==='
tail -n 45 "$log"
```

These commands only read an existing text file. They do not use Optolink, pause services or change parameters. The full `.log` is also suitable; the JSONL need not be retransmitted.

The raw log may establish the exact failed request, reply timing, other received bytes and the partial round. It cannot by itself necessarily prove the physical origin of a corrupted/unavailable byte. Further source analysis or a specifically designed controlled test may remain necessary.

## Changes needed before production-quality acquisition

1. Preserve raw bytes and the declared conversion separately from quality. Mark isolated FF samples in this observed context as suspect rather than publishing 7650 rpm or a confirmed phase transition. Do not replace them silently with zero, last-known values or a guessed state; do not assume FF is universally invalid in every GFA register.
2. Separate complete-frame/read receipt, passing P80 identity guard and physical/semantic plausibility. `guard_passed` should not be called general `measurement_valid`.
3. Preserve failed request/round context and exact failure elapsed time in machine-readable output before cleanup. Earlier confirmed and partial records should remain distinguishable.
4. Any bounded reread or resynchronization policy must be explicitly reviewed after the raw evidence is inspected, logged as a separate attempt and never reported as an uninterrupted successful session. Keep existing read allowlists and service recovery.
5. Only then attempt another naturally occurring operating trace and consider HA integration. Do not use these suspect values to control fan, burner or pump.

These are documented follow-up requirements, not a claim that a corrected logger was deployed in this analysis. The existing helpers, protocol settings, dashboard, installer/updater and all heater parameters remain unchanged. The next user action is log retrieval, not another live probe.
