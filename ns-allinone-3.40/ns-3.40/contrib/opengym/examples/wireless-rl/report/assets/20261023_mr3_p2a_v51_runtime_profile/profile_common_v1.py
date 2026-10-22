"""Disabled prospective profile helpers: stdlib, no application import here."""
from decimal import Decimal
import hashlib
import gzip
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import time

ROOT = Path('/home/zhuyulab/ns3-workspace')
W = ROOT / 'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl'
EPISODE = ROOT / ('ros2_ws/ros2-multi-robot-automap/log/mr3_p2a_reach_v50/'
    'mr3_p2a_reach_v50_reset/worker0/episode001_open_101')
EVIDENCE_FREEZE = '23e909380b470039bd5680cf2d07710dca71097e'
RUNTIME = 'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/mr3_learning/audit_reach_runtime.py'
SUPPORT = 'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/mr3_learning/reach_support_replay.py'
INIT = 'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/mr3_learning/__init__.py'
PURE = 'ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/multi_robot_exploration/'
NATIVE = 'ros2_ws/ros2-multi-robot-automap/src/multi_robot/'
# Exact source_proof() set for cone-support-v2; __init__ is an extra import pin.
EVIDENCE_SOURCES = {PURE + name for name in (
    'motion_safety.py', 'mr3_reach_runtime.py', 'mr3_reach_geometry.py',
    'mr3_velocity_metric.py', 'mr3_safety_intent.py', 'mr3_information.py',
    'peer_obstacles.py', 'mr3_control_phase.py', 'mr3_motion_control.py',
    'mr3_drive_phase.py', 'mr3_episode.py', 'mr3_motion_safety.py', 'mr3_reach_support.py')}
EVIDENCE_SOURCES.update(NATIVE + name for name in (
    'src/mr3_gazebo_diff_drive.cpp', 'CMakeLists.txt', 'include/multi_robot/mr3_drive_feed.hpp',
    'include/multi_robot/paired_wheel_slew.hpp', 'include/multi_robot/mr3_drive_target.hpp',
    'include/multi_robot/mr3_odometry_json.hpp', 'launch/gazebo_multirobot_mapping_with_nav2.launch.py'))
EVIDENCE_SOURCES.update((RUNTIME, SUPPORT, INIT, 'ros2_ws/ros2-multi-robot-automap/scripts/mr3_env_worker.py'))
INPUTS = ('metadata.json', 'supervisor_metadata.json', 'transitions.jsonl',
    'drive_tb1.jsonl', 'drive_tb2.jsonl', 'drive_tb3.jsonl',
    'odometry_tb1.jsonl', 'odometry_tb2.jsonl', 'odometry_tb3.jsonl',
    'motion_safety.jsonl', 'physics.jsonl', 'drive_phase_worker.jsonl',
    'control_phase_worker.jsonl', 'information_states.jsonl')


def require(value, message):
    if not value:
        raise ValueError(message)


def stamp(path):
    s = path.lstat()
    require(stat.S_ISREG(s.st_mode), 'not a non-symlink regular file: ' + str(path))
    return [s.st_dev, s.st_ino, s.st_mode, s.st_size, s.st_mtime_ns, s.st_ctime_ns]


def remaining(deadline_ns, maximum=None):
    seconds = (deadline_ns - time.monotonic_ns()) / 1e9
    require(seconds > 0, 'prospective main work deadline exhausted')
    return seconds if maximum is None else min(seconds, maximum)


def bind(path, expected=None, deadline_ns=None):
    path = Path(path)
    before = stamp(path)
    digest, size = hashlib.sha256(), 0
    with path.open('rb') as stream:
        while True:
            if deadline_ns is not None:
                remaining(deadline_ns)
            block = stream.read(1024 * 1024)
            if not block:
                break
            digest.update(block); size += len(block)
    require(stamp(path) == before, 'file changed during hashing: ' + str(path))
    row = dict(path=str(path), bytes=size, sha256=digest.hexdigest(), stat=before)
    if expected is not None:
        require(size == expected['bytes'] and row['sha256'] == expected['sha256'],
                'bound file bytes differ: ' + str(path))
    return row


def read_json(path):
    def unique(rows):
        result = {}
        for key, value in rows:
            require(key not in result, 'duplicate JSON key: ' + key)
            result[key] = value
        return result
    raw = Path(path).read_bytes()
    if Path(path).suffix == '.gz':
        raw = gzip.decompress(raw)
    return json.loads(raw, object_pairs_hook=unique,
        parse_constant=lambda value: (_ for _ in ()).throw(ValueError('nonfinite JSON: ' + value)))


def write(path, value):
    with Path(path).open('x') as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write('\n')


def identity(pid):
    fields = (Path('/proc') / str(pid) / 'stat').read_text().rsplit(')', 1)[1].split()
    return dict(pid=pid, parent=int(fields[1]), group=int(fields[2]), session=int(fields[3]),
                start_ticks=int(fields[19]), state=fields[0])


def source_rows(scope, execution_freeze, deadline_ns):
    require(type(execution_freeze) is str and re.fullmatch('[0-9a-f]{40}', execution_freeze),
            'exact future profiling execution freeze required')
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT,
        timeout=remaining(deadline_ns, 10), text=True).strip()
    require(head == execution_freeze, 'profiler HEAD differs from its execution freeze')
    rows = scope['evidence_sources']
    require({r['path'] for r in rows} == EVIDENCE_SOURCES and len(rows) == len(EVIDENCE_SOURCES),
            'exact evidence source inventory differs')
    result = []
    for kind, specs in (('evidence', rows), ('execution', scope['execution_sources'])):
        for spec in specs:
            relative = Path(spec['path'])
            require(not relative.is_absolute() and '..' not in relative.parts, 'source path escapes ROOT')
            path = ROOT / relative
            row = bind(path, spec, deadline_ns)
            revisions = (EVIDENCE_FREEZE, execution_freeze) if kind == 'evidence' else (execution_freeze,)
            for revision in revisions:
                raw = subprocess.check_output(['git', 'show', revision + ':' + str(relative)], cwd=ROOT,
                    timeout=remaining(deadline_ns, 10))
                require(len(raw) == row['bytes'] and hashlib.sha256(raw).hexdigest() == row['sha256'],
                        'current/Git source differs at ' + revision + ':' + str(relative))
            result.append(dict(row, source_role=kind, git_revisions=list(revisions)))
    interpreter = scope['interpreter']
    require(Path(interpreter['path']) == Path('/usr/bin/python3').resolve(), 'interpreter binding path differs')
    result.append(dict(bind(interpreter['path'], interpreter, deadline_ns),
                       source_role='interpreter', git_revisions=[]))
    return result


def input_rows(scope, deadline_ns):
    specs = scope['inputs']
    require(len(specs) == len(INPUTS) and {r['logical_name'] for r in specs} == set(INPUTS),
            'exact fourteen logical input bindings required')
    result = []
    for spec in specs:
        name = spec['logical_name']
        logical = EPISODE / name
        selected = logical if logical.exists() else Path(str(logical) + '.gz')
        require(str(selected) == spec['path'], 'reader encoded-file selection differs: ' + name)
        result.append(dict(bind(selected, spec, deadline_ns), logical_name=name))
    return result


def validate_scope(scope):
    require(scope.get('schema') == 'mr3-single-ep-runtime-profile-scope-v1'
            and scope.get('native_evidence_freeze') == EVIDENCE_FREEZE
            and scope.get('episode') == str(EPISODE), 'not the one fixed V50 EP/evidence freeze')
    require(type(scope.get('epoch')) is str and scope['epoch'], 'sealed actual epoch required')
    require(scope.get('main_seconds') == 840 and scope.get('tail_seconds') == 60
            and scope.get('guard_cleanup_reserve_seconds') == 30,
            'prospective 840+60 reservation / internal cleanup reserve differs')
    budget = scope['budget_admission']
    require(budget.get('schema') == 'mr3-runtime-profile-budget-admission-v1', 'new actual balance admission required')
    used, balance = Decimal(budget['engineering_used_seconds']), Decimal(budget['engineering_remaining_seconds'])
    require(used.is_finite() and balance.is_finite() and used >= 0 and balance >= 900
            and used + balance == Decimal('75000') and budget.get('reservation_seconds') == 900,
            'actual post-close remaining balance cannot fund 900; no pilot/final borrowing')


def clean_environment():
    removed = {'PYTHONPATH', 'PYTHONHOME', 'VIRTUAL_ENV', 'LD_LIBRARY_PATH', 'AMENT_PREFIX_PATH',
               'CMAKE_PREFIX_PATH', 'COLCON_PREFIX_PATH', 'ROS_PACKAGE_PATH', 'GAZEBO_PLUGIN_PATH',
               'GAZEBO_MODEL_PATH', 'GAZEBO_RESOURCE_PATH'}
    env = {key: value for key, value in os.environ.items() if key not in removed and not key.startswith('CONDA')}
    env.update(PATH='/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin',
        PYTHONNOUSERSITE='1', PYTHONDONTWRITEBYTECODE='1', CUDA_VISIBLE_DEVICES='',
        OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1', MKL_NUM_THREADS='1')
    return env
