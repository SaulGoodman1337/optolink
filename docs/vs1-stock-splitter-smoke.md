# WB2A stock splitter permanent-VS1 smoke gate

Status: **prepared; live execution pending.**

This is the final read-path gate before adding production GFA polling to the splitter.

## Why this gate exists

The bounded mixed-session probe already passed on the exact VDensHO1 / 20C2 appliance:

- normal VS1 `F7 Virtual_READ` values matched their P300 values byte-for-byte;
- direct `6B GFA_READ` requests for P80/P06/P09/P87 were interleaved in the same persistent VS1 session;
- P80 remained `0x20`;
- no `FF` occurred;
- P300 and services were restored.

That proves the protocol primitive. It does **not** yet prove that the actual stock splitter process, current Home Assistant poll list and MQTT publication path behave correctly when the splitter itself stays permanently in VS1 mode.

This gate tests exactly that, without adding any GFA code.

## Helper

```text
config/optolink-splitter/wb2a-stock-vs1-smoke.py
```

Version:

```text
1.0.0
```

Pinned commit:

```text
af582f24b144863221d0a1e3137ce27eeb47d1ba
```

Git blob:

```text
2a53de0c41e2a1adcb17b5025113e7b09b647149
```

SHA256:

```text
a9cd4a1b1750d650573d8718a85e940fffa231c4bff62500265b2215f07241c3
```

The helper's nine offline logic tests cover settings patching, missing-setting refusal, literal setting parsing, poll-topic extraction, disabled groups, MQTT topic formatting/collision detection, journal success/error classification and duration bounds.

## Stock-code requirement

The gate refuses live execution unless:

- `/opt/optolink` HEAD equals its local `origin/main`;
- the checkout has no tracked modifications;
- `homeassistant_poll_list.py` exists;
- legacy `poll_list.py` is absent;
- `port_vitoconnect is None`;
- production `vs1protocol` is currently `False`;
- the splitter service is already active/running;
- MQTT is configured.

Untracked local configuration files are permitted; tracked splitter source modifications are not.

## Temporary settings

Only these four explicit assignments in `/opt/optolink/settings_ini.py` are changed for the test:

```python
vs1protocol = True
mqtt_listen = None
tcpip_port = None
olbreath = 0.15
```

The original settings bytes, file mode, uid and gid are saved first.

The replacement file is written atomically. The original file is restored byte-for-byte before normal services are restarted.

### Why command/write ingress is disabled

The upstream MQTT handler returns immediately when `mqtt_listen is None`, before both legacy command processing and `/set` handling. Thus incoming MQTT commands and HA set topics are ignored during the gate.

`tcpip_port = None` removes the TCP request ingress.

The party emulator is stopped if it was active.

The helper itself has no direct Optolink write implementation and does not add any GFA polling.

## 30-second validation

The current stock splitter is started with the temporary settings and must remain active/running with one unchanged MainPID for the complete window.

Its journal must contain:

```text
VS1/KW protocol initialized
enter main loop
```

Configured timeout/poll/restart error patterns cause FAIL.

### Existing Home Assistant poll list

The helper parses the installed `homeassistant_poll_list.py` and builds the exact MQTT topics for every poll item enabled on poll cycle 0.

It subscribes to the existing MQTT base topic before the temporary splitter starts. Retained/pre-test messages are cleared before the measurement window.

Every enabled cycle-0 poll topic must be newly published at least once during the gate. Missing topics are listed and cause FAIL.

This validates the current HA read path rather than a small hand-picked subset.

## Cleanup

Cleanup handlers for SIGINT, SIGTERM and SIGHUP are armed **before** service/settings changes.

On every ordinary success/error/signal cleanup path:

1. stop temporary VS1 splitter if running;
2. restore original `settings_ini.py` atomically;
3. verify original SHA256 exactly;
4. restart splitter if it was previously running;
5. restart party emulator if it was previously running;
6. require restored splitter to be active/running;
7. verify its journal again shows `VS2/300 protocol initialized`;
8. delete the local backup only after exact restore verification.

If restore cannot be verified, the root-only backup is retained and its path is printed.

SIGKILL, host power loss, storage failure and similar catastrophic interruption remain outside software cleanup guarantees.

## Live command

Run in the optolink-splitter LXC as root:

```bash
(
  set -euo pipefail

  script=/root/wb2a-stock-vs1-smoke.py
  tmp=$(mktemp)
  trap 'rm -f "$tmp"' EXIT

  curl --fail --show-error --location --retry 2 --connect-timeout 15 \
    'https://raw.githubusercontent.com/SaulGoodman1337/optolink/af582f24b144863221d0a1e3137ce27eeb47d1ba/config/optolink-splitter/wb2a-stock-vs1-smoke.py' \
    -o "$tmp"

  printf '%s  %s\n' \
    'a9cd4a1b1750d650573d8718a85e940fffa231c4bff62500265b2215f07241c3' \
    "$tmp" | sha256sum -c -

  install -m 0700 "$tmp" "$script"

  /opt/optolink/venv/bin/python "$script" --self-test
  /opt/optolink/venv/bin/python -u "$script" --execute --seconds 30
)
```

Do not manually stop services and do not edit settings first.

A successful tail should include approximately:

```text
TRACKED_CHECKOUT=clean_origin_main
EXPECTED_CYCLE0_MQTT_TOPICS=<n>
JOURNAL_VS1_INITIALIZED=yes
JOURNAL_MAIN_LOOP=yes
JOURNAL_UNEXPECTED_RESTART=no
MQTT_EXPECTED=<n>
MQTT_SEEN=<n>
MQTT_MISSING=0
SETTINGS_RESTORED=yes
SERVICE_RESTORED=optolink-splitter.service running
SERVICE_RESTORED=optolink-party-emulator.service running   # if it was active before
RESTORED_BASELINE_PROTOCOL=VS2/300
RESULT=PASS
```

Output files:

```text
LOG=/root/wb2a-stock-vs1-smoke-....log
JOURNAL=/root/wb2a-stock-vs1-smoke-....journal.log
MQTT_CAPTURE=/root/wb2a-stock-vs1-smoke-....mqtt.json
```

The MQTT capture contains topic names and observed values, but no MQTT credentials. Do **not** upload a retained `settings_ini.py.vs1-smoke-backup-...` file if a restore failure ever leaves one behind, because the settings file may contain credentials.

## PASS meaning

A PASS would establish that the current **unmodified upstream splitter**, current HA read poll list and MQTT read-publication path operate successfully during a bounded permanent-VS1 run on this appliance.

A PASS still does not validate:

- VS1 Virtual_WRITE;
- production GFA polling;
- long-duration FF behavior;
- catastrophic-interruption recovery.

After a PASS, the next implementation step is a narrow structured `GFA_READ 0x6B` path under the splitter's single serial owner, applied reproducibly by this repository so the existing updater cannot silently erase it.

Machine-readable preparation evidence:

[stock VS1 smoke preparation](../config/optolink-splitter/research/vitosoft/vs1-stock-splitter-smoke-prep-2026-09-24-evidence.json).
