# One real read-only acceptance (NOT automatically executed)

`live_probe.py` is deliberately inert without both `--execute` and
`--accept-telemetry-pause`. The saved source snapshot includes an **unmodified**
copy of the historical `tools/wb2a-handover-probe.py` module as `legacy_probe.py`
(Git blob `006c3c75f6e5e0dc3f564156985912bffb1d9bdc`) to reuse its audited
service manifest, `/proc` serial ownership guard, locks, pySerial exclusive
open and systemd recovery primitives. This is **not** an update to the running
P300 research branch or production checkout.

An active research logger or incomplete service state causes immediate refusal.
A successful worker must prove P300 20C2/0103, VS1 20C2/0103, P80=20, valid
P06 and fresh production GFA, with the original service restored. Independent
`ExecStopPost` runs after worker death, including SIGKILL; it is not a guarantee
against host/power/kernel failures. No undocumented writes or real device
parameter changes are implemented.

Run Linux Python 3.11+ offline regressions before authorization:

```sh
python3 -m unittest discover -s tests -p 'test_handover*.py' -v
```

The complete reasoning and recovery limits are in
`docs/handover-live-acceptance-2026-10-09.md`.
