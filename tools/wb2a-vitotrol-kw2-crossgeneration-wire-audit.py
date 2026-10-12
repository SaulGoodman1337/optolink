#!/usr/bin/env python3
"""Reconcile original 2010 KarlKoch V200KW2 KM-Bus evidence with real V300 and WB2A.

Offline only. Does NOT emulate Vitotrol, inject KM frames, read/write live
heating control, or establish portability of an unknown 2010 ROM dump method.
The 2010 KarlKoch article asserts a ~128KiB Optolink software read, without
publishing the exact Optolink firmware-read request/handshake or monitor code.
"""
from __future__ import annotations
import argparse
from collections import Counter
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import zipfile

WIKI_REPO=Path("/home/chatgpt-admin/research/openv.wiki")
WIKI_COMMIT="a1d3f9c6dc35b1ca3099a6b452f9ea975e53b962"  # KarlKoch 2010-10-22
WIKI_SHA="a248ec890d4832294c5fac2e85b6b82b9df5021b78d42dc89ddc5bcdf0c6a5bc"
ORIGINAL_V300_ZIP_SHA="eb398ec9b4b174354425d2615f7d76937acaf5e0e1cde4df154fee78425bab93"
ORIGINAL_V300_BIN_SHA="b6d5b0526d0b0a96e5bc3369de639763ef95db9786ee51a1c0b26ecbb229d068"
WB2A_EVENT_SHA="26669707fbd572f25a384b865740c730ec9f4b7e1035cde33cbb142ae99d2e27"

MASTER_WIKI_CLASS11_SLOT3=bytes.fromhex("1100330a0301f8043fd6")
MASTER_WIKI_CLASS01_SLOT1=bytes.fromhex("0100330a0101f80431b4")
MASTER_SLOT1_DERIVED=bytes.fromhex("1100330a0101f80449ef")
WB2A_REAL_MASTER=bytes.fromhex("0100310901010027fa")
WB2A_REAL_RX_CLASS01=bytes.fromhex("0001b10a010100004353")
V300_REAL_ID=bytes.fromhex("0011b3100101f811f938fa01fb0a1db1")
V300_REAL_B1=bytes.fromhex("0011b10a0101001219d5")
V300_REAL_PONG=bytes.fromhex("001180080101f95c")

HERE=Path(__file__).resolve().parent
def _import_crc():
    src=HERE/"wb2a-vitotrol-optolink-rx-audit.py"
    spec=importlib.util.spec_from_file_location("vt_kw2_2010_wire_crc",src)
    if spec is None or spec.loader is None:
        raise ValueError("no shared CRC implementation")
    mod=importlib.util.module_from_spec(spec)
    sys.modules[spec.name]=mod
    spec.loader.exec_module(mod)
    return mod.crc16_kermit
crc16=_import_crc()


class EvidenceRejected(ValueError):pass


def _sha(actual:bytes,expect:str,label:str):
    if type(actual) is not bytes or hashlib.sha256(actual).hexdigest()!=expect:
        raise EvidenceRejected(f"unexpected immutable {label} source")


def wiki_2010_source(repo=WIKI_REPO):
    if not repo.is_dir() or not (repo/".git").exists():
        raise EvidenceRejected("original imported wiki-history repo missing")
    proc=subprocess.run(
        ["git","-C",str(repo),"show",WIKI_COMMIT+":KM-Bus.md"],
        capture_output=True,timeout=8,check=True)
    _sha(proc.stdout,WIKI_SHA,"2010 KarlKoch KM-Bus")
    return proc.stdout


def check_karlkoch_source(blob:bytes)->dict:
    _sha(blob,WIKI_SHA,"2010 KarlKoch KM-Bus")
    raw=blob.decode("utf-8")
    requirements={
        "M30612MC mask ROM and historical Optolink read claim":"M30612MC" in raw and "über [Optolink]" in raw,
        "128KB firmware and disassembly origin":"128 KByte" in raw and "57000 Zeilen" in raw,
        "class11 remote IDs":"0x11 | 0x01 | 0x34,0x38" in raw,
        "class11 2nd remote slot":"0x11 | 0x02 | 0x34,0x38" in raw,
        "class11 3rd remote slot":"0x11 | 0x03 | 0x34,0x38" in raw,
        "class01 slot1":"0x01 | 0x01 | 0x11" in raw,
        "31 to B1 response grammar":"0x31 | 0xB1" in raw,
        "33 to B3 response grammar":"0x33 | 0xB3" in raw,
        "CRC over complete frame has remainder zero":"CRC über alles 0" in raw,
        "documented class11 slot3 master CRC":"01-F8 04-3F D6" in raw,
        "documented class01 slot1 master CRC":"01-F8 04-31 B4" in raw,
    }
    if not all(requirements.values()):
        raise EvidenceRejected("missing KW2 table, CRC proof, or documentation claim")
    return {
        "original_2010_KarlKoch_git_commit":WIKI_COMMIT,
        "original_2010_KarlKoch_sha256":WIKI_SHA,
        "required_historical_document_sections":requirements,
        "KM_class11_slots":[1,2,3],
        "KM_class11_ids":[0x34,0x38],
        "old_200KW2_mcu":"M30612MC",
        "old_reported_firmware_bytes":131072,
        "old_claim_Optolink_readout":True,
        "old_rom_dump_procedure_preserved_in_source":False,
        "old_program_ROM_bytes_recovered":False,
    }


def check_v300(archive:bytes)->dict:
    _sha(archive,ORIGINAL_V300_ZIP_SHA,"genuine external V300 TX ZIP")
    with zipfile.ZipFile(io.BytesIO(archive)) as z:
        if [i.filename for i in z.infolist()]!=["log.bin"]:
            raise EvidenceRejected("zip content differs from original")
        member=z.getinfo("log.bin")
        if member.file_size!=3858:
            raise EvidenceRejected("wrong original V300 source length")
        binary=z.read(member)
    _sha(binary,ORIGINAL_V300_BIN_SHA,"genuine V300 TX binary")
    counts=Counter();packets=[]
    pos=0
    while pos+8<=len(binary):
        n=binary[pos+3]
        if n<8 or n>32 or pos+n>len(binary):
            break
        frame=binary[pos:pos+n]
        if frame[:2]!=b"\x00\x11" or crc16(frame)!=0:
            raise EvidenceRejected("one of sequential original V300 frames CRC-invalid")
        packets.append(frame)
        counts[frame[2]]+=1
        pos+=n
    if (len(packets)!=448 or
        counts!=Counter({0x80:416,0xbf:30,0xb3:1,0xb1:1}) or
        binary[pos:]!=bytes.fromhex("00118008")):
        raise EvidenceRejected("wrong genuine V300 stream coverage")
    for expected in (V300_REAL_ID,V300_REAL_B1,V300_REAL_PONG):
        if expected not in packets:
            raise EvidenceRejected("expected genuine V300 frame missing")
    if [V300_REAL_ID[i] for i in (7,9,11,13)]!=[0x11,0x38,0x01,0x0a]:
        raise EvidenceRejected("V300 identity does not match documented class ID")
    return {
        "archive_sha256":ORIGINAL_V300_ZIP_SHA,
        "original_bin_sha256":ORIGINAL_V300_BIN_SHA,
        "CRC_valid_uninterrupted_slave_frames":len(packets),
        "opcode_counts":{f"0x{k:02x}":v for k,v in sorted(counts.items())},
        "original_V300_class11_source":True,
        "V300_ID_F8_to_FB":"1138010a",
        "V300_B3_ID_frame":V300_REAL_ID.hex(),
        "V300_B1_register00_frame":V300_REAL_B1.hex(),
        "V300_PONG_frame":V300_REAL_PONG.hex(),
    }


def check_wb2a_event(blob:bytes)->dict:
    _sha(blob,WB2A_EVENT_SHA,"WB2A source-attested live event")
    r=json.loads(blob)
    if (r.get("mode")!="NATURAL_MASTER_EVENT_GATED_OPTOLINK_P300_READONLY"
        or r.get("device")!="20C2/0103" or r.get("controller_writes")!=0
        or r.get("master_read_count")!=96 or r.get("read_count")!=134
        or len(r.get("followups",[]))!=1):
        raise EvidenceRejected("WB2A event scope changed")
    case=r["followups"][0]
    tx=bytes.fromhex(case["master_before"]["data"])
    rx=bytes.fromhex(case["rx_immediate"]["data"])
    if (tx[:9]!=WB2A_REAL_MASTER or rx[2:12]!=WB2A_REAL_RX_CLASS01
        or crc16(tx[:9])!=0 or crc16(rx[2:12])!=0):
        raise EvidenceRejected("WB2A actual source frames CRC or bytes differ")
    if (case.get("index")!=85 or case["master_before"]["address"]!="0x161a"
        or case["rx_immediate"]["address"]!="0x1640"
        or case["master_before"]["controller_read_only"] is not True
        or case["rx_immediate"]["controller_read_only"] is not True):
        raise EvidenceRejected("WB2A master/RX RAM copies not validated")
    return {
        "real_WB2A_source_sha256":WB2A_EVENT_SHA,
        "real_WB2A_native_master_31_00":WB2A_REAL_MASTER.hex(),
        "real_WB2A_native_slave_class01_B1_00":WB2A_REAL_RX_CLASS01.hex(),
        "real_WB2A_class01_request_31_response_B1_grammar":True,
        "real_WB2A_slave_class11_Vitotrol_received":False,
        "real_WB2A_UART_ISR_invocation_proven":False,
        "real_WB2A_optical_ROM_monitor_proven":False,
    }


def verify_all(wiki:bytes,v300:bytes,wb2a:bytes)->dict:
    original=check_karlkoch_source(wiki)
    ext=check_v300(v300)
    device=check_wb2a_event(wb2a)
    checks=[MASTER_WIKI_CLASS11_SLOT3,MASTER_WIKI_CLASS01_SLOT1,
            MASTER_SLOT1_DERIVED,WB2A_REAL_MASTER,WB2A_REAL_RX_CLASS01,
            V300_REAL_ID,V300_REAL_B1,V300_REAL_PONG]
    if any(crc16(frame)!=0 or frame[3]!=len(frame) for frame in checks):
        raise EvidenceRejected("cross-generation packet grammar/CRC mismatch")
    synthesized=MASTER_WIKI_CLASS11_SLOT3[:4]+b"\x01"+MASTER_WIKI_CLASS11_SLOT3[5:8]
    valid_new=synthesized+crc16(synthesized).to_bytes(2,"little")
    if valid_new!=MASTER_SLOT1_DERIVED:
        raise EvidenceRejected("slot3 to slot1 CRC recomputation differs")
    return {
        "mode":"OFFLINE_CROSS_GENERATION_KW2_WB2A_KMBUS_WIRE_GATES",
        "2010_openv":original,"2018_real_V300":ext,"2026_WB2A_controller":device,
        "verified_frame_types":[
            "class11 slot3 B3-ID request from old V200KW2 wiki",
            "class01 slot1 B3-ID request from old V200KW2 wiki",
            "class11 slot1 B3-ID request mathematically derived (NOT observed live)",
            "class01 31/00 command and B1/00 response from real WB2A",
            "class11 original V300 B3 ID, B1 register00, and 80 PONG"
        ],
        "slot1_class11_master_discovery_derived_only":MASTER_SLOT1_DERIVED.hex(),
        "CRC16_KERMIT_full_frame_remainder_zero_for_all_reference_frames":True,
        "common_classes_slots_idformats_and_opcode_grammar_supported":True,
        "old_2010_optolink_ROM_transfer_exact_command_known":False,
        "WB2A_ROM_reader_callable_proven":False,
        "WB2A_program_ROM_image_recovered":False,
        "WB2A_Vitotrol_enrollment_proven":False,
        "off_line_no_new_controller_reads_or_writes":True,
        "next_gate":"obtain original 2010 Optolink monitor/sequence, not blindly send ROM guesses",
    }


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("original_v300_zip",type=Path)
    p.add_argument("original_wb2a_event",type=Path)
    p.add_argument("--out",type=Path)
    a=p.parse_args()
    if (a.original_v300_zip.is_symlink() or a.original_wb2a_event.is_symlink()
        or not a.original_v300_zip.is_file() or not a.original_wb2a_event.is_file()
        or a.original_v300_zip.stat().st_size>5_000
        or a.original_wb2a_event.stat().st_size>300_000):
        p.error("requires two real, size-limited research originals")
    report=verify_all(wiki_2010_source(),
                      a.original_v300_zip.read_bytes(),
                      a.original_wb2a_event.read_bytes())
    out=json.dumps(report,indent=2,sort_keys=True)+"\n"
    if a.out:a.out.write_text(out)
    print(out)


if __name__=="__main__":main()
