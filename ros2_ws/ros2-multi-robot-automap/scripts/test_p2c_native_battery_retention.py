"""Complete private battery records bind waiting epochs without changing control."""
import ast
import copy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from std_msgs.msg import String

from multi_robot_exploration import control
from p2c_initial_replenishment import audit_first_window_reservation_waits


def record_function(output, full_capture):
    source = Path(__file__).with_name('observe_p3b5.py').read_text()
    function = next(n for n in ast.parse(source).body if isinstance(n,ast.FunctionDef) and n.name=='record')
    namespace = dict(json=json,last={},args=SimpleNamespace(output=output),
        node=SimpleNamespace(get_clock=lambda:SimpleNamespace(now=lambda:SimpleNamespace(nanoseconds=13_000_000_000))),
        navigation_capture=object() if full_capture else None)
    exec(compile(ast.get_source_segment(source,function),'<production observer record>','exec'),namespace)
    return namespace['record'],namespace['last']


@pytest.mark.parametrize('full_capture', [False,True])
@pytest.mark.parametrize('change', ['energy_only','mode','return_count','charge_count'])
def test_continuous_source_epochs_retained_in_full_capture_and_legacy_events_preserved(tmp_path,full_capture,change):
    output=tmp_path/'native.jsonl';record,last=record_function(output,full_capture)
    first=dict(mode='ACTIVE',return_count=1,charge_count=0,energy=18.,stamp_sec=11.)
    second={**first,'energy':17.98,'stamp_sec':12.}
    if change=='mode':second['mode']='RETURNING'
    elif change!='energy_only':second[change]+=1
    record('/tb1/battery_state',String(data=json.dumps(first)))
    record('/tb1/battery_state',String(data=json.dumps(second)))
    rows=[json.loads(line) for line in output.read_text().splitlines()]
    assert rows[0]['data']==first and len(rows)==(1 if change=='energy_only' and not full_capture else 2)
    if len(rows)==2:assert rows[1]['data']==second
    assert last['/tb1/battery_state']==(second['mode'],second['return_count'],second['charge_count'])


def wait():
    state=dict(mode='ACTIVE',stamp_sec=11.,charge_count=0,charge_radius_m=.8,capacity=100.,
        charge_target_fraction=.8,energy=40.,charge_x=2.,charge_y=3.)
    position=[2.,3.];window=control.initial_replenishment_prefix(state,position,0,.1);window['generated_at_sec']=13.
    return dict(event_time=13.,started_at_sec=13.,planning_started_at_sec=13.,wait_timeout_sec=10.,navigation_timeout_sec=60.,
        movement_authorized=False,native_credit_added=False,task_phase='EXPLORE',context=['EXPLORE',False,['tb1'],None],
        robot='tb1',completed_exploration_legs=0,battery_state=state,current_position=position,initial_window=window,
        rejected_targets=[[4.,3.]],reserved_routes=[[[2.,3.],[4.,3.]]],
        inputs={'tb1/battery_state':dict(source_time=11.,age_sec=2.,ttl_sec=5.)})


def test_wait_requires_exact_published_model_and_its_original_header():
    e=wait();native={'tb1':[copy.deepcopy(e['battery_state'])]}
    assert audit_first_window_reservation_waits([e],native,True)['waits']==1
    e['inputs']['tb1/battery_state'].update(source_time=12.,age_sec=1.)
    with pytest.raises(AssertionError,match='battery epoch'):
        audit_first_window_reservation_waits([e],native,True)


def test_native_source_binding_cannot_be_replaced_by_nearest_mode_event(tmp_path):
    output=tmp_path/'native.jsonl';record,_=record_function(output,True)
    e=wait();original={**e['battery_state'],'energy':40.02,'stamp_sec':10.}
    record('/tb1/battery_state',String(data=json.dumps(original)))
    record('/tb1/battery_state',String(data=json.dumps(e['battery_state'])))
    with pytest.raises(AssertionError,match='original native battery'):
        audit_first_window_reservation_waits([e],{'tb1':[original]},True)
    retained={'tb1':[json.loads(line)['data'] for line in output.read_text().splitlines()]}
    assert audit_first_window_reservation_waits([e],retained,True)['waits']==1
