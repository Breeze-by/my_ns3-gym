"""Artificial records only: never call main or open the real motion file."""
import copy, hashlib, importlib.util, io, json, time, unittest
from pathlib import Path
from unittest.mock import patch
HERE=Path(__file__).resolve().parent
s=importlib.util.spec_from_file_location('v74_descriptor',HERE/'describe_reach_rejection_v1.py')
m=importlib.util.module_from_spec(s);s.loader.exec_module(m)


def certificate(ok):
    frame={'reported_normal_defined':True,'separation_sufficient_under_declared_sets':ok,
        'log_intervals_only':True,'distance_norm_bounds_m':['3/5','3/5'],
        'required_centre_distance_upper_bounds_m':['7/10','7/10'],
        'squared_slack_bounds_m2':['-13/100','-13/100'],'base_reserve_m':'1/2',
        'left':{'kind':'X','support_upper_bounds_m':['1/5','1/5']},
        'right':{'kind':'D','support_upper_bounds_m':['0','0']}}
    return {'schema':'mr3-reach-cone-support-separation-v2','geometric_necessary':ok,
        'geometric_sufficient':ok,'legacy_hard_gates_passed':True,
        'common_world_odom_calibrated':True,'uncertainty_m':'3/50','ages_ns':[0,200000000],
        'map':copy.deepcopy(frame),'raw':copy.deepcopy(frame)}


def row(seq=1,clock=None,robot='tb3',reason='linear_brake_preserve_requested_turn'):
    clock=m.BEGIN_NS if clock is None else clock
    checks={'tb1':certificate(False),'tb2':certificate(True)}
    d={'reason':reason,'allow':True,'output':[0,-.2],
        'reach_pair_checks':{'tb1':certificate(True),'tb2':certificate(True)},
        'component_filter':{'canonical_input':[.15,-.2],'rejected_transition_checks':checks}}
    if reason=='reach_transition_envelope':d={'reason':reason,'allow':False,'output':[0,0],'reach_pair_checks':checks}
    return {'schema':'mr3-motion-safety-v1','epoch':m.EPOCH,'record_sequence':seq,'kind':'reach_decision',
        'sim_time_sec':clock/1e9,'wall_monotonic_ns':1000+seq,'payload':{
        'robot':robot,'clock_ns':clock,'decision_sequence':seq+100,
        'request':{'v':.15,'w':-.2,'sequence':seq+1000,'received_stamp':clock/1e9},
        'effective_request':[.15,-.2],'motion_authority_profile':'mr3-owned-stream-authority-v1',
        'motion_authority':{'permission':'normal_reach','state':'ACTIVE','owner':{'id':'synthetic_goal'}},
        'own_state':{'name':robot,'epoch':m.EPOCH,'source_stamp':{'sec':44,'nanosec':720000000},'odometry':{'synthetic_full':True}},
        'received_peers':{'tb1':{'name':'tb1','safety':{'synthetic_intent':True}},'tb2':{'name':'tb2','zero':0}},
        'decision':d,'intent':{'role':'D','synthetic':True},'tracker':{'role':'D','anchor':None},
        'safety_table_sha256':'f'*64,'started':True,'ready':True}}


def analyze(rows,**kwargs):
    raw=b''.join(m.canonical(r)+b'\n' for r in rows)
    return m.analyze_stream(io.BytesIO(raw),expected_bytes=len(raw),expected_sha256=m.sha(raw),deadline_ns=time.monotonic_ns()+10**10,**kwargs)


class Tests(unittest.TestCase):
    def test_same_line_full_context_and_original_types(self):
        original=row();v=analyze([original]);self.assertTrue(v['passed'])
        sample=v['rejection_samples'][0]
        self.assertEqual(sample['row'],original)
        self.assertEqual(sample['reference']['line_sha256'],m.sha(m.canonical(original)+b'\n'))
        self.assertEqual(sample['row']['payload']['decision']['component_filter']['rejected_transition_checks']['tb1']['map']['squared_slack_bounds_m2'],['-13/100','-13/100'])
        self.assertEqual(sample['row']['payload']['received_peers']['tb2']['zero'],0)

    def test_current_D_pass_is_not_rejected_X_check(self):
        v=analyze([row()]);a=v['per_peer_original_check_aggregates']
        current=a['decision.reach_pair_checks']['peers']['tb1']['necessary_fields']['geometric_necessary'][0]
        rejected=a['decision.component_filter.rejected_transition_checks']['peers']['tb1']['necessary_fields']['geometric_necessary'][0]
        self.assertIs(current['original_field']['value'],True)
        self.assertIs(rejected['original_field']['value'],False)
        self.assertFalse(v['mathematical_pair_checks_replayed'])
        self.assertFalse(v['actual_wheel_SetParam_or_readback_checked'])

    def test_fixed_first_per_reason_and_first_lower_middle_last(self):
        rows=[row(i+1,m.BEGIN_NS+i*20000000,reason='reach_transition_envelope' if i==3 else 'linear_brake_preserve_requested_turn') for i in range(10)]
        v=analyze(rows);self.assertTrue(v['passed']);selected=v['rejection_samples']
        self.assertEqual([s['reference']['record_sequence'] for s in selected],[1,4,5,10])
        self.assertEqual(selected[2]['selection_labels'],['middle'])
        self.assertEqual(v['candidate_records'],10)

    def test_robot_and_half_open_window(self):
        rows=[row(1,m.BEGIN_NS-1),row(2,robot='tb1'),row(3),row(4,m.END_NS)]
        v=analyze(rows);self.assertTrue(v['passed']);self.assertEqual(v['candidate_records'],1)
        self.assertEqual(v['rejection_samples'][0]['reference']['record_sequence'],3)

    def test_missing_null_false_zero_preserved(self):
        original=row();d=original['payload']['decision'];d.pop('reach_pair_checks')
        d['component_filter']['rejected_transition_checks']['tb1']['geometric_necessary']=None
        d['component_filter']['rejected_transition_checks']['tb2']['geometric_necessary']=0
        v=analyze([original]);self.assertTrue(v['passed']);a=v['per_peer_original_check_aggregates']
        self.assertEqual(a['decision.reach_pair_checks']['check_map_presence']['field'][0]['original_field'],{'present':False})
        values=[a['decision.component_filter.rejected_transition_checks']['peers'][p]['necessary_fields']['geometric_necessary'][0]['original_field']['value'] for p in ('tb1','tb2')]
        self.assertIsNone(values[0]);self.assertIs(type(values[1]),int)

    def test_request_unknown_not_filled_or_nearest_joined(self):
        r=row();r['payload'].pop('effective_request')
        v=analyze([r,row(2)]);self.assertTrue(v['passed'])
        self.assertEqual(v['unavailable_request_or_output_ticks'],1)
        self.assertEqual(v['rejection_samples'][0]['row']['payload']['request']['sequence'],1002)
        self.assertNotIn('raw_request_join',v['rejection_samples'][0])

    def test_nonrejection_not_sampled(self):
        r=row();r['payload']['decision']['output'][0]=.15
        z=row(2);z['payload']['effective_request'][0]=0
        v=analyze([r,z]);self.assertTrue(v['passed']);self.assertEqual(v['candidate_records'],0)
        self.assertEqual(v['other_window_decisions'],2)

    def test_resource_overflow_is_partial_FAIL(self):
        with patch.dict(m.LIMITS,max_candidate_records=1):v=analyze([row(),row(2)])
        self.assertFalse(v['passed']);self.assertFalse(v['complete_input_read'])
        self.assertEqual(v['resource_or_finish_failure'],'candidate record cap')
        self.assertEqual(v['candidate_records'],1)
        with patch.dict(m.LIMITS,max_candidate_bytes=1):v=analyze([row()])
        self.assertFalse(v['passed']);self.assertIn('payload byte cap',v['resource_or_finish_failure'])

    def test_typed_margin_value_cap_is_honest_FAIL(self):
        r=row(2);r['payload']['decision']['reach_pair_checks']['tb1']['map']['base_reserve_m']='51/100'
        with patch.dict(m.LIMITS,max_values_per_margin=1):v=analyze([row(),r])
        self.assertFalse(v['passed']);self.assertIn('aggregation bound',v['resource_or_finish_failure'])

    def test_all_strict_JSON_parse_and_byte_hash_accounted(self):
        prefix=m.canonical(row())+b'\n';raw=prefix+b'{"x":1,"x":2}\n'+b'{"x":1e999}\n'
        counts=[];v=m.analyze_stream(io.BytesIO(raw),expected_bytes=len(raw),expected_sha256=m.sha(raw),deadline_ns=time.monotonic_ns()+10**10,on_read=counts.append)
        self.assertFalse(v['passed']);self.assertTrue(v['complete_input_read']);self.assertTrue(v['input_SHA_matches_pin'])
        self.assertEqual(v['parse_errors'],2);self.assertEqual(sum(counts),len(raw))

    def test_hash_tail_and_sequence_failures_not_rejudged(self):
        v=analyze([row(),row()]);self.assertFalse(v['passed']);self.assertEqual(v['semantic_error_count'],1)
        raw=m.canonical(row())
        v=m.analyze_stream(io.BytesIO(raw),expected_bytes=len(raw),expected_sha256=m.sha(raw),deadline_ns=time.monotonic_ns()+10**10)
        self.assertFalse(v['passed']);self.assertFalse(v['complete_newline_tail'])
        self.assertIs(v['old_FAIL_rejudged'],False)

    def test_unknown_reason_is_literal_and_covered_not_normalized(self):
        r=row(reason='new_literal_reason');v=analyze([r]);self.assertTrue(v['passed'])
        self.assertIn('first_reason:new_literal_reason',v['rejection_samples'][0]['selection_labels'])
        self.assertEqual(v['window_reason_counts'],{'new_literal_reason':1})

    def test_unadmitted_spec_refuses_before_any_actual_read(self):
        spec_path=HERE/'description_spec_v1.json'
        if not spec_path.exists():spec_path=HERE/'description_spec_draft_v1.json'
        spec=json.loads(spec_path.read_bytes());spec['admitted']=False
        with self.assertRaisesRegex(ValueError,'unadmitted'):m.validate_admission(spec,'a'*40)
        spec['admitted']=True;m.validate_admission(spec,'a'*40)
        spec['inputs'][0]['path']='/tmp/other'
        with self.assertRaises(ValueError):m.validate_admission(spec,'a'*40)
        self.assertEqual(len(m.INTERPRETATION_SOURCES),21)
        self.assertTrue(any(k.endswith('/mr3_reach_support.py') for k in m.INTERPRETATION_SOURCES))
