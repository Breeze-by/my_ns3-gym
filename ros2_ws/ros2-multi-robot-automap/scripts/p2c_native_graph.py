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


def complete_native_graph(node,robot_count):
    from multi_robot_exploration.bypass_audit import (
        expected_runtime_nodes,graph_snapshot,manifest_path,runtime_violations)
    from rclpy.impl.implementation_singleton import rclpy_implementation
    import json
    rules=json.loads(manifest_path().read_text())
    try:
        snapshot=graph_snapshot(node)
        assert expected_runtime_nodes(rules,robot_count)<=snapshot['nodes'].keys(),'incomplete application graph'
        native_tf_ingress_audit(snapshot,robot_count,True)
        assert not runtime_violations(node,rules,robot_count),'forbidden bypass'
    except rclpy_implementation.NodeNameNonExistentError as error:
        # The graph may change between discovery and endpoint enumeration.
        raise AssertionError('discovery changed during native graph capture') from error
    return snapshot
