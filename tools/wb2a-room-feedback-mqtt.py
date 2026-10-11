#!/usr/bin/env python3
"""Experimental Optolink-only closed-loop room-temperature compensation.

This is NOT a KM-bus Vitotrol. Measured home room temperature is obtained
from an explicit, non-retained MQTT sensor topic and used to adjust the
WB2A EXTERNAL NORMAL ROOM SETPOINT 0x2321 (not the observed room-sensor
0x0896). It has not been long-term qualified for unattended heating control.

No serial port, protocol switch, unknown SRAM address, SFR, or direct
burner/pump manipulation. An INDEPENDENT reset mechanism is required before
--execute because the external room setpoint might survive a host crash.
Do not enable until a genuine current MQTT sensor source has been proven.
"""
from __future__ import annotations

import argparse
from collections import deque
from dataclasses import dataclass
import importlib.util
import json
import math
from pathlib import Path
import queue
import re
import runpy
import sys
import time

SRC=Path(__file__).resolve().parent
SPEC=importlib.util.spec_from_file_location(
    'wb2a_external_room_actuator_mqtt',
    SRC/'wb2a-external-room-influence.py')
if SPEC is None or SPEC.loader is None:
    raise RuntimeError('external-room actuator missing')
actuator=importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name]=actuator
SPEC.loader.exec_module(actuator)

MAX_SENSOR_AGE_S=90.0
MIN_REWRITE_S=25.0
MAX_DURATION_S=3600.0


class FeedbackRejected(RuntimeError):
    pass


@dataclass(frozen=True)
class RoomSample:
    temperature_c: float
    at_monotonic_s: float


def decode_live_sensor(payload: bytes, *,
                       retained: bool, at_s: float) -> RoomSample:
    """Only fresh non-retained numeric samples; refuse stale retained MQTT."""
    if (type(payload) is not bytes or len(payload)>140
            or not math.isfinite(at_s) or type(retained) is not bool):
        raise FeedbackRejected('bounded sensor input required')
    if retained:
        raise FeedbackRejected('retained message has no verified freshness')
    try:
        text=payload.decode('utf-8')
        if re.fullmatch(r'\s*[+-]?(?:\d+(?:\.\d+)?|\.\d+)\s*',text):
            value=float(text)
        else:
            obj=json.loads(text)
            if type(obj) is not dict or set(obj)!={'temperature'}:
                raise FeedbackRejected('only temperature JSON key accepted')
            value=obj['temperature']
    except (UnicodeDecodeError,ValueError,json.JSONDecodeError) as exc:
        raise FeedbackRejected('unsupported sensor payload') from exc
    if type(value) not in (float,int) or not math.isfinite(value) or not 10<=value<=32:
        raise FeedbackRejected('implausible or nonnumeric room temperature')
    return RoomSample(float(value),at_s)


class FeedbackCore:
    """No broker dependency; one owner, fixed actuator, safe stale-data restore."""
    def __init__(self,client,*,now=time.monotonic):
        self.client=client
        self.now=now
        self.target_c=None
        self.last_command=0
        self.last_written_at=None
        self.last_sample=None
        self.active=False
        self.events=deque(maxlen=120)
        self.ended=False

    def preflight(self):
        if self.active or self.ended:
            raise FeedbackRejected('one bounded experiment only')
        if self.client.read(0x00f8,8)!=actuator.ID:
            raise FeedbackRejected('wrong boiler firmware')
        if (self.client.read(0x27A0,1)!=b'\x00'
            or self.client.read(0x27B0,1)!=b'\x00'):
            raise FeedbackRejected('real Vitotrol/room influence configured')
        if self.client.read(actuator.EXTERNAL_ROOM_SETPOINT,1)!=b'\x00':
            raise FeedbackRejected('some other process owns external setpoint')
        if self.client.read(actuator.CURRENT_FAULT,1)!=b'\x00':
            raise FeedbackRejected('active boiler fault')
        nominal=self.client.read(actuator.NORMAL_ROOM_SETPOINT,1)
        if len(nominal)!=1 or not 17<=nominal[0]<=24:
            raise FeedbackRejected('normal room target outside bounded range')
        self.target_c=float(nominal[0])
        self.active=True
        self.events.append({'event':'baseline',
                            'normal_target_c':self.target_c})
        return self.target_c

    def update(self,sample:RoomSample):
        if not self.active or self.ended:
            raise FeedbackRejected('controller not active')
        if type(sample) is not RoomSample or not 10<=sample.temperature_c<=32:
            raise FeedbackRejected('invalid sample object')
        if sample.at_monotonic_s>self.now()+2:
            raise FeedbackRejected('future timestamp')
        self.last_sample=sample

    def tick(self):
        if not self.active or self.ended:
            raise FeedbackRejected('controller inactive')
        now=self.now()
        if (self.last_sample is None or
            now-self.last_sample.at_monotonic_s>MAX_SENSOR_AGE_S or
            now<self.last_sample.at_monotonic_s-2):
            if self.last_command:
                self.release()
            self.events.append({'event':'no_fresh_sensor'})
            return False
        if (self.last_written_at is not None
            and now-self.last_written_at<MIN_REWRITE_S):
            return False
        if (self.client.read(actuator.CURRENT_FAULT,1)!=b'\x00' or
            self.client.read(actuator.NORMAL_ROOM_SETPOINT,1)!=bytes((int(self.target_c),)) or
            self.client.read(0x27A0,1)!=b'\x00' or
            self.client.read(0x27B0,1)!=b'\x00'):
            self.release()
            raise FeedbackRejected('controller state changed, override released')
        currently=self.client.read(actuator.EXTERNAL_ROOM_SETPOINT,1)
        if currently !=bytes((self.last_command,)):
            self.last_command=0
            self.ended=True
            raise FeedbackRejected('external setpoint taken over by another controller')
        desired=actuator.compute_external_setpoint(
            self.target_c,self.last_sample.temperature_c)
        # Avoid unbounded jumps after sensor spikes; at most 1 whole C
        # per feedback update. If unchanged, no rewrite needed.
        if self.last_command:
            desired=max(self.last_command-1,min(self.last_command+1,desired))
        if desired==self.last_command:
            self.last_written_at=now
            return False
        # Treat any begun write as possibly applied, even when MQTT reply
        # times out or the first readback fails. Cleanup must never assume
        # that last_command is still the old (possibly zero) value.
        self.last_command=desired
        try:
            self.client.write_external(desired)
            if self.client.read(actuator.EXTERNAL_ROOM_SETPOINT,1)!=bytes((desired,)):
                raise FeedbackRejected('control write/readback mismatch')
        except Exception as original_error:
            try:
                self.release()
            except Exception as recovery_error:
                raise FeedbackRejected(
                    'write/readback failed and restore unverified: '+
                    str(recovery_error)) from original_error
            raise
        self.last_written_at=now
        self.events.append({'event':'applied',
                            'room_c':self.last_sample.temperature_c,
                            'normal_target_c':self.target_c,
                            'external_setpoint_c':desired})
        return True

    def release(self):
        # Only release a known value that the experiment itself wrote.
        if self.last_command:
            self.client.write_external(0)
            if self.client.read(actuator.EXTERNAL_ROOM_SETPOINT,1)!=b'\x00':
                raise FeedbackRejected('restore readback not zero')
            self.events.append({'event':'released',
                                'last_external_setpoint_c':self.last_command})
        self.last_command=0
        self.last_written_at=None

    def shutdown(self):
        try:
            self.release()
        finally:
            self.active=False
            self.ended=True


def _settings(path:Path):
    if path.is_symlink() or not path.is_file():
        raise FeedbackRejected('regular known settings file required')
    d=runpy.run_path(str(path))
    broker=d.get('mqtt_broker')
    userpass=d.get('mqtt_user')
    if type(broker) is not str or ':' not in broker:
        raise FeedbackRejected('MQTT broker not configured')
    host,port=broker.rsplit(':',1)
    if not re.fullmatch(r'[a-zA-Z0-9.\-]+',host) or not port.isdigit():
        raise FeedbackRejected('bad broker address')
    if type(userpass) is not str or ':' not in userpass:
        raise FeedbackRejected('MQTT credentials unavailable')
    username,password=userpass.split(':',1)
    return host,int(port),username,password


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--sensor-topic',required=True)
    p.add_argument('--settings',type=Path,
                   default=Path('/opt/optolink/settings_ini.py'))
    p.add_argument('--duration-seconds',type=float,default=600)
    p.add_argument('--execute',action='store_true')
    p.add_argument('--independent-restore-armed',action='store_true')
    args=p.parse_args()
    if not re.fullmatch(r'[a-zA-Z0-9_\-/]{1,150}',args.sensor_topic):
        p.error('explicit exact MQTT topic without wildcards required')
    if (not math.isfinite(args.duration_seconds) or
        not 60<=args.duration_seconds<=MAX_DURATION_S):
        p.error('bounded 60..3600 second experiment only')
    if not args.execute:
        print(json.dumps({
           'mode':'CONFIGURATION_DRY_RUN_NO_CONTROLLER_WRITES',
           'sensor_topic':args.sensor_topic,
           'mqtt_sensor_must_be_nonretained_and_live':True,
           'external_room_setpoint_address':'0x2321',
           'real_vitotrol_emulation':False,
           'independent_rollback_required':True},indent=2))
        return 0
    if not args.independent_restore_armed:
        p.error('independent restore is mandatory before execution')
    # Import paho only in the explicitly executing branch.
    from paho.mqtt import client as mqtt
    host,port,user,password=_settings(args.settings)
    samples=queue.Queue(maxsize=10)
    broker=mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
                       client_id='wb2a-room-feedback-optolink-20261011')
    broker.username_pw_set(user,password)
    connected=False
    def on_connect(cl,_u,_f,rc,_p):
        nonlocal connected
        connected=rc==0
        if connected:cl.subscribe(args.sensor_topic,qos=0)
    def on_disconnect(cl,_u,_f,_rc,_p):
        nonlocal connected
        connected=False
    def on_message(_cl,_u,msg):
        if msg.topic!=args.sensor_topic:return
        try:
            sample=decode_live_sensor(msg.payload,retained=msg.retain,
                                      at_s=time.monotonic())
        except FeedbackRejected:
            return
        try:
            samples.put_nowait(sample)
        except queue.Full:
            # Drop outdated samples, never queue stale commands.
            try:samples.get_nowait()
            except queue.Empty:pass
            samples.put_nowait(sample)
    broker.on_connect=on_connect
    broker.on_disconnect=on_disconnect
    broker.on_message=on_message
    core=FeedbackCore(actuator.NativeOptolinkClient())
    core.preflight()
    started=time.monotonic()
    try:
        broker.connect(host,port,keepalive=20)
        broker.loop_start()
        while time.monotonic()-started<args.duration_seconds:
            try:
                sample=samples.get(timeout=2)
                core.update(sample)
            except queue.Empty:pass
            if not connected:
                core.release()
            else:
                core.tick()
    finally:
        try:
            core.shutdown()
        finally:
            broker.loop_stop()
            broker.disconnect()
    print(json.dumps({
        'mode':'BOUND_EXPERIMENT_DONE_AND_SETPOINT_RESTORED',
        'vitotrol_registered':False,
        'external_override_restored':True,
        'events':list(core.events),
    },indent=2))
    return 0


if __name__=='__main__':
    raise SystemExit(main())
