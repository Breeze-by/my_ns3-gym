from pathlib import Path
from collections import Counter
from decimal import Decimal
import ast
import hashlib
import json
import re
import subprocess
import time

started = time.monotonic_ns()
ROOT = Path('/home/zhuyulab/ns3-workspace')
W = ROOT / 'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl'
A = W / 'report/assets/20261019_mr3_p2a_v13'
FREEZE = '0063aa233ba3008ddcc1eb09ea8068112eea3965'

def sha(p):
    h = hashlib.sha256()
    with p.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()

def read_json(p):
    return json.loads(p.read_text())

def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT)

idx = read_json(A / 'continuation_canonical_copy_index_v1.json')
assert idx['copied_files'] == 77 and idx['copied_bytes'] == 312548714
for row in idx['files']:
    p = ROOT / row['canonical']
    assert p.is_file() and not p.is_symlink()
    assert p.stat().st_size == row['bytes'] and sha(p) == row['sha256'], str(p)

packet = A / 'closed_continuation'
manifest = read_json(packet / 'manifest.json')
assert sha(packet / 'manifest.json') == 'c0ce1e52e2132408c42ca99d7e6e0661259f67abc52055d2c8729cdbb87f61ee'
assert manifest['file_count'] == 4296 and manifest['raw_bytes'] == 4343294556
assert len(manifest['parts']) == 7
h = hashlib.sha256()
size = 0
for row in manifest['parts']:
    p = packet / row['path']
    assert p.stat().st_size == row['bytes'] and sha(p) == row['sha256']
    with p.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b''):
            h.update(chunk)
            size += len(chunk)
assert size == manifest['archive_bytes'] == 300436279
assert h.hexdigest() == manifest['archive_sha256'] == '3d478529538d8307fee859667a2b33da203faef90f9c8175c79cf99a8fa99235'
assert all(manifest[k] is True for k in ['all_tar_members_sha_size_roundtrip_verified',
    'gzip_eof_crc_verified', 'parts_concatenation_sha_verified',
    'all_selected_input_stat_sha_stable_end_verified', 'selected_directory_membership_stable_end_verified',
    'verification_only_bindings_stat_sha_stable_end_verified'])
postpack = read_json(packet / 'checks/postpack_verification_v1.json')

forensics = read_json(A / 'closed_minimum_forensics/mr3_p2a_v13_minimum_forensic_small_packet_sources_v1.json')
raw = {r['original_path']: r for r in manifest['files']}
raw_refs = forensics['large_packet_raw_input_references_only_do_not_copy_into_small_packet']
for row in raw_refs:
    assert raw[row['path']]['sha256'] == row['sha256'] and raw[row['path']]['bytes'] == row['bytes']
source_refs = forensics['runtime_frozen_source_references_no_need_duplicate_large_source_pack']
for row in source_refs:
    rel = str(Path(row['path']).relative_to(ROOT))
    content = git('show', FREEZE + ':' + rel)
    assert len(content) == row['bytes'] and hashlib.sha256(content).hexdigest() == row['sha256']

receipts = A / 'continuation_receipts'
auth = read_json(receipts / 'mr3_p2a_v13_engineering_budget_acceptance_34000_v1.json')
assert 'USER_APPROVED' in json.dumps(auth)
q = read_json(receipts / 'mr3_p2a_v13_completed_38_role_qualification_v1.json')
assert q['passed'] is True and q['original_matrix_passed'] is False
assert q['freeze'] == FREEZE and q['completed_scientific_roles'] == 38
assert len(q['roles']) == len({(r['stage'], r['role']) for r in q['roles']}) == 38
assert Counter(r['stage'] for r in q['roles']) == {'interface': 11, 'terminal': 8, 'reset': 11, 'deadline': 8}
account_names = ['mr3_p2a_v13_deadline_completion_accounting_root_v2.json',
                 'mr3_p2a_v13_preparation_qualification_tail_accounting_root_v1.json',
                 'mr3_p2a_v13_ppo_minimum_accounting_root_v3.json']
used = Decimal('23877.5745780506018')
fees = []
for name in account_names:
    d = read_json(receipts / name)
    assert Decimal(d['prior_used_wall_seconds']) == used
    fee = Decimal(d['charged_wall_seconds'])
    used += fee
    assert Decimal(d['cumulative_used_wall_seconds']) == used
    assert Decimal(d['remaining_wall_seconds']) == Decimal(34000) - used
    assert d['within_allocation'] is True and d['cumulative_within_ceiling'] is True
    fees.append(str(fee))
assert used == Decimal('31596.4775930946018')
minimum_final = read_json(receipts / 'mr3_p2a_v13_ppo_minimum_final_absence_v3.json')
assert minimum_final['passed'] is False and minimum_final['execution_passed'] is False
assert minimum_final['closure_passed'] is True and minimum_final['saved_identity_count'] == 49
assert minimum_final['all_saved_identities_gone'] is True

modified = git('diff', '--name-only').decode().splitlines()
assert all(p.endswith(('.md', '.json')) for p in modified), modified
assert not git('diff', '--', str((W / 'MR3_ENV_CONTRACT.md').relative_to(ROOT)))
old_log = git('show', 'HEAD:' + str((W / 'log.md').relative_to(ROOT)))
assert (W / 'log.md').read_bytes().startswith(old_log), 'Shared log is append-only'
links = []
for rel in modified:
    if not rel.endswith('.md'):
        continue
    p = ROOT / rel
    changes = git('diff', '--unified=0', '--', rel).decode()
    new_lines = '\n'.join(line[1:] for line in changes.splitlines()
                          if line.startswith('+') and not line.startswith('+++'))
    for target in re.findall(r'\[[^\]]*\]\(([^)]+)\)', new_lines):
        target = target.strip('<>')
        if re.match(r'^[a-z]+://', target) or target.startswith('#'):
            continue
        local = target.split('#', 1)[0]
        dest = Path(local) if local.startswith('/') else p.parent / local
        assert dest.exists(), (rel, target)
        links.append({'from': rel, 'target': target})

ast_paths, json_paths = [], []
for row in idx['files']:
    p = ROOT / row['canonical']
    if p.suffix == '.py':
        ast.parse(p.read_text(), filename=str(p))
        ast_paths.append(row['canonical'])
    if p.suffix == '.json':
        read_json(p)
        json_paths.append(row['canonical'])

assert git('branch', '--show-current').decode().strip() == 'main'
out = {'schema': 'mr3-v13-continuation-root-static-review-v1',
       'scope': 'Canonical bytes/links/JSON/Python AST/account consistency only; no native, GPU, formal science consumer, raw mathematical audit rerun or production model change.',
       'passed': True, 'canonical_copy_count': len(idx['files']), 'canonical_copy_bytes': idx['copied_bytes'],
       'packet_parts': len(manifest['parts']), 'archive_bytes': size, 'archive_sha256': h.hexdigest(),
       'full_member_crc_proof_scope': 'Already completed by packer and independent creator before main restoration; this root static pass verifies copied manifest/part SHA and concatenation, without rerunning full member decompression.',
       'raw_packet_reference_count': len(raw_refs), 'frozen_git_source_reference_count': len(source_refs),
       'new_local_links': links, 'python_ast_paths': ast_paths, 'json_paths': json_paths,
       'qualification_role_count': 38, 'original_matrix_passed': False,
       'minimum_passed': False, 'minimum_closure_passed': True,
       'actual_engineering_charges': fees, 'engineering_used': str(used),
       'engineering_remaining': str(Decimal(34000)-used), 'engineering_ceiling': '34000',
       'shared_log_append_only': True, 'production_contract_changed': False,
       'modified_tracked_files': modified, 'main_head': git('rev-parse', 'HEAD').decode().strip(),
       'internal_cpu_started_monotonic_ns': started, 'internal_cpu_completed_monotonic_ns': time.monotonic_ns()}
dest = A / 'checks/continuation_copy/closed_continuation_static_review_v1.json'
assert not dest.exists()
dest.write_text(json.dumps(out, ensure_ascii=False, indent=2) + '\n')
print(json.dumps({'passed': True, 'copy_count': len(idx['files']), 'parts': len(manifest['parts']),
                  'new_local_links': len(links), 'python_ast': len(ast_paths), 'json': len(json_paths),
                  'output': str(dest), 'output_sha256': sha(dest)}))
