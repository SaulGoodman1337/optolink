#!/usr/bin/env python3
"""Bounded persistent MQTT client: existing Optolink splitter is sole serial owner.

No changes to /opt/optolink and no new serial owner. QoS0 shared responses
have no request IDs, so we verify address/status/size and timestamp, reject
timeouts and record remaining same-address ambiguity. Do NOT claim ISR atomicity.
"""
from __future__ import annotations
import argparse
from collections import Counter
import json
import os
from pathlib import Path
from queue import Empty,Queue
import re
import statistics
import sys
import threading
import time

NATIVE_CONFIG=Path("/opt/optolink/settings_ini.py")
VALID_ID="20c2000300000103"
IDENTITY="read;0x00f8;8"
CHECKS=("read;0x27a0;1","read;0x27b0;1","read;0x7342;1",
        "read;0x5738;1")
FULL_RX="request;3;0x1640;32"
RX="request;3;0x164b;32"
META="request;3;0x164c;32"
MASTER="request;3;0x161a;32"
ALLOWED={
 IDENTITY:(0xf8,8),CHECKS[0]:(0x27a0,1),CHECKS[1]:(0x27b0,1),
 CHECKS[2]:(0x7342,1),CHECKS[3]:(0x5738,1),
 FULL_RX:(0x1640,32),RX:(0x164b,32),META:(0x164c,32),MASTER:(0x161a,32),
 "read;0x0a5c;4":(0x0a5c,4),"read;0x089c;1":(0x089c,1),
}
VS1_ONLY={IDENTITY,*CHECKS}
P300_ONLY={IDENTITY,*CHECKS,FULL_RX,RX,META,MASTER,"read;0x0a5c;4","read;0x089c;1"}
RESPONSE=re.compile(r"^(\d+);(?:0x)?([a-fA-F0-9]+);([0-9a-fA-F]*)$")


class Refused(RuntimeError):pass


def decode(cmd,body:str):
    if cmd not in ALLOWED:raise Refused("not an approved P300/VS1 read")
    if type(body) is not str or len(body)>160:raise Refused("unexpected MQTT packet")
    m=RESPONSE.fullmatch(body.strip())
    if not m:raise Refused("unparsable response")
    if int(m[1])!=1:raise Refused("controller returned error status")
    addr=int(m[2],16)
    if addr!=ALLOWED[cmd][0]:raise Refused("mismatched request address")
    try:payload=bytes.fromhex(m[3])
    except ValueError as exc:raise Refused("non-hex reply") from exc
    if len(payload)!=ALLOWED[cmd][1]:raise Refused("partial or oversized read")
    return payload.hex()


def assert_protocol(p300:bool,filename=NATIVE_CONFIG):
    if os.geteuid()!=0 and p300:raise Refused("native P300 requires root")
    if filename.is_symlink() or not filename.is_file():
        raise Refused("missing actual existing configuration")
    import ast
    assignments=[]
    for n in ast.parse(filename.read_text(encoding="utf-8-sig")).body:
        if isinstance(n,ast.Assign):
            for t in n.targets:
                if isinstance(t,ast.Name) and t.id=="vs1protocol":
                    assignments.append(ast.literal_eval(n.value))
    if assignments!=[not p300]:raise Refused("native-vs1 protocol switch not verified")


class BrokerReads:
    def __init__(self,connect_fn,*,clock=time.monotonic):
        self.clock=clock
        self.queue=Queue()
        self.ready=threading.Event()
        self.connector=connect_fn
        self.client=None
        self.request_log=[]
        self.unmatched=Counter()
        self.listen=None
        self.respond=None

    def __enter__(self):
        # Lazy import avoids network access on unit-test discovery.
        directory="/opt/optolink"
        if directory not in sys.path:sys.path.insert(0,directory)
        from c_settings_adapter import settings
        self.listen=settings.mqtt_listen
        self.respond=settings.mqtt_respond
        if self.listen!="openv/cmnd" or self.respond!="openv/resp":
            raise Refused("unknown target MQTT topics")
        self.client=self.connector()
        if self.client is None:raise Refused("MQTT connection failed")
        def received(client,user,msg):
            if msg.topic==self.respond:
                try:raw=msg.payload.decode("ascii")
                except UnicodeError:raw=""
                self.queue.put((self.clock(),raw))
        def subscribed(client,user,mid,reasons,properties=None):
            if reasons and any(getattr(r,"is_failure",False) for r in reasons):
                return
            self.ready.set()
        self.client.on_message=received
        self.client.on_subscribe=subscribed
        rc,_=self.client.subscribe(self.respond,qos=0)
        if rc!=0 or not self.ready.wait(3.0):
            raise Refused("MQTT response subscription not acknowledged")
        return self

    def __exit__(self,*exc):
        if self.client is not None:
            self.client.loop_stop()
            self.client.disconnect()

    def request(self,cmd:str,*,deadline_s=5,clock=None):
        if cmd not in ALLOWED:
            raise Refused("request outside fixed read whitelist")
        now=self.clock if clock is None else clock
        drained=0
        while True:
            try:self.queue.get_nowait();drained+=1
            except Empty:break
        started=now()
        info=self.client.publish(self.listen,cmd,qos=0,retain=False)
        if getattr(info,"rc",1)!=0:raise Refused("MQTT publish failed")
        if hasattr(info,"wait_for_publish"):
            info.wait_for_publish(timeout=2.0)
        received=None;data=None;ignored=[]
        while now()-started<=deadline_s:
            try:moment,raw=self.queue.get(timeout=min(0.1,deadline_s))
            except Empty:continue
            if moment<started:
                ignored.append("old");continue
            if raw.startswith("Error:"):
                raise Refused("splitter reported request error")
            try:payload=decode(cmd,raw)
            except Refused as err:
                # Shared response topic can carry replies for other producers.
                # Fail if the response refers to same requested address or
                # matches address but is malformed; otherwise ignore it.
                m=RESPONSE.fullmatch(raw.strip())
                if m and int(m[2],16)==ALLOWED[cmd][0]:
                    raise
                ignored.append("other");continue
            received=moment;data=payload
            break
        if data is None:
            raise Refused(f"no validated reply within {deadline_s}s for {cmd}")
        self.unmatched.update(ignored)
        row={"command":cmd,"address":f"0x{ALLOWED[cmd][0]:04x}",
             "data":data,"valid_read":True,"controller_read_only":True,
             "mono_start":round(started,6),"mono_response":round(received,6),
             "duration_ms":round((received-started)*1000,3),
             "drained_before":drained,"ignored_other_responses":len(ignored)}
        self.request_log.append(row)
        return row


def capture(client,*,p300:bool,cycles:int):
    if type(cycles) is not int or not 4<=cycles<=32:
        raise Refused("only 4..32 bounded cycles")
    permitted=P300_ONLY if p300 else VS1_ONLY
    def read(c):
        if c not in permitted:raise Refused("command not allowed in this phase")
        return client.request(c)
    ident=read(IDENTITY)
    if ident["data"]!=VALID_ID:raise Refused("wrong WB2A identity")
    before=[read(x) for x in CHECKS]
    if any(row["data"]!="00" for row in before):raise Refused("wrong A0/B0/type/fault state")
    cycles_out=[]
    for i in range(cycles):
        commands=(RX,META,MASTER) if p300 and i%2==0 else (
            (MASTER,META,RX) if p300 else (IDENTITY,CHECKS[i%4]))
        result=[read(c) for c in commands]
        cycles_out.append({"index":i,"rows":result,
                           "all_controller_reads_sequential_not_atomic":True})
    after=[read(c) for c in CHECKS]
    if any(row["data"]!="00" for row in after):raise Refused("controller guard changed")
    final=[read("read;0x0a5c;4"),read("read;0x089c;1")] if p300 else []
    allrows=[ident,*before,*(x for z in cycles_out for x in z["rows"]),*after,*final]
    durations=[r["duration_ms"] for r in allrows]
    return {"mode":"PERSISTENT_MQTT_READONLY_P300" if p300 else "PERSISTENT_MQTT_READONLY_VS1",
            "target":"20C2/0103","cycle_count":cycles,"identity":ident,
            "baseline":before,"cycles":cycles_out,"after":after,"final":final,
            "read_count":len(allrows),"durations_ms":durations,
            "median_request_duration_ms":round(statistics.median(durations),3),
            "p95_request_duration_ms":round(sorted(durations)[int(.95*(len(durations)-1))],3),
            "controller_writes":0,"one_serial_owner":True,
            "mqtt_response_request_id_available":False,
            "identical_address_concurrent_producer_attribution_proven":False,
            "controller_state_atomic":False}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--execute",action="store_true")
    p.add_argument("--mode",choices=("vs1","p300"),default="vs1")
    p.add_argument("--cycles",type=int,default=8)
    p.add_argument("--output",type=Path)
    args=p.parse_args()
    if not args.execute:
        print(json.dumps({"mode":"DRY_RUN","p300_reads":sorted(P300_ONLY),
                          "vs1_reads":sorted(VS1_ONLY),"controller_writes":0},indent=2))
        return
    if not args.output or not str(args.output).startswith("/tmp/wb2a-vitotrol-persistent-"):
        p.error("requires private /tmp/wb2a-vitotrol-persistent-* output")
    p300=args.mode=="p300"
    assert_protocol(p300)
    if "/opt/optolink" not in sys.path:
        sys.path.insert(0,"/opt/optolink")
    from homeassistant_publish import connect_mqtt
    with BrokerReads(lambda:connect_mqtt(retries=1,delay=1)) as bus:
        report=capture(bus,p300=p300,cycles=args.cycles)
    args.output.write_text(json.dumps(report,indent=2,sort_keys=True)+"\n")
    print(json.dumps({"mode":report["mode"],"reads":report["read_count"],
                      "median_ms":report["median_request_duration_ms"],
                      "p95_ms":report["p95_request_duration_ms"],
                      "writes":0,"path":str(args.output)}))


if __name__=="__main__":main()
