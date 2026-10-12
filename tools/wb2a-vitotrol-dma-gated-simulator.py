#!/usr/bin/env python3
"""B: offline M16C DMAC single-byte ROM-bridge model with fail-closed gates.

Source is the SHA-attested live read-only DMA-SFR JSON; this tool itself
never configures a controller. Simulates address motion with synthetic data,
not the contents of the boiler ROM. Do not use as a controller-write plan.
"""
from __future__ import annotations
from collections import Counter
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

HERE=Path(__file__).resolve().parent
PIN_DMA_SHA="d45c80d6c63786c67c6a9d338159fe409be8c0c8333d8aca0c0983181ead802f"
FAR_ROM_EXAMPLE=0xF0000
SCRATCH_EXAMPLE=0x3301
ROM_SIZE=16
VALID_MODE={"fixed","increment"}

spec=importlib.util.spec_from_file_location(
    "wb2a_vitotrol_dma_guarded_source",
    HERE/"wb2a-vitotrol-dma-rom-audit.py"
)
if spec is None or spec.loader is None:raise RuntimeError("DMA source auditor missing")
auditmod=importlib.util.module_from_spec(spec)
sys.modules[spec.name]=auditmod
spec.loader.exec_module(auditmod)


class InvalidModel(ValueError):pass


def mock_transfer(source:int,target:int,length:int,source_mode:str,dest_mode:str,
                  seed:bytes) -> dict:
    if not (type(source) is int and 0xC0000<=source<=0xFFFFF and
            type(target) is int and 0x400<=target<=0x53FF and
            type(length) is int and 1<=length<=32 and
            source_mode in VALID_MODE and dest_mode in VALID_MODE and
            type(seed) is bytes and len(seed)==length):
        raise InvalidModel("finite hypothetical ROM->lowRAM single-byte transfer only")
    if source+length-1>0xFFFFF or target+length-1>0x53FF:
        raise InvalidModel("address overflow in hypothetical transfer")
    # M16C/62P DSD/DAD cannot be simultaneously incremented.
    if source_mode=="increment" and dest_mode=="increment":
        raise InvalidModel("both source+destination increment not allowed")
    results={}
    refs=[]
    for i in range(length):
        src=source+(i if source_mode=="increment" else 0)
        dst=target+(i if dest_mode=="increment" else 0)
        # The pattern only stands for a synthetic test ROM.
        val=seed[i if source_mode=="increment" else 0]
        results[dst]=val
        refs.append({"src":f"0x{src:05x}","dst":f"0x{dst:05x}","byte":f"{val:02x}"})
    return {
        "source_mode":source_mode,"destination_mode":dest_mode,
        "source_is_synthetic_rom":True,"example_20bit_source":f"0x{source:05x}",
        "example_destination_not_proven_spare_ram":f"0x{target:04x}",
        "byte_clock_events":length,"unique_rom_source_addresses":len({x["src"] for x in refs}),
        "unique_ram_destination_addresses":len(results),
        "result_address_to_byte":{f"0x{k:04x}":f"{v:02x}" for k,v in sorted(results.items())},
        "every_original_rom_byte_present_at_distinct_ram_destination":
          len(results)==length and len({x["src"] for x in refs})==length,
        "requires_controller_side_reprogramming_or_other_safe_transport":length>1,
        "no_write_performed":True,
    }


def conclude(source:dict) -> dict:
    if (not isinstance(source,dict)
        or source.get("mode")!="M16C_DMA_ROM_BRIDGE_OCCUPANCY_READ_ONLY"
        or source.get("controller_writes")!=0
        or source.get("dma_triggered") is not False):
        raise InvalidModel("not the expected bounded original snapshot")
    verified=auditmod.audit(source)
    if len(verified["samples"])!=5:
        raise InvalidModel("original five DMA snapshots mandatory")
    c0,c1=verified["channels"]
    if c0["selectors"]!=["0x0f"] or c1["selectors"]!=["0x0a"]:
        raise InvalidModel("unexpected DMA selector ownership")
    if c0["dest_set"]!=["0x003aa"] or c1["dest_set"]!=["0x003a2"]:
        raise InvalidModel("live UART register destinations changed")
    if c0["source_set"]!=["0x0161b","0x01621"] or c1["source_set"]!=["0x019af"]:
        raise InvalidModel("live firmware ownership source changed")
    if not (c0["nonconstant_transfer_count"] and c1["nonconstant_transfer_count"]):
        raise InvalidModel("historical transfer counter variation missing")
    pattern=bytes((17*i+3)&0xff for i in range(ROM_SIZE))
    fixed_target=mock_transfer(FAR_ROM_EXAMPLE,SCRATCH_EXAMPLE,ROM_SIZE,
                                "increment","fixed",pattern)
    fixed_source=mock_transfer(FAR_ROM_EXAMPLE,SCRATCH_EXAMPLE,ROM_SIZE,
                                "fixed","increment",pattern)
    return {
        "mode":"OFFLINE_20BIT_ROM_TO_SRAM_DMA_FEASIBILITY_GATE",
        "hardware_sfr_snapshots_attested":5,
        "source_sha256":PIN_DMA_SHA,
        "channels":verified["channels"],
        "dma0_owns_kmbus_uart1":True,
        "dma1_owns_only_optolink_uart0_tx":True,
        "dma0_momentary_dmae_zero_proves_free_channel":False,
        "dma1_momentary_dmae_zero_proves_free_channel":False,
        "uart0_control_link_recoverable_after_dma1_reassignment_proven":False,
        "rom_to_ram_single_byte_architecturally_plausible":True,
        "actual_20bit_program_rom_read_proven":False,
        "model_rom_source_is_synthetic":True,
        "source_auto_increment_fixed_destination":fixed_target,
        "fixed_source_destination_auto_increment":fixed_source,
        "linear_rom_to_linear_ram_by_both_auto_increment_supported":False,
        "controller_side_dma_lease_and_autonomous_restore_available":False,
        "controller_source_20bit_bank_verified":False,
        "controller_scratch_destination_unowned_proven":False,
        "safe_active_live_dma_configuration_authorized":False,
        "controller_writes":0,
        "device_transport_initialized":False,
    }


def run(original:bytes) -> dict:
    if type(original) is not bytes or len(original)>80_000:
        raise InvalidModel("bounded DMA source data required")
    if hashlib.sha256(original).hexdigest()!=PIN_DMA_SHA:
        raise InvalidModel("not pinned original read-only DMA live data")
    return conclude(json.loads(original))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("read_only_dma_json",type=Path)
    p.add_argument("--out",type=Path)
    a=p.parse_args()
    if a.read_only_dma_json.is_symlink() or not a.read_only_dma_json.is_file():
        p.error("pinned original JSON required")
    result=run(a.read_only_dma_json.read_bytes())
    out=json.dumps(result,sort_keys=True,indent=2)+"\n"
    if a.out:
        a.out.write_text(out)
    print(out)


if __name__=="__main__":main()
