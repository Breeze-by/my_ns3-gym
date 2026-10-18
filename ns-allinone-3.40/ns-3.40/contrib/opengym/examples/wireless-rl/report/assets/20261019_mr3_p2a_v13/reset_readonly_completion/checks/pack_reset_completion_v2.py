"""CPU-only archive of the closed reset read-only completion, separate from original raw."""
from collections import Counter
from decimal import Decimal
import gzip
import hashlib
import json
from pathlib import Path
import subprocess
import tarfile

OUT = Path('/tmp/mr3_p2a_v13_reset_completion_packet_v2')
EVIDENCE = Path('/tmp/mr3_p2a_v13_reset_completion_evidence_v2')
FREEZE = '0063aa233ba3008ddcc1eb09ea8068112eea3965'
ROOT = Path('/home/zhuyulab/ns3-workspace')


def sha(path):
    value = hashlib.sha256()
    with path.open('rb') as source:
        for block in iter(lambda: source.read(1024 * 1024), b''):
            value.update(block)
    return value.hexdigest()


def sig(path):
    s = path.stat()
    return [s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns]


def load(path):
    return json.loads(Path(path).read_text())


def save(path, value):
    with path.open('x') as target:
        json.dump(value, target, indent=2, allow_nan=False)
        target.write('\n')


def main():
    summary = load(EVIDENCE / 'summary.json')
    plan_path = Path('/tmp/mr3_p2a_v13_reset_completion_plan_v2.json')
    plan = load(plan_path)
    outer = load('/tmp/mr3_p2a_v13_reset_completion_outer_wait_v2.json')
    final = load('/tmp/mr3_p2a_v13_reset_completion_final_absence_v2.json')
    account = load('/tmp/mr3_p2a_v13_reset_completion_accounting_root_v2.json')
    observation = load('/tmp/mr3_p2a_v13_reset_completion_root_wait_observation_v2.json')
    tools = load('/tmp/mr3_p2a_v13_reset_completion_root_actual_tool_waits_v2.json')
    reference = load(OUT / 'original_raw_reference.json')
    proof = load(OUT / 'checks/postclose_source_absence_proof.json')
    assert all(v['freeze'] == FREEZE for v in (summary, plan, outer, final, account, observation, tools, reference))
    assert summary['plan_sha256'] == sha(plan_path) == 'b7df79cea5432664f850affdaad0f41e138f71307191b7eff25ec496bd75b430'
    assert summary['passed'] is True and summary['errors'] == [] and summary['skipped_jobs'] == []
    assert summary['all_submitted_children_waited'] is True and summary['within_allocation'] is True
    assert summary['completed_scientific_roles'] == 30 and summary['total_required_roles'] == 38
    assert summary['new_passed_reset_roles'] == ['input', 'angular', 'physics', 'closure']
    assert summary['original_matrix_passed'] is False and summary['all38_scientific_complete'] is False and summary['ppo_admission'] is False
    assert summary['new_native_calls'] == summary['gpu_calls'] == summary['signals_sent'] == 0
    assert outer['returncode'] == 0 and outer['errors'] == []
    assert final['passed'] is True and final['closure_passed'] is True and final['execution_passed'] is True
    assert final['saved_identity_count'] == len(final['identities']) == 548 and final['all_saved_identities_gone'] is True
    assert all(r['same_identity_present'] is False for r in final['identities'])
    assert all(final[k] is False for k in ('original_matrix_passed', 'all38_scientific_complete', 'ppo_admission'))
    for p, expected in final['inputs'].items():
        path = Path(p)
        assert path.stat().st_size == expected['bytes'] and sha(path) == expected['sha256'], p
    assert final['plan'] == outer['plan'] == {'path': str(plan_path), 'bytes': plan_path.stat().st_size, 'sha256': sha(plan_path)}
    assert final['tool'] == outer['tool'] == plan['tool']
    assert sha(Path(plan['tool']['path'])) == plan['tool']['sha256'] == '3dd3e75b1d3be168099579d3b3aa9dcba8e8421c2b8f95a149dc6a7f3a85b275'
    for p in (summary['runtime_source_proof_before'], summary['runtime_source_proof_end'], plan['runtime_source_proof_at_prepare']):
        assert p['source_bindings_verified'] == 279 and p['elf_bindings_verified'] == 10
        assert p['runtime_head'] == FREEZE and p['clean_worktree'] is True and p['ancestor_check_actual_returncode'] == 0
    assert proof['source_count'] == 279 and proof['elf_count'] == 10 and proof['actual_saved_identity_count'] == 548
    assert len(reference['reused_original_input_bindings']) == reference['reused_input_count'] == 186
    assert reference['original_manifest']['sha256'] == '914f9428cc0c0b2970e87571d77f977e144cd4f897c6d12f9747f67e0bb6d65d'
    assert reference['original_archive_sha256'] == '2671b53407e1dc018094236dff9ddf3e2c5d30211f338822ee53789a60b92195'
    assert sha(Path(reference['original_manifest']['path'])) == reference['original_manifest']['sha256']

    actual = []
    assert set(summary['new_jobs']) == {j['id'] for j in plan['jobs']} and len(summary['new_jobs']) == 9
    for job in plan['jobs']:
        row = summary['new_jobs'][job['id']]
        assert sha(Path(row['output'])) == row['output_sha256']
        if row['execution_kind'] == 'subprocess_waited':
            assert load(row['receipt']) == row
            assert load(row['output'])['passed'] is row['passed']
            assert row['returncode'] == (1 if job['id'] == 'physical_per_episode' else 0)
        else:
            assert row['execution_kind'] in ('aggregate', 'fifo_manifest') and row['returncode'] is None
        assert row['passed'] is (job['id'] != 'physical_per_episode')
        actual.append({'id': job['id'], 'role': job['role'], 'required': job.get('required', True),
            'execution_kind': row['execution_kind'], 'actual_wait_returncode': row['returncode'],
            'passed': row['passed'], 'actual_wait_wall_seconds': row.get('wall_seconds'),
            'original_output': row['output'], 'output_sha256': row['output_sha256'],
            'original_receipt': row.get('receipt')})
    assert Counter(r['execution_kind'] for r in actual) == {'subprocess_waited': 7, 'aggregate': 1, 'fifo_manifest': 1}
    assert next(j for j in plan['jobs'] if j['id'] == 'physical_per_episode')['required'] is False
    coverage = Path('/tmp/mr3_p2a_v13_reset_optional_coverage_review_v1.json')
    assert sha(coverage) == 'd323b6cb03bb7d833ae415e2cf4092c90e64e79d1dc07a9658541206e5df7c6d'
    coverage_value = load(coverage)
    assert coverage_value['per_episode_command_actual_returncode'] == 1
    assert coverage_value['per_episode_report_passed'] is False and coverage_value['mandatory_pooled_passed'] is True

    index_path = Path('/tmp/mr3_p2a_v13_reset_completion_prepare_cpu_artifact_index_v1.json')
    assert sha(index_path) == '4ba4a93cd597300a99ce0eff7ebceaf5b92f72a843437ce1e8436359a8f8c635'
    index = load(index_path)
    indexed = [*index['attribution_receipts'], *index['derived_console_copies'], *index['existing_cpu_and_source_artifacts']]
    for expected in indexed:
        p = Path(expected['path'])
        assert p.stat().st_size == expected['bytes'] and sha(p) == expected['sha256']
    old_cpu = load('/tmp/mr3_p2a_v13_reset_completion_cpu_final_v1.json')
    cpu14 = load('/tmp/mr3_p2a_v13_reset_completion_cpu_final_v2.json')
    cpu18 = load('/tmp/mr3_p2a_v13_reset_completion_v2_cpu_v1.json')
    assert old_cpu['tests'] == 14 and old_cpu['passed'] is False and old_cpu['actual_wait_returncode'] == 1
    assert cpu14['tests'] == 14 and cpu14['passed'] is True and cpu14['actual_wait_returncode'] == 0
    assert cpu18['tests'] == 18 and cpu18['passed'] is True and cpu18['actual_wait_returncode'] == 0
    assert sha(Path('/tmp/test_mr3_p2a_v13_reset_completion_failed_fixture_v1.py')) == old_cpu['test_source']['sha256']
    assert sha(Path('/tmp/test_mr3_p2a_v13_reset_completion_v1.py')) == cpu14['test_source']['sha256']

    inputs, rows = [], []

    def add(path, name, group, scope):
        p = Path(path)
        assert p.is_file() and not p.is_symlink()
        initial = sig(p)
        value = sha(p)
        assert sig(p) == initial
        inputs.append(p)
        rows.append({'path': name, 'bytes': initial[2], 'sha256': value, 'original_path': str(p),
                     'source_stat': initial, 'group': group, 'source_origin': 'actual_closed_file', 'scope': scope})

    for p in sorted(EVIDENCE.rglob('*')):
        assert not p.is_symlink() and (p.is_file() or p.is_dir())
        if p.is_file():
            add(p, 'reset_readonly_evidence/' + p.relative_to(EVIDENCE).as_posix(), 'actual_closed_completion',
                'Actual new closed reset-only read-only evidence, including optional physical FAIL and required pooled PASS. No new native.')
    for expected in indexed:
        p = Path(expected['path'])
        scope = 'Outside-Git preparation/tool/test/CPU artifact. Preserve its original version and PASS or nonzero outcome; not a frozen Git native source.'
        if expected in index['attribution_receipts']:
            scope += ' Later exact attribution of actual conversation tool return; original independent metadata did not exist and original start/end remain unknown/null. No rerun.'
        if expected in index['derived_console_copies']:
            scope += ' Later extraction from actual prior tool return, explicitly not a contemporaneous independent console file.'
        if p.name == 'test_mr3_p2a_v13_reset_completion_failed_fixture_v1.py':
            scope += ' Preserved failing fixture bytes match the earlier failed14 CPU receipt; the named v1 test path was later corrected.'
        add(p, 'prepare_cpu_artifacts/' + p.name, 'prepare_cpu_artifacts', scope)
    add(index_path, 'prepare_cpu_artifacts/' + index_path.name, 'prepare_cpu_artifacts', index['scope'])
    for suffix in ('accounting_root_v2.json', 'final_absence_v2.json', 'outer_wait_v2.json',
                   'root_actual_tool_waits_v2.json', 'root_wait_observation_v2.json', 'inventory_v1.json'):
        p = Path('/tmp/mr3_p2a_v13_reset_completion_' + suffix)
        add(p, 'external_receipts/' + p.name, 'actual_wait_accounting_inventory',
            'Original actual closure/wait/observed-root-accounting receipt or original9pending static inventory; no unknown end or missing returncode reconstructed.')
    add(coverage, 'external_receipts/' + coverage.name, 'optional_coverage_closed_review', coverage_value['scope'])
    add(OUT / 'original_raw_reference.json', 'original_raw_reference.json', 'original_raw_reference', reference['scope'])
    add(OUT / 'checks/postclose_source_absence_proof.json', 'archive_checks/postclose_source_absence_proof.json',
        'postclose_static_proof', proof['scope'])
    assert len({r['path'] for r in rows}) == len(rows)
    inventory = {'schema': 'mr3-reset-completion-packet-input-inventory-v1', 'freeze': FREEZE,
                 'file_count': len(rows), 'raw_bytes': sum(r['bytes'] for r in rows),
                 'file_counts_by_group': dict(Counter(r['group'] for r in rows)), 'files': rows,
                 'scope': 'Only closed reset read-only completion scope; no original5.53GB raw duplication or future collector/deadline/PPO drafts.'}
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
                    assert sig(p) == row['source_stat'] and sha(p) == row['sha256']
    expected, seen = {r['path']: r for r in rows}, set()
    with tarfile.open(archive_path, 'r:gz') as archive:
        for member in archive:
            assert member.isfile() and member.name in expected and member.name not in seen
            seen.add(member.name)
            size, value = 0, hashlib.sha256()
            with archive.extractfile(member) as source:
                for block in iter(lambda: source.read(1024 * 1024), b''):
                    size += len(block)
                    value.update(block)
            assert size == expected[member.name]['bytes'] and value.hexdigest() == expected[member.name]['sha256']
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
            p = OUT / ('closed.tar.gz.part%04d' % index)
            with p.open('xb') as target:
                target.write(block)
            assert p.stat().st_size <= 49_000_000
            parts.append({'path': p.name, 'bytes': len(block), 'sha256': sha(p)})
    combined = hashlib.sha256()
    for p in parts:
        with (OUT / p['path']).open('rb') as source:
            for block in iter(lambda: source.read(1024 * 1024), b''):
                combined.update(block)
    assert combined.hexdigest() == sha(archive_path)
    for p, row in zip(inputs, rows):
        assert sig(p) == row['source_stat'] and sha(p) == row['sha256']
    assert sha(Path(reference['original_manifest']['path'])) == reference['original_manifest']['sha256']
    for row in proof['postclose_source_bindings_actual_sha_verified']:
        p = ROOT / row['path']
        assert sig(p) == row['observed_stat'] and sha(p) == row['sha256']
    for row in proof['postclose_elf_bindings_actual_sha_verified']:
        p = Path(row['path']).resolve(strict=True)
        assert str(p) == row['resolved_path'] and sig(p) == row['observed_stat'] and sha(p) == row['sha256']
    assert subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip() == FREEZE
    assert subprocess.check_output(['git', 'rev-parse', 'origin/main'], cwd=ROOT, text=True).strip() == FREEZE
    assert not subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT, text=True)
    gross = Decimal(observation['observed_wall_monotonic_ns'] - outer['started_wall_monotonic_ns']) / Decimal(10**9)
    assert gross == Decimal(account['gross_through_post_final_wait_observation_seconds']) == Decimal('201.694081283')
    assert gross + Decimal(account['complete_observation_tool_wall_seconds']) == Decimal(account['charged_wall_seconds']) == Decimal('201.941336859')
    assert Decimal(account['prior_used_wall_seconds']) + Decimal(account['charged_wall_seconds']) == Decimal(account['cumulative_used_wall_seconds']) == Decimal('23877.5745780506018')
    assert Decimal(account['cumulative_used_wall_seconds']) + Decimal(account['remaining_wall_seconds']) == Decimal('30000')
    assert account['remaining_wall_seconds'] == '6122.4254219493982' and account['within_allocation'] is True
    note = {'schema': 'mr3-reset-completion-archive-accounting-note-v1', 'freeze': FREEZE,
            'original_root_accounting': account, 'formula': '(4110612730319366 - 4110411036238083) / 1e9 + 0.247255576',
            'scope': 'Original root conservative charge includes actual outer/final waits and deliberately adds whole observation-tool wall. Unknown end/start fields in prepare attributions remain unknown. Archive CPU does not add native engineering charge.'}
    save(OUT / 'accounting.json', note)
    direct = [{'path': str(p.relative_to(OUT)), 'bytes': p.stat().st_size, 'sha256': sha(p)}
              for p in (Path(__file__), OUT / 'inventory_draft.json', OUT / 'accounting.json', OUT / 'original_raw_reference.json')]
    result = {'schema': 'mr3-v13-closed-reset-readonly-completion-packet-v2', 'freeze': FREEZE,
        'file_count': len(rows), 'raw_bytes': inventory['raw_bytes'], 'file_counts_by_group': inventory['file_counts_by_group'],
        'files': rows, 'parts': parts, 'direct_files': direct,
        'archive_bytes': archive_path.stat().st_size, 'archive_sha256': sha(archive_path),
        'all_tar_members_sha_size_roundtrip_verified': True, 'gzip_eof_crc_verified': True,
        'parts_concatenation_sha_verified': True, 'all_original_input_stat_sha_stable_end_verified': True,
        'postclose279_sources_and10_elfs_stat_sha_stable_pack_end_verified': True,
        'clean_head_origin0063_pack_end_verified': True,
        'original_raw_reference': reference, 'original_raw_bytes_repacked': 0,
        'runtime_source_proof_at_prepare': plan['runtime_source_proof_at_prepare'],
        'runtime_source_proof_before': summary['runtime_source_proof_before'], 'runtime_source_proof_end': summary['runtime_source_proof_end'],
        'postclose_actual_source_and_absence_proof': {'path': 'archive_checks/postclose_source_absence_proof.json', 'source_count': 279, 'elf_count': 10, 'saved_identity_count': 548},
        'preserved_outcome': {'execution_passed': True, 'original_matrix_passed': False,
            'original_passed_roles': 26, 'new_passed_roles': ['input', 'angular', 'physics', 'closure'],
            'completed_scientific_roles': 30, 'total_required_roles': 38, 'all38_scientific_complete': False,
            'deadline_roles_unstarted': 8, 'ppo_admission': False, 'new_native_calls': 0, 'gpu_calls': 0,
            'all9_jobs_completed': actual, 'actual_command_wait_count': 7, 'actual_aggregate_count': 2,
            'optional_per_episode_physics_actual_wait_returncode': 1, 'optional_per_episode_report_passed': False,
            'mandatory_predeclared_pooled_physics_actual_wait_returncode': 0, 'mandatory_pooled_physics_passed': True,
            'actual_outer_wait_returncode': 0, 'independent_final_passed': True, 'all_saved_identities_gone': True, 'saved_identity_count': 548,
            'scope': 'Optional per-episode FAIL for missing corridors/tb3 stop coverage remains FAIL; unchanged predeclared pooled criterion PASS is distinct. Deferred custody has explicitly different synchronous-parent provenance. This closes only new reset read-only scope and never rewrites the original stage-budget FAIL, supplies deadline/PPO/95%/P2A credit, or claims continuous body safety.'},
        'cpu_history': {'initial_binding_failures_preserved': True, 'failed14_fixture_actual_wait_returncode': 1,
            'final14_cpu_actual_wait_returncode': 0, 'final18_cpu_actual_wait_returncode': 0,
            'derived_console_provenance': index['initial_console_provenance'], 'earlier12_cpu_evidence_scope': index['earlier_12_test_pass'],
            'scope': 'Prepare v1/v2 actual tool attributions are later exact conversation-return copies, not contemporaneous original files. Missing historical start/end remain null, and no absent12-test source/console snapshot is fabricated. All /tmp tools/tests are outside Git0063 native source.'},
        'accounting': note, 'restore': 'Restore original V13 raw from its separately SHA-bound original packet, then concatenate this packet parts, verify SHA/gzipCRC and all tar members against files[]. direct_files[] are needed too. Later checks/pack_actual_wait.json and actual creator tool receipt independently bind this manifest without changing it.',
        'scope': 'Closed reset-only read-only completion packet, exclusively/tmp. All original FAIL/nonzero/unknown provenance preserved. No original raw5.53GB duplication, no original bigpacket edit, no new source/ELF/Git/native/consumer or CPU test execution, and no running future collector/deadline/PPO draft included.'}
    save(OUT / 'manifest.json', result)
    archive_path.unlink()
    print(json.dumps({k: result[k] for k in ('file_count', 'raw_bytes', 'archive_bytes', 'archive_sha256', 'parts')}), flush=True)


if __name__ == '__main__':
    main()
