# VS1/P300 acceleration - second offline phase (2026-10-09)

**Branch:** `optolink-handover-acceleration` (based independently on
`optolink-splitter-ha`, not on Draft PR #46).

## Verified changes

- Brought the offline coordinator and two existing test modules from the
  standalone working copy into this branch, without importing the active
  research loggers or changing a service.
- Added a **low-level wire phase guard**, separate from the coordinator's
  state. A raw call to its `tx()` method cannot inject a P300 frame in a
  verified VS1 phase, a GFA read in a verified P300 phase or EOT without
  entering an explicit handshake. As Python cannot isolate untrusted
  callers, these are defense-in-depth invariants, not a security boundary.
- Unified P300 frame parsing against a single absolute monotonic receive
  deadline. ACK, repeated ACK, STX, length and body cannot independently
  extend the 3-s frame limit (excluding deliberate gap/quiet guards).
- Kept **1 ENQ only for the validated return from verified P300**. Cold
  setup and separately reported recovery remain **2 ENQ**. No retry is
  counted as a successful fast switch, and the original failure propagates.
- The cooperative port lease rejects symlinks, nonregular or non-owner-only
  lock files. A competing *independent* process is tested with `flock`.
- Added two Linux PTY tests for real kernel byte-stream handling and trailing
  RX rejection. PTYs are **offline simulators**, not Optolink hardware.

## Verification

Run on the separately isolated test directory:

```sh
PYTHONPATH=tools python -m unittest discover -s tests -p 'test_handover*.py' -v
```

**34 / 34 tests successful locally**: fake-peer controls and frames,
identity and P06/P80 guards, stale/invalid mode rejection, corruption,
packet deadline and timeout, failed fast return, conservative bounded restore,
lease permissions and symlinks, cross-process contention, request serialization,
PTY kernel I/O and historical latency arithmetic. A GitHub Actions workflow
for Python 3.11/3.12 is added to execute the same **offline-only** tests on
this branch. Runner success should be separately inspected; no green remote
CI result is asserted merely because a workflow file exists.

## Scope limits, unchanged

- A cooperative lock **cannot** prevent noncooperating existing serial
  processes. No real serial constructor exists in this prototype.
- An abrupt process kill, kernel/USB failure or failed initial sync cannot be
  guaranteed recoverable from an in-process context manager. A separately
  supervised and validated recovery process is mandatory before device use.
- The coordinator has no bounded priority queue, data freshness guarantees,
  independent P300 actual-P06 source, production HA API compatibility, or
  hardware-tested timing gain. Those are explicit non-goals for this phase.
- The historical full roundtrip is still ~4.610s with two ENQ waits adding
  ~3.995s. There are **no new hardware latency measurements** here.
- No edits to `/opt/optolink`, `optolink-p300-migration`, Draft PR #46, running
  P300 logger sources, heating-controller settings or services.

## Next implementation gates

1. Model a bounded central request queue and data freshness ledger with
   separate VS1/P300 operation contracts; validate starvation and cancellation
   only with simulation.
2. Add a standalone recovery-supervisor **mock** for interrupted operations,
   owned-port detection and selective restoration; never ship a live launcher
   as part of the offline test package.
3. Audit how the existing MQTT/HA dispatcher, VS1 and VS2 adapters select
   mode and retain session state. Preserve readbacks, priorities and GFA.
4. Before proposing one new real hardware experiment, require an original
   source-backed shortcut hypothesis, measurable edge-to-edge timestamp
   distinction, an explicit stop/recovery runbook and user approval.

[Original measured-source audit](handover-acceleration-research-2026-10-09.md)
