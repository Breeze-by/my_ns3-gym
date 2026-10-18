"""Archive only closed V12 originals and the already verified exclusive snapshots.

No current worktree source or potentially rebuilt original ELF is used as V12.
"""
from collections import Counter
from decimal import Decimal
import gzip
import hashlib
import json
from pathlib import Path
import tarfile

ROOT = Path('/home/zhuyulab/ns3-workspace')
W = ROOT / 'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl'
OUT = W / 'report/assets/20261019_mr3_p2a_v12/closed_evidence'
FREEZE = 'ea759bea57d1e2ddd126d56c3a81801a072535a0'
CACHE = Path('/tmp/mr3_p2a_v12_closed_capture_v1')
CAPTURE = CACHE / 'capture_manifest.json'
DRAFT = Path('/tmp/mr3_p2a_v12_closed_archive_inventory_draft_v1.json')
EVIDENCE = Path('/tmp/mr3_p2a_v12_matrix_evidence')


def file_sha(path):
    value = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(block)
    return value.hexdigest()


def signature(path):
    s = path.stat()
    return [s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns]


def exclusive(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write('\n')


def main():
    capture = json.loads(CAPTURE.read_text())
    draft = json.loads(DRAFT.read_text())
    assert capture['freeze'] == draft['freeze'] == FREEZE
    assert file_sha(CAPTURE) == draft['capture_manifest_sha256']
    assert capture['plan_source_bindings_verified'] == 277
    assert len(capture['binaries']) == 10 and len(capture['frozen_sources']) == 395
    cached_sources = {r['original_relative_path']: r for r in capture['frozen_sources']}
    cached_binaries = {r['original_binding']['path']: r for r in capture['binaries']}
    plan_relative = str((W / 'report/assets/20261019_mr3_p2a_v12/predeclared_plan_v12.json').relative_to(ROOT))
    plan_path = Path(cached_sources[plan_relative]['path'])
    plan = json.loads(plan_path.read_text())
    summary = json.loads((EVIDENCE / 'summary.json').read_text())
    launch = json.loads(Path('/tmp/mr3_p2a_v12_matrix_execution_receipt.json').read_text())
    final = json.loads(Path('/tmp/mr3_p2a_v12_matrix_final_closure.json').read_text())
    root_wait = json.loads(Path('/tmp/mr3_p2a_v12_matrix_root_wait_observation.json').read_text())
    root_account = json.loads(Path('/tmp/mr3_p2a_v12_accounting_root_v1.json').read_text())
    preflight = json.loads(Path('/tmp/mr3_p2a_v12_preflight.json').read_text())
    assert all(v['freeze'] == FREEZE for v in (summary, launch, final, root_wait, root_account, preflight))
    assert all(v['plan_sha256'] == file_sha(plan_path) for v in (summary, launch, preflight))
    assert preflight['passed'] is True and launch['returncode'] == 1
    assert launch['wall_seconds'] == '1849.821587123'
    assert summary['passed'] is False and summary['all_submitted_children_waited'] is True
    assert final['closure_passed'] is True and final['all_saved_identities_gone'] is True
    assert final['saved_identity_count'] == len(final['identities']) == 253
    assert final['execution_passed'] is False and final['passed'] is False
    assert all(r['current'] is None and r['same_identity_present'] is False for r in final['identities'])
    assert 'ended_wall_monotonic_ns' not in final
    for name, expected in final['inputs'].items():
        p = Path(name)
        assert p.stat().st_size == expected['bytes'] and file_sha(p) == expected['sha256'], name

    stages = {r['stage']: r for r in summary['stages']}
    assert [(r['stage'], r['status']) for r in summary['stages']] == [
        ('interface', 'PASS'), ('terminal', 'PASS'), ('reset', 'FAIL'), ('deadline', 'SKIPPED')]
    stage_presence, stage_outcomes = [], []
    submitted_science, unsubmitted_science = [], []
    submitted_auxiliary, unsubmitted_auxiliary = [], []
    for stage in plan['stages']:
        name = stage['stage']
        observed = stages[name]
        run = Path(stage['run_directory'])
        present = run.is_dir()
        presence = {'stage': name, 'original_path': str(run), 'actual_directory_exists': present,
                    'original_execution_status': observed['status'], 'planned_episodes': stage['expected_episodes']}
        stage_presence.append(presence)
        if present:
            native = json.loads(Path(stage['native']['output']).read_text())
            watcher = json.loads(Path(stage['watcher']['output']).read_text())
            assert native['freeze'] == watcher['freeze'] == FREEZE
            episodes = sorted(str(p.relative_to(run)) for p in run.glob('worker*/episode*') if p.is_dir())
            presence['actual_episode_directories'] = episodes
            stage_outcomes.append({'stage': name, 'native_original_passed': native['passed'],
                'native_actual_wait_returncode': observed['native']['returncode'],
                'native_valid_transitions': native['valid_transitions'],
                'watcher_original_passed': watcher['passed'],
                'watcher_actual_wait_returncode': observed['watcher']['returncode'],
                'native_output_original_path': stage['native']['output'],
                'watcher_output_original_path': stage['watcher']['output']})
        else:
            assert observed['status'] == 'SKIPPED'
        observed_jobs = observed.get('audits', {})
        skips = {r['id']: r for r in observed.get('skipped_audits', [])}
        for job in stage['audits']:
            row = {'stage': name, 'id': job['id'], 'role': job['role'],
                   'required': job['required'], 'output_original_path': job['output']}
            if job['id'] in observed_jobs:
                value = observed_jobs[job['id']]
                assert file_sha(Path(value['output'])) == value['output_sha256']
                if value['execution_kind'] == 'subprocess_waited':
                    assert value['freeze'] == FREEZE
                    assert json.loads(Path(value['receipt']).read_text()) == value
                    assert json.loads(Path(value['output']).read_text())['passed'] is value['passed']
                    row['receipt_original_path'] = value['receipt']
                    row['actual_wait_wall_seconds'] = value['wall_seconds']
                else:
                    assert value['execution_kind'] == 'fifo_manifest' and value['returncode'] is None
                row.update(status='ACTUALLY_COMPLETED', passed=value['passed'],
                    execution_kind=value['execution_kind'], actual_wait_returncode=value['returncode'],
                    output_sha256=value['output_sha256'])
                (submitted_science if job['role'] else submitted_auxiliary).append(row)
            else:
                assert not Path(job['output']).exists(), job['output']
                if job.get('receipt'):
                    assert not Path(job['receipt']).exists(), job['receipt']
                    row['receipt_original_path'] = job['receipt']
                row['status'] = 'NOT_SUBMITTED'
                if job['id'] in skips:
                    row['original_skip_record'] = skips[job['id']]
                (unsubmitted_science if job['role'] else unsubmitted_auxiliary).append(row)
    assert [r['stage'] for r in stage_presence if r['actual_directory_exists']] == ['interface', 'terminal', 'reset']
    assert [len(r.get('actual_episode_directories', [])) for r in stage_presence] == [1, 2, 2, 0]
    assert len(submitted_science) == len(unsubmitted_science) == 19
    assert all(r['passed'] and r['actual_wait_returncode'] == 0 for r in submitted_science)
    assert [r['native_actual_wait_returncode'] for r in stage_outcomes] == [0, 0, 1]
    assert [r['watcher_actual_wait_returncode'] for r in stage_outcomes] == [0, 0, 0]

    sources, rows = [], []
    for item in draft['files']:
        group, original = item['group'], item['original_path']
        if group == 'frozen_related_sources':
            cached = cached_sources[original]
            path, name = Path(cached['path']), 'frozen_sources/' + original
        elif group == 'ten_original_elf_snapshots':
            cached = cached_binaries[original]
            path = Path(cached['snapshot_path'])
            name = 'binaries/' + cached['role'] + '/' + path.name
        else:
            path = Path(original)
            if group.startswith('native_'):
                stage = group.removeprefix('native_')
                run = Path(next(r for r in plan['stages'] if r['stage'] == stage)['run_directory'])
                name = 'native_runs/' + stage + '/' + path.relative_to(run).as_posix()
            elif group == 'matrix_evidence':
                name = 'matrix_evidence/' + path.relative_to(EVIDENCE).as_posix()
            elif group == 'external_sdformat_probe':
                name = group + '/' + path.relative_to('/tmp/mr3_p2a_v12_actual_sdformat_parse_v1').as_posix()
            elif group == 'outside_git_ppo_tools':
                name = 'external_ppo_tools/' + path.name
            elif group == 'capture_provenance':
                name = 'capture_provenance/' + path.name
            else:
                assert group == 'external_checks'
                name = group + '/' + path.name
        assert path.is_file() and not path.is_symlink(), str(path)
        stat = signature(path)
        sha = file_sha(path)
        assert signature(path) == stat and stat[2] == item['bytes']
        row = {'path': name, 'original_path': original, 'bytes': stat[2], 'sha256': sha,
               'archive_input_path': str(path), 'archive_input_stat': stat, 'inventory_group': group,
               'source_origin': 'actual_closed_file'}
        if group == 'frozen_related_sources':
            assert sha == cached['sha256']
            row.update(source_origin='git_blob', freeze=FREEZE,
                scope='Exact original Git blob captured before the source was unfrozen; not a later worktree file.')
        elif group == 'ten_original_elf_snapshots':
            assert sha == cached['sha256'] == cached['original_binding']['sha256']
            assert stat == cached['snapshot_stat']
            row.update(source_origin='exclusive_original_elf_snapshot',
                original_binding=cached['original_binding'], original_capture_stat=cached['original_stat'],
                scope='Original bound ELF matched and remained stat/SHA stable through the completed exclusive capture. Later original-path rebuilds are outside V12; only this captured snapshot is packed.')
        elif group == 'outside_git_ppo_tools':
            row['scope'] = 'External /tmp orchestration/CPU tool; outside original Git freeze and never invoked for native/PPO in this failed V12 matrix.'
            if path.name == 'mr3_p2a_ppo_phase_runner_original_cpu_v1.py':
                row['lineage'] = 'Explicit reconstruction matching original v1 CPU-receipt SHA, not an original filesystem capture.'
            elif path.name == 'mr3_p2a_ppo_phase_runner_v1.py':
                row['lineage'] = 'Actual later v1-path bytes; initial CPU receipt is preserved separately and does not bind this overwritten path.'
        rows.append(row)
        sources.append(path)
    assert len(rows) == draft['file_count'] == 1718
    assert len({r['path'] for r in rows}) == len(rows)
    assert sum(r['bytes'] for r in rows) == draft['raw_bytes'] == 1320736482
    print(json.dumps({'phase': 'inventory_bound', 'files': len(rows), 'raw_bytes': draft['raw_bytes']}), flush=True)

    archive_path = OUT / 'closed.tar.gz'
    with archive_path.open('xb') as destination:
        with gzip.GzipFile(filename='', fileobj=destination, mode='wb', mtime=0, compresslevel=6) as zipped:
            with tarfile.open(fileobj=zipped, mode='w|') as archive:
                for path, row in zip(sources, rows):
                    info = tarfile.TarInfo(row['path'])
                    info.size, info.mode, info.mtime = row['bytes'], 0o644, 0
                    with path.open('rb') as stream:
                        archive.addfile(info, stream)
                    assert signature(path) == row['archive_input_stat'] and file_sha(path) == row['sha256']
    print(json.dumps({'phase': 'compressed', 'archive_bytes': archive_path.stat().st_size}), flush=True)
    expected, seen = {r['path']: r for r in rows}, set()
    with tarfile.open(archive_path, 'r:gz') as archive:
        for member in archive:
            assert member.isfile() and member.name in expected and member.name not in seen
            seen.add(member.name)
            size, value = 0, hashlib.sha256()
            with archive.extractfile(member) as stream:
                for block in iter(lambda: stream.read(1024 * 1024), b''):
                    size += len(block)
                    value.update(block)
            assert size == expected[member.name]['bytes']
            assert value.hexdigest() == expected[member.name]['sha256']
    assert seen == set(expected)
    with gzip.open(archive_path, 'rb') as stream:
        while stream.read(1024 * 1024):
            pass
    parts = []
    with archive_path.open('rb') as stream:
        for index in range(10000):
            block = stream.read(49_000_000)
            if not block:
                break
            part = OUT / ('closed.tar.gz.part%04d' % index)
            with part.open('xb') as target:
                target.write(block)
            assert part.stat().st_size < 100_000_000
            parts.append({'path': part.name, 'bytes': len(block), 'sha256': file_sha(part)})
    combined = hashlib.sha256()
    for part in parts:
        with (OUT / part['path']).open('rb') as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b''):
                combined.update(block)
    archive_sha = file_sha(archive_path)
    assert combined.hexdigest() == archive_sha
    for path, row in zip(sources, rows):
        assert signature(path) == row['archive_input_stat'] and file_sha(path) == row['sha256']
    print(json.dumps({'phase': 'roundtrip_crc_parts_end_stability_verified'}), flush=True)

    observation_path = Path(root_account['observation']['path'])
    assert file_sha(observation_path) == root_account['observation']['sha256']
    start = launch['started_wall_monotonic_ns']
    observation_ns = root_wait['after_final_wait_wall_monotonic_ns']
    gross = Decimal(observation_ns - start) / Decimal(10**9)
    assert str(gross) == root_account['gross_to_observation_seconds'] == '1851.020996216'
    assert gross + Decimal(root_account['complete_final_tool_call_wall_seconds']) == Decimal('1851.306438272')
    assert Decimal('15072.2794512436018') + Decimal('1851.306438272') == Decimal(root_account['engineering_cumulative_seconds'])
    assert Decimal(root_account['engineering_cumulative_seconds']) + Decimal(root_account['engineering_remaining_seconds']) == Decimal('30000')
    accounting = {'schema': 'mr3-p2a-v12-root-declared-conservative-charge-archive-v1', 'freeze': FREEZE,
        'original_root_accounting': root_account, 'original_after_actual_final_wait_observation': root_wait,
        'outer_actual_wait': {'start_wall_monotonic_ns': start,
            'end_wall_monotonic_ns': launch['ended_wall_monotonic_ns'],
            'returncode': launch['returncode'], 'wall_seconds': launch['wall_seconds']},
        'independent_final_reader_internal_observation_wall_monotonic_ns': final['wall_monotonic_ns'],
        'independent_final_reader_exact_end_timestamp': None,
        'independent_final_reader_actual_tool_returncode': None,
        'formula': '(4101229845555849 - 4099378824559633) / 1e9 + 0.285442056',
        'charge_seconds_conservative_upper_bound': '1851.306438272',
        'engineering_used_before_seconds': '15072.2794512436018',
        'engineering_used_after_seconds': '16923.5858895156018',
        'engineering_remaining_after_seconds': '13076.4141104843982',
        'engineering_authorized_total_seconds': '30000',
        'pilot_decisions_remaining_unchanged': 1870, 'pilot_wall_seconds_remaining_unchanged': '2905.9547395464029',
        'scope': 'Root-declared conservative upper bound from observation after real waits plus the whole observation-tool wall; this deliberately overcounts. The original final has no end or actual-tool-returncode field, and neither is invented. Packing is CPU-only and excluded from native engineering charge.'}
    exclusive(OUT / 'accounting.json', accounting)
    with (OUT / 'inventory_draft.json').open('xb') as stream:
        stream.write(DRAFT.read_bytes())
    direct = [{'path': str(p.relative_to(OUT)), 'bytes': p.stat().st_size, 'sha256': file_sha(p)}
              for p in (Path(__file__), OUT / 'accounting.json', OUT / 'inventory_draft.json')]
    ppo_v2 = json.loads(Path('/tmp/mr3_p2a_ppo_phase_runner_cpu_receipt_v2.json').read_text())
    result = {'schema': 'mr3-p2a-v12-closed-packet-v1', 'freeze': FREEZE,
        'file_count': len(rows), 'raw_bytes': draft['raw_bytes'],
        'archive_bytes': archive_path.stat().st_size, 'archive_sha256': archive_sha,
        'files': rows, 'parts': parts, 'direct_files': direct,
        'file_counts_by_top_directory': dict(Counter(r['path'].split('/')[0] for r in rows)),
        'original_plan_source_bindings_verified': capture['plan_source_bindings_verified'],
        'custody_source_bindings_verified': capture['custody_source_bindings_verified'],
        'frozen_related_source_files': 395, 'source_scope': draft['source_scope'],
        'all_tar_members_byte_roundtrip_verified': True, 'gzip_to_eof_crc_verified': True,
        'parts_concatenation_sha_verified': True, 'all_archive_input_stat_sha_stable_end_verified': True,
        'original_elf_capture_before_unfreeze_verified': True,
        'current_original_elf_rechecked_after_future_rebuild': False,
        'git_source_bytes_bound_to_original_freeze': True, 'binary_inventory': capture['binaries'],
        'gross_wall_accounting': accounting,
        'preserved_outcome': {'stage_directory_presence': stage_presence, 'native_and_watcher_results': stage_outcomes,
            'outer_actual_wait_returncode': launch['returncode'], 'matrix_coordinator_passed': summary['passed'],
            'matrix_coordinator_internal_charge_seconds': summary['charged_wall_seconds'],
            'all_submitted_children_waited': summary['all_submitted_children_waited'],
            'final_absence_closure_passed': final['closure_passed'],
            'all_actual_saved_matrix_identities_gone': final['all_saved_identities_gone'],
            'actual_saved_matrix_identity_count': final['saved_identity_count'],
            'overall_execution_passed': final['passed'],
            'scientific_roles_with_actual_waited_receipts': submitted_science,
            'scientific_roles_without_submitted_receipts': unsubmitted_science,
            'auxiliary_jobs_actually_completed': submitted_auxiliary,
            'auxiliary_jobs_without_submitted_receipts': unsubmitted_auxiliary,
            'ppo_minimum_pilot_final_only_validation': 'NOT_SUBMITTED_AFTER_MATRIX_FAILURE',
            'gpu_calls': summary['gpu_calls'], 'optimizer_steps': summary['optimizer_steps'],
            'scope': 'The reset native rc1 and its two actual worker attempts remain failures. Deadline, reset consumers and PPO remain unsubmitted. Successful absence of all 253 saved identities is separate from failed overall execution. No missing process identity, episode, result or returncode is invented.'},
        'external_ppo_tool_scope': {'git_freeze_source_claimed': False, 'native_uses_in_v12': 0,
            'v1_lineage': ppo_v2['v1_retention'], 'peer_review_embedded_original': ppo_v2['peer_review'],
            'separate_peer_message_original_file': None,
            'scope': 'Actual outside-Git tool/CPU files and embedded review only. Explicit reconstruction and overwritten v1 path retain their actual lineage. No standalone peer-message original exists.'},
        'restore': 'Concatenate parts in listed order, verify archive_sha256, read gzip through EOF, and verify each regular tar member SHA/size against files[]. Frozen sources are 395 related original Git blobs, not the whole monorepo. Binary members are ten exclusive original V12 snapshots. direct_files[] binds the pack script, accounting and pre-pack inventory. Later checks/pack_actual_wait.json binds this manifest after the CPU pack child really exits.',
        'scope': 'Canonical V12 closed evidence only. No native/consumer was rerun, and no source/runtime original was edited. All failures/SKIP remain preserved. No complete 38-role matrix, PPO minimum, pilot, final-policy validation, 95% reliability or P2A acceptance credit.'}
    exclusive(OUT / 'manifest.json', result)
    archive_path.unlink()
    print(json.dumps({k: result[k] for k in ('file_count', 'raw_bytes', 'archive_bytes', 'archive_sha256', 'parts')}), flush=True)


if __name__ == '__main__':
    main()
