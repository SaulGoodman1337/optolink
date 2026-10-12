#!/usr/bin/env python3
"""SHA-attested read-only WB2A register00 metadata progression, three sessions.

Original FullRAM snapshot64: 0A04.
Original short natural event85: 0A07.
New natural event198: 0A08 -> seven 0600 in sequential ~230ms P300 reads.
No exact IRQ timing, ROM dump or external 11-class Vitotrol slave proof.
"""
from __future__ import annotations
import argparse
from collections import Counter
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location("vt_meta_audit_oldevent",
 HERE/"wb2a-vitotrol-master31-register00-event-audit.py")
if spec is None or spec.loader is None:raise ValueError("missing pinned prior evidence decoder")
old=importlib.util.module_from_spec(spec);sys.modules[spec.name]=old
spec.loader.exec_module(old)

NEW_SHA="a7194c20d6582b7c71cba1626c867e523b5cd2aec978292ad235cc75281c1b04"
CURRENT_MASTER=bytes.fromhex("0100310901010027fa")
CURRENT_SLAVE=bytes.fromhex("0001b10a010100004353")
NEXT_SLAVE=bytes.fromhex("0001b10a01011000d2c6")


class InvalidEvidence(ValueError):pass


def validate_source(blob:bytes)->dict:
    if type(blob) is not bytes or hashlib.sha256(blob).hexdigest()!=NEW_SHA:
        raise InvalidEvidence("not original Oct 11 21:31 meta progression")
    r=json.loads(blob)
    if (r.get("mode")!="NATURAL_CLASS31_REGISTER00_METAPROGRESSION_READONLY"
        or r.get("device")!="20C2/0103" or r.get("TX_polls")!=199
        or r.get("total_read_count")!=221 or r.get("controller_writes")!=0
        or r.get("event_found") is not True
        or r.get("master_header_counts")!={"010031":2,"0100b1":167,"2000b3":30}
        or r.get("vitotrol_status",{}).get("data")!="00000000"):
        raise InvalidEvidence("different source scope/mode")
    event=r["event"]
    if event.get("poll_index")!=198 or event.get("master_first_copy_crc_valid") is not True:
        raise InvalidEvidence("no expected register00 event")
    master=event["master_register00"]
    rx=event["rx_first"]
    late=event["rx_after"]
    p300next=event["master_after"]
    def raw32(row,addr):
        if (not isinstance(row,dict) or row.get("valid_read") is not True
            or row.get("address")!=f"0x{addr:04x}"):
            raise InvalidEvidence("invalid read reply/address")
        data=bytes.fromhex(row["data"])
        if len(data)!=32:raise InvalidEvidence("non 32B P300 controller copy")
        return data
    tx=raw32(master,0x161a)
    rxbin=raw32(rx,0x1640)
    later=raw32(late,0x1640)
    txlast=raw32(p300next,0x161a)
    if tx[:9]!=CURRENT_MASTER or old.crc.crc16_kermit(tx[:9])!=0:
        raise InvalidEvidence("bad matching master 31/00")
    if rxbin[2:12]!=CURRENT_SLAVE or old.crc.crc16_kermit(rxbin[2:12])!=0:
        raise InvalidEvidence("wrong initial special B1 response")
    if later[2:12]!=NEXT_SLAVE or old.crc.crc16_kermit(later[2:12])!=0:
        raise InvalidEvidence("missing natural B1/10 replacement")
    suffix=txlast[:txlast[3]]
    if txlast[:3]!=bytes.fromhex("0100b1") or old.crc.crc16_kermit(suffix)!=0:
        raise InvalidEvidence("wrong subsequent master")
    timestamps=[(master["mono_start"],master["mono_response"]),
                (rx["mono_start"],rx["mono_response"])]
    seq=event.get("metadata_166a166b_seq")
    reads=event.get("metadata_original_reads")
    if (not isinstance(reads,list) or len(reads)!=8 or
        seq!=["0a08"]+["0600"]*7):
        raise InvalidEvidence("metadata transition not validated")
    for index,row in enumerate(reads):
        data=raw32(row,0x164c)
        if data[-2:].hex()!=seq[index]:raise InvalidEvidence("metadata reply not as claimed")
        timestamps.append((row["mono_start"],row["mono_response"]))
    timestamps.extend([(late["mono_start"],late["mono_response"]),
                       (p300next["mono_start"],p300next["mono_response"])])
    if any(a>=b or b-a>5.5 for a,b in timestamps):
        raise InvalidEvidence("timestamp invalid")
    if any(timestamps[i][1]>timestamps[i+1][0] for i in range(len(timestamps)-1)):
        raise InvalidEvidence("non sequential P300 copies")
    first_response=reads[0]["mono_response"]
    second_response=reads[1]["mono_response"]
    delta_ms=round((second_response-first_response)*1000,3)
    if not 100<delta_ms<1000:raise InvalidEvidence("unexpected followup interval")
    if event.get("full_rx_after_master_host_gap_ms",999)>20:
        raise InvalidEvidence("not an immediate fast event")
    return {
        "mode":"PINNED_31_00_B1_00_META08_TO_0600",
        "source_sha256":NEW_SHA,
        "TX_polls":199,"valid_p300_reads":221,
        "event_index":198,
        "matched_master_31_00":CURRENT_MASTER.hex(),
        "initial_crc_valid_class01_b1_00":CURRENT_SLAVE.hex(),
        "later_crc_valid_class01_b1_10":NEXT_SLAVE.hex(),
        "metadata_sequence_8_individual_copies":seq,
        "metadata_first_two_response_end_delta_ms":delta_ms,
        "meta_0a08_observed_once_then_0600_seven_times":True,
        "two_values_coexist_as_distinct_32byte_copies":True,
        "controller_data_not_ISR_atomic_across_reads":True,
        "controller_writes":0,"UART1_ISR_or_firmware_dispatcher_proven":False,
        "physical_km_bus_onwire_response_proven":False,
    }


def combine(new_blob:bytes,old_blob:bytes,fullram:bytes)->dict:
    now=validate_source(new_blob)
    history=old.inspect(old_blob,fullram)
    prior=history["event"]
    if (prior.get("metadata_166a166b_from_single_copy")!="0a07"
        or history["old_meta_166a166b"]!="0a04"
        or history["historical_to_live_changed_ram_byte_addresses"]!=["0x166b"]):
        raise InvalidEvidence("historical timeline not pinned")
    now.update({
        "cross_era_original_source_hashes":{
            "fullram":old.FULL_SHA,"previous_event":old.EVENT_SHA,"new_event":NEW_SHA
        },
        "observed_166a166b_special_values_in_separate_sessions":{
            "historical_snapshot64":"0a04",
            "previous_short_event85":"0a07",
            "new_followup_event198":"0a08",
        },
        "all_three_special_states_have_166a_0a":True,
        "metadata_second_byte_04_07_08_has_no_verified_semantic_label":True,
        "evidence_for_short_lived_166a_0a_state":True,
        "physical_uart1_rx_ISR_proven":False,"firmware_dump_obtained":False,
        "class11_vitotrol_registered":False,
    })
    return now


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("new_event",type=Path)
    p.add_argument("prior_event",type=Path)
    p.add_argument("fullram_bundle",type=Path)
    p.add_argument("--out",type=Path)
    a=p.parse_args()
    sources=(a.new_event,a.prior_event,a.fullram_bundle)
    if any(s.is_symlink() or not s.is_file() for s in sources):
        p.error("only private regular original evidence files")
    if a.new_event.stat().st_size>400_000 or a.prior_event.stat().st_size>300_000 or a.fullram_bundle.stat().st_size>old.crc.MAX_ARCHIVE_BYTES:
        p.error("input unexpectedly large")
    result=combine(*(f.read_bytes() for f in sources))
    text=json.dumps(result,sort_keys=True,indent=2)+"\n"
    if a.out:a.out.write_text(text)
    print(text)


if __name__=="__main__":main()
