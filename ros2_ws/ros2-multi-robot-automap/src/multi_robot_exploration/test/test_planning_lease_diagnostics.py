"""Diagnostics only copy abandoned inputs; source leases and owners stay intact."""
import base64
import copy
import json
from types import SimpleNamespace
import zlib

import numpy as np
import pytest

from multi_robot_exploration import control as c
from test_lazy_frontier_gain import mapping_snapshot_node


@pytest.mark.parametrize('rally', [False, True])
def test_abandoned_snapshot_preserves_maps_sources_and_rate_limits_without_motion(monkeypatch, rally):
    node, sent = mapping_snapshot_node()
    node.enable_rally = rally
    if not rally:
        node.initial_search_visits = None
        del node.initial_search_views
    node.planning_lease_diagnostics = {}
    initial = node.now()
    source_inputs = copy.deepcopy(node.input_freshness_details())
    deadline = min(sample['source_time'] + sample['ttl_sec']
                   for sample in source_inputs.values() if sample['source_time'] is not None)
    events = []
    node.consumed_publisher = SimpleNamespace(publish=lambda msg: events.append(json.loads(msg.data)))
    clock = [initial]
    node.now = lambda: clock[0]
    expired_at = [deadline + .01]
    def slow_candidates(*args, **kwargs):
        clock[0] = expired_at[0]
        return [], dict(frontier_groups=0, groups_with_viewpoints=0)
    monkeypatch.setattr(c, 'robot_candidate_assignments', slow_candidates)
    stamps = dict(node.robot_odom_received_at)
    for elapsed in (0., 1., 31.):
        clock[0] = initial
        expired_at[0] = deadline + .01 + elapsed
        c.HeadquartersControl.assign_idle_robots(node)
    assert not sent and not node.rally_charge_requested
    assert all(state == 'idle' for state in node.robot_states.values())
    assert node.robot_odom_received_at == stamps
    assert len(events) == 3 and [e['diagnostic_inputs'] is not None for e in events] == [True, False, True]
    for e in events:
        assert e['event_time'] > e['source_deadline_sec']
        assert e['inputs_at_start'] == c.input_freshness_at(source_inputs, initial)
        if e['diagnostic_inputs'] is not None:
            d = e['diagnostic_inputs']
            g = d['planning_map']
            raw = np.frombuffer(zlib.decompress(base64.b64decode(g['grid'])), dtype='<i2').reshape(g['shape'])
            np.testing.assert_array_equal(raw, node.map_data)
            assert g['source_time'] == source_inputs['headquarters/fused_map_snapshot']['source_time']
            assert d['robot_positions'] == {n: list(p) for n, p in node.robot_positions.items()}
            if not rally:
                assert d['initial_search_views'] == d['initial_search_visits'] == []
