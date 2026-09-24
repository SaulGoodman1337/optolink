# Internal pump identity / K30-K31 read-only probe - 2026-09-24

## Purpose

Characterize the installed WB2A internal-pump capability and the configuration layer immediately upstream of the already verified runtime command `0x0A3C ~= 0x7660[1]`.

This probe is **read-only**. Do not write K30 or K31.

## Source-backed targets

| Address | Meaning | Notes |
| --- | --- | --- |
| `0x5730 / 1` | K30 - internal circulation-pump identification/capability | VDensHO1; 0=multi-stage, 1=variable-speed, 2=variable-speed with flow-rate capability |
| `0x5731 / 1` | K31 - set speed internal pump | VDensHO1 configuration object; not treated as a volatile runtime request |
| `0x7752 / 1` | K52 - hydraulic-separator sensor | helps determine whether a boiler-circuit-pump role is configured |
| `0x27E5 / 1` | E5 / KM-BUS heating-circuit pump A1 identification | distinguishes the A1 pump participant/configuration view |
| `0x27E6..0x27E9 / 1` | E6/E7/E8/E9 | A1 variable-speed pump configuration |
| `0x0A54 / 4` | internal-pump software-index block | VDensHO1 diagnostic; software-index subfield is byte 3 |
| `0x0A3C / 1` | final internal-pump command shadow | already hardware-correlated with `0x7660[1]` |
| `0x7660 / 2` | internal physical-pump runtime/output | byte 1 is the verified speed path |
| `0x7663 / 2` | A1 runtime/output | useful same-window discriminator |

## Bounded read-only sequence

```bash
echo "=== Internal pump identity / role ==="
/usr/local/bin/optolink-debug request "r;0x5730;1;raw;False"
/usr/local/bin/optolink-debug request "r;0x5731;1;raw;False"
/usr/local/bin/optolink-debug request "r;0x7752;1;raw;False"

echo
echo "=== A1 pump configuration ==="
/usr/local/bin/optolink-debug request "r;0x27E5;1;raw;False"
/usr/local/bin/optolink-debug request "r;0x27E6;1;raw;False"
/usr/local/bin/optolink-debug request "r;0x27E7;1;raw;False"
/usr/local/bin/optolink-debug request "r;0x27E8;1;raw;False"
/usr/local/bin/optolink-debug request "r;0x27E9;1;raw;False"

echo
echo "=== Internal pump software identity ==="
/usr/local/bin/optolink-debug request "r;0x0A54;4;raw;False"

echo
echo "=== Same-window runtime correlation ==="
/usr/local/bin/optolink-debug request "r;0x0A3C;1;raw;False"
/usr/local/bin/optolink-debug request "r;0x7660;2;raw;False"
/usr/local/bin/optolink-debug request "r;0x7663;2;raw;False"
```

## Interpretation

### K30 / 0x5730

```text
00 = multi-stage / stufig
01 = variable-speed / drehzahlgeregelt
02 = variable-speed with flow-rate capability
```

A result of `02` is especially important: it proves that this controller/pump configuration distinguishes a flow-capable internal pump. It does **not** by itself prove that the flow value is exposed as a normal VDensHO1 datapoint.

### K31 / 0x5731

Preserve the raw byte. Although the metadata defines read/write access, do not modify it during this research phase. K31 is a configuration/set-speed object, not a demonstrated volatile command path.

### 0x0A54

Read all four bytes. The Vitosoft definition places the internal-pump software-index subfield at byte position 3. Preserve the entire block because the preceding bytes may contain related participant identity/version material.

## Decision tree

- **K30=00:** revisit why speed-like runtime bytes are still present; the configuration says multi-stage.
- **K30=01:** variable-speed internal pump without declared flow-rate capability. Continue with firmware/runtime arbitration; do not spend time hunting a mandatory flow sensor.
- **K30=02:** prioritize the internal-pump/KM-BUS telemetry for a flow-rate channel and inspect non-obvious VDensHO1 events/blocks around the pump participant.
- **K52=00:** no hydraulic-separator sensor configured; normal direct A1 heating remains the expected E6/E7-controlled path.
- **K52 nonzero:** re-evaluate K31 as a boiler-circuit-pump configuration input.
- **0x0A54 valid/non-FF:** record it as the internal-pump software identity and correlate it with any manufacturer/protocol evidence.

## Safety boundary

No writes to `0x5730`, `0x5731`, E5-E9, K52 or any KM-BUS participant object are part of this probe.
