"""Closed-episode, mask-preserving rollouts for the MR3 MaskablePPO pilot.

The collector closes every episode before an optimizer update. A late, no-action
terminal notification can therefore settle the preceding decision before that
decision is ever used for learning. API calls and actor samples are distinct.
"""

import copy
from dataclasses import dataclass, field, replace
import math

import numpy as np
import torch
from sb3_contrib.common.maskable.buffers import MaskableDictRolloutBuffer


def _finite(value, name):
    if isinstance(value, (bool, np.bool_)) or not isinstance(
            value, (int, float, np.integer, np.floating)) or not math.isfinite(value):
        raise ValueError(f"{name} must be a finite number")
    return float(value)


def _time_ns(value):
    return round(_finite(value, "simulation timestamp") * 10**9)


@dataclass(frozen=True)
class DecisionTransition:
    """One submitted decision, with its sampling-time tensors and probability.

    ``info`` describes the returned transition; its epoch is mandatory.
    ``next_value`` is computed by the unchanged collecting policy from the actual
    next observation. True task termination suppresses it; external truncation
    retains it. No-action terminal records must use ``merge_zero_terminal``.
    """

    observation: dict
    action: int
    reward: float
    value: float
    log_prob: float
    next_value: float
    dt: float
    terminated: bool
    truncated: bool
    info: dict = field(default_factory=dict)
    action_mask: object = None

    def __post_init__(self):
        if type(self.terminated) is not bool or type(self.truncated) is not bool \
                or (self.terminated and self.truncated):
            raise ValueError("termination and truncation must be distinct boolean flags")
        info = copy.deepcopy(self.info)
        if not isinstance(info, dict) or not isinstance(info.get("epoch"), str) \
                or not info["epoch"]:
            raise ValueError("a decision requires its nonempty episode epoch")
        if info.get("action_submitted", True) is not True:
            raise ValueError("a no-action API record is not an actor decision")
        if info.get("terminal_observation_reused", False):
            raise ValueError("a reused terminal observation must settle a preceding decision")
        for name in ("reward", "value", "log_prob", "next_value", "dt"):
            object.__setattr__(self, name, _finite(getattr(self, name), name))
        if self.dt < 0 or self.dt > 1.:
            raise ValueError("decision duration must lie within the one-second step")
        if not self.terminated and _time_ns(self.dt) != 10**9:
            raise ValueError("nonterminal and external-truncation decisions require one second")
        if self.dt == 0 and not info.get("merged_zero_terminal", False):
            physical_dt = _finite(info.get("physical_dt"), "physical_dt")
            if not self.terminated or not 0 < physical_dt <= .02:
                raise ValueError("zero-duration submitted terminal requires real physical advance")
        if not isinstance(self.observation, dict) or "action_mask" not in self.observation:
            raise ValueError("the sampling observation must contain its saved action mask")
        observation = {}
        for key, array in self.observation.items():
            if not isinstance(key, str) or not isinstance(array, np.ndarray):
                raise ValueError("observations must contain named numpy tensors")
            frozen = array.copy()
            if not np.isfinite(frozen).all():
                raise ValueError("observation tensors must be finite")
            frozen.setflags(write=False)
            observation[key] = frozen
        original_mask = observation["action_mask"]
        if original_mask.ndim != 1 or not np.isin(original_mask, (0, 1)).all():
            raise ValueError("the observation action mask must be a binary vector")
        mask = original_mask.astype(bool, copy=True)
        if self.action_mask is not None and not np.array_equal(self.action_mask, mask):
            raise ValueError("rollout mask must equal the sampling observation mask")
        if isinstance(self.action, (bool, np.bool_)) or not isinstance(
                self.action, (int, np.integer)) or not 0 <= self.action < len(mask) \
                or not mask[self.action]:
            raise ValueError("the sampled joint action must be legal under its saved mask")
        if self.log_prob > 1e-6:
            raise ValueError("a sampled categorical log probability cannot be positive")
        mask.setflags(write=False)
        object.__setattr__(self, "observation", observation)
        object.__setattr__(self, "action_mask", mask)
        object.__setattr__(self, "action", int(self.action))
        object.__setattr__(self, "info", info)


def merge_zero_terminal(previous, reward, info):
    """Settle a proven same-boundary terminal without another actor sample/gamma.

    The environment has already checked exact snapshot reuse. This layer also
    binds the scalar settlement to the previous epoch, reward sequence, delivery
    watermarks and effective end time. A first-call or duplicate settlement is
    rejected instead of assigning a reward to an action that was never executed.
    """
    if not isinstance(previous, DecisionTransition) or previous.terminated or previous.truncated:
        raise ValueError("zero terminal requires a preceding open submitted decision")
    reward = _finite(reward, "terminal settlement reward")
    if not isinstance(info, dict):
        raise ValueError("zero terminal requires explicit environment proof")
    diagnostic = info.get("reward_diagnostics", {})
    prior_diagnostic = previous.info.get("reward_diagnostics", {})
    if not isinstance(diagnostic, dict) or not isinstance(prior_diagnostic, dict) \
            or not isinstance(diagnostic.get("reward_terms"), dict):
        raise ValueError("zero terminal requires scalar reward diagnostics")
    if (info.get("epoch") != previous.info["epoch"]
            or info.get("action_submitted") is not False
            or info.get("terminal_observation_reused") is not True
            or info.get("dt") != 0. or info.get("physical_dt") != 0.
            or "command" not in info or info["command"] is not None
            or info.get("bootstrap") != 0
            or type(info.get("requested_action")) is not int
            or not 0 <= info["requested_action"] < len(previous.action_mask)
            or diagnostic.get("epoch") != previous.info["epoch"]
            or diagnostic.get("terminated") is not True
            or diagnostic.get("truncated") is not False
            or diagnostic.get("reward") != reward
            or diagnostic.get("delta_sim_time") != 0.
            or diagnostic.get("new_correct_free_cells") != 0
            or diagnostic.get("reward_terms", {}).get("coverage") != 0.
            or diagnostic.get("map_pairing_scope") != "terminal_evaluator_frozen_before_drain"
            or type(prior_diagnostic.get("sequence")) is not int
            or type(diagnostic.get("sequence")) is not int
            or diagnostic["sequence"] != prior_diagnostic["sequence"] + 1
            or not isinstance(info.get("reason"), str) or not info["reason"]
            or info["reason"] != diagnostic.get("reason")
            or not isinstance(info.get("watermarks"), dict)
            or info.get("watermarks") != previous.info.get("watermarks")):
        raise ValueError("invalid zero-duration/no-action terminal settlement proof")
    end_ns = _time_ns(prior_diagnostic.get("effective_step_end"))
    if any(_time_ns(diagnostic.get(key)) != end_ns for key in
           ("step_start", "effective_step_end", "requested_step_end")):
        raise ValueError("zero terminal must settle the preceding unchanged boundary")
    for key in ("observation_sequence", "observation_digest", "candidate_version"):
        if key not in info or info[key] != previous.info.get(key):
            raise ValueError("zero terminal must retain the preceding observation identity")
    merged_info = copy.deepcopy(previous.info)
    merged_info.update(merged_zero_terminal=True, terminal_settlement_info=copy.deepcopy(info),
                       reason=info["reason"], bootstrap=0)
    return replace(previous, reward=previous.reward + reward, terminated=True,
                   truncated=False, next_value=0., info=merged_info)


class DurationAwareMaskableDictRolloutBuffer(MaskableDictRolloutBuffer):
    """SB3 buffer with explicit next values and per-sim-second GAE discounts.

    It stores flattened, fully closed episodes in one logical environment. Actual
    simulator workers remain isolated; flattening never makes their GAE chains
    adjacent because each episode terminates or externally truncates explicitly.
    """

    def __init__(self, *args, **kwargs):
        if kwargs.get("n_envs", 1) != 1:
            raise ValueError("closed episodes must be flattened into one logical environment")
        super().__init__(*args, **kwargs)

    def reset(self):
        super().reset()
        self.durations = np.zeros(self.buffer_size, dtype=np.float64)
        self.next_values = np.zeros(self.buffer_size, dtype=np.float64)
        self.terminated = np.zeros(self.buffer_size, dtype=bool)
        self.truncated = np.zeros(self.buffer_size, dtype=bool)
        self.transition_metadata = []

    def add_transition(self, transition, *, episode_start):
        if self.full or not isinstance(transition, DecisionTransition):
            raise ValueError("buffer requires an unfilled slot and a submitted decision")
        if not self.observation_space.contains(transition.observation):
            raise ValueError("saved observation violates the frozen observation space")
        if len(transition.action_mask) != self.mask_dims:
            raise ValueError("saved action mask does not match the discrete action space")
        index = self.pos
        super().add(
            {key: value[np.newaxis] for key, value in transition.observation.items()},
            np.asarray([[transition.action]]), np.asarray([transition.reward]),
            np.asarray([episode_start]), torch.tensor([transition.value]),
            torch.tensor([transition.log_prob]), action_masks=transition.action_mask[np.newaxis],
        )
        self.durations[index] = transition.dt
        self.next_values[index] = transition.next_value
        self.terminated[index] = transition.terminated
        self.truncated[index] = transition.truncated
        self.transition_metadata.append(copy.deepcopy(transition.info))

    def compute_returns_and_advantage(self, last_values=None, dones=None):
        """Bootstrap truncation once; stop recursion at every closed boundary."""
        if not self.full or not (self.terminated[-1] or self.truncated[-1]):
            raise ValueError("GAE requires complete closed episodes, including the final row")
        carry = 0.
        for index in reversed(range(self.buffer_size)):
            discount = self.gamma ** self.durations[index]
            trace_discount = self.gae_lambda ** self.durations[index]
            bootstrap = 0. if self.terminated[index] else self.next_values[index]
            delta = float(self.rewards[index, 0]) + discount * bootstrap - float(self.values[index, 0])
            closed = self.terminated[index] or self.truncated[index]
            carry = delta + (0. if closed else discount * trace_discount * carry)
            self.advantages[index, 0] = carry
        self.returns = self.advantages + self.values

    def get(self, batch_size=None):
        """Keep SB3's permutation while merging a final singleton minibatch.

        MaskablePPO normalizes advantages with an unbiased standard deviation.
        A one-row minibatch would produce NaN. Closed episode lengths vary, so
        the last minibatch may contain ``batch_size + 1`` rows instead.
        """
        if self.buffer_size < 2 or (batch_size is not None and
                                    (type(batch_size) is not int or batch_size < 2)):
            raise ValueError("normalized PPO minibatches require at least two decisions")
        pending = None
        for sample in super().get(batch_size):
            if pending is None:
                pending = sample
            elif len(sample.actions) == 1:
                fields = {name: torch.cat((getattr(pending, name), getattr(sample, name)))
                          for name in pending._fields if name != "observations"}
                fields["observations"] = {
                    key: torch.cat((pending.observations[key], sample.observations[key]))
                    for key in pending.observations}
                yield type(pending)(**fields)
                pending = None
            else:
                yield pending
                pending = sample
        if pending is not None:
            yield pending


def build_rollout_buffer(episodes, observation_space, action_space, *, gamma=.99,
                         gae_lambda=.95, device="cpu"):
    """Build an exact, full SB3 training buffer from settled closed episodes."""
    gamma = _finite(gamma, "gamma")
    gae_lambda = _finite(gae_lambda, "gae_lambda")
    if not 0 < gamma <= 1 or not 0 < gae_lambda <= 1:
        raise ValueError("per-second gamma and GAE lambda must lie in (0, 1]")
    episodes = [list(episode) for episode in episodes]
    if not episodes or any(not episode for episode in episodes):
        raise ValueError("a rollout needs nonempty closed episodes")
    seen_epochs = set()
    for episode in episodes:
        if any(not isinstance(row, DecisionTransition) for row in episode):
            raise ValueError("episodes contain submitted DecisionTransition rows only")
        epoch = episode[0].info["epoch"]
        if epoch in seen_epochs:
            raise ValueError("a closed episode epoch cannot appear twice in a rollout")
        seen_epochs.add(epoch)
        prior_end_ns = None
        prior_sequence = None
        for index, row in enumerate(episode):
            closed = row.terminated or row.truncated
            if row.info["epoch"] != epoch or closed != (index == len(episode) - 1):
                raise ValueError("each episode must keep one epoch and close exactly at its final row")
            diagnostic = row.info.get("reward_diagnostics", {})
            if not isinstance(diagnostic, dict) or diagnostic.get("epoch") != epoch \
                    or type(diagnostic.get("sequence")) is not int:
                raise ValueError("each decision requires its epoch-bound reward sequence")
            start_ns = _time_ns(diagnostic.get("step_start"))
            end_ns = _time_ns(diagnostic.get("effective_step_end"))
            sequence = diagnostic["sequence"]
            if (end_ns - start_ns != _time_ns(row.dt)
                    or (prior_end_ns is not None and start_ns != prior_end_ns)
                    or (prior_sequence is not None and sequence != prior_sequence + 1)):
                raise ValueError("episode decisions require contiguous time and reward sequences")
            prior_end_ns, prior_sequence = end_ns, sequence
            if not closed and not math.isclose(
                    row.next_value, episode[index + 1].value, rel_tol=1e-5, abs_tol=1e-6):
                raise ValueError("next value must come from the unchanged collecting policy")
    buffer = DurationAwareMaskableDictRolloutBuffer(
        sum(map(len, episodes)), observation_space, action_space, device=device,
        gamma=gamma, gae_lambda=gae_lambda, n_envs=1,
    )
    for episode in episodes:
        for index, transition in enumerate(episode):
            buffer.add_transition(transition, episode_start=index == 0)
    buffer.compute_returns_and_advantage()
    return buffer
