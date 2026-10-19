#!/usr/bin/python3
"""Final static evidence and link check; no simulator or scientific replay."""
import ast
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import re
import subprocess
from urllib.parse import unquote


ROOT = Path('/home/zhuyulab/ns3-workspace')
W = ROOT/'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl'
A = Path(__file__).resolve().parent
FREEZE = '3631c788ca46e03a52f34ad48c41611761c17f1e'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text())


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    assert not args.output.exists()
    checked = []
    projection = read(A/'reader_optimization_projection_result_v2.json')
    assert projection['passed'] and projection['whole_file_inverse_equal']
    assert not projection['scientific_pass_claimed'] and not projection['native_admission']
    manifest = read(A/'reader_optimization_projection_manifest_v2.json')
    assert sha(A/'combined_reader_optimization_v2.patch') == manifest['patch_sha256']
    for module in manifest['modules']:
        assert sha(ROOT/module['relative_path']) == module['current_sha256']
    runtime_path = W/'mr3_learning/audit_reach_runtime.py'
    frozen_runtime = subprocess.check_output(
        ['git', 'show', FREEZE+':'+runtime_path.relative_to(ROOT).as_posix()], cwd=ROOT)
    def declarations(raw):
        return [ast.dump(node, include_attributes=False) for node in ast.parse(raw).body
                if isinstance(node, (ast.Assign, ast.AnnAssign))]
    assert declarations(runtime_path.read_bytes()) == declarations(frozen_runtime)
    for name in ('combined_reader_cpu_attempt_v1', 'combined_projection_cpu_attempt_v2',
                 'bounded_helper_cpu_attempt_v1', 'accounting_cpu_attempt_v2'):
        directory = A/'checks'/name
        receipt = read(directory/'actual_wait.json')
        assert receipt['actual_waited'] and receipt['actual_returncode'] == 0
        assert receipt['source_unchanged'] and receipt['passed']
        for position, binding in enumerate(receipt['source_before']):
            origin = Path(binding['path'])
            assert sha(origin) == binding['sha256']
            copied = directory/'source_snapshots'/f'{position:02d}_{origin.name}'
            assert sha(copied) == binding['sha256']
        checked.append(str(directory.relative_to(W)))
    assert 'Ran 131 tests' in (A/'checks/combined_reader_cpu_attempt_v1/console.log').read_text()

    account = read(A/'engineering_accounting_v2.json')
    assert account['passed'] and account['global_wall_union_charged_once'] and account['charged_segments_disjoint']
    assert account['profile_v2_fully_contained_in_first_information_wait']
    assert Decimal(account['overlap_not_charged_twice_seconds']) == Decimal('269.000729653')
    fee = sum((Decimal(row['charged_seconds']) for row in account['charged_outer_waits']), Decimal(0))
    assert fee == Decimal(account['new_actual_engineering_seconds'])
    assert Decimal(account['prior_cumulative_seconds']) + fee == Decimal(account['cumulative_seconds'])
    assert Decimal(account['cumulative_seconds']) + Decimal(account['remaining_seconds']) == Decimal('52000')
    assert Decimal(account['remaining_seconds']) < Decimal('18000')
    assert account['pilot_decisions_remaining'] == 1870 and account['final_only_validations'] == 3
    assert not account['scientific_qualification'] and not account['new_native_runs']
    assert not account['gpu_calls']
    failure = read(A/'accounting_v1_failed_attempt/tool_failure_v1.json')
    assert failure['actual_exit_code'] == 1 and failure['actual_child_ns_wait'] is None
    assert sha(A/'generate_engineering_accounting_v1.py') == failure['source_sha256']
    assert sha(A/'accounting_v1_failed_attempt/source_snapshot.py') == failure['source_sha256']

    runtime = read(A/'closed_regressions/runtime_regression_v1/result.json')
    assert runtime['passed'] and runtime['complete_core_and_artifact_result_exact']
    assert runtime['source_unchanged'] and runtime['inputs_unchanged']
    assert runtime['source_projection_result_exact'] and not runtime['qualification_passed']
    info = read(A/'closed_regressions/information_regression_v2/result.json')
    assert info['passed'] and info['attempted_episodes'] == 1 and not info['errors']
    for name in ('runtime_regression_v1', 'information_regression_v2'):
        directory = A/'closed_regressions'/name
        outer = read(directory/'outer/actual_wait.json')
        child = read(directory/'child/actual_wait.json')
        assert outer['passed'] and outer['actual_waited'] and outer['source_unchanged']
        assert child['passed'] and child['actual_waited'] and not child['timed_out']
        assert child['signals_sent'] == []
        checked.append(str(directory.relative_to(W)))

    original = read(A.parent/'20261019_mr3_p2a_v19/closed_execution/auxiliary_closure_v1/matrix/summary.json')
    assert original['passed'] is False and original['all_submitted_children_waited']
    old_log = subprocess.check_output(['git', 'show', FREEZE+':'+(W/'log.md').relative_to(ROOT).as_posix()], cwd=ROOT)
    current_log = (W/'log.md').read_bytes()
    assert current_log.startswith(old_log), 'historical log rewritten'
    documents = [(W/'log.md', current_log[len(old_log):].decode())]
    for path in (W/'report/20261019_mr3_p2a_v19.md', W/'report/20261020_mr3_p2a_v20.md'):
        documents.append((path, path.read_text()))
    for path in (ROOT/'AGENTS.md', W/'AGENTS.md', W/'RESEARCH_PLAN.md', W/'IMPLEMENTATION_PLAN.md',
                 ROOT/'ros2_ws/ros2-multi-robot-automap/user_guide.md',
                 ROOT/'ros2_ws/ros2-multi-robot-automap/launch_commands.md'):
        line = next(line for line in path.read_text().splitlines() if line.startswith('2026-10-20'))
        documents.append((path, line))
    final_report = (W/'report/20261020_mr3_p2a_v20.md').read_text()
    assert account['cumulative_seconds'] in final_report and account['remaining_seconds'] in final_report
    for module in manifest['modules']:
        assert module['current_sha256'] in final_report
    links = []
    for path, text in documents:
        for raw in re.findall(r'\]\(([^)]+)\)', text):
            target = raw.strip('<>')
            if target.startswith(('http:', 'https:', '#', 'mailto:')):
                continue
            target = unquote(target.split('#', 1)[0])
            assert (path.parent/target).exists(), (path, target)
            links.append({'document':str(path.relative_to(ROOT)), 'target':target})
    paths = [*A.glob('*.py'), *A.parent.joinpath('20261019_mr3_p2a_v20').glob('*.py'),
             *(W/'mr3_learning').glob('audit_reach_*.py'),
             W/'mr3_learning/tests/test_reach_information_index_regression.py',
             W/'mr3_learning/tests/test_reach_runtime_index_regression.py']
    for path in paths:
        ast.parse(path.read_bytes(), filename=str(path))
    for path in [A/'engineering_accounting_v2.json', W/'report/ARCHIVE_INDEX.json',
                 A/'next_engineering_budget_proposal_v1.json', A/'next_engineering_budget_proposal_v2.json']:
        read(path)
    subprocess.run(['git', 'diff', '--check'], cwd=ROOT, check=True)
    result = {'schema':'mr3-v20-closed-preparation-static-v1', 'passed':True,
              'scope':'static source/evidence/link/accounting validation only',
              'checked_evidence_roots':checked, 'new_or_selected_links':links,
              'parsed_live_and_helper_python_files':len(paths), 'historical_log_append_only':True,
              'runtime_top_level_declarations_equal_frozen':True,
              'cumulative_engineering_seconds':account['cumulative_seconds'],
              'remaining_engineering_seconds':account['remaining_seconds'],
              'scientific_qualification':False, 'native_runs':0, 'gpu_calls':0}
    with args.output.open('x') as stream:
        json.dump(result, stream, indent=2)
        stream.write('\n')
    print(json.dumps({k:v for k,v in result.items() if k not in ('new_or_selected_links',)}))


if __name__ == '__main__':
    main()
