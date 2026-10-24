"""Private scalar evaluator for the 2D proxy, never an actor dependency.

Construct this class only inside the isolated evaluator process. Contract truth,
correct-cell masks and the world evaluation state remain private. Responses are
detached JSON scalars from the original metric and reward implementations.
No proxy result supplies Gazebo/SLAM/Nav2/DDS/contact/native qualification credit.
"""

import copy
import hashlib
import json
import math
from pathlib import Path

import numpy as np

from multi_robot_exploration.mr3_episode import TASK_DURATION_NS, elapsed_ns, finite_time
from multi_robot_exploration.mr3_reward import RewardLedger
from multi_robot_exploration.mr3_task_contract import (
    compare_contract_occupancy_grid, load_contract_truth, load_task_contract,
    sample_contract_occupancy_grid,
)
from multi_robot_exploration.task_evaluator import mr3_participation_pass, mr3_quality_pass


ROBOTS = ("tb1", "tb2", "tb3")
NATIVE_GATES = (
    "native_slam", "native_nav2", "native_dds", "native_18_stream_contact_monitoring",
    "native_rigid_body_safety", "native_process_reset_and_closure", "native_95_task",
)


def _counter(value, name):
    if type(value) is not int or value < 0:
        raise ValueError(name + " must be a nonnegative integer")
    return value


class ProxyReward:
    """Reuse frozen task truth, metrics, gates and first-correct-cell rewards."""

    def __init__(self, scene, epoch):
        if scene not in ("open", "rooms", "corridors"):
            raise ValueError("only the three accepted development scenes are supported")
        if not isinstance(epoch, str) or not epoch:
            raise ValueError("proxy reward epoch must be nonempty")
        component = Path(__file__).resolve().parents[2] / "multi_robot"
        world = component / "worlds" / ("p1c_" + scene + ".world")
        self._contract = load_task_contract(component / "config/mr3_p1a" / (scene + ".json"), world)
        self._truth = load_contract_truth(world, self._contract)
        self.scene, self.epoch, self._ledger = scene, epoch, None
        self._responses = {}
        self._last_paths = {name: 0. for name in ROBOTS}
        self._last_goals = {name: 0 for name in ROBOTS}

    def _map(self, grid, resolution, origin):
        values = np.asarray(grid)
        if values.ndim != 2 or not values.shape[0] or not values.shape[1]:
            raise ValueError("proxy reward requires a nonempty two-dimensional delivered map")
        args = (self._truth, values.ravel(), values.shape[1], values.shape[0], resolution, origin)
        metrics = compare_contract_occupancy_grid(*args)
        sampled = sample_contract_occupancy_grid(*args)
        correct = ((sampled >= 0) & (sampled < 50)
                   & ~self._truth.occupied & self._truth.roi_mask)
        return values, correct, metrics

    @staticmethod
    def _physical(physical_state, goal_counts, navigation_closed):
        if type(navigation_closed) is not bool:
            raise ValueError("navigation_closed must be an explicit proxy executor boolean")
        paths = physical_state["path_lengths"]
        if set(paths) != set(ROBOTS) or set(goal_counts) != set(ROBOTS):
            raise ValueError("path lengths and goal counts must name exactly three robots")
        lengths = {}
        for name in ROBOTS:
            value = paths[name]
            if isinstance(value, bool) or not isinstance(value, (int, float)) \
                    or not math.isfinite(value) or value < 0:
                raise ValueError("proxy path lengths must be finite nonnegative scalars")
            lengths[name] = float(value)
        goals = {name: _counter(goal_counts[name], name + " goal count") for name in ROBOTS}
        collisions = _counter(physical_state["collision_events"], "collision_events")
        return lengths, goals, collisions

    def _gates(self, metrics, paths, goals, navigation_closed, collisions):
        quality = mr3_quality_pass(metrics, self._contract.data["quality"])
        participation = mr3_participation_pass(
            paths, {name: range(goals[name]) for name in ROBOTS}, self._contract.data["participation"])
        live = dict(metrics, map_quality_pass=quality, robot_participation_pass=participation,
                    navigation_protocol_closed=navigation_closed, proxy_contact_events=collisions)
        eligible = (metrics["correct_free_coverage_ratio"] >= self._contract.data["coverage_threshold"]
                    and quality and participation and navigation_closed and collisions == 0)
        return live, bool(eligible)

    @staticmethod
    def _scope(response, metrics, success=False):
        return {**copy.deepcopy(response), "metrics": copy.deepcopy(metrics),
                "evaluation_scope": "isolated_2d_proxy_only",
                "proxy_task_success": bool(success), "native_task_success": False,
                "native_qualification": False,
                "native_gates_unprovided": {name: None for name in NATIVE_GATES}}

    def initialize(self, grid, resolution, origin, start_time):
        """Bind the first actual delivered snapshot at reward seq0 without gain."""
        if self._ledger is not None:
            raise ValueError("proxy reward seq0 was already bound; reset requires a new evaluator")
        start = finite_time(start_time, "start_time")
        _, correct, metrics = self._map(grid, resolution, origin)
        self._ledger = RewardLedger(self.epoch, start,
            ~self._truth.occupied & self._truth.roi_mask, correct)
        metrics, _ = self._gates(metrics, self._last_paths, self._last_goals, False, 0)
        return self._scope({
            "schema": "mr3-reward-v1", "kind": "reward_reset_binding", "epoch": self.epoch,
            "sequence": 0, "reward": 0., "terminated": False, "truncated": False,
            "reason": None, "step_start": start, "effective_step_end": start,
            "delta_sim_time": 0., "elapsed_sim_time": 0., "reset_bound": True,
            "initial_correct_free_cells": self._ledger.initial_correct_count,
        }, metrics)

    def check(self, physical_state, now, *, navigation_failed=False):
        """Private lightweight 20 ms terminal check; never advance the ledger."""
        if self._ledger is None:
            raise ValueError("proxy terminal checks require actual seq0 initialization")
        if type(navigation_failed) is not bool:
            raise ValueError("navigation_failed must be a boolean")
        elapsed = elapsed_ns(self._ledger.start_sim_time, now)
        if elapsed < 0:
            raise ValueError("proxy evaluator clock regressed before task start")
        collisions = _counter(physical_state["collision_events"], "collision_events")
        reason = ("timeout" if elapsed >= TASK_DURATION_NS else
                  "navigation_failure" if navigation_failed else
                  "collision" if collisions else None)
        return {"terminal_reason": reason, "terminated": reason is not None,
                "elapsed_sim_time": elapsed / 1e9, "proxy_contact_events": collisions,
                "evaluation_scope": "isolated_2d_proxy_only", "native_task_success": False}

    def inspect(self, grid, resolution, origin, *, physical_state, goal_counts,
                navigation_closed=False):
        """Private map gate inspection to request actual proxy terminal closure.

        The candidate is only a task-terminal handshake trigger. It must never
        be delivered to actor/candidate/mask/planning consumers as a feature.
        """
        _, _, metrics = self._map(grid, resolution, origin)
        paths, goals, collisions = self._physical(physical_state, goal_counts, navigation_closed)
        metrics, eligible = self._gates(metrics, paths, goals, navigation_closed, collisions)
        candidate = (metrics["correct_free_coverage_ratio"] >= self._contract.data["coverage_threshold"]
                     and metrics["map_quality_pass"] and metrics["robot_participation_pass"]
                     and collisions == 0)
        return {"metrics": metrics, "coverage_candidate": bool(candidate),
                "proxy_success_gates_closed": eligible,
                "evaluation_scope": "isolated_2d_proxy_only", "native_task_success": False,
                "native_gates_unprovided": {name: None for name in NATIVE_GATES}}

    def advance(self, grid, resolution, origin, *, sequence, step_start, step_end,
                physical_state, goal_counts, navigation_closed, goal_switches,
                rejected_actions, external_truncation=None, terminal_reason=None):
        if self._ledger is None:
            raise ValueError("proxy reward requires actual seq0 initialization first")
        values, correct, metrics = self._map(grid, resolution, origin)
        paths, goals, collisions = self._physical(physical_state, goal_counts, navigation_closed)
        metrics, eligible = self._gates(metrics, paths, goals, navigation_closed, collisions)
        # Bind wrapper-only gate inputs as well as the original ledger inputs.
        # A duplicate cannot alter participation/closure while borrowing reward.
        fingerprint = hashlib.sha256(json.dumps({
            "resolution": resolution, "origin": list(origin), "shape": list(values.shape),
            "sequence": sequence, "step_start": step_start, "step_end": step_end,
            "paths": paths, "goals": goals, "navigation_closed": navigation_closed,
            "collisions": collisions, "goal_switches": goal_switches,
            "rejected_actions": rejected_actions, "external_truncation": external_truncation,
            "terminal_reason": terminal_reason,
        }, sort_keys=True, allow_nan=False, separators=(",", ":")).encode()
            + values.astype(np.int16).tobytes()).hexdigest()
        previous = self._responses.get(sequence)
        if previous is not None:
            if fingerprint != previous[0]:
                raise ValueError("proxy reward sequence reused with conflicting gate input")
            return copy.deepcopy(previous[1])
        if any(paths[name] < self._last_paths[name] or goals[name] < self._last_goals[name]
               for name in ROBOTS):
            raise ValueError("proxy cumulative participation counters regressed")
        reason = terminal_reason
        # The original ledger also enforces this precedence; retain it before
        # interpreting an explicit coverage claim or an external sampler cut.
        if elapsed_ns(self._ledger.start_sim_time, step_end) >= TASK_DURATION_NS:
            reason = "timeout"
        elif reason == "coverage_reached" and not eligible:
            raise ValueError("proxy coverage success lacks unchanged task gates")
        elif reason is None and eligible:
            reason = "coverage_reached"
        result = self._ledger.advance(
            epoch=self.epoch, sequence=sequence, step_start=step_start, step_end=step_end,
            current_correct_free_mask=correct, collision_events=collisions,
            goal_switches=goal_switches, rejected_actions=rejected_actions,
            terminal_reason=reason, external_truncation=external_truncation)
        response = self._scope(result, metrics,
            success=eligible and result["reason"] == "coverage_reached")
        self._last_paths, self._last_goals = paths, goals
        self._responses[sequence] = (fingerprint, copy.deepcopy(response))
        return response
