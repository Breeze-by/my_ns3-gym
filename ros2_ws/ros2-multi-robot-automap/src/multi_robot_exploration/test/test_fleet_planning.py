import math
from dataclasses import replace

import numpy as np
import pytest
from types import SimpleNamespace

from multi_robot_exploration import control as c
from multi_robot_exploration.fleet_planning import (
    FleetSnapshot, MotionProposal, complete_budget, joint_motions, plan_fleet, plan_exploration,
    qualified_motion_route,
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


def test_actual_metric_start_avoids_an_unsafe_raster_centre_without_erasing_obstacles():
    snapshot=world()
    local=np.zeros(snapshot.grid.shape,dtype=np.int16)
    local[0,0]=100
    local=c.immutable_grid_snapshot(local,local.shape)
    snapshot=replace(snapshot,positions={'tb1':(.379,.025)},maps={
        'tb1':dict(data=local,resolution=.1,origin=(-.025,-.025))})
    leg=((.35,.05),(.45,.05),(.75,.05))
    assert not c.route_respects_known_obstacles(local,.1,(-.025,-.025),
                                              (snapshot.positions['tb1'],*leg))
    route=qualified_motion_route(snapshot,'tb1',leg,{})
    assert route==(snapshot.positions['tb1'],*leg[1:])
    from p2c_global_audit import check_route
    evidence=c.grid_audit_evidence(local,.1,(-.025,-.025),'delivered',10.,10.)
    check_route(evidence,route,local=True)
    assert local[0,0]==100
    assert qualified_motion_route(snapshot,'tb1',((.35,.05),(.225,.025),(.75,.05)),{}) is None


def test_joint_rally_assignment_uses_each_robots_actual_approach_constraints():
    snapshot=world()
    blocked=np.zeros_like(snapshot.grid)
    blocked[:,40]=100
    blocked=c.immutable_grid_snapshot(blocked,blocked.shape)
    args=(snapshot.grid,snapshot.resolution,snapshot.origin,snapshot.positions,(7.25,4.25))
    assert c.assign_rally_poses(*args)
    assert not c.assign_rally_poses(*args,approach_grids={'tb1':blocked})
    assert blocked[:,40].min()==100


def test_unissued_charge_does_not_lock_an_invalid_fleet_assignment_but_native_return_does():
    snapshot=world()
    grid=snapshot.grid.copy()
    grid[42,52]=100
    grid=c.immutable_grid_snapshot(grid,grid.shape)
    final=c.RallyPose(5.25,4.25,math.atan2(-.25,.75))
    snapshot=replace(snapshot,phase='RALLY',grid=grid,target=(6.,4.),
        maps={'tb1':dict(data=grid,resolution=.1,origin=(0.,0.))},
        final_poses={'tb1':final},charge_pending=('tb1',))
    proposal=plan_fleet(snapshot)
    assert proposal.final_poses and proposal.final_poses!={'tb1':final}
    native=replace(snapshot,batteries={'tb1':{**snapshot.batteries['tb1'],'mode':'RETURNING'}},
                   available=())
    held=plan_fleet(native)
    assert not held.final_poses and not held.motions
    assert held.blocked['fleet']=='invalid_final_wait_for_owned_traffic'


def test_disconnected_local_approach_observes_disputed_route_from_its_own_component():
    snapshot=world()
    local=np.zeros_like(snapshot.grid)
    local[:,40]=100
    local=c.immutable_grid_snapshot(local,local.shape)
    snapshot=replace(snapshot,phase='FOUND',target=(7.25,4.25),maps={
        'tb1':dict(data=local,resolution=.1,origin=(0.,0.))})
    proposal=plan_fleet(snapshot)
    assert not proposal.final_poses and len(proposal.motions)==1
    motion=proposal.motions[0]
    assert motion.robot=='tb1' and motion.kind=='target_information_survey' and motion.pose.x<4.
    assert motion.required_energy<snapshot.batteries['tb1']['energy']
    assert c.route_respects_known_obstacles(local,.1,(0.,0.),motion.route)
    assert not plan_fleet(replace(snapshot,survey_attempts=snapshot.survey_limit)).motions
    assert not plan_fleet(replace(snapshot,at_time=12.1)).motions
    assert local[:,40].min()==100


def unfunded_survey_world():
    snapshot = world()
    local = np.zeros_like(snapshot.grid)
    local[:,40] = 100
    local = c.immutable_grid_snapshot(local,local.shape)
    snapshot = replace(snapshot,phase='FOUND',target=(7.25,4.25),maps={
        'tb1':dict(data=local,resolution=.1,origin=(0.,0.))})
    funded = plan_fleet(snapshot).motions[0]
    reserve = complete_budget(snapshot,'tb1',(snapshot.positions['tb1'],),
                              snapshot.positions['tb1'],{})
    assert reserve < funded.required_energy < 80.
    energy = (reserve + funded.required_energy) / 2.
    return replace(snapshot,batteries={'tb1':{**snapshot.batteries['tb1'],'energy':energy}})


def test_missing_local_information_can_fund_its_prerequisite_without_erasing_the_wall():
    snapshot = unfunded_survey_world()
    proposal = plan_fleet(snapshot)
    assert not proposal.motions and not proposal.final_poses
    assert len(proposal.charges) == 1
    charge = proposal.charges[0]
    assert charge.robot == 'tb1' and charge.reason == 'unfunded_information_task'
    assert snapshot.batteries['tb1']['energy'] < charge.required_energy < 80.
    assert c.route_respects_known_obstacles(snapshot.maps['tb1']['data'],.1,(0.,0.),
                                          charge.return_route)
    replenished = replace(snapshot,batteries={'tb1':{**snapshot.batteries['tb1'],
                                                    'energy':80.,'charge_count':1}})
    after = plan_fleet(replenished)
    assert not after.charges and len(after.motions) == 1
    assert after.motions[0].kind == 'target_information_survey'
    assert after.motions[0].required_energy < 80.
    assert not after.final_poses and not after.snapshot.completed_legs
    assert snapshot.maps['tb1']['data'][:,40].min() == 100


@pytest.mark.parametrize('condition',[
    'unaffordable_return','inactive','pending_charge','owned_navigation',
    'insufficient_capacity','stale_source','future_source'])
def test_information_funding_requires_a_safe_available_current_return(condition):
    snapshot = unfunded_survey_world()
    state = dict(snapshot.batteries['tb1'])
    if condition == 'unaffordable_return':
        state['energy'] = 0.
    elif condition == 'inactive':
        state['mode'] = 'CHARGING'
    elif condition == 'pending_charge':
        snapshot = replace(snapshot,charge_pending=('tb1',))
    elif condition == 'owned_navigation':
        snapshot = replace(snapshot,live_routes={'tb1':((1.25,1.25),(2.25,1.25))})
    elif condition == 'insufficient_capacity':
        state['charge_target_fraction'] = .1
    elif condition == 'stale_source':
        snapshot = replace(snapshot,at_time=12.1)
    else:
        snapshot = replace(snapshot,at_time=9.9)
    proposal = plan_fleet(replace(snapshot,batteries={'tb1':state}))
    assert not proposal.motions and not proposal.charges
