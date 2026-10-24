"""Exercise delivered commands and real terminal ownership without ROS."""

import math

import pytest

from multi_robot_exploration.mr3_protocol import GoalDispatcher


def protocol():
    events = []
    return GoalDispatcher("episode-a", events.append), events


def submit(dispatcher, choice="GOAL", now=0.0, sequence=1, robot="tb1", **kwargs):
    goal = kwargs.pop("goal", {"x": 1.0, "y": 2.0} if choice == "GOAL" else None)
    return dispatcher.submit(
        robot, choice, now, observation_version=7, command_id=sequence,
        expires_at=kwargs.pop("expires_at", now + 2), goal=goal, **kwargs,
    )


def start(dispatcher, robot="tb1", now=0.0, sequence=1):
    assert submit(dispatcher, robot=robot, now=now, sequence=sequence) == "sent"
    goal_id = dispatcher.navigation()[robot]["goal_id"]
    assert dispatcher.on_accept(robot, goal_id, True, now) == "active"
    return goal_id


def renew_until(dispatcher, goal_id, end, robot="tb1", start_time=1):
    for now in range(start_time, end + 1):
        assert dispatcher.renew(robot, goal_id, dispatcher.epoch, now, now + 2) == "renewed"


def test_keep_never_submits_goal_and_navigation_is_detached():
    dispatcher, events = protocol()
    goal_id = start(dispatcher)
    for now in (0.5, 1.0, 1.5):
        assert submit(dispatcher, "KEEP", now, sequence=int(now * 2 + 1)) == "kept"
    assert [event["type"] for event in events] == ["send_goal"]
    observed = dispatcher.navigation()
    assert observed["tb1"]["goal_id"] == goal_id == "episode-a:tb1:1"
    assert observed["tb1"]["commitment_until"] == 5.0
    assert observed["tb1"]["observation_version"] == 7
    observed["tb1"]["goal_x"] = 100
    assert dispatcher.navigation()["tb1"]["goal_x"] == 1.0


def test_minimum_commitment_blocks_discretionary_switch_and_wait():
    dispatcher, events = protocol()
    goal_id = start(dispatcher)
    renew_until(dispatcher, goal_id, 4)
    assert submit(dispatcher, now=4.5, sequence=2) == "commitment_locked"
    assert submit(dispatcher, "WAIT", 4.5, 3) == "commitment_locked"
    assert len(events) == 1
    assert submit(dispatcher, "WAIT", 5.0, 4) == "waiting"
    assert [event["type"] for event in events] == ["send_goal", "cancel_goal"]


def test_commitment_starts_on_acceptance_not_transmission():
    dispatcher, _ = protocol()
    assert submit(dispatcher) == "sent"
    goal_id = dispatcher.navigation()["tb1"]["goal_id"]
    dispatcher.renew("tb1", goal_id, dispatcher.epoch, 1, 3)
    dispatcher.on_accept("tb1", goal_id, True, 1.5)
    assert dispatcher.navigation()["tb1"]["commitment_until"] == 6.5


def test_switch_sends_only_after_old_terminal_not_cancel_ack():
    dispatcher, events = protocol()
    old = start(dispatcher)
    renew_until(dispatcher, old, 5)
    assert submit(dispatcher, now=5.0, sequence=2, goal={"x": 3, "y": 4}) == "switch_pending"
    assert len([event for event in events if event["type"] == "send_goal"]) == 1
    assert dispatcher.on_cancel_response("tb1", old, True, 5.1) == "awaiting_terminal"
    assert not dispatcher.closed
    assert len([event for event in events if event["type"] == "send_goal"]) == 1
    assert dispatcher.on_result("tb1", old, 5, 5.2) == "replacement_sent"
    assert dispatcher.navigation()["tb1"]["goal_id"] == "episode-a:tb1:2"
    assert dispatcher.navigation()["tb1"]["goal_x"] == 3
    assert [event["type"] for event in events] == [
        "send_goal", "cancel_goal", "cancel_response", "protocol_terminal", "send_goal",
    ]
    assert dispatcher.on_result("tb1", old, 5, 5.3) == "stale_goal"
    assert dispatcher.navigation()["tb1"]["goal_id"] == "episode-a:tb1:2"


def test_switch_ttl_is_not_refreshed_while_waiting_for_terminal():
    dispatcher, events = protocol()
    old = start(dispatcher)
    renew_until(dispatcher, old, 5)
    submit(dispatcher, now=5, sequence=2)
    assert dispatcher.on_result("tb1", old, "CANCELED", 7) == "replacement_expired"
    assert dispatcher.closed and not dispatcher.failed
    assert events[-1]["type"] == "pending_goal_expired"
    assert len([event for event in events if event["type"] == "send_goal"]) == 1


def test_wait_during_cancel_discards_pending_replacement():
    dispatcher, events = protocol()
    old = start(dispatcher)
    renew_until(dispatcher, old, 5)
    submit(dispatcher, now=5, sequence=2)
    assert submit(dispatcher, "WAIT", 5.1, 3) == "waiting"
    assert dispatcher.on_result("tb1", old, 5, 5.2) == "terminal"
    assert dispatcher.closed
    assert len([event for event in events if event["type"] == "cancel_goal"]) == 1
    assert len([event for event in events if event["type"] == "send_goal"]) == 1


def test_pending_acceptance_wait_cancels_late_accepted_goal():
    dispatcher, events = protocol()
    submit(dispatcher)
    goal_id = dispatcher.navigation()["tb1"]["goal_id"]
    assert submit(dispatcher, "WAIT", 0.5, 2) == "waiting"
    assert not [event for event in events if event["type"] == "cancel_goal"]
    assert dispatcher.on_accept("tb1", goal_id, True, 3) == "canceling"
    assert dispatcher.navigation()["tb1"]["phase"] == "canceling"
    assert not dispatcher.failed
    assert dispatcher.on_result("tb1", goal_id, 5, 3.1) == "terminal"
    assert dispatcher.closed


def test_pending_acceptance_and_canceling_lock_goal_ownership():
    dispatcher, events = protocol()
    submit(dispatcher)
    goal_id = dispatcher.navigation()["tb1"]["goal_id"]
    assert submit(dispatcher, now=0.1, sequence=2) == "ownership_locked"
    dispatcher.on_accept("tb1", goal_id, True, 0.1)
    renew_until(dispatcher, goal_id, 5)
    submit(dispatcher, "WAIT", 5.1, 3)
    assert submit(dispatcher, now=5.2, sequence=4) == "ownership_locked"
    assert len([event for event in events if event["type"] == "send_goal"]) == 1


def test_acceptance_timeout_keeps_unknown_owner_and_late_acceptance_cancels():
    dispatcher, events = protocol()
    submit(dispatcher)
    goal_id = dispatcher.navigation()["tb1"]["goal_id"]
    renew_until(dispatcher, goal_id, 9)
    dispatcher.tick(10)
    state = dispatcher.navigation()["tb1"]
    assert state["phase"] == "unknown" and state["owned"]
    assert state["failure"] == "navigation_response_timeout"
    assert dispatcher.failed and not dispatcher.closed
    assert submit(dispatcher, now=10, sequence=2) == "stopped"
    assert dispatcher.on_accept("tb1", goal_id, True, 11) == "canceling"
    assert dispatcher.on_result("tb1", goal_id, 5, 11.1) == "terminal"
    assert dispatcher.closed and dispatcher.failed
    assert len([event for event in events if event["type"] == "send_goal"]) == 1
    assert len([event for event in events if event["type"] == "protocol_failure"]) == 1


def test_late_rejection_closes_unknown_ownership_without_clearing_failure():
    dispatcher, _ = protocol()
    submit(dispatcher)
    goal_id = dispatcher.navigation()["tb1"]["goal_id"]
    renew_until(dispatcher, goal_id, 9)
    dispatcher.tick(10)
    assert dispatcher.on_accept("tb1", goal_id, False, 11) == "rejected"
    assert dispatcher.closed and dispatcher.failed
    assert dispatcher.navigation()["tb1"]["failure"] == "navigation_response_timeout"


@pytest.mark.parametrize("cancel_accepted,reason", [
    (True, "navigation_cancel_timeout"), (False, "navigation_cancel_rejected"),
    (None, "navigation_cancel_timeout"),
])
def test_cancel_rpc_requires_real_terminal_even_after_positive_ack(cancel_accepted, reason):
    dispatcher, _ = protocol()
    goal_id = start(dispatcher)
    renew_until(dispatcher, goal_id, 5)
    submit(dispatcher, "WAIT", 5, 2)
    if cancel_accepted is not None:
        dispatcher.on_cancel_response("tb1", goal_id, cancel_accepted, 5.1)
    dispatcher.tick(15)
    state = dispatcher.navigation()["tb1"]
    assert state["phase"] == "unknown" and state["goal_id"] == goal_id
    assert state["failure"] == reason
    assert dispatcher.on_result("tb1", goal_id, 5, 16) == "terminal"
    assert dispatcher.closed and dispatcher.failed


def test_rejected_cancel_can_race_with_success_without_false_failure():
    dispatcher, _ = protocol()
    goal_id = start(dispatcher)
    renew_until(dispatcher, goal_id, 5)
    submit(dispatcher, "WAIT", 5, 2)
    dispatcher.on_cancel_response("tb1", goal_id, False, 5.1)
    dispatcher.on_result("tb1", goal_id, 4, 5.2)
    assert dispatcher.closed and not dispatcher.failed


def test_execution_timeout_does_not_inherit_renewal_or_command_ttl():
    dispatcher, events = protocol()
    goal_id = start(dispatcher)
    renew_until(dispatcher, goal_id, 59)
    dispatcher.tick(60)
    state = dispatcher.navigation()["tb1"]
    assert state["failure"] == "navigation_execution_timeout"
    assert state["phase"] == "canceling" and not dispatcher.closed
    assert len([event for event in events if event["type"] == "cancel_goal"]) == 1


@pytest.mark.parametrize("accepted", [False, True])
def test_expired_goal_lease_stops_even_during_acceptance(accepted):
    dispatcher, events = protocol()
    submit(dispatcher)
    goal_id = dispatcher.navigation()["tb1"]["goal_id"]
    if accepted:
        dispatcher.on_accept("tb1", goal_id, True, 0)
    dispatcher.tick(2)
    assert dispatcher.failed and not dispatcher.closed
    assert dispatcher.navigation()["tb1"]["failure"] == "goal_lease_expired"
    assert dispatcher.renew("tb1", goal_id, dispatcher.epoch, 2.1, 4.1) == "stopping"
    if not accepted:
        assert dispatcher.on_accept("tb1", goal_id, True, 2.1) == "canceling"
    assert len([event for event in events if event["type"] == "cancel_goal"]) == 1


def test_keep_and_duplicate_renewal_cannot_hide_expired_transport_lease():
    dispatcher, _ = protocol()
    goal_id = start(dispatcher)
    assert dispatcher.renew("tb1", goal_id, dispatcher.epoch, 0.2, 2.2) == "renewed"
    assert dispatcher.renew("tb1", goal_id, dispatcher.epoch, 0.4, 2.2) == "stale_renewal"
    assert submit(dispatcher, "KEEP", 1, 2) == "kept"
    dispatcher.tick(2.2)
    assert dispatcher.failed


def test_safety_stop_bypasses_commitment_and_stops_all_three_without_replacement():
    dispatcher, events = protocol()
    ids = {robot: start(dispatcher, robot=robot) for robot in dispatcher.robots}
    dispatcher.safety_stop(0.1, "evaluator_complete")
    assert dispatcher.stopped and not dispatcher.failed and not dispatcher.closed
    assert len([event for event in events if event["type"] == "cancel_goal"]) == 3
    dispatcher.safety_stop(0.2, "evaluator_complete")
    assert len([event for event in events if event["type"] == "cancel_goal"]) == 3
    for robot, goal_id in ids.items():
        dispatcher.on_result(robot, goal_id, 5, 0.3)
    assert dispatcher.closed and not dispatcher.failed


def test_safety_stop_does_not_hide_already_expired_lease():
    dispatcher, _ = protocol()
    start(dispatcher)
    dispatcher.safety_stop(2.1, "evaluator_complete")
    assert dispatcher.failed
    assert dispatcher.navigation()["tb1"]["failure"] == "goal_lease_expired"


def test_one_protocol_failure_cancels_team_and_rejection_is_explicit_terminal():
    dispatcher, events = protocol()
    first = start(dispatcher)
    submit(dispatcher, robot="tb2")
    second = dispatcher.navigation()["tb2"]["goal_id"]
    assert dispatcher.on_accept("tb2", second, False, 0.1) == "rejected"
    assert dispatcher.failed and dispatcher.navigation()["tb2"]["phase"] == "failed"
    assert dispatcher.navigation()["tb1"]["phase"] == "canceling"
    assert events[-1]["type"] == "cancel_goal" and events[-1]["goal_id"] == first


def test_command_epoch_sequence_duplicate_and_expiry_are_idempotent():
    dispatcher, events = protocol()
    assert submit(dispatcher, command_epoch="old") == "stale_epoch"
    assert submit(dispatcher) == "sent"
    assert submit(dispatcher, now=0.1, expires_at=2) == "duplicate"
    assert submit(dispatcher, now=0.1, expires_at=2, goal={"x": 2, "y": 3}) == "command_id_conflict"
    assert submit(dispatcher, "KEEP", 0.2, 3) == "kept"
    assert submit(dispatcher, "KEEP", 0.3, 2) == "stale_command"
    assert submit(dispatcher, "KEEP", 0.4, 4, expires_at=0.4) == "expired"
    assert submit(dispatcher, "KEEP", 0.5, 4, expires_at=0.4) == "duplicate"
    assert len(events) == 1


@pytest.mark.parametrize("kwargs,expected", [
    ({"expires_at": 3}, "invalid_ttl"),
    ({"created_at": 0.1}, "invalid_ttl"),
    ({"expires_at": float("inf")}, "invalid_ttl"),
    ({"goal": {"x": float("nan"), "y": 0}}, "invalid_goal"),
])
def test_invalid_commands_never_reach_action_client(kwargs, expected):
    dispatcher, events = protocol()
    assert submit(dispatcher, **kwargs) == expected
    assert dispatcher.closed and not dispatcher.failed and not events


def test_reset_requires_real_closure_and_rejects_late_epoch_callbacks():
    dispatcher, _ = protocol()
    old = start(dispatcher)
    dispatcher.safety_stop(0.1, "reset_requested")
    with pytest.raises(RuntimeError, match="unresolved"):
        dispatcher.reset("episode-b")
    dispatcher.on_result("tb1", old, 5, 0.2)
    dispatcher.reset("episode-b")
    assert dispatcher.closed and not dispatcher.stopped and not dispatcher.failed
    new = start(dispatcher)
    assert new != old
    assert dispatcher.on_accept("tb1", old, True, 0.1) == "stale_goal"
    assert dispatcher.on_result("tb1", old, 4, 0.1) == "stale_goal"
    assert dispatcher.renew("tb1", old, "episode-a", 0.1, 2.1) == "stale_epoch"
    assert submit(dispatcher, now=0.1, sequence=2, command_epoch="episode-a") == "stale_epoch"
    assert dispatcher.navigation()["tb1"]["goal_id"] == new


def test_clock_reversal_is_not_silently_treated_as_same_episode():
    dispatcher, _ = protocol()
    dispatcher.tick(1)
    with pytest.raises(ValueError, match="clock reversed"):
        dispatcher.tick(0.5)


def test_nonterminal_result_preserves_unknown_owner_and_abort_is_terminal_failure():
    dispatcher, _ = protocol()
    goal_id = start(dispatcher)
    assert dispatcher.on_result("tb1", goal_id, 2, 0.1) == "nonterminal"
    assert dispatcher.navigation()["tb1"]["phase"] == "unknown"
    assert dispatcher.failed and not dispatcher.closed
    dispatcher.on_result("tb1", goal_id, 6, 0.2)
    assert dispatcher.closed and dispatcher.failed


def test_terminal_result_during_commitment_releases_owner():
    dispatcher, _ = protocol()
    goal_id = start(dispatcher)
    dispatcher.on_result("tb1", goal_id, 4, 0.5)
    assert dispatcher.closed and not dispatcher.failed
    assert submit(dispatcher, now=0.6, sequence=2) == "sent"


def test_endpoint_fault_during_acceptance_latches_failure_and_cancels_late_accept():
    dispatcher, events = protocol()
    submit(dispatcher)
    goal_id = dispatcher.navigation()["tb1"]["goal_id"]
    dispatcher.fail("tb1", .1, "accept_rpc_error")
    assert dispatcher.failed and not dispatcher.closed
    assert dispatcher.navigation()["tb1"]["failure"] == "accept_rpc_error"
    assert dispatcher.on_accept("tb1", goal_id, True, .2) == "canceling"
    assert dispatcher.failed and not dispatcher.closed
    dispatcher.on_result("tb1", goal_id, 5, .3)
    assert dispatcher.closed and dispatcher.failed
    assert len([event for event in events if event["type"] == "protocol_failure"]) == 1


def test_endpoint_fault_during_execution_preserves_ownership_until_real_terminal():
    dispatcher, events = protocol()
    goal_id = start(dispatcher)
    dispatcher.fail("tb1", .1, "result_rpc_error")
    state = dispatcher.navigation()["tb1"]
    assert state["phase"] == "canceling" and state["goal_id"] == goal_id
    assert dispatcher.failed and not dispatcher.closed
    dispatcher.on_cancel_response("tb1", goal_id, True, .2)
    assert not dispatcher.closed
    dispatcher.on_result("tb1", goal_id, 5, .3)
    assert dispatcher.closed and dispatcher.failed
    assert len([event for event in events if event["type"] == "cancel_goal"]) == 1


def at_edge(stamp, offset_ns):
    return (round(stamp * 10**9) + offset_ns) / 10**9


def renew_fractional(dispatcher, goal_id, origin, seconds):
    for offset in range(1, seconds + 1):
        now = at_edge(origin, offset * 10**9)
        assert dispatcher.renew("tb1", goal_id, dispatcher.epoch, now, now + 2) == "renewed"


@pytest.mark.parametrize("created,expires", [(254.6, 256.6), (255.6, 257.6)])
def test_literal_two_second_ttl_and_duplicate_payload_are_preserved(created, expires):
    dispatcher, events = protocol()
    assert submit(dispatcher, now=created, created_at=created, expires_at=expires) == "sent"
    event = events[0]
    assert event["created_at"] == created and event["expires_at"] == expires
    assert submit(dispatcher, now=created + .1, created_at=created,
                  expires_at=expires) == "duplicate"
    # Different literal payloads retain their original conflict semantics even
    # when their timestamps round to the same physical nanosecond.
    assert submit(dispatcher, now=created + .1,
                  created_at=math.nextafter(created, math.inf),
                  expires_at=expires) == "command_id_conflict"
    assert len(events) == 1 and not dispatcher.closed


@pytest.mark.parametrize("offset_ns", [-1, 0, 1])
def test_command_ttl_upper_bound_has_no_one_nanosecond_tolerance(offset_ns):
    dispatcher, events = protocol()
    status = submit(dispatcher, "KEEP", 254.6, created_at=254.6,
                    expires_at=at_edge(256.6, offset_ns))
    assert status == ("kept" if offset_ns <= 0 else "invalid_ttl")
    assert dispatcher.closed and not dispatcher.failed and not events


@pytest.mark.parametrize("offset_ns", [-1, 0, 1])
def test_command_expiration_is_the_exact_exclusive_endpoint(offset_ns):
    dispatcher, events = protocol()
    status = submit(dispatcher, "KEEP", at_edge(256.6, offset_ns),
                    created_at=254.6, expires_at=256.6)
    assert status == ("kept" if offset_ns < 0 else "expired")
    assert dispatcher.closed and not dispatcher.failed and not events


@pytest.mark.parametrize("offset_ns", [-1, 0, 1])
def test_command_creation_cannot_be_one_nanosecond_in_the_future(offset_ns):
    dispatcher, _ = protocol()
    created = at_edge(254.6, offset_ns)
    status = submit(dispatcher, "KEEP", 254.6, created_at=created,
                    expires_at=at_edge(created, 2 * 10**9))
    assert status == ("kept" if offset_ns <= 0 else "invalid_ttl")


@pytest.mark.parametrize("offset_ns", [-1, 0, 1])
def test_renewal_ttl_upper_bound_uses_endpoint_nanoseconds(offset_ns):
    dispatcher, _ = protocol()
    goal_id = start(dispatcher, now=253.6)
    status = dispatcher.renew("tb1", goal_id, dispatcher.epoch, 254.6,
                              at_edge(256.6, offset_ns))
    assert status == ("renewed" if offset_ns <= 0 else "invalid_ttl")
    assert not dispatcher.closed and not dispatcher.failed


@pytest.mark.parametrize("offset_ns", [-1, 0, 1])
def test_renewal_expiration_and_same_lease_are_not_falsely_extended(offset_ns):
    dispatcher, _ = protocol()
    goal_id = start(dispatcher, now=6.03)
    status = dispatcher.renew("tb1", goal_id, dispatcher.epoch, 7.03,
                              at_edge(8.03, offset_ns))
    assert status == ("renewed" if offset_ns > 0 else "stale_renewal")
    assert not dispatcher.closed and not dispatcher.failed


@pytest.mark.parametrize("offset_ns", [-1, 0, 1])
def test_renewal_must_expire_strictly_after_its_receipt(offset_ns):
    dispatcher, _ = protocol()
    goal_id = start(dispatcher, now=253.6)
    status = dispatcher.renew("tb1", goal_id, dispatcher.epoch, 254.6,
                              at_edge(254.6, offset_ns))
    assert status == ("stale_renewal" if offset_ns > 0 else "invalid_ttl")
    assert not dispatcher.closed and not dispatcher.failed


@pytest.mark.parametrize("accepted", [False, True])
@pytest.mark.parametrize("offset_ns", [-1, 0, 1])
def test_lease_expires_at_exact_ns_and_never_releases_unknown_owner(accepted, offset_ns):
    dispatcher, _ = protocol()
    assert submit(dispatcher, now=6.03) == "sent"
    goal_id = dispatcher.navigation()["tb1"]["goal_id"]
    if accepted:
        dispatcher.on_accept("tb1", goal_id, True, 6.03)
    now = at_edge(8.03, offset_ns)
    dispatcher.tick(now)
    assert dispatcher.failed is (offset_ns >= 0)
    assert not dispatcher.closed and dispatcher.navigation()["tb1"]["goal_id"] == goal_id
    if not accepted:
        dispatcher.on_accept("tb1", goal_id, True, now)
    assert not dispatcher.closed
    dispatcher.on_result("tb1", goal_id, 5 if dispatcher.failed else 4, now)
    assert dispatcher.closed and dispatcher.failed is (offset_ns >= 0)


@pytest.mark.parametrize("offset_ns", [-1, 0, 1])
def test_fractional_commitment_unlocks_at_five_exact_seconds(offset_ns):
    dispatcher, events = protocol()
    goal_id = start(dispatcher, now=5.03)
    renew_fractional(dispatcher, goal_id, 5.03, 4)
    assert dispatcher.navigation()["tb1"]["commitment_until"] == 10.03
    status = submit(dispatcher, "WAIT", at_edge(10.03, offset_ns), sequence=2)
    assert status == ("commitment_locked" if offset_ns < 0 else "waiting")
    assert len([e for e in events if e["type"] == "cancel_goal"]) == (offset_ns >= 0)
    assert not dispatcher.closed and not dispatcher.failed


@pytest.mark.parametrize("offset_ns", [-1, 0, 1])
def test_accept_rpc_deadline_and_late_acceptance_at_fractional_time(offset_ns):
    dispatcher, events = protocol()
    assert submit(dispatcher, now=6.08) == "sent"
    goal_id = dispatcher.navigation()["tb1"]["goal_id"]
    renew_fractional(dispatcher, goal_id, 6.08, 9)
    now = at_edge(16.08, offset_ns)
    dispatcher.tick(now)
    state = dispatcher.navigation()["tb1"]
    assert state["failure"] == ("navigation_response_timeout" if offset_ns >= 0 else None)
    assert state["phase"] == ("unknown" if offset_ns >= 0 else "accepting")
    assert not dispatcher.closed
    assert dispatcher.on_accept("tb1", goal_id, True, now) == (
        "canceling" if offset_ns >= 0 else "active")
    assert not dispatcher.closed
    dispatcher.on_result("tb1", goal_id, 5 if offset_ns >= 0 else 4, now)
    assert dispatcher.closed and dispatcher.failed is (offset_ns >= 0)
    assert len([e for e in events if e["type"] == "send_goal"]) == 1


@pytest.mark.parametrize("offset_ns", [-1, 0, 1])
def test_cancel_rpc_deadline_requires_terminal_after_positive_ack(offset_ns):
    dispatcher, _ = protocol()
    goal_id = start(dispatcher, now=.08)
    renew_fractional(dispatcher, goal_id, .08, 6)
    assert submit(dispatcher, "WAIT", 6.08, sequence=2) == "waiting"
    dispatcher.on_cancel_response("tb1", goal_id, True, 6.09)
    now = at_edge(16.08, offset_ns)
    dispatcher.tick(now)
    state = dispatcher.navigation()["tb1"]
    assert state["failure"] == ("navigation_cancel_timeout" if offset_ns >= 0 else None)
    assert state["phase"] == ("unknown" if offset_ns >= 0 else "canceling")
    assert not dispatcher.closed
    dispatcher.on_result("tb1", goal_id, 5, now)
    assert dispatcher.closed and dispatcher.failed is (offset_ns >= 0)


@pytest.mark.parametrize("offset_ns", [-1, 0, 1])
def test_execution_deadline_is_not_extended_by_float_subtraction_or_lease(offset_ns):
    dispatcher, _ = protocol()
    goal_id = start(dispatcher, now=5.07)
    renew_fractional(dispatcher, goal_id, 5.07, 59)
    now = at_edge(65.07, offset_ns)
    dispatcher.tick(now)
    state = dispatcher.navigation()["tb1"]
    assert state["failure"] == ("navigation_execution_timeout" if offset_ns >= 0 else None)
    assert not dispatcher.closed
    dispatcher.on_result("tb1", goal_id, 5 if offset_ns >= 0 else 4, now)
    assert dispatcher.closed and dispatcher.failed is (offset_ns >= 0)


@pytest.mark.parametrize("offset_ns", [-1, 0, 1])
def test_pending_switch_keeps_original_literal_expiry_and_requires_positive_ns(offset_ns):
    dispatcher, events = protocol()
    old = start(dispatcher, now=.03)
    renew_fractional(dispatcher, old, .03, 6)
    literal_expiry = 6.03 + 2
    assert submit(dispatcher, now=6.03, sequence=2, created_at=6.03,
                  expires_at=literal_expiry) == "switch_pending"
    dispatcher.on_cancel_response("tb1", old, True, 6.04)
    assert not dispatcher.closed
    now = at_edge(8.03, offset_ns)
    result = dispatcher.on_result("tb1", old, 5, now)
    assert result == ("replacement_sent" if offset_ns < 0 else "replacement_expired")
    sent = [e for e in events if e["type"] == "send_goal"]
    assert len(sent) == (2 if offset_ns < 0 else 1)
    if offset_ns < 0:
        assert sent[-1]["expires_at"] == literal_expiry and sent[-1]["created_at"] == 6.03
        assert not dispatcher.closed
        dispatcher.on_result("tb1", sent[-1]["goal_id"], 4, now)
    assert dispatcher.closed and not dispatcher.failed


def test_equal_nanosecond_clock_encoding_is_not_a_rewind_but_one_ns_is():
    dispatcher, _ = protocol()
    dispatcher.tick(6.03 + 2)
    dispatcher.tick(8.03)
    with pytest.raises(ValueError, match="clock reversed"):
        dispatcher.tick(at_edge(8.03, -1))


@pytest.mark.parametrize("duration_key", [
    "commitment_sec", "response_timeout_sec", "cancel_timeout_sec",
    "execution_timeout_sec", "lease_sec",
])
@pytest.mark.parametrize("duration", [1e-12, .4e-9, .5e-9])
def test_positive_duration_that_rounds_to_zero_ns_is_explicitly_rejected(duration_key, duration):
    with pytest.raises(ValueError, match="positive nanosecond interval"):
        GoalDispatcher("small-duration", lambda event: None, **{duration_key: duration})


@pytest.mark.parametrize("duration_key", [
    "commitment_sec", "response_timeout_sec", "cancel_timeout_sec",
    "execution_timeout_sec", "lease_sec",
])
def test_one_ns_duration_is_supported_without_clipping(duration_key):
    dispatcher = GoalDispatcher("one-ns", lambda event: None, **{duration_key: 1e-9})
    assert getattr(dispatcher, duration_key) == 1e-9


def test_one_ns_lease_is_fresh_then_expires_without_false_owner_release():
    dispatcher = GoalDispatcher("one-ns", lambda event: None, lease_sec=1e-9)
    assert submit(dispatcher, now=6.03, expires_at=at_edge(6.03, 1)) == "sent"
    goal_id = dispatcher.navigation()["tb1"]["goal_id"]
    assert dispatcher.on_accept("tb1", goal_id, True, 6.03) == "active"
    dispatcher.tick(at_edge(6.03, 1))
    assert dispatcher.failed and not dispatcher.closed
    dispatcher.on_result("tb1", goal_id, 5, at_edge(6.03, 1))
    assert dispatcher.closed and dispatcher.failed


def test_unrepresentable_command_time_is_invalid_without_releasing_owner():
    dispatcher, _ = protocol()
    goal_id = start(dispatcher)
    assert submit(dispatcher, "KEEP", .1, sequence=2, expires_at=1e308) == "invalid_ttl"
    assert dispatcher.renew("tb1", goal_id, dispatcher.epoch, .2, 1e308) == "invalid_ttl"
    assert not dispatcher.closed and not dispatcher.failed
