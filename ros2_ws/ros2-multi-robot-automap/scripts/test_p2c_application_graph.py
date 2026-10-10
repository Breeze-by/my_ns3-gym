"""An incomplete discovery snapshot cannot certify absence of bypasses."""
import copy
import gzip
import json
from pathlib import Path

import pytest
from check_p3c_gate import monitor_graph_audit
from p2c_native_graph import application_graph_audit, native_tf_ingress_audit


def originals():
    path=Path(__file__).resolve().parents[1]/'src/multi_robot_exploration/test/fixtures/p2c_v66_application_graphs.json.gz'
    with gzip.open(path,'rt') as stream:return json.load(stream)


def test_original_early_snapshot_remains_rejected_and_original_native_snapshot_is_complete():
    d=originals();assert d['original_strict']=='FAIL' and d['original_native_phase']=='COMPLETE'
    with pytest.raises(KeyError):monitor_graph_audit(d['early_graph'])
    with pytest.raises(AssertionError):application_graph_audit(d['early_graph'],2)
    assert application_graph_audit(d['native_graph'],2)['status']=='PASS'
    assert native_tf_ingress_audit(d['native_graph'],2,True)['status']=='PASS'


@pytest.mark.parametrize('node,direction,topic',[
    ('/gateway_metrics','publishers','/gateway/metrics'),
    ('/gateway_metrics','subscribers','/clock'),
    ('/gateway_metrics','subscribers','/gateway/fault_configuration'),
    ('/gateway_metrics','subscribers','/tb2/battery_state'),
    ('/gateway_metrics','subscribers','/tb2/collision'),
    ('/gateway_metrics','subscribers','/gateway/received/tb2/odom'),
    ('/headquarters_control','subscribers','/gateway/received/target_detection'),
    ('/headquarters_control','subscribers','/gateway/received/tb2/map'),
    ('/headquarters_control','subscribers','/gateway/received/tb2/odom'),
    ('/headquarters_control','subscribers','/gateway/received/tb2/tf'),
    ('/headquarters_control','subscribers','/gateway/received/tb2/battery_state'),
    ('/headquarters_control','publishers','/gateway/request/tb2/charge'),
    ('/headquarters_control','action_clients','/gateway/tb2/navigate_to_pose'),
    ('/merge_map','publishers','/merge_map'),
    ('/merge_map','subscribers','/gateway/received/tb2/map'),
])
def test_positive_endpoint_must_exist_with_the_correct_type(node,direction,topic):
    graph=copy.deepcopy(originals()['native_graph']);graph['nodes'][node][direction]=[row for row in graph['nodes'][node][direction] if row[0]!=topic]
    with pytest.raises(AssertionError):application_graph_audit(graph,2)


@pytest.mark.parametrize('change',['metrics_node','ap_node','merge_node','wrong_type','metrics_goal','metrics_service_client','metrics_truth','metrics_task_publisher','gui','wrong_robot_count'])
def test_missing_nodes_or_forbidden_observer_controls_still_fail(change):
    graph=copy.deepcopy(originals()['native_graph']);nodes=graph['nodes'];metrics=nodes['/gateway_metrics'];count=2
    if change=='metrics_node':del nodes['/gateway_metrics']
    if change=='ap_node':del nodes['/headquarters_control']
    if change=='merge_node':del nodes['/merge_map']
    if change=='wrong_type':metrics['publishers'][0][1]=['nav_msgs/msg/Odometry']
    if change=='metrics_goal':metrics['action_clients'].append(['/tb2/navigate_to_pose',['nav2_msgs/action/NavigateToPose']])
    if change=='metrics_service_client':metrics['clients'].append(['/tb2/change_state',['lifecycle_msgs/srv/ChangeState']])
    if change=='metrics_truth':metrics['subscribers'].append(['/gazebo/model_states',['gazebo_msgs/msg/ModelStates']])
    if change=='metrics_task_publisher':metrics['publishers'].append(['/task_state',['std_msgs/msg/String']])
    if change=='gui':nodes['/gateway_monitor']=copy.deepcopy(metrics)
    if change=='wrong_robot_count':count=3
    with pytest.raises(AssertionError):application_graph_audit(graph,count)


def test_legacy_native_capture_and_unrelated_errors_remain_distinct(monkeypatch):
    import p2c_native_graph as graph
    from multi_robot_exploration import bypass_audit
    old=originals()['native_graph'];del old['nodes']['/gateway_metrics']
    monkeypatch.setattr(bypass_audit,'graph_snapshot',lambda *a:old)
    monkeypatch.setattr(bypass_audit,'runtime_violations',lambda *a:[])
    assert graph.complete_native_graph(None,2)==old
    with pytest.raises(AssertionError):graph.complete_native_graph(None,2,True)


@pytest.mark.parametrize('existing',['native','canonical'])
def test_observer_cannot_overwrite_existing_graph_evidence(tmp_path,existing):
    import ast
    from types import SimpleNamespace
    from unittest.mock import Mock
    path=Path(__file__).with_name('observe_p3b5.py');tree=ast.parse(path.read_text())
    writer=next(n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name=='save_native_graph')
    paths={name:tmp_path/(name+'.json') for name in ('native','canonical')}
    paths[existing].write_bytes(b'original graph evidence')
    node=Mock();node.get_clock.return_value.now.return_value.nanoseconds=10**9
    namespace=dict(graph_saved=False,last={'/tb1/battery_state':{},'/tb2/battery_state':{}},node=node,
        args=SimpleNamespace(robot_count=2,native_tf_graph_output=paths['native'],application_graph_output=paths['canonical']),
        complete_native_graph=lambda *a:originals()['native_graph'],json=json)
    exec(compile(ast.Module(body=[writer],type_ignores=[]),str(path),'exec'),namespace)
    with pytest.raises(FileExistsError):namespace['save_native_graph']()
    assert paths[existing].read_bytes()==b'original graph evidence' and not namespace['graph_saved']
