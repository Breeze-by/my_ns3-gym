"""Reject forged native return predictions, map provenance and cost totals."""
import base64
import copy
import hashlib
import json
import zlib

import numpy as np
import pytest

from check_p2c_gate import return_audit
from multi_robot_exploration import control


def trace():
    grid = np.zeros((44, 44), dtype='<i2')
    grid[:35, 20] = 100
    position, home = (3.1, 1.1), (5.1, 1.1)
    distance, route = control.known_return_route(
        grid, .2, (0., 0.), position, home, .8, include_route=True)
    budget = control.return_energy_budget(distance, 1., .02, 2., .18, 8., 30., 1.,.5)
    budget.update(route=route, map_version=1, map_source='local',
                  map_source_time=10., map_age_sec=1.,
                  odom_source_time=10.9,frame_source_time=10.5,pose_age_sec=.5,frame_stamp_offset_sec=.5,
                  map_content_blake2b=hashlib.blake2b(grid.tobytes(), digest_size=16).hexdigest())
    saved = dict(shape=grid.shape, resolution=.2, origin=(0., 0.),
                 source='local', source_time=10., version=1,
                 encoding='zlib_base64_int16_le',
                 grid=base64.b64encode(zlib.compress(grid.tobytes())).decode())
    common = dict(robot='tb1', return_count=1, energy=40., sim_time=11.,
                  home=home, charge_radius_m=.8,
                  energy_model=dict(move_cost_per_m=1., idle_cost_per_sec=.02,
                      path_factor=2., nominal_speed_mps=.18, safety_margin=8., recovery_wait_sec=30.))
    predicted = budget['required_energy'] - 8.
    return [dict(common, event='return_started', position=position, budget=budget, map_evidence=saved),
            dict(common, event='return_leg_sent', route=route[:8], budget=budget, map_evidence=saved, position=position),
            dict(common, event='return_finished', sim_time=111., energy=28.,
                 outcome='charger_stopped', actual_distance_m=10., actual_elapsed_sec=100.,
                 actual_energy_spent=12., predicted_energy_spent=predicted, prediction_error=12.-predicted)]


@pytest.mark.parametrize('corruption', [None, 'distance', 'cost', 'map_digest', 'map_version',
    'stale', 'missing_finish', 'missing_start', 'duplicate_finish', 'actual_cost',
    'actual_energy', 'prediction', 'overrun', 'nan','pose_age','stale_odom','future_tf','missing_pose'])
def test_return_audit_reconstructs_originals_and_rejects_corruption(tmp_path, corruption):
    events = copy.deepcopy(trace())
    if corruption == 'distance': events[0]['budget']['path_distance_m'] = 2.
    if corruption == 'cost': events[0]['budget']['required_energy'] = 12.
    if corruption == 'map_digest': events[0]['budget']['map_content_blake2b'] = '0'*32
    if corruption == 'map_version': events[0]['map_evidence']['version'] = 2
    if corruption == 'stale': events[0]['sim_time'] = 16.
    if corruption == 'missing_finish': events.pop()
    if corruption == 'missing_start': events.pop(0)
    if corruption == 'duplicate_finish': events.append(events[-1])
    if corruption == 'actual_cost': events[-1]['actual_distance_m'] = 20.
    if corruption == 'actual_energy': events[-1]['energy'] = 29.
    if corruption == 'prediction': events[-1]['predicted_energy_spent'] += 1.
    if corruption == 'overrun': events[-1]['prediction_error'] = 1.
    if corruption == 'nan': events[-1]['actual_elapsed_sec'] = float('nan')
    if corruption == 'pose_age':events[0]['budget']['pose_age_sec']=0.
    if corruption == 'stale_odom':events[0]['budget']['odom_source_time']=8.
    if corruption == 'future_tf':events[0]['budget']['frame_source_time']=12.
    if corruption == 'missing_pose':events[0]['budget'].pop('odom_source_time')
    path = tmp_path/'safety_events.jsonl'
    path.write_text(''.join(json.dumps(dict(topic='/tb1/battery_return_audit', data=e))+'\n' for e in events))
    if corruption is None:
        result = return_audit(path,True)
        assert result['charger_returns'] == 1
        assert result['map_budget_reconstructions'] == 2
    else:
        with pytest.raises((AssertionError,KeyError)):
            return_audit(path,True)
