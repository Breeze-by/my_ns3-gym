"""Seal and run the declared V60 artificial CPU groups; never a World activity."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import subprocess

ROOT = Path('/home/zhuyulab/ns3-workspace')
W = ROOT / 'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl'
ROS = ROOT / 'ros2_ws/ros2-multi-robot-automap'
A = Path(__file__).resolve().parent
SPEC = A / 'fresh_cpu_spec_v2.json'
PYTHON = '/home/zhuyulab/miniconda3/envs/ns3gym/bin/python'
P = ROS / 'src/multi_robot_exploration/multi_robot_exploration'
ROS_TEST = ROS / 'src/multi_robot_exploration/test'
W_TEST = W / 'mr3_learning/tests'


def load(path):
    def unique(pairs):
        value = dict(pairs)
        if len(value) != len(pairs):
            raise ValueError('duplicate fresh CPU JSON member')
        return value
    return json.loads(Path(path).read_text(), object_pairs_hook=unique,
        parse_constant=lambda value: (_ for _ in ()).throw(ValueError('nonfinite CPU JSON')))


def proof(path):
    path = Path(path)
    before = path.stat()
    raw = path.read_bytes()
    after = path.stat()
    if any(getattr(before,k) != getattr(after,k) for k in ('st_dev','st_ino','st_size','st_mtime_ns','st_ctime_ns')):
        raise ValueError('CPU source changed while reading: '+str(path))
    return {'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw)}


def python_paths():
    # Filesystem union is intentional: Git-add cannot turn an untracked test
    # from an artifact into runtime after this preparation has been measured.
    paths = set()
    for directory in (W/'mr3_learning', W_TEST, P, ROS_TEST,
                      ROS/'src/merge_map/merge_map', ROS/'src/merge_map/test', A):
        paths.update(directory.glob('*.py'))
    paths.update((ROS/'scripts/mr3_env_worker.py',
        ROS/'src/multi_robot/launch/gazebo_multirobot_mapping_with_nav2.launch.py'))
    return sorted(paths)


def current_python_paths():
    return {str(p.relative_to(ROOT)) for p in python_paths() if p.parent != A}


def changed_python_paths(baseline):
    changed = set()
    for relative in current_python_paths():
        previous = subprocess.run(['git','show',baseline+':'+relative], cwd=ROOT,
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        if previous.returncode != 0 or previous.stdout != (ROOT/relative).read_bytes():
            changed.add(relative)
    return changed


def group_argv(group):
    tests = [str(ROOT/relative) for relative in group['test_files']]
    junit = str(A/'checks'/group['id']/'junit.xml')
    python = '/usr/bin/python3' if group['environment'] == 'ros-system' else PYTHON
    command = [python,'-B','-m','pytest','-q',*tests,'--junitxml',junit]
    if group['environment'] == 'ros-system':
        text = ('source /opt/ros/humble/setup.bash && source '+
            shlex.quote(str(ROS/'install/setup.bash'))+' && exec '+shlex.join(command))
        return ['/usr/bin/bash','--noprofile','--norc','-e','-c',text]
    return command


def validate_spec(spec, *, sealed=True):
    if (spec.get('schema') != 'mr3-v65-fresh-cpu-spec-v1' or
        spec.get('source_policy') != 'explicit-filesystem-python-runtime-and-test-union-v1' or
        spec.get('scientific_qualification_credit') is not False or
        re.fullmatch('[0-9a-f]{40}',spec.get('baseline_freeze','')) is None):
        raise ValueError('invalid V60 fresh CPU declaration')
    if subprocess.check_output(['git','cat-file','-t',spec['baseline_freeze']],cwd=ROOT).strip() != b'commit':
        raise ValueError('CPU baseline is not an existing exact commit')
    groups = spec.get('groups')
    if type(groups) is not list or {g.get('environment') for g in groups} != {'ros-system','ns3gym'} or len(groups) != 2:
        raise ValueError('exact ROS/system and ns3gym CPU groups required')
    if len({g['id'] for g in groups}) != 2:
        raise ValueError('duplicate CPU group id')
    for group in groups:
        if re.fullmatch('[a-z0-9_]+',group['id']) is None or not group['test_files'] or len(group['test_files']) != len(set(group['test_files'])):
            raise ValueError('invalid CPU group/test set')
        directories = (ROS_TEST, ROS/'src/merge_map/test') if group['environment'] == 'ros-system' else (W_TEST,)
        for name in group['test_files']:
            path = ROOT/name
            if path.parent not in directories or not path.name.startswith('test_') or path.suffix != '.py' or not path.is_file():
                raise ValueError('unexpected artificial CPU test path: '+name)
        if group.get('actual_argv') != group_argv(group):
            raise ValueError('CPU command differs from declared exact tests')
    if sealed:
        if type(spec.get('source_bindings')) is not dict or any(
            type(relative) is not str or type(row) is not dict or set(row) != {'sha256','bytes'} or
            type(row['bytes']) is not int or row['bytes'] < 0 or type(row['sha256']) is not str or
            re.fullmatch('[0-9a-f]{64}',row['sha256']) is None
            for relative,row in spec['source_bindings'].items()):
            raise ValueError('malformed sealed CPU source binding')
        if spec.get('status') != 'SEALED_NOT_EXECUTED' or spec.get('source_bindings') != {
            str(path.relative_to(ROOT)):proof(path) for path in python_paths()}:
            raise ValueError('CPU tested sources are not the sealed exact current filesystem union')
        changed = changed_python_paths(spec['baseline_freeze'])
        if set(spec['replacement_paths']) != changed:
            raise ValueError('changed/new Python production/test set differs from sealed scope')
        covered = set()
        for group in groups:
            expected = {name for name in changed if name.startswith(
                'ros2_ws/' if group['environment'] == 'ros-system' else str((W/'mr3_learning').relative_to(ROOT))+'/')}
            if set(group['covered_paths']) != expected:
                raise ValueError('new current source has no exact assigned CPU group')
            covered.update(expected)
        if covered != changed:
            raise ValueError('changed/new Python source lacks fresh CPU coverage')
    return spec


def seal():
    spec = load(SPEC)
    validate_spec(spec,sealed=False)
    if spec.get('status') != 'PREPARED_UNSEALED':
        raise ValueError('sealed CPU declarations are not silently rewritten')
    changed = changed_python_paths(spec['baseline_freeze'])
    for group in spec['groups']:
        prefix = 'ros2_ws/' if group['environment'] == 'ros-system' else str((W/'mr3_learning').relative_to(ROOT))+'/'
        group['covered_paths'] = sorted(name for name in changed if name.startswith(prefix))
        directories = (ROS_TEST, ROS/'src/merge_map/test') if group['environment'] == 'ros-system' else (W_TEST,)
        group['test_files'] = sorted(set(group['test_files']) | {
            name for name in changed if (ROOT/name).parent in directories and (ROOT/name).name.startswith('test_')})
        group['actual_argv'] = group_argv(group)
    spec['replacement_paths'] = sorted(changed)
    spec['source_bindings'] = {str(path.relative_to(ROOT)):proof(path) for path in python_paths()}
    spec['status'] = 'SEALED_NOT_EXECUTED'
    validate_spec(spec)
    SPEC.write_text(json.dumps(spec,indent=2)+'\n')
    print(json.dumps({'sealed':True,'groups':[g['id'] for g in spec['groups']],
        'changed_python_sources':len(changed),'source_bindings':len(spec['source_bindings'])}))


def run(group_name):
    spec = validate_spec(load(SPEC))
    group = next(g for g in spec['groups'] if g['environment'] == group_name)
    sources = python_paths()+[SPEC]
    snapshots = A/'checks/source_snapshots'
    snapshots.mkdir(parents=True,exist_ok=True)
    rows = []
    for path in sources:
        raw = path.read_bytes(); relative = str(path.relative_to(ROOT)); value = proof(path)
        if hashlib.sha256(raw).hexdigest() != value['sha256'] or len(raw) != value['bytes']:
            raise ValueError('source changed while preparing its CPU recovery')
        previous = subprocess.run(['git','show',spec['baseline_freeze']+':'+relative],cwd=ROOT,
            stdout=subprocess.PIPE,stderr=subprocess.DEVNULL)
        row = dict(path=relative,**value)
        if previous.returncode == 0 and previous.stdout == raw:
            row.update(kind='git_blob',freeze=spec['baseline_freeze'])
        else:
            target = snapshots/(value['sha256']+'_'+path.name)
            if target.exists():
                if target.read_bytes() != raw: raise ValueError('CPU source snapshot collision')
            else:
                with target.open('xb') as stream:stream.write(raw)
            row.update(kind='snapshot',snapshot=str(target.relative_to(A)))
        rows.append(row)
    recovery = A/'checks'/(group['id']+'_source_recovery.json')
    with recovery.open('x') as stream:
        json.dump({'baseline_freeze':spec['baseline_freeze'],'sources':rows},stream,indent=2);stream.write('\n')
    python = '/usr/bin/python3' if group_name == 'ros-system' else PYTHON
    argv=[python,'-B','-m','mr3_learning.reach_execution','--scope','cpu','--output',str(A/'checks'/group['id'])]
    for path in sources:argv+=['--source',str(path)]
    argv+=['--',*group['actual_argv']]
    env=dict(os.environ,PYTHONNOUSERSITE='1',PYTHONDONTWRITEBYTECODE='1',CUDA_VISIBLE_DEVICES='')
    env.pop('PYTHONPATH',None)
    env.pop('PYTHONHOME',None)
    return subprocess.call(argv,cwd=W,env=env)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    choose=parser.add_mutually_exclusive_group(required=True)
    choose.add_argument('--seal',action='store_true')
    choose.add_argument('--group',choices=('ros-system','ns3gym'))
    args=parser.parse_args()
    if args.seal:return seal()
    return run(args.group)


if __name__ == '__main__':
    raise SystemExit(main())
