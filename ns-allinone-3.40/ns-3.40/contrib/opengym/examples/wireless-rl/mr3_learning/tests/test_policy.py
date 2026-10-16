"""CPU policy/optimizer contracts on frozen observations; no ROS or simulation."""

import copy
from pathlib import Path
import tempfile
import unittest

import gymnasium as gym
import numpy as np
from sb3_contrib import MaskablePPO
from sb3_contrib.common.maskable.buffers import MaskableDictRolloutBuffer
from sb3_contrib.common.maskable.policies import MaskableMultiInputActorCriticPolicy
import torch
from torch import nn

from mr3_learning.model import MR3ActorCritic, MR3Encoder
from mr3_learning.observation import encode_snapshot, observation_space
from mr3_learning.policy import MR3FeaturesExtractor, policy_kwargs
from mr3_learning.tests.test_observation import fixture


class FrozenObservationEnv(gym.Env):
    """Space provider for algorithm serialization; cannot produce transitions."""

    def __init__(self):
        self.observation_space = observation_space()
        self.action_space = gym.spaces.Discrete(1000)

    def reset(self, *, seed=None, options=None):
        super().reset(seed=seed)
        return encode_snapshot(fixture()), {}

    def step(self, action):
        raise AssertionError("this serialization fixture must never be sampled")


class PolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.previous_threads = torch.get_num_threads()
        torch.set_num_threads(1)

    @classmethod
    def tearDownClass(cls):
        torch.set_num_threads(cls.previous_threads)

    def setUp(self):
        torch.manual_seed(101)
        self.observation = encode_snapshot(fixture())
        self.mask = self.observation["action_mask"].astype(bool)
        self.policy = MaskableMultiInputActorCriticPolicy(
            observation_space(), gym.spaces.Discrete(1000), lambda _: 3e-4,
            **policy_kwargs()).cpu()
        self.policy.set_training_mode(False)

    def tensors(self, observation=None):
        return self.policy.obs_to_tensor(
            self.observation if observation is None else observation)[0]

    def test_fixed_shared_capacity_direct_heads_and_no_adaptive_normalization(self):
        self.assertFalse(self.policy.normalize_images)
        self.assertTrue(self.policy.share_features_extractor)
        self.assertIs(self.policy.pi_features_extractor, self.policy.vf_features_extractor)
        self.assertIsInstance(self.policy.features_extractor, MR3FeaturesExtractor)
        self.assertEqual(self.policy.features_extractor.features_dim, 256)
        self.assertEqual((self.policy.action_net.in_features, self.policy.action_net.out_features),
                         (256, 1000))
        self.assertEqual((self.policy.value_net.in_features, self.policy.value_net.out_features),
                         (256, 1))
        self.assertFalse(any(isinstance(module, (nn.BatchNorm1d, nn.BatchNorm2d, nn.LayerNorm))
                             for module in self.policy.modules()))
        self.assertEqual(len(self.policy.mlp_extractor.policy_net), 0)
        self.assertEqual(len(self.policy.mlp_extractor.value_net), 0)

    def test_binary_maps_reach_shared_encoders_without_division_by_255(self):
        seen = {}
        encoder = self.policy.features_extractor.encoder

        def capture(name):
            def hook(module, inputs):
                seen[name] = inputs[0].detach().clone()
            return hook

        hooks = [encoder.global_encoder[0].register_forward_pre_hook(capture("global_map")),
                 encoder.local_encoder[0].register_forward_pre_hook(capture("local_maps"))]
        try:
            with torch.no_grad():
                features = self.policy.extract_features(self.tensors())
        finally:
            for hook in hooks:
                hook.remove()
        self.assertEqual(tuple(features.shape), (1, 256))
        expected_global = torch.as_tensor(self.observation["global_map"]).float().unsqueeze(0)
        expected_local = torch.as_tensor(self.observation["local_maps"]).float()
        torch.testing.assert_close(seen["global_map"], expected_global, rtol=0, atol=0)
        torch.testing.assert_close(seen["local_maps"], expected_local, rtol=0, atol=0)
        self.assertEqual(seen["global_map"].max().item(), 1.)

    def test_shared_encoder_preserves_probe_weights_and_features(self):
        probe = MR3ActorCritic().cpu()
        encoder_state = {name: value for name, value in probe.state_dict().items()
                         if not name.startswith(("actor.", "critic."))}
        encoder = self.policy.features_extractor.encoder
        encoder.load_state_dict(encoder_state, strict=True)
        self.policy.action_net.load_state_dict(probe.actor.state_dict())
        self.policy.value_net.load_state_dict(probe.critic.state_dict())
        tensors = self.tensors()
        with torch.no_grad():
            expected_logits, expected_value = probe(tensors)
            features = self.policy.extract_features(tensors)
            logits = self.policy.action_net(features).masked_fill(
                ~tensors["action_mask"].bool(), -torch.inf)
            values = self.policy.value_net(features).flatten()
        torch.testing.assert_close(logits, expected_logits, rtol=0, atol=0)
        torch.testing.assert_close(values, expected_value, rtol=0, atol=0)
        self.assertEqual(sum(p.numel() for p in encoder.parameters()),
                         sum(p.numel() for p in MR3Encoder().parameters()))

    def test_mask_is_distribution_metadata_and_no_private_inputs_are_accepted(self):
        altered = copy.deepcopy(self.observation)
        altered["action_mask"][:] = 1
        with torch.no_grad():
            before = self.policy.extract_features(self.tensors())
            after = self.policy.extract_features(self.tensors(altered))
        torch.testing.assert_close(before, after, rtol=0, atol=0)
        space = observation_space()
        space.spaces["truth"] = gym.spaces.Box(0, 1, shape=(2,), dtype=np.float32)
        with self.assertRaisesRegex(ValueError, "exactly"):
            MR3FeaturesExtractor(space)
        tensors = self.tensors()
        tensors["info"] = torch.zeros(1, 1)
        with self.assertRaisesRegex(ValueError, "frozen observation keys"):
            self.policy.features_extractor(tensors)

    def test_joint_distribution_never_samples_masked_actions(self):
        with torch.no_grad():
            distribution = self.policy.get_distribution(
                self.tensors(), action_masks=self.mask[np.newaxis])
            probabilities = distribution.distribution.probs
            self.assertEqual(tuple(probabilities.shape), (1, 1000))
            self.assertEqual(probabilities[0, ~self.mask].count_nonzero().item(), 0)
            self.assertAlmostEqual(probabilities.sum().item(), 1., places=6)
            for _ in range(32):
                action = distribution.get_actions().item()
                self.assertTrue(self.mask[action])

    def test_rollout_retains_sampling_mask_and_exact_old_log_probability(self):
        buffer = MaskableDictRolloutBuffer(
            2, observation_space(), gym.spaces.Discrete(1000), device="cpu", n_envs=1)
        source_observation = copy.deepcopy(self.observation)
        source_mask = self.mask.copy()
        for index in range(2):
            source_observation["action_mask"] = source_mask.astype(np.int8)
            tensors = self.tensors(source_observation)
            with torch.no_grad():
                actions, values, log_probability = self.policy(
                    tensors, action_masks=source_mask[np.newaxis])
            buffer.add(
                {key: value[np.newaxis] for key, value in source_observation.items()},
                actions.cpu().numpy(), np.array([1.], dtype=np.float32),
                np.array([index == 0]), values, log_probability,
                action_masks=source_mask[np.newaxis])
            if index == 0:
                # A later state has a different candidate/mask. Neither the
                # source array nor a future mask can rewrite the saved sample.
                source_mask[:] = False
                source_mask[np.flatnonzero(self.mask)[0]] = True
        source_mask[:] = False
        source_observation["action_mask"][:] = 0
        buffer.compute_returns_and_advantage(torch.zeros(1), np.array([True]))
        self.assertEqual(buffer.action_masks[0, 0].astype(bool).tolist(), self.mask.tolist())
        sample = next(buffer.get(batch_size=2))
        with torch.no_grad():
            _, reevaluated, _ = self.policy.evaluate_actions(
                sample.observations, sample.actions.flatten().long(),
                action_masks=sample.action_masks)
        torch.testing.assert_close(reevaluated, sample.old_log_prob, rtol=1e-6, atol=1e-6)
        np.testing.assert_array_equal(sample.observations["action_mask"].numpy().astype(bool),
                                      sample.action_masks.numpy().astype(bool))

    def test_actor_critic_and_shared_map_features_receive_finite_gradients_and_update(self):
        observation = {key: np.stack([value, value])
                       for key, value in self.observation.items()}
        observation["task"][1, 0] += .1
        tensors = self.tensors(observation)
        legal = np.flatnonzero(self.mask)
        self.assertGreaterEqual(len(legal), 2)
        actions = torch.as_tensor(legal[:2], dtype=torch.long)
        masks = np.stack([self.mask, self.mask])
        actor_before = self.policy.action_net.weight.detach().clone()
        critic_before = self.policy.value_net.weight.detach().clone()
        map_layer = self.policy.features_extractor.encoder.global_encoder[0]
        map_before = map_layer.weight.detach().clone()
        self.policy.optimizer.zero_grad()
        values, log_probability, entropy = self.policy.evaluate_actions(
            tensors, actions, action_masks=masks)
        advantages = torch.tensor([1., -.5])
        loss = -(log_probability * advantages).mean() + .5 * values.square().mean()
        loss = loss - .01 * entropy.mean()
        loss.backward()
        for layer in (self.policy.action_net, self.policy.value_net, map_layer):
            self.assertTrue(torch.isfinite(layer.weight.grad).all())
            self.assertGreater(layer.weight.grad.abs().sum().item(), 0.)
        self.policy.optimizer.step()
        self.assertFalse(torch.equal(actor_before, self.policy.action_net.weight))
        self.assertFalse(torch.equal(critic_before, self.policy.value_net.weight))
        self.assertFalse(torch.equal(map_before, map_layer.weight))

    def test_algorithm_checkpoint_reloads_same_masked_deterministic_action_and_value(self):
        algorithm = MaskablePPO(
            "MultiInputPolicy", FrozenObservationEnv(), device="cpu", seed=101,
            n_steps=2, batch_size=2, n_epochs=1, policy_kwargs=policy_kwargs())
        expected, _ = algorithm.predict(
            self.observation, deterministic=True, action_masks=self.mask)
        with torch.no_grad():
            tensors = algorithm.policy.obs_to_tensor(self.observation)[0]
            expected_value = algorithm.policy.predict_values(tensors)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "policy"
            algorithm.save(path)
            loaded = MaskablePPO.load(path, device="cpu")
        actual, _ = loaded.predict(
            self.observation, deterministic=True, action_masks=self.mask)
        with torch.no_grad():
            actual_value = loaded.policy.predict_values(tensors)
        np.testing.assert_array_equal(actual, expected)
        self.assertTrue(self.mask[int(actual)])
        torch.testing.assert_close(actual_value, expected_value, rtol=0, atol=0)
        self.assertFalse(loaded.policy.normalize_images)


if __name__ == "__main__":
    unittest.main()
