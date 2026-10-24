"""Artificial metadata/RPC/public admission only; no ROS graph or learning."""
import ast
import contextlib
import copy
import importlib
import io
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch

from mr3_learning import motion_authority_profile as profiles
from mr3_learning import supervisor as sup
from mr3_learning import benchmark as bench
from mr3_learning import ppo
from mr3_learning import reach_preparation as preparation
# These are ordinary installed/source-package imports, never /tmp candidates.
ROOT=sup.WORKSPACE
W=ROOT/'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl'
PROFILE=profiles.MOTION_AUTHORITY_PROFILE
assert Path(sup.__file__).resolve()==(W/'mr3_learning/supervisor.py').resolve()
assert Path(bench.__file__).resolve()==(W/'mr3_learning/benchmark.py').resolve()
assert Path(ppo.__file__).resolve()==(W/'mr3_learning/ppo.py').resolve()


class AdmissionReached(Exception):pass


def artificial_qualification():
    episodes=[{'directory':f'/ARTIFICIAL/episode{i:03d}','epoch':f'artificial-{i}'} for i in range(12)]
    proof={'schema':'mr3-independent-motion-authority-qualification-v1','profile':PROFILE,
        'passed':True,'freeze':'a'*40,'raw_generation_known':False,
        'episodes':[dict(row,passed=True,profile=PROFILE,robots=['tb1','tb2','tb3'],
                         runtime_result_sha256='0'*64) for row in episodes]}
    return {'safety_contract':'mr3-reach-v1','motion_authority_profile':PROFILE,
            'freeze':'a'*40,'episodes':episodes,'motion_authority_replay':proof}


class MetadataEntryContracts(unittest.TestCase):

    def test_supervisor_actual_reset_rpc_metadata_and_legacy_shape(self):
        self.assertIsNone(profiles.motion_authority_profile_for_safety_contract('legacy'))
        self.assertEqual(profiles.motion_authority_profile_for_safety_contract('mr3-reach-v1'),PROFILE)
        for bad in (True,None,1,[],{},'reach'):
            with self.assertRaises(ValueError):profiles.motion_authority_profile_for_safety_contract(bad)
        for contract in ('legacy','mr3-reach-v1'):
            with tempfile.TemporaryDirectory() as temp:
                supervisor=sup.Supervisor(output_root=temp,safety_contract=contract)
                requests=[]
                class Peer:
                    def send(self,value):requests.append(copy.deepcopy(value))
                    def receive(self,timeout):
                        value=requests[-1]
                        return {'id':value['id'],'epoch':value['epoch'],'ok':True,
                                'result':{'snapshot':{'epoch':value['epoch']}}}
                fixture_identity={'pid':12345,'parent':1,'group':12345,'session':12345,'start_ticks':5,'state':'S'}
                dummy=NS(pid=12345,stdout=NS(fileno=lambda:0),stdin=NS(fileno=lambda:1))
                with patch.object(sup.subprocess,'Popen',return_value=dummy) as launch, \
                     patch.object(sup,'process_identity',return_value=fixture_identity), \
                     patch.object(sup,'JsonLinePeer',return_value=Peer()), \
                     patch.object(sup,'remember_processes'):
                    try:result=supervisor.reset(scene='open',seed=101)
                    finally:
                        if supervisor.episode is not None:
                            supervisor.episode.stop_monitor.set();supervisor.episode.monitor.join(timeout=1)
                            supervisor.episode.output.close()
                self.assertEqual(requests[0]['op'],'reset')
                metadata=json.loads((supervisor.episode.directory/'supervisor_metadata.json').read_text())
                expected=PROFILE if contract=='mr3-reach-v1' else None
                self.assertEqual(supervisor.motion_authority_profile,expected)
                self.assertEqual(requests[0].get('motion_authority_profile'),expected)
                self.assertEqual(metadata.get('motion_authority_profile'),expected)
                if expected is None:
                    self.assertNotIn('motion_authority_profile',requests[0])
                    self.assertNotIn('motion_authority_profile',metadata)
                else:
                    self.assertEqual(requests[0]['safety_contract'],'mr3-reach-v1')
                    self.assertEqual(metadata['actuation_profile'],'initial-zero-encoder-hold-v1')
                self.assertEqual(result['snapshot']['epoch'],requests[0]['epoch'])
                launch.assert_called_once()


    def test_public_benchmark_records_fixed_profile_without_native_worker(self):
        for contract in ('legacy','mr3-reach-v1'):
            with tempfile.TemporaryDirectory() as temp, patch.object(bench,'run_worker',return_value={
                    'worker_id':0,'episodes':[{'transitions':1,'truncated':True,'terminated':False}],
                    'shutdown_receipts':[],'error':None}), patch.object(bench,'resource_sample',return_value={}):
                with contextlib.redirect_stdout(io.StringIO()):
                    bench.main(['--workers','1','--steps','1','--schedule','open:101','--run-id','fixture',
                                '--output-root',temp,'--safety-contract',contract])
                metadata=json.loads((Path(temp)/'fixture/benchmark_metadata.json').read_text())
                self.assertEqual(metadata.get('motion_authority_profile'),PROFILE if contract=='mr3-reach-v1' else None)
                self.assertEqual(metadata.get('actuation_profile'),
                    'initial-zero-encoder-hold-v1' if contract=='mr3-reach-v1' else None)
                if contract=='mr3-reach-v1':self.assertFalse(metadata['training_eligible'])

    def test_public_PPO_missing_or_mixed_authority_refuses_before_targets_or_model(self):
        base={'safety_contract':'mr3-reach-v1','actuation_profile':'initial-zero-encoder-hold-v1',
              'motion_authority_profile':PROFILE}
        # Reader qualification is mocked only at the preexisting admission API;
        # this checks public PPO's extra refusal, not native qualification.
        for plan,qualification in ((dict(base),{}),
                ({k:v for k,v in base.items() if k!='motion_authority_profile'},artificial_qualification()),
                (dict(base,motion_authority_profile='wrong'),artificial_qualification()),
                (dict(base),{'motion_authority_profile':PROFILE,'motion_authority_proof':{'passed':False}})):
            with tempfile.TemporaryDirectory() as temp, \
                 patch.object(preparation,'load_plan',return_value=plan), \
                 patch.object(preparation,'validate_qualification',return_value=qualification), \
                 patch.object(ppo.subprocess,'check_output',return_value='a'*40), \
                 patch.object(ppo,'MaskablePPO') as model, \
                 patch.object(ppo,'build_rollout_buffer') as targets, \
                 patch.object(ppo,'collect_episodes') as collect, \
                 contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises((ValueError,SystemExit)):
                    ppo.main(['--run-id','refused','--output-root',temp,'--decisions','2','--wall-seconds','1',
                        '--device','cpu','--safety-contract','mr3-reach-v1','--reach-plan',temp+'/plan.json',
                        '--reach-qualification',temp+'/qualification.json'])
                model.assert_not_called();targets.assert_not_called();collect.assert_not_called()
                self.assertFalse((Path(temp)/'refused').exists())

    def test_public_PPO_positive_complete_twelve_role_gate_reaches_only_pre_model_boundary(self):
        plan={'safety_contract':'mr3-reach-v1','actuation_profile':'initial-zero-encoder-hold-v1',
              'motion_authority_profile':PROFILE}
        qualification=artificial_qualification();proof=qualification['motion_authority_replay']
        self.assertEqual(profiles.require_qualified_motion_authority(qualification),proof)
        for mutate in (lambda q:q['motion_authority_replay']['episodes'].pop(),
                       lambda q:q['motion_authority_replay'].update(raw_generation_known=True),
                       lambda q:q['motion_authority_replay']['episodes'][0].update(robots=['tb1','tb2'])):
            invalid=copy.deepcopy(qualification);mutate(invalid)
            with self.assertRaises(ValueError):profiles.require_qualified_motion_authority(invalid)
        with tempfile.TemporaryDirectory() as temp, \
             patch.object(preparation,'load_plan',return_value=plan), \
             patch.object(preparation,'validate_qualification',return_value=qualification), \
             patch.object(ppo.subprocess,'check_output',return_value='a'*40), \
             patch.object(ppo.time,'monotonic',side_effect=AdmissionReached('after admission before model')), \
             patch.object(ppo,'MaskablePPO') as model, \
             patch.object(ppo,'build_rollout_buffer') as targets:
            with self.assertRaises(AdmissionReached):
                ppo.main(['--run-id','stopped_before_model','--output-root',temp,'--decisions','2',
                    '--wall-seconds','1','--device','cpu','--safety-contract','mr3-reach-v1',
                    '--reach-plan',temp+'/plan.json','--reach-qualification',temp+'/qualification.json'])
            model.assert_not_called();targets.assert_not_called()
            self.assertFalse((Path(temp)/'stopped_before_model').exists())


if __name__=='__main__':unittest.main(verbosity=2)
