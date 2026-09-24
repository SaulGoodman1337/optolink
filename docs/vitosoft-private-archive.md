# Private Vitosoft collector source archive

Source repository: [SaulGoodman1337/Viessmann-Vitosoft-300-SID1](https://github.com/SaulGoodman1337/Viessmann-Vitosoft-300-SID1).

This is the private source companion to the existing [derived archive analysis](../config/optolink-splitter/research/vitosoft/private-archive-2026-09-23-analysis.md). Do not copy proprietary binaries, full decompilations, SQL contents, credentials or machine inventories into this public repository.

## Snapshot identity and verification

Snapshot: `vitosoft-private-archive-20260923-205048`.

SHA256: `50f8215ea74b1d507c78d28294814db1a5fc65683b3308f23057a2fce8bb4daa`.

The chat upload with `(1)` in its filename has the same bytes as the already analyzed snapshot. It is not a newer collector run. On 2026-09-24, complete extraction and independent checks again found:

- 15,351 regular files, 4,129,216,971 uncompressed bytes;
- all 15,350 final manifest entries hash-correct, no missing files;
- all 7,105 installation files matching the collector's source inventory;
- 144 SQL tables with 608,740 actual CSV rows, each matching the reported counts.

The original archive is 319,029,638 bytes. Matching counts and hashes do not establish exhaustive collection of every host directory or a transaction-consistent SQL backup.

## Publication boundary

**Initial status on 2026-09-24: documentation, selected small reports and tools are committed to the private repository; the complete 7z payload is not yet uploaded.** Do not mistake the source catalog for the actual source bytes.

The private repository includes `tools/Publish-VitosoftArchive.ps1` for a one-time authenticated upload of the existing archive as a private release asset. It checks repository privacy, size and hash, verifies a fresh asset download, and writes `catalog/import-receipt.json`. No new collector run is needed.

For later status, check that receipt and the actual asset under tag `collector-20260923-205048`. A release asset is separate from normal Git history and `git clone`. The text-only ChatGPT GitHub connection does not automatically make large binary assets readable; use appropriate authenticated local access or targeted text extracts with provenance.

## Entry points in the private repository

| Path | Purpose |
| --- | --- |
| `README.md` | Import status, source identity and entry points. |
| `AGENTS.md` | Evidence, privacy and cross-repository working rules. |
| `catalog/snapshot.json` | Machine-readable inventory and validation results. |
| `docs/COVERAGE-AND-GAPS.md` | Actual collection gaps versus reporting artifacts and analysis gaps. |
| `docs/OPTOLINK-INTEGRATION.md` | Exact archive paths for XML, SQL, IL and preserved binaries. |
| `docs/TODO.md` | Focused follow-up tasks without unnecessary full recollection. |
| `tools/verify_snapshot.py` | Reproducible read-only manifest, source-inventory and SQL row verification. |

## Conclusions that must not be reopened as missing collection

The SQL update tables were successfully exported and are empty, not missing. The 38 Strong Name failures are unsigned-assembly results, not 38 lost DLLs. Four protected FlowCalibration IL outputs represent two original binary versions, both preserved. Blank wrapper exit codes do not invalidate independently verified SQL or deep outputs.

Actual remaining boundaries include incomplete reflection/decompilation, no ILSpy fallback in this snapshot, missing per-key/per-directory negative status reports, no authenticated WB2A firmware image, and no physical coding-plug memory dumps. Existing resources that have not yet been understood are an analysis backlog, not automatically missing collection.

## Current appliance research stays here

Read [GFA quality-aware logger and FF checkpoint - 2026-09-24](gfa-quality-logger.md) before older GFA log-retrieval instructions. The requested FF raw contexts and existing JSONL were already supplied and analyzed. The new quality helper is offline-tested; its automatic re-entry after FF remains unvalidated on the appliance at that checkpoint. Do not request those same excerpts again or confuse this open hardware validation with collector completeness.

The private source archive does not supersede subsequent hardware observations. Preserve source path/hash, device and burner-variant applicability, and the distinction between metadata, host implementation, hardware observation and hypothesis. No production configuration or appliance state was changed by this archive documentation work.
