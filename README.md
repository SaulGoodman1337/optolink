# Optolink

Standalone Proxmox VE helpers, configuration, diagnostics and research for local Viessmann Optolink access.

This repository was split from `SaulGoodman1337/community-scripts` with path-filtered Git history. The relevant Optolink commit history, authors and timestamps were retained; commit SHAs changed as expected because the history was filtered.

## Included components

| Component | Purpose | Default port |
| --- | --- | ---: |
| **Optolink-Splitter** | Privileged Debian LXC for a physical Viessmann Optolink adapter, MQTT and TCP/IP access | TCP `65234` |
| **Optolink-Web** | Unprivileged Debian LXC with a browser UI for an existing Optolink-Splitter | Web `8080` |

## Install on a Proxmox VE host

For the current public repository:

```bash
bash -c "$(curl -fsSL https://raw.githubusercontent.com/SaulGoodman1337/optolink/main/ct/optolink-splitter.sh)"
```

or:

```bash
bash -c "$(curl -fsSL https://raw.githubusercontent.com/SaulGoodman1337/optolink/main/ct/optolink-web.sh)"
```

If the repository is private, use the authenticated `csrun` bootstrap described in [docs/private-access.md](docs/private-access.md).

## Existing LXC migration

Existing Optolink LXCs that were installed from `SaulGoodman1337/community-scripts` can retain their current compatibility wrapper. Change only the stored repository:

```bash
sed -i \
  's|^COMMUNITY_SCRIPTS_REPO=.*|COMMUNITY_SCRIPTS_REPO=SaulGoodman1337/optolink|' \
  /etc/community-scripts-private.conf

update
```

Then verify the relevant service:

```bash
systemctl is-active optolink-splitter.service
```

Do not remove the Optolink files from the old `community-scripts` repository until the migrated LXC has completed a successful `update`.

## Documentation

- [Private Vitosoft source archive](docs/vitosoft-private-archive.md) - private companion repository, verified collector coverage and explicit full-payload import status; no raw proprietary files in this repository.
- [Stock splitter permanent-VS1 smoke gate - 2026-09-24](docs/vs1-stock-splitter-smoke.md) - prepared final read-path gate before production GFA polling: stock splitter, current HA poll list, MQTT coverage check, write ingress disabled, byte-exact settings restore.
- [Mixed VS1 Virtual/GFA integration validation - 2026-09-24](docs/vs1-mixed-gfa-integration.md) - live PASS: stable P300/F7/P300 values matched while GFA 6B reads were interleaved in one VS1 session. Next gate: stock splitter with the existing HA read poll list in temporary permanent-VS1 mode, write ingress disabled.
- [GFA measured 150-ms pacing result - 2026-09-24](docs/gfa-paced-comparison.md) - 2 FF replies in 1130 measurement-round reads versus 4 in 804 at the earlier spacing; descriptive improvement, not a fix. Final abort was due to insufficient re-entry time; P300/services restored. Next: unchanged helper, one 60-second naturally established firing observation. Read before older GFA next-action sections.
- [GFA quality-aware logger and FF checkpoint - 2026-09-24](docs/gfa-quality-logger.md) - original quality/re-entry implementation and prior raw-FF analysis; the newer measured result above supersedes its pending-hardware-test wording.
- [Vitosoft all-devices cross-profile analysis - 2026-09-24](config/optolink-splitter/research/vitosoft/all-devices-2026-09-24.md) - 399-profile relation graph, exact VDens/VPend/VScot alias, orphan events, WILO/EEPROM linkage limits; derived metadata only.
- [Current WB2A research plan and TODOs - 2026-09-24](docs/research-plan-2026-09-24.md) - authoritative current execution queue, priorities, completion criteria and evidence discipline.
- [PCB research: 7424735 / VBC130 comparison board](config/optolink-splitter/research/regulation-board-7424735-pcb-research.md) - online comparison-board analysis, likely M16C/62P M30624FGPFP MCU, X15/X10/KM-BUS follow-up, and explicit WB2A/GG1 identity boundary; tracked in issue #25.
- [Collector research checkpoint - 2026-09-23](docs/collector-research-checkpoint.md) - historical cross-topic checkpoint; retained for evidence, but its old next-action wording is superseded by the current research plan.
- [Private archive analysis and evidence](config/optolink-splitter/research/vitosoft/private-archive-2026-09-23-analysis.md) - verified archive/SQL coverage, variant-specific GFA map, corrected firmware and pump assumptions; derived information only.
- [Project roadmap](docs/project-roadmap.md)
- [Repository cleanup plan](docs/repository-cleanup-plan.md)
- [Optolink-Splitter](docs/optolink-splitter.md)
- [Optolink-Web](docs/optolink-web.md)
- [Private repository access](docs/private-access.md)
- [WB2A research notes](config/optolink-splitter/research/README.md)

## Repository layout

```text
ct/                         Proxmox LXC entrypoints
install/                    In-container installers
tools/                      Update, profile, debug and emulator helpers
config/optolink-splitter/   Profiles, Home Assistant config and research
apps/optolink-web/          Optolink-Web application
docs/                       User documentation
json/                       Helper metadata
```

The Proxmox helper scripts continue to use the shared `community-scripts/core` framework where appropriate. Compatibility variable names such as `COMMUNITY_SCRIPTS_REPO` are intentionally retained so existing installations can migrate without changing their local updater layout.
