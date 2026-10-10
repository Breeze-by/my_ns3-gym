"""One initial policy top-up needs actual work and fresh complete safety inputs."""
import copy
import gzip
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from multi_robot_exploration import control as c
from p2c_initial_replenishment import initial_replenishment_audit
from p2c_return_preparation import decode_grid
from test_exploration_charging import assignment, opportunity_node


FIXTURE = Path(__file__).parent/'fixtures/p2c_v70_initial_replenishment_inputs.json.gz'
assert hashlib.sha256(FIXTURE.read_bytes()).hexdigest() == '1b82c2264b2f1ba7879ef4c06a7fdf019e68e0ac1eca0114c93c8102a8128bce'
REFERENCE = json.load(gzip.open(FIXTURE, 'rt'))


def old_budget():
    source = REFERENCE['original_budget']
    assert hashlib.sha256(source.encode()).hexdigest() == REFERENCE['original_budget_sha256']
    namespace = dict(vars(c))
    exec(compile(source, '<a383cda original budget>', 'exec'), namespace)
    return namespace['exploration_charge_budget']


def conditional_node(saved):
    event = copy.deepcopy(saved['event'])
    planning = event['planning_map']
    names = list(event['robot_positions'])
    states = event['battery_states']
    stamps = lambda kind: {name:event['inputs'][name+'/'+kind]['source_time'] for name in names}
    node = SimpleNamespace(now=lambda:event['event_time'], enable_rally=True,
        task_state=event['task_phase'], map_data=decode_grid(planning),
        resolution=planning['resolution'], origin=planning['origin'], map_received_at=planning['source_time'],
        robot_positions=event['robot_positions'], battery_states=states,
        battery_modes={name:state['mode'] for name,state in states.items()},
        robot_maps={name:dict(data=decode_grid(row),resolution=row['resolution'],origin=row['origin'])
                    for name,row in event['return_maps'].items()},
        robot_map_received_at=stamps('map_snapshot'), robot_odom_received_at=stamps('pose_state'),
        robot_tf_received_at=stamps('frame_state'), successful_exploration_legs={event['robot']:saved['ordinary_successes']},
        opportunity_charge_evidence={})
    preference = event['travel_preference']
    goal = assignment(*preference['target'], distance=preference['planned_distance_m'])
    return node, event['robot'], goal


@pytest.mark.parametrize('index', range(len(REFERENCE['snapshots'])))
def test_original_near_home_snapshots_have_an_explicit_separate_policy_threshold(index):
    node,name,goal = conditional_node(REFERENCE['snapshots'][index])
    before = old_budget()(node,name,goal,True)
    after = c.HeadquartersControl.exploration_charge_budget(node,name,goal,True)
    assert before is None and after is not None
    evidence = node.initial_replenishment_evidence[name]
    assert after[1] == node.battery_states[name]['capacity']*node.battery_states[name]['charge_target_fraction']
    assert evidence['trip_required_energy'] < after[0] < after[1]
    assert evidence['trip_required_energy'] == pytest.approx(c.HeadquartersControl.exploration_required_energy(
        node,name,goal.path_distance_m,(goal.x,goal.y)))
    node.battery_states[name]['charge_count'] = 1
    assert c.HeadquartersControl.exploration_charge_budget(node,name,goal,True) == old_budget()(node,name,goal,True)
    assert not node.initial_replenishment_evidence


def node():
    h,requests,events,sent = opportunity_node()
    h.enable_rally = True
    h.message_freshness_timeout_sec = 5.
    h.clock = 10.
    h.now = lambda:h.clock
    h.map_self_return_cells = {}
    h.opportunity_charge_evidence = {}
    for name,state in h.battery_states.items():
        state.update(mode='ACTIVE',stamp_sec=10.,charge_count=0,return_count=0,charge_radius_m=.8)
    h.battery_states['tb1']['energy'] = 40.
    h.input_freshness_details = lambda:c.HeadquartersControl.input_freshness_details(h)
    h.fresh_robot_inputs = lambda:all(s['source_time'] is not None and 0<=h.now()-s['source_time']<=s['ttl_sec']
        for s in h.input_freshness_details().values())
    return h,requests,events,sent


def test_policy_request_uses_original_clear_return_path_and_distinct_trip_cost():
    h,requests,events,sent = node()
    assert c.HeadquartersControl.request_exploration_charge(h,[('tb1',assignment(3.5,3.,distance=.5))])
    assert not sent and len(requests)==len(events)==1
    assert requests[0][1]['reason']=='initial_near_home_replenishment'
    assert requests[0][1]['required_energy']==80.
    assert events[0]['initial_replenishment']['trip_required_energy']<40.
    assert events[0]['return_preparation']['clearance_m']==1.8
    h.battery_states['tb1']['charge_count']=1
    h.rally_charge_requested.clear()
    assert not c.HeadquartersControl.request_exploration_charge(h,[('tb1',assignment(3.5,3.,distance=.5))])
    assert len(requests)==1


@pytest.mark.parametrize('reason',('spawn','no_work','prior_charge','bool_count','missing_count',
    'mapping_only','far','full','capacity','unknown_contact','stale','live_peer','returning_peer','charging_peer'))
def test_policy_does_not_create_a_charge_from_ineligible_context(reason):
    h,requests,events,_ = node()
    if reason=='spawn':h.robot_positions['tb1']=(2.,3.)
    if reason=='no_work':h.successful_exploration_legs.clear()
    if reason=='prior_charge':h.battery_states['tb1']['charge_count']=1
    if reason=='bool_count':h.battery_states['tb1']['charge_count']=False
    if reason=='missing_count':h.battery_states['tb1'].pop('charge_count')
    if reason=='mapping_only':h.enable_rally=False
    if reason=='far':h.robot_positions['tb1']=(5.,3.)
    if reason=='full':h.battery_states['tb1']['energy']=80.
    if reason=='capacity':h.battery_states['tb1']['capacity']=10.
    if reason=='unknown_contact':
        h.map_data=h.map_data.copy();h.map_data[:,24:27]=-1
        h.source_map_data=h.map_data
        for value in h.robot_maps.values():value['data']=h.map_data
    if reason=='stale':h.clock=12.001
    if reason=='live_peer':h.robot_states['tb2']='active'
    if reason=='returning_peer':h.battery_modes['tb2']='RETURNING'
    if reason=='charging_peer':h.battery_modes['tb2']='CHARGING'
    c.HeadquartersControl.request_exploration_charge(h,[('tb1',assignment(3.5,3.,distance=.5))])
    assert not requests and not any(e.get('initial_replenishment') for e in events)


def test_expired_during_contact_planning_sends_nothing_then_fresh_sources_reprice(monkeypatch):
    h,requests,events,_ = node()
    original = c.plan_rally_leg
    def expire(*args,**kwargs):
        result=original(*args,**kwargs);h.clock=13.;return result
    monkeypatch.setattr(c,'plan_rally_leg',expire)
    assert not c.HeadquartersControl.request_exploration_charge(h,[('tb1',assignment(3.5,3.,distance=.5))])
    assert not requests and not events
    monkeypatch.setattr(c,'plan_rally_leg',original)
    h.map_received_at=13.
    for name in h.robot_positions:
        for stamps in (h.robot_map_received_at,h.robot_odom_received_at,h.robot_tf_received_at,h.battery_state_received_at):
            stamps[name]=13.
        h.battery_states[name]['stamp_sec']=13.
    assert c.HeadquartersControl.request_exploration_charge(h,[('tb1',assignment(3.5,3.,distance=.5))])
    assert events[-1]['initial_replenishment']['trip_evaluated_at_sec']==13.


def reader_inputs():
    h,_,events,_=node()
    c.HeadquartersControl.request_exploration_charge(h,[('tb1',assignment(3.5,3.,distance=.5))])
    rows=[dict(event='coordinator_navigation_decision',robot='tb1',kind='exploration',event_time=9.),
        dict(event='enqueue',message_type='navigation_goal',recipient='tb1',correlation_id=1,event_time=9.),
        dict(event='navigation_outcome',recipient='tb1',correlation_id=1,status=4,event_time=9.5),events[0]]
    native=[dict(topic='/tb1/battery_state',observer_time=10.,data=copy.deepcopy(h.battery_states['tb1']))]
    return rows,native


@pytest.mark.parametrize('change',('receipt_order','small_header_gap','future_success','future_command','old_declaration','ambiguous_kind'))
def test_work_binding_uses_original_source_epoch_and_not_receipt_order(tmp_path,change):
    rows,native=reader_inputs()
    if change=='receipt_order':rows.append(rows.pop(2))
    if change=='small_header_gap':rows[1]['source_time']=9.1
    if change=='future_success':rows[2]['event_time']=10.1
    if change=='future_command':rows[1]['source_time']=10.
    if change=='old_declaration':rows[0]['event_time']=6.9
    if change=='ambiguous_kind':rows.insert(1,{**rows[0],'kind':'exploration_return_yield'})
    path,native_path=tmp_path/'ledger.jsonl',tmp_path/'native.jsonl'
    path.write_text(''.join(json.dumps(row)+'\n' for row in rows))
    native_path.write_text(''.join(json.dumps(row)+'\n' for row in native))
    if change in ('receipt_order','small_header_gap'):
        assert initial_replenishment_audit(path,True,native_path)['policy_requests']==1
    else:
        with pytest.raises(AssertionError):initial_replenishment_audit(path,True,native_path)


@pytest.mark.parametrize('corruption',(None,'no_work','yield_credit','failed_result','duplicate_credit',
    'missing_command','native_count','native_mode','native_radius','missing_native','threshold','cost',
    'distance','stale','future_trip','late_trip','body','position','home','phase','counter','missing_field','undeclared'))
def test_independent_reader_rebuilds_policy_and_rejects_forged_authority(tmp_path,corruption):
    rows,native=reader_inputs();event=rows[-1];saved=event['initial_replenishment']
    if corruption=='no_work':saved['completed_exploration_legs']=0
    if corruption=='yield_credit':rows[0]['kind']='exploration_return_yield'
    if corruption=='failed_result':rows[2]['status']=6
    if corruption=='duplicate_credit':rows.insert(3,copy.deepcopy(rows[2]));saved['completed_exploration_legs']=2
    if corruption=='missing_command':rows.pop(1)
    if corruption=='native_count':native[0]['data']['charge_count']=1
    if corruption=='native_mode':native[0]['data']['mode']='CHARGING'
    if corruption=='native_radius':native[0]['data']['charge_radius_m']=1.6
    if corruption=='missing_native':native.clear()
    if corruption=='threshold':event['required_energy']=79.
    if corruption=='cost':saved['trip_required_energy']+=1.
    if corruption=='distance':saved['trip_distance_m']+=1.
    if corruption=='stale':event['inputs']['tb1/frame_state']['source_time']=7.
    if corruption=='future_trip':saved['trip_evaluated_at_sec']=11.
    if corruption=='late_trip':saved['evaluated_at_sec']=11.
    if corruption=='body':event['return_preparation']['robot_positions']['tb2']=[2.7,3.]
    if corruption=='position':saved['robot_position']=[4.,3.]
    if corruption=='home':saved['home']=[1.,3.]
    if corruption=='phase':event['task_phase']='RALLY'
    if corruption=='counter':saved['battery_state']['charge_count']=False
    if corruption=='missing_field':event.pop('initial_replenishment')
    path,native_path=tmp_path/'ledger.jsonl',tmp_path/'native.jsonl'
    path.write_text(''.join(json.dumps(row)+'\n' for row in rows))
    native_path.write_text(''.join(json.dumps(row)+'\n' for row in native))
    if corruption is None:
        assert initial_replenishment_audit(path,True,native_path)['policy_requests']==1
    else:
        with pytest.raises(AssertionError):initial_replenishment_audit(path,corruption!='undeclared',native_path)
