"""Build explicit disabled ABI and run finite artificial sensor-chain checks."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import shlex
import subprocess

A = Path(__file__).resolve().parent
ROOT = next(p for p in A.parents if (p / '.git').exists())
ROS = ROOT / 'ros2_ws/ros2-multi-robot-automap'
PKG = ROS / 'src/multi_robot_exploration'
SDK = ROS / 'src/slam_toolbox/lib/karto_sdk'
LIB = (ROS / 'build/slam_toolbox/lib/karto_sdk/libkartoSlamToolbox.so').resolve()
HELPER = A.parent / '20261021_mr3_p2a_v29_karto/run_cpu_v1.py'
spec = importlib.util.spec_from_file_location('karto_cpu_process_helper', HELPER)
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)
sha, phase = helper.sha, helper.phase


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build-dir',type=Path,required=True)
    parser.add_argument('--evidence-dir',type=Path,required=True)
    args = parser.parse_args()
    args.build_dir.mkdir(parents=True,exist_ok=False)
    E = args.evidence_dir.resolve()
    assert E.is_relative_to(A)
    E.mkdir(parents=True,exist_ok=False)
    compiler = Path('/usr/bin/g++').resolve()
    sources = [Path(__file__),A/'predeclared_plan_v1.json',HELPER,LIB,compiler,
        PKG/'multi_robot_exploration/mr3_proxy2d_karto_native.cpp',
        PKG/'multi_robot_exploration/mr3_proxy2d_karto.py',
        PKG/'test/proxy2d_karto_cpu.py',PKG/'test/test_mr3_proxy2d_mapping_quality.py',
        PKG/'multi_robot_exploration/mr3_proxy2d_world.py',
        PKG/'multi_robot_exploration/mr3_task_contract.py',
        PKG/'multi_robot_exploration/task_evaluator.py']
    sources += sorted((SDK/'include/karto_sdk').glob('*.h'))
    sources += sorted((SDK/'include/karto_sdk').glob('*.hpp'))
    before = [sha(p) for p in sources]
    env = dict(os.environ,PATH='/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin',
        PYTHONNOUSERSITE='1',PYTHONDONTWRITEBYTECODE='1',CUDA_VISIBLE_DEVICES='')
    for key in ('LD_LIBRARY_PATH','LD_PRELOAD','PYTHONPATH','PYTHONHOME','LIBRARY_PATH',
                'CPATH','CPLUS_INCLUDE_PATH','C_INCLUDE_PATH'):
        env.pop(key,None)
    binary = args.build_dir.resolve()/'libmr3_karto_adapter.so'
    command = [str(compiler),'-std=c++17','-O1','-fPIC','-shared','-I'+str(SDK/'include'),
        '-I/usr/include/eigen3',str(sources[5]),str(LIB),'-lboost_serialization','-ltbb',
        '-Wl,-rpath,'+str(LIB.parent),'-o',str(binary)]
    result = dict(schema='mr3-p2a-v30-adapter-build-v1',passed=False,phases=[],
        source_before=before,compiler_version=subprocess.check_output([str(compiler),'--version'],env=env,text=True),
        new_engineering_seconds='0',production_enabled=False,qualification=False)
    try:
        build = phase('compile',command,E/'compile_stdout.log',E/'compile_stderr.log',90,env)
        result['phases'].append(build)
        assert build['returncode']==0 and not build['signals'] and not build['identity_capture_error']
        result['binary'] = sha(binary)
        result['elf_dynamic'] = subprocess.check_output(['/usr/bin/readelf','-d',str(binary)],env=env,text=True)
        script = ('source /opt/ros/humble/setup.bash\nsource '+shlex.quote(str(ROS/'install/setup.bash'))+
            '\nexport LD_LIBRARY_PATH='+shlex.quote(str(LIB.parent))+':"$LD_LIBRARY_PATH"\n'+
            'exec /usr/bin/python3 -B '+shlex.quote(str(PKG/'test/proxy2d_karto_cpu.py'))+
            ' --library '+shlex.quote(str(binary))+' --output '+shlex.quote(str(E/'adapter_result_v1.json')))
        run = phase('adapter_cpu',['/usr/bin/bash','-c',script],E/'test_stdout.log',
                    E/'test_stderr.log',60,env)
        result['phases'].append(run)
        assert run['returncode']==0 and not run['signals'] and not run['identity_capture_error']
        probe = json.loads((E/'adapter_result_v1.json').read_text())
        assert probe['passed'] is True and probe['tests']==14
        assert {Path(p).resolve() for p in probe['loaded_karto_paths']}=={LIB}
        assert probe['identity']==run['saved_identity']
        result['passed']=True
    except Exception as error:
        result['error']=repr(error)
    result['source_after']=[sha(p) for p in sources]
    result['source_unchanged']=result['source_before']==result['source_after']
    result['passed'] &= result['source_unchanged']
    with (E/'build_receipt_v1.json').open('x') as stream:
        json.dump(result,stream,indent=2,allow_nan=False)
        stream.write('\n')
    print(json.dumps({k:result.get(k) for k in ('passed','source_unchanged','error')}))
    return 0 if result['passed'] else 1


if __name__=='__main__':
    raise SystemExit(main())
