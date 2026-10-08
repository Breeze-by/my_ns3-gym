"""Actual graph must keep native sensor routing robot-local and before faults."""
import pytest
from check_p2c_gate import native_tf_ingress_audit


def graph():
    nodes={}
    for robot in ('tb1','tb2','tb3'):
        nodes[f'/{robot}/battery_manager']=dict(subscribers=[[f'/{robot}/battery/source_tf',['tf2_msgs/msg/TFMessage']]],publishers=[])
        nodes[f'/{robot}/gateway_tf_ingress']=dict(subscribers=[[f'/{robot}/tf',['tf2_msgs/msg/TFMessage']]],
            publishers=[[f'/{robot}/battery/source_tf',['tf2_msgs/msg/TFMessage']],
                        [f'/{robot}/gateway/source_tf',['tf2_msgs/msg/TFMessage']]])
    nodes['/headquarters_control']=dict(subscribers=[],publishers=[])
    return dict(nodes=nodes)


@pytest.mark.parametrize('corruption',[None,'missing_battery_node','missing_producer_node','missing_native','raw_native','missing_source','missing_ap','ap_leak','peer_leak'])
def test_native_filtered_graph_rejects_wrong_input_and_remote_consumers(corruption):
    g=graph();nodes=g['nodes'];battery=nodes['/tb3/battery_manager'];source=nodes['/tb3/gateway_tf_ingress']
    if corruption=='missing_native':battery['subscribers']=[]
    if corruption=='raw_native':battery['subscribers'].append(['/tb3/tf',[]])
    if corruption=='missing_source':source['subscribers']=[]
    if corruption=='missing_ap':source['publishers'].pop()
    if corruption=='ap_leak':nodes['/headquarters_control']['subscribers'].append(['/tb3/battery/source_tf',[]])
    if corruption=='peer_leak':nodes['/tb1/battery_manager']['subscribers'].append(['/tb3/battery/source_tf',[]])
    if corruption=='missing_battery_node':nodes.pop('/tb3/battery_manager')
    if corruption=='missing_producer_node':nodes.pop('/tb3/gateway_tf_ingress')
    if corruption is None:
        result=native_tf_ingress_audit(g,3,True);assert result['robot_local_filtered_tf']==['tb1','tb2','tb3']
    else:
        with pytest.raises(AssertionError):native_tf_ingress_audit(g,3,True)


def test_historical_raw_native_graph_is_retained_with_its_original_scope():
    assert native_tf_ingress_audit({},3)['status']=='LEGACY_RAW_INPUT'
