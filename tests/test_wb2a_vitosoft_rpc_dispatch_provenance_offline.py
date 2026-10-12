"""Negative/positive tests for original VitoSoft/GWG/VS1/P300 dispatch evidence."""
from __future__ import annotations
import copy
import hashlib
import importlib.util
from pathlib import Path
from types import SimpleNamespace as NS
import sys
import tempfile
import unittest

SOURCE=Path(__file__).resolve().parents[1]/"tools"/"wb2a-vitosoft-rpc-dispatch-provenance-offline.py"
spec=importlib.util.spec_from_file_location("wb2a_rpc_dispatch_pinned_offline",SOURCE)
a=importlib.util.module_from_spec(spec)
sys.modules[spec.name]=a
spec.loader.exec_module(a)


def fake(offset,name,value=None,*,token=False):
    operand=NS(value=value) if token else value
    return NS(offset=offset,opcode=NS(name=name),operand=operand)


def make_switch_table(mapping=None):
    if mapping is None:mapping=a.EXPECTED_VS1_TO_WIRE
    instructions=[]
    for i,(fc,vs) in enumerate(mapping.items()):
        base=i*10
        dest=200+i*5
        kind="ldc.i4" if fc>8 else f"ldc.i4.{fc}"
        instructions.extend([fake(base,kind,fc if fc>8 else None),
                             fake(base+1,"beq.s",dest),
                             fake(dest,"ldc.i4",vs),
                             fake(dest+1,"newobj",0x06000001,token=True)])
    return instructions


class DispatcherPureCases(unittest.TestCase):
    def test_original_source_has_14_critical_exact_il_hashes(self):
        self.assertEqual(len(a.METHODS),14)
        self.assertEqual(len(a.EXPECTED_VS1_TO_WIRE),6)
        self.assertEqual(a.EXPECTED_VS1_TO_WIRE[1],0xF7)
        self.assertEqual(a.EXPECTED_VS1_TO_WIRE[201],0x6B)
        self.assertEqual(a.EXPECTED_VS1_TO_WIRE[123],0x7B)
        self.assertEqual(a.EXPECTED_FC_ENUM["Remote_Procedure_Call"],7)

    def test_decode_complete_synthetic_source_mapping(self):
        self.assertEqual(a.decode_vs1_branch_table(make_switch_table()),
                         a.EXPECTED_VS1_TO_WIRE)

    def test_mutated_201_gfa_opcode_rejected(self):
        rows=make_switch_table({**a.EXPECTED_VS1_TO_WIRE,201:0x6F})
        with self.assertRaises(a.Rejected):a.decode_vs1_branch_table(rows)

    def test_invented_rpc7_mapping_rejected(self):
        rows=make_switch_table({**a.EXPECTED_VS1_TO_WIRE,7:0x7})
        with self.assertRaises(a.Rejected):a.decode_vs1_branch_table(rows)

    def test_mutated_process_read_mapping_rejected(self):
        rows=make_switch_table({**a.EXPECTED_VS1_TO_WIRE,123:0x72})
        with self.assertRaises(a.Rejected):a.decode_vs1_branch_table(rows)

    def test_tampered_constructor_token_rejected(self):
        rows=make_switch_table()
        idx=next(i for i,item in enumerate(rows) if item.opcode.name=="newobj")
        rows[idx]=fake(rows[idx].offset,"newobj",0x06000099,token=True)
        with self.assertRaises(a.Rejected):a.decode_vs1_branch_table(rows)

    def test_duplicate_vs1_case_rejected(self):
        rows=make_switch_table()
        rows.extend([fake(700,"ldc.i4.1"),fake(701,"beq.s",710),
                     fake(710,"ldc.i4",0xF7),fake(711,"newobj",0x06000001,token=True)])
        with self.assertRaises(a.Rejected):a.decode_vs1_branch_table(rows)

    def test_missing_branch_target_rejected(self):
        rows=make_switch_table()
        rows[1]=fake(rows[1].offset,"beq.s",9999)
        with self.assertRaises(a.Rejected):a.decode_vs1_branch_table(rows)

    def test_bad_opcode_number_constant_rejected(self):
        rows=make_switch_table()
        idx=next(i for i,item in enumerate(rows) if item.opcode.name=="ldc.i4" and item.operand==201)
        rows[idx]=fake(rows[idx].offset,"ldc.i4",301)
        with self.assertRaises(a.Rejected):a.decode_vs1_branch_table(rows)

    def test_known_integer_loading_forms(self):
        for n,c,v in [("ldc.i4.1",None,1),("ldc.i4.7",None,7),
                      ("ldc.i4.s",201,201),("ldc.i4",123,123),("ldc.i4.m1",None,-1)]:
            self.assertEqual(a.constant(fake(1,n,c)),v)
        self.assertIsNone(a.constant(fake(1,"ldfld",201)))

    def test_call_token_and_field_loading(self):
        instructions=[fake(1,"ldfld",0x0400013E,token=True),
                      fake(2,"call",0x0600000D,token=True),
                      fake(3,"callvirt",0x06000021,token=True)]
        self.assertEqual(a.method_field_loads(instructions),[0x0400013E])
        a.require_calls(instructions,{0x0600000D,0x06000021},"test")
        with self.assertRaises(a.Rejected):
            a.require_calls(instructions,{0x0A0000E7},"reject an invented 32-bit codec")

    def test_fake_source_SHA_rejected(self):
        with tempfile.TemporaryDirectory(prefix="wb2a-oem-") as t:
            p=Path(t)/"source"
            p.write_bytes(b"123456789")
            with self.assertRaises(a.Rejected):
                a.attest_file(p,9,"00"*32)

    def test_fake_source_size_rejected(self):
        with tempfile.TemporaryDirectory(prefix="wb2a-oem-") as t:
            p=Path(t)/"source"
            p.write_bytes(b"123456789")
            with self.assertRaises(a.Rejected):
                a.attest_file(p,8,hashlib.sha256(b"123456789").hexdigest())

    def test_symbolic_symlink_source_rejected(self):
        with tempfile.TemporaryDirectory(prefix="wb2a-oem-") as t:
            p=Path(t)/"source"
            p.write_bytes(b"123456789")
            s=Path(t)/"symbolic"
            s.symlink_to(p)
            with self.assertRaises(a.Rejected):
                a.attest_file(s,9,hashlib.sha256(b"123456789").hexdigest())

    def test_source_file_has_no_heater_IO(self):
        source=SOURCE.read_text(encoding="utf-8")
        for forbidden in ("serial.Serial(", "/dev/tty", "socket.connect(",
                          "subprocess.run(", "systemctl stop",
                          "systemctl restart","Physical_WRITE","sendRawRequest("):
            self.assertNotIn(forbidden,source)

    def test_nonexistent_original_file_skips_ci_without_writes(self):
        self.assertFalse(a.EXPECTED_VS1_TO_WIRE.get(7))
        self.assertEqual(a.EXPECTED_FC_ENUM["KMBUS_EEPROM_READ"],67)


class DispatcherPinnedOriginal(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sources=[entry[0] for entry in a.SOURCE_FILES.values()]
        x=Path("/home/chatgpt-admin/research/vitosoft-lfs/DPDefinitions.xml")
        y=Path("/home/chatgpt-admin/research/vitosoft-lfs/ecnEventType.xml")
        if not (all(path.is_file() for path in sources) and x.is_file() and y.is_file()):
            raise unittest.SkipTest("Private OEM DLLs or original VitoSoft catalog absent in GitHub CI")
        cls.selected,cls.enums,cls.names=a.load_il()
        cls.types,cls.ids,cls.links,cls.defs,cls.meta=a.load_all_host_sources()

    def test_original_14_method_bodies_and_metadata_validated(self):
        self.assertEqual(len(self.selected),14)
        self.assertEqual(self.enums["VS1FunctionCode"],a.EXPECTED_VS1_ENUM)
        self.assertEqual(self.enums["FunctionCodes"],a.EXPECTED_FC_ENUM)

    def test_real_named_RPC_branch_targets_are_exact(self):
        self.assertTrue(self.names["A010_LON_00_to_15_explicitly_route_to_prefix_Default"])
        self.assertEqual(self.names["LON_router_exact_name_cases"],16)
        self.assertTrue(self.names["VitoCom_Neuron_ID_separate_A010_RPC_converter"])
        self.assertTrue(self.names["extra_LON_0_catalog_alias_absent_from_explicit_name_switch"])

    def test_real_tampered_named_RPC_branch_cannot_be_mistaken_for_ROM_service(self):
        # Actual pinned original IL string token for the first LON selector.
        private=Path(a.SOURCE_FILES["interface_core"][0])
        sys.path.insert(0,str(a.PRIVATE/"pydeps"))
        import dnfile
        pe=dnfile.dnPE(str(private))
        ins=list(self.selected[0x06000215])
        found=None
        for j,op in enumerate(ins[:-2]):
            if op.opcode.name!="ldstr":continue
            val=str(pe.net.user_strings.get(op.operand.value&0x00FFFFFF).value)
            if val=="Teilnehmerliste_LON_00~0xA010":
                found=j+2
                break
        self.assertIsNotNone(found)
        self.assertIn(ins[found].opcode.name,("brtrue","brtrue.s"))
        self.assertEqual(ins[found].operand,1589)
        ins[found]=fake(ins[found].offset,ins[found].opcode.name,1580)
        with self.assertRaises(a.Rejected):
            a.validate_rpc_name_routing(pe,ins)

    def test_real_dispatch_and_source_call_graph(self):
        result=a.validate_oem_path(self.selected)
        self.assertTrue(result["six_VS1_dispatch_codes_only_in_selected_OEM_conversion"])
        self.assertFalse(result["VS1_generic_RPC7_opcode_emitted_by_converter"])
        self.assertEqual(result["actual_oem_internal_function_to_VS1_opcode"]["201"],"0x6B")
        self.assertTrue(result["multi_request_explicit_conv_u2_address_narrowing"])
        self.assertTrue(result["default_RPC_read_uses_EventType_PrefixRead_as_request_payload"])
        self.assertTrue(result["A400_proxy_uses_Int16_address_bytes"])

    def test_missing_original_VS1_to_VS2_selection_fails(self):
        mutated=dict(self.selected)
        tok=0x06000086
        mutated[tok]=[ins for ins in self.selected[tok] if
                      not (ins.opcode.name in ("call","callvirt") and
                           getattr(ins.operand,"value",None)==0x0600004D)]
        with self.assertRaises(a.Rejected):a.validate_oem_path(mutated)

    def test_missing_original_RPC_prefix_call_fails(self):
        mutated=dict(self.selected)
        tok=0x06000216
        mutated[tok]=[ins for ins in self.selected[tok] if
                      not (ins.opcode.name in ("call","callvirt") and
                           getattr(ins.operand,"value",None)==0x060000ED)]
        with self.assertRaises(a.Rejected):a.validate_oem_path(mutated)

    def test_original_VS1_converter_loses_case_on_tamper(self):
        mutated=dict(self.selected)
        tok=0x0600000D
        table=copy.copy(self.selected[tok])
        target=next(i for i,ins in enumerate(table)
                    if ins.opcode.name=="ldc.i4" and ins.operand==201)
        original=table[target]
        table[target]=fake(original.offset,"ldc.i4",205)
        mutated[tok]=table
        with self.assertRaises(a.Rejected):a.validate_oem_path(mutated)

    def test_original_VS1_16bit_fields_cannot_be_extended_without_failure(self):
        mutated=dict(self.selected)
        tok=0x060001F6
        mutated[tok]=[ins for ins in self.selected[tok] if
                      not (ins.opcode.name=="ldfld" and
                           getattr(ins.operand,"value",None)==0x0400013E)]
        with self.assertRaises(a.Rejected):a.validate_oem_path(mutated)

    def test_original_full_399_profile_host_membership(self):
        result=a.check_device_catalog(self.types,self.ids,self.links,self.defs)
        self.assertEqual(self.meta["all_type_count"],399)
        self.assertEqual(result["all_399_catalog_PROZESS_READ_event_definitions"],30)
        self.assertEqual(result["all_PROZESS_READ_device_profiles"],["VSorp"])
        self.assertEqual(result["WB2A_RPC_0xA010_distinct_index_values"],16)
        self.assertEqual(result["WB2A_RPC_potentially_mutating_or_reset_host_entries"],5)
        self.assertEqual(result["WB2A_KMBUS_EEPROM_READ_host_events"],0)
        for version in ("VScotHO1_200_10","VScotHO1_200_11"):
            info=result["later_HO2B_GFA_bulk_evidence"][version]
            self.assertEqual(info["16byte_FH_HC_UC_objects"],98)
            self.assertEqual(info["total_GFA_READ_objects"],264)
            self.assertEqual(info["actual_first_FH_HC_address"],"0xC0F0")
            self.assertFalse(info["same_bulk_GFA_service_on_WB2A_proven"])

    def test_original_newer_bulk_GFA_length_modified_rejected(self):
        modified={k:v for k,v in self.defs.items()}
        name="VSKO_FH_HC_01~0xA0F0"
        modified[name]={**modified[name],"BlockLength":"1"}
        with self.assertRaises(a.Rejected):
            a.check_device_catalog(self.types,self.ids,self.links,modified)

    def test_original_newer_GFA_descriptor_address_alias_modified_rejected(self):
        modified={k:v for k,v in self.defs.items()}
        name="VSKO_FH_HC_01~0xA0F0"
        modified[name]={**modified[name],"Address":"0xA0F0"}
        with self.assertRaises(a.Rejected):
            a.check_device_catalog(self.types,self.ids,self.links,modified)

    def test_original_target_rpc_read_index_modified_rejected(self):
        modified={k:v for k,v in self.defs.items()}
        name="Teilnehmerliste_LON_01~0xA010"
        modified[name]={**modified[name],"PrefixRead":"11"}
        with self.assertRaises(a.Rejected):
            a.check_device_catalog(self.types,self.ids,self.links,modified)

    def test_original_target_rpc_mutating_flag_modified_rejected(self):
        modified={k:v for k,v in self.defs.items()}
        name="Teilnehmerliste_LON_01~0xA010"
        modified[name]={**modified[name],"AccessMode":"ReadWrite"}
        with self.assertRaises(a.Rejected):
            a.check_device_catalog(self.types,self.ids,self.links,modified)

    def test_original_process_read_other_family_modified_rejected(self):
        changed={k:v for k,v in self.links.items()}
        wanted=next(x for x,name in self.ids.items()
                    if name=="VSorp_Heiznetztyp~0x2010")
        changed["60"]=set(changed["60"])|{wanted}
        with self.assertRaises(a.Rejected):
            a.check_device_catalog(self.types,self.ids,changed,self.defs)

    def test_integrated_original_audit_has_zero_rom_bytes(self):
        data=a.audit()
        self.assertEqual(data["audit"],"PASS")
        self.assertEqual(data["verified_main_program_ROM_bytes"],0)
        self.assertFalse(data["new_ROM_service_discovered"])
        self.assertFalse(data["ready_for_new_live_ROM_probe"])
        self.assertEqual(data["controller_reads"],0)
        self.assertEqual(data["controller_writes"],0)


if __name__=="__main__":
    unittest.main()
