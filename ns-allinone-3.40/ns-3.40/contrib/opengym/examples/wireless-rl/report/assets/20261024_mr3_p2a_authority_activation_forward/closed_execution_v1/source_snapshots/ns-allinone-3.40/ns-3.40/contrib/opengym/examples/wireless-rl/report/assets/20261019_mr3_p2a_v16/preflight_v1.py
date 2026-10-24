"""Frozen source/build/reader-dispatch preflight; no simulator or GPU operation."""
from pathlib import Path
import argparse
import hashlib
import json
import sys

ROOT = Path('/home/zhuyulab/ns3-workspace')
W = ROOT/'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl'
sys.path.insert(0, str(W))
from mr3_learning import native_custody_reach, reach_preparation, reach_gates
from mr3_learning import audit_reach_preparation, audit_reach_controlled_physics
from mr3_learning import audit_reach_peer_control, audit_reach_cadence, audit_reach_ppo
from mr3_learning.reach_policy_chain import stage_spec

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--plan', required=True, type=Path)
parser.add_argument('--freeze', required=True)
parser.add_argument('--output', required=True, type=Path)
args = parser.parse_args()
plan = reach_preparation.load_plan(args.plan)
for name in plan['policy_stages']:
    stage_spec(plan,args.plan,Path('/tmp/mr3_p2a_reach_v16_qualification.json'),name)
source_proof = reach_preparation.source_check(plan, args.plan, args.freeze)
identity = native_custody_reach.verify_binding(ROOT, args.freeze, plan['custody_binding'])
_, executor = reach_preparation.load_executor()
_, control = audit_reach_controlled_physics.load_impl()
_, full = audit_reach_preparation.load_impl(args.plan)
_, peer = audit_reach_peer_control.load_impl()
_, cadence = audit_reach_cadence.load_implementation()
_, policy = audit_reach_ppo.load_impl(args.plan)
*_, native_sources = reach_gates.load_native_gates(ROOT, args.freeze, args.plan)
reach_preparation.source_check(plan, args.plan, args.freeze)
result = {'schema':'mr3-reach-preflight-v1', 'passed':True,
    'freeze':args.freeze, 'safety_contract':'mr3-reach-v1',
    'plan_sha256':reach_preparation.sha(args.plan),
    'source_proof':source_proof, 'native_gate_sources':native_sources,
    'actual_binary_binding':identity,
    'dispatch_projections':{'executor':executor,'controlled':control,'full':full,
                            'peer_control':peer,'cadence':cadence,'ppo':policy},
    'scientific_native_credit':False, 'gpu_calls':0, 'optimizer_steps':0,
    'scope':'Frozen source, actual on-disk ELF/build identity and exact reader dispatch only. Each new native role must execute on fresh same-freeze artifacts.'}
reach_preparation.dump(args.output,result)
print(json.dumps({'passed':True,'sources':len(source_proof),'output':str(args.output)}))
