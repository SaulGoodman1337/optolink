# WB2A stock splitter permanent-VS1 smoke gate

Status: **PASS on hardware. The current splitter runtime, full 212-topic HA cycle-0 read path, MQTT publication and permanent VS1 session all completed successfully for 60 seconds, followed by byte-exact settings restore and confirmed return to VS2/300.**

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
homeassistant_publish.py 21d272008206abaa766563f59bd30379b80a02ce
mqtt_util.py             5f4b159e0431a87fbdb1683fd6568971cf1a3260
```

Any additional tracked modification or any different content in either file remains a hard preflight failure.

## Fourth preflight result - line-ending normalization accounted for

The fourth attempt also stopped before any service or settings change. The two intended profile-patched files had the correct semantic changes but different Git blobs than the first reconstruction.

The reason is the profile helper implementation itself: it uses Python `Path.read_text()` and `Path.write_text()`. The upstream files are CRLF-formatted; Python's universal-newline read followed by text write normalizes them to LF while applying the intended source patch.

Replaying that exact transformation produces the **same blobs observed on the LXC**:

```text
homeassistant_publish.py 21d272008206abaa766563f59bd30379b80a02ce
mqtt_util.py             5f4b159e0431a87fbdb1683fd6568971cf1a3260
```

v1.0.6 pins these real on-disk results. No other tracked modification is accepted.

## Sixth attempt - MQTT observer bug fixed before VS1 start

The next attempt passed the complete stock/profile preflight, identified 212 expected cycle-0 MQTT topics, captured the original settings SHA256 and stopped the splitter. The actual VS1 splitter run still did **not** start because the independent MQTT observer crashed first.

Cause:

```text
TypeError: int() argument must be a string, a bytes-like object or a real number, not 'ReasonCode'
```

The helper explicitly uses Paho callback API v2. Current Paho v2 supplies a `ReasonCode` object and exposes `reason_code.is_failure`; v1.0.5 incorrectly attempted `int(reason_code)`.

Cleanup succeeded:

- original settings SHA256: `afb2beeddbdde21b6bbfdf0a66ec3be0f77998a7c1f50c32d7386d5eefe9ea05`;
- restored settings SHA256: identical;
- splitter service restarted;
- backup removed only after byte-exact restore.

The old `RESTORED_BASELINE_PROTOCOL=NOT_CONFIRMED` was a verification-timing weakness, not evidence that the restored splitter was unusable. v1.0.6 waits up to 10 seconds for the VS2/300 initialization marker and performs that check before restarting Party.

v1.0.6 also increases the smoke window to **60 seconds**. With 212 expected topics and `olbreath=0.15`, the breath delay alone gives a 31.8-second lower bound before serial response and MQTT overhead, so 30 seconds was not a sound complete-cycle gate.

## Successful live run - 2026-09-24

The first complete live VS1 smoke run passed:

```text
STOCK_VERIFY_MODE=git-origin-main-plus-vdensho1-profile-patches
PROFILE_PATCH_BLOBS=match files=2
EXPECTED_CYCLE0_MQTT_TOPICS=212
MQTT_SUBSCRIBED_BASE=openv/#
VS1_MAINPID=194040
JOURNAL_VS1_INITIALIZED=yes
JOURNAL_MAIN_LOOP=yes
JOURNAL_UNEXPECTED_RESTART=no
MQTT_EXPECTED=212
MQTT_SEEN=212
MQTT_MISSING=0
SETTINGS_RESTORED=yes
SERVICE_RESTORED=optolink-splitter.service running
RESTORED_BASELINE_PROTOCOL=VS2/300
BACKUP_REMOVED=yes
RESULT=PASS
```

Runtime window: 60 seconds.

Settings integrity:

```text
original SHA256  afb2beeddbdde21b6bbfdf0a66ec3be0f77998a7c1f50c32d7386d5eefe9ea05
temporary SHA256 1de56b47c4b4ade262ea31c9b9069a029ddf6241f28804d77047b8ce3a78a033
restored SHA256  afb2beeddbdde21b6bbfdf0a66ec3be0f77998a7c1f50c32d7386d5eefe9ea05
```

This establishes the bounded production **read** path in permanent VS1 mode on this exact VDensHO1 / 20C2 appliance:

- the stock splitter plus the two intentional VDensHO1 profile patches remained on one stable MainPID;
- VS1/KW initialized and entered the main loop;
- every one of the 212 enabled cycle-0 HA poll topics was freshly published;
- no internal restart was observed;
- the original settings were restored byte-for-byte;
- the normal VS2/300 baseline initialized again afterward.

The result does not yet validate VS1 Virtual_WRITE, production GFA polling, long-duration FF rate or catastrophic-interruption recovery.

The next implementation step is therefore a **read-only structured GFA_READ 0x6B path** under the splitter's existing single VS1 serial owner.

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

## 60-second validation

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
  /opt/optolink/venv/bin/python -u "$script" --execute --seconds 60
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

The PASS establishes that the current upstream splitter runtime plus the two intentional VDensHO1 profile patches, current HA read poll list and MQTT read-publication path operate successfully during a bounded permanent-VS1 run on this appliance.

A PASS still does not validate:

- VS1 Virtual_WRITE;
- production GFA polling;
- long-duration FF behavior;
- catastrophic-interruption recovery.

After a PASS, the next implementation step is a narrow structured `GFA_READ 0x6B` path under the splitter's single serial owner, applied reproducibly by this repository so the existing updater cannot silently erase it.

Machine-readable preparation evidence:

[stock VS1 smoke preparation](../config/optolink-splitter/research/vitosoft/vs1-stock-splitter-smoke-prep-2026-09-24-evidence.json).
