#!/usr/bin/env python3
"""Exact cached geometry still uses actual DDS source leases and action Futures."""
import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import types

import rclpy

from multi_robot_exploration import control as current
from check_p2c_known_fallback_runtime import case, SOURCE

REFERENCE='5be5ce8cedfbe38fcb6d8e50a35e3ae7356ecdfd'


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();assert not args.output.exists()
    assert os.environ.get('ROS_DOMAIN_ID') in ('216','217')
    fixture=Path(__file__).resolve().parent.parent/'src/multi_robot_exploration/test/fixtures/p2c_v71_known_search_fallback.json.gz'
    saved=json.load(gzip.open(fixture,'rt'))
    literal=subprocess.check_output(['rtk','proxy','git','show',REFERENCE+':'+SOURCE],text=True)
    old=types.ModuleType('p2c_frozen_camera_geometry');old.__file__=current.__file__
    old.__package__='multi_robot_exploration';sys.modules[old.__name__]=old
    exec(compile(literal,'<5be5ce8 frozen>','exec'),old.__dict__)
    current.camera_search_ray_geometry.cache_clear()
    rclpy.init(args=['--ros-args','-p','use_sim_time:=true','-p','robot_count:=2',
        '-p','enable_battery:=true','-p','enable_rally:=true','-p','auto_save_map:=false'])
    try:
        rows=[]
        for label,module in [('frozen',old),('current',current)]:
            path=args.output.with_name(args.output.stem+'_'+label+'.json')
            result=case(module,'current',saved,path)
            result['label']=label;rows.append(result)
        decisions=[next(e for e in r['private_events'] if e.get('event')=='coordinator_navigation_decision') for r in rows]
        fields=('robot','kind','requested_position','requested_yaw')
        assert all(decisions[0][k]==decisions[1][k] for k in fields)
        fields=('planned_distance_m','required_energy','information_gain','required_energy_evaluated_at_sec')
        assert all(decisions[0]['travel_preference'][k]==decisions[1]['travel_preference'][k] for k in fields)
        info=current.camera_search_ray_geometry.cache_info();assert info.hits>0
        output=dict(status='PASS',reference_commit=REFERENCE,
            reference_control_sha256=hashlib.sha256(literal.encode()).hexdigest(),
            control_sha256=hashlib.sha256(Path(current.__file__).read_bytes()).hexdigest(),
            fixture_sha256=hashlib.sha256(fixture.read_bytes()).hexdigest(),cases=rows,
            cache_info=info._asdict(),exact_dispatch_geometry_gain_budget_equal=True,
            all_owned_closed=True,scope='Actual isolated DDS and synthetic ActionServer/Future; expired source zero-action and fresh current complete-budget admission for both full versions. No Gazebo motion, native charge cycle or task causal proof.')
        args.output.write_text(json.dumps(output,indent=2)+'\n')
        print(json.dumps(dict(status='PASS',cache_info=output['cache_info'],futures=[r['ordinary_future_successes'] for r in rows])))
    finally:rclpy.shutdown()


if __name__=='__main__':main()
