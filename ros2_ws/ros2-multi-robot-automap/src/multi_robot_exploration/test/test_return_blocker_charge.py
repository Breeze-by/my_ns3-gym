import copy,json,math
import pytest
from multi_robot_exploration import control as c
from p2c_return_preparation import audit_preparation
from return_blocker_reference import original_admit,snapshot_node

@pytest.mark.parametrize('index',range(3))
def test_original_unfunded_refuge_stalls_but_current_blocker_return_is_funded(index):
    h,requests,events,sent=snapshot_node(index);proposal=copy.deepcopy(h.pending_exploration_return_yield)
    for _ in range(2):assert original_admit()(h)
    assert h.pending_exploration_return_yield==proposal and not requests and not sent and not events
    previous=(2.9391165283301905,.6559068757746642,65)
    h.exploration_resume_intents['tb2']=previous;work=copy.deepcopy(h.successful_exploration_legs)
    assert c.HeadquartersControl.admit_exploration_return_yield(h)
    assert h.pending_exploration_return_yield is None and not sent
    assert [n for n,_ in requests]==['tb2'] and set(h.rally_charge_requested)=={'tb2'}
    assert h.exploration_resume_intents['tb2']==previous and h.successful_exploration_legs==work
    event=events[-1];assert audit_preparation(event)=='charge'
    assert event['preparation_charge']['returning']=='tb1'
    proof=event['preparation_charge'];energy=h.battery_states['tb2']['energy']
    assert proof['current_return_required_energy']<energy<=proof['refuge_required_energy']
    assert event['required_energy']<h.battery_states['tb2']['capacity']*h.battery_states['tb2']['charge_target_fraction']

@pytest.mark.parametrize('reason',['stale','future','missing','unsafe_current_return','capacity','own_return',
    'beneficiary_returning','charging_peer','live_peer','pending_owner','all_unknown_return','no_budget'])
def test_blocker_charge_keeps_source_energy_body_and_serial_owner_guards(reason,monkeypatch):
    h,requests,events,sent=snapshot_node();name='tb2'
    if reason=='stale':h.clock+=2.001
    if reason=='future':h.robot_tf_received_at[name]=h.clock+.1
    if reason=='missing':h.robot_map_received_at[name]=None
    if reason=='unsafe_current_return':h.battery_states[name]['energy']=1.
    if reason=='capacity':h.battery_states[name].update(capacity=10.,charge_target_fraction=.8)
    if reason=='own_return':h.battery_modes[name]='RETURNING'
    if reason=='beneficiary_returning':h.battery_modes['tb1']='RETURNING'
    if reason=='charging_peer':h.battery_modes['tb3']='CHARGING'
    if reason=='live_peer':h.robot_states['tb3']='active'
    if reason=='pending_owner':h.rally_charge_requested['tb1']=h.clock
    if reason=='all_unknown_return':
        raw=h.map_data.copy();raw[:]=-1;h.map_data=h.source_map_data=raw
        for value in h.robot_maps.values():value['data']=raw
    if reason=='no_budget':monkeypatch.setattr(c.HeadquartersControl,'exploration_required_energy',lambda *a,**k:None)
    c.HeadquartersControl.admit_exploration_return_yield(h)
    assert not sent and not requests and not any(e.get('event')=='coordinator_charge_decision' for e in events)

@pytest.mark.parametrize('tamper',['beneficiary','blocker','body','map','source','route','point','refuge_price',
    'current_price','charge_price','energy','authority','clearance','evaluated'])
def test_independent_reader_rejects_preparation_charge_tampering(tamper):
    h,requests,events,sent=snapshot_node();c.HeadquartersControl.admit_exploration_return_yield(h)
    e=copy.deepcopy(events[-1]);w=e['preparation_charge']
    if tamper=='beneficiary':w['returning']='tb2'
    if tamper=='blocker':w['blocker']='tb3'
    if tamper=='body':w['robot_positions']['tb2'][0]+=1.
    if tamper=='map':w['planning_map']['source_time']-=.1
    if tamper=='source':w['inputs']['tb2/frame_state']['source_time']-=.1
    if tamper=='route':w['protected_routes']['tb1'][0][0]+=1.
    if tamper=='point':w['refuge_position'][0]+=1.
    if tamper=='refuge_price':w['refuge_required_energy']-=1.
    if tamper=='current_price':w['current_return_required_energy']-=1.
    if tamper=='charge_price':e['required_energy']-=1.
    if tamper=='energy':e['available_energy']+=1.
    if tamper=='authority':w['ordinary_navigation_authorized']=True
    if tamper=='clearance':w['clearance_m']=.5
    if tamper=='evaluated':w['current_return_required_energy_evaluated_at_sec']-=3.
    with pytest.raises((AssertionError,ValueError,KeyError)):audit_preparation(e)

def test_dropped_geometric_budget_does_not_keep_a_permanent_entry_block(monkeypatch):
    h,requests,events,sent=snapshot_node()
    monkeypatch.setattr(c.HeadquartersControl,'exploration_required_energy',lambda *a,**k:None)
    assert c.HeadquartersControl.admit_exploration_return_yield(h)
    assert h.pending_exploration_return_yield is None and not requests and not sent

def test_a_blocker_without_a_search_intent_does_not_inherit_a_refuge_as_frontier():
    h,requests,events,sent=snapshot_node();h.exploration_resume_intents.pop('tb2',None)
    c.HeadquartersControl.admit_exploration_return_yield(h)
    assert requests and 'tb2' not in h.exploration_resume_intents and not sent
