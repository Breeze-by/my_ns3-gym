#!/usr/bin/env python3
"""Actual DDS publication of current known-space candidates; synthetic grids only."""
import argparse
import ast
import hashlib
import json
import math
from pathlib import Path
import subprocess
import time
from unittest.mock import Mock

import numpy as np
import rclpy
from geometry_msgs.msg import PoseStamped
from rclpy.executors import SingleThreadedExecutor
from rclpy.node import Node
from std_msgs.msg import String

from multi_robot_exploration import control as c
from check_p2c_gate import exploration_travel_audit, target_survey_audit

REFERENCE='89ee853151d45ae5dbe604f00ccafa8b522c7eb9'
SOURCE='ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/multi_robot_exploration/control.py'


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists():parser.error('do not overwrite runtime evidence')
    old=subprocess.check_output(['git','show',REFERENCE+':'+SOURCE],text=True)
    before=ast.parse(old);after=ast.parse(Path(c.__file__).read_text())
    functions=lambda tree:{n.name:n for n in tree.body if isinstance(n,ast.FunctionDef)}
    old_functions=functions(before);new_functions=functions(after)
    for name in ('visible_unknown_gain','known_search_interest','known_search_view'):
        assert ast.dump(old_functions[name])==ast.dump(new_functions[name])
    namespace=dict(vars(c));exec(compile(ast.Module(body=[old_functions['known_space_search_candidates']],type_ignores=[]),'<frozen known-space candidate>','exec'),namespace)
    rclpy.init(args=['--ros-args','-p','use_sim_time:=true','-p','robot_count:=1',
        '-p','enable_battery:=false','-p','enable_rally:=true','-p','auto_save_map:=false'])
    coordinator=receiver=None;executor=SingleThreadedExecutor();received=[]
    try:
        coordinator=c.HeadquartersControl();receiver=Node('p2c_visual_witness_receiver')
        for timer in coordinator.timers:timer.cancel()
        for node in (coordinator,receiver):executor.add_node(node)
        subscription=receiver.create_subscription(String,coordinator.consumed_publisher.topic_name,
            lambda message:received.append(json.loads(message.data)),10)
        deadline=time.monotonic()+10.
        while coordinator.consumed_publisher.get_subscription_count()!=1 and time.monotonic()<deadline:
            time.sleep(.02)
        assert coordinator.consumed_publisher.get_subscription_count()==1
        grid=np.zeros((80,100),dtype='<i2');grid.setflags(write=False)
        coordinator.map_data=coordinator.source_map_data=grid
        coordinator.resolution=.1;coordinator.origin=(0.,0.);coordinator.map_received_at=10.
        coordinator.now=lambda:10.;coordinator.task_state='EXPLORE'
        coordinator.robot_positions['tb1']=(2.05,3.05)
        for times in (coordinator.robot_odom_received_at,coordinator.robot_tf_received_at,coordinator.robot_map_received_at):times['tb1']=10.
        coordinator.robot_maps['tb1']=dict(data=grid,resolution=.1,origin=(0.,0.))
        mask=c.traversable_grid(grid,.1,c.PATH_CLEARANCE_M)
        fields={'tb1':c.exploration_distance_field(grid,mask,.1,(0.,0.),coordinator.robot_positions['tb1'])}
        inputs=(grid,.1,(0.,0.),'tb1',coordinator.robot_positions['tb1'],[coordinator.robot_positions['tb1']])
        original_rows=namespace['known_space_search_candidates'](*inputs,face_interest=True)
        current_rows=c.known_space_search_candidates(*inputs,face_interest=True)
        assert original_rows==current_rows,'integer normalization changed a candidate value'
        def publish(candidate_function):
            visits=list(coordinator.initial_search_visits.values())
            candidates=candidate_function(grid,.1,(0.,0.),'tb1',coordinator.robot_positions['tb1'],
                [*[v['position'] for v in visits],coordinator.robot_positions['tb1']],face_interest=True)
            a=max(candidates,key=lambda row:row[0])[3]
            f=c.HeadquartersControl.frontier_travel_preference(coordinator,'tb1',a,fields)
            f.update(base_utility=a.utility,battery_factor=1.,adjusted_utility=a.utility*f['factor'],
                information_gain=a.viewpoint.information_gain,frontier_group_id=a.viewpoint.group_id,
                frontier_group_size=a.viewpoint.group_size,excluded_targets=[],nominal_blocked_positions=[],
                blocked_positions=[],planned_distance_m=a.path_distance_m,initial_search_visits=visits,
                search_kind='known_space',view_yaw=a.navigation_yaw,continuation_weight=1.)
            f['adjusted_utility']*=f.get('mission_spatial_diversity',{}).get('factor',1.)
            if coordinator.enable_battery:
                f['required_energy']=coordinator.exploration_required_energy('tb1',a.path_distance_m,(a.x,a.y))
            f['scheduling_score']=f['adjusted_utility'];coordinator.exploration_travel_choices={'tb1':f}
            pose=PoseStamped();pose.pose.position.x=a.x;pose.pose.position.y=a.y
            pose.pose.orientation.z=math.sin(a.navigation_yaw/2.);pose.pose.orientation.w=math.cos(a.navigation_yaw/2.)
            coordinator.record_navigation_decision('tb1','initial_visual_search',pose)
            return a
        old_error=None
        try:publish(namespace['known_space_search_candidates'])
        except TypeError as error:
            old_error=str(error);assert 'int64 is not JSON serializable' in old_error
        assert old_error is not None,'frozen failure no longer reproduced'
        candidate=publish(c.known_space_search_candidates)
        deadline=time.monotonic()+5.
        while not received and time.monotonic()<deadline:executor.spin_once(timeout_sec=.02)
        assert len(received)==1 and received[0]['kind']=='initial_visual_search'
        assert type(received[0]['travel_preference']['frontier_group_id']) is int
        audit=exploration_travel_audit(received,True,True,True,True)
        coordinator.enable_battery=True
        coordinator.battery_states['tb1']=dict(mode='ACTIVE',energy=80.,capacity=100.,stamp_sec=10.,
            charge_x=2.05,charge_y=3.05,charge_radius_m=.8,charge_target_fraction=.8,
            move_cost_per_m=1.,idle_cost_per_sec=.02,return_path_factor=2.,nominal_speed_mps=.18,
            return_safety_margin=8.,return_recovery_wait_sec=30.)
        coordinator.battery_state_received_at['tb1']=10.
        coordinator.initial_search_visits={(i,0):dict(source='ap_delivered_pose_history',robot='tb1',
            position=[4.55+.5*i,3.05],observed_at_sec=9.,pose_source_time=8.5,frame_source_time=8.7) for i in range(8)}
        publish(c.known_space_search_candidates)
        deadline=time.monotonic()+5.
        while len(received)<2 and time.monotonic()<deadline:executor.spin_once(timeout_sec=.02)
        assert len(received)==2 and received[-1]['travel_preference']['mission_spatial_diversity']['visits']
        mission_audit=exploration_travel_audit(received[-1:],True,True,True,True,True)
        survey_grid=np.zeros((80,100),dtype='<i2');survey_grid[55:,:50]=-1
        survey_grid.setflags(write=False)
        coordinator.map_data=coordinator.source_map_data=survey_grid
        coordinator.robot_maps['tb1']=dict(data=survey_grid,resolution=.1,origin=(0.,0.))
        coordinator.frontier_cache=None
        coordinator.task_state='FOUND';coordinator.target=(2.05,6.55)
        coordinator.target_received_source_time=10.;coordinator.target_observing_robot='tb1'
        coordinator.battery_modes['tb1']='ACTIVE'
        # The actual DDS recorder/selector/planner run on the real node; this
        # synthetic action client does not run Nav2 or move a robot.
        action_client=Mock();action_client.server_is_ready.return_value=True
        coordinator.robot_nav_clients['tb1']=action_client
        assert coordinator.survey_target_frontiers(coordinator.robot_positions)
        assert action_client.send_goal_async.called and coordinator.target_survey_choice is None
        deadline=time.monotonic()+5.
        while not any(e.get('kind')=='target_information_survey' for e in received) and time.monotonic()<deadline:
            executor.spin_once(timeout_sec=.02)
        survey_events=[e for e in received if e.get('kind')=='target_information_survey']
        assert len(survey_events)==1
        survey_audit=target_survey_audit(survey_events,True,3.)
        result=dict(status='PASS',scope='Actual isolated ROS DDS publication, synthetic delivered grid/pose; no task or Wi-Fi claim',
            reference_commit=REFERENCE,reference_control_sha256=hashlib.sha256(old.encode()).hexdigest(),
            control_sha256=hashlib.sha256(Path(c.__file__).read_bytes()).hexdigest(),
            numeric_candidate_equality=True,candidates_compared=len(current_rows),
            frozen_expected_error=old_error,current_group_id=candidate.viewpoint.group_id,
            independent_audit=audit,mission_diversity_audit=mission_audit,
            target_survey_audit=survey_audit,synthetic_survey_action_client=True,received=received)
        args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(result,indent=2)+'\n')
        print(json.dumps({k:v for k,v in result.items() if k!='received'}))
    finally:
        executor.shutdown()
        for node in (coordinator,receiver):
            if node is not None:node.destroy_node()
        rclpy.shutdown()


if __name__=='__main__':main()
