"""Only fixed diagnostic command/thread hooks; original files stay untouched."""
from functools import wraps
import hashlib
import importlib
import importlib.util
import importlib.metadata
import json
from pathlib import Path
import runpy
import shlex
import sys
from types import ModuleType, SimpleNamespace

HERE = Path(__file__).resolve().parent
ROOT = Path('/home/zhuyulab/ns3-workspace')
W = ROOT / 'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl'
ROS = ROOT / 'ros2_ws/ros2-multi-robot-automap'
ENTRY = HERE / 'fixed_roles_entry_v1.py'
RUN = Path('/tmp/mr3_p2a_v62_open101_8step_profile_v1')
SUPERVISOR = W / 'mr3_learning/supervisor.py'
WORKER = ROS / 'scripts/mr3_env_worker.py'
REAL_RUN_PATH = runpy.run_path


def require(value, reason):
    if not value:
        raise ValueError(reason)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def replace_one(text, old, new):
    require(text.count(old) == 1, 'fixed source hook is missing/ambiguous')
    changed = text.replace(old, new)
    require(changed.count(new) == 1 and changed.replace(new, old) == text, 'whole-byte inverse differs')
    return changed, (old, new)


def project(source, raw):
    text, edits = raw.decode(), []
    if source == SUPERVISOR:
        old = "                   '&& exec /usr/bin/python3 \"$1/scripts/mr3_env_worker.py\" '\n"
        value = '&& exec /usr/bin/python3 -B ' + shlex.quote(str(ENTRY)) + ' "$1/scripts/mr3_env_worker.py" '
        text, edit = replace_one(text, old, '                   ' + repr(value) + '\n')
        edits.append(edit)
    elif source == WORKER:
        old = '        self.spin_thread = threading.Thread(target=spin, name="mr3_worker_ros", daemon=True)'
        new = '        self.spin_thread = threading.Thread(target=lambda: __import__("fixed_process_profile_v1").profiled_call("ros_spin", spin), name="mr3_worker_ros", daemon=True)'
        text, edit = replace_one(text, old, new)
        edits.append(edit)
        old = '            "ros2", "launch", "multi_robot", "gazebo_multirobot_mapping_with_nav2.launch.py",'
        prefix = '/usr/bin/python3 -B ' + shlex.quote(str(ENTRY))
        new = ('            "ros2", "launch", "--launch-prefix", ' + repr(prefix)
               + ', "--launch-prefix-filter", "^(motion_safety|mr3_adapter)$", '
               + '"multi_robot", "gazebo_multirobot_mapping_with_nav2.launch.py",')
        text, edit = replace_one(text, old, new)
        edits.append(edit)
    else:
        raise ValueError('source is outside the two fixed projections')
    inverse = text
    for old, new in reversed(edits):
        inverse = inverse.replace(new, old)
    require(inverse.encode() == raw, 'final original-source inverse differs')
    return text.encode(), edits


def bound_source(path):
    pins = json.loads((HERE / 'base_source_pins_v1.json').read_text())
    raw = path.read_bytes()
    require(sha(raw) == pins['sources'][str(path)]['sha256'], 'fixed E base source differs')
    return raw


def preserve_projection(destination, source, raw, changed, edits):
    destination.mkdir(exist_ok=False)
    (destination / 'base.py').open('xb').write(raw)
    (destination / 'executed_projection.py').open('xb').write(changed)
    value = dict(original_path=str(source), original_sha256=sha(raw),
                 executed_projection_sha256=sha(changed), edits=edits,
                 compile_filename=str(source), original_file_and_main_semantics=True,
                 whole_byte_inverse_checked=True, scientific_qualification=False)
    (destination / 'projection.json').open('x').write(json.dumps(value, indent=2) + '\n')


def install_supervisor():
    require('mr3_learning.supervisor' not in sys.modules, 'Supervisor was imported before the fixed hook')
    raw = bound_source(SUPERVISOR)
    changed, edits = project(SUPERVISOR, raw)
    preserve_projection(RUN / 'supervisor_projection', SUPERVISOR, raw, changed, edits)
    name = 'mr3_learning.supervisor'
    spec = importlib.util.spec_from_file_location(name, SUPERVISOR)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    exec(compile(changed, str(SUPERVISOR), 'exec'), module.__dict__)


def install_role(core, role):
    def execute(program, *, run_name):
        require(run_name == '__main__' and program == str(core.PROGRAMS[role]), 'fixed role execution differs')
        if role == 'worker':
            raw = bound_source(WORKER)
            changed, edits = project(WORKER, raw)
            preserve_projection(core.OWNED_EPISODE / 'profiles/worker/source_projection', WORKER, raw, changed, edits)
            module = ModuleType('__main__')
            module.__dict__.update(__file__=program, __package__=None, __loader__=None,
                                   __spec__=None, __cached__=None)
            previous = sys.modules.get('__main__')
            sys.modules['__main__'] = module
            try:
                exec(compile(changed, program, 'exec'), module.__dict__)
                return dict(module.__dict__)
            finally:
                sys.modules['__main__'] = previous
        if role in ('motion_safety', 'adapter'):
            name = 'motion_safety' if role == 'motion_safety' else 'mr3_adapter'
            module = importlib.import_module('multi_robot_exploration.' + name)
            require(Path(module.__file__).resolve() == core.SOURCES[role][0].resolve(), 'actual fixed module source differs')
            entrypoints = [item for item in importlib.metadata.distribution('multi-robot-exploration').entry_points
                           if item.group == 'console_scripts' and item.name == name]
            require(len(entrypoints) == 1 and entrypoints[0].value == 'multi_robot_exploration.' + name + ':main'
                    and entrypoints[0].load() is module.main, 'actual fixed console entrypoint differs')
            destination = core.OWNED_EPISODE / ('profiles/' + role + '/console_resolution.json')
            destination.open('x').write(json.dumps(dict(role=role, source_path=str(Path(module.__file__).resolve()),
                source_sha256=sha(bound_source(core.SOURCES[role][0])), entrypoint=entrypoints[0].value,
                loaded_function_is_bound_module_main=True), indent=2)+'\n')
            if role == 'motion_safety':
                return REAL_RUN_PATH(program, run_name=run_name)
            original = module.encode_snapshot
            @wraps(original)
            def encode(*args, **kwargs):
                return core.profiled_call('encoder', original, *args, **kwargs)
            module.encode_snapshot = encode
            destination = core.OWNED_EPISODE / 'profiles/adapter/encoder_hook.json'
            destination.open('x').write(json.dumps(dict(function=original.__qualname__, module=original.__module__,
                source_sha256=sha(bound_source(core.SOURCES[role][0])),
                scope='same original encode_snapshot args/kwargs/return/exception; only explicit thread profiling wrapper'), indent=2)+'\n')
            try:
                return REAL_RUN_PATH(program, run_name=run_name)
            finally:
                module.encode_snapshot = original
        return REAL_RUN_PATH(program, run_name=run_name)
    # Replace only this core module alias, never the shared stdlib runpy module.
    core.runpy = SimpleNamespace(run_path=execute)
