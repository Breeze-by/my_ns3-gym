import math
from dataclasses import replace

import numpy as np
import pytest
from types import SimpleNamespace

from multi_robot_exploration import control as c
from multi_robot_exploration.fleet_planning import (
    FleetSnapshot, MotionProposal, complete_budget, joint_motions, plan_fleet, plan_exploration,
    qualified_motion_route, ExplorationObjective,
    plan_observer_heading, ChargeProposal, planned_charge_returns, return_helper_beneficiary_current,
    camera_heading_candidates, camera_heading_current,
    route_length,
    minimum_polyline_separation, stationary_route_clears_bodies, stationary_route_clears_corridors,
    stationary_route_is_known,
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


def tiny_camera_world(fully_viewed=False):
    grid = np.zeros((32,32),dtype=np.int16)
    grid[[0,-1],:] = grid[:,[0,-1]] = 100
    grid = c.immutable_grid_snapshot(grid,grid.shape)
    position = (.825,.825)
    base = world(30.)
    battery = {**base.batteries['tb1'],'charge_x':position[0],'charge_y':position[1]}
    views = tuple(dict(position=position,yaw=index*2.*math.pi/16,
        pose_source_time=9.+index/100.,frame_source_time=9.,robot='tb1')
        for index in (range(16) if fully_viewed else (0,)))
    return replace(base,grid=grid,resolution=.05,positions={'tb1':position},
        batteries={'tb1':battery},maps={'tb1':dict(data=grid,resolution=.05,origin=(0.,0.))},
        views=views,yaws={'tb1':0.})


@pytest.mark.parametrize('fully_viewed',[False,True])
def test_known_room_without_useful_translation_retains_funded_camera_heading(fully_viewed):
    snapshot = tiny_camera_world(fully_viewed)
    safe = c.traversable_grid(snapshot.grid,.05,c.ROBOT_CLEARANCE_M)
    field = c.exploration_distance_field(snapshot.grid,
        c.traversable_grid(snapshot.grid,.05,c.PATH_CLEARANCE_M),.05,(0.,0.),snapshot.positions['tb1'])
    assert float(np.max(field[safe])) < c.USEFUL_TRAVEL_M
    interest = c.camera_search_interest(snapshot.grid,.05,(0.,0.),snapshot.views)
    if fully_viewed:
        assert not interest.any()
    result = plan_fleet(snapshot)
    assert len(result.motions)==1 and not result.charges
    motion = result.motions[0]
    assert motion.kind=='exploration_camera_heading' and motion.information_cells
    assert motion.pose.x==motion.pose.y==.825 and math.dist(*motion.route)==0.
    assert motion.wait_sec==motion.nominal_orientation_time_sec==60.
    base = complete_budget(snapshot,'tb1',motion.route,(.825,.825),{})
    assert math.isclose(motion.required_energy-base,60*.02) and motion.required_energy < 30.
    objective = ExplorationObjective(snapshot,interest)
    assert objective.ready_time((motion,))==61.
    assert objective.score((motion,)) > objective.score(())==0.
    assert not snapshot.completed_legs and not snapshot.pending_views


@pytest.mark.parametrize('variant',['stale_pose','future_tf','stale_battery','missing_map',
                                  'unfunded','native','issued','live','demand','body'])
def test_stationary_camera_candidate_preserves_original_source_funding_and_ownership(variant):
    snapshot = tiny_camera_world()
    if variant in ('stale_pose','future_tf','stale_battery'):
        key,stamp = {'stale_pose':('tb1/pose_state',7.99),'future_tf':('tb1/frame_state',10.01),
                     'stale_battery':('tb1/battery_state',4.99)}[variant]
        snapshot = replace(snapshot,sources={**snapshot.sources,key:stamp})
    elif variant=='missing_map':
        snapshot = replace(snapshot,maps={})
    elif variant=='unfunded':
        snapshot = replace(snapshot,batteries={'tb1':{**snapshot.batteries['tb1'],'energy':9.5}})
    elif variant=='native':
        snapshot = replace(snapshot,batteries={'tb1':{**snapshot.batteries['tb1'],'mode':'RETURNING'}})
    elif variant=='issued':
        snapshot = replace(snapshot,charge_pending=('tb1',))
    elif variant=='live':
        snapshot = replace(snapshot,live_routes={'tb1':(snapshot.positions['tb1'],)},available=())
    elif variant=='demand':
        snapshot = replace(snapshot,charge_intents={'tb1':ChargeProposal('tb1',40.,(), 'unfunded_information_task')})
    else:
        snapshot = replace(snapshot,positions={**snapshot.positions,'tb2':(.825,1.415)})
    objective = ExplorationObjective(snapshot,snapshot.grid==0)
    assert not camera_heading_candidates(snapshot,'tb1',{},(),objective)


def test_owned_camera_orientation_time_is_parallel_and_survives_cancel_prediction_removal():
    snapshot = tiny_camera_world(True)
    pose = c.RallyPose(.825,.825,math.pi)
    snapshot = replace(snapshot,live_routes={'tb1':((.825,.825),)},pending_views={'tb1':pose},
        pending_orientation_times={'tb1':60.},available=())
    objective = ExplorationObjective(snapshot,np.zeros(snapshot.grid.shape,dtype=bool))
    assert objective.committed and objective.ready_time(())==61.
    motion = MotionProposal('tb1','exploration_camera_heading',pose,((.825,.825),),1.,11.,
        nominal_orientation_time_sec=60.)
    assert objective.ready_time((motion,))==61.  # same actor replaces, not doubles its allocation
    canceled = ExplorationObjective(replace(snapshot,pending_views={}),snapshot.grid==0)
    assert not canceled.committed and canceled.ready_time(())==61.
    released = ExplorationObjective(replace(snapshot,pending_views={},live_routes={},pending_orientation_times={}),
                                    snapshot.grid==0)
    assert released.ready_time(())==1.
    large = world()
    parallel = replace(large,positions={'tb1':(1.25,1.25),'tb2':(4.25,1.25)},
        batteries={**large.batteries,'tb2':large.batteries['tb1']},required=('tb1','tb2'),
        pending_orientation_times={'tb1':60.,'tb2':60.})
    combined = ExplorationObjective(parallel,parallel.grid==0)
    assert math.isclose(combined.ready_time(()),61.+3./.18)
    failed_owner = ExplorationObjective(replace(parallel,required=('tb2',),
        pending_orientation_times={'tb1':60.},pending_views={}),parallel.grid==0)
    assert failed_owner.ready_time(())==61.  # real unclosed owner is not erased by participant exclusion


def test_owned_camera_heading_does_not_predict_a_new_360_degree_mapping_observation():
    snapshot = world()
    grid = np.zeros(snapshot.grid.shape,dtype=np.int16)
    grid[5:20,20:30] = -1
    grid = c.immutable_grid_snapshot(grid,grid.shape)
    pose = c.RallyPose(1.25,1.25,math.pi)
    pending = replace(snapshot,grid=grid,pending_views={'tb1':pose},
        live_routes={'tb1':((1.25,1.25),)},pending_orientation_times={'tb1':60.})
    objective = ExplorationObjective(pending,grid==0)
    mapping = set(map(int,c.visible_unknown_gain(grid,(12,12),20,return_cells=True)))
    assert mapping and not objective.committed.intersection(mapping)
    ordinary = ExplorationObjective(replace(pending,pending_orientation_times={}),grid==0)
    assert mapping <= ordinary.committed


def test_camera_connector_checks_continuous_body_and_simplified_corridor_interior():
    body_route = ((.01,.59995),(.03,.59995))
    body = (.02,0.)
    assert all(math.dist(point,body) > .6 for point in body_route)
    assert math.isclose(minimum_polyline_separation(body_route,(body,)),.59995)
    assert not stationary_route_clears_bodies(body_route,(body,))
    corridor_route = ((.01,1.79999),(.03,1.79999))
    assert all(math.dist(point,body) > 1.8 for point in corridor_route)
    assert not stationary_route_clears_corridors(corridor_route,((body,),))
    # The physical reserved path may be simplified; its endpoints alone do
    # not define the nearest point to the stationary robot.
    reserved = ((-4.,0.),(4.,0.))
    assert all(math.dist((0.,1.),point) > 1.8 for point in reserved)
    assert not stationary_route_clears_corridors(((0.,1.),),(reserved,))
    assert minimum_polyline_separation(((0.,-1.),(0.,1.)),reserved)==0.


def test_camera_metric_connector_cannot_cross_unknown_side_cell_between_known_endpoints():
    snapshot = tiny_camera_world()
    grid = np.array(snapshot.grid,copy=True)
    grid[10,11] = -1
    snapshot = replace(snapshot,grid=c.immutable_grid_snapshot(grid,grid.shape))
    route = ((.545,.540),(.555,.555))
    start,end = (c.world_to_grid(*point,.05,0.,0.) for point in route)
    assert grid[start]==grid[end]==0 and math.dist(*route) < .02
    assert c.has_known_line_of_sight(grid,start,end)  # original centre line misses this metric side crossing
    assert not stationary_route_is_known(snapshot,route)
    known = replace(snapshot,grid=tiny_camera_world().grid)
    assert stationary_route_is_known(known,route)


def test_joint_camera_heading_cannot_hide_conflict_in_a_new_ordinary_route_interior():
    heading = MotionProposal('tb1','exploration_camera_heading',c.RallyPose(2.,3.,math.pi),
        ((2.,3.),),100.,11.,frozenset({1}),nominal_orientation_time_sec=60.)
    crossing = MotionProposal('tb2','exploration',c.RallyPose(4.,2.,0.),
        ((0.,2.),(4.,2.)),80.,15.,frozenset({2}))
    safe = replace(crossing,pose=c.RallyPose(4.,0.,0.),route=((0.,2.),(0.,0.),(4.,0.)),utility=70.)
    assert not c.routes_conflict(heading.route,crossing.route)  # legacy vertices miss the closest interior
    assert joint_motions({'tb1':[heading],'tb2':[crossing,safe]})==(heading,safe)
    assert not joint_motions({'tb1':[heading]},reservations=(crossing.route,))
    assert joint_motions({'tb2':[crossing,safe]},continuous_reservations=(heading.route,))==(safe,)


def test_real_camera_and_translation_bounds_include_the_same_declared_action_time():
    snapshot = replace(world(),yaws={'tb1':0.})
    objective = ExplorationObjective(snapshot,snapshot.grid==0)
    headings = camera_heading_candidates(snapshot,'tb1',{},(),objective)
    assert headings
    pose = c.RallyPose(3.25,1.25,math.pi)
    route = ((1.25,1.25),(3.25,1.25))
    required = complete_budget(snapshot,'tb1',route,(pose.x,pose.y),{})
    translation = MotionProposal('tb1','exploration',pose,route,1.,required,camera_view(snapshot,pose))
    for motion in (*headings,translation):
        expected_duration = 1.+route_length(motion.route)/.18+motion.nominal_orientation_time_sec
        expected_score = len(motion.information_cells)/expected_duration
        assert math.isclose(objective.score((motion,)),expected_score)
        assert math.isclose(objective.bound('tb1',motion.pose,motion.route,
            len(motion.information_cells),1.,motion.nominal_orientation_time_sec),expected_score)
        assert required < snapshot.batteries['tb1']['energy']


def test_camera_orientation_fallback_and_bound_price_original_time_without_fake_route():
    snapshot = world()
    grid = np.zeros(snapshot.grid.shape,dtype=np.int16)
    grid[:,40] = 100
    grid = c.immutable_grid_snapshot(grid,grid.shape)
    snapshot = replace(snapshot,grid=grid,positions={'tb1':(1.25,1.25),'tb2':(5.25,1.25)},
        required=('tb1','tb2'),batteries={**snapshot.batteries,'tb2':snapshot.batteries['tb1']})
    objective = ExplorationObjective(snapshot,grid==0)
    motion = MotionProposal('tb1','exploration_camera_heading',c.RallyPose(1.25,1.25,math.pi),
        ((1.25,1.25),),1.,11.,frozenset({100}),nominal_orientation_time_sec=60.)
    assert objective.ready_time((motion,)) is None
    expected = c.exploration_utility(1.,0,60.*.18)
    assert math.isclose(objective.score((motion,)),expected) and expected > 0.
    assert objective.score((replace(motion,nominal_orientation_time_sec=120.),)) < expected
    assert math.isclose(objective.bound('tb1',motion.pose,motion.route,1,1.,60.),expected)
    assert route_length(motion.route)==0. and motion.required_energy==11.


def test_pending_expected_mass_can_rationally_wait_for_a_costly_weak_camera_heading():
    snapshot = world()
    pending = c.RallyPose(2.25,2.25,0.)
    snapshot = replace(snapshot,positions={'tb1':(1.25,1.25),'tb2':(5.25,1.25)},
        required=('tb1','tb2'),pending_views={'tb1':pending},
        live_routes={'tb1':((1.25,1.25),(2.25,2.25))})
    objective = ExplorationObjective(snapshot,snapshot.grid==0)
    pose = c.RallyPose(5.25,1.25,math.pi)
    new_cell = min(camera_view(snapshot,pose)-objective.committed)
    motion = MotionProposal('tb2','exploration_camera_heading',pose,
        ((5.25,1.25),),1.,11.,frozenset({new_cell}),nominal_orientation_time_sec=60.)
    assert objective.score(()) > objective.score((motion,)) > 0.
    assert not joint_motions({'tb2':[motion]},scorer=objective.score)
    assert objective.bound('tb2',motion.pose,motion.route,1,1.,60.) >= objective.score((motion,))


def test_heading_alone_does_not_expand_existing_after_work_scout_charge_trigger():
    snapshot = tiny_camera_world()
    snapshot = replace(snapshot,batteries={'tb1':{**snapshot.batteries['tb1'],
        'energy':20.,'charge_x':.225}},completed_legs={'tb1':1})
    result = plan_fleet(snapshot)
    assert len(result.motions)==1 and result.motions[0].kind=='exploration_camera_heading'
    assert not result.charges and result.snapshot.completed_legs=={'tb1':1}


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


def camera_view(snapshot, pose):
    cell = c.world_to_grid(pose.x,pose.y,snapshot.resolution,*snapshot.origin)
    hits = c.visible_unknown_gain(snapshot.grid,cell,c.INFORMATION_RADIUS_M/snapshot.resolution,
                                  snapshot.grid==0,return_cells=True)
    rows,columns = np.unravel_index(hits,snapshot.grid.shape)
    delta = np.arctan2(rows-cell[0],columns-cell[1])-pose.yaw
    return frozenset(map(int,hits[np.abs(np.arctan2(np.sin(delta),np.cos(delta)))
                                 <=c.INITIAL_SEARCH_VIEW_FOV_RAD/2.]))


def test_async_observation_commitments_change_the_joint_choice_without_observation_credit():
    snapshot = world()
    pending = c.RallyPose(2.25,2.25,0.)
    snapshot = replace(snapshot,positions={'tb1':(1.25,1.25),'tb2':(4.25,1.25)},
        required=('tb1','tb2'),available=('tb2',),pending_views={'tb1':pending},
        live_routes={'tb1':((1.25,1.25),(2.25,2.25))})
    objective = ExplorationObjective(snapshot,snapshot.grid==0)
    left,right = c.RallyPose(4.25,2.25,math.pi),c.RallyPose(4.25,2.25,0.)
    redundant = MotionProposal('tb2','exploration',left,((4.25,1.25),(4.25,2.25)),
        100.,15.,camera_view(snapshot,left))
    novel = replace(redundant,pose=right,utility=99.,information_cells=camera_view(snapshot,right))
    assert len(redundant.information_cells&objective.committed) > len(novel.information_cells&objective.committed)
    assert joint_motions({'tb2':[redundant,novel]}) == (redundant,)
    assert joint_motions({'tb2':[redundant,novel]},scorer=objective.score) == (novel,)
    assert not snapshot.views and not snapshot.completed_legs
    released = ExplorationObjective(replace(snapshot,pending_views={},live_routes={}),snapshot.grid==0)
    assert not released.committed and not released.pending
    # A current-map projection is rebuilt, never a reused flattened old-grid ID.
    changed = np.zeros((80,120),dtype=np.int16)
    changed[22,22] = 100
    changed = c.immutable_grid_snapshot(changed,changed.shape)
    updated = replace(snapshot,grid=changed)
    assert not ExplorationObjective(updated,changed==0).committed


def test_owned_expected_information_prices_a_new_observations_readiness_opportunity_cost():
    snapshot = world()
    pending = c.RallyPose(2.25,2.25,0.)
    snapshot = replace(snapshot,positions={'tb1':(1.25,1.25),'tb2':(5.25,1.25)},
        required=('tb1','tb2'),available=('tb2',),pending_views={'tb1':pending},
        live_routes={'tb1':((1.25,1.25),(2.25,2.25))})
    before = (snapshot.views,dict(snapshot.completed_legs),dict(snapshot.pending_views))
    objective = ExplorationObjective(snapshot,snapshot.grid==0)
    pose = c.RallyPose(7.25,1.25,0.)
    visible_novel = camera_view(snapshot,pose)-objective.committed
    assert visible_novel and objective.committed
    # A single genuine new cell need not justify delaying already funded work.
    motion = MotionProposal('tb2','exploration',pose,((5.25,1.25),(7.25,1.25)),
        1.,15.,frozenset({min(visible_novel)}))
    assert objective.ready_time((motion,)) > objective.ready_time(())
    assert objective.score(()) > objective.score((motion,)) > 0.
    assert not joint_motions({'tb2':[motion]},snapshot.live_routes.values(),scorer=objective.score)
    duplicate = replace(motion,information_cells=frozenset({min(objective.committed)}))
    assert objective.score((duplicate,)) < objective.score(())
    assert not joint_motions({'tb2':[duplicate]},snapshot.live_routes.values(),scorer=objective.score)
    assert (snapshot.views,snapshot.completed_legs,snapshot.pending_views) == before


def test_search_refinement_prices_preferred_overlap_and_positive_historical_camera_potential(monkeypatch):
    snapshot = world()
    pending = c.RallyPose(2.25,2.25,0.)
    snapshot = replace(snapshot,positions={'tb1':(1.25,1.25),'tb2':(5.25,1.25)},
        required=('tb1','tb2'),available=('tb2',),pending_views={'tb1':pending},
        live_routes={'tb1':((1.25,1.25),(2.25,2.25))})
    interest = np.zeros(snapshot.grid.shape,dtype=bool)
    interest[22,40] = True
    monkeypatch.setattr(c,'camera_search_interest',lambda *a,**k:interest.copy())
    rows = [(1.,'tb2',0,SimpleNamespace(x=5.25,y=2.25))]
    monkeypatch.setattr(c,'robot_candidate_assignments',lambda *a,**k:(rows,{}))
    monkeypatch.setattr(c,'known_space_search_candidates',lambda *a,**k:[])
    objective = ExplorationObjective(snapshot,interest)
    pose = c.RallyPose(5.25,2.25,math.pi)
    cell = c.world_to_grid(pose.x,pose.y,snapshot.resolution,*snapshot.origin)
    visible = c.visible_unknown_gain(snapshot.grid,cell,c.INFORMATION_RADIUS_M/snapshot.resolution,
                                     interest,return_cells=True)
    assert visible.size == 1 and set(map(int,visible)) <= objective.committed
    result = plan_exploration(snapshot,{}, {})
    assert len(result.motions) == 1 and not result.charges
    assert set(map(int,visible)) <= objective.committed
    assert result.motions[0].information_cells-objective.committed
    assert objective.ready_time(result.motions) < objective.ready_time(())
    assert objective.score(result.motions) > objective.score(())
    motion = result.motions[0]
    assert math.isclose(objective.score((motion,)),
        (objective.mass(objective.committed)+objective.mass(motion.information_cells-objective.committed)
         *motion.information_weight)/objective.ready_time((motion,)))


def test_joint_search_accounts_for_future_fleet_gathering_without_changing_return_prices():
    snapshot = replace(world(),positions={'tb1':(1.25,1.25),'tb2':(5.25,1.25)},
                       required=('tb1','tb2'))
    objective = ExplorationObjective(snapshot,snapshot.grid==0)
    farther = MotionProposal('tb1','exploration',c.RallyPose(.25,1.25,0.),
        ((1.25,1.25),(.25,1.25)),100.,15.,frozenset(range(100)))
    nearer = replace(farther,pose=c.RallyPose(2.25,1.25,0.),
        route=((1.25,1.25),(2.25,1.25)),utility=99.)
    assert objective.ready_time((nearer,)) < objective.ready_time((farther,))
    assert joint_motions({'tb1':[farther,nearer]}) == (farther,)
    assert joint_motions({'tb1':[farther,nearer]},scorer=objective.score) == (nearer,)
    for motion in (farther,nearer):
        assert complete_budget(snapshot,'tb1',motion.route,
            (motion.pose.x,motion.pose.y),{}) < snapshot.batteries['tb1']['energy']
    assert snapshot.batteries['tb1']['return_path_factor'] == 2.


def test_gathering_forecast_uses_known_graph_detours_and_does_not_invent_a_missing_path():
    grid = np.zeros((80,100),dtype=np.int16)
    grid[:,40] = 100
    grid[65:75,40] = 0
    grid = c.immutable_grid_snapshot(grid,grid.shape)
    snapshot = replace(world(),grid=grid,positions={'tb1':(2.25,2.25),'tb2':(6.25,2.25)},
                       required=('tb1','tb2'))
    proxy = ExplorationObjective(snapshot,grid==0)
    assert proxy.ready_time(()) > 1. + 10. / .18
    disconnected = grid.copy()
    disconnected[:,40] = 100
    disconnected = c.immutable_grid_snapshot(disconnected,disconnected.shape)
    blocked = replace(snapshot,grid=disconnected)
    assert ExplorationObjective(blocked,disconnected==0).ready_time(()) is None
    assert disconnected[:,40].min() == 100


def observer_heading_world():
    snapshot = world()
    return replace(snapshot, phase='RALLY', target=(1.12, 2.8), observer='tb1',
        sources={**snapshot.sources, 'headquarters/target_detection':4.},
        yaws={'tb1':2.454}, confirmations={'tb1':4.}, target_fov_rad=math.pi/2.)


def test_lapsed_real_observation_restores_heading_before_the_valid_target_lease_expires():
    snapshot = observer_heading_world()
    before = (dict(snapshot.sources), dict(snapshot.confirmations), snapshot.grid.tobytes())
    proposal = plan_fleet(snapshot)
    assert len(proposal.motions) == 1 and not proposal.charges
    motion = proposal.motions[0]
    assert motion.kind == 'target_observation_heading' and motion.robot == 'tb1'
    assert all(point == snapshot.positions['tb1'] for point in motion.route)
    assert (motion.pose.x, motion.pose.y) == snapshot.positions['tb1']
    assert motion.pose.yaw == pytest.approx(math.atan2(1.55, -.13), abs=1e-12)
    assert motion.wait_sec == snapshot.goal_timeout_sec == 60.
    stationary = complete_budget(snapshot, 'tb1', motion.route, motion.route[-1], {})
    assert math.isclose(motion.required_energy-stationary, .02*60.)
    assert (snapshot.sources, snapshot.confirmations, snapshot.grid.tobytes()) == before
    assert not snapshot.completed_legs and not snapshot.views and snapshot.survey_attempts == 0


@pytest.mark.parametrize('condition', [
    'recent_confirmation', 'fresh_alternate', 'owned', 'pending_charge', 'returning',
    'charging', 'peer_returning', 'stale_target', 'future_target', 'future_confirmation',
    'stale_pose', 'future_pose', 'stale_map', 'aligned_heading', 'outside_range',
    'unsafe_local_cell', 'peer_body', 'peer_reservation', 'unfunded',
])
def test_observer_heading_preserves_source_ownership_geometry_and_return_guards(condition):
    snapshot = observer_heading_world()
    state = dict(snapshot.batteries['tb1'])
    if condition == 'recent_confirmation':
        snapshot = replace(snapshot, confirmations={'tb1':5.})
    elif condition == 'fresh_alternate':
        snapshot = replace(snapshot, confirmations={'tb1':4., 'tb2':9.},
            positions={**snapshot.positions, 'tb2':(4.25,4.25)},
            batteries={**snapshot.batteries, 'tb2':{**state, 'mode':'ACTIVE'}})
    elif condition == 'owned':
        snapshot = replace(snapshot, live_routes={'tb1':(snapshot.positions['tb1'],)})
    elif condition == 'pending_charge':
        snapshot = replace(snapshot, charge_pending=('tb1',))
    elif condition in ('returning', 'charging'):
        state['mode'] = condition.upper()
    elif condition == 'peer_returning':
        snapshot = replace(snapshot, batteries={**snapshot.batteries,
            'tb2':{**state, 'mode':'RETURNING'}})
    elif condition in ('stale_target', 'future_target', 'stale_pose', 'future_pose', 'stale_map'):
        key, stamp = {
            'stale_target':('headquarters/target_detection',-50.001),
            'future_target':('headquarters/target_detection',10.001),
            'stale_pose':('tb1/pose_state',7.999),
            'future_pose':('tb1/pose_state',10.001),
            'stale_map':('tb1/map_snapshot',4.999),
        }[condition]
        snapshot = replace(snapshot, sources={**snapshot.sources,key:stamp})
    elif condition == 'future_confirmation':
        snapshot = replace(snapshot, confirmations={'tb1':10.001})
    elif condition == 'aligned_heading':
        snapshot = replace(snapshot, yaws={'tb1':math.atan2(1.55,-.13)})
    elif condition == 'outside_range':
        snapshot = replace(snapshot, target=(5.25,1.25))
    elif condition == 'unsafe_local_cell':
        local = snapshot.grid.copy()
        local[12,12] = 100
        local = c.immutable_grid_snapshot(local,local.shape)
        snapshot = replace(snapshot, maps={'tb1':dict(data=local,resolution=.1,origin=(0.,0.))})
    elif condition == 'peer_body':
        snapshot = replace(snapshot, positions={**snapshot.positions,'tb2':(1.5,1.25)})
    elif condition == 'peer_reservation':
        snapshot = replace(snapshot, live_routes={'tb2':((1.25,1.25),(2.25,1.25))})
    else:
        state['energy'] = 0.
    snapshot = replace(snapshot,batteries={**snapshot.batteries,'tb1':state})
    assert plan_observer_heading(snapshot,{}, {}) is None


def test_unknown_unissued_return_is_optional_but_unknown_native_return_pauses_fleet():
    grid = np.zeros((160,400),dtype=np.int16)
    grid[[0,-1],:] = grid[:,[0,-1]] = 100
    grid = c.immutable_grid_snapshot(grid,grid.shape)
    local = grid.copy()
    local[:,180] = 100
    local = c.immutable_grid_snapshot(local,local.shape)
    base = world().batteries['tb1']
    states = {robot:{**base,'charge_x':1.025,'charge_y':4.025,'mode':mode}
              for robot,mode in [('tb1','ACTIVE'),('tb2','RETURNING'),('tb3','ACTIVE')]}
    positions = {'tb1':(4.025,4.025),'tb2':(7.025,4.025),'tb3':(14.025,4.025)}
    sources = {'headquarters/fused_map_snapshot':10., **{
        robot+'/'+kind:10. for robot in positions
        for kind in ('map_snapshot','pose_state','frame_state','battery_state')}}
    maps = {robot:dict(data=local if robot=='tb3' else grid,resolution=.05,origin=(0.,0.))
            for robot in positions}
    demand = ChargeProposal('tb3',60.,(),'unfunded_information_task',(16.025,4.025))
    snapshot = FleetSnapshot('EXPLORE',10.,grid,.05,(0.,0.),positions,states,maps,sources,
        ('tb1','tb3'),required=tuple(positions),charge_intents={'tb3':demand},
        charge_intent_slots={'tb3':'main'})
    assert not planned_charge_returns(snapshot,{})
    offered = plan_fleet(snapshot)
    assert len(offered.motions) == 1
    assert offered.motions[0].robot == 'tb1' and offered.motions[0].beneficiary == 'tb2'
    unknown_native = replace(snapshot,batteries={**states,'tb3':{**states['tb3'],'mode':'RETURNING'}},
                             available=('tb1',))
    paused = plan_fleet(unknown_native)
    assert not paused.motions and not paused.charges
    assert paused.blocked == {'fleet':'unknown_live_return_corridor'}


@pytest.mark.parametrize('mode',['ACTIVE','RETURNING','CHARGING','FAILED',None])
@pytest.mark.parametrize('slot',['issued','intent'])
def test_return_helper_membership_never_authorizes_a_failed_or_missing_beneficiary(mode,slot):
    proposal = MotionProposal('tb2','charge_clearance',c.RallyPose(1.,1.,0.),((1.,1.),),1.,10.,
                              beneficiary='tb1')
    modes = {} if mode is None else {'tb1':mode}
    issued,intents = (('tb1',),()) if slot=='issued' else ((),('tb1',))
    assert return_helper_beneficiary_current(proposal,modes,issued,intents) == (
        mode in ('ACTIVE','RETURNING','CHARGING'))
