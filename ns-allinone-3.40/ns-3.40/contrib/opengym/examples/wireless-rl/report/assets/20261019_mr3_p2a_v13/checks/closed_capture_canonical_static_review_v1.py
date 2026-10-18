import ast
import hashlib
import json
import re
import subprocess
import time
from decimal import Decimal as D
from pathlib import Path

ROOT = Path('/home/zhuyulab/ns3-workspace')
W = ROOT / 'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl'
A = W / 'report/assets/20261019_mr3_p2a_v13'
started = time.monotonic_ns()


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


copies = json.loads((A / 'closed_capture_canonical_copy_index_v1.json').read_text())
for row in copies['files']:
    p = ROOT / row['canonical_path']
    assert p.stat().st_size == row['bytes'] and sha(p) == row['sha256'], p

packets = []
for name, members, raw, count in [('closed_evidence', 5432, 5534884383, 8),
                                  ('reset_readonly_completion', 56, 2482835, 1)]:
    p = A / name
    m = json.loads((p / 'manifest.json').read_text())
    assert (m['file_count'], m['raw_bytes'], len(m['parts'])) == (members, raw, count)
    digest = hashlib.sha256()
    size = 0
    for part in m['parts']:
        q = p / part['path']
        assert q.stat().st_size == part['bytes'] and sha(q) == part['sha256']
        assert q.stat().st_size < 50_000_000
        with q.open('rb') as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b''):
                digest.update(chunk)
                size += len(chunk)
    assert digest.hexdigest() == m['archive_sha256'] and size == m['archive_bytes']
    packets.append({'path': str(p.relative_to(ROOT)), 'members': members,
                    'raw_bytes': raw, 'parts': count, 'archive_sha256': digest.hexdigest()})

proposal_path = A / 'prospective_continuation/mr3_p2a_v13_engineering_continuation_budget_proposal_v2.json'
proposal = json.loads(proposal_path.read_text())
assert sha(proposal_path) == '669c1b64305a9b25d00848a177c137cff848cb33dd2a7248fb74f80492bc4d44'
assert proposal['status'] == 'SEALED_PROPOSAL_AWAITING_USER_APPROVAL'
assert proposal['original_matrix_passed'] is False and proposal['ppo_has_started'] is False
assert proposal['completed_scientific_roles_under_new_distinct_protocol'] == 30
assert proposal['deadline_scientific_roles_unstarted'] == 8
assert sum(map(D, proposal['prospective_allocations_wall_seconds'].values())) == D('9500')
assert D('30000') - D(proposal['accounted_used_wall_seconds']) == D(proposal['accounted_remaining_wall_seconds'])
assert D('34000') - D(proposal['accounted_used_wall_seconds']) == D(proposal['proposed_available_wall_seconds'])
assert D(proposal['proposed_available_wall_seconds']) - D('9500') == D(proposal['proposed_headroom_after_allocations_wall_seconds'])
assert D(proposal['accounted_remaining_wall_seconds']) < D('9400') < D('9500')

py_count = 0
json_count = 0
for base in [A / 'closed_evidence', A / 'reset_readonly_completion', A / 'prospective_continuation']:
    for p in base.rglob('*'):
        if p.suffix == '.py':
            ast.parse(p.read_text(), filename=str(p))
            py_count += 1
        elif p.suffix == '.json':
            json.loads(p.read_text())
            json_count += 1

changed = subprocess.run(['git', 'diff', '--name-only'], cwd=ROOT, text=True,
                         capture_output=True, check=True).stdout.splitlines()
new_links = []
for name in changed:
    if not name.endswith('.md'):
        continue
    patch = subprocess.run(['git', 'diff', '--unified=0', '--', name], cwd=ROOT,
                           text=True, capture_output=True, check=True).stdout
    for line in patch.splitlines():
        if not line.startswith('+') or line.startswith('+++'):
            continue
        for value in re.findall(r'\]\(([^)]+)\)', line):
            if '://' in value or value.startswith('#'):
                continue
            value = value.split('#', 1)[0].strip('<>')
            p = Path(value) if value.startswith('/') else (ROOT / name).parent / value
            assert p.exists(), (name, value)
            new_links.append({'document': name, 'target': value})

report = (W / 'report/20261019_mr3_p2a_v13.md').read_text()
assert '原矩阵仍为FAIL' in report
assert '548' in report and '539' in report and 'physical_per_episode' in report
assert '≥9500' in report and '9400' in report
assert '历史记录，不重跑' in report and 'AWAITING_USER_APPROVAL' in report
result = {'schema': 'mr3-p2a-v13-canonical-static-review-v1', 'passed': True,
          'runtime_freeze': '0063aa233ba3008ddcc1eb09ea8068112eea3965',
          'copied_files_sha_size_verified': len(copies['files']), 'packets': packets,
          'python_ast_parsed': py_count, 'json_parsed': json_count,
          'new_local_links_verified': new_links,
          'engineering_current_approved_ceiling': '30000',
          'current_available': proposal['accounted_remaining_wall_seconds'],
          'new_34000_authorization_present': False,
          'root_future_minimum_balance_including_qualification_tail': '9500',
          'sealed_tool_minimum_balance': '9400',
          'current_balance_forbids_new_native': True,
          'forecast_only_available_if_explicit_new_approval': proposal['proposed_available_wall_seconds'],
          'started_wall_monotonic_ns': started,
          'ended_wall_monotonic_ns': time.monotonic_ns(),
          'scope': 'Static copy/hash/arithmetic/link/AST/JSON review only. Existing archive CRC/member proofs are preserved; no scientific consumer, native, PPO, GPU, source clean-runtime check or new approval was executed or invented.'}
out = A / 'checks/closed_capture_canonical_static_review_v1.json'
out.write_text(json.dumps(result, indent=2, ensure_ascii=False) + '\n')
print(json.dumps({'passed': True, 'copied_files': len(copies['files']),
                  'new_local_links': len(new_links), 'python_ast': py_count,
                  'json': json_count, 'output': str(out), 'sha256': sha(out)}))
