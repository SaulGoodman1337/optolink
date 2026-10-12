#!/usr/bin/env python3
"""Observe natural 0x31/B3/33 master TX contexts via existing serial-owner MQTT.

Only bounded, whitelisted P300 Physical_READs and existing VS1 datapoints.
The master TX frame is copied in a single FC03 source read, but its electrical
bus transmission is NOT proven. Event follow-up FULL_RX and metadata reads
remain sequential, and cannot prove causality, IRQ delivery or enrolment.
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

HERE=Path(__file__).resolve().parent
def filemod(path,name):
    spec=importlib.util.spec_from_file_location(name,HERE/path)
    if spec is None or spec.loader is None:raise RuntimeError("verified source unavailable")
    mod=importlib.util.module_from_spec(spec);sys.modules[spec.name]=mod
    spec.loader.exec_module(mod);return mod
fast=filemod("wb2a-vitotrol-persistent-mqtt-readonly.py","vt_persistent_event_fast")
frames=filemod("wb2a-vitotrol-optolink-rx-audit.py","vt_persistent_event_crc")
TRIGGERS=frozenset(("010031","2000b3","110033"))
LIMIT_EVENT_EXTRA=16
MIN_POLLS=32
MAX_POLLS=96
assert set((fast.IDENTITY,*fast.CHECKS,fast.MASTER,fast.META,fast.FULL_RX,
            "read;0x0a5c;4","read;0x089c;1")).issubset(fast.P300_ONLY)


class Refused(ValueError):pass


def master(src:dict)->dict:
    raw=bytes.fromhex(src["data"])
    if len(raw)!=32:raise Refused("not exact whole master physical copy")
    n=raw[3]
    frame=raw[:n] if 8<=n<=22 else b""
    return {"header":raw[:3].hex(),"frame":frame.hex(),
            "crc_valid":bool(frame and frames.crc16_kermit(frame)==0),
            "complete_master_copied_in_one_p300_request":True,
            "physical_master_bus_transmitted_proven":False}


def parse_rx(src:dict)->dict:
    raw=bytes.fromhex(src["data"])
    if len(raw)!=32:raise Refused("not exact historical RX window")
    size=raw[5]
    frame=raw[2:2+size] if 8<=size<=30 else b""
    valid=bool(frame and frame[0]==0 and frame[1]!=0
               and frames.crc16_kermit(frame)==0)
    return {"crc_valid":valid,"frame_hex":frame.hex(),
            "frame_size":size,"source_single_copy":True,
            "uart_rx_ISR_or_parser_commit_proven":False}


def capture(client,*,polls:int=96):
    if type(polls) is not int or not MIN_POLLS<=polls<=MAX_POLLS:
        raise Refused("only 32..96 bounded TX polling attempts")
    def read(cmd):
        if cmd not in fast.P300_ONLY:raise Refused("read outside P300 whitelist")
        return client.request(cmd)
    identity=read(fast.IDENTITY)
    if identity["data"]!=fast.VALID_ID:raise Refused("wrong controller/firmware")
    before=[read(c) for c in fast.CHECKS]
    if any(r["data"]!="00" for r in before):raise Refused("baseline A0/B0/Type/Fault not zero")
    events=[];sampled=[];headers=Counter();crc_good=Counter()
    triggered=Counter()
    started=time.monotonic()
    for i in range(polls):
        tx=read(fast.MASTER)
        parsed=master(tx)
        headers[parsed["header"]]+=1
        crc_good["VALID" if parsed["crc_valid"] else "INVALID_OR_PARTIAL"]+=1
        critical=parsed["crc_valid"] and parsed["header"] in TRIGGERS
        if critical and len(events)<LIMIT_EVENT_EXTRA:
            rx=read(fast.FULL_RX)
            meta=read(fast.META)
            post=read(fast.MASTER)
            pair=bytes.fromhex(meta["data"])[-2:].hex()
            after=master(post)
            triggered[parsed["header"]]+=1
            events.append({"index":i,"master_before":tx,
                           "master_before_parsed":parsed,
                           "rx_immediate":rx,"rx_decoded":parse_rx(rx),
                           "metadata_166a_166b":pair,
                           "metadata_raw_read":meta,
                           "master_after":post,"master_after_parsed":after,
                           "master_to_rx_host_elapsed_ms":round(
                               (rx["mono_start"]-tx["mono_response"])*1000,3),
                           "master_rx_meta_sequential":True,
                           "controller_parser_acceptance_proven":False})
        elif i%8==0:
            rx=read(fast.FULL_RX)
            meta=read(fast.META)
            sampled.append({"index":i,"master":parsed,"rx":parse_rx(rx),
                            "metadata_166a_166b":bytes.fromhex(meta["data"])[-2:].hex(),
                            "rx_read":rx,"meta_read":meta})
    after=[read(c) for c in fast.CHECKS]
    if any(x["data"]!="00" for x in after):raise Refused("controller mode or error changed")
    status=[read(x) for x in ("read;0x0a5c;4","read;0x089c;1")]
    return {
        "mode":"NATURAL_MASTER_EVENT_GATED_OPTOLINK_P300_READONLY",
        "device":"20C2/0103","identity":identity,
        "guards_before":before,"guards_after":after,
        "master_read_count":polls,
        "master_header_counts":dict(sorted(headers.items())),
        "master_crc_validity":dict(sorted(crc_good.items())),
        "triggered_header_counts":dict(sorted(triggered.items())),
        "max_event_followups":LIMIT_EVENT_EXTRA,
        "followups":events,"background_samples":sampled,
        "vitotrol_swindex":status[0],"sensor_089c":status[1],
        "read_count":len(client.request_log),
        "request_median_ms":round(statistics.median(
            x["duration_ms"] for x in client.request_log),3),
        "request_p95_ms":round(sorted(x["duration_ms"] for x in client.request_log)[
            int(.95*(len(client.request_log)-1))],3),
        "capture_elapsed_s":round(time.monotonic()-started,3),
        "controller_writes":0,"new_hardware_access":False,
        "mqtt_same_address_correlation_proven":False,
        "km_bus_physical_onwire_or_uart_ISR_proven":False,
    }


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--execute",action="store_true")
    p.add_argument("--polls",type=int,default=96)
    p.add_argument("--output",type=Path)
    args=p.parse_args()
    if not args.execute:
        print(json.dumps({"mode":"DRY_RUN","read_allowlist":sorted(fast.P300_ONLY),
             "triggers":sorted(TRIGGERS),"controller_writes":0},indent=2))
        return
    if not args.output or not str(args.output).startswith("/tmp/wb2a-vitotrol-natural-event-"):
        p.error("private /tmp/wb2a-vitotrol-natural-event-* output required")
    fast.assert_protocol(True)
    if "/opt/optolink" not in sys.path:sys.path.insert(0,"/opt/optolink")
    from homeassistant_publish import connect_mqtt
    with fast.BrokerReads(lambda:connect_mqtt(retries=1,delay=1)) as bus:
        evidence=capture(bus,polls=args.polls)
    args.output.write_text(json.dumps(evidence,sort_keys=True,indent=2)+"\n")
    print(json.dumps({"mode":evidence["mode"],"reads":evidence["read_count"],
                      "events":len(evidence["followups"]),
                      "median_ms":evidence["request_median_ms"],"writes":0}))


if __name__=="__main__":main()
