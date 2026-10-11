"""Persistent-MQTT read-only instrument; no MQTT/socket/controller in tests."""
from __future__ import annotations
import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest

SRC=Path(__file__).resolve().parents[1]/"tools/wb2a-vitotrol-persistent-mqtt-readonly.py"
spec=importlib.util.spec_from_file_location("wb2a_vt_persist_mqtt_test",SRC)
m=importlib.util.module_from_spec(spec);sys.modules[spec.name]=m
spec.loader.exec_module(m)


class Monotonic:
    def __init__(self):self.t=1000.
    def __call__(self):self.t+=0.005;return self.t


class PublishInfo:
    rc=0
    def wait_for_publish(self,timeout):return True


class FakeClient:
    def __init__(self,clock,custom=None):
        self.clock=clock;self.custom=custom or {}
        self.reads=[];self.connected=True
        self.on_message=None
        self.on_subscribe=None
    def subscribe(self,topic,qos=0):
        self.on_subscribe(self,None,1,[],None)
        return 0,1
    def publish(self,topic,cmd,qos=0,retain=False):
        self.reads.append((topic,cmd))
        if cmd==m.IDENTITY:value=m.VALID_ID
        elif cmd in (m.RX,m.META,m.MASTER):value="00"*32
        elif cmd=="read;0x0a5c;4":value="00000000"
        elif cmd=="read;0x089c;1":value="03"
        else:value="00"
        response=self.custom.get(cmd)
        if response is None:
            response=f"1;0x{m.ALLOWED[cmd][0]:x};{value}"
        self.on_message(self,None,SimpleNamespace(topic="openv/resp",
            payload=response.encode("ascii")))
        return PublishInfo()
    def loop_stop(self):self.connected=False
    def disconnect(self):pass


class FakeSettings:
    mqtt_listen="openv/cmnd"
    mqtt_respond="openv/resp"


class Tests(unittest.TestCase):
    def test_whitelist_contains_no_write(self):
        self.assertTrue(all(x.startswith(("read;","request;3;")) for x in m.ALLOWED))
        self.assertEqual(m.ALLOWED[m.RX],(0x164b,32))
        self.assertEqual(m.ALLOWED[m.META],(0x164c,32))

    def test_decode_requires_confirmed_code_address_length(self):
        good=m.decode(m.META,"1;0x164c;"+"00"*32)
        self.assertEqual(len(good),64)
        for bad in ("5;0x164c;"+"00"*32,
                    "1;0x164b;"+"00"*32,
                    "1;0x164c;"+"00"*31,
                    "Error: rejected"):
            with self.subTest(bad=bad[:20]),self.assertRaises(m.Refused):
                m.decode(m.META,bad)

    def test_persistent_single_subscription_and_bounded_cycles(self):
        clock=Monotonic()
        fake=FakeClient(clock)
        old=sys.modules.get("c_settings_adapter")
        sys.modules["c_settings_adapter"]=SimpleNamespace(settings=FakeSettings())
        try:
            with m.BrokerReads(lambda:fake,clock=clock) as broker:
                result=m.capture(broker,p300=True,cycles=4)
        finally:
            if old is None:sys.modules.pop("c_settings_adapter",None)
            else:sys.modules["c_settings_adapter"]=old
        self.assertEqual(result["read_count"],23)
        self.assertEqual(len(fake.reads),23)
        self.assertEqual(result["controller_writes"],0)
        self.assertEqual(result["cycle_count"],4)
        self.assertFalse(result["mqtt_response_request_id_available"])
        self.assertFalse(fake.connected)

    def test_vs1_benchmark_does_not_issue_p300_reads(self):
        clock=Monotonic();fake=FakeClient(clock)
        old=sys.modules.get("c_settings_adapter")
        sys.modules["c_settings_adapter"]=SimpleNamespace(settings=FakeSettings())
        try:
            with m.BrokerReads(lambda:fake,clock=clock) as broker:
                r=m.capture(broker,p300=False,cycles=4)
        finally:
            if old is None:sys.modules.pop("c_settings_adapter",None)
            else:sys.modules["c_settings_adapter"]=old
        self.assertEqual(r["read_count"],17)
        self.assertFalse(any(c.startswith("request;") for _,c in fake.reads))

    def test_malformed_same_address_fails_closed(self):
        clock=Monotonic();fake=FakeClient(clock,custom={m.IDENTITY:"1;0xf8;00"})
        old=sys.modules.get("c_settings_adapter")
        sys.modules["c_settings_adapter"]=SimpleNamespace(settings=FakeSettings())
        try:
            with m.BrokerReads(lambda:fake,clock=clock) as broker:
                with self.assertRaises(m.Refused):
                    broker.request(m.IDENTITY)
        finally:
            if old is None:sys.modules.pop("c_settings_adapter",None)
            else:sys.modules["c_settings_adapter"]=old

    def test_invalid_cycles_or_unknown_requests(self):
        for n in (0,3,33,True,3.5):
            with self.subTest(n=n),self.assertRaises(m.Refused):
                m.capture(SimpleNamespace(request=lambda x:None),p300=True,cycles=n)
        c=m.BrokerReads(lambda:None)
        with self.assertRaises(m.Refused):
            c.request("request;4;0x166a;1;0a")

    def test_vs1_setting_gate_with_temp_file(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            cfg=Path(d)/"settings_ini.py"
            cfg.write_text("vs1protocol = True\n")
            m.assert_protocol(False,cfg)
            cfg.write_text("vs1protocol = False\n")
            with self.assertRaises(m.Refused):
                m.assert_protocol(False,cfg)


if __name__=="__main__":unittest.main()
