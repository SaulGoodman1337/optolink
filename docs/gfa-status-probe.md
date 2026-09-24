# WB2A GFA status/startup probe

Status: **the guarded 37 C trigger run completed successfully and strongly correlates P87 bit 1 with release of the high-start modulation plateau. A complete Collector-v6 static search now confirms that Vitosoft itself exposes P84-P88 only as raw integer values; no manufacturer phase enum or status-bit table was recovered.**

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

### Collector-v6 static semantic search - completed

A dedicated search covered 1,134 text-like Collector-v6 artifacts, including normalized metadata, SQL exports, translations, XML and IL-derived text. It was followed by an exact SQL relation check for events 8208-8212.

All five events resolve to the same generic value type:

```text
EventValueType 12927 = Allgemein_Int
storage type         = Int
EnumType             = False
conversion           = NoConversion
low-level parameter  = Byte
SDK type             = Int
FCRead                = GFA_READ
FCWrite               = undefined
```

The German and English resource text adds only:

```text
P84 = GFA Betriebsphase / GBCU operating phase
P85 = GFA Status 1 / GBCU status 1
P86 = GFA Status 2 / GBCU status 2
P87 = GFA Status 3 / GBCU status 3
P88 = GFA Status 4 / GBCU status 4
```

No phase-value table and no bit names for P85-P88 were recovered. This is a strong negative result **within the installed Vitosoft corpus**, not proof that no burner-controller vendor document or firmware can define them.

The absence is meaningful because adjacent Vitosoft parameters do carry explicit bit descriptions when available: P83 has a FA0...FA7 bit-position description and the CES/common P89 definition explicitly names FA9/FA11/FA8 bits. Therefore repeated searches of the same Vitosoft corpus for a hidden P84-P88 enum are now closed.

Evidence: [P84-P88 static semantic boundary](../config/optolink-splitter/research/vitosoft/gfa-p84-p88-static-semantics-2026-09-24-evidence.json).

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

## Successful triggered startup result - 2026-09-24

Input: `Eingefügter Text(20260924-084636).txt`, 196251 bytes, 1004 lines, SHA256:

```text
61fa75e4b256dde5706088f1d6e00f682080d83c08870e49a278bf7168b7e337
```

Helper v1.0.1 completed the full guarded sequence:

- original A1 normal/day setpoint `0x2306 = 21 C`;
- pre-trigger `0x55DC = 0`;
- temporary `0x2306 = 37 C` write acknowledged and read back as 37;
- 50/50 accepted GFA rounds, zero rejected rounds, zero reconnects and no FF;
- four P80 checks all returned `20`;
- exact restore `0x2306 = 21 C` acknowledged and read back as 21;
- P300 restored to `20C2`, splitter and party emulator restored;
- `RESULT=PASS`.

The first same-session P80 was available 4.352 s after the setpoint trigger. The first P84 sample followed 4.793 s after the trigger, so this run still misses the earliest several seconds of startup. It begins in P84 raw `02`; unlike the earlier natural-start trace it does not sample the short P84=`04` state.

### P84 / P87 sequence

Observed first samples:

| Parameter/state | First receive | Time after 37 C trigger |
| --- | --- | ---: |
| P84 `02` | 10:42:08.273 | 4.793 s |
| P87 `20` bits [5] | 10:42:08.554 | 5.074 s |
| P87 `40` bits [6] | 10:42:14.456 | 10.976 s |
| P84 `05` | 10:42:15.451 | 11.971 s |
| P87 `50` bits [4,6] | 10:42:15.658 | 12.178 s |
| P84 `06` | 10:42:16.657 | 13.177 s |
| P87 `60` bits [5,6] | 10:42:16.939 | 13.459 s |
| P87 `62` bits [1,5,6] | 10:42:26.805 | 23.325 s |

The P87 progression is therefore:

```text
20 -> 40 -> 50 -> 60 -> 62
 b5    b6   b4+b6 b5+b6 b1+b5+b6
```

These are raw observations only. Do not assign manufacturer names to bits 1/4/5/6.

### Strongest timing correlation so far: P87 bit 1 and plateau release

P09 remained at raw `93` = 57.6534% through the high-start plateau. P87 remained `60` through that hold. In round 16:

- P87 was first observed as `62` at **10:42:26.805**, adding bit 1;
- P09 was first observed below the plateau at **10:42:27.302**, raw `91` = 56.8690%.

The observed sample times differ by only **0.497 s**. Because the channels are sequential, strict event ordering is not proven. The true P87 transition is bracketed by its `60` sample at 10:42:25.522 and `62` sample at 10:42:26.805. The true P09 release is bracketed by `93` at 10:42:26.019 and `91` at 10:42:27.302. Those windows overlap from **10:42:26.019 to 10:42:26.805**.

This establishes a substantially stronger statement than the earlier timing-only lead:

> **P87 bit 1 is a strong candidate marker associated with release/end of the high-start modulation plateau.**

It does **not** yet establish that bit 1 means "flame stabilized", "regulation enabled" or any other manufacturer-defined term.

Relative to first observed P84=`06`, P87=`62` appears 10.148 s later. Relative to first P87=`60`, it appears 9.866 s later. That closely reproduces the short post-start hold identified in the previous capture.

Fan response is consistent with the same transition but less sharply aligned: P06 stays around 4.4 krpm through the plateau and its first sustained fall after P87=`62` is 4320 rpm at 10:42:29.455.

### Restore behavior

At cleanup the script restored `0x2306=21` and verified the readback. Immediately afterwards `0x55DC` was raw `0x21` = 33, so restoring the normal setpoint does **not** imply immediate burner shutdown. A future repeated trigger must still wait for `0x55DC=0`, as the helper already requires.

[Machine-readable triggered-startup evidence](../config/optolink-splitter/research/vitosoft/gfa-triggered-startup-2026-09-24-evidence.json).

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
