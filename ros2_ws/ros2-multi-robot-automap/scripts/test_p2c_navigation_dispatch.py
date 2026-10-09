"""Private lease evidence cannot enlarge TTLs or renew original observations."""
from copy import deepcopy
import json

import pytest

from p2c_navigation_dispatch import navigation_dispatch_audit


def decision():
    return dict(event='coordinator_navigation_decision', event_time=10., robot='tb1', kind='rally',
                dispatch_goal_source_time_sec=10., dispatch_lease_deadline_sec=12., inputs={
                    'tb1/pose_state': dict(source_time=10., ttl_sec=2., age_sec=0.),
                    'tb1/map_snapshot': dict(source_time=10., ttl_sec=5., age_sec=0.)})


def audit(tmp_path, events):
    path = tmp_path / 'ledger.jsonl'
    path.write_text(''.join(json.dumps(e) + '\n' for e in events))
    return navigation_dispatch_audit(path, True)


def test_current_admission_and_expired_publication(tmp_path):
    original = decision()
    revoke = deepcopy(original)
    revoke.update(event='coordinator_navigation_dispatch_revoked', event_time=12.1,
                  decision_time_sec=10., stage='audit_publication', shutdown_requested=False)
    for sample in revoke['inputs'].values():
        sample['age_sec'] = 2.1
    row = audit(tmp_path, [original, revoke])
    assert row['decisions'] == row['publication_revocations'] == 1


@pytest.mark.parametrize('mutate', [
    lambda e: e.update(dispatch_lease_deadline_sec=15.),
    lambda e: e.update(dispatch_goal_source_time_sec=11.),
    lambda e: e['inputs']['tb1/pose_state'].update(ttl_sec=3.),
    lambda e: e['inputs']['tb1/pose_state'].update(source_time=11.),
    lambda e: e['inputs']['tb1/pose_state'].update(source_time=7.),
    lambda e: e['inputs']['tb1/pose_state'].update(age_sec=1.),
    lambda e: e['inputs'].clear(),
])
def test_false_freshness_claim_is_rejected(tmp_path, mutate):
    event = decision(); mutate(event)
    with pytest.raises(AssertionError):
        audit(tmp_path, [event])


def test_revocation_does_not_renew_sources_or_claim_an_unexpired_reason(tmp_path):
    original = decision()
    revoke = deepcopy(original)
    revoke.update(event='coordinator_navigation_dispatch_revoked', event_time=10.,
                  decision_time_sec=10., stage='audit_publication', shutdown_requested=False)
    with pytest.raises(AssertionError):
        audit(tmp_path, [original, revoke])
    revoke['event_time'] = 12.1
    revoke['inputs']['tb1/pose_state'].update(source_time=12.1, age_sec=0.)
    with pytest.raises(AssertionError):
        audit(tmp_path, [original, revoke])


def test_additional_body_lease_keeps_its_preparation_epoch(tmp_path):
    event = decision(); event['kind'] = 'exploration_return_yield'
    event['dispatch_lease_deadline_sec'] = 11.
    event['return_preparation'] = dict(inputs={
        'tb2/pose_state': dict(source_time=9., ttl_sec=2., age_sec=.5)})
    assert audit(tmp_path, [event])['decisions'] == 1
    event['event_time'] = event['dispatch_goal_source_time_sec'] = 11.1
    for sample in event['inputs'].values():
        sample['age_sec'] = 1.1
    with pytest.raises(AssertionError):
        audit(tmp_path, [event])
