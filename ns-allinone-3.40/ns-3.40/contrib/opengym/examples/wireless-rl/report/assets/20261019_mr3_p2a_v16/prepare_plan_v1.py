"""Seal current reach source/ELF identities; this script cannot launch native work."""
from pathlib import Path
import argparse
import hashlib
import json
import sys

ROOT = Path('/home/zhuyulab/ns3-workspace')
W = ROOT/'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl'
A = Path(__file__).resolve().parent
sys.path.insert(0, str(W))
from mr3_learning import native_custody_reach as custody
from mr3_learning.reach_preparation import build_plan, dump, sha

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--revision', type=int, default=5)
args = parser.parse_args()
assert args.revision >= 2


def spec(path):
    path = Path(path)
    return {'path': str(path.relative_to(ROOT)), 'sha256': sha(path)}


prior = W/'report/assets/20261019_mr3_p2a_v15/checks'
actual_wait = prior/'final_ros_build_attempt_v1/actual_wait.json'
wait = json.loads(actual_wait.read_text())
assert wait['actual_waited'] and wait['passed'] and wait['actual_returncode'] == 0 and wait['source_unchanged']
bridge = {'schema': custody.SCHEMA_BUILD_BRIDGE, 'safety_contract': custody.CONTRACT,
    'passed': True, 'scope': 'existing-v15-build-revalidated; no-new-build',
    'commands': [{'argv': wait['actual_argv'], 'returncode': wait['actual_returncode'],
                  'observed_returncode': wait['actual_returncode']}],
    'actual_wait': spec(actual_wait),
    'manifest_actual_wait': spec(prior/'static_preparation_attempt_v2/actual_wait.json'),
    'manifest_result': spec(prior/'static_preparation_attempt_v2/result.json'),
    'manifest': spec(prior/'static_preparation_attempt_v2/source_binary_manifest.json'),
    'compiler_flags_archive': spec(prior/'static_preparation_attempt_v2/actual_compile_flags.make')}
for key in ('actual_wait','manifest_actual_wait','manifest_result','manifest','compiler_flags_archive'):
    bridge[key]['path'] = str((ROOT/bridge[key]['path']).resolve())
manifest_wait = json.loads(Path(bridge['manifest_actual_wait']['path']).read_text())
manifest_result = json.loads(Path(bridge['manifest_result']['path']).read_text())
assert manifest_wait['actual_argv'][-1] == bridge['manifest_result']['path']
assert manifest_result['source_manifest']['path'] == bridge['manifest']['path']
manifest_flags = json.loads(Path(bridge['manifest']['path']).read_text())['compiler_flags']
assert bridge['compiler_flags_archive']['sha256'] == manifest_flags['sha256']
assert Path(bridge['compiler_flags_archive']['path']).read_bytes() == Path(manifest_flags['path']).read_bytes()
bridge_path = A/'native_build_evidence_bridge_v3.json'
if bridge_path.exists():
    assert json.loads(bridge_path.read_text()) == bridge
else:
    dump(bridge_path,bridge)
binding = json.loads((W/'report/assets/20261019_mr3_p2a_v13/native_custody_binding.json').read_text())
binding.update(schema=custody.SCHEMA_BINDING, safety_contract=custody.CONTRACT,
               execution_phase_protocol=custody.PROTOCOL)
for row in binding['binaries'].values():
    row.update(custody.load_implementation()[0].file_proof(row['path']))
binding['compiled_sources']['driver']['compiled_drive_feed_sha256'] = spec(
    ROOT/'ros2_ws/ros2-multi-robot-automap/src/multi_robot/include/multi_robot/mr3_drive_feed.hpp')
for fields in binding['compiled_sources'].values():
    for row in fields.values():
        row['sha256'] = sha(ROOT/row['path'])
sources = {str(ROOT/row['path']): row for row in binding['source_bindings']}
source_paths = set(custody.REQUIRED_SOURCES)
source_paths.update(str(p.relative_to(ROOT)) for p in (W/'mr3_learning').glob('*.py'))
source_paths.update(row['path'] for fields in binding['compiled_sources'].values() for row in fields.values())
source_paths.update(str(p.relative_to(ROOT)) for p in A.glob('*.py'))
for relative in source_paths:
    sources[str(ROOT/relative)] = spec(ROOT/relative)
for row in sources.values():
    path = Path(row['path']); path = path if path.is_absolute() else ROOT/path
    row['sha256'] = sha(path)
binding['source_bindings'] = sorted(sources.values(), key=lambda row: row['path'])
binding['qualification_wrappers'] = [spec(p) for p in sorted((W/'mr3_learning').glob('*.py'))
    if p.name.startswith(('audit_reach_', 'reach_')) or p.name == 'native_custody_reach.py']
binding['build_receipts'] = [spec(bridge_path), *binding['build_receipts'][1:]]
binding_path = A/f'native_custody_binding_v{args.revision}.json'
dump(binding_path, binding)
plan_path = A/f'predeclared_plan_v{args.revision}.json'
plan = build_plan(plan_path=plan_path,
    output_directory=Path('/tmp/mr3_p2a_reach_v16_matrix'),
    run_root=ROOT/'ros2_ws/ros2-multi-robot-automap/log/mr3_p2a_reach_v16',
    custody_binding=binding_path, binary_proof=bridge_path,
    preflight=Path('/tmp/mr3_p2a_reach_v16_preflight.json'),
    engineering_remaining_seconds='20403.5224069053982', run_prefix='mr3_p2a_reach_v16')
for relative in ('MR3_ENV_CONTRACT.md', 'MR3_REACH_CONTRACT.md',
    'report/assets/20261019_mr3_p2a_v14/scientific_contract_candidate_v1.md',
    'report/assets/20261019_mr3_p2a_v15/contract_acceptance_v1.json',
    'report/assets/20261019_mr3_p2a_v16/budget_acceptance_v1.json'):
    p = W/relative; plan['source_bindings'][str(p.relative_to(ROOT))] = sha(p)
plan['post_qualification'] = {
    'fresh_minimum': {'seed':41, 'decisions':16, 'wall_reservation_seconds':'1800',
        'native_wall_seconds':'1150', 'epochs':4, 'batch_size':16,
        'required':'actual eligible samples, positive optimizer changes and complete new independent audit'},
    'external_final_and_accounting_reservation_seconds':'300',
    'pilot_remaining_decisions':1870, 'pilot_remaining_wall_seconds':'2905.9547395464029',
    'final_only_development_validations':3, 'p2b_or_gateway_authorized':False,
    'no_retry_on_required_failure':True}
learner = plan['learner_python']
policy_root = ROOT/'ros2_ws/ros2-multi-robot-automap/log/mr3_ppo_reach_v16'
qualification = '/tmp/mr3_p2a_reach_v16_qualification.json'
plan['policy_stages'] = {}
for name, workers, schedule, decisions, steps, native_cap, cap, domain, port, batch in (
    ('minimum',1,'open:101',16,16,'1150','1800',180,14201,16),
    ('pilot',2,'open:101',1870,64,'2100','2905.9547395464029',182,14211,64),
    ('validation',4,'open:401,open:402,open:403',900,300,'8500','9000',186,14221,64)):
    run_id = 'mr3_p2a_reach_v16_'+name
    argv = [learner,'-m','mr3_learning.ppo','--safety-contract','mr3-reach-v1',
        '--reach-plan',str(plan_path),'--reach-qualification',qualification,
        '--mode','evaluate' if name=='validation' else 'train','--workers',str(workers),
        '--schedule',schedule,'--decisions',str(decisions),'--episode-steps',str(steps),
        '--wall-seconds',native_cap,'--seed','41','--batch-size',str(batch),'--epochs','4',
        '--device','cuda:0','--base-domain',str(domain),'--base-port',str(port),
        '--output-root',str(policy_root),'--run-id',run_id]
    if name=='validation':
        argv += ['--checkpoint',str(policy_root/'mr3_p2a_reach_v16_pilot/final.zip')]
    condition = {'requires':'matrix_qualification' if name=='minimum' else name=='pilot' and 'minimum_complete' or 'pilot_complete'}
    if name!='minimum':
        previous = 'minimum' if name=='pilot' else 'pilot'
        condition.update(previous_stage_summary=f'/tmp/mr3_p2a_reach_v16_{previous}/summary.json',
            previous_stage_outer_wait=f'/tmp/mr3_p2a_reach_v16_{previous}_wait/actual_wait.json',
            previous_stage_final_absence=f'/tmp/mr3_p2a_reach_v16_{previous}_final.json')
    plan['policy_stages'][name] = {'argv':argv, 'run_directory':str(policy_root/run_id),
        'output_directory':f'/tmp/mr3_p2a_reach_v16_{name}', 'wall_seconds':cap,
        'tail_reserve_seconds':'500',
        'condition':condition}
plan['supersedes_unexecuted_draft'] = {'path':str(A/'predeclared_plan_v1.json'),
    'sha256':sha(A/'predeclared_plan_v1.json'),
    'reason':'Complete policy-stage live custody/actual-wait/final-absence route added before source freeze or native work; original draft retained, never executed.'}
plan['supersedes_unexecuted_archive_draft'] = {'path':str(A/'predeclared_plan_v2.json'),
    'sha256':sha(A/'predeclared_plan_v2.json'),
    'reason':'Complete closed episode archive inventory and failure-receipt preservation added before any freeze/native work; original revision2 retained, never executed.'}
plan['supersedes_failed_preflight_plan'] = {'path':str(A/'predeclared_plan_v3.json'),
    'sha256':sha(A/'predeclared_plan_v3.json'),
    'freeze':'1833b8d40144e25149a9df0fd2196eaeb491e65f',
    'reason':'CPU preflight failed before any native launch: bridge declaration used relative paths although original manifest command/result recorded absolute paths. Preserve failed bridge/plan; new bridge uses exact original absolute identities, unchanged strict predicates.'}
plan['supersedes_unexecuted_build_scope_draft'] = {'path':str(A/'predeclared_plan_v4.json'),
    'sha256':sha(A/'predeclared_plan_v4.json'),
    'reason':'Read-only original evidence inspection before any new freeze/native run established the V15 ELF manifest did not inventory CMake. Bind CMake to its real build before/after and current freeze, and add the real archived/current compiler flags conjunction; never invent a missing old manifest entry.'}
from mr3_learning.reach_policy_chain import stage_spec
for name in plan['policy_stages']:
    stage_spec(plan,plan_path,Path(qualification),name)
dump(plan_path, plan)
print(json.dumps({'plan':str(plan_path), 'plan_sha256':sha(plan_path),
                  'source_bindings':len(plan['source_bindings']), 'binaries':len(plan['library_bindings'])}))
