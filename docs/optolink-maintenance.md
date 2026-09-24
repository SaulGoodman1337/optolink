# Optolink maintenance CLI

`optolink-maintenance` is the guarded service/maintenance interface for the
locally verified **Vitodens 200-W WB2A / VDensHO1 / 20C2 / SW03** maintenance
datapoints.

It deliberately exposes only operations that were verified on the real local
controller. It is not a generic raw Optolink write tool.

## Installation

The normal splitter update installs the CLI as:

```text
/usr/local/bin/optolink-maintenance
/usr/bin/optolink-maintenance -> /usr/local/bin/optolink-maintenance
```

The executable is installed with mode `0750`. Run it as root on the
Optolink-Splitter host.

After updating the repository deployment:

```bash
update
optolink-maintenance status
```

## Verified controller contract

| Address | Access used by CLI | Verified meaning |
| --- | --- | --- |
| `0x5721` | read/write | burner-runtime maintenance threshold; raw x 100 h; source range 0..10000 h; changing 0 -> nonzero can re-baseline `0x7570` |
| `0x5723` | read/write | maintenance time interval; 0..24 months |
| `0x5724` | read/write sequence | maintenance state; verified maintenance reset sequence `1 -> 0` |
| `0x756C` | read-only | `LastCheckInterval` 32-bit reference; exact Vitosoft wall-clock conversion still unresolved |
| `0x7570` | read-only | `LastBurnerCheck` burner-runtime-seconds baseline |
| `0x08A7` | read-only | total burner runtime in seconds |
| `0x088A` | read-only | total burner starts |

The verified derived burner runtime since the current maintenance reference is:

```text
(current 0x08A7 - stored 0x7570) / 3600
```

The maintenance reset does **not** reset `0x08A7` or `0x088A`.

## Commands

### Status

```bash
optolink-maintenance status
```

For machine-readable output:

```bash
optolink-maintenance --json status
```

Use `--verbose` when individual splitter requests/responses are needed for
diagnostics. Verbose protocol output goes to stderr so `--json` remains
parseable on stdout.

### Burner-runtime maintenance threshold

The operator-facing value is supplied in hours. Only exact 100 h steps in the
verified source range are accepted:

```bash
optolink-maintenance set-hours 3000 \
  --confirm-reference-reset RESET-BRENNERREFERENZ
```

Examples:

```text
0 h      -> raw 0
100 h    -> raw 1
3000 h   -> raw 30
10000 h  -> raw 100 / 0x64
```

The command reads the current value first. If the requested value is already
active, it performs no write unless `--force` is supplied.

Every write is independently read back. If the requested state cannot be
verified, the CLI attempts to restore and verify the previous value.

A later live CLI test exposed an important side effect that the earlier raw
probe had masked: changing `0x5721` from 0 h to a nonzero threshold
re-baselined `0x7570` to the current total burner-runtime counter. Therefore
every actual `set-hours` write now requires:

```text
--confirm-reference-reset RESET-BRENNERREFERENZ
```

The observed restore from 100 h back to 0 h did not re-baseline `0x7570`
again, but the CLI intentionally applies the confirmation guard conservatively
to every real threshold write.

Changing `0x5721` did not alter `0x756C`, `0x08A7` or `0x088A`.

### Time interval

```bash
optolink-maintenance set-months 12 \
  --confirm-reference-reset RESET-ZEITREFERENZ
```

Accepted values are `0..24` months.

**Important:** a write to `0x5723` re-baselines the 32-bit `0x756C`
`LastCheckInterval` reference. This side effect was observed on the real
controller for both the
temporary 24-month setting and the restore to zero. Therefore the CLI refuses
an actual `0x5723` write unless the explicit
`--confirm-reference-reset RESET-ZEITREFERENZ` acknowledgement is present.

When the requested month value is already active, the default behavior is a
no-op so the existing time reference is preserved. `--force` permits an
intentional same-value write, but the explicit reference-reset acknowledgement
is still required.

### Maintenance reset

```bash
optolink-maintenance reset --confirm RESET-WARTUNG
```

This executes the locally verified sequence:

```text
0x5724 = 1
0x5724 = 0
```

The CLI always attempts to return `0x5724` to `0` in a safety/finalization
path, even if the first write ACK or subsequent readback fails.

After the sequence it verifies:

- `0x5724` returned to `Grundzustand`;
- whether `0x756C` changed;
- whether `0x7570` changed;
- that any existing burner-runtime reference remains plausible;
- total burner runtime and total burner starts did not decrease.

Live testing shows that the reference effects are not perfectly symmetric:
`0x756C` is re-baselined by the reset, while `0x7570` is
controller-state/configuration dependent. An early reset initialized a zero
`0x7570` reference; a later end-to-end CLI reset with `0x5721 = 0 h`
left an existing `0x7570` reference unchanged. The CLI therefore reports the
two reference changes separately instead of claiming that both always reset.

The configured `0x5721` and `0x5723` thresholds remain intact.

## Guard rails

The CLI intentionally contains the following restrictions:

- a process lock prevents parallel maintenance CLI sessions;
- `0x756C` and `0x7570` have no write command;
- `set-hours` rejects values outside 0..10000 h or values not divisible by
  100 h;
- `set-hours` requires explicit acknowledgement that the burner-runtime
  reference `0x7570` may be re-baselined;
- `set-months` rejects values outside 0..24;
- `set-months` requires explicit acknowledgement of the reference reset;
- `reset` requires the exact `RESET-WARTUNG` confirmation token;
- writes use readback as the authoritative success criterion;
- ambiguous/failed writes attempt rollback to the previous configuration;
- maintenance reset is kept separate from burner-fault unlock/reset semantics.

## MQTT API backend

The guarded MQTT service now uses the same shared core as this CLI:

```text
optolink-maintenance
        \
         -> optolink_maintenance_core.py -> splitter MQTT
        /
optolink-maintenance-api
```

See [Optolink maintenance MQTT API](optolink-maintenance-api.md) for the
request/response schema, retained state topic, request-ID deduplication and
Home Assistant integration rules.

## Future Home Assistant use

The Home Assistant/dashboard workstream may build controls on top of this
verified contract, but should preserve the same constraints:

- bounded numeric control for `0x5721` with explicit warning that a real
  threshold change can re-baseline `0x7570`;
- bounded numeric control for `0x5723` with explicit warning that changing it
  re-baselines the `LastCheckInterval` reference;
- protected maintenance-reset action;
- no direct write access to `0x756C` or `0x7570`;
- no reuse of the maintenance reset as a burner-fault reset.

The CLI's `--json` mode is intended to make a future wrapper/service easier
without requiring Home Assistant to construct raw `w;0x....` requests.

## Live CLI verification status

The production CLI paths have been verified on the local controller for:

- no-op suppression for `set-hours 0` and `set-months 0`;
- range and confirmation guards with no write leakage;
- `set-hours 100` plus readback and restore to zero;
- explicit protection for the discovered `0x7570` re-baseline side effect;
- `set-months 1` plus readback and restore to zero;
- `0x756C` re-baselining on both actual `0x5723` writes while `0x7570`
  remained unchanged.

The guarded `reset` path is also live-verified end-to-end. The observed
`0x5724` transition was `00 -> 01 -> 00`; `0x756C` changed, while
`0x7570` remained unchanged with the burner-hours threshold configured to
0 h. The CLI now reports these reference effects independently.


### Note on `LastCheckInterval`

The raw `0x756C` value advances in seconds-like increments and changes when
the maintenance interval/reference is re-baselined. An earlier research pass
temporarily interpreted the 32-bit little-endian value as a Unix timestamp.
That interpretation is **not considered verified**: the public Vitosoft
reverse-engineering documentation lists `LastCheckInterval` as a special
converter whose algorithm is not implemented, and the decoded wall-clock value
does not consistently match the host/controller time. The CLI therefore keeps
this field semantically raw until the exact converter is reconstructed.
