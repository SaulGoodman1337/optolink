#!/usr/bin/env python3
"""WB2A 20C2 read-only FULL physical-RAM capture bracketed by real VS1 GFA P06.

Never interpret P09 or native 55D3 bytes as an RPM source. A 20 KiB sweep is
time-ordered, NOT an atomic memory image. Production ownership is restored by
systemd ExecStopPost, even after worker failure.
"""
from __future__ import annotations

import argparse
from collections import Counter
import datetime as dt
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import signal
import stat
import subprocess
import sys
import tarfile
import tempfile
import time

VERSION = "1.0.0-fullram-p06-bracket"
PROJECT = Path("/root/p300-trial-work/project")
ROOT = Path("/root/p300-trial-work/p300-fullram-results")
BUNDLES = Path("/root/p300-trial-work/research-bundles")
UNIT = "optolink-p300-fullram-logger.service"
PYTHON = "/opt/optolink/venv/bin/python"
DEEP_NAME = "wb2a-p300-deep-logger.py"
BASE_NAME = "wb2a-uart1-overnight.py"
HELPER_NAME = "wb2a-handover-probe.py"
RAM_START, RAM_STOP, BLOCK_SIZE = 0x0400, 0x5400, 32
BLOCK_COUNT = (RAM_STOP - RAM_START) // BLOCK_SIZE
STATUS_SPEC = (1, 0x55D3, 11)
CHECKPOINT_BLOCKS = 32
DEFAULT_HOURS, MAX_HOURS = 4, 8
REFERENCE_SECONDS = 6.0
PROGRESS_SECONDS = 20.0
MIN_FREE_BYTES = 384 * 1024 * 1024
MAX_SESSION_BYTES = 256 * 1024 * 1024
MAX_LOG_BYTES = 128 * 1024 * 1024
PREFLIGHT_BYTES = MIN_FREE_BYTES + 2 * MAX_SESSION_BYTES
# Conservative planning at 90 s/scan, 640 records and status/trace overhead.
PLAN_SECONDS_PER_SCAN = 90
ESTIMATED_BYTES_PER_SCAN = 1024 * 1024

def utc():
    return dt.datetime.now(dt.timezone.utc).isoformat()

def sha256(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def addresses(descending=False):
    seq = range(BLOCK_COUNT - 1, -1, -1) if descending else range(BLOCK_COUNT)
    return tuple(RAM_START + index * BLOCK_SIZE for index in seq)

def request_frame(fc, addr, length):
    if (fc, addr, length) != STATUS_SPEC and not (
        type(fc) is int and fc == 3 and type(addr) is int and
        type(length) is int and length == BLOCK_SIZE and
        RAM_START <= addr <= RAM_STOP - BLOCK_SIZE and
        (addr - RAM_START) % BLOCK_SIZE == 0
    ):
        raise ValueError("FULLRAM_UNREVIEWED_READ")
    body = bytes((5, 0, fc, addr >> 8, addr & 255, length))
    return b"\x41" + body + bytes((sum(body) & 255,))

def load_deep(directory):
    source = Path(directory) / ("deep.py" if (Path(directory) / "deep.py").is_file() else DEEP_NAME)
    if not source.is_file() or source.is_symlink():
        raise RuntimeError("PINNED_DEEP_MISSING")
    spec = importlib.util.spec_from_file_location("p300_fullram_pinned_deep", source)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

# Import is inert: the pinned transport/helper opens no port and controls no service.
DEEP = load_deep(Path(__file__).resolve().parent)

class PacketError(RuntimeError):
    def __init__(self, reason, *, received=b"", tx_utc=None, tx_monotonic=None):
        super().__init__(reason)
        self.received = bytes(received)
        self.tx_utc = tx_utc
        self.tx_monotonic = tx_monotonic

class FullRamWire(DEEP.DeepWire):
    """Reuse the proven two-ENQ VS1 and identified P300 handover, not the 8-block set."""

    @staticmethod
    def permitted(phase, raw, base):
        if phase != "p300":
            return DEEP.DeepWire.permitted(phase, raw, base)
        if raw == b"\x06":
            return True  # P300 response acknowledgment, not a controller write.
        if len(raw) != 8:
            return False
        try:
            return raw == request_frame(raw[3], (raw[4] << 8) | raw[5], raw[6])
        except ValueError:
            return False

    def packet(self, spec):
        fc, addr, length = spec
        request = request_frame(fc, addr, length)
        if self.phase != "p300":
            raise RuntimeError("P300_PACKET_OUTSIDE_P300")
        received = bytearray()
        sent_at_utc = None
        sent_at_mono = None
        try:
            self.w.gap()
            sent_at_mono = self.w.clock()
            sent_at_utc = utc()
            self.send(request)
            deadline = self.w.clock() + 3.0

            def take(n):
                data = self.w.exact(n, deadline)
                received.extend(data)
                return data

            if take(1) != b"\x06":
                raise RuntimeError("P300_INITIAL_ACK_INVALID")
            ack_count = 1
            for _ in range(8):
                first = take(1)
                if first != b"\x06":
                    break
                ack_count += 1
            else:
                raise RuntimeError("P300_TOO_MANY_ACK")
            if first != b"\x41":
                raise RuntimeError("P300_STX_INVALID")
            size = take(1)[0]
            if not 5 <= size <= 37:
                raise RuntimeError("P300_SIZE_OUT_OF_BOUNDS")
            response_body = take(size + 1)
            if ((size + sum(response_body[:-1])) & 255) != response_body[-1]:
                raise RuntimeError("P300_CHECKSUM_MISMATCH")
            msg, observed_fc, hi, lo, observed_len = response_body[:5]
            data = response_body[5:-1]
            if msg != 1:
                raise RuntimeError("P300_ERROR_OR_UNEXPECTED_MESSAGE_" + f"{msg:02x}")
            if (observed_fc, (hi << 8) | lo, observed_len) != spec:
                raise RuntimeError("P300_FUNCTION_ADDRESS_LENGTH_MISMATCH")
            if size != 5 + length or len(data) != length:
                raise RuntimeError("P300_PAYLOAD_SIZE_MISMATCH")
            self.send(b"\x06")
            self.w.quiet()
            end = self.w.clock()
            return {
                "fc": fc, "address": f"0x{addr:04x}", "length": length,
                "request_hex": request.hex(), "response_hex": received.hex(),
                "ack_count": ack_count, "host_ack_hex": "06",
                "response_message": msg, "response_fc": observed_fc,
                "response_address": f"0x{((hi << 8) | lo):04x}",
                "response_length": observed_len,
                "checksum_valid": True, "payload_hex": data.hex(), "data": data,
                "tx_utc": sent_at_utc, "rx_utc": utc(),
                "tx_monotonic": sent_at_mono, "rx_monotonic": end,
                "duration_ms": round((end - sent_at_mono) * 1000, 3),
                "retry_count": 0, "result": "OK",
            }
        except BaseException as exc:
            raise PacketError(str(exc), received=received, tx_utc=sent_at_utc,
                              tx_monotonic=sent_at_mono) from exc

def write_jsonl(stream, row):
    stream.write(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n")

def sync_stream(stream):
    stream.flush()
    os.fsync(stream.fileno())

def storage_guard(session, streams=()):
    if shutil.disk_usage(session).free < MIN_FREE_BYTES:
        raise RuntimeError("FULLRAM_LOW_DISK_RESERVE")
    total = 0
    for p in session.rglob("*"):
        if p.is_symlink():
            raise RuntimeError("FULLRAM_UNEXPECTED_SYMLINK")
        if p.is_file():
            total += p.stat().st_size
    if total > MAX_SESSION_BYTES:
        raise RuntimeError("FULLRAM_SESSION_SIZE_LIMIT")
    for stream in streams:
        if stream and not stream.closed and stream.tell() > MAX_LOG_BYTES:
            raise RuntimeError("FULLRAM_SINGLE_LOG_SIZE_LIMIT")

def reference(wire, stream, snap_id, side, stop=None, seconds=REFERENCE_SECONDS):
    """Six or more seconds of *actual* VS1 P06; sequential, never simultaneous."""
    start = time.monotonic()
    result = {"snapshot_id": snap_id, "side": side, "begin_utc": utc(),
              "begin_monotonic": start, "reads": 0, "p06": [],
              "p09": [], "p87": [], "p80": [], "p10": [], "p84": []}
    def take(key):
        sample = wire.vs1_read(key)  # SIGTERM cannot abort this transaction.
        write_jsonl(stream, {"snapshot_id": snap_id, "side": side,
                             "round": rounds, **sample})
        result[key.lower()].append(sample)
        result["reads"] += 1

    rounds = 0
    take("P80")
    take("P10")
    take("P84")
    while (time.monotonic() - start < seconds or rounds < 6):
        if stop is not None and stop.signum is not None:
            break
        rounds += 1
        for key in ("P06", "P09", "P87", "P06"):
            take(key)
        if stop is None or stop.signum is None:
            time.sleep(.15)
    # Confirm GFA identity again, even when an operator requested a stop.
    take("P80")
    end = time.monotonic()
    p06 = result["p06"]
    raw = {s["hex"] for s in p06 if s["valid"]}
    invalid = sum(not s["valid"] for s in p06)
    result.update(end_utc=utc(), end_monotonic=end, duration_s=round(end-start, 3),
                  rounds=rounds, p06_valid=len(p06)-invalid, p06_invalid_ff=invalid,
                  p06_raw_unique=sorted(raw), p06_rpm_unique=sorted(
                      {s["rpm"] for s in p06 if s["valid"]}),
                  stable=(rounds >= 6 and end-start >= seconds and invalid == 0
                          and len(raw) == 1 and len(p06) >= 12),
                  identity_verified=all(v["hex"] == "20" for v in result["p80"]))
    # JSON summary deliberately excludes read objects here; complete raw entries
    # are retained in vs1.jsonl with their own timestamps.
    return {k: v for k, v in result.items()
            if k not in {"p06", "p09", "p87", "p80", "p10", "p84"}}

def classify(pre, post, statuses):
    if not pre or not post or not pre.get("identity_verified") or not post.get("identity_verified"):
        return "TRANSITION_OR_UNKNOWN"
    if not pre["stable"] or not post["stable"]:
        return "TRANSITION_OR_UNKNOWN"
    if pre["p06_raw_unique"] != post["p06_raw_unique"]:
        return "TRANSITION_OR_UNKNOWN"
    if statuses and len({s["flame"] for s in statuses}) > 1:
        return "TRANSITION_OR_UNKNOWN"
    return ("STABLE_BRACKET_OFF" if pre["p06_raw_unique"] == ["00"]
            else "STABLE_BRACKET_RUNNING")

def emit_packet(packet, snapshot_id, ordinal=None):
    return {k: v for k, v in packet.items() if k != "data"} | {
        "snapshot_id": snapshot_id, "scan_ordinal": ordinal,
        "retry_count": 0}

def read_status(wire, stream, snap_id, after_blocks):
    pkt = wire.packet(STATUS_SPEC)
    data = pkt["data"]
    item = emit_packet(pkt, snap_id)
    item.update(after_blocks=after_blocks, flame=bool(data[5] & 0x20),
                lockout=bool(data[5] & 0x40),
                byte0_diagnostic=data[0], byte7_diagnostic=data[7],
                byte9_diagnostic=data[9], rpm_alias_verified=False)
    write_jsonl(stream, item)
    return item

def restore_canonical(partial, output, descending):
    """Full output is always ordered by rising physical address."""
    if not descending:
        os.replace(partial, output)
    else:
        with partial.open("rb") as src, output.open("xb") as dst:
            for index in range(BLOCK_COUNT):
                src.seek((BLOCK_COUNT - 1 - index) * BLOCK_SIZE)
                data = src.read(BLOCK_SIZE)
                if len(data) != BLOCK_SIZE:
                    raise RuntimeError("REVERSE_CANONICALIZATION_SHORT_READ")
                dst.write(data)
            sync_stream(dst)
        partial.unlink()
    if output.stat().st_size != RAM_STOP - RAM_START:
        raise RuntimeError("FULLRAM_BINARY_LENGTH_INVALID")
    return sha256(output)

def switch(wire, stream, reason, to_p300):
    before = wire.phase
    started = time.monotonic()
    row = {"from": before, "to": "p300" if to_p300 else "vs1",
           "reason": reason, "start_utc": utc(), "start_monotonic": started,
           "identity_verified": False, "result": "ERROR"}
    try:
        if to_p300:
            wire.identify_p300()
        else:
            wire.set_phase("recovery")
            wire.identify_vs1()
            wire.set_phase("vs1")
        row["identity_verified"] = True
        row["result"] = "OK"
    except BaseException as exc:
        row["error"] = str(exc)
        raise
    finally:
        row["end_utc"] = utc()
        row["end_monotonic"] = time.monotonic()
        row["duration_s"] = round(row["end_monotonic"] - started, 3)
        write_jsonl(stream, row)
        sync_stream(stream)

def capture_snapshot(session, wire, streams, ident, descending, deadline, stop, checkpoint):
    name = f"s{ident:05d}"
    partial = session / "snapshots" / (name + ".partial.bin")
    complete_file = session / "snapshots" / (name + ".bin")
    meta = {"snapshot_id": ident, "version": VERSION, "device_id": "20c2",
            "software": "0103", "gfa_p80": "20", "range_start": "0x0400",
            "range_last_inclusive": "0x53ff", "bytes_expected": 20480,
            "blocks_expected": BLOCK_COUNT, "block_size": BLOCK_SIZE,
            "direction": "descending" if descending else "ascending",
            "atomic_ram_image": False, "complete": False, "marker": "PARTIAL",
            "blocks_ok": 0, "blocks_failed": 0, "retries": 0,
            "start_utc": utc(), "start_monotonic": time.monotonic(),
            "pre_reference": None, "post_reference": None,
            "checkpoints": 0, "errors": [], "stop_reason": None}
    statuses = []
    try:
        meta["pre_reference"] = reference(wire, streams["vs1"], ident, "PRE", stop=stop)
        sync_stream(streams["vs1"])
        if stop.signum is not None or time.monotonic() >= deadline:
            meta["stop_reason"] = "BEFORE_P300_SCAN"
        else:
            switch(wire, streams["switch"], name + "_PRE_TO_P300", True)
            meta["scan_start_utc"], meta["scan_start_monotonic"] = utc(), time.monotonic()
            with partial.open("xb") as out:
                for ordinal, addr in enumerate(addresses(descending), 1):
                    if stop.signum is not None:
                        meta["stop_reason"] = "OPERATOR_STOP_SAFE_BOUNDARY"
                        break
                    if time.monotonic() >= deadline:
                        meta["stop_reason"] = "DURATION_LIMIT_SAFE_BOUNDARY"
                        break
                    try:
                        packet = wire.packet((3, addr, BLOCK_SIZE))
                    except PacketError as exc:
                        meta["blocks_failed"] += 1
                        write_jsonl(streams["blocks"], {
                            "snapshot_id": ident, "scan_ordinal": ordinal,
                            "block_index": (addr-RAM_START)//BLOCK_SIZE,
                            "address": f"0x{addr:04x}", "requested_length": BLOCK_SIZE,
                            "request_hex": request_frame(3, addr, BLOCK_SIZE).hex(),
                            "rx_observed_hex": exc.received.hex(), "tx_utc": exc.tx_utc,
                            "tx_monotonic": exc.tx_monotonic, "rx_utc": utc(),
                            "rx_monotonic": time.monotonic(), "retry_count": 0,
                            "result": "ERROR", "error": str(exc)})
                        raise
                    out.write(packet["data"])
                    meta["blocks_ok"] += 1
                    row = emit_packet(packet, ident, ordinal)
                    row.update(block_index=(addr-RAM_START)//BLOCK_SIZE,
                               requested_length=BLOCK_SIZE)
                    write_jsonl(streams["blocks"], row)
                    if ordinal % CHECKPOINT_BLOCKS == 0:
                        sync_stream(out)
                        sync_stream(streams["blocks"])
                        try:
                            status = read_status(wire, streams["status"], ident, ordinal)
                            statuses.append(status)
                            meta["checkpoints"] += 1
                        except PacketError as exc:
                            write_jsonl(streams["status"], {
                                "snapshot_id": ident, "after_blocks": ordinal,
                                "result": "ERROR", "rx_observed_hex": exc.received.hex(),
                                "retry_count": 0, "error": str(exc)})
                            raise
                        checkpoint(ident, meta["blocks_ok"], len(statuses))
                sync_stream(out)
            meta["scan_end_utc"], meta["scan_end_monotonic"] = utc(), time.monotonic()
            if wire.phase == "p300":
                switch(wire, streams["switch"], name + "_P300_TO_POST", False)
            meta["post_reference"] = reference(
                wire, streams["vs1"], ident, "POST", stop=None,
                seconds=REFERENCE_SECONDS)
            sync_stream(streams["vs1"])
    except BaseException as exc:
        meta["errors"].append(str(exc) or type(exc).__name__)
        # If safe, restore VS1 to collect a bounded post-error reference.
        if wire.phase == "p300":
            try:
                switch(wire, streams["switch"], name + "_ERROR_TO_VS1", False)
            except BaseException as recovery_exc:
                meta["errors"].append("SWITCH_VS1:" + str(recovery_exc))
        if wire.phase == "vs1" and meta["pre_reference"] and not meta["post_reference"]:
            try:
                meta["post_reference"] = reference(wire, streams["vs1"], ident, "POST_ERROR",
                                                   stop=None, seconds=REFERENCE_SECONDS)
            except BaseException as recovery_exc:
                meta["errors"].append("POST_VS1:" + str(recovery_exc))
    finally:
        meta["end_utc"], meta["end_monotonic"] = utc(), time.monotonic()
        meta["duration_s"] = round(meta["end_monotonic"] - meta["start_monotonic"], 3)
        meta["classification"] = classify(meta["pre_reference"], meta["post_reference"], statuses)
        meta["flame_seen"] = any(s["flame"] for s in statuses)
        meta["flame_transition_seen"] = len({s["flame"] for s in statuses}) > 1
        meta["checkpoints"] = len(statuses)
        valid = (meta["blocks_ok"] == BLOCK_COUNT and not meta["errors"]
                 and meta["pre_reference"] and meta["post_reference"]
                 and meta["pre_reference"]["identity_verified"]
                 and meta["post_reference"]["identity_verified"])
        if valid and partial.is_file():
            try:
                meta["sha256"] = restore_canonical(partial, complete_file, descending)
                meta["data_file"] = complete_file.name
                meta["bytes_stored"] = complete_file.stat().st_size
                meta["complete"], meta["marker"] = True, "COMPLETE"
            except BaseException as exc:
                meta["errors"].append("CANONICALIZE:" + str(exc))
        if not meta["complete"]:
            original = complete_file if complete_file.is_file() else partial
            if original.is_file():
                meta["data_file"] = original.name
                meta["bytes_stored"] = original.stat().st_size
                meta["sha256"] = sha256(original)
            else:
                meta["bytes_stored"] = 0
                meta["sha256"] = None
        DEEP.load_local_base(Path(__file__).resolve().parent).h.atomic_json(
            session / "snapshots" / (name + ".json"), meta)
        for s in streams.values():
            sync_stream(s)
    return meta

def validate_state(session):
    if session.parent != ROOT or session.is_symlink() or not session.name.startswith("run-"):
        raise RuntimeError("FULLRAM_INVALID_SESSION")
    if session.stat().st_uid != 0 or session.stat().st_mode & 0o077:
        raise RuntimeError("FULLRAM_SESSION_NOT_PRIVATE")
    statefile = session / "state.json"
    if statefile.is_symlink() or not statefile.is_file():
        raise RuntimeError("FULLRAM_STATE_MISSING")
    state = json.loads(statefile.read_text())
    h = DEEP.load_local_base(session).h
    if set(state["services"]) != set(h.SERVICES):
        raise RuntimeError("FULLRAM_SERVICE_MANIFEST_INVALID")
    if any(type(v) is not bool for v in state["services"].values()):
        raise RuntimeError("FULLRAM_SERVICE_MANIFEST_NOT_BOOL")
    if (len(state["restore"]) != len(set(state["restore"])) or
            any(u not in h.SERVICES or not state["services"][u] for u in state["restore"])):
        raise RuntimeError("FULLRAM_RESTORE_INTENT_INVALID")
    if not 1 <= state["hours"] <= MAX_HOURS:
        raise RuntimeError("FULLRAM_HOURS_INVALID")
    for key, filename in (("logger_sha256", "logger.py"), ("deep_sha256", "deep.py"),
                          ("base_sha256", "base.py"), ("helper_sha256", HELPER_NAME)):
        DEEP.check_hash(session / filename, state[key])
    return state

def progress(session, phase, counts, start, hours, recent=None):
    # Count durable switch records, including failed attempts. The snapshot worker
    # does not own this counter: switches occur inside capture_snapshot().
    switch_log = session / "switch.jsonl"
    if switch_log.is_file():
        with switch_log.open(encoding="utf-8") as source:
            counts["SWITCHES"] = sum(bool(line.strip()) for line in source)
    base = DEEP.load_local_base(Path(__file__).resolve().parent)
    base.h.atomic_json(session / "progress.json", {
        "state": "RUNNING_READ_ONLY", "phase": phase, "updated_utc": utc(),
        "elapsed_s": round(time.monotonic()-start, 2), "limit_hours": hours,
        "snapshots_complete": counts["COMPLETE"], "snapshots_partial": counts["PARTIAL"],
        "stable_off": counts["STABLE_BRACKET_OFF"],
        "stable_running": counts["STABLE_BRACKET_RUNNING"],
        "p06_zero_samples": counts["P06_ZERO"], "p06_positive_samples": counts["P06_POS"],
        "native_flame_samples": counts["FLAME"], "native_flame_edges": counts["FLAME_EDGES"],
        "blocks_read": counts["BLOCKS"], "switch_count": counts["SWITCHES"],
        "last_snapshot": recent,
    })

def run_worker(session):
    base = DEEP.load_local_base(session)
    h = base.h
    state = validate_state(session)
    report = {"version": VERSION, "session": session.name, "begin_utc": utc(),
              "errors": [], "worker_vs1_restored": False,
              "write_commands_issued": False, "rpm_alias_verified": False,
              "observation_finished": False, "operator_stop": False,
              "snapshots": []}
    start = time.monotonic()
    deadline = start + state["hours"]*3600
    stopper = DEEP.DeferredStop()
    for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        signal.signal(sig, stopper.on_signal)
    counts = Counter()
    handle = wire = None
    streams = {}
    last_progress = start
    last_flame = None

    def heartbeat(snap_id=None, blocks=0, status_count=0):
        nonlocal last_progress, last_flame
        storage_guard(session, streams.values())
        base.isolation(state["port"])
        # Status rows are checkpointed during scanning; never read extra UART registers.
        if time.monotonic()-last_progress >= PROGRESS_SECONDS:
            progress(session, "P300_SCAN", counts, start, state["hours"],
                     {"id": snap_id, "blocks": blocks, "status_checks": status_count})
            last_progress = time.monotonic()

    try:
        live = h.read_settings(h.SETTINGS.read_text())
        if live["port_optolink"] != state["port"]:
            raise RuntimeError("FULLRAM_PORT_CHANGED")
        if h.unit_state(h.MAIN).get("WorkingDirectory") != "/opt/optolink":
            raise RuntimeError("FULLRAM_PRODUCTION_PATH_CHANGED")
        for unit, previous in state["services"].items():
            if (h.unit_state(unit).get("ActiveState") == "active") != previous:
                raise RuntimeError("FULLRAM_SERVICE_CHANGED_" + unit)
        h.pause_services(session, state)  # restore intent persisted BEFORE stopping.
        base.isolation(state["port"])
        handle = h.open_serial(state["port"])
        for k in ("vs1", "blocks", "status", "switch", "trace"):
            streams[k] = (session / (k + ".jsonl")).open("x", encoding="utf-8")
        (session / "snapshots").mkdir(mode=0o700)
        delegate = base.UART1Wire(handle)
        delegate.trace_sink = streams["trace"]
        wire = FullRamWire(delegate)
        delegate.send = wire.send
        wire.identify_vs1()  # Verified 20C2, 0103; no cached VS1 assumption.
        initial = [wire.vs1_read(k) for k in ("P80", "P06")]
        report["initial_gfa"] = initial
        if initial[0]["hex"] != "20":
            raise RuntimeError("FULLRAM_INITIAL_P80_NOT_20")
        progress(session, "VS1_PRE", counts, start, state["hours"])
        print("FULLRAM_WORKER_STARTED=READ_ONLY_20KIB", flush=True)
        while time.monotonic() < deadline and stopper.signum is None:
            heartbeat()
            index = len(report["snapshots"]) + 1
            desc = index % 2 == 0
            snapshot = capture_snapshot(
                session, wire, streams, index, desc, deadline, stopper, heartbeat)
            report["snapshots"].append({
                "id": index, "marker": snapshot["marker"],
                "classification": snapshot["classification"],
                "bytes": snapshot["bytes_stored"], "sha256": snapshot["sha256"],
                "errors": snapshot["errors"]})
            counts[snapshot["marker"]] += 1
            counts[snapshot["classification"]] += 1
            counts["BLOCKS"] += snapshot["blocks_ok"]
            # Count real VS1 P06 samples, not native modulation.
            for side in ("pre_reference", "post_reference"):
                ref = snapshot.get(side) or {}
                if ref.get("p06_raw_unique") == ["00"] and ref.get("stable"):
                    counts["P06_ZERO"] += ref.get("p06_valid", 0)
                elif ref.get("p06_raw_unique") and ref.get("stable"):
                    counts["P06_POS"] += ref.get("p06_valid", 0)
            # Enumerate statuses from per-snapshot file without holding the run in RAM.
            with (session / "status.jsonl").open(encoding="utf-8") as status_file:
                # Count the current snapshot only; full status file may contain prior runs.
                for line in status_file:
                    item = json.loads(line)
                    if item.get("snapshot_id") != index or item.get("result") != "OK":
                        continue
                    counts["FLAME"] += bool(item["flame"])
                    if last_flame is not None and item["flame"] != last_flame:
                        counts["FLAME_EDGES"] += 1
                    last_flame = item["flame"]
            progress(session, "VS1_REFERENCE", counts, start, state["hours"],
                     report["snapshots"][-1])
            last_progress = time.monotonic()
            if snapshot["errors"]:
                report["errors"].extend(snapshot["errors"])
                break
            if snapshot["marker"] != "COMPLETE":
                break
        report["operator_stop"] = stopper.signum is not None
        report["observation_finished"] = (
            not report["errors"] and (stopper.signum is not None or time.monotonic() >= deadline))
    except BaseException as exc:
        report["errors"].append(str(exc) or type(exc).__name__)
    finally:
        for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
            signal.signal(sig, signal.SIG_IGN)
        if wire:
            try:
                final = wire.restore_final_gfa()
                report["final_gfa"] = final
                report["worker_vs1_restored"] = final[0]["hex"] == "20" and final[1]["valid"]
            except BaseException as exc:
                report["errors"].append("WORKER_VS1_RESTORE:" + str(exc))
            try:
                wire.w.flush_trace()
                report["trace_records"] = wire.w.trace_records_written
            except BaseException as exc:
                report["errors"].append("TRACE_FLUSH:" + str(exc))
        for name, stream in streams.items():
            try:
                sync_stream(stream)
                stream.close()
            except BaseException as exc:
                report["errors"].append("LOG_CLOSE_" + name + ":" + str(exc))
        if handle is not None:
            try:
                handle.close()
            except BaseException as exc:
                report["errors"].append("SERIAL_CLOSE:" + str(exc))
        report["end_utc"] = utc()
        report["duration_s"] = round(time.monotonic() - start, 3)
        report["counts"] = dict(counts)
        h.atomic_json(session / "measurement.json", report)
        h.atomic_json(session / "progress.json", {
            "state": "WORKER_EXITED_RECOVERY_PENDING", "end_utc": utc(),
            "counts": dict(counts), "worker_vs1_restored": report["worker_vs1_restored"],
            "errors": report["errors"]})
    return 0 if report["worker_vs1_restored"] and report["observation_finished"] else 1

def worker(session):
    base = DEEP.load_local_base(session)
    with base.locks():
        return run_worker(session)

def archive(session):
    if ROOT.is_symlink() or BUNDLES.is_symlink():
        raise RuntimeError("FULLRAM_BUNDLE_SYMLINK")
    BUNDLES.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(BUNDLES, 0o700)
    output = BUNDLES / ("p300-fullram-" + session.name + "-bundle.tar.gz")
    if output.exists():
        if not output.is_file() or output.is_symlink():
            raise RuntimeError("FULLRAM_BUNDLE_UNSAFE")
        return output
    manifest = {"version": VERSION, "session": session.name,
                "rpm_alias_verified": False, "write_commands_issued": False,
                "production_approved": False, "files": {}}
    filelist = [p for p in session.rglob("*") if p.is_file()]
    for path in sorted(filelist):
        if path.is_symlink():
            raise RuntimeError("FULLRAM_ARCHIVE_SYMLINK")
        st = path.stat()
        if not stat.S_ISREG(st.st_mode) or st.st_uid != 0 or st.st_mode & 0o077:
            raise RuntimeError("FULLRAM_ARCHIVE_MEMBER_PERMISSIONS_" + path.name)
        relative = path.relative_to(session).as_posix()
        manifest["files"][relative] = {"sha256": sha256(path), "size": st.st_size}
    if sum(x["size"] for x in manifest["files"].values()) > MAX_SESSION_BYTES:
        raise RuntimeError("FULLRAM_ARCHIVE_SIZE_GUARD")
    tmp = None
    try:
        with tempfile.NamedTemporaryFile(prefix="p300-fullram-", suffix=".tar.gz",
                                         dir=BUNDLES, delete=False) as f:
            tmp = Path(f.name)
        os.chmod(tmp, 0o600)
        with tarfile.open(tmp, "w:gz") as tar:
            for p in sorted(filelist):
                tar.add(p, arcname="p300-fullram/" + p.relative_to(session).as_posix(),
                        recursive=False)
            data = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode()
            info = tarfile.TarInfo("p300-fullram/bundle-manifest.json")
            info.size = len(data)
            info.mode = 0o600
            tar.addfile(info, io.BytesIO(data))
        os.replace(tmp, output)
    finally:
        if tmp:
            tmp.unlink(missing_ok=True)
    return output

def recover(session):
    state = validate_state(session)
    base = DEEP.load_local_base(session)
    h = base.h
    errors, restored = [], []
    with base.locks():
        if state["restore"] and h.MAIN in state["restore"]:
            try:
                h.command(["systemctl", "start", h.MAIN])
                h.wait_main_ready()
                restored.append(h.MAIN)
            except BaseException as exc:
                errors.append("MAIN_NOT_READY_DEFER_HELPERS:" + str(exc))
        if not errors:
            for unit in reversed(state["restore"]):
                if unit == h.MAIN:
                    continue
                try:
                    h.command(["systemctl", "start", unit])
                    if (unit != "optolink-clock-sync.service" and
                            h.unit_state(unit).get("ActiveState") != "active"):
                        raise RuntimeError("SERVICE_NOT_ACTIVE_" + unit)
                    restored.append(unit)
                except BaseException as exc:
                    errors.append(unit + ":" + str(exc))
        h.atomic_json(session / "recovery.json", {
            "services_restored": not errors, "units_restored": restored,
            "errors": errors, "systemd_result": os.getenv("SERVICE_RESULT", "unknown")})
    try:
        health = DEEP.post_restore_health(base)
        h.atomic_json(session / "health.json", health)
        state_progress = json.loads((session / "progress.json").read_text()) if (
            session / "progress.json").is_file() else {}
        state_progress.update(state="RESTORED" if not errors else "RESTORE_NOT_VERIFIED",
                              restored_utc=utc(), service_restore_verified=not errors,
                              p80_p06_production_health_verified=bool(
                                  health.get("production_main_verified") and all(
                                      health.get("gfa_reads", {}).get(k, {}).get(
                                          "format_and_identity_verified")
                                      for k in ("P80", "P06"))))
        h.atomic_json(session / "progress.json", state_progress)
    except BaseException as exc:
        errors.append("HEALTH:" + str(exc))
    try:
        path = archive(session)
        print("UPLOAD_ONE_FILE=" + str(path), flush=True)
    except BaseException as exc:
        errors.append("ARCHIVE:" + str(exc))
    return int(bool(errors))

def competing(base):
    for unit in (UNIT, DEEP.UNIT, *DEEP.SELF_NAMED_SERVICE_UNITS):
        if base.h.unit_state(unit).get("ActiveState") not in ("inactive", "failed"):
            raise RuntimeError("FULLRAM_COMPETING_LOGGER_" + unit)

def start(hours):
    if os.geteuid() != 0:
        raise RuntimeError("FULLRAM_ROOT_REQUIRED")
    if type(hours) is not int or not 1 <= hours <= MAX_HOURS:
        raise RuntimeError("FULLRAM_HOURS_RANGE_1_TO_8")
    if any(p.is_symlink() for p in (PROJECT, ROOT, BUNDLES)):
        raise RuntimeError("FULLRAM_UNSAFE_ROOT_PATH")
    base = DEEP.load_local_base(PROJECT / "tools")
    h = base.h
    with base.locks():
        settings, services = h.preflight()
        competing(base)
        if shutil.disk_usage(PROJECT).free < PREFLIGHT_BYTES:
            raise RuntimeError("FULLRAM_PREFLIGHT_NEED_896_MIB_FREE")
        ROOT.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(ROOT, 0o700)
        for f in ROOT.glob("run-*/state.json"):
            recover_file = f.with_name("recovery.json")
            previous = json.loads(f.read_text())
            if previous.get("restore") and (not recover_file.is_file() or
                    not json.loads(recover_file.read_text()).get("services_restored")):
                raise RuntimeError("FULLRAM_UNRESOLVED_OLD_RESTORE_" + f.parent.name)
        stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        session = ROOT / ("run-" + stamp + "-" + str(os.getpid()))
        session.mkdir(mode=0o700)
        sources = {"logger.py": Path(__file__).resolve(),
                   "deep.py": PROJECT / "tools" / DEEP_NAME,
                   "base.py": PROJECT / "tools" / BASE_NAME,
                   HELPER_NAME: PROJECT / "tools" / HELPER_NAME}
        hashes = {}
        for filename, source in sources.items():
            if not source.is_file() or source.is_symlink():
                raise RuntimeError("FULLRAM_SOURCE_NOT_REGULAR_" + filename)
            shutil.copyfile(source, session / filename)
            os.chmod(session / filename, 0o600)
            hashes[filename] = sha256(session / filename)
        source_sha = h.command(["git", "-C", str(PROJECT), "rev-parse", "HEAD"]).strip()
        h.atomic_json(session / "state.json", {
            "version": VERSION, "hours": hours, "services": services, "restore": [],
            "port": settings["port_optolink"],
            "source_checkout_sha": source_sha,
            "logger_sha256": hashes["logger.py"], "deep_sha256": hashes["deep.py"],
            "base_sha256": hashes["base.py"], "helper_sha256": hashes[HELPER_NAME]})
    run = [
        "systemd-run", "--unit=" + UNIT, "--no-block", "--collect",
        "--property=Type=exec", "--property=Restart=no",
        "--property=TimeoutStopSec=300", "--property=KillMode=control-group",
        "--property=UMask=0077",
        "--property=ExecStopPost=" + PYTHON + " -u " + str(session/"logger.py") +
            " --recover " + str(session),
        PYTHON, "-u", str(session/"logger.py"), "--worker", str(session)]
    proc = subprocess.run(run, check=False, capture_output=True, text=True, timeout=30)
    if proc.returncode:
        raise RuntimeError("FULLRAM_SYSTEMD_START_REJECTED:" + proc.stderr[-500:])
    print("SESSION=" + str(session))
    print("UNIT=" + UNIT)
    print("HOURS=" + str(hours))
    print("START_ACCEPTED_NO_PRODUCTION_CHANGE=YES")
    return 0

def latest():
    if ROOT.is_symlink() or not ROOT.is_dir():
        raise RuntimeError("FULLRAM_NO_SESSION")
    matches = sorted(p for p in ROOT.glob("run-*") if p.is_dir() and not p.is_symlink())
    if not matches:
        raise RuntimeError("FULLRAM_NO_SESSION")
    return matches[-1]

def status():
    session = latest()
    base = DEEP.load_local_base(PROJECT / "tools")
    print("SESSION=" + str(session))
    print("UNIT_STATE=" + base.h.unit_state(UNIT).get("ActiveState", "unknown"))
    path = session / "progress.json"
    print("PROGRESS=" + path.read_text().strip() if path.is_file() else "PROGRESS=STARTING")
    for name in ("recovery.json", "health.json"):
        file = session / name
        if file.is_file():
            print(name.upper() + "=" + file.read_text().strip())
    archive_path = BUNDLES / ("p300-fullram-" + session.name + "-bundle.tar.gz")
    if archive_path.is_file():
        print("UPLOAD_ONE_FILE=" + str(archive_path))
    return 0

def stop():
    session = latest()
    base = DEEP.load_local_base(PROJECT / "tools")
    state = base.h.unit_state(UNIT).get("ActiveState")
    if state in ("active", "activating", "deactivating"):
        proc = subprocess.run(["systemctl", "stop", UNIT], capture_output=True,
                              text=True, check=False, timeout=360)
        if proc.returncode:
            print("SYSTEMD_STOP_ERROR=" + proc.stderr[-500:])
    elif state not in ("inactive", "failed"):
        raise RuntimeError("FULLRAM_UNEXPECTED_UNIT_STATE_" + str(state))
    for _ in range(45):
        if (session / "recovery.json").is_file() and (
                BUNDLES / ("p300-fullram-" + session.name + "-bundle.tar.gz")).is_file():
            break
        time.sleep(1)
    recovery = json.loads((session / "recovery.json").read_text()) if (
        session / "recovery.json").is_file() else {}
    health = json.loads((session / "health.json").read_text()) if (
        session / "health.json").is_file() else {}
    good = recovery.get("services_restored") and health.get("production_main_verified") and all(
        health.get("gfa_reads", {}).get(k, {}).get("format_and_identity_verified")
        for k in ("P80", "P06"))
    print("SERVICE_RESTORE=" + ("PASS" if recovery.get("services_restored") else "NOT_VERIFIED"))
    print("VS1_P80_P06_HEALTH=" + ("PASS" if good else "NOT_VERIFIED"))
    archive_path = BUNDLES / ("p300-fullram-" + session.name + "-bundle.tar.gz")
    if archive_path.is_file():
        print("UPLOAD_ONE_FILE=" + str(archive_path))
    else:
        print("UPLOAD_ARCHIVE_NOT_VERIFIED")
    return 0 if good and archive_path.is_file() else 1

def main():
    p = argparse.ArgumentParser(description=__doc__)
    group = p.add_mutually_exclusive_group()
    group.add_argument("--start", action="store_true")
    group.add_argument("--status", action="store_true")
    group.add_argument("--stop", action="store_true")
    group.add_argument("--worker", type=Path)
    group.add_argument("--recover", type=Path)
    p.add_argument("--hours", type=int, default=DEFAULT_HOURS)
    a = p.parse_args()
    os.umask(0o077)
    if a.worker or a.recover:
        if os.geteuid() != 0 or "INVOCATION_ID" not in os.environ:
            p.error("supervised systemd root session required")
        return worker(a.worker) if a.worker else recover(a.recover)
    if a.start:
        return start(a.hours)
    if a.status:
        return status()
    if a.stop:
        return stop()
    expected = a.hours * 3600 / PLAN_SECONDS_PER_SCAN
    print(f"PLAN ONLY: {VERSION}; default {DEFAULT_HOURS} h; {BLOCK_COUNT} x 32 B = 20480 B.")
    print("FC03 RAM 0400..53FF; FC01/55D3/11 every 32 blocks; real VS1 P06 before/after.")
    print(f"Rough {expected:.0f} scans / {a.hours} h, approx {expected * ESTIMATED_BYTES_PER_SCAN / 2**20:.0f} MiB uncompressed (NOT a guarantee).")
    print(f"Preflight free >= {PREFLIGHT_BYTES // 2**20} MiB; hard session limit {MAX_SESSION_BYTES // 2**20} MiB.")
    print("No device writes, U1RB, P09-as-RPM, burner commands or productive code replacement.")
    return 0

if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, ValueError, OSError, subprocess.SubprocessError) as exc:
        print("REFUSED_OR_FAILED=" + str(exc), file=sys.stderr)
        raise SystemExit(1)
