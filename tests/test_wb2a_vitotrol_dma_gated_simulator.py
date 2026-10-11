"""B: fail-closed offline 20-bit DMA simulated ROM-byte transport."""
from __future__ import annotations
import ast
import importlib.util
import json
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/"tools/wb2a-vitotrol-dma-gated-simulator.py"
spec=importlib.util.spec_from_file_location("wb2a_vt_dmac_simulator",SRC)
m=importlib.util.module_from_spec(spec)
sys.modules[spec.name]=m
spec.loader.exec_module(m)
LIVE=Path("/tmp/wb2a-vitotrol-dma-rom-occupancy-live-20261011.json")


class DmaGatedSimulatorTests(unittest.TestCase):
    def test_one_byte_source_auto_increment_fixed_destination(self):
        r=m.mock_transfer(0xF0000,0x3301,4,"increment","fixed",
                          bytes.fromhex("12345678"))
        self.assertEqual(r["unique_rom_source_addresses"],4)
        self.assertEqual(r["unique_ram_destination_addresses"],1)
        self.assertEqual(r["result_address_to_byte"],{"0x3301":"78"})
        self.assertFalse(r["every_original_rom_byte_present_at_distinct_ram_destination"])
        self.assertTrue(r["no_write_performed"])

    def test_fixed_source_and_destination_increment_repeats_one_byte(self):
        r=m.mock_transfer(0xF0000,0x3301,4,"fixed","increment",
                          bytes.fromhex("12345678"))
        self.assertEqual(r["unique_rom_source_addresses"],1)
        self.assertEqual(r["unique_ram_destination_addresses"],4)
        self.assertEqual(r["result_address_to_byte"],
                         {"0x3301":"12","0x3302":"12","0x3303":"12","0x3304":"12"})
        self.assertFalse(r["every_original_rom_byte_present_at_distinct_ram_destination"])

    def test_single_transfer_is_possible_as_synthetic_model_only(self):
        r=m.mock_transfer(0xFFFFF,0x0400,1,"fixed","fixed",b"\xAB")
        self.assertEqual(r["result_address_to_byte"],{"0x0400":"ab"})
        self.assertFalse(r["requires_controller_side_reprogramming_or_other_safe_transport"])
        self.assertTrue(r["source_is_synthetic_rom"])

    def test_simultaneously_incrementing_both_is_rejected(self):
        with self.assertRaises(m.InvalidModel):
            m.mock_transfer(0xF0000,0x3301,4,"increment","increment",bytes(4))

    def test_invalid_address_and_width_rejected(self):
        for src,target,n,sm,dm,seed in [
            (0xF000,0x3301,4,"increment","fixed",bytes(4)),
            (0x100000,0x3301,4,"increment","fixed",bytes(4)),
            (0xF0000,0x003AA,4,"increment","fixed",bytes(4)),
            (0xF0000,0x53FF,4,"increment","fixed",bytes(4)),
            (0xF0000,0x3301,33,"increment","fixed",bytes(33)),
            (0xF0000,0x3301,4,"foo","fixed",bytes(4)),
            (0xF0000,0x3301,4,"fixed","fixed",bytes(3)),
        ]:
            with self.subTest(src=src,target=target,n=n),self.assertRaises(m.InvalidModel):
                m.mock_transfer(src,target,n,sm,dm,seed)

    def test_live_attested_original_and_safe_gate_when_available(self):
        if not LIVE.is_file():
            self.skipTest("original live DMA read source unavailable")
        report=m.run(LIVE.read_bytes())
        self.assertEqual(report["hardware_sfr_snapshots_attested"],5)
        self.assertEqual(report["channels"][0]["selectors"],["0x0f"])
        self.assertEqual(report["channels"][1]["selectors"],["0x0a"])
        self.assertEqual(report["channels"][0]["dma_enabled_samples"],1)
        self.assertEqual(report["channels"][1]["dma_enabled_samples"],0)
        self.assertFalse(report["dma0_momentary_dmae_zero_proves_free_channel"])
        self.assertFalse(report["dma1_momentary_dmae_zero_proves_free_channel"])
        self.assertFalse(report["safe_active_live_dma_configuration_authorized"])
        self.assertEqual(report["controller_writes"],0)
        self.assertFalse(report["actual_20bit_program_rom_read_proven"])
        self.assertEqual(
            report["source_auto_increment_fixed_destination"]["unique_ram_destination_addresses"],1)

    def test_bad_sha_and_unauthorized_write_rejected(self):
        with self.assertRaises(m.InvalidModel):
            m.run(b"{}")
        with self.assertRaises(m.InvalidModel):
            m.conclude({"mode":"M16C_DMA_ROM_BRIDGE_OCCUPANCY_READ_ONLY",
                        "controller_writes":1,"dma_triggered":False})

    def test_no_transport_or_external_process(self):
        names=set()
        for n in ast.walk(ast.parse(SRC.read_text())):
            if isinstance(n,ast.Import):
                names.update(x.name.split(".")[0] for x in n.names)
            elif isinstance(n,ast.ImportFrom) and n.module:
                names.add(n.module.split(".")[0])
        self.assertFalse(names & {"serial","subprocess","socket","paho","requests"})


if __name__=="__main__":unittest.main()
