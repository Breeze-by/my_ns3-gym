"""One mission executor for joint planning, local returns and all navigation.

The accepted baseline remains available for controlled comparisons. The new
executor reuses its delivered-state adapters, protocol and geometry, but does
not run the baseline's independent exploration/rally dispatch state machines.
"""

from dataclasses import dataclass, field, replace
import hashlib
import json
import math
import threading
import time

from action_msgs.msg import GoalStatus
from geometry_msgs.msg import PoseStamped
from nav2_msgs.action import NavigateToPose
from std_msgs.msg import String

from . import control as geometry
from .fleet_planning import (
    FleetSnapshot, MotionProposal, PlanningWorker, camera_cells, complete_budget,
    contact_route, protected_returns, robot_grid, route_length,
    qualified_motion_route,
)


@dataclass
class NavigationTask:
    generation: int
    proposal: MotionProposal
    phase: str
    started_at: float
    handle: object = None
    cancel_reason: str | None = None
    last_progress_at: float = 0.0
    best_distance: float = math.inf
    sources: dict = field(default_factory=dict)
    progress_position: tuple | None = None
    progress_yaw: float | None = None
    progress_source: float = -math.inf


class GlobalHeadquartersControl(geometry.HeadquartersControl):
    def __init__(self):
        super().__init__()
        mode = self.get_parameter("mission_planner").value
        self.planning_worker = PlanningWorker() if self.global_enabled else None
        self.navigation_tasks = {}
        self.navigation_generation = 0
        self.plan_generation = 0
        self.last_global_diagnostic_at = -math.inf
        self.last_global_dispatch_at = -math.inf
        self.last_plan_context = None
        self.global_charge_intent = None
        self.global_charge_requested_at = None
        self.global_charge_started = False
        self.global_confirmations = {}
        self.global_nav_failures = {}
        self.global_blocked_since = {}
        self.global_scan_steps = {}
        self.global_survey_attempts = 0
        self.global_map_encodings = {}
        self.admission_geometry_caches = {}
        self.return_geometry_caches = {}
        self.nominal_rally_caches = {}
        self.global_charge_context = None
        self.deferred_charge_intent = None
        self.last_hold_work_sec = 0.
        self.last_hold_block_reason = None
        self.get_logger().info("Mission planner: " + mode)

    def create_snapshot_subscription(self, msg_type, topic, callback, qos_profile):
        if not hasattr(self, 'global_enabled'):
            mode = self.declare_parameter('mission_planner', 'global').value
            if mode not in ('global', 'baseline'):
                raise ValueError('mission_planner must be global or baseline')
            self.global_enabled = mode == 'global'
            if self.global_enabled:
                self.received_snapshot_lock = threading.Lock()
                self.received_snapshot_callbacks = {}
                self.received_snapshot_guard = self.create_guard_condition(self.drain_received_snapshots)
        if not self.global_enabled:
            return super().create_snapshot_subscription(msg_type, topic, callback, qos_profile)

        def received(message):
            if self.shutdown_requested:
                return
            producer = None
            if topic.endswith('/target_detection'):
                try:
                    producer = json.loads(message.data)['robot']
                    if producer not in self.robot_positions:
                        producer = None
                except (KeyError, TypeError, ValueError, json.JSONDecodeError):
                    producer = None
            with self.received_snapshot_lock:
                self.received_snapshot_callbacks[topic, producer] = callback, message
            try:
                self.received_snapshot_guard.trigger()
            except Exception:
                if not self.shutdown_requested and self.context.ok():
                    raise

        # Receipts and the live clock share the existing light group. Complete
        # objects are applied only by the guard or an entry in the serial group.
        # QoS, subscriptions, source stamps and the two ROS workers are unchanged.
        return self.create_subscription(msg_type, topic, received, qos_profile,
                                        callback_group=self.clock_callback_group)

    def drain_received_snapshots(self):
        lock = getattr(self, 'received_snapshot_lock', None)
        if lock is None:
            return
        with lock:
            pending, self.received_snapshot_callbacks = self.received_snapshot_callbacks, {}
        if self.shutdown_requested:
            return
        for callback, message in pending.values():
            callback(message)

    def destroy_node(self):
        worker = getattr(self, "planning_worker", None)
        if worker is not None:
            worker.close()
        return super().destroy_node()

    def assign_idle_robots(self):
        if not getattr(self, "global_enabled", False):
            return super().assign_idle_robots()
        # The single mission timer owns all admissions; this inherited timer
        # cannot independently start exploration while another role is pending.

    def cancel_stalled_goals(self):
        if not getattr(self, "global_enabled", False):
            return super().cancel_stalled_goals()
        self.drain_received_snapshots()
        now = self.now()
        for robot, task in tuple(self.navigation_tasks.items()):
            timeout = (self.rally_goal_timeout_sec if task.proposal.kind in ("rally", "rally_yield")
                       else self.goal_timeout_sec)
            if now - task.started_at >= timeout:
                self.cancel_navigation(robot, "timeout")
            elif now - task.last_progress_at >= geometry.NO_PROGRESS_SEC:
                self.cancel_navigation(robot, "no_progress")

    def cancel_navigation(self, robot, reason):
        task = self.navigation_tasks.get(robot)
        if task is None or task.cancel_reason is not None:
            return
        task.cancel_reason = reason
        if task.handle is not None:
            task.handle.cancel_goal_async()
        self.get_logger().info(f"Canceling {robot} {task.proposal.kind}: {reason}")

    def robot_odom_callback(self, message, robot_name):
        super().robot_odom_callback(message, robot_name)
        if not getattr(self, 'global_enabled', False):
            return
        task = self.navigation_tasks.get(robot_name)
        if task is None:
            return
        source = message.header.stamp.sec + message.header.stamp.nanosec / 1e9
        position = (message.pose.pose.position.x, message.pose.pose.position.y)
        yaw = geometry.quaternion_yaw(message.pose.pose.orientation)
        if (not all(math.isfinite(value) for value in (*position, yaw, source))
                or source <= task.progress_source
                or not 0 <= self.now() - source <= geometry.STATE_TTL_SEC['pose_state']):
            return
        # Odom-frame displacement is physical progress. A map-to-odom
        # correction alone, or replaying the same odometry, cannot renew it.
        task.progress_source = source
        if task.progress_position is None:
            task.progress_position, task.progress_yaw = position, yaw
        elif (math.dist(position, task.progress_position) >= .1
                or abs(math.atan2(math.sin(yaw-task.progress_yaw),
                                 math.cos(yaw-task.progress_yaw))) >= .1):
            task.progress_position, task.progress_yaw = position, yaw
            task.last_progress_at = self.now()

    def battery_state_callback(self, message, robot_name):
        if not getattr(self, "global_enabled", False):
            return super().battery_state_callback(message, robot_name)
        try:
            event = json.loads(message.data)
            mode = str(event["mode"])
            source = float(event["stamp_sec"])
            if (mode not in ("ACTIVE", "RETURNING", "CHARGING", "FAILED")
                    or not math.isfinite(source)
                    or not 0 <= self.now() - source <= geometry.STATE_TTL_SEC["battery_state"]
                    or self.battery_state_received_at[robot_name] is not None
                    and source <= self.battery_state_received_at[robot_name]):
                return
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            self.get_logger().error(f"Invalid delivered battery state for {robot_name}")
            return
        previous = self.battery_modes[robot_name]
        self.battery_states[robot_name] = event
        self.battery_state_received_at[robot_name] = source
        self.battery_modes[robot_name] = mode
        if mode == "FAILED":
            # mark_robot_failed owns the explicit isolation event.
            self.battery_modes[robot_name] = previous
            self.mark_robot_failed(robot_name, event.get("failure_reason", "battery_failure"))
            self.cancel_navigation(robot_name, "local_failure")
        elif mode != "ACTIVE":
            self.cancel_navigation(robot_name, "local_return")
        intent = getattr(self, "global_charge_intent", None)
        if intent is not None and intent.robot == robot_name:
            if mode in ("RETURNING", "CHARGING"):
                self.global_charge_started = True
            elif (mode == "ACTIVE" and self.global_charge_started) or mode == "FAILED":
                self.global_charge_intent = self.deferred_charge_intent
                self.deferred_charge_intent = None
                self.global_charge_requested_at = None
                self.global_charge_started = False
                self.rally_charge_requested.pop(robot_name, None)
                self.get_logger().info(f"Charge dependency closed for {robot_name}")
            elif (mode == "ACTIVE" and self.global_charge_requested_at is not None
                  and source >= self.global_charge_requested_at + geometry.CHARGE_REQUEST_TTL_SEC):
                self.global_charge_intent = None
                self.global_charge_requested_at = None
                self.rally_charge_requested.pop(robot_name, None)

    def target_detection_callback(self, message):
        if getattr(self, "global_enabled", False):
            try:
                event=json.loads(message.data)
                robot=str(event['robot'])
                target=float(event['target_x']),float(event['target_y'])
                source=float(event['_gateway']['source_time'])
                distance=float(event.get('max_distance_m',3.))
                fov=math.radians(float(event.get('field_of_view_deg',90.)))
                if (robot not in self.robot_positions or not all(math.isfinite(v) for v in (*target,source,distance,fov))
                        or distance<=0 or not 0<fov<=2*math.pi or not 0<=self.now()-source<=geometry.TARGET_DETECTION_TTL_SEC
                        or self.target is not None and target!=self.target):
                    return
            except (KeyError, TypeError, ValueError, json.JSONDecodeError):
                return
        previous_observer = getattr(self, "target_observing_robot", None)
        super().target_detection_callback(message)
        if not getattr(self, "global_enabled", False) or self.target!=target:
            return
        # The target lease is globally monotone, but observation producers
        # have independent leases. A delivered older/equal peer confirmation
        # can be fresh without rewinding the accepted target source.
        if source<=self.global_confirmations.get(robot,-math.inf):
            return
        self.global_confirmations[robot] = source
        self._emit('coordinator_global_confirmation',robot=robot,source_time=source,
                   message_id=event['_gateway'].get('message_id'))
        if (previous_observer in self.global_confirmations
                and self.battery_modes[previous_observer] == "ACTIVE"
                and 0 <= self.now() - self.global_confirmations[previous_observer]
                <= geometry.TARGET_OBSERVER_FRESHNESS_SEC):
            self.target_observing_robot = previous_observer

    def _sources_current(self, sources, include_target=True):
        now = self.now()
        if getattr(self, "shutdown_requested", False):
            return False
        return all(math.isfinite(stamp) and 0 <= now - stamp <= (
            geometry.TARGET_DETECTION_TTL_SEC if key.endswith("target_detection")
            else min(self.message_freshness_timeout_sec,
                     geometry.STATE_TTL_SEC[key.rsplit("/", 1)[1]]))
            for key, stamp in sources.items()
            if include_target or not key.endswith("target_detection"))

    def _snapshot(self):
        self.drain_received_snapshots()
        if not self.fresh_robot_inputs():
            return None
        now = self.now()
        required = tuple(self.participating_robots())
        if any(position is None for position in self.robot_positions.values()):
            return None
        # Moving local returns are also physical traffic. Their current body
        # must come from delivered pose/TF, never a native observer or home pose.
        for robot in required:
            if any(stamp is None or not 0 <= now - stamp <= geometry.STATE_TTL_SEC["pose_state"]
                   for stamp in (self.robot_odom_received_at[robot], self.robot_tf_received_at[robot])):
                return None
        sources = {key: row["source_time"] for key, row in self.input_freshness_details().items()
                   if row["source_time"] is not None}
        for robot in required:
            sources[robot + "/pose_state"] = self.robot_odom_received_at[robot]
            sources[robot + "/frame_state"] = self.robot_tf_received_at[robot]
        maps = {}
        for robot, local in geometry.HeadquartersControl.delivered_return_maps(self, now).items():
            maps[robot] = dict(local)
            sources[robot + "/map_snapshot"] = self.robot_map_received_at[robot]
        fresh_target = self.task_state in ("FOUND", "RALLY") and self.fresh_target()
        if not fresh_target:
            sources.pop("headquarters/target_detection", None)
        if not self._sources_current(sources):
            return None
        positions = {robot: tuple(position) for robot, position in self.robot_positions.items()
                     if position is not None}
        live = {robot: geometry.remaining_rally_route(task.proposal.route, positions[robot])
                for robot, task in self.navigation_tasks.items() if robot in positions}
        available = tuple(robot for robot in required if self.battery_modes[robot] == "ACTIVE"
                          and robot not in self.navigation_tasks
                          and (self.deferred_charge_intent is None or robot != self.deferred_charge_intent.robot))
        pending = tuple(self.rally_charge_requested)
        if self.global_charge_intent is not None:
            pending = tuple(set(pending) | {self.global_charge_intent.robot})
        history = tuple((x, y) for x, y, expiry in (*self.target_history, *self.bad_targets)
                        if expiry > now)
        return FleetSnapshot(
            self.task_state, now, self.map_data, self.resolution, tuple(self.origin),
            positions, {robot: dict(state) for robot, state in self.battery_states.items()
                        if state and state.get('mode') != 'FAILED'} if self.enable_battery else {},
            maps, sources, available, live, dict(self.successful_exploration_legs),
            history, tuple({**view, "position": tuple(view["position"])}
                           for view in getattr(self, "initial_search_views", {}).values()),
            self.target if fresh_target else None,
            self.target_observing_robot if fresh_target else None,
            dict(self.rally_final_targets) if fresh_target else {}, pending,
            self.rally_max_concurrent if fresh_target else geometry.EXPLORATION_MAX_CONCURRENT,
            self.rally_hold_sec, self.target_view_distance, self.rally_position_tolerance,
            dict(self.global_nav_failures), required,
            tuple(robot for robot, final in self.rally_final_targets.items()
                  if self.rally_arrived.get(robot, False) and robot in positions
                  and math.dist(positions[robot], (final.x, final.y)) <= self.rally_position_tolerance),
            dict(self.global_scan_steps), self.global_survey_attempts,
            self.num_robots * (1 + self.rally_max_retries),
            self.source_map_data, dict(self.map_self_return_cells))

    def _encoded_map(self, data, resolution, origin, source, stamp):
        key = (data.shape, resolution, tuple(origin),
               hashlib.blake2b(data.tobytes(), digest_size=16).digest())
        if key not in self.global_map_encodings:
            if len(self.global_map_encodings) >= 16:
                self.global_map_encodings.clear()
            self.global_map_encodings[key] = geometry.grid_audit_evidence(
                data, resolution, origin, source, stamp, stamp)
        return {**self.global_map_encodings[key], "source": source,
                "source_time": stamp, "version": stamp}

    def _world_evidence(self, snapshot):
        return {
            "source_map": self._encoded_map(snapshot.source_grid if snapshot.source_grid is not None
                else snapshot.grid, snapshot.resolution, snapshot.origin, "ap_delivered_fused_map",
                snapshot.sources["headquarters/fused_map_snapshot"]),
            "self_return_cells": snapshot.self_return_cells,
            "planning_map": self._encoded_map(snapshot.grid, snapshot.resolution,
                snapshot.origin, "ap_delivered_planning_map",
                snapshot.sources["headquarters/fused_map_snapshot"]),
            "return_maps": {robot: self._encoded_map(local["data"], local["resolution"],
                local["origin"], "ap_delivered_robot_map", snapshot.sources[robot + "/map_snapshot"])
                for robot, local in snapshot.maps.items()},
            "positions": snapshot.positions, "battery_states": snapshot.batteries,
            "sources": snapshot.sources, "charge_pending": snapshot.charge_pending,
            "live_routes": snapshot.live_routes, "required": snapshot.required,
            "target": snapshot.target, "observer": snapshot.observer,
            "completed_legs": snapshot.completed_legs,
            "confirmations":dict(self.global_confirmations),
        }

    def _emit(self, event, **details):
        self.consumed_publisher.publish(String(data=json.dumps(
            {"event": event, "event_time": self.now(), "task_phase": self.task_state, **details},
            sort_keys=True)))

    def _active_observer(self, snapshot, robot):
        stamp = self.global_confirmations.get(robot)
        return (robot == self.target_observing_robot and stamp is not None
                and snapshot.batteries.get(robot, {}).get("mode", "ACTIVE") == "ACTIVE"
                and 0 <= snapshot.at_time - stamp <= geometry.TARGET_OBSERVER_FRESHNESS_SEC
                and not any(peer != robot and 0 <= snapshot.at_time - source
                            <= geometry.TARGET_OBSERVER_FRESHNESS_SEC
                            and snapshot.batteries.get(peer, {}).get("mode", "ACTIVE") == "ACTIVE"
                            for peer, source in self.global_confirmations.items()))

    def _admission_caches(self, snapshot, robot):
        local = snapshot.maps.get(robot)
        key = (snapshot.grid.shape, snapshot.resolution, snapshot.origin,
            hashlib.blake2b(snapshot.grid.tobytes(), digest_size=16).digest(),
            None if local is None else (local['data'].shape, local['resolution'], tuple(local['origin']),
                hashlib.blake2b(local['data'].tobytes(), digest_size=16).digest()),
            tuple(sorted(snapshot.positions.items())))
        caches = self.admission_geometry_caches.setdefault(robot, {})
        if caches.get('epoch') != key:
            caches.clear()
            caches['epoch'] = key
        # Reverse charger fields depend on map/contact geometry, not on peer
        # bodies or tiny pose changes. Their original content keys invalidate
        # changed maps; every query still rebuilds the actual start prefix and
        # prices the current sources and energy. Motion fields keep the full
        # body epoch above.
        caches['returns'] = self.return_geometry_caches.setdefault(robot, {})
        return caches

    def _protect_traffic(self, snapshot):
        protected = protected_returns(snapshot, {})
        for robot, task in tuple(self.navigation_tasks.items()):
            kind = task.proposal.kind
            if self.battery_modes[robot] != "ACTIVE":
                self.cancel_navigation(robot, "local_return")
            elif kind == "exploration" and snapshot.target is not None:
                self.cancel_navigation(robot, "target_found")
            elif kind in ("rally", "rally_yield", "target_information_survey") and snapshot.target is None:
                self.cancel_navigation(robot, "target_expired")
            elif protected is None:
                self.cancel_navigation(robot, "unknown_return_corridor")
            else:
                route = geometry.remaining_rally_route(task.proposal.route, snapshot.positions[robot])
                allowed = task.proposal.beneficiary if kind in ("local_return_yield", "charge_clearance") else None
                if any(geometry.routes_conflict(route, corridor) for peer, corridor in protected.items()
                       if peer not in (robot, allowed)):
                    self.cancel_navigation(robot, "return_corridor")

    def _nominal_caches(self, snapshot, robot):
        # Waiting prices use a static, complete approach without peer bodies.
        # Reuse its field only for identical maps and the same start cell;
        # prepend the actual live position again when calculating distance.
        admission=self._admission_caches(snapshot,robot)
        key=(admission['epoch'][:-1],geometry.world_to_grid(
            *snapshot.positions[robot],snapshot.resolution,*snapshot.origin))
        caches=self.nominal_rally_caches.setdefault(robot,{})
        if caches.get('epoch')!=key:
            caches.clear()
            caches['epoch']=key
        caches['returns']=self.return_geometry_caches.setdefault(robot,{})
        return caches

    def _validate_final_poses(self, snapshot, poses):
        if set(poses) != set(snapshot.required) or snapshot.target is None:
            return False
        safe = geometry.traversable_grid(snapshot.grid, snapshot.resolution, geometry.RALLY_CLEARANCE_M)
        for robot, pose in poses.items():
            cell = geometry.world_to_grid(pose.x, pose.y, snapshot.resolution, *snapshot.origin)
            if (not 0 <= cell[0] < safe.shape[0] or not 0 <= cell[1] < safe.shape[1] or not safe[cell]
                    or not geometry.rally_target_view(snapshot.grid, snapshot.resolution, snapshot.origin,
                        (pose.x, pose.y), snapshot.target, snapshot.target_range - snapshot.position_tolerance)
                    or abs(math.atan2(math.sin(pose.yaw - math.atan2(snapshot.target[1] - pose.y,
                        snapshot.target[0] - pose.x)), math.cos(pose.yaw - math.atan2(
                        snapshot.target[1] - pose.y, snapshot.target[0] - pose.x)))) > 1e-6):
                return False
            if any(peer != robot and math.dist((pose.x, pose.y), (other.x, other.y))
                   < geometry.RALLY_MIN_SEPARATION_M for peer, other in poses.items()):
                return False
        return True

    def _current_motion(self, snapshot, proposal, waits, owned_task=None):
        robot, kind = proposal.robot, proposal.kind
        if owned_task is None and (robot not in snapshot.available or robot in self.navigation_tasks):
            return None
        if owned_task is not None and (self.navigation_tasks.get(robot) is not owned_task
                or self.battery_modes[robot] != 'ACTIVE'):
            return None
        if kind in ("rally", "rally_yield", "target_information_survey") and snapshot.target is None:
            return None
        if kind == "exploration" and snapshot.target is not None:
            return None
        caches = self._admission_caches(snapshot, robot)
        grid = robot_grid(snapshot, robot, caches)
        bodies = [position for peer, position in snapshot.positions.items() if peer != robot]
        if kind == "target_reacquisition_scan":
            cell = geometry.world_to_grid(*snapshot.positions[robot], snapshot.resolution, *snapshot.origin)
            safe = geometry.traversable_grid(grid, snapshot.resolution, geometry.PATH_CLEARANCE_M)
            if (not 0 <= cell[0] < safe.shape[0] or not 0 <= cell[1] < safe.shape[1] or not safe[cell]
                    or any(math.dist(snapshot.positions[robot], position) < geometry.RALLY_DYNAMIC_CLEARANCE_M
                           for position in bodies)):
                return None
            actual = geometry.RallyPose(*snapshot.positions[robot], proposal.pose.yaw)
            route = (snapshot.positions[robot],)
        else:
            actual, route = geometry.plan_rally_leg(
                proposal.pose, grid, snapshot.resolution, snapshot.origin, snapshot.positions[robot],
                geometry.MAX_NAVIGATION_LEG_M, bodies,
                visible_only=kind in ("local_return_yield", "charge_clearance", "rally_yield"),
                route_cache=caches.setdefault("motion_routes", {}))
        if actual is None:
            return None
        if owned_task is not None:
            # Revalidate the exact issued metric goal, never a new rounded
            # waypoint or heading. A newly required longer leg is canceled.
            if (geometry.world_to_grid(actual.x, actual.y, snapshot.resolution, *snapshot.origin)
                    != geometry.world_to_grid(proposal.pose.x, proposal.pose.y,
                                              snapshot.resolution, *snapshot.origin)
                    or any(math.dist((proposal.pose.x, proposal.pose.y), position)
                           < geometry.RALLY_DYNAMIC_CLEARANCE_M for position in bodies)):
                return None
            actual = proposal.pose
            route = (*route, (actual.x, actual.y))
            if not geometry.route_respects_known_obstacles(grid, snapshot.resolution,
                    snapshot.origin, (snapshot.positions[robot], *route)):
                return None
        if kind not in ("rally", "target_reacquisition_scan"):
            cell = geometry.world_to_grid(actual.x, actual.y, snapshot.resolution, *snapshot.origin)
            endpoint_mask = geometry.traversable_grid(grid, snapshot.resolution, geometry.ROBOT_CLEARANCE_M)
            if (not 0 <= cell[0] < endpoint_mask.shape[0] or not 0 <= cell[1] < endpoint_mask.shape[1]
                    or not endpoint_mask[cell]):
                return None
        actual = geometry.RallyPose(actual.x, actual.y, proposal.pose.yaw)
        full = qualified_motion_route(snapshot, robot, route, caches)
        if full is None:
            return None
        protected = protected_returns(snapshot, {})
        if protected is None:
            return None
        for peer, corridor in protected.items():
            if peer == robot:
                continue
            if kind in ("local_return_yield", "charge_clearance") and peer == proposal.beneficiary:
                distances = [min(math.dist(point, other) for other in corridor) for point in full]
                if (distances[-1] < geometry.RALLY_ROUTE_SEPARATION_M
                        or any(after + snapshot.resolution < min(before, geometry.RALLY_ROUTE_SEPARATION_M)
                               for before, after in zip(distances, distances[1:]))):
                    return None
            elif geometry.routes_conflict(full, corridor):
                return None
        if any(geometry.routes_conflict(full, live) for peer, live in snapshot.live_routes.items()
               if peer != robot):
            return None
        destination = (actual.x, actual.y)
        budget_time = self.now()
        pricing = replace(snapshot, at_time=budget_time)
        wait = geometry.RALLY_GOAL_TIMEOUT_SEC if kind == "target_reacquisition_scan" else 0.
        complete = full
        if kind == "rally":
            final = self.rally_final_targets[robot]
            _, remaining = geometry.plan_rally_leg(final, grid, snapshot.resolution,
                snapshot.origin, destination, blocked_positions=bodies)
            if not remaining:
                return None
            # Cell-centre geometry and the permanent metric target can differ
            # when a delivered map origin changes. Fund the exact nominal
            # connector too; the actual shorter stop receives its own return
            # price below.
            complete = (*full, *remaining, (final.x,final.y))
            destination = final.x, final.y
            # A complete all-peer wait is repriced at the current epoch. The
            # proposed wait is a lower bound on this admission's wait reserve.
            wait = max(waits.get(robot, 0.), self._current_wait(pricing, robot)) + self.rally_hold_sec
            if owned_task is not None:
                actual = proposal.pose
            elif math.dist((actual.x, actual.y), destination) > self.rally_position_tolerance:
                actual = geometry.RallyPose(actual.x, actual.y,
                    geometry.route_arrival_yaw(route, final.yaw))
            else:
                actual = geometry.RallyPose(actual.x, actual.y, final.yaw)
        information = proposal.information_cells
        if kind == "exploration" and owned_task is None:
            cell = geometry.world_to_grid(actual.x, actual.y, snapshot.resolution, *snapshot.origin)
            interest = geometry.camera_search_interest(snapshot.grid, snapshot.resolution,
                                                       snapshot.origin, snapshot.views)
            visual, yaw = camera_cells(snapshot.grid, cell,
                                       geometry.INFORMATION_RADIUS_M / snapshot.resolution, interest)
            mapping = frozenset(map(int, geometry.visible_unknown_gain(snapshot.grid, cell,
                geometry.INFORMATION_RADIUS_M / snapshot.resolution, return_cells=True)))
            information = visual | mapping
            if not information or route_length(full) < geometry.USEFUL_TRAVEL_M:
                return None
            if visual:
                actual = geometry.RallyPose(actual.x, actual.y, yaw)
        complete = qualified_motion_route(snapshot, robot, complete[1:], caches)
        if complete is None:
            return None
        required = complete_budget(pricing, robot,
                                   complete, destination, caches, wait)
        if required is not None and kind=='rally':
            stopped=complete_budget(pricing,robot,
                full,(actual.x,actual.y),caches,wait)
            if stopped is None:
                return None
            required=max(required,stopped)
        if required is None or snapshot.batteries and snapshot.batteries[robot]["energy"] <= required:
            return None
        return replace(proposal, pose=actual, route=full, required_energy=required,
                       information_cells=information, complete_route=complete,
                       budget_time=budget_time, wait_sec=wait)

    def _current_wait(self, snapshot, waiting_robot):
        # Bound nominal outstanding peer travel and serialized charge time.
        # No Euclidean fallback can supply a feasible path or a return price.
        bases, travel, charge_times = {}, {}, {}
        for robot, final in self.rally_final_targets.items():
            caches = self._nominal_caches(snapshot, robot)
            grid = robot_grid(snapshot, robot, caches)
            _, route = geometry.plan_rally_leg(final, grid, snapshot.resolution,
                snapshot.origin, snapshot.positions[robot],
                route_cache=caches.setdefault("nominal_rally_routes", {}))
            if not route:
                return math.inf
            state = snapshot.batteries.get(robot, {})
            speed = float(state.get("nominal_speed_mps", .18))
            full = (snapshot.positions[robot], *route)
            travel[robot] = route_length(full) / speed
            base = complete_budget(snapshot, robot, full, (final.x, final.y), caches, self.rally_hold_sec)
            if base is None:
                return math.inf
            bases[robot] = base
            if snapshot.batteries:
                contact = contact_route(snapshot, robot, snapshot.positions[robot], caches)
                if contact is None:
                    return math.inf
                charge_times[robot] = (contact["path_distance_m"] * float(state.get("return_path_factor", 2.)) / speed
                    + float(state.get("charge_duration_sec", 6.))
                    + float(state.get("return_recovery_wait_sec", geometry.RETURN_RECOVERY_WAIT_SEC)))
        if not snapshot.batteries:
            return max((duration for robot, duration in travel.items() if robot != waiting_robot), default=0.)
        _, waits = geometry.rally_wait_requirements(bases, snapshot.batteries,
            {robot: state["mode"] for robot, state in snapshot.batteries.items()}, travel, charge_times)
        return waits.get(waiting_robot, math.inf)

    def _send_motion(self, snapshot, proposal):
        robot = proposal.robot
        if robot in self.navigation_tasks or not self.robot_nav_clients[robot].server_is_ready():
            return False
        self.navigation_generation += 1
        task = NavigationTask(self.navigation_generation, proposal, self.task_state,
                              self.now(), last_progress_at=self.now(), sources=dict(snapshot.sources))
        odom = self.robot_last_odom.get(robot)
        if odom is not None:
            task.progress_position = (odom.pose.pose.position.x, odom.pose.pose.position.y)
            task.progress_yaw = geometry.quaternion_yaw(odom.pose.pose.orientation)
            task.progress_source = odom.header.stamp.sec + odom.header.stamp.nanosec / 1e9
        self.navigation_tasks[robot] = task
        goal = NavigateToPose.Goal()
        goal.pose = PoseStamped()
        goal.pose.header.frame_id = "map"
        goal.pose.pose.position.x, goal.pose.pose.position.y = proposal.pose.x, proposal.pose.y
        goal.pose.pose.orientation.z = math.sin(proposal.pose.yaw / 2.)
        goal.pose.pose.orientation.w = math.cos(proposal.pose.yaw / 2.)
        proof = self._motion_proof(snapshot, task, proposal)
        self._emit("coordinator_global_motion_admission", **proof)
        if not self._sources_current(snapshot.sources, include_target=proposal.kind not in (
                "local_return_yield", "exploration", "target_reacquisition_scan")):
            self.navigation_tasks.pop(robot)
            self._emit("coordinator_global_motion_revoked", robot=robot, generation=task.generation,
                       reason="source_expired_during_proof_encoding")
            return False
        self.goal_routes[robot] = proposal.route
        recorded = self.record_navigation_decision(robot,
            "target_reacquisition_exploration" if proposal.kind == "exploration"
            and self.task_state in ("FOUND", "RALLY") else
            "target_survey" if proposal.kind == "target_information_survey" else proposal.kind, goal.pose)
        if recorded is False or not self._sources_current(snapshot.sources, include_target=proposal.kind not in (
                "local_return_yield", "exploration", "target_reacquisition_scan")):
            self.navigation_tasks.pop(robot)
            self.goal_routes[robot] = ()
            self._emit("coordinator_global_motion_revoked", robot=robot, generation=task.generation,
                       reason="source_expired_before_send")
            return False
        goal.pose.header.stamp = self.get_clock().now().to_msg()
        try:
            future = self.robot_nav_clients[robot].send_goal_async(
                goal, feedback_callback=lambda feedback, token=task: self._feedback(token, feedback))
            geometry.defer_action_done_callback(self, future,
                lambda completed, token=task: self._goal_response(token, completed))
        except Exception as error:
            self._finish_navigation(task, None, "send_exception:" + str(error))
            return False
        self.robot_states[robot] = "active"
        self.goal_routes[robot] = proposal.route
        self._emit("coordinator_global_motion_sent", robot=robot, generation=task.generation,
                   stamp_sec=goal.pose.header.stamp.sec + goal.pose.header.stamp.nanosec / 1e9)
        if proposal.kind == "target_information_survey":
            self.global_survey_attempts += 1
        self.get_logger().info(f"Global {proposal.kind}: {robot} -> "
                               f"({proposal.pose.x:.2f}, {proposal.pose.y:.2f}), "
                               f"budget={proposal.required_energy:.2f}")
        return True

    def _motion_proof(self, snapshot, task, proposal):
        return {
            "robot": proposal.robot, "generation": task.generation, "kind": proposal.kind,
            "beneficiary": proposal.beneficiary, "route": proposal.route,
            "complete_task_route": proposal.complete_route or proposal.route,
            "requested_position": [proposal.pose.x, proposal.pose.y],
            "requested_yaw": proposal.pose.yaw, "required_energy": proposal.required_energy,
            "budget_evaluated_at_sec": proposal.budget_time, "waiting_time_budget_sec": proposal.wait_sec,
            "final_poses": {peer: [pose.x, pose.y, pose.yaw] for peer, pose in self.rally_final_targets.items()},
            "world": self._world_evidence(snapshot),
        }

    def _revalidate_pending_motion(self, task):
        snapshot = self._snapshot()
        if snapshot is None:
            return False
        robot = task.proposal.robot
        snapshot = replace(snapshot, live_routes={peer: route for peer, route
            in snapshot.live_routes.items() if peer != robot})
        actual = self._current_motion(snapshot, task.proposal, {}, owned_task=task)
        if actual is None:
            return False
        self._emit('coordinator_global_motion_revalidation',
                   **self._motion_proof(snapshot, task, actual))
        if not self._sources_current(snapshot.sources, include_target=actual.kind not in (
                'local_return_yield', 'exploration', 'target_reacquisition_scan')):
            return False
        task.proposal, task.sources = actual, dict(snapshot.sources)
        self.goal_routes[robot] = actual.route
        self._emit('coordinator_global_motion_revalidated', robot=robot,
                   generation=task.generation, validated_at_sec=self.now())
        return True

    def _goal_response(self, task, future):
        self.drain_received_snapshots()
        robot = task.proposal.robot
        try:
            handle = future.result()
        except Exception as error:
            self._finish_navigation(task, None, "request_exception:" + str(error))
            return
        if handle is None or not handle.accepted:
            self._finish_navigation(task, None, "rejected")
            return
        if self.navigation_tasks.get(robot) is not task:
            handle.cancel_goal_async()
            return
        task.handle = handle
        compatible = (task.proposal.kind not in ("rally", "rally_yield", "target_information_survey")
                      or self.task_state == "RALLY" and self.fresh_target()
                      or task.proposal.kind == "target_information_survey" and self.task_state == "FOUND"
                      and self.fresh_target())
        if task.proposal.kind == "exploration" and self.task_state in ("FOUND", "RALLY") and self.fresh_target():
            compatible = False
        if not compatible:
            task.cancel_reason = task.cancel_reason or "phase_changed"
        elif not self._sources_current(task.sources, include_target=task.proposal.kind not in (
                "local_return_yield", "exploration", "target_reacquisition_scan")):
            if task.cancel_reason is None and not self._revalidate_pending_motion(task):
                task.cancel_reason = "source_expired_at_acceptance"
        if task.cancel_reason is not None or self.battery_modes[robot] != "ACTIVE" or self.shutdown_requested:
            handle.cancel_goal_async()
        geometry.defer_action_done_callback(self, handle.get_result_async(),
            lambda completed, token=task: self._goal_result(token, completed))

    def _goal_result(self, task, future):
        try:
            status, error = future.result().status, None
        except Exception as failure:
            status, error = None, str(failure)
        self._finish_navigation(task, status, error)

    def _feedback(self, task, feedback):
        # Feedback is an observation, not mission mutation. The action client
        # subscription runs in the same serialized callback group as the node.
        if self.navigation_tasks.get(task.proposal.robot) is not task:
            return
        distance = float(feedback.feedback.distance_remaining)
        if math.isfinite(distance) and distance < task.best_distance - .1:
            task.best_distance = distance
            task.last_progress_at = self.now()

    def _finish_navigation(self, task, status, error):
        robot = task.proposal.robot
        if self.navigation_tasks.get(robot) is not task:
            return
        self.navigation_tasks.pop(robot)
        self.robot_states[robot] = "failed" if self.battery_modes[robot] == "FAILED" else "idle"
        self.goal_routes[robot] = ()
        success = status == GoalStatus.STATUS_SUCCEEDED
        kind = task.proposal.kind
        if success:
            self.global_nav_failures[robot] = 0
            final = self.rally_final_targets.get(robot)
            if kind == "rally" and final is not None:
                self.rally_arrived[robot] = (
                    math.dist((task.proposal.pose.x, task.proposal.pose.y), (final.x, final.y))
                    <= self.rally_position_tolerance
                    and abs(math.atan2(math.sin(task.proposal.pose.yaw - final.yaw),
                                       math.cos(task.proposal.pose.yaw - final.yaw))) < 1e-6)
            if kind == "exploration" and self.task_state in ("EXPLORE", "FOUND_UNCONFIRMED"):
                self.successful_exploration_legs[robot] = self.successful_exploration_legs.get(robot, 0) + 1
            if kind == "target_reacquisition_scan":
                self.global_scan_steps[robot] = self.global_scan_steps.get(robot, 0) + 1
            if kind == "exploration":
                if self.task_state in ("FOUND", "RALLY"):
                    self.global_scan_steps[robot] = 0
                self.target_history.append((task.proposal.pose.x, task.proposal.pose.y,
                                            self.now() + geometry.TARGET_HISTORY_SEC))
        elif task.cancel_reason not in ("local_return", "local_failure", "target_found",
                                       "target_expired", "return_corridor", "unknown_return_corridor",
                                       "phase_changed", "source_expired_at_acceptance", "mission_terminal"):
            self.global_nav_failures[robot] = self.global_nav_failures.get(robot, 0) + 1
            if kind == "rally" and self.global_nav_failures[robot] > self.rally_max_retries:
                self.fail_task("rally_navigation_failed:" + robot)
            elif kind == "exploration":
                self.bad_targets.append((task.proposal.pose.x, task.proposal.pose.y,
                                         self.now() + geometry.BAD_TARGET_SEC))
        self._emit("coordinator_global_motion_closed", robot=robot, generation=task.generation,
                   kind=kind, status=status, error=error, cancel_reason=task.cancel_reason)

    def _prepare_charge(self, snapshot):
        intent = self.global_charge_intent
        if snapshot is None or intent is None or self.global_charge_requested_at is not None:
            return
        robot = intent.robot
        if robot in self.navigation_tasks or snapshot.batteries[robot]["mode"] != "ACTIVE":
            return
        caches = self._admission_caches(snapshot, robot)
        contact = contact_route(snapshot, robot, snapshot.positions[robot], caches)
        return_budget_time = self.now()
        reserve = complete_budget(replace(snapshot, at_time=return_budget_time), robot,
                                  (snapshot.positions[robot],), snapshot.positions[robot], caches)
        if contact is None or reserve is None or snapshot.batteries[robot]["energy"] <= reserve:
            self.global_charge_intent = self.deferred_charge_intent
            self.deferred_charge_intent = None
            return
        state = snapshot.batteries[robot]
        target = float(state["capacity"]) * float(state["charge_target_fraction"])
        required = intent.required_energy
        desired_route, desired_wait, desired_time = (), 0., None
        if intent.destination is not None:
            grid = robot_grid(snapshot, robot, caches)
            _, route = geometry.plan_rally_leg(geometry.RallyPose(*intent.destination, 0.), grid,
                snapshot.resolution, snapshot.origin, snapshot.positions[robot],
                blocked_positions=[position for peer, position in snapshot.positions.items() if peer != robot])
            if not route:
                return
            desired_route = (snapshot.positions[robot], *route)
            desired_time = self.now()
            pricing = replace(snapshot, at_time=desired_time)
            desired_wait = self.rally_hold_sec + self._current_wait(pricing, robot) if intent.reason == "whole_rally_and_wait" else 0.
            required = complete_budget(pricing, robot, desired_route,
                                      intent.destination, caches, desired_wait)
            if required is None:
                return
        if intent.reason == "low_energy_after_actual_work":
            if not self.successful_exploration_legs.get(robot, 0):
                self.global_charge_intent = None
                return
            required = max(required, .25 * target)
        if not math.isfinite(required) or not state["energy"] <= required <= target:
            self.global_charge_intent = self.deferred_charge_intent
            self.deferred_charge_intent = None
            self._emit('coordinator_global_charge_intent_closed',robot=robot,
                       reason='current_task_funded_or_unavailable',required_energy=required)
            return
        # Protection blocks execution, not invalidation of an obsolete demand.
        if (any(other['mode'] in ('RETURNING','CHARGING') for other in snapshot.batteries.values())
                or self._active_observer(snapshot,robot)):
            return
        for peer, route in snapshot.live_routes.items():
            if peer != robot and geometry.routes_conflict(contact["route"], route):
                helper = self.navigation_tasks.get(peer)
                if (helper is not None and helper.proposal.kind in ('charge_clearance', 'local_return_yield')
                        and helper.proposal.beneficiary == robot):
                    # This funded, monotone escape is our own dependency.
                    # Charge waits for its real closure and final body check.
                    return
                self.cancel_navigation(peer, "return_corridor")
                return
        # A stationary contact does not reserve a fictitious moving segment;
        # every actual navigation continues to use the original 1.8 m limit.
        if contact["path_distance_m"] > 0.:
            if any(peer != robot and geometry.routes_conflict((position,), contact["route"])
                   for peer, position in snapshot.positions.items()):
                return
        stamp = self.now()
        message = String(data=json.dumps({"robot": robot, "stamp_sec": stamp,
            "task_phase": self.task_state, "reason": intent.reason,
            "required_energy": required, "available_energy": state["energy"]}, sort_keys=True))
        self._emit("coordinator_global_charge_admission", robot=robot, required_energy=required,
                   current_return_required=reserve, return_route=contact["route"],
                   budget_evaluated_at_sec=return_budget_time, destination=intent.destination,
                   desired_task_route=desired_route, desired_task_wait_sec=desired_wait,
                   desired_task_budget_at_sec=desired_time,
                   reason=intent.reason, world=self._world_evidence(snapshot))
        if not self._sources_current(snapshot.sources, include_target=intent.reason == "whole_rally_and_wait"):
            return
        self.charge_request_publishers[robot].publish(message)
        self.global_charge_requested_at = stamp
        self.rally_charge_requested[robot] = stamp
        self._emit("coordinator_global_charge_sent", robot=robot, stamp_sec=stamp)

    def _hold(self, snapshot):
        started = time.monotonic()
        try:
            return self._check_hold(snapshot)
        finally:
            self.last_hold_work_sec = time.monotonic() - started

    def _check_hold(self, snapshot):
        if self.task_state != "RALLY" or not self.rally_final_targets or snapshot.target is None:
            self.rally_hold_started_at = None
            self.last_hold_block_reason = 'phase_or_target'
            return
        stable = (not self.navigation_tasks and self.global_charge_intent is None
                  and all(self.rally_arrived.get(robot, False) for robot in snapshot.required)
                  and all(self.battery_modes[robot] == "ACTIVE" for robot in snapshot.required)
                  and geometry.robots_stable(self.robot_positions, self.robot_velocities,
                      self.rally_final_targets, self.rally_position_tolerance,
                      self.rally_linear_tolerance, self.rally_angular_tolerance))
        if not stable:
            self.rally_hold_started_at = None
            self.last_hold_block_reason = 'ownership_charge_or_arrival'
            return
        for robot, final in self.rally_final_targets.items():
            # Recheck full hold and return reserves; stopping at a temporary
            # yield does not modify final poses or begin completion timing.
            required = complete_budget(replace(snapshot,at_time=self.now()), robot,
                (snapshot.positions[robot],), (final.x, final.y),
                {'returns':self.return_geometry_caches.setdefault(robot,{})}, self.rally_hold_sec)
            if required is None or snapshot.batteries and snapshot.batteries[robot]["energy"] <= required:
                self.rally_hold_started_at = None
                self.last_hold_block_reason = 'unfunded_complete_hold_return:' + robot
                return
        if not self._sources_current(snapshot.sources):
            self.rally_hold_started_at = None
            self.last_hold_block_reason = 'source_expired_during_hold_price'
            return
        self.last_hold_block_reason = None
        now = self.now()
        if self.rally_hold_started_at is None:
            self.rally_hold_started_at = now
        elif now - self.rally_hold_started_at >= self.rally_hold_sec:
            self.publish_task_state("PARTIAL_COMPLETE" if len(snapshot.required) != self.num_robots else "COMPLETE")

    def update_mission(self):
        if not getattr(self, "global_enabled", False):
            return super().update_mission()
        self.drain_received_snapshots()
        if self.return_probe_paused or self.shutdown_requested:
            return
        if self.task_state in ("COMPLETE", "PARTIAL_COMPLETE", "FAILED"):
            for robot in tuple(self.navigation_tasks):
                self.cancel_navigation(robot, "mission_terminal")
            return
        if not self.participating_robots():
            self.fail_task("all_robots_failed")
            return
        snapshot = self._snapshot()
        if snapshot is None:
            self.rally_hold_started_at = None
            self.last_hold_block_reason='input_unavailable'
            if self.now()-self.last_global_diagnostic_at>=5.:
                self.last_global_diagnostic_at=self.now()
                self._emit('coordinator_global_wait',inputs=self.input_freshness_details(),
                    owned=list(self.navigation_tasks),reason='input_unavailable')
            return
        if (self.global_charge_intent is not None and self.global_charge_requested_at is None
                and self.global_charge_context != snapshot.context):
            self.global_charge_intent = None
            self.deferred_charge_intent = None
            snapshot = self._snapshot()
            if snapshot is None:
                return
        self._protect_traffic(snapshot)
        self._hold(snapshot)
        if self.task_state in ("COMPLETE", "PARTIAL_COMPLETE", "FAILED"):
            return
        self._prepare_charge(snapshot)
        try:
            proposal = self.planning_worker.poll()
        except Exception as error:
            self._emit("coordinator_global_planner_error", error=repr(error))
            self.get_logger().error("Fleet planning failed: " + repr(error))
            proposal = None
        if proposal is not None and proposal.snapshot.context == snapshot.context:
            self.plan_generation += 1
            if self.now() - self.last_global_diagnostic_at >= 5.:
                self.last_global_diagnostic_at = self.now()
                self._emit("coordinator_global_proposal", generation=self.plan_generation,
                    computed_at=proposal.snapshot.at_time,
                    computation_wall_sec=proposal.computation_wall_sec, blocked=proposal.blocked,
                    motions=[{"robot": motion.robot, "kind": motion.kind,
                              "position": [motion.pose.x, motion.pose.y]} for motion in proposal.motions],
                    charges=[charge.robot for charge in proposal.charges],
                    arrived=dict(self.rally_arrived),owned=list(self.navigation_tasks),
                    charge_intent=None if self.global_charge_intent is None else {
                        'robot':self.global_charge_intent.robot,'reason':self.global_charge_intent.reason,
                        'requested_at':self.global_charge_requested_at,
                        'deferred':None if self.deferred_charge_intent is None else self.deferred_charge_intent.robot},
                    hold_started_at=self.rally_hold_started_at,hold_block_reason=self.last_hold_block_reason,
                    hold_work_sec=self.last_hold_work_sec,sources=snapshot.sources,
                    delivered_stable=geometry.robots_stable(self.robot_positions,self.robot_velocities,
                        self.rally_final_targets,self.rally_position_tolerance,
                        self.rally_linear_tolerance,self.rally_angular_tolerance))
            if (proposal.final_poses and proposal.final_poses != self.rally_final_targets
                    and not self.navigation_tasks and not snapshot.charge_pending
                    and self._validate_final_poses(snapshot, proposal.final_poses)
                    and self._sources_current(snapshot.sources)):
                self.rally_targets = dict(proposal.final_poses)
                self.rally_final_targets = dict(proposal.final_poses)
                self.rally_dispatch_order = sorted(proposal.final_poses)
                self.rally_arrived = dict.fromkeys(self.robot_positions, False)
                self.publish_rally_assignments()
                self.publish_task_state("RALLY")
                self.rally_hold_started_at = None
                snapshot = self._snapshot()
            if snapshot is None:
                return
            if self.global_charge_intent is None and proposal.charges and not snapshot.charge_pending:
                eligible = [charge for charge in proposal.charges if charge.robot not in self.navigation_tasks]
                if eligible:
                    self.global_charge_intent = min(eligible, key=lambda charge:
                        (self._active_observer(snapshot,charge.robot),route_length(charge.return_route), charge.robot))
                    self.global_charge_context = snapshot.context
                    self.global_charge_started = False
                    self._prepare_charge(snapshot)
            elif (self.global_charge_intent is not None and self.global_charge_requested_at is None
                    and self.deferred_charge_intent is None):
                eligible = [charge for charge in proposal.charges if charge.robot not in self.navigation_tasks
                            and not self._active_observer(snapshot,charge.robot)]
                dependency = min(eligible,key=lambda charge:(route_length(charge.return_route),charge.robot)) if (
                    self._active_observer(snapshot,self.global_charge_intent.robot) and eligible) else next((charge for charge in proposal.charges
                    if charge.reason == "unfunded_return_clearance"
                    and charge.robot != self.global_charge_intent.robot), None)
                if dependency is not None:
                    self.deferred_charge_intent = self.global_charge_intent
                    self.global_charge_intent = dependency
                    self.global_charge_context = snapshot.context
                    refreshed = self._snapshot()
                    if refreshed is not None:
                        self._prepare_charge(refreshed)
            for motion in proposal.motions:
                if self.global_charge_intent is not None and motion.robot == self.global_charge_intent.robot:
                    continue
                current = self._snapshot()
                if current is None:
                    break
                actual = self._current_motion(current, motion, proposal.wait_budgets)
                if actual is not None:
                    self._send_motion(current, actual)
        current = self._snapshot()
        if current is not None and current.available:
            self.planning_worker.submit(current)
