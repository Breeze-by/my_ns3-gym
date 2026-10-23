"""Artificial received snapshots only; no original input or native execution."""
import copy
import importlib.util
import json
import math
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('fixed_description',HERE/'describe_probe_v1.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


def setUpModule():
    target=os.environ.get('MR3_V68_TOY_IDENTITY_OUTPUT')
    if target:
        with Path(target).open('x') as stream:json.dump(m.self_identity(),stream)


def snapshot(t):
    robots=[]
    for i,name in enumerate(m.ROBOTS):
        robots.append(dict(name=name,x=float(i*4),y=0.,yaw=0.,v=0.,w=0.,fresh=True,valid=True,
            odom_source_stamp=40.+t,activity={'estimated_path_m':0.,'path_observation_complete':True},
            navigation=dict(phase='idle',owned=False,goal_id=None,accepted_at=None,
                accepted_goal_count=0,cancel_requested=False,stop_reason=None,last_goal_id=None,
                last_terminal=None,commitment_until=0.,commitment_remaining_sec=0.)))
    value=dict(epoch='toy',sequence=t+1,source_stamp=40.+t,task_elapsed_sec=float(t),robots=robots,
        candidates=[dict(index=i,x=1.45,y=0.,path_distances_m=[0.,0.,0.],valid=True,reachable=[True]*3) for i in range(8)],
        per_robot_action_mask=[[True]*10 for _ in range(3)],joint_action_mask=[True]*1000,
        diagnostics={'mask_reasons':{'per_robot':[{}, {}, {}]}})
    resign(value);return value


def resign(value):
    value['digest']=m.sha(m.canonical({k:v for k,v in value.items() if k!='digest'}))


def fixture():
    snapshots=[snapshot(t) for t in range(33)];rows=[{'kind':'reset','snapshot':snapshots[0],'info':{'epoch':'toy'}}]
    planned=[]
    for t in range(32):
        before=snapshots[t];cleanup=10<=t<13 or t>=28;action=999 if cleanup else 888
        command=dict(epoch='toy',command_id=t+1,observation_sequence=t+1,observation_digest=before['digest'],
            action=action,created_at=40.+t,expires_at=42.+t)
        rows.append({'kind':'step','snapshot':snapshots[t+1],'info':{'epoch':'toy','command':command}})
        planned.append(dict(epoch='toy',observation_sequence=t+1,observation_digest=before['digest'],action=action,
            clock_ns=(40+t)*10**9,task_elapsed_sec=float(t),round='initial' if t<13 else 'second',
            eligible_long_goal_candidates={} if cleanup else {n:[] for n in m.ROBOTS},
            reasons={n:'bounded_cleanup_wait_no_credit' for n in m.ROBOTS} if cleanup else {},
            goal_robots=[],wait_robots=list(m.ROBOTS) if cleanup else []))
    original=dict(epoch='toy',decisions=planned,rounds={r:{n:{} for n in m.ROBOTS} for r in m.ROUNDS},
        coverage_failures=[{'round':'initial','robot':'tb1','reason':'artificial missing goal'}],coverage_passed=False)
    summary=dict(freeze='50c740a64754aaa2dc3f2707cf5b0159eb929a28',workers=1,schedule=[['open',101]],
        preparation_probe_version=m.PROBE,passed=False,workers_results=[{'worker_id':0,'episodes':[{
            'epoch':'toy','preparation_probe_diagnostics':{'reach_v2_stimulus':original}}]}])
    return rows,summary


class DescriptionTests(unittest.TestCase):
    def test_full33_previous_command_post_join_and_original_failure(self):
        rows,summary=fixture();value=m.describe(rows,summary,'toy')
        self.assertEqual(len(value['decisions']),32);self.assertEqual(len(value['robot_rounds']),6)
        self.assertEqual(value['decisions'][0]['previous_snapshot_line'],1)
        self.assertEqual(value['decisions'][0]['step_line'],2)
        self.assertEqual(value['final_observation']['sequence'],33)
        self.assertTrue(value['final_observation']['no_extra_command'])
        self.assertFalse(value['original_activity_passed']);self.assertFalse(value['native_or_physics_or_qualification_credit'])
        self.assertLess(len(m.canonical(value)),1048576)

    def test_command_must_bind_previous_not_post_snapshot(self):
        rows,summary=fixture();cmd=rows[1]['info']['command'];after=rows[1]['snapshot']
        cmd.update(observation_sequence=after['sequence'],observation_digest=after['digest'])
        with self.assertRaisesRegex(ValueError,'previous snapshot'):m.describe(rows,summary,'toy')

    def test_null_initial_path_and_incomplete_path_are_separate_blockers(self):
        s=snapshot(0);s['robots'][0]['activity']={'estimated_path_m':None,'path_observation_complete':False}
        state={r:{n:{} for n in m.ROBOTS} for r in m.ROUNDS}
        _,robots,_,_=m.predicates(s,state,{'action':888,'eligible_long_goal_candidates':{n:[] for n in m.ROBOTS}})
        checks=robots[0]['GOAL_common']
        self.assertFalse(checks['path_finite']);self.assertFalse(checks['path_observation_complete'])
        self.assertEqual(robots[0]['activity']['estimated_path_m'],{'present':True,'value':None})

    def test_endpoint_1_45_is_strict_and_path_positive_is_independent(self):
        s=snapshot(0);c=s['candidates'][0];c.update(x=1.45,path_distances_m=[2.,0.,0.])
        state={r:{n:{} for n in m.ROBOTS} for r in m.ROUNDS};plan={'action':888,'eligible_long_goal_candidates':{n:[] for n in m.ROBOTS}}
        _,r,_,_=m.predicates(s,state,plan)
        self.assertTrue(r[0]['candidates'][0]['checks']['path_distance_positive'])
        self.assertFalse(r[0]['candidates'][0]['checks']['endpoint_strictly_over_1_45'])
        c['x']=math.nextafter(1.45,math.inf)
        _,r,_,_=m.predicates(s,state,plan)
        self.assertTrue(r[0]['candidates'][0]['checks']['endpoint_strictly_over_1_45'])

    def test_far_endpoint_does_not_override_original_mask(self):
        s=snapshot(0);s['candidates'][0].update(x=-2.,path_distances_m=[3.,0.,0.])
        s['per_robot_action_mask'][0][0]=False
        state={r:{n:{} for n in m.ROBOTS} for r in m.ROUNDS}
        _,r,_,_=m.predicates(s,state,{'action':888,'eligible_long_goal_candidates':{n:[] for n in m.ROBOTS}})
        self.assertTrue(r[0]['candidates'][0]['checks']['endpoint_strictly_over_1_45'])
        self.assertFalse(r[0]['candidates'][0]['checks']['original_mask']);self.assertFalse(r[0]['candidates'][0]['eligible'])

    def test_missing_and_empty_eligible_and_cleanup_wait_no_scientific_credit(self):
        rows,summary=fixture();value=m.describe(rows,summary,'toy')
        early=value['decisions'][0]['robots'][0];cleanup=value['decisions'][10]['robots'][0]
        self.assertEqual(early['summary_eligible'],{'present':True,'value':[]})
        self.assertEqual(cleanup['summary_eligible'],{'present':False})
        self.assertEqual(cleanup['mode'],'bounded_cleanup_wait_no_credit')
        self.assertTrue(all('wait_command_id' not in r['reconstructed'] for r in value['robot_rounds']))

    def test_joint_mask_and_nonapproach_are_distinct_filters(self):
        s=snapshot(0);s['candidates'][0].update(x=-2.,path_distances_m=[3.,0.,0.])
        state={r:{n:{} for n in m.ROBOTS} for r in m.ROUNDS};plan={'action':888,'eligible_long_goal_candidates':{n:[] for n in m.ROBOTS}}
        _,r,legal,_=m.predicates(s,state,plan)
        self.assertIn(88,legal);self.assertGreater(r[0]['candidates'][0]['feasible_joint_count'],0)
        s['joint_action_mask'][88]=False
        _,_,legal,_=m.predicates(s,state,plan);self.assertNotIn(88,legal)
        s['joint_action_mask'][88]=True;s['candidates'][0]['x']=2.
        _,r,legal,_=m.predicates(s,state,plan)
        self.assertTrue(r[0]['candidates'][0]['eligible']);self.assertNotIn(88,legal)

    def test_moving_wait_preserves_commitment_mask_and_forward_speed(self):
        s=snapshot(6);r=s['robots'][0];r['v']=.08;r['activity']['estimated_path_m']=.06
        r['navigation'].update(phase='active',owned=True,goal_id='g')
        state={rr:{n:{} for n in m.ROBOTS} for rr in m.ROUNDS}
        state['initial']['tb1']={'goal_id':'g','goal_command_id':1,'accepted_at_ns':40*10**9,'baseline_path_m':0.}
        plan={'action':988,'eligible_long_goal_candidates':{n:[] for n in m.ROBOTS if n!='tb1'}}
        _,robots,_,_=m.predicates(s,state,plan);self.assertEqual(robots[0]['mode'],'moving_owned_first_legal_wait')
        s['per_robot_action_mask'][0][9]=False
        _,robots,_,_=m.predicates(s,state,plan);self.assertFalse(robots[0]['moving_WAIT']['original_wait_mask'])
        r['v']=-.08;s['per_robot_action_mask'][0][9]=True
        _,robots,_,_=m.predicates(s,state,plan);self.assertFalse(robots[0]['moving_WAIT']['forward_speed'])

    def test_pending_admission_and_duplicate_json_rejected(self):
        with self.assertRaisesRegex(ValueError,'unadmitted'):m.validate_admission({'admitted':False},'a'*40)
        with self.assertRaisesRegex(ValueError,'duplicate'):m.decode('{"a":0,"a":1}')
        self.assertNotEqual(m.present({'a':False},'a'),m.present({'a':None},'a'))
        config={'admitted':True,'execution_freeze':'CLI_EXACT_PUSHED_FREEZE','identity':{'epoch':'toy'},
            'inputs':[{'path':str(path),'encoding':'plain','expected_bytes':0,'expected_sha256':'a'*64,
                'max_encoded_bytes':limit,'max_decoded_bytes':limit} for path,limit in zip(m.INPUT_PATHS,(4194304,262144))],
            'aggregate_limits':{'max_inputs':2,'max_encoded_bytes':4456448,'max_decoded_bytes':4456448,
                'max_output_bytes':1048576,'max_snapshot_rows':33,'max_candidate_predicate_rows':792,'max_robot_round_summaries':6},
            'output':{'path':str(m.OUTPUT),'native_or_physics_or_qualification_credit':False}}
        m.validate_admission(config,'a'*40)
        config['execution_freeze']='a'*40
        with self.assertRaisesRegex(ValueError,'execution freeze'):m.validate_admission(config,'a'*40)

    def test_regular_owned_fixture_and_byte_cap(self):
        with tempfile.TemporaryDirectory(prefix='v68-toy-') as name:
            p=Path(name)/'toy.json';p.write_bytes(b'{}\n')
            raw,_=m.fixed_file(p,3);self.assertEqual(raw,b'{}\n')
            with self.assertRaises(ValueError):m.fixed_file(p,2)
            link=Path(name)/'link';link.symlink_to(p)
            with self.assertRaises(ValueError):m.fixed_file(link,3)
            consumed=[];real_open=Path.open
            class MutatingRead:
                def __init__(self,stream):self.stream=stream
                def __enter__(self):return self
                def __exit__(self,*args):self.stream.close()
                def fileno(self):return self.stream.fileno()
                def read(self,*args):
                    data=self.stream.read(*args);current=p.stat()
                    os.utime(p,ns=(current.st_atime_ns,current.st_mtime_ns+1))
                    return data
            def opener(path,*args,**kwargs):return MutatingRead(real_open(path,*args,**kwargs))
            with patch.object(Path,'open',autospec=True,side_effect=opener):
                with self.assertRaisesRegex(ValueError,'input changed'):m.fixed_file(p,3,consumed.append)
            self.assertEqual(consumed,[3])  # A post-read failure cannot report zero consumption.


if __name__=='__main__':unittest.main(verbosity=2)
