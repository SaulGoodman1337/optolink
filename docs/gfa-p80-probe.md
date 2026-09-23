# WB2A read-only GFA P80 identity probe

Status: **implemented and offline-tested; first local hardware execution pending**.

This runbook advances Step A in [the collector checkpoint](collector-research-checkpoint.md). The helper is now implemented; a successful GFA read on the WB2A has NOT yet been observed. No production profile, dashboard, updater or controller parameter was changed while preparing it.

Helper: [`config/optolink-splitter/wb2a-gfa-p80-probe.py`](../config/optolink-splitter/wb2a-gfa-p80-probe.py).

Implementation commit: `ab32e2d2fe2c165390d7098dcffc4bb2e097543d`.

SHA256 of the tested script:

```text
6de883c422a09c821b342d12e5bb71dd3d518d8115ec2495bdfb202f5a7f50cb
```

The committed Git blob `f5c9b1ba0d928b5f477b2d6acdaaed34a8ff91f2` matches the locally compiled/tested file byte for byte.

## Local prerequisites confirmed by user output

- Splitter service active/running, working directory `/opt/optolink`.
- Interpreter `/opt/optolink/venv/bin/python`, Python 3.13.5 and pyserial 3.5.
- `vs1protocol = False` (normal P300/VS2).
- `port_vitoconnect = None`.
- `port_optolink` is the configured Silicon Labs CP2102 stable by-id path, resolving to `/dev/ttyUSB0`.
- A different USB adapter resolves to `/dev/ttyUSB2`; it is not selected or probed.

The helper re-reads only literal settings assignments with `ast`, never imports/executes the settings module, and does not rewrite it. It refuses conditional/ambiguous port settings rather than guessing.

## Deliberately narrow test sequence

1. Require the splitter to be running. If the optional party emulator is running, remember and pause it first.
2. Pause the splitter, check for remaining serial-port owners, open 4800 8E2 using pyserial exclusive access and Linux TIOCEXCL, then check for conflicting existing owners again.
3. Initialize P300 and read only Virtual_READ `0x00F8 / 2`. Require device identification `20C2` before sending a GFA command.
4. Leave P300 with EOT. Observe interface-detection ENQ and a fresh VS1 synchronization ENQ. Send STX plus `GFA_READ 0x4050 / 1` together. No virtual write, EEPROM write, GFA write or process write is implemented.
5. Repeat the same P80-only read with independent synchronization. Require matching values from the source-defined set 0x20/0x21/0x22/0x23. Reject unknown values, trailing data and mismatched samples.
6. In cleanup, initialize P300 and verify a checksum-valid, matching `0x00F8 / 2` response, with at most two restoration attempts.
7. Close the serial port, restart the services that were previously running, and check that they stay active/running immediately after startup. An initially inactive party emulator stays inactive.

Only these fixed transmissions can pass the helper's TX allowlist:

```text
04                         EOT / interface synchronization
16 00 00                   VS2 initialization
06                         VS2 acknowledgement
41 05 00 01 00 F8 02 00    P300 Virtual_READ 00F8/2
01 6B 40 50 01             VS1 STX + GFA_READ P80/1
```

There is no arbitrary address/function-code option. Not even P06 is enabled in this first helper. The script does transmit protocol control bytes, so read-only means no device parameter/control-value writes, not passive bus sniffing.

## Source verification

The source protocol was rechecked directly in the supplied private archive's `tool-dumps/ildasm/MobileClient_vsmInterfaceCore.dll.il` without executing Vitosoft. Relevant methods are `VS1Message::getVS1MessageFromLDAPMessage`, `VS1::createVS1Connection`, `VS1::sendVS1Message`, `VSManager::StartCommunicationVS1` and `VSManager::ChangeInterface`.

The fresh-ENQ sequence follows the distinction between interface detection and the subsequent VS1 synchronization. The STX and P80 command are sent in one write to avoid a scheduling gap; this is the same byte stream, not an extra device command.

P300 framing and 4800 8E2 were cross-checked against upstream `philippoo66/optolink-splitter` files `optolinkvs1.py` (blob `cff6b4d8d52ca4ee1f79c310dd9377dba1a18270`) and `optolinkvs2.py` (blob `7d56f71b10d1bbb74ba2efb443bd16161aff71a8`). The helper is an independent minimal implementation and does not import the production splitter modules.

pyserial access/timeout behavior reference: https://pyserial.readthedocs.io/en/latest/pyserial_api.html

The provenance and variant-selection evidence remain in [the private-archive analysis](../config/optolink-splitter/research/vitosoft/private-archive-2026-09-23-analysis.md).

## Offline tests actually run

Compilation and the built-in `--self-test` passed. **23 tests** cover fixed frame bytes, valid/invalid checksums and responses, TX allowlist rejection, matching and inconsistent P80 values, unexpected ENQ/unknown values, P80 timeout, absent ENQ, trailing bytes, other known variants, wrong baseline identity, serial-open failure, stop-timeout-after-acceptance, interruption, recovery failure, close failure, restart failure, initially inactive services and settings parsing without execution.

These tests use simulated serial/systemd objects. They do not establish real CP2102 timing, kernel-exclusive-access behavior on the user's host, successful VS1 access to the appliance, MQTT health or a mechanical burner state. The baseline/cleanup reads are designed to establish communication when the user explicitly executes the helper.

## Execute in the existing splitter LXC as root

For the initial diagnostic, choose a normal burner-idle period rather than deliberately initiating a start or actuator test. Leave `vs1protocol` and all heating settings unchanged. Do not run another serial tool concurrently. The helper manages the service pause itself; do not stop the splitter beforehand.

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

Without `--execute`, the helper only prints a plan. `--self-test` does not import pyserial or touch systemd/serial hardware. No normal `update` is needed, and running `update` must not automatically execute this experiment.

The live run writes a new root-only `/root/wb2a-gfa-p80-<timestamp>-<pid>.log` and prints every TX/RX operation. Settings credentials and MQTT passwords are not logged.

## Interpret the result

Expected example, NOT a measured result:

```text
P80_RESULT=0x20 GFA
P300_RESTORED=yes
SPLITTER_RESTARTED=yes
RESULT=PASS
```

- `P80_RESULT` is confirmed only when the two one-byte reads match a known variant.
- `P300_RESTORED=yes` requires an actual valid 20C2 reply, not just successful transmission of initialization bytes.
- `SPLITTER_RESTARTED=yes` means systemd reported active/running after restart; check Home Assistant separately for renewed updates.
- `PASS` requires confirmed P80, verified P300 restoration and no recorded probe/recovery errors.
- Another known P80 variant is reported without automatically trying any additional GFA registers.
- `FAIL`/`NOT_VERIFIED` requires examination of the complete log before another attempt. Do not switch to guessed commands or parameter writes.

## Recovery boundaries

SIGINT, SIGTERM and SIGHUP enter cleanup; repeated ordinary interruption signals are ignored during cleanup. Service intent is recorded before stop, so an accepted stop followed by a client timeout still causes a restart attempt. Restarts are attempted even when the GFA read, P300 recovery or serial close fails.

There is no independent watchdog process. SIGKILL, power loss, a kernel/USB failure or a failed systemd job can prevent complete restoration; this must not be advertised as an unconditional guarantee. Serial access ownership is checked within the LXC's visible process namespace and does not detect unrelated host-side use outside that namespace.

If the helper has exited and the splitter did not restart, inspect/recover it using:

```bash
systemctl start optolink-splitter.service
systemctl --no-pager --full status optolink-splitter.service
journalctl -u optolink-splitter.service -n 60 --no-pager
```

Restore `optolink-party-emulator.service` separately only if the log shows it was running and paused by this test. Do not start competing serial processes while the helper still owns the adapter. A running service is not by itself proof of a recovered device link.

## Next step after a real result

Preserve the full first execution log. If P80 and restoration succeed, select the corresponding burner variant before building a second, still read-only observation helper for P06/P09/P10/P84. For the expected GFA variant P06 is RPM x30; P09 is modulation x0.3922, not RPM. No fan/pump/safety values are changed by this identity probe, and no new Home Assistant entity is introduced yet.
