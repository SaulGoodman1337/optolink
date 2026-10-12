"""Synthetic-only Vitotrol acceptance safety, timing and rollback tests."""
from __future__ import annotations

import ast
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/'tools'/'wb2a-vitotrol-acceptance-offline.py'
FIXTURE=ROOT/'tests'/'fixtures'/'wb2a-vitotrol-acceptance-synthetic-pass.json'
FAULT=ROOT/'tests'/'fixtures'/'wb2a-vitotrol-acceptance-synthetic-bc-fail.json'
spec=importlib.util.spec_from_file_location('vitotrol_acceptance_fixture',SRC)
acc=importlib.util.module_from_spec(spec)
sys.modules[spec.name]=acc
spec.loader.exec_module(acc)


def valid_case():
    return acc.parse_fixture(FIXTURE.read_bytes())


def failing_reasons(case):
    report=acc.evaluate(case)
    assert not report['live_hardware_authorized']
    assert not report['tested_controller']
    assert report['scenario_verdict']=='OFFLINE_SCENARIO_FAIL',report
    return report['scenario_reasons']


class VitotrolAcceptanceOfflineTests(unittest.TestCase):
    def test_synthetic_positive_never_authorizes_live_kessel(self):
        case=valid_case()
        report=acc.evaluate(case)
        self.assertEqual(report['scenario_verdict'],'OFFLINE_SCENARIO_PASS')
        self.assertEqual(report['evaluated_samples'],9)
        self.assertEqual(report['scenario_reasons'],[])
        self.assertFalse(report['live_hardware_authorized'])
        self.assertFalse(report['tested_controller'])
        self.assertFalse(report['optolink_rx_injection_implemented'])
        self.assertFalse(report['unsafe_controller_writes_available'])
        self.assertGreaterEqual(len(report['missing_hardware_proofs']),6)
        self.assertIn('controlled_optolink_rx_injection_service',
                      report['missing_hardware_proofs'])
        self.assertFalse(report['rpm_observer_modified'])

    def test_committed_bc_fixture_fails_closed_without_live_approval(self):
        failure=acc.evaluate(acc.parse_fixture(FAULT.read_bytes()))
        self.assertEqual(failure['scenario_verdict'],'OFFLINE_SCENARIO_FAIL')
        self.assertIn('CURRENT_BC_FAULT_OBSERVED',failure['scenario_reasons'])
        self.assertFalse(failure['live_hardware_authorized'])
        self.assertEqual(failure['missing_hardware_proofs'],
                         acc.evaluate(valid_case())['missing_hardware_proofs'])

    def test_no_synthetically_claimed_firmware_gates_can_authorize_live(self):
        scenario=valid_case()
        scenario['hardware_authorization']=True
        with self.assertRaises(acc.FixtureRejected):
            acc.evaluate(scenario)
        del scenario['hardware_authorization']
        for new_key in ('write_controller_ram','enable_raumaufschaltung',
                        'inject_raw_kmbus_frame', 'start_services'):
            changed=deepcopy(scenario)
            changed['events'][1][new_key]=True
            with self.subTest(new_key=new_key),self.assertRaises(acc.FixtureRejected):
                acc.evaluate(changed)
        self.assertFalse(acc.evaluate(scenario)['live_hardware_authorized'])

    def test_current_bc_fault_is_hard_abort_even_if_cleared_later(self):
        case=valid_case()
        case['events'][4]['bc_active']=True
        self.assertIn('CURRENT_BC_FAULT_OBSERVED',failing_reasons(case))
        self.assertFalse(case['events'][-1]['bc_active'])

    def test_new_bc_history_detected_even_when_current_bc_cleared(self):
        case=valid_case()
        case['events'][3]['bc_history_count']=5
        self.assertIn('FAULT_HISTORY_CHANGED_DURING_TEST',failing_reasons(case))
        case=valid_case()
        case['events'][4]['fault_history_fingerprint']='b'*64
        self.assertIn('FAULT_HISTORY_CHANGED_DURING_TEST',failing_reasons(case))

    def test_independent_vs1_or_controller_alarm_failure_is_abort(self):
        for key,value,code in (
            ('vs1_verified',False,'VS1_ORIGINAL_READBACK_UNVERIFIED'),
            ('other_alarm_active',True,'OTHER_CONTROLLER_ALARM_OBSERVED'),
            ('room_influence_enabled',True,'ROOM_INFLUENCE_MUST_STAY_DISABLED'),
            ('forced_burner_or_pump',True,'FORCED_BURNER_OR_PUMP_UNACCEPTABLE'),
        ):
            with self.subTest(key=key):
                case=valid_case()
                case['events'][5][key]=value
                self.assertIn(code,failing_reasons(case))

    def test_controller_coding_restoration_checks_each_field(self):
        for field,value in (
            ('a0_27a0','01'),
            ('remote_index_0a5c','1100010a'),
            ('room_0896','d200'),
            ('sensor_089c','00'),
        ):
            for phase_index in (6,7,8):
                with self.subTest(field=field,phase=phase_index):
                    case=valid_case()
                    case['events'][phase_index][field]=value
                    self.assertIn('ORIGINAL_CONFIG_READBACK_NOT_RESTORED',
                                  failing_reasons(case))

    def test_remote_index_must_be_present_and_stable(self):
        case=valid_case()
        case['events'][2]['remote_index_0a5c']='00000000'
        self.assertIn('NO_CONTROLLER_REMOTE_SOFTWARE_INDEX',failing_reasons(case))
        case=valid_case()
        case['events'][3]['remote_index_0a5c']='02000000'
        self.assertIn('REMOTE_SOFTWARE_IDENTITY_NOT_STABLE',failing_reasons(case))

    def test_temperature_requires_two_distinct_nonfallback_steps_and_readback(self):
        case=valid_case()
        case['events'][4]['room_0896']='c800'  # 20.0 fallback: not target 21.5
        self.assertIn('ROOM_TEMPERATURE_READBACK_MISMATCH',failing_reasons(case))
        case=valid_case()
        for row in case['events']:
            if row['phase']=='active':
                row['expected_room_tenths_c']=200
                row['room_0896']='c800'
        self.assertIn('INSUFFICIENT_DISTINCT_REMOTE_TEMPERATURE_CHALLENGES',
                      failing_reasons(case))
        case=valid_case()
        for row in case['events'][4:6]:
            row['expected_room_tenths_c']=210
            row['room_0896']='d200'
        self.assertIn('INSUFFICIENT_DISTINCT_REMOTE_TEMPERATURE_CHALLENGES',
                      failing_reasons(case))

    def test_sensor_status_must_change_but_is_not_mislabelled_as_verified_ok(self):
        case=valid_case()
        case['events'][2]['sensor_089c']='03'
        self.assertIn('SENSOR_STATUS_DID_NOT_CHANGE_FROM_BASELINE',
                      failing_reasons(case))
        self.assertFalse(acc.evaluate(valid_case())['tested_controller'])

    def test_baseline_needs_no_remote_and_no_preexisting_alarm(self):
        for key,val,code in (
            ('a0_27a0','01','BASELINE_NOT_REMOTE_FREE'),
            ('remote_index_0a5c','01000000','BASELINE_NOT_REMOTE_FREE'),
            ('bc_active',True,'BASELINE_ALARM_PRESENT'),
            ('other_alarm_active',True,'BASELINE_ALARM_PRESENT'),
        ):
            with self.subTest(key=key):
                case=valid_case()
                case['events'][0][key]=val
                self.assertIn(code,failing_reasons(case))

    def test_arm_must_not_change_plant_state(self):
        case=valid_case()
        case['events'][1]['a0_27a0']='01'
        self.assertIn('ORIGINAL_CONFIG_READBACK_NOT_RESTORED',failing_reasons(case))

    def test_active_phase_expects_remote_configuration(self):
        case=valid_case()
        case['events'][3]['a0_27a0']='00'
        self.assertIn('REMOTE_EXPECTATION_NOT_SET_IN_SYNTHETIC_ACTIVE_PHASE',
                      failing_reasons(case))

    def test_missing_rollback_and_too_short_postcheck(self):
        case=valid_case()
        case['events']=[x for x in case['events'] if x['phase']!='restored']
        self.assertIn('ROLLBACK_OR_POSTCHECK_MISSING',failing_reasons(case))
        case=valid_case()
        case['events'][-1]['t_ms']=85000  # < 30s after restored; also time reversal
        with self.assertRaises(acc.FixtureRejected):
            acc.evaluate(case)
        case=valid_case()
        case['events'][7]['t_ms']=70000
        case['events'][-1]['t_ms']=91000
        self.assertIn('POST_ROLLBACK_STABILITY_OBSERVATION_TOO_SHORT',
                      failing_reasons(case))

    def test_insufficient_liveness_or_overlong_active_window(self):
        case=valid_case()
        case['events'][2:6]=[case['events'][2]]
        self.assertIn('INSUFFICIENT_ACTIVE_SAMPLES',failing_reasons(case))
        case=valid_case()
        for row,clock in zip(case['events'][2:6],(2000,4000,6000,8000)):
            row['t_ms']=clock
        self.assertIn('INSUFFICIENT_REMOTE_ALIVE_OBSERVATION',
                      failing_reasons(case))
        case=valid_case()
        for row,clock in zip(case['events'][2:],(2000,32000,72000,100000,130000,150000,175000)):
            row['t_ms']=clock
        self.assertIn('ACTIVE_WINDOW_EXCEEDED',failing_reasons(case))

    def test_invalid_nonmonotonic_stale_and_time_bounds(self):
        case=valid_case()
        case['events'][3]['t_ms']=case['events'][2]['t_ms']
        with self.assertRaises(acc.FixtureRejected):
            acc.evaluate(case)
        case=valid_case()
        case['events'][5]['readback_age_ms']=5001
        with self.assertRaises(acc.FixtureRejected):
            acc.evaluate(case)
        case=valid_case()
        case['events'][-1]['t_ms']=180001
        with self.assertRaises(acc.FixtureRejected):
            acc.evaluate(case)

    def test_strict_byte_lengths_types_and_range(self):
        for key,bad in (
            ('a0_27a0','0000'),('sensor_089c','GG'),
            ('remote_index_0a5c','1'),('room_0896','ffff'),
            ('bc_active',1),('bc_history_count',True),
            ('expected_room_tenths_c',21.5),('readback_age_ms',False),
            ('fault_history_fingerprint','00'),
        ):
            with self.subTest(key=key):
                case=valid_case()
                case['events'][3][key]=bad
                with self.assertRaises(acc.FixtureRejected):
                    acc.evaluate(case)

    def test_no_duplicate_fields_nonfinite_and_no_live_mode(self):
        data=FIXTURE.read_bytes()
        with self.assertRaises(acc.FixtureRejected):
            acc.parse_fixture(b'{"schema":"x","schema":"x"}')
        with self.assertRaises(acc.FixtureRejected):
            acc.parse_fixture(b'{"mode":NaN}')
        case=valid_case()
        case['mode']='live'
        with self.assertRaises(acc.FixtureRejected):
            acc.evaluate(case)
        case=valid_case()
        case['device']['ident']='20C3'
        with self.assertRaises(acc.FixtureRejected):
            acc.evaluate(case)
        self.assertLess(len(data),acc.MAX_BYTES)

    def test_empty_large_and_event_injection_fail_closed(self):
        for blob in (b'',b' '* (acc.MAX_BYTES+1),b'{}'):
            with self.subTest(size=len(blob)),self.assertRaises(acc.FixtureRejected):
                acc.parse_fixture(blob)
        case=valid_case()
        case['events'].extend([deepcopy(case['events'][-1]) for _ in range(50)])
        with self.assertRaises(acc.FixtureRejected):
            acc.evaluate(case)

    def test_no_transport_or_controller_write_dependency(self):
        syntax=ast.parse(SRC.read_text())
        imports=set()
        for node in ast.walk(syntax):
            if isinstance(node,ast.Import):
                imports.update(a.name.split('.')[0] for a in node.names)
            elif isinstance(node,ast.ImportFrom) and node.module:
                imports.add(node.module.split('.')[0])
        self.assertFalse(imports & {
            'serial','socket','requests','subprocess','paho','ctypes',
            'paramiko','bluetooth','RPi','smbus','modbus_tk',
        })
        self.assertNotIn('Physical_WRITE',SRC.read_text())
        self.assertNotIn('Virtual_WRITE',SRC.read_text())
        self.assertFalse(acc.evaluate(valid_case())['live_hardware_authorized'])


if __name__=='__main__':
    unittest.main()
