"""Read-only staged packaging checks. No import of research/native consumers."""
import argparse
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import re
import subprocess
import time

ROOT = Path('/home/zhuyulab/ns3-workspace')
W = ROOT/'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl'
ROS = ROOT/'ros2_ws/ros2-multi-robot-automap'
A = Path(__file__).resolve().parent
CLOSED = W/'report/assets/20261019_mr3_p2a_v16/closed_execution'
BASE = 'd307a0b248a87bf1c03b41f4f7df4cb221253ac9'
PLAN_SHA = '0b9951b44e842ef2677234659d813d74c97447068fe34688cc4f4b4b04ae3833'
SCHEMA = 'mr3-v17-closed-preparation-integrity-v1'


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT)


def parse(raw):
    def pairs(rows):
        result = {}
        for key, value in rows:
            require(key not in result, 'duplicate JSON key: '+key)
            result[key] = value
        return result
    def invalid(value):
        raise ValueError('nonfinite JSON: '+value)
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=invalid)


class Inputs:
    def __init__(self):
        self.bindings = {}
        self.stats = {}
        self.index = {}

    def file(self, path, staged=False):
        path = Path(path)
        if path not in self.bindings:
            before = path.stat()
            digest, size = hashlib.sha256(), 0
            with path.open('rb') as stream:
                for chunk in iter(lambda: stream.read(1024*1024), b''):
                    digest.update(chunk); size += len(chunk)
            self.stats[path] = before
            self.bindings[path] = {'path':str(path), 'sha256':digest.hexdigest(), 'bytes':size}
        proof = self.bindings[path]
        if staged:
            relative = str(path.relative_to(ROOT))
            if relative not in self.index:
                process = subprocess.Popen(['git','cat-file','blob',':'+relative], cwd=ROOT,
                                           stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                digest, size = hashlib.sha256(), 0
                for chunk in iter(lambda: process.stdout.read(1024*1024), b''):
                    digest.update(chunk); size += len(chunk)
                error = process.stderr.read()
                require(process.wait() == 0, 'missing/index blob error: '+relative+' '+error.decode(errors='replace'))
                self.index[relative] = {'sha256':digest.hexdigest(), 'bytes':size}
            require(all(proof[key] == self.index[relative][key] for key in ('sha256','bytes')),
                    'current bytes differ from Git index: '+relative)
        return proof

    def raw(self, path, staged=True):
        proof = self.file(path, staged)
        raw = Path(path).read_bytes()
        require(sha(raw) == proof['sha256'] and len(raw) == proof['bytes'], 'input changed: '+str(path))
        return raw

    def document(self, path, staged=True):
        return parse(self.raw(path, staged))

    def finish(self):
        for path, before in self.stats.items():
            after = path.stat()
            require(all(getattr(before,key) == getattr(after,key) for key in
                        ('st_dev','st_ino','st_size','st_mtime_ns','st_ctime_ns')),
                    'input changed during checker: '+str(path))


def wait_math(value, returncode, schema):
    require(value.get('schema') == schema and value.get('actual_waited') is True
            and type(value.get('actual_returncode')) is int and value['actual_returncode'] == returncode
            and value.get('source_unchanged') is True
            and value.get('source_before') == value.get('source_after')
            and type(value.get('source_before')) is list and value['source_before']
            and value.get('passed') is (returncode == 0), 'actual wait/returncode/source facts differ')
    start, end = value['started_monotonic_ns'], value['ended_monotonic_ns']
    require(type(start) is int and type(end) is int and 0 < start < end, 'actual wait ns invalid')
    seconds = Decimal(end-start)/10**9
    require(Decimal(str(value['actual_child_wait_seconds'])) == seconds, 'actual wait duration is not exact ns difference')
    for key in ('coordinator_identity','child_identity'):
        identity = value[key]
        require(all(type(identity.get(name)) is int and identity[name] > 0 for name in ('pid','start_ticks')),
                'actual wait positive typed PID/start missing')
    require(value['child_identity']['parent'] == value['coordinator_identity']['pid'], 'actual waited child parent differs')
    require(not value.get('errors'), 'actual wait reports errors')
    return seconds


def check_cpu(inputs):
    directory = A/'checks/ack_runtime_cpu_attempt_v1'
    value = inputs.document(directory/'actual_wait.json')
    seconds = wait_math(value, 0, 'mr3-v15-finite-preparation-actual-child-wait-v1')
    require(seconds == Decimal('22.161525707') and value.get('native_admission') is False, 'CPU wait scope/duration differs')
    expected = [ROS/'src/multi_robot_exploration'/name for name in (
        'multi_robot_exploration/mr3_reach_runtime.py', 'multi_robot_exploration/mr3_drive_phase.py',
        'test/test_mr3_reach_runtime_independent.py', 'test/test_mr3_drive_phase.py', 'test/test_motion_safety_reach.py')]
    rows = value['source_after']
    require([row['path'] for row in rows] == [str(path) for path in expected], 'CPU five-source inventory/order differs')
    expected_snapshots = set()
    for ordinal, (path,row) in enumerate(zip(expected,rows)):
        proof = inputs.file(path, True)
        require(all(proof[key] == row[key] for key in ('sha256','bytes')), 'CPU source is not current: '+str(path))
        snapshot = directory/'source_snapshots'/f'{ordinal:02d}_{path.name}'
        expected_snapshots.add(snapshot.name)
        require(inputs.raw(snapshot) == inputs.raw(path), 'CPU exact ordinal snapshot differs: '+str(snapshot))
    require({path.name for path in (directory/'source_snapshots').iterdir()} == expected_snapshots,
            'CPU ordinal snapshot inventory differs')
    console = directory/'console.log'
    require(value['console']['path'] == str(console), 'CPU console path differs')
    proof = inputs.file(console, True)
    require(all(proof[key] == value['console'][key] for key in ('sha256','bytes')), 'CPU console SHA/bytes differs')
    require(re.search(rb'\b94 passed\b',inputs.raw(console)), 'actual CPU console lacks 94 passed')
    argv = ['/bin/bash','-c','source /opt/ros/humble/setup.bash; source "$1/install/setup.bash"; exec /usr/bin/python3 -B -m pytest -q test/test_mr3_reach_runtime_independent.py test/test_mr3_drive_phase.py test/test_motion_safety_reach.py',
            'mr3-ack-regression',str(ROS)]
    require(value['actual_argv'] == argv and value['cwd'] == str(ROS/'src/multi_robot_exploration'), 'CPU actual command/cwd differs')
    return str(seconds)


def check_copies(inputs):
    directories = {'matrix':Path('/tmp/mr3_p2a_reach_v16_matrix'),
        'matrix_outer':Path('/tmp/mr3_p2a_reach_v16_matrix_wait'),
        'preflight_outer':Path('/tmp/mr3_p2a_reach_v16_preflight_wait_v2'),
        'absence_outer':Path('/tmp/mr3_p2a_reach_v16_absence_wait')}
    pairs = []
    for name, original in directories.items():
        current = CLOSED/name
        current_files = {path.relative_to(current) for path in current.rglob('*') if path.is_file()}
        original_files = {path.relative_to(original) for path in original.rglob('*') if path.is_file()}
        require(current_files == original_files and current_files, 'closed copy inventory differs: '+name)
        pairs.extend((current/relative, original/relative) for relative in sorted(current_files))
    pairs.extend([(CLOSED/'preflight.json',Path('/tmp/mr3_p2a_reach_v16_preflight.json')),
                  (CLOSED/'external_absence.json',Path('/tmp/mr3_p2a_reach_v16_absence.json'))])
    for current, original in pairs:
        require(inputs.raw(current) == inputs.raw(original,False), 'raw closed original/canonical copy differs: '+str(current))
    return len(pairs)


def check_archive(inputs):
    manifest = inputs.document(CLOSED/'native_closed_manifest_v1.json')
    rows = manifest['source_files']
    require(manifest['schema'] == 'mr3-v16-closed-native-byte-archive-v1' and manifest['source_freeze'] == BASE
            and len(rows) == 459 and len({row['path'] for row in rows}) == 459
            and sum(row['bytes'] for row in rows) == manifest['source_bytes'] == 823412096,
            'closed archive original file inventory/totals differ')
    require(all(not Path(row['path']).is_absolute() and '..' not in Path(row['path']).parts
                and re.fullmatch('[0-9a-f]{64}',row['sha256']) for row in rows), 'archive manifest path/SHA malformed')
    require(manifest.get('all_archived_bytes_replayed') is True and manifest.get('source_unchanged') is True
            and manifest.get('scientific_pass_claimed') is False and manifest.get('native_experiment_reexecuted') is False,
            'archive original replay/scope facts differ')
    archive = CLOSED/'native_closed_v1.tar.gz'
    proof = inputs.file(archive, True)  # Streaming on-disk AND Git-index hashes; no decompression.
    require(manifest['archive']['path'] == str(archive) and proof['bytes'] == 80515160
            and all(proof[key] == manifest['archive'][key] for key in ('sha256','bytes')), 'archive actual/index bytes differ')
    return {'source_files':459,'source_bytes':823412096,'compressed_bytes':80515160,
            'archive_sha256':proof['sha256'],'decompressed_by_this_checker':False}


def check_accounting(inputs):
    accounting = inputs.document(CLOSED/'engineering_accounting_v1.json')
    fees = []
    for name, code in (('matrix_outer',1),('absence_outer',0)):
        path = CLOSED/name/'actual_wait.json'
        value = inputs.document(path)
        fees.append(wait_math(value,code,'mr3-reach-outer-actual-wait-v1'))
    require(fees == [Decimal('448.826082101'),Decimal('0.190795842')], 'actual outer fees differ')
    total = sum(fees)
    used = Decimal('31596.4775930946018')+total
    remaining = Decimal('52000')-used
    require(accounting['source_freeze'] == BASE and accounting['opening_used_wall_seconds'] == '31596.4775930946018'
            and Decimal(accounting['engineering_ceiling_wall_seconds']) == Decimal('52000')
            and total == Decimal(accounting['charged_this_version_seconds']) == Decimal('449.016877943')
            and used == Decimal(accounting['cumulative_used_seconds']) == Decimal('32045.4944710376018')
            and remaining == Decimal(accounting['remaining_seconds']) == Decimal('19954.5055289623982'), 'engineering accounting arithmetic differs')
    require(accounting.get('qualification_passed') is False and accounting.get('policy_stage_started') is False
            and accounting.get('cpu_preparation_charged_to_native') is False, 'failed V16 accounting scope differs')
    require(len(accounting['actual_outer_fees']) == 2, 'fee receipt set differs')
    for row,name,code,seconds in zip(accounting['actual_outer_fees'],('matrix_outer','absence_outer'),(1,0),fees):
        path = CLOSED/name/'actual_wait.json'
        require(row['path'] == str(path.relative_to(ROOT)) and row['sha256'] == inputs.file(path,True)['sha256']
                and row['actual_returncode'] == code and row['actual_waited'] is True
                and Decimal(row['seconds']) == seconds and row['charge_once_outer_includes_all_submitted_children'] is True,
                'outer fee is not bound once to its original actual wait')
    return {'charged_seconds':str(total),'cumulative_used_seconds':str(used),'remaining_seconds':str(remaining),'ceiling_seconds':'52000'}


def check_absence(inputs):
    value = inputs.document(CLOSED/'external_absence.json')
    require(value['schema'] == 'mr3-reach-external-process-absence-v1' and value.get('passed') is True
            and value.get('all_saved_identities_absent') is True and value.get('scientific_pass_claimed') is False
            and not any(value.get(key) for key in ('present','unreadable','errors','pids_without_saved_start')),
            'original external absence did not close')
    pairs = [(row['pid'],row['start_ticks']) for row in value['identities']]
    require(len(pairs) == len(set(pairs)) == value['identity_count'] == 48, 'external saved identity count differs')
    present, reused = [], []
    for pid,start in pairs:
        require(type(pid) is int and pid > 0 and type(start) is int and start > 0, 'invalid saved PID/start')
        try:
            tail = (Path('/proc')/str(pid)/'stat').read_text().rsplit(')',1)[1].split()
            current = int(tail[19])
            row = {'pid':pid,'saved_start_ticks':start,'current_start_ticks':current,'state':tail[0]}
            (present if current == start else reused).append(row)
        except (FileNotFoundError,ProcessLookupError):
            pass
    require(not present, 'saved process still present (including zombie): '+repr(present))
    return {'saved_identity_count':48,'present':present,'same_pid_different_start':reused}


def check_plan(inputs):
    path = A/'predeclared_plan_v1.json'
    require(inputs.file(path,True)['sha256'] == PLAN_SHA, 'predeclared V17 plan1 bytes differ')
    plan = inputs.document(path)
    sources = plan['source_bindings']
    require(type(sources) is dict and len(sources) == 659, 'plan1 659-source inventory differs')
    for name,digest in sources.items():
        source = Path(name) if Path(name).is_absolute() else ROOT/name
        require(source.is_relative_to(ROOT) and inputs.file(source,True)['sha256'] == digest,
                'plan frozen source current/index differs: '+name)
    binding_path = Path(plan['custody_binding'])
    require(binding_path == A/'native_custody_binding_v1.json', 'plan custody binding path differs')
    binding = inputs.document(binding_path)
    binaries = binding['binaries']; libraries = plan['library_bindings']
    require(len(binaries) == len(libraries) == 10 and {row['path'] for row in binaries.values()} == set(libraries),
            'plan/binding ten-ELF inventory differs')
    for row in binaries.values():
        path = Path(row['path']); proof = inputs.file(path)
        require(str(path.resolve(strict=True)) == row['resolved_path']
                and proof['sha256'] == row['sha256'] == libraries[str(path)] and proof['bytes'] == row['bytes'],
                'actual ELF/source freeze differs: '+str(path))
    budget = plan['budget']
    require(budget['engineering_used_at_plan_entry_seconds'] == '32045.4944710376018'
            and budget['engineering_remaining_seconds'] == '19954.5055289623982'
            and budget['approved_cumulative_engineering_seconds'] == '52000', 'plan budget differs from closed accounting')
    return {'plan_sha256':PLAN_SHA,'current_and_staged_sources':659,'actual_elf_count':10}


def check_production_diff(inputs):
    runtime = ROS/'src/multi_robot_exploration/multi_robot_exploration/mr3_reach_runtime.py'
    test = ROS/'src/multi_robot_exploration/test/test_mr3_reach_runtime_independent.py'
    roots = [str((ROS/'src').relative_to(ROOT)),str((ROS/'scripts').relative_to(ROOT)),str((W/'mr3_learning').relative_to(ROOT))]
    allowed = {str(path.relative_to(ROOT)) for path in (runtime,test)}
    for staged in (False,True):
        args = ['diff']+(['--cached'] if staged else [])+['--name-only',BASE,'--',*roots]
        require(set(git(*args).decode().splitlines()) == allowed, 'production diff includes changes beyond runtime and its independent test')
    old = git('show',BASE+':'+str(runtime.relative_to(ROOT)))
    before = (b'        if (target is None or value["clock_ns"] != target["clock_ns"]\n'
              b'                or value["source_clock_ns"] != target["clock_ns"]\n')
    after = (b'        # Storage may happen after publication during free-running startup.\n'
             b'        # receive() preserves that actual clock and checks source <= storage;\n'
             b'        # matching() separately requires equality at a paused control boundary.\n'
             b'        if (target is None or value["source_clock_ns"] != target["clock_ns"]\n')
    require(old.count(before) == 1 and inputs.raw(runtime) == old.replace(before,after), 'runtime diff is not the exact storage-clock-only repair')
    return {'production_changed_paths':sorted(allowed),'runtime_exact_whole_file_repair':True,
            'shared_driver_drive_phase_independent_reader_unchanged':True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args = parser.parse_args()
    require(not args.output.exists(), 'exclusive output already exists')
    require(not args.output.resolve().is_relative_to(A), 'write result outside preparation freeze')
    started = time.monotonic_ns(); inputs = Inputs(); metrics = {}; errors = []
    index_before = sha(git('ls-files','--stage','-z'))
    try:
        inputs.file(Path(__file__).resolve(),True)
        metrics['ack_cpu_seconds'] = check_cpu(inputs)
        metrics['closed_raw_files_compared'] = check_copies(inputs)
        metrics['archive'] = check_archive(inputs)
        metrics['accounting'] = check_accounting(inputs)
        metrics['absence'] = check_absence(inputs)
        metrics['plan'] = check_plan(inputs)
        metrics['production'] = check_production_diff(inputs)
        inputs.finish()
        require(sha(git('ls-files','--stage','-z')) == index_before, 'Git index changed while checker ran')
    except (OSError,ValueError,KeyError,TypeError,IndexError,subprocess.SubprocessError) as error:
        errors.append(type(error).__name__+': '+str(error))
    result = {'schema':SCHEMA,'passed':not errors,'scope':'staged_packaging_integrity_only',
              'scientific_pass_claimed':False,'native_admission':False,'native_runs':0,'gpu_calls':0,
              'started_monotonic_ns':started,'ended_monotonic_ns':time.monotonic_ns(),
              'metrics':metrics,'errors':errors,'input_bindings':list(inputs.bindings.values()),
              'git_index_source_bindings_checked':len(inputs.index),'git_index_inventory_sha256':index_before}
    with args.output.open('x') as stream:
        json.dump(result,stream,indent=2); stream.write('\n')
    print(json.dumps({'schema':SCHEMA,'passed':result['passed'],'metrics':metrics,'errors':errors,'output':str(args.output)}))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
