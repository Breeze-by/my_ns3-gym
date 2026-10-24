"""Artificial independent replay tampering; no actual input/native qualification."""
import copy
import json
import math
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from mr3_learning import reach_probe_masked_cancel_replay as replay
from mr3_learning import audit_reach_reset_workload as reset
from mr3_learning import audit_reach_preparation as full
from mr3_learning import reach_preparation as preparation
from mr3_learning.tests.masked_cancel_synthetic_trace import load_trace

ROOT=Path('/home/zhuyulab/ns3-workspace')
FREEZE='a'*40


def write_stage(directory):
    rows,diagnostics,epoch=load_trace()
    ep=directory/'worker0/episode001_open_101';ep.mkdir(parents=True)
    meta=dict(freeze=FREEZE,safety_contract='mr3-reach-v1',preparation_probe_version=replay.PROBE,
        preparation_motion_probe=True,goal_filter=replay.GOAL_FILTER,goal_rank=replay.GOAL_RANK,workers=1,schedule=[['open',101]],steps_per_episode=32)
    declared=dict(epoch=epoch,scene='open',seed=101,transitions=32,output_directory=str(ep),
        preparation_probe_diagnostics=diagnostics)
    summary=dict(meta,passed=True,workers_results=[{'worker_id':0,'error':None,'episodes':[declared]}])
    episode_meta=dict(goal_filter=replay.GOAL_FILTER,goal_rank=replay.GOAL_RANK,freeze=FREEZE,epoch=epoch,safety_contract='mr3-reach-v1',preparation_probe_version=replay.PROBE,
        execution_phase_protocol='mr3-controlled-execution-phase-v2',
        reset_handshake='paused-controlled-state-peer-guard-storage-v2',seed_rule='legacy',
        start_graph_rule='original-seed-cell',reach_geometry_rule='binary-cone-v1')
    for path,value in [(directory/'benchmark_metadata.json',meta),(directory/'benchmark_summary.json',summary),
                       (ep/'metadata.json',episode_meta),(ep/'supervisor_metadata.json',episode_meta)]:
        path.write_text(json.dumps(value)+'\n')
    (ep/'transitions.jsonl').write_text(''.join(json.dumps(row)+'\n' for row in rows))
    return ep,summary


def reseal_snapshot(rows,index):
    snapshot=rows[index]['snapshot']
    snapshot['digest']=replay.digest(replay.canonical({k:v for k,v in snapshot.items() if k!='digest'}))
    if index<len(rows)-1:rows[index+1]['info']['command']['observation_digest']=snapshot['digest']


class MaskedCancelReplayTests(unittest.TestCase):
    def test_independent_full32_fixture_matches_real_synthetic_producer(self):
        rows,diagnostics,epoch=load_trace();proof=replay.replay_episode(rows,diagnostics,epoch=epoch)
        self.assertTrue(proof['passed']);self.assertEqual(proof['goal_submissions'],6)
        self.assertEqual(proof['baseline_captures'],6);self.assertFalse(proof['producer_imported_as_oracle'])
        self.assertIsNone(proof['received_rounds']['initial']['tb1']['submitted_activity']['estimated_path_m'])

    def test_persisted_baseline_tamper_and_bool_are_rejected(self):
        for field,value in [('baseline_capture_count',True),('baseline_capture_count',2),
                            ('baseline_path_m',999.),('baseline_path_source_ns',0),
                            ('baseline_snapshot_digest','0'*64)]:
            with self.subTest(field=field,value=value):
                rows,d,e=load_trace();d['reach_masked_cancel_v1_stimulus']['rounds']['initial']['tb1'][field]=value
                with self.assertRaisesRegex(ValueError,'persisted'):replay.replay_episode(rows,d,epoch=e)

    def test_previous_snapshot_association_not_post_snapshot(self):
        rows,d,e=load_trace();cmd=rows[1]['info']['command'];cmd['observation_digest']=rows[1]['snapshot']['digest']
        with self.assertRaisesRegex(ValueError,'association'):replay.replay_episode(rows,d,epoch=e)

    def test_zero_baseline_is_valid_and_never_recaptured(self):
        rows,_,e=load_trace();s=copy.deepcopy(rows[1]['snapshot']);name='tb1';nav=s['robots'][0]['navigation']
        state={r:{n:{} for n in replay.ROBOTS} for r in replay.ROUNDS}
        state['initial'][name]={'goal_id':nav['goal_id'],'goal_created_ns':0,'baseline_capture_count':0}
        s['robots'][0]['activity']['estimated_path_m']=0.
        replay.observe(s,state);saved=copy.deepcopy(state['initial'][name])
        self.assertEqual(saved['baseline_capture_count'],1);self.assertEqual(saved['baseline_path_m'],0.)
        s['robots'][0]['activity']['estimated_path_m']=50.;replay.observe(s,state)
        self.assertEqual(state['initial'][name],saved)

    def test_baseline_requires_same_active_fresh_valid_accepted_complete_owner(self):
        rows,_,_=load_trace();good=rows[1]['snapshot']
        variants=[('navigation','goal_id','wrong'),('navigation','owned',False),('navigation','phase','canceling'),
            ('robot','fresh',False),('robot','valid',False),('activity','path_observation_complete',False),
            ('activity','estimated_path_m',None),('activity','estimated_path_m',-.1),
            ('activity','epoch','wrong'),('activity','state_sequence',True),
            ('activity','last_odom_source_stamp',0.),('activity','last_odom_source_stamp',100.)]
        for layer,key,value in variants:
            with self.subTest(layer=layer,key=key,value=value):
                s=copy.deepcopy(good);r=s['robots'][0];goal=r['navigation']['goal_id']
                (r if layer=='robot' else r[layer])[key]=value
                state={rr:{n:{} for n in replay.ROBOTS} for rr in replay.ROUNDS}
                state['initial']['tb1']={'goal_id':goal,'goal_created_ns':0,'baseline_capture_count':0}
                replay.observe(s,state);self.assertEqual(state['initial']['tb1']['baseline_capture_count'],0)

    def test_late_acceptance_and_natural_terminal_rejected(self):
        rows,d,e=load_trace();s=rows[3]['snapshot'];r=s['robots'][0]
        r['navigation']['accepted_at']=2.1;r['navigation']['commitment_until']=7.1;reseal_snapshot(rows,3)
        with self.assertRaises(ValueError):replay.replay_episode(rows,d,epoch=e)
        rows,d,e=load_trace();target=next(i for i,row in enumerate(rows)
            if row['snapshot']['robots'][0]['navigation'].get('last_terminal')=='CANCELED')
        rows[target]['snapshot']['robots'][0]['navigation']['last_terminal']='SUCCEEDED';reseal_snapshot(rows,target)
        with self.assertRaisesRegex(ValueError,'natural'):replay.replay_episode(rows,d,epoch=e)

    def test_speed_path_and_five_second_wait_gate_are_not_relaxed(self):
        for field,value in [('v',-.08),('v',.079)]:
            rows,d,e=load_trace();i=6;rows[i]['snapshot']['robots'][0][field]=value;reseal_snapshot(rows,i)
            with self.assertRaises(ValueError):replay.replay_episode(rows,d,epoch=e)
        for field,value in [('epoch','wrong'),('last_odom_source_stamp',None),
                            ('last_odom_source_stamp',.5),('last_odom_source_stamp',100.)]:
            rows,d,e=load_trace();rows[6]['snapshot']['robots'][0]['activity'][field]=value;reseal_snapshot(rows,6)
            with self.assertRaises(ValueError):replay.replay_episode(rows,d,epoch=e)
        rows,d,e=load_trace();rows[6]['snapshot']['robots'][0]['activity']['estimated_path_m']=.149;reseal_snapshot(rows,6)
        with self.assertRaises(ValueError):replay.replay_episode(rows,d,epoch=e)
        rows,d,e=load_trace();rows[6]['snapshot']['robots'][0]['navigation']['commitment_until']=9.;reseal_snapshot(rows,6)
        with self.assertRaisesRegex(ValueError,'commitment'):replay.replay_episode(rows,d,epoch=e)

    def test_handoff_and_cleanup_wait_cannot_be_forged(self):
        for field,value in [('handoff_observed_ns',7*10**9),('rest_source_ns',[7*10**9]*3),
                            ('wait_command_id',101),('wait_submitted_ns',10*10**9)]:
            rows,d,e=load_trace();d['reach_masked_cancel_v1_stimulus']['rounds']['initial']['tb1'][field]=value
            with self.assertRaises(ValueError):replay.replay_episode(rows,d,epoch=e)

    def test_original_joint_mask_and_no_endpoint_distance_veto(self):
        rows,d,e=load_trace();s=copy.deepcopy(rows[0]['snapshot'])
        # Artificial component choice check: rescale coordinates only; masks remain
        # explicitly supplied toy data, not a native map or obstacle proof.
        for r in s['robots']:
            r['x']*=.01;r['y']*=.01
        for c in s['candidates']:
            c['x']*=.01;c['y']*=.01
        states={r:{n:{} for n in replay.ROBOTS} for r in replay.ROUNDS}
        request,_=replay.choose(s,states,{})
        self.assertTrue(request['goal_robots']);self.assertNotIn('nominal_endpoint_reference_m',request)
        original=request['action'];s['joint_action_mask'][original]=False
        states={r:{n:{} for n in replay.ROBOTS} for r in replay.ROUNDS}
        other,_=replay.choose(s,states,{});self.assertNotEqual(other['action'],original)

    def test_v2_payload_or_pass_label_alone_cannot_acquire_v3_credit(self):
        rows,d,e=load_trace();d['reach_v2_stimulus']=d.pop('reach_masked_cancel_v1_stimulus')
        with self.assertRaisesRegex(ValueError,'explicit masked-cancel'):replay.replay_episode(rows,d,epoch=e)
        with self.assertRaises(ValueError):replay.require_stage_proof({'passed':True},freeze=FREEZE,episodes=1,helper_sha256='a'*64)

    def test_selected_profile_version_and_source_registration(self):
        self.assertEqual(reset.profile_spec(reset.PROFILE_MASKED)[1],replay.PROBE)
        with self.assertRaises(ValueError):reset.profile_from_plan({'reset_workload_reader_profile':reset.PROFILE_MASKED,
            'preparation_probe_version':reset.PROBE_VERSION_V2})
        self.assertTrue(replay.SOURCE_PATHS<=reset.source_paths(reset.PROFILE_MASKED))
        self.assertNotIn(replay.SOURCE,reset.source_paths(reset.PROFILE_V2))
        self.assertEqual(reset.profile_spec(reset.PROFILE_V2)[1],reset.PROBE_VERSION_V2)

    def test_actual_immutable_v3_projection_preserves_whole_inverse(self):
        with patch.object(reset,'WORKSPACE',ROOT):
            for kind in ('angular','physics'):
                module,proof=reset.load_reader(kind,workload_profile=reset.PROFILE_MASKED)
                self.assertEqual(module.PROBE_VERSION,replay.PROBE)
                self.assertTrue(proof['whole_source_inverse_equal']);self.assertEqual(len(proof['literal_changes']),1)
                old,_=reset.load_reader(kind,workload_profile=reset.PROFILE_V2)
                self.assertEqual(old.PROBE_VERSION,reset.PROBE_VERSION_V2)

    def test_actual_stage_replay_and_public_proof_shape_tamper(self):
        with tempfile.TemporaryDirectory(prefix='probe-v3-stage-') as tmp:
            directory=Path(tmp);write_stage(directory);proof=replay.replay_stage(directory,FREEZE)
            ids=replay.require_stage_proof(proof,freeze=FREEZE,episodes=1,helper_sha256=proof['helper_sha256'])
            self.assertEqual(len(ids),1)
            bad=copy.deepcopy(proof);bad['episodes'][0]['received_rounds']['initial']['tb1']['baseline_capture_count']=True
            with self.assertRaises(ValueError):replay.require_stage_proof(bad,freeze=FREEZE,episodes=1,helper_sha256=proof['helper_sha256'])
            (directory/'worker1/episode001_open_101').mkdir(parents=True)
            (directory/'worker1/episode001_open_101/metadata.json').write_text('{}')
            with self.assertRaisesRegex(ValueError,'extra/missing'):replay.replay_stage(directory,FREEZE)

    def test_public_full_route_replays_before_original_audit(self):
        with tempfile.TemporaryDirectory(prefix='probe-v3-full-') as tmp:
            directory=Path(tmp);write_stage(directory);plan=directory/'plan.json'
            plan.write_text(json.dumps({'reset_workload_reader_profile':reset.PROFILE_MASKED,'preparation_probe_version':replay.PROBE,
                'seed_rule':'legacy','start_graph_rule':'original-seed-cell','reach_geometry_rule':'binary-cone-v1'}))
            called=[];original=SimpleNamespace(audit=lambda *a:(called.append(True) or {'passed':True}))
            with patch.object(full,'load_impl',return_value=(original,{})):
                result=full.audit(directory,ROOT,FREEZE,plan)
                self.assertTrue(result['probe_masked_cancel_stimulus_replay']['passed']);self.assertEqual(called,[True])
                payload=json.loads((directory/'benchmark_summary.json').read_text())
                payload['workers_results'][0]['episodes'][0]['preparation_probe_diagnostics']['reach_masked_cancel_v1_stimulus']['rounds']['initial']['tb1']['baseline_capture_count']=True
                (directory/'benchmark_summary.json').write_text(json.dumps(payload));called.clear()
                with self.assertRaises(ValueError):full.audit(directory,ROOT,FREEZE,plan)
                self.assertEqual(called,[])

    def test_public_angular_route_conjoins_real_independent_replay(self):
        with tempfile.TemporaryDirectory(prefix='probe-v3-angular-') as tmp:
            directory=Path(tmp);write_stage(directory)
            leaf=SimpleNamespace(audit=lambda *a:{'schema':reset.EXPECTED_SCHEMAS['angular'],'passed':True,'errors':[]})
            with patch.object(reset,'load_reader',return_value=(leaf,{'whole_source_inverse_equal':True})):
                value=reset.audit(directory,FREEZE,kind='angular',workload_profile=reset.PROFILE_MASKED)
                self.assertTrue(value['passed']);self.assertTrue(value['probe_masked_cancel_stimulus_replay']['passed'])
                meta=json.loads((directory/'worker0/episode001_open_101/metadata.json').read_text())
                meta['preparation_probe_version']=reset.PROBE_VERSION_V2
                (directory/'worker0/episode001_open_101/metadata.json').write_text(json.dumps(meta))
                value=reset.audit(directory,FREEZE,kind='angular',workload_profile=reset.PROFILE_MASKED)
                self.assertFalse(value['passed'])

    def test_real_generated_plan_preserves_full_child_schema_and_new_profile(self):
        # The actual builder is used with readonly current binding metadata.
        # Before installation only the new helper's source availability is
        # projected; no Git/build/native admission is claimed by this fixture.
        binding=ROOT/'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261024_mr3_p2a_v67_owned_stream_qualification/native_custody_binding_v1.json'
        value=json.loads(binding.read_text());original_sha=preparation.sha
        def source_sha(path):
            if Path(path)==ROOT/replay.SOURCE and not Path(path).exists():
                return original_sha(replay.__file__)
            return original_sha(path)
        with tempfile.TemporaryDirectory(prefix='probe-v3-plan-') as tmp:
            root=Path(tmp);plan_path=root/'plan.json'
            with patch.object(preparation,'sha',side_effect=source_sha):
                plan=preparation.build_plan(plan_path=plan_path,output_directory=root/'output',run_root=root/'native',
                    custody_binding=binding,binary_proof=root/'binary.json',preflight=root/'preflight.json',
                    engineering_remaining_seconds='20000',reset_workload_reader_profile=reset.PROFILE_MASKED,
                    seed_rule=value.get('seed_rule','exact-point-bridge-v2'),start_graph_rule='point-attachment-3x3-v1',
                    reach_geometry_rule=value.get('reach_geometry_rule','cone-support-v2'),
                    actuation_profile=value['actuation_profile'],motion_authority_profile=value['motion_authority_profile'])
            self.assertEqual(plan['preparation_probe_version'],replay.PROBE)
            self.assertEqual(sum(s['expected_episodes'] for s in plan['stages']),12)
            self.assertEqual(sum(len(preparation.primitives.roles(s)) for s in plan['stages']),30)
            self.assertIn(replay.SOURCE,plan['source_bindings'])
            for stage in plan['stages']:
                child=next(job for job in stage['audits'] if job.get('role')=='full')
                self.assertEqual(child['argv'][1:3],['-m','mr3_learning.audit_reach_preparation'])
                self.assertEqual(preparation.argument(child['argv'],'--plan'),str(plan_path))
                if stage['stage'] in ('interface','reset'):
                    self.assertEqual(preparation.argument(stage['native']['argv'],'--preparation-probe-version'),replay.PROBE)
            changed=copy.deepcopy(plan);changed['source_bindings'].pop(replay.SOURCE)
            with self.assertRaises(ValueError):preparation.validate_plan(changed)
            changed=copy.deepcopy(plan);changed['preparation_probe_version']=reset.PROBE_VERSION_V2
            with self.assertRaises(ValueError):preparation.validate_plan(changed)


    def test_approach_goal_is_allowed_by_actual_supplied_mask_and_rank(self):
        rows,_,_=load_trace();s=copy.deepcopy(rows[0]['snapshot'])
        # A fixed component fixture: original supplied masks are the tested input,
        # while independent full input/physics gates retain actual geometry credit.
        for i,r in enumerate(s['robots']):
            r.update(x=float(i*2),y=0.,yaw=0.)
            s['per_robot_action_mask'][i]=[False]*8+[True,True]
        s['candidates'][0].update(x=1.,y=0.,path_distances_m=[9.,9.,9.])
        s['candidates'][1].update(x=5.,y=2.,path_distances_m=[1.,1.,1.])
        s['per_robot_action_mask'][0][0]=True
        s['per_robot_action_mask'][0][1]=True
        s['joint_action_mask']=[False]*1000
        for a in (88,188,888):s['joint_action_mask'][a]=True
        rounds={r:{n:{} for n in replay.ROBOTS} for r in replay.ROUNDS}
        request,_=replay.choose(s,rounds,{})
        self.assertEqual(request['action'],88)
        self.assertFalse(replay.lifecycle.nonapproach(s,(0,8,8)))
        self.assertEqual(request['goal_filter'],replay.GOAL_FILTER)

    def test_max_min_path_precedes_sum_and_zero_remains_legal(self):
        rows,_,_=load_trace();s=copy.deepcopy(rows[0]['snapshot'])
        for i in range(3):s['per_robot_action_mask'][i]=[False]*8+[True,True]
        for c,paths in [(0,[100.,0.,0.]),(1,[0.,1.,0.]),(2,[0.,0.,1.]),
                        (3,[4.,0.,0.]),(4,[0.,4.,0.]),(5,[0.,0.,4.])]:
            s['candidates'][c]['path_distances_m']=paths
        for i,cs in enumerate(((0,3),(1,4),(2,5))):
            for c in cs:s['per_robot_action_mask'][i][c]=True
        s['joint_action_mask']=[False]*1000
        for a in (12,345,888):s['joint_action_mask'][a]=True
        blank=lambda:{r:{n:{} for n in replay.ROBOTS} for r in replay.ROUNDS}
        request,_=replay.choose(s,blank(),{});self.assertEqual(request['action'],345)
        s['joint_action_mask'][345]=False
        s['candidates'][0]['path_distances_m'][0]=0.
        request,_=replay.choose(s,blank(),{});self.assertEqual(request['action'],12)
        self.assertIn(0,request['eligible_goal_candidates']['tb1'])

    def test_bad_legal_path_is_data_failure_even_outside_goal_window(self):
        for bad in (None,-1.,float('inf'),True):
            rows,_,_=load_trace();s=copy.deepcopy(rows[0]['snapshot'])
            s['task_elapsed_sec']=11.
            s['per_robot_action_mask'][0][0]=True
            s['candidates'][0]['path_distances_m'][0]=bad
            blank={r:{n:{} for n in replay.ROBOTS} for r in replay.ROUNDS}
            with self.subTest(value=bad),self.assertRaisesRegex(ValueError,'invalid path'):
                replay.choose(s,blank,{})

    def test_invalid_coordinates_never_become_silent_candidate_filter(self):
        rows,_,_=load_trace();s=copy.deepcopy(rows[0]['snapshot'])
        s['per_robot_action_mask'][0][0]=True;s['candidates'][0]['x']=None
        with self.assertRaisesRegex(ValueError,'coordinates'):
            replay.choose(s,{r:{n:{} for n in replay.ROBOTS} for r in replay.ROUNDS},{})

    def test_original_per_robot_false_is_not_overridden_by_joint_true(self):
        rows,_,_=load_trace();s=copy.deepcopy(rows[0]['snapshot'])
        s['joint_action_mask']=[False]*1000;s['joint_action_mask'][888]=True
        s['per_robot_action_mask'][0][8]=False
        with self.assertRaisesRegex(ValueError,'no original legal'):
            replay.choose(s,{r:{n:{} for n in replay.ROBOTS} for r in replay.ROUNDS},{})

    def test_old_profile_and_mixed_state_are_rejected_both_directions(self):
        rows,d,e=load_trace()
        d['reach_v3_stimulus']=copy.deepcopy(d[replay.STATE_KEY])
        with self.assertRaisesRegex(ValueError,'explicit masked-cancel'):
            replay.replay_episode(rows,d,epoch=e)
        from mr3_learning.tests.probe_v3_synthetic_trace import load_trace as old_trace
        old_rows,old_d,old_e=old_trace();old_d[replay.STATE_KEY]={}
        with self.assertRaisesRegex(ValueError,'explicit v3'):
            replay.lifecycle.replay_episode(old_rows,old_d,epoch=old_e)

    def test_qualification_requires_nine_distinct_actual_probe_identities(self):
        # Component identity receipt after substantive stage replay; not a fake
        # full qualification. The public qualifier calls this after12EP/30roles.
        episodes=[dict(directory='/artificial/stage/episode'+str(i),epoch='toy'+str(i),full_result_sha256='a'*64)
                  for i in range(9)]
        expected={(r['directory'],r['epoch']) for r in episodes}
        proof=preparation._probe_qualification_receipt(reset.PROFILE_MASKED,replay.PROBE,FREEZE,episodes,expected)
        self.assertTrue(proof['passed']);self.assertEqual(len(proof['episodes']),9)
        for bad in (episodes[:-1],episodes[:-1]+[episodes[0]]):
            with self.assertRaisesRegex(ValueError,'lacks all actual'):
                preparation._probe_qualification_receipt(reset.PROFILE_MASKED,replay.PROBE,FREEZE,bad,expected)
        with self.assertRaisesRegex(ValueError,'profile'):
            preparation._probe_qualification_receipt(reset.PROFILE_MASKED,reset.PROBE_VERSION_V3,FREEZE,episodes,expected)

    def test_reset_post_math_reader_rechecks_selected_masked_input_bytes(self):
        for kind in ('angular','physics'):
            with self.subTest(kind=kind),tempfile.TemporaryDirectory(prefix='masked-post-math-') as tmp:
                directory=Path(tmp);ep,_=write_stage(directory)
                def mutate(*args):
                    path=ep/'transitions.jsonl'
                    path.write_bytes(path.read_bytes()+b'\n')
                    return {'schema':reset.EXPECTED_SCHEMAS[kind],'passed':True,'errors':[]}
                leaf=SimpleNamespace(audit=mutate)
                with patch.object(reset,'load_reader',return_value=(leaf,{'whole_source_inverse_equal':True})):
                    result=reset.audit(directory,FREEZE,kind=kind,workload_profile=reset.PROFILE_MASKED,
                        per_episode_report=directory/'per_episode.json' if kind=='physics' else None)
                self.assertTrue(result['original_reader_result']['passed'])
                self.assertTrue(result['probe_masked_cancel_stimulus_replay']['passed'])
                self.assertFalse(result['passed'])
                self.assertTrue(any('input changed before outer verdict' in e for e in result['errors']))
        # The profile can reject before the selected checker/key is initialized;
        # this remains an honest failure receipt, not UnboundLocalError.
        result=reset.audit(Path('/artificial/not-opened'),FREEZE,kind='angular',workload_profile='unknown')
        self.assertFalse(result['passed']);self.assertTrue(result['errors'])


if __name__=='__main__':unittest.main()
