# WB2A heating-pump minimum override

## Purpose

The local 20C2 controller keeps coding address E7 (A1 heating-pump minimum speed) in physical RAM at `0x20A5`. The firmware reloads the configured E7 value in a background cycle of roughly 2.1 seconds. A guarded one-byte Physical_WRITE to `0x20A5` affects the live A1 pump request without rewriting the persistent E7 coding.

`optolink-pump-override.service` exposes this as a Home Assistant/MQTT switch.

## Rollout

Run the normal private updater on the Optolink LXC:

```bash
update
```

The updater installs:

- `/usr/local/bin/optolink-pump-override`
- `/etc/systemd/system/optolink-pump-override.service`

When MQTT is configured, the updater enables and starts the service automatically. Fresh installations install the unit but leave it disabled until MQTT is configured and a later `update` is run.

## Home Assistant

The service publishes MQTT discovery for a switch with unique ID:

```text
optolink_pump_min_override
```

Topics:

```text
command: openv/pump_min_override/set
state:   openv/pump_min_override/state
status:  openv/pump_min_override/status
```

Accepted command payloads are `ON`/`OFF` plus the usual boolean aliases (`1/0`, `true/false`, `ein/aus`).

The intended HA automation is to switch the override ON after the existing flame/burner signal indicates a space-heating burner cycle. The service automatically switches itself OFF and releases the serial port when the flame ends or DHW starts, so HA does not need fast timing.

## Runtime behavior

On `ON`, the service fails closed unless all of the following are true:

- normal splitter was active before takeover;
- controller identity is exactly `20 C2`;
- current fault and current alarm are zero;
- configured/working E7 is exactly 30%;
- DHW state is zero;
- flame is currently active.

For an accepted override the service temporarily stops schedule manager, Party emulator and splitter, enters P300 once, and keeps the P300 session open for the burner cycle. It sets only physical RAM byte `0x20A5` to 100 and polls that byte. When the controller's periodic task restores it to 30, the service immediately writes 100 again. The measured Physical_WRITE repair time is about 50 ms; in the validation run A1/A3C stayed at 100 for every sampled runtime point.

The service ends the override on any of these conditions:

- MQTT `OFF`;
- flame off;
- DHW becomes active;
- current fault/alarm becomes nonzero;
- two-hour maximum runtime;
- SIGTERM/SIGINT;
- serial/protocol error.

It then restores `0x20A5` to 30, leaves P300 and restarts only the services that were active before takeover. Independently, controller firmware also restores the configured E7 value if the override process disappears unexpectedly.

## Operational limitation

While the override owns the serial adapter, the normal Optolink splitter is intentionally paused. Normal HA Optolink sensor updates therefore freeze for that burner cycle. The override daemon itself continues publishing its retained state/status and directly monitors flame, DHW and faults over P300. When the override ends, normal splitter polling resumes automatically.

## Diagnostics

```bash
systemctl status optolink-pump-override
journalctl -u optolink-pump-override -n 100 --no-pager
```

The retained status topic reports reasons such as `ready`, `engaged`, `reload_repaired`, `active`, `flame_off`, `dhw_started`, `released`, `busy` or `error`.

## Production architecture rejection: exclusive P300 ownership

The initially prepared production service that would hold the serial adapter in P300 for the complete burner cycle is rejected because it pauses normal Optolink/Home Assistant telemetry for the full override duration. The installer/updater no longer deploys or enables that service.

A read-only protocol-handover latency test then measured whether brief periodic VS1 -> P300 -> VS1 switches could preserve useful telemetry. On the local 20C2 hardware the measured transition was:

```text
VS1 -> P300 switch:  1680.5 ms
P300 identity:          51.8 ms
P300 -> VS1 switch:  4237.0 ms
VS1 identity:           21.0 ms
total:                5990.3 ms
```

Since the controller reloads the E7 RAM cache approximately every 2.1 seconds, protocol-switching for every repair is not viable. It would consume more time than the reload interval and repeatedly interrupt production polling.

Therefore a production pump override must preserve the permanent VS1 session. At present the only source-backed writable pump-minimum path available inside that session is normal E7 Virtual_WRITE/F4. Its nonvolatile persistence/endurance semantics remain unresolved, so flame-by-flame E7 rewriting is not enabled by the updater.
