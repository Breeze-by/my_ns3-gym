"""
Full-body contact accounting and simulation-time monitoring for MR3.

This module has no ROS dependency. The caller supplies ContactsState messages
and the simulation time at receipt, and polls health throughout the task.
"""

from dataclasses import dataclass
import math


@dataclass(frozen=True)
class ContactComponent:
    link: str
    collision: str
    topic_suffix: str
    support_eligible: bool = False


CONTACT_COMPONENTS = {
    "base": ContactComponent("base_link", "base_collision", "collision"),
    "lidar": ContactComponent("base_scan", "lidar_sensor_collision", "collision/lidar"),
    "wheel_left": ContactComponent(
        "wheel_left_link", "wheel_left_collision", "collision/wheel_left", True,
    ),
    "wheel_right": ContactComponent(
        "wheel_right_link", "wheel_right_collision", "collision/wheel_right", True,
    ),
    "caster_back_left": ContactComponent(
        "caster_back_left_link", "collision", "collision/caster_back_left", True,
    ),
    "caster_back_right": ContactComponent(
        "caster_back_right_link", "collision", "collision/caster_back_right", True,
    ),
}


def contact_topics(robot, compact=False):
    if compact:
        return {name: f"/mr3_contacts/{robot}/{name}" for name in CONTACT_COMPONENTS}
    return {name: f"/{robot}/{component.topic_suffix}"
            for name, component in CONTACT_COMPONENTS.items()}


def filter_non_support_contacts(robot, component, states, support_collision_names):
    """
    Exclude only an exact own wheel/caster--declared support collision pair.

    A wrong component, unscoped/unknown collision, robot contact or base/lidar
    contact is retained. Counts are contact-state samples, not distinct events.
    """
    spec = CONTACT_COMPONENTS[component]
    own_collision = f"{robot}::{spec.link}::{spec.collision}"
    retained = []
    filtered = 0
    for state in states:
        first, second = state.collision1_name, state.collision2_name
        support = spec.support_eligible and (
            (first == own_collision and second in support_collision_names)
            or (second == own_collision and first in support_collision_names)
        )
        if support:
            filtered += 1
        else:
            retained.append(state)
    return tuple(retained), filtered


@dataclass
class _ComponentState:
    message_count: int = 0
    accepted_message_count: int = 0
    invalid_timestamp_count: int = 0
    duplicate_message_count: int = 0
    last_source: float = None
    last_receipt: float = None
    max_source_gap: float = 0.0
    max_receipt_gap: float = 0.0
    filtered_support_count: int = 0
    non_support_sample_count: int = 0
    active: bool = False


class ContactMonitor:
    """
    Require every component to remain fresh after start, with latched failure.

    Source time and receipt time use the same Gazebo simulation clock. Startup
    source=0 messages are counted but cannot establish readiness. Repeated source
    stamps never refresh either clock. start() preserves all startup contacts.
    Event/duration counts are each robot's union of active component contacts,
    so one contact seen by multiple body sensors is not counted twice per robot.
    """

    def __init__(self, robot_names, support_collision_names, max_age_sec=0.5, compact=False):
        if not math.isfinite(max_age_sec) or max_age_sec <= 0:
            raise ValueError("max_age_sec must be finite and positive")
        self.robot_names = tuple(robot_names)
        if not self.robot_names or len(set(self.robot_names)) != len(self.robot_names):
            raise ValueError("robot_names must be nonempty and unique")
        self.support_collision_names = frozenset(support_collision_names)
        if any(not isinstance(name, str) or len(name.split("::")) != 3
               or any(not part for part in name.split("::"))
               for name in self.support_collision_names):
            raise ValueError("support collisions require exact model::link::collision names")
        if any(name.split("::")[0] in self.robot_names
               for name in self.support_collision_names):
            raise ValueError("a robot collision cannot be declared as support ground")
        self.max_age_sec = max_age_sec
        self.compact = compact
        self.components = {(robot, name): _ComponentState()
                           for robot in self.robot_names for name in CONTACT_COMPONENTS}
        self.started = False
        self.latched_issues = {}
        self.robot_active = {robot: False for robot in self.robot_names}
        self.robot_event_count = {robot: 0 for robot in self.robot_names}
        self.robot_duration = {robot: 0.0 for robot in self.robot_names}
        self.robot_updated_at = {robot: None for robot in self.robot_names}

    def unhealthy_components(self, now):
        if not math.isfinite(now) or now < 0:
            raise ValueError("now must be a finite nonnegative simulation time")
        issues = {}
        for (robot, name), state in self.components.items():
            reason = ""
            if state.last_source is None or state.last_source <= 0:
                reason = "missing_source_time"
            elif state.last_receipt is None:
                reason = "missing_receipt_time"
            elif state.last_source > now or state.last_receipt > now:
                reason = "future_time"
            elif now - state.last_source > self.max_age_sec:
                reason = "source_stale"
            elif now - state.last_receipt > self.max_age_sec:
                reason = "receipt_stale"
            if reason:
                issues[f"{robot}/{name}"] = reason
        if self.started:
            self.latched_issues.update(issues)
        return issues

    def start(self, now):
        self.started = True
        return self.unhealthy_components(now)

    def _record_active(self, robot, component, active, now):
        previous = self.robot_updated_at[robot]
        if previous is not None and self.robot_active[robot]:
            self.robot_duration[robot] += max(0.0, now - previous)
        self.robot_updated_at[robot] = now
        self.components[(robot, component)].active = active
        union_active = any(self.components[(robot, name)].active
                           for name in CONTACT_COMPONENTS)
        if union_active and not self.robot_active[robot]:
            self.robot_event_count[robot] += 1
        self.robot_active[robot] = union_active

    def update(self, robot, component, message, receipt_sim_time):
        if not math.isfinite(receipt_sim_time) or receipt_sim_time < 0:
            raise ValueError("receipt_sim_time must be finite and nonnegative")
        state = self.components[(robot, component)]
        if self.started:
            self.unhealthy_components(receipt_sim_time)
        state.message_count += 1
        retained, filtered = filter_non_support_contacts(
            robot, component, message.states, self.support_collision_names,
        )
        state.filtered_support_count += filtered
        state.non_support_sample_count += len(retained)
        stamp = message.header.stamp
        source = stamp.sec + stamp.nanosec / 1e9
        reason = ""
        if not math.isfinite(source) or source < 0 or not 0 <= stamp.nanosec < 10**9:
            reason = "invalid_source_time"
        elif source > receipt_sim_time:
            reason = "future_source_time"
        elif state.last_receipt is not None and receipt_sim_time < state.last_receipt:
            reason = "receipt_time_regressed"
        elif state.last_source is not None and source < state.last_source:
            reason = "source_time_regressed"
        elif state.last_source is not None and source == state.last_source:
            state.duplicate_message_count += 1
            # Duplicate timing cannot establish new health, but contact
            # evidence must remain conservative even when its stamp repeats.
            # An empty duplicate must not clear an active contact either.
            if retained:
                self._record_active(robot, component, True, receipt_sim_time)
            return {"accepted": False, "active": state.active,
                    "filtered_support_count": filtered, "non_support_count": len(retained)}
        if reason:
            state.invalid_timestamp_count += 1
            if self.started:
                self.latched_issues[f"{robot}/{component}"] = reason
            # Preserve real contact evidence even if its timestamp is invalid;
            # an invalid empty message must not clear a known active contact.
            if retained:
                self._record_active(robot, component, True, receipt_sim_time)
            return {"accepted": False, "active": state.active,
                    "filtered_support_count": filtered, "non_support_count": len(retained)}
        if state.last_source is not None and state.last_source > 0:
            source_gap = source - state.last_source
            receipt_gap = receipt_sim_time - state.last_receipt
            state.max_source_gap = max(state.max_source_gap, source_gap)
            state.max_receipt_gap = max(state.max_receipt_gap, receipt_gap)
            if self.started and (source_gap > self.max_age_sec or receipt_gap > self.max_age_sec):
                self.latched_issues[f"{robot}/{component}"] = (
                    "source_gap" if source_gap > self.max_age_sec else "receipt_gap"
                )
        state.last_source = source
        state.last_receipt = receipt_sim_time
        state.accepted_message_count += 1
        self._record_active(robot, component, bool(retained), receipt_sim_time)
        if self.started:
            self.unhealthy_components(receipt_sim_time)
        return {"accepted": True, "active": state.active,
                "filtered_support_count": filtered, "non_support_count": len(retained)}

    def summary(self, now):
        issues = self.unhealthy_components(now)
        components = {}
        for (robot, name), state in self.components.items():
            components.setdefault(robot, {})[name] = {
                "topic": contact_topics(robot, self.compact)[name],
                "message_count": state.message_count,
                "accepted_message_count": state.accepted_message_count,
                "invalid_timestamp_count": state.invalid_timestamp_count,
                "duplicate_message_count": state.duplicate_message_count,
                "last_source_time_sec": state.last_source,
                "last_receipt_time_sec": state.last_receipt,
                "max_source_gap_sec": state.max_source_gap,
                "max_receipt_gap_sec": state.max_receipt_gap,
                "source_age_sec": None if state.last_source is None else now - state.last_source,
                "receipt_age_sec": (
                    None if state.last_receipt is None else now - state.last_receipt
                ),
                "filtered_support_count": state.filtered_support_count,
                "non_support_sample_count": state.non_support_sample_count,
                "active": state.active,
                "health_reason": issues.get(f"{robot}/{name}", ""),
            }
        robots = {}
        for robot in self.robot_names:
            duration = self.robot_duration[robot]
            if self.robot_active[robot] and self.robot_updated_at[robot] is not None:
                duration += max(0.0, now - self.robot_updated_at[robot])
            robots[robot] = {"event_count": self.robot_event_count[robot],
                             "duration_sec": duration, "active": self.robot_active[robot]}
        return {
            "fresh": not issues,
            "ever_unhealthy": bool(self.latched_issues),
            "latched_issues": dict(self.latched_issues),
            "max_age_sec": self.max_age_sec,
            "support_collision_names": sorted(self.support_collision_names),
            "contact_transport": "mr3_contact_reducer_v1" if self.compact else "raw",
            "sample_count_scope": (
                "one representative per pair per source message; raw counts in state.info"
                if self.compact else "raw ContactState samples"
            ),
            "components": components,
            "robots": robots,
            "filtered_support_count": sum(
                s.filtered_support_count for s in self.components.values()
            ),
            "event_count": sum(self.robot_event_count.values()),
            "duration_sec": sum(row["duration_sec"] for row in robots.values()),
        }
