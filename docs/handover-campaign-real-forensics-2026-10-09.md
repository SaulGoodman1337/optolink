# WB2A handover research: verified results of the seven-round campaign

Date: 2026-10-09. Research branch only: `optolink-handover-acceleration`.
These values are calculated exclusively from operator-submitted terminal output.
No fresh access to hardware and no original device-side UART time captures exist.
See `tests/fixtures/real_campaign_20261009.json` for the sanitized,
source-derived test fixture and `tools/handover_acceleration/campaign_forensics.py`
for deterministic analysis of original local session files.

## A. Completed live results, without test-mock noise

The operator tested `dec2bf6ea0c91a933a951df06d556f775387d4db` using
`campaign.py --execute --accept-telemetry-pause --include-early-vs1`.
**228 offline regression tests passed** in that LXC environment.
The command prints several synthetic `PRODUCTION_HEALTH` lines before
`Ran 228 tests`: those are unittest mock cases, NOT repeated real MQTT checks.

### Seven verified standard single-ENQ roundtrips

| Variant | Complete single-ENQ roundtrip + GFA (ms) | Effective duration incl. added idle (ms) | First P300 ENQ after EOT (ms) | VS1 ENQ after EOT (ms) |
|---|---:|---:|---:|---:|
| control_a | 4678.910 | 4678.910 | 1998.187 | 1997.371 |
| vs1_idle_400 | 4680.756 | 5080.756 | 1997.233 | 1997.419 |
| vs1_idle_1100 | 4499.808 | 5599.808 | 1873.021 | 1997.370 |
| p300_idle_400 | 4669.045 | 5069.045 | 1997.828 | 1997.718 |
| p300_idle_1100 | 4623.621 | 5723.621 | 1997.821 | 1998.104 |
| both_idle_700 | 4633.550 | 6033.550 | 1997.149 | 1997.350 |
| control_b | 4730.588 | 4730.588 | 1997.310 | 1996.430 |

- Mean *core* roundtrip (seven runs): **4645.183 ms**, median 4669.045 ms.
- Mean *total including both inserted idle offsets*: **5273.754 ms**.
- Mean sum of both EOT->ENQ host waits: **3977.187 ms** (85.62% of
  the mean core roundtrip). The remaining 667.995 ms include real wire
  time and required read/CRC/identity/GFA verification, not solely overhead.
- The sole shorter ENQ reading is 1873.021 ms, in a run with 1100 ms
  *additional* VS1 idle. It is not a reproducible net acceleration.
- Phase sweep finished `PASS_VERIFIED_READ_ONLY_PHASE_SWEEP`, no
  measurement errors, original services restored and subsequent MQTT
  health `P80=20` / `P06=00` passed.
- Previous 4610.091 ms result is a distinct n=3 test series with different
  verification segmentation. No per-round hardware acceleration claim follows.

**Important accounting correction:** The historic field name
`full_elapsed_after_vs1_idle_ms` includes additional *P300* idle but explicitly
excludes the optional *VS1* idle. An analysis which treats that field as
complete inclusive wall time rewards the 1100-ms VS1 delay incorrectly.
The new analyzer adds **both** idle offsets, with a consistency check against
that historic field.

## B. Negative early-START and early-VS1 variants reveal timing continuity

There were two different operator-approved experimental attempts:

| Evidence | Experimental early P300-START | Experimental early VS1-ID |
|---|---:|---:|
| First EOT -> recovery EOT | 376.323 ms | 375.789 ms |
| Recovery EOT -> first observed ENQ | 1621.454 ms | 1622.895 ms |
| **First EOT -> first observed ENQ** | **1997.777 ms** | **1998.684 ms** |
| First EOT -> second observed ENQ | 4235.737 ms | 4235.861 ms |

Each early experiment sent a **known** read/synchronization telegram before
any expected ENQ; neither returned the required verified response inside the
350-ms experiment window. Both experimental hypotheses are negative within
that specified timeout. A two-ENQ recovery followed. P80 and true GFA P06
were subsequently verified over production MQTT, each showing respectively
`20` and `00`. `CAMPAIGN=EARLY_VS1_NEGATIVE_BUT_RESTORED` with exit code 0
means the scientific negative was successfully *recovered*; it does **NOT**
mean a successful early handshake.

**New evidence:** A second EOT approximately 376 ms after the first did not
push the observed first ENQ back to 2 s **after the second** EOT. Both
attempts instead have the first observed ENQ around 1998 ms **after the
first** EOT. This supports persistence of a pending synchronization
cycle across the second EOT in these two observations. It does not prove a
universal, unconditional firmware timer, and host/USB/driver timestamps
are not precise controller-side wire times.

The current validated single-ENQ operation still waits for approximately
2 s ENQ on each direction. Two speculative early-before-ENQ mechanisms
were tested and failed (within 350 ms). **There is no validated sub-4-s
read-only roundtrip on this controller as of this evidence.** Unknown
alternative states are not excluded by this sample.

## C. Engineering consequence: do not optimize the wrong metric

1. Further `sleep` reductions in the Python host cannot eliminate
   3.98 s of independently observed ENQ waits. Changing a *timeout*
   changes failure time, not controller response time.
2. Changing the time EOT is sent by inserting 400/700/1100 ms idle did not
   produce an inclusive improvement. Identical retries are low-value.
3. Avoiding whole VS1/P300/VS1 roundtrips by **one in-process owner with
   a P300 batch** is the measurable next software lever. It reduces number
   of expensive synchronization pairs, not the inherent timing of one pair.
4. Real VS1 GFA P06 cannot be replaced by P09/P10 or a stale RAM echo.
   In the cost model a continuous 2.1-s P06 freshness deadline rules out
   even one P300 roundtrip at the observed switching cost; missing continuous
   service is a hard constraint, not merely a scheduling preference.
5. The next potential **on-wire** breakthrough would require a *new verified
   state-transition mechanism* or an equivalent continuously updating
   sensor source. The tested early START and early VS1 ID do not provide it.

## D. New executable research components

- `campaign_forensics.py`: offline-only validated analysis. Reads the original
  `campaign.json`, the linked `summary.json` and each `recovery.json`, plus an
  optional earlier P300 session. Requires actual positive restore evidence;
  rejects missing files, malformed timings, FF P06, invalid P80, wrong stage
  ordering, corrupted service state and symlinked session artifacts.
- `phase_executor.py`: injected *offline* execution of a typed
  `phase_planner.py` plan against the existing `HandoverCoordinator`,
  including proper P300 batching, verified VS1 GFA, guarded session
  generations and fail-closed CRC/identity recovery. It has no serial
  discovery, open call, systemctl commands or production import path.
  The only implemented P300 operation remains identity FC01/00F8; it is
  **not** a verified new RAM or pump-command executor.
- `tests/test_handover_campaign_forensics.py` and
  `tests/test_handover_phase_executor.py`: new regression and error scenarios.

### Pure offline replay on the Optolink LXC

Once checked out at a pinned new commit (provided in the user conversation),
run without touching the currently running logger or services:

```sh
python3 tools/handover_acceleration/campaign_forensics.py \
  --campaign /root/p300-trial-work/handover-acceleration-live-results/campaign-20261009T200824Z-295114 \
  --early-p300-session /root/p300-trial-work/handover-acceleration-live-results/run-20261009T194636Z-294918
```

The script only reads existing JSON evidence and prints
`OFFLINE_FORENSICS_RESULT=COMPLETE_NO_HARDWARE_USED` if all evidence
checks pass. It does not issue even a new MQTT read, open any serial port,
start a service, or run another hardware handshake.

## E. Next implementation gate

The offline executor establishes state and batching semantics but is not
wired into the existing production splitter. Before enabling it live,
preserve the current MQTT/TCP, HA GFA and phased poll API, original write
readbacks, one in-process serial owner, and independent crash recovery.
Do not switch the live boiler to this experimental partial adapter.
