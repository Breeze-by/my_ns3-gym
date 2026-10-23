"""Validate the real sealed V69 plan and the existing strict CPU attacks."""

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

from mr3_learning import reach_preparation as preparation
from mr3_learning import reach_policy_chain as policy
from mr3_learning.initial_encoder_replay import PROFILE as ACTUATION_PROFILE
from . import prepare_plan_v1 as preparing

ASSETS = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    plan_path = ASSETS / 'plan_v1.json'
    plan = preparation.load_plan(plan_path)
    if (plan.get('actuation_profile') != ACTUATION_PROFILE
            or plan.get('motion_authority_profile') != preparing.MOTION_AUTHORITY_PROFILE):
        raise ValueError('V69 plan omitted its fixed actuation profile')
    resource, inputs = preparing.verify_plan_resource(plan)
    inputs.finish()
    qualification = Path('/tmp/mr3_p2a_reach_v69_qualification.json')
    stages = {name: policy.stage_spec(plan, plan_path, qualification, name)
              for name in policy.STAGES}
    if sum(len(preparation.primitives.roles(stage)) for stage in plan['stages']) != 30:
        raise ValueError('matrix must preserve all 30 mandatory roles')
    if sum(stage['expected_episodes'] for stage in plan['stages']) != 12:
        raise ValueError('matrix must preserve all 12 episodes')
    for stage in plan['stages']:
        if preparation.argument(stage['native']['argv'], '--reach-geometry-rule') != 'cone-support-v2':
            raise ValueError('actual native command omitted the explicit geometry rule')
    for name, spec in stages.items():
        if plan['policy_stages'][name].get('actuation_profile') != ACTUATION_PROFILE:
            raise ValueError('policy registry omitted the exact actuation profile')
        if preparation.argument(spec['argv'], '--reach-geometry-rule') != 'cone-support-v2':
            raise ValueError('policy command omitted the explicit geometry rule')
    value = {'schema': 'mr3-v69-sealed-plan-cpu-check-v1', 'passed': True,
             'plan': str(plan_path), 'plan_sha256': hashlib.sha256(plan_path.read_bytes()).hexdigest(),
             'mandatory_roles': 30, 'episodes': 12,
             'engineering_resource': plan['engineering_resource'], 'numeric_user_approval_claimed': False,
             'actuation_profile': ACTUATION_PROFILE,
             'policy_stages': {name: {'argv': spec['argv'], 'condition': spec['condition']}
                               for name, spec in stages.items()},
             'seed_rule': plan.get('seed_rule'), 'start_graph_rule': plan.get('start_graph_rule'),
             'reach_geometry_rule': plan.get('reach_geometry_rule'), 'world_started': False,
             'native_or_training_credit': False, 'engineering_increment_seconds': '0'}
    with args.output.open('x') as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write('\n')
    print(json.dumps({'passed': True, 'mandatory_roles': 30, 'episodes': 12}))


if __name__ == '__main__':
    main()
