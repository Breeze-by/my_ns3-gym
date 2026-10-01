"""Read-only physical evidence for a prospective local return navigation probe."""
import argparse, json
from pathlib import Path
import rclpy
from rclpy.node import Node
from rclpy.parameter import Parameter
from rclpy.executors import ExternalShutdownException
from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy
from std_msgs.msg import String
from gazebo_msgs.msg import ModelStates
from action_msgs.msg import GoalStatusArray
p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args()
a.output.parent.mkdir(parents=True,exist_ok=True)
rclpy.init();node=Node('p3b5_read_only_return_physics',parameter_overrides=[Parameter('use_sim_time',value=True)])
latched=QoSProfile(depth=10,reliability=ReliabilityPolicy.RELIABLE,durability=DurabilityPolicy.TRANSIENT_LOCAL)
models=QoSProfile(depth=5,reliability=ReliabilityPolicy.BEST_EFFORT)
battery={};status={};last=-1.
stream=a.output.open('a',buffering=1)
def stamp():return node.get_clock().now().nanoseconds/1e9
def state(name,msg):
    data=json.loads(msg.data);battery[name]=data
    stream.write(json.dumps({'event':'battery','observer_time':stamp(),'robot':name,'data':data})+'\n')
def action(name,msg):
    status[name]=[{'uuid':list(x.goal_info.goal_id.uuid),'status':x.status} for x in msg.status_list]
def positions(msg):
    global last
    now=stamp()
    if now-last<.1:return
    last=now
    robots={}
    for name,pose,twist in zip(msg.name,msg.pose,msg.twist):
        if name in ('tb1','tb2'):
            robots[name]={'x':pose.position.x,'y':pose.position.y,'speed':(twist.linear.x**2+twist.linear.y**2)**.5,'battery':battery.get(name),'nav2_status':status.get(name,[])}
    stream.write(json.dumps({'event':'physics','observer_time':now,'robots':robots})+'\n')
for name in ('tb1','tb2'):
    node.create_subscription(String,f'/{name}/battery_state',lambda m,n=name:state(n,m),latched)
    node.create_subscription(GoalStatusArray,f'/{name}/navigate_to_pose/_action/status',lambda m,n=name:action(n,m),latched)
node.create_subscription(ModelStates,'/gazebo/model_states',positions,models)
print('READY',flush=True)
try:rclpy.spin(node)
except (KeyboardInterrupt,ExternalShutdownException):pass
finally:
    stream.close();node.destroy_node()
    if rclpy.ok():rclpy.shutdown()
