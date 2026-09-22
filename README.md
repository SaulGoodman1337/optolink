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

or:

```bash
systemctl is-active optolink-web.service
```

Do not remove the Optolink files from the old `community-scripts` repository until the migrated LXC has completed a successful `update`.

## Documentation

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
