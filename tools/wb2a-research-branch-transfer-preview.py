#!/usr/bin/env python3
"""Read-only transfer PREVIEW for GWG/20-bit ROM research into optolink-research.

The current feature branch is NOT a substitute for the independent long-lived
optolink-research branch. Its history includes production-feature changes.
This audit selects GWG/ROM-focused files only, identifies two-sided divergence,
and never modifies refs, stages files, creates commits or writes the target.

The explicit omission of docs/README.md is deliberate: research has an
independent index, which must be updated with a separate reviewed change.
"""
from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
from pathlib import Path
import subprocess
import sys

PREFIXES = (
    "docs/wb2a-gwg-*",
    "docs/wb2a-c5-f9-fault-incident-*",
    "docs/wb2a-v200kw2-*gwg*",
    "docs/wb2a-vitotrol-200kw2-gwg*",
    "docs/wb2a-gg1-bootloader-gwg*",
    "docs/wb2a-optolink-rom*",
    "docs/wb2a-optolinklogger-*",
    "docs/wb2a-vitosoft-oem-*",
    "docs/wb2a-optolink-only-rom*",
    "docs/wb2a-vitotrol-rom*",
    "tools/wb2a-gwg-*",
    "tools/wb2a-c5-f9-incident-audit-offline.py",
    "tools/wb2a-experiment-fault-gate.py",
    "tools/wb2a-experiment-with-fault-gate.sh",
    "tools/wb2a-v200kw2-gwg*",
    "tools/wb2a-m16c-boot*",
    "tools/wb2a-optolink-rom*",
    "tools/wb2a-optolinklogger-*",
    "tools/wb2a-vitosoft-oem-*",
    "tools/wb2a-vitotrol-rom*",
    "tools/wb2a-research-branch-transfer-preview.py",
    "tools/optolinkgwg.py",
    "tools/optolink-apply-gwg-readonly-patch.py",
    "tests/test_gwg_*",
    "tests/test_optolinkgwg.py",
    "tests/test_wb2a_gwg*",
    "tests/test_wb2a_c5_f9_incident_audit_offline.py",
    "tests/test_wb2a_experiment_fault_gate.py",
    "tests/test_wb2a_experiment_fault_wrapper_offline.py",
    "tests/test_wb2a_m16c*",
    "tests/test_wb2a_optolink_rom*",
    "tests/test_wb2a_optolinklogger_*",
    "tests/test_wb2a_vitosoft_oem_*",
    "tests/test_wb2a_vitotrol_rom*",
    "tests/test_wb2a_research_branch_transfer_preview.py",
)
OMIT = ("docs/README.md", "README.md", "install/", "config/", "apps/", "ct/")
MAX_CANDIDATE_SIZE = 500_000


class UnsafePreview(ValueError):
    pass


def git(repo: Path, *args: str, allow_not_found: bool = False) -> bytes | None:
    cmd = ["git", "-C", str(repo), *args]
    p = subprocess.run(cmd, capture_output=True, timeout=15)
    if p.returncode:
        if allow_not_found and p.returncode == 128:
            return None
        raise UnsafePreview("git read-only failure: " + repr(args) + ": " +
                            p.stderr.decode(errors="replace")[:350])
    return p.stdout


def list_tree(repo: Path, ref: str) -> dict[str, tuple[str, str]]:
    raw = git(repo, "ls-tree", "-r", "-z", ref)
    found = {}
    for item in raw.split(b"\0"):
        if not item:
            continue
        header, name = item.split(b"\t", 1)
        mode, kind, sha = header.decode().split()
        found[name.decode()] = mode, sha
    return found


def blob_sha256(repo: Path, ref: str, path: str, tree: dict) -> tuple[str, int]:
    mode, sha = tree[path]
    if mode not in ("100644", "100755"):
        raise UnsafePreview("symlink/submodule/unknown mode forbidden: " + path)
    content = git(repo, "show", f"{ref}:{path}")
    if content is None or len(content) > MAX_CANDIDATE_SIZE:
        raise UnsafePreview("missing or oversize artifact: " + path)
    return hashlib.sha256(content).hexdigest(), len(content)


def preview(repo: Path, source: str, target: str) -> dict:
    if not (repo / ".git").exists():
        # Worktrees have a .git file; existence suffices.
        raise UnsafePreview("expected git worktree")
    for name in (source, target):
        if not name or any(x in name for x in ("\n", "\r", "\x00", "--")):
            raise UnsafePreview("unsafe branch ref")
        git(repo, "rev-parse", "--verify", name + "^{commit}")
    base = git(repo, "merge-base", source, target).decode().strip()
    s_head = git(repo, "rev-parse", source).decode().strip()
    t_head = git(repo, "rev-parse", target).decode().strip()
    divergence = git(repo, "rev-list", "--left-right", "--count",
                     f"{target}...{source}").decode().strip().split()
    src, dst, common = (list_tree(repo, r) for r in (source, target, base))
    chosen = sorted(p for p in src
                    if any(fnmatch.fnmatchcase(p, rule) for rule in PREFIXES))
    if not chosen:
        raise UnsafePreview("no GWG/ROM research artifacts found at source")
    artifacts = []
    for path in chosen:
        if path in OMIT or any(path.startswith(x) for x in OMIT if x.endswith("/")):
            raise UnsafePreview("production or index file accidentally selected")
        s_hash, s_size = blob_sha256(repo, source, path, src)
        if path not in dst:
            decision = "NEW_IN_RESEARCH"
            other = None
        else:
            t_hash, _ = blob_sha256(repo, target, path, dst)
            other = t_hash
            if t_hash == s_hash:
                decision = "IDENTICAL"
            else:
                s_base = common.get(path)
                t_changed = s_base is None or s_base != dst[path]
                s_changed = s_base is None or s_base != src[path]
                if s_changed and t_changed:
                    decision = "CONFLICT_BOTH_SIDES_CHANGED"
                else:
                    decision = "REVIEW_REPLACEMENT"
        artifacts.append({
            "path": path, "source_sha256": s_hash,
            "target_sha256": other, "size_bytes": s_size,
            "decision": decision,
        })
    categories = {item["decision"] for item in artifacts}
    return {
        "kind": "READ_ONLY_BRANCH_IMPORT_PLAN_NOT_A_MERGE",
        "feature_branch": source, "research_branch": target,
        "source_head": s_head, "target_head": t_head,
        "common_ancestor": base,
        "target_only_commits": int(divergence[0]),
        "source_only_commits": int(divergence[1]),
        "candidate_file_count": len(artifacts),
        "new_files": sum(x["decision"] == "NEW_IN_RESEARCH" for x in artifacts),
        "identical": sum(x["decision"] == "IDENTICAL" for x in artifacts),
        "review_replacements": sum(x["decision"] == "REVIEW_REPLACEMENT" for x in artifacts),
        "conflicts": sum(x["decision"] == "CONFLICT_BOTH_SIDES_CHANGED" for x in artifacts),
        "guard": "NO_DIRECT_MERGE_OR_CHERRYPICK_OF_FEATURE_HISTORY",
        "docs_index_requires_manual_review": "docs/README.md",
        "merge_performed": False, "branch_modified": False,
        "files": artifacts,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--source", default="HEAD")
    parser.add_argument("--target", default="origin/optolink-research")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    report = preview(args.repo.resolve(), args.source, args.target)
    text = json.dumps(report, sort_keys=True, indent=2) + "\n"
    if args.out:
        args.out.write_text(text, encoding="utf-8")
    print(text, end="")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (UnsafePreview, OSError, subprocess.TimeoutExpired) as exc:
        print("PREVIEW_REJECTED:", exc, file=sys.stderr)
        sys.exit(2)
