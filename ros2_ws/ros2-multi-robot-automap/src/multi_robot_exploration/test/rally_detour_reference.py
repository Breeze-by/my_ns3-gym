"""Original CDR fixture with explicit conditional action state."""
import base64,copy,gzip,json,math
from pathlib import Path
from types import SimpleNamespace
from rclpy.serialization import deserialize_message
from nav_msgs.msg import OccupancyGrid,Odometry
from multi_robot_exploration import control as c

FIXTURE=Path(__file__).parent/'fixtures/p2c_v94_active_rally_detour.json.gz'

def fixture_node(checkpoint=235.):
    saved=json.load(gzip.open(FIXTURE,'rt'));snap=next(s for s in saved['snapshots'] if s['time']==checkpoint)
    names=saved['names'];now=saved['start']+checkpoint;events=[];logs=[];canceled=[]
    def message(row,kind):return deserialize_message(base64.b64decode(row['cdr']['cdr']),kind)
    def geometry(row):
        m=message(row,OccupancyGrid)
        return dict(data=c.immutable_grid_snapshot(m.data,(m.info.height,m.info.width)),resolution=m.info.resolution,origin=(m.info.origin.position.x,m.info.origin.position.y))
    raw=geometry(snap['captured']['/merge_map']);maps={n:geometry(snap['captured'][f'/{n}/map']) for n in names};positions={}
    for n in names:
        m=message(snap['captured'][f'/{n}/odom'],Odometry);tf=snap['transforms'][n];x,y=m.pose.pose.position.x,m.pose.pose.position.y;tx,ty=tf['translation'];yaw=tf['yaw']
        positions[n]=(tx+math.cos(yaw)*x-math.sin(yaw)*y,ty+math.sin(yaw)*x+math.cos(yaw)*y)
    planning,cells=c.planning_grid_without_self_returns(raw['data'],raw['resolution'],raw['origin'],positions)
    assignments=snap['rally_assignment_record']['data'];targets={n:c.RallyPose(**p) for n,p in assignments['poses'].items()}
    handles={n:None if n=='tb1' else SimpleNamespace(cancel_goal_async=lambda n=n:canceled.append(n)) for n in names}
    decisions=snap['last_rally_decisions'];states={n:copy.deepcopy(snap['battery'][n]['data']) for n in names}
    node=SimpleNamespace(clock=now,enable_battery=True,task_state='RALLY',shutdown_requested=False,
        map_data=planning,source_map_data=raw['data'],map_self_return_cells=cells,resolution=raw['resolution'],origin=raw['origin'],
        map_received_at=snap['captured']['/merge_map']['source_time'],robot_maps=maps,robot_positions=positions,
        robot_map_received_at={n:snap['captured'][f'/{n}/map']['source_time'] for n in names},
        robot_odom_received_at={n:snap['captured'][f'/{n}/odom']['source_time'] for n in names},
        robot_tf_received_at={n:snap['transforms'][n]['source_time'] for n in names},
        battery_states=states,battery_modes={n:s['mode'] for n,s in states.items()},battery_state_received_at={n:s['stamp_sec'] for n,s in states.items()},
        target=(assignments['target_x'],assignments['target_y']),target_received_source_time=now-.1,target_observing_robot='tb1',rally_observer_guard='tb1',
        message_freshness_timeout_sec=5.,rally_hold_sec=5.,rally_position_tolerance=.35,goal_timeout_sec=60.,rally_goal_timeout_sec=60.,
        rally_targets=targets,rally_final_targets=dict(targets),rally_dispatch_order=list(names),rally_goal_handles=handles,
        rally_goal_pending=dict.fromkeys(names,False),rally_goal_started_at={n:decisions[n]['event_time']+.1 for n in names},
        rally_yield_requested=dict.fromkeys(names,False),rally_battery_preempted=dict.fromkeys(names,False),rally_arrived={n:n=='tb1' for n in names},
        rally_yield_targets=set(),return_yield_targets={},rally_probe_targets=set(),rally_charge_requested={},rally_precharge_staging={},
        rally_leg_poses={n:c.RallyPose(*decisions[n]['requested_position'],decisions[n]['requested_yaw']) for n in names},
        rally_leg_routes={n:tuple(map(tuple,decisions[n]['outbound_map_route']['route'])) if n!='tb1' else () for n in names},
        rally_attempts=dict.fromkeys(names,0),rally_route_unavailable_since=dict.fromkeys(names,None),rally_recovery_requested=dict.fromkeys(names,False),
        rally_wait_budgets={},goal_handles=dict.fromkeys(names,None),robot_states=dict.fromkeys(names,'idle'),
        survey_goal_pending=False,survey_goal_handle=None,target_scan_handle=None,target_scan_robot=None)
    node.now=lambda:node.clock;node.participating_robots=lambda:list(names);node.input_robot_names=node.participating_robots
    node.fresh_robot_inputs=lambda:c.HeadquartersControl.fresh_robot_inputs(node)
    node.fresh_robot_poses=lambda:c.HeadquartersControl.fresh_robot_poses(node)
    node.fresh_target=lambda:c.HeadquartersControl.fresh_target(node)
    node.input_freshness_details=lambda:c.HeadquartersControl.input_freshness_details(node)
    node.get_logger=lambda:SimpleNamespace(info=logs.append,warn=logs.append)
    node.consumed_publisher=SimpleNamespace(publish=lambda msg:events.append(json.loads(msg.data)))
    node.publish_rally_assignments=lambda:None
    return node,events,canceled,saved
