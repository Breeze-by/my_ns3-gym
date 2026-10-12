import math
from dataclasses import replace

import numpy as np
from types import SimpleNamespace

from multi_robot_exploration import control as c
from multi_robot_exploration.fleet_planning import (
    FleetSnapshot, MotionProposal, complete_budget, joint_motions, plan_fleet, plan_exploration,
)


def test_generator_upper_bound_order_cannot_hide_better_actual_information_goal(monkeypatch):
    grid=c.immutable_grid_snapshot(np.zeros((80,80),dtype=np.int16),(80,80))
    snapshot=FleetSnapshot('EXPLORE',10.,grid,.1,(0.,0.),{'tb1':(4.25,4.25)},
        {},{}, {'headquarters/fused_map_snapshot':10.,'tb1/pose_state':10.,
        'tb1/frame_state':10.},('tb1',))
    # Eight highly optimistic distant generator rows precede a genuinely
    # useful nearby camera point. All gains and paths below are real geometry.
    rows=[(10000.,'tb1',i,SimpleNamespace(x=.55,y=.55+.1*i)) for i in range(8)]
    rows.append((1.,'tb1',8,SimpleNamespace(x=2.55,y=4.25)))
    monkeypatch.setattr(c,'robot_candidate_assignments',lambda *a,**k:(rows,{}))
    monkeypatch.setattr(c,'known_space_search_candidates',lambda *a,**k:[])
    proposal=plan_exploration(snapshot,{}, {})
    assert len(proposal.motions)==1
    assert math.dist((proposal.motions[0].pose.x,proposal.motions[0].pose.y),(2.55,4.25))<1e-8


def world(energy=40., obstacle=False):
    grid = np.zeros((80, 100), dtype=np.int16)
    if obstacle:
        grid[:, 40] = 100
    grid = c.immutable_grid_snapshot(grid, grid.shape)
    battery = dict(mode="ACTIVE", energy=energy, charge_x=1.25, charge_y=1.25,
        capacity=100., charge_target_fraction=.8, charge_radius_m=.8,
        move_cost_per_m=1., idle_cost_per_sec=.02, return_path_factor=2.,
        nominal_speed_mps=.18, return_safety_margin=8., charge_duration_sec=6.)
    sources = {"headquarters/fused_map_snapshot": 10., **{
        "tb1/" + kind: 10. for kind in ("map_snapshot", "pose_state", "frame_state", "battery_state")}}
    return FleetSnapshot("EXPLORE", 10., grid, .1, (0., 0.),
        {"tb1": (1.25, 1.25)}, {"tb1": battery},
        {"tb1": dict(data=grid, resolution=.1, origin=(0., 0.))},
        sources, ("tb1",), required=("tb1",))


def test_full_task_and_contact_return_are_funded_without_straight_line_fallback():
    snapshot = world()
    route = ((1.25, 1.25), (3.25, 1.25))
    required = complete_budget(snapshot, "tb1", route, route[-1], {})
    assert required > 8. + 2.
    assert complete_budget(world(obstacle=True), "tb1",
        ((1.25, 1.25), (5.25, 1.25)), (5.25, 1.25), {}) is None
    assert complete_budget(replace(snapshot, at_time=12.1), "tb1", route, route[-1], {}) is None


def test_joint_choice_can_skip_greedy_leader_to_enable_more_fleet_information():
    def option(robot, x, gain, cells):
        return MotionProposal(robot, "exploration", c.RallyPose(x, 0., 0.),
            ((x, 0.), (x, 1.)), gain, 10., frozenset(cells))
    greedy = option("tb1", 0., 10., range(10))
    alternative = option("tb1", 5., 9., range(10, 19))
    peer = option("tb2", .5, 9., range(20, 29))
    chosen = joint_motions({"tb1": [greedy, alternative], "tb2": [peer]})
    assert chosen == (alternative, peer)
    assert not c.routes_conflict(*(choice.route for choice in chosen))


def test_overlapping_camera_information_does_not_count_twice():
    first = MotionProposal("tb1", "exploration", c.RallyPose(0., 0., 0.),
        ((0., 0.), (0., 1.)), 10., 8., frozenset(range(10)))
    redundant = replace(first, robot="tb2", pose=c.RallyPose(5., 0., 0.),
                         route=((5., 0.), (5., 1.)))
    novel = replace(redundant, utility=6., information_cells=frozenset(range(10, 16)))
    assert joint_motions({"tb1": [first], "tb2": [redundant, novel]}) == (first, novel)


def test_global_exploration_budgets_actual_goal_and_keeps_snapshot_immutable():
    snapshot = world()
    before = snapshot.grid.tobytes()
    proposal = plan_fleet(snapshot)
    assert proposal.motions
    for motion in proposal.motions:
        assert motion.kind == "exploration" and motion.information_cells
        assert math.dist(motion.route[-1], (motion.pose.x, motion.pose.y)) < .11
        assert motion.required_energy < snapshot.batteries[motion.robot]["energy"]
        assert route_length(motion.route) <= c.MAX_NAVIGATION_LEG_M + .2
    assert snapshot.grid.tobytes() == before and not snapshot.grid.flags.writeable


def route_length(route):
    return sum(math.dist(a, b) for a, b in zip(route, route[1:]))


def test_zero_energy_never_admits_exploration():
    proposal = plan_fleet(world(energy=0.))
    assert not proposal.motions
