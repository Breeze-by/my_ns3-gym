"""Only direct fakeproc observe calls; no old suite, formal CLI or native data."""
import hashlib
import argparse
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import time
from unittest.mock import patch

D = Path(__file__).parent
start = time.monotonic()


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ROOT = Path('/home/zhuyulab/ns3-workspace')
A25 = ROOT / 'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261018_mr3_p2a0_v25_smoother/independent'
base_path = A25 / 'mr3_v25_smoother_custody_v1.py'
new_path = D / 'mr3_v26_smoother_custody_v2.py'
fixture_path = A25 / 'test_smoother_custody_v1.py'
assert hashlib.sha256(base_path.read_bytes()).hexdigest() == '6edeb3a7e814fb024594be724ef98dce39e1d23a84af5d34d6d6faac0b5cb88b'
assert hashlib.sha256(fixture_path.read_bytes()).hexdigest() == 'd892ec45feac53c8bdf36a10a2f49f14fb443322a2f218cd8298f0fab8eaf15e'
base = load('original_6ede', base_path)
new = load('prospective_v26', new_path)
fixture = load('prior_fakeproc_fixture_only', fixture_path)


def snapshot(f):
    result = {}
    for pid in (101, 102, 110):
        result[str(pid)] = {}
        for name in ('stat', 'cmdline', 'maps'):
            path = f.proc / str(pid) / name
            result[str(pid)][name] = path.read_bytes().decode() if path.exists() else None
    result['disk'] = {name: {'sha256': hashlib.sha256(Path(row['path']).read_bytes()).hexdigest(),
                             'inode': Path(row['path']).stat().st_ino}
                      for name, row in f.binding['installed'].items()}
    return result


def run_case(module, kind):
    with tempfile.TemporaryDirectory(prefix='mr3-v26-fakeproc-') as directory, patch.object(fixture, 'm', module):
        f = fixture.Fixture(Path(directory))
        before = snapshot(f)
        original = module.file_proof
        count = 0
        hook_facts = {}

        def hook(value, read):
            nonlocal count
            count += 1
            if count == 3 and kind == 'hash_error_plus_ancestor_z':
                path = Path(f.binding['installed']['core']['path'])
                path.write_bytes(b'\x7fELFchanged')
                path = f.proc / '102/stat'
                path.write_text(path.read_text().replace(') S ', ') Z '))
                hook_facts.update(snapshot(f))
            result = original(value, read)
            if count == 4:
                path = f.proc / '110/maps'
                if kind == 'unrelated_vma':
                    with path.open('a') as stream:
                        stream.write('3000-4000 rw-p 00000000 00:00 0 [heap]\n')
                elif kind == 'ancestor_z':
                    path = f.proc / '102/stat'
                    path.write_text(path.read_text().replace(') S ', ') Z '))
                elif kind == 'ancestor_gone':
                    (f.proc / '102/stat').unlink()
                elif kind == 'wrong_core_inode':
                    parts = path.read_text().split()
                    parts[4] = str(int(parts[4]) + 1)
                    path.write_text(' '.join(parts) + '\n')
                elif kind == 'wrong_core_path':
                    path.write_text(path.read_text().replace(str(Path(f.binding['installed']['core']['path'])),
                        '/opt/ros/humble/lib/libvelocity_smoother_core.so'))
                elif kind == 'process_reuse':
                    path = f.proc / '110/stat'
                    path.write_text(path.read_text().replace('1010', '7777'))
                elif kind == 'ancestor_reuse_z':
                    path = f.proc / '102/stat'
                    path.write_text(path.read_text().replace('1002', '7777').replace(') S ', ') Z '))
                elif kind == 'wrong_argv':
                    path = f.proc / '110/cmdline'
                    path.write_bytes(path.read_bytes().replace(b'__ns:=/tb1', b'__ns:=/tb2'))
                elif kind == 'after_reuse_z_missing_exe':
                    path = f.proc / '110/stat'
                    path.write_text(path.read_text().replace('1010', '7777').replace(') S ', ') Z '))
                    (f.proc / '110/exe').unlink()
                hook_facts.update(snapshot(f))
            return result

        with patch.object(module, 'file_proof', side_effect=hook):
            proof = f.observe()
        return {'passed': proof['passed'], 'errors': proof['errors'],
                'episode_complete': proof['episodes'][0]['complete'],
                'pending_reason': proof['episodes'][0].get('pending_reason'),
                'attempts': proof['episodes'][0].get('attempts'),
                'first_process_facts': proof['episodes'][0].get('processes', {}).get('tb1', {}).get('capture_facts'),
                'before_fixture': before, 'after_hook_fixture': hook_facts}


cases = ('unrelated_vma', 'ancestor_z', 'ancestor_gone', 'wrong_core_inode',
         'wrong_core_path', 'process_reuse', 'ancestor_reuse_z', 'wrong_argv',
         'hash_error_plus_ancestor_z', 'after_reuse_z_missing_exe')
parser = argparse.ArgumentParser()
parser.add_argument('--case', choices=cases)
parser.add_argument('--output', type=Path, default=D / 'counterexamples_result_v2.json')
args = parser.parse_args()
selected_cases = (args.case,) if args.case else cases
results = {}
for case in selected_cases:
    old, proposed = run_case(base, case), run_case(new, case)
    assert old['passed'] is False and old['errors'], (case, old)
    if case == 'unrelated_vma':
        assert proposed['passed'] is True and proposed['errors'] == []
        facts = proposed['first_process_facts']
        assert facts['whole_maps_same'] is False and facts['checks']['core_mapping_same'] is True
        assert all(value is True for value in facts['checks'].values())
    elif case in ('ancestor_z', 'ancestor_gone'):
        assert proposed['passed'] is False and proposed['errors'] == []
        assert proposed['episode_complete'] is False
        assert 'no credit' in proposed['pending_reason']
    else:
        assert proposed['passed'] is False and proposed['errors'], (case, proposed)
    results[case] = {'original_6ede': old, 'prospective': proposed}

record = {'schema': 'mr3-v26-specific-capture-counterexamples-v1', 'passed': True,
    'cases': results, 'case_count': len(results), 'direct_observe_calls': len(results) * 2,
    'source_sha256': {str(path): hashlib.sha256(path.read_bytes()).hexdigest()
                      for path in (base_path, new_path, fixture_path, Path(__file__))},
    'argv': sys.argv, 'wall_seconds': time.monotonic() - start,
    'scope': 'Only explicitly selected isolated fakeproc cases using exact6ede and prospective source direct observe; no original21suite, formal review/consumer CLI, real /proc, ROS/DDS/build/native or native035 rerun. Proves synthetic behavior only, not actual035 cause.'}
path = args.output
with path.open('x') as stream:
    json.dump(record, stream, indent=2, allow_nan=False)
    stream.write('\n')
print(json.dumps({'result': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                  'cases': len(results), 'wall_seconds': record['wall_seconds']}))
