"""MaskablePPO policy configuration for the frozen MR3 tensor contract.

Pass ``policy_kwargs()`` to MaskablePPO's ``MultiInputPolicy``. The joint
1000-class actor and centralized scalar value head consume the same 256
features. The collector supplies the saved joint mask to the distribution;
the mask is deliberately excluded from the learned encoder. No info/reward
diagnostics, truth input, adaptive normalization or extra policy MLP is used.
"""

from gymnasium import spaces
from stable_baselines3.common.torch_layers import BaseFeaturesExtractor

from .model import MR3Encoder
from .observation import TENSOR_SCHEMA, observation_space as tensor_space


class MR3FeaturesExtractor(BaseFeaturesExtractor):
    """Reuse the P1C CNN/MLP capacity without SB3's image-intensity scaling."""

    def __init__(self, observation_space):
        if not isinstance(observation_space, spaces.Dict) or observation_space != tensor_space():
            raise ValueError(f"MR3 policy requires exactly {TENSOR_SCHEMA}")
        super().__init__(observation_space, features_dim=MR3Encoder.features_dim)
        self.encoder = MR3Encoder()
        self._input_keys = frozenset(observation_space.spaces)

    def forward(self, observations):
        if frozenset(observations) != self._input_keys:
            raise ValueError("MR3 features accept only the frozen observation keys")
        return self.encoder(observations)


def policy_kwargs():
    """Fresh SB3 kwargs: fixed scaling, shared features and direct output heads."""
    return {
        "features_extractor_class": MR3FeaturesExtractor,
        "normalize_images": False,
        "share_features_extractor": True,
        "net_arch": [],
    }
