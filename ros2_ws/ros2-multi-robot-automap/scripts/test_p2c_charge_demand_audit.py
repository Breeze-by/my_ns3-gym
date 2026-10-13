"""Typed source and lifecycle counterexamples; no physical or mission credit."""
import base64
import copy
import gzip
import json
import math

import pytest
from rclpy.serialization import serialize_message
from std_msgs.msg import String

from p2c_global_audit import audit_motion, contact, geometry_world, global_mission_audit, scalar_budget
from test_p2c_observer_heading_audit import fixture, stamp


def demand(slot='main'):
    return dict(slot=slot, reason='unfunded_information_task', required_energy=50.,
                destination=[7., 5.], park_for=None)


def helper_fixture(actor_slot='main', beneficiary='native', role=None):
    event, rows, state, _ = fixture()
    state['energy'] = 18.
    world = event['world']
    world['target'], world['observer'], world['confirmations'] = None, None, {}
    world['sources'].pop('headquarters/target_detection')
    world['required'] = ['tb1', 'tb2']
    world['charge_pending'] = ['tb2'] if beneficiary == 'issued' else []
    world['charge_intents'] = {'tb1':demand(actor_slot)} if actor_slot else {}
    world['planned_return_routes'] = {}
    position = world['positions']['tb1']
    world['positions']['tb2'] = (position[0]+3., position[1])
    world['yaws']['tb2'] = 1.5
    peer = {**state, 'energy':40., 'mode':'ACTIVE' if beneficiary in ('soft','issued') else 'RETURNING',
            'charge_x':position[0]-1., 'charge_y':position[1]}
    world['battery_states']['tb2'] = peer
    world['return_maps']['tb2'] = copy.deepcopy(world['return_maps']['tb1'])
    for kind in ('map_snapshot', 'pose_state', 'frame_state', 'battery_state'):
        world['sources']['tb2/'+kind] = world['sources']['tb1/'+kind]
    if beneficiary in ('soft', 'native_soft'):
        world['charge_intents']['tb2'] = demand('deferred' if actor_slot else 'main')
    grid, maps = geometry_world(event)
    for robot in world['charge_intents']:
        if world['battery_states'][robot]['mode'] == 'ACTIVE':
            world['planned_return_routes'][robot] = contact(world, grid, maps, robot, world['positions'][robot])['route']
    endpoint = (position[0], position[1]-1.9)
    event.update(kind=role or ('charge_clearance' if beneficiary in ('soft','issued') else 'local_return_yield'),
        beneficiary='tb2', route=[position, endpoint], complete_task_route=[position, endpoint],
        requested_position=endpoint, requested_yaw=0., waiting_time_budget_sec=0.)
    event['required_energy'] = scalar_budget(event, grid, maps, event['route'], endpoint)
    topics = dict(rows)
    topics['/gateway/received/tb1/battery_state'].data = json.dumps(state)
    odom = copy.deepcopy(topics['/gateway/received/tb1/odom'])
    odom.pose.pose.position.x += 3.*math.cos(.3)
    odom.pose.pose.position.y -= 3.*math.sin(.3)
    rows.extend([('/gateway/received/tb2/map', copy.deepcopy(topics['/gateway/received/tb1/map'])),
        ('/gateway/received/tb2/odom', odom), ('/tb2/odom', copy.deepcopy(odom)),
        ('/gateway/received/tb2/tf', copy.deepcopy(topics['/gateway/received/tb1/tf'])),
        ('/tb2/tf', copy.deepcopy(topics['/tb1/tf'])),
        ('/gateway/received/tb2/battery_state', String(data=json.dumps(peer)))])
    return event, rows, {'tb1':state, 'tb2':peer}


def write_sources(tmp_path, rows, states, extra=()):
    with gzip.open(tmp_path/'navigation_inputs.jsonl.gz', 'wt') as stream:
        for topic, message in rows:
            stream.write(json.dumps(dict(topic=topic, received_sim_time=30.,
                cdr=base64.b64encode(serialize_message(message)).decode()))+'\n')
    (tmp_path/'safety_events.jsonl').write_text(''.join(json.dumps(dict(topic='/'+robot+'/battery_state', data=state))+'\n'
        for robot,state in [*states.items(), *extra]))


@pytest.mark.parametrize('slot,beneficiary,role', [
    ('main','native',None), ('deferred','native',None),
    (None,'soft',None), (None,'issued',None),
    ('main','native_soft',None), ('main','native_soft','charge_clearance')])
def test_only_real_ownership_excludes_a_funded_current_helper(tmp_path, slot, beneficiary, role):
    from p2c_global_audit import bind_sources
    event, rows, states = helper_fixture(slot, beneficiary, role)
    assert audit_motion(event) == 2
    write_sources(tmp_path, rows, states)
    assert bind_sources([event], tmp_path/'navigation_inputs.jsonl.gz', tmp_path/'safety_events.jsonl') == 3


@pytest.mark.parametrize('corruption', ['ordinary', 'native_actor', 'issued_actor', 'stale_beneficiary',
    'missing_beneficiary', 'missing_soft_corridor', 'clipped_corridor', 'forged_corridor',
    'native_soft_corridor', 'duplicate_slot', 'nonmonotone', 'budget',
    'failed_beneficiary', 'quarantined_beneficiary'])
def test_helper_demand_proof_rejects_corrupted_authority_or_geometry(corruption):
    beneficiary = ('soft' if corruption in ('missing_soft_corridor','clipped_corridor','forged_corridor')
                   else 'issued' if corruption in ('failed_beneficiary','quarantined_beneficiary') else 'native')
    event, _, _ = helper_fixture(beneficiary=beneficiary)
    world = event['world']
    if corruption == 'ordinary': event['kind'] = 'exploration'
    if corruption == 'native_actor': world['battery_states']['tb1']['mode'] = 'RETURNING'
    if corruption == 'issued_actor':
        world['charge_intents'].pop('tb1');world['planned_return_routes'].pop('tb1')
        world['charge_pending'].append('tb1')
    if corruption == 'stale_beneficiary': world['sources']['tb2/pose_state'] = 7.9
    if corruption == 'missing_beneficiary': event['beneficiary'] = 'tb3'
    if corruption == 'failed_beneficiary': world['battery_states']['tb2']['mode'] = 'FAILED'
    if corruption == 'quarantined_beneficiary': world['required'].remove('tb2')
    if corruption == 'missing_soft_corridor': world['planned_return_routes'].pop('tb2')
    if corruption == 'clipped_corridor': world['planned_return_routes']['tb2'] = world['planned_return_routes']['tb2'][:1]
    if corruption == 'forged_corridor': world['planned_return_routes']['tb2'] = [[1.,1.], *world['planned_return_routes']['tb2'][1:]]
    if corruption == 'native_soft_corridor':
        world['charge_intents']['tb2'] = demand('deferred')
        grid,maps=geometry_world(event)
        world['planned_return_routes']['tb2'] = contact(world,grid,maps,'tb2',world['positions']['tb2'])['route']
    if corruption == 'duplicate_slot': world['charge_intents']['tb2'] = demand('main')
    if corruption == 'nonmonotone':
        point=world['positions']['tb1']
        event['route'] = [point,(point[0],point[1]-1.7),(point[0],point[1]-1.2),event['requested_position']]
        event['complete_task_route'] = event['route']
    if corruption == 'budget': event['required_energy'] += .01
    with pytest.raises(AssertionError): audit_motion(event)


def lifecycle_fixture(tmp_path, corruption=None):
    helper, rows, states = helper_fixture(actor_slot=None)
    initial = copy.deepcopy(states)
    initial['tb2']['mode'] = 'ACTIVE'
    for topic,message in rows:
        if topic.endswith('/battery_state'):
            robot=topic.split('/')[-2]
            message.data=json.dumps(initial[robot])
    world = copy.deepcopy(helper['world'])
    world['battery_states'] = copy.deepcopy(initial)
    world['completed_legs'] = {'tb1':1}
    position = world['positions']['tb1']
    charge = dict(event='coordinator_global_charge_admission',event_time=10.,robot='tb1',world=world,
        budget_evaluated_at_sec=9.9,required_energy=20.,destination=position,desired_task_route=[position],
        desired_task_budget_at_sec=9.9,desired_task_wait_sec=0.,reason='low_energy_after_actual_work')
    grid,maps=geometry_world(charge)
    charge['current_return_required']=scalar_budget(charge,grid,maps,[position],position)
    charge['return_route']=contact(world,grid,maps,'tb1',position)['route']
    returning={**initial['tb1'],'stamp_sec':10.2,'mode':'RETURNING'}
    charging={**returning,'stamp_sec':10.3,'mode':'CHARGING'}
    active={**initial['tb1'],'stamp_sec':16.4,'energy':80.,'charge_count':1}
    transitions=[dict(event='coordinator_global_charge_request_transition',event_time=10.25,robot='tb1',
        requested_at_sec=10.,battery_source_time=10.2,battery_state=returning,previous_mode='ACTIVE'),
        dict(event='coordinator_global_charge_request_transition',event_time=10.35,robot='tb1',
        requested_at_sec=10.,battery_source_time=10.3,battery_state=charging,previous_mode='RETURNING')]
    closed=dict(event='coordinator_global_charge_request_closed',event_time=16.45,robot='tb1',
        requested_at_sec=10.,battery_source_time=16.4,battery_state=active,
        observed_return_started=True,reason='native_cycle_closed')
    if corruption in ('lease_expiry','early_lease'):
        transitions=[]
        source=20.1 if corruption=='lease_expiry' else 19.9
        active={**initial['tb1'],'stamp_sec':source}
        closed.update(event_time=source+.05,battery_source_time=source,battery_state=active,
                      observed_return_started=False,reason='request_lease_ended')
    current=copy.deepcopy(rows)
    for data in (returning,charging,active):
        rows.append(('/gateway/received/tb1/battery_state',String(data=json.dumps(data))))
    at=active['stamp_sec']+.2
    for topic,message in current:
        if topic.endswith('/target_detection'):continue
        if topic.endswith('/tf'):
            for transform in message.transforms:stamp(transform.header,at)
        elif topic.endswith(('/map','/odom')):stamp(message.header,at)
        elif topic.endswith('/battery_state'):
            robot=topic.split('/')[-2]
            data=active if robot=='tb1' else {**states['tb2'],'stamp_sec':at}
            message.data=json.dumps(data)
    rows.extend(current)
    helper['event_time']=helper['budget_evaluated_at_sec']=at+.05
    for key in helper['world']['sources']:helper['world']['sources'][key]=at
    for saved in (helper['world']['source_map'],helper['world']['planning_map'],*helper['world']['return_maps'].values()):saved['source_time']=at
    helper['world']['battery_states']['tb1']=active
    helper['world']['sources']['tb1/battery_state']=active['stamp_sec']
    helper['world']['battery_states']['tb2']={**states['tb2'],'stamp_sec':at}
    grid,maps=geometry_world(helper)
    helper['required_energy']=scalar_budget(helper,grid,maps,helper['route'],helper['requested_position'])
    admission={**helper,'event':'coordinator_global_motion_admission','generation':1}
    sent=dict(event='coordinator_global_motion_sent',robot='tb1',generation=1,stamp_sec=at+.05)
    finish=dict(event='coordinator_global_motion_closed',robot='tb1',generation=1,status=4,error='')
    ledger=[charge,dict(event='coordinator_global_charge_sent',robot='tb1',stamp_sec=10.),*transitions,closed,admission,sent,finish]
    if corruption=='omit_closed':ledger.remove(closed)
    if corruption=='wrong_requested':transitions[0]['requested_at_sec']=10.1
    if corruption=='forged_native_state':transitions[0]['battery_state']={**returning,'energy':17.}
    if corruption=='missing_delivery':rows=[(t,m) for t,m in rows if not(t.endswith('/battery_state') and json.loads(m.data).get('stamp_sec')==10.2)]
    if corruption=='missing_transition':ledger=[row for row in ledger if row not in transitions]
    if corruption in ('omit_all_fields','omit_all_fields_no_manifest'):
        for row in ledger:
            if 'world' in row:
                row['world'].pop('charge_intents');row['world'].pop('planned_return_routes')
    if corruption!='omit_all_fields_no_manifest':
        (tmp_path/'manifest.json').write_text(json.dumps(dict(config=dict(global_algorithm=dict(charge_ownership='declared current contract')))))
    extra=[('tb1',data) for data in (returning,charging,active)]+[('tb2',helper['world']['battery_states']['tb2'])]
    write_sources(tmp_path,rows,initial,extra)
    (tmp_path/'ledger.jsonl').write_text(''.join(json.dumps(row)+'\n' for row in ledger))


@pytest.mark.parametrize('corruption',[None,'lease_expiry','early_lease','omit_closed','wrong_requested',
    'forged_native_state','missing_delivery','missing_transition','omit_all_fields','omit_all_fields_no_manifest'])
def test_issued_charge_closes_only_on_bound_applied_native_state(tmp_path,corruption):
    lifecycle_fixture(tmp_path,corruption)
    if corruption in (None,'lease_expiry'):
        audited=global_mission_audit(tmp_path,True)
        assert audited['sent']==audited['closed']==audited['charge_admissions']==1
        assert not audited['pending_issued_charge_requests_at_shutdown']
    else:
        with pytest.raises(AssertionError):global_mission_audit(tmp_path,True)
