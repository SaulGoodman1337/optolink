#!/usr/bin/env python3
"""Stop-on-natural-31/00 P300 read-only trace; test whether 166B=07 persists.

No active KM traffic, serial port access, controller writes, UART/DMA/IRQ
manipulation. Use only existing optolink-splitter MQTT queue. All RAM copies
are sequential, not ISR-atomic. An independent supervisor must restore VS1.
"""
from __future__ import annotations
from collections import Counter
import argparse
import importlib.util
import json
from pathlib import Path
import statistics
import sys
import time

ROOT=Path(__file__).resolve().parent
def module(file,name):
    spec=importlib.util.spec_from_file_location(name,ROOT/file)
    if spec is None or spec.loader is None:raise RuntimeError("missing stable source")
    m=importlib.util.module_from_spec(spec);sys.modules[spec.name]=m
    spec.loader.exec_module(m);return m

base=module("wb2a-vitotrol-persistent-mqtt-readonly.py","vt_reg00_meta_base")
crc=module("wb2a-vitotrol-optolink-rx-audit.py","vt_reg00_meta_crc")
REQ31_00=bytes.fromhex("0100310901010027fa")
MAX_POLLS=256
MAX_DURATION=105.0
META_REPETITIONS=8


class Refused(RuntimeError):pass


def master(raw:bytes)->dict:
    if len(raw)!=32:raise Refused("whole 32B TX required")
    n=raw[3]
    f=raw[:n] if 8<=n<=22 else b""
    return {"header":raw[:3].hex(),"full_crc_valid":bool(f and crc.crc16_kermit(f)==0),
            "frame_hex":f.hex(),"same_copy":True,
            "verified_electrical_tx":False}


def rx_frame(raw:bytes)->dict:
    if len(raw)!=32:raise Refused("known 32B RX frame required")
    n=raw[5]
    f=raw[2:2+n] if 8<=n<=30 else b""
    return {"frame_hex":f.hex(),"crc_valid":bool(f and crc.crc16_kermit(f)==0),
            "class11_is_vitotrol":len(f)>1 and f[1]==0x11,
            "uart1_interrupt_confirmed":False}


def measure(client,*,max_polls:int=256,clock=time.monotonic):
    if type(max_polls) is not int or not 32<=max_polls<=MAX_POLLS:
        raise Refused("fixed upper 256 natural TX polls")
    def read(c):
        if c not in base.P300_ONLY:raise Refused("fixed P300 allowlist violation")
        return client.request(c)
    identity=read(base.IDENTITY)
    if identity["data"]!=base.VALID_ID:raise Refused("wrong original device")
    before=[read(c) for c in base.CHECKS]
    if any(z["data"]!="00" for z in before):
        raise Refused("A0/B0/type/fault not original")
    began=clock()
    headers=Counter();regular=[];event=None;checked=0
    for i in range(max_polls):
        if clock()-began>MAX_DURATION:
            raise Refused("bounded observation timeout")
        tx=read(base.MASTER);checked+=1
        q=master(bytes.fromhex(tx["data"]))
        headers[q["header"]]+=1
        if q["full_crc_valid"] and q["frame_hex"]==REQ31_00.hex():
            first=read(base.FULL_RX)
            metareads=[read(base.META) for _ in range(META_REPETITIONS)]
            last=read(base.FULL_RX)
            aftertx=read(base.MASTER)
            meta_values=[bytes.fromhex(z["data"])[-2:].hex() for z in metareads]
            event={
                "poll_index":i,"master_register00":tx,
                "master_first_copy_crc_valid":True,
                "rx_first":first,"rx_first_decoded":rx_frame(bytes.fromhex(first["data"])),
                "metadata_166a166b_seq":meta_values,
                "metadata_original_reads":metareads,
                "rx_after":last,"rx_after_decoded":rx_frame(bytes.fromhex(last["data"])),
                "master_after":aftertx,
                "master_after_decoded":master(bytes.fromhex(aftertx["data"])),
                "full_rx_after_master_host_gap_ms":round(
                    (first["mono_start"]-tx["mono_response"])*1000,3),
                "all_reads_sequential":True,
                "physical_trigger_or_UART_ISR_proven":False,
            }
            break
        if i%16==0:
            regular.append({"index":i,"master":q})
    after=[read(c) for c in base.CHECKS]
    if any(x["data"]!="00" for x in after):raise Refused("unexpected controller state")
    final=[read("read;0x0a5c;4"),read("read;0x089c;1")]
    return {"mode":"NATURAL_CLASS31_REGISTER00_METAPROGRESSION_READONLY",
            "device":"20C2/0103","identity":identity,
            "preflight":before,"postflight":after,
            "TX_polls":checked,"master_header_counts":dict(headers),
            "event_found":event is not None,"event":event,
            "sampling_background":regular,
            "capture_elapsed_s":round(clock()-began,3),
            "total_read_count":len(client.request_log),
            "median_request_ms":round(statistics.median(
                x["duration_ms"] for x in client.request_log),3),
            "vitotrol_status":final[0],"room_sensor_status":final[1],
            "controller_writes":0,"new_serial_owner":False,
            "metadata_single_copy_each_not_atomic_across_times":True,
            "mqtt_shared_topic_request_ids_exist":False,
            "rom_dump_received":False}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--execute",action="store_true")
    p.add_argument("--polls",type=int,default=256)
    p.add_argument("--output",type=Path)
    a=p.parse_args()
    if not a.execute:
        print(json.dumps({"mode":"PLAN","target":"31/00","metadata_repeats":8,
                          "poll_limit":MAX_POLLS,"controller_writes":0},indent=2))
        return
    if not a.output or not str(a.output).startswith("/tmp/wb2a-vitotrol-reg00-metaprogress-"):
        p.error("only private /tmp/wb2a-vitotrol-reg00-metaprogress-* output")
    base.assert_protocol(True)
    if "/opt/optolink" not in sys.path:sys.path.insert(0,"/opt/optolink")
    from homeassistant_publish import connect_mqtt
    with base.BrokerReads(lambda:connect_mqtt(retries=1,delay=1)) as client:
        report=measure(client,max_polls=a.polls)
    a.output.write_text(json.dumps(report,indent=2,sort_keys=True)+"\n")
    print(json.dumps({"found":report["event_found"],"TX_polls":report["TX_polls"],
                      "controller_reads":report["total_read_count"],
                      "median_ms":report["median_request_ms"],"writes":0,
                      "output":str(a.output)}))


if __name__=="__main__":main()
