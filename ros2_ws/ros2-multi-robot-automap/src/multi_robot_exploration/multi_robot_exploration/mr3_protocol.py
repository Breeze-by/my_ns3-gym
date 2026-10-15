"""Stable Nav2 goal ownership, independent of ROS and exploration decisions.

All time values are episode simulation seconds. Command freshness and the
renewable execution lease are bounded by two seconds; neither changes the
ten-second action RPC deadlines or the sixty-second execution deadline. A
transport must deliver explicit lease renewals, including while acceptance is
pending. No timeout is evidence that Nav2 has released a goal.
"""

from dataclasses import dataclass
import math


ROBOTS = ("tb1", "tb2", "tb3")
TERMINAL_STATUSES = {4: "SUCCEEDED", 5: "CANCELED", 6: "ABORTED"}


@dataclass
class _Robot:
    phase: str = "idle"
    goal_id: str = None
    goal: dict = None
    command: dict = None
    requested_at: float = None
    accepted_at: float = None
    commitment_until: float = 0.0
    lease_until: float = None
    cancel_started_at: float = None
    cancel_requested: bool = False
    cancel_accepted: bool = None
    accepted: bool = False
    pending: dict = None
    failure: str = None
    stop_reason: str = None
    last_terminal: str = None
    last_goal_id: str = None


class GoalDispatcher:
    """Own one action per robot without choosing or repairing exploration goals.

    ``emit`` receives dictionaries with ``type``, ``robot``, ``epoch``,
    ``goal_id`` and ``stamp``. ``send_goal`` also contains x/y, command metadata
    and lease expiry; ``cancel_goal`` is emitted once per owned goal. The ROS
    adapter queues these events and reports real action callbacks through
    on_accept/on_cancel_response/on_result.
    """

    def __init__(
        self, epoch, emit, robots=ROBOTS, commitment_sec=5.0,
        response_timeout_sec=10.0, cancel_timeout_sec=10.0,
        execution_timeout_sec=60.0, lease_sec=2.0,
    ):
        if not isinstance(epoch, str) or not epoch:
            raise ValueError("epoch must be a nonempty string")
        if tuple(robots) != ROBOTS:
            raise ValueError("MR3 requires exactly tb1/tb2/tb3")
        self.epoch = epoch
        self.emit = emit
        self.robots = tuple(robots)
        self.commitment_sec = self._positive(commitment_sec)
        self.response_timeout_sec = self._positive(response_timeout_sec)
        self.cancel_timeout_sec = self._positive(cancel_timeout_sec)
        self.execution_timeout_sec = self._positive(execution_timeout_sec)
        self.lease_sec = self._positive(lease_sec)
        self._epochs = {epoch}
        self._initialize()

    @staticmethod
    def _positive(value):
        value = float(value)
        if not math.isfinite(value) or value <= 0:
            raise ValueError("protocol durations must be finite and positive")
        return value

    def _initialize(self):
        self.states = {robot: _Robot() for robot in self.robots}
        self._commands = {robot: {} for robot in self.robots}
        self._last_command = {robot: -1 for robot in self.robots}
        self._now = None
        self.stopped = False

    @property
    def closed(self):
        """Return true only when real rejection/result closed every goal."""
        return all(state.goal_id is None for state in self.states.values())

    @property
    def failed(self):
        return any(state.failure is not None for state in self.states.values())

    def _time(self, now):
        now = float(now)
        if not math.isfinite(now) or now < 0:
            raise ValueError("simulation time must be finite and nonnegative")
        if self._now is not None and now < self._now:
            raise ValueError("simulation clock reversed; start a new episode epoch")
        self._now = now
        return now

    def _emit(self, event_type, robot, now, **fields):
        state = self.states[robot]
        self.emit(dict(type=event_type, robot=robot, epoch=self.epoch,
                       goal_id=state.goal_id, stamp=now, **fields))

    def _remember(self, robot, command_id, fingerprint, result):
        commands = self._commands[robot]
        commands[command_id] = (fingerprint, result)
        self._last_command[robot] = max(command_id, self._last_command[robot])
        # Older commands remain stale even after their duplicate entry expires.
        while len(commands) > 1024:
            del commands[next(iter(commands))]
        return result

    def submit(
        self, robot, choice, now, observation_version, command_id, expires_at,
        goal=None, command_epoch=None, created_at=None,
    ):
        """Apply a delivered GOAL/KEEP/WAIT command, returning an audit status.

        Command ids are monotonically increasing nonnegative integers per robot.
        A switch retains its original expiry while waiting for old-goal terminal
        confirmation. A delayed switch is discarded, never silently refreshed.
        """
        self.tick(now)
        now = self._now
        if robot not in self.states:
            return "unknown_robot"
        if command_epoch is not None and command_epoch != self.epoch:
            return "stale_epoch"
        if (not isinstance(command_id, int) or isinstance(command_id, bool)
                or command_id < 0):
            return "invalid_command_id"
        if (not isinstance(observation_version, int) or isinstance(observation_version, bool)
                or observation_version < 0):
            return "invalid_observation_version"
        if choice not in ("GOAL", "KEEP", "WAIT"):
            return "invalid_choice"
        try:
            expires_at = float(expires_at)
            generated_at = now if created_at is None else float(created_at)
            coordinates = None if goal is None else (float(goal["x"]), float(goal["y"]))
        except (TypeError, ValueError, KeyError, OverflowError):
            return "invalid_command"
        if choice == "GOAL" and (coordinates is None or not all(
                math.isfinite(value) for value in coordinates)):
            return "invalid_goal"
        if choice != "GOAL" and coordinates is not None:
            return "invalid_goal"
        fingerprint = (choice, observation_version, expires_at, coordinates, created_at)
        seen = self._commands[robot].get(command_id)
        if seen is not None:
            return "duplicate" if seen[0] == fingerprint else "command_id_conflict"
        if command_id <= self._last_command[robot]:
            return "stale_command"

        def finish(result):
            return self._remember(robot, command_id, fingerprint, result)

        if (not math.isfinite(expires_at) or not math.isfinite(generated_at)
                or generated_at > now or generated_at < 0
                or expires_at - generated_at > self.lease_sec + 1e-9):
            return finish("invalid_ttl")
        if expires_at <= now or expires_at <= generated_at:
            return finish("expired")
        if self.stopped:
            return finish("stopped")
        state = self.states[robot]
        if choice == "KEEP":
            return finish("kept")
        if (state.phase == "active" and now < state.commitment_until):
            return finish("commitment_locked")
        if choice == "WAIT":
            state.pending = None
            self._cancel(robot, now, "wait")
            return finish("waiting")
        if state.goal_id is not None and state.phase != "active":
            return finish("ownership_locked")
        command = dict(
            command_id=command_id, observation_version=observation_version,
            created_at=generated_at, expires_at=expires_at,
            goal=dict(x=coordinates[0], y=coordinates[1]),
        )
        if state.goal_id is None:
            self._start(robot, command, now)
            return finish("sent")
        state.pending = command
        self._cancel(robot, now, "switch")
        return finish("switch_pending")

    def _start(self, robot, command, now):
        state = self.states[robot]
        state.phase = "accepting"
        state.goal_id = f"{self.epoch}:{robot}:{command['command_id']}"
        state.goal = command["goal"].copy()
        state.command = command
        state.requested_at = now
        state.accepted_at = None
        state.commitment_until = 0.0
        state.lease_until = command["expires_at"]
        state.cancel_started_at = None
        state.cancel_requested = False
        state.cancel_accepted = None
        state.accepted = False
        state.pending = None
        state.stop_reason = None
        self._emit("send_goal", robot, now, **command, lease_until=state.lease_until,
                   x=state.goal["x"], y=state.goal["y"])

    def renew(self, robot, goal_id, epoch, now, expires_at):
        """Renew an existing goal lease using a delivered, bounded heartbeat."""
        self.tick(now)
        now = self._now
        if epoch != self.epoch:
            return "stale_epoch"
        if robot not in self.states or self.states[robot].goal_id != goal_id:
            return "stale_goal"
        try:
            expires_at = float(expires_at)
        except (TypeError, ValueError, OverflowError):
            return "invalid_ttl"
        if (not math.isfinite(expires_at) or expires_at <= now
                or expires_at - now > self.lease_sec + 1e-9):
            return "invalid_ttl"
        state = self.states[robot]
        if (self.stopped or state.cancel_requested
                or state.phase not in ("accepting", "active")):
            return "stopping"
        if expires_at <= state.lease_until:
            return "stale_renewal"
        state.lease_until = expires_at
        return "renewed"

    def _cancel(self, robot, now, reason):
        state = self.states[robot]
        if state.goal_id is None:
            return
        state.stop_reason = reason
        state.cancel_requested = True
        if not state.accepted or state.cancel_started_at is not None:
            return
        state.phase = "canceling"
        state.cancel_started_at = now
        self._emit("cancel_goal", robot, now, reason=reason)

    def safety_stop(self, now, reason):
        """Stop the episode and request cancellation, preserving unknown owners."""
        self.tick(now)
        self._stop(self._now, reason)

    def _stop(self, now, reason):
        self.stopped = True
        for robot, state in self.states.items():
            state.pending = None
            self._cancel(robot, now, str(reason))

    def _fail(self, robot, now, reason):
        state = self.states[robot]
        if state.failure is None:
            state.failure = reason
            self._emit("protocol_failure", robot, now, reason=reason)
        self._stop(now, reason)
        if state.goal_id is None:
            state.phase = "failed"

    def on_accept(self, robot, goal_id, accepted, now):
        self.tick(now)
        now = self._now
        state = self.states.get(robot)
        if state is None or state.goal_id != goal_id:
            return "stale_goal"
        if state.accepted:
            return "duplicate"
        if not accepted:
            self._release(robot, now, "REJECTED")
            self._fail(robot, now, "navigation_rejected")
            return "rejected"
        state.accepted = True
        state.accepted_at = now
        state.commitment_until = now + self.commitment_sec
        if self.stopped or state.cancel_requested or state.failure:
            self._cancel(robot, now, state.stop_reason or "late_acceptance")
            return "canceling"
        state.phase = "active"
        return "active"

    def on_cancel_response(self, robot, goal_id, accepted, now):
        self.tick(now)
        state = self.states.get(robot)
        if state is None or state.goal_id != goal_id:
            return "stale_goal"
        if state.cancel_started_at is None:
            return "unexpected_cancel_response"
        if state.cancel_accepted is not None:
            return "duplicate"
        state.cancel_accepted = bool(accepted)
        self._emit("cancel_response", robot, self._now, accepted=bool(accepted))
        return "awaiting_terminal"

    def _release(self, robot, now, status):
        state = self.states[robot]
        self._emit("protocol_terminal", robot, now, status=status,
                   command_id=state.command["command_id"])
        state.last_terminal = status
        state.last_goal_id = state.goal_id
        state.goal_id = None
        state.goal = None
        state.command = None
        state.requested_at = None
        state.accepted_at = None
        state.lease_until = None
        state.commitment_until = 0.0
        state.cancel_started_at = None
        state.cancel_accepted = None
        state.accepted = False
        state.cancel_requested = False
        state.phase = "failed" if state.failure else "idle"

    def on_result(self, robot, goal_id, status, now):
        self.tick(now)
        now = self._now
        state = self.states.get(robot)
        if state is None or state.goal_id != goal_id:
            return "stale_goal"
        status = TERMINAL_STATUSES.get(status, status)
        if status not in ("SUCCEEDED", "CANCELED", "ABORTED"):
            self._fail(robot, now, "navigation_nonterminal_result")
            state.phase = "unknown"
            return "nonterminal"
        pending = state.pending
        cancel_requested = state.cancel_requested
        self._release(robot, now, status)
        state.pending = None
        if status == "ABORTED" or (status == "CANCELED" and not cancel_requested):
            self._fail(robot, now, "navigation_" + status.lower())
        if pending is not None and not self.stopped:
            if pending["expires_at"] > now:
                self._start(robot, pending, now)
                return "replacement_sent"
            self._emit("pending_goal_expired", robot, now,
                       command_id=pending["command_id"], expires_at=pending["expires_at"])
            return "replacement_expired"
        return "terminal"

    def tick(self, now):
        """Enforce independent RPC, execution and delivered-lease deadlines."""
        now = self._time(now)
        for robot, state in self.states.items():
            if state.goal_id is None:
                continue
            if state.phase == "accepting":
                if now - state.requested_at >= self.response_timeout_sec:
                    self._fail(robot, now, "navigation_response_timeout")
                    state.phase = "unknown"
                elif not state.cancel_requested and now >= state.lease_until:
                    self._fail(robot, now, "goal_lease_expired")
                    state.phase = "unknown"
            elif state.phase == "active":
                if now - state.accepted_at >= self.execution_timeout_sec:
                    self._fail(robot, now, "navigation_execution_timeout")
                elif now >= state.lease_until:
                    self._fail(robot, now, "goal_lease_expired")
            elif state.phase == "canceling":
                if now - state.cancel_started_at >= self.cancel_timeout_sec:
                    reason = ("navigation_cancel_rejected" if state.cancel_accepted is False
                              else "navigation_cancel_timeout")
                    self._fail(robot, now, reason)
                    state.phase = "unknown"

    def navigation(self, now=None):
        """Return a detached observation of protocol ownership and target state."""
        if now is not None:
            self.tick(now)
        result = {}
        for robot, state in self.states.items():
            command = state.command or {}
            result[robot] = dict(
                phase=state.phase, goal_id=state.goal_id,
                goal_x=None if state.goal is None else state.goal["x"],
                goal_y=None if state.goal is None else state.goal["y"],
                command_id=command.get("command_id"),
                observation_version=command.get("observation_version"),
                created_at=command.get("created_at"), expires_at=command.get("expires_at"),
                requested_at=state.requested_at, accepted_at=state.accepted_at,
                commitment_until=state.commitment_until, lease_until=state.lease_until,
                cancel_requested=state.cancel_requested, failure=state.failure,
                stop_reason=state.stop_reason, owned=state.goal_id is not None,
                last_terminal=state.last_terminal, last_goal_id=state.last_goal_id,
            )
        return result

    def reset(self, epoch, now=0.0):
        """Start a fresh epoch after all owned action terminals were observed."""
        if not self.closed:
            raise RuntimeError("cannot reset while Nav2 ownership is unresolved")
        if not isinstance(epoch, str) or not epoch or epoch in self._epochs:
            raise ValueError("reset requires a new nonempty episode epoch")
        self.epoch = epoch
        self._epochs.add(epoch)
        self._initialize()
        self._time(now)
