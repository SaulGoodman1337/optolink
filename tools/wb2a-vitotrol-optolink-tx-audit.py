#!/usr/bin/env python3
"""Inspect a precisely authorized FC03/32 read of SRAM 0x161A (offline).

A CRC-valid buffer is NOT proof that a telegram was transmitted on the
physical KM-Bus. The M16C/UART1-RX/ISR/injection route is not established.
This tool cannot read or write the boiler and never opens Optolink/MQTT.
"""
from __future__ import annotations
import argparse
import importlib.util
import json
from pathlib import Path
import sys

HELPER=Path(__file__).with_name('wb2a-vitotrol-optolink-rx-audit.py')
spec=importlib.util.spec_from_file_location('wb2a_tx_audit_crc',HELPER)
if spec is None or spec.loader is None:
    raise RuntimeError('offline CRC module missing')
rx=importlib.util.module_from_spec(spec)
sys.modules[spec.name]=rx
spec.loader.exec_module(rx)


class TxAuditRejected(ValueError):
    pass


def audit_window(raw:bytes)->dict:
    if type(raw) is not bytes or len(raw)!=32:
        raise TxAuditRejected('exact FC03 0x161A/32 SRAM bytes required')
    length=raw[3]
    frame=raw[:length] if 8<=length<=32 else b''
    crc_ok=bool(frame) and rx.crc16_kermit(frame)==0
    plausible=crc_ok and frame[1]==0x00 and frame[0]!=0x00
    slot=frame[4] if plausible and len(frame)>=8 else None
    register=frame[6] if plausible and len(frame)>=8 else None
    count=frame[7] if plausible and len(frame)>=8 else None
    discovery=(plausible and frame[0]==0x11 and frame[2]==0x33
               and length==10 and slot in (1,2) and frame[5]==1
               and register==0xF8 and count==4)
    return {
        'source':'P300_FC03_RAM_161A_32_NO_WIRE_CAPTURE',
        'full_32_byte_window_hex':raw.hex(),
        'candidate_frame_hex':frame.hex() if frame else None,
        'candidate_length':length,
        'destination_class':f'{frame[0]:02x}' if crc_ok else None,
        'source_class':f'{frame[1]:02x}' if crc_ok else None,
        'command_byte':f'{frame[2]:02x}' if crc_ok else None,
        'participant_class_semantics_verified':False,
        'crc16_kermit_valid':bool(crc_ok),
        'km_bus_master_format_plausible':bool(plausible),
        'vitotrol_discovery_shape':bool(discovery),
        'discovery_slot':slot if discovery else None,
        'candidate_register':f'{register:02x}' if discovery else None,
        'candidate_register_length':count if discovery else None,
        'physical_km_bus_wire_observed':False,
        'controller_uart1_rx_handler_identified':False,
        'controller_vitotrol_acceptance_verified':False,
        'ram_write_or_irq_injection_authorized':False,
        'notes':'A non-atomic SRAM/DMA view is not a verified transmitted telegram',
    }


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--sample-161a',required=True,metavar='EXACT_64_HEX')
    a=p.parse_args()
    try:
        raw=bytes.fromhex(a.sample_161a)
        result=audit_window(raw)
    except (TxAuditRejected,ValueError) as exc:
        p.error(str(exc))
    print(json.dumps(result,indent=2,sort_keys=True))


if __name__=='__main__':
    main()
