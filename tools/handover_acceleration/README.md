# Experimental handover coordinator - offline only

This package is a **protocol-state model**, not a configured Optolink service.

- No production import path, pySerial constructor, device discovery, systemd command,
  GFA write, RAM write, or operator-facing hardware command is provided.
- `HandoverCoordinator` accepts an injected serial-like object and a **cooperative**
  `PortLease`. The caller must not pass a real port while another owner exists.
- `ReadOnlyWire` permits only fixed read-only identity/GFA telegrams and
  protocol-control frames. Its low-level allowlist is phase-specific.
- The `2 ENQ` initial/rescue path and the `1 ENQ` verified P300-to-VS1 return
  come from **distinct** previously measured test conditions; the fake peer
  does **not** establish any new controller behavior.
- The model does not support the complete production polling / writeback API,
  nor FC03 diagnostics; no production deployment is authorized.
- `fcntl.flock` only cooperates with other processes taking the same lock.
  Before any future actual port integration an independent supervisor, kernel
  `TIOCEXCL` / pySerial `exclusive=True`, real owner detection, selective
  restoration of previously active services and fail-safe restart must exist.

Run locally on Linux with Python 3.11+ (only standard library and fake ports):

```sh
python -m unittest discover -s tests -p 'test_handover*.py' -v
```

The PTY test uses `pty.openpty()` (a virtual pair in the test process), **not**
`/dev/ttyUSB*` or a Viessmann interface.

## Offline request policy and provenance

`scheduler.py` adds a bounded read-only queue and a separate GFA freshness
ledger. A ticket contains an absolute monotonic deadline, explicitly typed
read kind and queued/running/terminal state. Only one consumer can hold an
in-flight ticket. The queue prefers a currently active protocol for at most a
configurable batch before serving the other pending mode; it **does not**
perform any serial I/O or switching. It is **not** yet wired to the coordinator.

The GFA ledger rejects invalid P80, FF and unverified samples. It requires
matching session generation and maximum age on readback, and never maps P09
modulation to P06 measured RPM. Its `vs1_verified` argument is a future
integration precondition, not a cryptographic proof of transport state.

## Optional one-shot real hardware acceptance (explicit opt-in)

`live_probe.py` is a separate, **non-production** test requiring
`--execute --accept-telemetry-pause`. Its default is inert. It is installed
in this research branch together with a Git-blob-pinned copy of the existing
read-only recovery helper, `legacy_probe.py`.

The code refuses to stop production if another P300/RPM research logger is
active, then supervises a single VS1->P300->VS1 cycle with systemd
`ExecStopPost` recovery. The active original services are selectively restored
and tested after the worker exits. **Never run if an RPM logger is active;
let its normal run complete.** Read `docs/handover-live-acceptance-2026-10-09.md`
before using the opt-in flags. The read-only wire and fake-peer tests are safe
on a machine with an active logger, but the execution flags are not.

## Seven-round protocol phase campaign (research only)

The `campaign.py` entrypoint runs a fixed seven-round **known-handshake**
EOT-phase sweep with immutable read-only frames and two control rounds. Only
after complete independent restoration and a fresh validated production MQTT
P80/P06 check may it run **one separately supervised** early-VS1-identity
experiment, which sends the known VS1 ID read after EOT before ENQ. It never
repeats the previously negative early-P300-START experiment. All stage
manifests and raw events stay in a private research results directory.

Default `campaign.py` is **plan-only**. A hardware run requires exactly
`--execute --accept-telemetry-pause` and the separate
`--include-early-vs1` flag for the speculative second stage. No historical
failed hypothesis is considered a success. Detailed German runbook:
`docs/handover-multistage-campaign-2026-10-09.md`.

## Live evidence forensic replay and offline batching (2026-10-09)

The real seven-round campaign and both unsuccessful early-before-ENQ trials
are analyzed in `docs/handover-campaign-real-forensics-2026-10-09.md`.
`campaign_forensics.py` reads ONLY existing session JSON and does not send
any MQTT/serial messages. `phase_executor.py` integrates the offline typed
planner with the injected, preverified coordinator to demonstrate a single
P300 session for multiple **identity** reads. It is **not** a production
adapter, a physical RAM interface or a substitute for real GFA P06.
The unmodified production splitter and P300 logger remain entirely separate.

## 2026-10-10: Single-owner arbitration and admission safety (offline only)

The installed legacy pump service was explicitly stopped/disabled by the
operator; the active splitter remains unchanged. The v2 one-shot supervisor
takes its exact shared `physical-ram-snapshot.lock` and refuses an active
or transitioning pump owner before suspending any service. The staged-copy
manifest includes new dependencies and the actual subprocess import graph is
regression-tested.

`runtime_admission.py` adds a strict opt-in transaction-level gate in which
MQTT/TCP, scheduled HA readbacks, external writers and VS1 identity must all
prove an idle epoch. A write/opaque request remains fenced until an **explicit**
external producer acknowledgement and a >=5-second HA settlement interval.
An eligible, bounded batch can reuse the **same** injected port and verify
the original GFA P80/P06 after fixed FC03 reads. The patched shadow dispatcher
only **observes** write intent: it does not enable recurring handovers or
publish new commands. Deployment is blocked until external producer fences
and independent recovery arbitration are wired and hardware-accepted.
Details: `docs/vs1-p300-runtime-admission-2026-10-10.md`.

## New offline main-loop bridge and physically documented FC03 read fixtures

`dispatcher_bridge.py` now models a *single existing* serial owner with exact
legacy MQTT/TCP/poll preservation. Every historical request still passes to
`requests_util.response_to_request`, including writes and readbacks. Maintenance
remains disabled by default; the proof of an active VS1 owner is invalidated
by any opaque legacy operation, and failed maintenance closes its dispatch
boundary until external recovery. `HandoverCoordinator.borrow_existing_vs1`
checks fresh VS1 ID/software/P80/P06 without opening or closing the current
serial handle; only the fake-port path is proven so far. Offline FC03 reads are
restricted to two previously hardware-researched diagnostic addresses:
`0x0f20/32` and `0x1c60/32`. P300 RAM is not a valid GFA P06 source.

`dispatcher_patch.py` constructs/compiles a *copy* of the pinned original
Optolink main loop; the patch is inert by default and, even with the shadow
flag, does not enable P300 maintenance. The original program, services,
operational parameters and HA writers are not patched or redeployed.
See `docs/handover-inprocess-dispatcher-integration-2026-10-09.md`.

For a non-invasive comparison against the actually installed production
sources, use `dispatcher_runtime_audit.py --root /opt/optolink`. It reads only
three Python source files, never imports/runs them and never touches settings,
services, MQTT or any serial device. It reports whether the strict shadow-copy
patch source constraints match the deployed HA-patched main loop.

## Supervised in-process, read-only acceptance release candidate

`hybrid_acceptance.py` makes a versioned, copied build from the **actual
installed** `/opt/optolink/optolinkvs2_switch.py`, with the operator-verified
SHA256 pinned; it never edits the original code or starts a second serial
process while the old owner is running. `hybrid_boot.py` executes exactly one
fixed FC01 identity plus two FC03/32 reads after borrowing the same handle
inside the copied original process, then restores and verifies real VS1/GFA
before exiting. A separate systemd worker/recovery path restores original
services and verifies their MQTT data afterwards. The feature is disabled by
default and explicitly refuses unrelated code/transport profiles. It is
**one-shot hardware acceptance**, not an installed recurring hybrid service.

See `docs/handover-inprocess-oneshot-release-2026-10-09.md`.
