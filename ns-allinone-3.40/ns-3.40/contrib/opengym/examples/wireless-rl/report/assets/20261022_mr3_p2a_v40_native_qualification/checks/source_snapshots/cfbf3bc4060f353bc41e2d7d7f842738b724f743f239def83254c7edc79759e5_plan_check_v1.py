"""Validate the real sealed V40 plan and the existing strict CPU attacks."""

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

from mr3_learning import reach_preparation as preparation
from mr3_learning import reach_policy_chain as policy

ASSETS = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    plan_path = ASSETS / 'plan_v1.json'
    plan = preparation.load_plan(plan_path)
    qualification = Path('/tmp/mr3_p2a_reach_v40_qualification.json')
    stages = {name: policy.stage_spec(plan, plan_path, qualification, name)
              for name in policy.STAGES}
    if sum(len(preparation.primitives.roles(stage)) for stage in plan['stages']) != 30:
        raise ValueError('matrix must preserve all 30 mandatory roles')
    if sum(stage['expected_episodes'] for stage in plan['stages']) != 12:
        raise ValueError('matrix must preserve all 12 episodes')
    command = [sys.executable, '-B', '-m', 'unittest',
               'mr3_learning.tests.test_reach_qualification',
               'mr3_learning.tests.test_reach_training_admission',
               'mr3_learning.tests.test_reach_policy_chain',
               'mr3_learning.tests.test_audit_reach_ppo']
    subprocess.run(command, cwd=preparation.WORKSPACE / preparation.WIRELESS_RELATIVE, check=True)
    fixture_command = [sys.executable, '-B', '-m', 'pytest', '-q',
                       str(ASSETS / 'test_prepare_plan_v1.py')]
    subprocess.run(fixture_command, cwd=preparation.WORKSPACE / preparation.WIRELESS_RELATIVE, check=True)
    value = {'schema': 'mr3-v40-sealed-plan-cpu-check-v1', 'passed': True,
             'plan': str(plan_path), 'plan_sha256': hashlib.sha256(plan_path.read_bytes()).hexdigest(),
             'mandatory_roles': 30, 'episodes': 12,
             'policy_stages': {name: {'argv': spec['argv'], 'condition': spec['condition']}
                               for name, spec in stages.items()},
             'seed_rule': plan.get('seed_rule'), 'start_graph_rule': plan.get('start_graph_rule'),
             'unit_test_argv': command, 'plan_fixture_argv': fixture_command, 'world_started': False,
             'native_or_training_credit': False, 'engineering_increment_seconds': '0'}
    with args.output.open('x') as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write('\n')
    print(json.dumps({'passed': True, 'mandatory_roles': 30, 'episodes': 12}))


if __name__ == '__main__':
    main()
