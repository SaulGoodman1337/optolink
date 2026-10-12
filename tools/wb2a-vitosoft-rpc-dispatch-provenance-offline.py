#!/usr/bin/env python3
"""Audit real OEM CLR IL dispatch path and WB2A RPC metadata (OFFLINE ONLY).

The OEM installer and extracted DLLs must never be executed. Source-size, whole
SHA256 and per-method raw IL hashes fail closed. This tool reads private original
DLLs and the VitoSoft host XML only; it cannot contact Optolink or a heater.

A verified host RPC transport is NOT a verified MCU ROM oracle.
"""
from __future__ import annotations
from collections import Counter, defaultdict
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
PRIVATE=Path("/home/chatgpt-admin/research/vitosoft-oem-original-20261012")
LIB_DIR=PRIVATE/"extracted-readonly/data/OFFLINE/3C8BB38F/CEE8DEB9"
SOURCE_FILES={
 "interface_core":(LIB_DIR/"vsmInterfaceCore.dll",368640,
   "1653fa1346bd37b3e599cdf55fe8eb053d985f8efb8a007c18b94996a575f90d"),
 "interface_common":(LIB_DIR/"vsmInterfaceCommon.dll",81920,
   "ac47b8ede5c4fc7e66eccf1d7f8b32c9c0c186093c7e5a49787a208675f5cb7f"),
}
# Exact original MethodDef indices and hashes; multiple overloaded .sendLDAP
# methods are deliberately NOT conflated by name alone.
METHODS={
 0x0600000B:("vsmInterfaceCore.vs.VS1Message.toByteArray",
   "066589f4027c15f1d108f031794c28ce4eafb1a2a78f62781c3d27ac4ae7e502"),
 0x0600000C:("vsmInterfaceCore.vs.VS1Message.getBytesToRead",
   "960e09d7c5d97c56c0319360dbb0714aab235c92c7ab3218fe21688dfb462e93"),
 0x0600000D:("vsmInterfaceCore.vs.VS1Message.getVS1MessageFromLDAPMessage",
   "13c77176913b37f33b1ba2ab2e386192f33172df1db394e7d0cecc1dc7d0e6c7"),
 0x06000020:("vsmInterfaceCore.vs.VS1.sendVSMessage",
   "3afe7e87e30b2684e5d1abff6db4e6c5ffd168e5fc30296e091328d5d463621a"),
 0x0600004D:("vsmInterfaceCore.vs.VS2.sendLDAP",
   "0b72dc6fc299184ce82e0ca78ba8bd0f6b4542ae5d9efeb206c11725ca5a1889"),
 0x06000086:("vsmInterfaceCore.vs.VSManager.sendLDAP",
   "1b4982e64b70bb5657792988cf09aebe689244a3f055b5a9d99d6a5ff053130e"),
 0x060001F6:("vsmInterfaceCore.protocols.LDAPMessage.toByteArray",
   "94e79a50315944793100e12d69cc9f5f89a94b04208d9b96e9434c0ddf5f0d60"),
 0x06000215:("vsmInterfaceCore.rpc.RPCConverter.ConvertReadRequestToDevice",
   "ec4d3490bac635cb0116173b29abeed9deb9fff6eccb5afa29f66860e078b6ae"),
 0x06000216:("vsmInterfaceCore.rpc.RPCConverter.ConvertRpcToDevice_Default",
   "aac1a03cb6a5d02a4f46cf99beacb076b9f21183603bc24d583ca1716233c0f3"),
 0x06000268:("vsmInterfaceCore.rpc.RPCConverter.ConvertRpcToDevice_VitosorpAccessController",
   "d5ff9521de8db164b8ed94f25ae569da9400d3ded18ecc5c4669705a1432c416"),
 0x06000358:("vsmInterfaceCore.multirequest.MultiRequestDictionary.createMultiRequest",
   "ea673fc349d3a8086eb94d6183993132e6e25e8b08d31586a76d04c91d42480a"),
 0x0600065E:("vsmInterfaceCore.bushandler.RequestCreator.createReadBlockEventTypeRequest",
   "cacbdfd3b03407c5c65169bb531a182bfa7fe01c99019aae02d061e24b565139"),
 0x06000671:("vsmInterfaceCore.bushandler.RequestCreator.CreateReadRequest",
   "48104e10555268f606f267c3f50fe4be8c21e4dc608a96039b6db113fdabd5b7"),
 0x06000672:("vsmInterfaceCore.bushandler.RequestCreator.GetRequestIdentGroup",
   "a59436ae04a52e0d2979e22c9ca6e110daa4107d34907dabecf8e859d8e2dc4d"),
}
EXPECTED_VS1_TO_WIRE={1:0xF7,2:0xF4,201:0x6B,202:0x68,123:0x7B,120:0x78}
EXPECTED_VS1_ENUM={
 "Virtuell_Read":0xF7,"Virtuell_Write":0xF4,"GFA_Read":0x6B,
 "GFA_Write":0x68,"PROZESS_READ":0x7B,"PROZESS_WRITE":0x78,
}
EXPECTED_FC_ENUM={
 "Virtual_READ":1,"Virtual_WRITE":2,"Remote_Procedure_Call":7,
 "GFA_READ":201,"GFA_WRITE":202,"PROZESS_READ":123,
 "PROZESS_WRITE":120,"KMBUS_EEPROM_READ":67,
}


class Rejected(ValueError):
    pass


def attest_file(path:Path,size:int,sha:str)->str:
    if path.is_symlink() or not path.is_file() or path.stat().st_size!=size:
        raise Rejected("invalid private OEM binary source/length")
    with path.open("rb") as file:actual=hashlib.file_digest(file,"sha256").hexdigest()
    if actual!=sha:raise Rejected("changed private OEM binary SHA")
    return actual


def load_il():
    for path,size,sha in SOURCE_FILES.values():attest_file(path,size,sha)
    deps=PRIVATE/"pydeps"
    if not deps.is_dir():raise Rejected("private local IL parsers unavailable")
    sys.path.insert(0,str(deps))
    import dnfile
    from dncil.cil.body import CilMethodBody
    from dncil.cil.body.reader import CilMethodBodyReaderBytes
    pe=dnfile.dnPE(str(SOURCE_FILES["interface_core"][0]))
    if not pe.net or not pe.net.mdtables:raise Rejected("missing OEM CLR metadata")
    rows=pe.net.mdtables.MethodDef.rows
    byptr={id(row):0x06000000+i for i,row in enumerate(rows,1)}
    owned={}
    for t in pe.net.mdtables.TypeDef.rows:
        name=str(t.TypeNamespace)+"."+str(t.TypeName)
        for ref in t.MethodList:
            if ref.row:owned[byptr[id(ref.row)]]=name+"."+str(ref.row.Name)
    selected={}
    for tok,(expected,hash_expected) in METHODS.items():
        idx=tok&0x00FFFFFF
        if not 1<=idx<=len(rows) or owned.get(tok)!=expected:
            raise Rejected("changed original OEM method owner or token")
        row=rows[idx-1]
        if not row.Rva:raise Rejected("OEM method without real IL body")
        body=CilMethodBody(CilMethodBodyReaderBytes(pe.get_data(row.Rva,50000)))
        digest=hashlib.sha256(body.raw_bytes).hexdigest()
        if digest!=hash_expected:raise Rejected("changed original OEM IL method body")
        selected[tok]=body.instructions
    common=dnfile.dnPE(str(SOURCE_FILES["interface_common"][0]))
    if not common.net or not common.net.mdtables:raise Rejected("missing OEM enum metadata")
    enums=read_enum_values(common)
    names=validate_rpc_name_routing(pe,selected[0x06000215])
    return selected,enums,names


def read_enum_values(pe):
    constants={}
    for row in pe.net.mdtables.Constant.rows:
        target=getattr(row.Parent,"row",None)
        raw=getattr(row.Value,"value",None)
        if target is not None and isinstance(raw,bytes) and 1<=len(raw)<=4:
            constants[id(target)]=int.from_bytes(raw,"little")
    found={}
    for t in pe.net.mdtables.TypeDef.rows:
        name=str(t.TypeName)
        if name not in ("VS1FunctionCode","FunctionCodes"):continue
        if name in found:raise Rejected("ambiguous common enum")
        found[name]={str(f.row.Name):constants[id(f.row)]
                     for f in t.FieldList
                     if f.row and id(f.row) in constants}
    for name,values in (("VS1FunctionCode",EXPECTED_VS1_ENUM),
                        ("FunctionCodes",EXPECTED_FC_ENUM)):
        if not all(found.get(name,{}).get(k)==v for k,v in values.items()):
            raise Rejected("OEM enum values do not match dispatcher")
    return {name:{k:found[name][k] for k in expected}
            for name,expected in (("VS1FunctionCode",EXPECTED_VS1_ENUM),
                                  ("FunctionCodes",EXPECTED_FC_ENUM))}


def constant(ins)->int|None:
    name=ins.opcode.name
    if name=="ldc.i4.m1":return -1
    if name in ("ldc.i4","ldc.i4.s"):return int(ins.operand)
    if name.startswith("ldc.i4."):
        tail=name.split(".")[-1]
        if tail.isdecimal():return int(tail)
    return None


def method_calls(ins)->set[int]:
    return {item.operand.value for item in ins
            if item.opcode.name in ("call","callvirt","newobj")
            and hasattr(item.operand,"value")}


def method_field_loads(ins)->list[int]:
    return [item.operand.value for item in ins
            if item.opcode.name=="ldfld" and hasattr(item.operand,"value")]


def require_calls(ins,required:set[int],name:str):
    missing=required-method_calls(ins)
    if missing:raise Rejected(name+" missing expected call(s) "+
                              ",".join(hex(i) for i in sorted(missing)))


def decode_vs1_branch_table(ins)->dict[int,int]:
    """Read actual CLR conditional branch targets, not merely a grep of constants."""
    index={x.offset:i for i,x in enumerate(ins)}
    result={}
    for j,item in enumerate(ins):
        if item.opcode.name not in ("beq","beq.s") or j==0:continue
        value=constant(ins[j-1])
        target=item.operand
        if value is None or not isinstance(target,int) or target not in index:
            continue
        k=index[target]
        if k+1>=len(ins):continue
        command=constant(ins[k])
        new=ins[k+1]
        if command is None or new.opcode.name!="newobj" or getattr(new.operand,"value",None)!=0x06000001:
            continue
        if value in result:raise Rejected("duplicate VS1 dispatch case")
        result[value]=command
    if result!=EXPECTED_VS1_TO_WIRE:
        raise Rejected("VS1 conversion table is not the six pinned read/write mappings")
    return result


def validate_rpc_name_routing(pe,ins)->dict:
    """Resolve real CLR UserString literals and actual IL conditional branches."""
    offset_to_idx={x.offset:i for i,x in enumerate(ins)}
    labels={}
    for j,item in enumerate(ins[:-2]):
        if item.opcode.name!="ldstr" or not hasattr(item.operand,"value"):continue
        call,branch=ins[j+1],ins[j+2]
        if (call.opcode.name!="call" or
            getattr(call.operand,"value",None)!=0x0A0000E2 or
            branch.opcode.name not in ("brtrue","brtrue.s")):continue
        if branch.operand not in offset_to_idx:raise Rejected("unresolved OEM read RPC branch")
        user=pe.net.user_strings.get(item.operand.value&0x00FFFFFF)
        name=str(getattr(user,"value",None))
        if name in labels and labels[name]!=branch.operand:
            raise Rejected("ambiguous OEM RPC event-name switch")
        labels[name]=branch.operand
    for target,call_target in ((1580,0x0600021C),(1589,0x06000216)):
        if target not in offset_to_idx:raise Rejected("unknown original OEM RPC target")
        k=offset_to_idx[target]
        if k+2>=len(ins) or ins[k+2].opcode.name!="call" or getattr(ins[k+2].operand,"value",None)!=call_target:
            raise Rejected("original OEM name-switch callee changed")
    expected_names={f"Teilnehmerliste_LON_{i:02d}~0xA010" for i in range(16)}
    if not expected_names.issubset(labels) or any(labels[n]!=1589 for n in expected_names):
        raise Rejected("A010 LON indexed reads no longer use default prefix converter")
    if labels.get("Vitocom_Neuron_ID~0xA010")!=1580:
        raise Rejected("Vitocom neuron ID has changed to a different converter")
    if "Teilnehmerliste_LON_0~0xA010" in labels:
        raise Rejected("undocumented duplicate LON event alias is now handled")
    return {
       "A010_LON_00_to_15_explicitly_route_to_prefix_Default":True,
       "LON_router_exact_name_cases":len(expected_names),
       "VitoCom_Neuron_ID_separate_A010_RPC_converter":True,
       "extra_LON_0_catalog_alias_absent_from_explicit_name_switch":True,
       "new_main_controller_ROM_oracle_discovered":False,
    }


def validate_oem_path(selected)->dict:
    convert=selected[0x0600000D]
    mapping=decode_vs1_branch_table(convert)
    required_source_fields={0x0400013D,0x0400013E,0x0400013F,0x04000141}
    if not required_source_fields.issubset(method_field_loads(convert)):
        raise Rejected("conversion no longer copies function, address high/low and length")
    if 0x04000140 not in method_field_loads(convert):
        raise Rejected("VS1 write conversion lost data source")
    wire=selected[0x0600000B]
    if not {0x04000001,0x04000002,0x04000003,0x04000004}.issubset(method_field_loads(wire)):
        raise Rejected("VS1 telegram serializer no longer reads four fields")
    readlength=selected[0x0600000C]
    require_calls(readlength,{0x06000002,0x06000007},"VS1 read reply length")
    manager=selected[0x06000086]
    require_calls(manager,{0x0600000D,0x06000021,0x0600004D},"OEM protocol select")
    direct_vs1=selected[0x06000020]
    require_calls(direct_vs1,{0x0600000D,0x06000021},"direct VS1 path")
    ldap=selected[0x060001F6]
    if not {0x0400013D,0x0400013E,0x0400013F,0x04000141}.issubset(method_field_loads(ldap)):
        raise Rejected("LDAP serializer no longer has fixed two-byte address")
    if sum(x.opcode.name=="shl" for x in ldap)!=2:
        raise Rejected("LDAP code/sequence byte packing changed")
    multi=selected[0x06000358]
    require_calls(multi,{0x06000343,0x060000E7,0x060000F5,0x060001F5},
                  "LDAP multi-request builder")
    if sum(x.opcode.name=="conv.u2" for x in multi)<2 or not any(x.opcode.name=="conv.u1" for x in multi):
        raise Rejected("multi-request address/length narrowing changed")
    ident=selected[0x06000672]
    require_calls(ident,{0x060000EB,0x060000EF,0x06000661},"RPC group classifier")
    if not any(constant(x)==7 for x in ident):
        raise Rejected("RPC7 group selector absent")
    creator=selected[0x06000671]
    require_calls(creator,{0x06000672,0x06000210,0x06000213,0x0600065E},
                  "OEM request builder")
    separate=selected[0x0600065E]
    if not any(constant(x)==7 for x in separate):
        raise Rejected("RPC7 missing from read-block special path")
    read_converter=selected[0x06000215]
    require_calls(read_converter,{0x06000216,0x0600021C,0x06000268},
                  "OEM read-RPC semantic branch selector")
    rpc=selected[0x06000216]
    require_calls(rpc,{0x060000ED,0x060000F1,0x0600053A,
                       0x06000126,0x060000F6},"RPC prefix conversion")
    if any(x.opcode.name in ("call","callvirt") and getattr(x.operand,"value",None)==0x0A0000E7
           for x in rpc):
        raise Rejected("unrecognized Int32->bytes in default RPC")
    legacy=selected[0x06000268]
    require_calls(legacy,{0x060000E7,0x0A0000F9,0x060000E8},"old access proxy")
    if 0x0A0000E7 in method_calls(legacy):
        raise Rejected("non-pinned 32-bit address proxy call")
    literal={constant(x) for x in legacy}
    if not {0xA400,0xA401}.issubset(literal):
        raise Rejected("proxy no longer addresses A400/A401")
    return {
      "actual_oem_internal_function_to_VS1_opcode":{
          str(k):f"0x{v:02X}" for k,v in sorted(mapping.items())
      },
      "six_VS1_dispatch_codes_only_in_selected_OEM_conversion":True,
      "VS1_generic_RPC7_opcode_emitted_by_converter":7 in mapping,
      "common_route":"RequestCreator -> MultiRequestDictionary.createMultiRequest -> LDAPMessage -> VSManager.sendLDAP",
      "VS1_path":"VSManager.sendLDAP -> getVS1MessageFromLDAPMessage -> VS1.sendMessageAsynch",
      "VS2_path":"VSManager.sendLDAP -> VS2.sendLDAP -> DAPProtocol.createVS2LDAPTelegram",
      "VS1_has_2_address_fields":True,
      "P300_LDAP_has_2_address_fields":True,
      "multi_request_explicit_conv_u2_address_narrowing":True,
      "default_RPC_read_uses_EventType_PrefixRead_as_request_payload":True,
      "default_RPC_read_sets_length_to_prefix_payload_bytes":True,
      "A400_proxy_uses_Int16_address_bytes":True,
      "deduced_universal_ROM_copy_command":False,
    }


def load_all_host_sources():
    helper=ROOT/"tools"/"wb2a-gwg-vs1-p300-generation-oracle-audit.py"
    if not helper.is_file():raise Rejected("missing previous proven source auditor")
    sp=importlib.util.spec_from_file_location("wb2a_crossgen_catalog_audit",helper)
    mod=importlib.util.module_from_spec(sp)
    sys.modules[sp.name]=mod
    sp.loader.exec_module(mod)
    # Both 186-MB and 9.9-MB original XML are fully checked, not trusted by path.
    for name in ("dp","events"):
        path,sha,size=mod.SOURCES[name]
        mod.sha_original(path,sha,size)
    return mod.load_catalog(mod.DP,mod.EVENT)


def check_device_catalog(types,ids,links,defs)->dict:
    back={v:k for k,v in types.items()}
    if back.get("VDensHO1")!="60" or back.get("V200KW2")!="26":
        raise Rejected("wrong target/source family")
    events=lambda name: [defs[ids[i]] for i in links[back[name]]]
    target=events("VDensHO1")
    fcs=Counter(r.get("FCRead") or "undefined" for r in target)
    if fcs!={"Virtual_READ":462,"GFA_READ":94,"Remote_Procedure_Call":22,"undefined":3}:
        raise Rejected("WB2A request profile unexpectedly changed")
    rpc=[r for r in target if r.get("FCRead")=="Remote_Procedure_Call"]
    lon=[r for r in rpc if r.get("Address")=="0xA010"]
    if (len(rpc)!=22 or len(lon)!=17 or
        not all(r.get("AccessMode")=="Read" and r.get("BlockLength")=="6"
                and len(r.get("PrefixRead",""))==2 for r in lon)):
        raise Rejected("not the original LON indexed read descriptor family")
    ids_lon=[int(r["PrefixRead"],16) for r in lon]
    if sorted(set(ids_lon))!=list(range(16)) or ids_lon.count(0)!=2:
        raise Rejected("unexpected indexed LON RPC parameter window")
    unsafe=[r for r in rpc if r.get("AccessMode")!="Read"]
    if len(unsafe)!=5:
        raise Rejected("wrong potentially state-changing RPC classification")
    if sum(bool(r.get("PrefixRead")) for r in rpc)!=19:
        raise Rejected("WB2A RPC prefix count changed")
    other=[r for r in rpc if r.get("Address")!="0xA010"]
    if set(r.get("Address") for r in other)!={"0xA009","0xA029","0xA050","0xA051"}:
        raise Rejected("new RPC service address needs independent analysis")
    process_aliases={s for s,r in defs.items() if r.get("FCRead")=="PROZESS_READ"}
    owners={types[pid] for pid,events_i in links.items()
            if process_aliases.intersection({ids[i] for i in events_i})}
    if len(process_aliases)!=30 or owners!={"VSorp"}:
        raise Rejected("process-read source-family membership changed")
    oldgwg=events("GWG_VBEM_00")
    if sum(r.get("FCRead")=="KMBUS_EEPROM_READ" for r in oldgwg)!=54:
        raise Rejected("old GWG routed read evidence changed")
    newer_bulk={}
    for family in ("VScotHO1_200_10","VScotHO1_200_11"):
        gf=[r for r in events(family) if r.get("FCRead")=="GFA_READ"]
        lengths=dict(sorted(Counter(int(r.get("BlockLength",0) or 0)
                                    for r in gf).items()))
        bulky=[r for r in gf if r.get("BlockLength")=="16" and
               r.get("ID","").startswith(("VSKO_FH_HC_","VSKO_FH_UC_"))]
        if (len(gf)!=264 or lengths!={1:129,2:34,4:1,7:2,16:98} or len(bulky)!=98):
            raise Rejected("newer HO2B GFA bulk block structure changed")
        sample=[r for r in bulky if r.get("ID")=="VSKO_FH_HC_01~0xA0F0"]
        if len(sample)!=1 or sample[0].get("Address")!="0xC0F0":
            raise Rejected("actual GFA address differs from attested host descriptor")
        newer_bulk[family]={"total_GFA_READ_objects":len(gf),
                            "GFA_read_block_length_distribution":lengths,
                            "16byte_FH_HC_UC_objects":len(bulky),
                            "first_FH_HC_event_alias":"VSKO_FH_HC_01~0xA0F0",
                            "actual_first_FH_HC_address":"0xC0F0",
                            "same_bulk_GFA_service_on_WB2A_proven":False}
    if any(r.get("FCRead")=="GFA_READ" and r.get("BlockLength")!="1" for r in target):
        raise Rejected("unanticipated WB2A multi-byte GFA host descriptor")
    return {
      "WB2A_device_id":"20C2","WB2A_host_profile":"VDensHO1",
      "WB2A_FCRead_counts":dict(sorted(fcs.items())),
      "WB2A_PROZESS_READ_host_events":0,
      "all_399_catalog_PROZESS_READ_event_definitions":len(process_aliases),
      "all_PROZESS_READ_device_profiles":sorted(owners),
      "WB2A_KMBUS_EEPROM_READ_host_events":0,
      "old_GWG_VBEM_00_KMBUS_EEPROM_READ_event_links":54,
      "WB2A_RPC_host_events":len(rpc),
      "WB2A_RPC_prefix_read_entries":sum(bool(r.get("PrefixRead")) for r in rpc),
      "WB2A_RPC_0xA010_read_aliases":len(lon),
      "WB2A_RPC_0xA010_distinct_index_values":len(set(ids_lon)),
      "WB2A_RPC_0xA010_defined_indices_hex":[f"{a:02X}" for a in sorted(set(ids_lon))],
      "WB2A_RPC_0xA010_block_length_in_host":6,
      "WB2A_RPC_potentially_mutating_or_reset_host_entries":len(unsafe),
      "WB2A_RPC_0xA010_rom_pointer_or_checksum_verified":False,
      "WB2A_other_RPC_addresses":sorted(set(r["Address"] for r in other)),
      "later_HO2B_GFA_bulk_evidence":newer_bulk,
    }


def audit()->dict:
    selected,enums,names=load_il()
    wire=validate_oem_path(selected)
    types,ids,links,defs,meta=load_all_host_sources()
    device=check_device_catalog(types,ids,links,defs)
    return {
       "audit":"PASS","date":"2026-10-12",
       "source_kind":"PRIVATE_OEM_CLR_IL_AND_VITOSOFT_XML_ONLY",
       "oem_binary_SHA256":{k:info[2] for k,info in SOURCE_FILES.items()},
       "source_method_body_SHA256":{hex(tok):sha for tok,(_,sha) in METHODS.items()},
       "verified_original_CLR_methods":len(selected),
       "oem_enum_values":enums,
       "oem_RPC_read_name_dispatcher":names,
       "dispatcher":wire,
       "device_families":device,
       "original_catalog":meta,
       "controller_reads":0,"controller_writes":0,
       "verified_main_program_ROM_bytes":0,
       "ready_for_new_live_ROM_probe":False,
       "new_ROM_service_discovered":False,
    }


def main():
    import argparse
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out",type=Path)
    args=p.parse_args()
    result=audit()
    data=json.dumps(result,indent=2,sort_keys=True)+"\n"
    if args.out:args.out.write_text(data,encoding="utf-8")
    print(data,end="")


if __name__=="__main__":
    try:main()
    except (OSError,KeyError,Rejected,IndexError,ValueError) as exc:
        print("REJECTED: "+str(exc),file=sys.stderr)
        sys.exit(2)
