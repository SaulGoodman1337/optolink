# WB2A next phase: production baseline and offline gates (2026-10-10)

Status: verified runtime inspection and offline tests, **not** P300-RPM verification or live hybrid enrollment.

## Git and scope
- Repo: SaulGoodman1337/optolink; `main` and `feat/wb2a-next-phase-20261010` compared identical at `7a5122986524dfb22e032a43e0ffafb5a083c18a` before this document.
- New isolated local worktree rooted at `/home/chatgpt-admin/optolink-wb2a-next-phase-20261010`, checked out from refreshed `origin/main`. Existing research and prior uncommitted worktrees untouched.
- Production remains on the separate `/opt/optolink` upstream installation.

## Live read-only production audit
- At ~20:14 Europe/Berlin: six production services/timer active (splitter, party emulator, schedule manager, maintenance API, service programs, clock sync); continuous hybrid canary and pump override inactive.
- `optolink-hybrid status`: `VS1_BETRIEB_OK`, lock `FREI`, no enrollment, automation disabled, no controller writes.
- Serial CP2102 `/dev/serial/by-id/usb-Silicon_Labs_CP2102_USB_to_UART_Bridge_Controller_0001-if00-port0`: `lsof` shows splitter PID 320661 as serial owner (other entries were its threads).
- MQTT TCP connections to existing broker observed, maintenance API journal reports successful connection. Live MQTT debug commands through the existing splitter returned GFA P80 `20`, P06 `00` (0 rpm), P09 `00`; these are legitimate live VS1 replies. Home Assistant entity freshness **not yet verified**.
- Journal error-priority query for the selected production units over 45 minutes returned no errors.

## Offline regression
- `python3 -m unittest discover -s tests -p 'test_handover_*.py' -q` -> 236 tests, OK.
- `python3 -m unittest discover -s tests -p 'test_optolink_hybrid_production.py' -v` -> 11 tests, OK.
- No controller RAM writes, serial handover, service restarts, or modification of installed production files performed.

## Historical RPM evidence examined (research only)
- Read existing `/root/p300-trial-work/project/docs/p300-rpm-next-experiment-and-architecture-2026-10-09.md`, `p300-rpm-trigger-runbook-2026-10-09.md` and stored run `run-20261009T174812Z-293099`.
- Final run reports 2,185 cycles, 8,740 packets, 10 candidate changes, 2 flame edges, **zero qualified triggers**. Operator stop after ~2752s; quality PARTIAL; no verified P300 RPM. Recovery marked RESTORED and health `production_main_verified=true`, `ha_entity_freshness_verified=false`.
- Continue only from offline timed comparison of `0x0F20` and `0x1C76` with FC01 status and independent VS1 P06/P09. Do not publish inferred RPM or restart wide RAM sweeps.

## Next testable engineering work
1. Derive a fixture-only correlation and temporal-gap classifier from archived sessions, with tests rejecting unstable bracket samples, FF, status copies, and any false claim of verified RPM.
2. Assess single-owner VS1-default request batching against current admission/lease/restore components. Enforce transaction boundary, bounded P300 dwell, starvation protection, and VS1 P80/P06 return gates.
3. Separately inspect MQTT state timestamps for Home Assistant freshness and the inactive pump override implementation, with no activation.
4. Route experimental raw data and firmware interpretation into `optolink-research`; retain operational software and tests here. No `main` merge until tested.
