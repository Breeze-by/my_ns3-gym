"""Fixed three-role profiler for one future open101/eight-step diagnostic.

No native invocation is admitted by this draft. Only a source-bound fixed
diagnostic launcher may activate these roles; actual ROS argv is recorded.
"""
import cProfile
import hashlib
import json
import os
from pathlib import Path
import runpy
import stat
import sys
import threading
import time

PROFILE_ID = 'mr3-p2a-v62-open101-8step-cprofile-v1'
ROOT = Path('/home/zhuyulab/ns3-workspace')
ROS = ROOT / 'ros2_ws/ros2-multi-robot-automap'
OWNED_EPISODE = Path('/tmp/mr3_p2a_v62_open101_8step_profile_v1/native/worker0/episode001_open_101')
PROGRAMS = {
    'motion_safety': ROS / 'install/multi_robot_exploration/lib/multi_robot_exploration/motion_safety',
    'adapter': ROS / 'install/multi_robot_exploration/lib/multi_robot_exploration/mr3_adapter',
    'worker': ROS / 'scripts/mr3_env_worker.py',
}
PROGRAM_SHA256 = {
    'motion_safety': '91cc9e0015cfe3d87d2414da809e85da19613c59009c01ec71e15f4730dd5ba3',
    'adapter': 'fee68e207cb6bceb113fcebfc4964b0d00a3466a5b68b04c396fae613a45f225',
    'worker': '229ffdfdfd9b623c97b8ebe1937daa6058c20376e73d227dc7d097869f3c8879',
}
SOURCES = {
    'motion_safety': (ROS / 'src/multi_robot_exploration/multi_robot_exploration/motion_safety.py',
                      'f01ae5213740cfb134423fd0e4ddc2d880e2114db66bc63c16164ad027d05735'),
    'adapter': (ROS / 'src/multi_robot_exploration/multi_robot_exploration/mr3_adapter.py',
                '0dcd5545059c44b266c4d7a0e54b96f59373e7952500e110cac8a0d9d4250cfb'),
    'worker': (PROGRAMS['worker'], PROGRAM_SHA256['worker']),
}
LANES = {'motion_safety': ('main',), 'adapter': ('main', 'encoder'), 'worker': ('main', 'ros_spin')}
_ACTIVE = None


def require(value, reason):
    if not value:
        raise ValueError(reason)


def identity():
    fields = Path('/proc/self/stat').read_text().rsplit(')', 1)[1].split()
    return dict(pid=os.getpid(), parent=int(fields[1]), group=int(fields[2]),
                session=int(fields[3]), start_ticks=int(fields[19]))


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def fingerprint(value):
    return {key: getattr(value, key) for key in
            ('st_dev', 'st_ino', 'st_mode', 'st_size', 'st_mtime_ns', 'st_ctime_ns')}


def program_identity(path):
    # Installed console entries may be legitimate known symlinks. Bind both.
    return dict(literal_lstat=fingerprint(path.lstat()), resolved_path=str(path.resolve(strict=True)),
                resolved_target_stat=fingerprint(path.stat()))


def write(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write('\n')


class Capture:
    def __init__(self, role, directory):
        self.role, self.directory = role, directory
        self.main_thread = threading.get_ident()
        self.profiles, self.threads, self.active, self.calls, self.cpu_ns = {}, {}, {}, {}, {}
        self.thread_objects = {}
        self.lock = threading.Lock()

    def call(self, lane, function, *args, **kwargs):
        require(lane in LANES[self.role], 'lane is not whitelisted for this fixed role')
        thread = threading.get_ident()
        require((lane == 'main') == (thread == self.main_thread), 'lane/thread ownership differs')
        with self.lock:
            require(lane not in self.threads or self.threads[lane] == thread, 'lane moved to another thread')
            require(not self.active.get(lane, False), 'nested/reentrant use of one profiler')
            self.threads[lane] = thread
            self.thread_objects[lane] = threading.current_thread()
            self.profiles.setdefault(lane, cProfile.Profile())
            self.active[lane] = True
        started = time.thread_time_ns()
        try:
            # runcall propagates SystemExit and BaseException; CLI runctx does not.
            return self.profiles[lane].runcall(function, *args, **kwargs)
        finally:
            self.cpu_ns[lane] = self.cpu_ns.get(lane, 0) + time.thread_time_ns() - started
            self.calls[lane] = self.calls.get(lane, 0) + 1
            self.active[lane] = False

    def finish(self):
        rows, errors = [], []
        for lane in LANES[self.role]:
            path = self.directory / (lane + '.pstats')
            if (lane not in self.profiles or self.active.get(lane)
                    or lane != 'main' and self.thread_objects[lane].is_alive()):
                errors.append(lane + ': unobserved or still active; no complete profile claim')
                continue
            try:
                require(not path.exists(), 'profile output exists')
                self.profiles[lane].dump_stats(path)
                raw = path.read_bytes()
                rows.append(dict(lane=lane, path=str(path), bytes=len(raw), sha256=sha(raw),
                                 thread_ident=self.threads[lane], calls=self.calls[lane],
                                 thread_exit_observed=lane != 'main',
                                 thread_cpu_ns=self.cpu_ns[lane]))
            except Exception as error:
                errors.append(lane + ': ' + repr(error))
        return rows, errors


def profiled_call(lane, function, *args, **kwargs):
    """Only the fixed encoder or ROS-spin source hook calls this in its own thread."""
    require(_ACTIVE is not None, 'fixed diagnostic capture is not active')
    require(lane != 'main', 'main entry cannot be called through a thread hook')
    return _ACTIVE.call(lane, function, *args, **kwargs)


def run_role(role, program_argv):
    global _ACTIVE
    require(role in PROGRAMS and role in LANES, 'unknown fixed profiling role')
    require(_ACTIVE is None, 'one active role capture per process')
    require(type(program_argv) is list and program_argv and all(type(v) is str for v in program_argv),
            'exact original program argv required')
    require(program_argv[0] == str(PROGRAMS[role]), 'program is outside the exact role whitelist')
    parameter_paths = []
    if role == 'worker':
        require(program_argv[1:] == ['--run-dir', str(OWNED_EPISODE)], 'worker argv differs from fixed owned episode')
    else:
        require(program_argv[1:2] == ['--ros-args'], 'only original ROS node arguments are allowed')
        expected_name = 'motion_safety' if role == 'motion_safety' else 'mr3_adapter'
        index, named = 2, False
        while index < len(program_argv):
            flag = program_argv[index]
            require(index + 1 < len(program_argv), 'incomplete original ROS argument')
            value = program_argv[index + 1]
            if flag in ('-r', '--remap'):
                require(value in ('__node:=' + expected_name, '__ns:=/'), 'undeclared node remap')
                named = named or value == '__node:=' + expected_name
            elif flag == '--params-file':
                parameter_paths.append(Path(value))
            else:
                raise ValueError('undeclared original ROS node argument')
            index += 2
        require(named and 1 <= len(parameter_paths) <= 4, 'fixed node name and actual parameter files required')
    sources = {}
    for source, expected in ((PROGRAMS[role], PROGRAM_SHA256[role]), SOURCES[role]):
        before, raw = program_identity(source), source.read_bytes()
        require(sha(raw) == expected and before == program_identity(source), 'fixed console/source bytes differ')
        sources[str(source)] = dict(identity=before, raw=raw, sha256=expected)
    program = PROGRAMS[role]
    directory = OWNED_EPISODE / 'profiles' / role
    require(directory.parent == directory.parent.resolve(strict=True), 'owned output parent is not canonical')
    directory.mkdir(exist_ok=False)
    parameters = []
    for index, path in enumerate(parameter_paths, 1):
        require(path.is_absolute() and path == path.resolve(strict=True), 'parameter path has a symlink component')
        before = path.lstat()
        require(stat.S_ISREG(before.st_mode) and before.st_size <= 1048576, 'parameter file is not bounded regular input')
        raw = path.read_bytes()
        require(fingerprint(before) == fingerprint(path.lstat()) and len(raw) == before.st_size, 'parameter file changed')
        snapshot = directory / ('parameters_' + str(index) + '.yaml')
        snapshot.open('xb').write(raw)
        parameters.append(dict(path=str(path), bytes=len(raw), sha256=sha(raw),
                               stat=fingerprint(before), snapshot=str(snapshot), read_only_source=True))
    owner = identity()
    started, cpu_started = time.monotonic_ns(), time.process_time_ns()
    actual_argv = [value.decode() for value in Path('/proc/self/cmdline').read_bytes().split(b'\0') if value]
    write(directory / 'started.json', dict(profile_id=PROFILE_ID, role=role, identity=owner,
          actual_argv=actual_argv, program_argv=program_argv, parameters=parameters,
          sources={path:dict(identity=row['identity'], sha256=row['sha256'], bytes=len(row['raw'])) for path,row in sources.items()},
          started_monotonic_ns=started))
    old_argv, outcome = sys.argv, dict(kind='returned')
    capture = Capture(role, directory)
    _ACTIVE = capture
    try:
        sys.argv = list(program_argv)
        capture.call('main', runpy.run_path, str(program), run_name='__main__')
    except BaseException as error:
        outcome = dict(kind=type(error).__name__, repr=repr(error))
        if isinstance(error, SystemExit):
            outcome['exit_code_repr'] = repr(error.code)
        raise
    finally:
        sys.argv, _ACTIVE = old_argv, None
        # Ordinary auxiliary dump errors never replace the target exception/rc.
        # KeyboardInterrupt/SystemExit are not suppressed; no signal handler is installed.
        try:
            profiles, errors = capture.finish()
            stable = all(row['identity'] == program_identity(Path(path)) and Path(path).read_bytes() == row['raw']
                         for path, row in sources.items())
            write(directory / 'finished.json', dict(profile_id=PROFILE_ID, role=role, identity=owner,
                  target_outcome=outcome, profiles=profiles, profile_errors=errors,
                  profile_complete=not errors and stable, source_stable=stable, parameters=parameters,
                  started_monotonic_ns=started, ended_monotonic_ns=time.monotonic_ns(),
                  process_cpu_ns=time.process_time_ns() - cpu_started,
                  coverage='main plus only explicit role thread hooks; other threads/native internals not decomposed',
                  scientific_qualification=False))
        except Exception as error:
            # Missing/failed finish receipt makes the future parent diagnostic FAIL.
            # Preserve the target's real SystemExit/exception/signal semantics.
            try:
                write(directory / 'profile_dump_error.json', dict(error=repr(error), target_outcome=outcome))
            except Exception:
                pass


def main(argv=None):
    command = list(sys.argv[1:] if argv is None else argv)
    roles = [role for role, program in PROGRAMS.items() if command and command[0] == str(program)]
    require(len(roles) == 1, 'prefix target is outside the fixed three-role whitelist')
    run_role(roles[0], command)
    return 0
