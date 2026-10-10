# WB2A real hardware: verified borrowed-port VS1/P300/VS1 read-only switch

**Date:** 2026-10-10, 09:09-09:10 Europe/Berlin. **Machine:** optolink-splitter. **Git branch:** optolink-handover-acceleration. This is a bounded **single** real hardware acceptance run, not a deployed continuous hybrid.

## Root cause and exact correction

The first one-shot acceptance from 09:01 failed at `ReadOnlyWire.verify_attached_vs1()`, with `ProtocolError("RX deadline")`. The existing original splitter had already initialized VS1 using `EOT -> ENQ -> STX + F7 00 F8 04`, receiving `20 C2 00 03`. A second `STX + F7 00 F8 02` is **not** valid in the already active KW/VS1 session; the controller stayed silent.

The fix **does not** weaken identity checking. `ReadOnlyWire.verify_attached_vs1()` now sends a fresh `F7 00 F8 02` identity read **without STX**, then `F7 77 8C 02` firmware and VS1 GFA P80/P06, all with bounded responses and exact validation. The cold VS1 path still uses EOT/ENQ and STX. Fixed-wire tests expressly distinguish both modes.

## Successful one-shot result

Supervisor session:
`/root/p300-trial-work/handover-acceleration-live-results/run-inprocess-20261010T070956Z-299360`.

- `hybrid-summary.json`: `PASS_VERIFIED_INPROCESS_FIXED_FC03`, `worker_verified=true`, `boot_record_verified=true`, `unit_rc=0`, `services_restored=true`, `production_splitter_running=true`; verified independent `ExecStopPost` recovery, no worker errors.
- `hybrid-result.json`: one P300 window, ID `20c2`, read-only two fixed FC03 blocks (32 bytes each), existing serial handle borrowed, **no second serial open, no device write**.
- Exact real RAM:
  - `0x0F20/32` = `540926a9b10000210b62006464d308f50e18006408020000cc06c2016b0d6b0d`
  - `0x1C60/32` = `24e0090000000000000048430000484303030c0c40005426a9b10000210b6200`
- Final independent VS1 GFA: `P80=0x20`, `P06=0x53` (2,490 RPM if interpreted as normal GFA raw *30; **not** verified as a P300 RPM signal).
- Bound timings (ms): `attach=293.278`; `p300_and_vs1=4902.278`; `total=5368.663`. Real service unit duration 25.396s including startup/teardown/recovery.
- Installed original source hash unchanged. MQTT final health `1;0x4050;20` and `1;0x4006;53`. Production Party/Schedule/Maintenance/Service Programs restored.

## Release interpretation

**The physical VS1/P300 switching protocol works under an exclusive on-serial-port read-only test.** This does **not yet** authorize always-on automated switching between logical multi-message MQTT writes or a production merge. The runtime admission/producer-fence prototypes still lack full installation in the productive producer processes.

Next validate standalone real repeated bounded switching, then integrate a permanent single port owner with a provable writer/readback barrier, service health and fail-closed recovery. No merge before the operator approves.
