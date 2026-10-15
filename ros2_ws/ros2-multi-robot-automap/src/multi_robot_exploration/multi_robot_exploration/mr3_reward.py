"""First-correct-cell reward bookkeeping, confined to the evaluator process.

This module has no actor, navigation, ROS or map sampling interface. Its boolean
truth/correct-cell inputs stay inside the independent evaluator. Only detached
JSON scalar summaries may cross the training IPC boundary.
"""

import copy
from dataclasses import asdict, dataclass
import hashlib
import json
import math

import numpy as np


SCHEMA = "mr3-reward-v1"
TASK_DURATION_SEC = 300.0
TASK_FAILURE_REASONS = frozenset((
    "timeout", "navigation_failure", "collision", "collision_monitoring_interrupted",
    "map_contract_error", "pose_discontinuity", "task_gate_regressed_during_closure",
    "navigation_closure_timeout", "navigation_closure_invalid",
))


@dataclass(frozen=True)
class RewardWeights:
    """Predeclared initial reward scale; not a learned-performance claim."""

    coverage: float = 10.0
    time: float = 1.0
    collision: float = 20.0
    switch: float = .01
    invalid: float = .05
    success: float = 10.0
    failure: float = 20.0

    def __post_init__(self):
        for name, value in asdict(self).items():
            if isinstance(value, bool) or not math.isfinite(value) or value < 0:
                raise ValueError(f"reward weight {name} must be finite and nonnegative")
        if self.failure <= self.coverage:
            raise ValueError("failure penalty must exceed all possible coverage reward")
        if self.collision <= self.coverage + self.time:
            raise ValueError("contact penalty must exceed coverage gain and saved task time")


def _finite_time(value, name):
    if isinstance(value, bool):
        raise ValueError(f"{name} must be finite simulation time")
    value = float(value)
    if not math.isfinite(value) or value < 0:
        raise ValueError(f"{name} must be finite nonnegative simulation time")
    return value


def _counter(value, name):
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a nonnegative integer")
    return value


class RewardLedger:
    """An epoch-owned, monotone first-correct-free-cell ledger.

    Initial known free cells seed the ledger without rewarding startup warmup.
    Repeated snapshots, map regression, re-upload and loop closure cannot pay
    again for any truth cell. Success must already have been confirmed by the
    unchanged evaluator gates, including terminal navigation ownership.
    """

    def __init__(self, epoch, start_sim_time, truth_free_mask,
                 initial_correct_free_mask, weights=None):
        if not isinstance(epoch, str) or not epoch:
            raise ValueError("reward epoch must be nonempty")
        self.epoch = epoch
        self.start_sim_time = _finite_time(start_sim_time, "start_sim_time")
        self.weights = RewardWeights() if weights is None else weights
        self._free = np.asarray(truth_free_mask)
        if self._free.ndim != 2 or self._free.dtype != np.bool_:
            raise ValueError("truth_free_mask must be a two-dimensional boolean array")
        self._free = self._free.copy()
        self.denominator = int(np.count_nonzero(self._free))
        if not self.denominator:
            raise ValueError("reward truth must contain free cells")
        self._seen = self._correct_mask(initial_correct_free_mask)
        self.initial_correct_count = int(np.count_nonzero(self._seen))
        self.rewarded_correct_count = 0
        self.last_end = self.start_sim_time
        self.last_sequence = 0
        self.sealed = False
        self._counts = {"collision_events": 0, "goal_switches": 0, "rejected_actions": 0}
        self._responses = {}

    def _correct_mask(self, value):
        mask = np.asarray(value)
        if mask.shape != self._free.shape or mask.dtype != np.bool_:
            raise ValueError("correct-free mask must match the boolean truth grid")
        if np.any(mask & ~self._free):
            raise ValueError("correct-free mask includes occupied or outside-ROI cells")
        return mask.copy()

    def advance(self, *, epoch, sequence, step_start, step_end,
                current_correct_free_mask, collision_events, goal_switches,
                rejected_actions, terminal_reason=None, external_truncation=None):
        """Account one actual simulation interval and return JSON scalar values.

        Exact duplicate sequences return the original result. Conflicting,
        skipped, reversed or cross-epoch input fails without changing any ledger
        state. A terminal/truncated ledger cannot accept another transition.
        """
        if epoch != self.epoch:
            raise ValueError("reward request belongs to a different episode epoch")
        sequence = _counter(sequence, "sequence")
        if sequence < 1:
            raise ValueError("reward sequence starts at one")
        start = _finite_time(step_start, "step_start")
        end = _finite_time(step_end, "step_end")
        if end < start:
            raise ValueError("reward simulation time moved backwards")
        mask = self._correct_mask(current_correct_free_mask)
        counts = {
            "collision_events": _counter(collision_events, "collision_events"),
            "goal_switches": _counter(goal_switches, "goal_switches"),
            "rejected_actions": _counter(rejected_actions, "rejected_actions"),
        }
        if terminal_reason is not None and terminal_reason != "coverage_reached" \
                and terminal_reason not in TASK_FAILURE_REASONS:
            raise ValueError("unknown task terminal reason; infrastructure is a worker exception")
        if external_truncation in (None, False):
            cut = None
        elif external_truncation is True:
            cut = "external_truncation"
        elif isinstance(external_truncation, str) and external_truncation.strip():
            cut = external_truncation
        else:
            raise ValueError("external_truncation must be a reason string or boolean")
        fingerprint = hashlib.sha256(json.dumps({
            "start": start, "end": end, "counts": counts,
            "terminal_reason": terminal_reason, "external_truncation": cut,
        }, sort_keys=True, separators=(",", ":")).encode() + mask.tobytes()).hexdigest()
        previous = self._responses.get(sequence)
        if previous is not None:
            if fingerprint != previous[0]:
                raise ValueError("reward sequence reused with conflicting input")
            return copy.deepcopy(previous[1])
        if self.sealed:
            raise ValueError("reward ledger is already terminal or truncated")
        if sequence != self.last_sequence + 1:
            raise ValueError("reward sequence is not the next transition")
        if not math.isclose(start, self.last_end, rel_tol=0., abs_tol=1e-8):
            raise ValueError("reward intervals are not contiguous")
        if any(counts[key] < self._counts[key] for key in counts):
            raise ValueError("reward event counters regressed")
        elapsed = end - self.start_sim_time
        reason = terminal_reason
        if elapsed >= TASK_DURATION_SEC:
            reason = "timeout"
        elif counts["collision_events"] and reason == "coverage_reached":
            raise ValueError("contact cannot be classified as task success")
        elif counts["collision_events"] and reason is None:
            reason = "collision"
        terminated = reason is not None
        truncated = bool(cut is not None and not terminated)
        if end == start and not terminated and not truncated:
            raise ValueError("a nonterminal reward transition must advance simulation time")
        newly_correct = mask & ~self._seen
        new_count = int(np.count_nonzero(newly_correct))
        deltas = {key: counts[key] - self._counts[key] for key in counts}
        weights = self.weights
        terms = {
            "coverage": weights.coverage * new_count / self.denominator,
            "time": -weights.time * (end - start) / TASK_DURATION_SEC,
            "collision": -weights.collision * deltas["collision_events"],
            "switch": -weights.switch * deltas["goal_switches"],
            "invalid": -weights.invalid * deltas["rejected_actions"],
            "success": weights.success if reason == "coverage_reached" else 0.,
            "failure": -weights.failure if terminated and reason != "coverage_reached" else 0.,
        }
        result = {
            "schema": SCHEMA, "epoch": self.epoch, "sequence": sequence,
            "step_start": start, "effective_step_end": end,
            "delta_sim_time": end - start, "elapsed_sim_time": elapsed,
            "remaining_sim_time": max(0., TASK_DURATION_SEC - elapsed),
            "reward": float(sum(terms.values())), "reward_terms": terms,
            "reward_weights": asdict(weights),
            "terminated": terminated, "truncated": truncated,
            "reason": reason if terminated else cut if truncated else None,
            "new_correct_free_cells": new_count,
            "rewarded_correct_free_cells": self.rewarded_correct_count + new_count,
            "initial_correct_free_cells": self.initial_correct_count,
            "current_correct_free_cells": int(np.count_nonzero(mask)),
            "truth_free_cell_count": self.denominator,
            **{key + "_delta": value for key, value in deltas.items()},
        }
        self._seen |= newly_correct
        self.rewarded_correct_count += new_count
        self.last_end = end
        self.last_sequence = sequence
        self._counts = counts
        self.sealed = terminated or truncated
        self._responses[sequence] = (fingerprint, copy.deepcopy(result))
        return result
