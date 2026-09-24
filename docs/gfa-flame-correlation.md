# WB2A GFA flame/status correlation probe

Status: **v1.0.2 prepared. v1.0.1 reached the controller and restored the setpoint safely, but captured no burner startup before a known sporadic P87=FF; the child now inherits the reviewed FF re-entry policy and explicitly reports whether startup activity was seen.**

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

## First production-VS1 live run - null startup + FF transport abort

The first v1.0.1 production run successfully passed all controller preconditions and verified the temporary demand stimulus:

```text
P300 identity        = 20C2
original 0x2306      = 21 C
pre-trigger 0x55DC   = 0
P80 independent      = 20, 20
temporary 0x2306     = 37 C, readback verified
```

The observation then produced **32 complete accepted mixed rounds**. Every complete round was:

```text
P84                = 00
P87                = 00
0x55D3 flame       = 0
0x55DD flame       = 0
0x55D3 lockout     = 0
0x55D3 fine value  = 0
```

The two independent flame indicators agreed in every complete round. No startup activity was captured.

Attempt 33 returned raw `FF` at P87 (`0x4057`). The value was correctly quarantined as unresolved, but v1.0.1 of the mixed child failed to catch the inherited `SuspectFF` exception and therefore aborted instead of running the already-reviewed P300/P80 re-identification path.

Cleanup was successful:

```text
TRIGGER_VERIFIED=yes
SETPOINT_RESTORED=yes
P300_RESTORED=yes
SPLITTER_RESTARTED=yes
post-restore 0x55DC=0
```

`P80_CONFIRMED=NOT_CONFIRMED` in this failed run means the closing observation guard was not reached after the FF abort; it does not invalidate the earlier two independent P80=20 checks or imply a changed burner variant.

### Important interpretation

The identical 37 C room-setpoint stimulus had previously produced P84=02 only 4.793 s after the trigger and then a complete controller-driven startup. Here it produced no P84/P87/flame activity for more than 32 s. Therefore **0x2306=37 is a bounded heating-demand stimulus, not a direct burner-start command**. Whether the controller actually starts the burner also depends on the current thermal/control state (for example hysteresis or restart inhibition).

Machine evidence: [gfa-flame-correlation-null-run-2026-09-24-evidence.json](../config/optolink-splitter/research/vitosoft/gfa-flame-correlation-null-run-2026-09-24-evidence.json).

### v1.0.2 correction

The mixed child now catches the same inherited `SuspectFF` exception as the reviewed status/quality helpers:

- reject the entire current round;
- retain raw FF as rejected evidence;
- perform full P300 20C2 + independent P80 + same-session P80 re-identification;
- open a new segment only if the inherited bounded policy permits it;
- clear prior state so no transition is inferred across the quality gap;
- emit `STARTUP_ACTIVITY_SEEN=yes|no` at observation completion.

No trigger, write, restore or GFA safety boundary changed.
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
