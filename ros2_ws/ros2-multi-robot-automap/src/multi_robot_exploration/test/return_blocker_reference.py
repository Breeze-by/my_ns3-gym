"""Conditional late v93 inputs; capture matching does not replay callbacks."""
import base64,copy,gzip,hashlib,json,math
from pathlib import Path
from types import SimpleNamespace
from rclpy.serialization import deserialize_message
from nav_msgs.msg import OccupancyGrid,Odometry
from multi_robot_exploration import control as c
from test_known_search_fallback import original_snapshot_node

PATH=Path(__file__).parent/'fixtures/p2c_v93_unfunded_return_blocker.json.gz'
assert hashlib.sha256(PATH.read_bytes()).hexdigest()=='fb755914604b5e68964c0a8171547994554cfd8192c930680f3b99d5592c28aa'
SAVED=json.load(gzip.open(PATH,'rt'))

def original_admit():
    text=SAVED['functions']['admit_exploration_return_yield']
    assert hashlib.sha256(text.encode()).hexdigest()==SAVED['function_sha256']['admit_exploration_return_yield']
    ns=dict(vars(c));exec(compile(text,'<8fe24f8 original return-yield admission>','exec'),ns)
    return ns['admit_exploration_return_yield']

def snapshot_node(index=0):
    snap=copy.deepcopy(SAVED['snapshots'][index]);e=copy.deepcopy(SAVED['original_diagnostic'])
    h,requests,events,sent=original_snapshot_node(dict(event=e));h.clock=SAVED['start']+snap['time'];names=list(h.robot_positions)
    h.input_robot_names=lambda:list(h.robot_positions);h.participating_robots=h.input_robot_names
    def message(row,kind):return deserialize_message(base64.b64decode(row['cdr']['cdr']),kind)
    m=message(snap['captured']['/merge_map'],OccupancyGrid);h.source_map_data=c.immutable_grid_snapshot(m.data,(m.info.height,m.info.width));h.map_data=h.source_map_data
    h.resolution=m.info.resolution;h.origin=(m.info.origin.position.x,m.info.origin.position.y);h.map_received_at=snap['captured']['/merge_map']['source_time'];h.frontier_cache=None
    h.robot_maps={};h.robot_yaws={};h.robot_positions={}
    for name in names:
        m=message(snap['captured'][f'/{name}/map'],OccupancyGrid)
        h.robot_maps[name]=dict(data=c.immutable_grid_snapshot(m.data,(m.info.height,m.info.width)),resolution=m.info.resolution,origin=(m.info.origin.position.x,m.info.origin.position.y))
        m=message(snap['captured'][f'/{name}/odom'],Odometry);tf=snap['transforms'][name];tx,ty=tf['translation'];yaw=tf['yaw'];x,y=m.pose.pose.position.x,m.pose.pose.position.y
        h.robot_positions[name]=(tx+math.cos(yaw)*x-math.sin(yaw)*y,ty+math.sin(yaw)*x+math.cos(yaw)*y)
        h.robot_yaws[name]=math.atan2(math.sin(c.quaternion_yaw(m.pose.pose.orientation)+yaw),math.cos(c.quaternion_yaw(m.pose.pose.orientation)+yaw))
        h.robot_odom_received_at[name]=snap['captured'][f'/{name}/odom']['source_time'];h.robot_tf_received_at[name]=tf['source_time'];h.robot_map_received_at[name]=snap['captured'][f'/{name}/map']['source_time']
        h.battery_states[name]=snap['battery'][name]['data'];h.battery_state_received_at[name]=h.battery_states[name]['stamp_sec']
    h.robot_states=dict.fromkeys(names,'idle');h.battery_modes={n:s['mode'] for n,s in h.battery_states.items()}
    h.rally_charge_requested={};h.goal_routes={};h.goal_targets=dict.fromkeys(names,None);h.goal_handles=dict.fromkeys(names,None)
    h.exploration_return_yields={};h.pending_exploration_return_yield=None;h.successful_exploration_legs=dict(tb1=4,tb2=5,tb3=5);h.initial_search_next=dict(tb1=False,tb2=False,tb3=True)
    h.active_exclusions=lambda:[];h.initial_search_goals=dict.fromkeys(names,False)
    h.charge_request_publishers={n:SimpleNamespace(publish=lambda msg,n=n:requests.append((n,json.loads(msg.data)))) for n in names}
    h.message_freshness_timeout_sec=5.;h.shutdown_requested=False
    h.fresh_robot_poses=lambda:c.HeadquartersControl.fresh_robot_poses(h);h.fresh_robot_inputs=lambda:c.HeadquartersControl.fresh_robot_inputs(h)
    h.exploration_charge_budgets={};h.get_logger=lambda:SimpleNamespace(info=lambda _:None,warn=lambda _:None)
    assert h.fresh_robot_inputs()
    assert c.HeadquartersControl.prepare_exploration_return(h,'tb1') and h.pending_exploration_return_yield['robot']=='tb2'
    return h,requests,events,sent
