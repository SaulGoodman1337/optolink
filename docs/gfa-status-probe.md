# WB2A GFA status/startup probe

Status: **first live status run completed; it started already in P84=06, so the actual burner start was missed. A guarded 37 C trigger follow-up is prepared and offline-tested.**

This helper follows the successful continuous startup capture documented in [GFA pacing comparison](gfa-paced-comparison.md). Its purpose is narrowly defined: observe raw GFA phase/status bytes around a normal startup without assigning undocumented semantics.

## Why these targets

The locally confirmed VDensHO1 / 20C2 burner variant is GFA (P80 = 0x20). Derived private-archive evidence places these read-only events inside that branch:

| Parameter | Address | Recovered source label | Current interpretation |
| --- | --- | --- | --- |
| P12 | 0x400C | Digitaleingang mit Bit-Kodierung | Raw bit-coded digital input; bit meanings unknown |
| P84 | 0x4054 | GFA Betriebsphase | Raw operating phase; enum unknown |
| P85 | 0x4055 | GFA Status 1 | Raw status byte; bit meanings unknown |
| P86 | 0x4056 | GFA Status 2 | Raw status byte; bit meanings unknown |
| P87 | 0x4057 | GFA Status 3 | Raw status byte; bit meanings unknown |
| P88 | 0x4058 | GFA Status 4 | Raw status byte; bit meanings unknown |
| P80 | 0x4050 | variant selector | Must remain 0x20 |

A public Vitosoft-derived export in MorrisonHB/Optolink_02 independently contains the same generic P12 and P84-P88 labels. It supplies no P84 enum and no P12/P85-P88 bit table, so the helper deliberately does not invent names such as flame, ignition, gas valve or safety chain.

[Machine-readable target evidence](../config/optolink-splitter/research/vitosoft/gfa-status-targets-2026-09-24-evidence.json) records the branch constraints, public corroboration and exclusions.

### Important variant exclusions

Do not transfer nearby definitions from other burner variants into this WB2A GFA branch.

- The common/SCOT/CES P89 label `b0=FA9, b1=FA11, b2=FA8` is **not** applied locally. The confirmed GFA branch uses a different event at the same 0x4059 address.
- P13/P14/P15 ionization-related labels and P17 flame-formation-time occur in the wider VSKO union/public exports but are not members of the selected local GFA group. They are not enabled by this probe.
- P84 raw values 00/02/04/05/06 remain raw states until a manufacturer enum or independent correlation establishes names.

An ordinary P300 datapoint at 0x55DD is named `Flammensignal` in the wider event export. It is a separate future correlation candidate, not a simultaneous channel in this VS1-exclusive test.

## First live status result - 2026-09-24

The first 60-second status run completed cleanly: 49 accepted rounds, zero rejected rounds, zero reconnects, closing P80=20, verified P300 20C2 restoration and service restart.

However, the capture began with P84 already at `06` and P84 stayed `06` for the entire run. It therefore did **not** capture the actual 00->02->04->05->06 startup sequence.

Observed raw values:

| Parameter | Observed values | Change |
| --- | --- | --- |
| P84 | `06` | none |
| P12 | `00` | none |
| P85 | `21` | none |
| P86 | `0B` | none |
| P87 | `60 -> 62` | **bit 1 changed 0 -> 1** |
| P88 | `00` | none |

The first observed P87=60 sample was at 09:25:13.167 +02:00. The first P87=62 sample was at 09:25:20.539 +02:00. Bits 5 and 6 remained set; only bit 1 changed. This is a useful timing candidate, but it is not assigned a functional meaning.

[Machine-readable live evidence](../config/optolink-splitter/research/vitosoft/gfa-status-run-2026-09-24-evidence.json).

## Measurement design

Helper: [`wb2a-gfa-status-probe.py`](../config/optolink-splitter/wb2a-gfa-status-probe.py), version 1.0.0.

Implementation commit: `1e76701d8395841a081a3bd6eca67d8ffcbc12af`.

SHA256:

```text
912de7276ed2a26330abbfb0d7c5778862d171fa5a179ab1b73043fdee9c59bc
```

Git blob:

```text
b863aefb16da180564baf3dc0468b25f2cf3b141
```

The exact pinned parent is `wb2a-gfa-paced-probe.py` SHA256 `053c7806d863c7fe551903a24498f4841c0d2235b661e674f80f07696065e974`; that helper recursively verifies the quality/cycle/session/P80 chain.

The new helper keeps **five same-session reads per measurement round**, matching the count of the clean paced startup trace:

- Bank A: P84, P12, P85, P86, then P80 guard.
- Bank B: P84, P12, P87, P88, then P80 guard.
- A/B alternate each attempted round.

Thus P84 and P12 are sampled every round. P85/P86 and P87/P88 are sampled every other round. This is preferable to reading all six runtime targets plus P80 every round because the previously brief P84=04 and P84=05 stages were each only about one second apart.

Minimum reply-to-next-request spacing remains the experimental 150 ms. It is not a recovered Viessmann specification and is not claimed to eliminate FF replies.

## Data policy

For P12 and P85-P88 the JSONL stores:

- raw byte and hex byte;
- set bit positions;
- exact host receive time;
- reply latency and paced gap;
- changes as old/new raw bytes plus XOR-derived changed-bit positions.

No bit receives a functional name. P84 is stored as a raw byte without bit decomposition. A following P80=20 guard confirms branch/alignment at that point; it is not a checksum proving each preceding value physically correct.

FF handling is inherited from the reviewed quality policy:

- the whole current round is rejected;
- raw FF remains in the rejected evidence;
- no zero/last-value substitution;
- a full P300 20C2 + two independent P80=20 + same-session P80=20 re-identification may open a new segment;
- at most three re-identifications;
- another FF too soon after re-entry stops instead of entering a retry loop;
- non-FF identity mismatch, timeout, unexpected trailing bytes, partial writes and excess host gaps remain fatal.

## Safety boundary

The fixed live TX allowlist contains only the previously used communication controls/identity reads plus one-byte GFA_READ function 0x6B for P12, P80 and P84-P88.

There is:

- no GFA_WRITE or PROCESS_WRITE;
- no arbitrary address option;
- no burner start command;
- no actuator test;
- no gas-valve or flame-safety command;
- no coding change;
- no permanent protocol-setting change.

Normal HA/MQTT/TCP polling and a previously active party emulator are paused while the helper owns the serial port. An externally maintained request can therefore change. Prefer a normal boiler-controlled heat demand, as in the previous successful startup capture.

## Offline verification

Compilation and plan-only invocation passed. `--self-test` passes **143 offline tests**:

```text
23 P80 helper tests
33 session helper tests
33 cycle helper tests
20 quality helper tests
16 pacing helper tests
18 new status-probe tests
```

The new tests cover fixed alternating banks, exact read framing, no write functions, 150-ms pacing, raw bit views, XOR bit-change reporting, P84-only phase-change counting, FF quarantine on every runtime position, bounded re-entry, wrong P80, timeout, trailing data, unknown addresses, scheduler stalls, inactive party behavior, duration bounds and simulated 60-second completion.

These are simulated tests; they do not establish the live status-byte semantics.

## Triggered follow-up - capture the real start

The next helper changes only the already-supported A1 normal-room/day setpoint, event 82 at `0x2306`, as a controlled demand stimulus.

Helper: [`wb2a-gfa-triggered-status-probe.py`](../config/optolink-splitter/wb2a-gfa-triggered-status-probe.py), version 1.0.1.

Implementation commit:

```text
8259cd5f3c07c4d46939e17e7bc87dc47378717f
```

Git blob:

```text
98f2f5342d24e32d7cb8b088a5af3589d378526d
```

SHA256:

```text
6d5810e1595ba6e464452dcd927259e9bade8f550a92b492fd40c2a27972604b
```

The published Git blob exactly matches the offline-tested local file. The helper recursively pins the unchanged status/pacing/quality/cycle/session/P80 chain.

### Trigger sequence

1. Require the splitter to be running; pause the active party emulator and splitter.
2. Verify P300 identity 20C2.
3. Read and retain the exact current A1 normal setpoint at `0x2306`.
4. Read `0x55DC` and require raw zero so the burner is off before the stimulus.
5. Require the original setpoint to be 3..36 C; if it is already 37, abort without writing.
6. Confirm P80=20 twice.
7. Return to P300 and re-read both mutable preconditions.
8. Mark cleanup as required **before** the write, then write only `0x2306=37` and require exact readback.
9. Switch immediately to VS1.
10. Capture `P84/P87/P06/P09` every round, followed by P80=20.
11. In cleanup, return to P300 and restore the exact pre-read `0x2306` value with readback verification before services restart.

The focused four-channel set deliberately combines the new P87 candidate with the already validated startup observables:

- P84 raw phase;
- P87 raw status/bit positions;
- P06 GFA-reported fan speed, x30 rpm;
- P09 GFA modulation setpoint, x0.3922%.

This gives roughly the same five-read round size as the clean paced startup capture while directly testing whether P87 bit 1 aligns with P84 transitions or the later release of the high-start plateau.

### Write boundary

The only parameter write address implemented by this helper is `0x2306`.

Allowed setpoint writes are only:

- temporary value 37 C; and
- the exact original value captured before the trigger.

There is no coding write, GFA_WRITE, PROCESS_WRITE, actuator test, gas-valve command or flame-safety write. A failed restore is a hard FAIL and is printed as `SETPOINT_RESTORED=NOT_VERIFIED` plus a `CRITICAL` error.

The cleanup covers ordinary exceptions and SIGINT/SIGTERM/SIGHUP. It cannot guarantee restoration after SIGKILL, host power failure, USB removal or controller/hardware failure.

### Offline verification

The published live code was compiled and exercised through **168 tests**:

```text
143 inherited transport/status tests
15 triggered-probe protocol/frame tests
10 triggered-probe integration/cleanup tests
```

The new integration tests include burner-active refusal, already-37 refusal, mutable-precondition change, exact 37->original restoration, lost trigger response after the simulated physical write, interruption during VS1 capture, hard restore failure, fixed write address/value bounds, focused read-address bounds and inactive-party preservation.

### First trigger attempt - parser correction

The first triggered run on 2026-09-24 did **not** enter the GFA observation loop. Preconditions were clean: original `0x2306=21 C`, `0x55DC=0`, P300 `20c2`, and two independent P80 replies `20`.

The temporary write request was:

```text
41 06 00 02 23 06 01 25 57
```

The WB2A replied:

```text
41 05 01 02 23 06 01 32
```

Version 1.0.0 incorrectly interpreted the final payload byte `01` as a data-length field requiring one following echoed data byte. Live evidence shows that for this successful Virtual_WRITE response it is the **acknowledged write length**. The response contains no echoed value.

The same response was received for all three cleanup writes requesting the original 21 C. Because v1.0.0 raised before its following Virtual_READ, the run itself could not prove the restored value by readback. The controller nevertheless acknowledged each one-byte restore write. Before another trigger run, manually verify `0x2306` and `0x55DC`.

Version 1.0.1 corrects only this response decoding. It still verifies the actual setpoint value exclusively with the following Virtual_READ; no safety check was removed. The full pinned chain passes **168/168 offline tests**, including the exact live WB2A response above.

[Machine-readable failed-run evidence](../config/optolink-splitter/research/vitosoft/gfa-triggered-status-failed-run-2026-09-24-evidence.json).

### First triggered live run

Start with the boiler burner off and the normal day setpoint below 37 C. **Do not manually set 37 C first**; the helper does that itself.

Run as root in the same LXC. Do not stop the splitter first and do not change `vs1protocol`.

```bash
(
  set -euo pipefail

  script=/root/wb2a-gfa-triggered-status-probe.py
  tmp=$(mktemp)
  trap 'rm -f "$tmp"' EXIT

  curl --fail --show-error --location --retry 2 --connect-timeout 15 \
    'https://raw.githubusercontent.com/SaulGoodman1337/optolink/8259cd5f3c07c4d46939e17e7bc87dc47378717f/config/optolink-splitter/wb2a-gfa-triggered-status-probe.py' \
    -o "$tmp"

  printf '%s  %s\n' \
    '6d5810e1595ba6e464452dcd927259e9bade8f550a92b492fd40c2a27972604b' \
    "$tmp" | sha256sum -c -

  install -m 0700 "$tmp" "$script"

  /opt/optolink/venv/bin/python "$script" --self-test
  /opt/optolink/venv/bin/python -u "$script" --execute --seconds 60
)
```

The pinned parent helper files must remain unchanged beside it in `/root`.

Expected successful cleanup indicators include:

```text
ORIGINAL_DAY_SETPOINT=<previous value>
TRIGGER_SETPOINT=37
TRIGGER_VERIFIED=yes
SETPOINT_RESTORED=yes
P80_CONFIRMED=0x20 GFA
P300_RESTORED=yes
SPLITTER_RESTARTED=yes
RESULT=PASS
```

If `SETPOINT_RESTORED=NOT_VERIFIED` appears, verify/reset the day setpoint manually before doing anything else and do not blindly rerun.

Retain the printed `LOG=` and `JSONL=` files. The next analysis will compare the exact 37 C trigger timestamp with P84, P87 bit 1, P06 fan speed and P09 modulation-setpoint transitions. A timing correlation is still not a vendor-defined bit name.
