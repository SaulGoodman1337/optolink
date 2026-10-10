# VS1/P300 handover: in-process dispatcher integration audit

Date: 2026-10-09. **Static offline code review only.** No real port opened,
no service executed, no production patch or modification to the P300 research
branch. All original source refs are pinned below.

## Refined architecture decision

**Use an in-process single serial owner, not a second long-lived serial daemon.**
The existing `optolinkvs2_switch.py` already opens the Optolink device once at
4800 8E2, `exclusive=True`, `timeout=0`, then issues ordinary poll, MQTT and
TCP requests from its principal scheduling loop. Most local helper services
communicate with that split owner through MQTT and never take the serial
adapter themselves. A separate daemon opening the same port would either
compete with production or require a risky owner transfer on each window.
Neither choice makes the WB2A answer ENQ faster.

The present standalone `handover_acceleration.coordinator` remains an
**offline I/O-injection simulator**. This audit is a plan for an eventual
in-process service replacement; it does not authorize direct integration.

## Concrete call graph and disruption points

| Existing source | Observed behavior | Integration requirement |
|---|---|---|
| `optolinkvs2_switch.py` lines ~508-528 | Serial open with 4800, 8E2, `exclusive=True`, `timeout=0` | Retain precisely one serial handle; future manager must wrap this handle, not open another. Add independently checked exclusive kernel ownership before any later device usage. |
| Same module, ~650-770 | Main loop multiplexes existing poll list, MQTT command and TCP request; requests are synchronous on the serial handle | Introduce an atomic in-process session/transaction boundary. No switch in mid-request, between write and readback, or during scheduled forced-refresh. Do not duplicate a second worker calling the handle. |
| `requests_util.response_to_request()` ~145-266 | Splits string requests into `read`, `write`, `writeraw`, `raw`, and `request` and forwards to the static `vs12_adapter` | Strongly type operations; preserve existing verified writes/readbacks only on approved VS1 path. The new read-only experimental manager must not expose the generic/raw or RAM-write handlers. |
| `vs12_adapter.py` line 9 | Global `VS2 = not settings.vs1protocol` at import | This is *configuration*, not a dynamic session variable. Never flip it mid-frame; adapters and active session state must be separate objects. |
| `optolinkvs1.py` ~30-39, 105-114 | Host-side `SYNC_TIMEOUT=0.6`, global `last_comm`; intermittent re-init and input purge | The manager owns session generations; mark old sync proofs invalid immediately after EOT, protocol switch, RX fault or loss of port. No input purge inside a pending reply. |
| HA GFA patch `tools/optolink-apply-vs1-gfa-readonly-patch.py` | Inserts `read_gfa_ext`, `gfaread` and `gfa:` scaling with 25-ms first gap, 150-ms FF retry; tracks P80 gate | Preserve exact P80=20 gate and P06 raw semantics. Invalidate P80 verification whenever mode/session changes. Do not invent a P300 GFA alias. |
| HA scheduling patch `tools/optolink-apply-phased-poll-scheduler-patch.py` | Adds phased/once groups, force-refresh and poll-cycle controls | Maintain group phase, `ONCE` and `forcepoll` semantics through queued wait time and resume; no unbounded P300 window starving GFA. |
| `homeassistant_publish.py` and `mqtt_util.py` | Existing topics, state publication, discovery and request/response format | Keep topics/entity identity and publish-time freshness separately from transport-time freshness. Cached values must not be advertised as fresh physical P06. |
| Auxiliary services (architecture documentation) | Clock sync, schedules, maintenance, party and service programs use MQTT | Retain their existing write gates, locks, transactional readback and timer ordering. No second serial owner. |

The existing settings can optionally enable a Vitoconnect serial link; in that
mode the upstream code also starts a reader thread and a direct forwarding
path. **A future hybrid owner must explicitly refuse this mode unless its
thread/port topology is separately audited.** The local single-head WB2A
profile has historically used `port_vitoconnect=None`, but a future code path
must verify it at runtime rather than assume it.

## Recommended integration seams, with explicit non-goals

1. **Session owner:** Replace only the serial *dispatch seam* inside the
   main loop with a manager object holding the existing serial handle. Do not
   wrap the old `vs12_adapter` in a second daemon. Keep the default mode VS1.
2. **Typed requests:** Separate `VS1_GFA_READ`, `VS1_VIRTUAL_READ`,
   `VS1_VERIFIED_WRITE_READBACK` and `P300_VERIFIED_READ` in a new internal
   command interface. The current isolated prototype implements only fixed
   identity and read-only GFA; no general P300 RAM API yet.
3. **Atomic windows:** Queue requests while handshaking; never interrupt an
   on-wire transaction. Preserve existing HA write/restore semantics and
   ensure every accepted request completes, fails clearly or expires.
4. **Request fairness:** Bound queue size, waiting age and time in any P300
   diagnostic window. Prefer reusing a *currently* verified VS1 session for
   multiple GFA reads instead of triggering a handshake per parameter.
5. **Freshness:** Track source protocol, monotonic sample time, serial-session
   generation and error status. Mark values stale during handover. Separate
   freshness from MQTT retain and message-republish timestamps. Read-only P06
   is the actual GFA RPM raw byte; P09/P10 are never interchangeable.
6. **Recovery:** For failed transitions, reject new commands and perform one
   distinct conservative 2-ENQ VS1 recovery under independent supervision.
   After unexpected process/USB loss, **do not assume** the in-process
   `__exit__` ran; an external supervisor must restore only previously active
   services after confirming port freedom and original VS1 operation.
7. **Rollout:** Feature-flag off, no deployed integration, no hardware speed
   claims. Only after a later reviewed hardware gate could the future manager
   be considered for shadow diagnostics or an entirely separate maintenance
   deployment. Never modify `/opt/optolink` as part of this research branch.

## What can and cannot become faster

An in-process owner removes future *process-level* port handoffs between
requests and may amortize session verification within one valid protocol
phase. These benefits are architectural and **not yet measured**. For the
already measured EOT-based single-ENQ roundtrip, about **3.995 seconds** are
spent waiting for two ENQs. Neither an async queue nor a subprocess-free
adapter changes this observation. The current fastest validated complete
roundtrip remains **4.610 seconds** (three valid hardware rounds).

Without a new verified on-wire path or elimination of whole handovers via a
truly equivalent live P300 GFA source, a claim of <4 s, <2 s or <1 s is
not supported by the evidence. In particular, a 2.1-s approximate asynchronous
pump-RAM reload interval cannot be serviced safely by the measured 4.6-s
roundtrip. No new hardware probe or write experiment follows from this audit.

## Additional offline contracts before any integration

- Competing inbound polling/MQTT/TCP requests cannot interleave bytes on the
  serial port, even when a request times out or is cancelled.
- A write plus its exact readback (when authorized) is one atomic transaction;
  no queued P300 transition may split them. The present prototype exposes no
  write operations, by design.
- Wrong VS1/P300 identity, P80 mismatch, invalid P06/FF, bad CRC, unexpected
  ACK/EOT, stale session generation and attempted second port ownership all
  fail closed and never produce fresh GFA data.
- A failed fast handshake is reported as failed **even if** subsequent
  conservative recovery succeeds. A recovery fault does not restart endless
  hardware retries.
- Prior active service state, timer ordering and explicit owner release must
  be captured by a future **independent** recovery supervisor and validated
  in a mock environment before any operator-approved hardware proposal.

## Pinned sources

- [Original upstream main loop](https://github.com/philippoo66/optolink-splitter/blob/c1ee204a1421447721603c5f21c6da7337fdac97/optolinkvs2_switch.py)
- [Original request dispatcher](https://github.com/philippoo66/optolink-splitter/blob/c1ee204a1421447721603c5f21c6da7337fdac97/requests_util.py)
- [Original static protocol adapter](https://github.com/philippoo66/optolink-splitter/blob/c1ee204a1421447721603c5f21c6da7337fdac97/vs12_adapter.py)
- [HA GFA read-only patch](https://github.com/SaulGoodman1337/optolink/blob/555528c5075315db0fd50fd17ee5dd3a806f67e0/tools/optolink-apply-vs1-gfa-readonly-patch.py)
- [HA phased poll patch](https://github.com/SaulGoodman1337/optolink/blob/555528c5075315db0fd50fd17ee5dd3a806f67e0/tools/optolink-apply-phased-poll-scheduler-patch.py)
- [Production architecture](https://github.com/SaulGoodman1337/optolink/blob/555528c5075315db0fd50fd17ee5dd3a806f67e0/docs/architecture.md)
- [Measured-source audit](handover-acceleration-research-2026-10-09.md)