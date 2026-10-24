"""Finite real-DDS CPU queue experiment; no driver, simulator or policy runs.

An isolated synthetic publisher uses the unchanged depth-one ACK QoS. Both
subscribers match before the same 128-message burst and remain unspun until
all individual DDS acknowledgments return. The reach subscriber uses the
production storage_receipt_qos builder, not a copied candidate depth.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import time

import rclpy
from rclpy.context import Context
from rclpy.duration import Duration
from rclpy.executors import SingleThreadedExecutor
from rclpy.node import Node
from rclpy.signals import SignalHandlerOptions
from rclpy.utilities import get_rmw_implementation_identifier
from std_msgs.msg import String

from multi_robot_exploration import motion_safety

ROOT = Path('/home/zhuyulab/ns3-workspace')
PRODUCTION = ROOT/'ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/multi_robot_exploration/motion_safety.py'
SCHEMA = 'mr3-v18-ros-storage-queue-burst-v1'
DOMAIN = 222
BURST = 128
WORK_GUARD_SECONDS = 40
WALL_LIMIT_SECONDS = 45


def require(value, reason):
    if not value:
        raise ValueError(reason)


def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False)


def binding(path):
    path = Path(path).resolve()
    before = path.stat(); raw = path.read_bytes(); after = path.stat()
    fields = ('st_dev','st_ino','st_size','st_mtime_ns','st_ctime_ns')
    require(all(getattr(before,key) == getattr(after,key) for key in fields), 'source changed while read: '+str(path))
    return {'path':str(path),'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw),
            'stat':[getattr(after,key) for key in fields]}


def qos_value(qos):
    return {'history':int(qos.history),'depth':qos.depth,'reliability':int(qos.reliability),
            'durability':int(qos.durability),'deadline_ns':qos.deadline.nanoseconds,
            'lifespan_ns':qos.lifespan.nanoseconds,'liveliness':int(qos.liveliness),
            'liveliness_lease_duration_ns':qos.liveliness_lease_duration.nanoseconds,
            'avoid_ros_namespace_conventions':qos.avoid_ros_namespace_conventions}


def endpoint_value(endpoint):
    return {'node_name':endpoint.node_name,'node_namespace':endpoint.node_namespace,
            'topic_type':endpoint.topic_type,'endpoint_gid':bytes(endpoint.endpoint_gid).hex(),
            'qos':qos_value(endpoint.qos_profile)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args = parser.parse_args()
    require(not args.output.exists() and args.output.resolve().is_relative_to(Path('/tmp')),
            'exclusive new /tmp output required')
    started = time.monotonic_ns(); deadline = time.monotonic()+WORK_GUARD_SECONDS
    errors, publications, graph, cleanup = [], [], {}, []
    callbacks = {'legacy':[],'reach':[]}
    source_before, source_after, entities = [], [], {}
    context, executor, nodes = Context(), None, []
    initialized = False
    rmw, actual_domain, delayed_spin_started, burst_completed = None, None, None, None
    topic = '/mr3/cpu_storage_queue_burst_'+str(os.getpid())
    epoch = 'mr3-storage-queue-cpu-'+str(os.getpid())
    expected = {i:{'schema':'mr3-drive-target-consumed-v1','epoch':epoch,'robot':'tb1',
        'clock_ns':i*20_000_000+10_000_000,'source_clock_ns':i*20_000_000,
        'decision_sequence':i,'cmd_seq':i,'linear_x':0.0,'angular_z':0.0}
        for i in range(1,BURST+1)}

    def remaining(maximum):
        value = min(maximum,deadline-time.monotonic())
        require(value > 0, 'finite ROS CPU work wall guard expired')
        return value

    def receive(arm, node, message):
        row = {'callback_wall_monotonic_ns':time.monotonic_ns(),
               'callback_ros_clock_ns':node.get_clock().now().nanoseconds,'raw_json':message.data}
        try:
            payload = json.loads(message.data)
            require(type(payload) is dict and set(payload) == set(expected[1]), 'callback ACK fields differ')
            sequence = payload['decision_sequence']
            require(type(sequence) is int and sequence in expected
                    and type(payload['cmd_seq']) is int and type(payload['clock_ns']) is int
                    and type(payload['source_clock_ns']) is int
                    and canonical(payload) == canonical(expected[sequence]), 'callback payload differs from the actual published synthetic ACK')
            row.update(id=sequence,message=payload,valid=True)
        except (ValueError,KeyError,TypeError) as error:
            row.update(valid=False,error=str(error)); errors.append(arm+' callback: '+str(error))
        callbacks[arm].append(row)

    try:
        require(Path(motion_safety.__file__).resolve() == PRODUCTION, 'production QoS builder loaded from another source')
        source_paths = [Path(__file__).resolve(),PRODUCTION,Path(rclpy.__file__).resolve(),
            Path(sys.modules['rclpy.publisher'].__file__).resolve(),
            Path(sys.modules['rclpy.node'].__file__).resolve(),
            Path(sys.modules['rclpy.qos'].__file__).resolve()]
        source_before = [binding(path) for path in source_paths]
        rclpy.init(context=context,domain_id=DOMAIN,signal_handler_options=SignalHandlerOptions.NO)
        initialized = True; rmw = get_rmw_implementation_identifier()
        actual_domain = context.get_domain_id()
        require(actual_domain == DOMAIN, 'actual ROS context is not isolated on domain222')
        publisher_node = Node('mr3_storage_queue_cpu_publisher',context=context)
        nodes.append(publisher_node)
        publisher = publisher_node.create_publisher(String,topic,motion_safety.storage_receipt_qos(False))
        entities['publisher'] = {'node':publisher_node.get_fully_qualified_name(),
                                 'topic':publisher.topic_name,'qos':qos_value(publisher.qos_profile)}
        for arm, enabled in (('legacy',False),('reach',True)):
            node = Node('mr3_storage_queue_cpu_'+arm,context=context); nodes.append(node)
            subscription = node.create_subscription(String,topic,
                lambda message, arm=arm, node=node:receive(arm,node,message),
                motion_safety.storage_receipt_qos(enabled))
            entities[arm] = {'node':node.get_fully_qualified_name(),
                             'topic':subscription.topic_name,'qos':qos_value(subscription.qos_profile)}
        executor = SingleThreadedExecutor(context=context)
        for node in nodes:
            executor.add_node(node)
        discovery_deadline = min(deadline,time.monotonic()+8)
        while True:
            publishers = publisher_node.get_publishers_info_by_topic(topic)
            subscribers = publisher_node.get_subscriptions_info_by_topic(topic)
            if publisher.get_subscription_count() == 2 and len(publishers) == 1 and len(subscribers) == 2:
                graph['matched_wall_monotonic_ns'] = time.monotonic_ns()
                graph['publishers'] = [endpoint_value(row) for row in publishers]
                graph['subscribers'] = [endpoint_value(row) for row in subscribers]
                require({row.node_name for row in publishers} == {'mr3_storage_queue_cpu_publisher'}
                        and {row.node_name for row in subscribers} == {'mr3_storage_queue_cpu_legacy','mr3_storage_queue_cpu_reach'}
                        and all(row.topic_type == 'std_msgs/msg/String' for row in [*publishers,*subscribers]),
                        'actual graph contains an unexpected endpoint')
                break
            require(time.monotonic() < discovery_deadline,'finite actual DDS graph matching guard expired')
            time.sleep(min(.01,remaining(.01)))
        require(all(not rows for rows in callbacks.values()), 'subscriber was spun before the delayed burst')
        for sequence,payload in expected.items():
            remaining(.25)
            row = {'id':sequence,'message':payload,'raw_json':canonical(payload),
                   'publish_started_wall_monotonic_ns':time.monotonic_ns(),
                   'matched_subscriptions':publisher.get_subscription_count()}
            publications.append(row)
            require(row['matched_subscriptions'] == 2,'actual subscriber matching changed during burst')
            publisher.publish(String(data=row['raw_json']))
            row['publish_completed_wall_monotonic_ns'] = time.monotonic_ns()
            row['wait_for_all_acked_started_wall_monotonic_ns'] = time.monotonic_ns()
            timeout_ns = int(remaining(.25)*1_000_000_000)
            row['ack_timeout_ns'] = timeout_ns
            row['all_acked'] = publisher.wait_for_all_acked(Duration(nanoseconds=timeout_ns))
            row['wait_for_all_acked_completed_wall_monotonic_ns'] = time.monotonic_ns()
            require(row['all_acked'] is True,'real DDS acknowledgment did not complete for synthetic ACK '+str(sequence))
        burst_completed = time.monotonic_ns()
        require(all(not rows for rows in callbacks.values()), 'callbacks ran before intentional delayed spin')
        delayed_spin_started = time.monotonic_ns()
        drain_deadline = min(deadline,time.monotonic()+4)
        quiet_since = None
        while time.monotonic() < drain_deadline:
            executor.spin_once(timeout_sec=remaining(.02))
            if len(callbacks['reach']) >= BURST and callbacks['legacy']:
                quiet_since = quiet_since or time.monotonic()
                if time.monotonic()-quiet_since >= .25:
                    break
        identifiers = {arm:[row.get('id') for row in rows] for arm,rows in callbacks.items()}
        require(identifiers['reach'] == list(range(1,BURST+1)), 'reach queue did not deliver all128 exactly once in order')
        require(0 < len(identifiers['legacy']) < BURST and identifiers['legacy'][-1] == BURST
                and len(set(identifiers['legacy'])) == len(identifiers['legacy'])
                and identifiers['legacy'] == sorted(identifiers['legacy']), 'depth-one observed behavior did not retain latest with fewer than128 callbacks')
        require(all(row['callback_wall_monotonic_ns'] >= delayed_spin_started for rows in callbacks.values() for row in rows),
                'callback timestamp precedes actual delayed spin')
        graph['publishers_after'] = [endpoint_value(row) for row in publisher_node.get_publishers_info_by_topic(topic)]
        graph['subscribers_after'] = [endpoint_value(row) for row in publisher_node.get_subscriptions_info_by_topic(topic)]
        require(graph['publishers_after'] == graph['publishers']
                and sorted(graph['subscribers_after'],key=lambda r:r['node_name'])
                == sorted(graph['subscribers'],key=lambda r:r['node_name']), 'actual DDS endpoints changed during finite experiment')
    except (OSError,ValueError,KeyError,TypeError,RuntimeError) as error:
        errors.append(type(error).__name__+': '+str(error))
    finally:
        if executor is not None:
            row = {'operation':'executor_shutdown','started_monotonic_ns':time.monotonic_ns()}
            try:
                row['returned'] = executor.shutdown(timeout_sec=1.0)
                require(row['returned'] is True,'executor shutdown did not complete')
            except Exception as error:
                row['error'] = repr(error); errors.append('cleanup: '+repr(error))
            row['ended_monotonic_ns'] = time.monotonic_ns(); cleanup.append(row)
        for node in reversed(nodes):
            row = {'operation':'destroy_node','node':node.get_fully_qualified_name(),
                   'started_monotonic_ns':time.monotonic_ns()}
            try:
                node.destroy_node(); row['completed'] = True
            except Exception as error:
                row['error'] = repr(error); errors.append('cleanup: '+repr(error))
            row['ended_monotonic_ns'] = time.monotonic_ns(); cleanup.append(row)
        if initialized:
            row = {'operation':'rclpy_shutdown','started_monotonic_ns':time.monotonic_ns()}
            try:
                rclpy.shutdown(context=context)
                row['context_ok_after'] = context.ok()
                require(row['context_ok_after'] is False,'ROS context remained active after actual shutdown')
            except Exception as error:
                row['error'] = repr(error); errors.append('cleanup: '+repr(error))
            row['ended_monotonic_ns'] = time.monotonic_ns(); cleanup.append(row)
        if source_before:
            try:
                source_after = [binding(row['path']) for row in source_before]
                require(source_after == source_before,'CPU source changed during real DDS experiment')
            except (OSError,ValueError) as error:
                errors.append(str(error))
    ended = time.monotonic_ns()
    if ended-started > WALL_LIMIT_SECONDS*1_000_000_000:
        errors.append('actual finite CPU wall duration exceeded45 seconds')
    result = {'schema':SCHEMA,'passed':not errors,'scope':'bounded real ROS DDS CPU queue experiment with synthetic ACK traffic',
        'scientific_pass_claimed':False,'native_admission':False,'native_runs':0,'gpu_calls':0,'optimizer_steps':0,
        'general_losslessness_proved':False,'old_missing_ack_reconstructed':False,
        'ros_domain_id':DOMAIN,'actual_context_domain_id':actual_domain,
        'rmw_implementation_identifier':rmw,'topic':topic,'epoch':epoch,
        'production_builder':'multi_robot_exploration.motion_safety.storage_receipt_qos',
        'declared_burst_size':BURST,'work_wall_guard_seconds':WORK_GUARD_SECONDS,'wall_limit_seconds':WALL_LIMIT_SECONDS,
        'started_monotonic_ns':started,'ended_monotonic_ns':ended,'actual_internal_wall_ns':ended-started,
        'burst_completed_wall_monotonic_ns':burst_completed,'delayed_spin_started_wall_monotonic_ns':delayed_spin_started,
        'configured_actual_entities':entities,'actual_graph':graph,'publications':publications,
        'callbacks':callbacks,'received_ids':{arm:[row.get('id') for row in rows] for arm,rows in callbacks.items()},
        'cleanup':cleanup,'source_before':source_before,'source_after':source_after,
        'source_unchanged':bool(source_before) and source_before == source_after,'errors':errors,
        'limitations':'Only this matched endpoint128-message delayed-spin burst is tested. Native producer/consumer streams, arbitrary delay, physical response and fresh full scientific qualification remain unproved. The external finite runner records the real process wait.'}
    with args.output.open('x') as stream:
        json.dump(result,stream,indent=2); stream.write('\n')
    print(json.dumps({'schema':SCHEMA,'passed':result['passed'],'received_ids':result['received_ids'],
                      'actual_internal_wall_ns':ended-started,'errors':errors,'output':str(args.output)}))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
