"""Formal retargets must lose the previous refuge's dispatch exception."""
import copy
import json

import pytest

from p2c_navigation_dispatch import navigation_dispatch_audit


def rows():
    pose = [6., 2.5, 0.]
    return [dict(event='coordinator_rally_recovery_retarget', event_time=9.9, robot='tb1',
                 blocker='tb2', new_target=pose, movement_authorized=False,
                 previous_intent=dict(return_yield_owner='tb2', temporary_yield=True, probe=True)),
            dict(event='coordinator_navigation_decision', event_time=10., robot='tb1', kind='rally',
                 dispatch_goal_source_time_sec=10., dispatch_lease_deadline_sec=12.,
                 inputs={'tb1/pose_state': dict(source_time=10., age_sec=0., ttl_sec=2.),
                         'headquarters/target_detection': dict(source_time=10., age_sec=0., ttl_sec=60.)},
                 rally_recovery_intent=dict(return_yield_owner=None, temporary_yield=False, probe=False,
                                            current_target=pose, final_target=pose))]


@pytest.mark.parametrize('mutation', [None, 'local', 'yield', 'probe', 'missing', 'expired', 'authority'])
def test_transition_reader_rejects_stale_dispatch_roles_and_keeps_original_leases(tmp_path, mutation):
    events = copy.deepcopy(rows()); event = events[-1]
    if mutation == 'local':
        event['kind'] = 'local_return_yield'
        event['rally_recovery_intent'].update(return_yield_owner='tb2', temporary_yield=True)
    if mutation == 'yield': event['rally_recovery_intent']['temporary_yield'] = True
    if mutation == 'probe': event['rally_recovery_intent']['probe'] = True
    if mutation == 'missing': del event['rally_recovery_intent']
    if mutation == 'expired': event['inputs']['tb1/pose_state']['source_time'] = 7.
    if mutation == 'authority': events[0]['movement_authorized'] = True
    p = tmp_path/'ledger.jsonl'; p.write_text(''.join(json.dumps(e)+'\n' for e in events))
    if mutation:
        with pytest.raises((AssertionError, KeyError)):
            navigation_dispatch_audit(p, True, True)
    else:
        result = navigation_dispatch_audit(p, True, True)
        assert result['decisions'] == result['permanent_retargets'] == 1


def test_a_later_genuine_local_refuge_keeps_its_target_independent_safety_exception(tmp_path):
    events = rows(); event = events[-1]; event['kind'] = 'local_return_yield'
    event['rally_recovery_intent'].update(current_target=[4., 1.5, 0.], temporary_yield=True, return_yield_owner='tb2')
    event['inputs']['headquarters/target_detection'] = dict(source_time=-51., age_sec=61., ttl_sec=60.)
    p = tmp_path/'ledger.jsonl'; p.write_text(''.join(json.dumps(e)+'\n' for e in events))
    assert navigation_dispatch_audit(p, True, True)['status'] == 'PASS'
