"""Fixed two-file runtime adapter, method-level Git I/O fixture; no native admission."""
import ast
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import types
import unittest
from unittest import mock

D=Path(__file__).parent
REAL_ROOT=Path('/home/zhuyulab/ns3-workspace')
W='ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/'
AUDITOR=W+'mr3_learning/audit_ppo.py'
FREEZE='a'*40


class RuntimeProjection(unittest.TestCase):
    def setUp(self):
        spec=importlib.util.spec_from_file_location('new_projection',D/'mr3_p2a0_v21_ray_preflight_v1.py')
        self.pre=importlib.util.module_from_spec(spec);spec.loader.exec_module(self.pre)
        self.directory=tempfile.TemporaryDirectory(prefix='mr3_v21_projection_CPU_')
        self.addCleanup(self.directory.cleanup);self.root=Path(self.directory.name)
        self.blobs={}
        for relative in self.pre.RAY_EXECUTION_DELTAS:
            if relative.endswith('/CMakeLists.txt'):raw=(REAL_ROOT/relative).read_bytes()
            else:raw=(D/'proposed_launch.py').read_bytes()
            self.write(relative,raw);self.blobs[(FREEZE,relative)]=raw
            self.blobs[(self.pre.RAY_NORMATIVE_FREEZE,relative)]=subprocess.check_output(
                ['git','show',self.pre.RAY_NORMATIVE_FREEZE+':'+relative],cwd=REAL_ROOT)
        raw=(REAL_ROOT/AUDITOR).read_bytes();self.write(AUDITOR,raw);self.blobs[(FREEZE,AUDITOR)]=raw
        tree=ast.parse(raw)
        assignment=next(n for n in tree.body if isinstance(n,ast.Assign) and any(
            isinstance(t,ast.Name) and t.id=='EXECUTION_CONFIG_PINS' for t in n.targets))
        namespace={'ROS':'ros2_ws/ros2-multi-robot-automap/','WIRELESS':W}
        exec(compile(ast.Module(body=[assignment],type_ignores=[]),'actual_fixed_pin_declaration','exec'),namespace)
        self.module=types.ModuleType('mr3_learning.audit_ppo');self.module.EXECUTION_CONFIG_PINS=namespace['EXECUTION_CONFIG_PINS']
        self.original=self.module.EXECUTION_CONFIG_PINS;self.copy=dict(self.original);self.called=0
        def fake_loader(root,freeze):
            self.called+=1;self.assertEqual(root,self.root);self.assertEqual(freeze,FREEZE)
            changes={p:v for p,v in self.module.EXECUTION_CONFIG_PINS.items() if v!=self.original[p]}
            self.assertEqual(changes,{p:v[1] for p,v in self.pre.RAY_EXECUTION_DELTAS.items()})
            return ('method-level unchanged gate stub',{'source_bindings':'not actual native admission'})
        self.module.load_native_gates=fake_loader
        package=types.ModuleType('mr3_learning');package.__path__=[];package.audit_ppo=self.module
        self.package=package
        self.pre.ROOT=self.root
        self.pre.git_raw=lambda freeze,path:self.blobs[(freeze,str(path))]

    def write(self,relative,raw):
        path=self.root/relative;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)

    def run_adapter(self):
        with mock.patch.dict(sys.modules,{'mr3_learning':self.package,'mr3_learning.audit_ppo':self.module}):
            return self.pre.load_native_gates_with_ray(FREEZE)

    def test_actual_two_sources_inverse_and_only_two_pins_changed(self):
        result,proof=self.run_adapter()
        self.assertEqual(self.called,1);self.assertTrue(proof['original_pin_dict_restored'])
        self.assertEqual(len(proof['files']),2)
        self.assertTrue(all(v['strict_inverse_whole_bytes_equal'] for v in proof['files'].values()))
        self.assertIs(self.module.EXECUTION_CONFIG_PINS,self.original)
        self.assertEqual(self.module.EXECUTION_CONFIG_PINS,self.copy)

    def test_loader_error_always_restores_entire_original_dict(self):
        def failed(root,freeze):raise RuntimeError('actual loader failure fixture')
        self.module.load_native_gates=failed
        with self.assertRaisesRegex(RuntimeError,'actual loader failure'):self.run_adapter()
        self.assertIs(self.module.EXECUTION_CONFIG_PINS,self.original)
        self.assertEqual(self.module.EXECUTION_CONFIG_PINS,self.copy)

    def test_wrong_actual_source_or_git_bytes_refused(self):
        for relative in self.pre.RAY_EXECUTION_DELTAS:
            path=self.root/relative;raw=path.read_bytes();path.write_bytes(raw+b'\n# extra unintended delta\n')
            with self.subTest(actual_path=relative),self.assertRaises(ValueError):self.run_adapter()
            path.write_bytes(raw)
            self.blobs[(FREEZE,relative)]=raw+b'wrong frozen source'
            with self.subTest(git_path=relative),self.assertRaises(ValueError):self.run_adapter()
            self.blobs[(FREEZE,relative)]=raw
        self.assertEqual(self.called,0)
        self.assertIs(self.module.EXECUTION_CONFIG_PINS,self.original)

    def test_wrong_normative_blob_original_pin_or_auditor_refused(self):
        relative=next(iter(self.pre.RAY_EXECUTION_DELTAS))
        key=(self.pre.RAY_NORMATIVE_FREEZE,relative);old=self.blobs[key];self.blobs[key]=old+b'changed baseline'
        with self.assertRaises(ValueError):self.run_adapter()
        self.blobs[key]=old
        self.original[relative]='0'*64
        with self.assertRaises(ValueError):self.run_adapter()
        self.original[relative]=self.copy[relative]
        raw=(self.root/AUDITOR).read_bytes();(self.root/AUDITOR).write_bytes(raw+b'changed auditor')
        with self.assertRaises(ValueError):self.run_adapter()
        self.assertEqual(self.called,0)
        self.assertIs(self.module.EXECUTION_CONFIG_PINS,self.original)


if __name__=='__main__':unittest.main()
