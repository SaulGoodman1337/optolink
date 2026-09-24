# Wartung / Maintenance completion checkpoint - 2026-09-24

This document closes the 2026-09-24 maintenance workstream for the local
**Viessmann Vitodens 200-W WB2A / VDensHO1 / device 0x20C2 / SW03** setup.

The currently verified scope is complete end-to-end:

```text
Home Assistant
  -> staging
  -> explicit confirmation
  -> guarded maintenance MQTT API
  -> shared maintenance core
  -> Optolink splitter
  -> controller write/readback
  -> retained/API state
  -> Home Assistant
```

No further raw maintenance write experiments are required for the verified
scope.

## 1. Verified controller contract

| Address | Access | Verified meaning / behavior |
| --- | --- | --- |
| `0x5721` | R/W | burner-runtime maintenance threshold, raw x 100 h, range 0..10000 h |
| `0x5723` | R/W | maintenance interval, 0..24 months |
| `0x5724` | R/W sequence | maintenance state/reset, verified reset sequence `1 -> 0` |
| `0x756C` | read-only | `LastCheckInterval` reference, seconds-like progression, exact converter unresolved |
| `0x7570` | read-only | burner-runtime-seconds maintenance reference / `LastBurnerCheck` |
| `0x08A7` | read-only | lifetime burner runtime in raw seconds |
| `0x088A` | read-only | lifetime burner starts |

Important side effects:

- changing `0x5721` can re-baseline `0x7570`;
- changing `0x5723` re-baselines `0x756C`;
- maintenance reset `0x5724: 1 -> 0` re-baselines `0x756C`;
- the reset effect on `0x7570` is controller/configuration dependent;
- `0x08A7` and `0x088A` are not maintenance-reset counters.

The verified derived burner runtime since the current burner reference is:

```text
(current 0x08A7 seconds - stored 0x7570 seconds) / 3600
```

Do not present `0x756C` as a verified Unix timestamp. It is a
`LastCheckInterval` reference with an unresolved Vitosoft conversion.

## 2. Shared maintenance implementation

The maintenance logic exists only once:

```text
/opt/optolink/optolink_maintenance_core.py
```

Two frontends use it:

```text
/usr/local/bin/optolink-maintenance
/usr/local/bin/optolink-maintenance-api
```

The shared advisory lock is:

```text
/opt/optolink/.maintenance.lock
mode 0660
owner optolink:optolink
```

The root CLI and unprivileged API therefore cannot execute a maintenance
operation concurrently.

## 3. Guarded CLI

Verified commands:

```bash
optolink-maintenance status
optolink-maintenance set-hours <0..10000> \
  --confirm-reference-reset RESET-BRENNERREFERENZ
optolink-maintenance set-months <0..24> \
  --confirm-reference-reset RESET-ZEITREFERENZ
optolink-maintenance reset --confirm RESET-WARTUNG
```

Verified guard behavior:

- out-of-range values are rejected;
- same-value writes are suppressed as no-ops unless forced;
- real `set-hours` writes require burner-reference acknowledgement;
- real `set-months` writes require interval-reference acknowledgement;
- reset requires the exact reset acknowledgement;
- ACK alone is never authoritative;
- write success requires independent readback;
- ambiguous writes attempt configuration rollback;
- rollback does not claim to reverse already-triggered reference side effects;
- reset always attempts to finalize `0x5724=0`.

Live CLI paths verified:

- `set-hours 0` no-op;
- `set-months 0` no-op;
- rejection/confirmation guards;
- `set-hours 0 -> 100 -> 0`;
- `set-months 0 -> 1 -> 0`;
- `reset 0x5724: 00 -> 01 -> 00`.

## 4. Important live semantic findings

### 0x5721 / 0x7570

A real `0x5721: 0 h -> 100 h` change re-baselined `0x7570` to the current
burner runtime. The restore `100 h -> 0 h` did not re-baseline it again in
that capture.

Therefore every real threshold write is conservatively protected.

### 0x5723 / 0x756C

Every tested real `0x5723` write re-baselined `0x756C`.

A set/restore pair also showed the reference advancing by the same number of
counts as approximately elapsed seconds. This supports seconds-like progression
but does not establish a Unix epoch.

### 0x5724 reset

The reset sequence `1 -> 0` is verified.

A first reset initialized an empty `0x7570` reference. A later reset with an
existing burner reference and `0x5721=0 h` left `0x7570` unchanged.
Therefore the `0x7570` reset effect must be reported, not assumed.

## 5. MQTT maintenance API

Service:

```text
optolink-maintenance-api.service
```

Runs as:

```text
User=optolink
Group=optolink
```

Core topics:

```text
openv/maintenance/cmnd
openv/maintenance/result
openv/maintenance/state
openv/maintenance/status
openv/maintenance/availability
```

Staging topics:

```text
openv/maintenance/stage/hours/set
openv/maintenance/stage/hours/state
openv/maintenance/stage/months/set
openv/maintenance/stage/months/state
```

Verified API protections:

- recent request-ID deduplication;
- retained command messages ignored;
- serial queue;
- shared CLI/API lock;
- range checks;
- confirmation checks;
- independent write readback;
- reset safety finalization;
- retained normalized state;
- explicit `busy` response on lock contention.

Live API tests completed:

- read-only `status`;
- duplicate request replay;
- no-op `set_hours 0`;
- no-op `set_months 0`;
- unconfirmed write/reset rejection;
- shared lock contention;
- real `set_months 0 -> 1 -> 0` with readback and restore.

## 6. systemd lifecycle correction

An initial unit version used:

```ini
Requires=optolink-splitter.service
PartOf=optolink-splitter.service
```

This caused an independent splitter restart to propagate a clean stop to the
maintenance API.

The corrected service uses:

```ini
After=network-online.target optolink-splitter.service
Wants=network-online.target optolink-splitter.service
Restart=always
```

Live regression test:

```text
before:
  optolink-splitter.service        active
  optolink-maintenance-api.service active

systemctl restart optolink-splitter.service

after:
  optolink-splitter.service        active
  optolink-maintenance-api.service active
  openv/maintenance/availability  online
```

The lifecycle fix is complete.

## 7. Home Assistant integration

New MQTT Discovery entities:

```text
number.vitodens_200_wb2a_wartung_brennerstunden_sollwert
number.vitodens_200_wb2a_wartung_zeitintervall_sollwert
sensor.vitodens_200_wb2a_wartung_brenner_seit_referenz
sensor.vitodens_200_wb2a_wartung_api_status
binary_sensor.vitodens_200_wb2a_wartung_api_verfuegbar
```

The two Number entities are **staging controls only**.

They publish to:

```text
openv/maintenance/stage/hours/set
openv/maintenance/stage/months/set
```

They do not publish to the raw splitter command topic.

Live staging-isolation tests proved:

```text
staged:     100 h / 1 month
controller:   0 h / 0 months
```

No controller write occurs until the explicit Apply action is confirmed.

## 8. Home Assistant Wartung view

Main file:

```text
config/optolink-splitter/homeassistant-dashboard.yaml
```

The `Wartung` view contains:

- API availability/status;
- actual burner-hours threshold;
- staged burner-hours target;
- actual month interval;
- staged month target;
- burner runtime since current reference;
- explicit Apply actions;
- protected maintenance reset;
- visible warnings about reference side effects;
- compact safety-information card.

The first live render exposed oversized default `button-card` icons. This was
a presentation-only issue. Dedicated compact maintenance action templates now
keep Apply/Reset cards small and consistent with the Diagnose/Pumpen design
language.

## 9. Home Assistant end-to-end verification

The full interaction path was verified live.

### Staging

In Home Assistant:

```text
actual hours    0 h
staged hours  100 h

actual months   0
staged months   1
```

The controller remained unchanged.

### Apply

The user applied only the month interval.

Observed in Home Assistant:

```text
actual hours    0 h
staged hours  100 h

actual months   1
staged months   1

API status      OK
```

This proved that the independently staged burner-hours target was not
accidentally applied.

### Restore

The month interval was then returned from `1 -> 0` using the same Home
Assistant staged + confirmed Apply path.

The restore succeeded.

Therefore this path is fully verified:

```text
HA Number
 -> stage topic
 -> explicit Apply + confirmation
 -> maintenance/cmnd
 -> guarded API
 -> shared core
 -> Optolink write
 -> readback
 -> normalized state
 -> Home Assistant
```

## 10. Evidence and source files

Primary implementation:

- `config/optolink-splitter/optolink_maintenance_core.py`
- `tools/optolink-maintenance.py`
- `tools/optolink-maintenance-api.py`
- `config/optolink-splitter/optolink-maintenance-api.service`
- `config/optolink-splitter/vdensho1-20c2-wb2a-homeassistant.py`
- `config/optolink-splitter/homeassistant-dashboard.yaml`

Documentation:

- `docs/optolink-maintenance.md`
- `docs/optolink-maintenance-api.md`
- `docs/homeassistant-dashboard-checkpoint-2026-09-24.md`
- `docs/project-roadmap.md`

Raw/research evidence:

- `config/optolink-splitter/research/vitosoft/maintenance-readonly-prep-2026-09-24-evidence.json`
- `config/optolink-splitter/research/vitosoft/maintenance-write-probe-prep-2026-09-24-evidence.json`

## 11. End-of-day state

Verified controller configuration after the final month restore:

```text
0x5721 = 0 h
0x5723 = 0 months
0x5724 = Grundzustand
```

The maintenance interval was intentionally re-baselined during controlled
tests, so the current `0x756C` reference is a test-era reference and must not
be interpreted as an original physical-service date.

The burner reference `0x7570` was also affected during the controlled
threshold/reset research and must be described as the current burner
maintenance reference, not automatically as the last physical service.

One UI cleanup item remains: verify the retained staged burner-hours target is
back at `0 h`. During the final HA month Apply test, `100 h` was intentionally
left staged to prove that independent staged values are not applied together.
Do not treat a staged value as controller configuration.

## 12. Tomorrow - 2026-09-25

Start with the existing repository state; do not reconstruct the dashboard or
maintenance backend from memory.

Recommended order:

1. verify/reset the retained staged burner-hours target to `0 h`;
2. do a short final Wartung UI polish:
   - replace cryptic top badges (`Ein / Aus / OK`) with clearer labels where
     practical;
   - consider numeric +/- or box-style controls instead of long sliders;
   - improve the very-small `Brenner seit Referenz` presentation;
3. live-test one guarded **Zeitprogramme** Home Assistant weekday edit and
   verify manager status, byte-exact readback and dashboard presentation;
4. return to Diagnose:
   - cold-load test without switching views;
   - finish deterministic colors on short-history cards;
   - review fault-history presentation;
5. review additional useful already-polled values for the top-level dashboard,
   especially effective boiler target, exhaust temperature, DHW flow,
   economy/frost/holiday state;
6. continue dashboard modernization one page at a time, with Pumpen/Heizung as
   the next visual candidates after the remaining Diagnose issues are stable.

Do not perform more maintenance backend write experiments unless a new
unverified behavior specifically requires one.
