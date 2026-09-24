# WB2A GFA P87/P09 high-resolution correlation

Status: **prepared; local syntax and 9/9 new logic tests pass. Live execution pending.**

## Why this probe exists

The successful 2026-09-24 triggered startup established the strongest current timing lead:

- P87 stayed at `0x60` during the high-start P09 plateau.
- P87 was first observed at `0x62` (bit 1 added) at 10:42:26.805.
- P09 was first observed below raw `0x93` / 57.6534% at 10:42:27.302.
- The observed sample separation was 0.497 s, but the true transition windows still overlapped because P84/P87/P06/P09 were sampled sequentially only once per roughly 1.2-second round.

See [successful triggered startup evidence](../config/optolink-splitter/research/vitosoft/gfa-triggered-startup-2026-09-24-evidence.json).

## Static P87 result

The exact local target is event 8211:

```text
P87
address: 0x4057
source label: GFA Status 3
length: 1 byte
conversion: NoConversion
```

The inspected private Vitosoft archive contains no value table, enum, or bit definition for P87/P85-P88. A public Vitosoft-derived export in `MorrisonHB/Optolink_02` independently confirms the same generic event name and address but likewise supplies no bit table.

Therefore P87 bit 1 must remain **unnamed**. The live association with plateau release is not a manufacturer-defined semantic label.

[Machine-readable static/probe evidence](../config/optolink-splitter/research/vitosoft/gfa-p87-static-and-hires-2026-09-24-evidence.json).

## Probe design

Helper:

```text
config/optolink-splitter/wb2a-gfa-p87-p09-hires-probe.py
```

Version:

```text
1.0.0
```

Implementation commit:

```text
c5e2b2662fe586df0c740b78100714db38723664
```

Git blob:

```text
afe7b9b63ac7cc87b7607403fbcc30c8ae1a569f
```

SHA256:

```text
b5249b35e30258494a8c3a7c681d31913f1a13a7663f302e23d146cc90f4413c
```

The Git blob exactly matches the locally compiled/tested file.

The helper pins the already hardware-proven triggered parent:

```text
wb2a-gfa-triggered-status-probe.py
SHA256 6d5810e1595ba6e464452dcd927259e9bade8f550a92b492fd40c2a27972604b
```

That parent recursively pins the status/pacing/quality/cycle/session/P80 chain.

### Sampling

Each guarded block contains two P87/P09 pairs and one final P80 identity guard.

Odd blocks:

```text
P87 -> P09 -> P87 -> P09 -> P80
```

Even blocks:

```text
P09 -> P87 -> P09 -> P87 -> P80
```

The order reversal reduces systematic timing bias from always reading one channel first.

The reply-to-next-request minimum remains **150 ms**, exactly as in the previous paced tests. This experiment changes channel count/order, not transport pacing.

A P80=20 at the end of the block validates both preceding pairs according to the existing acquisition policy. If an FF occurs anywhere in the block, the entire block is quarantined and the inherited bounded re-identification policy applies.

The JSONL records each accepted pair separately with:

- exact P87 and P09 receive timestamps;
- actual sample order;
- pair span in milliseconds;
- P87 raw value and set-bit positions;
- P09 raw value and x0.3922% conversion;
- changes relative to the preceding accepted pair;
- the following P80 guard.

This should reduce the same-channel timing bracket substantially compared with the four-runtime-channel startup capture.

## Trigger and restore

No new parameter-write implementation exists in this helper. It reuses the exact pinned parent sequence:

1. require P300 20C2;
2. read and retain current A1 normal/day setpoint `0x2306`;
3. require pre-trigger `0x55DC=0`;
4. confirm local GFA P80=20;
5. re-check mutable preconditions;
6. write only `0x2306=37 C`;
7. verify 37 C by immediate Virtual_READ;
8. switch to VS1 and capture P87/P09;
9. restore the exact original `0x2306` value;
10. verify the restored value by Virtual_READ before services restart.

There is no coding write, GFA_WRITE, PROCESS_WRITE, actuator test, gas-valve command, or flame-safety write.

As before, software cleanup cannot guarantee restoration after SIGKILL, host power failure, USB removal, or controller/hardware failure.

## Test status

The new file passes:

```text
python -m py_compile: PASS
new local logic tests: 9/9 PASS
```

The isolated build environment did not contain the pinned parent files, so it could not re-run the inherited chain there. On the appliance, `--self-test` first runs the 9 new tests and then the complete pinned triggered-parent self-test chain before live execution.

Live hardware behavior of this new sampling arrangement is not yet established.

## First live run

The burner must be off before the trigger. The helper enforces `0x55DC=0`; if it is still running after the previous experiment, it aborts before writing 37 C.

The default capture is intentionally shortened to **35 seconds**. The previous event appeared about 23.3 s after the 37 C trigger, so this retains margin while reducing the duration of the artificial high room-temperature demand.

Run as root in the same LXC. Leave the existing pinned helper files unchanged in `/root`.

```bash
(
  set -euo pipefail

  script=/root/wb2a-gfa-p87-p09-hires-probe.py
  tmp=$(mktemp)
  trap 'rm -f "$tmp"' EXIT

  curl --fail --show-error --location --retry 2 --connect-timeout 15 \
    'https://raw.githubusercontent.com/SaulGoodman1337/optolink/c5e2b2662fe586df0c740b78100714db38723664/config/optolink-splitter/wb2a-gfa-p87-p09-hires-probe.py' \
    -o "$tmp"

  printf '%s  %s\n' \
    'b5249b35e30258494a8c3a7c681d31913f1a13a7663f302e23d146cc90f4413c' \
    "$tmp" | sha256sum -c -

  install -m 0700 "$tmp" "$script"

  /opt/optolink/venv/bin/python "$script" --self-test
  /opt/optolink/venv/bin/python -u "$script" --execute --seconds 35
)
```

Do not manually set 37 C first. Do not manually stop the splitter or party emulator.

Retain both output files:

```text
LOG=/root/wb2a-gfa-p87-p09-hires-....log
JSONL=/root/wb2a-gfa-p87-p09-hires-....jsonl
```

If the precondition reports `0x55DC != 0`, no trigger write is sent; wait for a normal burner-off state before trying again.

If `SETPOINT_RESTORED=NOT_VERIFIED` appears, verify/reset the day setpoint manually before doing anything else.

## Analysis target

The next analysis will construct independent brackets for:

1. last P87 sample with bit 1 clear;
2. first P87 sample with bit 1 set;
3. last P09 sample on the high-start plateau;
4. first P09 sample below the plateau.

If those two transition intervals do not overlap, we can establish observed temporal ordering. If they still overlap, the correct conclusion remains correlation without strict ordering; the pacing should not be reduced merely to force a desired result.
