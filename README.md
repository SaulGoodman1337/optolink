# Optolink-Web

This branch contains the **standalone Optolink-Web application** and its Proxmox LXC deployment files.

It is intentionally separated from both the production splitter/Home Assistant branch and the firmware/reverse-engineering workspace.

## Branch purpose

Optolink-Web is a lightweight browser UI for an already running Optolink-Splitter. It does not own the USB/Optolink adapter. Communication is via the splitter TCP endpoint and optionally MQTT.

Included here:

- FastAPI/uvicorn web backend;
- static frontend and templates;
- datapoint catalog;
- LXC installer and update flow;
- Community Scripts metadata;
- web-specific documentation.

Not included:

- physical Optolink-Splitter deployment;
- Home Assistant production profile;
- firmware/EEPROM/KBus research;
- experimental probes or hardware reverse engineering.

Use `optolink-splitter-ha` for the production splitter and `optolink-research` for research.

## Installation

Run the web LXC from this branch. The branch defaults in the installer and updater are pinned to `optolink-web`.

After installation configure:

```text
/etc/optolink-web.env
```

At minimum:

```text
OPTOLINK_HOST=<splitter-ip>
OPTOLINK_PORT=65234
```

Optional MQTT settings provide live values. Writes remain disabled by default:

```text
ALLOW_WRITES=false
```

## Service

```bash
systemctl status optolink-web --no-pager
systemctl restart optolink-web
journalctl -u optolink-web -f
```

The web UI listens on port `8080`.

## Update

Inside the Optolink-Web LXC:

```bash
update
```

The updater refreshes only this web application and its Python dependencies. `/etc/optolink-web.env` is preserved.

## Security

The application currently has no built-in user authentication. Keep it on a trusted network or place it behind an authenticated reverse proxy. Do not enable `ALLOW_WRITES` until the TCP/MQTT connection and relevant datapoints have been verified.

## Repository layout

- `apps/optolink-web/` — application, templates and static assets;
- `ct/optolink-web.sh` — Proxmox Community Scripts entrypoint;
- `install/optolink-web-install.sh` — in-container installation;
- `json/optolink-web.json` — metadata;
- `docs/optolink-web.md` — detailed application documentation;
- `tools/private-run.sh`, `tools/private-update.sh` — branch-aware update bootstrap.

This branch is not part of the production Optolink-Splitter runtime.
