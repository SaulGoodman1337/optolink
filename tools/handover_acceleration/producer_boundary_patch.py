"""Reproducibly patch COPIES of audited external writers for hybrid transactions.

This generator NEVER installs or executes a production program. Every
transaction method retains the exclusive cross-process writer lease across
read-before-write, write, readback and possible rollback. Unlike a frame-level
mutex, the lease is held while sleeps/waits are pending too.

All listed service source versions must be reviewed and deployed as a unit,
with producer_fence installed, before enabling recurring VS1/P300 handovers.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
from pathlib import Path


class ProducerPatchRejected(RuntimeError):
    pass


TARGETS = {
    "party": ("PartyEmulator", ("activate", "deactivate",
                                "recover_startup", "sync_emulated_controls")),
    "schedule": ("ScheduleManager", ("apply", "apply_editor")),
    "service-programs": ("ServiceProgramManager", ("apply_action",)),
    "clock-sync": ("ClockSync", ("synchronize",)),
    "maintenance": (None, ("_with_session",)),
}


def patch_producer(source: str, kind: str) -> str:
    if kind not in TARGETS or not isinstance(source, str):
        raise ProducerPatchRejected("exactly one known producer kind required")
    if "# HYBRID_PRODUCER_EPOCH_V1" in source:
        raise ProducerPatchRejected("source already instrumented")
    owner, methods = TARGETS[kind]
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        raise ProducerPatchRejected("producer Python source is not valid") from exc
    defs = [node for node in tree.body if isinstance(node, (ast.FunctionDef,
            ast.AsyncFunctionDef, ast.ClassDef))]
    if owner is None:
        hosts = [tree]
    else:
        hosts = [node for node in defs if isinstance(node, ast.ClassDef)
                 and node.name == owner]
    if len(hosts) != 1:
        raise ProducerPatchRejected("producer class or module count mismatch")
    host = hosts[0]
    declarations = [node.name for node in host.body
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))]
    for name in methods:
        if declarations.count(name) != 1:
            raise ProducerPatchRejected("producer transaction boundary missing: " + name)
    if any(isinstance(node, ast.AsyncFunctionDef) and node.name in methods
           for node in host.body):
        raise ProducerPatchRejected("async writers require separate lease review")
    # The invocation must be last, not at arbitrary module import time.
    main_checks = [node for node in tree.body if isinstance(node, ast.If)
                   and any(isinstance(n, ast.Name) and n.id == "__name__"
                           for n in ast.walk(node.test))]
    if not main_checks and kind == "maintenance":
        # Library module, imported by the API and CLI; instrumentation must
        # take effect during import, after the original function definition.
        index = len(source.splitlines(keepends=True))
    elif len(main_checks) == 1 and main_checks[0].end_lineno is not None:
        index = main_checks[0].lineno - 1
    else:
        raise ProducerPatchRejected("unexpected module entrypoint topology")

    prefix = (
        "\n# HYBRID_PRODUCER_EPOCH_V1 -- transaction-scoped, fail-closed\n"
        "from functools import wraps as _hybrid_wraps\n"
        "from handover_acceleration.producer_fence import writer_transaction as _hybrid_writer_transaction\n"
        "from handover_acceleration.producer_fence import mark_unverified_write as _hybrid_mark_unverified_write\n\n"
        "def _hybrid_protect_transaction(_method):\n"
        "    @_hybrid_wraps(_method)\n"
        "    def _guarded(*args, **kwargs):\n"
        f"        with _hybrid_writer_transaction({kind!r}):\n"
        "            _result = _method(*args, **kwargs)\n"
        "            if _result is False:\n"
        f"                _hybrid_mark_unverified_write({kind!r})\n"
        "            return _result\n"
        "    return _guarded\n\n"
    )
    prefix += "".join(
        f"{owner + '.' if owner else ''}{name} = "
        f"_hybrid_protect_transaction({owner + '.' if owner else ''}{name})\n"
        for name in methods
    ) + "\n"
    lines = source.splitlines(keepends=True)
    # Insert immediately BEFORE main instead of AFTER it, so a script executed
    # directly never starts handling MQTT before its transaction guard exists.
    # Do not place patches inside an indented class/function.
    candidate = "".join(lines[:index]) + prefix + "".join(lines[index:])
    try:
        compile(candidate, "<hybrid-producer-shadow>", "exec")
    except SyntaxError as exc:
        raise ProducerPatchRejected("patched producer does not compile") from exc
    return candidate


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kind", choices=tuple(TARGETS), required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--expected-sha256", help="optionally pin exact source bytes")
    args = parser.parse_args(argv)
    source = args.source.resolve()
    dest = args.output.resolve()
    if source == dest or args.source.is_symlink():
        raise ProducerPatchRejected("will not patch production source in place")
    raw = args.source.read_bytes()
    if args.expected_sha256 and hashlib.sha256(raw).hexdigest() != args.expected_sha256:
        raise ProducerPatchRejected("audited writer source hash changed")
    edited = patch_producer(raw.decode("utf-8"), args.kind)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(edited, encoding="utf-8")
    print("HYBRID_PRODUCER_SHADOW=PASS " + args.kind)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
