"""CPU-only packet of the original closed V13 failed matrix, never its future completion."""
from collections import Counter
from decimal import Decimal
import gzip
import hashlib
import json
from pathlib import Path
import subprocess
import tarfile

ROOT = Path('/home/zhuyulab/ns3-workspace')
W = ROOT / 'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl'
OUT = Path('/tmp/mr3_p2a_v13_closed_original_capture_v1')
FREEZE = '0063aa233ba3008ddcc1eb09ea8068112eea3965'
EVIDENCE = Path('/tmp/mr3_p2a_v13_matrix_evidence')
ASSET_REL = 'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261019_mr3_p2a_v13/'


def sha(path):
    result = hashlib.sha256()
    with path.open('rb') as source:
        for block in iter(lambda: source.read(1024 * 1024), b''):
            result.update(block)
    return result.hexdigest()


def sig(path):
    s = path.stat()
    return [s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns]


def save(path, value):
    with path.open('x') as output:
        json.dump(value, output, indent=2, allow_nan=False)
        output.write('\n')


def load(path):
    return json.loads(Path(path).read_text())


def main():
    capture_path = OUT / 'capture_manifest.json'
    capture = load(capture_path)
    assert capture['freeze'] == FREEZE and capture['plan_source_bindings_verified'] == 279
    assert len(capture['binaries']) == 10 and len(capture['frozen_sources']) == 304
    frozen = {r['original_relative_path']: r for r in capture['frozen_sources']}
    plan_path = Path(frozen[ASSET_REL + 'predeclared_plan_v13.json']['path'])
    binding_path = Path(frozen[ASSET_REL + 'native_custody_binding.json']['path'])
    plan, binding = load(plan_path), load(binding_path)
    summary = load(EVIDENCE / 'summary.json')
    launch = load('/tmp/mr3_p2a_v13_matrix_execution_receipt.json')
    final = load('/tmp/mr3_p2a_v13_matrix_final_closure.json')
    accounting = load('/tmp/mr3_p2a_v13_accounting_root_v1.json')
    observation = load('/tmp/mr3_p2a_v13_matrix_root_wait_observation.json')
    actual_tools = load('/tmp/mr3_p2a_v13_root_actual_tool_waits_v1.json')
    preflight = load('/tmp/mr3_p2a_v13_preflight.json')
    assert all(v['freeze'] == FREEZE for v in (summary, launch, final, accounting, observation, actual_tools, preflight))
    assert all(v['plan_sha256'] == sha(plan_path) for v in (summary, launch, preflight))
    assert preflight['passed'] is True and launch['returncode'] == 1
    assert summary['passed'] is False and summary['all_submitted_children_waited'] is True
    assert summary['gpu_calls'] == summary['optimizer_steps'] == summary['signals_sent'] == 0
    assert final['closure_passed'] is True and final['all_saved_identities_gone'] is True
    assert final['saved_identity_count'] == len(final['identities']) == 539
    assert final['execution_passed'] is False and final['passed'] is False
    assert all(r['current'] is None and r['same_identity_present'] is False for r in final['identities'])
    assert 'ended_wall_monotonic_ns' not in final
    for name, expected in final['inputs'].items():
        p = Path(name)
        assert p.stat().st_size == expected['bytes'] and sha(p) == expected['sha256'], name
    assert sha(Path('/tmp/mr3_p2a_v13_closed_original_scientific_inventory_v1.json')) == 'ecd28dc1cf9167450aefe49aa73460bf4debdb334d2bafd5e956401d7d8d1c0e'

    inputs, rows = [], []

    def add(path, archive_path, group, **extra):
        path = Path(path)
        assert path.is_file() and not path.is_symlink(), str(path)
        initial = sig(path)
        value = sha(path)
        assert sig(path) == initial
        inputs.append(path)
        rows.append({'path': archive_path, 'bytes': initial[2], 'sha256': value,
                     'archive_input_path': str(path), 'archive_input_stat': initial,
                     'source_origin': 'actual_closed_file', 'group': group, **extra})

    def directory(path, prefix, group):
        path = Path(path)
        assert path.is_dir()
        for p in sorted(path.rglob('*')):
            assert not p.is_symlink() and (p.is_file() or p.is_dir()), str(p)
            if p.is_file():
                add(p, prefix + '/' + p.relative_to(path).as_posix(), group)

    stages = {r['stage']: r for r in summary['stages']}
    assert [(r['stage'], r['status']) for r in summary['stages']] == [
        ('interface', 'PASS'), ('terminal', 'PASS'), ('reset', 'FAIL'), ('deadline', 'SKIPPED')]
    stage_inventory, completed, pending = [], [], []
    directory(EVIDENCE, 'matrix_evidence', 'matrix_evidence')
    for stage in plan['stages']:
        name, run = stage['stage'], Path(stage['run_directory'])
        observed = stages[name]
        present = run.is_dir()
        episodes = sorted(str(p.relative_to(run)) for p in run.glob('worker*/episode*') if p.is_dir()) if present else []
        row = {'stage': name, 'original_run_directory': str(run), 'actual_directory_exists': present,
               'original_status': observed['status'], 'original_passed': observed['passed'],
               'original_wall_seconds': observed.get('wall_seconds'), 'planned_episodes': stage['expected_episodes'],
               'actual_episode_directories': episodes}
        if present:
            directory(run, 'native_runs/' + name, 'native_' + name)
            native, watcher = load(stage['native']['output']), load(stage['watcher']['output'])
            assert native['freeze'] == watcher['freeze'] == FREEZE
            assert native['passed'] is True and watcher['passed'] is True
            assert observed['native']['returncode'] == observed['watcher']['returncode'] == 0
            row.update(native_actual_wait_returncode=0, watcher_actual_wait_returncode=0,
                       native_valid_transitions=native['valid_transitions'])
        else:
            assert observed['status'] == 'SKIPPED'
        stage_inventory.append(row)
        skips = {r['id']: r for r in observed.get('skipped_audits', [])}
        for job in stage['audits']:
            result = observed.get('audits', {}).get(job['id'])
            info = {'stage': name, 'id': job['id'], 'role': job['role'], 'original_output': job['output']}
            if result is not None:
                assert sha(Path(result['output'])) == result['output_sha256']
                assert result['passed'] is True
                if result['execution_kind'] == 'subprocess_waited':
                    assert result['returncode'] == 0 and load(result['receipt']) == result
                    assert load(result['output'])['passed'] is True
                    info.update(original_receipt=result['receipt'], actual_wait_wall_seconds=result['wall_seconds'])
                else:
                    assert result['execution_kind'] == 'fifo_manifest' and result['returncode'] is None
                info.update(passed=True, actual_wait_returncode=result['returncode'],
                            execution_kind=result['execution_kind'], output_sha256=result['output_sha256'])
                completed.append(info)
            else:
                assert not Path(job['output']).exists()
                if job.get('receipt'):
                    assert not Path(job['receipt']).exists()
                    info['original_receipt'] = job['receipt']
                info.update(status='NOT_SUBMITTED', original_plan_job=job)
                if job['id'] in skips:
                    info['original_skip_record'] = skips[job['id']]
                pending.append(info)
    assert [len(r['actual_episode_directories']) for r in stage_inventory] == [1, 2, 8, 0]
    assert [r.get('native_valid_transitions') for r in stage_inventory] == [32, 8, 256, None]
    science = [r for r in completed if r['role']]
    unsubmitted_science = [r for r in pending if r['role']]
    assert len(science) == 26 and len(unsubmitted_science) == 12
    reset = stages['reset']
    assert reset['error'] is None and reset['within_stage_wall_allocation'] is False
    assert Decimal(reset['wall_seconds']) > Decimal(reset['effective_stage_wall_cap_seconds'])
    assert len(reset['audits']) == 20 and len(reset['skipped_audits']) == 9
    assert all(r['returncode'] == 0 and r['passed'] is True for r in reset['audits'].values())
    assert all(r['reason'] == 'stage_wall_allocation_exhausted' for r in reset['skipped_audits'])

    external_names = [
        'accounting_root_v1.json', 'binaryproof.json', 'closed_archive_preparation_checklist_v1.json',
        'closed_original_scientific_inventory_v1.json', 'gentle_turn_config_cpu_receipt_v1.json',
        'gentle_turn_config_cpu_v1.bash', 'gentle_turn_config_cpu_v1.log', 'gentle_turn_yaml_delta_v1.json',
        'matrix_execution_receipt.json', 'matrix_final_closure.json', 'matrix_root_wait_observation.json',
        'nav2_profile_cpu_initial_v1.json', 'nav2_profile_cpu_v1.json', 'nav2_profile_cpu_v1.log',
        'nav2_profile_initial_benchmark.py', 'ppo_phase_v2_commands_v1.md',
        'ppo_phase_v2_static_entry_review_v1.json', 'preflight.json',
        'reset_completion_inventory_v1.json', 'root_actual_tool_waits_v1.json']
    for name in external_names:
        p = Path('/tmp/mr3_p2a_v13_' + name)
        scope = 'Original closed V13 matrix external receipt or separate CPU/static preparation snapshot. No future deferred reset completion or PPO execution is included.'
        if 'initial' in name:
            scope += ' Initial CPU draft/source snapshot is distinct from the actual frozen native source.'
        if name == 'reset_completion_inventory_v1.json':
            scope += ' This is static inventory of the original skips, not execution of any skipped job.'
        add(p, 'external_checks/' + p.name, 'external_checks', scope=scope)
    ppo_names = [
        'mr3_p2a_ppo_phase_runner_cpu_receipt_v1.json', 'mr3_p2a_ppo_phase_runner_cpu_receipt_v2.json',
        'mr3_p2a_ppo_phase_runner_original_cpu_v1.py', 'mr3_p2a_ppo_phase_runner_v1.py',
        'mr3_p2a_ppo_phase_runner_v1_usage.md', 'mr3_p2a_ppo_phase_runner_v2.py',
        'mr3_p2a_ppo_phase_runner_v2_usage.md', 'test_mr3_p2a_ppo_phase_runner_v1.py',
        'test_mr3_p2a_ppo_phase_runner_v2.py']
    for name in ppo_names:
        scope = 'Outside-Git orchestration/CPU tool, never invoked for native/PPO in this original failed matrix.'
        if name == 'mr3_p2a_ppo_phase_runner_original_cpu_v1.py':
            scope += ' Explicit reconstruction matching initial CPU SHA, not an original filesystem capture.'
        if name == 'mr3_p2a_ppo_phase_runner_v1.py':
            scope += ' Actual overwritten v1-path bytes; initial v1 CPU receipt does not bind these later bytes.'
        add(Path('/tmp') / name, 'external_ppo_tools/' + name, 'outside_git_ppo_tools', scope=scope)
    historical = [Path('/tmp/mr3_p2a0_v26_deadline_launch.json'),
                  ROOT / 'ros2_ws/ros2-multi-robot-automap/log/mr3_p2a0/mr3_p2a0_20261018_v26_deadline/benchmark_summary.json',
                  Path('/tmp/mr3_p2a0_v26_information_supplement_execution_v1.json'),
                  Path('/tmp/mr3_p2a0_v26_recovery_close_summary_v1.json')]
    for p in historical:
        add(p, 'historical_capacity_v26/' + p.name, 'historical_capacity_v26',
            scope='Historical V26 closed small receipts/recovery report used only as capacity reference. Different source, deployment, workload costs and competing activity; no V13 scientific credit or future wall upper bound. Original parent interruption/unknown returncode remain preserved.')
    for r in capture['frozen_sources']:
        p = Path(r['path'])
        assert sha(p) == r['sha256'] and p.stat().st_size == r['bytes']
        add(p, 'frozen_sources/' + r['original_relative_path'], 'frozen_related_sources',
            source_origin='git_blob', original_path=r['original_relative_path'], freeze=FREEZE,
            scope='Exact original 0063aa Git blob. Related plan/custody/assets/report scope only, not whole monorepo.')
    for r in capture['binaries']:
        p = Path(r['snapshot_path'])
        assert sig(p) == r['snapshot_stat'] and sha(p) == r['sha256'] == r['original_binding']['sha256']
        add(p, 'binaries/' + r['role'] + '/' + p.name, 'ten_original_elf_snapshots',
            source_origin='exclusive_original_elf_snapshot', original_path=r['original_binding']['path'],
            original_binding=r['original_binding'], original_capture_stat=r['original_stat'])
    add(capture_path, 'capture_provenance/capture_manifest.json', 'capture_provenance')
    add(OUT / 'checks/prepack_absence_check.json', 'capture_provenance/prepack_absence_check.json', 'capture_provenance')
    assert len({r['path'] for r in rows}) == len(rows)
    inventory = {'schema': 'mr3-v13-original-closed-packet-input-inventory-v1', 'freeze': FREEZE,
                 'file_count': len(rows), 'raw_bytes': sum(r['bytes'] for r in rows),
                 'file_counts_by_group': dict(Counter(r['group'] for r in rows)), 'files': rows,
                 'scope': 'Actual original closed failed matrix only; no future deferred completion/PPO artifacts.'}
    save(OUT / 'inventory_draft.json', inventory)
    print(json.dumps({k: inventory[k] for k in ('file_count', 'raw_bytes', 'file_counts_by_group')}), flush=True)

    archive_path = OUT / 'closed.tar.gz'
    with archive_path.open('xb') as destination:
        with gzip.GzipFile(filename='', fileobj=destination, mode='wb', mtime=0, compresslevel=6) as zipped:
            with tarfile.open(fileobj=zipped, mode='w|') as archive:
                for p, row in zip(inputs, rows):
                    info = tarfile.TarInfo(row['path'])
                    info.size, info.mode, info.mtime = row['bytes'], 0o644, 0
                    with p.open('rb') as source:
                        archive.addfile(info, source)
                    assert sig(p) == row['archive_input_stat'] and sha(p) == row['sha256']
    print(json.dumps({'phase': 'compressed', 'archive_bytes': archive_path.stat().st_size}), flush=True)
    expected, seen = {r['path']: r for r in rows}, set()
    with tarfile.open(archive_path, 'r:gz') as archive:
        for member in archive:
            assert member.isfile() and member.name in expected and member.name not in seen
            seen.add(member.name)
            total, value = 0, hashlib.sha256()
            with archive.extractfile(member) as stream:
                for block in iter(lambda: stream.read(1024 * 1024), b''):
                    total += len(block)
                    value.update(block)
            assert total == expected[member.name]['bytes'] and value.hexdigest() == expected[member.name]['sha256']
    assert seen == set(expected)
    with gzip.open(archive_path, 'rb') as source:
        while source.read(1024 * 1024):
            pass
    parts = []
    with archive_path.open('rb') as source:
        for index in range(10000):
            block = source.read(49_000_000)
            if not block:
                break
            part = OUT / ('closed.tar.gz.part%04d' % index)
            with part.open('xb') as target:
                target.write(block)
            assert part.stat().st_size <= 49_000_000
            parts.append({'path': part.name, 'bytes': len(block), 'sha256': sha(part)})
    concat = hashlib.sha256()
    for part in parts:
        with (OUT / part['path']).open('rb') as source:
            for block in iter(lambda: source.read(1024 * 1024), b''):
                concat.update(block)
    archive_sha = sha(archive_path)
    assert concat.hexdigest() == archive_sha
    for p, row in zip(inputs, rows):
        assert sig(p) == row['archive_input_stat'] and sha(p) == row['sha256']
    # The captured originals are still frozen; verify aliases/ELF originals as well.
    for r in capture['binaries']:
        p = Path(r['original_binding']['path']).resolve(strict=True)
        assert str(p) == r['original_binding']['resolved_path'] and sig(p) == r['original_stat'] and sha(p) == r['sha256']
    assert subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip() == FREEZE
    assert subprocess.check_output(['git', 'rev-parse', 'origin/main'], cwd=ROOT, text=True).strip() == FREEZE
    assert not subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT, text=True)

    gross = Decimal(observation['observed_wall_monotonic_ns'] - launch['started_wall_monotonic_ns']) / Decimal(10**9)
    assert gross == Decimal(accounting['gross_through_post_final_wait_observation_seconds']) == Decimal('6750.096230428')
    assert gross + Decimal(accounting['complete_observation_tool_wall_seconds']) == Decimal(accounting['charged_wall_seconds']) == Decimal('6752.047351676')
    assert Decimal(accounting['prior_used_wall_seconds']) + Decimal(accounting['charged_wall_seconds']) == Decimal(accounting['cumulative_used_wall_seconds']) == Decimal('23675.6332411916018')
    assert Decimal(accounting['cumulative_used_wall_seconds']) + Decimal(accounting['remaining_wall_seconds']) == Decimal('30000')
    assert accounting['remaining_wall_seconds'] == '6324.3667588083982'
    assert sha(Path(accounting['observation']['path'])) == accounting['observation']['sha256']
    account_note = {'schema': 'mr3-v13-original-matrix-conservative-archive-account-v1',
        'freeze': FREEZE, 'original_root_accounting': accounting,
        'formula': '(4109365423665771 - 4102615327435343) / 1e9 + 1.951121248',
        'original_outer_actual_wait': launch, 'original_final_internal_observation_wall_monotonic_ns': final['wall_monotonic_ns'],
        'original_final_exact_end_timestamp': None,
        'actual_tool_completion_rows': [{k: v for k, v in r.items() if k != 'output'} for r in actual_tools['waits'] if 'exit_code' in r],
        'pilot_decisions_remaining_unchanged': 1870, 'pilot_wall_seconds_remaining_unchanged': '2905.9547395464029',
        'scope': 'Exact root conservative upper charge; original final no exact end is invented. Complete observation-tool wall includes all its actual wait portions and is deliberately added to the after-final-wait gross. Final poll alone is not whole phase wall. Packing CPU is excluded from native engineering charge.'}
    save(OUT / 'accounting.json', account_note)
    direct = [{'path': str(p.relative_to(OUT)), 'bytes': p.stat().st_size, 'sha256': sha(p)}
              for p in (Path(__file__), OUT / 'inventory_draft.json', OUT / 'accounting.json')]
    result = {'schema': 'mr3-v13-original-closed-failed-matrix-packet-v1', 'freeze': FREEZE,
        'file_count': len(rows), 'raw_bytes': inventory['raw_bytes'], 'file_counts_by_group': inventory['file_counts_by_group'],
        'files': rows, 'parts': parts, 'direct_files': direct,
        'archive_bytes': archive_path.stat().st_size, 'archive_sha256': archive_sha,
        'plan_source_bindings_verified': 279, 'custody_source_bindings_verified': capture['custody_source_bindings_verified'],
        'related_original_git_blobs': 304, 'actual_original_elf_snapshots': 10,
        'binary_inventory': capture['binaries'], 'stage_inventory': stage_inventory,
        'all_tar_members_sha_size_roundtrip_verified': True, 'gzip_eof_crc_verified': True,
        'parts_concatenation_sha_verified': True, 'all_archive_input_stat_sha_stable_end_verified': True,
        'original_elf_stat_sha_still_stable_end_verified': True, 'clean_frozen_head_and_origin_end_verified': True,
        'preserved_outcome': {'matrix_execution_passed': False, 'outer_actual_wait_returncode': 1,
            'original_final_absence_passed': True, 'all_saved_identities_gone': True, 'saved_identity_count': 539,
            'original_final_execution_passed': False, 'original_submitted_children_all_waited': True,
            'scientific_roles_actually_passed': science, 'scientific_roles_not_submitted': unsubmitted_science,
            'scientific_pass_count': 26, 'scientific_required_count': 38,
            'all_completed_jobs': completed, 'all_unsubmitted_jobs': pending,
            'reset_submitted_audits_all_actual_rc0_pass': 20, 'reset_skipped_audits': reset['skipped_audits'],
            'reset_original_wall_seconds': reset['wall_seconds'], 'reset_original_effective_stage_cap_seconds': reset['effective_stage_wall_cap_seconds'],
            'reset_original_stage_passed': False, 'reset_original_error': None,
            'deadline_started': False, 'ppo_minimum_pilot_validation_started': False,
            'future_reset_readonly_completion_included': False, 'gpu_calls': 0, 'optimizer_steps': 0,
            'scope': 'Original stage-budget FAIL remains permanent; all submitted native/watch/science results are preserved separately. Twelve scientific roles are absent (four reset, eight deadline), including nine original reset skipped jobs. This packet grants no complete38-role matrix, minimum/pilot/PPO/final-policy/95% or P2A PASS credit.'},
        'gross_wall_accounting': account_note,
        'restore': 'Concatenate parts in listed order and verify archive_sha256, gzip EOF/CRC and every regular member SHA/size against files[]. Source inputs are original closed runtime/external files, exclusive original ELF snapshots and exact0063aa related Git blobs. direct_files[] bind the pack tool, prepack inventory and accounting. Later checks/pack_actual_wait.json binds this immutable manifest after the real CPU child exit.',
        'scope': 'Only original closed V13 matrix FAIL, stored exclusively in /tmp. HistoricalV26 capacity data and outside-Git CPU/static tools have their separate scopes. Future reset completion and all unstarted PPO/runtime artifacts are excluded. No Git/ELF/source/runtime original edited and no reader/native rerun.'}
    save(OUT / 'manifest.json', result)
    archive_path.unlink()
    print(json.dumps({k: result[k] for k in ('file_count', 'raw_bytes', 'archive_bytes', 'archive_sha256', 'parts')}), flush=True)


if __name__ == '__main__':
    main()
