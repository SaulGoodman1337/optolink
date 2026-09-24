# WB2A GFA P87/P09 high-resolution correlation

Status: **live run completed successfully; temporal ordering resolved. P87 bit 1 becomes set before P09 leaves the high-start plateau. Causality and manufacturer bit semantics remain unresolved.**

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

## Live result - temporal ordering resolved

Source: `Eingefügter Text(20260924-090716).txt`, 139565 bytes, 707 lines, SHA256:

```text
7300d9dc272e8668c0ab2d518826a9f04037cb09dbba47f97dd382570b3ce946
```

The 35-second run completed cleanly:

- 29 accepted P80-guarded blocks;
- 58 accepted P87/P09 pairs;
- zero rejected blocks;
- zero reconnections;
- no observed FF;
- all expected P80 identity checks remained `20`;
- temporary 37 C setpoint and exact restore to 21 C were both readback-verified;
- P300 20C2 and services were restored;
- final result `PASS`.

### Critical non-overlapping transition windows

P87 bit 1:

```text
last confirmed clear: P87=0x60 at 11:06:06.897
first confirmed set:  P87=0x62 at 11:06:07.392
transition bracket:   (11:06:06.897, 11:06:07.392]
width:                495 ms
```

P09 high-start plateau:

```text
last confirmed plateau: P09=0x93 at 11:06:07.649
first confirmed lower:  P09=0x91 at 11:06:08.139
transition bracket:     (11:06:07.649, 11:06:08.139]
width:                  490 ms
```

The intervals **do not overlap**. The latest possible time of the P87 bit-1 transition is 11:06:07.392, while the earliest possible P09 release is after the last confirmed `0x93` sample at 11:06:07.649. There is therefore a **minimum 257-ms separation** between the two transition windows.

The critical block makes this directly visible:

```text
11:06:06.897  P87 = 0x60
11:06:07.392  P87 = 0x62   bit 1 now set
11:06:07.649  P09 = 0x93   plateau still present
11:06:07.856  P87 = 0x62
11:06:08.139  P09 = 0x91   plateau has begun to fall
```

Thus this run establishes **temporal ordering**:

> **P87 bit 1 becomes set before P09 leaves the high-start modulation plateau.**

This is stronger than the previous four-channel run, where the two event windows overlapped.

It still does **not** establish:

- that P87 bit 1 causes the P09 release;
- that bit 1 is a flame-detection signal;
- that bit 1 means "flame stabilized", "stabilization complete" or "regulation enabled";
- any manufacturer-defined semantic name.

The correct current description is an **unnamed GFA status precursor/marker that precedes release of the high-start P09 plateau**.

Relative to the 37 C trigger:

| Observation | Time after trigger |
| --- | ---: |
| last P87 bit-1 clear | 21.502 s |
| first P87 bit-1 set | 21.997 s |
| last P09 `0x93` plateau sample | 22.254 s |
| first P09 below plateau | 22.744 s |

The first observed P87=`60` occurred 12.640 s after the trigger. This narrower run observed P87 `20->50->60->62`; omission of the earlier `40` state does not supersede the prior wider capture, which observed `20->40->50->60->62`.

The same-channel receive interval was typically about 0.5 seconds (median approximately 497 ms for P87 and 496 ms for P09). No faster polling is required merely to establish ordering.

At cleanup, the original 21 C setpoint was restored and verified. Immediate `0x55DC=0x29` (41 decimal) again showed that restoring the room setpoint does not imply immediate burner shutdown.

[Machine-readable live evidence](../config/optolink-splitter/research/vitosoft/gfa-p87-p09-hires-run-2026-09-24-evidence.json).

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

Live hardware behavior is now established for the successful 35-second run above.

## Reproduction command

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

## Analysis conclusion

The requested brackets are now measured and do not overlap. Temporal ordering is resolved for this run: P87 bit 1 is set before P09 leaves the high-start plateau. No additional faster polling is justified solely for ordering. Future work should focus on static/vendor semantics and production-safe access/integration rather than increasing diagnostic bus load.
