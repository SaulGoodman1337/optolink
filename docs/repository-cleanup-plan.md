# Repository cleanup plan

The repository has accumulated production profiles, experimental poll lists,
loggers, dashboard YAML, services and research notes in the same directory.
The next cleanup should make the distinction between **production**,
**research**, **diagnostics**, **legacy/archive** and **documentation**
obvious.

This document is a plan only. Do not move files until all installer/updater
references have been identified and a migration can be tested atomically.

## Current pain points

The main concentration is `config/optolink-splitter/`, which currently mixes:

- the production Home Assistant profile;
- a large Home Assistant dashboard;
- draft/experimental profiles;
- service units;
- diagnostic loggers;
- research documents;
- legacy VScotHO1 material;
- mapping/reference material.

Several scripts in `install/` and `tools/` use literal repository paths.
Moving files without updating these paths would break installation or
`update`.

## Proposed target layout

```text
config/optolink-splitter/
  profiles/
    vdensho1-20c2-wb2a-homeassistant.py
    vscotho1-20cb-poll-list.py

  homeassistant/
    dashboard.yaml

  systemd/
    optolink-party-emulator.service

  diagnostics/
    wb2a-rkr-cycle-logger.py
    wb2a-single-session-logger.py

  research/
    README.md
    device-vdensho1-20c2-wb2a.md
    coding-plug-7833971-2015-0201.md
    archive/
      ...old draft poll lists...

  reference/
    vcontrol-mapping.md

tools/
  install-helpers/
    ...profile application/update helpers...
  diagnostics/
    optolink-debug.py
  party/
    optolink-party-emulator.py
    optolink-party-test.sh
  bootstrap/
    private-run.sh
    private-update.sh

docs/
  project-roadmap.md
  repository-cleanup-plan.md
  optolink-splitter.md
  optolink-web.md
  private-access.md
```

The exact final names can be adjusted during the refactor; the important
boundary is production vs diagnostics vs research/archive.

## Cleanup sequence

### Phase 1 - inventory and classify

- enumerate every repository file;
- classify each file as production, deployment, diagnostic, research,
  reference, legacy/archive or documentation;
- identify duplicate/draft files and determine whether they still contain
  unique knowledge;
- identify every literal path reference in installers, updaters, apply
  helpers, README/docs and service installation logic.

### Phase 2 - remove stale concepts before moving paths

- eliminate disproved labels such as the former `0x55D3[6:7]` blower-rpm
  interpretation;
- update stale research entrypoints and "next experiment" sections;
- distinguish active production profiles from drafts by filename/location;
- preserve historical research that still explains why a mapping was rejected.

### Phase 3 - move files atomically

- move one logical group at a time;
- update all references in the same commit;
- keep the user-facing installed command paths stable, for example:
  `/usr/local/bin/optolink-debug`,
  `/usr/local/bin/wb2a-rkr-cycle-logger`, and `update`;
- retain compatibility wrappers only where they materially simplify migration.

### Phase 4 - validate

For the Optolink-Splitter installation:

- run Python compile checks for all installed Python files;
- run shell syntax checks on installer/update/apply scripts;
- run the Home Assistant discovery dry-run;
- perform a real `update` on the existing LXC;
- verify `optolink-splitter.service` and party-emulator service;
- verify Home Assistant MQTT discovery and state refresh;
- verify the diagnostic commands still resolve from `/usr/bin`.

For Optolink-Web:

- verify its installer/update references were not affected.

## Documentation structure

The root README should stay short and navigational.

Use:

- `docs/project-roadmap.md` for open work;
- `docs/repository-cleanup-plan.md` for repository maintenance;
- `config/optolink-splitter/research/README.md` for the current WB2A
  reverse-engineering checkpoint;
- device/coding-plug research files for detailed evidence;
- normal user documentation for installation and operation.

Avoid storing "what to do tomorrow" only at the bottom of a long device
research log. The central roadmap should be the first place to check.

## Important compatibility constraint

The current LXC updater and profile helper reference concrete repository paths.
A structural cleanup is therefore not a cosmetic rename operation. Treat it as
a deployment refactor and keep installation/update behavior working throughout.
