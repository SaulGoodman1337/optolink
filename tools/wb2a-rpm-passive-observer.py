#!/usr/bin/env python3
"""Bounded multi-day passive VS1 MQTT observer: never publishes or opens serial.

This does NOT measure P300 actual fan RPM. It records independently
timestamped, non-retained VS1 telemetry for later short P300 crosschecks.
"""
from __future__ import annotations
import argparse
import ast
from collections import Counter
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import re
import signal
import time

SCHEMA_VERSION = 1
SOURCE = "VS1_MQTT_PUBLISHED_NOT_P300_RPM"
TRACKED = {
    "p06": ("geblaesedrehzahl_gfa_p06",),
    "p09": ("modulation_gfa_p09", "brennermodulation_gfa_p09"),
    "flame": ("brennerstatus", "flamme", "brenner_ein"),
}
MAX_VALUE = 32
MIN_SAMPLE_SECONDS = 5.0
MAX_DURATION_HOURS = 120
MAX_EVENTS = 400000
MAX_BYTES = 60 * 1024 * 1024


def read_config(path: Path):
    """Use AST literals only: never execute the boiler's settings source."""
    found = {}
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for statement in tree.body:
        if isinstance(statement, ast.Assign):
            for target in statement.targets:
                if isinstance(target, ast.Name) and target.id in (
                    "mqtt_broker", "mqtt_user", "mqtt_topic"
                ):
                    found[target.id] = ast.literal_eval(statement.value)
    if (any(not isinstance(found.get(k),str)
            for k in ("mqtt_broker","mqtt_topic"))
            or not re.fullmatch(r"[A-Za-z0-9_.:-]{3,160}",found["mqtt_broker"])
            or not re.fullmatch(r"[A-Za-z0-9_-]{2,40}",found["mqtt_topic"])):
        raise ValueError("literal MQTT broker/topic configuration required")
    host, port_string = found["mqtt_broker"].rsplit(":",1)
    port=int(port_string)
    if not host or not 1 <= port <= 65535:
        raise ValueError("bad broker endpoint")
    user=found.get("mqtt_user","")
    if not isinstance(user,str) or len(user)>512:
        raise ValueError("invalid secret configuration")
    return host,port,found["mqtt_topic"],user


def metric_for_topic(topic: str, root: str):
    if not topic.startswith(root+"/"):
        return None
    leaf=topic[len(root)+1:].lower()
    if "/" in leaf or leaf in ("cmnd","resp"):
        return None
    for kind, aliases in TRACKED.items():
        if leaf in aliases:
            return kind
    return None


def finite_display_value(payload: bytes):
    if not isinstance(payload,bytes) or len(payload)>MAX_VALUE or not payload:
        return None
    try:
        raw=payload.decode("ascii")
    except UnicodeDecodeError:
        return None
    if not re.fullmatch(r"-?[0-9]{1,6}(?:\.[0-9]{1,3})?",raw):
        return None
    number=float(raw)
    if not math.isfinite(number) or abs(number)>100000:
        return None
    return raw


class PassiveRecorder:
    """Return a sample only when fresh, in scope and not too frequent."""
    def __init__(self, root: str):
        self.root = root
        self.last = {}
        self.counts = Counter()
        self.max_p06_published = None
        self.p06_positive_samples = 0

    def record(self, topic: str, payload: bytes, *, retained: bool,
               mono: float, utc: str):
        if retained or type(mono) not in (int,float) or not math.isfinite(mono):
            return None
        kind=metric_for_topic(topic,self.root)
        raw=finite_display_value(payload)
        if kind is None or raw is None:
            return None
        if kind in self.last and mono-self.last[kind]<MIN_SAMPLE_SECONDS:
            return None
        self.last[kind]=mono
        self.counts[kind]+=1
        if kind=="p06":
            current=float(raw)
            self.max_p06_published=(current if self.max_p06_published is None
                                    else max(self.max_p06_published,current))
            self.p06_positive_samples+=int(current>0)
        return {"schema":SCHEMA_VERSION,"source":SOURCE,
                "utc":utc,"monotonic_s":round(mono,3),
                "metric":kind,"value_display":raw,
                "retained":False}


def atomic_json(path: Path, obj):
    tmp=path.with_suffix(".tmp")
    with tmp.open("w",encoding="utf-8") as handle:
        os.chmod(tmp,0o600)
        json.dump(obj,handle,sort_keys=True,indent=2)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp,path)


def protected_directory(path: Path):
    if not path.is_absolute() or str(path).startswith("/tmp/"):
        raise ValueError("absolute non-tmp recording directory required")
    if path.is_symlink():
        raise ValueError("symlink output is forbidden")
    path.mkdir(parents=True,exist_ok=True,mode=0o700)
    st=path.lstat()
    if not path.is_dir() or st.st_uid!=os.geteuid() or (st.st_mode & 0o077):
        raise ValueError("private owner-only output directory required")


def run(settings: Path, out_dir: Path, duration_hours: float,
        *, max_events: int = MAX_EVENTS,max_bytes: int = MAX_BYTES):
    if (not 0 < duration_hours <= MAX_DURATION_HOURS
            or not 1 <= max_events <= MAX_EVENTS
            or not 1024 <= max_bytes <= MAX_BYTES):
        raise ValueError("invalid hard observation limits")
    host,port,root,credentials=read_config(settings)
    protected_directory(out_dir)
    import paho.mqtt.client as mqtt  # imported only in explicit live function
    recorder=PassiveRecorder(root)
    begin=time.monotonic()
    until=begin+duration_hours*3600
    stop=False
    event_count=0
    total_bytes=0
    connected=False
    reason="DURATION_REACHED"
    last_update=0.0
    handle=None
    active_day=None
    def handle_stop(_signum,_frame):
        nonlocal stop,reason
        stop=True
        reason="SIGNAL_STOPPED"
    old_term=signal.signal(signal.SIGTERM,handle_stop)
    old_int=signal.signal(signal.SIGINT,handle_stop)
    client=mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,
                       client_id="wb2a-rpm-passive-"+str(os.getpid()))
    if credentials:
        user,pwd=credentials.split(":",1) if ":" in credentials else (credentials,None)
        client.username_pw_set(user,pwd)
    def on_connect(client,userdata,flags,reason_code,properties):
        nonlocal connected
        connected=reason_code.value==0
        if connected:
            client.subscribe(root+"/#",qos=0)
    def on_disconnect(client,userdata,disconnect_flags,reason_code,properties):
        nonlocal connected
        connected=False
    def on_message(_client,_userdata,msg):
        nonlocal event_count,total_bytes,handle,active_day,stop,reason
        if stop or time.monotonic() >= until:
            return
        utc=datetime.now(timezone.utc).isoformat(timespec="milliseconds")
        item=recorder.record(msg.topic,msg.payload,retained=bool(msg.retain),
                             mono=time.monotonic(),utc=utc)
        if item is None:
            return
        payload=(json.dumps(item,sort_keys=True,separators=(",",":"))+"\n").encode()
        if event_count>=max_events or total_bytes+len(payload)>max_bytes:
            reason="CAPACITY_REACHED"
            stop=True
            return
        day=utc[:10]
        if day!=active_day:
            if handle is not None:
                handle.flush()
                handle.close()
            active_day=day
            target=out_dir/("vs1-"+day+".jsonl")
            fd=os.open(str(target),os.O_WRONLY|os.O_APPEND|os.O_CREAT|os.O_NOFOLLOW,0o600)
            handle=os.fdopen(fd,"ab",buffering=0)
        handle.write(payload)
        event_count+=1
        total_bytes+=len(payload)
    client.on_connect=on_connect
    client.on_disconnect=on_disconnect
    client.on_message=on_message
    progress_path=out_dir/"progress.json"
    def checkpoint(final=False):
        atomic_json(progress_path,{
            "schema":SCHEMA_VERSION,"source":SOURCE,
            "started_monotonic_s":round(begin,3),
            "elapsed_s":round(time.monotonic()-begin,2),
            "remaining_s":max(0,round(until-time.monotonic(),2)),
            "connected":connected,"events":event_count,
            "stored_bytes":total_bytes,"counts":dict(recorder.counts),
            "max_p06_published_display":recorder.max_p06_published,
            "p06_positive_samples":recorder.p06_positive_samples,
            "last_seen_by_kind_monotonic_s":recorder.last,
            "observation_final":final,
            "termination_reason":reason if final else None,
            "p300_actual_rpm_verified":False,
            "serial_connections_opened":0,
            "controller_writes_sent":0,
            "mqtt_publishes_sent":0,
        })
    try:
        checkpoint()
        client.connect(host,port,keepalive=25)
        while not stop and time.monotonic()<until:
            # Passive network I/O only; no MQTT publish, no controller commands.
            code=client.loop(timeout=1.0)
            if code!=mqtt.MQTT_ERR_SUCCESS:
                reason="BROKER_DISCONNECTED"
                break
            if time.monotonic()-last_update>30:
                checkpoint()
                last_update=time.monotonic()
    finally:
        try:
            client.disconnect()
        except Exception:
            pass
        if handle is not None:
            handle.flush()
            os.fsync(handle.fileno())
            handle.close()
        checkpoint(final=True)
        signal.signal(signal.SIGTERM,old_term)
        signal.signal(signal.SIGINT,old_int)
    return 0 if reason in ("DURATION_REACHED","SIGNAL_STOPPED") else 3


def main():
    cli=argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--settings",type=Path,
                     default=Path("/opt/optolink/settings_ini.py"))
    cli.add_argument("--out-dir",type=Path,required=True)
    cli.add_argument("--duration-hours",type=float,default=96.0)
    cli.add_argument("--max-events",type=int,default=MAX_EVENTS)
    cli.add_argument("--max-bytes",type=int,default=MAX_BYTES)
    cli.add_argument("--start",action="store_true")
    args=cli.parse_args()
    if not args.start:
        print("PLAN ONLY: passive MQTT/VS1 recording; no serial or P300 I/O")
        return 0
    return run(args.settings,args.out_dir,args.duration_hours,
               max_events=args.max_events,max_bytes=args.max_bytes)


if __name__=="__main__":
    raise SystemExit(main())
