# VS1/P300 acceleration - offline bounded scheduling and provenance

Date: 2026-10-09. Research branch: `optolink-handover-acceleration`.

## New isolated Python components

- `tools/handover_acceleration/scheduler.py`: `BoundedReadQueue`, strictly
  typed `ReadKind`, queue tickets with finite monotonic TTLs, capacity,
  queued cancellation, single in-flight owner, bounded same-protocol batching
  and explicit completion status. No request can be cancelled during a
  transaction and no write/raw request kinds can enter the queue.
- `GfaFreshnessLedger`: stores only accepted **real VS1 GFA** raw bytes tagged
  with source, observation time and session generation. The caller must prove
  VS1 is verified; the independent model does not open or inspect a device.
  An invalid P80, P06 FF or unverified read invalidates the old sample; an
  outdated session generation or TTL causes a stale-read error. P09 is never
  used as P06 RPM data. Valid P06 zero is preserved.
- `tests/test_handover_scheduler.py`: 17 new offline queue/ledger regression
  tests covering starvation bounds, admission, expiry, cancellation,
  competing consumer threads, frame atomicity and stale GFA prohibition.

**51/51 local tests passed** in the combined source tree (34 protocol and
latency tests plus 17 queue/freshness tests). GitHub CI covers both Python
3.11 and Python 3.12; CI conclusions need to be read from the relevant pushed
commit, not presumed from this document.

## What this does not do

There is no actual dispatcher integration, no automatic P300/VS1 scheduling,
no physical FC03/RAM read capability, no hardware I/O, no new timing result,
no production writes, no original splitter modification and no independent
recovery supervisor. A safe future deployment would need an explicit link
between the verified coordinator state/generation, ticket execution and GFA
ledger. The queue's protocol-batching policy controls task order only; it
**cannot shorten** the approximately 2.0-s ENQ synchronization waits.

In particular, no existing P06/P300 logger or Draft PR #46 was changed.
The new model remains intentionally inert until later integration gates are
met and explicitly approved.

## Sources and decision records

- [Initial measured-time audit](handover-acceleration-research-2026-10-09.md)
- [Phase-2 protocol/state/PTY tests](handover-acceleration-phase-2-2026-10-09.md)
- [Static production dispatcher integration audit](handover-dispatcher-integration-audit-2026-10-09.md)
