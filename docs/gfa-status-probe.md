# WB2A GFA status/startup probe

Status: **prepared and offline-tested; not yet executed on the appliance**.

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

## Recommended first live run

Use a **normal heat demand**, not an actuator test or direct burner/safety manipulation. As with the successful startup trace, start the helper before or just as the controller begins its normal firing sequence if practical.

Run in the same LXC as root. Do not stop the splitter first and do not change `vs1protocol`.

```bash
(
  set -euo pipefail

  script=/root/wb2a-gfa-status-probe.py
  tmp=$(mktemp)
  trap 'rm -f "$tmp"' EXIT

  curl --fail --show-error --location --retry 2 --connect-timeout 15 \
    'https://raw.githubusercontent.com/SaulGoodman1337/optolink/1e76701d8395841a081a3bd6eca67d8ffcbc12af/config/optolink-splitter/wb2a-gfa-status-probe.py' \
    -o "$tmp"

  printf '%s  %s\n' \
    '912de7276ed2a26330abbfb0d7c5778862d171fa5a179ab1b73043fdee9c59bc' \
    "$tmp" | sha256sum -c -

  install -m 0700 "$tmp" "$script"

  /opt/optolink/venv/bin/python "$script" --self-test
  /opt/optolink/venv/bin/python -u "$script" --execute --seconds 60
)
```

The pinned paced/quality/cycle/session/P80 helper files must remain unchanged in `/root`; loading stops before service/serial activity if a dependency hash differs.

Retain both paths printed as:

```text
LOG=/root/wb2a-gfa-status-...
JSONL=/root/wb2a-gfa-status-...
```

If the result is FAIL, do not blindly rerun. The accepted/rejected raw records remain useful for analysis.

## What the next analysis will test

The preceding startup capture observed P84 `00 -> 02 -> 04 -> 05 -> 06`, followed by a roughly 9.4-10.4 second delay before the high startup plateau began to fall. The new capture will ask:

1. Does P12 change at, before or after those P84 transitions?
2. Which P85-P88 bytes/bits change near 02/04/05/06?
3. Does any bit transition remain stable through the later startup-hold release?
4. Are the same changes present in idle versus firing states?
5. Are any changes short enough that the alternating-bank cadence could miss them?

A correlation is evidence for timing/association, not automatically a functional bit name. A second controlled observation or independent flame signal is required before promoting a candidate to a named Home Assistant entity.
