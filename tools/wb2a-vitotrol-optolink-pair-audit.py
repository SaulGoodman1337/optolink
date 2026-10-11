#!/usr/bin/env python3
"""Offline-only interpretation of ONE fixed P300 KM-Bus TX/RX RAM pair.

The 64 bytes are concatenated fixed FC03/32 views at 0x161A and 0x1640.
They are acquired sequentially inside one P300 session, NOT atomically.
Even a valid class-11 TX/RX RAM pair cannot prove physical wire delivery,
UART1 interrupt execution, or Vitotrol acceptance by VDensHO1/20C2.

This tool neither contacts nor writes to the live heater.
"""
from __future__ import annotations
import argparse
import importlib.util
import json
from pathlib import Path
import re
import sys


def _import(name: str, filename: str):
    spec=importlib.util.spec_from_file_location(name,Path(__file__).with_name(filename))
    if spec is None or spec.loader is None:
        raise RuntimeError('offline frame parser missing')
    mod=importlib.util.module_from_spec(spec)
    sys.modules[spec.name]=mod
    spec.loader.exec_module(mod)
    return mod


tx_audit=_import('wb2a_paired_tx_audit','wb2a-vitotrol-optolink-tx-audit.py')
rx_audit=_import('wb2a_paired_rx_audit','wb2a-vitotrol-optolink-rx-audit.py')


class PairRejected(ValueError):
    pass


def inspect_pair(raw: bytes) -> dict:
    """Conservative static classification; all hardware claims fail closed."""
    if type(raw) is not bytes or len(raw)!=64:
        raise PairRejected('one exactly 64-byte TX161A+RX1640 read required')
    tx=tx_audit.audit_window(raw[:32])
    try:
        rx=rx_audit.parse_1640_block(raw[32:])
        receive_candidate=True
        receive_rejection=None
    except rx_audit.EvidenceRejected as exc:
        receive_candidate=False
        receive_rejection=str(exc)
        rx=None
    vitotrol_rx_candidate=bool(receive_candidate and rx['src_class']=='11')
    return {
        'source':'FIXED_P300_FC03_161A_32_PLUS_1640_32',
        'full_64_byte_pair_hex':raw.hex(),
        'master_tx':tx,
        'candidate_rx':rx,
        'candidate_rx_rejection':receive_rejection,
        'candidate_rx_crc_valid':receive_candidate,
        'candidate_vitotrol_class11_reply':vitotrol_rx_candidate,
        'candidate_vitotrol_class11_discovery':tx['vitotrol_discovery_shape'],
        'sequential_nonatomic_ram_samples':True,
        'physical_km_bus_wire_capture':False,
        'uart1_rx_parser_and_isr_verified':False,
        'p300_rx_injection_primitive_verified':False,
        'remote_accepted_by_regulator':False,
        'controller_write_authorized':False,
    }


def compare_pair_reads(before:bytes, when_remote_expected:bytes) -> dict:
    """Compare snapshots under known caller-recorded coding, no causality."""
    normal=inspect_pair(before)
    remote=inspect_pair(when_remote_expected)
    tx_before=normal['master_tx']['candidate_frame_hex']
    tx_after=remote['master_tx']['candidate_frame_hex']
    rx_before=normal['candidate_rx']['frame_hex'] if normal['candidate_rx'] else None
    rx_after=remote['candidate_rx']['frame_hex'] if remote['candidate_rx'] else None
    return {
        'normal_config':'A0:0_B0:0_CLAIMED_BY_OPERATOR',
        'remote_expected_config':'A0:1_B0:3_CLAIMED_BY_OPERATOR',
        'tx_master_frame_same':tx_before==tx_after,
        'rx_candidate_frame_same':rx_before==rx_after,
        'normal_master_class':normal['master_tx']['destination_class'],
        'remote_expected_master_class':remote['master_tx']['destination_class'],
        'normal_rx_source_class':normal['candidate_rx']['src_class'] if normal['candidate_rx'] else None,
        'remote_expected_rx_source_class':remote['candidate_rx']['src_class'] if remote['candidate_rx'] else None,
        'any_class11_seen_in_ram':any((normal['candidate_vitotrol_class11_reply'],
                                      normal['candidate_vitotrol_class11_discovery'],
                                      remote['candidate_vitotrol_class11_reply'],
                                      remote['candidate_vitotrol_class11_discovery'])),
        'intended_single_window_for_each_typed_request':True,
        'actual_hardware_window_proven_by_offline_bytes':False,
        'same_physical_bus_instant_for_both_reads':False,
        'independent_original_vs1_return_attestation_included':False,
        'controller_remote_acceptance_proven':False,
        'causal_effect_of_a0b0_coding_proven':False,
    }


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--pair-hex',required=True,help='64 raw bytes in TX, RX order')
    p.add_argument('--remote-expected-pair-hex',help='second 64-byte pair (no writes)')
    args=p.parse_args()
    try:
        first=bytes.fromhex(args.pair_hex)
        if args.remote_expected_pair_hex is None:
            report=inspect_pair(first)
        else:
            report=compare_pair_reads(first,bytes.fromhex(args.remote_expected_pair_hex))
    except (ValueError,PairRejected) as exc:
        p.error(str(exc))
    print(json.dumps(report,sort_keys=True,indent=2))


if __name__=='__main__':
    main()
