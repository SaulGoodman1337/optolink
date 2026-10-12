#!/usr/bin/env python3
"""Follow-up historical 200KW2 / GWG read-only compatibility on real 20C2.

Only after prior exact GWG C7/20C2 live proof is SHA-verified, and after
independent systemd restore is ACTIVE with original splitter STOPPED.
Test documented alternate GWG address F8 for PHYSICAL READ (Viessmann community
2053 listing, NOT a 200KW2-specific trace); add C7 8-byte ID and F9 overlap.
Never opens serial by default, never writes controller, flash, EEPROM or RAM.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import time

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location(
    "wb2a_v200kw2_original_first_window_gate",
    HERE/"wb2a-v200kw2-gwg-live-original-audit.py")
if not spec or not spec.loader:raise RuntimeError("pinned first live window audit unavailable")
previous=importlib.util.module_from_spec(spec);sys.modules[spec.name]=previous
spec.loader.exec_module(previous)

PORT="/dev/serial/by-id/usb-Silicon_Labs_CP2102_USB_to_UART_Bridge_Controller_0001-if00-port0"
EXPECTED_ID=bytes.fromhex("20c20003")
EXPECTED_ID8=bytes.fromhex("20c2000300000103")
EXPECTED_SHA="e9a120ef37fe17236a7505ee713c8dd338d98d5093ed75dfb34629d7e8f5c42d"
OUTPUT="/tmp/wb2a-v200kw2-gwg-followup-20261012.json"
TIMER="wb2a-v200kw2-gwg-followup-restore-20261012.timer"
CASES={
  "kw_baseline_before":("01f700f804",4,1),
  "gwg_c7_f8_8bytes":("01c7f80804",8,1),
  "gwg_c7_f9_3bytes":("01c7f90304",3,1),
  "gwg_cb_f8_1byte":("01cbf80104",1,2),
  "gwg_c5_f8_1byte":("01c5f80104",1,2),
  "kw_baseline_after":("01f700f804",4,1),
}
READ_SET={0xf7,0xc7,0xcb,0xc5}
assert set(CASES)=={"kw_baseline_before","gwg_c7_f8_8bytes","gwg_c7_f9_3bytes",
                    "gwg_cb_f8_1byte","gwg_c5_f8_1byte","kw_baseline_after"}
for w,n,reps in CASES.values():
    frame=bytes.fromhex(w)
    assert frame[0]==1 and len(frame)==5 and frame[1] in READ_SET
    assert frame[1]!=0xf7 or frame==bytes.fromhex("01f700f804")
    assert 1<=n<=8 and 1<=reps<=2

class Refused(RuntimeError):pass


def prerequisite(raw:bytes):
    result=previous.audit(raw)
    if not result["2010_GWG_C7_is_directly_compatible_with_WB2A_20C2"]:
        raise Refused("first real 2010 C7 compatibility capture missing")
    return result["source_original_json_sha256"]


def checks(*,execute=False,root=False,port_exists=False,original=b"",timer=None):
    if (not execute or not root or not port_exists or not timer
        or hashlib.sha256(original).hexdigest()!=EXPECTED_SHA
        or b"vs1protocol = True" not in original):
        raise Refused("independent restore, root, unchanged VS1 and explicit execution required")


def one_read(port,frame:bytes,nbytes:int,*,now=time.monotonic,sleep=time.sleep)->dict:
    if frame not in [bytes.fromhex(x[0]) for x in CASES.values()]:
        raise Refused("not a source-backed fixed read request")
    if nbytes not in (1,3,4,8):
        raise Refused("unsafe arbitrary receive length")
    port.reset_input_buffer()
    if port.write(b"\x04")!=1:raise Refused("failed 04 sync")
    port.flush()
    start=now();sync=bytearray()
    found=False
    while now()-start<3.0:
        b=port.read(1)
        if b:
            sync.extend(b)
            if b==b"\x05":
                found=True;break
        else:sleep(0.005)
    if not found:
        return {"wire":frame.hex(),"sync":sync.hex(),"synced":False,"reply":""}
    port.reset_input_buffer()
    if port.write(frame)!=len(frame):raise Refused("short fixed historical GWG send")
    port.flush()
    reply=bytearray();start=now();latest=start
    while now()-start<0.70:
        received=port.read_all()
        if received:
            reply.extend(received);latest=now()
        elif reply and now()-latest>0.08:break
        else:sleep(0.006)
    return {"wire":frame.hex(),"sync":sync.hex(),"synced":True,"reply":reply.hex(),
            "expected_bytes":nbytes,"bytes_received":len(reply)}


def capture(port,first_hash:str)->dict:
    rows=[]
    for key,(hex_frame,n,reps) in CASES.items():
        for rep in range(reps):
            result=one_read(port,bytes.fromhex(hex_frame),n)
            result["case"]=key;result["rep"]=rep
            rows.append(result)
            print(json.dumps(result,sort_keys=True),flush=True)
            if key.startswith("kw_baseline") and (
                not result["synced"] or result["reply"]!=EXPECTED_ID.hex()):
                raise Refused("known WB2A KW identity failed; stop GWG exploration")
    lookup=lambda key:[x["reply"] for x in rows if x["case"]==key]
    return {
        "mode":"LEGACY_GWG_F8_ADDRESS_FOLLOWUP_READONLY",
        "device":"WB2A VDensHO1 20C2/0103",
        "prerequisite_proven_first_GWG_C7_sha256":first_hash,
        "records":rows,
        "total_read_requests":len(rows),
        "gwg_c7_8byte_id_matches_vs1":lookup("gwg_c7_f8_8bytes")==[EXPECTED_ID8.hex()],
        "gwg_c7_f9_3byte_id_matches_vs1":lookup("gwg_c7_f9_3bytes")==["c20003"],
        "gwg_cb_f8_responses":lookup("gwg_cb_f8_1byte"),
        "gwg_c5_f8_responses":lookup("gwg_c5_f8_1byte"),
        "gwg_cb_c5_proven_20bit_rom_service":False,
        "program_rom_bytes_recovered":False,
        "controller_writes":0,"controller_eeprom_writes":0,
        "original_vs1_restore_required":True,
        "response_to_unlisted_opcode_could_be_unexpected":False,
        "independent_restoration_of_original_owner_prearmed":True,
    }


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--execute",action="store_true")
    ap.add_argument("--output",type=Path)
    a=ap.parse_args()
    if not a.execute:
        print(json.dumps({"mode":"DRY_RUN","cases":CASES,
             "requires_first_live_C7_positive":True,"controller_writes":0},indent=2))
        return
    if a.output is None or str(a.output)!=OUTPUT:
        ap.error("only exact private second-window output")
    import subprocess
    def active(unit):
        return subprocess.run(["systemctl","is-active","--quiet",unit],
                              timeout=5,capture_output=True).returncode==0
    config=Path("/opt/optolink/settings_ini.py").read_bytes()
    checks(execute=True,root=os.geteuid()==0,port_exists=Path(PORT).is_char_device(),
        original=config,timer=active(TIMER) and not active("optolink-splitter.service"))
    previous_hash=prerequisite(Path(previous.ORIGINAL).read_bytes())
    import serial
    with serial.Serial(PORT,baudrate=4800,bytesize=8,
                       parity=serial.PARITY_EVEN,stopbits=serial.STOPBITS_TWO,
                       timeout=0.07,write_timeout=1.0,exclusive=True) as port:
        try:report=capture(port,previous_hash)
        finally:
            port.write(b"\x04");port.flush()
    a.output.write_text(json.dumps(report,indent=2,sort_keys=True)+"\n")
    print(json.dumps({"c7len8":report["gwg_c7_8byte_id_matches_vs1"],
        "c7f9":report["gwg_c7_f9_3byte_id_matches_vs1"],
        "CB_F8":report["gwg_cb_f8_responses"],
        "C5_F8":report["gwg_c5_f8_responses"],
        "controller_writes":0},sort_keys=True))


if __name__=="__main__":main()
