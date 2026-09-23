# WB2A read-only GFA P80 identity probe

Status: **hardware-verified on the local WB2A on 2026-09-23 at 22:33 Europe/Berlin**.

The user's live transcript confirms two independent P80 replies `0x20` (GFA), actual P300 device replies `20C2` before and after the test, restoration of both running services, and `RESULT=PASS`. This completes Step A in [the collector checkpoint](collector-research-checkpoint.md).

**The current next step is the bounded P06/P09/P10/P84 snapshot**, not another unmodified P80-only test. See [GFA live checkpoint and snapshot instructions](gfa-live-checkpoint.md) for the observed timestamps, scope and next command. No runtime GFA values have yet been hardware-validated in this checkpoint.

## Reproducible P80 helper

Helper: [`config/optolink-splitter/wb2a-gfa-p80-probe.py`](../config/optolink-splitter/wb2a-gfa-p80-probe.py).

Implementation commit: `ab32e2d2fe2c165390d7098dcffc4bb2e097543d`.

SHA256:

```text
6de883c422a09c821b342d12e5bb71dd3d518d8115ec2495bdfb202f5a7f50cb
```

Git blob: `f5c9b1ba0d928b5f477b2d6acdaaed34a8ff91f2`.

The original helper is unchanged after the successful run. Its exact bytes are also a pinned dependency of the new snapshot helper. Do not edit it to add arbitrary addresses.

## Confirmed local prerequisites

- Splitter active/running, working directory `/opt/optolink`.
- `/opt/optolink/venv/bin/python`, Python 3.13.5 and pyserial 3.5.
- `vs1protocol = False`; `port_vitoconnect = None`.
- Configured Silicon Labs CP2102 by-id path resolves to `/dev/ttyUSB0`.
- A different adapter resolving to `/dev/ttyUSB2` was not selected.

The helper parses literal settings with `ast`, never imports/executes the settings module, and does not rewrite it. Conditional/ambiguous port settings are refused.

## Narrow sequence used successfully

1. Require the splitter to be running; remember and pause an active party emulator first.
2. Pause splitter, check remaining serial owners, open 4800 8E2 with pyserial exclusive access and Linux TIOCEXCL, then recheck conflicting existing owners.
3. Initialize P300; read only Virtual_READ `0x00F8 / 2`; require `20C2` before a GFA request.
4. Leave P300 with EOT, observe interface-detection ENQ and a fresh VS1 ENQ; send STX plus `GFA_READ 0x4050 / 1` together.
5. Repeat P80 with independent synchronization. Require matching source-defined variants; reject unknown values, trailing data and mismatch.
6. In cleanup, initialize P300 and verify an actual checksum-valid `20C2` reply, with at most two attempts.
7. Close serial, restart previously running services, and check they stay active/running immediately after startup. An initially inactive party emulator stays inactive.

The entire fixed TX allowlist is:

```text
04                         EOT / synchronization
16 00 00                   VS2 initialization
06                         VS2 acknowledgement
41 05 00 01 00 F8 02 00    P300 Virtual_READ 00F8/2
01 6B 40 50 01             VS1 STX + GFA_READ P80/1
```

No arbitrary function/address option, parameter write, GFA write, EEPROM write or process write exists. Read-only here includes transmitted protocol-control bytes; it does not mean passive sniffing. No production profile, updater, dashboard or controller setting is modified.

## Source verification and offline tests

The protocol was checked in the preserved archive's `tool-dumps/ildasm/MobileClient_vsmInterfaceCore.dll.il`, especially `VS1Message::getVS1MessageFromLDAPMessage`, `VS1::createVS1Connection`, `VS1::sendVS1Message`, `VSManager::StartCommunicationVS1` and `ChangeInterface`. Vitosoft was not executed.

The fresh ENQ distinguishes interface detection from VS1 synchronization. Combined STX/read transmission avoids a scheduling gap while preserving the byte stream.

P300 framing and 4800 8E2 were cross-checked against upstream `philippoo66/optolink-splitter` files `optolinkvs1.py` (blob `cff6b4d8d52ca4ee1f79c310dd9377dba1a18270`) and `optolinkvs2.py` (blob `7d56f71b10d1bbb74ba2efb443bd16161aff71a8`). The helper is independent and does not import production splitter modules.

pyserial reference: https://pyserial.readthedocs.io/en/latest/pyserial_api.html

Compilation and **23 built-in offline tests** passed, both during preparation and in the user's transcript. They cover fixed frames, checksums, response identity, TX allowlist, P80 mismatch/unknown/other variants, absent ENQ, timeout, trailing bytes, wrong device, open/stop/close/restart/recovery failures, interruption, initially inactive services and literal settings parsing.

Those tests use simulated I/O. The subsequent live transcript separately demonstrates this specific hardware success; neither simulated tests nor one successful run establish unconditional recovery or complete MQTT/HA health.

## Command retained for reproduction, not the next requested test

The original helper can still be installed/executed as follows. For the already successful installation, proceed to [the snapshot](gfa-live-checkpoint.md) instead of repeating it unnecessarily.

```bash
(
  set -euo pipefail
  script=/root/wb2a-gfa-p80-probe.py
  tmp=$(mktemp)
  trap 'rm -f "$tmp"' EXIT

  curl --fail --show-error --location --retry 2 --connect-timeout 15 \
    'https://raw.githubusercontent.com/SaulGoodman1337/optolink/ab32e2d2fe2c165390d7098dcffc4bb2e097543d/config/optolink-splitter/wb2a-gfa-p80-probe.py' \
    -o "$tmp"

  printf '%s  %s\n' \
    '6de883c422a09c821b342d12e5bb71dd3d518d8115ec2495bdfb202f5a7f50cb' \
    "$tmp" | sha256sum -c -

  install -m 0700 "$tmp" "$script"
  /opt/optolink/venv/bin/python "$script" --self-test
  /opt/optolink/venv/bin/python -u "$script" --execute
)
```

Do not stop the splitter beforehand, permanently change VS1 settings, or run another serial process concurrently. No normal `update` is needed and updates must not automatically execute the test. Without `--execute` only a plan is printed. `--self-test` does not import pyserial or touch systemd/hardware.

Each explicit live run writes a root-only `/root/wb2a-gfa-p80-<timestamp>-<pid>.log` with TX/RX operations, not MQTT credentials. During the service pause normal polling and the paused emulator are unavailable.

## Interpret the measured result

Actual final status from the user's run:

```text
P80_RESULT=0x20 GFA
P300_RESTORED=yes
SPLITTER_RESTARTED=yes
RESULT=PASS
```

- P80 requires two matching known variants.
- P300_RESTORED requires an actual valid `20C2` reply, not just sent initialization bytes.
- SPLITTER_RESTARTED means systemd reported running; verify HA data freshness separately.
- PASS requires confirmed identity, verified P300 and no recorded probe/recovery error.
- Other known variants are reported without automatically reading additional registers.
- FAIL/NOT_VERIFIED requires full-log inspection before another attempt.

The transcript is user-provided live evidence. The named standalone log file was not separately retrieved. P80 does not prove that every event in the GFA branch works or that firmware flashing is possible.

## Recovery boundaries

SIGINT/SIGTERM/SIGHUP enter cleanup; ordinary repeated interruption signals are ignored during cleanup. Service intent is recorded before stop, so an accepted stop followed by a timeout still leads to restart attempts. Restarts are attempted even after read, recovery or close failures.

There is no independent watchdog. SIGKILL, power loss, USB/kernel failure or failed systemd jobs can prevent restoration. Serial-owner inspection is limited to the LXC-visible process namespace; it cannot see unrelated host-side use outside that namespace.

If the helper has exited and splitter restart failed:

```bash
systemctl start optolink-splitter.service
systemctl --no-pager --full status optolink-splitter.service
journalctl -u optolink-splitter.service -n 60 --no-pager
```

Restore the party emulator separately only if the log shows it was active and paused. Never start competing serial processes while the helper still owns the adapter. A running service alone is not proof of device-link recovery.

## Next step

The live P80 value selects the GFA branch: P06 is actual fan speed x30 rpm; P09 is modulation x0.3922, not RPM. The new four-register helper has been prepared and offline-tested. Its first real execution remains pending. No operational Home Assistant entity or rapid burner-start logger has been introduced yet. See [the live checkpoint](gfa-live-checkpoint.md).
