"""Actual canonical worker profile entry and metadata; no ROS graph/World."""
import ast
import copy
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace as NS
import unittest
from multi_robot_exploration.mr3_motion_authority import PROFILE

SCRIPTS=Path(__file__).resolve().parents[3]/'scripts'
sys.path.insert(0,str(SCRIPTS))
spec=importlib.util.spec_from_file_location('_mr3_authority_worker_canonical',SCRIPTS/'mr3_env_worker.py')
worker=importlib.util.module_from_spec(spec);spec.loader.exec_module(worker)
assert Path(worker.__file__).resolve()==(SCRIPTS/'mr3_env_worker.py').resolve()
worker_tree=ast.parse(Path(worker.__file__).read_text())

class WorkerProfileContracts(unittest.TestCase):
    def test_actual_request_helper_and_constructor_reject_mixed_profile_before_ROS_start(self):
        self.assertIsNone(worker.motion_authority_profile_from_request({}))
        self.assertIsNone(worker.motion_authority_profile_from_request({'safety_contract':'legacy','motion_authority_profile':None}))
        self.assertEqual(worker.motion_authority_profile_from_request({'safety_contract':'mr3-reach-v1','motion_authority_profile':PROFILE}),PROFILE)
        for contract,profile in (('legacy',PROFILE),('mr3-reach-v1',None),('mr3-reach-v1',True),
                                 ('mr3-reach-v1',''),('mr3-reach-v1','initial-zero-encoder-hold-v1')):
            request={'epoch':'artificial','scene':'open','seed':101,'safety_contract':contract,'motion_authority_profile':profile}
            with self.assertRaises(ValueError):worker.motion_authority_profile_from_request(request)
            with tempfile.TemporaryDirectory() as directory:
                with self.assertRaisesRegex(ValueError,'receiving-authority profile'):
                    worker.Worker(Path(directory),request)
        for contract in (True,None,[],{},1):
            with self.assertRaises(ValueError):worker.motion_authority_profile_from_request({'safety_contract':contract})

    def test_actual_constructor_launch_metadata_region_has_fixed_profile_no_extra_CLI(self):
        cls=next(n for n in worker_tree.body if isinstance(n,ast.ClassDef) and n.name=='Worker')
        init=next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name=='__init__')
        start=next(i for i,n in enumerate(init.body) if isinstance(n,ast.Assign)
            and any(isinstance(t,ast.Attribute) and t.attr=='command' for t in n.targets))
        end=next(i for i,n in enumerate(init.body) if i>start and isinstance(n,ast.Expr)
            and isinstance(n.value,ast.Call) and isinstance(n.value.func,ast.Attribute)
            and n.value.func.attr=='write_text')
        # Exact actual constructor source; only graph/process initialization is
        # excluded. This does not claim that the full worker actually launched.
        for contract in ('legacy','mr3-reach-v1'):
            with tempfile.TemporaryDirectory() as temporary:
                directory=Path(temporary)
                shell=NS(epoch='artificial_epoch',scene='open',seed=101,safety_contract=contract,
                    motion_authority_profile=PROFILE if contract=='mr3-reach-v1' else None,
                    reach_geometry_rule='binary-cone-v1',seed_rule='legacy',start_graph_rule='original-seed-cell',
                    preparation_probe_version=None,terminal_probe=False,plant_stimulus_arm=None,
                    plant_stimulus_work_deadline_ns=None,transport_environment={},
                    control_version=2 if contract=='mr3-reach-v1' else 1,
                    startup_readiness_protocol='received-input-pause-drain-v1',startup_deadline_ns=900,
                    startup_wait_deadline_ns=800)
                namespace=dict(vars(worker),self=shell,directory=directory,
                    subprocess=NS(check_output=lambda *args,**kwargs:'a'*40))
                exec(compile(ast.Module(body=init.body[start:end+1],type_ignores=[]),worker.__file__,'exec'),namespace)
                metadata=json.loads((directory/'metadata.json').read_text())
                self.assertEqual(metadata.get('motion_authority_profile'),shell.motion_authority_profile)
                self.assertIn('mr3_safety_contract:='+contract,shell.command)
                self.assertFalse(any('motion_authority_profile:=' in x for x in shell.command))
                self.assertEqual(metadata.get('actuation_profile'),
                    'initial-zero-encoder-hold-v1' if contract=='mr3-reach-v1' else None)

if __name__=='__main__':unittest.main(verbosity=2)
