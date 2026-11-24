# Branch-Übersicht

Stand: 24.11.2026. Diese Übersicht ordnet alle Zweige des Repositorys ein.
**Es wurde kein Zweig gelöscht.** Veraltete Zweige bleiben als Archiv
erhalten; sie sind hier nur gekennzeichnet, damit klar ist, wo aktiv
gearbeitet wird.

## Aktive Zweige

| Zweig | Zweck |
| --- | --- |
| `main` | Freigegebener Produktivstand und empfohlener Update-Kanal (`COMMUNITY_SCRIPTS_REF=main`). |
| `optolink-research` | Reverse Engineering, Firmware, EEPROM, KM-Bus. Gehört nicht nach `main`. |
| `optolink-web` | Getrennt entwickelte Weboberfläche. |
| `feat/wb2a-vitotrol-rpm-20261010` | Draft-PR #52: Vitotrol-KM-Bus-Emulation und RPM-Beobachter (Research). |

## Historisch, vollständig in `main` enthalten

Diese Zweige enthalten keine Commits, die nicht schon in `main` sind.
Sie können als Referenz bleiben.

| Zweig | Bemerkung |
| --- | --- |
| `optolink-splitter-ha` | Ehemaliger Integrationszweig, letzter Stand PR #49 (10.10.2026). Bleibt für alte Installationen mit `COMMUNITY_SCRIPTS_REF=optolink-splitter-ha` erreichbar. Umstellung: `optolink-update-main-umstellen --freigeben`. |
| `backup/main-before-hybrid-release-20261010` | Sicherung von `main` vor dem Hybrid-Release. |
| `backup/optolink-splitter-ha-before-hybrid-20261010` | Sicherung des Integrationszweigs vor dem Hybrid-Release. |
| `feat/hybrid-production-de-docs-20261010` | Deutsche Hybrid-Dokumentation, gemergt. |
| `feat/wb2a-next-phase-20261010` | On-Demand-P300 (PR #51), gemergt. |

## Historisch, nicht gemergt (Archiv)

Diese Zweige enthalten Arbeit, die nicht in `main` übernommen wurde.
Sie sind auf veralteter Basis entstanden und sollten **nicht** direkt
gemergt werden. Benötigte Inhalte bei Bedarf gezielt übernehmen
(Cherry-Pick oder Neuimplementierung auf `main`).

### Hybrid- und P300-Entwicklung (Oktober 2026)

| Zweig | Bemerkung |
| --- | --- |
| `optolink-p300-migration` | Draft-PR #46: vollständige P300-Migration. Weitgehend durch den Hybridansatz in `main` ersetzt. |
| `optolink-handover-acceleration` | Vorarbeit für den beschleunigten VS1/P300-Wechsel; Ergebnis liegt in `tools/handover_acceleration/` auf `main`. |
| `feat/main-gwg-p300-vs1-dokumentation-20261013` | Quellzweig von PR #53; inhaltlich in `main` (Squash-Merge). |
| `fix/ha-mqtt-retained-states` | MQTT-Retain-Änderung, auf `main` bewusst zurückgenommen. |
| `research/v200kw2-protocol300` | P300-Nachweis an einer V200KW2. |

### Zeitprogramm-Dashboard (25.09.2026)

`feat/schedule-datetime-spinner-20260925`,
`feat/schedule-day-cards-20260925`,
`feat/schedule-day-editor-20260925`,
`feat/schedule-time-entities-20260925`,
`fix/schedule-browser-mod-sequence-20260925`,
`fix/schedule-day-card-clicks-20260925`,
`fix/schedule-day-card-yaml-20260925`,
`fix/poll-conversion-failsoft-20260925`

### Research- und Dokumentationsstände (24./25.09.2026)

Diese Zweige gehören thematisch nach `optolink-research`:

- GFA / Flamme / P80–P88:
  `fix/gfa-flame-ff-reentry-20260924`,
  `fix/gfa-flame-prod-vs1-settings-20260924`,
  `fix/gfa-flame-prod-vs1-settings-20260924-r2`,
  `fix/p80-fast-regression-20260924`,
  `research/gfa-flame-correlation-probe-20260924`,
  `research/gfa-p81-p83-live-20260924`,
  `research/gfa-p84-p88-static-result-20260924`,
  `docs/gfa-p81-p83-runbook-20260924`
- Codierstecker / Codierkarte:
  `research/coding-card-7656-layout-20260924`,
  `research/coding-date-separation-20260924`,
  `research/coding-summary-structure-20260924`,
  `research/gfa-coding-plug-live-20260924`,
  `research/gfa-coding-plug-live-20260924-r2`,
  `docs/coding-plug-date-correlation-20260924`,
  `docs/gfa-coding-plug-runbook-20260924`
- Pumpe:
  `research/flowcalibration-closure-20260924`,
  `research/internal-pump-k30-k31-20260924`,
  `research/internal-pump-live-20260924`,
  `docs/pump-current-conclusion-20260924`,
  `docs/pump-host-layer-closed-20260924`,
  `docs/pump-metadata-20260924`,
  `docs/pump-service-diagnostic-semantics-20260924`
- LON:
  `research/lon-closure-20260924`,
  `research/lon-input-classification-20260924`,
  `research/lon-manual-resolution-20260924`
- Firmware / Hardware / EEPROM:
  `docs/firmware-current-20260924`,
  `docs/eeprom-blocked-until-20260925`,
  `research/wb2a-gg1-hardware-architecture-20260924`,
  `research/new-readonly-results-20260924`
- Sammel- und Tagesstände:
  `docs/read-later-profile-audit-20260924`,
  `docs/research-consolidation-read-later-20260924`,
  `docs/research-refresh-20260924`,
  `docs/tomorrow-checkpoint-20260925`,
  `docs/tomorrow-checkpoint-20260925-r2`,
  `docs/tomorrow-checkpoint-20260925-r3`

## Regeln für neue Zweige

- Produktionsänderungen: kurzlebiger Zweig von `main`, PR gegen `main`.
- Research: von `optolink-research` abzweigen und dorthin zurückführen.
- Nach dem Merge bleibt der Zweig bestehen oder wird hier unter
  „Historisch“ eingetragen; Löschen nur nach ausdrücklicher Freigabe.
