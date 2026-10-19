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
