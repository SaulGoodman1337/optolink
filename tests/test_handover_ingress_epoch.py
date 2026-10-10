"""Deterministic ingress freeze and burst-buffering tests (no sockets)."""
from __future__ import annotations

from pathlib import Path
import sys
import threading
import time
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
from handover_acceleration.ingress_epoch import IngressEpoch, IngressRejected


class FakeTcpServer:
    def __init__(self,*args,**kwargs):
        self.received_data=""
        self.open=True
    def _listen(self):
        return None
    def get_request(self):
        data=self.received_data
        self.received_data=""
        return data
    def send(self,data):
        pass
    def stop(self):
        self.open=False


class IngressEpochTests(unittest.TestCase):
    def test_fifo_preserves_multiple_tcp_requests(self):
        gate=IngressEpoch()
        server=gate.tcp_class(FakeTcpServer)()
        for text in ("read;f8", "w;2306", "gfaread;4006"):
            server.received_data=text
        self.assertEqual(server.pending_count(),3)
        self.assertEqual([server.get_request() for _ in range(4)],
                         ["read;f8","w;2306","gfaread;4006",""])
        self.assertFalse(gate.tcp_overflow)

    def test_queue_overflow_does_not_overwrite_preceding_commands(self):
        gate=IngressEpoch(max_tcp_queue=2)
        server=gate.tcp_class(FakeTcpServer)()
        server.received_data="req-a"
        server.received_data="req-b"
        with self.assertRaisesRegex(IngressRejected,"overflow"):
            server.received_data="req-c"
        self.assertTrue(gate.tcp_overflow)
        self.assertEqual(server.get_request(),"req-a")
        self.assertEqual(server.get_request(),"req-b")

    def test_mqtt_callback_blocks_for_entire_p300_epoch(self):
        gate=IngressEpoch()
        started=threading.Event()
        done=threading.Event()
        observed=[]
        def callback(message):
            observed.append(message)
            done.set()
        cb=gate.wrap_mqtt_callback(callback)
        def other():
            started.set()
            cb("delayed-write")
        with gate.freeze():
            worker=threading.Thread(target=other,daemon=True)
            worker.start()
            self.assertTrue(started.wait(1))
            self.assertFalse(done.wait(.08))
            self.assertEqual(observed,[])
        self.assertTrue(done.wait(2))
        self.assertEqual(observed,["delayed-write"])
        worker.join(timeout=2)

    def test_tcp_acceptance_and_special_command_blocked(self):
        gate=IngressEpoch()
        server=gate.tcp_class(FakeTcpServer)()
        entered=threading.Event()
        done=threading.Event()
        specials=[]
        wrapped=gate.wrap_tcp_command(lambda cmd,source:specials.append((cmd,source)))
        def network():
            entered.set()
            server.received_data="w;0x2306;1;20"
            wrapped("reloadini",2)
            done.set()
        with gate.freeze():
            worker=threading.Thread(target=network,daemon=True)
            worker.start()
            self.assertTrue(entered.wait(1))
            self.assertFalse(done.wait(.08))
            self.assertEqual(server.pending_count(),0)
        self.assertTrue(done.wait(2))
        self.assertEqual(server.get_request(),"w;0x2306;1;20")
        self.assertEqual(specials,[("reloadini",2)])
        worker.join(timeout=2)

    def test_no_second_mainloop_or_nested_freeze(self):
        gate=IngressEpoch()
        with gate.freeze():
            with self.assertRaisesRegex(IngressRejected,"nested"):
                with gate.freeze():
                    pass
        exc=[]
        def worker():
            try:
                with gate.freeze(): pass
            except Exception as e: exc.append(e)
        t=threading.Thread(target=worker)
        t.start();t.join(2)
        self.assertEqual(len(exc),1)
        self.assertIsInstance(exc[0],IngressRejected)

    def test_callback_exception_does_not_leave_gate_frozen(self):
        gate=IngressEpoch()
        cb=gate.wrap_mqtt_callback(lambda _:1/0)
        with self.assertRaises(ZeroDivisionError):cb("x")
        with gate.freeze():pass
        self.assertEqual(gate.freeze_depth,0)

    def test_parallel_mqtt_tcp_write_readback_bursts_are_fenced_and_preserved(self):
        """Synthetic write commands: never open a controller or dispatch a frame."""
        gate=IngressEpoch(max_tcp_queue=64)
        tcp=gate.tcp_class(FakeTcpServer)()
        observed=[]
        cb=gate.wrap_mqtt_callback(
            lambda msg: observed.append(("mqtt",msg)))
        mqtt=[f"w;0x2303;1;{i};False" for i in range(25)]
        incoming=[f"gfaread;0x4006;1;raw;False;{i}" for i in range(25)]
        ready=[threading.Event(),threading.Event()]
        def mqtt_producer():
            ready[0].set()
            for msg in mqtt:
                cb(msg)
        def tcp_producer():
            ready[1].set()
            for msg in incoming:
                tcp.received_data=msg
        with gate.freeze():
            a=threading.Thread(target=mqtt_producer)
            b=threading.Thread(target=tcp_producer)
            a.start();b.start()
            self.assertTrue(ready[0].wait(2))
            self.assertTrue(ready[1].wait(2))
            self.assertEqual(tcp.pending_count(),0)
            self.assertEqual(observed,[])
        a.join(timeout=2);b.join(timeout=2)
        self.assertFalse(a.is_alive())
        self.assertFalse(b.is_alive())
        self.assertEqual([msg for _,msg in observed],mqtt)
        self.assertEqual(tcp.pending_count(),len(incoming))
        self.assertEqual([tcp.get_request() for _ in incoming],incoming)
        self.assertFalse(gate.tcp_overflow)
        self.assertEqual(gate.freeze_depth,0)

    def test_unreviewed_tcp_contract_rejected(self):
        gate=IngressEpoch()
        for wrong in (object, lambda *a:None):
            with self.subTest(wrong=wrong),self.assertRaises(IngressRejected):
                gate.tcp_class(wrong)


if __name__=="__main__":
    unittest.main()
