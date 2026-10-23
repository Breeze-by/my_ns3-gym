"""One fixed description of two closed V62 main profiles; no activity credit."""
import argparse
import ast
import hashlib
import json
import marshal
import math
import os
from pathlib import Path
import stat
import subprocess
import time

ROOT = Path('/home/zhuyulab/ns3-workspace')
W = ROOT / 'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl'
A62 = W / 'report/assets/20261024_mr3_p2a_v62_process_profile'
A63 = W / 'report/assets/20261024_mr3_p2a_v63_profile_description'
G = '81e63f50699073286c9773dcb92106de63fdf4ca'
OUTPUT = Path('/tmp/mr3_p2a_v63_profile_description_v1.json')
OLD_ROOT = Path('/tmp/mr3_p2a_v62_open101_8step_profile_v1/native/worker0/episode001_open_101/profiles')
OLD_SOURCE = dict(path=str(A62/'review_profile_v1.py'), bytes=19058,
    sha256='c83a9e97804158e085fbe1b4146621846b4d3f6c2e287d3dda71dd3b5955b9bf')
OLD_SCOPE = dict(path=str(A62/'scope_v1.json'), bytes=338417,
    sha256='0ec6f36581b02b43aa16d7d5d1bd351ec52212262f2e57120b4cd809bdfb5b61')
PROFILES = [
    dict(role='motion_safety', lane='main', path=str(OLD_ROOT/'motion_safety/main.pstats'),
         bytes=402910, sha256='69f76cf0131e2bec91fa4cb969286a4c671eed091ea3e3077dc4d0178f451d93'),
    dict(role='adapter', lane='main', path=str(OLD_ROOT/'adapter/main.pstats'),
         bytes=492030, sha256='5f8451996b4aefdef30fb414a4d2f1e3ec11e4a3f9a494bd3da098306d89e81e'),
]
FINISHED = [
    dict(role='motion_safety', path=str(OLD_ROOT/'motion_safety/finished.json'), bytes=1665,
         sha256='8f0fb7852688ea8f31b618d3296315f28c56df85d823b6fca703dcad3ef42adc'),
    dict(role='adapter', path=str(OLD_ROOT/'adapter/finished.json'), bytes=1716,
         sha256='5357d00d45af76548b14901204205e06385d4a5770f230d9d6fdac4d77d2a7d8'),
]
RESOURCE = dict(max_profiles=2, profile_each_max_bytes=1048576, profile_total_max_bytes=2097152,
                metadata_total_max_bytes=8388608, work_wall_seconds=60, complete_parent_wall_seconds=120)


def require(value, reason):
    if not value:
        raise ValueError(reason)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def parse(raw):
    def unique(items):
        result = dict(items)
        require(len(result) == len(items), 'duplicate JSON member')
        return result
    return json.loads(raw, object_pairs_hook=unique,
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError('nonfinite JSON: '+value)))


def identity():
    fields = Path('/proc/self/stat').read_text().rsplit(')', 1)[1].split()
    return dict(pid=os.getpid(), parent=int(fields[1]), group=int(fields[2]),
                session=int(fields[3]), start_ticks=int(fields[19]))


def fingerprint(value):
    return [getattr(value, key) for key in ('st_dev', 'st_ino', 'st_mode', 'st_size', 'st_mtime_ns', 'st_ctime_ns')]


def validate_spec(spec):
    require(type(spec) is dict and spec.get('schema') == 'mr3-v63-partial-profile-description-spec-v1'
            and type(spec.get('admitted')) is bool and spec['admitted'] is True, 'spec is not admitted')
    require(spec.get('historical_source_freeze') == G and spec.get('old_scope') == OLD_SCOPE
            and spec.get('description_source') == OLD_SOURCE and spec.get('profiles') == PROFILES
            and spec.get('finished_metadata') == FINISHED, 'fixed old source/scope/metadata/profile pins differ')
    require(all(type(row.get('bytes')) is int and type(row.get('sha256')) is str
                for row in [spec['old_scope'],spec['description_source'],*spec['profiles'],*spec['finished_metadata']]),
            'fixed source/input pins are not typed')
    require(spec.get('resource') == RESOURCE and all(type(spec['resource'][key]) is int for key in RESOURCE),
            'fixed typed resource limits differ')
    inventory = spec.get('closed_inventory')
    require(type(inventory) is dict and inventory.get('path') == str(A62/'closed_inventory_v1.json')
            and type(inventory.get('bytes')) is int and 0 < inventory['bytes'] <= RESOURCE['metadata_total_max_bytes']
            and type(inventory.get('sha256')) is str and len(inventory['sha256']) == 64,
            'closed V62 inventory has not been pinned')
    require(all(value in '0123456789abcdef' for value in inventory['sha256']), 'inventory SHA is not lowercase hex')
    require(spec.get('output') == str(OUTPUT) and spec.get('scientific_qualification') is False
            and spec.get('capacity_qualified') is False and spec.get('old_FAIL_rejudged') is False,
            'fixed descriptive-only scope differs')


class Reads:
    def __init__(self, started):
        self.deadline = started + RESOURCE['work_wall_seconds'] * 10**9
        self.bindings, self.stats = [], {}
        self.profile_bytes = self.metadata_bytes = self.git_show_bytes = 0

    def check_time(self):
        require(time.monotonic_ns() < self.deadline, 'work deadline exceeded; partial description retained')

    def current_source(self, path):
        self.check_time()
        require(path.is_absolute() and path == path.resolve(strict=True), 'source path has a symlink component')
        before = path.lstat()
        require(stat.S_ISREG(before.st_mode)
                and self.metadata_bytes + before.st_size <= RESOURCE['metadata_total_max_bytes'], 'source/metadata limit exceeded')
        previous = self.stats.get(path)
        require(previous is None or previous == fingerprint(before), 'source changed between reads')
        raw = path.read_bytes()
        self.metadata_bytes += len(raw)
        require(len(raw) == before.st_size and fingerprint(before) == fingerprint(path.lstat()), 'source changed while read')
        self.stats[path] = fingerprint(before)
        self.bindings.append(dict(path=str(path),bytes=len(raw),sha256=sha(raw),stat=fingerprint(before),full_read_passes=1,profile=False))
        self.check_time()
        return raw

    def read(self, binding, *, profile=False):
        self.check_time()
        path = Path(binding['path'])
        require(path.is_absolute() and path == path.resolve(strict=True), 'input path has a symlink component')
        before = path.lstat()
        require(stat.S_ISREG(before.st_mode) and type(binding['bytes']) is int
                and before.st_size == binding['bytes'], 'input is not the declared regular file')
        if profile:
            require(before.st_size <= RESOURCE['profile_each_max_bytes']
                    and self.profile_bytes + before.st_size <= RESOURCE['profile_total_max_bytes'], 'profile limit exceeded')
        else:
            require(self.metadata_bytes + before.st_size <= RESOURCE['metadata_total_max_bytes'], 'metadata limit exceeded')
        previous = self.stats.get(path)
        require(previous is None or previous == fingerprint(before), 'bound input changed between reads')
        raw = path.read_bytes()
        if profile: self.profile_bytes += len(raw)
        else: self.metadata_bytes += len(raw)
        require(sha(raw) == binding['sha256'] and len(raw) == binding['bytes']
                and fingerprint(before) == fingerprint(path.lstat()), 'complete input SHA/bytes/stat differs')
        self.stats[path] = fingerprint(before)
        self.bindings.append(dict(**binding, stat=fingerprint(before), full_read_passes=1, profile=profile))
        self.check_time()
        return raw

    def frozen(self, path, freeze):
        self.check_time()
        raw = subprocess.check_output(['git','show',freeze+':'+str(path.relative_to(ROOT))], cwd=ROOT)
        self.git_show_bytes += len(raw)
        return raw

    def finish(self):
        self.check_time()
        for path, before in self.stats.items():
            require(fingerprint(path.lstat()) == before, 'bound input changed before final description')


def old_description_function(raw):
    """Exact two AST nodes from the whole-module-pinned G source, no imports."""
    require(len(raw) == OLD_SOURCE['bytes'] and sha(raw) == OLD_SOURCE['sha256'], 'original whole description module differs')
    tree = ast.parse(raw, filename=OLD_SOURCE['path'])
    functions = [node for node in tree.body if isinstance(node, ast.FunctionDef)
                 and node.name in ('require', 'pstats_description')]
    require([node.name for node in functions] == ['require', 'pstats_description'], 'fixed original function selection differs')
    namespace = {'math': math, 'marshal': marshal}
    exec(compile(ast.Module(body=functions, type_ignores=[]), OLD_SOURCE['path'], 'exec'), namespace)
    return namespace['pstats_description']


def inventory_members(inventory):
    require(type(inventory) is dict and inventory.get('schema') == 'mr3-v62-opaque-closed-inventory-v1',
            'closed inventory schema differs')
    entries = inventory.get('entries')
    require(type(entries) is list, 'closed regular inventory entries missing')
    selected = []
    for profile in PROFILES:
        found = [row for row in entries if type(row) is dict and row.get('original') == profile['path']]
        require(len(found) == 1 and found[0].get('original_bytes') == profile['bytes']
                and found[0].get('original_sha256') == profile['sha256'], 'profile has no exact same-entry original inventory pin')
        selected.append(found[0])
    return selected


def describe(args):
    started = time.monotonic_ns()
    result = dict(schema='mr3-v63-partial-profile-description-v1', passed=False, description_complete=False,
        old_activity_passed=False, old_FAIL_rejudged=False, scientific_qualification=False,
        capacity_qualified=False, P2A_complete=False, root_cause='UNKNOWN',
        coverage='Only the two saved main lanes; no encoder/worker or all-five-lane claim; no new sampling',
        consumer_identity=identity(), actual_argv=[os.fsdecode(v) for v in Path('/proc/self/cmdline').read_bytes().split(b'\0') if v],
        started_monotonic_ns=started, execution_freeze=args.freeze, historical_source_freeze=G,
        profiles=[], errors=[])
    reads = Reads(started)
    try:
        require(Path(__file__).resolve() == A63/'describe_partial_profiles_v1.py'
                and args.spec == A63/'spec_v1.json' and args.output == OUTPUT, 'fixed canonical consumer/spec/output required')
        git = lambda *v: subprocess.check_output(['git',*v],cwd=ROOT)
        require(args.freeze == git('rev-parse','HEAD').decode().strip()
                == git('rev-parse','origin/main').decode().strip() and not git('status','--porcelain'),
                'exact clean pushed source freeze required')
        spec_raw = reads.current_source(args.spec)
        require(reads.frozen(args.spec,args.freeze) == spec_raw, 'spec itself differs from execution freeze')
        own = reads.current_source(Path(__file__))
        require(reads.frozen(Path(__file__),args.freeze) == own, 'consumer differs from execution freeze')
        spec = parse(spec_raw)
        validate_spec(spec)  # Must pass before opening any original pstats.
        original = reads.read(OLD_SOURCE)
        require(reads.frozen(Path(OLD_SOURCE['path']),G) == original, 'description source is not exact original G')
        description = old_description_function(original)
        old_scope = reads.read(OLD_SCOPE)
        require(reads.frozen(Path(OLD_SCOPE['path']),G) == old_scope, 'old scope is not exact G')
        inventory = parse(reads.read(spec['closed_inventory']))
        result['selected_closed_inventory_entries'] = inventory_members(inventory)
        metadata = {row['role']: parse(reads.read(row)) for row in FINISHED}
        for profile in PROFILES:
            meta = metadata[profile['role']]
            rows = meta.get('profiles')
            require(meta.get('profile_id') == 'mr3-p2a-v62-open101-8step-cprofile-v1'
                    and meta.get('role') == profile['role'] and meta.get('source_stable') is True
                    and type(meta.get('profile_complete')) is bool and type(rows) is list,
                    'original finished metadata identity differs')
            lane = [row for row in rows if row.get('lane') == 'main' and row.get('path') == profile['path']]
            require(len(lane) == 1 and lane[0]['bytes'] == profile['bytes'] and lane[0]['sha256'] == profile['sha256'],
                    'profile is not the exact original finished main lane')
        for profile in PROFILES:
            raw = reads.read(profile, profile=True)  # Exactly one full read and decode per selected original.
            summary = description(raw)
            reads.check_time()
            meta = metadata[profile['role']]
            result['profiles'].append(dict(**profile, description=summary,
                original_profile_complete=meta['profile_complete'], original_profile_errors=meta['profile_errors'],
                original_identity=meta['identity'], original_target_outcome=meta['target_outcome'],
                original_process_cpu_ns=meta['process_cpu_ns'], original_main_thread=meta['profiles'][0],
                original_elapsed_monotonic_ns=meta['ended_monotonic_ns']-meta['started_monotonic_ns']))
        reads.finish()
        require(reads.current_source(args.spec) == spec_raw and reads.current_source(Path(__file__)) == own,
                'consumer/spec bytes changed before final description')
        result.update(passed=True,description_complete=True,
                      description_scope='Complete descriptions of the two exact selected partial-activity profile files only')
    except (OSError,ValueError,KeyError,TypeError,IndexError,EOFError,SyntaxError,subprocess.CalledProcessError) as error:
        result['errors'].append(repr(error))
    result.update(ended_monotonic_ns=time.monotonic_ns(), input_bindings=reads.bindings,
                  profile_bytes_read=reads.profile_bytes, metadata_bytes_read=reads.metadata_bytes,
                  git_source_bytes_returned=reads.git_show_bytes, partial=not result['description_complete'],
                  resource=RESOURCE, original_logs_read=0, native_runs=0, model_runs=0, signals_sent=0)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--freeze',required=True)
    parser.add_argument('--spec',required=True,type=Path)
    parser.add_argument('--output',required=True,type=Path)
    args = parser.parse_args(argv)
    require(args.output == OUTPUT and args.output.parent == args.output.parent.resolve(strict=True), 'fixed output required')
    result = describe(args)
    raw = (json.dumps(result,indent=2,allow_nan=False)+'\n').encode()
    if len(raw) > 1048576:
        result.update(passed=False,description_complete=False,partial=True,profiles=[],
                      errors=[*result['errors'],'description output limit exceeded; original failed files unchanged'])
        raw = (json.dumps(result,indent=2,allow_nan=False)+'\n').encode()
    with args.output.open('xb') as output: output.write(raw)
    print(json.dumps({key:result[key] for key in ('schema','passed','description_complete','profile_bytes_read','errors')}))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
