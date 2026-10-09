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
