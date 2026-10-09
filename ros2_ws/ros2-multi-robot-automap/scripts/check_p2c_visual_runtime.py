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
from geometry_msgs.msg import PoseStamped, TransformStamped
from nav_msgs.msg import Odometry
from rclpy.executors import SingleThreadedExecutor
from rclpy.node import Node
from std_msgs.msg import String
from tf2_msgs.msg import TFMessage

from multi_robot_exploration import control as c
from check_p2c_gate import exploration_travel_audit, target_survey_audit, observer_heading_audit

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
    assert ast.dump(old_functions['known_search_interest'])==ast.dump(new_functions['known_search_interest'])
    reference_math=('visible_unknown_gain','known_search_interest','known_search_view','known_space_search_candidates')
    namespace=dict(vars(c));exec(compile(ast.Module(body=[old_functions[name] for name in reference_math],
        type_ignores=[]),'<frozen known-space math and candidate>','exec'),namespace)
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
        interest=c.known_search_interest(grid,.1,(0.,0.),inputs[-1])
        numeric_math_checks=0
        for cell in ((0,0),(1,1),(39,49),(79,99)):
            for radius in (.5,1.,19.9999997,20.,40.0000001):
                expected=namespace['visible_unknown_gain'](grid,cell,radius,interest,True)
                actual=c.visible_unknown_gain(grid,cell,radius,interest,True)
                assert np.array_equal(actual,expected),'changed original sorted ray cells'
                assert c.known_search_view(grid,cell,radius,interest)==namespace['known_search_view'](grid,cell,radius,interest)
                numeric_math_checks+=1
        original_rows=namespace['known_space_search_candidates'](*inputs,face_interest=True)
        current_rows=c.known_space_search_candidates(*inputs,face_interest=True)
        assert original_rows==current_rows,'integer normalization changed a candidate value'
        def publish(candidate_function, camera_views=None):
            visits=list(coordinator.initial_search_visits.values())
            options=dict(face_interest=True)
            if camera_views is not None:options['camera_views']=camera_views
            candidates=candidate_function(grid,.1,(0.,0.),'tb1',coordinator.robot_positions['tb1'],
                [*[v['position'] for v in visits],coordinator.robot_positions['tb1']],**options)
            a=max(candidates,key=lambda row:row[0])[3]
            f=c.HeadquartersControl.frontier_travel_preference(coordinator,'tb1',a,fields)
            f.update(base_utility=a.utility,battery_factor=1.,adjusted_utility=a.utility*f['factor'],
                information_gain=a.viewpoint.information_gain,frontier_group_id=a.viewpoint.group_id,
                frontier_group_size=a.viewpoint.group_size,excluded_targets=[],nominal_blocked_positions=[],
                blocked_positions=[],planned_distance_m=a.path_distance_m,initial_search_visits=visits,
                search_kind='known_space',view_yaw=a.navigation_yaw,continuation_weight=1.)
            f['adjusted_utility']*=f.get('mission_spatial_diversity',{}).get('factor',1.)
            if camera_views is not None:
                f.update(initial_search_views=camera_views,
                    search_view_model=dict(radius_m=c.INFORMATION_RADIUS_M,
                        fov_rad=c.INITIAL_SEARCH_VIEW_FOV_RAD,heading_bins=16))
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
        odom_publisher=receiver.create_publisher(Odometry,'/gateway/received/tb1/odom',10)
        tf_publisher=receiver.create_publisher(TFMessage,'/gateway/received/tb1/tf',10)
        deadline=time.monotonic()+10.
        while (odom_publisher.get_subscription_count()!=1 or tf_publisher.get_subscription_count()!=1
                ) and time.monotonic()<deadline:
            executor.spin_once(timeout_sec=.02)
        assert odom_publisher.get_subscription_count()==tf_publisher.get_subscription_count()==1
        transform=TransformStamped();transform.header.frame_id='tb1/map';transform.child_frame_id='tb1/odom'
        transform.header.stamp.sec=10;transform.transform.rotation.w=1.
        tf_publisher.publish(TFMessage(transforms=[transform]))
        odom=Odometry();odom.header.stamp.sec=10
        odom.pose.pose.position.x=2.05;odom.pose.pose.position.y=3.05;odom.pose.pose.orientation.w=1.
        odom_publisher.publish(odom)
        deadline=time.monotonic()+5.
        while not getattr(coordinator,'initial_search_views',{}) and time.monotonic()<deadline:
            executor.spin_once(timeout_sec=.02)
        views=list(coordinator.initial_search_views.values())
        assert len(views)==1 and views[0]['yaw']==0. and views[0]['pose_source_time']==views[0]['frame_source_time']==10.
        publish(c.known_space_search_candidates,views)
        deadline=time.monotonic()+5.
        while len(received)<3 and time.monotonic()<deadline:executor.spin_once(timeout_sec=.02)
        assert len(received)==3
        camera_audit=exploration_travel_audit(received[-1:],True,True,True,True,True,True)
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
        coordinator.survey_goal_pending=False;coordinator.survey_goal_handle=None
        coordinator.robot_positions['tb1']=(2.05,4.05);coordinator.robot_yaws['tb1']=0.
        coordinator.target_received_source_time=9.5
        calls=action_client.send_goal_async.call_count
        assert not coordinator.restore_observer_heading()
        assert action_client.send_goal_async.call_count==calls
        deadline=time.monotonic()+5.
        while not any(e.get('event')=='coordinator_observer_heading_quiet_hold' for e in received) and time.monotonic()<deadline:
            executor.spin_once(timeout_sec=.02)
        coordinator.target_received_source_time=4.
        assert coordinator.restore_observer_heading()
        assert action_client.send_goal_async.call_count==calls+1
        deadline=time.monotonic()+5.
        while not any(e.get('kind')=='target_observation_heading' for e in received) and time.monotonic()<deadline:
            executor.spin_once(timeout_sec=.02)
        heading_events=[e for e in received if e.get('event')=='coordinator_observer_heading_quiet_hold'
            or e.get('kind')=='target_observation_heading']
        headings=observer_heading_audit(heading_events,True)
        assert headings['quiet_holds']==headings['heading_turns']==1
        result=dict(status='PASS',scope='Actual isolated ROS DDS publication, synthetic delivered grid/pose; no task or Wi-Fi claim',
            reference_commit=REFERENCE,reference_control_sha256=hashlib.sha256(old.encode()).hexdigest(),
            control_sha256=hashlib.sha256(Path(c.__file__).read_bytes()).hexdigest(),
            numeric_candidate_equality=True,candidates_compared=len(current_rows),
            independently_compiled_reference_math=list(reference_math),numeric_ray_and_view_checks=numeric_math_checks,
            frozen_expected_error=old_error,current_group_id=candidate.viewpoint.group_id,
            independent_audit=audit,mission_diversity_audit=mission_audit,
            target_survey_audit=survey_audit,synthetic_survey_action_client=True,received=received)
        result['observer_heading_audit']=headings
        result['camera_search_audit']=camera_audit
        result['actual_delivered_pose_and_tf_dds_history']=views
        args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(result,indent=2)+'\n')
        print(json.dumps({k:v for k,v in result.items() if k!='received'}))
    finally:
        executor.shutdown()
        for node in (coordinator,receiver):
            if node is not None:node.destroy_node()
        rclpy.shutdown()


if __name__=='__main__':main()
