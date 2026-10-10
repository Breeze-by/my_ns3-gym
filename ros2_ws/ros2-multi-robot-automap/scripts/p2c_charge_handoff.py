#!/usr/bin/env python3
"""Read private geometric repricing handoffs; all command audits stay separate."""
import json
import math
from pathlib import Path


def charge_geometry_handoff_audit(ledger: Path, enabled=False):
    retained = handoffs = 0
    pending = None
    robots = {}
    for line in ledger.open():
        event = json.loads(line)
        kind = event.get('event')
        if kind == 'coordinator_planning_lease_expired':
            if enabled:
                assert 'charge_geometry_preference' in event, 'missing geometric handoff declaration'
            hint = event.get('charge_geometry_preference')
            pending = hint
            if hint is None:
                continue
            assert enabled, 'undeclared charge geometry preference'
            assert set(hint) == {'robot', 'point', 'context', 'generated_at'}, 'preference contains authority or prices'
            point = hint['point']
            assert len(point) == 2 and all(math.isfinite(v) for v in point)
            assert hint['generated_at'] == event['planning_started_at_sec'], 'preference origin renewed'
            assert math.isfinite(hint['generated_at']) and hint['generated_at'] <= event['event_time']
            assert event['event_time'] > event['source_deadline_sec'], 'retention did not follow an expired callback'
            context = hint['context']
            assert len(context) == 4 and context[0] in ('EXPLORE', 'FOUND_UNCONFIRMED', 'FOUND', 'RALLY')
            assert context[2] == sorted(set(context[2])) and hint['robot'] in context[2]
            geometry = event['geometry_preferences']
            assert geometry and geometry['context'] == context, 'preference context differs'
            assert point in geometry['points'].get(hint['robot'], ()), 'unrecorded geometric point'
            retained += 1
        elif kind == 'coordinator_charge_geometry_handoff':
            assert enabled and pending is not None, 'handoff has no declared retained origin'
            hint = event['preference']
            assert hint == pending, 'handoff changed retained geometry or origin'
            now = event['event_time']
            assert math.isfinite(now) and 0 <= now-hint['generated_at'] <= 10., 'expired geometric preference'
            assert event['task_phase'] == hint['context'][0], 'handoff phase changed'
            assert event['candidate_robot_names'] == [hint['robot']], 'handoff did not focus one current generator'
            for name in hint['context'][2]:
                assert event['robot_states'][name] == 'idle', 'handoff during peer action'
                assert event['battery_modes'][name] == 'ACTIVE', 'handoff during local safety return'
                for sample_kind, ttl in (('pose_state', 2.), ('frame_state', 2.),
                                         ('map_snapshot', 5.), ('battery_state', 5.)):
                    sample = event['inputs'][name+'/'+sample_kind]
                    assert isinstance(sample['source_time'], (int, float)) and math.isfinite(sample['source_time'])
                    assert 0 <= now-sample['source_time'] <= sample['ttl_sec'] <= ttl, 'stale current handoff body source'
                    assert math.isclose(sample['age_sec'], now-sample['source_time'], abs_tol=1e-8)
            sample = event['inputs']['headquarters/fused_map_snapshot']
            assert 0 <= now-sample['source_time'] <= sample['ttl_sec'] <= 5., 'stale current handoff map'
            assert math.isclose(sample['age_sec'], now-sample['source_time'], abs_tol=1e-8)
            handoffs += 1
            robots[hint['robot']] = robots.get(hint['robot'], 0)+1
            pending = None
    return dict(enabled=enabled, retained_geometry_count=retained, current_handoff_count=handoffs,
                robots=robots, pending_geometry_at_stop=pending is not None,
                scope='Geometry preferences only; current trip, charge, body, action and native completion audits remain required')
