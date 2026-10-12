#!/usr/bin/env python3
"""Strictly offline: is WB2A GG1 bootloader-readout bench ready?

NO serial access, NO execution of m16cflasher, NO boot/reset, NO
GPIO/relay writes, NO connection to a live gas-heating controller.
A positive plan would apply only to a disconnected, electrically isolated
spare GG1 board AFTER its real MCU marking has been independently read.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

EXPECTED_FLASHER_SHA="8b097885014d1ee082b6c66a58bfd51ce93b3e58abc64c349eddc6335d5784ce"
EXPECTED_FLASHER_COMMIT="cc8f1c387a5bb86ff25600eacb59a576b5312163"
EXPECTED_DMA_SOURCE_SHA="d45c80d6c63786c67c6a9d338159fe409be8c0c8333d8aca0c0983181ead802f"
FLASHER=Path("/home/chatgpt-admin/research/m16c-flasher-source-review-20261011/build-review/m16cflasher")
SOURCE_REPO=Path("/home/chatgpt-admin/research/m16c-flasher-source-review-20261011")
DMA=Path("/tmp/wb2a-vitotrol-dma-rom-occupancy-live-20261011.json")
CONFIG=Path("/opt/optolink/settings_ini.py")
EXPECTED_CONFIG_SHA="e9a120ef37fe17236a7505ee713c8dd338d98d5093ed75dfb34629d7e8f5c42d"
# M16C/61: M30612MCA 128KB MASK ROM; not a Flash MCU. A trailing
# laser/ROM-number suffix is still needed for a complete positive ID.
MASK_MATCH=re.compile(r"^M30612MC[A-Z0-9-]*$",re.I)
# M16C/62P: M30624FGPFP/GP recognized flash candidates, never
# assume the local GG1 has this chip from a photo of another controller.
FLASH_MATCH=re.compile(r"^M30624FGP(?:FP|GP)(?:[-A-Z0-9]*)$",re.I)
PATHS=(FLASHER,DMA,CONFIG)
PROHIBITED=("erase","program","blank_chk","erase_unlocked","download","lock_off","lock_on","prog_lock_bit")


class NotAttested(ValueError):pass


def safe_hash(path:Path,max_bytes:int):
 if path.is_symlink() or not path.is_file() or path.stat().st_size>max_bytes:
  raise NotAttested(f"original path absent, linked or unexpectedly large: {path}")
 return hashlib.sha256(path.read_bytes()).hexdigest()


def classify(part_no:str|None):
 if not part_no:
  return ("UNIDENTIFIED",None)
 name=part_no.strip().upper()
 if MASK_MATCH.fullmatch(name):
  return ("MASK_ROM_NO_FLASH_BOOT",name)
 if FLASH_MATCH.fullmatch(name):
  return ("POTENTIAL_FLASH_M16C62P_CONFIRM_PACKAGE_AND_REVISION",name)
 return ("UNKNOWN_VARIANT_NEEDS_DATASHEET",name)


def analyze(*,part_no=None,spare_board=False,lab_supply_verified=False,
            validated_pinout=False,uart1_isolated=False,id_code_available=False,
            source_hashes=None):
 if source_hashes is None:
  source_hashes={str(FLASHER):safe_hash(FLASHER,750000),
                 str(DMA):safe_hash(DMA,100000),
                 str(CONFIG):safe_hash(CONFIG,100000)}
 details=[]
 for name,expected in (
     (str(FLASHER),EXPECTED_FLASHER_SHA),
     (str(DMA),EXPECTED_DMA_SOURCE_SHA),
     (str(CONFIG),EXPECTED_CONFIG_SHA)):
  passed=source_hashes.get(name)==expected
  details.append({"source":name,"sha256_valid":passed,"expected_sha256":expected})
 if not all(x["sha256_valid"] for x in details):
  raise NotAttested("original installed host or historical source changed")
 variant,reported=classify(part_no)
 # Deliberately NO 'ready to toggle mode on heating system' state:
 # even flash/spare candidates require independent physical corroboration.
 gates={
  "exact_board_mcu_marking_provided":bool(reported),
  "flash_variant_plausible":variant=="POTENTIAL_FLASH_M16C62P_CONFIRM_PACKAGE_AND_REVISION",
  "physically_separate_non-operational_spare_GG1_board":bool(spare_board),
  "safe_laboratory_supply_supervised":bool(lab_supply_verified),
  "confirmed_specific_pinout_and_voltage":bool(validated_pinout),
  "UART1_RXD1_TXD1_physically_accessible_and_electrically_isolated":bool(uart1_isolated),
  "authorised_seven_byte_ID_available_for_memory_read":bool(id_code_available),
 }
 # This is a documentary checklist ONLY, never permission for an actual
 # boot trigger, pin drive, UART operation or heating hardware modification.
 return {
  "mode":"OFFLINE_STATIC_WB2A_BOOTLOADER_READOUT_PROVENANCE_PRECHECK",
  "status":"NO_LIVE_BOOT_TRIGGER_PERMITTED",
  "named_part":reported,
  "family_interpretation":variant,
  "source_attestations":details,
  "preflight_evidence_gates":gates,
  "all_documented_evidence_gates_supplied":all(gates.values()),
  "actual_device_identification_by_laser_marking_proven_by_software":False,
  "actual_GG1_pinout_electrically_verified_by_software":False,
  "current_optolink_program_UART":"UART0 (DMA1 -> 0x03A2, supported by five 20C2 historical samples)",
  "standard_M16C62P_flash_boot_UART":"UART1 RXD1/TXD1",
  "actual_optolink_optical_receiver_wired_to_boot_RXD1_proven":False,
  "production_optolink_serial_settings":"4800-8E2",
  "bench_flashboot_UART_settings":"9600-8N1 (m16cflasher default)",
  "necessary_reset_mode_signals_FOR_FLASH_62P_BENCH_ONLY":[
    "CNVSS=VCC","CE/P5_0=VCC","EPM/P5_5=VSS","SCLK1/P6_5=VSS",
    "controlled hardware RESET while strapped",
  ],
  "source_not_applicable_to_mask_ROM_M30612MCA":True,
  "7byte_bootloader_read_security_id_may_be_required":True,
  "no_default_unknown_ID_bypass_supported":True,
  "raw_optolink_cannot_directly_activate_the_M16C62P_boot_ROM":True,
  "safe_future_connectivity_checks_on_isolated_spare_only":["ver","status"],
  "disallowed_operations_even_for_preflight":list(PROHIBITED),
  "full_flash_dump_now_possible":False,
  "bootloader_connected":False,
  "mcu_flash_type_verified_on_real_WB2A":False,
  "program_ROM_20bit_bytes_recovered":False,
  "serial_ports_opened":0,"controller_commands_sent":0,"controller_writes":0,
 }


def provenance():
 r=subprocess.run(["git","-C",str(SOURCE_REPO),"rev-parse","HEAD"],
                  capture_output=True,text=True,timeout=5,check=True)
 if r.stdout.strip()!=EXPECTED_FLASHER_COMMIT:
  raise NotAttested("M16C serial boot source revision unexpected")
 return {"flasher_source_commit":EXPECTED_FLASHER_COMMIT}


def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument("--mcu-part",default=None,
  help="TRANSCRIBED actual marking; never treat as automatically verified")
 p.add_argument("--spare-board",action="store_true")
 p.add_argument("--lab-supply-verified",action="store_true")
 p.add_argument("--pinout-verified",action="store_true")
 p.add_argument("--uart1-isolated",action="store_true")
 p.add_argument("--id-code-available",action="store_true")
 p.add_argument("--out",type=Path)
 args=p.parse_args()
 result=analyze(part_no=args.mcu_part,spare_board=args.spare_board,
                lab_supply_verified=args.lab_supply_verified,
                validated_pinout=args.pinout_verified,uart1_isolated=args.uart1_isolated,
                id_code_available=args.id_code_available)
 result.update(provenance())
 serialized=json.dumps(result,sort_keys=True,indent=2)+"\n"
 if args.out:args.out.write_text(serialized)
 print(serialized)


if __name__=="__main__":main()
