"""Observed-grid execution of supplied subgoals; never exploration selection.

This kinematic proxy is not Nav2 or the native reach guard. It reuses native
observed-grid path geometry and necessary pair geometry, with explicit proxy
state/frame assumptions. Truth geometry and evaluator state are not arguments.
"""
import math

import numpy as np

from .mr3_observation import (
    CLEARANCE_M, GOAL_XY_TOLERANCE_M, SEED_RULES, _cell, _path_distances, native_traversable,
)
from .mr3_reach_geometry import Direction, disk, normal, pair_certificate
from .mr3_seed_certificate import (
    _number, canonical_cell_centre, canonical_seed_cell,
    certify_estimated_segment, certify_seed_pose_bridge,
)

ROBOTS = ("tb1", "tb2", "tb3")


def _lookahead_cells(traversable, field, cell):
    """The existing bounded supplied-goal descent, retaining every node."""
    row, col = cell
    result = []
    for _ in range(5):
        choices = []
        for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (-1, 1), (1, -1), (1, 1)):
            r, c = row + dr, col + dc
            if not (0 <= r < traversable.shape[0] and 0 <= c < traversable.shape[1]) \
                    or not traversable[r, c]:
                continue
            if dr and dc and not (traversable[row, c] and traversable[r, col]):
                continue
            if field[r, c] < field[row, col] - 1e-9:
                choices.append((field[r, c], r, c))
        if not choices:
            break
        _, row, col = min(choices)
        result.append((row, col))
    return result


class ProxyNavigator:
    def __init__(self, *, seed_rule="legacy", start_graph_rule="original-seed-cell"):
        if seed_rule not in SEED_RULES:
            raise ValueError("unsupported seed rule")
        from .mr3_observation import validate_start_graph_rule
        validate_start_graph_rule(start_graph_rule, seed_rule=seed_rule)
        self.seed_rule = seed_rule
        self.start_graph_rule = start_graph_rule
        self.paths = {}
        self.blocked_quanta = {name: 0 for name in ROBOTS}

    def _seed_bridge_velocity(self, name, state, navigation, cell, clearance):
        """Exact-mode recentering only while the old scalar pose bound fails.

        Rotation is in place. Translation has w=0 and is separately certified
        over its proposed fixed 20ms straight segment. No curve is borrowed
        from the pose-to-centre certificate; no graph/seed/pose is changed.
        This remains estimated proxy geometry, not a plant-tracking proof.
        """
        grid, resolution, origin = navigation["grid"], navigation["resolution"], navigation["origin"]
        x = origin[0] + (cell[1] + .5) * resolution
        y = origin[1] + (cell[0] + .5) * resolution
        pose = (state["x"], state["y"])
        distance = math.dist(pose, (x, y))  # Same legacy offset primitive as observation.
        if float(clearance[cell]) - distance >= CLEARANCE_M:
            return None  # Resume the unchanged graph/lookahead controller.
        bridge = certify_seed_pose_bridge(grid, resolution, origin, pose, cell,
                                         seed_cell_traversable=True)
        if not bridge["accepted"]:
            self.blocked_quanta[name] += 1
            return (0., 0.)
        angle = math.atan2(y - pose[1], x - pose[0]) - state["yaw"]
        angle = math.atan2(math.sin(angle), math.cos(angle))
        if abs(angle) > .1:
            return (0., max(-.6, min(.6, 2 * angle)))
        # Fixed worker quantum, not a caller-tunable horizon. Limit displacement
        # to remaining centre distance; angular tolerance alone authorizes none.
        linear = min(.12, distance / .02)
        if linear * .02 > distance:
            linear = math.nextafter(linear, 0.)
        proposed = (pose[0] + linear * .02 * math.cos(state["yaw"]),
                    pose[1] + linear * .02 * math.sin(state["yaw"]))
        if not certify_estimated_segment(grid, resolution, origin, pose, proposed)["accepted"]:
            self.blocked_quanta[name] += 1
            return (0., 0.)
        return (linear, 0.)

    def _exact_waypoint_velocity(self, name, state, navigation, waypoint):
        """Execute an already certified v2 waypoint without borrowing an arc.

        Every moving proposal is straight for the worker's fixed 20ms quantum,
        independently certified, and no longer than the remaining waypoint
        distance. This is estimated geometry, not a tracking guarantee.
        """
        pose = (state["x"], state["y"])
        distance = math.dist(pose, waypoint)
        if not distance:
            return (0., 0.)
        angle = math.atan2(waypoint[1] - pose[1], waypoint[0] - pose[0]) - state["yaw"]
        angle = math.atan2(math.sin(angle), math.cos(angle))
        if abs(angle) > .1:
            return (0., max(-.6, min(.6, 2 * angle)))
        linear = min(.12, distance / .02)
        # Check actual represented endpoints, including addition rounding. A
        # rounded-up short proposal may reduce speed by a few ULPs, otherwise
        # it stops rather than overshooting or snapping. No clearance changes.
        start_q = tuple(_number(value) for value in pose)
        remaining2 = sum((_number(waypoint[i]) - start_q[i]) ** 2 for i in range(2))
        for _ in range(4):
            proposed = (pose[0] + linear * .02 * math.cos(state["yaw"]),
                        pose[1] + linear * .02 * math.sin(state["yaw"]))
            proposed2 = sum((_number(proposed[i]) - start_q[i]) ** 2 for i in range(2))
            if proposed2 <= remaining2:
                break
            linear = math.nextafter(linear, 0.)
        else:
            self.blocked_quanta[name] += 1
            return (0., 0.)
        if not certify_estimated_segment(
                navigation["grid"], navigation["resolution"], navigation["origin"],
                pose, proposed)["accepted"]:
            self.blocked_quanta[name] += 1
            return (0., 0.)
        return (linear, 0.)

    def _exact_goal_velocity(self, name, state, navigation, cell, waypoints):
        """v2: certify the existing goal route longest first, then same seed."""
        grid, resolution, origin = navigation["grid"], navigation["resolution"], navigation["origin"]
        pose = (state["x"], state["y"])
        for waypoint_cell in reversed(waypoints):
            waypoint = canonical_cell_centre(waypoint_cell, resolution, origin)
            if certify_estimated_segment(grid, resolution, origin, pose, waypoint)["accepted"]:
                return self._exact_waypoint_velocity(name, state, navigation, waypoint)
        # No new graph node or goal is sought. This is only the same already
        # traversable canonical seed centre, with its entire bridge certified.
        bridge = certify_seed_pose_bridge(grid, resolution, origin, pose, cell,
                                         seed_cell_traversable=True)
        if bridge["accepted"]:
            return self._exact_waypoint_velocity(name, state, navigation,
                canonical_cell_centre(cell, resolution, origin))
        self.blocked_quanta[name] += 1
        return (0., 0.)

    @staticmethod
    def _point_graph_continuation(navigation, proposed, anchor, route, traversable, field):
        """A retained or handed-off original anchor certifies the next point.

        This is a nominal fixed-map/goal invariant, not a tracking guarantee.
        The handoff set contains only this supplied-goal route's original
        nodes; it never searches for an exploration target or widens 3x3.
        """
        grid, resolution, origin = navigation["grid"], navigation["resolution"], navigation["origin"]
        cell = canonical_seed_cell(proposed, resolution, origin, grid.shape)
        if cell is None or grid[cell] != 0:
            return None
        for node in dict.fromkeys((anchor, *route)):
            if (not (0 <= node[0] < grid.shape[0] and 0 <= node[1] < grid.shape[1])
                    or max(abs(node[0] - cell[0]), abs(node[1] - cell[1])) > 1
                    or not traversable[node] or not math.isfinite(field[node])):
                continue
            centre = canonical_cell_centre(node, resolution, origin)
            if certify_estimated_segment(grid, resolution, origin, proposed, centre)["accepted"]:
                return node
        return None

    def _point_graph_velocity(self, name, state, navigation, traversable, field):
        """Connect a virtual start to the unchanged supplied-goal graph."""
        from .mr3_point_graph import point_graph_attachments
        grid, resolution, origin = navigation["grid"], navigation["resolution"], navigation["origin"]
        pose = (state["x"], state["y"])
        attachments = point_graph_attachments(grid, resolution, origin, pose)
        choices = []
        for entry in attachments["anchors"]:
            node = tuple(entry["cell"])
            if traversable[node] and math.isfinite(field[node]):
                cost = entry["bridge_length_m"] + float(field[node])
                if math.isfinite(cost):
                    choices.append((cost, *node))
        if not choices:
            self.blocked_quanta[name] += 1
            return (0., 0.)
        _, row, col = min(choices)
        anchor = (row, col)
        route = _lookahead_cells(traversable, field, anchor)
        # The connection anchor is not an exact-centre arrival requirement.
        # Try the original descending route directly, then its certified entry
        # bridge. This avoids a zero-length-centre deadpoint far from the goal.
        for node in (*reversed(route), anchor):
            waypoint = canonical_cell_centre(node, resolution, origin)
            if not certify_estimated_segment(grid, resolution, origin, pose, waypoint)["accepted"]:
                continue
            output = self._exact_waypoint_velocity(name, state, navigation, waypoint)
            if output[1]:
                return output  # In-place rotation retains the nominal point.
            if not output[0]:
                continue
            proposed = (pose[0] + output[0] * .02 * math.cos(state["yaw"]),
                        pose[1] + output[0] * .02 * math.sin(state["yaw"]))
            if self._point_graph_continuation(navigation, proposed, anchor, route, traversable, field) is not None:
                return output
        self.blocked_quanta[name] += 1
        return (0., 0.)

    def target_velocity(self, name, state, goal, navigation):
        if goal is None:
            return (0., 0.), False
        distance = math.hypot(goal["x"] - state["x"], goal["y"] - state["y"])
        if distance <= GOAL_XY_TOLERANCE_M:
            return (0., 0.), True
        grid, resolution, origin = navigation["grid"], navigation["resolution"], navigation["origin"]
        digest = navigation.get("payload_sha256")
        if not isinstance(digest, str) or len(digest) != 64:
            raise ValueError("delivered navigation map requires its content identity")
        # Delivery/header identities still have to be present, but a new stamp
        # alone does not change this purely geometric field. Pack the current
        # bytes each time so mutable arrays or reused payload IDs cannot hide a
        # changed input. Only one field per robot is retained.
        key = (grid.dtype.str, grid.shape, grid.tobytes(order="C"), resolution,
               tuple(origin), goal["x"], goal["y"])
        cached = self.paths.get(name)
        if cached is None or cached[0] != key:
            traversable, clearance = native_traversable(grid, resolution)
            target = _cell(goal["x"], goal["y"], resolution, origin, grid.shape)
            distances, ids = _path_distances(traversable, [target], resolution)
            field = np.full(grid.shape, np.inf)
            field[ids >= 0] = distances[0, ids[ids >= 0]]
            cached = (key, traversable, field)
            if self.seed_rule != "legacy":
                cached += (clearance,)
            self.paths[name] = cached
        _, traversable, field = cached[:3]
        if self.start_graph_rule == "point-attachment-3x3-v1":
            return self._point_graph_velocity(name, state, navigation, traversable, field), False
        cell = (canonical_seed_cell((state["x"], state["y"]), resolution, origin, grid.shape)
                if self.seed_rule == "exact-point-bridge-v2" else
                _cell(state["x"], state["y"], resolution, origin, grid.shape))
        if cell is None or not traversable[cell] or not math.isfinite(field[cell]):
            self.blocked_quanta[name] += 1
            return (0., 0.), False
        if self.seed_rule == "exact-point-bridge-v2":
            return self._exact_goal_velocity(name, state, navigation, cell,
                _lookahead_cells(traversable, field, cell)), False
        if self.seed_rule != "legacy":
            bridge_output = self._seed_bridge_velocity(name, state, navigation, cell, cached[3])
            if bridge_output is not None:
                return bridge_output, False
        waypoints = _lookahead_cells(traversable, field, cell)
        row, col = waypoints[-1] if waypoints else cell
        x, y = origin[0] + (col + .5) * resolution, origin[1] + (row + .5) * resolution
        angle = math.atan2(y - state["y"], x - state["x"]) - state["yaw"]
        angle = math.atan2(math.sin(angle), math.cos(angle))
        return (.12 * max(0., math.cos(angle)) if abs(angle) < .45 else 0.,
                max(-.6, min(.6, 2 * angle))), False

    def commands(self, states, goals, navigation_maps, scans, now):
        outputs, reached = {}, []
        for name in ROBOTS:
            output, done = self.target_velocity(name, states[name], goals.get(name), navigation_maps[name])
            if done:
                reached.append(name)
            scan = scans[name]
            # A local sensor stop is not an exploration fallback or truth test.
            forward = np.cos(scan["angles"]) > .7
            if output[0] > 0 and np.min(scan["ranges"][forward]) < .40:
                output = (0., output[1])
                self.blocked_quanta[name] += 1
            outputs[name] = output
        denied = set()
        for index, left in enumerate(ROBOTS):
            for right in ROBOTS[index + 1:]:
                delta = tuple(states[right][k] - states[left][k] for k in ("x", "y"))
                reaches = []
                for name in (left, right):
                    v, _ = outputs[name]
                    yaw = states[name]["yaw"]
                    direction = (math.cos(yaw), math.sin(yaw))
                    reaches.append(normal((Direction(direction, direction, .05),)) if v else disk())
                ages = [max(0, round((now - states[n]["source_stamp"]) * 1e9)) for n in (left, right)]
                if max(ages) > 200_000_000:
                    denied.update((left, right))
                    continue
                certificate = pair_certificate(delta, delta, ages, *reaches,
                    legacy_hard_gates_passed=True, common_world_odom_calibrated=True)
                if not certificate["geometric_necessary"]:
                    denied.update((left, right))
        for name in denied:
            outputs[name] = (0., 0.)
            self.blocked_quanta[name] += 1
        return outputs, reached
