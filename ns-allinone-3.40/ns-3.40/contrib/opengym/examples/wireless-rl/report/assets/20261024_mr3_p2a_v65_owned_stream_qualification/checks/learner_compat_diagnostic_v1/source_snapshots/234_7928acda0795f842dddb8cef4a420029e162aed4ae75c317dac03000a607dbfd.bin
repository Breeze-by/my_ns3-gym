"""Received local-odom activity cannot count map corrections or warmup."""

import copy

import pytest

from multi_robot_exploration.mr3_activity import ReceivedActivity, ROBOTS


def delivered(sequence, stamp, x=0., epoch="epoch-a", map_x=None):
    sec = int(stamp)
    nanosec = round((stamp - sec) * 1e9)
    return {"epoch": epoch, "sequence": sequence, "robots": [
        {"name": name, "epoch": epoch, "valid": True,
         "odom_source_stamp": stamp, "x": x if map_x is None else map_x, "y": 0.,
         "odometry": {
             "header": {"stamp": {"sec": sec, "nanosec": nanosec}, "frame_id": "odom"},
             "child_frame_id": "base_footprint",
             "pose": {"pose": {"position": {"x": x, "y": 0.}}},
         }}
        for name in ROBOTS]}


def test_release_excludes_warmup_and_first_post_release_point_only_anchors():
    tracker = ReceivedActivity("epoch-a")
    assert tracker.update(delivered(1, 1., 50.), 1.) is None
    tracker.start(2.)
    tracker.update(delivered(2, 1.9, 60.), 2.)
    assert tracker.snapshot("tb1")["estimated_path_m"] is None
    tracker.update(delivered(3, 2., 70.), 2.)
    tracker.update(delivered(4, 2.1, 70.4), 2.1)
    assert tracker.snapshot("tb1")["estimated_path_m"] == pytest.approx(.4)
    assert tracker.snapshot("tb1")["sample_count"] == 2


def test_duplicate_sequence_and_duplicate_or_older_odom_sources_cannot_add_motion():
    tracker = ReceivedActivity("epoch-a")
    tracker.start(1.)
    tracker.update(delivered(1, 1.), 1.)
    tracker.update(delivered(2, 1.1, .3), 1.1)
    saved = tracker.snapshot("tb1")
    assert tracker.update(delivered(2, 1.2, 50.), 1.2) is None
    tracker.update(delivered(3, 1.1, .3), 1.3)
    tracker.update(delivered(4, 1.05, 40.), 1.3)
    assert tracker.snapshot("tb1") == {**saved, "state_sequence": 4}
    tracker.update(delivered(5, 1.2, .4), 1.3)
    assert tracker.snapshot("tb1")["estimated_path_m"] == pytest.approx(.4)


def test_tf_map_loop_closure_changes_cannot_create_local_odometry_motion():
    tracker = ReceivedActivity("epoch-a")
    tracker.start(1.)
    tracker.update(delivered(1, 1., 0., map_x=0.), 1.)
    tracker.update(delivered(2, 1.1, 0., map_x=50.), 1.1)
    assert tracker.snapshot("tb1")["estimated_path_m"] == 0.
    tracker.update(delivered(3, 1.2, .2, map_x=-80.), 1.2)
    assert tracker.snapshot("tb1")["estimated_path_m"] == pytest.approx(.2)


@pytest.mark.parametrize("fault", ["missing", "future", "nonfinite", "stamp_conflict"])
def test_bad_source_is_visible_and_cannot_inflate_estimated_path(fault):
    tracker = ReceivedActivity("epoch-a")
    tracker.start(1.)
    tracker.update(delivered(1, 1.), 1.)
    state = delivered(2, 1.1, 5.)
    robot = state["robots"][0]
    if fault == "missing":
        del robot["odometry"]
    elif fault == "future":
        state = delivered(2, 1.2, 5.)
    elif fault == "nonfinite":
        robot["odometry"]["pose"]["pose"]["position"]["x"] = float("nan")
    else:
        robot["odom_source_stamp"] = 1.
    tracker.update(state, 1.1)
    assert tracker.snapshot("tb1")["estimated_path_m"] == 0.
    assert not tracker.snapshot("tb1")["path_observation_complete"]


def test_conflicting_same_source_and_changed_frame_are_not_counted_as_motion():
    tracker = ReceivedActivity("epoch-a")
    tracker.start(1.)
    tracker.update(delivered(1, 1.), 1.)
    tracker.update(delivered(2, 1., 100.), 1.1)
    changed = delivered(3, 1.1, 100.)
    for robot in changed["robots"]:
        robot["odometry"]["header"]["frame_id"] = "other_odom"
    tracker.update(changed, 1.1)
    assert tracker.snapshot("tb1")["estimated_path_m"] == 0.
    assert not tracker.snapshot("tb1")["path_observation_complete"]


def test_delivery_gaps_remain_explicit_and_do_not_invent_missing_curves():
    tracker = ReceivedActivity("epoch-a")
    tracker.start(1.)
    tracker.update(delivered(1, 1.), 1.)
    tracker.update(delivered(2, 2., .2), 2.)
    assert tracker.snapshot("tb1")["estimated_path_m"] == pytest.approx(.2)
    assert not tracker.snapshot("tb1")["path_observation_complete"]


def test_new_epoch_resets_history_and_old_epoch_deliveries_are_ignored():
    old = ReceivedActivity("epoch-a")
    old.start(1.)
    old.update(delivered(1, 1.), 1.)
    old.update(delivered(2, 1.1, 2.), 1.1)
    tracker = ReceivedActivity("epoch-b")
    tracker.start(1.)
    assert tracker.update(delivered(3, 1.2, 20.), 1.2) is None
    assert tracker.snapshot("tb1")["estimated_path_m"] is None
    state = delivered(1, 1., epoch="epoch-b")
    original = copy.deepcopy(state)
    tracker.update(state, 1.)
    assert state == original
    assert tracker.snapshot("tb1")["estimated_path_m"] == 0.
    tracker.start(1.)
    with pytest.raises(ValueError):
        tracker.start(2.)
