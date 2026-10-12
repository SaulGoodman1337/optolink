"""Offline pcapng replay: original KM-Bus master and experimental emulator."""
from __future__ import annotations

import ast
import importlib.util
import json
from pathlib import Path
import struct
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]


def import_script(name: str, filename: str):
    path=ROOT/'tools'/filename
    spec=importlib.util.spec_from_file_location(name,path)
    mod=importlib.util.module_from_spec(spec)
    sys.modules[name]=mod
    spec.loader.exec_module(mod)
    return mod


pcap=import_script('wb2a_pcap_audit_test','wb2a-vitotrol-public-pcap-audit.py')
model=import_script('wb2a_model_pcap_test','wb2a-vitotrol-offline.py')
SOURCES=Path('/tmp/wb2a-vitotrol-public-sources-20261010')


def block(code:int,body:bytes)->bytes:
    body+=b'\x00'*((-len(body))%4)
    size=12+len(body)
    return struct.pack('<II',code,size)+body+struct.pack('<I',size)


def ethernet_packet(frame:bytes)->bytes:
    udp=struct.pack('>HHHH',1024,4000,8+len(frame),0)+frame
    ip=struct.pack('>BBHHHBBH4s4s',0x45,0,20+len(udp),0,0x4000,
                   64,17,0,bytes([192,168,0,2]),bytes([192,168,0,3]))
    return (bytes.fromhex('0050b60840a60060371234560800')+
            ip+udp).ljust(60,b'\x00')


def sample_pcap(messages,*,resolution:int=6,linktype:int=1):
    shb=block(0x0a0d0d0a,struct.pack('<IHHq',0x1a2b3c4d,1,0,-1))
    options=struct.pack('<HH',9,1)+bytes([resolution])+b'\x00'*3+struct.pack('<HH',0,0)
    idb=block(1,struct.pack('<HHI',linktype,0,65535)+options)
    payload=b''
    for ticks,frame in messages:
        eth=ethernet_packet(frame)
        payload+=block(6,struct.pack('<IIIII',0,(ticks>>32)&0xffffffff,
                                     ticks&0xffffffff,len(eth),len(eth))+eth)
    return shb+idb+payload


STATUS11=model.append_crc(bytes([0x11,0,0xbf,40,1,1,0x11])+b'\xaa'*31)
STATUS12=model.append_crc(bytes([0x11,0,0xbf,40,2,1,0x12])+b'\xaa'*31)
STATUS1A=model.append_crc(bytes([0x11,0,0xbf,11,2,1,0x1a,0x54,0x2d]))
STATUS1D=model.append_crc(bytes([0x11,0,0xbf,21,1,1,0x1d])+b'\xaa'*12)
PING=bytes.fromhex('1100000801010888')


class PublicPcapAuditTests(unittest.TestCase):
    def test_real_original_master_full_crc_and_new_status_semantics(self):
        file=SOURCES/'original-bus-master-capture.zip'
        if not file.exists():
            self.skipTest('optional public OpenV source archive not present on CI')
        report=pcap.audit_zip('master',file.read_bytes())
        self.assertTrue(report['source_identity_and_integrity_verified'])
        self.assertTrue(report['all_packets_crc_valid'])
        self.assertEqual(report['total_validated_km_bus_udp_packets'],5269)
        self.assertEqual(report['class_direction_command_counts']['1100bf'],326)
        self.assertEqual(report['master_class11_bf_record_counts'],{'11':180,'1d':146})
        self.assertEqual(report['master_class11_bf_record_lengths'],{'11/40':180,'1d/21':146})
        self.assertEqual(report['master_class11_f8_discovery_slots'],{'2':76,'3':76})
        self.assertEqual(report['class11_ping_count'],681)
        self.assertEqual(report['frames_from_slave_class11'],0)
        self.assertLess(report['master_bf11_to_next_ping_ethernet_gap_s']['median'],.1)
        self.assertFalse(report['physical_km_bus_waveform_or_response_deadline_proven'])
        self.assertFalse(report['controller_write_authorized'])

    def test_real_emulated_remote_capture_source_and_replay_478_master_records(self):
        file=SOURCES/'kmbus-captures.zip'
        if not file.exists():
            self.skipTest('optional public OpenV source archive not present on CI')
        import zipfile
        with zipfile.ZipFile(file) as z:
            frames=pcap.parse_pcapng(z.read(pcap.SOURCE['emulator']['member']))
        report=pcap.audit_zip('emulator',file.read_bytes())
        self.assertEqual(report['total_validated_km_bus_udp_packets'],701)
        self.assertEqual(report['class_direction_command_counts'],{'0011bf':223,'1100bf':478})
        self.assertEqual(report['master_class11_bf_record_counts'],
                         {'11':24,'12':111,'1a':277,'1d':33,'1e':33})
        self.assertEqual(report['frames_from_slave_class11'],223)
        self.assertEqual(report['source_class11_bf_record_counts'],{'16':223})
        self.assertEqual(report['source_class11_bf_record_lengths'],{'16/12':223})
        checked_16=0
        for captured in frames:
            b=captured.km_bus
            if b[:3]!=bytes.fromhex('0011bf'):
                continue
            data=model.decode_candidate_slave_record_16(b)
            self.assertEqual(data['record'],0x16)
            self.assertEqual(data['slot'],2)
            self.assertFalse(data['command_semantics_verified_for_wb2a'])
            self.assertFalse(data['controller_write_authorized'])
            checked_16+=1
        self.assertEqual(checked_16,223)
        self.assertFalse(report['local_wb2a_capture'])
        emulators={s:model.OfflineVitotrolState(slot=s) for s in (1,2)}
        counters={}
        for frame in frames:
            b=frame.km_bus
            if b[:3]!=bytes.fromhex('1100bf'):
                continue
            expected=model.decode_master_status(b)
            slot=b[4]
            self.assertEqual(expected['slot'],slot)
            self.assertFalse(expected['decoded_status_verified'])
            self.assertIsNone(emulators[slot].respond(b,at_s=frame.timestamp_s))
            counters[b[6]]=counters.get(b[6],0)+1
        self.assertEqual(sum(counters.values()),478)
        self.assertFalse(report['safe_optolink_internal_vitotrol_injection_proven'])

    def test_full_public_master_capture_replay_only_answers_slot2_discovery(self):
        file=SOURCES/'original-bus-master-capture.zip'
        if not file.exists():
            self.skipTest('optional public OpenV source archive not present on CI')
        import zipfile
        with zipfile.ZipFile(file) as z:
            frames=pcap.parse_pcapng(z.read(pcap.SOURCE['master']['member']))
        v=model.OfflineVitotrolState(slot=2,identity=model.IDENTITY_V200)
        answered=[]
        for capture in frames:
            out=v.respond(capture.km_bus,at_s=capture.timestamp_s)
            if out is not None:
                answered.append((capture.km_bus,out))
        # This is a *synthetic* response model, not a KM-Bus slave.
        self.assertEqual(len(answered),76)
        self.assertTrue(all(input[:3]==bytes.fromhex('110033')
                            and input[4]==2 for input,_ in answered))
        self.assertTrue(all(model.decode_candidate_slave_reply(output)['slot']==2
                            for _,output in answered))
        self.assertTrue(v.discovered)
        self.assertIsNone(v.temperature)
        self.assertFalse(any(input[4] != 2 for input,_ in answered))

    def test_sample_source_backed_master_status_is_opaque_not_write(self):
        for slot,frame in [(1,STATUS11),(2,STATUS12),(2,STATUS1A),(1,STATUS1D)]:
            with self.subTest(slot=slot,record=frame[6]):
                result=model.decode_master_status(frame)
                self.assertEqual(result['record'],frame[6])
                self.assertFalse(result['decoded_status_verified'])
                v=model.OfflineVitotrolState(slot=slot)
                self.assertIsNone(v.respond(frame,at_s=8.0))
                self.assertFalse(v.discovered)
                self.assertIsNone(v.temperature)
        with self.assertRaises(model.FrameRejected):
            model.decode_master_status(model.append_crc(
                bytes([0x11,0,0xbf,11,1,1,0x11,0,0])))
        with self.assertRaises(model.FrameRejected):
            model.decode_master_status(model.append_crc(
                bytes([0x11,0,0xbf,40,2,1,0x1a])+b'\xaa'*31))

    def test_public_slot2_control_record_exact_crc_and_no_write(self):
        # Raw 2018 third-party emulated TX, NOT verified original WB2A RX.
        frame=bytes.fromhex('0011bf0c020116aaaa4dc1a8')
        o=model.decode_candidate_slave_record_16(frame)
        self.assertEqual(o['xor_decoded_payload_hex'],'0000e7')
        self.assertEqual(o['record'],0x16)
        self.assertFalse(o['controller_write_authorized'])
        self.assertFalse(o['command_semantics_verified_for_wb2a'])
        with self.assertRaises(model.FrameRejected):
            model.decode_candidate_slave_record_15(frame)
        bad=bytearray(frame);bad[-1]^=1
        with self.assertRaises(model.FrameRejected):
            model.decode_candidate_slave_record_16(bytes(bad))
        # Forged slot 1 with correct CRC is not a valid slot-2 record.
        wrong=model.append_crc(frame[:4]+bytes([1])+frame[5:-2])
        with self.assertRaises(model.FrameRejected):
            model.decode_candidate_slave_record_16(wrong)

    def test_both_timestamp_resolutions_and_ethernet_padding(self):
        for res,mul in [(6,1_000_000),(9,1_000_000_000)]:
            b=sample_pcap([(mul,PING),(mul+mul//4,STATUS11)],resolution=res)
            rows=pcap.parse_pcapng(b)
            self.assertEqual([r.km_bus for r in rows],[PING,STATUS11])
            self.assertEqual([r.timestamp_s for r in rows],[1.0,1.25])
            report=pcap.audit_frames(rows)
            self.assertEqual(report['master_class11_bf_record_counts'],{'11':1})
            self.assertEqual(report['class11_ping_count'],1)
            self.assertFalse(report['local_wb2a_capture'])

    def test_corrupt_crc_and_length_trailer_rejected(self):
        good=sample_pcap([(1_000_000,PING),(1_200_000,STATUS11)])
        flipped=bytearray(good)
        pos=good.index(STATUS11)
        flipped[pos+7]^=1
        with self.assertRaisesRegex(pcap.PcapRejected,'CRC'):
            pcap.parse_pcapng(bytes(flipped))
        flipped=bytearray(good)
        flipped[-1]^=1
        with self.assertRaisesRegex(pcap.PcapRejected,'trailer'):
            pcap.parse_pcapng(bytes(flipped))
        with self.assertRaises(pcap.PcapRejected):
            pcap.parse_pcapng(good[:-1])

    def test_reject_truncated_frame_bad_udp_lengths_and_nonmonotonic_pcap(self):
        good=sample_pcap([(1_000_000,PING),(1_250_000,STATUS11)])
        for wrong in (None,'bad',True,good[:40]):
            with self.subTest(wrong=repr(wrong)[:18]),self.assertRaises(pcap.PcapRejected):
                pcap.parse_pcapng(wrong)
        bad=bytearray(good)
        # For first synthetic IP packet, corrupt UDP datagram size.
        ptr=bad.index(PING)
        struct.pack_into('>H',bad,ptr-4,17)
        with self.assertRaises(pcap.PcapRejected):
            pcap.parse_pcapng(bytes(bad))
        backwards=sample_pcap([(2_000_000,PING),(1_000_000,STATUS11)])
        with self.assertRaisesRegex(pcap.PcapRejected,'non-monotonic'):
            pcap.parse_pcapng(backwards)

    def test_reject_unsupported_interface_resolution_duplicate_idb_and_untrusted_zip(self):
        for blob in (sample_pcap([(1_000_000,PING)],resolution=11),
                     sample_pcap([(1_000_000,PING)],linktype=147)):
            with self.assertRaises(pcap.PcapRejected):
                pcap.parse_pcapng(blob)
        good=sample_pcap([(1_000_000,PING)])
        # Insert a second interface before the first packet.
        second_idb=block(1,struct.pack('<HHI',1,0,65535))
        headlen=struct.unpack_from('<I',good,4)[0]
        idblen=struct.unpack_from('<I',good,headlen+4)[0]
        both=good[:headlen+idblen]+second_idb+good[headlen+idblen:]
        with self.assertRaisesRegex(pcap.PcapRejected,'repeated interface'):
            pcap.parse_pcapng(both)
        with self.assertRaisesRegex(pcap.PcapRejected,'SHA'):
            pcap.audit_zip('master',good)
        with self.assertRaises(pcap.PcapRejected):
            pcap.audit_zip('other',good)

    def test_public_decoder_has_no_transport_or_controller_write_paths(self):
        src=ast.parse((ROOT/'tools'/'wb2a-vitotrol-public-pcap-audit.py').read_text())
        modules=set()
        for n in ast.walk(src):
            if isinstance(n,ast.Import):
                modules.update(alias.name.split('.')[0] for alias in n.names)
            if isinstance(n,ast.ImportFrom) and n.module:
                modules.add(n.module.split('.')[0])
        self.assertFalse(modules & {
            'os','socket','serial','subprocess','requests','paho','ctypes','shutil'
        })


if __name__=="__main__":
    unittest.main()
