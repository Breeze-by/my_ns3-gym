import ast
import hashlib
import json
from pathlib import Path
ROOT=Path('/home/zhuyulab/ns3-workspace')
W=ROOT/'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl'
A=W/'report/assets/20261018_mr3_p2a0_v23_entry'
P=Path('/tmp/mr3_p2a0_v23_entry_proposal_v1')
raw=(P/'handoff_v1.json').read_bytes()
assert hashlib.sha256(raw).hexdigest()=='beaa24797911fa210db5f7f83a69a3c676ae3c3b9cdf0acd11a21e17237d0ba9'
h=json.loads(raw);assert h['source_STOP'] and h['metadata_STOP'] and not h['native_admission_granted']
assert len(h['promotion_list'])==8
for row in h['promotion_list']:
    raw=Path(row['source']).read_bytes();dest=Path(row['destination'])
    assert dest.is_relative_to(A) and not dest.exists()
    assert hashlib.sha256(raw).hexdigest()==row['sha256'] and len(raw)==row['bytes']
    if dest.suffix=='.py':ast.parse(raw)
    dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(raw);assert dest.read_bytes()==raw
plan=json.loads((A/'predeclared_plan_v23.json').read_bytes())
old=json.loads((A.parent/'20261018_mr3_p2a0_v22_ray_box/predeclared_plan_v22.json').read_bytes())
pins={r['path']:r['sha256'] for r in plan['independent_source_bindings']}
assert len(pins)==198 and len(old['independent_source_bindings'])==191
assert all(pins[row['path']]==row['sha256'] for row in old['independent_source_bindings'])
for relative,digest in pins.items():assert hashlib.sha256((ROOT/relative).read_bytes()).hexdigest()==digest,relative
assert plan['readiness']['status']=='ready' and not plan['readiness']['pending_bindings']
assert plan['max_api_records']==608 and plan['max_submitted_script_decisions']==596 and plan['max_total_wall_seconds']==18000
assert plan['prior_entry_cost']['wall_seconds']==0.24578428314998746
assert [len(r['required_audit_receipts']) for r in plan['stages']]==[10,7,10,7]
assert all(r['command'][0]=='/home/zhuyulab/miniconda3/envs/ns3gym/bin/python' for r in plan['stages'])
Path('/tmp/mr3_p2a0_v23_root_source_static_v1.json').write_text(json.dumps({'schema':'mr3-v23-root-promotion-static-v1','passed':True,'exact_promoted':h['promotion_list'],'bindings':198,'old191_unchanged':True,'conda_benchmark_commands_bound':True,'all_original_stage_gates_and_budgets':True,'scope':'Source/AST/hash/plan check only; no actual new frozen preflight or native.'},indent=2)+'\n')
print('Promoted8 final files; 198 currentSHA/191 exactold/7Python AST, 34jobs/60859618000+priorcarry verified.')
