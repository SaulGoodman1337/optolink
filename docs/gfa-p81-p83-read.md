# GFA P81-P83 read-only identity runbook - 2026-09-24

## Purpose

Complete the local burner-controller/GFA software identity without adding new transport logic or changing controller parameters.

Static source evidence for the local `P80=0x20` GFA branch defines:

| Parameter | Address | Meaning | Access |
| --- | --- | --- | --- |
| P80 | `0x4050` | GFA/BCU variant selector | GFA_READ, 1 byte |
| P81 | `0x4051` | FA software version | GFA_READ, 1 byte |
| P82 | `0x4052` | FA software revision | GFA_READ, 1 byte |
| P83 | `0x4053` | appliance/GFA configuration | GFA_READ, 1 byte |

All four use `NoConversion`. The recovered definition has `AccessMode=Read` and no GFA write function.

Machine-readable preparation: [gfa-p81-p83-read-prep-2026-09-24-evidence.json](../config/optolink-splitter/research/vitosoft/gfa-p81-p83-read-prep-2026-09-24-evidence.json).

## Preconditions

- production splitter is active and already running the validated permanent VS1 + read-only GFA patch;
- use the existing `/usr/local/bin/optolink-debug` MQTT client;
- no service stop and no protocol-mode change are required;
- do not use a write command.

## Bounded read sequence

Run on the Optolink-Splitter LXC:

```bash
echo "=== P80 opening guard ==="
/usr/local/bin/optolink-debug request "gfaread;0x4050;1;raw;False"

echo
echo "=== P81 software version ==="
/usr/local/bin/optolink-debug request "gfaread;0x4051;1;raw;False"

echo
echo "=== P82 software revision ==="
/usr/local/bin/optolink-debug request "gfaread;0x4052;1;raw;False"

echo
echo "=== P83 appliance/GFA configuration ==="
/usr/local/bin/optolink-debug request "gfaread;0x4053;1;raw;False"

echo
echo "=== P80 closing guard ==="
/usr/local/bin/optolink-debug request "gfaread;0x4050;1;raw;False"
```

## Acceptance criteria

Treat the run as valid only when:

1. opening P80 returns success with raw `20`;
2. P81, P82 and P83 each return a successful one-byte value;
3. closing P80 again returns success with raw `20`;
4. no OL error, splitter restart or second-FF/quarantine failure is observed around the sequence.

If P80 is not `20`, stop interpretation of P81-P83 for this run.

## Interpretation rules

Record raw hex first:

```text
P80 = 0x..
P81 = 0x..
P82 = 0x..
P83 = 0x..
```

Do not automatically concatenate P81/P82 into a marketing/release version. A source-backed notation may be added later if Vitosoft/service documentation supplies the mapping.

Keep these identities separate:

- main regulation: `0x778C/0x778D = 01/03`, raw pair `0x0103`;
- device software index: `0x00FB = 03`;
- GFA branch: P80 = `0x20`;
- GFA software identity: P81/P82;
- GFA appliance/configuration byte: P83;
- coding-card summary: `0x7656`;
- coding-plug GFA diagnostics: P90/P100-P108.

## Follow-up

After a successful run:

- preserve the five responses verbatim;
- update the machine-readable evidence with the measured P81-P83 bytes;
- mark the P81-P83 TODO complete in [research-plan-2026-09-24.md](research-plan-2026-09-24.md);
- only then decide whether these stable identity values should be added as low-frequency Home Assistant diagnostic entities.
