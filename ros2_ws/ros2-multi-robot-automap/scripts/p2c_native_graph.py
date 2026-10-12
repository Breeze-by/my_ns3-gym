"""Read-only complete native TF graph evidence for prospective P2C originals."""


def native_tf_ingress_audit(graph,robot_count,required=False):
    if not required:return dict(status='LEGACY_RAW_INPUT',required=False)
    nodes=graph['nodes'];verified=[]
    for index in range(1,robot_count+1):
        robot=f'tb{index}';topic=f'/{robot}/battery/source_tf';battery=f'/{robot}/battery_manager'
        producer=f'/{robot}/gateway_tf_ingress'
        assert {battery,producer}<=nodes.keys(),('incomplete native graph',robot)
        subscribers={row[0] for row in nodes[battery]['subscribers']}
        assert topic in subscribers and f'/{robot}/tf' not in subscribers
        assert f'/{robot}/tf' in {row[0] for row in nodes[producer]['subscribers']}
        outputs={row[0] for row in nodes[producer]['publishers']}
        assert {topic,f'/{robot}/gateway/source_tf'}<=outputs
        consumers=[name for name,node in nodes.items() if topic in {row[0] for row in node['subscribers']}]
        assert consumers==[battery],('native TF leaked to another consumer',topic,consumers)
        verified.append(robot)
    return dict(status='PASS',required=True,robot_local_filtered_tf=verified,
        ap_native_tf_consumers=0,source_time_renewal=False)


def application_graph_audit(graph,robot_count):
    """Require positive application endpoints as well as the old bypass veto."""
    from check_p3c_gate import monitor_graph_audit
    assert '/gateway_metrics' in graph['nodes'],'incomplete application graph: metrics node'
    monitor_graph_audit(graph)
    nodes=graph['nodes']
    def require(name,direction,expected):
        assert name in nodes,('incomplete application graph',name)
        endpoints=dict(nodes[name][direction])
        assert all(endpoints.get(topic)==[kind] for topic,kind in expected.items()),(
            'incomplete application endpoints',name,direction)
    require('/gateway_metrics','publishers',{'/gateway/metrics':'std_msgs/msg/String'})
    require('/gateway_metrics','subscribers',{
        '/clock':'rosgraph_msgs/msg/Clock','/task_state':'std_msgs/msg/String',
        '/robot_failure':'std_msgs/msg/String','/gateway/fault_configuration':'std_msgs/msg/String',
        **{f'/tb{i}/battery_state':'std_msgs/msg/String' for i in range(1,robot_count+1)},
        **{f'/tb{i}/collision':'gazebo_msgs/msg/ContactsState' for i in range(1,robot_count+1)},
        **{f'/gateway/received/tb{i}/odom':'nav_msgs/msg/Odometry' for i in range(1,robot_count+1)}})
    require('/headquarters_control','subscribers',{
        '/clock':'rosgraph_msgs/msg/Clock','/merge_map':'nav_msgs/msg/OccupancyGrid',
        '/gateway/received/target_detection':'std_msgs/msg/String',
        '/gateway/received/target_observation':'std_msgs/msg/String',
        '/gateway/received/battery_failure':'std_msgs/msg/String',
        **{f'/gateway/received/tb{i}/{suffix}':kind for i in range(1,robot_count+1)
            for suffix,kind in (('odom','nav_msgs/msg/Odometry'),('map','nav_msgs/msg/OccupancyGrid'),
                                ('tf','tf2_msgs/msg/TFMessage'),('battery_state','std_msgs/msg/String'))}})
    require('/headquarters_control','publishers',{
        '/gateway/consumed':'std_msgs/msg/String','/task_state':'std_msgs/msg/String',
        **{f'/gateway/request/tb{i}/charge':'std_msgs/msg/String' for i in range(1,robot_count+1)}})
    require('/headquarters_control','action_clients',{
        f'/gateway/tb{i}/navigate_to_pose':'nav2_msgs/action/NavigateToPose' for i in range(1,robot_count+1)})
    require('/merge_map','publishers',{'/merge_map':'nav_msgs/msg/OccupancyGrid'})
    require('/merge_map','subscribers',{
        f'/gateway/received/tb{i}/map':'nav_msgs/msg/OccupancyGrid' for i in range(1,robot_count+1)})
    return dict(status='PASS',metrics_and_ap_endpoints_complete=True,robot_count=robot_count)


def complete_native_graph(node,robot_count,require_application=False):
    from multi_robot_exploration.bypass_audit import (
        expected_runtime_nodes,graph_snapshot,manifest_path,runtime_violations)
    from rclpy.impl.implementation_singleton import rclpy_implementation
    import json
    rules=json.loads(manifest_path().read_text())
    try:
        snapshot=graph_snapshot(node)
        assert expected_runtime_nodes(rules,robot_count)<=snapshot['nodes'].keys(),'incomplete application graph'
        native_tf_ingress_audit(snapshot,robot_count,True)
        if require_application:application_graph_audit(snapshot,robot_count)
        assert not runtime_violations(node,rules,robot_count),'forbidden bypass'
    except rclpy_implementation.NodeNameNonExistentError as error:
        # The graph may change between discovery and endpoint enumeration.
        raise AssertionError('discovery changed during native graph capture') from error
    return snapshot
