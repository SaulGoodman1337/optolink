# Optolink Research Archive

This branch is the **research and reverse-engineering workspace** for the Optolink project.

It preserves the complete pre-cleanup repository state so firmware, EEPROM, KBus, VitoTest, coding-plug, physical-memory and experimental controller work remains reproducible and does not contaminate the production deployment branch.

## Important

**Do not use this branch as the update source for the production Optolink-Splitter machine.**

The production runtime lives on:

```text
optolink-splitter-ha
```

The separate browser application lives on:

```text
optolink-web
```

This research branch intentionally contains experimental scripts, probes, captured evidence, historical documentation and code that may acquire the serial bus directly or exercise controller-specific operations.

## Preserved research areas

The archive includes, among other work:

- firmware readout and M16C/M306xx investigations;
- P300 EEPROM read mapping and address-space experiments;
- KBus/KMBus protocol and participant analysis;
- coding-plug dumps, correlations and reverse engineering;
- VitoTest historical artifacts and function classification;
- physical RAM/SFR/read-path probes;
- GFA and combustion diagnostics experiments;
- pump and hydraulic behavior investigations;
- Vitotrol emulation and protocol research;
- historical V-Comm/OpenV/Vitosoft source and provenance analysis;
- one-off loggers, diagnostic probes and supporting evidence.

Primary locations include:

```text
config/optolink-splitter/research/
research/
tools/
docs/
```

## Why this branch keeps the pre-cleanup snapshot

Research results frequently depend on the exact helper scripts, evidence files and documentation that existed when a test was performed. Deleting unrelated files from this branch would make older notes harder to reproduce and could break links between evidence and tooling.

For that reason this branch acts as an archival research baseline rather than a minimal deployable tree.

## Production boundary

Anything needed for day-to-day operation of the real splitter must be promoted deliberately to `optolink-splitter-ha` and must meet all of these conditions:

1. it is required for the functional splitter/Home Assistant deployment;
2. it does not depend on a one-off research probe;
3. it has bounded behavior and rollback/readback semantics where writes are involved;
4. it can pass static/syntax validation;
5. the production README and updater are updated accordingly.

Do not merge the whole research branch into the production branch.

## Firmware and EEPROM safety

Many tools in this branch were built to investigate undocumented controller behavior. Treat read/write addresses, physical-memory access and firmware-related commands as device-specific research material, not generic operational interfaces.

Before running an experimental tool:

- inspect its source and address range;
- verify whether it is read-only or can write;
- ensure the normal splitter does not simultaneously own an exclusive serial path when the tool requires direct access;
- preserve an exact baseline and a restoration procedure;
- prefer readback verification over transport return codes where the controller behavior has shown ambiguous acknowledgements.

## Branch relationship

- `main` — untouched pre-cleanup repository baseline;
- `optolink-research` — active research/archive branch;
- `optolink-splitter-ha` — minimal production splitter + Home Assistant branch;
- `optolink-web` — isolated web application branch.

Research can continue here without changing the production update surface.
