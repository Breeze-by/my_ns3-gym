"""Small feed-forward CNN/MLP contract probe; no algorithm or training loop."""

import torch
from torch import nn


def _map_encoder(output_size, pool_size):
    # The fixed 128/64 inputs become 32/16 after the two convolutions.
    # Disjoint 8x8/4x4 averages equal adaptive 4x4 pooling on these shapes,
    # avoiding the unsupported deterministic adaptive CUDA backward operation.
    return nn.Sequential(
        nn.Conv2d(3, 16, kernel_size=5, stride=2, padding=2), nn.ReLU(),
        nn.Conv2d(16, 32, kernel_size=3, stride=2, padding=1), nn.ReLU(),
        nn.AvgPool2d(kernel_size=pool_size), nn.Flatten(),
        nn.Linear(512, output_size), nn.ReLU(),
    )


class MR3ActorCritic(nn.Module):
    """Capacity probe for fixed tensors, shared local encoders and 1000-way head."""

    def __init__(self):
        super().__init__()
        self.global_encoder = _map_encoder(128, pool_size=8)
        self.local_encoder = _map_encoder(64, pool_size=4)
        self.robot_encoder = nn.Sequential(nn.Linear(64, 64), nn.ReLU())
        self.candidate_encoder = nn.Sequential(nn.Linear(16, 32), nn.ReLU())
        self.history_encoder = nn.Sequential(nn.Linear(192, 64), nn.ReLU())
        self.task_encoder = nn.Sequential(nn.Linear(12, 32), nn.ReLU())
        self.fusion = nn.Sequential(nn.Linear(864, 256), nn.ReLU())
        self.actor = nn.Linear(256, 1000)
        self.critic = nn.Linear(256, 1)

    def forward(self, observation):
        batch = observation["global_map"].shape[0]
        # The maps are binary flags. Dividing these values by 255 is incorrect.
        local_maps = observation["local_maps"].float().reshape(batch * 3, 3, 64, 64)
        features = torch.cat((
            self.global_encoder(observation["global_map"].float()),
            self.local_encoder(local_maps).reshape(batch, -1),
            self.robot_encoder(observation["robots"]).reshape(batch, -1),
            self.candidate_encoder(observation["candidates"]).reshape(batch, -1),
            self.history_encoder(observation["history"].reshape(batch, -1)),
            self.task_encoder(observation["task"]),
        ), dim=-1)
        latent = self.fusion(features)
        mask = observation["action_mask"].bool()
        if not torch.all(mask.any(dim=-1)):
            raise ValueError("every sample requires at least one legal joint action")
        logits = self.actor(latent).masked_fill(~mask, -torch.inf)
        return logits, self.critic(latent).squeeze(-1)
