#!/usr/bin/env python3
"""OFFLINE: evaluate a ROM-content *oracle* instead of a 20-bit read endpoint.

One hypothetical way to recover ROM bytes without passing ROM addresses is a
checksum of the first N bytes of firmware, where N can be incremented by one.
If consecutive prefix CRC16 values and the polynomial are known, the CRC state
before/after one appended byte identifies the byte by exhaustive 256-way test.

The current WB2A / VDensHO1 has NO verified controllable prefix CRC oracle.
Never interpret simulated CRCs or a fixed full-ROM checksum as device firmware.
No imports or actions to access a serial port or the gas controller.
"""
from __future__ import annotations

import argparse
import binascii
import json
from collections import Counter
from pathlib import Path
import sys


class OracleRejected(ValueError):
    pass


def _word(x: int) -> int:
    if type(x) is not int or not 0 <= x <= 0xFFFF:
        raise OracleRejected("expected finite CRC16 integer")
    return x


def recover_appended_byte(crc_before: int, crc_after: int) -> int:
    """Invert one known CRC-16/CCITT update without the unknown ROM byte."""
    before, after = _word(crc_before), _word(crc_after)
    matches = [b for b in range(256)
               if binascii.crc_hqx(bytes((b,)), before) == after]
    if len(matches) != 1:
        raise OracleRejected("not a unique byte under CRC-16/CCITT")
    return matches[0]


def recover_contiguous_prefix_oracle(
    samples: list[dict], *, first_length: int, first_crc: int
) -> bytes:
    """Given CRC(first_length) and CRC(N+1), recover only the appended bytes.

    The source and prefix start must be identical across all samples. This
    synthetic mathematical function does not verify those device properties.
    An observed controller CRC would require independent provenance.
    """
    _word(first_crc)
    if type(first_length) is not int or not 0 <= first_length <= 0x100000:
        raise OracleRejected("invalid initial prefix length")
    if type(samples) is not list or not 1 <= len(samples) <= 262144:
        raise OracleRejected("nonempty bounded consecutive sample list required")
    result = bytearray()
    state = first_crc
    for index, sample in enumerate(samples, 1):
        if not isinstance(sample, dict) or set(sample) != {"length", "crc"}:
            raise OracleRejected("sample must include only length and crc")
        expected = first_length + index
        if sample["length"] != expected or type(sample["length"]) is not int:
            raise OracleRejected("missing or reordered prefix length")
        if expected > 0x100000:
            raise OracleRejected("sample beyond one MiB")
        state_next = _word(sample["crc"])
        result.append(recover_appended_byte(state, state_next))
        state = state_next
    return bytes(result)


def candidate_gate(*, device: str, measured: bool, read_only: bool,
                   same_start: bool, selectable_length: bool,
                   known_crc16_ccitt: bool, sequential_prefix_responses: bool,
                   controller_identity_verified: bool) -> dict:
    """Conservative gate against mistaking an attractive thought experiment
    for a real safe controller readout mechanism.
    """
    if not isinstance(device, str):
        raise OracleRejected("bad device")
    fields = (measured, read_only, same_start, selectable_length,
              known_crc16_ccitt, sequential_prefix_responses,
              controller_identity_verified)
    if any(type(value) is not bool for value in fields):
        raise OracleRejected("all evidence gates must be Boolean")
    ready = (device == "20C2/0103" and all(fields))
    return {
        "device": device,
        "live_read_allowed_by_this_audit": False,
        "hypothesis_passes_evidence_gate": ready,
        "no_controller_dump_inferred_from_oracle_math": True,
        "missing_requirements": [] if ready else [
            name for name, yes in (
                ("exact_20C2_identity", device == "20C2/0103"),
                ("measured_original_output", measured),
                ("read_only", read_only),
                ("same_ROM_start", same_start),
                ("selectable_prefix_length_N", selectable_length),
                ("known_CRC16_polynomial_init_semantics", known_crc16_ccitt),
                ("original_contiguous_prefix_responses", sequential_prefix_responses),
                ("measured_identity_confirmed", controller_identity_verified)
            ) if not yes
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true",
                        help="run a synthetic CRC demonstration, never contact hardware")
    parser.add_argument("--out", type=Path)
    opts = parser.parse_args()
    if not opts.self_test:
        parser.error("only --self-test is available; no live I/O exists")
    simulated_rom = (
        b"WB2A-SYNTHETIC-NOT-FIRMWARE-" + bytes(range(64)) +
        b"-no-real-controller-code-"
    )
    base_length = 10
    before = binascii.crc_hqx(simulated_rom[:base_length], 0xFFFF)
    values = [
        {"length": i, "crc": binascii.crc_hqx(simulated_rom[:i], 0xFFFF)}
        for i in range(base_length + 1, len(simulated_rom) + 1)
    ]
    recovered = recover_contiguous_prefix_oracle(
        values, first_length=base_length, first_crc=before)
    assert recovered == simulated_rom[base_length:]
    gate = candidate_gate(
        device="20C2/0103", measured=False, read_only=False,
        same_start=False, selectable_length=False, known_crc16_ccitt=False,
        sequential_prefix_responses=False,
        controller_identity_verified=True)
    output = {
        "mode": "SYNTHETIC_CRC16_PREFIX_ORACLE_INVERSION_ONLY",
        "audit": "PASS", "synthetic_secret_total_bytes": len(simulated_rom),
        "synthetic_suffix_recovered_bytes": len(recovered),
        "synthetic_suffix_matches": True,
        "real_WB2A_oracle_proven": False, "real_WB2A_firmware_bytes": 0,
        "WB2A_gate": gate,
        "fixed_full_ROM_checksum_suffices_for_reconstruction": False,
        "controller_io": 0, "controller_writes": 0,
    }
    rendered = json.dumps(output, indent=2, sort_keys=True) + "\n"
    if opts.out:
        opts.out.write_text(rendered, encoding="utf-8")
    print(rendered, end="")


if __name__ == "__main__":
    try:
        main()
    except OracleRejected as exc:
        print("ROM_ORACLE_REJECTED: " + str(exc), file=sys.stderr)
        raise SystemExit(2)
