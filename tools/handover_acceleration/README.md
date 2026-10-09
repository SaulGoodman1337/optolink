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
