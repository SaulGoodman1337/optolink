"""Read-only analysis of an archived WB2A handover measurement.

No hardware connection, imports of pySerial, subprocess calls, systemd operations,
network requests, or modifications to the measured session. This module can
also simulate the existing *offline* fairness scheduler with synthetic work.

Measurements are HOST observations, not firmware or wire timestamps.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

try:
    from .scheduler import BoundedReadQueue, ReadKind
except ImportError:  # invoked as a standalone script from an isolated checkout
    from scheduler import BoundedReadQueue, ReadKind


class EvidenceError(ValueError):
    """The evidence is missing, inconsistent, or unsuitable for calculation."""


def _milliseconds(value, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (float, int)):
        raise EvidenceError(f"{label}: expected a numeric millisecond value")
    value = float(value)
    if not math.isfinite(value) or value < 0:
        raise EvidenceError(f"{label}: expected finite non-negative milliseconds")
    return value


def analyze_measurement(measurement: dict, *, service_runtime_ms: float | None = None,
                        p06_max_age_ms: float | None = None) -> dict:
    """Compute reproducible facts and *conditional* opportunity bounds.

    Reject malformed or incomplete trace material instead of turning it into
    a speed-up claim. The first/second ENQ values are relative to a single EOT;
    the cold setup is outside the reported VS1->P300->VS1 roundtrip.
    """
    if not isinstance(measurement, dict):
        raise EvidenceError("measurement must be a JSON object")
    phase = measurement.get("phases_ms")
    if not isinstance(phase, dict):
        raise EvidenceError("phases_ms missing")
    required = (
        "cold_setup", "vs1_to_p300_with_verified_identity",
        "p300_to_vs1_fast_with_verified_gfa",
        "remaining_gfa_block_p09_p87", "roundtrip_with_gfa",
    )
    times = {key: _milliseconds(phase.get(key), key) for key in required}
    roundtrip = times["roundtrip_with_gfa"]
    parts = (times["vs1_to_p300_with_verified_identity"] +
             times["p300_to_vs1_fast_with_verified_gfa"] +
             times["remaining_gfa_block_p09_p87"])
    if abs(parts - roundtrip) > 1.0:
        raise EvidenceError("phase durations do not sum to roundtrip")

    trace = measurement.get("enq_trace")
    if not isinstance(trace, list) or len(trace) != 3:
        raise EvidenceError("three distinct EOT/ENQ trace groups required")
    expected_names = ("cold_vs1_setup", "vs1_to_p300", "p300_to_vs1")
    observed = {}
    for row, name, count in zip(trace, expected_names, (2, 1, 1)):
        if not isinstance(row, dict) or row.get("name") != name:
            raise EvidenceError("incorrect EOT trace phase order/name")
        waits = row.get("enq_wait_ms")
        if not isinstance(waits, list) or len(waits) != count:
            raise EvidenceError(f"{name}: expected {count} individually observed ENQs")
        xs = [_milliseconds(x, name) for x in waits]
        if any(x <= 0 for x in xs) or any(a >= b for a, b in zip(xs, xs[1:])):
            raise EvidenceError("ENQ timestamps must be positive and strictly increasing")
        observed[name] = xs

    main_wait = observed["vs1_to_p300"][0]
    back_wait = observed["p300_to_vs1"][0]
    enq_total = main_wait + back_wait
    if enq_total > roundtrip + 1.0:
        raise EvidenceError("ENQ waits exceed complete roundtrip")

    cold_first, cold_second = observed["cold_vs1_setup"]
    result = {
        "scope": "archived controller/host exchange; zero new serial activity",
        "historical_measurement": {
            "experiment_pass": measurement.get("experiment_pass"),
            "vs1_link_restored": measurement.get("vs1_link_restored"),
            "errors": measurement.get("errors", []),
        },
        "measured_roundtrip_ms": round(roundtrip, 3),
        "measured_cold_setup_ms_outside_roundtrip": round(times["cold_setup"], 3),
        "main_enq_to_p300_ms": round(main_wait, 3),
        "main_enq_to_vs1_ms": round(back_wait, 3),
        "two_enq_waits_total_ms": round(enq_total, 3),
        "two_enq_fraction_percent": round(enq_total * 100 / roundtrip, 2),
        "non_enq_total_ms_including_controller_and_line": round(roundtrip - enq_total, 3),
        "cold_second_enq_additional_ms": round(cold_second - cold_first, 3),
        "absolute_host_only_savings_upper_bound_ms": round(roundtrip - enq_total, 3),
        "software_only_under_4s_by_same_handshake": bool(enq_total < 4000.0),
        "limits": [
            "ENQ durations are host-observed, not proven firmware delays.",
            "RX buffers may include multiple bytes recorded at a single host timestamp.",
            "Non-ENQ time includes real serial/controller work; it is NOT all removable host sleep.",
            "This single recorded run is not a statistical estimate of future switch speed.",
        ],
    }
    if service_runtime_ms is not None:
        service_runtime_ms = _milliseconds(service_runtime_ms, "service_runtime_ms")
        if service_runtime_ms + 1 < roundtrip + times["cold_setup"]:
            raise EvidenceError("service runtime shorter than known phases")
        result["supervisor_timeline_ms"] = {
            "reported_service_runtime_ms": round(service_runtime_ms, 3),
            "measured_roundtrip_ms": round(roundtrip, 3),
            "measured_pre_roundtrip_cold_setup_ms": round(times["cold_setup"], 3),
            "other_runtime_ms_not_attributed": round(
                max(0, service_runtime_ms - roundtrip - times["cold_setup"]), 3),
            "caution": "Runtime outside these phases may include service stop/start,"
                       " recovery, setup, logging, and overhead; not all is avoidable.",
        }
    if p06_max_age_ms is not None:
        freshness = _milliseconds(p06_max_age_ms, "p06_max_age_ms")
        result["p06_freshness_example"] = {
            "user_specified_max_age_ms": freshness,
            "observed_enq_only_roundtrip_ms": round(enq_total, 3),
            "compatible_with_observed_roundtrip": freshness >= enq_total,
            "caution": "P06 cannot be freshly read in verified VS1 while the port"
                       " is in P300. Do not substitute P09/RAM or stale P06.",
        }
    return result


def simulate_current_queue(vs1_reads: int, p300_reads: int, *, max_same_mode: int = 4) -> dict:
    """Count separate P300 episodes in the CURRENT simple fairness rule.

    Synthetic tasks are all instantly handled. This models mode order only,
    NOT correctness for outstanding real deadlines, writes, or GFA freshness.
    """
    for v, name in ((vs1_reads, "vs1_reads"), (p300_reads, "p300_reads"),
                    (max_same_mode, "max_same_mode")):
        if type(v) is not int or v < (1 if name == "max_same_mode" else 0):
            raise EvidenceError(f"invalid {name}")
    if vs1_reads + p300_reads > 10000:
        raise EvidenceError("synthetic queue too large")
    queue = BoundedReadQueue(capacity=max(1, vs1_reads+p300_reads),
                             max_same_mode=max_same_mode, clock=lambda: 0.0)
    for _ in range(vs1_reads):
        queue.submit(ReadKind.VS1_P06)
    for _ in range(p300_reads):
        queue.submit(ReadKind.P300_ID)
    mode = "vs1"
    transitions = 0
    p300_windows = 0
    plan = []
    while queue.pending_count():
        task = queue.take(preferred_mode=mode)
        if task is None:
            raise EvidenceError("queue has pending items but did not dispatch")
        if task.kind.mode != mode:
            transitions += 1
            if task.kind.mode == "p300":
                p300_windows += 1
            mode = task.kind.mode
        plan.append(mode)
        queue.finish(task, success=True)
    if mode != "vs1":
        transitions += 1  # conservative final restore to VS1
    return {
        "vs1_reads": vs1_reads,
        "p300_reads": p300_reads,
        "max_same_mode": max_same_mode,
        "mode_runs": _run_length_modes(plan),
        "p300_windows_current_fairness": p300_windows,
        "protocol_transitions_including_final_vs1": transitions,
        "minimum_p300_windows_if_independent_and_deadline_compatible": int(p300_reads > 0),
        "warning": "Grouping across the original request order requires explicit"
                   " independence, compatible deadlines and permission to let VS1"
                   " samples become stale; this does NOT authorize reordering.",
    }


def _run_length_modes(plan: list[str]) -> list[dict]:
    result = []
    for name in plan:
        if result and result[-1]["mode"] == name:
            result[-1]["reads"] += 1
        else:
            result.append({"mode": name, "reads": 1})
    return result


def batch_savings(measured_roundtrip_ms: float, enq_total_ms: float,
                  separate_windows: int, grouped_windows: int = 1) -> dict:
    """Conditional gross fixed-overhead savings, excluding additional reads.

    Assumes identical verification/GFA scope each time, and that independent
    P300 reads can safely share a single verified phase. No hardware timing
    gain from making an individual switch faster is claimed.
    """
    for n in (separate_windows, grouped_windows):
        if type(n) is not int or n < 1:
            raise EvidenceError("window counts must be positive integers")
    if grouped_windows > separate_windows:
        raise EvidenceError("cannot increase windows in a savings calculation")
    whole = _milliseconds(measured_roundtrip_ms, "measured_roundtrip_ms")
    enq = _milliseconds(enq_total_ms, "enq_total_ms")
    if enq > whole:
        raise EvidenceError("ENQ total exceeds roundtrip")
    saved = separate_windows - grouped_windows
    return {
        "original_windows": separate_windows,
        "grouped_windows": grouped_windows,
        "avoided_full_roundtrips": saved,
        "gross_avoided_enq_wait_ms": round(saved * enq, 3),
        "gross_avoided_identical_roundtrip_ms": round(saved * whole, 3),
        "condition": "Only if requests are independent, deadlines compatible,"
                     " one P300 phase remains verified, and VS1/P06 freshness"
                     " can safely be sacrificed for the batch. No payload read"
                     " time or startup/restore overhead included.",
    }


def _load_session(path: Path) -> tuple[dict, dict | None]:
    if not path.is_dir():
        raise EvidenceError("session path is not a directory")
    try:
        measurement = json.loads((path / "measurement.json").read_text(encoding="utf-8"))
        summary_path = path / "summary.json"
        summary = (json.loads(summary_path.read_text(encoding="utf-8"))
                   if summary_path.is_file() else None)
    except (OSError, ValueError) as exc:
        raise EvidenceError("session evidence missing or invalid") from exc
    return measurement, summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session", required=True, type=Path,
                        help="path containing the existing measurement.json; READ ONLY")
    parser.add_argument("--service-runtime-ms", type=float,
                        help="optional systemd runtime from earlier console, if known")
    parser.add_argument("--p06-max-age-ms", type=float,
                        help="optional hypothetical P06 freshness requirement")
    parser.add_argument("--vs1-reads", type=int, default=12,
                        help="synthetic queue workload, default 12")
    parser.add_argument("--p300-reads", type=int, default=12,
                        help="synthetic queue workload, default 12")
    parser.add_argument("--max-same-mode", type=int, default=4,
                        help="current simple fair scheduling bound, default 4")
    args = parser.parse_args(argv)
    try:
        measurement, summary = _load_session(args.session)
        result = analyze_measurement(measurement, service_runtime_ms=args.service_runtime_ms,
                                     p06_max_age_ms=args.p06_max_age_ms)
        if isinstance(summary, dict):
            result["original_saved_summary_result"] = summary.get("result")
            result["original_summary_must_not_be_rewritten"] = True
        simulation = simulate_current_queue(args.vs1_reads, args.p300_reads,
                                            max_same_mode=args.max_same_mode)
        result["synthetic_current_scheduler"] = simulation
        n = simulation["p300_windows_current_fairness"]
        if n > 0:
            result["conditional_batched_savings"] = batch_savings(
                result["measured_roundtrip_ms"], result["two_enq_waits_total_ms"], n)
        result["hypothetical_ten_independent_p300_reads"] = batch_savings(
            result["measured_roundtrip_ms"], result["two_enq_waits_total_ms"], 10)
    except EvidenceError as exc:
        parser.error(str(exc))
    print(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
