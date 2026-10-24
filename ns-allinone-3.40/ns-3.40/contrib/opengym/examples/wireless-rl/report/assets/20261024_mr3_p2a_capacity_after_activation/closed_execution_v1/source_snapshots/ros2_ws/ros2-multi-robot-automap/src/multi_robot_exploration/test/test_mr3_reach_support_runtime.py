"""Artificial real-tracker feeds for the explicit pair-certificate selection."""
import copy
from fractions import Fraction as Q
import json

import pytest
from multi_robot_exploration import mr3_reach_geometry as geometry
from multi_robot_exploration import mr3_reach_runtime as reach
from test_mr3_reach_runtime_independent import Feed, peer


def feed_with_rule(monkeypatch, rule):
    original = reach.ReachTracker
    with monkeypatch.context() as context:
        context.setattr(reach, 'ReachTracker', lambda epoch, robot:
                        original(epoch, robot, reach_geometry_rule=rule))
        return Feed()


def tight_peers(feed):
    return {'tb2': peer('tb2', feed.now, (-.45, -.45)),
            'tb3': peer('tb3', feed.now, (-.45, .45))}


@pytest.mark.parametrize('rule', [None, True, False, 0, 1, '', 'legacy', 'cone-support-v1', []])
def test_unknown_or_nonstring_rules_fail_before_tracker_is_usable(rule):
    with pytest.raises(ValueError, match='reach_geometry_rule'):
        reach.ReachTracker('epoch', 'tb1', reach_geometry_rule=rule)


def test_rule_contract_pair_is_strict_and_cannot_hot_switch():
    assert reach.validate_reach_geometry_rule('binary-cone-v1', safety_contract='legacy') == 'binary-cone-v1'
    with pytest.raises(ValueError, match='requires explicit'):
        reach.validate_reach_geometry_rule('cone-support-v2', safety_contract='legacy')
    tracker = reach.ReachTracker('epoch', 'tb1', reach_geometry_rule='cone-support-v2')
    with pytest.raises(AttributeError):
        tracker.reach_geometry_rule = 'binary-cone-v1'
    assert tracker.status()['reach_geometry_rule'] == 'cone-support-v2'
    assert 'reach_geometry_rule' not in reach.ReachTracker('epoch', 'tb1').status()


def test_default_and_explicit_v1_pair_proofs_preserve_original_complete_json():
    feed = Feed().disk()
    own, peers = feed.own(), feed.peers()
    default = reach.pair_checks(own, peers, feed.now)
    explicit = reach.pair_checks(own, peers, feed.now, reach_geometry_rule='binary-cone-v1')
    expected = {}
    for name, other in peers.items():
        ox, oy = reach.raw_xy(own['odometry'])
        px, py = reach.raw_xy(other['odometry'])
        expected[name] = geometry.pair_certificate(
            (geometry.exact(other['x'])-geometry.exact(own['x']),
             geometry.exact(other['y'])-geometry.exact(own['y'])),
            (px-ox, py-oy), (0, 0), reach.reach_for(own, feed.now), reach.reach_for(other, feed.now),
            legacy_hard_gates_passed=True, common_world_odom_calibrated=True)
    assert json.dumps(default, sort_keys=True) == json.dumps(explicit, sort_keys=True) == json.dumps(expected, sort_keys=True)
    assert all(row['schema'] == 'mr3-reach-geometric-necessary-v1' for row in default.values())


def test_v1_rejects_original_tight_cone_transition_and_preserves_requested_turn(monkeypatch):
    feed = feed_with_rule(monkeypatch, 'binary-cone-v1').disk()
    feed.peers = lambda: tight_peers(feed)
    result = feed.tick((.1, .2))
    assert result['reason'] == 'linear_brake_preserve_requested_turn'
    assert result['output'] == [0., .2] and feed.r.role == 'D'
    assert all(row['schema'] == 'mr3-reach-geometric-necessary-v1'
               for row in result['reach_pair_checks'].values())


def test_v2_current_and_prospective_checks_use_same_explicit_rule_and_real_transition(monkeypatch):
    feed = feed_with_rule(monkeypatch, 'cone-support-v2').disk()
    feed.peers = lambda: tight_peers(feed)
    seen = []
    original = reach.pair_checks

    def spy(own, peers, clock, *, reach_geometry_rule='binary-cone-v1'):
        seen.append((reach_geometry_rule, own['safety']['intent']['role']))
        return original(own, peers, clock, reach_geometry_rule=reach_geometry_rule)

    monkeypatch.setattr(reach, 'pair_checks', spy)
    first = feed.tick((.1, 0.))
    assert seen == [('cone-support-v2', 'D'), ('cone-support-v2', 'X')]
    assert first['reason'] == 'announce_transition_zero' and first['output'] == [0., 0.]
    assert feed.r.role == 'X'
    assert all(row['reach_geometry_rule'] == 'cone-support-v2'
               and row['geometric_necessary'] is True for row in first['reach_pair_checks'].values())
    seen.clear()
    second = feed.tick((.1, 0.))
    assert seen == [('cone-support-v2', 'X')]
    assert second['reason'] == 'reach_clear' and second['output'] == [.1, 0.]
    assert feed.r.actual_normal is False  # Storage alone cannot prove actual takeover.


def test_v2_does_not_borrow_map_distance_to_hide_bad_raw_pair(monkeypatch):
    feed = feed_with_rule(monkeypatch, 'cone-support-v2').disk()
    peers = {'tb2': peer('tb2', feed.now, (.5, 0.), map_xy=(3., 0.)),
             'tb3': peer('tb3', feed.now, (0., 3.))}
    result = feed.r.decide((.1, .2), feed.own(), peers, feed.now, feed.r.current_intent)
    assert result['output'] == [0., 0.]
    assert result['allow'] is False
    bad = result['reach_pair_checks']['tb2']
    assert bad['map']['separation_sufficient_under_declared_sets'] is True
    assert bad['raw']['separation_sufficient_under_declared_sets'] is False


def test_v2_preserves_existing_model_latch_and_intent_schema(monkeypatch):
    feed = feed_with_rule(monkeypatch, 'cone-support-v2').disk()
    value = copy.deepcopy(feed.r.current_intent)
    assert value['schema'] == 'mr3-safety-intent-v1'
    assert 'reach_geometry_rule' not in value
    peers = feed.peers()
    peers['tb2']['epoch'] = 'other-epoch'
    with pytest.raises(ValueError):
        feed.r.decide((.1, 0.), feed.own(), peers, feed.now, feed.r.current_intent)
    assert feed.r.fault is not None
