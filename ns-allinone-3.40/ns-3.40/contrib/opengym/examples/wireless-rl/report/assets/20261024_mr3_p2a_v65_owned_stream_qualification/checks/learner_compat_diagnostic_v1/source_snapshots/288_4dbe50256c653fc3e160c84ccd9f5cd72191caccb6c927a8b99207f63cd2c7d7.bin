"""Finite stop-path debt must not become an infinite terminal L1 budget."""
from fractions import Fraction

from test_mr3_reach_runtime_independent import Feed


def test_fixed_terminal_disk_allows_small_repeated_motion_after_finite_stop_horizon():
    feed = Feed().normal()
    feed.tick((0., 0.))
    origin = feed.r.backup_from
    # Every command below is independently fixed full zero. At most .009m/s
    # along each 20ms chord and <.2mm from either possible terminal anchor;
    # total L1 eventually exceeds D, while the finite H path does not.
    for index in range(820):
        feed.stage_next_raw(xy=(.00018 if index % 2 else 0., 0.), velocity=(.009, 0.))
        assert feed.r.synchronize(feed.now) is True
        feed.publish((0., 0.))
    assert feed.r.backup_from == origin
    assert feed.r.terminal_anchor is not None
    assert feed.r.cumulative_path_m > .144
    assert feed.r.backup_path_lower <= Fraction(18, 125)
    assert feed.r.fault is None


def test_inadequate_transition_reserve_can_only_preserve_the_original_safe_disk_turn():
    import copy
    from test_mr3_reach_runtime_independent import peer
    for turn in (-.2, .2):
        feed = Feed().disk()
        anchors = copy.deepcopy(feed.r.anchors)
        peers = {'tb2': peer('tb2', feed.now, (-.56, 0.)),
                 'tb3': peer('tb3', feed.now, (0., 3.))}
        result = feed.r.decide((.1, turn), feed.own(), peers, feed.now, feed.r.current_intent)
        assert result['output'] == [0., turn]
        assert result['reason'] == 'linear_brake_preserve_requested_turn'
        assert feed.r.role == 'D' and feed.r.signs == ()
        assert feed.r.anchors == anchors
        assert all(row['geometric_necessary'] for row in result['reach_pair_checks'].values())
        assert not all(row['geometric_necessary'] for row in
                       result['component_filter']['rejected_transition_checks'].values())
