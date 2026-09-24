# WB2A stock splitter permanent-VS1 smoke gate

Status: **prepared; first live attempt stopped safely at preflight because the migrated installation has no `.git` metadata. v1.0.3 now supports exact runtime-file hash verification as a fallback. Live VS1 execution still pending.**

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
1.0.3
```

Pinned commit:

```text
421b72c0578a31a4e67865385a59d1b04054e6f5
```

Git blob:

```text
3a81d4f1d3c856a3d03b176f4d1ca11c63efd27f
```

SHA256:

```text
26d4435b69353794d704526a0a5204b858df0871c13d9409876ecd060a943145
```

The helper's thirteen embedded offline logic tests cover settings patching, missing-setting refusal, literal setting parsing, poll-topic extraction, disabled groups, MQTT topic formatting/collision detection, journal success/error classification, Git-blob hashing and duration bounds.

## Stock-code requirement

The first live attempt on 2026-09-24 stopped safely before any settings/service change because `git rev-parse HEAD` exited with code 128. That exit code alone does not distinguish a missing `.git` directory from Git's `safe.directory` ownership protection. v1.0.3 handles both cases: if `.git` exists, Git is invoked with a per-process `safe.directory=/opt/optolink`; if `.git` is absent, the exact 14-file runtime blob manifest is used. No device command, temporary settings write or service stop occurred in the failed preflight.

v1.0.3 accepts either of two strict stock-source verification modes:

1. **Git mode:** `/opt/optolink` is a Git checkout, HEAD equals local `origin/main`, and no tracked files are modified.
2. **Migrated-install fallback:** if `.git` is absent, 14 critical runtime Python files must match exact Git-blob IDs from upstream commit `c1ee204a1421447721603c5f21c6da7337fdac97`. These include the main splitter, VS1/VS2 transports, request/poll/settings/MQTT/HA modules and supporting runtime helpers. Any missing or differing file aborts before changes.

The gate additionally refuses live execution unless:

- `homeassistant_poll_list.py` exists;
- legacy `poll_list.py` is absent;
- `port_vitoconnect is None`;
- production `vs1protocol` is currently `False`;
- the splitter service is already active/running;
- MQTT is configured.

Untracked local configuration files are permitted; tracked splitter source modifications are not.

## Second preflight result - intentional VDensHO1 runtime patches

The second live attempt again stopped **before any service/settings change**. This time Git verification succeeded far enough to show exactly two tracked runtime modifications:

```text
M homeassistant_publish.py
M mqtt_util.py
```

These are intentional changes applied by `tools/optolink-apply-vdensho1-ha-profile.sh`:

- `homeassistant_publish.py`: expands `{mqtt_base}` and `%mqtt_listen%` placeholders in generated Home Assistant discovery strings.
- `mqtt_util.py`: replaces one delayed writable-state readback with staged delays `0.25, 1.0, 2.5, 5.0` seconds.

v1.0.3 accepts **only these two paths and only their exact patched Git-blob IDs**:

```text
homeassistant_publish.py 49107392ee71af629e6af8eafec337852d6340aa
mqtt_util.py             b5173ee7a4e04e9ada50b0ed708d65accc10ca46
```

Any additional tracked modification or any different content in either file remains a hard preflight failure.

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
STOCK_VERIFY_MODE=git-origin-main-plus-vdensho1-profile-patches
TRACKED_CHECKOUT=origin_main_plus_exact_vdensho1_profile_patches
PROFILE_PATCH_BLOBS=match files=2
# or, if .git is truly absent:
STOCK_VERIFY_MODE=runtime-blob-manifest-plus-vdensho1-profile-patches
RUNTIME_BLOB_MANIFEST=match files=14
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
