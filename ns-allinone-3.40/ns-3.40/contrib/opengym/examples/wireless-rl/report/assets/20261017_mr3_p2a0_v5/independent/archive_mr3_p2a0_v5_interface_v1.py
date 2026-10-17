"""Archive the closed v5 failure without rewriting prior prefreeze evidence."""
from pathlib import Path
import gzip
import hashlib
import io
import json
import shutil
import subprocess
import tarfile

REPO = Path('/home/zhuyulab/ns3-workspace')
W = REPO / 'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl'
ASSETS = W / 'report/assets/20261017_mr3_p2a0_v5'
FREEZE = '57b7c7f372aef4d84acd25fcd97a9944fa1fe9bb'
TMP = Path('/tmp')
PACK = TMP / 'v5_selected_interface'
NATIVE = ASSETS / 'native/interface'
INDEPENDENT = ASSETS / 'independent'
ACCOUNTING = ASSETS / 'accounting'

def sha(data):
    return hashlib.sha256(data).hexdigest()

def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x') as out:
        out.write(json.dumps(data, indent=2, allow_nan=False) + '\n')

def copy_original(source, target, compress=False):
    raw = source.read_bytes()
    target.parent.mkdir(parents=True, exist_ok=True)
    if compress:
        with target.open('xb') as sink:
            with gzip.GzipFile(filename='', mode='wb', fileobj=sink, mtime=0) as out:
                out.write(raw)
    else:
        with target.open('xb') as sink:
            sink.write(raw)
    encoded = target.read_bytes()
    assert (gzip.decompress(encoded) if compress else encoded) == raw
    return {'source': str(source), 'selected': str(target.relative_to(ASSETS)),
            'encoding': 'gzip' if compress else 'identity', 'raw_bytes': len(raw),
            'raw_sha256': sha(raw), 'selected_bytes': len(encoded),
            'selected_sha256': sha(encoded)}

before = json.loads((TMP / 'mr3_p2a0_v5_assets_before_archive_v1.json').read_text())
for row in before['files']:
    assert sha((ASSETS / row['path']).read_bytes()) == row['sha256']
manifest = json.loads((PACK / 'manifest.json').read_text())
for row in manifest['files']:
    encoded = (PACK / row['selected']).read_bytes()
    raw = gzip.decompress(encoded) if row['encoding'] == 'gzip' else encoded
    assert len(encoded) == row['selected_bytes'] and sha(encoded) == row['selected_sha256']
    assert len(raw) == row['raw_bytes'] and sha(raw) == row['raw_sha256']
    assert Path(row['source']).read_bytes() == raw
assert manifest['source_files'] == 351
shutil.copytree(PACK, NATIVE)
originals = []
for name in [
    'mr3_p2a0_v5_interface_full_audit.json',
    'mr3_p2a0_v5_interface_close_transport_review_v1.json',
    'mr3_p2a0_v5_interface_live_05_final.json',
    'mr3_p2a0_v5_interface_live_05_final_fifo_phase.json',
    'mr3_p2a0_v5_interface_fixed_angular_v1.json',
    'mr3_p2a0_v5_interface_guard_pipeline_review_v1.json',
    'mr3_p2a0_v5_interface_input_review_v1.json',
    'mr3_p2a0_v5_local_control_review_v1.json',
    'mr3_p2a0_v5_source_preflight.json',
]:
    originals.append(copy_original(TMP / name, INDEPENDENT / name))
for name in ['mr3_p2a0_v5_tb2_angular_failure_forensics_v1.json',
             'mr3_p2a0_v5_tb2_90_94_forensics_v1.json']:
    originals.append(copy_original(TMP / name, INDEPENDENT / (name + '.gz'), True))
for name in ['mr3_p2a0_v5_interface_accounting_v1.json',
             'mr3_p2a0_v5_interface_launch.json']:
    originals.append(copy_original(TMP / name, ACCOUNTING / name))
for name in ['mr3_p2a0_v5_interface_console.log',
             'mr3_p2a0_v5_interface_full_audit_console.log']:
    originals.append(copy_original(TMP / name, ACCOUNTING / (name + '.gz'), True))
for name in ['mr3_p2a0_v4_guard_pipeline_review.py',
             'mr3_p2a0_v4_independent_input_episode_review_v1.py',
             'mr3_readonly_v4_interface_review.py']:
    originals.append(copy_original(TMP / name, INDEPENDENT / name))
originals.append(copy_original(TMP / 'mr3_p2a_package.py', INDEPENDENT / 'archive_selected_originals_v1.py'))
originals.append(copy_original(Path(__file__), INDEPENDENT / Path(__file__).name))
for path in sorted((TMP / 'mr3_p2a0_v5_diffdrive_primary_source_v1').rglob('*')):
    if path.is_file():
        originals.append(copy_original(path, INDEPENDENT / 'diffdrive_primary_source_v1' / path.relative_to(TMP / 'mr3_p2a0_v5_diffdrive_primary_source_v1')))
full = json.loads((TMP / 'mr3_p2a0_v5_interface_full_audit.json').read_text())
assert full['passed'] is False and full['freeze'] == FREEZE
assert len(full['source_bindings']) == 87
source_rows = []
source_tar = io.BytesIO()
with tarfile.open(fileobj=source_tar, mode='w') as out:
    for relative, binding in sorted(full['source_bindings'].items()):
        spec = binding.get('git_source', binding.get('source'))
        assert spec == FREEZE + ':' + relative
        payload = subprocess.check_output(['git', 'show', spec], cwd=REPO)
        assert sha(payload) == binding['sha256']
        if 'worktree_sha256' in binding:
            assert sha(payload) == binding['worktree_sha256']
        info = tarfile.TarInfo(relative)
        info.size = len(payload)
        info.mode = 0o644
        info.mtime = 0
        out.addfile(info, io.BytesIO(payload))
        source_rows.append({'relative_path': relative, 'git_source': spec,
                            'bytes': len(payload), 'sha256': sha(payload)})
source_path = INDEPENDENT / 'source_bindings_57b7c7f372ae.tar.gz'
with source_path.open('xb') as sink:
    with gzip.GzipFile(filename='', mode='wb', fileobj=sink, mtime=0) as out:
        out.write(source_tar.getvalue())
write_json(INDEPENDENT / 'source_bindings_57b7c7f372ae.json', {
    'schema': 'mr3-frozen-native-audit-source-payloads-v1', 'freeze': FREEZE,
    'source_binding_count': len(source_rows), 'source': 'exact Git object bytes from original full audit bindings',
    'archive': source_path.name, 'archive_sha256': sha(source_path.read_bytes()),
    'decoded_tar_sha256': sha(source_tar.getvalue()), 'files': source_rows,
    'scope': 'Preserves the original 87 Git source bindings; no re-evaluation using newer working tree code.'})
write_json(INDEPENDENT / 'archive_originals_manifest_v2.json', {
    'schema': 'mr3-p2a0-v5-original-review-archive-v2', 'freeze': FREEZE, 'files': originals,
    'native_manifest': 'native/interface/manifest.json',
    'native_manifest_sha256': sha((NATIVE / 'manifest.json').read_bytes()),
    'native_selected_files': manifest['source_files'], 'native_raw_bytes': manifest['raw_bytes'],
    'native_selected_bytes': manifest['selected_bytes'],
    'scope': 'Original outputs copied byte for byte or losslessly gzip; FAIL outputs remain FAIL.'})
close = json.loads((TMP / 'mr3_p2a0_v5_interface_close_transport_review_v1.json').read_text())
angular = json.loads((TMP / 'mr3_p2a0_v5_interface_fixed_angular_v1.json').read_text())
account = json.loads((TMP / 'mr3_p2a0_v5_interface_accounting_v1.json').read_text())
launch = json.loads((TMP / 'mr3_p2a0_v5_interface_launch.json').read_text())
write_json(ACCOUNTING / 'stage_outcomes_v2.json', {
    'schema': 'mr3-p2a0-v5-final-stage-accounting-v2', 'freeze': FREEZE,
    'stages': {'interface': {'status': 'FAIL', 'reason': 'actual tb2 angular norm exceeds unchanged 1.2 rad/s gate',
                             'returned_step_api_rows': account['returned_step_api_rows'],
                             'task_duration_sec': account['returned_physical_ns'] / 1e9,
                             'cleanup_physics_sec': account['physical_after_last_returned_snapshot_ns'] / 1e9,
                             'alignment_physics_sec': account['controlled_warmup_alignment_ns'] / 1e9,
                             'benchmark_wall_sec': account['wall_sec_including_all_attempts'],
                             'launcher_wall_sec': launch['wall_duration_sec'],
                             'maximum_angular_norm_rad_s': angular['robots']['tb2']['max_angular_norm_rad_s'],
                             'sampled_bounds_passed': angular['sampled_bounds_passed'],
                             'stimulus_coverage_passed': angular['stimulus_coverage_passed'],
                             'native_full_audit_passed': full['passed'], 'native_full_audit_errors': full['errors']},
               'terminal': {'status': 'SKIP', 'reason': 'interface real failure; declared stop rule'},
               'reset': {'status': 'SKIP', 'reason': 'interface real failure; declared stop rule'},
               'deadline': {'status': 'SKIP', 'reason': 'interface real failure; declared stop rule'}},
    'closure': {'saved_owned_plus_parent_launcher_identities': close['unique_saved_owned_plus_parent_launcher'],
                'all_same_identities_gone': close['all_saved_owned_and_benchmark_launcher_gone'],
                'native_started': close['native']['started'], 'native_exited': close['native']['exited'],
                'all_native_exit_zero': all(x == 0 for x in close['native']['returncodes']),
                'worker_returncode': close['supervisor']['worker_returncode'],
                'forced_shutdown': close['supervisor']['forced_shutdown']},
    'no_policy_gpu_training_or_95pct_credit': True,
    'pilot_decisions_charged_this_preparation': 0,
    'scope': 'Engineering preparation failure only. Passing parameter/activity/map/FIFO/closure subsets do not replace the failed physical bound or unrun stages.'})
for row in before['files']:
    assert sha((ASSETS / row['path']).read_bytes()) == row['sha256']
write_json(INDEPENDENT / 'archive_verification_v2.json', {
    'schema': 'mr3-p2a0-v5-canonical-archive-verification-v2', 'passed': True,
    'freeze': FREEZE, 'prior_assets_checked_unchanged': len(before['files']),
    'prior_assets': before['files'], 'native_selected_files_checked': manifest['source_files'],
    'native_selected_sha_decode_raw_sha_and_original_bytes_equal': True,
    'original_review_files_checked': len(originals), 'exact_git_source_payloads_checked': len(source_rows),
    'detached_full_audit_rerun': False,
    'detached_full_audit_scope': 'Original frozen full audit and 87 Git byte proofs preserved. Archive verification checks encoded/decoded/source bytes, without granting a new native audit or changing FAIL.'})
files = [{'path': str(p.relative_to(ASSETS)), 'bytes': p.stat().st_size, 'sha256': sha(p.read_bytes())}
         for p in sorted(ASSETS.rglob('*')) if p.is_file()]
write_json(ASSETS / 'inventory_v2.json', {'schema': 'mr3-p2a0-v5-final-inventory-v2', 'self_excluded': True,
    'freeze': FREEZE, 'prior_inventory_retained': 'prefreeze_inventory_v5.json',
    'prior_asset_count': len(before['files']), 'prior_assets_unchanged': True,
    'files': files, 'scope': 'All current v5 assets; prior prefreeze evidence and original FAIL outputs retained.'})
print(json.dumps({'passed': True, 'assets_files_excluding_inventory': len(files),
                  'native_files': manifest['source_files'], 'original_review_files': len(originals),
                  'source_bindings': len(source_rows), 'prior_assets_unchanged': len(before['files']),
                  'inventory_sha256': sha((ASSETS / 'inventory_v2.json').read_bytes())}, indent=2))
