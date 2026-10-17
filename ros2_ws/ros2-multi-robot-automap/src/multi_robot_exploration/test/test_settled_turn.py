"""Received-only settled-turn qualification, drift reserve and failure regressions."""

import copy
import hashlib
import json
import math

import pytest

from multi_robot_exploration.mr3_motion_safety import (
    REST_SPEED_BOUND, SETTLE_PUBLICATION_SEC, SettledTurnTracker, guard_motion,
    valid_settled_turn,
)


def odom(source_ns, x=.00024, y=0.):
    return {"header": {"stamp": {"sec": source_ns // 10**9, "nanosec": source_ns % 10**9},
                       "frame_id": "odom"}, "child_frame_id": "base_footprint",
            "pose": {"pose": {"position": {"x": 0., "y": 0., "z": 0.}}},
            "twist": {"twist": {"linear": {"x": x, "y": y, "z": 0.}}}}


def ready_tracker():
    tracker = SettledTurnTracker()
    tracker.output(0., 1_000_000_000, 1)
    for sequence, source in enumerate((1_950_000_000, 1_970_000_000, 1_990_000_000), 1):
        tracker.observe(odom(source), sequence)
    return tracker


def states(tracker=None, distance=.84):
    own = {"name": "tb1", "epoch": "e", "valid": True, "x": 0., "y": 0.,
           "yaw": 0., "v": .00024, "w": -.13, "source_stamp": 1.85,
           "odom_source_stamp": 1.99, "tf_source_stamp": 1.85,
           "planar_speed_mps": .00024,
           "settled_turn": tracker.certificate(2_000_000_000) if tracker else None}
    peers = {name: {**own, "name": name, "x": x, "y": y, "v": 0., "w": 0.,
                    "source_stamp": 1.85, "settled_turn": None}
             for name, x, y in (("tb2", distance, 0.), ("tb3", 4., 4.))}
    return own, peers


def test_qualification_requires_three_later_fresh_sources_and_exact_payload_hash():
    tracker = SettledTurnTracker()
    tracker.output(0., 1_000_000_000, 1)
    assert SETTLE_PUBLICATION_SEC == pytest.approx(.94)
    for sequence, source in enumerate((1_900_000_000, 1_950_000_000, 1_970_000_000), 1):
        tracker.observe(odom(source), sequence)
    assert tracker.certificate(2_000_000_000) is None
    payload = odom(1_990_000_000)
    tracker.observe(payload, 4)
    certificate = tracker.certificate(2_000_000_000)
    assert certificate["samples"][-1]["odom_sha256"] == hashlib.sha256(json.dumps(
        payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
    own, _ = states(tracker)
    assert valid_settled_turn(own, 2.)


def test_real_tiny_residual_deadlock_needs_positive_finite_drift_reserve():
    own, peers = states()
    original = guard_motion([0., -.8], own, peers, 2., "e")
    assert original["reason"] == "peer_braking_nonclosing" and not original["allow"]
    own, peers = states(ready_tracker())
    decision = guard_motion([0., -.8], own, peers, 2., "e")
    assert decision["output"] == [0., -.8]
    assert decision["reason"] == "settled_turn_drift_reserve"
    check = decision["settled_turn_check"]
    assert check["own_drift_reserve_m"] == pytest.approx(.0078)
    assert check["peer_braking_reserve_m"] == pytest.approx(.144)
    assert check["required_body_margin_m"] == pytest.approx(.1518)
    # The original measured-motion direction checks remain in the diagnostic.
    assert decision["near_peer_checks"][0]["direction_checks"]
    own, peers = states(ready_tracker(), distance=.75)
    assert guard_motion([0., -.8], own, peers, 2., "e")["output"] == [0., 0.]


def test_mixed_filter_retains_requested_turn_only_and_never_authorizes_translation():
    own, peers = states(ready_tracker())
    decision = guard_motion([.26, -.8], own, peers, 2., "e")
    assert decision["output"] == [0., -.8]
    assert decision["reason"] == "linear_brake_preserve_requested_turn"
    assert decision["component_filter"]["rotation_check"]["reason"] == "settled_turn_drift_reserve"
    assert guard_motion([.26, 0.], own, peers, 2., "e")["output"] == [0., 0.]


@pytest.mark.parametrize("fault", ["epoch", "stale", "body", "speed", "command", "nonfinite"])
def test_settled_certificate_never_bypasses_original_invalid_input_or_body_gate(fault):
    own, peers = states(ready_tracker())
    command = [0., -.8]
    if fault == "epoch":
        own["epoch"] = "old"
    elif fault == "stale":
        peers["tb2"]["source_stamp"] = 1.
    elif fault == "body":
        peers["tb2"]["x"] = .49
    elif fault == "speed":
        own["v"] = .31
    elif fault == "command":
        command = [0., -math.nextafter(math.nextafter(.8, math.inf), math.inf)]
    else:
        own["x"] = math.nan
    assert guard_motion(command, own, peers, 2., "e")["output"] == [0., 0.]


@pytest.mark.parametrize("fault", ["few", "duplicate", "too_early", "stale", "future",
                                   "speed", "hash", "source", "sequence", "missing_odom"])
def test_certificate_rejects_incomplete_forged_or_stale_rest_evidence(fault):
    own, _ = states(ready_tracker())
    value = own["settled_turn"]
    if fault == "few":
        value["samples"].pop()
    elif fault == "duplicate":
        value["samples"][1] = copy.deepcopy(value["samples"][0])
    elif fault == "too_early":
        value["zero_since_ns"] = 1_050_000_000
    elif fault == "stale":
        for sample in value["samples"]:
            sample["source_ns"] -= 150_000_000
    elif fault == "future":
        value["samples"][-1]["source_ns"] = 2_010_000_000
    elif fault == "speed":
        own["planar_speed_mps"] = math.nextafter(.01, math.inf)
    elif fault == "hash":
        value["samples"][0]["odom_sha256"] = "z" * 64
    elif fault == "source":
        own["odom_source_stamp"] = 1.98
    elif fault == "sequence":
        value["samples"][1]["input_sequence"] = 1
    else:
        del own["odom_source_stamp"]
    assert not valid_settled_turn(own, 2.)


def test_zero_history_and_three_samples_reset_on_any_nonzero_final_output():
    tracker = ready_tracker()
    tracker.activate(2_000_000_000)
    tracker.output(.000001, 2_000_000_000, 2)
    assert tracker.active_since_ns is None and tracker.zero_since_ns is None
    assert tracker.certificate(2_000_000_000) is None
    tracker.output(0., 2_020_000_000, 3)
    tracker.observe(odom(2_030_000_000), 4)
    assert tracker.certificate(2_040_000_000) is None
    assert SettledTurnTracker().certificate(2_040_000_000) is None


@pytest.mark.parametrize("fault", [
    "speed", "lateral_speed", "gap", "stale", "conflict", "backward"])
def test_active_model_breach_is_reported_before_qualification_can_be_cleared(fault):
    tracker = ready_tracker()
    tracker.activate(2_000_000_000)
    with pytest.raises(ValueError):
        if fault == "speed":
            speed = math.nextafter(REST_SPEED_BOUND, math.inf)
            tracker.observe(odom(2_010_000_000, x=speed), 4)
        elif fault == "lateral_speed":
            tracker.observe(odom(2_010_000_000, x=0., y=.0101), 4)
        elif fault == "gap":
            tracker.observe(odom(2_100_000_001), 4)
        elif fault == "stale":
            tracker.certificate(2_090_000_001)
        elif fault == "conflict":
            tracker.observe(odom(1_990_000_000, x=.00025), 4)
        else:
            tracker.observe(odom(1_980_000_000), 4)
    assert tracker.active_since_ns == 2_000_000_000


def test_identical_source_duplicate_does_not_fabricate_third_sample():
    tracker = SettledTurnTracker()
    tracker.output(0., 1_000_000_000, 1)
    payload = odom(1_950_000_000)
    for sequence in range(1, 4):
        tracker.observe(payload, sequence)
    assert tracker.certificate(2_000_000_000) is None


def test_future_callback_source_is_retained_but_never_consumed_before_its_clock():
    tracker = ready_tracker()
    tracker.observe(odom(2_010_000_000), 4)
    assert tracker.certificate(2_000_000_000) is None
    # New fresh sources must reconstruct qualification after an unavailable phase.
    tracker.observe(odom(2_030_000_000), 5)
    tracker.observe(odom(2_050_000_000), 6)
    tracker.observe(odom(2_070_000_000), 7)
    assert tracker.certificate(2_080_000_000) is not None


def test_repeated_grants_do_not_refresh_entire_zero_segment_path_budget():
    tracker = ready_tracker()
    tracker.activate(2_000_000_000)
    for index in range(1, 41):
        payload = odom(1_990_000_000 + index * 20_000_000)
        payload["pose"]["pose"]["position"]["x"] = index * .0001
        tracker.observe(payload, index + 3)
    tracker.output(0., 2_800_000_000, 2)
    tracker.activate(2_800_000_000)
    assert tracker.active_since_ns == 2_000_000_000
    assert tracker.active_path_m == pytest.approx(.004)
    # Return toward the anchor: net displacement is small, total travel is not.
    with pytest.raises(ValueError, match="total drift budget"):
        for index in range(1, 41):
            payload = odom(2_790_000_000 + index * 20_000_000)
            payload["pose"]["pose"]["position"]["x"] = .004 - index * .0001
            tracker.observe(payload, index + 43)
    assert tracker.active_path_m > .0078


def test_low_reported_twist_cannot_hide_position_chord_speed_violation():
    tracker = ready_tracker()
    tracker.activate(2_000_000_000)
    payload = odom(2_010_000_000, x=0.)
    payload["pose"]["pose"]["position"]["x"] = .00021
    with pytest.raises(ValueError, match="chord speed bound"):
        tracker.observe(payload, 4)


def test_task_release_excludes_prewarm_history_before_initial_driver_storage_barrier():
    tracker = ready_tracker()
    tracker.release(2_000_000_000)
    assert tracker.zero_since_ns == 2_000_000_000
    assert tracker.certificate(2_000_000_000) is None
    for sequence, source in enumerate((2_950_000_000, 2_970_000_000, 2_990_000_000), 4):
        tracker.observe(odom(source), sequence)
    assert tracker.certificate(3_000_000_000) is not None
    with pytest.raises(ValueError, match="release"):
        tracker.release(3_000_000_000)


@pytest.mark.parametrize("clock,sequence", [
    (1_999_999_999, 3), (2_000_000_000, 2), (2_000_000_000, True)])
def test_output_regressions_reject_before_resetting_active_model(clock, sequence):
    tracker = ready_tracker()
    tracker.output(0., 2_000_000_000, 2)
    tracker.activate(2_000_000_000)
    with pytest.raises(ValueError):
        tracker.output(.26, clock, sequence)
    assert tracker.active_since_ns == 2_000_000_000
