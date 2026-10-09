"""Independently reconstruct private navigation admission and revocation leases."""
import json
import math


TARGET_INDEPENDENT = ('local_return_yield', 'target_reacquisition_scan',
                      'target_reacquisition_exploration')


def used_inputs(event):
    used = {key: row for key, row in event['inputs'].items()
            if key != 'headquarters/target_detection' or event['kind'] not in TARGET_INDEPENDENT}
    if event['kind'] == 'exploration_return_yield':
        extra = event['return_preparation']['inputs']
        for key in used.keys() & extra.keys():
            assert used[key]['source_time'] == extra[key]['source_time']
            assert used[key]['ttl_sec'] == extra[key]['ttl_sec']
        used.update(extra)
    if 'rally_transit_observer' in event:
        saved = event['rally_transit_observer']
        assert saved['heartbeat_sec'] == 5.
        assert saved['observer_source_time'] == saved['confirmation']['source_time']
        assert saved['observer_source_time'] <= event['inputs']['headquarters/target_detection']['source_time']
        used['headquarters/transit_observer_heartbeat'] = dict(source_time=saved['observer_source_time'], ttl_sec=5.)
    assert used, 'navigation decision without source leases'
    return used


def sample_deadline(key, row):
    source, ttl = row['source_time'], row['ttl_sec']
    limit = (60. if key == 'headquarters/target_detection' else
             2. if key.endswith(('/pose_state', '/frame_state')) else 5.)
    assert isinstance(source, (int, float)) and math.isfinite(source)
    assert isinstance(ttl, (int, float)) and math.isfinite(ttl) and 0 < ttl <= limit
    return source + ttl


def navigation_dispatch_audit(path, required=False):
    if not required:
        return None
    decisions = {}; count = revoked = 0
    for line in path.open():
        event = json.loads(line)
        kind = event.get('event')
        if kind not in ('coordinator_navigation_decision', 'coordinator_navigation_dispatch_revoked'):
            continue
        now = event['event_time']
        assert math.isfinite(now)
        if kind == 'coordinator_navigation_decision':
            used = used_inputs(event)
            deadline = min(sample_deadline(key, row) for key, row in used.items())
            assert math.isclose(event['dispatch_lease_deadline_sec'], deadline, abs_tol=1e-9, rel_tol=0.)
            assert event['dispatch_goal_source_time_sec'] == now
            for key, row in used.items():
                age = now - row['source_time']
                assert 0 <= age <= row['ttl_sec']
                if key in event['inputs']:
                    assert math.isclose(event['inputs'][key]['age_sec'], age, abs_tol=1e-9, rel_tol=0.)
            decisions.setdefault((event['robot'], event['kind'], now), []).append(event)
            count += 1
        else:
            key = (event['robot'], event['kind'], event['decision_time_sec'])
            assert decisions.get(key), 'revocation without original private admission'
            original = decisions[key].pop()
            assert event['stage'] == 'audit_publication'
            assert event['dispatch_lease_deadline_sec'] == original['dispatch_lease_deadline_sec']
            assert set(event['inputs']) == set(original['inputs'])
            for name, row in event['inputs'].items():
                assert row['source_time'] == original['inputs'][name]['source_time']
                assert row['ttl_sec'] == original['inputs'][name]['ttl_sec']
                if row['source_time'] is not None:
                    assert math.isclose(row['age_sec'], now - row['source_time'], abs_tol=1e-9, rel_tol=0.)
            used = used_inputs(original)
            assert (event['shutdown_requested'] or any(
                now < row['source_time'] or now > sample_deadline(name, row) for name, row in used.items()))
            revoked += 1
    return dict(status='PASS', decisions=count, publication_revocations=revoked,
                scope='Private admission/deadline and revocation provenance; actual ActionServer non-dispatch is separately exercised by the DDS component proof')
