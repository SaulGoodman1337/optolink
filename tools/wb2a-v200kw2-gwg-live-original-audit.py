#!/usr/bin/env python3
"""Offline, SHA-pinned audit of original 2026-10-12 WB2A live GWG C7/CB/C5.

No serial access, no imports of productive firmware services. Reject altered
captures and prevent incorrect inference from CB/C5 no-response at address 6F.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path

SHA="37721acbbc7c503f6214f163142d4df2743f78ca8286ba8afbb8160ec6b652cf"
ORIGINAL="/tmp/wb2a-v200kw2-gwg-legacy-readonly-20261012.json"
ALLOWED={
 "kw_baseline_before":("01f700f804","20c20003",1),
 "historical_2010_gwg_c7_id":("01c7f80404","20c20003",2),
 "gwg_cb_legacy_outside_temp_example":("01cb6f0104","",2),
 "gwg_c5_legacy_xram_6f":("01c56f0104","",2),
 "kw_baseline_after":("01f700f804","20c20003",1),
}

class Refused(ValueError):pass


def audit(raw:bytes)->dict:
    if type(raw) is not bytes or len(raw)>30000 or hashlib.sha256(raw).hexdigest()!=SHA:
        raise Refused("not original immutable 2026-10-12 GWG live source")
    src=json.loads(raw)
    if (src.get("mode")!="PINNED_HISTORICAL_GWG_READONLY_PROBE"
        or src.get("status")!="BOUNDED_READONLY_COMPLETED"
        or src.get("actual_io")!=8 or src.get("controller_writes")!=0
        or src.get("controller_eeprom_writes")!=0
        or src.get("real_WB2A_GWG_C7_direct_read_confirmed") is not True
        or src.get("ROM_20bit_bank_access_proven") is not False
        or src.get("actual_program_ROM_bytes_recovered") is not False):
        raise Refused("unexpected read count, write guard, or capture declaration")
    items=src.get("records")
    if not isinstance(items,list) or len(items)!=8:
        raise Refused("original full 8 response tuples not present")
    expected=[(key,w,rx,rep) for key,(w,rx,count) in ALLOWED.items()
              for rep in range(count)]
    out=[]
    for obs,(label,wire,response,repeat) in zip(items,expected):
        if (obs.get("name")!=label or obs.get("rep")!=repeat
            or obs.get("tx_hex")!=wire or obs.get("response_hex")!=response
            or obs.get("sync_bytes")!="05" or obs.get("sync_ok") is not True
            or obs.get("response_bytes")!=len(bytes.fromhex(response))
            or obs.get("response_candidate") is not bool(response)):
            raise Refused("an individual historical exact request or response changed")
        out.append({"case":label,"repeat":repeat,"request":wire,
                    "response":response,"sync":obs["sync_bytes"]})
    if src.get("other_legacy_responses")!={k:[r for _ in range(n)]
            for k,(_,r,n) in ALLOWED.items() if k.startswith("gwg_")}:
        raise Refused("the two negative legacy outcomes must not be rewritten")
    return {
        "mode":"OFFLINE_BYTE_EXACT_WB2A_2010_GWG_COMPATIBILITY_FORENSIC",
        "source_original_json_sha256":SHA,
        "device":"WB2A VDensHO1 20C2/0103",
        "real_controller_synchronized_raw_read_telegrams":len(out),
        "live_sources":out,
        "2010_GWG_C7_original_accepted_and_returned_20C2_ID_twice":True,
        "2010_GWG_C7_is_directly_compatible_with_WB2A_20C2":True,
        "historical_GWG_CB_0x6F_responses":[],"historical_GWG_C5_0x6F_responses":[],
        "CB_C5_not_supported_on_all_addresses_proven":False,
        "GWG_C7_8bit_read_is_program_ROM_monitor_proven":False,
        "original_2010_128KiB_ROM_dump_algorithm_recovered":False,
        "controller_writes":0,"controller_io_during_offline_audit":0,
    }


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("immutable_original",type=Path)
    ap.add_argument("--out",type=Path)
    opt=ap.parse_args()
    if (str(opt.immutable_original)!=ORIGINAL
        or opt.immutable_original.is_symlink()
        or not opt.immutable_original.is_file()):
        ap.error("original private path required")
    result=audit(opt.immutable_original.read_bytes())
    output=json.dumps(result,indent=2,sort_keys=True)+"\n"
    if opt.out:opt.out.write_text(output)
    print(output)


if __name__=="__main__":main()
