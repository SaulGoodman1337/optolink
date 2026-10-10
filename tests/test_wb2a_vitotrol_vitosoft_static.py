"""Real SHA-pinned VitoSoft catalog and synthetic adversarial join tests."""
from __future__ import annotations
import ast
import importlib.util
import json
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'tools'/'wb2a-vitotrol-vitosoft-static.py'
spec=importlib.util.spec_from_file_location('wb2a_vitosoft_static',SOURCE)
m=importlib.util.module_from_spec(spec);sys.modules[spec.name]=m;spec.loader.exec_module(m)
SOURCES=Path('/home/chatgpt-admin/research/vitosoft-lfs')


def sample(*,crosswrite='XRAM_WRITE',device_type=60,add_alias=True, duplicate=False):
    types=f'<ecnDatapointType><Id>{device_type}</Id><Address>VDensHO1</Address></ecnDatapointType>'
    links=(f'<ecnDataPointTypeEventTypeLink><DataPointTypeId>{device_type}</DataPointTypeId><EventTypeId>71</EventTypeId></ecnDataPointTypeEventTypeLink>'
           '<ecnDataPointTypeEventTypeLink><DataPointTypeId>61</DataPointTypeId><EventTypeId>72</EventTypeId></ecnDataPointTypeEventTypeLink>')
    if duplicate:
        links+=f'<ecnDataPointTypeEventTypeLink><DataPointTypeId>{device_type}</DataPointTypeId><EventTypeId>71</EventTypeId></ecnDataPointTypeEventTypeLink>'
    rows=('<ecnEventType><Id>71</Id><Address>Remote_F8~0x00F8</Address></ecnEventType>'
          '<ecnEventType><Id>72</Id><Address>OtherProfileXram~0x1642</Address></ecnEventType>')
    dp=(f'<root>{types}{links}{rows}</root>').encode()
    ev=('<EventTypes><EventType><ID>Remote_F8~0x00F8</ID><Address>0x00F8</Address><AccessMode>Read</AccessMode><FCRead>Virtual_READ</FCRead><FCWrite>undefined</FCWrite></EventType>'
        f'<EventType><ID>OtherProfileXram~0x1642</ID><Address>0x1642</Address><AccessMode>ReadWrite</AccessMode><FCRead>Virtual_READ</FCRead><FCWrite>{crosswrite}</FCWrite></EventType></EventTypes>').encode()
    if not add_alias:
        ev=ev.replace(b'Remote_F8~0x00F8',b'not_the_correct_alias')
    return dp,ev


class VitosoftStaticTests(unittest.TestCase):
    def test_real_exact_20c2_profile_only_pinned_local_export(self):
        if not (SOURCES/'DPDefinitions.xml').is_file():
            self.skipTest('optional external source archive not mounted on CI')
        r=m.audit_paths(SOURCES/'DPDefinitions.xml',SOURCES/'ecnEventType.xml')
        self.assertTrue(r['sha256_pinned'])
        self.assertEqual(r['source_sha256']['dp'],m.DP_SHA)
        self.assertEqual(r['source_sha256']['event'],m.EVENT_SHA)
        self.assertEqual(r['target_datapoint_type'],60)
        self.assertEqual(r['matched_profile_descriptors'],581)
        self.assertEqual(r['read_function_codes'],{
          'Virtual_READ':462,'GFA_READ':94,'Remote_Procedure_Call':22,'undefined':3})
        self.assertEqual(r['write_function_codes'],{
          'Virtual_WRITE':182,'Remote_Procedure_Call':22,'undefined':377})
        self.assertEqual(r['rpcs_in_device_profile'],22)
        self.assertEqual(r['raw_rx_injection_alias_count'],0)
        self.assertEqual(r['dangerous_crossprofile_write_aliases'],[])
        self.assertEqual(r['addresses']['0x1642'],[])
        self.assertEqual(r['addresses']['0x0896'][0]['access'],'Read')
        self.assertEqual(r['addresses']['0x089c'][0]['write'],'undefined')
        self.assertEqual(r['addresses']['0x0a5c'][0]['access'],'Read')
        self.assertEqual(len(r['addresses']['0x27a0']),2)
        self.assertFalse(r['controller_write_authorized'])
        self.assertFalse(r['physical_uart1_isr_verified'])
        self.assertFalse(r['optolink_rx_injection_service_verified'])

    def test_cross_profile_xram_write_never_bleeds_into_exact_device(self):
        dp,events=sample()
        result=m.catalog_audit(dp,events,verify_sha=False)
        self.assertEqual(result['matched_profile_descriptors'],1)
        self.assertEqual(result['read_function_codes'],{'Virtual_READ':1})
        self.assertEqual(result['write_function_codes'],{'undefined':1})
        self.assertEqual(result['dangerous_crossprofile_write_aliases'],[])
        self.assertEqual(result['addresses']['0x1642'],[])
        self.assertFalse(result['controller_write_authorized'])

    def test_cross_profile_kbus_transparent_write_also_not_inherited(self):
        for code in ('KBUS_TRANSPARENT_WRITE','KBUS_DIRECT_WRITE','Physical_WRITE'):
            with self.subTest(code=code):
                dp,e=sample(crosswrite=code)
                obj=m.catalog_audit(dp,e,verify_sha=False)
                self.assertEqual(obj['write_function_codes'],{'undefined':1})

    def test_missing_device_type_alias_and_ambiguous_links_rejected(self):
        dp,e=sample(device_type=61)
        with self.assertRaises(m.SourceRejected):m.catalog_audit(dp,e,verify_sha=False)
        dp,e=sample(add_alias=False)
        with self.assertRaises(m.SourceRejected):m.catalog_audit(dp,e,verify_sha=False)
        dp,e=sample(duplicate=True)
        with self.assertRaises(m.SourceRejected):m.catalog_audit(dp,e,verify_sha=False)

    def test_manipulated_xml_rejected_before_pinned_hash_claim(self):
        dp,e=sample()
        with self.assertRaises(m.SourceRejected):m.catalog_audit(dp,e)
        with self.assertRaises(m.SourceRejected):m.catalog_audit(b'',e,verify_sha=False)
        with self.assertRaises(m.SourceRejected):m.catalog_audit(dp,b'',verify_sha=False)
        with self.assertRaises(m.SourceRejected):m.catalog_audit(dp[:-15],e,verify_sha=False)

    def test_static_only_imports_never_open_controller(self):
        tree=ast.parse(SOURCE.read_text())
        imports=set()
        for node in ast.walk(tree):
            if isinstance(node,ast.Import):imports.update(x.name.split('.')[0] for x in node.names)
            elif isinstance(node,ast.ImportFrom) and node.module:
                imports.add(node.module.split('.')[0])
        self.assertFalse(imports & {'socket','serial','requests','paho','subprocess','ctypes','paramiko'})
        self.assertTrue(m.catalog_audit(*sample(),verify_sha=False)['new_hardware_io'] is False)


if __name__=='__main__':unittest.main()
