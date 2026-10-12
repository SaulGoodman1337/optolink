#!/usr/bin/env python3
"""Bounded read-only native P300 ROM-bridge / Vitotrol RX dispatcher discriminator.

Exactly the existing Optolink splitter owns the port. No controller writes;
no service switching inside this script; no general address sweeps.
A separate independent systemd restore is mandatory for live execution.
"""
from __future__ import annotations

import argparse
import ast
import json
import os
from pathlib import Path
import re
import subprocess
import time

SETTINGS = Path("/opt/optolink/settings_ini.py")
EXPECTED_ID = "20c2000300000103"
RESPONSE = re.compile(r"<- openv/resp:\s*(\d+);0x([0-9a-fA-F]+);([0-9a-fA-F]*)")
# The observations are fixed to source-supported WB2A live physical RAM/SFR
# anchors, previously tested high 16-bit service addresses, and FC99 reads.
IDENTITY = ("read;0x00f8;8", 0xF8, 8)
BASELINE = (
    ("read;0x27a0;1", 0x27A0, 1),
    ("read;0x27b0;1", 0x27B0, 1),
    ("read;0x7342;1", 0x7342, 1),
    ("read;0x5738;1", 0x5738, 1),
)
ROM_READS = (
    ("request;3;0xf000;16", 0xF000, 16),
    ("request;3;0xe000;16", 0xE000, 16),
    ("request;3;0xfff0;16", 0xFFF0, 16),
)
INDIRECT_READS = (
    ("request;99;0x0000;2", 0x0000, 2),
    ("request;99;0x0b51;2", 0x0B51, 2),
    ("request;99;0x0b74;2", 0x0B74, 2),
    ("request;99;0x0b7e;2", 0x0B7E, 2),
    ("request;99;0x1a7d;2", 0x1A7D, 2),
    # Same 16-bit service high window as FC03: read-only discriminator.
    ("request;99;0xe000;2", 0xE000, 2),
    ("request;99;0xf000;2", 0xF000, 2),
    ("request;99;0xfff0;2", 0xFFF0, 2),
)
RX_PROBES = (
    ("request;3;0x0b40;32", 0x0B40, 32),
    ("request;3;0x0b60;32", 0x0B60, 32),
    ("request;3;0x0b80;32", 0x0B80, 32),
    ("request;3;0x161a;32", 0x161A, 32),
    ("request;3;0x1640;32", 0x1640, 32),
    ("request;3;0x1660;32", 0x1660, 32),
    ("request;3;0x0054;1", 0x0054, 1),
    ("request;3;0x03ac;2", 0x03AC, 2),
    ("request;3;0x0020;16", 0x0020, 16),
    ("read;0x0a5c;4", 0x0A5C, 4),
    ("read;0x089c;1", 0x089C, 1),
)
# Paired A/B/A read-only high-range discriminator, not an arbitrary scan.
HIGH_PAIR_PROBES = (
    ROM_READS[1], INDIRECT_READS[5],
    ("request;99;0xe002;2", 0xE002, 2),
    ROM_READS[0], INDIRECT_READS[6],
    ("request;99;0xf002;2", 0xF002, 2),
    ROM_READS[2], INDIRECT_READS[7],
    ("request;99;0xfff2;2", 0xFFF2, 2),
)
DMA_PROBES = (
    ("request;3;0x0020;32", 0x0020, 32),  # both M16C DMAC channels, including SAR/DAR/TCR/CON
    ("request;3;0x03b8;4", 0x03B8, 4),   # DMiSL request-select / software-trigger SFRs
    ("read;0x0a5c;4", 0x0A5C, 4),       # no Vitotrol state change
    ("read;0x089c;1", 0x089C, 1),       # unmodified room-sensor state
)
COPY_PROBES = (
    ("request;3;0x1de0;32", 0x1DE0, 32),
    ("request;3;0x1e60;32", 0x1E60, 32),
    ("request;3;0x3300;32", 0x3300, 32),
)
ALLOWED = {cmd: (addr, n) for cmd, addr, n in
           (IDENTITY, *BASELINE, *ROM_READS, *INDIRECT_READS, *RX_PROBES, *COPY_PROBES, *HIGH_PAIR_PROBES, *DMA_PROBES)}


class Rejected(RuntimeError):
    pass


def decode(command: str, output: str, returncode: int) -> dict:
    if command not in ALLOWED:
        raise Rejected("unapproved operation")
    if type(output) is not str or len(output) > 5000:
        raise Rejected("invalid/boundless response")
    matches = list(RESPONSE.finditer(output))
    if len(matches) != 1 or returncode != 0:
        raise Rejected("missing/ambiguous P300 response")
    m = matches[0]
    code, addr, payload = int(m[1]), int(m[2], 16), m[3]
    expected_addr, expected_count = ALLOWED[command]
    if addr != expected_addr or len(payload) % 2:
        raise Rejected("response address/hex mismatch")
    raw = bytes.fromhex(payload)
    if code == 1 and len(raw) != expected_count:
        raise Rejected("successful response length mismatch")
    return {"command": command, "code": code, "address": f"0x{addr:04x}",
            "data": raw.hex(), "valid_read": code == 1,
            "controller_read_only": True}


def require_native(settings: Path = SETTINGS) -> None:
    if os.geteuid() != 0:
        raise Rejected("root required")
    syntax = ast.parse(settings.read_text(encoding="utf-8-sig"))
    flags = []
    for n in syntax.body:
        if isinstance(n, ast.Assign):
            for target in n.targets:
                if isinstance(target, ast.Name) and target.id == "vs1protocol":
                    flags.append(ast.literal_eval(n.value))
    if flags != [False]:
        raise Rejected("existing splitter must be configured for native P300")


def invoke(command: str, *, runner=subprocess.run) -> dict:
    if command not in ALLOWED:
        raise Rejected("operation outside fixed whitelist")
    p = runner(["/usr/local/bin/optolink-debug", "request", command,
                "--timeout", "6"], capture_output=True, text=True,
               timeout=11, check=False)
    return decode(command, p.stdout, p.returncode)


def hard(row: dict) -> str:
    if not row["valid_read"]:
        raise Rejected("mandatory controller read failed: " + row["command"])
    return row["data"]


def run(*, invoke_fn=invoke, cycles: int = 3) -> dict:
    if type(cycles) is not int or not 1 <= cycles <= 3:
        raise Rejected("cycles must be 1..3")
    started = time.monotonic()
    identity = invoke_fn(IDENTITY[0])
    if hard(identity) != EXPECTED_ID:
        raise Rejected("wrong device identity")
    baseline = [invoke_fn(row[0]) for row in BASELINE]
    if any(hard(row) != "00" for row in baseline):
        raise Rejected("baseline A0/B0/type/fault must all be 00")
    evidence = {"target": "20C2/0103", "mode": "READ_ONLY_NATIVE_P300",
                "identity": identity, "baseline": baseline, "rom_service": [],
                "indirect_service": [], "copy_context": [], "rx_samples": []}
    for cmd, _, _ in ROM_READS:
        evidence["rom_service"].append(invoke_fn(cmd))
    for cmd, _, _ in INDIRECT_READS:
        # Unknown read-only indirect endpoints may return error status.
        evidence["indirect_service"].append(invoke_fn(cmd))
    for cmd, _, _ in COPY_PROBES:
        evidence["copy_context"].append(invoke_fn(cmd))
    for index in range(cycles):
        rows = []
        for cmd, _, _ in RX_PROBES:
            row = invoke_fn(cmd)
            hard(row)
            rows.append(row)
        evidence["rx_samples"].append({"index": index, "rows": rows})
    evidence["after"] = [invoke_fn(row[0]) for row in BASELINE]
    if any(hard(row) != "00" for row in evidence["after"]):
        raise Rejected("baseline changed during read-only probe")
    evidence.update({
        "duration_s": round(time.monotonic() - started, 3),
        "controller_writes": 0, "uart_or_dma_register_writes": 0,
        "physical_uart1_rx_irq_proven": False,
        "code_execution_or_rom_mapping_proven": False,
        "received_vitotrol_proven": False,
        "inferred_code_target_allowed": False,
        "no_second_serial_owner": True,
    })
    return evidence


def run_high(*, invoke_fn=invoke, cycles: int = 3) -> dict:
    if type(cycles) is not int or not 2 <= cycles <= 4:
        raise Rejected("high-only cycles must be 2..4")
    started = time.monotonic()
    ident = invoke_fn(IDENTITY[0])
    if hard(ident) != EXPECTED_ID:
        raise Rejected("wrong 20C2 target")
    baseline = [invoke_fn(x[0]) for x in BASELINE]
    if any(hard(x) != "00" for x in baseline):
        raise Rejected("configuration or current fault not baseline")
    windows = []
    for i in range(cycles):
        rows = [invoke_fn(cmd) for cmd, _, _ in HIGH_PAIR_PROBES]
        for row in rows:
            hard(row)
        windows.append({"index": i, "rows": rows})
    after = [invoke_fn(x[0]) for x in BASELINE]
    if any(hard(x) != "00" for x in after):
        raise Rejected("end readback changed")
    return {
        "target": "20C2/0103", "mode": "HIGH_FC03_FC99_ABA_READ_ONLY",
        "identity": ident, "baseline": baseline, "windows": windows,
        "after": after, "duration_s": round(time.monotonic()-started,3),
        "rom_program_code_verified": False, "20bit_address_transported": False,
        "controller_writes": 0, "second_serial_owner": False,
        "unknown_controller_commands_sent": False,
    }


def run_dma(*, invoke_fn=invoke, cycles: int = 5) -> dict:
    """Check real M16C DMA channel occupancy, never configure/trigger it."""
    if type(cycles) is not int or not 2 <= cycles <= 6:
        raise Rejected("DMA watch bounded to 2..6 snapshots")
    started = time.monotonic()
    ident = invoke_fn(IDENTITY[0])
    if hard(ident) != EXPECTED_ID:
        raise Rejected("not the original 20C2 device")
    baseline = [invoke_fn(x[0]) for x in BASELINE]
    if any(hard(x) != "00" for x in baseline):
        raise Rejected("baseline A0/B0/type/fault mismatch")
    rows = []
    for i in range(cycles):
        part = [invoke_fn(x[0]) for x in DMA_PROBES]
        for r in part:
            hard(r)
        rows.append({"index": i, "reads": part})
    after = [invoke_fn(x[0]) for x in BASELINE]
    if any(hard(r) != "00" for r in after):
        raise Rejected("unexpected status after read-only DMA observation")
    return {"mode": "M16C_DMA_ROM_BRIDGE_OCCUPANCY_READ_ONLY",
            "target": "20C2/0103", "identity": ident, "baseline": baseline,
            "dma_snapshots": rows, "after": after,
            "duration_s": round(time.monotonic()-started,3),
            "controller_writes": 0, "dma_triggered": False,
            "rom_contents_read": False, "channel_reassignment_allowed": False,
            "serial_owner": "optolink-splitter.service"}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--execute", action="store_true")
    p.add_argument("--cycles", type=int, default=3)
    group = p.add_mutually_exclusive_group()
    group.add_argument("--high-only", action="store_true")
    group.add_argument("--dma-only", action="store_true")
    p.add_argument("--output", type=Path)
    args = p.parse_args()
    if not args.execute:
        print(json.dumps({"mode": "PLAN_ONLY", "allowed_commands": sorted(ALLOWED),
                          "requires_independent_restore": True, "writes": 0}, indent=2))
        return 0
    if args.output is None or not str(args.output).startswith("/tmp/wb2a-vitotrol-"):
        p.error("bounded /tmp/wb2a-vitotrol-... output required")
    require_native()
    out = (run_dma(cycles=args.cycles) if args.dma_only else
           run_high(cycles=args.cycles) if args.high_only else
           run(cycles=args.cycles))
    args.output.write_text(json.dumps(out, indent=2, sort_keys=True) + "\n")
    if args.dma_only:
        total = 1 + len(out["baseline"]) + len(out["after"]) + sum(
            len(x["reads"]) for x in out["dma_snapshots"])
        n = len(out["dma_snapshots"])
    elif args.high_only:
        total = 1 + len(out["baseline"]) + len(out["after"]) + sum(
            len(x["rows"]) for x in out["windows"])
        n = len(out["windows"])
    else:
        total = 1 + len(out["baseline"]) + len(out["after"]) + (
            len(out["rom_service"]) + len(out["indirect_service"]) +
            len(out["copy_context"]) + sum(len(x["rows"]) for x in out["rx_samples"]))
        n = len(out["rx_samples"])
    print(json.dumps({"output": str(args.output), "samples": n,
                      "total_commands": total, "read_only": True,
                      "duration_s": out["duration_s"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
