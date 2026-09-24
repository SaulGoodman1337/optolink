# GFA live checkpoint - 2026-09-24

**Current status: permanent VS1 plus structured read-only GFA access is VERIFIED ACTIVE on the VDensHO1 / 20C2 production splitter. P80/P06/P09/P87 are published through the single serial owner; P06 is the canonical blower-RPM source. Production timing is global 25 ms, GFA first attempt 25 ms, one raw-FF retry at 150 ms, then quarantine/failure. The current research queue is in [research-plan-2026-09-24.md](research-plan-2026-09-24.md).**

Historical experiment sections below are retained as evidence. Their old "next step" wording is superseded when it conflicts with the verified production status above and the current research plan.

A firing snapshot decoded P06 as 4110 rpm; the continuous trace independently supports the channel with a coherent 0->660->2490->4500 rpm startup and subsequent ramp down to 2790 rpm. Permanent Home Assistant integration is now verified active. The older isolated P06=FF conversion to 7650 rpm remains invalid as a physical event.

## GFA software identity P81-P83 - PASS 2026-09-24

A bounded read-only sequence through the already active production `gfaread` path returned:

```text
opening P80 = 0x20
P81          = 0x02  FA software version
P82          = 0x06  FA software revision
P83          = 0x76  appliance/GFA configuration
closing P80 = 0x20
```

The GFA branch identity was therefore stable before and after the three reads. Vitosoft defines all three as one-byte `GFA_READ`, `NoConversion`, read-only values. The evidence supports separate raw version/revision values `2` and `6`; it does **not** yet prove an official display notation such as `2.6` or `02.06`. A later Collector-v6 translation search recovered a source description for P83 that maps several bit positions to FA0...FA7 configuration flags. The local raw `0x76` has bits 1,2,4,5,6 set. Full decoding is deliberately withheld because the retained source description itself marks bit 4 as `0`/reserved while the local byte has bit 4 set.

Evidence: [P81-P83 live identity](../config/optolink-splitter/research/vitosoft/gfa-p81-p83-live-2026-09-24-evidence.json).

## P84-P88 static semantics - Vitosoft boundary reached 2026-09-24

A full Collector-v6 search plus exact SQL relation check established that P84-P88 are stored as raw read-only integers. Events 8208-8212 all use generic EventValueType `12927 = Allgemein_Int`, `EnumType=False`, `NoConversion`, one-byte `GFA_READ`. The installation contains no recovered value enum for P84 and no bit table for P85-P88.

This closes repeated Vitosoft-static hunting for those meanings. Existing live facts remain valid: P84 progresses through raw `00/02/04/05/06`; P87 through `20/40/50/60/62`; and high-resolution timing places P87 bit 1 before P09 leaves the high-start plateau. Functional names remain unproven until independent live correlation or new GFA/firmware documentation supplies them.

Evidence: [P84-P88 static semantic boundary](../config/optolink-splitter/research/vitosoft/gfa-p84-p88-static-semantics-2026-09-24-evidence.json).

## GFA coding-plug diagnostics P90/P100-P108 - PASS 2026-09-24

The local GFA branch was guarded by P80=`20` before and after a complete read-only coding-plug diagnostic sequence. Same-window regulation values were `0x1010 = 7833971` and `0x7656 = 20 15 02 01`.

```text
P90  = 00
P100 = 63  -> 99 * 0.3922 = 38.8278 %
P101 = 15
P102 = 01
P103 = 14
P104 = 0C
P105 = 04
P106 = D6
P107 = 02
P108 = 00
```

The values `15`, `01` and `02` also occur in the regulation-side coding-card summary `20 15 02 01`, providing direct cross-domain correlation. Exact field assignment remains open because retained public metadata does not prove the `0x7656` member byte positions. P103-P105 are source-labelled day/month/year but the raw-to-calendar representation is not yet resolved; P106 remains a CRC diagnostic byte with unknown algorithm.

Byte-for-byte comparison with both saved spare-chip1 EEPROM images found no contiguous live GFA vector. Several individual live values do occur at corresponding offsets inside the duplicated 82-byte physical record, creating candidate locations for the next side-labelled EEPROM campaign.

Evidence: [P90-P108 live coding-plug correlation](../config/optolink-splitter/research/vitosoft/gfa-coding-plug-p90-p108-live-2026-09-24-evidence.json).

Evidence:

- [Continuous startup trace](../config/optolink-splitter/research/vitosoft/gfa-startup-run-2026-09-24-evidence.json).
- [Status-target selection](../config/optolink-splitter/research/vitosoft/gfa-status-targets-2026-09-24-evidence.json).
- [First long-run failure and FF samples](../config/optolink-splitter/research/vitosoft/gfa-cycle-ff-2026-09-23-evidence.json).
- [Snapshot comparison](../config/optolink-splitter/research/vitosoft/gfa-snapshots-2026-09-23-evidence.json).
- [Same-session measurements and timing](../config/optolink-splitter/research/vitosoft/gfa-session-2026-09-23-evidence.json).
- [Static variant/scaling definitions](../config/optolink-splitter/research/vitosoft/private-archive-2026-09-23-evidence.json).

This is the current hardware checkpoint. Older collector documents describe static-only work, and older helper/runbook text may describe the state before its first execution. Preserve both the successful short tests and the unsuccessful long observation below.

## 0xxxxxxxxxxxxx. GFA freshness / P80 guard latency fix - 2026-09-24

A live-dashboard observation showed that P06 blower RPM could sometimes take roughly one to two minutes to appear after a state change.

The direct cause is not the P06 poll group: P06/P09/P87 are `FAST`. With the current permanent-VS1 `olbreath=0.15` and roughly 33 fast poll items, their normal cadence should be on the order of seconds, not minutes.

The production identity guard introduced a latency corner case:

- P80 was `NORMAL` (cycle 15);
- P06/P09/P87 were `FAST`;
- a transient P80 communication failure cleared the cached P80=20 guard;
- subsequent productive GFA reads were suppressed until the next successful P80 poll;
- fifteen fast cycles can reach approximately the observed one-to-two-minute delay once serial and other splitter traffic are included.

Fix:

- P80 is now polled as `FAST`, immediately before P06/P09/P87;
- a transient P80 transport failure no longer clears a previously validated P80=20 identity;
- a successful P80 read with a value other than 0x20 still revokes the guard immediately;
- on process start the guard remains closed until the first successful P80=20 read.

Patch helper v1.0.3 commit: `686739502cbd3fedbe2a40faed6434f01f1c297a`.
Production profile P80 FAST commit: `7775b4f412e6e8ed41cef981b7aa7f159b515e55`.

## 0xxxxxxxxxxxx. Dashboard integration for live GFA values - 2026-09-24

The Home Assistant dashboard now surfaces the production GFA signals:

- `sensor.vitodens_200_wb2a_geblaesedrehzahl_gfa_p06` as the real controller-reported blower speed;
- `sensor.vitodens_200_wb2a_gfa_modulationssollwert_p09` beside the existing modulation signal;
- `sensor.vitodens_200_wb2a_gfa_status3_p87` as raw diagnostics only.

Dashboard changes:

- blower RPM badge on the main heating overview;
- P06/P09/P87 chips on the Diagnose view;
- P06 row in the existing `Brenner / Regelung` background-graph card with P09 as its extra value;
- dedicated 24 h `Gebläse & GFA` ApexCharts graph with separate RPM and percent axes.

The old disproven interpretation of `0x55D3[6:7]` as blower RPM remains excluded. P06/0x4006 is now the canonical blower-speed source for this installation.

Dashboard commit: `818c04a39752ee88868a01a9acaeb6e390696161`.

## 0xxxxxxxxxxx. Permanent VS1 + GFA production verification PASS - 2026-09-24

The post-activation production verification is complete.

Live settings:

```text
vs1protocol=True
olbreath=0.15
port_vitoconnect=None
mqtt_topic=openv
mqtt_listen=openv/cmnd
```

Both services are active/running:

```text
optolink-splitter.service
optolink-party-emulator.service
```

The permanent splitter journal showed:

```text
VS1/KW protocol initialized
enter main loop
```

with no restart/error marker in the verification window.

The full Home Assistant discovery retry completed successfully:

```text
294 entities published successfully
```

Fresh GFA MQTT values after a forced poll:

```text
P80=20
P06=0
P09=0.0
P87=00
GFA_TOPICS_SEEN=4/4
```

P80 therefore satisfies the production identity guard and all four GFA topics are live through the persistent single-owner VS1 splitter path.

**Production status: VERIFIED ACTIVE.**

## 0xxxxxxxxxx. Permanent VS1 + read-only GFA production activation - 2026-09-24

Production activation was executed with the validated VDensHO1 helper.

Observed:

```text
Validated upstream ref: c1ee204a1421447721603c5f21c6da7337fdac97
VS1_GFA_READONLY_PATCH_TESTS=7/7
PATCHED_FILES=optolinkvs1.py,vs12_adapter.py,requests_util.py
RESULT=PASS
Discovery dry-run OK.
Restarting Optolink-Splitter with VDensHO1 profile...
Party emulation service is active.
```

The new GFA discovery entities were published:

```text
GFA P80 Typ
Gebläsedrehzahl GFA P06
GFA Modulationssollwert P09
GFA Status3 P87
```

The final Home Assistant discovery publish exceeded the helper's non-fatal 45 second timeout after already publishing hundreds of entities. This was not a VS1/GFA transport failure; the helper explicitly left Optolink active. The helper timeout was subsequently increased to 120 seconds in commit `fb59dd137656001efe071d31350a058cd5d4ed9b`.

A post-activation verification of live P80/P06/P09/P87 values and the permanent VS1 journal state is the immediate next step.

Evidence: [production activation](../config/optolink-splitter/research/vitosoft/vs1-gfa-production-activation-2026-09-24-evidence.json).

## 0xxxxxxxxx. Real splitter permanent-VS1 write path PASS - 2026-09-24

The final bounded integration gate passed through the **actual running splitter production path**:

```text
MQTT /set
 -> mqtt_util.handle_set_topic
 -> splitter command queue
 -> requests_util.response_to_request
 -> vs12_adapter.write_datapoint_ext
 -> stock optolinkvs1 F4
 -> WB2A
```

Observed live sequence:

```text
BASELINE_2306=0x15 (21 C)
TARGET_2306=0x16 (22 C)
CHANGE_RESPONSE=1;0x2306;22
CHANGED_STATE=22
RESTORE_RESPONSE=1;0x2306;21
RESTORED_STATE=21
FINAL_SPLITTER_F7_2306=0x15 (21 C)
JOURNAL_UNEXPECTED_RESTART=no
VS1_MAINPID_STABLE=yes
SETTINGS_RESTORED=yes
RESTORED_BASELINE_PROTOCOL=VS2/300
TARGET_WRITE_VERIFIED=yes
RESTORE_VERIFIED=yes
DIRECT_FALLBACK_USED=no
RESULT=PASS
```

This removes the remaining splitter-transport blocker for permanent VS1 on the exact VDensHO1/20C2 installation. The current live HA profile's Optolink-backed writable controls are all one-byte datapoints; schedules remain read-only.

The helper printed `ERROR: 0` before/after the run because its outer exception wrapper also caught successful `SystemExit(0)`. This was cosmetic only; the gate itself returned PASS and completed normal recovery.

Production deployment is a separate step and had **not** been performed by this gate. The successful test restored the original settings byte-for-byte and returned the splitter to VS2/300.

Evidence: [real-splitter VS1 write gate](../config/optolink-splitter/research/vitosoft/vs1-splitter-write-gate-prep-2026-09-24-evidence.json).

## 0xxxxxxxx. Stock VS1 F4 value mutation + restore PASS - 2026-09-24

The actual one-byte state mutation gate passed on ordinary setpoint `0x2306`:

```text
BASELINE_2306=0x15 (21 C)
TARGET_2306=0x16 (22 C)
F4_CHANGE_REPLY=00
CHANGED_READBACK_2306=0x16 (22 C)
F4_RESTORE_REPLY=00
RESTORED_READBACK_2306=0x15 (21 C)
P300_POST_2306=0x15 (21 C)
TARGET_WRITE_VERIFIED=yes
RESTORE_VERIFIED=yes
P300_RESTORED=yes
P300_VALUE_RESTORED=yes
RESULT=PASS
```

Therefore stock VS1/F4 is no longer only handshake-tested: actual mutation and exact restoration are hardware-proven on this appliance. As in the idempotent run, response payload `00` is not a value echo; F7/P300 readback is authoritative.

Audit of the current live HA profile shows that all exposed Optolink-backed writable controls resolve to one-byte datapoints. Weekly schedules remain read-only. This removes the current write-width transport blocker for permanent VS1; appliance-specific semantics of every service coding remain a separate validation question.

One final integration gate is prepared to exercise the real running splitter path through an isolated temporary MQTT `/set` namespace before permanent activation.

Evidence: [F4 change/restore gate](../config/optolink-splitter/research/vitosoft/vs1-f4-change-restore-prep-2026-09-24-evidence.json).

## 0xxxxxxx. Stock VS1 F4 idempotent transport PASS - 2026-09-24

The stock upstream VS1 write implementation has now passed a bounded hardware transport test on ordinary setpoint `0x2306`.

Observed:

```text
VS1_IDENTITY=20c2
BASELINE_2306=0x15 (21 C)
F4_IDEMPOTENT_WRITE addr=0x2306 value=0x15
F4_RESPONSE ret=0x01 addr=0x2306 data=00
READBACK_2306=0x15 (21 C)
FINAL_VS1_2306=0x15
P300_RESTORED=yes
SPLITTER_RESTARTED=yes
RESULT=PASS
```

Important response semantic: the F4 response payload was `00`, not an echo of the requested `15`. Effective value confirmation therefore relies on the following F7 readback, not on the response payload.

This proves F4 transport acceptance and same-value readback, but not yet actual state mutation. The next gate is a bounded one-degree `0x2306` change with exact F4 restore plus F7 and P300 post-verification.

Evidence: [idempotent F4 gate](../config/optolink-splitter/research/vitosoft/vs1-f4-idempotent-prep-2026-09-24-evidence.json).

## 0xxxxxx. Stock splitter permanent-VS1 read gate PASS - 2026-09-24

The completed 60-second gate passed:

```text
VS1_MAINPID=194040
JOURNAL_VS1_INITIALIZED=yes
JOURNAL_MAIN_LOOP=yes
JOURNAL_UNEXPECTED_RESTART=no
MQTT_EXPECTED=212
MQTT_SEEN=212
MQTT_MISSING=0
SETTINGS_RESTORED=yes
RESTORED_BASELINE_PROTOCOL=VS2/300
RESULT=PASS
```

Original and restored `settings_ini.py` SHA256 were identical:
`afb2beeddbdde21b6bbfdf0a66ec3be0f77998a7c1f50c32d7386d5eefe9ea05`.

This hardware-validates the existing HA read path in permanent VS1 mode. It removes the remaining read-side architecture objection to running normal F7 datapoints and future GFA 6B reads under one splitter-owned serial session.

Still unresolved before a permanent production switch:

- VS1 Virtual_WRITE / F4 behavior;
- the actual structured GFA_READ splitter patch;
- long-duration FF behavior;
- catastrophic interruption recovery.

Evidence: [stock VS1 smoke gate](../config/optolink-splitter/research/vitosoft/vs1-stock-splitter-smoke-prep-2026-09-24-evidence.json).

## 0xxxxx. Stock splitter permanent-VS1 smoke gate prepared - 2026-09-24

The next gate is implemented in [`vs1-stock-splitter-smoke.md`](vs1-stock-splitter-smoke.md). It requires a clean tracked `/opt/optolink` checkout at `origin/main`, leaves splitter source unmodified, and temporarily changes only:

```text
vs1protocol=True
mqtt_listen=None
tcpip_port=None
olbreath=0.15
```

The helper ultimately ran the stock splitter for 60 seconds, required a stable MainPID plus `VS1/KW protocol initialized` and `enter main loop`, and subscribed to the existing MQTT base topic. All 212 Home Assistant poll items enabled on cycle 0 published freshly; retained pre-test messages did not count.

The original `settings_ini.py` is saved and later restored byte-for-byte, including mode/uid/gid. SIGINT/SIGTERM/SIGHUP cleanup is armed before any service/settings change. The normal splitter and Party state are restored, and the baseline splitter must log `VS2/300 protocol initialized` again.

Preparation evidence: [stock VS1 smoke gate](../config/optolink-splitter/research/vitosoft/vs1-stock-splitter-smoke-prep-2026-09-24-evidence.json).

## 0xxxx. Mixed VS1 F7/6B hardware compatibility PASS - 2026-09-24

The read-only mixed-session probe passed. Seven stable datapoints matched byte-for-byte across P300-before, VS1/F7 and P300-after:

```text
00F8 20c2
00FB 03
2306 15
2323 02
6300 37
6773 00
778C 0103
```

Inside the same persistent VS1 session, GFA reads returned P80=`20,20`, P06=`00`, P09=`93`, P87=`20`. No FF occurred. P300 and both previously running services were restored. The intended 150-ms reply-to-next-request spacing was actually observed at 150-151 ms during the mixed block.

This proves the transport primitive needed for a one-owner VS1 design on this appliance. It does not yet validate the complete production poll list, sustained HA freshness, VS1 Virtual_WRITE behavior, long-run FF rate or recovery policy.

Next: run the unmodified upstream splitter temporarily in permanent VS1 mode with the existing HA read poll list, while disabling MQTT/TCP write ingress and stopping the party emulator. Only after that passes should a structured GFA_READ production patch be enabled.

Evidence: [mixed VS1 live run](../config/optolink-splitter/research/vitosoft/vs1-mixed-compat-run-2026-09-24-evidence.json). Runbook: [mixed VS1 integration](vs1-mixed-gfa-integration.md).

## 0xxx. P87 semantic bound and production-integration probe - 2026-09-24

Static Vitosoft metadata still supplies only `P87 / GFA Status 3 / 0x4057`; no bit table was recovered. Public WB2A service documentation places first valid ionization at flame formation about 2-3 seconds after gas-valve opening, while a Viessmann Customer-Care VSKO description associates E8 / VSKO 61 and 189 with invalid ionization during a 10-second start phase and separately describes VSKO code 5 as flame loss during stabilization time.

Together with the measured P87.b1 timing, this argues against interpreting bit 1 as first flame recognition. The bounded wording is: **unnamed GFA status marker/precursor near the end of the supervised start/stabilization interval**. Manufacturer semantics and causality remain unresolved.

Upstream splitter inspection at `philippoo66/optolink-splitter` main `c1ee204a1421447721603c5f21c6da7337fdac97` shows that permanent VS1/KW mode already carries ordinary Virtual_READ/WRITE traffic through F7/F4, but structured generic requests are not implemented for VS1 and no structured GFA_READ helper exists in `optolinkvs1.py`.

The prepared [mixed VS1 compatibility probe](vs1-mixed-gfa-integration.md) therefore tests the prerequisite without changing configuration: P300 stable values -> one persistent VS1 session with interleaved F7 and 6B reads -> P300 stable post-check. Only after a PASS should a production splitter patch be designed.

Machine evidence: [P87 semantics / VS1 integration checkpoint](../config/optolink-splitter/research/vitosoft/gfa-p87-semantics-vs1-integration-2026-09-24-evidence.json).

## 0xx. P87/P09 high-resolution ordering resolved - 2026-09-24

The 35-second hi-res run completed with 29 accepted P80-guarded blocks / 58 accepted P87-P09 pairs, zero rejected blocks, zero reconnects and no FF. The 37 C trigger and exact 21 C restore were readback-verified; P300 20C2 and both services were restored; result PASS.

Critical brackets:

```text
P87 bit 1 clear -> set:
(11:06:06.897, 11:06:07.392]   width 495 ms

P09 plateau 0x93 -> below:
(11:06:07.649, 11:06:08.139]   width 490 ms
```

These windows do not overlap. At 11:06:07.392 P87 was already `0x62`, while at 11:06:07.649 P09 was still `0x93`. The minimum separation between the windows is 257 ms. Therefore **P87 bit 1 becomes set before P09 leaves the high-start modulation plateau** in this run.

This establishes temporal ordering, not causality. Bit 1 still must not be named "flame stabilized", "stabilization complete", "regulation enabled" or any other vendor semantic. Static sources still provide only `P87 / GFA Status 3 / 0x4057`.

No faster live polling is required merely to establish ordering. Next work should focus on P87 semantics/source interpretation and production-safe VS1 integration.

Evidence: [hi-res live run](../config/optolink-splitter/research/vitosoft/gfa-p87-p09-hires-run-2026-09-24-evidence.json). Detailed analysis: [P87/P09 high-resolution correlation](gfa-p87-p09-hires.md).

## 0x. P87 static review and high-resolution follow-up prepared - 2026-09-24

Static evidence remains limited to event 8211, `P87 GFA Status 3`, address `0x4057`, one byte, NoConversion. No enum or bit-definition table was recovered from the inspected private Vitosoft archive, and the public Vitosoft-derived export only corroborates the same generic event label. P87 bit 1 therefore remains unnamed.

The prepared [P87/P09 high-resolution probe](gfa-p87-p09-hires.md) reuses the exact pinned v1.0.1 37 C trigger and exact-value restore. It samples two P87/P09 pairs between P80 guards and reverses pair order by block, while retaining the existing 150-ms minimum reply gap. Default live window is 35 s. No new write path exists.

Machine evidence: [P87 static/hi-res preparation](../config/optolink-splitter/research/vitosoft/gfa-p87-static-and-hires-2026-09-24-evidence.json).

## 0. Successful self-triggered startup correlation - 2026-09-24

Trigger helper v1.0.1 read the original A1 normal setpoint as 21 C and `0x55DC=0`, wrote only `0x2306=37`, verified 37 by Virtual_READ, and then captured 50 clean GFA rounds. Cleanup restored and read back 21 C; P300 20C2 and both services were restored. Result PASS, zero rejected rounds/reconnects/FF.

The capture begins 4.793 s after the 37 C trigger at P84=02. It observes P87 `20->40->50->60->62`, P84 `02->05->06`, fan rise through 2490->3900->4500->4590 rpm and the subsequent high-start hold.

The key new correlation is P87 `60->62`: bit 1 is first observed set at 10:42:26.805. P09 is first observed below its raw-93 / 57.6534% plateau at 10:42:27.302. Their true transition windows overlap within the same sequential acquisition round, so causal order is not proven, but bit 1 is now a strong candidate marker for the release/end of the high-start plateau. It must not yet be named "flame stabilized" or "regulation enabled".

First P84=06 to first P87=62: 10.148 s. First P87=60 to first P87=62: 9.866 s. This reproduces the previously observed short startup hold.

At restore, `0x2306=21` was read back successfully, but immediate `0x55DC=0x21` showed the burner still active. A restored room setpoint therefore does not imply immediate burner shutdown.

Evidence: [successful triggered startup](../config/optolink-splitter/research/vitosoft/gfa-triggered-startup-2026-09-24-evidence.json). Detailed analysis: [GFA status/startup probe](gfa-status-probe.md).

## 0a. Triggered-status attempt - write ACK parser corrected, 2026-09-24

The first self-triggered helper read `0x2306=21` and `0x55DC=0`, confirmed P80=20 twice, then sent the bounded temporary write `0x2306=37`. The WB2A returned `41 05 01 02 23 06 01 32`. Version 1.0.0 misparsed the final payload byte as a data-length field and aborted before the required readback or any GFA observation.

Cleanup sent the original 21 C value three times; all three writes received the same successful one-byte Virtual_WRITE acknowledgement. Because the parser aborted before readback, that run did not independently verify the final setpoint value. P300 20C2 was restored and both services restarted.

Version 1.0.1 corrects this specific response grammar while retaining exact Virtual_READ verification of the requested value. Commit `8259cd5f3c07c4d46939e17e7bc87dc47378717f`, SHA256 `6d5810e1595ba6e464452dcd927259e9bade8f550a92b492fd40c2a27972604b`; 168/168 offline tests pass, including the exact live ACK frame.

Evidence: [failed triggered-status run](../config/optolink-splitter/research/vitosoft/gfa-triggered-status-failed-run-2026-09-24-evidence.json).

## 0. Latest live result - continuous startup trace, 2026-09-24

The unchanged paced helper ran for 60 seconds with 150-ms minimum reply spacing. The appliance transitioned from idle-like zero GFA values into a complete startup-like sequence during the observation. All 49 rounds were accepted; no FF reply or reconnect occurred. Closing P80 remained 20, P300 20C2 was restored, and both previously running services reported running.

Observed P84 raw sequence: **00 -> 02 -> 04 -> 05 -> 06**. No manufacturer phase names have been recovered, so these remain raw states.

Key timing:

- P84 02 at 08:56:37.119.
- P09 raw 93 / 57.6534% at 08:56:37.895.
- P10 raw 58 / 35.2% at 08:56:38.104.
- P06 first nonzero at 08:56:38.882: 660 rpm.
- P06 first reaches 4500 rpm at 08:56:41.339.
- P84 04 at 08:56:45.655, 05 at 08:56:46.766, 06 at 08:56:47.934.
- P09 first leaves its 57.6534% plateau 9.368 s after the first observed 06.
- P06 first drops below 4410 rpm 10.362 s after the first observed 06.
- Last round: 2790 rpm, P09 34.9058%, P10 33.2%, P84 06.

This is the strongest timing lead for the short startup-hold/flame-stabilization investigation. It does not prove that P84=06 is flame recognition because the logger did not poll an independent flame signal. See [paced comparison](gfa-paced-comparison.md) and the machine-readable startup evidence for details.

## 1. First P80 hardware result

Source: the user's pasted console transcript naming `/root/wb2a-gfa-p80-20260923-223259-168588.log`; the separately stored log file was not fetched.

Helper: `wb2a-gfa-p80-probe.py` 1.0.0, commit `ab32e2d2fe2c165390d7098dcffc4bb2e097543d`, SHA256 `6de883c422a09c821b342d12e5bb71dd3d518d8115ec2495bdfb202f5a7f50cb`.

Local environment: Python 3.13.5 / pyserial 3.5, configured CP2102 by-id adapter resolving to `/dev/ttyUSB0`, 4800 8E2, `vs1protocol=False`, no Vitoconnect forwarding adapter. The other USB adapter was not selected.

| Local time (+02:00) | Observation |
| --- | --- |
| 22:32:59.146 / .172 | Running party emulator and splitter stopped. |
| 22:33:01.258 | Baseline P300 Virtual_READ 00F8/2 returned `20 c2`. |
| 22:33:05.495 -> .595 | `01 6b 40 50 01` -> `20`. |
| 22:33:09.880 -> 22:33:10.027 | Independently synchronized repeat -> `20`. |
| 22:33:12.139 | Restored P300 00F8/2 again returned `20 c2`. |
| 22:33:14.167 / 22:33:16.210 | Splitter and party reported running; PASS. |

Both GFA reads used EOT, interface-detection ENQ, a fresh VS1 ENQ, then STX plus GFA_READ. The P300 response frame excluding ACK was `41 07 01 01 00 f8 02 20 c2 e5` before and after the test.

This established P80=`0x20`, the locally selected GFA branch, and independent read/recovery. The [P80 runbook](gfa-p80-probe.md) preserves the procedure and restoration limits. The tested P80 helper is unchanged.

## 2. Burner-off and burner-on snapshots

Source: two uploaded console transcripts. Burner off/on was explicitly reported by the user; the snapshot helper did not poll flame state. The separate device-side `.log` files were not fetched.

Helper: `wb2a-gfa-snapshot.py` 1.0.0, commit `8e9b2271c0bbc4bc8691f2778720a444e9f26476`, SHA256 `b8a89bae4a7dbcc4047b115d9c733f596f0e3a9a60d8025db7a86e1c9caf0141`. Both user runs passed hash checks and 45 offline tests before serial access.

| Register | Burner off | Burner on | Burner-on SAMPLE time |
| --- | --- | --- | --- |
| P06 / 0x4006 | `00` -> 0 rpm | `89` = 137 -> **4110 rpm** | 22:45:07.923 |
| P09 / 0x4009 | `00` -> 0% | `7b` = 123 -> **48.2406% modulation setpoint** | 22:45:12.268 |
| P10 / 0x400A | `00` -> 0% | `67` = 103 -> **41.2% fan PWM setpoint** | 22:45:16.612 |
| P84 / 0x4054 | `00` | **`06`** | 22:45:20.978 |

Idle SAMPLE times were 22:42:17.349, 22:42:21.802, 22:42:26.242 and 22:42:30.667. The source-hashed snapshot JSON preserves exact raw samples/timestamps/latencies.

The GFA-branch source events are 8175 (P06 x30 rpm), 8259 (P09 x0.3922%), 8179 (P10 x0.4%) and 8208 (P84 raw). P09 is not a fan-RPM setpoint for this branch.

| Check | Burner-off run | Burner-on run |
| --- | --- | --- |
| Transcript-named log | `wb2a-gfa-snapshot-20260923-224201-168882.log` | `wb2a-gfa-snapshot-20260923-224452-168983.log` |
| P80 values including closing guard | `20 / 20 / 20` | `20 / 20 / 20` |
| P300 before/after | `20c2 / 20c2` | `20c2 / 20c2` |
| Runtime reads | 4/4 | 4/4 |
| P300 restored / splitter restarted | yes / yes | yes / yes |
| Party restored / final result | yes / PASS | yes / PASS |
| Total logged duration | 39.126 s | 38.804 s |
| Splitter stop -> running | 37.058 s | 36.735 s |
| P06 -> P84 SAMPLE span | 13.318 s | 13.055 s |

Home Assistant value delivery was explicitly reported after the first snapshot. The second transcript proves service restoration but does not independently confirm application freshness.

The off/on contrast supports meaningful runtime values, including a GFA-reported RPM value. It is not independent tachometer calibration. P09 and P10 are distinct command quantities sampled at different instants; their difference is not automatically a fault. No simultaneous 55DC/A305 comparison or thermal-kW calibration was supplied.

P84=00 and P84=06 are observed raw states, not a recovered manufacturer enum. Do not declare 06 exclusively steady regulation or assign every other phase a guessed name. In this VS1 reply context, P84 raw `06` is data, not a P300 acknowledgement.

The independent-synchronization snapshot spans about 13 seconds across its four channels. It cannot resolve the approximately 12-second post-flame interval or prove a relationship at one common instant.

## 3. Same-session access is locally demonstrated for the short test

Helper: `wb2a-gfa-session-probe.py` 1.0.0, commit `3b9bb24e035034745b3b3949ad0a86817985597a`, SHA256 `32351e07cb0d661c00f7bcb7851d8103aca0b9cbc2f339041202e48b760d6da2`. The original tested helper is unchanged.

Source: uploaded `Eingefügter Text(20260923-205625).txt`, SHA256 `cdea0307880b69ecbc22ea6af9a81a4e2068c36f315a1320210e7639bedeb1ab`, naming `/root/wb2a-gfa-session-20260923-225537-169322.log`. All 56 offline tests and the download hash check passed before the actual run.

### Actual sequence

- 22:55:37.764/.787: party emulator and splitter paused.
- 22:55:39.873: baseline P300 identification `20c2` confirmed.
- 22:55:44.175 and 22:55:48.521: two independently synchronized P80 replies `20`.
- 22:55:48.571: first bare `6b 40 50 01` request in the still-active VS1 session, without new EOT/STX; reply `20` at 22:55:48.627.
- Ten response-paced P06/P09/P10/P84 rounds, each followed by P80=`20`, completed without reinitializing the session.
- 22:55:54.930: `ROUND_CONFIRMED=10/10`; burst 6.359 s; 40 runtime samples.
- 22:55:59.316: independent closing P80 reply `20`.
- 22:56:01.428: restored P300 `00F8/2 = 20c2` verified.
- 22:56:03.458 and 22:56:05.508: splitter and party reported running.
- 22:56:05.509: `SESSION_ROUNDS=10/10`, `P80_CONFIRMED=0x20 GFA`, `P300_RESTORED=yes`, `SPLITTER_RESTARTED=yes`, `RESULT=PASS`.

There were 11 successful same-session P80 guards (initial guard plus ten rounds) and three successful independent P80 reads (two entry plus one exit). All 40 runtime replies were `00`. These are actual zero-valued responses, not missing data; P80 consistently returned nonzero `20` in the same transport. The state is consistent with idle, but there was no independent flame measurement or explicit new burner-state report in this upload.

### Timing calculated from the uploaded transcript

| Metric | Minimum | Mean | Maximum |
| --- | ---: | ---: | ---: |
| Consecutive P06 host-receive interval | 597 ms | **625.889 ms** | 703 ms |
| P06-to-P84 span within a round | 322.3 ms | **367.35 ms** | 417.6 ms |
| Individual runtime reply latency | 55.1 ms | 74.06 ms | 151.5 ms |

Approximately 1.60 complete channel sets per second follows from the P06 intervals. Do not divide 40 by 6.359 and call that the sampling rate of each sensor. All channels are sequential, and the device's internal acquisition time is not known from host receive timestamps.

The four-channel spread is substantially shorter than the previous approximately 13-second snapshots. This supported moving to a bounded observation window, but was not proof of minutes-long data validity or a complete burner cycle. No new Home Assistant freshness report was supplied for this specific run.

### Source model and retained constraints

Vitosoft IL methods `VS1Message::toByteArray` (285-322), `VS1::_timer_processor_Elapsed` (985-1099) and `VS1::sendVS1Message` (1283-1510) separate setup/STX from subsequent four-byte reads. The observed short session supports that model locally. `sendKeepVS1Message` exists separately, but no additional keepalive command is introduced.

The pinned session helper enforces the fixed read allowlist, 300-ms host idle-gap guard, no continuation through unexpected queued/trailing data, no automatic retransmission and a 20-second burst budget. Its 56 tests cover framing, identities, per-round guards, timestamps, timeouts, logging stalls and recovery paths. Passing the following P80 guard confirms identity/alignment at that point, NOT per-value integrity or physical plausibility; see the counterexamples in the long run below.

## 4. First long observation failed; recovery worked

The [GFA observation logger](gfa-cycle-logger.md) was executed for a requested 300 seconds. Logger commit: `008e802ea8d5d0dc5a7a8658896722d37ed922da`; SHA256 `d5d98242e6f9526522a53f3c801d856ba8c1a7fde6349c05b56059fa732a54e3`. It requires the unchanged P80 and session helpers. All 89 offline tests passed before the run, but those simulated tests did not establish live response validity.

Source: `Eingefügter Text(20260923-211214).txt`, SHA256 `c2f84dfd3e70d2204fa03011568b9b58895d0ff094e95948901fab3d830b6642`. It includes the complete generated JSONL (466 objects, 463 rounds) as well as the console transcript. Only the separate TX/RX `.log` is still missing.

| Event | Result |
| --- | --- |
| Observation start | 23:06:39.617 +02:00 |
| Retained rounds | 463, all with P80=20; 1852 runtime values |
| All-zero rounds | 461 |
| Round 142, P06 at 23:08:06.612 | Isolated FF, mechanically decoded as 7650 rpm; P09/P10/P84 zero, P80=20 |
| Round 222, P84 at 23:08:56.490 | Isolated FF, surrounding phases zero; P06/P09/P10 zero, P80=20 |
| Next attempted round 464 | P80=FF, guard mismatch; not published as a valid complete JSON round |
| Failure message | 23:11:26.069, RESULT=FAIL |
| P300 restoration | 23:11:28.130, actual 20C2 identity verified on attempt 1 |
| Splitter / party running | 23:11:30.205 / 23:11:32.261 |

P06 and P84 each returned zero immediately before and after their isolated FF values. The two nonzero rounds are not evidence of a burner start. No separate flame state was captured. The earlier firing snapshot does not establish firing during this later observation.

The reported summary duration, 285.814239 seconds, stops at the last completed round in version 1.0.0. The console start-to-failure interval is 286.452 seconds. Do not infer a fixed five-minute session expiry: anomalies already occurred around 87 and 137 seconds, and the failed guard's exact raw context remains unavailable.

Retained-round timings: P06 interval 564.993-746.024 ms, mean 616.970 ms; P06-to-P84 span 318.604-511.339 ms, mean 369.652 ms. These approximately 1.62 rounds/second measurements do not compensate for missing per-value validity. See the linked evidence and [detailed investigation](gfa-cycle-ff-investigation.md) for counts, exact timestamps and code references.

The inspected helper raises a distinct exception on a timeout; it does not synthesize FF. The terminal message means the identity check processed FF instead of 20, not a decoded boiler fault or a successful changed device identity. Its physical origin is not established. Internal GFA response availability, transient/serial behavior and other causes remain hypotheses.

The current logger scales runtime FF without a quality flag when the next P80 passes. Its 7650-rpm output and phase-change counters therefore must not be treated as validated physical events. This is an acquisition-quality limitation, not a reason to discard raw evidence, silently replace FF with zero or disable the guard.

## 5. Immediate next step and production boundary

**Read the existing log before any repeat.** The offline extraction command and precise file path are in [the FF investigation](gfa-cycle-ff-investigation.md). The full JSONL is already available and analyzed; do not request it again. Do not repeat the unchanged 300-second test, extend it to 600 seconds, guess new commands or remove identity validation.

Documented logger follow-up: retain raw/converted/quality fields separately; report suspect FF values without claiming a universal sentinel definition; distinguish identity-guard success from measurement validity; preserve failed-round context and actual failure elapsed time; review any bounded reread/resynchronization policy explicitly after inspecting the raw evidence. No revised live logger was deployed in this analysis.

Normal MQTT/TCP polling and a running party emulator were paused throughout. Service restoration succeeded, but current Home Assistant freshness still requires a separate observation. Old HA states are not contemporaneous samples during a pause. Pausing an emulator can affect externally maintained heating requests; the absence of activity here does not by itself identify why the burner remained idle-like.

Only after response quality is resolved should another natural operating trace be collected and phase/55DC/flame correlation expanded. Permanent Home Assistant acquisition requires deliberate serial ownership and protocol scheduling, not another competing serial process. Do not use the suspect values for fan, burner or pump control.

GFA software identity/coding-plug diagnostics, E7 persistence, internal-pump request selection, full firmware acquisition and M2 remain separate research tasks. No production dashboard, poll list, updater behavior, heating coding or safety parameter was changed by this analysis.
