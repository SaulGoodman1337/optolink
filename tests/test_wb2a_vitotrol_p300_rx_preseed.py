"""Offline negative/positive regression for native P300 preseed experiment."""
import importlib.util
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

path=Path(__file__).resolve().parents[1]/"tools/wb2a-vitotrol-p300-rx-preseed.py"
sp=importlib.util.spec_from_file_location("preseed_test",path)
m=importlib.util.module_from_spec(sp)
sys.modules[sp.name]=m
sp.loader.exec_module(m)
b=m.bridge
ORIGINAL=bytes.fromhex("00000001b10a010110fe23d8fa01fb0122d1")+bytes(14)
TX=bytes.fromhex("1100330a0101f80449ef").ljust(32,b"\x00")
D1=bytearray(32)
D1[11]=1
D1[13:17]=bytes.fromhex("42160afe")
D2=bytearray(32)
D2[10:13]=bytes.fromhex("060001")


class FakeP300:
    def __init__(self):
        self.virtual={0x27a0:b"\x00",0x27b0:b"\x00",0x7342:b"\x00",
                      0x0a5c:bytes(4),0x0896:bytes.fromhex("c800"),
                      0x089c:b"\x03",0x5738:b"\x00"}
        self.rx=bytearray(ORIGINAL)
        self.writes=[]
        self.fail_on=None
        self.snapshots=0

    def read(self,addr,n):
        if (addr,n)==(0x00f8,8):return b.DEVICE
        return self.virtual[addr]

    def physical_read(self):
        return bytes(self.rx)

    def request(self,request,addr):
        expect=f"request;3;0x{addr:04x};32"
        if request!=expect:
            raise AssertionError("unexpected P300 request")
        if addr==0x161a:return b.Response(1,addr,TX)
        if addr==0x1640:
            self.snapshots+=1
            return b.Response(1,addr,bytes(self.rx))
        if addr==0x0b60:return b.Response(1,addr,bytes(D1))
        if addr==0x1660:return b.Response(1,addr,bytes(D2))
        raise AssertionError("unexpected physical address")

    def write_config(self,addr,value):
        self.writes.append(("code",addr,value))
        self.virtual[addr]=bytes([value])

    def physical_write(self,addr,data):
        if self.fail_on=="physical":
            self.fail_on=None
            raise b.BridgeRejected("intentional test injection failure")
        assert addr==0x1642
        self.writes.append(("rx",addr,bytes(data)))
        self.rx[2:2+len(data)]=data


class PreseedTests(unittest.TestCase):
    def test_strict_synthetic_valid_frame_parse(self):
        self.assertEqual(m.compact_frame(TX)["frame_at_zero"],
                         "1100330a0101f80449ef")
        self.assertIsNone(m.compact_frame(bytes(32))["frame_at_zero"])
        raw=bytearray(TX);raw[-1]^=1
        self.assertIsNone(m.compact_frame(bytes(raw))["frame_at_two"])
        with self.assertRaises(b.BridgeRejected):
            m.compact_frame(bytes(31))

    def test_response_present_before_remote_configuration_and_full_restore(self):
        c=FakeP300()
        report=m.PreseedProbe(c,now=lambda:1.0,sleep=lambda _:None).run(
            count=3,configure_type=True)
        self.assertFalse(report["remote_accepted_by_regulator"])
        self.assertTrue(report["rx_physical_write_readback_exact"])
        self.assertEqual(len(report["live_snapshots"]),3)
        self.assertTrue(report["restore_ok"])
        self.assertFalse(report["controller_rx_isr_or_parser_invocation_proven"])
        self.assertEqual(bytes(c.rx),ORIGINAL)
        self.assertEqual([x[:2] for x in c.writes[:4]],
                         [("rx",0x1642),("code",0x7342),("code",0x27a0),
                          ("code",0x27b0)])
        self.assertEqual(report["live_snapshots"][0]["rx_descriptor_index"],"01")
        self.assertEqual(report["live_snapshots"][0]["rx_descriptor"],"42160afe")
        self.assertEqual(report["live_snapshots"][0]["rx_metadata"],"060001")
        self.assertEqual(report["live_snapshots"][0]["master_tx"]["frame_at_zero"],
                         TX[:10].hex())
        self.assertEqual(report["live_snapshots"][0]["rx_candidate"]["frame_at_two"],
                         b.FRAME_ORIGINAL_B3.hex())
        self.assertEqual(report["a0_remote_model_expected"],"02")
        self.assertEqual(report["live_snapshots"][0]["virtual"]["a0"],"02")
        self.assertEqual(report["after_restore"]["a0"],"00")
        self.assertEqual(report["after_restore"]["b0"],"00")

    def test_fault_during_preseed_still_restores_baseline(self):
        c=FakeP300();c.fail_on="physical"
        with self.assertRaises(b.BridgeRejected):
            m.PreseedProbe(c).run(count=1)
        self.assertEqual(bytes(c.rx),ORIGINAL)
        self.assertEqual(c.virtual[0x27a0],b"\x00")

    def test_strict_bounded_samples(self):
        c=FakeP300()
        p=m.PreseedProbe(c)
        for num in (-1,0,17,True,"8"):
            with self.subTest(num=num),self.assertRaises(b.BridgeRejected):
                p.run(count=num)
        for delay in (-.1,3.5,False,"0.2"):
            with self.subTest(delay=delay),self.assertRaises(b.BridgeRejected):
                p.run(count=1,gap_s=delay)
        self.assertEqual(c.writes,[])

    def test_preseed_is_not_considered_participant_acceptance(self):
        c=FakeP300()
        c.virtual[0x7342]=b"\x00"
        state=m.PreseedProbe(c,now=lambda:0.0).run(count=1)
        self.assertEqual(state["baseline_virtual"]["swindex"],"00000000")
        self.assertEqual(state["active_final_virtual"]["room_raw"],"c800")
        self.assertFalse(state["remote_accepted_by_regulator"])

    def test_only_matched_v200_and_v300_codings(self):
        self.assertEqual(m.VALID_VARIANTS["v300_original"][0],2)
        self.assertEqual(m.VALID_VARIANTS["v200_reference"][0],1)
        self.assertEqual(b.model.decode_candidate_slave_reply(
            m.VALID_VARIANTS["v300_original"][1])["identity_bytes"],"1138010a")
        self.assertEqual(b.model.decode_candidate_slave_reply(
            m.VALID_VARIANTS["v200_reference"][1])["identity_bytes"],"11340005")
        c=FakeP300()
        result=m.PreseedProbe(c,now=lambda:1.0,sleep=lambda _:None).run(
            count=1,variant="v200_reference")
        self.assertEqual(result["a0_remote_model_expected"],"01")
        self.assertEqual(result["live_snapshots"][0]["virtual"]["a0"],"01")
        self.assertFalse(result["remote_accepted_by_regulator"])
        self.assertEqual(bytes(c.rx),ORIGINAL)
        with self.assertRaises(b.BridgeRejected):
            m.PreseedProbe(c).run(count=1,variant="invented")

    def test_device_list_strict(self):
        self.assertEqual(m.FIXED_RAM,(0x161a,0x1640,0x0b60,0x1660))
        self.assertEqual(m.RX_TAG,0x1642)
        self.assertEqual(m.MAX_SNAPSHOTS,16)


if __name__=="__main__":
    unittest.main()
