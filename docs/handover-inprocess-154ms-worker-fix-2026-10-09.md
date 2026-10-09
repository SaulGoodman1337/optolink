# WB2A 154-ms Worker-Boot-Failure: root cause and regression fix

Observation (operator's LXC console, 2026-10-09 21:17 UTC):

- Offline 348 tests succeeded, but systemd worker exited `status=1/FAILURE`
  after **154 ms**.
- `boot_record_verified=false`, `worker_errors=[]`, `services_restored=false`,
  no verified real P300 reads.
- This original result must remain `FAIL_OR_NOT_VERIFIED`. A stored
  `services_restored=false` is absence of recovery proof, not proof that
  production services are down. Inspect actual unit status and MQTT GFA health.

## Deterministic cause identified in sources

`hybrid_acceptance.execute()` created session `inprocess-<timestamp>-<pid>`.
The *same* pinned `legacy_probe.validate_session()` used by both
`live_probe.verify_session()` and the independent `--recover` handler enforces:

```python
session.parent == ROOT and session.name.startswith('run-')
```

Consequently the previous worker failed during its initial validation *before*
constructing its result dictionary; the recovery handler also refused the
same session before producing `recovery.json`. The measured 154 ms is
consistent with this double preflight failure; the original LXC journal was
not provided and therefore the precise traceback has not been confirmed.

## New release acceptance guards

1. Hybrid sessions use `run-inprocess-<UTC>-<pid>`; both worker and independent
   recovery now satisfy the pinned validator without weakening it.
2. A separate process runs the exact *staged* `hybrid_acceptance.py
   --staged-preflight <session>` before systemd-run. It imports the staged
   `live_probe` and original validated recovery helper, calls
   `live.verify_session()`, checks all staged file hashes and re-audits the
   original `/opt/optolink` source. Failure blocks any service interruption.
3. The supervisor reads genuine production MQTT GFA P80/P06 **before** staging
   the hardware job and refuses an unverified original system.
4. Worker diagnostics are written even if its import/session/manifest/lock
   validation fails, so `worker_errors` no longer silently appears empty.
5. The post-run summary separately reads and reports current active/running
   original splitter status and its valid P80/P06 responses, even if
   `recovery.json` was not produced. This check never substitutes for the
   independent recovery proof required for an overall PASS.
6. The serial/FC03 allowlists, device identity checks, source SHA256 pin,
   read-only shadow-copy architecture, logger conflict guards, service
   restoration watchdog and explicit opt-in stay unchanged.

All tests are run without a physical boiler on the CI runner. A successful CI
**does not** substitute for the real hardware acceptance; do not claim the
154-ms incident was physically retested by this change.

## Only after GitHub CI passes

Use one immutable commit. The operator can run the existing supervised
`hybrid_acceptance.py --execute --accept-telemetry-pause` script after its
original MQTT P80/P06 preflight confirms the service healthy; the release
now automatically performs a staged subprocess smoke test first.

The real success criterion remains one P300 FC01 plus exactly two fixed FC03
reads, verified VS1 return, original GFA P80/P06, independent recovery
and fresh production MQTT health. No background deployment, permanent hybrid
mode or arbitrary controller writes are authorized by the acceptance.
