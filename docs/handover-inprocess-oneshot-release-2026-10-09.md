# WB2A Hybrid-In-Process – release candidate for one supervised hardware acceptance

Stand: 2026-10-09. **Research branch only**, no production installation.

## Product acceptance boundary

A runnable, complete **one-shot, read-only** acceptance workflow now exists:

1. The CLI checks the operator-pinned installed dispatcher SHA256
   `e4be265db857d32486fd50aa7eee359e9a054b951e478d5847f17702a0ce7fac`,
   three call sites, GFA extension, original write commands and static protocol
   adapter. No config, credentials, serial port or services are inspected while
   running the default planning command.
2. On `--execute --accept-telemetry-pause`, the existing `live_probe` safety
   guard refuses active P300/RPM research loggers, snapshots the original
   service states, stages immutable copies of the hybrid library and a patched
   version of the *actually installed* original main loop under private mode
   `0700` session storage. The original `/opt/optolink` source is not changed.
3. The systemd-supervised worker checks the full source manifest and verifies
   original ownership again **before** pausing previously active services.
   Only after the original port becomes free does it run the original startup
   logic from the staged copy. The original startup opens exactly one serial
   handle at the configured 4800/8E2 transport and initializes VS1 once.
4. At the original main-loop seam, before any normal poll/MQTT/TCP dispatch,
   a tightly gated one-shot takes the **identical already-open serial object**.
   It verifies VS1 device ID `20C2`, firmware `0103`, P80=`20`, and a valid
   real VS1 GFA P06, without an additional EOT/cold two-ENQ handshake.
5. A single read-only P300 window then performs exactly three typed reads:
   FC01 identity `00F8/2`, FC03 `0F20/32`, FC03 `1C60/32` with full
   ACK/STX/size/address/function/checksum validation. No other RAM addresses,
   writes, GFA aliases or raw user commands are available. The normal verified
   single-ENQ return restores VS1 and refreshes its real P80/P06. **The old
   patched `requests_util.response_to_request()` is then used to recheck actual
   P80 and P06**, not a cached/pseudo-RPM value.
6. The one-shot script exits immediately, *before* the copied original program
   runs any normal poll/MQTT/TCP requests. The original serial handle is
   closed only by the normal program shutdown, not by the borrowed coordinator.
   Independent `ExecStopPost` recovers/validates VS1 and selectively restarts
   only the services that were active before the test; the operator sees a
   separate production MQTT GFA P80/P06 health check.

**No self-updater, no installed service modification, no production software
merge or write-path replacement.** The operator-approved acceptance test is
not the fully deployed recurring hybrid product. Normal requests, HA entities,
write/readback programs, clock/party/service and polling remain under the
original production service after the test.

## Hardware acceptance command (only after CI is successful)

From a pinned GitHub clone, run:

```sh
/opt/optolink/venv/bin/python -m unittest discover -s tests -p 'test_handover*.py' -q
/opt/optolink/venv/bin/python -u tools/handover_acceleration/hybrid_acceptance.py \
  --execute --accept-telemetry-pause
```

An ordinary CLI call without `--execute` is **plan-only**. Aborts/refusals have
exit status 1. Success requires:

- Staged copy actual main loop terminates with `0` after one exact 3-read
  P300 window and fresh original GFA P80=`20` / P06 other than `FF`.
- Independent recovery confirms verified VS1 and restoration of previously
  active original services, and a subsequent production MQTT P80/P06 check is
  valid. Only then is `RESULT=PASS_VERIFIED_INPROCESS_FIXED_FC03` emitted.
- Results live in
  `/root/p300-trial-work/handover-acceleration-live-results/inprocess-.../`:
  `hybrid-result.json`, `measurement.json`, `recovery.json`,
  `hybrid-summary.json`, the manifest and staged source copies. The
  `HYBRID_SUMMARY` console line includes separately attributed, measured
  `phase_ms.attach`, `phase_ms.p300_and_vs1`, `phase_ms.total`,
  original post-return GFA values and independent recovery status. A PASS
  requires a second verification of the actual on-disk boot evidence, not
  only a worker-generated success flag.

The unit has separate execution/stop time limits and a distinct root-owned
recovery process. This substantially reduces risk but **does not guarantee**
recovery after kernel/USB/controller failures; if the result says
`FAIL_OR_NOT_VERIFIED`, do not repeatedly launch this test without diagnosis.

## What this result can and cannot prove

It can confirm the new borrowed-port VS1 attachment on real hardware, return
through the copied original dispatcher, verify two actual fixed FC03 blocks
and compare host-observed timings to the previous single-ENQ manager.
No hardware acceptance result exists for this new code yet.

It **cannot** prove regular unbounded use of P300 maintenance in production,
GFA validity from a P300 RAM byte, multi-message MQTT write/readback
transaction safety or a sub-four-second single handover. The 2026-10-09
hardware phase campaign measured seven complete 4.5–4.73 second rounds; both
350-ms before-ENQ experiments failed, followed by successful VS1 recovery.

## Acceptance prerequisites for a recurring production hybrid

A sustained deployment still needs complete source-level mapping of *all*
inter-request write/readback sequences (clock, schedules, party, maintenance,
HA automation); stronger independent recovery for a permanently installed
hybrid owner; runtime deadlines, GFA freshness/backpressure; a long-lived
hardware soak test with fault injection; and an explicit rollbackable versioned
release. The `hybrid_acceptance.py` path deliberately forbids a repeating
maintenance mode and thus does not open a race between a write request and
its readback.

## Test evidence

Offline CI runs the full protocol/serial/PTy/runtime regression suite under
Python 3.11 and 3.12 and compiles a patched copy of the SHA-pinned upstream
`optolinkvs2_switch.py` (Git blob
`1fae36baae1c2ef264906c8eca76ef15c5152974`). New tests execute the
patch-generated main function under injected MQTT/TCP/serial dependencies,
verify no legacy request is processed in the one-shot mode, validate
that the copied worker imports its full module graph without access to
the original research checkout, and exercise
CRC failure, wrong ID, P80/P06 invalidity, symlink/stage tampering, unit
failure, service-state mismatch, watchdog timeout and post-restore health
failure. **These are software regression results, not another physical test.**
