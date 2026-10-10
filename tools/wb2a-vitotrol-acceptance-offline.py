#!/usr/bin/env python3
"""Fail-closed, strictly SYNTHETIC WB2A Vitotrol acceptance scenario evaluator.

Offline fixture analysis ONLY. This program has no Optolink/MQTT/systemd,
serial or controller access, nor any way to authorize hardware use.
No firmware RX/commit/injection service has been proven for 20C2.
"""
from __future__ import annotations

from collections import Counter
import argparse
import json
from pathlib import Path
import re
import sys

SCHEMA = "wb2a-vitotrol-acceptance-offline-v1"
DEVICE = {"controller": "VDensHO1", "ident": "20C2", "software": "0103", "heating_circuit": 1}
MAX_EVENTS = 48
MAX_BYTES = 96_000
MAX_TOTAL_MS = 180_000
MAX_ACTIVE_MS = 90_000
MAX_AGE_MS = 5_000
MIN_ACTIVE_SPAN_MS = 30_000
MIN_POSTCHECK_MS = 30_000
MIN_TEMP_TARGETS = 2
MIN_CONFIRMATIONS_PER_TARGET = 2
# These are current research BLOCKERS, not controls that JSON can turn off.
UNPROVEN_HARDWARE_GATES = (
    "20c2_uart1_rx_parser_and_state_commit",
    "controlled_optolink_rx_injection_service",
    "atomic_write_ownership_and_commit_recovery",
    "independent_controller_coding_rollback_acceptance",
    "independent_current_alarm_and_history_live_monitoring",
    "supervised_test_window_without_rpm_recording_disruption",
)


class FixtureRejected(ValueError):
    pass


def _strict_object(pairs: list[tuple[str, object]]) -> dict:
    out = {}
    for k, v in pairs:
        if k in out:
            raise FixtureRejected("duplicate JSON field: " + k)
        out[k] = v
    return out


def parse_fixture(source: bytes) -> dict:
    if type(source) is not bytes or not 2 <= len(source) <= MAX_BYTES:
        raise FixtureRejected("finite synthetic JSON fixture bytes required")
    try:
        fixture = json.loads(source.decode("utf-8"), object_pairs_hook=_strict_object,
                             parse_constant=lambda val: (_ for _ in ()).throw(
                                 FixtureRejected("non-finite JSON constant: " + val)))
    except (UnicodeError, json.JSONDecodeError) as e:
        raise FixtureRejected("malformed synthetic fixture JSON") from e
    if type(fixture) is not dict or set(fixture) != {"schema", "mode", "device", "events"}:
        raise FixtureRejected("exact offline fixture structure required")
    if fixture["schema"] != SCHEMA or fixture["mode"] != "synthetic_offline":
        raise FixtureRejected("only explicitly synthetic offline scenarios accepted")
    if (type(fixture["device"]) is not dict or fixture["device"] != DEVICE
            or type(fixture["device"].get("heating_circuit")) is not int):
        raise FixtureRejected("only exact VDensHO1/20C2/0103 HK1 fixture accepted")
    events = fixture["events"]
    if type(events) is not list or not 1 <= len(events) <= MAX_EVENTS:
        raise FixtureRejected("bounded event list required")
    for i, row in enumerate(events):
        _validate_event(row, i)
    times = [r["t_ms"] for r in events]
    if times[0] != 0 or any(y <= x for x, y in zip(times, times[1:])):
        raise FixtureRejected("strictly increasing time from zero required")
    if times[-1] > MAX_TOTAL_MS:
        raise FixtureRejected("simulated test outside bounded duration")
    return fixture


_KEYS = {
    "t_ms", "phase", "a0_27a0", "remote_index_0a5c", "room_0896",
    "sensor_089c", "expected_room_tenths_c", "bc_active", "bc_history_count",
    "fault_history_fingerprint", "other_alarm_active", "vs1_verified",
    "readback_age_ms", "room_influence_enabled", "forced_burner_or_pump",
}


def _hex(value: object, n_bytes: int, name: str) -> None:
    if type(value) is not str or not re.fullmatch(r"[0-9a-f]{"+str(n_bytes*2)+r"}", value):
        raise FixtureRejected(name + " requires exact lowercase " + str(n_bytes) + " byte hex")


def _validate_event(r: object, i: int) -> None:
    if type(r) is not dict or set(r) != _KEYS:
        raise FixtureRejected(f"event {i} must contain exact readback-only fields")
    if type(r["t_ms"]) is not int or not 0 <= r["t_ms"] <= MAX_TOTAL_MS:
        raise FixtureRejected("event timestamp invalid")
    if r["phase"] not in ("baseline", "armed", "active", "restored", "postcheck"):
        raise FixtureRejected("unsupported acceptance phase")
    for name, count in (("a0_27a0", 1), ("remote_index_0a5c", 4),
                        ("room_0896", 2), ("sensor_089c", 1),
                        ("fault_history_fingerprint", 32)):
        _hex(r[name], count, name)
    for name in ("bc_active", "other_alarm_active", "vs1_verified",
                 "room_influence_enabled", "forced_burner_or_pump"):
        if type(r[name]) is not bool:
            raise FixtureRejected("boolean required: " + name)
    if type(r["bc_history_count"]) is not int or r["bc_history_count"] < 0:
        raise FixtureRejected("nonnegative historical BC count required")
    age = r["readback_age_ms"]
    if type(age) is not int or not 0 <= age <= MAX_AGE_MS:
        raise FixtureRejected("readback too stale/unverifiable")
    temp = int.from_bytes(bytes.fromhex(r["room_0896"]), "little")
    if not 50 <= temp <= 350:
        raise FixtureRejected("implausible room-temperature register readback")
    target = r["expected_room_tenths_c"]
    if r["phase"] == "active":
        if type(target) is not int or not 50 <= target <= 350:
            raise FixtureRejected("active phase requires precise synthetic temperature target")
    elif target is not None:
        raise FixtureRejected("targets permitted only in active phase")


def _code_summary(reasons: list[str], events: list[dict]) -> dict:
    # Hardware gate is *not* configurable by the fixture. In particular a
    # forged positive acceptance trace cannot turn simulated PASS into GO.
    return {
        "mode": "SYNTHETIC_OFFLINE_ONLY",
        "device": DEVICE,
        "evaluated_samples": len(events),
        "scenario_verdict": "OFFLINE_SCENARIO_PASS" if not reasons else "OFFLINE_SCENARIO_FAIL",
        "scenario_reasons": reasons,
        "live_hardware_authorized": False,
        "optolink_rx_injection_implemented": False,
        "missing_hardware_proofs": list(UNPROVEN_HARDWARE_GATES),
        "tested_controller": False,
        "rpm_observer_modified": False,
        "unsafe_controller_writes_available": False,
        "interpretation": "Offline plausibility only; never proof that a Vitotrol was accepted",
    }


def evaluate(fixture: dict) -> dict:
    """Evaluate prevalidated synthetic snapshots; no physical action."""
    if type(fixture) is not dict:
        raise FixtureRejected("validated synthetic fixture required")
    # Revalidate even if the caller bypassed the JSON loader.
    fixture = parse_fixture(json.dumps(fixture,allow_nan=False).encode("utf-8"))
    samples = fixture["events"]
    reasons = []

    def fail(reason: str) -> None:
        if reason not in reasons:
            reasons.append(reason)

    phases = [r["phase"] for r in samples]
    if phases[0] != "baseline":
        fail("BASELINE_NOT_FIRST")
    if phases.count("baseline") != 1 or phases.count("armed") != 1:
        fail("BASELINE_ARMED_CARDINALITY")
    if phases.count("restored") != 1 or phases.count("postcheck") < 2:
        fail("ROLLBACK_OR_POSTCHECK_MISSING")
    if phases.count("active") < 4:
        fail("INSUFFICIENT_ACTIVE_SAMPLES")
    legal = ["baseline", "armed", "active", "restored", "postcheck"]
    ranks = [legal.index(p) for p in phases]
    if ranks != sorted(ranks) or set(phases) != set(legal):
        fail("INVALID_PHASE_ORDER")
    base = samples[0]
    if base["a0_27a0"] != "00" or base["remote_index_0a5c"] != "00000000":
        fail("BASELINE_NOT_REMOTE_FREE")
    if base["bc_active"] or base["other_alarm_active"]:
        fail("BASELINE_ALARM_PRESENT")
    baseline_fault = base["fault_history_fingerprint"]
    baseline_count = base["bc_history_count"]
    base_registers = {k:base[k] for k in ("a0_27a0", "remote_index_0a5c", "room_0896", "sensor_089c")}
    for row in samples:
        if not row["vs1_verified"]:
            fail("VS1_ORIGINAL_READBACK_UNVERIFIED")
        if row["room_influence_enabled"]:
            fail("ROOM_INFLUENCE_MUST_STAY_DISABLED")
        if row["forced_burner_or_pump"]:
            fail("FORCED_BURNER_OR_PUMP_UNACCEPTABLE")
        if row["bc_active"]:
            fail("CURRENT_BC_FAULT_OBSERVED")
        if row["other_alarm_active"]:
            fail("OTHER_CONTROLLER_ALARM_OBSERVED")
        if row["bc_history_count"] != baseline_count or row["fault_history_fingerprint"] != baseline_fault:
            fail("FAULT_HISTORY_CHANGED_DURING_TEST")
        if row["phase"] in ("baseline", "armed", "restored", "postcheck"):
            if any(row[k] != baseline for k,baseline in base_registers.items()):
                fail("ORIGINAL_CONFIG_READBACK_NOT_RESTORED")

    active = [s for s in samples if s["phase"]=="active"]
    if active:
        if active[-1]["t_ms"]-active[0]["t_ms"] < MIN_ACTIVE_SPAN_MS:
            fail("INSUFFICIENT_REMOTE_ALIVE_OBSERVATION")
        if active[-1]["t_ms"]-active[0]["t_ms"] > MAX_ACTIVE_MS:
            fail("ACTIVE_WINDOW_EXCEEDED")
        counts=Counter(s["expected_room_tenths_c"] for s in active)
        # Two genuinely different, nonfallback targets with repeated readbacks
        # make a fixed 20.0 deg C placeholder impossible to mistake for proof.
        distinct = [v for v,n in counts.items()
                    if n >= MIN_CONFIRMATIONS_PER_TARGET
                    and abs(v-int.from_bytes(bytes.fromhex(base["room_0896"]),"little")) >= 5]
        if len(distinct) < MIN_TEMP_TARGETS:
            fail("INSUFFICIENT_DISTINCT_REMOTE_TEMPERATURE_CHALLENGES")
        for row in active:
            if row["a0_27a0"] != "01":
                fail("REMOTE_EXPECTATION_NOT_SET_IN_SYNTHETIC_ACTIVE_PHASE")
            if row["remote_index_0a5c"] == "00000000":
                fail("NO_CONTROLLER_REMOTE_SOFTWARE_INDEX")
            if row["remote_index_0a5c"] == base["remote_index_0a5c"]:
                fail("REMOTE_SOFTWARE_INDEX_UNCHANGED")
            if row["sensor_089c"] == base["sensor_089c"]:
                fail("SENSOR_STATUS_DID_NOT_CHANGE_FROM_BASELINE")
            if int.from_bytes(bytes.fromhex(row["room_0896"]),"little") != row["expected_room_tenths_c"]:
                fail("ROOM_TEMPERATURE_READBACK_MISMATCH")
        if len({s["remote_index_0a5c"] for s in active})!=1:
            fail("REMOTE_SOFTWARE_IDENTITY_NOT_STABLE")

    restored = next((s for s in samples if s["phase"]=="restored"),None)
    postchecks = [s for s in samples if s["phase"]=="postcheck"]
    if restored and postchecks:
        if postchecks[-1]["t_ms"]-restored["t_ms"] < MIN_POSTCHECK_MS:
            fail("POST_ROLLBACK_STABILITY_OBSERVATION_TOO_SHORT")
        if postchecks[0]["t_ms"] <= restored["t_ms"]:
            fail("POSTCHECK_BEFORE_RESTORATION")
    return _code_summary(reasons,samples)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("fixture",type=Path, help="strictly synthetic JSON evidence, no live controller I/O")
    args = p.parse_args()
    try:
        if args.fixture.stat().st_size > MAX_BYTES:
            p.error("offline fixture exceeds bounded size")
        result=evaluate(parse_fixture(args.fixture.read_bytes()))
    except (FixtureRejected, OSError) as exc:
        p.error("offline fixture rejected: " + str(exc))
    print(json.dumps(result,indent=2,sort_keys=True))
    if result["scenario_verdict"] != "OFFLINE_SCENARIO_PASS":
        # A failed simulation is a genuine nonzero test-runner result; a
        # passed simulation STILL NEVER authorizes a real controller test.
        sys.exit(2)


if __name__=="__main__":
    main()
