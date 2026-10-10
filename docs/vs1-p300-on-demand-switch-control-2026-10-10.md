# WB2A VS1/P300: on-demand, user-facing read-only switch (pre-merge)

**Branch:** `optolink-handover-acceleration`. **State:** GitHub development branch, no merge and no permanent service deployment.

## Verified scope of v1 operational switching

The original splitter is the sole serial owner throughout a *temporary* shadow process. A root-owned systemd supervision unit takes a private snapshot of active services, stops the known services, starts a copy of the original dispatcher, borrows that single opened VS1 port **without an additional STX** and performs **one** P300 read batch:

1. Verify live KW/VS1 device ID, firmware, GFA P80/P06.
2. Enter P300 and verify device ID and firmware.
3. Read fixed FC03 blocks `0x0F20/32` and `0x1C60/32`.
4. Return to VS1 with verified ID/firmware/P80/P06 and original GFA.
5. Original service exits; systemd `ExecStopPost` independently reclaims pump-owner exclusion, verifies VS1 and restores only previously active services.
6. A **fresh** original MQTT GFA P80/P06 check must succeed before any result can report PASS.

This is explicitly a **pausing** (typically ~25-second service interruption including teardown/recovery) on-demand tool, NOT a seamless always-on live protocol driver. No RAM writes or arbitrary controller addresses are exposed.

## Stable CLI

Run from the exact reviewed development checkout (or later approved deployed release):

```bash
cd /home/chatgpt-admin/optolink-hybrid-dev
python3 tools/handover_acceleration/switchctl.py status
sudo -n /opt/optolink/venv/bin/python \
  tools/handover_acceleration/switchctl.py snapshot --accept-telemetry-pause
```

The first command does read-only MQTT GFA health checks and reports each relevant unit state as JSON.

The second command prints structured JSON with `status`, `verified`, `vs1_restored`, `services_restored`, `production_health`, `time_ms`, `vs1`, `p300` and `session`. A PASS requires all independent physical, recovery and production service/readback proofs. A stale or absent recovery report, missing source session, short P300 frame, unverified post-run GFA, worker failure, or time-out returns a nonzero exit code and no claimed P300 sample. No automatic repeat on FAIL.

The last physical evidence lives in the owner-only root path `/root/p300-trial-work/handover-acceleration-live-results/run-inprocess-*` and is not overwritten.

## Transactional live integration: separate workstream, NOT deployed

`producer_boundary_patch.py` generates a copy of each actually installed external writer, checked by AST for the exact public transaction method(s):

| Source | Cooperatively fenced methods |
|---|---|
| `/usr/local/bin/optolink-party-emulator` | `activate`, `deactivate`, `recover_startup`, `sync_emulated_controls` |
| `/usr/local/bin/optolink-schedule-manager` | `apply` |
| `/usr/local/bin/optolink-service-programs` | `apply_action` |
| `/usr/local/bin/optolink-clock-sync` | `synchronize` |
| `/opt/optolink/optolink_maintenance_core.py` | `_with_session` |

The wrappers hold the common OS `flock` across all original method calls, sleeps, post-write readbacks and rollbacks. A future main loop may take the *same* lease in nonblocking mode. The generator refuses a missing method, async drift, already patched sources, unsafe symlink source or same-file overwrite; with `--expected-sha256`, exact source identity may additionally be enforced.

The generated copies have compiled successfully against all five of the real installed source files, but **the production scripts do not yet include these hooks**. No unattended P300 window can be considered safe from all logical writes until the actual producer rollout and direct MQTT/TCP delayed-readback barrier are integrated and tested.

## Hardware evidence so far

First corrected physical one-shot session:
`run-inprocess-20261010T070956Z-299360` (2026-10-10 09:09 CEST).

`PASS_VERIFIED_INPROCESS_FIXED_FC03`:
- Real GFA P80 `20`, P06 `53`, 2,490 RPM on the conventional VS1 scale.
- Phase `p300_and_vs1=4902.278ms`, end-to-end in-process `5368.663ms`.
- `services_restored=true`; `independent_recovery.verified=true`; production GFA post-check passed.
- FC03 fixed block raw bytes recorded in `docs/vs1-p300-hardware-pass-2026-10-10.md`.

The attached-session bug was a second, invalid start byte; correct warm ID is `F7 00 F8 02` without a new `STX`. Cold reinitialization remains EOT/ENQ/STX. Tests distinguish both.

## Merge acceptance remains blocked until

- The operator approves a merge explicitly.
- A reviewed integration/deployment plan covers the external writers, timer-delayed HA readbacks and a protected MQTT/TCP admission epoch, without losing normal write/readback semantics.
- Real end-to-end controller service health and full source/feature tests pass in the target configuration.
- No service interruption unexpectedly changes burner or pump configuration.

**The switchctl on-demand supervisor can be used without merging and leaves the existing productive splitter intact after each successful independent recovery.**


## Second real hardware acceptance: stable switchctl JSON

On 2026-10-10 around 09:19 CEST, the actual operator-approved root invocation
`sudo -n /opt/optolink/venv/bin/python tools/handover_acceleration/switchctl.py snapshot --accept-telemetry-pause`
exited with status **0** and structured `PASS_VERIFIED_READONLY_SWITCH`.

Session: `run-inprocess-20261010T071900Z-299959`.

- P300 ID: `20c2`.
- FC03 `0x0F20/32`: `54092696ae0000210b620064648d05f50e18006408020000580dc2016b0d6b0d`.
- FC03 `0x1C60/32`: `24e0090000000000000048430000484303030c0c4000542696ae0000210b6200`.
- VS1 P80: `20`; VS1 P06: `53` (GFA raw, equals 2490 RPM on the standard ×30 scale).
- Timings: attach `357.260ms`, P300 plus VS1 return `4902.715ms`, total internal test `5433.093ms`.
- The independent recovery unit exited successfully; previously active services restored, original MQTT GFA readings valid, no reported writes or second serial open.

This is the **second separately verified physical handover** in the same morning; the first fixed one-shot also passed. Both were temporary service-pausing tests, not a multi-hour or simultaneous-production-writer acceptance.
