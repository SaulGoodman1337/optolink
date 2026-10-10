# WB2A VS1/P300: Single-owner runtime admission and pump arbitration (2026-10-10)

**Branch:** `optolink-handover-acceleration`. **Status:** offline development and tests, NOT deployed and NOT hardware-accepted. The real productive service and the boiler were not modified by this work.

## Source audit and currently observed machine state

- Desktop Commander: `optolink-splitter`, Debian 13, development account `chatgpt-admin`, Python 3.13.5. The account is not root; the root-only research directory cannot be read. The original application at `/opt/optolink` is readable.
- Production `optolinkvs2_switch.py` SHA256 `e4be265db857d32486fd50aa7eee359e9a054b951e478d5847f17702a0ce7fac`. Its three dispatch seams match the strict shadow-copy patch: one poll and two MQTT/TCP uses. GFA extension and legacy write/readback parsers are preserved.
- The operator explicitly stopped and disabled `optolink-pump-override.service`; read-only verification returned `inactive` and `disabled`, and the original `optolink-splitter.service` returned `active`. Neither a running daemon nor a currently active RAM override is implied by historical startup status.
- Contrary to the original handover text, the old pump daemon really existed and had been running as root. Its source opens pySerial and writes the physical volatile E7 byte at `0x20A5`. It takes `/run/lock/physical-ram-snapshot.lock` before stopping services. The service may be re-enabled later, so the hybrid must not rely only on this morning's disabled status.

## Implemented hardware-free integration step

### 1. Cross-owner guard in the one-shot hardware candidate

New `tools/handover_acceleration/port_ownership.py` acquires the **same** nonblocking `flock` path as the legacy pump daemon. It refuses symlink/relative/weakly permissioned lockfiles and refuses an active, transitioning or unknown pump unit state.

`hybrid_acceptance.py` now checks both before taking the supervisor's existing research locks and before **any** service pause. The launcher and actual staged systemd worker check independently. The worker holds the shared pump lease throughout its supervised critical section. A stopped daemon cannot race the worker via the old lock if it is activated in parallel. The shadow release is now versioned `inprocess-fc03-oneshot-v2-owner-gate`.

**Scope limit:** the independent `live_probe.py --recover` path still uses its existing legacy research locks rather than the new pump lock, because `legacy_probe.py` is Git-blob-pinned and recovery semantics must not be casually changed. Do not claim full competitive-owner recovery proof before adding an independently tested recovery-side arbitration wrapper.

### 2. Strict multi-message writer fencing

New `runtime_admission.py` provides `RuntimeAdmissionGate`, `DispatcherSnapshot`, and an optional fixed read-only in-process P300 batch. It makes the following *separate* preconditions explicit:

- Original serial-owner thread and verified VS1 session; no reentrancy.
- No pending MQTT, TCP, forced polling or delayed HA readback.
- No current legacy frame; admitted new MQTT/TCP writes are fenced.
- Independent Party, schedules, clock and maintenance writers have **all** acknowledged a quiescent epoch valid through the P300 batch.
- No unfinished legacy write transaction. Any legacy `write`, `writeraw`, opaque `raw`, generic `request` or uninterpretable command latches a write fence. **Time alone does not release it**: a trusted producer must confirm complete write/readback/rollback. For HA `/set`, at least 5.25 seconds after the last observed write must additionally pass, because production schedules readbacks at 0.25, 1.0, 2.5 and 5.0 seconds.
- Engineering budget must fit the nearest writer deadline; batch cooldown is at least 30 seconds (default 120 seconds).

With an externally supplied *verified* snapshot, `run_readonly_batch(...)` borrows the identical opened serial object, revalidates VS1 ID/software/P80/P06, executes precisely one allowlisted P300 read window (FC01 identity and FC03 `0x0F20/32`, `0x1C60/32`), returns through verified VS1, resets the original adapter sync and independently queries original GFA P80/P06. It preserves real VS1 P06 RPM, **not** P09 modulation or RAM-proxy values. Invalid CRC, wrong P80, incomplete restore or overbudget execution latches a fail-closed gate.

### 3. Genuine source-compatible shadow seam, but NO auto P300

`dispatcher_patch.py` still generates a **copy** of the actual original splitter and leaves `allow_maintenance=False`. Under the existing explicit shadow flag, its 3 preserved dispatch hooks additionally run only `RuntimeAdmissionGate.observe_legacy()` to record opaque write intent. With the flag unset the direct original `requests_util.response_to_request` remains unchanged.

No new MQTT command or unrestricted RAM interface exists. The guarded runtime module is *not* automatically called by the live loop; it needs a real, reviewed producer-barrier integration. There is **no** claim of always-on VS1/P300 operation in production yet.

The staged one-shot manifest now includes and hashes `port_ownership.py` and `runtime_admission.py`. The separate staged-interpreter test imports these files using the same import topology as the eventual systemd worker, to catch missing-module failures not seen in ordinary unit tests.

## Test boundary

Run `python3 -m unittest discover -s tests -p 'test_handover*.py' -q` in a clean research checkout. Regressions include dual-owner `flock`, symlinks, pump active or transitioning before service pause, withheld external producer ACK, delayed HA readback, MQTT/TCP backlogs, near writer deadlines, wrong owner thread, stale GFA P80, corrupt FC03, one-port borrowing, deterministic cooldown, disabled shadow behavior and source-copy stage/import checks.

Tests use fake port and/or source copies. **No real hardware protocol change happened during this implementation.** Previously documented 360 passing tests, 154-ms real worker abort, and ~4.6-second physical handover are unchanged historical evidence.

## Remaining acceptance gates

1. Add a producer-barrier/acknowledgement protocol to actual schedule, Party, maintenance, clock-sync, MQTT and TCP write programs. Pending HA delayed readbacks are currently kept in background threads in `mqtt_util.force_delayed`; their scheduled-but-not-yet-queued state cannot be inferred from an empty queue. Install trustworthy accounting **before** enabling recurring P300 transitions.
2. Independently protect the recovery path against a reactivated legacy pump daemon; preserve tested `ExecStopPost` rollback.
3. Execute exactly one explicitly authorized, systemd-supervised hardware acceptance of the new v2 worker, with before/after GFA health, independent recovery and service restoration. **Operator approval to stop the pump daemon does not authorize a separate telemetry interruption or protocol switch.**
4. Once safe, measure end-to-end real MQTT/TCP/write-readback parity, queued-request latency and P06 freshness in a versioned deployment candidate.
5. Continue the original task list separately: genuine P300 blower RPM remains unproved; Vitotrol class `0x11` UART1 RX handler remains unresolved; volatile pump override must eventually share the same physical port owner.

**Production footprint of this commit: zero.** `/opt/optolink`, `/etc/systemd/system`, MQTT, controller coding and serial port are not modified.
