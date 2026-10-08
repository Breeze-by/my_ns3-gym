#!/usr/bin/env python3
"""Exact geometry comparison; component CPU times are not task counterfactuals."""
import argparse
import ast
import base64
from dataclasses import asdict, is_dataclass
import hashlib
import json
from pathlib import Path
import subprocess
import time
import zlib

import numpy as np

from multi_robot_exploration import control as c


def geometry(e):
    raw = np.frombuffer(zlib.decompress(base64.b64decode(e['grid'])), dtype='<i2').reshape(e['shape'])
    return dict(data=raw, resolution=e['resolution'], origin=e['origin'])


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--assignment-input', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--reference-commit', default='4de14884ff93d3c43aed22f60d4a16f4d9a3bb85')
    args = p.parse_args()
    if args.output.exists(): p.error('do not overwrite CPU evidence')
    path = 'ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/multi_robot_exploration/control.py'
    reference = subprocess.check_output(['git', 'show', args.reference_commit+':'+path], text=True)
    names = {'route_respects_known_obstacles', 'qualified_return_candidates',
             'funded_rally_replacement', 'assign_rally_poses'}
    functions = [n for n in ast.parse(reference).body if isinstance(n, ast.FunctionDef) and n.name in names]
    assert len(functions) == len(names)
    scope = dict(vars(c))
    exec(compile(ast.Module(body=functions, type_ignores=[]), '<frozen P2C v12>', 'exec'), scope)
    event = json.loads(args.assignment_input.read_text())
    g = geometry(event['planning_map'])
    maps = {name: geometry(e) for name, e in event['return_maps'].items()}
    assignment = dict(raw_grid=g['data'], resolution=g['resolution'], origin=g['origin'],
        robot_positions=event['robot_positions'], target=event['target'], objective=event['objective'],
        battery_states=event['battery_states'], observer_robot=event['observer_robot'],
        current_positions=event['current_positions'], hold_sec=event['hold_sec'], return_maps=maps)
    repair = dict(raw_grid=g['data'], resolution=g['resolution'], origin=g['origin'],
        position=event['current_positions']['tb3'], target=event['target'], state=event['battery_states']['tb3'],
        local_map=maps['tb3'], reserved=[p for n, p in event['current_positions'].items() if n != 'tb3'],
        blocked=[p for n, p in event['current_positions'].items() if n != 'tb3'],
        map_age=max(event['inputs'][k]['age_sec'] for k in ('headquarters/fused_map_snapshot', 'tb3/map_snapshot')),
        pose_age=max(event['inputs'][k]['age_sec'] for k in ('tb3/pose_state', 'tb3/frame_state')))
    fixture_path = Path(c.__file__).parents[1]/'test/fixtures/p2c_v11_endpoint_repair.json'
    fixture = json.loads(fixture_path.read_text()); x = fixture['event']; s = geometry(x['fused_map'])
    successful = dict(raw_grid=s['data'], resolution=s['resolution'], origin=s['origin'],
        position=fixture['snapshot']['robots']['tb2']['pose'], target=fixture['target'],
        state=fixture['snapshot']['robots']['tb2']['battery'], local_map=geometry(x['local_map']),
        reserved=[fixture['reserved']], blocked=[fixture['reserved']],
        map_age=max(x['inputs'][k]['age_sec'] for k in ('headquarters/fused_map_snapshot', 'tb2/map_snapshot')),
        pose_age=max(x['inputs'][k]['age_sec'] for k in ('tb2/pose_state', 'tb2/frame_state')))
    cases = dict(original_failed_assignment=('assign_rally_poses', assignment),
                 constructed_dense_negative=('funded_rally_replacement', repair),
                 constructed_v11_positive=('funded_rally_replacement', successful))
    rows = {}
    for name, (function, kwargs) in cases.items():
        timings = dict(frozen_v12=[], batch_samples=[]); answers = {}
        for repeat in range(3):
            labels = list(timings) if repeat % 2 == 0 else list(timings)[::-1]
            for label in labels:
                fn = scope[function] if label == 'frozen_v12' else getattr(c, function)
                start = time.perf_counter(); answer = fn(**kwargs)
                timings[label].append(time.perf_counter()-start); answers[label] = answer
        assert answers['frozen_v12'] == answers['batch_samples'], (name, answers)
        rows[name] = dict(exact_output_equal=True, result=answers['batch_samples'],
            timings={label: dict(raw_sec=values, median_sec=float(np.median(values))) for label, values in timings.items()})
        print(name, rows[name], flush=True)
    result = dict(status='PASS', scope='Same-process exact geometry outputs on one original assignment and two explicitly constructed repair inputs; no mission counterfactual or worst-case timing bound',
        reference_commit=args.reference_commit, reference_control_sha256=hashlib.sha256(reference.encode()).hexdigest(),
        current_control_sha256=hashlib.sha256(Path(c.__file__).read_bytes()).hexdigest(),
        assignment_input_sha256=hashlib.sha256(args.assignment_input.read_bytes()).hexdigest(),
        constructed_positive_fixture_sha256=hashlib.sha256(fixture_path.read_bytes()).hexdigest(), cases=rows)
    args.output.write_text(json.dumps(result, indent=2,
        default=lambda value: asdict(value) if is_dataclass(value) else value)+'\n')


if __name__ == '__main__': main()
