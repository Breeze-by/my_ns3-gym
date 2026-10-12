"""Joint fleet proposals computed without ROS nodes or execution authority.

A proposal can outlive its source leases. The executor must reconstruct its
routes, return reserves and ownership from current delivered inputs before
issuing any command. Historical view masks are search preferences, not proof
that a target is absent. All geometry uses the existing P2C safety operators.
"""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from itertools import product
import math
import time

import numpy as np

from . import control as geometry


@dataclass(frozen=True)
class FleetSnapshot:
    phase: str
    at_time: float
    grid: np.ndarray
    resolution: float
    origin: tuple
    positions: dict
    batteries: dict
    maps: dict
    sources: dict
    available: tuple
    live_routes: dict = field(default_factory=dict)
    completed_legs: dict = field(default_factory=dict)
    history: tuple = ()
    views: tuple = ()
    target: tuple | None = None
    observer: str | None = None
    final_poses: dict = field(default_factory=dict)
    charge_pending: tuple = ()
    maximum_concurrent: int = geometry.EXPLORATION_MAX_CONCURRENT
    hold_sec: float = geometry.RALLY_HOLD_SEC
    target_range: float = 3.0
    position_tolerance: float = geometry.RALLY_POSITION_TOLERANCE_M
    attempts: dict = field(default_factory=dict)
    required: tuple | None = None
    arrived: tuple = ()
    scan_steps: dict = field(default_factory=dict)
    survey_attempts: int = 0
    survey_limit: int = 9
    source_grid: np.ndarray | None = None
    self_return_cells: dict = field(default_factory=dict)

    @property
    def context(self):
        return self.phase, tuple(sorted(self.required or self.positions)), self.target


@dataclass(frozen=True)
class MotionProposal:
    robot: str
    kind: str
    pose: geometry.RallyPose
    route: tuple
    utility: float
    required_energy: float
    information_cells: frozenset = frozenset()
    beneficiary: str | None = None
    complete_route: tuple = ()
    budget_time: float | None = None
    wait_sec: float = 0.0


@dataclass(frozen=True)
class ChargeProposal:
    robot: str
    required_energy: float
    return_route: tuple
    reason: str
    destination: tuple | None = None


@dataclass(frozen=True)
class FleetProposal:
    snapshot: FleetSnapshot
    motions: tuple = ()
    charges: tuple = ()
    final_poses: dict = field(default_factory=dict)
    wait_budgets: dict = field(default_factory=dict)
    blocked: dict = field(default_factory=dict)
    computation_wall_sec: float = 0.0


class PlanningWorker:
    """One in-flight pure computation; no stale work queue or ROS mutation."""

    def __init__(self):
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="fleet-plan")
        self.future = None
        self.closed = False

    def submit(self, snapshot):
        if self.closed or self.future is not None:
            return False
        self.future = self.executor.submit(plan_fleet, snapshot)
        return True

    def poll(self):
        if self.future is None or not self.future.done():
            return None
        future, self.future = self.future, None
        return future.result()

    def close(self):
        self.closed = True
        self.executor.shutdown(wait=True, cancel_futures=True)
        self.future = None


def route_length(route):
    return sum(math.dist(a, b) for a, b in zip(route, route[1:]))


def qualified_motion_route(snapshot, robot, leg, caches):
    """Check actual continuous geometry, including the metric start connector.

    A raster centre can move an already-clear real pose towards an obstacle.
    Remove only that redundant first centre when the direct next connector
    has known line of sight and both original continuous predicates pass.
    No obstacle, clearance limit or bounded-start escape rule is changed.
    """
    if not leg:
        return None
    position = snapshot.positions[robot]
    local = snapshot.maps.get(robot)
    def valid(route):
        if not geometry.route_respects_known_obstacles(snapshot.grid, snapshot.resolution,
                snapshot.origin, route, cache=caches.setdefault('fused_obstacles', {})):
            return False
        return local is None or geometry.route_respects_known_obstacles(local['data'],
            local['resolution'], local['origin'], route,
            cache=caches.setdefault('local_obstacles', {}))
    full = (position, *leg)
    if valid(full):
        return full
    if len(leg)>1 and geometry.world_to_grid(*position,snapshot.resolution,*snapshot.origin)==(
            geometry.world_to_grid(*leg[0],snapshot.resolution,*snapshot.origin)):
        start = geometry.world_to_grid(*position,snapshot.resolution,*snapshot.origin)
        next_cell = geometry.world_to_grid(*leg[1],snapshot.resolution,*snapshot.origin)
        anchored = (position,*leg[1:])
        if geometry.has_known_line_of_sight(snapshot.grid,start,next_cell) and valid(anchored):
            return anchored
    return None


def robot_grid(snapshot, robot, caches):
    local = snapshot.maps.get(robot)
    if local is None:
        return snapshot.grid
    return geometry.constrained_return_grid(
        snapshot.grid, snapshot.resolution, snapshot.origin, local,
        caches.setdefault("constraints", {}))


def contact_route(snapshot, robot, position, caches):
    state = snapshot.batteries[robot]
    candidates = geometry.qualified_return_candidates(
        snapshot.grid, snapshot.resolution, snapshot.origin, position,
        (float(state["charge_x"]), float(state["charge_y"])),
        float(state.get("charge_radius_m", .8)), snapshot.maps.get(robot),
        caches.setdefault("returns", {}))
    return min((row for row in candidates if row["qualified"]),
               key=lambda row: (row["path_distance_m"], row["source"] != "local"),
               default=None)


def complete_budget(snapshot, robot, task_route, destination, caches, wait_sec=0.):
    """Fund the complete proposed task, endpoint return and current return."""
    state = snapshot.batteries.get(robot)
    if state is None:
        return 0.0
    current = contact_route(snapshot, robot, snapshot.positions[robot], caches)
    endpoint = contact_route(snapshot, robot, destination, caches)
    if current is None or endpoint is None or not task_route:
        return None
    keys = ("headquarters/fused_map_snapshot", robot + "/map_snapshot")
    map_age = max(snapshot.at_time - snapshot.sources[key] for key in keys
                  if key in snapshot.sources)
    pose_age = max(snapshot.at_time - snapshot.sources[robot + "/" + kind]
                   for kind in ("pose_state", "frame_state"))
    if not (0 <= map_age <= geometry.STATE_TTL_SEC["map_snapshot"]
            and 0 <= pose_age <= geometry.STATE_TTL_SEC["pose_state"]
            and math.isfinite(wait_sec) and wait_sec >= 0):
        return None
    model = (
        float(state.get("move_cost_per_m", 1.)),
        float(state.get("idle_cost_per_sec", .02)),
        float(state.get("return_path_factor", 2.)),
        float(state.get("nominal_speed_mps", .18)),
        float(state.get("return_safety_margin", 8.)),
        float(state.get("return_recovery_wait_sec", geometry.RETURN_RECOVERY_WAIT_SEC)),
        map_age, pose_age)
    task = geometry.battery_assignment_required_energy(
        route_length(task_route), endpoint["path_distance_m"], *model)
    reserve = geometry.battery_assignment_required_energy(
        0., current["path_distance_m"], *model)
    return max(task, reserve) + model[1] * wait_sec


def protected_returns(snapshot, caches):
    result = {}
    for robot, state in snapshot.batteries.items():
        if state["mode"] not in ("RETURNING", "CHARGING") and robot not in snapshot.charge_pending:
            continue
        if robot not in snapshot.maps or robot not in snapshot.positions:
            return None
        contact = contact_route(snapshot, robot, snapshot.positions[robot],
                                caches.setdefault(robot, {}))
        if contact is None:
            return None
        result[robot] = contact["route"]
    return result


def camera_cells(grid, cell, radius_cells, interest):
    hits = geometry.visible_unknown_gain(grid, cell, radius_cells, interest,
                                         return_cells=True)
    if not hits.size:
        return frozenset(), 0.0
    rows, columns = np.unravel_index(hits, grid.shape)
    radius = max(1, math.ceil(radius_cells))
    sectors = geometry.known_search_sector_table(
        radius, geometry.INITIAL_SEARCH_VIEW_FOV_RAD)
    masks = sectors[rows - cell[0] + radius, columns - cell[1] + radius]
    best = int(np.argmax(np.count_nonzero(masks, axis=0)))
    return frozenset(map(int, hits[masks[:, best]])), best * 2. * math.pi / 16.


def joint_motions(pools, reservations=(), maximum=3):
    """Compare compatible fleet choices and discount duplicated information.

    Each robot has a bounded, deterministic candidate pool, including wait.
    This is a joint heuristic over that pool, not a global-optimality claim.
    The unchanged 1.8 m route and 1.2 m exploration endpoint separation apply.
    """
    names = sorted(pools)
    best, best_score = (), (-math.inf, -math.inf)
    for choices in product(*(tuple(pools[name]) + (None,) for name in names)):
        motions = tuple(choice for choice in choices if choice is not None)
        if len(motions) > maximum:
            continue
        accepted = []
        valid = True
        cells, gain = set(), 0.
        for choice in motions:
            if any(geometry.routes_conflict(choice.route, route) for route in reservations):
                valid = False
                break
            for other in accepted:
                separation = (geometry.MIN_TARGET_SEPARATION_M
                              if choice.kind == other.kind == "exploration"
                              else geometry.RALLY_MIN_SEPARATION_M)
                if (math.dist((choice.pose.x, choice.pose.y), (other.pose.x, other.pose.y)) < separation
                        or geometry.routes_conflict(choice.route, other.route)):
                    valid = False
                    break
            if not valid:
                break
            new = len(choice.information_cells - cells)
            fraction = new / len(choice.information_cells) if choice.information_cells else 1.
            gain += choice.utility * fraction
            cells.update(choice.information_cells)
            accepted.append(choice)
        score = (gain, len(motions))
        if valid and score > best_score:
            best, best_score = motions, score
    return best


def _safe_endpoint(safe, snapshot, pose):
    cell = geometry.world_to_grid(pose.x, pose.y, snapshot.resolution, *snapshot.origin)
    return 0 <= cell[0] < safe.shape[0] and 0 <= cell[1] < safe.shape[1] and safe[cell]


def _escape(snapshot, beneficiary, protected, caches):
    """Clear an actual corridor before requesting traffic that would use it."""
    route = protected[beneficiary]
    target = route[-1]
    choices = []
    clearance = max(geometry.RALLY_ROUTE_SEPARATION_M,
                    float(snapshot.batteries.get(beneficiary, {}).get("charge_radius_m", .8))
                    + geometry.RALLY_DYNAMIC_CLEARANCE_M)
    for robot in snapshot.available:
        if robot == beneficiary or not geometry.routes_conflict(
                (snapshot.positions[robot],), route, clearance):
            continue
        if snapshot.batteries and snapshot.batteries[robot]["mode"] != "ACTIVE":
            continue
        grid = robot_grid(snapshot, robot, caches.setdefault(robot, {}))
        blocked = [position for peer, position in snapshot.positions.items() if peer != robot]
        view_range = (snapshot.target_range - snapshot.position_tolerance
                      if robot == snapshot.observer and snapshot.target is not None else None)
        pose = geometry.rally_yield_pose(
            grid, snapshot.resolution, snapshot.origin, snapshot.positions[robot],
            snapshot.target if view_range is not None else target,
            blocked_positions=blocked,
            reserved_routes=(*protected.values(), *snapshot.live_routes.values()),
            route_separation_m=clearance, visible_only=True,
            target_view_distance=view_range)
        if pose is None:
            continue
        actual, leg = geometry.plan_rally_leg(
            pose, grid, snapshot.resolution, snapshot.origin, snapshot.positions[robot],
            geometry.MAX_NAVIGATION_LEG_M, blocked_positions=blocked, visible_only=True)
        if actual is None or math.dist((actual.x, actual.y), (pose.x, pose.y)) > snapshot.resolution:
            continue
        full = qualified_motion_route(snapshot,robot,leg,caches[robot])
        if full is None:
            continue
        required = complete_budget(snapshot, robot, full, (pose.x, pose.y),
                                   caches[robot])
        if required is None:
            continue
        if snapshot.batteries and float(snapshot.batteries[robot]["energy"]) <= required:
            state = snapshot.batteries[robot]
            contact = contact_route(snapshot, robot, snapshot.positions[robot], caches[robot])
            reserve = complete_budget(snapshot, robot, (snapshot.positions[robot],),
                                      snapshot.positions[robot], caches[robot])
            target_energy = float(state["capacity"]) * float(state["charge_target_fraction"])
            actual_return = any(value["mode"] in ("RETURNING", "CHARGING")
                                for value in snapshot.batteries.values())
            if (not actual_return and contact is not None and reserve is not None
                    and reserve < float(state["energy"]) <= required < target_energy
                    and not any(geometry.routes_conflict(contact["route"], live)
                                for live in snapshot.live_routes.values())):
                return ChargeProposal(robot, required, contact["route"],
                                      "unfunded_return_clearance", (pose.x, pose.y))
            continue
        if any(geometry.routes_conflict(full, other) for peer, other in protected.items()
               if peer not in (robot, beneficiary)):
            continue
        if any(geometry.routes_conflict(full, live) for live in snapshot.live_routes.values()):
            continue
        kind = ("local_return_yield" if snapshot.batteries.get(beneficiary, {}).get("mode")
                in ("RETURNING", "CHARGING") else "charge_clearance")
        choices.append(MotionProposal(robot, kind, actual, full,
                                      1., required, beneficiary=beneficiary))
    return min(choices, key=lambda choice: (route_length(choice.route), choice.robot), default=None)


def plan_exploration(snapshot, caches, protected):
    pools, charges, blocked = {}, [], {}
    frontier = geometry.prepare_frontier_data(snapshot.grid, snapshot.resolution, defer_gain=True)
    camera_interest = geometry.camera_search_interest(
        snapshot.grid, snapshot.resolution, snapshot.origin, snapshot.views)
    combined_interest = camera_interest | (snapshot.grid < 0)
    reservations = (*snapshot.live_routes.values(), *protected.values())
    for robot in snapshot.available:
        state = snapshot.batteries.get(robot)
        if state is not None and (state["mode"] != "ACTIVE" or robot in snapshot.charge_pending):
            continue
        grid = robot_grid(snapshot, robot, caches.setdefault(robot, {}))
        bodies = [position for peer, position in snapshot.positions.items() if peer != robot]
        endpoint_mask = geometry.traversable_grid(grid, snapshot.resolution, geometry.ROBOT_CLEARANCE_M)
        rows, _ = geometry.robot_candidate_assignments(
            snapshot.grid, snapshot.resolution, snapshot.origin, robot,
            snapshot.positions[robot], snapshot.history, frontier,
            blocked_positions=bodies)
        search_cache = {}
        rows.extend(geometry.known_space_search_candidates(
            snapshot.grid, snapshot.resolution, snapshot.origin, robot,
            snapshot.positions[robot], (), snapshot.history, bodies,
            gain_cache=search_cache, face_interest=True,
            camera_views=snapshot.views, defer_gain=True))
        candidates, seen, geometric = [], set(), []
        route_cache = {}
        # Realize the actual dispatched endpoint before comparing bounds.
        # Frontier and known-camera generators use different old score units;
        # neither their order nor their unexecuted distant endpoint is an
        # upper bound on the new combined short-leg objective.
        for _, _, _, assignment in rows:
            pose, leg = geometry.plan_rally_leg(
                geometry.RallyPose(assignment.x, assignment.y, 0.), grid,
                snapshot.resolution, snapshot.origin, snapshot.positions[robot],
                geometry.MAX_NAVIGATION_LEG_M, blocked_positions=bodies,
                clearance_m=geometry.PATH_CLEARANCE_M, visible_only=False,
                route_cache=route_cache)
            if pose is None or not _safe_endpoint(endpoint_mask, snapshot, pose):
                continue
            cell = geometry.world_to_grid(pose.x, pose.y, snapshot.resolution, *snapshot.origin)
            if cell in seen:
                continue
            seen.add(cell)
            full = qualified_motion_route(snapshot,robot,leg,caches[robot])
            if full is None:
                continue
            if route_length(full) < geometry.USEFUL_TRAVEL_M:
                continue
            if any(geometry.routes_conflict(full, reserved) for reserved in reservations):
                continue
            radius=math.ceil(geometry.INFORMATION_RADIUS_M/snapshot.resolution)+1
            r,c=cell
            count=int(np.count_nonzero(combined_interest[
                max(0,r-radius):min(snapshot.grid.shape[0],r+radius+1),
                max(0,c-radius):min(snapshot.grid.shape[1],c+radius+1)]))
            reuse=geometry.target_reuse_penalty((pose.x,pose.y),snapshot.history)
            bound=geometry.exploration_utility(count,0,route_length(full))*reuse
            if bound>0:
                geometric.append((bound,pose,full,cell,reuse,
                    math.atan2(assignment.y-pose.y,assignment.x-pose.x)))

        def refine(candidate):
            _,pose,full,cell,reuse,frontier_yaw=candidate
            mapping = frozenset(map(int, geometry.visible_unknown_gain(
                snapshot.grid, cell, geometry.INFORMATION_RADIUS_M / snapshot.resolution,
                return_cells=True)))
            visual, yaw = camera_cells(snapshot.grid, cell,
                                       geometry.INFORMATION_RADIUS_M / snapshot.resolution,
                                       camera_interest)
            information = mapping | visual
            if not information:
                return None
            if not visual:
                yaw = frontier_yaw
            pose = geometry.RallyPose(pose.x, pose.y, yaw)
            required = complete_budget(snapshot, robot, full, (pose.x, pose.y), caches[robot])
            if required is None:
                blocked[robot] = "no_qualified_complete_return"
                return None
            utility = geometry.exploration_utility(len(information), 0, route_length(full))*reuse
            choice = MotionProposal(robot, "exploration", pose, full, utility,
                                    required, information)
            if state is None or float(state["energy"]) > required:
                return choice
            elif required < float(state["capacity"]) * float(state["charge_target_fraction"]):
                contact = contact_route(snapshot, robot, snapshot.positions[robot], caches[robot])
                charges.append(ChargeProposal(robot, required, contact["route"], "unfunded_information_task",
                                              (pose.x, pose.y)))
            return None

        # Reuse the reviewed lazy ranking algorithm. Stop only after it has
        # proved each of the retained eight actual funded scores against all
        # remaining bounds, not after eight feasible rows in generator order.
        for choice in geometry.lazy_priority_candidates(geometric,evaluate=refine,
                upper_bound=lambda item:item.utility if isinstance(item,MotionProposal) else item[0],
                priority=lambda item:item.utility):
            candidates.append(choice)
            if len(candidates)==8:
                break
        candidates.sort(key=lambda choice: (-choice.utility, choice.pose.x, choice.pose.y))
        pools[robot] = candidates[:8]
        if (state is not None and candidates and snapshot.completed_legs.get(robot, 0) > 0
                and int(state.get("charge_count", 0)) == 0
                and geometry.PATH_CLEARANCE_M < math.dist(snapshot.positions[robot],
                    (float(state["charge_x"]), float(state["charge_y"])))
                <= 2. * float(state.get("charge_radius_m", .8))
                and float(state["energy"]) <= .25 * float(state["capacity"]) * float(state["charge_target_fraction"])):
            contact = contact_route(snapshot, robot, snapshot.positions[robot], caches[robot])
            if contact is not None:
                threshold = .25 * float(state["capacity"]) * float(state["charge_target_fraction"])
                charges.append(ChargeProposal(robot, max(candidates[0].required_energy, threshold),
                                              contact["route"], "low_energy_after_actual_work",
                                              (candidates[0].pose.x, candidates[0].pose.y)))
    motions = joint_motions(pools, reservations, snapshot.maximum_concurrent)
    best_charges = {}
    for charge in charges:
        if pools.get(charge.robot) and charge.reason == "unfunded_information_task":
            continue
        prior = best_charges.get(charge.robot)
        if prior is None or charge.required_energy < prior.required_energy:
            best_charges[charge.robot] = charge
    return FleetProposal(snapshot, motions, tuple(best_charges.values()), blocked=blocked)


def plan_rally(snapshot, caches, protected):
    poses = dict(snapshot.final_poses)
    if poses:
        # A permanent assignment is valid only on the current delivered map.
        # Reconsider the fleet together after all owned legs and returns close;
        # a temporarily parked peer alone must not invalidate the final plan.
        valid = True
        safe = geometry.traversable_grid(snapshot.grid, snapshot.resolution, geometry.RALLY_CLEARANCE_M)
        for robot, pose in poses.items():
            cell = geometry.world_to_grid(pose.x, pose.y, snapshot.resolution, *snapshot.origin)
            grid = robot_grid(snapshot, robot, caches.setdefault(robot, {}))
            _, route = geometry.plan_rally_leg(pose, grid, snapshot.resolution,
                snapshot.origin, snapshot.positions[robot])
            if (not 0 <= cell[0] < safe.shape[0] or not 0 <= cell[1] < safe.shape[1] or not safe[cell]
                    or not geometry.rally_target_view(snapshot.grid, snapshot.resolution, snapshot.origin,
                        (pose.x, pose.y), snapshot.target, snapshot.target_range - snapshot.position_tolerance)
                    or not route or snapshot.batteries and contact_route(snapshot, robot,
                        (pose.x, pose.y), caches[robot]) is None):
                valid = False
                break
        if not valid:
            if snapshot.live_routes or protected:
                return FleetProposal(snapshot, blocked={"fleet": "invalid_final_wait_for_owned_traffic"})
            poses = {}
    if not poses:
        required = snapshot.required or tuple(snapshot.positions)
        future = {robot: snapshot.positions[robot] for robot in required}
        for robot, state in snapshot.batteries.items():
            if state["mode"] in ("RETURNING", "CHARGING"):
                future[robot] = float(state["charge_x"]), float(state["charge_y"])
        poses = geometry.assign_rally_poses(
            snapshot.grid, snapshot.resolution, snapshot.origin, future,
            snapshot.target, battery_states={robot: snapshot.batteries[robot] for robot in required}
            if snapshot.batteries else None,
            observer_robot=snapshot.observer, current_positions=snapshot.positions,
            hold_sec=snapshot.hold_sec, return_maps=snapshot.maps,
            approach_grids={robot:robot_grid(snapshot,robot,caches.setdefault(robot,{}))
                            for robot in required})
        if len(poses) == len(required):
            return FleetProposal(snapshot, final_poses=poses)
        return plan_target_survey(snapshot, caches, protected)
    bases, travel, charge_time, paths, blocked = {}, {}, {}, {}, {}
    for robot, pose in poses.items():
        state = snapshot.batteries.get(robot)
        grid = robot_grid(snapshot, robot, caches.setdefault(robot, {}))
        _, route = geometry.plan_rally_leg(
            pose, grid, snapshot.resolution, snapshot.origin, snapshot.positions[robot],
            blocked_positions=[position for peer, position in snapshot.positions.items() if peer != robot])
        if not route:
            blocked[robot] = "body_or_map_blocks_complete_approach"
            continue
        full = qualified_motion_route(snapshot,robot,(*route,(pose.x,pose.y)),caches[robot])
        if full is None:
            blocked[robot] = 'continuous_local_approach_unavailable'
            continue
        paths[robot] = full
        speed = float(state.get("nominal_speed_mps", .18)) if state is not None else .18
        travel[robot] = route_length(full) / speed
        base = complete_budget(snapshot, robot, full, (pose.x, pose.y), caches[robot], snapshot.hold_sec)
        if base is None:
            blocked[robot] = "no_qualified_complete_return"
            continue
        bases[robot] = base
        if state is not None:
            contact = contact_route(snapshot, robot, snapshot.positions[robot], caches[robot])
            charge_time[robot] = (float(state.get("charge_duration_sec", 6.))
                                 + contact["path_distance_m"] * float(state.get("return_path_factor", 2.)) / speed
                                 + float(state.get("return_recovery_wait_sec", geometry.RETURN_RECOVERY_WAIT_SEC)))
    if snapshot.batteries:
        requirements, waits = geometry.rally_wait_requirements(
            bases, snapshot.batteries,
            {robot: state["mode"] for robot, state in snapshot.batteries.items()},
            travel, charge_time)
    else:
        requirements, waits = bases, dict.fromkeys(bases, 0.)
    pools, charges = {}, []
    for robot in snapshot.available:
        if robot not in paths or robot not in requirements:
            continue
        pose, state = poses[robot], snapshot.batteries.get(robot)
        required = requirements[robot]
        if state is not None and (state["mode"] != "ACTIVE" or robot in snapshot.charge_pending):
            continue
        if state is not None and float(state["energy"]) <= required:
            if required <= float(state["capacity"]) * float(state["charge_target_fraction"]):
                contact = contact_route(snapshot, robot, snapshot.positions[robot], caches[robot])
                charges.append(ChargeProposal(robot, required, contact["route"], "whole_rally_and_wait",
                                              (pose.x, pose.y)))
            else:
                blocked[robot] = "complete_rally_exceeds_charge_capacity"
            continue
        if robot in snapshot.arrived:
            continue
        limit = min(geometry.MAX_NAVIGATION_LEG_M,
                    geometry.rally_leg_limit(snapshot.attempts.get(robot, 0)))
        grid = robot_grid(snapshot, robot, caches[robot])
        actual, leg = geometry.plan_rally_leg(
            pose, grid, snapshot.resolution, snapshot.origin, snapshot.positions[robot],
            limit, blocked_positions=[position for peer, position in snapshot.positions.items() if peer != robot],
            visible_only=False)
        if actual is None:
            continue
        if math.dist((actual.x, actual.y), (pose.x, pose.y)) > snapshot.position_tolerance:
            actual = geometry.route_arrival_yaw(leg, pose.yaw)
            actual = geometry.RallyPose(leg[-1][0], leg[-1][1], actual)
        full = qualified_motion_route(snapshot,robot,leg,caches[robot])
        if full is None:
            continue
        utility = 1. / (geometry.PLANNING_OVERHEAD_SEC + route_length(paths[robot]))
        if robot == snapshot.observer:
            utility *= 2.
        pools[robot] = [MotionProposal(robot, "rally", actual, full, utility,
                                      required, complete_route=paths[robot])]
    reservations = (*snapshot.live_routes.values(), *protected.values())
    motions = joint_motions(pools, reservations, snapshot.maximum_concurrent)
    if not motions and blocked:
        # Clearing a real parked body is a dependency of a complete approach.
        # A future priority route alone does not acquire physical ownership.
        for beneficiary in sorted(blocked):
            if beneficiary not in snapshot.available:
                continue
            grid = robot_grid(snapshot, beneficiary, caches.setdefault(beneficiary, {}))
            for peer in snapshot.available:
                if peer == beneficiary:
                    continue
                _, route = geometry.plan_rally_leg(
                    poses[beneficiary], grid, snapshot.resolution, snapshot.origin,
                    snapshot.positions[beneficiary],
                    blocked_positions=[position for robot, position in snapshot.positions.items()
                                       if robot not in (beneficiary, peer)])
                if not route:
                    continue
                escape = _escape(snapshot, beneficiary,
                                 {beneficiary: (snapshot.positions[beneficiary], *route)}, caches)
                if escape is not None and escape.robot == peer:
                    if isinstance(escape, ChargeProposal):
                        return FleetProposal(snapshot, charges=(escape,), final_poses=poses,
                                             wait_budgets=waits, blocked=blocked)
                    motions = (MotionProposal(escape.robot, "rally_yield", escape.pose,
                        escape.route, escape.utility, escape.required_energy,
                        beneficiary=beneficiary),)
                    break
            if motions:
                break
    return FleetProposal(snapshot, motions, tuple(charges), poses, waits, blocked)


def plan_target_survey(snapshot, caches, protected):
    """Observe missing target-area geometry from an actual funded safe route."""
    if snapshot.survey_attempts >= snapshot.survey_limit:
        return FleetProposal(snapshot, blocked={"fleet": "target_survey_attempts_exhausted"})
    modes = {robot: state["mode"] for robot, state in snapshot.batteries.items()}
    if not snapshot.batteries:
        modes = dict.fromkeys(snapshot.positions, "ACTIVE")
    rows = geometry.target_survey_candidates(snapshot.grid, snapshot.resolution,
        snapshot.origin, snapshot.positions, modes, snapshot.target,
        snapshot.target_range, snapshot.position_tolerance)
    desired = []
    # Missing local approach geometry must be observed by the affected mapper.
    # Peer-fused free space cannot erase that robot's positive obstacles. Use
    # the first disputed cell on its complete fused approach only as an
    # information destination; the actual move remains locally constrained.
    for robot in snapshot.available:
        grid = robot_grid(snapshot, robot, caches.setdefault(robot, {}))
        final = snapshot.final_poses.get(robot) or geometry.rally_survey_pose(
            snapshot.grid, snapshot.resolution, snapshot.origin, snapshot.positions[robot], snapshot.target)
        if final is None:
            continue
        _, local_route = geometry.plan_rally_leg(final, grid, snapshot.resolution,
            snapshot.origin, snapshot.positions[robot], math.inf)
        if local_route:
            continue
        _, fused_route = geometry.plan_rally_leg(final, snapshot.grid, snapshot.resolution,
            snapshot.origin, snapshot.positions[robot], math.inf)
        local_safe = geometry.traversable_grid(grid,snapshot.resolution,geometry.PATH_CLEARANCE_M)
        for point in fused_route:
            cell = geometry.world_to_grid(*point, snapshot.resolution, *snapshot.origin)
            if not local_safe[cell] and snapshot.grid[cell]==0:
                view = geometry.rally_survey_pose(grid, snapshot.resolution, snapshot.origin,
                                                snapshot.positions[robot], point)
                if view is None:
                    # A disputed cell can already be close. Observe it from
                    # another reachable viewpoint rather than forcing a
                    # strictly closer pose that cannot exist outside the wall.
                    safe = geometry.traversable_grid(grid,snapshot.resolution,geometry.ROBOT_CLEARANCE_M)
                    field = geometry.exploration_distance_field(grid,safe,snapshot.resolution,
                                                                snapshot.origin,snapshot.positions[robot])
                    if field is not None:
                        raster_rows,raster_columns=np.indices(grid.shape)
                        xs=snapshot.origin[0]+(raster_columns+.5)*snapshot.resolution
                        ys=snapshot.origin[1]+(raster_rows+.5)*snapshot.resolution
                        squared=(xs-point[0])**2+(ys-point[1])**2
                        eligible=safe & np.isfinite(field) & (squared>=.7**2) & (
                            squared<=geometry.INFORMATION_RADIUS_M**2) & (
                            field>=geometry.USEFUL_TRAVEL_M)
                        for row,column in sorted(np.argwhere(eligible),key=lambda cell:field[tuple(cell)]):
                            if geometry.has_known_line_of_sight(snapshot.grid,(row,column),cell):
                                x,y=geometry.grid_to_world(row,column,snapshot.resolution,*snapshot.origin)
                                view=geometry.RallyPose(x,y,math.atan2(point[1]-y,point[0]-x))
                                break
                if view is not None:
                    desired.append((robot, view, 1., point))
                break
    desired.extend((row["robot"], geometry.RallyPose(*row["desired_position"], row["desired_yaw"]),
                    row["utility"], snapshot.target) for row in rows)
    for robot in snapshot.available:
        pose = geometry.rally_survey_pose(snapshot.grid, snapshot.resolution,
            snapshot.origin, snapshot.positions[robot], snapshot.target)
        if pose is not None:
            desired.append((robot, pose, 1., snapshot.target))
    for robot, pose, utility, information_target in desired:
        if robot not in snapshot.available:
            continue
        grid = robot_grid(snapshot, robot, caches.setdefault(robot, {}))
        actual, route = geometry.plan_rally_leg(pose, grid, snapshot.resolution,
            snapshot.origin, snapshot.positions[robot], geometry.MAX_NAVIGATION_LEG_M,
            [position for peer, position in snapshot.positions.items() if peer != robot])
        if actual is None:
            continue
        full = qualified_motion_route(snapshot, robot, route, caches[robot])
        if full is None:
            continue
        if route_length(full) <= snapshot.position_tolerance:
            continue
        if any(geometry.routes_conflict(full, reserved)
               for reserved in (*protected.values(), *snapshot.live_routes.values())):
            continue
        actual = geometry.RallyPose(actual.x, actual.y,
            math.atan2(information_target[1] - actual.y, information_target[0] - actual.x))
        required = complete_budget(snapshot, robot, full, (actual.x, actual.y), caches[robot])
        if required is None or snapshot.batteries and snapshot.batteries[robot]["energy"] <= required:
            continue
        return FleetProposal(snapshot, motions=(MotionProposal(robot, "target_information_survey",
            actual, full, utility, required),), blocked={"fleet": "incomplete_target_area_assignment"})
    return FleetProposal(snapshot, blocked={"fleet": "no_funded_target_survey"})


def plan_blind_scan(snapshot, caches, protected):
    """Four headings at a currently safe pose, independent of any old target."""
    if snapshot.live_routes or protected:
        return None
    for robot in sorted(snapshot.available, key=lambda name: (snapshot.scan_steps.get(name, 0), name)):
        count = snapshot.scan_steps.get(robot, 0)
        if count >= 4:
            continue
        grid = robot_grid(snapshot, robot, caches.setdefault(robot, {}))
        cell = geometry.world_to_grid(*snapshot.positions[robot], snapshot.resolution, *snapshot.origin)
        safe = geometry.traversable_grid(grid, snapshot.resolution, geometry.PATH_CLEARANCE_M)
        if not 0 <= cell[0] < safe.shape[0] or not 0 <= cell[1] < safe.shape[1] or not safe[cell]:
            continue
        route = (snapshot.positions[robot],)
        required = complete_budget(snapshot, robot, route, route[-1], caches[robot],
                                   geometry.RALLY_GOAL_TIMEOUT_SEC)
        if required is None or snapshot.batteries and snapshot.batteries[robot]["energy"] <= required:
            continue
        pose = geometry.RallyPose(*snapshot.positions[robot], count * math.pi / 2.)
        return FleetProposal(snapshot, motions=(MotionProposal(robot, "target_reacquisition_scan",
            pose, route, 1., required, wait_sec=geometry.RALLY_GOAL_TIMEOUT_SEC),))
    return None


def plan_fleet(snapshot):
    started = time.perf_counter()
    caches = {}
    protected = protected_returns(snapshot, caches)
    if protected is None:
        result = FleetProposal(snapshot, blocked={"fleet": "unknown_live_return_corridor"})
    else:
        escape = next((choice for beneficiary in sorted(protected)
                       if (choice := _escape(snapshot, beneficiary, protected, caches)) is not None), None)
        if escape is not None:
            if isinstance(escape, ChargeProposal):
                result = FleetProposal(snapshot, charges=(escape,), final_poses=snapshot.final_poses)
            else:
                result = FleetProposal(snapshot, motions=(escape,), final_poses=snapshot.final_poses)
        elif snapshot.target is not None and snapshot.phase in ("FOUND", "RALLY"):
            result = plan_rally(snapshot, caches, protected)
        else:
            result = (plan_blind_scan(snapshot, caches, protected)
                      if snapshot.phase in ("FOUND", "RALLY") else None)
            if result is None:
                result = plan_exploration(snapshot, caches, protected)
    return FleetProposal(result.snapshot, result.motions, result.charges,
                         result.final_poses, result.wait_budgets, result.blocked,
                         time.perf_counter() - started)
