# WB2A GFA flame/status correlation probe

Status: **v1.0.1 prepared for permanent production VS1; first v1.0.0 live attempt aborted safely at settings preflight; corrected live run pending**

## Goal

Resolve the timing relationship between raw GFA phase/status values and two
independent, already hardware-verified normal Optolink flame indicators.

This is the next step after the Collector-v6 static search established that
Vitosoft contains no manufacturer enum/bit table for P84-P88.

## Channels

Each accepted mixed-VS1 round reads, in order:

| Order | Transport | Address | Meaning |
| ---: | --- | --- | --- |
| 1 | GFA_READ 0x6B | P84 / `0x4054` | raw GFA operating phase |
| 2 | Virtual_READ 0xF7 | `0x55D3 / 9` | shared fire-control runtime block |
| 3 | GFA_READ 0x6B | P87 / `0x4057` | raw GFA status 3 |
| 4 | Virtual_READ 0xF7 | `0x55DD / 1` | independent source-labelled flame signal |
| 5 | GFA_READ 0x6B | P80 / `0x4050` | local GFA identity guard, must remain 0x20 |

Hardware-verified decoding used for correlation:

```text
0x55D3 byte 5 bit 0x20 = flame
0x55D3 byte 5 bit 0x40 = fire-control lockout
0x55D3 byte 0          = fine GFA power/control diagnostic value

0x55DD byte 0 bit 0x20 = flame signal
```

The two flame channels remain independent observations. Their agreement or
disagreement is recorded per round.

## Trigger and safety boundary

The helper does not reimplement the trigger logic. It SHA256-pins
`wb2a-gfa-triggered-status-probe.py` and reuses its tested sequence:

1. require local P300 identity 20C2;
2. require burner inactive via the existing `0x55DC=0` precondition;
3. read and retain the exact current A1 normal/day setpoint `0x2306`;
4. write only `0x2306=37 C` as a bounded demand stimulus;
5. verify exact readback;
6. capture the mixed F7/6B startup window;
7. restore the exact original `0x2306` value with readback verification before
   restarting services.

There is no GFA_WRITE, PROCESS_WRITE, coding write, actuator command, gas-valve
command or flame-safety write.

As with the inherited trigger helper, restoration cannot be guaranteed after
SIGKILL, host power loss, USB removal or hardware failure.

## Timing

The mixed F7/6B transport was already hardware-validated in one persistent VS1
session. This correlation probe retains a conservative **150 ms minimum
reply-to-next-request gap**.

A complete round therefore spans sequential samples, not simultaneous ones.
Every transition must be treated as a time bracket between the last old sample
and the first new sample.

## Offline verification

GitHub Actions run `36049274704` completed successfully:

- Python compile: PASS;
- new flame-correlation frame/decoder tests: **6/6**;
- pinned triggered-parent protocol tests: PASS;
- pinned triggered-parent integration/cleanup tests: PASS;
- complete recursive GFA transport/status test chain: PASS.

The inherited tests include exact setpoint restoration, active-burner refusal,
lost trigger response, interruption cleanup, restore hard-failure handling,
fixed write-address bounds, FF quarantine, P80 identity guards and service
restoration.

## First live attempt: preflight-only abort

The first live invocation on 2026-09-24 completed the full offline test chain, then aborted immediately with:

```text
ERROR: Require explicit vs1protocol = False; settings are never modified.
```

This was a helper compatibility defect, not a controller or transport failure. The
historical P80 parent was written before the production splitter moved to permanent
`vs1protocol=True`, and its standalone `read_settings()` deliberately rejects that
mode.

The correlation child has been corrected to parse the production settings itself
without importing or modifying them. It now requires:

```text
vs1protocol = True
port_vitoconnect = None
port_optolink = a literal local /dev/... path
```

The old parent remains unchanged and SHA256-pinned. Trigger/write/restore behavior
is therefore unchanged; only the child entrypoint's configuration precondition is
updated for the current production architecture.

The failed first attempt occurred before serial ownership and before
`run_triggered()`; no controller write or observation was performed.

## Live interpretation targets

The live run is intended to answer only timing/order questions such as:

- At which raw P84 state does the first independent flame signal appear?
- Do `0x55D3` and `0x55DD` assert within the same sequential round?
- Which P87 raw value/bit transition brackets first flame?
- Does P87 bit 1 occur at flame establishment, or only later as already
  indicated by its strong correlation with high-start plateau release?
- Does the fine `0x55D3[0]` control value start changing before flame, as
  earlier pre-purge evidence suggests?

Do **not** assign manufacturer names to P84 states or P87 bits merely because
they happen near a flame transition.

## Result handling

Retain both printed paths:

```text
LOG=...
JSONL=...
```

Analysis should use receive timestamps and transition windows from JSONL rather
than console line order alone.
