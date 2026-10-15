"""Gymnasium boundary around the process-rebuilding MR3 supervisor.

The supervisor owns ROS/Gazebo processes, the independent reward process, fixed
simulation-time advancement and native terminal closure. This wrapper imports
no ROS code and never creates goals, rewards, maps, or replacement observations.
Infrastructure exceptions propagate; an absent next observation is not replaced
with a fabricated transition. ``max_steps`` is an external sampler limit passed
to the supervisor for the final complete step; the task deadline takes priority.
"""

import copy
import math

import gymnasium as gym
import numpy as np

from .observation import TENSOR_SCHEMA, encode_snapshot, observation_space


def _safe_info(value):
    """Keep aggregate diagnostics while refusing private reward/evaluation arrays."""
    if isinstance(value, dict):
        output = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError("info keys must be strings")
            normalized = key.lower().replace("_", "").replace("-", "")
            if ("mask" in normalized or "indices" in normalized or "cellids" in normalized
                    or normalized in (
                        "truth", "groundtruth", "correctcells", "firstcorrectcells")):
                raise ValueError("private truth/mask/cell-index data must not enter Gym info")
            output[key] = _safe_info(item)
        return output
    if isinstance(value, list):
        return [_safe_info(item) for item in value]
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float) and math.isfinite(value):
        return value
    raise ValueError("info must contain finite JSON diagnostics, without private arrays")


class MR3Env(gym.Env):
    """One centralized joint-action environment with exactly three robot slots."""

    metadata = {"render_modes": []}

    def __init__(self, supervisor=None, *, scene="open", max_steps=None):
        super().__init__()
        if supervisor is None:
            from .supervisor import Supervisor
            supervisor = Supervisor()
        self.supervisor = supervisor
        self.scene = scene
        self.max_steps = self._limit(max_steps)
        self.observation_space = observation_space()
        self.action_space = gym.spaces.Discrete(1000)
        self.render_mode = None
        self._snapshot = None
        self._watermarks = None
        self._epoch = None
        self._episode_done = True
        self._closed = False
        self._steps = 0
        self._active_limit = self.max_steps

    @staticmethod
    def _limit(value):
        if value is not None and (type(value) is not int or value <= 0):
            raise ValueError("max_steps must be a positive integer or None")
        return value

    def _validate_reused_terminal(self, payload, info, requested_action):
        """A late terminal at the saved boundary submits no new action or tick."""
        snapshot = payload["snapshot"]
        diagnostic = info.get("reward_diagnostics", {})
        if not isinstance(diagnostic, dict):
            raise ValueError("reused terminal observation requires reward diagnostics")
        if (payload["terminated"] is not True or payload["truncated"] is not False
                or snapshot != self._snapshot or info.get("dt") != 0.
                or info.get("physical_dt") != 0. or info.get("action_submitted") is not False
                or "command" not in info or info["command"] is not None
                or type(info.get("requested_action")) is not int
                or info["requested_action"] != requested_action
                or info.get("epoch") != self._epoch
                or not isinstance(info.get("watermarks"), dict)
                or info["watermarks"] != self._watermarks
                or diagnostic.get("epoch") != self._epoch
                or type(diagnostic.get("sequence")) is not int
                or diagnostic["sequence"] != self._steps + 1
                or diagnostic.get("terminated") is not True
                or diagnostic.get("truncated") is not False
                or diagnostic.get("map_pairing_scope") !=
                "terminal_evaluator_frozen_before_drain"
                or type(diagnostic.get("new_correct_free_cells")) is not int
                or diagnostic["new_correct_free_cells"] != 0
                or not isinstance(diagnostic.get("reward_terms"), dict)
                or type(diagnostic["reward_terms"].get("coverage")) not in (int, float)
                or diagnostic["reward_terms"]["coverage"] != 0.
                or diagnostic.get("reward") != payload["reward"]
                or not isinstance(diagnostic.get("reason"), str) or not diagnostic["reason"]
                or info.get("reason") != diagnostic["reason"]):
            raise ValueError("reused terminal observation lacks zero-duration/no-action proof")
        boundary_ns = round(snapshot["source_stamp"] * 10**9)
        times = [diagnostic.get(key) for key in
                 ("step_start", "effective_step_end", "requested_step_end")]
        if (any(type(value) not in (int, float) or not math.isfinite(value)
                or round(value * 10**9) != boundary_ns for value in times)
                or type(diagnostic.get("delta_sim_time")) not in (int, float)
                or diagnostic["delta_sim_time"] != 0.):
            raise ValueError("reused terminal reward must end at the unchanged physical boundary")

    def _unpack(self, payload, *, resetting=False, requested_action=None):
        if not isinstance(payload, dict):
            raise ValueError("supervisor must return an explicit transition payload")
        snapshot = payload["snapshot"]
        terminated, truncated = payload["terminated"], payload["truncated"]
        if type(terminated) is not bool or type(truncated) is not bool:
            raise ValueError("terminal and truncation flags must be booleans")
        if terminated and truncated:
            raise ValueError("task termination takes priority over external truncation")
        if resetting and (terminated or truncated):
            raise ValueError("reset did not produce a live initial episode")
        reward = payload["reward"]
        if isinstance(reward, bool) or not isinstance(reward, (int, float)) \
                or not math.isfinite(reward):
            raise ValueError("supervisor reward must be finite")
        observation = encode_snapshot(snapshot)
        if not self.observation_space.contains(observation):
            raise ValueError("encoded snapshot violates its frozen tensor space")
        epoch = snapshot.get("epoch")
        if not isinstance(epoch, str) or not epoch:
            raise ValueError("every episode requires a nonempty epoch")
        info = _safe_info(payload["info"])
        if not isinstance(info, dict):
            raise ValueError("transition info must be a dictionary")
        reused = info.get("terminal_observation_reused", False)
        if type(reused) is not bool or (resetting and reused):
            raise ValueError("invalid terminal observation reuse flag")
        if not resetting:
            if epoch != self._epoch:
                raise ValueError("cross-epoch transition")
            if reused:
                self._validate_reused_terminal(payload, info, requested_action)
            elif snapshot["sequence"] <= self._snapshot["sequence"]:
                raise ValueError("a transition cannot reuse an old observation sequence")
            if snapshot["source_stamp"] < self._snapshot["source_stamp"]:
                raise ValueError("simulation time rewound within an episode")
        dt = info.get("dt")
        if (isinstance(dt, bool) or not isinstance(dt, (int, float))
                or not math.isfinite(dt)):
            raise ValueError("transition info.dt must be a finite simulation duration")
        if resetting:
            if dt != 0 or reward != 0:
                raise ValueError("reset must initialize zero duration and zero reward")
        else:
            physical_dt = snapshot["source_stamp"] - self._snapshot["source_stamp"]
            declared = info.get("physical_dt")
            if (isinstance(declared, bool) or not isinstance(declared, (int, float))
                    or not math.isfinite(declared)
                    or not math.isclose(declared, physical_dt, abs_tol=1e-6)):
                raise ValueError("physical_dt must match the two captured simulation boundaries")
            if reused:
                pass  # The exact zero-duration/no-action terminal proof was checked above.
            elif not 0 < physical_dt <= 1.0 + 1e-6 or not 0 <= dt <= physical_dt + 1e-6:
                raise ValueError("simulation durations are outside the fixed-step contract")
            elif terminated:
                if physical_dt - dt > 0.020001:
                    raise ValueError("terminal detection lag exceeded one 20ms quantum")
            elif not (math.isclose(physical_dt, 1.0, abs_tol=1e-6)
                      and math.isclose(dt, 1.0, abs_tol=1e-6)):
                raise ValueError("nonterminal transitions must span exactly one simulated second")
        info.update({
            "epoch": epoch, "observation_sequence": snapshot["sequence"],
            "observation_digest": snapshot["digest"],
            "candidate_version": snapshot["candidate_version"],
            "tensor_schema": TENSOR_SCHEMA,
        })
        self._snapshot = copy.deepcopy(snapshot)
        self._watermarks = copy.deepcopy(info.get("watermarks"))
        self._epoch = epoch
        self._episode_done = terminated or truncated
        return observation, float(reward), terminated, truncated, info

    def reset(self, *, seed=None, options=None):
        if self._closed:
            raise RuntimeError("a closed MR3Env cannot be reset")
        if isinstance(seed, (bool, np.bool_)):
            raise ValueError("seed must be an integer, not a boolean")
        super().reset(seed=seed)
        options = dict(options or {})
        unknown = set(options) - {"scene", "max_steps"}
        if unknown:
            raise ValueError(f"unsupported reset options: {sorted(unknown)}")
        scene = options.get("scene", self.scene)
        if not isinstance(scene, str) or not scene:
            raise ValueError("scene must be a nonempty declared scene name")
        self._active_limit = self._limit(options.get("max_steps", self.max_steps))
        episode_seed = int(seed) if seed is not None else int(self.np_random.integers(1, 2**31))
        previous_epoch = self._epoch
        self._episode_done = True
        self._snapshot = None
        self._watermarks = None
        self._steps = 0
        payload = self.supervisor.reset(scene=scene, seed=episode_seed)
        if previous_epoch is not None and payload["snapshot"].get("epoch") == previous_epoch:
            raise ValueError("a full process reset must create a new episode epoch")
        observation, _, _, _, info = self._unpack(payload, resetting=True)
        info.update({"scene": scene, "seed": episode_seed})
        return observation, info

    def step(self, action):
        if self._closed or self._snapshot is None or self._episode_done:
            raise RuntimeError("reset is required before another step")
        if isinstance(action, (bool, np.bool_)) or not self.action_space.contains(action):
            raise ValueError("action must be an integer in [0, 999]")
        external = None
        if self._active_limit is not None and self._steps + 1 >= self._active_limit:
            external = "external_sampler_limit"
        self._episode_done = True  # A failed IPC/encoding call cannot be reused.
        payload = self.supervisor.step(int(action), external_truncation=external)
        result = self._unpack(payload, requested_action=int(action))
        self._steps += 1
        return result

    def action_masks(self):
        if self._snapshot is None or self._closed:
            raise RuntimeError("reset is required before querying an action mask")
        return np.asarray(self._snapshot["joint_action_mask"], dtype=bool).copy()

    def close(self):
        if not self._closed:
            self.supervisor.close()
            self._closed = True
            self._episode_done = True
