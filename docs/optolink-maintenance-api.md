# Optolink maintenance MQTT API

The maintenance MQTT API exposes the already verified WB2A / VDensHO1
maintenance functions through a guarded application-level interface.

Home Assistant should use this API rather than publishing raw
`w;0x....` commands to the splitter.

## Architecture

```text
Home Assistant
      |
      v
openv/maintenance/cmnd
      |
      v
optolink-maintenance-api.service
      |
      v
optolink_maintenance_core.py
      |
      v
openv/cmnd + openv/resp
      |
      v
Optolink splitter / controller
```

The root-operated `optolink-maintenance` CLI uses the same
`optolink_maintenance_core.py` implementation. CLI and API also share the
same advisory lock:

```text
/opt/optolink/.maintenance.lock
```

The lock file is provisioned as `0660 optolink:optolink`. A CLI action and
an API action therefore cannot execute maintenance operations concurrently.

## Service

```bash
systemctl status optolink-maintenance-api
journalctl -u optolink-maintenance-api -f
```

The service runs as the unprivileged `optolink` user.

The update path enables and restarts the service only when
`settings.mqtt_broker` is configured. Fresh installations intentionally
leave it disabled because the default broker is `None`.

## Topics

Assuming the standard base topic `openv`:

| Topic | Direction | Retained | Purpose |
| --- | --- | --- | --- |
| `openv/maintenance/cmnd` | client -> API | no | JSON requests |
| `openv/maintenance/result` | API -> client | no | per-request result |
| `openv/maintenance/state` | API -> clients | yes | latest normalized maintenance state |
| `openv/maintenance/availability` | API -> clients | yes | `online` / clean-shutdown `offline` |

The base topic is derived from `settings.mqtt_topic`.

## Request envelope

Every request must contain a unique `request_id` and an `action`.

```json
{
  "api_version": 1,
  "request_id": "ha-20260924-001",
  "action": "status"
}
```

Allowed request IDs match:

```text
[A-Za-z0-9._:-]{1,128}
```

The API retains the most recent 100 request results in memory. Reusing a
request ID replays the cached result instead of executing the controller action
again. This prevents accidental duplicate writes from repeated MQTT delivery
or client retries.

## Actions

### status

```json
{
  "api_version": 1,
  "request_id": "status-001",
  "action": "status"
}
```

No write is performed.

### set_hours

```json
{
  "api_version": 1,
  "request_id": "hours-001",
  "action": "set_hours",
  "value": 3000,
  "confirm_reference_change": true
}
```

Constraints:

- integer 0..10000;
- exact 100-hour steps;
- no-op when the value is already active unless `force: true`;
- every actual write requires `confirm_reference_change: true`;
- an actual `0x5721` change can re-baseline `0x7570`.

The result reports whether the burner reference actually changed.

### set_months

```json
{
  "api_version": 1,
  "request_id": "months-001",
  "action": "set_months",
  "value": 12,
  "confirm_reference_change": true
}
```

Constraints:

- integer 0..24;
- no-op when the value is already active unless `force: true`;
- every actual write requires `confirm_reference_change: true`;
- every actual `0x5723` write re-baselines `0x756C`.

### reset

```json
{
  "api_version": 1,
  "request_id": "reset-001",
  "action": "reset",
  "confirm": true
}
```

The core executes the verified sequence:

```text
0x5724 = 1
readback == 1
0x5724 = 0
readback == 0
```

The safety-finalization path still attempts and verifies `0x5724 = 0` when
the first phase produces an ambiguous error.

The result reports the two reference effects independently:

```json
{
  "reference_changes": {
    "interval_0x756C": true,
    "burner_0x7570": false
  }
}
```

This is intentional. Live tests show that the `0x7570` effect of the reset is
controller-state/configuration dependent.

## Successful result

Example shape:

```json
{
  "api_version": 1,
  "request_id": "hours-001",
  "ok": true,
  "action": "set_hours",
  "completed_at": "2026-09-24T20:00:00Z",
  "deduplicated": false,
  "data": {
    "action": "set-hours",
    "changed": true
  }
}
```

The exact action data includes readback and reference information from the
shared maintenance core.

## Error result

```json
{
  "api_version": 1,
  "request_id": "hours-002",
  "ok": false,
  "action": "set_hours",
  "completed_at": "2026-09-24T20:00:00Z",
  "deduplicated": false,
  "error": "changing 0x5721 can re-baseline the burner-runtime maintenance reference at 0x7570",
  "code": "confirmation_required",
  "details": {
    "reference": "0x7570"
  }
}
```

Write-verification errors can additionally contain:

```json
{
  "configuration_restore": {
    "attempted": true,
    "verified": true
  },
  "reference_side_effects_reversible": false
}
```

A restored configuration value must not be interpreted as proof that a
reference side effect was undone. Writes to `0x5721` and `0x5723` can
change their associated reference even when a later rollback restores the
configuration byte.

## Retained state

`openv/maintenance/state` publishes a normalized state object after service
startup and after successful requests:

```json
{
  "api_version": 1,
  "hours_threshold": 0,
  "interval_months": 0,
  "maintenance_state": 0,
  "maintenance_state_text": "Grundzustand",
  "interval_reference_raw": "c988b56a",
  "interval_reference_uint": 1790281929,
  "burner_reference_raw": "134cce03",
  "burner_reference_seconds": 63851539,
  "burner_total_seconds": 63851541,
  "burner_total_hours": 17736.539,
  "burner_since_reference_hours": 0.000556,
  "burner_starts": 487380
}
```

`interval_reference_uint` remains a raw little-endian integer. It must not be
presented as a verified Unix timestamp.

## Home Assistant design rule

Home Assistant should stage desired values in helpers and execute the API only
after an explicit Apply/Reset confirmation.

Do not connect an interactive MQTT Number entity directly to `0x5721` or
`0x5723`.

Recommended flow:

```text
input_number
   -> explicit Apply button
   -> confirmation dialog
   -> MQTT API request
   -> core validation/write/readback
   -> result + retained state
```
