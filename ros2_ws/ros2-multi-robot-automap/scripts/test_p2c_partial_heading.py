import copy,json,math
from pathlib import Path

import pytest

from check_p2c_gate import observer_heading_audit,planning_position_tolerance
from check_p3c5_gate import native_safety_ok


def original(tmp_path):
    path=Path(__file__).resolve().parents[1]/'src/multi_robot_exploration/test/fixtures/p2c_v64_unassigned_heading.json'
    fixture=json.loads(path.read_text())
    (tmp_path/'runner.log').write_text(fixture['runner_text'])
    return fixture


def test_unassigned_found_observer_uses_executed_limit_without_native_hold_claim(tmp_path):
    fixture=original(tmp_path);result=fixture['result'];before=copy.deepcopy(result)
    with pytest.raises(TypeError):
        observer_heading_audit(fixture['heading_records'],True,result['target_max_distance_m'],
            result['rally_position_tolerance_m'],math.radians(result['target_field_of_view_deg']))
    native_safety_ok(result)
    tolerance=planning_position_tolerance(result,tmp_path)
    proof=observer_heading_audit(fixture['heading_records'],True,result['target_max_distance_m'],
        tolerance,math.radians(result['target_field_of_view_deg']))
    assert proof['quiet_holds']>0 and tolerance==.35
    assert result==before and result['native_rally_hold_proof'] is None
    assert not result['success'] and not result['rally_assignments']


@pytest.mark.parametrize('mutation',['missing_command','missing_limit','duplicate_limit','looser_limit','nan_limit','native_mismatch'])
def test_unassigned_limit_requires_exact_executed_provenance(tmp_path,mutation):
    fixture=original(tmp_path);result=fixture['result'];text=fixture['runner_text']
    if mutation=='missing_command':text=text.replace('Command: ','Ignored: ')
    if mutation=='missing_limit':text=text.replace('rally_position_tolerance_m:=0.35','')
    if mutation=='duplicate_limit':text=text.replace('rally_position_tolerance_m:=0.35','rally_position_tolerance_m:=0.35 rally_position_tolerance_m:=0.35')
    if mutation=='looser_limit':text=text.replace('rally_position_tolerance_m:=0.35','rally_position_tolerance_m:=0.5')
    if mutation=='nan_limit':text=text.replace('rally_position_tolerance_m:=0.35','rally_position_tolerance_m:=nan')
    if mutation=='native_mismatch':result['rally_position_tolerance_m']=.5
    (tmp_path/'runner.log').write_text(text)
    with pytest.raises(AssertionError):planning_position_tolerance(result,tmp_path)


@pytest.mark.parametrize('distance,passes',[(2.649,True),(2.651,False)])
def test_unassigned_heading_keeps_original_camera_error_margin(tmp_path,distance,passes):
    fixture=original(tmp_path);event=fixture['heading_records'][0]
    event.update(position=[0.,0.],target=[distance,0.],desired_yaw=0.,yaw=math.pi/2)
    tolerance=planning_position_tolerance(fixture['result'],tmp_path)
    if passes:assert observer_heading_audit([event],True,3.,tolerance,math.pi/2)['quiet_holds']==1
    else:
        with pytest.raises(AssertionError):observer_heading_audit([event],True,3.,tolerance,math.pi/2)


@pytest.mark.parametrize('mutation',['expired_target','stale_tf','missing_camera'])
def test_unassigned_heading_still_rejects_stale_or_incomplete_evidence(tmp_path,mutation):
    fixture=original(tmp_path);event=fixture['heading_records'][0];fov=math.pi/2
    if mutation=='expired_target':
        event['inputs']['headquarters/target_detection'].update(source_time=event['event_time']-6.,age_sec=6.)
        event['target_source_time']=event['event_time']-6.
    if mutation=='stale_tf':event['inputs'][event['robot']+'/frame_state'].update(source_time=event['event_time']-2.01,age_sec=2.01)
    if mutation=='missing_camera':fov=None
    tolerance=planning_position_tolerance(fixture['result'],tmp_path)
    with pytest.raises(AssertionError):observer_heading_audit([event],True,3.,tolerance,fov)
