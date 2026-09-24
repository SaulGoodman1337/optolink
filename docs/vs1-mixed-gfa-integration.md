# WB2A mixed VS1 Virtual/GFA compatibility probe

Status: **prepared, read-only, live execution pending.**

## Why this test exists

The direct GFA work has resolved the P87/P09 ordering. The remaining production question is whether the normal Virtual_READ traffic and direct GFA_READ traffic can coexist in one persistent VS1/KW session on this exact VDensHO1 / 20C2 appliance.

The inspected upstream splitter already supports permanent VS1/KW mode for its normal Virtual_READ / Virtual_WRITE path. In that mode structured datapoint reads use F7 and writes use F4; one main loop owns the serial interface and serializes poll-list, MQTT and TCP work. The current structured generic request path is not implemented for VS1, and optolinkvs1.py has no structured GFA_READ helper even though 0x6B is known in the function table.

Upstream inspected at `philippoo66/optolink-splitter` main commit `c1ee204a1421447721603c5f21c6da7337fdac97`, source version `1.11.5.0`.

Production must therefore **not** be switched to `vs1protocol=True` merely from source inspection. This probe verifies the required mixed traffic first.

## Probe identity

- File: `config/optolink-splitter/wb2a-vs1-mixed-compat-probe.py`
- Version: `1.0.0`
- Commit: `2b7b5cff88dd732ea062b70873bca1873fcfad5a`
- Git blob: `dab9f3e5134c7706e269b7a111e2f715c8fda225`
- SHA256: `0e2bc4cc59e54d6c189d31545436328194f515cb9acb7a2b4d1807102ec5bb69`
- Pinned P80 parent SHA256: `6de883c422a09c821b342d12e5bb71dd3d518d8115ec2495bdfb202f5a7f50cb`

## Safety boundary

This helper is read-only. It has no Virtual_WRITE, GFA_WRITE, PROCESS_WRITE, coding write, actuator command or setpoint trigger. It stops the active party emulator and splitter only for exclusive serial ownership, then restores their previous running state.

It requires the production configuration to remain `vs1protocol = False` and `port_vitoconnect = None`; it does not modify either setting.

## Test sequence

### P300 baseline

The helper reads seven stable Virtual_READ values: `00F8/2`, `00FB/1`, `2306/1`, `2323/1`, `6300/1`, `6773/1`, and `778C/2`. Baseline identity must be `20C2`.

### One persistent VS1 session

The first request is STX + `F7 00F8 02` and must again return `20C2`. Without another EOT/protocol re-init, the helper then interleaves:

~~~text
F7 00FB/1
6B P80
F7 2306/1
6B P06
F7 2323/1
6B P09
F7 6300/1
6B P87
F7 6773/1
F7 778C/2
6B P80
~~~

The existing 150-ms diagnostic minimum reply gap is retained. Every stable F7 value must exactly equal its P300 baseline. Both P80 guards must be `0x20`; a GFA `0xFF` aborts the test. P06/P09/P87 are recorded only as runtime samples.

### P300 post-check

The helper returns to P300, verifies `20C2`, and reads the same stable values again. PASS requires `P300 before == VS1 F7 == P300 after` for every stable datapoint.

## Tests

The published helper embeds 8 new frame/allowlist tests and recursively runs 23 pinned P80/recovery tests. Before publication, the same runtime path was additionally exercised in 8 build-harness integration scenarios covering success, mixed F7/6B traffic, no write opcode, wrong P80, GFA FF, stable-value mismatch, service restoration and inactive-party preservation.

## Live command

No burner start is required. Do not change setpoints or operating mode during the short test.

~~~bash
(
  set -euo pipefail

  script=/root/wb2a-vs1-mixed-compat-probe.py
  tmp=$(mktemp)
  trap 'rm -f "$tmp"' EXIT

  curl --fail --show-error --location --retry 2 --connect-timeout 15 \
    'https://raw.githubusercontent.com/SaulGoodman1337/optolink/2b7b5cff88dd732ea062b70873bca1873fcfad5a/config/optolink-splitter/wb2a-vs1-mixed-compat-probe.py' \
    -o "$tmp"

  printf '%s  %s\n' \
    '0e2bc4cc59e54d6c189d31545436328194f515cb9acb7a2b4d1807102ec5bb69' \
    "$tmp" | sha256sum -c -

  install -m 0700 "$tmp" "$script"

  /opt/optolink/venv/bin/python "$script" --self-test
  /opt/optolink/venv/bin/python -u "$script" --execute
)
~~~

The pinned `/root/wb2a-gfa-p80-probe.py` must remain unchanged beside it.

A PASS tail includes `STABLE_VALUES_MATCH=yes`, `P300_RESTORED=yes`, `SPLITTER_RESTARTED=yes`, and `RESULT=PASS`. If the test fails, do not switch production to VS1 and do not blindly rerun; inspect the log first.

## Production direction after a PASS

A PASS would justify a staged implementation, not an immediate production flip:

1. keep one serial owner: the splitter;
2. run it permanently in VS1/KW mode;
3. retain existing HA Virtual_READ/WRITE traffic through F7/F4;
4. add a narrow structured `gfaread` / `read_gfa_ext()` path for 6B;
5. place P06/P09/P87/P80 in a conservative diagnostic poll group;
6. publish them through the existing MQTT/Home Assistant path;
7. retain FF quarantine/plausibility handling for direct GFA values.

This is preferable to periodic service stops and P300<->VS1 switching.

The local updater currently performs `git fetch origin main` followed by `git reset --hard origin/main` inside `/opt/optolink`. Therefore a local production patch would be erased on update unless the repository installer/updater reapplies it atomically or the change is accepted upstream. Do not hand-edit `/opt/optolink` as the final solution.

## P87 semantic boundary

The current static source evidence still provides no P87 bit table. Public Viessmann context says WB2A minimum ionization current should already be present when the flame forms, roughly 2-3 seconds after the gas valve opens, while VSKO E8 / codes 61 and 189 concern ionization current during a 10-second start phase and VSKO code 5 is described as flame loss during stabilization time.

Combined with the measured P87 bit-1 transition on the approximately ten-second timescale and before P09 release, the best current interpretation is an **unnamed GFA status marker/precursor near the end of the supervised start/stabilization interval**. This is not a manufacturer-defined bit name and does not prove causality.

Machine-readable checkpoint: [semantic/integration evidence](../config/optolink-splitter/research/vitosoft/gfa-p87-semantics-vs1-integration-2026-09-24-evidence.json).
