"""Canonical imports of public profile/reader gates with artificial artifacts."""
import copy
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from mr3_learning import audit_reach_reset_workload as reset
from mr3_learning import audit_reach_preparation as full
from mr3_learning import audit_reach_runtime as runtime
from mr3_learning import audit_reach_peer_control as peer
from mr3_learning import audit_reach_controlled_physics as controlled
from mr3_learning import audit_reach_cadence as cadence
from mr3_learning import motion_authority_audit as authority
from mr3_learning import motion_authority_profile as profile

ROOT=Path(runtime.__file__).resolve().parents[7]


class ProbeReaderTests(unittest.TestCase):
    def fixture(self,motion=True,actual=True):
        temporary=tempfile.TemporaryDirectory(prefix='mr3-authority-reader-artificial-')
        self.addCleanup(temporary.cleanup);root=Path(temporary.name);episode=root/'episode';episode.mkdir()
        plan=root/'fixture.json';plan.write_text(json.dumps(dict(reset_workload_reader_profile=reset.PROFILE_V2,
            preparation_probe_version=reset.PROBE_VERSION_V2)))
        metadata=dict(epoch='artificial',freeze='a'*40,safety_contract='mr3-reach-v1',
            execution_phase_protocol='mr3-controlled-execution-phase-v2',
            reset_handshake='paused-controlled-state-peer-guard-storage-v2')
        if actual:metadata['preparation_probe_version']=reset.PROBE_VERSION_V2
        for name in ('metadata.json','supervisor_metadata.json'):(episode/name).write_text(json.dumps(metadata))
        (episode/'benchmark_metadata.json').write_text(json.dumps(dict(preparation_motion_probe=motion)))
        return root,plan,episode

    def test_reset_reader_both_profiles_execute_unique_original_inverse(self):
        for name,version in ((reset.PROFILE,reset.PROBE_VERSION),(reset.PROFILE_V2,reset.PROBE_VERSION_V2)):
            for role in ('angular','physics'):
                module,proof=reset.load_reader(role,workload_profile=name)
                self.assertEqual(module.PROBE_VERSION,version)
                self.assertTrue(proof['whole_source_inverse_equal'])
                self.assertEqual(proof['source_sha256'],proof['inverse_sha256'])
                self.assertEqual(len(proof['literal_changes']),1)

    def test_reset_missing_wrong_pair_rejected_old_default_preserved(self):
        self.assertEqual(reset.profile_from_plan(dict(reset_workload_reader_profile=reset.PROFILE))[1],reset.PROBE_VERSION)
        for value in (None,True,'unknown'):
            with self.assertRaises(ValueError):reset.profile_spec(value)
        for value in (None,reset.PROBE_VERSION,'unknown'):
            with self.assertRaises(ValueError):reset.profile_from_plan(dict(
                reset_workload_reader_profile=reset.PROFILE_V2,preparation_probe_version=value))

    def test_full_selected_v2_unique_inverse(self):
        _,plan,_=self.fixture();module,proof=full.load_impl(plan)
        self.assertEqual(module.PREPARATION_PROBE_V6,reset.PROBE_VERSION_V2)
        self.assertTrue(proof['whole_source_inverse_equal']);self.assertEqual(proof['inverse_sha256'],full.SOURCE_SHA256)
        self.assertEqual(sum('outward-cancel' in row['before'] for row in proof['literal_changes']),1)

    def test_full_old_definition_defaults_to_original_profile(self):
        root,_,_=self.fixture();plan=root/'old.json';plan.write_text('{}')
        module,_=full.load_impl(plan);self.assertEqual(module.PREPARATION_PROBE_V6,reset.PROBE_VERSION)

    def test_full_nonprobe_does_not_borrow_probe_metadata_obligation(self):
        _,plan,episode=self.fixture(motion=False,actual=False)
        private=SimpleNamespace(audit=lambda *args:dict(passed=True,errors=[]))
        with patch.object(full,'load_impl',return_value=(private,{})):
            report=full.audit(episode,ROOT,'a'*40,plan)
        self.assertTrue(report['passed']);self.assertNotIn('episode_probe_profiles',report)

    def test_full_probe_role_missing_or_mixed_metadata_rejected_before_dispatch(self):
        _,plan,episode=self.fixture(actual=False)
        with patch.object(full,'load_impl') as dispatch:
            with self.assertRaises(ValueError):full.audit(episode,ROOT,'a'*40,plan)
            dispatch.assert_not_called()
        meta=json.loads((episode/'metadata.json').read_text());meta['preparation_probe_version']=reset.PROBE_VERSION_V2
        (episode/'metadata.json').write_text(json.dumps(meta))
        (episode/'supervisor_metadata.json').write_text(json.dumps(dict(meta,epoch='other')))
        with self.assertRaisesRegex(ValueError,'epoch differs'):
            reset.episode_probe_profiles(episode,'a'*40,workload_profile=reset.PROFILE_V2)


class PublicAuthorityTests(unittest.TestCase):
    def report(self):
        proof=dict(schema='mr3-independent-motion-authority-episode-v1',profile=profile.MOTION_AUTHORITY_PROFILE,
            passed=True,raw_generation_known=False,original_global_stop_debts_and_fixed_radius_passed=True,
            adapter=dict(original_six_phase_protocol_replayed=True),robots={name:dict(passed=True) for name in authority.ROBOTS})
        return dict(passed=True,motion_authority_profile=profile.MOTION_AUTHORITY_PROFILE,
            independent_motion_authority_replay_passed=True,motion_authority_replay=proof)

    def test_public_runtime_missing_authority_profile_rejected_before_source_or_raw(self):
        metadata=dict(safety_contract='mr3-reach-v1',actuation_profile='initial-zero-encoder-hold-v1')
        fake=SimpleNamespace(read=lambda *args:metadata)
        with patch.object(runtime,'Inputs',return_value=fake),patch.object(runtime,'source_proof') as source:
            with self.assertRaises(ValueError):runtime.audit_episode('/artificial/not-read','a'*40)
            source.assert_not_called()

    def test_public_role_requires_all_robots_stop_debts_protocol_and_unknown_generation(self):
        authority.require_episode_proof(self.report())
        for attack in ('robot','generation','debt','protocol','top'):
            report=self.report();proof=report['motion_authority_replay']
            if attack=='robot':proof['robots'].pop('tb3')
            elif attack=='generation':proof['raw_generation_known']=True
            elif attack=='debt':proof['original_global_stop_debts_and_fixed_radius_passed']=False
            elif attack=='protocol':proof['adapter']['original_six_phase_protocol_replayed']=False
            else:report['independent_motion_authority_replay_passed']=False
            with self.subTest(attack=attack),self.assertRaises(ValueError):authority.require_episode_proof(report)

    def test_full_public_motion_and_execution_input_routes_require_substantive_proof(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'plan.json';path.write_text(json.dumps(dict(safety_contract='mr3-reach-v1',
                motion_authority_profile=profile.MOTION_AUTHORITY_PROFILE)))
            module,_=full.load_impl(path)
            with patch.object(peer,'audit_episode',return_value=dict(passed=True)):
                with self.assertRaises(ValueError):module.audit_motion('/artificial/not-read')
            with self.assertRaises(ValueError):module.audit_execution_inputs('/artificial/not-read',dict(passed=True))

    def test_controlled_both_public_dispatches_forward_exact_plan_context(self):
        plan=Path('/artificial/plan-not-read.json');calls=[]
        fake=SimpleNamespace(dispatch_controlled_physics=lambda *args,**kwargs:calls.append('physics'),
            dispatch_controlled_readiness=lambda *args,**kwargs:calls.append('readiness'))
        with patch.object(controlled,'load_impl',return_value=(fake,{})) as load:
            controlled.dispatch_controlled_physics('a',plan_path=plan)
            controlled.dispatch_controlled_readiness('a',plan_path=plan)
        self.assertEqual(calls,['physics','readiness'])
        self.assertEqual(load.call_args_list[0].kwargs,dict(plan_path=plan))
        self.assertEqual(load.call_args_list[1].kwargs,dict(plan_path=plan))


if __name__=='__main__':unittest.main()
