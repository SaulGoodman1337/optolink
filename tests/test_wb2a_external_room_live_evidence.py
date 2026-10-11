"""Archived readback of real 20C2 external room setpoint A/B/A (+/-1°C).

This asserts the original November? No: exactly 2026-10-11 live files.
Optional private files are not bundled in CI. No controller IO in tests.
"""
import json
from pathlib import Path
import unittest

HARDWARE=Path('/tmp')
PROOFS={
  'heating':{
    'name':'wb2a-vitotrol-external-room-live-20261011.json',
    'actual_external_setpoint':22,
    'room_input':20.0,
    'actual_supply_active':374,
  },
  'cooling':{
    'name':'wb2a-vitotrol-external-room-cooling-live-20261011.json',
    'actual_external_setpoint':20,
    'room_input':22.0,
    'actual_supply_active':350,
  },
  'neutral':{
    'name':'wb2a-vitotrol-external-room-neutral-live-20261011.json',
    'actual_external_setpoint':21,
    'room_input':21.0,
    'actual_supply_active':355,
  },
}

def validate_real_live_readback(row:dict,scenario:dict):
    if type(row) is not dict or type(scenario) is not dict:
        raise ValueError('typed evidence required')
    if row.get('method')!='EXTERNAL_ROOM_SETPOINT_A1M1_OVER_OPTOLINK_NOT_KM_BUS_SLAVE':
        raise ValueError('source/method mismatch')
    if row.get('input_room_c')!=scenario['room_input'] or row.get('target_c')!=21:
        raise ValueError('wrong control input')
    if row.get('controller_identity_verified') is not True:
        raise ValueError('device identity not attested')
    if row.get('normal_room_target_verified')!=21:
        raise ValueError('normal room target not verified')
    if row.get('baseline_external_coding')!='00':
        raise ValueError('other override already active')
    if row.get('before_supply_deci_c')!=355 or row.get('after_supply_deci_c')!=355:
        raise ValueError('baseline/end supply mismatch')
    during=row.get('while_active')
    if type(during) is not dict:
        raise ValueError('missing two direct readbacks')
    if during.get('external_room_setpoint_c')!=scenario['actual_external_setpoint']:
        raise ValueError('external setpoint readback mismatch')
    if (during.get('supply_first_deci_c')!=scenario['actual_supply_active']
        or during.get('supply_second_deci_c')!=scenario['actual_supply_active']):
        raise ValueError('two supply readings not stable or inaccurate')
    if row.get('external_room_override_restored') is not True:
        raise ValueError('external override not restored')
    if row.get('actual_measured_room_source_connected') is not False:
        raise ValueError('synthetic test input is not HA measured room')
    if row.get('vitotrol_registered_with_firmware') is not False:
        raise ValueError('wrong Vitotrol-registered assertion')
    if row.get('physical_km_bus_reply_sent') is not False:
        raise ValueError('no KM-bus packet was sent')
    return {
      'proven_live_20c2_actuation':True,
      'supplier_setpoint_before_c':355/10,
      'supplier_setpoint_while_c':scenario['actual_supply_active']/10,
      'supplier_setpoint_after_c':355/10,
      'supply_change_c':(scenario['actual_supply_active']-355)/10,
      'room_setpoint_command_c':scenario['actual_external_setpoint'],
      'room_sensor_bound':False,
      'emulated_vitotrol_present':False,
    }


class HardwareProofTests(unittest.TestCase):
    def _synthetic(self,k):
        cfg=PROOFS[k]
        return {
          'method':'EXTERNAL_ROOM_SETPOINT_A1M1_OVER_OPTOLINK_NOT_KM_BUS_SLAVE',
          'input_room_c':cfg['room_input'],
          'target_c':21.0,'controller_identity_verified':True,
          'normal_room_target_verified':21,'baseline_external_coding':'00',
          'before_supply_deci_c':355,'after_supply_deci_c':355,
          'while_active':{
            'external_room_setpoint_c':cfg['actual_external_setpoint'],
            'supply_first_deci_c':cfg['actual_supply_active'],
            'supply_second_deci_c':cfg['actual_supply_active']},
          'external_room_override_restored':True,
          'actual_measured_room_source_connected':False,
          'vitotrol_registered_with_firmware':False,
          'physical_km_bus_reply_sent':False,
        }

    def test_local_two_real_controller_json_outputs_if_available(self):
        for kind,cfg in PROOFS.items():
            f=HARDWARE/cfg['name']
            if not f.is_file():self.skipTest('live root-only optional artifact absent')
            with self.subTest(kind=kind):
                result=validate_real_live_readback(json.loads(f.read_text()),cfg)
                self.assertTrue(result['proven_live_20c2_actuation'])
                self.assertFalse(result['emulated_vitotrol_present'])
                expected={'heating':1.9,'cooling':-0.5,'neutral':0.0}[kind]
                self.assertAlmostEqual(result['supply_change_c'],expected)

    def test_fixture_both_directions_work_without_fake_vitotrol(self):
        for kind,cfg in PROOFS.items():
            v=validate_real_live_readback(self._synthetic(kind),cfg)
            self.assertEqual(v['supplier_setpoint_before_c'],35.5)
            self.assertEqual(v['supplier_setpoint_after_c'],35.5)
            self.assertFalse(v['room_sensor_bound'])
            self.assertFalse(v['emulated_vitotrol_present'])

    def test_three_real_calibration_points_are_ordered_without_linear_assumption(self):
        by_setpoint={
            PROOFS[scenario]['actual_external_setpoint']:
            validate_real_live_readback(self._synthetic(scenario),cfg)['supplier_setpoint_while_c']
            for scenario,cfg in PROOFS.items()
        }
        self.assertEqual(by_setpoint,{20:35.0,21:35.5,22:37.4})
        self.assertTrue(by_setpoint[20]<by_setpoint[21]<by_setpoint[22])
        self.assertNotAlmostEqual(
            by_setpoint[22]-by_setpoint[21],
            by_setpoint[21]-by_setpoint[20])

    def test_remove_restore_proof_fails_closed(self):
        for k,cfg in PROOFS.items():
            with self.subTest(k=k):
                x=self._synthetic(k)
                x['external_room_override_restored']=False
                with self.assertRaises(ValueError):
                    validate_real_live_readback(x,cfg)

    def test_wrong_boiler_and_fabricated_sensor_rejected(self):
        cfg=PROOFS['heating']
        for key,val in (
            ('controller_identity_verified',False),
            ('vitotrol_registered_with_firmware',True),
            ('actual_measured_room_source_connected',True),
            ('physical_km_bus_reply_sent',True),
            ('baseline_external_coding','16'),
            ('before_supply_deci_c',356),
            ('after_supply_deci_c',354),
        ):
            with self.subTest(key=key):
                x=self._synthetic('heating')
                x[key]=val
                with self.assertRaises(ValueError):
                    validate_real_live_readback(x,cfg)

    def test_lack_of_two_stable_supply_readbacks_rejected(self):
        cfg=PROOFS['heating']
        x=self._synthetic('heating')
        x['while_active']['supply_second_deci_c']=360
        with self.assertRaises(ValueError):
            validate_real_live_readback(x,cfg)

    def test_command_not_current_external_setpoint_rejected(self):
        cfg=PROOFS['cooling']
        x=self._synthetic('cooling')
        x['while_active']['external_room_setpoint_c']=22
        with self.assertRaises(ValueError):
            validate_real_live_readback(x,cfg)


if __name__=='__main__':
    unittest.main()
